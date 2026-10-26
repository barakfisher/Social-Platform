"use client";
import { useCallback, useEffect, useState } from "react";
import { BookOpen, Plus, LoaderCircle, RefreshCw, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Locale } from "@/lib/i18n";

type Document = {
  id: string;
  title: string;
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
    limit: "Up to 100,000 characters. PDF and URL sources come later.",
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
    limit: "עד 100,000 תווים. קובצי PDF וקישורים יתווספו בהמשך.",
    next: "מקורות קודמים",
    previous: "מקורות חדשים יותר",
    deleted: "המקור נמחק.",
    dispatch: "לא ניתן היה להתחבר לשירות העיבוד. אפשר לנסות לעבד שוב.",
    failure: "העיבוד לא הסתיים. אפשר לנסות שוב.",
    invalid: "יש להזין כותרת וטקסט.",
  },
};
export function KnowledgeBase({ locale }: { locale: Locale }) {
  const t = messages[locale];
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    fetch("/api/knowledge/configuration", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => setConnected(data?.configured === true))
      .catch(() => setConnected(false));
  }, []);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [items, setItems] = useState<Document[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const [notice, setNotice] = useState<
    "saved" | "duplicate" | "deleted" | "invalid" | null
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
                        : t.failure}
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
