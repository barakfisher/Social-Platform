import { test, expect, type Page } from "@playwright/test";
import type { GeneratedPost, Review, SavedPost } from "../src/lib/posts";

const checked: Review = {
  status: "checked",
  findings: [],
  reason: null,
  retryable: false,
};
const run: GeneratedPost = {
  id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
  platform: "linkedin",
  language: "he",
  content: "מנטור הוא יועץ מנוסה. מנטורים מכפילים קידומים, כמו GPS לקריירה!",
  grounded: false,
  warnings: [],
  sources: [
    {
      chunk_id: "chunk-1",
      document_id: "doc-1",
      title: "מנטורינג ויקיפדיה",
      content: "מנטור הוא אדם המשמש כיועץ או מדריך.",
      source_location: {},
    },
  ],
  offer_details: "קורס מנטורינג למנהלים, מתחיל ב-1.12",
  metadata: {
    model: "test/model",
    brand_version: 1,
    prompt_version: "grounded-post-v4",
    grounding_review: {
      ...checked,
      findings: [
        {
          code: "unsupported_claim",
          sentence: "מנטורים מכפילים קידומים, כמו GPS לקריירה!",
          claim: "מנטורים מכפילים קידומים",
        },
        { code: "brand_style", sentence: null, claim: null },
      ],
    },
    preferences: { review_model: "openai/gpt-5.6-terra" },
  },
};
const reviewModels = {
  default: "openai/gpt-5.6-terra",
  models: [
    {
      id: "openai/gpt-5.6-terra",
      available: true,
      typical_usd: 0.016,
      max_usd: 0.063,
    },
  ],
};

async function mockGeneration(
  page: Page,
  result: GeneratedPost,
  onPost: (url: string, body: Record<string, unknown>) => unknown = () =>
    result,
) {
  await page.route("**/api/generation**", async (route) => {
    const url = route.request().url();
    if (route.request().method() === "GET") {
      await route.fulfill({
        json: url.endsWith("/review-models")
          ? reviewModels
          : { configured: true, brand_ready: true, ready_documents: 1 },
      });
      return;
    }
    await route.fulfill({ json: onPost(url, route.request().postDataJSON()) });
  });
}

test("findings appear in a separate panel, never inside the draft text", async ({
  page,
}) => {
  let sent: Record<string, unknown> = {};
  await mockGeneration(page, run, (_, body) => {
    sent = body;
    return run;
  });
  await page.goto("/he/create");
  await page.getByLabel("על מה נכתוב?", { exact: true }).fill("מה זה מנטורינג");
  await page.getByText("העדפות כתיבה", { exact: true }).click();
  await page.getByLabel("טון וסגנון").selectOption("humorous");
  await page.getByLabel("הנעה לפעולה").selectOption("signup");
  await expect(page.getByText("עובדת הכי טוב עם פרטי ההצעה")).toBeVisible();
  await page.getByLabel("פרטי ההצעה (רשות)").fill(run.offer_details);
  await page.getByRole("button", { name: "יצירת טיוטה", exact: true }).click();

  const draft = page.getByLabel("הטיוטה שלך", { exact: true });
  await expect(draft).toHaveValue(run.content);
  expect(sent).toMatchObject({
    tone: "humorous",
    tone_other: "",
    cta: "signup",
    cta_other: "",
    offer_details: run.offer_details,
  });
  const panel = page.getByTestId("review-findings");
  await expect(panel.getByRole("heading")).toHaveText("נקודות לבדיקה");
  await expect(panel.locator("blockquote")).toHaveText(
    "מנטורים מכפילים קידומים",
  );
  await expect(panel).toContainText("אין מקור שתומך בטענה הזו.");
  await expect(panel).toContainText("הנוסח לא תואם את קול המותג");
  // Checked findings need no retry until the text changes.
  await expect(panel.getByRole("button")).toHaveCount(0);
  await page.getByText("מקורות ששימשו לכתיבה (2)", { exact: true }).click();
  await expect(
    page.getByText("פרטי ההצעה (ממך)", { exact: true }),
  ).toBeVisible();
  for (const width of [390, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
  }
});

test("a clean review shows a confirmation line", async ({ page }) => {
  await mockGeneration(page, {
    ...run,
    grounded: true,
    metadata: { ...run.metadata, grounding_review: checked },
  });
  await page.goto("/en/create");
  await page
    .getByLabel("What would you like to write about?")
    .fill("Mentoring");
  await page
    .getByRole("button", { name: "Generate draft", exact: true })
    .click();
  await expect(page.getByTestId("review-clean")).toHaveText(
    "Every factual claim was found in your sources.",
  );
  await expect(page.getByTestId("review-findings")).toHaveCount(0);
});

test("an empty Other… blocks submission and Other text is sent", async ({
  page,
}) => {
  let posts = 0;
  let sent: Record<string, unknown> = {};
  await mockGeneration(page, run, (_, body) => {
    posts++;
    sent = body;
    return run;
  });
  await page.goto("/en/create");
  await page
    .getByLabel("What would you like to write about?")
    .fill("Mentoring");
  await page.getByText("Writing preferences", { exact: true }).click();
  await page.getByLabel("Call to action").selectOption("other");
  const other = page.getByLabel("Describe the call to action");
  await page
    .getByRole("button", { name: "Generate draft", exact: true })
    .click();
  expect(
    await other.evaluate((el: HTMLInputElement) => el.validity.valueMissing),
  ).toBe(true);
  expect(posts).toBe(0);
  await other.fill("Reply with your favorite mentor");
  await page
    .getByRole("button", { name: "Generate draft", exact: true })
    .click();
  await expect(page.getByLabel("Your draft", { exact: true })).toBeVisible();
  expect(sent).toMatchObject({
    cta: "other",
    cta_other: "Reply with your favorite mentor",
  });
});

const unchecked = (reason: string, retryable: boolean): GeneratedPost => ({
  ...run,
  language: "en",
  content: "Mentors give advice.",
  metadata: {
    ...run.metadata,
    grounding_review: {
      ...checked,
      status: "unchecked" as const,
      reason,
      retryable,
    },
  },
});

test("an unchecked draft explains why and checks the stored version again", async ({
  page,
}) => {
  const urls: string[] = [];
  await mockGeneration(
    page,
    unchecked("generation_unavailable", true),
    (url, body) => {
      urls.push(url);
      if (url.endsWith("/review")) {
        expect(body).toEqual({});
        return {
          ...unchecked("generation_unavailable", true),
          grounded: true,
          metadata: { ...run.metadata, grounding_review: checked },
        };
      }
      return unchecked("generation_unavailable", true);
    },
  );
  await page.goto("/en/create");
  await page
    .getByLabel("What would you like to write about?")
    .fill("Mentoring");
  await page
    .getByRole("button", { name: "Generate draft", exact: true })
    .click();
  const panel = page.getByTestId("review-findings");
  await expect(panel.getByRole("heading")).toContainText(
    "The source check did not complete",
  );
  await expect(panel).toContainText("Another try usually works.");
  await expect(panel).toContainText("~$0.016 per draft");

  // Unsaved edits cannot be checked: only server-saved text is reviewed.
  const draft = page.getByLabel("Your draft", { exact: true });
  await draft.fill("Mentors give advice. Edited.");
  await expect(
    panel.getByRole("button", { name: "Check again" }),
  ).toBeDisabled();
  await expect(panel).toContainText("Save your edits to check them.");
  await draft.fill("Mentors give advice.");

  await panel.getByRole("button", { name: "Check again" }).click();
  await expect(page.getByTestId("review-clean")).toBeVisible();
  expect(urls.at(-1)).toContain(`/api/generation/${run.id}/review`);
});

test("a non-retryable failure explains why without offering a retry", async ({
  page,
}) => {
  await mockGeneration(page, unchecked("generation_spending_limit", false));
  await page.goto("/he/create");
  await page.getByLabel("על מה נכתוב?", { exact: true }).fill("מנטורינג");
  await page.getByRole("button", { name: "יצירת טיוטה", exact: true }).click();
  const panel = page.getByTestId("review-findings");
  await expect(panel).toContainText("ממגבלת העלות לבקשה");
  await expect(panel.getByRole("button")).toHaveCount(0);
});

test("a blocked saved draft keeps its text, shows do-not-publish, and is checkable only after a new save", async ({
  page,
}) => {
  let stored: SavedPost = {
    id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
    platform: "linkedin",
    language: "en",
    content: "Mentors give advice. Use promo code ZEBRA.",
    status: "Draft",
    version: 1,
    sources: [],
    generation_run_id: null,
    generation_settings: {
      grounding_review: {
        ...checked,
        status: "blocked",
        reason: "draft_blocked",
        checked_version: 1,
      },
      preferences: { review_model: "openai/gpt-5.6-terra" },
    },
    created_at: "2026-10-27T10:00:00Z",
  };
  const reviews: string[] = [];
  await page.route("**/api/generation/review-models", (route) =>
    route.fulfill({ json: reviewModels }),
  );
  await page.route("**/api/posts**", async (route) => {
    const request = route.request();
    if (request.url().endsWith("/review")) {
      reviews.push(request.postDataJSON().version);
      stored = {
        ...stored,
        generation_settings: {
          ...stored.generation_settings,
          grounding_review: { ...checked, checked_version: stored.version },
        },
      };
      await route.fulfill({ json: stored });
      return;
    }
    if (request.method() === "PUT") {
      stored = {
        ...stored,
        content: request.postDataJSON().content,
        version: stored.version + 1,
      };
      await route.fulfill({ json: stored });
      return;
    }
    await route.fulfill({ json: { items: [stored], total: 1 } });
  });
  await page.goto("/en/history");
  await page.getByRole("button", { name: "Edit draft", exact: true }).click();
  const panel = page.getByTestId("review-findings");
  await expect(panel.getByRole("heading")).toHaveText(
    "Do not publish this draft",
  );
  await expect(page.getByLabel("Draft content", { exact: true })).toHaveValue(
    stored.content,
  );
  await expect(panel.getByRole("button")).toHaveCount(0);

  await page
    .getByLabel("Draft content", { exact: true })
    .fill("Mentors give advice.");
  await expect(panel).toContainText("Save your edits to check them.");
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await panel.getByRole("button", { name: "Check again" }).click();
  await expect(page.getByTestId("review-clean")).toBeVisible();
  expect(reviews).toEqual([2]);
});
