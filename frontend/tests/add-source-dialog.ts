import type { Page } from "@playwright/test";

// The Knowledge Base adds sources through a dialog: pick the kind, then fill its form.
type Choice = "text" | "file" | "url" | "drive";
const LABELS = {
  en: {
    open: "Add a source",
    text: "Write or paste text",
    file: "Upload a file",
    url: "Add a web page",
    drive: "Connect a Google Drive folder",
  },
  he: {
    open: "הוספת מקור",
    text: "כתיבה או הדבקת טקסט",
    file: "העלאת קובץ",
    url: "הוספת דף אינטרנט",
    drive: "חיבור תיקייה מ-Google Drive",
  },
};

// Focus returns here when the dialog closes.
export const addSourceButton = (page: Page) => page.locator("#add-source");

export async function openAddSource(
  page: Page,
  locale: "en" | "he",
  choice: Choice,
) {
  const labels = LABELS[locale];
  await page
    .getByRole("button", { name: labels.open, exact: true })
    .first()
    .click();
  // A choice's name is its title followed by its hint.
  await page
    .getByRole("dialog", { name: labels.open })
    .getByRole("button", { name: labels[choice] })
    .click();
}
