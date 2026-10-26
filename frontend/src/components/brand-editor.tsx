"use client";
import { useEffect, useRef, useState } from "react";
import { Check, Fingerprint, LoaderCircle, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Locale } from "@/lib/i18n";

const fields = [
  "name",
  "audience",
  "positioning",
  "voice",
  "guidelines",
  "prohibited_claims",
] as const;
type Field = (typeof fields)[number];
type Profile = Record<Field, string> & { version: number };
const blank: Profile = {
  name: "",
  audience: "",
  positioning: "",
  voice: "",
  guidelines: "",
  prohibited_claims: "",
  version: 0,
};
const messages = {
  en: {
    title: "Give your brand a voice",
    description:
      "Set the foundation for every post. Start with a name and add the details that make your brand yours.",
    labels: [
      "Brand name",
      "Audience",
      "Positioning",
      "Tone of voice",
      "Guidelines",
      "Prohibited claims",
    ],
    hints: [
      "Your company or personal brand",
      "Who are you speaking to?",
      "What do you offer, and what makes it different?",
      "For example: clear, warm, and confident",
      "Preferred wording, structure, and style",
      "Claims or topics your content must avoid",
    ],
    required: "Required",
    optional: "Optional",
    save: "Save Brand DNA",
    saving: "Saving…",
    loading: "Loading your brand…",
    saved: "Brand DNA saved",
    unsaved: "Unsaved changes",
    loadError: "We couldn’t load your brand. Please try again.",
    saveError: "We couldn’t save your changes. Your edits are still here.",
    conflict:
      "This profile was updated elsewhere. Copy any edits you want to keep, then reload the saved profile.",
    retry: "Try again",
    reload: "Reload saved profile",
    invalid: "Enter a brand name.",
    help: "Write in English, Hebrew, or a mix of both. Only the brand name is required.",
  },
  he: {
    title: "נותנים למותג שלך קול",
    description:
      "הבסיס לכל פוסט. מתחילים בשם ומוסיפים את הפרטים שמייחדים את המותג שלך.",
    labels: [
      "שם המותג",
      "קהל יעד",
      "מיצוב",
      "טון וסגנון",
      "הנחיות",
      "טענות אסורות",
    ],
    hints: [
      "שם העסק או המותג האישי שלך",
      "למי התוכן שלך מיועד?",
      "מה ההצעה שלך ומה מייחד אותה?",
      "למשל: ברור, חם ובטוח",
      "מילים מועדפות, מבנה וסגנון כתיבה",
      "טענות או נושאים שיש להימנע מהם",
    ],
    required: "חובה",
    optional: "רשות",
    save: "שמירת זהות המותג",
    saving: "שומר…",
    loading: "טוען את המותג שלך…",
    saved: "זהות המותג נשמרה",
    unsaved: "שינויים שלא נשמרו",
    loadError: "לא הצלחנו לטעון את המותג. אפשר לנסות שוב.",
    saveError: "לא הצלחנו לשמור את השינויים. העריכות שלך עדיין כאן.",
    conflict:
      "הפרופיל עודכן במקום אחר. יש להעתיק עריכות שברצונך לשמור, ואז לטעון את הפרופיל השמור.",
    retry: "ניסיון נוסף",
    reload: "טעינת הפרופיל השמור",
    invalid: "יש להזין שם למותג.",
    help: "אפשר לכתוב בעברית, באנגלית או בשילוב של שתיהן. רק שם המותג הוא שדה חובה.",
  },
};
export function BrandEditor({ locale }: { locale: Locale }) {
  const t = messages[locale];
  const [profile, setProfile] = useState<Profile>(blank);
  const [baseline, setBaseline] = useState<Profile>(blank);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<
    "loadError" | "saveError" | "conflict" | "invalid" | null
  >(null);
  const [saved, setSaved] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const errorRef = useRef<HTMLDivElement>(null);
  const dirty = JSON.stringify(profile) !== JSON.stringify(baseline);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetch("/api/brand", { signal: controller.signal, cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error();
        return response.json();
      })
      .then((data) => {
        const value = data ?? { ...blank };
        setProfile(value);
        setBaseline(value);
        setSaved(false);
      })
      .catch(() => {
        if (!controller.signal.aborted) setError("loadError");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [attempt]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (dirty) event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!profile.name.trim()) {
      setError("invalid");
      return;
    }
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const response = await fetch("/api/brand", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(profile),
      });
      if (!response.ok) {
        setError(response.status === 409 ? "conflict" : "saveError");
        return;
      }
      const value: Profile = await response.json();
      setProfile(value);
      setBaseline(value);
      setSaved(true);
    } catch {
      setError("saveError");
    } finally {
      setSaving(false);
    }
  }
  return (
    <section
      className="mt-10 rounded-2xl border border-border bg-card p-6 sm:p-9"
      aria-labelledby="brand-title"
    >
      <div className="mb-5 inline-flex rounded-xl bg-primary/10 p-3 text-primary">
        <Fingerprint size={25} />
      </div>
      <h2 id="brand-title" className="text-2xl font-semibold">
        {t.title}
      </h2>
      <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
        {t.description}
      </p>
      {loading ? (
        <p role="status" className="mt-8 flex items-center gap-2">
          <LoaderCircle size={18} className="animate-spin" />
          {t.loading}
        </p>
      ) : (
        <>
          {error && (
            <div
              ref={errorRef}
              tabIndex={-1}
              role="alert"
              className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800"
            >
              {t[error]}
              {(error === "loadError" || error === "conflict") && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="ms-3 mt-2"
                  onClick={() => setAttempt(attempt + 1)}
                >
                  {error === "conflict" ? t.reload : t.retry}
                </Button>
              )}
            </div>
          )}
          {error !== "loadError" && (
            <form onSubmit={save} className="mt-8">
              <fieldset disabled={saving} className="grid gap-6 sm:grid-cols-2">
                {fields.map((field, i) => (
                  <div
                    key={field}
                    className={field === "name" ? "sm:col-span-2" : ""}
                  >
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <label
                        htmlFor={`brand-${field}`}
                        className="text-sm font-medium"
                      >
                        {t.labels[i]}
                      </label>
                      <span className="text-xs text-muted-foreground">
                        {i === 0 ? t.required : t.optional}
                      </span>
                    </div>
                    {field === "name" ? (
                      <input
                        id={`brand-${field}`}
                        dir={
                          profile[field]
                            ? "auto"
                            : locale === "he"
                              ? "rtl"
                              : "ltr"
                        }
                        required
                        maxLength={200}
                        value={profile[field]}
                        placeholder={t.hints[i]}
                        onChange={(e) => {
                          setProfile({ ...profile, [field]: e.target.value });
                          setSaved(false);
                        }}
                        className="h-11 w-full rounded-lg border border-border bg-background px-3 text-start text-sm focus-visible:outline-2 focus-visible:outline-primary"
                      />
                    ) : (
                      <textarea
                        id={`brand-${field}`}
                        dir={
                          profile[field]
                            ? "auto"
                            : locale === "he"
                              ? "rtl"
                              : "ltr"
                        }
                        rows={4}
                        maxLength={i >= 4 ? 10000 : 5000}
                        value={profile[field]}
                        placeholder={t.hints[i]}
                        onChange={(e) => {
                          setProfile({ ...profile, [field]: e.target.value });
                          setSaved(false);
                        }}
                        className="w-full resize-y rounded-lg border border-border bg-background px-3 py-3 text-start text-sm leading-6 focus-visible:outline-2 focus-visible:outline-primary"
                      />
                    )}
                  </div>
                ))}
              </fieldset>
              <p className="mt-5 text-xs leading-5 text-muted-foreground">
                {t.help}
              </p>
              <div className="mt-7 flex flex-wrap items-center gap-4 border-t border-border pt-6">
                <Button
                  type="submit"
                  disabled={saving || !dirty || error === "conflict"}
                >
                  {saving ? (
                    <LoaderCircle size={16} className="animate-spin" />
                  ) : (
                    <Save size={16} />
                  )}
                  {saving ? t.saving : t.save}
                </Button>
                <span
                  role="status"
                  className="flex items-center gap-2 text-sm text-muted-foreground"
                >
                  {saved ? (
                    <>
                      <Check size={16} className="text-primary" />
                      {t.saved}
                    </>
                  ) : dirty ? (
                    t.unsaved
                  ) : (
                    ""
                  )}
                </span>
              </div>
            </form>
          )}
        </>
      )}
    </section>
  );
}
