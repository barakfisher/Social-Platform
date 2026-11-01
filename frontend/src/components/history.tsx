"use client";
import { useCallback, useEffect, useState } from "react";
import { History as HistoryIcon, RefreshCw, Save, Trash2 } from "lucide-react";
import { ReviewFindings } from "@/components/review-findings";
import { Button } from "@/components/ui/button";
import {
  apiRequest,
  inputClass,
  knowledgeLevel,
  type SavedPost,
} from "@/lib/posts";
import type { Locale } from "@/lib/i18n";
const copy = {
  en: {
    title: "Your drafts, together",
    body: "Find, edit, and keep the posts you want to share. All posts here are drafts.",
    search: "Search drafts",
    platform: "Platform filter",
    all: "All platforms",
    empty: "No drafts found.",
    loading: "Loading drafts…",
    edit: "Edit draft",
    save: "Save changes",
    saved: "Changes saved",
    cancel: "Close editor",
    remove: "Delete",
    confirm: "Permanently delete this draft?",
    yes: "Delete draft",
    no: "Cancel",
    error: "We couldn’t complete that request. Your edits are still here.",
    conflict:
      "This draft was updated elsewhere. Copy any edits you want to keep before loading the latest version.",
    reload: "Load latest version",
    refresh: "Refresh",
    previous: "Newer drafts",
    next: "Older drafts",
    draft: "Draft",
    content: "Draft content",
    sources: "Saved source references",
    deleted: "Draft deleted.",
    reviewUnavailable:
      "This draft was not generated with the current source check, so it cannot be checked again.",
    perCheck: "per check",
    knowledgeLevel: "Knowledge level",
    knowledgeLevels: {
      general: "Knowledge Base + general professional knowledge",
      knowledge_base: "Knowledge Base only",
    },
  },
  he: {
    title: "כל הטיוטות במקום אחד",
    body: "מוצאים, עורכים ושומרים את הפוסטים שברצונך לשתף. כל הפוסטים כאן הם טיוטות.",
    search: "חיפוש בטיוטות",
    platform: "סינון לפי פלטפורמה",
    all: "כל הפלטפורמות",
    empty: "לא נמצאו טיוטות.",
    loading: "טוען טיוטות…",
    edit: "עריכת טיוטה",
    save: "שמירת שינויים",
    saved: "השינויים נשמרו",
    cancel: "סגירת העורך",
    remove: "מחיקה",
    confirm: "למחוק את הטיוטה לצמיתות?",
    yes: "מחיקת הטיוטה",
    no: "ביטול",
    error: "לא הצלחנו להשלים את הבקשה. העריכות שלך עדיין כאן.",
    conflict:
      "הטיוטה עודכנה במקום אחר. יש להעתיק עריכות שברצונך לשמור לפני טעינת הגרסה העדכנית.",
    reload: "טעינת הגרסה העדכנית",
    refresh: "רענון",
    previous: "טיוטות חדשות יותר",
    next: "טיוטות קודמות",
    draft: "טיוטה",
    content: "תוכן הטיוטה",
    sources: "הפניות שמורות למקורות",
    deleted: "הטיוטה נמחקה.",
    reviewUnavailable:
      "הטיוטה לא נוצרה עם בדיקת המקורות הנוכחית, ולכן אי אפשר לבדוק אותה שוב.",
    perCheck: "לבדיקה",
    knowledgeLevel: "רמת ידע",
    knowledgeLevels: {
      general: "בסיס הידע + ידע מקצועי כללי",
      knowledge_base: "מבסיס הידע בלבד",
    },
  },
};
export function History({ locale }: { locale: Locale }) {
  const t = copy[locale];
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [platform, setPlatform] = useState("");
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<SavedPost[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<SavedPost | null>(null);
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<"saved" | "deleted" | null>(null);
  const [confirm, setConfirm] = useState<string | null>(null);
  const [reviewing, setReviewing] = useState(false);
  // Typical source-check cost per model, shown next to "Check again".
  const [costs, setCosts] = useState<Record<string, number>>({});
  useEffect(() => {
    apiRequest<{ models: { id: string; typical_usd: number | null }[] }>(
      "/api/generation/review-models",
    )
      .then((data) =>
        setCosts(
          Object.fromEntries(
            data.models
              .filter((m) => m.typical_usd !== null)
              .map((m) => [m.id, m.typical_usd as number]),
          ),
        ),
      )
      .catch(() => setCosts({}));
  }, []);
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(query);
      setOffset(0);
    }, 300);
    return () => clearTimeout(timer);
  }, [query]);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiRequest<{ items: SavedPost[]; total: number }>(
        `/api/posts?offset=${offset}&limit=20&q=${encodeURIComponent(search)}${platform ? "&platform=" + platform : ""}`,
      );
      setItems(data.items);
      setTotal(data.total);
    } catch {
      setError("api_unavailable");
    } finally {
      setLoading(false);
    }
  }, [offset, search, platform]);
  useEffect(() => {
    void load();
  }, [load]);
  async function save() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await apiRequest<SavedPost>(`/api/posts/${selected.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          platform: selected.platform,
          language: selected.language,
          status: "Draft",
          content,
          version: selected.version,
        }),
      });
      setSelected(result);
      setContent(result.content);
      setNotice("saved");
      await load();
    } catch (error) {
      setError(error instanceof Error ? error.message : "api_unavailable");
    } finally {
      setBusy(false);
    }
  }
  async function recheck() {
    if (!selected) return;
    setReviewing(true);
    setError(null);
    setNotice(null);
    try {
      const result = await apiRequest<SavedPost>(
        `/api/posts/${selected.id}/review`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ version: selected.version }),
        },
      );
      setSelected(result);
      setItems(items.map((post) => (post.id === result.id ? result : post)));
    } catch (error) {
      setError(error instanceof Error ? error.message : "api_unavailable");
    } finally {
      setReviewing(false);
    }
  }
  async function reload() {
    if (!selected) return;
    try {
      const data = await apiRequest<SavedPost>(`/api/posts/${selected.id}`);
      setSelected(data);
      setContent(data.content);
      setError(null);
    } catch {
      setError("api_unavailable");
    }
  }
  async function remove(id: string) {
    setBusy(true);
    setError(null);
    try {
      await apiRequest(`/api/posts/${id}`, { method: "DELETE" });
      setConfirm(null);
      setNotice("deleted");
      if (selected?.id === id) setSelected(null);
      if (items.length === 1 && offset > 0) setOffset(Math.max(0, offset - 20));
      else await load();
    } catch {
      setError("api_unavailable");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-labelledby="history-title" className="mt-10 space-y-6">
      <div className="rounded-2xl border border-border bg-card p-6 sm:p-9">
        <HistoryIcon size={25} className="mb-5 text-primary" />
        <h2 id="history-title" className="text-2xl font-semibold">
          {t.title}
        </h2>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">{t.body}</p>
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          <div>
            <label
              htmlFor="draft-search"
              className="mb-2 block text-sm font-medium"
            >
              {t.search}
            </label>
            <input
              id="draft-search"
              type="search"
              maxLength={200}
              dir="auto"
              value={query}
              className={inputClass}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div>
            <label
              htmlFor="draft-filter"
              className="mb-2 block text-sm font-medium"
            >
              {t.platform}
            </label>
            <select
              id="draft-filter"
              className={inputClass}
              value={platform}
              onChange={(e) => {
                setPlatform(e.target.value);
                setOffset(0);
              }}
            >
              <option value="">{t.all}</option>
              <option value="linkedin">LinkedIn</option>
              <option value="facebook">Facebook</option>
            </select>
          </div>
        </div>
        <div className="mt-4 flex items-center justify-between">
          <span className="text-sm text-muted-foreground">
            {total} · {t.draft}
          </span>
          <Button variant="ghost" size="sm" onClick={() => void load()}>
            <RefreshCw size={16} />
            {t.refresh}
          </Button>
        </div>
      </div>
      {error && (
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800"
        >
          {error === "draft_edit_conflict"
            ? t.conflict
            : error === "review_unavailable"
              ? t.reviewUnavailable
              : t.error}
          {error === "draft_edit_conflict" && (
            <Button
              variant="outline"
              className="ms-3"
              onClick={() => void reload()}
            >
              {t.reload}
            </Button>
          )}
        </div>
      )}
      <p role="status" className="text-sm text-primary">
        {notice ? t[notice] : ""}
      </p>
      {selected && (
        <div className="rounded-2xl border border-border bg-card p-6">
          <h3 className="mb-4 font-semibold">
            {t.edit} ·{" "}
            {selected.platform === "linkedin" ? "LinkedIn" : "Facebook"}
          </h3>
          {/* Only generated drafts carry the preferences they were written with. */}
          {selected.generation_settings.preferences && (
            <p
              data-testid="draft-knowledge-level"
              className="-mt-2 mb-4 text-xs text-muted-foreground"
            >
              {t.knowledgeLevel}:{" "}
              {
                t.knowledgeLevels[
                  knowledgeLevel(selected.generation_settings.preferences)
                ]
              }
            </p>
          )}
          <label htmlFor="draft-content" className="sr-only">
            {t.content}
          </label>
          <textarea
            id="draft-content"
            dir="auto"
            rows={10}
            maxLength={selected.platform === "linkedin" ? 3000 : 5000}
            value={content}
            onChange={(e) => {
              setContent(e.target.value);
              setNotice(null);
            }}
            disabled={busy}
            className={inputClass}
          />
          {(() => {
            const review = selected.generation_settings.grounding_review;
            const model =
              selected.generation_settings.preferences?.review_model ?? "";
            const cost = costs[model];
            return (
              <ReviewFindings
                locale={locale}
                review={review}
                stale={
                  review?.checked_version !== selected.version ||
                  content !== selected.content
                }
                canRecheck={content === selected.content}
                busy={reviewing}
                cost={
                  cost === undefined
                    ? undefined
                    : `~${new Intl.NumberFormat(locale === "he" ? "he-IL" : "en-US", { style: "currency", currency: "USD", maximumSignificantDigits: 2 }).format(cost)} ${t.perCheck}`
                }
                onRecheck={() => void recheck()}
              />
            );
          })()}
          <div className="mt-4 flex gap-3">
            <Button
              disabled={
                busy ||
                reviewing ||
                !content.trim() ||
                content === selected.content ||
                error === "draft_edit_conflict"
              }
              onClick={() => void save()}
            >
              <Save size={16} />
              {t.save}
            </Button>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => {
                setSelected(null);
                setError(null);
              }}
            >
              {t.cancel}
            </Button>
          </div>
          {selected.sources.length > 0 && (
            <details className="mt-5">
              <summary className="cursor-pointer text-sm font-medium">
                {t.sources}
              </summary>
              {selected.sources.map((source) => (
                <div
                  key={source.chunk_id}
                  className="mt-3 rounded-lg bg-background p-4"
                >
                  <p dir="auto" className="font-medium">
                    {source.title}
                  </p>
                  <p
                    dir="auto"
                    className="mt-2 whitespace-pre-wrap text-sm leading-6 text-muted-foreground"
                  >
                    {source.content}
                  </p>
                </div>
              ))}
            </details>
          )}
        </div>
      )}
      {loading ? (
        <p role="status">{t.loading}</p>
      ) : items.length === 0 ? (
        <p className="rounded-xl border border-border bg-card p-6 text-sm text-muted-foreground">
          {t.empty}
        </p>
      ) : (
        <ul className="space-y-4">
          {items.map((post) => (
            <li
              key={post.id}
              className="rounded-xl border border-border bg-card p-6"
            >
              <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
                <span>
                  {post.platform === "linkedin" ? "LinkedIn" : "Facebook"} ·{" "}
                  {t.draft}
                </span>
                <span>
                  {new Date(post.created_at).toLocaleDateString(
                    locale === "he" ? "he-IL" : "en-GB",
                  )}
                </span>
              </div>
              <p
                dir="auto"
                className="mt-4 line-clamp-4 whitespace-pre-wrap break-words text-sm leading-7"
              >
                {post.content}
              </p>
              <div className="mt-4 flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busy}
                  onClick={() => {
                    setSelected(post);
                    setContent(post.content);
                    setError(null);
                    setNotice(null);
                  }}
                >
                  {t.edit}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={busy}
                  onClick={() => setConfirm(post.id)}
                >
                  <Trash2 size={14} />
                  {t.remove}
                </Button>
              </div>
              {confirm === post.id && (
                <div className="mt-4 rounded-lg bg-muted p-4">
                  <p className="mb-3 text-sm">{t.confirm}</p>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      disabled={busy}
                      onClick={() => void remove(post.id)}
                    >
                      {t.yes}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setConfirm(null)}
                    >
                      {t.no}
                    </Button>
                  </div>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {(total > 20 || offset > 0) && (
        <div className="flex gap-3">
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
    </section>
  );
}
