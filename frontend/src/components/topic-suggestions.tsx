"use client";
import { useState } from "react";
import { Lightbulb, LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { apiRequest } from "@/lib/posts";
import type { Locale } from "@/lib/i18n";

type Suggestion = {
  topic: string;
  rationale: string;
  sources: { chunk_id: string; document_id: string; title: string }[];
};
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
    basedOn: "Based on",
    empty:
      "No topic could be tied to your sources this time. Try again, or add sources to your Knowledge Base.",
    insufficient:
      "Your Knowledge Base has no ready sources yet. Add a source and enable AI search first.",
    spendingLimit:
      "Suggesting topics would exceed the per-request AI cost limit set on the server.",
    error: "Topic ideas couldn’t be loaded. Try again.",
  },
  he: {
    suggest: "הצעת נושאים",
    suggesting: "מחפשים נושאים במקורות שלך…",
    hint: "רעיונות ממאגר הידע שלך. בחירה ברעיון ממלאת את הנושא.",
    title: "רעיונות לנושאים",
    use: "לכתוב על זה",
    basedOn: "על סמך",
    empty:
      "הפעם לא נמצא נושא שאפשר לקשר למקורות שלך. אפשר לנסות שוב או להוסיף מקורות למאגר הידע.",
    insufficient:
      "אין עדיין מקורות מוכנים במאגר הידע. יש להוסיף מקור ולהפעיל עבורו חיפוש AI.",
    spendingLimit: "הצעת נושאים תחרוג ממגבלת העלות של AI לבקשה שהוגדרה בשרת.",
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
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<SuggestionsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  async function suggest() {
    setBusy(true);
    setError(null);
    try {
      const data = await apiRequest<SuggestionsResponse>(
        "/api/generation/topic-suggestions",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            platform: request.platform,
            language: request.language,
            goal: request.goal,
            count: 3,
            writer_model: request.writer_model || null,
          }),
        },
      );
      setResult(data);
    } catch (caught) {
      setResult(null);
      setError(caught instanceof Error ? caught.message : "api_unavailable");
    } finally {
      setBusy(false);
    }
  }
  const message =
    error === "insufficient_context"
      ? t.insufficient
      : error === "generation_spending_limit"
        ? t.spendingLimit
        : t.error;
  return (
    <div className="mt-3 space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="button"
          variant="outline"
          disabled={disabled || busy}
          onClick={suggest}
        >
          {busy ? (
            <LoaderCircle className="animate-spin" size={16} />
          ) : (
            <Lightbulb size={16} />
          )}
          {busy ? t.suggesting : t.suggest}
        </Button>
        <p className="text-xs text-muted-foreground">{t.hint}</p>
      </div>
      {error && (
        <p role="alert" className="text-sm text-red-800">
          {message}
        </p>
      )}
      {result && result.suggestions.length === 0 && (
        <p role="status" className="text-sm text-muted-foreground">
          {t.empty}
        </p>
      )}
      {result && result.suggestions.length > 0 && (
        <section
          aria-label={t.title}
          data-testid="topic-suggestions"
          className="space-y-2"
        >
          <h3 className="text-sm font-medium">{t.title}</h3>
          <ul className="space-y-2">
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
                    {[...new Set(suggestion.sources.map((s) => s.title))].join(
                      ", ",
                    )}
                  </span>
                </p>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="mt-2"
                  onClick={() => onChoose(suggestion.topic)}
                >
                  {t.use}
                </Button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
