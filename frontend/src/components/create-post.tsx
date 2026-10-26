"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { LoaderCircle, PenLine, Save, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  apiRequest,
  inputClass,
  type GeneratedPost,
  type SavedPost,
} from "@/lib/posts";
import type { Locale } from "@/lib/i18n";
const copy = {
  en: {
    title: "Turn knowledge into your next post",
    body: "Choose a topic and a platform. Your Brand DNA and relevant sources will shape an editable draft.",
    platform: "Platform",
    language: "Post language",
    topic: "What would you like to write about?",
    topicHint: "Describe the idea or question your post should explore",
    goal: "Goal",
    tone: "Tone of voice",
    hook: "Hook",
    length: "Post length",
    cta: "Call to action",
    advanced: "Writing preferences",
    generate: "Generate draft",
    generating: "Writing your draft…",
    save: "Save Draft",
    saved: "Draft saved",
    output: "Your draft",
    sources: "Sources used",
    review:
      "Check factual claims against the sources before using this draft. AI may add unsupported details.",
    warnings: "Review notes",
    groundingFailed:
      "The draft did not pass its source check and was withheld. Try a narrower topic or add supporting knowledge.",
    noSources:
      "No source references were returned. Review factual claims carefully.",
    interrupted:
      "Generation was interrupted. Your inputs are preserved; try again to start a new request.",
    error:
      "We couldn’t complete that request. Your input and edits are still here.",
    brand: "Set up Brand DNA",
    knowledge: "Prepare knowledge sources",
    setupBrand: "Add your Brand DNA before generating a post.",
    setupKnowledge: "At least one source must be Ready for AI search.",
    setupKey: "The writing service is not connected yet.",
    checking: "Checking your workspace…",
    short: "Short",
    medium: "Medium",
    long: "Long",
    auto: "Automatic",
    question: "Question",
    insight: "Insight",
    story: "Story",
    media: "Images and topic suggestions will be available in a later step.",
    history: "Open History",
    insufficient:
      "No sufficiently relevant knowledge was found. Add or enable AI search for sources about this topic.",
    conflict:
      "This draft changed elsewhere. Open History to load its latest version before saving.",
    brandLimit:
      "Your brand profile and topic exceed the writing context limit. Shorten the guidance or topic and try again.",
    spendingLimit:
      "This request would exceed the per-request AI cost limit set on the server. Your inputs are preserved; try a shorter topic or raise the limit in the server settings.",
    usage: "Based on Brand DNA version",
    chars: "characters",
    defaults:
      "Defaults: brand voice, automatic hook, medium length, no call to action.",
    reviewModel: "Source check model",
    reviewHint:
      "Estimated cost of the source check per draft: typical, and the most the server will reserve. Writing and search are billed separately.",
    perDraft: "per draft",
    upTo: "up to",
    recommended: "recommended",
    costUnavailable: "cost unavailable",
    unavailable: "unavailable",
    loadingModels: "Loading models…",
    modelsUnavailable:
      "Model options couldn’t be loaded. The default source check will be used.",
    reviewModelUnavailable:
      "The selected source check model is no longer available. Choose another and try again.",
    notes: {
      "openai/gpt-5.6-terra": "stricter",
      "openai/gpt-4.1": "cheaper, less strict",
    } as Record<string, string>,
  },
  he: {
    title: "הופכים ידע לפוסט הבא שלך",
    body: "בוחרים נושא ופלטפורמה. זהות המותג ומקורות רלוונטיים יעצבו טיוטה שאפשר לערוך.",
    platform: "פלטפורמה",
    language: "שפת הפוסט",
    topic: "על מה נכתוב?",
    topicHint: "תיאור הרעיון או השאלה שהפוסט יעסוק בהם",
    goal: "מטרה",
    tone: "טון וסגנון",
    hook: "פתיחה",
    length: "אורך הפוסט",
    cta: "הנעה לפעולה",
    advanced: "העדפות כתיבה",
    generate: "יצירת טיוטה",
    generating: "כותב את הטיוטה…",
    save: "שמירת טיוטה",
    saved: "הטיוטה נשמרה",
    output: "הטיוטה שלך",
    sources: "מקורות ששימשו לכתיבה",
    review:
      "יש לבדוק את הטענות מול המקורות לפני שימוש בטיוטה. AI עלול להוסיף פרטים שאינם מבוססים.",
    warnings: "הערות לבדיקה",
    groundingFailed:
      "הטיוטה לא עברה את בדיקת המקורות ולא הוצגה. אפשר למקד את הנושא או להוסיף מקורות תומכים.",
    noSources: "לא הוחזרו הפניות למקורות. חשוב לבדוק את הטענות העובדתיות.",
    interrupted:
      "יצירת הטיוטה הופסקה. הפרטים שהזנת נשמרו; נסו שוב כדי להתחיל בקשה חדשה.",
    error: "לא הצלחנו להשלים את הבקשה. הקלט והעריכות שלך עדיין כאן.",
    brand: "הגדרת זהות המותג",
    knowledge: "הכנת מקורות ידע",
    setupBrand: "יש להגדיר את זהות המותג לפני יצירת פוסט.",
    setupKnowledge: "נדרש לפחות מקור אחד שמוכן לחיפוש AI.",
    setupKey: "שירות הכתיבה עדיין לא מחובר.",
    checking: "בודק את סביבת העבודה…",
    short: "קצר",
    medium: "בינוני",
    long: "ארוך",
    auto: "אוטומטית",
    question: "שאלה",
    insight: "תובנה",
    story: "סיפור",
    media: "תמונות והצעות לנושאים יתווספו בשלב הבא.",
    history: "פתיחת ההיסטוריה",
    insufficient:
      "לא נמצא ידע רלוונטי מספיק. אפשר להוסיף מקורות בנושא ולהפעיל עבורם חיפוש AI.",
    conflict:
      "הטיוטה עודכנה במקום אחר. יש לפתוח את ההיסטוריה ולטעון את הגרסה העדכנית לפני שמירה.",
    brandLimit:
      "זהות המותג והנושא חורגים ממגבלת ההקשר. אפשר לקצר את ההנחיות או הנושא ולנסות שוב.",
    spendingLimit:
      "הבקשה חורגת ממגבלת העלות של AI לבקשה שהוגדרה בשרת. הפרטים שהזנת נשמרו; אפשר לקצר את הנושא או להעלות את המגבלה בהגדרות השרת.",
    usage: "מבוסס על גרסת זהות המותג",
    chars: "תווים",
    defaults:
      "ברירת המחדל: קול המותג, פתיחה אוטומטית, אורך בינוני, ללא הנעה לפעולה.",
    reviewModel: "מודל לבדיקת המקורות",
    reviewHint:
      "עלות משוערת של בדיקת המקורות לכל טיוטה: עלות טיפוסית, והסכום המרבי שהשרת ישריין. הכתיבה והחיפוש מחויבים בנפרד.",
    perDraft: "לטיוטה",
    upTo: "עד",
    recommended: "מומלץ",
    costUnavailable: "העלות אינה זמינה",
    unavailable: "לא זמין",
    loadingModels: "טוען מודלים…",
    modelsUnavailable:
      "לא הצלחנו לטעון את אפשרויות המודל. תתבצע בדיקת המקורות המוגדרת כברירת מחדל.",
    reviewModelUnavailable:
      "המודל שנבחר לבדיקת המקורות כבר לא זמין. יש לבחור מודל אחר ולנסות שוב.",
    notes: {
      "openai/gpt-5.6-terra": "בדיקה מחמירה",
      "openai/gpt-4.1": "זול יותר, פחות מחמיר",
    } as Record<string, string>,
  },
};
type Capability = {
  configured: boolean;
  brand_ready: boolean;
  ready_documents: number;
};
type ReviewModelOption = {
  id: string;
  available: boolean;
  typical_usd: number | null;
  max_usd: number | null;
};
type ReviewModels = { default: string; models: ReviewModelOption[] };
// Display names only; the server owns the allowlist and the prices.
const modelNames: Record<string, string> = {
  "openai/gpt-5.6-terra": "GPT-5.6 Terra",
  "openai/gpt-4.1": "GPT-4.1",
};
function isReviewModels(data: unknown): data is ReviewModels {
  const value = data as ReviewModels | null;
  return (
    typeof value?.default === "string" &&
    Array.isArray(value.models) &&
    value.models.every((m) => typeof m?.id === "string")
  );
}
export function CreatePost({ locale }: { locale: Locale }) {
  const t = copy[locale];
  const [capability, setCapability] = useState<Capability | null>(null);
  const [form, setForm] = useState({
    platform: "linkedin",
    language: locale,
    topic: "",
    goal: locale === "he" ? "שיתוף ידע" : "Educate",
    tone: "",
    hook: "auto",
    length: "medium",
    cta: "",
    // Empty means the server's default source-check model.
    review_model: "",
  });
  const [reviewModels, setReviewModels] = useState<
    ReviewModels | "error" | null
  >(null);
  const [generated, setGenerated] = useState<GeneratedPost | null>(null);
  const [content, setContent] = useState("");
  const [saved, setSaved] = useState<SavedPost | null>(null);
  const [savedContent, setSavedContent] = useState("");
  const [busy, setBusy] = useState<"generate" | "save" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const request = useRef<{ signature: string; key: string } | null>(null);
  const saveKey = useRef<string>("");
  useEffect(() => {
    apiRequest<Capability>("/api/generation/configuration")
      .then(setCapability)
      .catch(() => setError("api_unavailable"));
    apiRequest<unknown>("/api/generation/review-models")
      .then((data) => setReviewModels(isReviewModels(data) ? data : "error"))
      .catch(() => setReviewModels("error"));
  }, []);
  const money = new Intl.NumberFormat(locale === "he" ? "he-IL" : "en-US", {
    style: "currency",
    currency: "USD",
    maximumSignificantDigits: 2,
  });
  function modelCost(option: ReviewModelOption) {
    return !option.available
      ? t.unavailable
      : option.typical_usd !== null && option.max_usd !== null
        ? `~${money.format(option.typical_usd)} ${t.perDraft} · ${t.upTo} ${money.format(option.max_usd)}`
        : t.costUnavailable;
  }
  function modelLabel(option: ReviewModelOption, defaultId: string) {
    const notes = [
      option.id === defaultId ? t.recommended : null,
      t.notes[option.id] ?? null,
    ].filter(Boolean);
    return `${modelNames[option.id] ?? option.id}${notes.length ? ` (${notes.join(", ")})` : ""} — ${modelCost(option)}`;
  }
  // A closed select truncates long options on phones, so the chosen cost is repeated below.
  const selectedModel =
    reviewModels && reviewModels !== "error"
      ? reviewModels.models.find(
          (option) => option.id === (form.review_model || reviewModels.default),
        )
      : undefined;
  async function generate(event: React.FormEvent) {
    event.preventDefault();
    setBusy("generate");
    setError(null);
    const signature = JSON.stringify(form);
    if (request.current?.signature !== signature)
      request.current = { signature, key: crypto.randomUUID() };
    try {
      const result = await apiRequest<GeneratedPost>("/api/generation", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...form, request_key: request.current!.key }),
      });
      setGenerated(result);
      setContent(result.content);
      setSaved(null);
      setSavedContent("");
      saveKey.current = crypto.randomUUID();
      request.current = null;
    } catch (error) {
      const code = error instanceof Error ? error.message : "api_unavailable";
      setError(code);
      // Preserve the key after an ambiguous network failure; reuse any already completed result.
      if (!["api_unavailable", "generation_in_progress"].includes(code))
        request.current = null;
    } finally {
      setBusy(null);
    }
  }
  async function save() {
    if (!generated) return;
    setBusy("save");
    setError(null);
    try {
      const body = {
        platform: generated.platform,
        language: generated.language,
        content,
        status: "Draft",
        ...(saved
          ? { version: saved.version }
          : { save_key: saveKey.current, generation_run_id: generated.id }),
      };
      const result = await apiRequest<SavedPost>(
        saved ? `/api/posts/${saved.id}` : "/api/posts",
        {
          method: saved ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
      );
      setSaved(result);
      setSavedContent(result.content);
    } catch (error) {
      setError(error instanceof Error ? error.message : "api_unavailable");
    } finally {
      setBusy(null);
    }
  }
  const allowed =
    !!capability?.configured &&
    capability.brand_ready &&
    capability.ready_documents > 0;
  const message = [
    "grounding_review_failed",
    "grounding_review_invalid",
    "insufficient_grounding",
  ].includes(error ?? "")
    ? t.groundingFailed
    : error === "generation_interrupted"
      ? t.interrupted
      : error === "insufficient_context"
        ? t.insufficient
        : error === "brand_setup_required"
          ? t.setupBrand
          : error === "draft_edit_conflict"
            ? t.conflict
            : ["generation_prompt_limit", "generation_topic_too_long"].includes(
                  error ?? "",
                )
              ? t.brandLimit
              : error === "generation_spending_limit"
                ? t.spendingLimit
                : error === "review_model_unavailable"
                  ? t.reviewModelUnavailable
                  : t.error;
  return (
    <section aria-labelledby="create-title" className="mt-10 space-y-6">
      <div className="rounded-2xl border border-border bg-card p-6 sm:p-9">
        <PenLine className="mb-5 text-primary" size={25} />
        <h2 id="create-title" className="text-2xl font-semibold">
          {t.title}
        </h2>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">{t.body}</p>
        {!capability ? (
          <p role="status" className="mt-5">
            {t.checking}
          </p>
        ) : (
          !allowed && (
            <div className="mt-5 rounded-lg bg-muted p-4 text-sm leading-7">
              {!capability.configured
                ? t.setupKey
                : !capability.brand_ready
                  ? t.setupBrand
                  : t.setupKnowledge}
              <div className="mt-2 flex gap-4">
                <Link className="underline" href={`/${locale}/brand`}>
                  {t.brand}
                </Link>
                <Link className="underline" href={`/${locale}/knowledge`}>
                  {t.knowledge}
                </Link>
              </div>
            </div>
          )
        )}
        <form onSubmit={generate} className="mt-7 space-y-5">
          <fieldset disabled={busy !== null} className="space-y-5">
            <div className="grid gap-5 sm:grid-cols-2">
              <div>
                <label
                  className="mb-2 block text-sm font-medium"
                  htmlFor="post-platform"
                >
                  {t.platform}
                </label>
                <select
                  id="post-platform"
                  className={inputClass}
                  value={form.platform}
                  onChange={(e) =>
                    setForm({ ...form, platform: e.target.value })
                  }
                >
                  <option value="linkedin">LinkedIn</option>
                  <option value="facebook">Facebook</option>
                </select>
              </div>
              <div>
                <label
                  className="mb-2 block text-sm font-medium"
                  htmlFor="post-language"
                >
                  {t.language}
                </label>
                <select
                  id="post-language"
                  className={inputClass}
                  value={form.language}
                  onChange={(e) =>
                    setForm({ ...form, language: e.target.value as Locale })
                  }
                >
                  <option value="en">English</option>
                  <option value="he">עברית</option>
                </select>
              </div>
            </div>
            <div>
              <label
                htmlFor="post-topic"
                className="mb-2 block text-sm font-medium"
              >
                {t.topic}
              </label>
              <textarea
                id="post-topic"
                className={inputClass}
                rows={4}
                required
                maxLength={2000}
                dir={form.topic ? "auto" : locale === "he" ? "rtl" : "ltr"}
                placeholder={t.topicHint}
                value={form.topic}
                onChange={(e) => setForm({ ...form, topic: e.target.value })}
              />
            </div>
            <div>
              <label
                htmlFor="post-goal"
                className="mb-2 block text-sm font-medium"
              >
                {t.goal}
              </label>
              <input
                id="post-goal"
                className={inputClass}
                maxLength={300}
                dir="auto"
                value={form.goal}
                onChange={(e) => setForm({ ...form, goal: e.target.value })}
              />
            </div>
            <details className="rounded-lg border border-border p-4">
              <summary className="cursor-pointer text-sm font-medium">
                {t.advanced}
              </summary>
              <p className="mt-3 text-xs text-muted-foreground">{t.defaults}</p>
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <div>
                  <label htmlFor="post-tone" className="mb-2 block text-sm">
                    {t.tone}
                  </label>
                  <input
                    id="post-tone"
                    className={inputClass}
                    maxLength={200}
                    dir="auto"
                    value={form.tone}
                    onChange={(e) => setForm({ ...form, tone: e.target.value })}
                  />
                </div>
                <div>
                  <label htmlFor="post-hook" className="mb-2 block text-sm">
                    {t.hook}
                  </label>
                  <select
                    id="post-hook"
                    className={inputClass}
                    value={form.hook}
                    onChange={(e) => setForm({ ...form, hook: e.target.value })}
                  >
                    {(["auto", "question", "insight", "story"] as const).map(
                      (key) => (
                        <option key={key} value={key}>
                          {t[key]}
                        </option>
                      ),
                    )}
                  </select>
                </div>
                <div>
                  <label htmlFor="post-length" className="mb-2 block text-sm">
                    {t.length}
                  </label>
                  <select
                    id="post-length"
                    className={inputClass}
                    value={form.length}
                    onChange={(e) =>
                      setForm({ ...form, length: e.target.value })
                    }
                  >
                    {(["short", "medium", "long"] as const).map((key) => (
                      <option key={key} value={key}>
                        {t[key]}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor="post-cta" className="mb-2 block text-sm">
                    {t.cta}
                  </label>
                  <input
                    id="post-cta"
                    className={inputClass}
                    maxLength={300}
                    dir="auto"
                    value={form.cta}
                    onChange={(e) => setForm({ ...form, cta: e.target.value })}
                  />
                </div>
                <div className="sm:col-span-2">
                  <label
                    htmlFor={
                      reviewModels === "error" ? undefined : "post-review-model"
                    }
                    className="mb-2 block text-sm"
                  >
                    {t.reviewModel}
                  </label>
                  {reviewModels === "error" ? (
                    <p role="status" className="text-xs text-muted-foreground">
                      {t.modelsUnavailable}
                    </p>
                  ) : (
                    <select
                      id="post-review-model"
                      className={inputClass}
                      aria-describedby="post-review-model-hint"
                      disabled={reviewModels === null}
                      value={form.review_model || reviewModels?.default || ""}
                      onChange={(e) =>
                        setForm({ ...form, review_model: e.target.value })
                      }
                    >
                      {reviewModels === null ? (
                        <option value="">{t.loadingModels}</option>
                      ) : (
                        reviewModels.models.map((option) => (
                          <option
                            key={option.id}
                            value={option.id}
                            disabled={!option.available}
                          >
                            {modelLabel(option, reviewModels.default)}
                          </option>
                        ))
                      )}
                    </select>
                  )}
                  {selectedModel && (
                    <p
                      data-testid="review-model-cost"
                      aria-live="polite"
                      className="mt-2 text-sm"
                    >
                      {modelCost(selectedModel)}
                    </p>
                  )}
                  <p
                    id="post-review-model-hint"
                    className="mt-2 text-xs text-muted-foreground"
                  >
                    {t.reviewHint}
                  </p>
                </div>
              </div>
            </details>
          </fieldset>
          <Button disabled={!allowed || busy !== null} type="submit">
            {busy === "generate" ? (
              <LoaderCircle className="animate-spin" size={16} />
            ) : (
              <Sparkles size={16} />
            )}
            {busy === "generate" ? t.generating : t.generate}
          </Button>
          <p className="text-xs text-muted-foreground">{t.media}</p>
        </form>
      </div>
      {error && (
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800"
        >
          {message}
        </div>
      )}
      {generated && (
        <div className="rounded-2xl border border-border bg-card p-6 sm:p-9">
          <h3 className="text-lg font-semibold">{t.output}</h3>
          <p className="mt-2 text-sm text-muted-foreground">{t.review}</p>
          {(!generated.grounded || generated.warnings.length > 0) && (
            <div
              role="note"
              className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm"
            >
              <p className="font-medium">{t.warnings}</p>
              {!generated.grounded && <p className="mt-2">{t.noSources}</p>}
              {generated.warnings
                .filter((w) => w !== "insufficient_grounding")
                .map((w, i) => (
                  <p key={i} dir="auto" className="mt-2">
                    {w}
                  </p>
                ))}
            </div>
          )}
          <label htmlFor="generated-content" className="sr-only">
            {t.output}
          </label>
          <textarea
            id="generated-content"
            className={inputClass + " mt-5"}
            rows={12}
            dir="auto"
            maxLength={generated.platform === "linkedin" ? 3000 : 5000}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            disabled={busy !== null}
          />
          <p className="mt-2 text-xs text-muted-foreground">
            {content.length} {t.chars} · {t.usage}{" "}
            {generated.metadata.brand_version}
          </p>
          <div className="mt-5 flex flex-wrap items-center gap-4">
            <Button
              disabled={
                busy !== null || !content.trim() || content === savedContent
              }
              onClick={() => void save()}
            >
              <Save size={16} />
              {t.save}
            </Button>
            <span role="status" className="text-sm text-primary">
              {saved && content === savedContent ? t.saved : ""}
            </span>
            {saved && (
              <Link className="text-sm underline" href={`/${locale}/history`}>
                {t.history}
              </Link>
            )}
          </div>
          {generated.sources.length > 0 && (
            <details className="mt-6 border-t border-border pt-4">
              <summary className="cursor-pointer text-sm font-medium">
                {t.sources} ({generated.sources.length})
              </summary>
              <ul className="mt-4 space-y-4">
                {generated.sources.map((s) => (
                  <li key={s.chunk_id} className="rounded-lg bg-background p-4">
                    <p className="font-medium" dir="auto">
                      {s.title}
                    </p>
                    <p
                      dir="auto"
                      className="mt-2 whitespace-pre-wrap text-sm leading-6 text-muted-foreground"
                    >
                      {s.content}
                    </p>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </section>
  );
}
