import { test, expect, type Page } from "@playwright/test";
import type {
  GeneratedPost,
  KnowledgeShare,
  Review,
  SavedPost,
} from "../src/lib/posts";

const share: KnowledgeShare = {
  sourced_claims: 3,
  general_claims: 2,
  unsupported_claims: 1,
  percent: 50,
  general_sentences: 2,
};
const checked: Review = {
  status: "checked",
  findings: [
    {
      code: "unsupported_claim",
      sentence: "Our mentees are promoted twice as fast.",
      claim: "Our mentees are promoted twice as fast",
    },
  ],
  reason: null,
  retryable: false,
  knowledge_share: share,
};
const run: GeneratedPost = {
  id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
  platform: "linkedin",
  language: "en",
  content:
    "A mentor shortens the learning curve. Our mentees are promoted twice as fast.",
  grounded: false,
  warnings: [],
  sources: [],
  offer_details: "",
  metadata: {
    model: "test/model",
    brand_version: 1,
    prompt_version: "grounded-post-v7",
    grounding_review: checked,
    preferences: {
      review_model: "openai/gpt-5.6-terra",
      knowledge_level: "general",
    },
  },
};

async function mockGeneration(
  page: Page,
  result: GeneratedPost,
  sent: Record<string, unknown>[],
) {
  await page.route("**/api/generation**", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        json: route.request().url().endsWith("-models")
          ? { default: "openai/gpt-4.1", models: [] }
          : { configured: true, brand_ready: true, ready_documents: 1 },
      });
      return;
    }
    sent.push(route.request().postDataJSON());
    await route.fulfill({ json: result });
  });
}

async function noHorizontalScroll(page: Page) {
  for (const width of [375, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
}

test("the knowledge level defaults to general knowledge, sets the length labels and is sent", async ({
  page,
}) => {
  const sent: Record<string, unknown>[] = [];
  await mockGeneration(page, run, sent);
  await page.goto("/en/create");
  const level = page.getByLabel("Knowledge level", { exact: true });
  await expect(level).toHaveValue("general");
  await expect(level).toHaveAccessibleDescription(/aims for the length/);
  await page.getByText("Writing preferences", { exact: true }).click();
  const length = page.getByLabel("Post length", { exact: true });
  await expect(length.locator("option:checked")).toHaveText(
    "Medium — 800–1,200 characters (~130–200 words)",
  );

  await level.selectOption("knowledge_base");
  await expect(level).toHaveAccessibleDescription(/may be shorter/);
  await expect(length.locator("option:checked")).toHaveText(
    "Medium — up to 1,200 characters (~200 words)",
  );
  await page
    .getByLabel("What would you like to write about?", { exact: true })
    .fill("Why mentoring helps new managers");
  await page
    .getByRole("button", { name: "Generate draft", exact: true })
    .click();
  await expect(page.getByLabel("Your draft", { exact: true })).toHaveValue(
    run.content,
  );
  expect(sent[0]).toMatchObject({ knowledge_level: "knowledge_base" });
  await noHorizontalScroll(page);
});

test("a checked draft shows how much of it the Knowledge Base supports", async ({
  page,
}) => {
  await mockGeneration(page, run, []);
  await page.goto("/en/create");
  await page
    .getByLabel("What would you like to write about?", { exact: true })
    .fill("Why mentoring helps new managers");
  await page
    .getByRole("button", { name: "Generate draft", exact: true })
    .click();
  const panel = page.getByTestId("review-findings");
  await expect(panel.getByTestId("knowledge-share")).toHaveText(
    "50% from your Knowledge Base · 2 general-knowledge sentences",
  );
  await expect(panel.locator("blockquote")).toHaveText(
    "Our mentees are promoted twice as fast",
  );
  await noHorizontalScroll(page);
  // After an edit the share would describe text that is no longer there.
  await page
    .getByLabel("Your draft", { exact: true })
    .fill("A mentor shortens the learning curve.");
  await expect(panel).toContainText("refer to an earlier version");
  await expect(panel.getByTestId("knowledge-share")).toHaveCount(0);
});

test("a clean Hebrew check shows the share, and no share without claims to count", async ({
  page,
}) => {
  let result: GeneratedPost = {
    ...run,
    language: "he",
    content: "מנטור מקצר את עקומת הלמידה.",
    metadata: {
      ...run.metadata,
      grounding_review: {
        ...checked,
        findings: [],
        knowledge_share: { ...share, percent: 0, general_sentences: 1 },
      },
    },
  };
  await page.route("**/api/generation**", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        json: route.request().url().endsWith("-models")
          ? { default: "openai/gpt-4.1", models: [] }
          : { configured: true, brand_ready: true, ready_documents: 1 },
      });
      return;
    }
    await route.fulfill({ json: result });
  });
  await page.goto("/he/create");
  await expect(page.getByLabel("רמת ידע", { exact: true })).toHaveValue(
    "general",
  );
  await page.getByLabel("על מה נכתוב?", { exact: true }).fill("מנטורינג");
  await page.getByRole("button", { name: "יצירת טיוטה", exact: true }).click();
  await expect(page.getByTestId("review-clean")).toBeVisible();
  await expect(page.getByTestId("knowledge-share")).toHaveText(
    "0% מבסיס הידע שלך · משפט אחד של ידע כללי",
  );
  await noHorizontalScroll(page);

  result = {
    ...result,
    id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
    metadata: {
      ...result.metadata,
      grounding_review: {
        ...checked,
        findings: [],
        knowledge_share: { ...share, percent: null, general_sentences: 0 },
      },
    },
  };
  await page.getByLabel("על מה נכתוב?", { exact: true }).fill("מנטורינג שוב");
  await page.getByRole("button", { name: "יצירת טיוטה", exact: true }).click();
  await expect(page.getByTestId("review-clean")).toBeVisible();
  await expect(page.getByTestId("knowledge-share")).toHaveCount(0);
});

const saved = (preferences?: SavedPost["generation_settings"]["preferences"]) =>
  ({
    id: "ffffffff-ffff-4fff-8fff-ffffffffffff",
    platform: "facebook",
    language: "he",
    content: "מנטור מקצר את עקומת הלמידה.",
    status: "Draft",
    version: 1,
    sources: [],
    generation_run_id: null,
    generation_settings: preferences ? { preferences } : {},
    created_at: "2026-11-01T10:00:00Z",
  }) satisfies SavedPost;

for (const [name, preferences, shown] of [
  [
    "general knowledge",
    { review_model: "openai/gpt-4.1", knowledge_level: "general" as const },
    "רמת ידע: בסיס הידע + ידע מקצועי כללי",
  ],
  [
    "a draft from before the choice",
    { review_model: "openai/gpt-4.1" },
    "רמת ידע: מבסיס הידע בלבד",
  ],
  ["a draft that was not generated", undefined, null],
] as const) {
  test(`History shows the knowledge level of ${name}`, async ({ page }) => {
    await page.route("**/api/generation/review-models", (route) =>
      route.fulfill({ json: { default: "openai/gpt-4.1", models: [] } }),
    );
    await page.route("**/api/posts**", (route) =>
      route.fulfill({ json: { items: [saved(preferences)], total: 1 } }),
    );
    await page.goto("/he/history");
    await page
      .getByRole("button", { name: "עריכת טיוטה", exact: true })
      .click();
    const level = page.getByTestId("draft-knowledge-level");
    if (shown) await expect(level).toHaveText(shown);
    else await expect(level).toHaveCount(0);
    await noHorizontalScroll(page);
  });
}
