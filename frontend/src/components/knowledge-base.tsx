"use client";
import { useCallback, useEffect, useState } from "react";
import {
  BookOpen,
  FileUp,
  Plus,
  LoaderCircle,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Locale } from "@/lib/i18n";

type Document = {
  id: string;
  title: string;
  source_type: "text" | "txt" | "pdf" | "url";
  filename: string | null;
  created_at: string;
  status: string;
  stage: string;
  chunk_count: number;
  error_code: string | null;
  text?: string;
  embedded_chunk_count?: number;
};
const messages = {
  en: {
    title: "Bring your expertise",
    description:
      "Add notes, product information, or brand stories. Your text is stored privately and prepared for future post generation.",
    label: "Source title",
    text: "Paste your text",
    titleHint: "For example: Our services and approach",
    textHint: "Add the knowledge you want your posts to draw from…",
    add: "Add to Knowledge Base",
    adding: "Adding…",
    saved: "Text saved. Preparation is queued.",
    duplicate:
      "This text is already in your Knowledge Base. No new source was added.",
    empty: "No sources yet. Add your first text above.",
    sources: "Your sources",
    loading: "Loading sources…",
    error:
      "We couldn’t complete that request. Your unsaved text is still here. Please try again.",
    refresh: "Refresh",
    pending: "Queued",
    processing: "Processing",
    prepared: "Text prepared",
    failed: "Preparation failed",
    ready: "Ready",
    embeddingNote:
      "Text preparation is available now. AI search and generation will become available after embeddings are connected.",
    chunks: "chunks",
    embed: "Enable AI search",
    embedding: "Preparing AI search",
    embeddingFailed: "AI search preparation failed",
    connectionMissing:
      "AI search is not connected yet. Your saved text will remain available.",
    connectionReady: "AI search can now be enabled for prepared sources.",
    embeddingError:
      "AI search preparation did not finish. Please retry or check the provider connection.",
    embedded: "prepared for AI search",
    retry: "Process again",
    remove: "Delete",
    confirm: "Delete this source and its prepared text?",
    yes: "Delete source",
    cancel: "Cancel",
    view: "View text",
    close: "Close text",
    limit: "Up to 100,000 characters.",
    upload: "Upload a file",
    fileLabel: "PDF or text file",
    uploadTitle: "File title (optional)",
    uploadTitleHint: "Defaults to the file name",
    uploadLimit: (size: string, pages: number) =>
      `PDF, TXT or Markdown (UTF-8), up to ${size} and ${pages} pages. Scanned PDFs need text recognition (OCR) first. Web links come later.`,
    uploadButton: "Upload file",
    uploadGeneric: "The upload didn’t finish. Please try again.",
    uploading: "Uploading",
    uploaded: "File uploaded. Preparation is queued.",
    uploadDuplicate:
      "This file is already in your Knowledge Base. No new source was added.",
    chooseFile: "Choose a file to upload.",
    typePasted: "Pasted text",
    typeTxt: "Text file",
    typePdf: "PDF",
    typeUrl: "Web link",
    added: "Added",
    uploadErrors: {
      file_too_large: "The file is larger than the upload limit.",
      file_type_unsupported: "Only PDF, TXT and Markdown files are supported.",
      file_signature_mismatch:
        "The file’s contents don’t match its type. Check that it is a real PDF or text file.",
      file_not_utf8:
        "The text file isn’t UTF-8. Save it as UTF-8 and upload it again.",
      file_not_text: "This doesn’t look like a text file.",
      source_empty: "The file is empty.",
      source_too_long: "The file has more text than a source may hold.",
      file_name_invalid: "The file name can’t be used. Rename the file.",
      storage_failed: "The file couldn’t be stored. Please try again.",
    } as Record<string, string>,
    processingErrors: {
      pdf_requires_ocr:
        "This PDF has no text layer (it looks scanned). Run text recognition (OCR) and upload it again.",
      pdf_encrypted:
        "This PDF is password-protected. Remove the protection and upload it again.",
      pdf_corrupt: "This PDF couldn’t be read. It may be damaged.",
      pdf_too_many_pages: "This PDF has more pages than allowed.",
      source_too_long: "This source has more text than a source may hold.",
      source_empty: "No text was found in this source.",
      source_file_missing:
        "The stored file is missing. Delete this source and upload it again.",
    } as Record<string, string>,
    next: "Older sources",
    previous: "Newer sources",
    deleted: "Source deleted.",
    dispatch: "The processing service could not be reached. Try Process again.",
    failure: "Processing did not finish. Try Process again.",
    invalid: "Enter a title and some text.",
  },
  he: {
    title: "מוסיפים את המומחיות שלך",
    description:
      "מוסיפים הערות, מידע על מוצרים או סיפורי מותג. הטקסט נשמר באופן פרטי ומוכן ליצירת פוסטים בהמשך.",
    label: "כותרת המקור",
    text: "הדבקת טקסט",
    titleHint: "למשל: השירותים והגישה שלנו",
    textHint: "כאן מוסיפים את הידע שעליו יתבססו הפוסטים שלך…",
    add: "הוספה למאגר הידע",
    adding: "מוסיף…",
    saved: "הטקסט נשמר ונשלח להכנה.",
    duplicate: "הטקסט הזה כבר נמצא במאגר הידע. לא נוסף מקור חדש.",
    empty: "עדיין אין מקורות. אפשר להוסיף את הטקסט הראשון למעלה.",
    sources: "המקורות שלך",
    loading: "טוען מקורות…",
    error:
      "לא הצלחנו להשלים את הבקשה. הטקסט שלא נשמר עדיין כאן. אפשר לנסות שוב.",
    refresh: "רענון",
    pending: "בתור",
    processing: "בעיבוד",
    prepared: "הטקסט מוכן",
    failed: "ההכנה נכשלה",
    ready: "מוכן",
    embeddingNote:
      "אפשר כבר להכין טקסטים. חיפוש ויצירה באמצעות AI יהיו זמינים לאחר חיבור שירות ההטמעות.",
    chunks: "מקטעים",
    embed: "הפעלת חיפוש AI",
    embedding: "מכין חיפוש AI",
    embeddingFailed: "הכנת חיפוש AI נכשלה",
    connectionMissing: "חיפוש AI עדיין לא מחובר. הטקסטים שנשמרו יישארו זמינים.",
    connectionReady: "אפשר כעת להפעיל חיפוש AI למקורות שהוכנו.",
    embeddingError:
      "הכנת חיפוש AI לא הסתיימה. אפשר לנסות שוב או לבדוק את החיבור לספק.",
    embedded: "מוכנים לחיפוש AI",
    retry: "ניסיון עיבוד נוסף",
    remove: "מחיקה",
    confirm: "למחוק את המקור ואת המקטעים שהוכנו ממנו?",
    yes: "מחיקת המקור",
    cancel: "ביטול",
    view: "הצגת הטקסט",
    close: "סגירת הטקסט",
    limit: "עד 100,000 תווים.",
    upload: "העלאת קובץ",
    fileLabel: "קובץ PDF או טקסט",
    uploadTitle: "כותרת לקובץ (לא חובה)",
    uploadTitleHint: "ברירת המחדל היא שם הקובץ",
    uploadLimit: (size: string, pages: number) =>
      `סוגי קבצים: PDF,‏ TXT או Markdown בקידוד UTF-8, עד ⁦${size}⁩ ו־${pages} עמודים. קובצי PDF סרוקים צריכים לעבור קודם זיהוי טקסט (OCR). קישורים יתווספו בהמשך.`,
    uploadButton: "העלאת הקובץ",
    uploadGeneric: "ההעלאה לא הסתיימה. אפשר לנסות שוב.",
    uploading: "מעלה",
    uploaded: "הקובץ הועלה ונשלח להכנה.",
    uploadDuplicate: "הקובץ הזה כבר נמצא במאגר הידע. לא נוסף מקור חדש.",
    chooseFile: "יש לבחור קובץ להעלאה.",
    typePasted: "טקסט מודבק",
    typeTxt: "קובץ טקסט",
    typePdf: "PDF",
    typeUrl: "קישור",
    added: "נוסף",
    uploadErrors: {
      file_too_large: "הקובץ גדול ממגבלת ההעלאה.",
      file_type_unsupported: "אפשר להעלות רק קובצי PDF,‏ TXT ו־Markdown.",
      file_signature_mismatch:
        "תוכן הקובץ לא תואם לסוג שלו. כדאי לבדוק שזה באמת קובץ PDF או קובץ טקסט.",
      file_not_utf8:
        "קובץ הטקסט לא בקידוד UTF-8. יש לשמור אותו כ־UTF-8 ולהעלות שוב.",
      file_not_text: "הקובץ לא נראה כמו קובץ טקסט.",
      source_empty: "הקובץ ריק.",
      source_too_long: "בקובץ יש יותר טקסט ממה שמקור יכול להכיל.",
      file_name_invalid: "אי אפשר להשתמש בשם הקובץ. יש לשנות את שמו.",
      storage_failed: "לא הצלחנו לשמור את הקובץ. אפשר לנסות שוב.",
    } as Record<string, string>,
    processingErrors: {
      pdf_requires_ocr:
        "בקובץ ה־PDF אין שכבת טקסט (נראה שהוא סרוק). יש להריץ זיהוי טקסט (OCR) ולהעלות שוב.",
      pdf_encrypted: "קובץ ה־PDF מוגן בסיסמה. יש להסיר את ההגנה ולהעלות שוב.",
      pdf_corrupt: "לא הצלחנו לקרוא את קובץ ה־PDF. ייתכן שהוא פגום.",
      pdf_too_many_pages: "בקובץ ה־PDF יש יותר עמודים מהמותר.",
      source_too_long: "במקור הזה יש יותר טקסט ממה שמקור יכול להכיל.",
      source_empty: "לא נמצא טקסט במקור הזה.",
      source_file_missing:
        "הקובץ השמור חסר. יש למחוק את המקור ולהעלות אותו שוב.",
    } as Record<string, string>,
    next: "מקורות קודמים",
    previous: "מקורות חדשים יותר",
    deleted: "המקור נמחק.",
    dispatch: "לא ניתן היה להתחבר לשירות העיבוד. אפשר לנסות לעבד שוב.",
    failure: "העיבוד לא הסתיים. אפשר לנסות שוב.",
    invalid: "יש להזין כותרת וטקסט.",
  },
};
const DEFAULT_LIMITS = { bytes: 10 * 1024 * 1024, pages: 300 };
const FILE_EXTENSIONS = [".pdf", ".txt", ".md"];
const megabytes = (bytes: number) =>
  `${Math.round((bytes / 1024 / 1024) * 10) / 10} MB`;
export function KnowledgeBase({ locale }: { locale: Locale }) {
  const t = messages[locale];
  const [connected, setConnected] = useState(false);
  const [limits, setLimits] = useState(DEFAULT_LIMITS);
  useEffect(() => {
    fetch("/api/knowledge/configuration", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        setConnected(data?.configured === true);
        if (data?.upload_max_bytes && data?.pdf_max_pages)
          setLimits({
            bytes: data.upload_max_bytes,
            pages: data.pdf_max_pages,
          });
      })
      .catch(() => setConnected(false));
  }, []);
  const [file, setFile] = useState<File | null>(null);
  const [fileTitle, setFileTitle] = useState("");
  const [progress, setProgress] = useState<number | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [items, setItems] = useState<Document[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const [notice, setNotice] = useState<
    | "saved"
    | "duplicate"
    | "deleted"
    | "invalid"
    | "uploaded"
    | "uploadDuplicate"
    | null
  >(null);
  const [confirm, setConfirm] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Document | null>(null);
  const load = useCallback(
    async (page = offset) => {
      try {
        const response = await fetch(`/api/knowledge?offset=${page}&limit=20`, {
          cache: "no-store",
        });
        if (!response.ok) throw new Error();
        const data = await response.json();
        setItems(data.items);
        setTotal(data.total);
        setError(false);
      } catch {
        setError(true);
      } finally {
        setLoading(false);
      }
    },
    [offset],
  );
  useEffect(() => {
    setLoading(true);
    void load();
  }, [load]);
  const active = items.some(
    (item) =>
      item.stage !== "text_prepared" &&
      ["Pending", "Processing"].includes(item.status),
  );
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => void load(), 3000);
    return () => clearInterval(timer);
  }, [active, load]);
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!title.trim() || !text.trim()) {
      setNotice("invalid");
      return;
    }
    setBusy("submit");
    setNotice(null);
    setError(false);
    try {
      const response = await fetch("/api/knowledge/text", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, text }),
      });
      if (!response.ok) throw new Error();
      const result = await response.json();
      setTitle("");
      setText("");
      setNotice(result.duplicate ? "duplicate" : "saved");
      setOffset(0);
      await load(0);
    } catch {
      setError(true);
    } finally {
      setBusy(null);
    }
  }
  async function uploadFile(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setNotice(null);
    setUploadError(null);
    if (!file) {
      setUploadError("chooseFile");
      return;
    }
    // The server checks the same limits; checking here saves a pointless upload.
    const extension = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    if (!FILE_EXTENSIONS.includes(extension)) {
      setUploadError("file_type_unsupported");
      return;
    }
    if (file.size > limits.bytes) {
      setUploadError("file_too_large");
      return;
    }
    if (file.size === 0) {
      setUploadError("source_empty");
      return;
    }
    setBusy("upload");
    setProgress(0);
    const query = new URLSearchParams({ filename: file.name });
    if (fileTitle.trim()) query.set("title", fileTitle.trim());
    try {
      // XMLHttpRequest reports upload progress; fetch does not.
      const result = await new Promise<{
        status: number;
        body: {
          duplicate?: boolean;
          error?: { code?: string; message?: string };
        };
      }>((resolve, reject) => {
        const request = new XMLHttpRequest();
        request.open("POST", `/api/knowledge/files?${query}`);
        request.setRequestHeader("Content-Type", "application/octet-stream");
        request.responseType = "json";
        request.upload.onprogress = (e) => {
          if (e.lengthComputable)
            setProgress(Math.round((e.loaded / e.total) * 100));
        };
        request.onload = () =>
          resolve({ status: request.status, body: request.response ?? {} });
        request.onerror = () => reject(new Error("network"));
        request.send(file);
      });
      if (result.status < 200 || result.status >= 300) {
        const code =
          result.body.error?.message ?? result.body.error?.code ?? "";
        setUploadError(code in t.uploadErrors ? code : "generic");
        return;
      }
      form.reset();
      setFile(null);
      setFileTitle("");
      setNotice(result.body.duplicate ? "uploadDuplicate" : "uploaded");
      setOffset(0);
      await load(0);
    } catch {
      setUploadError("generic");
    } finally {
      setBusy(null);
      setProgress(null);
    }
  }
  async function action(
    document: Document,
    kind: "retry" | "delete" | "view" | "embed",
  ) {
    setBusy(document.id);
    setError(false);
    setNotice(null);
    try {
      const response = await fetch(
        `/api/knowledge/${document.id}${kind === "retry" ? "/retry" : kind === "embed" ? "/embed" : ""}`,
        {
          method:
            kind === "delete"
              ? "DELETE"
              : kind === "retry" || kind === "embed"
                ? "POST"
                : "GET",
          cache: "no-store",
        },
      );
      if (!response.ok) throw new Error();
      if (kind === "view") setExpanded(await response.json());
      else {
        setConfirm(null);
        if (kind === "delete") {
          setNotice("deleted");
          if (expanded?.id === document.id) setExpanded(null);
        }
        if (kind === "delete" && items.length === 1 && offset > 0)
          setOffset(Math.max(0, offset - 20));
        else await load();
      }
    } catch {
      setError(true);
    } finally {
      setBusy(null);
    }
  }
  const sourceType = (item: Document) =>
    ({
      text: t.typePasted,
      txt: t.typeTxt,
      pdf: t.typePdf,
      url: t.typeUrl,
    })[item.source_type] ?? t.typePasted;
  const status = (item: Document) =>
    item.stage === "embedding_failed"
      ? t.embeddingFailed
      : ["embedding", "embedding_pending"].includes(item.stage)
        ? t.embedding
        : item.stage === "text_prepared"
          ? t.prepared
          : item.status === "Failed"
            ? t.failed
            : item.status === "Ready"
              ? t.ready
              : item.status === "Processing"
                ? t.processing
                : t.pending;
  return (
    <section aria-labelledby="knowledge-title" className="mt-10 space-y-6">
      <div className="rounded-2xl border border-border bg-card p-6 sm:p-9">
        <BookOpen size={25} className="mb-5 text-primary" />
        <h2 id="knowledge-title" className="text-2xl font-semibold">
          {t.title}
        </h2>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
          {t.description}
        </p>
        <form onSubmit={submit} className="mt-7 space-y-5">
          <fieldset disabled={busy === "submit"} className="space-y-5">
            <div>
              <label
                htmlFor="source-title"
                className="mb-2 block text-sm font-medium"
              >
                {t.label}
              </label>
              <input
                id="source-title"
                required
                maxLength={300}
                value={title}
                dir={title ? "auto" : locale === "he" ? "rtl" : "ltr"}
                onChange={(e) => setTitle(e.target.value)}
                placeholder={t.titleHint}
                className="h-11 w-full rounded-lg border border-border bg-background px-3 text-start text-sm focus-visible:outline-2 focus-visible:outline-primary"
              />
            </div>
            <div>
              <label
                htmlFor="source-text"
                className="mb-2 block text-sm font-medium"
              >
                {t.text}
              </label>
              <textarea
                id="source-text"
                required
                maxLength={100000}
                rows={8}
                value={text}
                dir={text ? "auto" : locale === "he" ? "rtl" : "ltr"}
                onChange={(e) => setText(e.target.value)}
                placeholder={t.textHint}
                aria-describedby="source-limit"
                className="w-full resize-y rounded-lg border border-border bg-background p-3 text-start text-sm leading-6 focus-visible:outline-2 focus-visible:outline-primary"
              />
              <p
                id="source-limit"
                className="mt-2 text-xs text-muted-foreground"
              >
                {t.limit}
              </p>
            </div>
          </fieldset>
          <Button type="submit" disabled={busy !== null}>
            {busy === "submit" ? (
              <LoaderCircle size={16} className="animate-spin" />
            ) : (
              <Plus size={16} />
            )}
            {busy === "submit" ? t.adding : t.add}
          </Button>
        </form>
        <form
          onSubmit={uploadFile}
          className="mt-8 space-y-5 border-t border-border pt-7"
          aria-labelledby="upload-title-heading"
        >
          <h3 id="upload-title-heading" className="font-semibold">
            {t.upload}
          </h3>
          <fieldset disabled={busy === "upload"} className="space-y-5">
            <div>
              <label
                htmlFor="source-file"
                className="mb-2 block text-sm font-medium"
              >
                {t.fileLabel}
              </label>
              <input
                id="source-file"
                type="file"
                accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown"
                aria-describedby="upload-limit"
                aria-invalid={uploadError !== null}
                onChange={(e) => {
                  setFile(e.target.files?.[0] ?? null);
                  setUploadError(null);
                }}
                className="block w-full max-w-full text-sm file:me-3 file:rounded-lg file:border file:border-border file:bg-background file:px-3 file:py-2 file:text-sm"
              />
              <p
                id="upload-limit"
                className="mt-2 text-xs leading-5 text-muted-foreground"
              >
                {t.uploadLimit(megabytes(limits.bytes), limits.pages)}
              </p>
            </div>
            <div>
              <label
                htmlFor="upload-title"
                className="mb-2 block text-sm font-medium"
              >
                {t.uploadTitle}
              </label>
              <input
                id="upload-title"
                maxLength={300}
                value={fileTitle}
                dir={fileTitle ? "auto" : locale === "he" ? "rtl" : "ltr"}
                onChange={(e) => setFileTitle(e.target.value)}
                placeholder={t.uploadTitleHint}
                className="h-11 w-full rounded-lg border border-border bg-background px-3 text-start text-sm focus-visible:outline-2 focus-visible:outline-primary"
              />
            </div>
          </fieldset>
          {progress !== null && (
            <div>
              <div
                role="progressbar"
                aria-label={t.uploading}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={progress}
                className="h-2 w-full overflow-hidden rounded-full bg-muted"
              >
                <div
                  className="h-full bg-primary transition-[width]"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                {t.uploading} {progress}%
              </p>
            </div>
          )}
          {uploadError && (
            <p role="alert" className="text-sm text-red-800">
              {uploadError === "chooseFile"
                ? t.chooseFile
                : (t.uploadErrors[uploadError] ?? t.uploadGeneric)}
            </p>
          )}
          <Button type="submit" disabled={busy !== null}>
            {busy === "upload" ? (
              <LoaderCircle size={16} className="animate-spin" />
            ) : (
              <FileUp size={16} />
            )}
            {t.uploadButton}
          </Button>
        </form>
        <p className="mt-5 text-xs leading-6 text-muted-foreground">
          {connected ? t.connectionReady : t.connectionMissing}
        </p>
      </div>
      {error && (
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800"
        >
          {t.error}
          <Button
            variant="outline"
            size="sm"
            className="ms-3"
            onClick={() => void load()}
          >
            {t.refresh}
          </Button>
        </div>
      )}
      <p role="status" className="text-sm text-primary">
        {notice ? t[notice] : ""}
      </p>
      <div className="rounded-2xl border border-border bg-card p-6 sm:p-9">
        <div className="mb-6 flex items-center justify-between gap-3">
          <h3 className="text-lg font-semibold">
            {t.sources} <span className="text-muted-foreground">({total})</span>
          </h3>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => void load()}
          >
            <RefreshCw size={16} />
            {t.refresh}
          </Button>
        </div>
        {loading ? (
          <p role="status">{t.loading}</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t.empty}</p>
        ) : (
          <ul className="space-y-4">
            {items.map((item) => (
              <li key={item.id} className="rounded-xl border border-border p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h4
                    dir="auto"
                    className="min-w-0 max-w-full break-words font-medium"
                  >
                    {item.title}
                  </h4>
                  <span className="rounded-full bg-primary/10 px-3 py-1 text-xs text-primary">
                    {status(item)}
                  </span>
                </div>
                <p className="mt-2 text-xs text-muted-foreground">
                  {sourceType(item)}
                  {item.filename && (
                    <>
                      {" · "}
                      <bdi>{item.filename}</bdi>
                    </>
                  )}
                  {!Number.isNaN(Date.parse(item.created_at)) && (
                    <>
                      {" · "}
                      {t.added}{" "}
                      <time dateTime={item.created_at}>
                        {new Intl.DateTimeFormat(locale, {
                          dateStyle: "medium",
                          timeStyle: "short",
                        }).format(new Date(item.created_at))}
                      </time>
                    </>
                  )}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {item.chunk_count} {t.chunks}
                  {item.embedded_chunk_count
                    ? ` · ${item.embedded_chunk_count} ${t.embedded}`
                    : ""}
                </p>
                {item.error_code && (
                  <p className="mt-3 text-sm text-red-800">
                    {item.stage === "embedding_failed"
                      ? t.embeddingError
                      : item.error_code === "dispatch_failed"
                        ? t.dispatch
                        : (t.processingErrors[item.error_code] ?? t.failure)}
                  </p>
                )}
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={busy !== null}
                    onClick={() =>
                      expanded?.id === item.id
                        ? setExpanded(null)
                        : void action(item, "view")
                    }
                  >
                    {expanded?.id === item.id ? t.close : t.view}
                  </Button>
                  {item.stage !== "text_prepared" &&
                    !item.stage.startsWith("embedding") &&
                    item.status !== "Ready" && (
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={busy !== null}
                        onClick={() => void action(item, "retry")}
                      >
                        <RefreshCw size={14} />
                        {t.retry}
                      </Button>
                    )}
                  {item.chunk_count > 0 && item.status !== "Ready" && (
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={busy !== null || !connected}
                      onClick={() => void action(item, "embed")}
                    >
                      {t.embed}
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={busy !== null}
                    onClick={() => setConfirm(item.id)}
                  >
                    <Trash2 size={14} />
                    {t.remove}
                  </Button>
                </div>
                {expanded?.id === item.id && (
                  <p
                    dir="auto"
                    className="mt-4 max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-background p-4 text-sm leading-7"
                  >
                    {expanded.text}
                  </p>
                )}
                {confirm === item.id && (
                  <div className="mt-4 rounded-lg bg-muted p-4">
                    <p className="mb-3 text-sm">{t.confirm}</p>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        disabled={busy !== null}
                        onClick={() => void action(item, "delete")}
                      >
                        {t.yes}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setConfirm(null)}
                      >
                        {t.cancel}
                      </Button>
                    </div>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
        {(total > 20 || offset > 0) && (
          <div className="mt-5 flex gap-3">
            <Button
              variant="outline"
              disabled={offset === 0 || loading}
              onClick={() => setOffset(Math.max(0, offset - 20))}
            >
              {t.previous}
            </Button>
            <Button
              variant="outline"
              disabled={offset + 20 >= total || loading}
              onClick={() => setOffset(offset + 20)}
            >
              {t.next}
            </Button>
          </div>
        )}
      </div>
    </section>
  );
}
