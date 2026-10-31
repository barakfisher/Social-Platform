import { test, expect, type Page } from "@playwright/test";

const writerModels = {
  default: "openai/gpt-4.1",
  models: [
    {
      id: "openai/gpt-4.1",
      available: true,
      typical_usd: 0.007,
      max_usd: 0.03,
    },
    {
      id: "google/gemini-3.8-flash",
      available: true,
      typical_usd: 0.004,
      max_usd: 0.02,
    },
    {
      id: "vendor/delisted",
      available: false,
      typical_usd: null,
      max_usd: null,
    },
  ],
};
const reviewModels = {
  default: "openai/gpt-5.6-terra",
  models: [
    {
      id: "openai/gpt-5.6-terra",
      available: true,
      typical_usd: 0.028,
      max_usd: 0.12,
    },
    {
      id: "openai/gpt-4.1",
      available: true,
      typical_usd: 0.008,
      max_usd: 0.05,
    },
  ],
};
const run = {
  id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  platform: "linkedin",
  language: "en",
  content: "We grow rosemary and sage.",
  grounded: true,
  warnings: [],
  sources: [],
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

type Fulfil = Parameters<Parameters<Page["route"]>[1]>[0];
async function mockApi(
  page: Page,
  options: {
    writers?: (route: Fulfil) => Promise<void>;
    generate?: (route: Fulfil) => Promise<void>;
  } = {},
) {
  await page.route("**/api/generation**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith("/writer-models")) {
      if (options.writers) await options.writers(route);
      else await route.fulfill({ json: writerModels });
      return;
    }
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
    if (options.generate) await options.generate(route);
    else await route.fulfill({ json: run });
  });
}

async function openModels(page: Page, locale: "en" | "he" = "en") {
  await page.goto(`/${locale}/create`);
  await page
    .getByRole("tab", {
      name: locale === "en" ? "Models and cost" : "מודלים ועלות",
    })
    .click();
}

test("writer select shows costs, the total follows both selects and the choice is sent", async ({
  page,
}) => {
  let sent: Record<string, unknown> | null = null;
  await mockApi(page, {
    generate: async (route) => {
      sent = route.request().postDataJSON();
      await route.fulfill({ json: run });
    },
  });
  await openModels(page);
  const writer = page.getByLabel("Writing model", { exact: true });
  await expect(writer).toHaveValue("openai/gpt-4.1");
  await expect(writer.locator("option")).toHaveText([
    "GPT-4.1 (recommended) — ~$0.007 per draft · up to $0.03",
    "Gemini 3.8 Flash — ~$0.004 per draft · up to $0.02",
    "vendor/delisted — unavailable",
  ]);
  await expect(writer.locator("option").nth(2)).toBeDisabled();
  await expect(page.getByTestId("writer-model-cost")).toHaveText(
    "~$0.007 per draft · up to $0.03",
  );
  const total = page.getByTestId("total-draft-cost");
  // GPT-4.1 writing + GPT-5.6 Terra source check.
  await expect(total).toHaveText("~$0.035 per draft · up to $0.15");
  await writer.selectOption("google/gemini-3.8-flash");
  await expect(total).toHaveText("~$0.032 per draft · up to $0.14");
  await page
    .getByLabel("Source check model", { exact: true })
    .selectOption("openai/gpt-4.1");
  await expect(total).toHaveText("~$0.012 per draft · up to $0.07");
  await page.getByRole("tab", { name: "Post details" }).click();
  await page
    .getByLabel("What would you like to write about?", { exact: true })
    .fill("Community garden herbs");
  await page
    .getByRole("button", { name: "Generate draft", exact: true })
    .click();
  await expect.poll(() => sent?.writer_model).toBe("google/gemini-3.8-flash");
  await expect.poll(() => sent?.review_model).toBe("openai/gpt-4.1");
});

test("while writer options load the select is disabled and the total is hidden", async ({
  page,
}) => {
  let release: () => void = () => {};
  const pending = new Promise<void>((resolve) => (release = resolve));
  await mockApi(page, {
    writers: async (route) => {
      await pending;
      await route.fulfill({ json: writerModels });
    },
  });
  await openModels(page);
  const writer = page.getByLabel("Writing model", { exact: true });
  await expect(writer).toBeDisabled();
  await expect(writer.locator("option")).toHaveText(["Loading models…"]);
  await expect(page.getByTestId("total-draft-cost")).toHaveCount(0);
  await page.getByRole("tab", { name: "Post details" }).click();
  // The summary next to Generate waits for the same lists as the models tab total.
  await expect(page.getByTestId("generate-cost")).toHaveCount(0);
  await page
    .getByLabel("What would you like to write about?", { exact: true })
    .fill("Community garden herbs");
  await expect(
    page.getByRole("button", { name: "Generate draft", exact: true }),
  ).toBeEnabled();
  release();
  await expect(page.getByTestId("generate-cost")).toBeVisible();
  await page.getByRole("tab", { name: "Models and cost" }).click();
  await expect(writer).toBeEnabled();
  await expect(page.getByTestId("total-draft-cost")).toBeVisible();
});

for (const [name, response] of [
  [
    "unreachable",
    { status: 503, json: { error: { message: "api_unavailable" } } },
  ],
  ["empty", { json: { default: "openai/gpt-4.1", models: [] } }],
] as const) {
  test(`${name} writer options fall back to the default writer`, async ({
    page,
  }) => {
    await mockApi(page, { writers: (route) => route.fulfill(response) });
    await openModels(page, "he");
    await expect(
      page.getByText(
        "לא הצלחנו לטעון את אפשרויות מודל הכתיבה. ייעשה שימוש במודל הכתיבה המוגדר כברירת מחדל.",
      ),
    ).toBeVisible();
    await expect(page.getByLabel("מודל לכתיבה", { exact: true })).toHaveCount(
      0,
    );
    await expect(page.getByTestId("total-draft-cost")).toHaveText(
      "העלות אינה זמינה",
    );
    await expect(
      page.getByRole("button", { name: "יצירת טיוטה", exact: true }),
    ).toBeEnabled();
  });
}

for (const [code, locale, text] of [
  [
    "writer_model_unavailable",
    "en",
    "The selected writing model is no longer available. Choose another and try again.",
  ],
  [
    "generation_model_unavailable",
    "he",
    "מודל הכתיבה שנבחר כבר לא זמין. יש לבחור מודל אחר ולנסות שוב.",
  ],
  [
    "generation_output_truncated",
    "en",
    "The writing model ran out of room before finishing the draft. Your inputs are preserved; try again or choose another writing model.",
  ],
  [
    "generation_output_truncated",
    "he",
    "למודל הכתיבה לא נשאר מקום לסיים את הטיוטה. הפרטים שהזנת נשמרו; אפשר לנסות שוב או לבחור מודל כתיבה אחר.",
  ],
] as const) {
  test(`${code} has its own ${locale} message and keeps the inputs`, async ({
    page,
  }) => {
    await mockApi(page, {
      generate: (route) =>
        route.fulfill({
          status: code === "writer_model_unavailable" ? 422 : 503,
          json: { error: { message: code } },
        }),
    });
    await page.goto(`/${locale}/create`);
    const topic = page.getByLabel(
      locale === "en" ? "What would you like to write about?" : /על מה/,
    );
    await topic.fill("Community garden herbs");
    await page
      .getByRole("button", {
        name: locale === "en" ? "Generate draft" : "יצירת טיוטה",
        exact: true,
      })
      .click();
    await expect(page.getByText(text, { exact: true })).toBeVisible();
    await expect(topic).toHaveValue("Community garden herbs");
  });
}

test("the total cost is visible on a phone", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await mockApi(page);
  await openModels(page, "he");
  const total = page.getByTestId("total-draft-cost");
  await total.scrollIntoViewIfNeeded();
  await expect(total).toBeInViewport();
  const box = await total.boundingBox();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(375);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
