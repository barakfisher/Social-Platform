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
  metadata: {
    model: "test/model",
    brand_version: 1,
    prompt_version: "grounded-post-v1",
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

for (const failure of ["grounding_review_failed", "generation_interrupted"]) {
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
          status: 409,
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
      page.getByRole("alert").filter({
        hasText:
          failure === "generation_interrupted"
            ? "Generation was interrupted"
            : "did not pass its source check",
      }),
    ).toContainText(
      failure === "generation_interrupted"
        ? "Generation was interrupted"
        : "did not pass its source check",
    );
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
