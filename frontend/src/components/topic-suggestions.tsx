"use client";
import { useEffect, useId, useRef, useState } from "react";
import { Lightbulb, LoaderCircle, RefreshCw, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { apiRequest } from "@/lib/posts";
import type { Locale } from "@/lib/i18n";

type Suggestion = {
  topic: string;
  rationale: string;
  sources: { chunk_id: string; document_id: string; title: string }[];
};
// How many ideas one click asks for; the server allows up to five.
const SUGGESTION_COUNT = 3;
type SuggestionsResponse = {
  suggestions: Suggestion[];
  reason: string | null;
};
const copy = {
  en: {
    suggest: "Suggest topics",
    suggesting: "Finding topics in your sources…",
    hint: "Ideas from your Knowledge Base. Choosing one fills in the topic.",
    title: "Topic ideas",
    use: "Use this topic",
    again: "Suggest other ideas",
    close: "Close",
    basedOn: "Sources it cites",
    empty:
      "No topic could be tied to your sources this time. Try again, or add sources to your Knowledge Base.",
    insufficient:
      "Your Knowledge Base has no ready sources yet. Add a source and enable AI search first.",
    spendingLimit:
      "Suggesting topics would exceed the per-request AI cost limit set on the server.",
    promptLimit:
      "Your brand profile is too long to suggest topics. Shorten its guidance and try again.",
    writerUnavailable:
      "The selected writing model is no longer available. Choose another and try again.",
    error: "Topic ideas couldn’t be loaded. Try again.",
  },
  he: {
    suggest: "הצעת נושאים",
    suggesting: "מחפשים נושאים במקורות שלך…",
    hint: "רעיונות ממאגר הידע שלך. בחירה ברעיון ממלאת את הנושא.",
    title: "רעיונות לנושאים",
    use: "לכתוב על זה",
    again: "להציע רעיונות אחרים",
    close: "סגירה",
    basedOn: "מקורות שצוינו",
    empty:
      "הפעם לא נמצא נושא שאפשר לקשר למקורות שלך. אפשר לנסות שוב או להוסיף מקורות למאגר הידע.",
    insufficient:
      "אין עדיין מקורות מוכנים במאגר הידע. יש להוסיף מקור ולהפעיל עבורו חיפוש AI.",
    spendingLimit: "הצעת נושאים תחרוג ממגבלת העלות של AI לבקשה שהוגדרה בשרת.",
    promptLimit:
      "זהות המותג ארוכה מדי להצעת נושאים. אפשר לקצר את ההנחיות ולנסות שוב.",
    writerUnavailable:
      "מודל הכתיבה שנבחר כבר לא זמין. יש לבחור מודל אחר ולנסות שוב.",
    error: "לא הצלחנו לטעון רעיונות לנושאים. אפשר לנסות שוב.",
  },
};

export function TopicSuggestions({
  locale,
  request,
  disabled,
  onChoose,
}: {
  locale: Locale;
  // What the post is for: the same platform, language, goal and writer as the draft.
  request: {
    platform: string;
    language: string;
    goal: string;
    writer_model: string;
  };
  disabled: boolean;
  onChoose: (topic: string) => void;
}) {
  const t = copy[locale];
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<SuggestionsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Ideas belong to the platform, language, goal and writer they were asked for.
  const { platform, language, goal, writer_model } = request;
  const signature = JSON.stringify([platform, language, goal, writer_model]);
  const current = useRef(signature);
  useEffect(() => {
    current.current = signature;
    setResult(null);
    setError(null);
  }, [signature]);
  async function suggest() {
    const asked = signature;
    setBusy(true);
    setError(null);
    try {
      const data = await apiRequest<SuggestionsResponse>(
        "/api/generation/topic-suggestions",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            platform,
            language,
            goal,
            count: SUGGESTION_COUNT,
            writer_model: writer_model || null,
          }),
        },
      );
      // The dialog may have been closed and the form changed while this was in flight.
      if (current.current === asked) setResult(data);
    } catch (caught) {
      if (current.current === asked) {
        setResult(null);
        setError(caught instanceof Error ? caught.message : "api_unavailable");
      }
    } finally {
      setBusy(false);
    }
  }
  // Ideas cost a paid request, so reopening shows the ones already found for the same inputs.
  function open() {
    dialog.current?.showModal();
    if (!busy && !result?.suggestions.length) void suggest();
  }
  function close() {
    dialog.current?.close();
  }
  function choose(topic: string) {
    close();
    onChoose(topic);
  }
  const message =
    error === "insufficient_context"
      ? t.insufficient
      : error === "generation_spending_limit"
        ? t.spendingLimit
        : error === "generation_prompt_limit"
          ? t.promptLimit
          : [
                "writer_model_unavailable",
                "generation_model_unavailable",
              ].includes(error ?? "")
            ? t.writerUnavailable
            : t.error;
  return (
    <div className="mt-3 flex flex-wrap items-center gap-3">
      <Button
        type="button"
        variant="outline"
        disabled={disabled}
        aria-haspopup="dialog"
        onClick={open}
      >
        <Lightbulb size={16} />
        {t.suggest}
      </Button>
      <p className="text-xs text-muted-foreground">{t.hint}</p>
      <dialog
        ref={dialog}
        aria-labelledby={titleId}
        // The dialog box has no padding, so a click on it (not its content) is on the backdrop.
        onClick={(event) => event.target === event.currentTarget && close()}
        className="m-auto w-[calc(100%-2rem)] max-w-xl rounded-2xl border border-border bg-card text-foreground shadow-xl backdrop:bg-black/40"
      >
        <div className="max-h-[85vh] space-y-4 overflow-y-auto p-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 id={titleId} className="text-lg font-semibold">
                {t.title}
              </h2>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                {t.hint}
              </p>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              aria-label={t.close}
              onClick={close}
            >
              <X size={18} />
            </Button>
          </div>
          {busy && (
            <p
              role="status"
              className="flex items-center gap-2 text-sm text-muted-foreground"
            >
              <LoaderCircle className="animate-spin" size={16} />
              {t.suggesting}
            </p>
          )}
          {!busy && error && (
            <p role="alert" className="text-sm text-red-800">
              {message}
            </p>
          )}
          {!busy && result && result.suggestions.length === 0 && (
            <p role="status" className="text-sm text-muted-foreground">
              {t.empty}
            </p>
          )}
          {!busy && result && result.suggestions.length > 0 && (
            <ul data-testid="topic-suggestions" className="space-y-2">
              {result.suggestions.map((suggestion) => (
                <li
                  key={suggestion.topic}
                  className="rounded-lg border border-border p-3"
                >
                  <p dir="auto" className="text-sm font-medium leading-6">
                    {suggestion.topic}
                  </p>
                  <p
                    dir="auto"
                    className="mt-1 text-xs leading-5 text-muted-foreground"
                  >
                    {suggestion.rationale}
                  </p>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">
                    {t.basedOn}:{" "}
                    <span dir="auto">
                      {[
                        ...new Set(suggestion.sources.map((s) => s.title)),
                      ].join(", ")}
                    </span>
                  </p>
                  <Button
                    type="button"
                    size="sm"
                    className="mt-2"
                    onClick={() => choose(suggestion.topic)}
                  >
                    {t.use}
                  </Button>
                </li>
              ))}
            </ul>
          )}
          <Button
            type="button"
            variant="outline"
            disabled={busy}
            onClick={() => void suggest()}
          >
            <RefreshCw size={16} />
            {t.again}
          </Button>
        </div>
      </dialog>
    </div>
  );
}
