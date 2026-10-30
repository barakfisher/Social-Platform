from io import BytesIO
from unittest.mock import patch
from uuid import UUID

import pytest
from pypdf import PdfReader, PdfWriter
from sqlalchemy import select

from app import storage
from app.config import get_settings
from app.extraction import ExtractionError, extract_pdf, page_range
from app.models import IngestionJob, KnowledgeChunk, KnowledgeDocument
from app.worker import process_text

OCTET = {"Content-Type": "application/octet-stream"}


def pdf(*pages: str) -> bytes:
    """A minimal valid PDF with one line of Helvetica text per page ('' for no text)."""
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b""]
    kids = []
    for text in pages:
        content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode() if text else b""
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content))
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents %d 0 R"
            b" /Resources << /Font << /F1 << /Type /Font /Subtype /Type1"
            b" /BaseFont /Helvetica >> >> >> >>" % len(objects)
        )
        kids.append(b"%d 0 R" % len(objects))
    objects[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (b" ".join(kids), len(kids))
    out = BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n%s\nendobj\n" % (number, body))
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(
        b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    )
    return out.getvalue()


def encrypted(data: bytes, user_password: str) -> bytes:
    writer = PdfWriter(clone_from=PdfReader(BytesIO(data)))
    writer.encrypt(user_password, owner_password="owner", algorithm="RC4-128")
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


@pytest.fixture
def private_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "source_storage_dir", str(tmp_path / "sources"))
    return tmp_path / "sources"


def upload(client, data: bytes, filename: str, **params):
    return client.post(
        "/knowledge/files", params={"filename": filename, **params}, content=data, headers=OCTET
    )


def job_for(factory, document_id):
    with factory() as session:
        return str(
            session.scalar(
                select(IngestionJob.id).where(IngestionJob.document_id == UUID(document_id))
            )
        )


def stored_files(directory):
    return sorted(p.name for p in directory.iterdir()) if directory.exists() else []


def test_pdf_pages_keep_their_numbers_and_skip_textless_pages():
    text, pages = extract_pdf(pdf("Garden notes", "", "Volunteer evenings"))
    assert text == "Garden notes\n\nVolunteer evenings"
    assert pages == [(0, 1), (14, 3)]
    assert page_range(pages, 0, 5) == {"page_start": 1, "page_end": 1}
    assert page_range(pages, 3, 20) == {"page_start": 1, "page_end": 3}
    assert page_range(pages, 14, len(text)) == {"page_start": 3, "page_end": 3}


@pytest.mark.parametrize(
    "data,code",
    [
        (pdf("", ""), "pdf_requires_ocr"),
        (encrypted(pdf("Secret"), "user-secret"), "pdf_encrypted"),
        (b"%PDF-1.4\nthis is not a pdf body", "pdf_corrupt"),
        (pdf("Truncated")[:60], "pdf_corrupt"),
    ],
)
def test_pdf_failures_have_actionable_codes(data, code):
    with pytest.raises(ExtractionError) as raised:
        extract_pdf(data)
    assert raised.value.code == code


def test_owner_password_only_pdf_opens():
    assert extract_pdf(encrypted(pdf("Open to read"), ""))[0] == "Open to read"


def test_pdf_limits(monkeypatch):
    monkeypatch.setattr(get_settings(), "pdf_max_pages", 2)
    with pytest.raises(ExtractionError, match="pdf_too_many_pages"):
        extract_pdf(pdf("a", "b", "c"))
    monkeypatch.setattr(get_settings(), "pdf_max_pages", 300)
    monkeypatch.setattr(get_settings(), "source_max_characters", 1000)
    with pytest.raises(ExtractionError, match="source_too_long"):
        extract_pdf(pdf("x" * 600, "y" * 600))


def test_storage_keys_are_opaque_private_and_validated(private_dir):
    key = storage.put(b"private bytes")
    assert len(key) == 32 and stored_files(private_dir) == [key]
    assert (private_dir / key).stat().st_mode & 0o777 == 0o600
    assert storage.read(key) == b"private bytes"
    for bad in ["../etc/passwd", "A" * 32, key + "0", ""]:
        with pytest.raises(storage.StorageError):
            storage.read(bad)
    storage.remove(key)
    storage.remove(key)
    with pytest.raises(storage.StorageError, match="source_file_missing"):
        storage.read(key)


def test_pdf_upload_extracts_pages_deduplicates_and_deletes_the_file(api, private_dir):
    client, factory, dispatch = api
    data = pdf("Community garden herbs", "Volunteer evenings on Tuesdays")
    response = upload(client, data, "C:\\Users\\me\\Garden Guide.pdf")
    assert response.status_code == 202
    result = response.json()
    assert result["source_type"] == "pdf"
    assert result["filename"] == "Garden Guide.pdf"
    assert result["title"] == "Garden Guide"
    assert result["duplicate"] is False and result["status"] == "Pending"
    job_id = job_for(factory, result["id"])
    dispatch.assert_called_once_with(args=[job_id], task_id=job_id)
    [key] = stored_files(private_dir)
    assert (private_dir / key).read_bytes() == data

    duplicate = upload(client, data, "copy.pdf", title="Another title").json()
    assert duplicate["id"] == result["id"] and duplicate["duplicate"] is True
    assert stored_files(private_dir) == [key]
    assert dispatch.call_count == 1

    process_text(job_id)
    process_text(job_id)
    prepared = client.get(result["status_url"]).json()
    assert prepared["stage"] == "text_prepared"
    assert prepared["text"] == "Community garden herbs\n\nVolunteer evenings on Tuesdays"
    with factory() as session:
        [chunk] = session.scalars(select(KnowledgeChunk)).all()
        assert chunk.source_location["page_start"] == 1
        assert chunk.source_location["page_end"] == 2

    assert client.delete(result["status_url"]).status_code == 200
    assert stored_files(private_dir) == []
    process_text(job_id)  # A queued delivery cannot recreate deleted content.
    assert client.get(result["status_url"]).status_code == 404


def test_text_file_upload_is_decoded_at_submission(api, private_dir):
    client, factory, _ = api
    data = "\ufeffכותרת\r\n\r\nEnglish and עברית".encode()
    result = upload(client, data, "notes.md", title="  הערות  ").json()
    assert result["source_type"] == "txt" and result["title"] == "הערות"
    assert client.get(result["status_url"]).json()["text"] == "כותרת\n\nEnglish and עברית"
    process_text(job_for(factory, result["id"]))
    assert client.get(result["status_url"]).json()["stage"] == "text_prepared"
    # Pasted text with the same content is a separate source type, not a duplicate.
    pasted = client.post(
        "/knowledge/text", json={"title": "t", "text": "כותרת\n\nEnglish and עברית"}
    )
    assert pasted.json()["duplicate"] is False


def test_scanned_pdf_fails_with_ocr_code_and_can_be_retried(api, private_dir):
    client, factory, dispatch = api
    result = upload(client, pdf(""), "scan.pdf").json()
    job_id = job_for(factory, result["id"])
    process_text(job_id)
    failed = client.get(result["status_url"]).json()
    assert failed["status"] == "Failed" and failed["error_code"] == "pdf_requires_ocr"
    assert failed["chunk_count"] == 0
    assert client.post(f"{result['status_url']}/retry").status_code == 202
    assert dispatch.call_count == 2


def test_missing_stored_file_fails_the_job(api, private_dir):
    client, factory, _ = api
    result = upload(client, pdf("Lost"), "lost.pdf").json()
    for name in stored_files(private_dir):
        (private_dir / name).unlink()
    process_text(job_for(factory, result["id"]))
    assert client.get(result["status_url"]).json()["error_code"] == "source_file_missing"


@pytest.mark.parametrize(
    "data,filename,status,code",
    [
        (b"%PDF-1.4", "notes.exe", 415, "file_type_unsupported"),
        (b"plain", "notes", 415, "file_type_unsupported"),
        (b"MZ not a pdf", "notes.pdf", 422, "file_signature_mismatch"),
        (b"%PDF-1.4 in a text file", "notes.txt", 422, "file_signature_mismatch"),
        (b"\xff\xfe\x00h\x00i", "notes.txt", 422, "file_not_utf8"),
        (b"bin\x00ary", "notes.txt", 422, "file_not_text"),
        (b"  \r\n ", "notes.txt", 422, "source_empty"),
        (b"", "notes.pdf", 422, "source_empty"),
        (b"%PDF-1.4", "\x00\x01", 422, "file_name_invalid"),
        (b"%PDF-1.4", "../../", 422, "file_name_invalid"),
    ],
)
def test_invalid_uploads_store_and_dispatch_nothing(api, private_dir, data, filename, status, code):
    client, factory, dispatch = api
    response = upload(client, data, filename)
    assert response.status_code == status
    assert response.json()["error"]["message"] == code
    dispatch.assert_not_called()
    assert stored_files(private_dir) == []
    with factory() as session:
        assert session.scalar(select(KnowledgeDocument.id)) is None


def test_oversized_upload_is_refused_before_storage(api, private_dir, monkeypatch):
    client, _, dispatch = api
    monkeypatch.setattr(get_settings(), "upload_max_bytes", 1024)
    response = upload(client, b"%PDF-" + b"x" * 1024, "big.pdf")
    assert response.status_code == 413
    assert response.json()["error"]["message"] == "file_too_large"
    assert stored_files(private_dir) == []
    dispatch.assert_not_called()


def test_storage_failure_creates_no_document(api, private_dir):
    client, factory, dispatch = api
    with patch("app.storage.put", side_effect=storage.StorageError("storage_failed")):
        response = upload(client, pdf("x"), "x.pdf")
    assert response.status_code == 503
    assert response.json()["error"]["message"] == "storage_failed"
    dispatch.assert_not_called()
    with factory() as session:
        assert session.scalar(select(KnowledgeDocument.id)) is None


def test_database_failure_removes_the_stored_file(api, private_dir):
    client, _, dispatch = api
    with patch("app.knowledge.seed_local_scope", side_effect=RuntimeError("database down")):
        response = upload(client, pdf("x"), "x.pdf")
    assert response.status_code == 500
    assert stored_files(private_dir) == []
    dispatch.assert_not_called()


def test_dispatch_failure_keeps_the_file_for_retry(api, private_dir):
    client, factory, dispatch = api
    dispatch.side_effect = ConnectionError("broker down")
    result = upload(client, pdf("Durable"), "durable.pdf").json()
    assert result["status"] == "Failed" and result["error_code"] == "dispatch_failed"
    assert len(stored_files(private_dir)) == 1
    dispatch.side_effect = None
    assert client.post(f"{result['status_url']}/retry").status_code == 202
    process_text(job_for(factory, result["id"]))
    assert client.get(result["status_url"]).json()["text"] == "Durable"
