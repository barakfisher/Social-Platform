"use client";
import {
  CheckCircle2,
  LoaderCircle,
  RotateCw,
  TriangleAlert,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Locale } from "@/lib/i18n";
import type { Review } from "@/lib/posts";

type Copy = {
  title: string;
  clean: string;
  uncheckedTitle: string;
  blockedTitle: string;
  blocked: string;
  stale: string;
  recheck: string;
  rechecking: string;
  saveFirst: string;
  findings: Record<string, [problem: string, action: string]>;
  unknownFinding: [string, string];
  reasons: Record<string, string>;
  unknownReason: string;
};
const copy: Record<Locale, Copy> = {
  en: {
    title: "Points to check",
    clean: "Every factual claim was found in your sources.",
    uncheckedTitle:
      "The source check did not complete. The facts in this draft were not checked.",
    blockedTitle: "Do not publish this draft",
    blocked:
      "It repeats instructions found in a source or your offer details, which usually means a source tried to steer the AI. Remove that text from the draft and check your sources, then save and check again.",
    stale: "These notes refer to an earlier version, before your edits.",
    recheck: "Check again",
    rechecking: "Checking…",
    saveFirst: "Save your edits to check them.",
    findings: {
      unsupported_claim: [
        "No source supports this claim.",
        "Remove or rephrase it, or add a source that states it.",
      ],
      contradicted_claim: [
        "This contradicts a source or your offer details.",
        "Correct it to match the source.",
      ],
      wrong_language: [
        "Parts of the draft are not in the requested language.",
        "Edit or generate again.",
      ],
      brand_style: [
        "This does not match your brand voice or guidelines.",
        "Adjust the wording.",
      ],
      prohibited_claim: [
        "The draft makes a claim your brand prohibits.",
        "Remove that claim.",
      ],
      off_topic: [
        "The draft strays from the topic.",
        "Refocus it on the topic.",
      ],
      platform_fit: [
        "The draft does not suit the platform.",
        "Adjust its length or style.",
      ],
    },
    unknownFinding: [
      "The checker flagged this.",
      "Review it before publishing.",
    ],
    reasons: {
      generation_unavailable:
        "The checking service did not respond. Another try usually works.",
      grounding_review_invalid:
        "The checker returned an invalid answer. Try again, or choose another source check model.",
      review_model_unavailable:
        "The source check model is not available right now. Choose another model and try again.",
      generation_model_unavailable:
        "The source check model is not available right now. Choose another model and try again.",
      generation_catalog_unavailable:
        "The model catalog could not be reached. Try again in a moment.",
      generation_spending_limit:
        "The check would cost more than the per-request limit set on the server.",
      generation_prompt_limit:
        "The draft and its sources are too long to check in one pass. Shorten the draft.",
      generation_context_limit:
        "The draft and its sources are too long to check in one pass. Shorten the draft.",
    },
    unknownReason:
      "The source check could not run. Check the service settings.",
  },
  he: {
    title: "נקודות לבדיקה",
    clean: "כל הטענות העובדתיות נמצאו במקורות שלך.",
    uncheckedTitle: "בדיקת המקורות לא הושלמה. העובדות בטיוטה לא נבדקו.",
    blockedTitle: "אין לפרסם את הטיוטה הזו",
    blocked:
      "היא חוזרת על הוראות שמופיעות במקור או בפרטי ההצעה, ובדרך כלל זה סימן שמקור ניסה לכוון את ה-AI. יש להסיר את הטקסט הזה מהטיוטה ולבדוק את המקורות, ואז לשמור ולבדוק שוב.",
    stale: "ההערות מתייחסות לגרסה קודמת, לפני העריכות שלך.",
    recheck: "בדוק שוב",
    rechecking: "בודק…",
    saveFirst: "יש לשמור את העריכות כדי לבדוק אותן.",
    findings: {
      unsupported_claim: [
        "אין מקור שתומך בטענה הזו.",
        "אפשר להסיר או לנסח מחדש, או להוסיף מקור שמציין אותה.",
      ],
      contradicted_claim: [
        "הטענה סותרת מקור או את פרטי ההצעה.",
        "כדאי לתקן לפי המקור.",
      ],
      wrong_language: [
        "חלקים מהטיוטה אינם בשפה שנבחרה.",
        "אפשר לערוך או ליצור מחדש.",
      ],
      brand_style: [
        "הנוסח לא תואם את קול המותג או ההנחיות.",
        "כדאי להתאים את הניסוח.",
      ],
      prohibited_claim: [
        "הטיוטה כוללת טענה שהמותג אוסר.",
        "יש להסיר את הטענה.",
      ],
      off_topic: ["הטיוטה סוטה מהנושא.", "כדאי למקד אותה בנושא."],
      platform_fit: [
        "הטיוטה לא מתאימה לפלטפורמה.",
        "כדאי להתאים אורך או סגנון.",
      ],
    },
    unknownFinding: ["הבודק סימן את זה.", "כדאי לבדוק לפני פרסום."],
    reasons: {
      generation_unavailable:
        "שירות הבדיקה לא הגיב. בדרך כלל ניסיון נוסף מצליח.",
      grounding_review_invalid:
        "הבודק החזיר תשובה לא תקינה. אפשר לנסות שוב או לבחור מודל בדיקה אחר.",
      review_model_unavailable:
        "מודל הבדיקה לא זמין כרגע. אפשר לבחור מודל אחר ולנסות שוב.",
      generation_model_unavailable:
        "מודל הבדיקה לא זמין כרגע. אפשר לבחור מודל אחר ולנסות שוב.",
      generation_catalog_unavailable:
        "לא הצלחנו להגיע לקטלוג המודלים. אפשר לנסות שוב בעוד רגע.",
      generation_spending_limit:
        "הבדיקה הייתה עולה יותר ממגבלת העלות לבקשה שהוגדרה בשרת.",
      generation_prompt_limit:
        "הטיוטה והמקורות ארוכים מדי לבדיקה אחת. כדאי לקצר את הטיוטה.",
      generation_context_limit:
        "הטיוטה והמקורות ארוכים מדי לבדיקה אחת. כדאי לקצר את הטיוטה.",
    },
    unknownReason:
      "לא ניתן היה להריץ את בדיקת המקורות. כדאי לבדוק את הגדרות השירות.",
  },
};

export function ReviewFindings({
  locale,
  review,
  stale,
  canRecheck,
  busy,
  cost,
  onRecheck,
}: {
  locale: Locale;
  review: Review | undefined;
  // The text on screen differs from the version the review applies to.
  stale: boolean;
  // False while there are unsaved edits: only a server-saved version can be checked.
  canRecheck: boolean;
  busy: boolean;
  cost?: string;
  onRecheck?: () => void;
}) {
  const t = copy[locale];
  if (!review) return null;
  const unchecked = review.status === "unchecked";
  const blocked = review.status === "blocked";
  // A block is lifted only by checking a newly saved version, never by retrying.
  const offerRecheck = onRecheck && ((unchecked && review.retryable) || stale);
  if (!unchecked && !blocked && review.findings.length === 0 && !stale)
    return (
      <p
        data-testid="review-clean"
        className="mt-4 flex items-center gap-2 text-sm text-primary"
      >
        <CheckCircle2 size={16} aria-hidden className="shrink-0" />
        {t.clean}
      </p>
    );
  return (
    <section
      aria-labelledby="review-findings-title"
      data-testid="review-findings"
      className={
        "mt-5 rounded-lg border p-4 text-sm " +
        (blocked
          ? "border-red-300 bg-red-50 text-red-900"
          : "border-amber-200 bg-amber-50 text-amber-950")
      }
    >
      <h4
        id="review-findings-title"
        className="flex items-center gap-2 font-medium"
      >
        <TriangleAlert size={16} aria-hidden className="shrink-0" />
        {blocked ? t.blockedTitle : unchecked ? t.uncheckedTitle : t.title}
      </h4>
      {stale && <p className="mt-2 text-xs">{t.stale}</p>}
      {blocked ? (
        <p className="mt-2">{t.blocked}</p>
      ) : unchecked ? (
        <p className="mt-2">
          {t.reasons[review.reason ?? ""] ?? t.unknownReason}
        </p>
      ) : (
        <ul className="mt-3 space-y-3">
          {review.findings.map((finding, index) => {
            const [problem, action] =
              t.findings[finding.code] ?? t.unknownFinding;
            return (
              <li key={index} className="rounded-md bg-white/70 p-3">
                {finding.claim && (
                  <blockquote
                    dir="auto"
                    className="border-s-2 border-amber-400 ps-3 italic"
                  >
                    {finding.claim}
                  </blockquote>
                )}
                <p className={finding.claim ? "mt-2" : ""}>{problem}</p>
                <p className="mt-1 text-xs text-amber-900/80">{action}</p>
              </li>
            );
          })}
        </ul>
      )}
      {offerRecheck && (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            disabled={busy || !canRecheck}
            onClick={onRecheck}
          >
            {busy ? (
              <LoaderCircle className="animate-spin" size={14} />
            ) : (
              <RotateCw size={14} />
            )}
            {busy ? t.rechecking : t.recheck}
          </Button>
          {canRecheck ? (
            cost && <span className="text-xs">{cost}</span>
          ) : (
            <span className="text-xs">{t.saveFirst}</span>
          )}
        </div>
      )}
    </section>
  );
}
