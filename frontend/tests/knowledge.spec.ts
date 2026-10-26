import { test, expect } from "@playwright/test";
const sourceDocument = {
  id: "11111111-1111-4111-8111-111111111111",
  title: "מקור לדוגמה",
  status: "Pending",
  stage: "pending",
  chunk_count: 0,
  error_code: null as string | null,
  text: "ידע בעברית / English",
};

test("pasted text prepares, survives reload, previews and deletes in Hebrew", async ({
  page,
}) => {
  let item: typeof sourceDocument | null = null;
  let ready = false;
  await page.route("**/api/knowledge**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === "POST") {
      item = { ...sourceDocument, ...request.postDataJSON() };
      await route.fulfill({ status: 202, json: { ...item, duplicate: false } });
      return;
    }
    if (request.method() === "DELETE") {
      item = null;
      await route.fulfill({ json: { deleted: true } });
      return;
    }
    if (url.pathname.endsWith(sourceDocument.id)) {
      await route.fulfill({ json: item });
      return;
    }
    if (item && ready)
      item = {
        ...item,
        stage: "text_prepared",
        status: "Processing",
        chunk_count: 2,
      };
    await route.fulfill({
      json: { items: item ? [item] : [], total: item ? 1 : 0 },
    });
  });
  await page.goto("/he/knowledge");
  await page
    .getByLabel("כותרת המקור", { exact: true })
    .fill(sourceDocument.title);
  await page
    .getByLabel("הדבקת טקסט", { exact: true })
    .fill(sourceDocument.text);
  await page
    .getByRole("button", { name: "הוספה למאגר הידע", exact: true })
    .click();
  await expect(page.getByText("בתור", { exact: true })).toBeVisible();
  ready = true;
  await expect(page.getByText("הטקסט מוכן", { exact: true })).toBeVisible({
    timeout: 10000,
  });
  await page.reload();
  await expect(page.getByText("הטקסט מוכן", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "הצגת הטקסט" }).click();
  await expect(
    page.getByText(sourceDocument.text, { exact: true }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.getByRole("button", { name: "מחיקה", exact: true }).click();
  await expect(
    page.getByText("למחוק את המקור ואת המקטעים שהוכנו ממנו?"),
  ).toBeVisible();
  await page.getByRole("button", { name: "מחיקת המקור", exact: true }).click();
  await expect(page.getByText("המקור נמחק.", { exact: true })).toBeVisible();
  await expect(
    page.getByText(sourceDocument.title, { exact: true }),
  ).toHaveCount(0);
});

test("failed submission keeps text and failed preparation can be retried", async ({
  page,
}) => {
  let fail = true;
  let item: typeof sourceDocument | null = null;
  await page.route("**/api/knowledge**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname.endsWith("/retry")) {
      item = {
        ...sourceDocument,
        stage: "text_prepared",
        status: "Processing",
        chunk_count: 1,
      };
      await route.fulfill({ status: 202, json: item });
      return;
    }
    if (request.method() === "POST") {
      if (fail) {
        await route.fulfill({
          status: 503,
          json: { error: { code: "api_unavailable" } },
        });
        return;
      }
      item = {
        ...sourceDocument,
        status: "Failed",
        stage: "failed",
        error_code: "dispatch_failed",
      };
      await route.fulfill({ status: 202, json: { ...item, duplicate: false } });
      return;
    }
    await route.fulfill({
      json: { items: item ? [item] : [], total: item ? 1 : 0 },
    });
  });
  await page.goto("/en/knowledge");
  await page.getByLabel("Source title", { exact: true }).fill("Saved source");
  await page
    .getByLabel("Paste your text", { exact: true })
    .fill("Keep these edits");
  await page
    .getByRole("button", { name: "Add to Knowledge Base", exact: true })
    .click();
  await expect(page.locator("section [role=alert]")).toContainText(
    "couldn’t complete",
  );
  await expect(page.getByLabel("Paste your text", { exact: true })).toHaveValue(
    "Keep these edits",
  );
  fail = false;
  await page
    .getByRole("button", { name: "Add to Knowledge Base", exact: true })
    .click();
  await expect(
    page.getByText("Preparation failed", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Process again", exact: true })
    .click();
  await expect(page.getByText("Text prepared", { exact: true })).toBeVisible();
});

test("AI search stays unavailable without a provider key", async ({ page }) => {
  await page.route("**/api/knowledge**", async (route) => {
    if (new URL(route.request().url()).pathname.endsWith("/configuration")) {
      await route.fulfill({ json: { configured: false } });
      return;
    }
    await route.fulfill({
      json: {
        items: [
          {
            ...sourceDocument,
            status: "Processing",
            stage: "text_prepared",
            chunk_count: 1,
          },
        ],
        total: 1,
      },
    });
  });
  await page.goto("/en/knowledge");
  await expect(
    page.getByText(
      "AI search is not connected yet. Your saved text will remain available.",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Enable AI search", exact: true }),
  ).toBeDisabled();
});

test("AI search preparation reaches Ready and shows a retryable provider failure", async ({
  page,
}) => {
  let item = {
    ...sourceDocument,
    status: "Processing",
    stage: "text_prepared",
    chunk_count: 1,
    embedded_chunk_count: 0,
  };
  let fail = true;
  await page.route("**/api/knowledge**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/configuration")) {
      await route.fulfill({ json: { configured: true } });
      return;
    }
    if (path.endsWith("/embed")) {
      item = fail
        ? {
            ...item,
            status: "Failed",
            stage: "embedding_failed",
            error_code: "embedding_authentication_failed",
          }
        : {
            ...item,
            status: "Ready",
            stage: "ready",
            error_code: null,
            embedded_chunk_count: 1,
          };
      await route.fulfill({ status: 202, json: item });
      return;
    }
    await route.fulfill({ json: { items: [item], total: 1 } });
  });
  await page.goto("/en/knowledge");
  await page
    .getByRole("button", { name: "Enable AI search", exact: true })
    .click();
  await expect(
    page.getByText("AI search preparation failed", { exact: true }),
  ).toBeVisible();
  fail = false;
  await page
    .getByRole("button", { name: "Enable AI search", exact: true })
    .click();
  await expect(page.getByText("Ready", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Enable AI search", exact: true }),
  ).toHaveCount(0);
});
