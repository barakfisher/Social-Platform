export const locales = ["en", "he"] as const;
export type Locale = (typeof locales)[number];
export const copy = {
  en: {
    product: "Social Platform",
    workspace: "Your brand workspace",
    nav: ["Brand DNA", "Knowledge Base", "Create Post", "History"],
    eyebrow: "YOUR CONTENT STUDIO",
    title: "A clear voice. Every post.",
    subtitle:
      "Build your brand foundation, bring your knowledge, and turn ideas into drafts worth sharing.",
    phase: "Draft studio · Phase 1",
    start: "Set up your brand",
    step: "Start here",
    brandTitle: "Give your brand a voice",
    brandBody:
      "Define your audience, positioning, and tone. Your Brand DNA will guide every draft.",
    knowledgeTitle: "Bring your expertise",
    knowledgeBody:
      "Your documents and notes will give your posts the context they need.",
    createTitle: "Make room for your next idea",
    createBody:
      "Grounded English and Hebrew drafts for LinkedIn and Facebook, shaped by your brand.",
    historyTitle: "Your drafts, together",
    historyBody:
      "Saved drafts will appear here as you build your content library.",
    upcoming: "Coming in the first working flow",
    empty: "Your workspace is ready to take shape.",
    language: "Switch to Hebrew",
    help: "Made for your ideas. Shaped by your brand.",
  },
  he: {
    product: "Social Platform",
    workspace: "סביבת העבודה של המותג שלך",
    nav: ["זהות המותג", "מאגר ידע", "יצירת פוסט", "היסטוריה"],
    eyebrow: "סטודיו התוכן שלך",
    title: "קול ברור. בכל פוסט.",
    subtitle:
      "בונים את יסודות המותג, מוסיפים ידע והופכים רעיונות לטיוטות ששווה לשתף.",
    phase: "סטודיו לטיוטות · שלב 1",
    start: "הגדרת המותג",
    step: "מתחילים כאן",
    brandTitle: "נותנים למותג שלך קול",
    brandBody: "מגדירים קהל יעד, מיצוב וסגנון. זהות המותג תנחה כל טיוטה.",
    knowledgeTitle: "מוסיפים את המומחיות שלך",
    knowledgeBody: "המסמכים וההערות שלך יעניקו לפוסטים את ההקשר הדרוש.",
    createTitle: "מקום לרעיון הבא שלך",
    createBody:
      "טיוטות מבוססות ידע בעברית ובאנגלית ללינקדאין ולפייסבוק, בקול של המותג שלך.",
    historyTitle: "כל הטיוטות במקום אחד",
    historyBody: "הטיוטות השמורות יופיעו כאן עם בניית ספריית התוכן שלך.",
    upcoming: "בקרוב בתהליך העבודה הראשון",
    empty: "סביבת העבודה שלך מוכנה להתחלה.",
    language: "Switch to English",
    help: "מקום לרעיונות שלך. בקול של המותג שלך.",
  },
};
export const sections = ["brand", "knowledge", "create", "history"] as const;
