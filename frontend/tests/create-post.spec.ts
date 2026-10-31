import { test, expect } from "@playwright/test";
const run = {
  id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  platform: "facebook",
  language: "he",
  content: "בגינה הקהילתית שלנו מגדלים רוזמרין ומרווה.",
  grounded: true,
  warnings: [],
  sources: [
    {
      chunk_id: "chunk-1",
      document_id: "doc-1",
      title: "Garden notes",
      content: "We grow rosemary and sage.",
      source_location: {},
    },
  ],
  offer_details: "",
  metadata: {
    model: "test/model",
    brand_version: 1,
    prompt_version: "grounded-post-v4",
    grounding_review: {
      status: "checked",
      findings: [],
      reason: null,
      retryable: false,
    },
    preferences: { review_model: "openai/gpt-5.6-terra" },
  },
};
const draft = {
  id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  platform: "facebook",
  language: "he",
  content: run.content,
  status: "Draft",
  version: 1,
  sources: run.sources,
  generation_run_id: run.id,
  generation_settings: {
    grounding_review: { ...run.metadata.grounding_review, checked_version: 1 },
  },
  created_at: "2026-10-25T10:00:00Z",
};

test("Hebrew generation edits, saves, reopens, updates and deletes a draft", async ({
  page,
}) => {
  let stored: typeof draft | null = null;
  await page.route("**/api/generation**", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        json: { configured: true, brand_ready: true, ready_documents: 1 },
      });
      return;
    }
    const body = route.request().postDataJSON();
    expect(body.platform).toBe("facebook");
    expect(body.language).toBe("he");
    await route.fulfill({ json: run });
  });
  await page.route("**/api/posts**", async (route) => {
    const request = route.request();
    if (request.method() === "POST") {
      stored = { ...draft, content: request.postDataJSON().content };
      await route.fulfill({ status: 201, json: stored });
      return;
    }
    if (request.method() === "PUT") {
      stored = {
        ...stored!,
        content: request.postDataJSON().content,
        version: 2,
      };
      await route.fulfill({ json: stored });
      return;
    }
    if (request.method() === "DELETE") {
      stored = null;
      await route.fulfill({ json: { deleted: true } });
      return;
    }
    await route.fulfill({
      json: { items: stored ? [stored] : [], total: stored ? 1 : 0 },
    });
  });
  await page.goto("/he/create");
  await page.getByLabel("פלטפורמה", { exact: true }).selectOption("facebook");
  await page
    .getByLabel("על מה נכתוב?", { exact: true })
    .fill("כתבו על הגינה הקהילתית והצמחים שלה");
  await page.getByRole("button", { name: "יצירת טיוטה", exact: true }).click();
  await expect(page.getByLabel("הטיוטה שלך", { exact: true })).toHaveValue(
    run.content,
  );
  await page
    .getByLabel("הטיוטה שלך", { exact: true })
    .fill(run.content + " בואו ללמוד איתנו.");
  await page.getByText("מקורות ששימשו לכתיבה (1)", { exact: true }).click();
  await expect(page.getByText("Garden notes", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "שמירת טיוטה", exact: true }).click();
  await expect(page.getByText("הטיוטה נשמרה", { exact: true })).toBeVisible();
  await page
    .getByRole("link", { name: "פתיחת ההיסטוריה", exact: true })
    .click();
  await page.getByRole("button", { name: "עריכת טיוטה", exact: true }).click();
  await page
    .getByLabel("תוכן הטיוטה", { exact: true })
    .fill("טיוטה מעודכנת עם רוזמרין");
  await page
    .getByRole("button", { name: "שמירת שינויים", exact: true })
    .click();
  await expect(page.getByText("השינויים נשמרו", { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.getByRole("button", { name: "מחיקה", exact: true }).click();
  await page.getByRole("button", { name: "מחיקת הטיוטה", exact: true }).click();
  await expect(page.getByText("הטיוטה נמחקה.", { exact: true })).toBeVisible();
});

test("generation failures retain input and ambiguous retries reuse their request key", async ({
  page,
}) => {
  const keys: string[] = [];
  await page.route("**/api/generation**", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        json: { configured: true, brand_ready: true, ready_documents: 1 },
      });
      return;
    }
    keys.push(route.request().postDataJSON().request_key);
    await route.fulfill(
      keys.length === 1
        ? { status: 503, json: { error: { message: "api_unavailable" } } }
        : { json: { ...run, platform: "linkedin", language: "en" } },
    );
  });
  await page.goto("/en/create");
  await page
    .getByLabel("What would you like to write about?", { exact: true })
    .fill("A garden post");
  await page
    .getByRole("button", { name: "Generate draft", exact: true })
    .click();
  await expect(page.locator("section [role=alert]")).toContainText(
    "couldn’t complete",
  );
  await expect(
    page.getByLabel("What would you like to write about?", { exact: true }),
  ).toHaveValue("A garden post");
  await page
    .getByRole("button", { name: "Generate draft", exact: true })
    .click();
  await expect(page.getByLabel("Your draft", { exact: true })).toHaveValue(
    run.content,
  );
  expect(keys.length).toBe(2);
  expect(keys[0]).toBe(keys[1]);
});

test("setup prerequisites prevent generation and explain the next action", async ({
  page,
}) => {
  await page.route("**/api/generation/configuration", (route) =>
    route.fulfill({
      json: { configured: true, brand_ready: false, ready_documents: 0 },
    }),
  );
  await page.goto("/en/create");
  await expect(
    page.getByText("Add your Brand DNA before generating a post."),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Generate draft", exact: true }),
  ).toBeDisabled();
});

test("history conflicts preserve edits until an explicit reload", async ({
  page,
}) => {
  let conflict = true;
  await page.route("**/api/posts**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === "PUT") {
      await route.fulfill({
        status: 409,
        json: { error: { message: "draft_edit_conflict" } },
      });
      conflict = false;
      return;
    }
    if (path.endsWith(draft.id)) {
      await route.fulfill({
        json: { ...draft, content: "Updated elsewhere", version: 2 },
      });
      return;
    }
    await route.fulfill({ json: { items: [draft], total: 1 } });
  });
  await page.goto("/en/history");
  await page.getByRole("button", { name: "Edit draft", exact: true }).click();
  await page
    .getByLabel("Draft content", { exact: true })
    .fill("My unsaved edits");
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(page.locator("section [role=alert]")).toContainText(
    "updated elsewhere",
  );
  await expect(page.getByLabel("Draft content", { exact: true })).toHaveValue(
    "My unsaved edits",
  );
  await page
    .getByRole("button", { name: "Load latest version", exact: true })
    .click();
  await expect(page.getByLabel("Draft content", { exact: true })).toHaveValue(
    "Updated elsewhere",
  );
  expect(conflict).toBe(false);
});

const failureMessages: Record<string, { status: number; text: string }> = {
  draft_blocked: {
    status: 409,
    text: "instructions aimed at the AI",
  },
  generation_interrupted: {
    status: 409,
    text: "Generation was interrupted",
  },
  generation_spending_limit: {
    status: 503,
    text: "per-request AI cost limit",
  },
};

for (const [failure, expected] of Object.entries(failureMessages)) {
  test(`${failure} withholds output and preserves topic for retry`, async ({
    page,
  }) => {
    let attempts = 0;
    const keys: string[] = [];
    await page.route("**/api/generation**", async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({
          json: { configured: true, brand_ready: true, ready_documents: 1 },
        });
        return;
      }
      attempts++;
      keys.push(route.request().postDataJSON().request_key);
      if (attempts === 1) {
        await route.fulfill({
          status: expected.status,
          json: { error: { message: failure } },
        });
      } else {
        await route.fulfill({
          json: { ...run, platform: "linkedin", language: "en" },
        });
      }
    });
    await page.goto("/en/create");
    await page
      .getByLabel("What would you like to write about?")
      .fill("Rosemary in the garden");
    await page
      .getByRole("button", { name: "Generate draft", exact: true })
      .click();
    await expect(
      page.getByRole("alert").filter({ hasText: expected.text }),
    ).toContainText(expected.text);
    await expect(page.getByLabel("Your draft", { exact: true })).toHaveCount(0);
    await expect(
      page.getByLabel("What would you like to write about?"),
    ).toHaveValue("Rosemary in the garden");
    await page
      .getByRole("button", { name: "Generate draft", exact: true })
      .click();
    await expect(page.getByLabel("Your draft", { exact: true })).toBeVisible();
    expect(keys[1]).not.toBe(keys[0]);
  });
}

const reviewModels = {
  default: "openai/gpt-5.6-terra",
  models: [
    {
      id: "openai/gpt-5.6-terra",
      available: true,
      typical_usd: 0.016,
      max_usd: 0.063,
    },
    {
      id: "openai/gpt-4.1",
      available: true,
      typical_usd: 0.008,
      max_usd: 0.05,
    },
    {
      id: "vendor/delisted",
      available: false,
      typical_usd: null,
      max_usd: null,
    },
  ],
};

test("source check model shows estimated costs and the choice is sent", async ({
  page,
}) => {
  let sent: Record<string, unknown> | null = null;
  await page.route("**/api/generation**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith("/review-models")) {
      await route.fulfill({ json: reviewModels });
      return;
    }
    if (request.method() === "GET") {
      await route.fulfill({
        json: { configured: true, brand_ready: true, ready_documents: 1 },
      });
      return;
    }
    sent = request.postDataJSON();
    await route.fulfill({
      json: { ...run, language: "en", platform: "linkedin" },
    });
  });
  await page.goto("/en/create");
  await page.getByRole("tab", { name: "Models and cost" }).click();
  const select = page.getByLabel("Source check model", { exact: true });
  await expect(select).toHaveValue("openai/gpt-5.6-terra");
  await expect(select.locator("option")).toHaveText([
    "GPT-5.6 Terra (recommended, stricter) — ~$0.016 per check · up to $0.063",
    "GPT-4.1 (cheaper, less strict) — ~$0.008 per check · up to $0.05",
    "vendor/delisted — unavailable",
  ]);
  await expect(select.locator("option").nth(2)).toBeDisabled();
  const cost = page.getByTestId("review-model-cost");
  await expect(cost).toHaveText("~$0.016 per check · up to $0.063");
  await select.selectOption("openai/gpt-4.1");
  await expect(cost).toHaveText("~$0.008 per check · up to $0.05");
  await page.getByRole("tab", { name: "Post details" }).click();
  await page
    .getByLabel("What would you like to write about?", { exact: true })
    .fill("Community garden herbs");
  await page
    .getByRole("button", { name: "Generate draft", exact: true })
    .click();
  await expect.poll(() => sent?.review_model).toBe("openai/gpt-4.1");
});

test("post length options show the character limit and about how many words", async ({
  page,
}) => {
  await page.route("**/api/generation**", async (route) => {
    await route.fulfill({
      json: { configured: true, brand_ready: true, ready_documents: 1 },
    });
  });
  for (const [locale, preferences, label, options] of [
    [
      "en",
      "Writing preferences",
      "Post length",
      [
        "Short — up to 600 characters (~100 words)",
        "Medium — up to 1,200 characters (~200 words)",
        "Long — up to 2,400 characters (~400 words)",
      ],
    ],
    [
      "he",
      "העדפות כתיבה",
      "אורך הפוסט",
      [
        "קצר — עד 600 תווים (כ־100 מילים)",
        "בינוני — עד 1,200 תווים (כ־200 מילים)",
        "ארוך — עד 2,400 תווים (כ־400 מילים)",
      ],
    ],
  ] as const) {
    await page.goto(`/${locale}/create`);
    await page.getByText(preferences, { exact: true }).click();
    const select = page.getByLabel(label, { exact: true });
    await expect(select.locator("option")).toHaveText([...options]);
    await expect(select).toHaveValue("medium");
  }
});

test("unavailable model options fall back to the default source check", async ({
  page,
}) => {
  await page.route("**/api/generation/review-models", (route) =>
    route.fulfill({
      status: 503,
      json: { error: { message: "api_unavailable" } },
    }),
  );
  await page.route("**/api/generation/configuration", (route) =>
    route.fulfill({
      json: { configured: true, brand_ready: true, ready_documents: 1 },
    }),
  );
  await page.goto("/he/create");
  await page.getByRole("tab", { name: "מודלים ועלות" }).click();
  await expect(
    page.getByText(
      "לא הצלחנו לטעון את אפשרויות המודל. תתבצע בדיקת המקורות המוגדרת כברירת מחדל.",
    ),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "יצירת טיוטה", exact: true }),
  ).toBeEnabled();
});
