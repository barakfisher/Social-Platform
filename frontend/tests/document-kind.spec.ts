import { test, expect, type Page } from "@playwright/test";

// SP-29: a source is knowledge or sample posts; topic ideas never restate a sample post.
const source = {
  id: "11111111-1111-4111-8111-111111111111",
  title: "Our posts",
  kind: "knowledge",
  source_type: "text",
  filename: null as string | null,
  url: null as string | null,
  fetched_at: null as string | null,
  created_at: "2026-10-30T09:15:00Z",
  status: "Ready",
  stage: "ready",
  chunk_count: 2,
  error_code: null as string | null,
  refresh_result: null as string | null,
  refresh: null as Record<string, unknown> | null,
};
const isList = (url: string) => new URL(url).pathname === "/api/knowledge";

async function stubList(page: Page, items = [source]) {
  await page.route("**/api/knowledge**", async (route) => {
    if (isList(route.request().url()))
      await route.fulfill({ json: { items, total: items.length } });
    else await route.fallback();
  });
}

test("each way of adding a source sends the chosen content type", async ({
  page,
}) => {
  const sent: Record<string, unknown> = {};
  await stubList(page, []);
  await page.route("**/api/knowledge/text", async (route) => {
    sent.text = route.request().postDataJSON().kind;
    await route.fulfill({ status: 202, json: { ...source, duplicate: false } });
  });
  await page.route("**/api/knowledge/url", async (route) => {
    sent.url = route.request().postDataJSON().kind;
    await route.fulfill({ status: 202, json: { ...source, duplicate: false } });
  });
  await page.route("**/api/knowledge/files**", async (route) => {
    sent.file = new URL(route.request().url()).searchParams.get("kind");
    await route.fulfill({ status: 202, json: { ...source, duplicate: false } });
  });
  await page.goto("/en/knowledge");

  const textKind = page.locator("#source-kind");
  await expect(textKind).toHaveValue("knowledge");
  await expect(textKind).toHaveAccessibleName("Content type");
  await expect(textKind).toHaveAccessibleDescription(
    "Sample posts are posts you already wrote. Topic ideas won’t suggest what they already say.",
  );
  await page.getByLabel("Source title").fill("Our posts");
  await page.getByLabel("Paste your text").fill("Our first post.");
  await textKind.selectOption("sample_posts");
  await page.getByRole("button", { name: "Add to Knowledge Base" }).click();
  await expect.poll(() => sent.text).toBe("sample_posts");
  // The next source starts as knowledge again.
  await expect(textKind).toHaveValue("knowledge");

  await page.locator("#file-kind").selectOption("sample_posts");
  await page.locator("#source-file").setInputFiles({
    name: "posts.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Our first post."),
  });
  await page.getByRole("button", { name: "Upload file" }).click();
  await expect.poll(() => sent.file).toBe("sample_posts");

  await page.locator("#link-kind").selectOption("sample_posts");
  await page.locator("#source-url").fill("https://garden.example/posts");
  await page.getByRole("button", { name: "Add web page" }).click();
  await expect.poll(() => sent.url).toBe("sample_posts");
});

test("changing a source's type saves it and keeps focus, in Hebrew", async ({
  page,
}) => {
  let patched: unknown = null;
  let release: () => void = () => {};
  const held = new Promise<void>((resolve) => (release = resolve));
  await stubList(page);
  await page.route(`**/api/knowledge/${source.id}`, async (route) => {
    if (route.request().method() !== "PATCH") return route.fallback();
    patched = route.request().postDataJSON();
    await held;
    await route.fulfill({ json: { ...source, kind: "sample_posts" } });
  });
  await page.goto("/he/knowledge");
  const kind = page.getByRole("combobox", { name: "סוג התוכן: Our posts" });
  await expect(kind).toHaveValue("knowledge");
  await kind.focus();
  await kind.selectOption("sample_posts");
  // Locked while it saves, so a second change cannot race the first.
  await expect(kind).toBeDisabled();
  release();
  await expect(
    page.getByText("סוג התוכן נשמר.", { exact: true }),
  ).toBeVisible();
  expect(patched).toEqual({ kind: "sample_posts" });
  await expect(kind).toHaveValue("sample_posts");
  await expect(kind).toBeEnabled();
  await expect(kind).toBeFocused();
});

test("a failed change keeps the saved type and says so", async ({ page }) => {
  await stubList(page);
  await page.route(`**/api/knowledge/${source.id}`, async (route) => {
    if (route.request().method() !== "PATCH") return route.fallback();
    await route.fulfill({
      status: 503,
      json: { error: { code: "api_unavailable" } },
    });
  });
  await page.goto("/en/knowledge");
  const kind = page.getByRole("combobox", { name: "Content type: Our posts" });
  await kind.selectOption("sample_posts");
  await expect(page.getByRole("alert").filter({ hasText: /\S/ })).toContainText(
    "The content type wasn’t changed.",
  );
  await expect(kind).toHaveValue("knowledge");
  await expect(kind).toBeEnabled();
});

test("a sample-posts source shows its type", async ({ page }) => {
  await stubList(page, [{ ...source, kind: "sample_posts" }]);
  await page.goto("/en/knowledge");
  await expect(
    page.getByRole("combobox", { name: "Content type: Our posts" }),
  ).toHaveValue("sample_posts");
});

test("a failed change says so in Hebrew and keeps focus on the type", async ({
  page,
}) => {
  await stubList(page);
  await page.route(`**/api/knowledge/${source.id}`, async (route) => {
    if (route.request().method() !== "PATCH") return route.fallback();
    await route.fulfill({ status: 503, json: {} });
  });
  await page.goto("/he/knowledge");
  const kind = page.getByRole("combobox", { name: "סוג התוכן: Our posts" });
  await expect(kind.locator("option")).toHaveText(["ידע", "פוסטים לדוגמה"]);
  await kind.selectOption("sample_posts");
  await expect(page.getByRole("alert").filter({ hasText: /\S/ })).toContainText(
    "סוג התוכן לא השתנה, ומוצג הסוג השמור.",
  );
  await expect(kind).toHaveValue("knowledge");
  await expect(kind).toBeFocused();
});

test("a list refresh sent before the change cannot undo it", async ({
  page,
}) => {
  // While a source is processing the list refreshes on a timer. A refresh that left
  // before the change and answers after it carries the old type, and when processing
  // ends in that same answer no later refresh would put the saved type back.
  const processing = {
    ...source,
    id: "22222222-2222-4222-8222-222222222222",
    title: "Still processing",
    status: "Processing",
    stage: "pending",
  };
  let stored = "knowledge";
  let held: (() => void) | null = null;
  let lists = 0;
  await page.route("**/api/knowledge**", async (route) => {
    const request = route.request();
    if (request.method() === "PATCH") {
      stored = request.postDataJSON().kind;
      await route.fulfill({ json: { ...source, kind: stored } });
      return;
    }
    if (!isList(request.url())) return route.fallback();
    lists += 1;
    const snapshot = [
      { ...source, kind: stored },
      lists === 1
        ? processing
        : { ...processing, status: "Ready", stage: "ready" },
    ];
    if (lists === 2) await new Promise<void>((resolve) => (held = resolve));
    await route.fulfill({ json: { items: snapshot, total: 2 } });
  });
  await page.goto("/en/knowledge");
  const kind = page.getByRole("combobox", { name: "Content type: Our posts" });
  await expect(kind).toHaveValue("knowledge");
  // The first timed refresh is now waiting with the old type.
  await expect.poll(() => held !== null).toBe(true);
  await kind.selectOption("sample_posts");
  await expect(
    page.getByText("Content type saved.", { exact: true }),
  ).toBeVisible();
  held!();
  // The stale answer was dropped, so the list was read again.
  await expect.poll(() => lists).toBe(3);
  await expect(kind).toHaveValue("sample_posts");
});
