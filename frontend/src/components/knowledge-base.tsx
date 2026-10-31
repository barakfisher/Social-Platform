"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  BookOpen,
  FileUp,
  Link2,
  Plus,
  LoaderCircle,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Locale } from "@/lib/i18n";

type Changes = {
  added: string[];
  removed: string[];
  added_count: number;
  removed_count: number;
};
// Knowledge is drawn on for facts; sample posts are the owner's finished posts (SP-29).
type DocumentKind = "knowledge" | "sample_posts";
const KINDS: DocumentKind[] = ["knowledge", "sample_posts"];
type Document = {
  id: string;
  title: string;
  kind: DocumentKind;
  source_type: "text" | "txt" | "pdf" | "url";
  filename: string | null;
  url?: string | null;
  fetched_at?: string | null;
  refresh_result?: "unchanged" | "replaced" | "appended" | "kept" | null;
  refresh?: {
    status: string;
    stage: string;
    error_code: string | null;
    added_count?: number;
    removed_count?: number;
  } | null;
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
    listError:
      "We couldn’t load your sources. Check the connection and try again.",
    error:
      "We couldn’t complete that request. Your unsaved text is still here. Please try again.",
    actionErrors: {
      refresh_in_progress:
        "This page is already loading again. Try again when it finishes.",
      refresh_not_ready:
        "This page can be loaded again once its text is prepared.",
      refresh_not_awaiting:
        "This choice was already made or the reload ended. The list is updated.",
      kind_not_saved:
        "The content type wasn’t changed. It still shows the saved type. Please try again.",
    } as Record<string, string>,
    refresh: "Refresh",
    pending: "Queued",
    processing: "Processing",
    prepared: "Text prepared",
    failed: "Preparation failed",
    ready: "Ready",
    embeddingNote:
      "Text preparation is available now. AI search and generation will become available after embeddings are connected.",
    chunks: "chunks",
    kindLabel: "Content type",
    kinds: { knowledge: "Knowledge", sample_posts: "Sample posts" } as Record<
      DocumentKind,
      string
    >,
    kindHint:
      "Sample posts are posts you already wrote. Topic ideas won’t suggest what they already say.",
    kindSaved: "Content type saved.",
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
    refreshPage: "Load again from the site",
    refreshing: "Loading again…",
    lastLoaded: "Last loaded",
    refreshUnchanged: "No changes since the last load.",
    refreshReplaced: "Replaced with the new version from the site.",
    refreshAppended: "New paragraphs from the site were added.",
    refreshKeptChoice: "Kept the current version.",
    refreshPreparing: "Preparing the new version for AI search…",
    changesFound: (added: number, removed: number) =>
      `The page changed: ${added} new paragraphs, ${removed} no longer on the site. The current version stays in use until you choose.`,
    showChanges: "Show changes",
    hideChanges: "Hide changes",
    newParagraphs: "New on the site",
    removedParagraphs: "No longer on the site",
    more: (count: number) => `…and ${count} more`,
    chooseReplace: "Replace with the new version",
    chooseAppend: "Add the new paragraphs",
    chooseKeep: "Keep the current version",
    choiceHint:
      "Adding keeps everything already saved. When facts conflict, posts use the newest.",
    refreshFailed: "Loading again didn’t finish:",
    refreshKept: "The previous version is still in use.",
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
      `PDF, TXT or Markdown (UTF-8), up to ${size} and ${pages} pages. Scanned PDFs need text recognition (OCR) first.`,
    uploadButton: "Upload file",
    linkHeading: "Add a web page",
    linkLabel: "Page address (URL)",
    linkTitle: "Page title (optional)",
    linkTitleHint: "Defaults to the page’s own title",
    linkLimit:
      "Public web pages only (http or https). The page is fetched in the background; its main text and headings are kept, menus and footers are dropped.",
    linkButton: "Add web page",
    linkAdded: "Web page added. It will be fetched and prepared.",
    linkDuplicate:
      "This web page is already in your Knowledge Base. No new source was added.",
    linkErrors: {
      url_invalid:
        "Enter a full web address, such as https://example.com/page.",
      url_scheme_unsupported: "Only http and https addresses are supported.",
      url_credentials:
        "Remove the user name or password from the address and try again.",
      url_port_unsupported:
        "Only standard web ports are supported. Remove the port number.",
      url_blocked_address:
        "This address points to a private or local network, which can’t be fetched.",
    } as Record<string, string>,
    linkGeneric: "The web page couldn’t be added. Please try again.",
    uploadGeneric: "The upload didn’t finish. Please try again.",
    uploading: "Uploading",
    saving: "Upload complete. Checking and saving the file…",
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
      upload_conflict:
        "A matching file was deleted while this one uploaded. Upload it again.",
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
      url_dns_failed:
        "The site’s address couldn’t be found. Check the link and try Process again.",
      url_blocked_address:
        "This address points to a private or local network, which can’t be fetched.",
      url_timeout: "The site took too long to answer. Try Process again later.",
      url_too_large: "The page is larger than the size limit.",
      url_http_error:
        "The site didn’t return the page (for example, not found or access denied).",
      url_unsupported_type:
        "This link isn’t a web page. To add a PDF, download it and upload the file.",
      url_too_many_redirects: "The link redirects too many times.",
      url_fetch_failed:
        "The site couldn’t be reached. Check the link and try Process again.",
      url_no_content:
        "No readable text was found on this page. Pages that need JavaScript to show their content aren’t supported; paste the text instead.",
      url_parse_failed: "This page couldn’t be read.",
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
    listError: "לא הצלחנו לטעון את המקורות. כדאי לבדוק את החיבור ולנסות שוב.",
    error:
      "לא הצלחנו להשלים את הבקשה. הטקסט שלא נשמר עדיין כאן. אפשר לנסות שוב.",
    actionErrors: {
      refresh_in_progress: "הדף כבר נטען מחדש. אפשר לנסות שוב כשהטעינה תסתיים.",
      refresh_not_ready: "אפשר לטעון את הדף מחדש אחרי שהטקסט שלו הוכן.",
      refresh_not_awaiting:
        "הבחירה כבר נעשתה או שהטעינה מחדש הסתיימה. הרשימה עודכנה.",
      kind_not_saved: "סוג התוכן לא השתנה, ומוצג הסוג השמור. אפשר לנסות שוב.",
    } as Record<string, string>,
    refresh: "רענון",
    pending: "בתור",
    processing: "בעיבוד",
    prepared: "הטקסט מוכן",
    failed: "ההכנה נכשלה",
    ready: "מוכן",
    embeddingNote:
      "אפשר כבר להכין טקסטים. חיפוש ויצירה באמצעות AI יהיו זמינים לאחר חיבור שירות ההטמעות.",
    chunks: "מקטעים",
    kindLabel: "סוג התוכן",
    kinds: { knowledge: "ידע", sample_posts: "פוסטים לדוגמה" } as Record<
      DocumentKind,
      string
    >,
    kindHint:
      "פוסטים לדוגמה הם פוסטים שכבר כתבת. רעיונות לנושאים לא יציעו את מה שכבר כתוב בהם.",
    kindSaved: "סוג התוכן נשמר.",
    embed: "הפעלת חיפוש AI",
    embedding: "מכין חיפוש AI",
    embeddingFailed: "הכנת חיפוש AI נכשלה",
    connectionMissing: "חיפוש AI עדיין לא מחובר. הטקסטים שנשמרו יישארו זמינים.",
    connectionReady: "אפשר כעת להפעיל חיפוש AI למקורות שהוכנו.",
    embeddingError:
      "הכנת חיפוש AI לא הסתיימה. אפשר לנסות שוב או לבדוק את החיבור לספק.",
    embedded: "מוכנים לחיפוש AI",
    retry: "ניסיון עיבוד נוסף",
    refreshPage: "טעינה מחדש מהאתר",
    refreshing: "נטען מחדש…",
    lastLoaded: "נטען לאחרונה",
    refreshUnchanged: "אין שינויים מאז הטעינה האחרונה.",
    refreshReplaced: "הוחלף בגרסה החדשה מהאתר.",
    refreshAppended: "פסקאות חדשות מהאתר נוספו.",
    refreshKeptChoice: "הגרסה הנוכחית נשמרה.",
    refreshPreparing: "מכין את הגרסה החדשה לחיפוש AI…",
    changesFound: (added: number, removed: number) =>
      `הדף השתנה: ${added} פסקאות חדשות, ${removed} שכבר לא באתר. הגרסה הנוכחית נשארת בשימוש עד שתבחרו.`,
    showChanges: "הצגת השינויים",
    hideChanges: "הסתרת השינויים",
    newParagraphs: "חדש באתר",
    removedParagraphs: "כבר לא באתר",
    more: (count: number) => `…ועוד ${count}`,
    chooseReplace: "החלפה בגרסה החדשה",
    chooseAppend: "הוספת הפסקאות החדשות",
    chooseKeep: "השארת הגרסה הנוכחית",
    choiceHint:
      "הוספה שומרת את כל מה שכבר נשמר. כשעובדות סותרות, הפוסטים משתמשים בחדשות ביותר.",
    refreshFailed: "הטעינה מחדש לא הסתיימה:",
    refreshKept: "הגרסה הקודמת עדיין בשימוש.",
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
      `סוגי קבצים: PDF,‏ TXT או Markdown בקידוד UTF-8, עד ⁦${size}⁩ ו־${pages} עמודים. קובצי PDF סרוקים צריכים לעבור קודם זיהוי טקסט (OCR).`,
    uploadButton: "העלאת הקובץ",
    linkHeading: "הוספת דף אינטרנט",
    linkLabel: "כתובת הדף (URL)",
    linkTitle: "כותרת לדף (לא חובה)",
    linkTitleHint: "ברירת המחדל היא הכותרת של הדף עצמו",
    linkLimit:
      "דפי אינטרנט ציבוריים בלבד (http או https). הדף נטען ברקע; נשמרים הטקסט הראשי והכותרות, בלי תפריטים ושורות תחתונות.",
    linkButton: "הוספת הדף",
    linkAdded: "הדף נוסף. הוא ייטען ויוכן ברקע.",
    linkDuplicate: "הדף הזה כבר נמצא במאגר הידע. לא נוסף מקור חדש.",
    linkErrors: {
      url_invalid: "יש להזין כתובת מלאה, למשל https://example.com/page.",
      url_scheme_unsupported: "אפשר להוסיף רק כתובות http או https.",
      url_credentials: "יש להסיר מהכתובת שם משתמש או סיסמה ולנסות שוב.",
      url_port_unsupported:
        "אפשר להשתמש רק בפורטים הרגילים של אתרים. יש להסיר את מספר הפורט.",
      url_blocked_address:
        "הכתובת מפנה לרשת פרטית או מקומית, ואי אפשר לטעון אותה.",
    } as Record<string, string>,
    linkGeneric: "לא הצלחנו להוסיף את הדף. אפשר לנסות שוב.",
    uploadGeneric: "ההעלאה לא הסתיימה. אפשר לנסות שוב.",
    uploading: "מעלה",
    saving: "ההעלאה הסתיימה. בודק ושומר את הקובץ…",
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
      upload_conflict: "קובץ זהה נמחק בזמן ההעלאה. אפשר להעלות את הקובץ שוב.",
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
      url_dns_failed:
        "לא מצאנו את כתובת האתר. כדאי לבדוק את הקישור ולנסות לעבד שוב.",
      url_blocked_address:
        "הכתובת מפנה לרשת פרטית או מקומית, ואי אפשר לטעון אותה.",
      url_timeout: "האתר לא ענה בזמן. אפשר לנסות לעבד שוב מאוחר יותר.",
      url_too_large: "הדף גדול ממגבלת הגודל.",
      url_http_error:
        "האתר לא החזיר את הדף (למשל, הדף לא נמצא או שהגישה נחסמה).",
      url_unsupported_type:
        "הקישור הזה אינו דף אינטרנט. כדי להוסיף PDF, יש להוריד אותו ולהעלות את הקובץ.",
      url_too_many_redirects: "הקישור מפנה הלאה יותר מדי פעמים.",
      url_fetch_failed:
        "לא הצלחנו להגיע לאתר. כדאי לבדוק את הקישור ולנסות לעבד שוב.",
      url_no_content:
        "לא נמצא טקסט קריא בדף. דפים שמציגים תוכן רק באמצעות JavaScript אינם נתמכים; אפשר להדביק את הטקסט במקום.",
      url_parse_failed: "לא הצלחנו לקרוא את הדף.",
    } as Record<string, string>,
    next: "מקורות קודמים",
    previous: "מקורות חדשים יותר",
    deleted: "המקור נמחק.",
    dispatch: "לא ניתן היה להתחבר לשירות העיבוד. אפשר לנסות לעבד שוב.",
    failure: "העיבוד לא הסתיים. אפשר לנסות שוב.",
    invalid: "יש להזין כותרת וטקסט.",
  },
};
const POLL_INTERVAL_MS = 3000;
const DEFAULT_LIMITS = { bytes: 10 * 1024 * 1024, pages: 300 };
const without = <T,>(record: Record<string, T>, key: string) =>
  Object.fromEntries(Object.entries(record).filter(([k]) => k !== key));
const FILE_EXTENSIONS = [".pdf", ".txt", ".md"];
const megabytes = (bytes: number) =>
  `${Math.round((bytes / 1024 / 1024) * 10) / 10} MB`;
// Processing again cannot fix these: the owner has to change the file or the link.
const FINAL_ERRORS = new Set([
  "pdf_requires_ocr",
  "pdf_encrypted",
  "pdf_corrupt",
  "pdf_too_many_pages",
  "source_too_long",
  "source_file_missing",
  "url_blocked_address",
  "url_unsupported_type",
]);
type Messages = (typeof messages)[Locale];
const awaitingChoice = (item: Document) =>
  item.refresh?.stage === "awaiting_decision";
const refreshing = (item: Document) =>
  ["Pending", "Processing"].includes(item.refresh?.status ?? "") &&
  !awaitingChoice(item);
// The list is polled while any source is in flight; text_prepared, Ready, Failed
// and a reload waiting for the owner's choice are resting states.
const inFlight = (item: Document) =>
  refreshing(item) ||
  (item.stage !== "text_prepared" &&
    ["Pending", "Processing"].includes(item.status));
const statusLabel = (item: Document, t: Messages) =>
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
// What a source settled into, announced to screen readers when polling ends for it.
// A finished reload says what happened to the page rather than the source's status.
const outcome = (item: Document, t: Messages, wasReloading: boolean) =>
  awaitingChoice(item)
    ? t.changesFound(
        item.refresh?.added_count ?? 0,
        item.refresh?.removed_count ?? 0,
      )
    : item.refresh?.status === "Failed"
      ? `${t.refreshFailed} ${t.refreshKept}`
      : wasReloading && item.refresh_result
        ? {
            unchanged: t.refreshUnchanged,
            replaced: t.refreshReplaced,
            appended: t.refreshAppended,
            kept: t.refreshKeptChoice,
          }[item.refresh_result]
        : statusLabel(item, t);
// Shows Hebrew and other non-ASCII addresses as written; the link keeps the encoded
// form. Bidirectional control characters stay encoded so they cannot reorder the text.
const readableUrl = (url: string) => {
  try {
    return decodeURI(url).replace(/[‎‏‪-‮⁦-⁩]/g, encodeURIComponent);
  } catch {
    return url;
  }
};
// Gives each row's buttons a name that says which source they act on.
const forSource = (label: string, item: Document) => `${label}: ${item.title}`;
const errorCode = async (response: Response) => {
  const body = await response.json().catch(() => ({}));
  return (body.error?.message ?? "") as string;
};
const known = (code: string, texts: Record<string, string>) =>
  Object.hasOwn(texts, code) ? code : "generic";
function KindField({
  id,
  value,
  onChange,
  t,
}: {
  id: string;
  value: DocumentKind;
  onChange: (kind: DocumentKind) => void;
  t: Messages;
}) {
  return (
    <div>
      <label htmlFor={id} className="mb-2 block text-sm font-medium">
        {t.kindLabel}
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value as DocumentKind)}
        aria-describedby={`${id}-hint`}
        className="h-11 w-full rounded-lg border border-border bg-background px-3 text-start text-sm focus-visible:outline-2 focus-visible:outline-primary"
      >
        {KINDS.map((kind) => (
          <option key={kind} value={kind}>
            {t.kinds[kind]}
          </option>
        ))}
      </select>
      <p id={`${id}-hint`} className="mt-2 text-xs text-muted-foreground">
        {t.kindHint}
      </p>
    </div>
  );
}
export function KnowledgeBase({ locale }: { locale: Locale }) {
  const t = messages[locale];
  // null until the configuration answers, so "not connected" never flashes.
  const [connected, setConnected] = useState<boolean | null>(null);
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
  const [link, setLink] = useState("");
  const [linkTitle, setLinkTitle] = useState("");
  const [linkError, setLinkError] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [textKind, setTextKind] = useState<DocumentKind>("knowledge");
  const [fileKind, setFileKind] = useState<DocumentKind>("knowledge");
  const [linkKind, setLinkKind] = useState<DocumentKind>("knowledge");
  const [items, setItems] = useState<Document[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  // A failed action: a code from actionErrors, or "generic".
  const [error, setError] = useState<string | null>(null);
  const [listFailed, setListFailed] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  // Element ids to focus after the next render, first one found wins. Buttons are
  // disabled while a request runs, which drops focus to <body>; this puts it back.
  const [focusTarget, setFocusTarget] = useState<string[] | null>(null);
  useEffect(() => {
    if (!focusTarget) return;
    focusTarget
      .map((id) => document.getElementById(id))
      .find((element) => element !== null)
      ?.focus();
    setFocusTarget(null);
  }, [focusTarget]);
  const [notice, setNotice] = useState<
    | "saved"
    | "duplicate"
    | "deleted"
    | "invalid"
    | "uploaded"
    | "uploadDuplicate"
    | "linkAdded"
    | "linkDuplicate"
    | "kindSaved"
    | null
  >(null);
  const [confirm, setConfirm] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Document | null>(null);
  // Bumped when a source changes in place; a list read that began before the change
  // answers with the old value and is dropped, and the next one shows the new.
  const listVersion = useRef(0);
  const load = useCallback(
    async (page = offset) => {
      const version = listVersion.current;
      try {
        const response = await fetch(`/api/knowledge?offset=${page}&limit=20`, {
          cache: "no-store",
        });
        if (!response.ok) throw new Error();
        const data = await response.json();
        if (version !== listVersion.current) return;
        setItems(data.items);
        setTotal(data.total);
        setListFailed(false);
      } catch {
        setListFailed(true);
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
  // What each source was doing at the last load: "reload", "processing" or nothing.
  const wasInFlight = useRef(new Map<string, string>());
  useEffect(() => {
    const settled = items.filter(
      (item) => wasInFlight.current.get(item.id) && !inFlight(item),
    );
    const reloading = new Set(
      settled
        .filter((item) => wasInFlight.current.get(item.id) === "reload")
        .map((item) => item.id),
    );
    wasInFlight.current = new Map(
      items
        .filter(inFlight)
        .map((item) => [item.id, refreshing(item) ? "reload" : "processing"]),
    );
    if (!settled.length) return;
    const text = settled
      .map(
        (item) => `${item.title}: ${outcome(item, t, reloading.has(item.id))}`,
      )
      .join(" ");
    // An unchanged text is not read again, so a repeat (the same failure after
    // Process again) gets an invisible difference.
    setAnnouncement((previous) => (previous === text ? `${text} ` : text));
  }, [items, t]);
  const [changes, setChanges] = useState<Record<string, Changes>>({});
  async function toggleChanges(item: Document) {
    if (changes[item.id]) {
      setChanges((current) => without(current, item.id));
      return;
    }
    setBusy(item.id);
    setError(null);
    try {
      const response = await fetch(
        `/api/knowledge/${item.id}/refresh-changes`,
        { cache: "no-store" },
      );
      if (!response.ok) {
        const code = await errorCode(response);
        setError(known(code, t.actionErrors));
        if (code === "refresh_not_awaiting") await load();
        return;
      }
      const found: Changes = await response.json();
      setChanges((current) => ({ ...current, [item.id]: found }));
    } catch {
      setError("generic");
    } finally {
      setBusy(null);
      setFocusTarget([`changes-${item.id}`, `source-${item.id}`]);
    }
  }
  async function choose(item: Document, choice: "replace" | "append" | "keep") {
    setBusy(item.id);
    setError(null);
    setNotice(null);
    try {
      const response = await fetch(
        `/api/knowledge/${item.id}/refresh-decision`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: choice }),
        },
      );
      if (!response.ok) {
        const code = await errorCode(response);
        setError(known(code, t.actionErrors));
        if (code === "refresh_not_awaiting") await load();
        return;
      }
      setChanges((current) => without(current, item.id));
      await load();
    } catch {
      setError("generic");
    } finally {
      setBusy(null);
      // The choice panel is gone; the row's title is the nearest stable place.
      setFocusTarget([`source-${item.id}`]);
    }
  }
  async function changeKind(item: Document, kind: DocumentKind) {
    listVersion.current += 1;
    setBusy(item.id);
    setError(null);
    setNotice(null);
    try {
      const response = await fetch(`/api/knowledge/${item.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind }),
      });
      if (!response.ok) throw new Error();
      const saved: Document = await response.json();
      // A list read sent while the change was being saved may predate it.
      listVersion.current += 1;
      setItems((current) =>
        current.map((other) =>
          other.id === item.id ? { ...other, kind: saved.kind } : other,
        ),
      );
      setNotice("kindSaved");
    } catch {
      // The select shows the stored kind, which this failure left unchanged.
      setError("kind_not_saved");
    } finally {
      setBusy(null);
      setFocusTarget([`kind-${item.id}`, `source-${item.id}`]);
    }
  }
  const active = items.some(inFlight);
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => void load(), POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [active, load]);
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!title.trim() || !text.trim()) {
      setNotice("invalid");
      setFocusTarget([title.trim() ? "source-text" : "source-title"]);
      return;
    }
    setBusy("submit");
    setNotice(null);
    setError(null);
    try {
      const response = await fetch("/api/knowledge/text", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, text, kind: textKind }),
      });
      if (!response.ok) throw new Error();
      const result = await response.json();
      setTitle("");
      setText("");
      setTextKind("knowledge");
      setNotice(result.duplicate ? "duplicate" : "saved");
      setOffset(0);
      await load(0);
    } catch {
      setError("generic");
    } finally {
      setBusy(null);
      setFocusTarget(["source-title"]);
    }
  }
  async function submitLink(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice(null);
    setLinkError(null);
    if (!/^https?:\/\/\S+$/i.test(link.trim())) {
      setLinkError(
        /^[a-z][a-z0-9+.-]*:/i.test(link.trim()) &&
          !/^https?:/i.test(link.trim())
          ? "url_scheme_unsupported"
          : "url_invalid",
      );
      setFocusTarget(["source-url"]);
      return;
    }
    setBusy("link");
    try {
      const response = await fetch("/api/knowledge/url", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: link.trim(),
          title: linkTitle.trim(),
          kind: linkKind,
        }),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) {
        const code = result.error?.message ?? "";
        setLinkError(known(code, t.linkErrors));
        return;
      }
      setLink("");
      setLinkTitle("");
      setLinkKind("knowledge");
      setNotice(result.duplicate ? "linkDuplicate" : "linkAdded");
      setOffset(0);
      await load(0);
    } catch {
      setLinkError("generic");
    } finally {
      setBusy(null);
      setFocusTarget(["source-url"]);
    }
  }
  async function uploadFile(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setNotice(null);
    setUploadError(null);
    // The server checks the same limits; checking here saves a pointless upload.
    const extension = file
      ? file.name.slice(file.name.lastIndexOf(".")).toLowerCase()
      : "";
    const refused = !file
      ? "chooseFile"
      : !FILE_EXTENSIONS.includes(extension)
        ? "file_type_unsupported"
        : file.size > limits.bytes
          ? "file_too_large"
          : file.size === 0
            ? "source_empty"
            : null;
    if (!file || refused) {
      setUploadError(refused);
      setFocusTarget(["source-file"]);
      return;
    }
    setBusy("upload");
    setProgress(0);
    const query = new URLSearchParams({ filename: file.name });
    if (fileTitle.trim()) query.set("title", fileTitle.trim());
    query.set("kind", fileKind);
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
            setProgress(Math.min(99, Math.round((e.loaded / e.total) * 100)));
        };
        // Every byte is sent; the server is now checking and storing the file.
        request.upload.onload = () => setProgress(100);
        request.onload = () =>
          resolve({ status: request.status, body: request.response ?? {} });
        request.onerror = () => reject(new Error("network"));
        request.send(file);
      });
      if (result.status < 200 || result.status >= 300) {
        const code =
          result.body.error?.message ?? result.body.error?.code ?? "";
        setUploadError(known(code, t.uploadErrors));
        return;
      }
      form.reset();
      setFile(null);
      setFileTitle("");
      setFileKind("knowledge");
      setNotice(result.body.duplicate ? "uploadDuplicate" : "uploaded");
      setOffset(0);
      await load(0);
    } catch {
      setUploadError("generic");
    } finally {
      setBusy(null);
      setProgress(null);
      setFocusTarget(["source-file"]);
    }
  }
  async function action(
    document: Document,
    kind: "retry" | "delete" | "view" | "embed" | "refresh",
  ) {
    setBusy(document.id);
    setError(null);
    setNotice(null);
    let deleted = false;
    try {
      const response = await fetch(
        `/api/knowledge/${document.id}${kind === "view" || kind === "delete" ? "" : `/${kind}`}`,
        {
          method:
            kind === "delete" ? "DELETE" : kind === "view" ? "GET" : "POST",
          cache: "no-store",
        },
      );
      if (!response.ok) {
        const code = await errorCode(response);
        setError(known(code, t.actionErrors));
        return;
      }
      if (kind === "view") setExpanded(await response.json());
      else {
        setConfirm(null);
        if (kind === "delete") {
          deleted = true;
          setNotice("deleted");
          if (expanded?.id === document.id) setExpanded(null);
        }
        if (kind === "delete" && items.length === 1 && offset > 0)
          setOffset(Math.max(0, offset - 20));
        else await load();
      }
    } catch {
      setError("generic");
    } finally {
      setBusy(null);
      // The pressed button stays for "view"; retry, reload and AI search replace
      // it with progress, and a deleted row is gone, so focus moves up.
      setFocusTarget(
        deleted
          ? ["sources-heading"]
          : [`${kind}-${document.id}`, `source-${document.id}`],
      );
    }
  }
  function openConfirm(item: Document) {
    setConfirm(item.id);
    setFocusTarget([`confirm-${item.id}`]);
  }
  function closeConfirm(item: Document) {
    setConfirm(null);
    setFocusTarget([`delete-${item.id}`]);
  }
  const sourceType = (item: Document) =>
    ({
      text: t.typePasted,
      txt: t.typeTxt,
      pdf: t.typePdf,
      url: t.typeUrl,
    })[item.source_type] ?? t.typePasted;
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
                aria-invalid={notice === "invalid" && !title.trim()}
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
                aria-invalid={notice === "invalid" && !text.trim()}
                className="w-full resize-y rounded-lg border border-border bg-background p-3 text-start text-sm leading-6 focus-visible:outline-2 focus-visible:outline-primary"
              />
              <p
                id="source-limit"
                className="mt-2 text-xs text-muted-foreground"
              >
                {t.limit}
              </p>
            </div>
            <KindField
              id="source-kind"
              value={textKind}
              onChange={setTextKind}
              t={t}
            />
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
                aria-describedby={
                  uploadError ? "upload-limit upload-error" : "upload-limit"
                }
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
            <KindField
              id="file-kind"
              value={fileKind}
              onChange={setFileKind}
              t={t}
            />
          </fieldset>
          {progress !== null && (
            <div>
              {/* Sending the bytes, then the server checking and storing them;
                  background preparation shows on the source's row afterwards. */}
              <div
                role="progressbar"
                aria-label={progress < 100 ? t.uploading : t.saving}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={progress < 100 ? progress : undefined}
                className="h-2 w-full overflow-hidden rounded-full bg-muted"
              >
                <div
                  className={`h-full bg-primary transition-[width] ${progress < 100 ? "" : "animate-pulse"}`}
                  style={{ width: `${progress}%` }}
                />
              </div>
              {/* Only the phase is live; reading every percent would flood a screen
                  reader, and the progress bar already carries the number. */}
              <p className="mt-1 text-xs text-muted-foreground">
                <span role="status">
                  {progress < 100 ? t.uploading : t.saving}
                </span>
                {progress < 100 && <span aria-hidden> {progress}%</span>}
              </p>
            </div>
          )}
          {uploadError && (
            <p id="upload-error" role="alert" className="text-sm text-red-800">
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
        <form
          onSubmit={submitLink}
          noValidate
          className="mt-8 space-y-5 border-t border-border pt-7"
          aria-labelledby="link-heading"
        >
          <h3 id="link-heading" className="font-semibold">
            {t.linkHeading}
          </h3>
          <fieldset disabled={busy === "link"} className="space-y-5">
            <div>
              <label
                htmlFor="source-url"
                className="mb-2 block text-sm font-medium"
              >
                {t.linkLabel}
              </label>
              <input
                id="source-url"
                type="url"
                inputMode="url"
                maxLength={2048}
                value={link}
                dir="ltr"
                onChange={(e) => {
                  setLink(e.target.value);
                  setLinkError(null);
                }}
                placeholder="https://"
                aria-describedby={
                  linkError ? "link-limit link-error" : "link-limit"
                }
                aria-invalid={linkError !== null}
                className="h-11 w-full rounded-lg border border-border bg-background px-3 text-start text-sm focus-visible:outline-2 focus-visible:outline-primary"
              />
              <p
                id="link-limit"
                className="mt-2 text-xs leading-5 text-muted-foreground"
              >
                {t.linkLimit}
              </p>
            </div>
            <div>
              <label
                htmlFor="link-title"
                className="mb-2 block text-sm font-medium"
              >
                {t.linkTitle}
              </label>
              <input
                id="link-title"
                maxLength={300}
                value={linkTitle}
                dir={linkTitle ? "auto" : locale === "he" ? "rtl" : "ltr"}
                onChange={(e) => setLinkTitle(e.target.value)}
                placeholder={t.linkTitleHint}
                className="h-11 w-full rounded-lg border border-border bg-background px-3 text-start text-sm focus-visible:outline-2 focus-visible:outline-primary"
              />
            </div>
            <KindField
              id="link-kind"
              value={linkKind}
              onChange={setLinkKind}
              t={t}
            />
          </fieldset>
          {linkError && (
            <p id="link-error" role="alert" className="text-sm text-red-800">
              {t.linkErrors[linkError] ?? t.linkGeneric}
            </p>
          )}
          <Button type="submit" disabled={busy !== null}>
            {busy === "link" ? (
              <LoaderCircle size={16} className="animate-spin" />
            ) : (
              <Link2 size={16} />
            )}
            {t.linkButton}
          </Button>
        </form>
        {connected !== null && (
          <p className="mt-5 text-xs leading-6 text-muted-foreground">
            {connected ? t.connectionReady : t.connectionMissing}
          </p>
        )}
      </div>
      {error && (
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800"
        >
          {t.actionErrors[error] ?? t.error}
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
      <p role="status" className="sr-only">
        {announcement}
      </p>
      <div className="rounded-2xl border border-border bg-card p-6 sm:p-9">
        <div className="mb-6 flex items-center justify-between gap-3">
          <h3
            id="sources-heading"
            tabIndex={-1}
            className="rounded text-lg font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
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
        {listFailed && !loading && (
          <div
            role="alert"
            className="mb-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800"
          >
            {t.listError}
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
        {loading ? (
          <p role="status" className="flex items-center gap-2 text-sm">
            <LoaderCircle size={16} className="animate-spin" aria-hidden />
            {t.loading}
          </p>
        ) : items.length === 0 ? (
          // A failed first load is not an empty Knowledge Base.
          listFailed ? null : (
            <p className="text-sm text-muted-foreground">{t.empty}</p>
          )
        ) : (
          <ul className="space-y-4">
            {items.map((item) => (
              <li key={item.id} className="rounded-xl border border-border p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h4
                    id={`source-${item.id}`}
                    tabIndex={-1}
                    dir="auto"
                    className="min-w-0 max-w-full break-words rounded font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                  >
                    {item.title}
                  </h4>
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-3 py-1 text-xs text-primary">
                    {inFlight(item) && (
                      <LoaderCircle
                        size={12}
                        className="animate-spin"
                        aria-hidden
                      />
                    )}
                    {statusLabel(item, t)}
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
                  {item.url && (
                    <>
                      {" · "}
                      <a
                        href={item.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        dir="ltr"
                        className="break-all underline underline-offset-2"
                      >
                        {readableUrl(item.url)}
                      </a>
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
                  {item.fetched_at &&
                    !Number.isNaN(Date.parse(item.fetched_at)) && (
                      <>
                        {" · "}
                        {t.lastLoaded}{" "}
                        <time dateTime={item.fetched_at}>
                          {new Intl.DateTimeFormat(locale, {
                            dateStyle: "medium",
                            timeStyle: "short",
                          }).format(new Date(item.fetched_at))}
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
                <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                  <label
                    htmlFor={`kind-${item.id}`}
                    className="text-muted-foreground"
                  >
                    {t.kindLabel}
                  </label>
                  <select
                    id={`kind-${item.id}`}
                    value={item.kind}
                    disabled={busy !== null}
                    aria-label={forSource(t.kindLabel, item)}
                    onChange={(e) =>
                      void changeKind(item, e.target.value as DocumentKind)
                    }
                    className="h-8 rounded-md border border-border bg-background px-2 text-xs focus-visible:outline-2 focus-visible:outline-primary disabled:opacity-60"
                  >
                    {KINDS.map((kind) => (
                      <option key={kind} value={kind}>
                        {t.kinds[kind]}
                      </option>
                    ))}
                  </select>
                  {busy === item.id && (
                    <LoaderCircle
                      size={12}
                      className="animate-spin"
                      aria-hidden
                    />
                  )}
                </div>
                {awaitingChoice(item) ? (
                  <div className="mt-3 rounded-lg border border-primary/30 bg-primary/5 p-4 text-sm">
                    <p>
                      {t.changesFound(
                        item.refresh?.added_count ?? 0,
                        item.refresh?.removed_count ?? 0,
                      )}
                    </p>
                    {changes[item.id] && (
                      <div className="mt-3 space-y-3">
                        {(
                          [
                            ["added", t.newParagraphs, "border-green-600"],
                            ["removed", t.removedParagraphs, "border-red-600"],
                          ] as const
                        ).map(([kind, heading, border]) =>
                          changes[item.id][kind].length ? (
                            <div key={kind}>
                              <p className="font-medium">{heading}</p>
                              <ul className="mt-1 space-y-2">
                                {changes[item.id][kind].map((paragraph, i) => (
                                  <li
                                    key={i}
                                    dir="auto"
                                    className={`whitespace-pre-wrap break-words border-s-4 ${border} bg-background p-2 text-sm leading-6`}
                                  >
                                    {paragraph}
                                  </li>
                                ))}
                              </ul>
                              {changes[item.id][`${kind}_count`] >
                                changes[item.id][kind].length && (
                                <p className="mt-1 text-xs text-muted-foreground">
                                  {t.more(
                                    changes[item.id][`${kind}_count`] -
                                      changes[item.id][kind].length,
                                  )}
                                </p>
                              )}
                            </div>
                          ) : null,
                        )}
                      </div>
                    )}
                    <p className="mt-3 text-xs text-muted-foreground">
                      {t.choiceHint}
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Button
                        id={`changes-${item.id}`}
                        variant="outline"
                        size="sm"
                        disabled={busy !== null}
                        aria-expanded={Boolean(changes[item.id])}
                        aria-label={forSource(
                          changes[item.id] ? t.hideChanges : t.showChanges,
                          item,
                        )}
                        onClick={() => void toggleChanges(item)}
                      >
                        {changes[item.id] ? t.hideChanges : t.showChanges}
                      </Button>
                      <Button
                        size="sm"
                        disabled={busy !== null}
                        aria-label={forSource(t.chooseReplace, item)}
                        onClick={() => void choose(item, "replace")}
                      >
                        {t.chooseReplace}
                      </Button>
                      <Button
                        size="sm"
                        disabled={busy !== null || !item.refresh?.added_count}
                        aria-label={forSource(t.chooseAppend, item)}
                        onClick={() => void choose(item, "append")}
                      >
                        {t.chooseAppend}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={busy !== null}
                        aria-label={forSource(t.chooseKeep, item)}
                        onClick={() => void choose(item, "keep")}
                      >
                        {t.chooseKeep}
                      </Button>
                    </div>
                  </div>
                ) : refreshing(item) ? (
                  <p className="mt-3 flex items-center gap-2 text-sm text-primary">
                    <LoaderCircle size={14} className="animate-spin" />
                    {item.refresh?.stage.startsWith("embedding")
                      ? t.refreshPreparing
                      : t.refreshing}
                  </p>
                ) : item.refresh?.status === "Failed" ? (
                  <p className="mt-3 text-sm text-red-800">
                    {t.refreshFailed}{" "}
                    {item.refresh.stage === "embedding_failed"
                      ? t.embeddingError
                      : (t.processingErrors[item.refresh.error_code ?? ""] ??
                        t.failure)}{" "}
                    {t.refreshKept}
                  </p>
                ) : item.refresh_result ? (
                  <p className="mt-3 text-sm text-muted-foreground">
                    {
                      {
                        unchanged: t.refreshUnchanged,
                        replaced: t.refreshReplaced,
                        appended: t.refreshAppended,
                        kept: t.refreshKeptChoice,
                      }[item.refresh_result]
                    }
                  </p>
                ) : null}
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
                    id={`view-${item.id}`}
                    variant="outline"
                    size="sm"
                    disabled={busy !== null}
                    aria-expanded={expanded?.id === item.id}
                    aria-label={forSource(
                      expanded?.id === item.id ? t.close : t.view,
                      item,
                    )}
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
                    item.status !== "Ready" &&
                    !FINAL_ERRORS.has(item.error_code ?? "") && (
                      <Button
                        id={`retry-${item.id}`}
                        variant="outline"
                        size="sm"
                        disabled={busy !== null}
                        aria-label={forSource(t.retry, item)}
                        onClick={() => void action(item, "retry")}
                      >
                        <RefreshCw size={14} aria-hidden />
                        {t.retry}
                      </Button>
                    )}
                  {item.source_type === "url" &&
                    ["text_prepared", "ready"].includes(item.stage) &&
                    !refreshing(item) &&
                    !awaitingChoice(item) && (
                      <Button
                        id={`refresh-${item.id}`}
                        variant="outline"
                        size="sm"
                        disabled={busy !== null}
                        aria-label={forSource(t.refreshPage, item)}
                        onClick={() => void action(item, "refresh")}
                      >
                        <RefreshCw size={14} aria-hidden />
                        {t.refreshPage}
                      </Button>
                    )}
                  {item.chunk_count > 0 &&
                    item.status !== "Ready" &&
                    !refreshing(item) && (
                      <Button
                        id={`embed-${item.id}`}
                        variant="outline"
                        size="sm"
                        disabled={busy !== null || !connected}
                        aria-label={forSource(t.embed, item)}
                        onClick={() => void action(item, "embed")}
                      >
                        {t.embed}
                      </Button>
                    )}
                  <Button
                    id={`delete-${item.id}`}
                    variant="ghost"
                    size="sm"
                    disabled={busy !== null}
                    aria-label={forSource(t.remove, item)}
                    onClick={() => openConfirm(item)}
                  >
                    <Trash2 size={14} aria-hidden />
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
                  <div
                    role="group"
                    aria-labelledby={`confirm-${item.id}`}
                    className="mt-4 rounded-lg bg-muted p-4"
                    onKeyDown={(e) => {
                      if (e.key === "Escape") closeConfirm(item);
                    }}
                  >
                    {/* Focused on open so the question is read before the buttons. */}
                    <p
                      id={`confirm-${item.id}`}
                      tabIndex={-1}
                      className="mb-3 rounded text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                    >
                      {t.confirm}
                    </p>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        disabled={busy !== null}
                        aria-label={forSource(t.yes, item)}
                        onClick={() => void action(item, "delete")}
                      >
                        {t.yes}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        aria-label={forSource(t.cancel, item)}
                        onClick={() => closeConfirm(item)}
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
