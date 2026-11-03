"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Copy,
  FolderSync,
  LoaderCircle,
  RefreshCw,
  Unlink,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Locale } from "@/lib/i18n";

// SP-30: a Google Drive folder shared with the service account; its files sync in daily.
type DocumentKind = "knowledge" | "sample_posts";
type Folder = {
  id: string;
  folder_id: string;
  name: string;
  kind: DocumentKind;
  status: "Pending" | "Syncing" | "Ready" | "Failed";
  error_code: string | null;
  synced_at: string | null;
  file_count: number;
  skipped_count: number;
  document_count: number;
};
type Listing = {
  configured: boolean;
  service_account_email: string | null;
  items: Folder[];
};
const messages = {
  en: {
    heading: "Connect a Google Drive folder",
    intro:
      "Files in the folder are added as sources and kept in sync once a day. A file you change is read again; a file you remove from the folder is removed here.",
    notConfigured:
      "Google Drive isn’t set up on the server yet. Add the service account key to connect folders.",
    shareStep: "1. In Google Drive, share the folder as Viewer with:",
    pasteStep: "2. Paste the folder’s link here.",
    copy: "Copy address",
    copied: "Address copied.",
    folderLabel: "Folder link",
    folderHint:
      "Google Docs, PDF, TXT and Markdown files directly in the folder are imported. Subfolders and other files are skipped.",
    connect: "Connect folder",
    connecting: "Checking the folder…",
    folders: "Connected folders",
    loading: "Loading folders…",
    loadError: "We couldn’t load your Drive folders. Please try again.",
    retry: "Try again",
    status: {
      Pending: "Queued",
      Syncing: "Syncing…",
      Ready: "Synced",
      Failed: "Sync failed",
    } as Record<Folder["status"], string>,
    lastSynced: "Last synced",
    neverSynced: "Not synced yet",
    files: (imported: number, skipped: number) =>
      skipped
        ? `${imported} files imported · ${skipped} skipped`
        : `${imported} files imported`,
    newFilesAs: (kind: string) => `New files are added as ${kind}`,
    kinds: { knowledge: "Knowledge", sample_posts: "Sample posts" } as Record<
      DocumentKind,
      string
    >,
    sync: "Refresh",
    disconnect: "Disconnect",
    confirm: (count: number) =>
      `Disconnect this folder and delete its ${count} sources from the Knowledge Base? Nothing changes in Google Drive.`,
    confirmYes: "Disconnect and delete",
    cancel: "Cancel",
    disconnected: "Folder disconnected. Its sources were deleted.",
    synced: (name: string) => `${name}: sync finished.`,
    errors: {
      drive_folder_invalid:
        "Paste a Google Drive folder link, such as https://drive.google.com/drive/folders/…",
      drive_not_a_folder: "This link is to a file, not a folder.",
      drive_not_shared:
        "The service account can’t see this folder. Share it as Viewer with the address above, then try again.",
      drive_not_configured: "Google Drive isn’t set up on the server.",
      drive_key_invalid:
        "The service account key was refused. Check the key file on the server.",
      drive_unavailable:
        "Google Drive didn’t answer. Try again in a few minutes.",
      drive_folder_too_large:
        "The folder has more files than a sync may read. Move some files to another folder.",
      drive_sync_interrupted:
        "The last sync was interrupted. Refresh to sync again.",
      dispatch_failed:
        "The sync service couldn’t be reached. Refresh to try again.",
      drive_request_failed:
        "Google Drive gave an answer we couldn’t use. Refresh to try again.",
      drive_sync_failed: "The sync stopped unexpectedly. Refresh to try again.",
      storage_failed: "A file couldn’t be stored. Refresh to try again.",
    } as Record<string, string>,
    syncErrorNote: "Nothing was deleted.",
    generic: "That didn’t work. Please try again.",
  },
  he: {
    heading: "חיבור תיקייה מ-Google Drive",
    intro:
      "הקבצים בתיקייה נוספים כמקורות ומסונכרנים פעם ביום. קובץ ששונה נקרא מחדש, וקובץ שהוצא מהתיקייה נמחק גם כאן.",
    notConfigured:
      "Google Drive עוד לא הוגדר בשרת. צריך להוסיף את מפתח ה-Service account כדי לחבר תיקיות.",
    shareStep: "1. ב-Google Drive, משתפים את התיקייה כ-Viewer (צפייה) עם:",
    pasteStep: "2. מדביקים כאן את הקישור לתיקייה.",
    copy: "העתקת הכתובת",
    copied: "הכתובת הועתקה.",
    folderLabel: "קישור לתיקייה",
    folderHint:
      "מיובאים קובצי Google Docs,‏ PDF,‏ TXT ו-Markdown שנמצאים ישירות בתיקייה. תת-תיקיות וקבצים אחרים מדולגים.",
    connect: "חיבור התיקייה",
    connecting: "בודק את התיקייה…",
    folders: "תיקיות מחוברות",
    loading: "טוען תיקיות…",
    loadError: "לא הצלחנו לטעון את התיקיות מ-Drive. אפשר לנסות שוב.",
    retry: "ניסיון חוזר",
    status: {
      Pending: "בתור",
      Syncing: "מסנכרן…",
      Ready: "מסונכרן",
      Failed: "הסנכרון נכשל",
    } as Record<Folder["status"], string>,
    lastSynced: "סונכרן לאחרונה",
    neverSynced: "עוד לא סונכרן",
    files: (imported: number, skipped: number) =>
      skipped
        ? `${imported} קבצים יובאו · ${skipped} דולגו`
        : `${imported} קבצים יובאו`,
    newFilesAs: (kind: string) => `קבצים חדשים נוספים כ${kind}`,
    kinds: { knowledge: "ידע", sample_posts: "פוסטים לדוגמה" } as Record<
      DocumentKind,
      string
    >,
    sync: "רענון",
    disconnect: "ניתוק",
    confirm: (count: number) =>
      `לנתק את התיקייה ולמחוק ממאגר הידע את ${count} המקורות שהגיעו ממנה? שום דבר לא משתנה ב-Google Drive.`,
    confirmYes: "ניתוק ומחיקה",
    cancel: "ביטול",
    disconnected: "התיקייה נותקה והמקורות שלה נמחקו.",
    synced: (name: string) => `${name}: הסנכרון הסתיים.`,
    errors: {
      drive_folder_invalid:
        "צריך להדביק קישור לתיקייה ב-Google Drive, למשל https://drive.google.com/drive/folders/…",
      drive_not_a_folder: "הקישור הוא לקובץ ולא לתיקייה.",
      drive_not_shared:
        "ה-Service account לא רואה את התיקייה. משתפים אותה כ-Viewer עם הכתובת שלמעלה ומנסים שוב.",
      drive_not_configured: "Google Drive לא הוגדר בשרת.",
      drive_key_invalid:
        "מפתח ה-Service account נדחה. כדאי לבדוק את קובץ המפתח בשרת.",
      drive_unavailable: "Google Drive לא ענה. אפשר לנסות שוב בעוד כמה דקות.",
      drive_folder_too_large:
        "בתיקייה יש יותר קבצים ממה שסנכרון יכול לקרוא. כדאי להעביר חלק מהקבצים לתיקייה אחרת.",
      drive_sync_interrupted:
        "הסנכרון האחרון נקטע. לוחצים על רענון כדי לסנכרן שוב.",
      dispatch_failed:
        "לא הצלחנו להגיע לשירות הסנכרון. לוחצים על רענון כדי לנסות שוב.",
      drive_request_failed:
        "Google Drive החזיר תשובה שלא הצלחנו להשתמש בה. לוחצים על רענון כדי לנסות שוב.",
      drive_sync_failed:
        "הסנכרון נעצר באופן לא צפוי. לוחצים על רענון כדי לנסות שוב.",
      storage_failed: "לא הצלחנו לשמור קובץ. לוחצים על רענון כדי לנסות שוב.",
    } as Record<string, string>,
    syncErrorNote: "שום דבר לא נמחק.",
    generic: "הפעולה לא הצליחה. אפשר לנסות שוב.",
  },
};
const POLL_INTERVAL_MS = 3000;
const syncing = (folder: Folder) =>
  folder.status === "Pending" || folder.status === "Syncing";

const fetchListing = async (): Promise<Listing> => {
  const response = await fetch("/api/knowledge/drive-folders", {
    cache: "no-store",
  });
  if (!response.ok) throw new Error();
  return response.json();
};
type KindFieldRender = (props: {
  id: string;
  value: DocumentKind;
  onChange: (kind: DocumentKind) => void;
}) => React.ReactNode;

// The connect form, shown in the Knowledge Base's add-source dialog.
export function DriveFolderConnect({
  locale,
  kindField,
  labelledBy,
  onConnected,
  onBusyChange,
}: {
  locale: Locale;
  // The Knowledge Base's own content-type control, so both read the same.
  kindField: KindFieldRender;
  labelledBy: string;
  onConnected: (duplicate: boolean) => void;
  // The dialog stays open while the folder is being checked.
  onBusyChange: (busy: boolean) => void;
}) {
  const t = messages[locale];
  const [listing, setListing] = useState<Listing | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [link, setLink] = useState("");
  const [kind, setKind] = useState<DocumentKind>("knowledge");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    try {
      setListing(await fetchListing());
      setLoadFailed(false);
    } catch {
      setLoadFailed(true);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => onBusyChange(busy), [busy, onBusyChange]);

  async function connect(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice("");
    setFormError(null);
    if (!link.trim()) {
      setFormError("drive_folder_invalid");
      document.getElementById("drive-folder")?.focus();
      return;
    }
    setBusy(true);
    try {
      const response = await fetch("/api/knowledge/drive-folders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ folder: link.trim(), kind }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        // The proxy's own errors (a timeout, an unreachable API) carry no message.
        setFormError(body.error?.message || "generic");
        return;
      }
      const result = await response.json();
      setLink("");
      setKind("knowledge");
      onConnected(Boolean(result.duplicate));
    } catch {
      setFormError("generic");
    } finally {
      setBusy(false);
    }
  }

  async function copyAddress(address: string) {
    try {
      await navigator.clipboard.writeText(address);
      setNotice(t.copied);
    } catch {
      // The address stays selectable on screen.
    }
  }

  return (
    <div className="space-y-5">
      <p className="text-xs leading-5 text-muted-foreground">{t.intro}</p>
      {listing === null && !loadFailed ? (
        <p role="status" className="flex items-center gap-2 text-sm">
          <LoaderCircle size={16} className="animate-spin" aria-hidden />
          {t.loading}
        </p>
      ) : listing === null ? (
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800"
        >
          {t.loadError}
          <Button
            variant="outline"
            size="sm"
            className="ms-3"
            onClick={() => void load()}
          >
            {t.retry}
          </Button>
        </div>
      ) : !listing.configured ? (
        <p className="text-sm text-muted-foreground">{t.notConfigured}</p>
      ) : (
        <form
          onSubmit={connect}
          noValidate
          aria-labelledby={labelledBy}
          className="space-y-5"
        >
          {listing.service_account_email && (
            <div className="text-sm">
              <p>{t.shareStep}</p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <code
                  id="drive-service-email"
                  dir="ltr"
                  className="max-w-full break-all rounded bg-muted px-2 py-1 text-xs"
                >
                  {listing.service_account_email}
                </code>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  aria-describedby="drive-service-email"
                  onClick={() =>
                    void copyAddress(listing.service_account_email ?? "")
                  }
                >
                  <Copy size={14} aria-hidden />
                  {t.copy}
                </Button>
              </div>
              <p className="mt-3">{t.pasteStep}</p>
            </div>
          )}
          <fieldset disabled={busy} className="space-y-5">
            <div>
              <label
                htmlFor="drive-folder"
                className="mb-2 block text-sm font-medium"
              >
                {t.folderLabel}
              </label>
              <input
                id="drive-folder"
                // The form appears once the folders load, after the step opened.
                autoFocus
                inputMode="url"
                maxLength={2048}
                value={link}
                dir="ltr"
                onChange={(e) => {
                  setLink(e.target.value);
                  setFormError(null);
                }}
                placeholder="https://drive.google.com/drive/folders/…"
                aria-describedby={
                  formError ? "drive-hint drive-error" : "drive-hint"
                }
                aria-invalid={formError !== null}
                className="h-11 w-full rounded-lg border border-border bg-background px-3 text-start text-sm focus-visible:outline-2 focus-visible:outline-primary"
              />
              <p
                id="drive-hint"
                className="mt-2 text-xs leading-5 text-muted-foreground"
              >
                {t.folderHint}
              </p>
            </div>
            {kindField({ id: "drive-kind", value: kind, onChange: setKind })}
          </fieldset>
          {formError && (
            <p id="drive-error" role="alert" className="text-sm text-red-800">
              {t.errors[formError] ?? t.generic}
            </p>
          )}
          <Button type="submit" disabled={busy}>
            {busy ? (
              <LoaderCircle size={16} className="animate-spin" />
            ) : (
              <FolderSync size={16} />
            )}
            {busy ? t.connecting : t.connect}
          </Button>
        </form>
      )}
      <p role="status" className="text-sm text-primary">
        {notice}
      </p>
    </div>
  );
}

// Connected folders, managed from the Knowledge Base page. Shows nothing until a
// folder is connected; connecting happens in the add-source dialog.
export function DriveFolders({
  locale,
  onSynced,
  version,
}: {
  locale: Locale;
  // A sync finished: the Knowledge Base list should show what it added or removed.
  onSynced: () => void;
  // Bumped when a folder is connected, so the list reads it.
  version: number;
}) {
  const t = messages[locale];
  const [listing, setListing] = useState<Listing | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [confirm, setConfirm] = useState<string | null>(null);
  const wasSyncing = useRef(new Set<string>());

  const load = useCallback(async () => {
    try {
      const data = await fetchListing();
      setListing(data);
      setLoadFailed(false);
      const finished = data.items.filter(
        (folder) => wasSyncing.current.has(folder.id) && !syncing(folder),
      );
      wasSyncing.current = new Set(
        data.items.filter(syncing).map((folder) => folder.id),
      );
      if (finished.length) {
        setNotice(finished.map((folder) => t.synced(folder.name)).join(" "));
        onSynced();
      }
    } catch {
      setLoadFailed(true);
    }
  }, [onSynced, t]);
  useEffect(() => {
    void load();
  }, [load, version]);
  const active = listing?.items.some(syncing) ?? false;
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => void load(), POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [active, load]);

  async function act(folder: Folder, action: "sync" | "disconnect") {
    setBusy(`${action}-${folder.id}`);
    setNotice("");
    setRowError(null);
    try {
      const response = await fetch(
        `/api/knowledge/drive-folders/${folder.id}${action === "sync" ? "/sync" : ""}`,
        { method: action === "sync" ? "POST" : "DELETE" },
      );
      if (!response.ok) throw new Error();
      if (action === "disconnect") {
        setConfirm(null);
        setNotice(t.disconnected);
        onSynced();
      }
      await load();
    } catch {
      setRowError(folder.id);
    } finally {
      setBusy(null);
    }
  }

  const time = (value: string) =>
    new Intl.DateTimeFormat(locale, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));

  if (loadFailed && listing === null)
    return (
      // Not an alert: nothing the owner did failed, and the page's own alerts stay alone.
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
        {t.loadError}
        <Button
          variant="outline"
          size="sm"
          className="ms-3"
          onClick={() => void load()}
        >
          {t.retry}
        </Button>
      </div>
    );
  // The last folder's disconnect notice stays until the next action.
  if (!listing?.configured || (!listing.items.length && !notice)) return null;
  return (
    <section
      aria-labelledby="drive-heading"
      className="rounded-2xl border border-border bg-card p-6 sm:p-9"
    >
      <h3 id="drive-heading" className="mb-4 text-lg font-semibold">
        {t.folders}
      </h3>
      <ul className="space-y-3">
        {listing.items.map((folder) => (
          <li key={folder.id} className="rounded-xl border border-border p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h4
                dir="auto"
                className="min-w-0 max-w-full break-words font-medium"
              >
                {folder.name || folder.folder_id}
              </h4>
              <span className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-3 py-1 text-xs text-primary">
                {syncing(folder) && (
                  <LoaderCircle
                    size={12}
                    className="animate-spin"
                    aria-hidden
                  />
                )}
                {t.status[folder.status]}
              </span>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              {folder.synced_at &&
              !Number.isNaN(Date.parse(folder.synced_at)) ? (
                <>
                  {t.lastSynced}{" "}
                  <time dateTime={folder.synced_at}>
                    {time(folder.synced_at)}
                  </time>
                </>
              ) : (
                t.neverSynced
              )}
              {" · "}
              {t.files(folder.document_count, folder.skipped_count)}
              {" · "}
              {t.newFilesAs(t.kinds[folder.kind])}
            </p>
            {folder.status === "Failed" && folder.error_code && (
              <p className="mt-3 text-sm text-red-800">
                {t.errors[folder.error_code] ?? t.generic} {t.syncErrorNote}
              </p>
            )}
            {rowError === folder.id && (
              <p role="alert" className="mt-3 text-sm text-red-800">
                {t.generic}
              </p>
            )}
            {confirm === folder.id ? (
              <div
                role="group"
                aria-labelledby={`drive-confirm-${folder.id}`}
                className="mt-4 rounded-lg bg-muted p-4"
              >
                <p id={`drive-confirm-${folder.id}`} className="text-sm">
                  {t.confirm(folder.document_count)}
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    disabled={busy !== null}
                    onClick={() => void act(folder, "disconnect")}
                  >
                    {t.confirmYes}
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
            ) : (
              <div className="mt-4 flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busy !== null || syncing(folder)}
                  aria-label={`${t.sync}: ${folder.name}`}
                  onClick={() => void act(folder, "sync")}
                >
                  <RefreshCw size={14} aria-hidden />
                  {t.sync}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busy !== null}
                  aria-label={`${t.disconnect}: ${folder.name}`}
                  onClick={() => setConfirm(folder.id)}
                >
                  <Unlink size={14} aria-hidden />
                  {t.disconnect}
                </Button>
              </div>
            )}
          </li>
        ))}
      </ul>
      <p role="status" className="mt-3 text-sm text-primary">
        {notice}
      </p>
    </section>
  );
}
