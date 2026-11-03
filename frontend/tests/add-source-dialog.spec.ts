import { test, expect, type Page } from "@playwright/test";
import { addSourceButton, openAddSource } from "./add-source-dialog";

// The Knowledge Base page shows sources; adding one happens in a two-step dialog.
const source = {
  id: "33333333-3333-4333-8333-333333333333",
  title: "Garden notes",
  kind: "knowledge",
  source_type: "text",
  filename: null as string | null,
  url: null as string | null,
  fetched_at: null as string | null,
  created_at: "2026-11-03T09:15:00Z",
  status: "Pending",
  stage: "queued",
  chunk_count: 0,
  error_code: null as string | null,
  refresh_result: null as string | null,
  refresh: null as Record<string, unknown> | null,
};
const isList = (url: string) => new URL(url).pathname === "/api/knowledge";

async function stubList(page: Page, items: (typeof source)[] = []) {
  await page.route("**/api/knowledge**", async (route) => {
    if (isList(route.request().url()))
      await route.fulfill({ json: { items, total: items.length } });
    else await route.fallback();
  });
}

test("the page shows sources and one way in; the forms wait in the dialog", async ({
  page,
}) => {
  await stubList(page);
  await page.goto("/en/knowledge");
  await expect(
    page.getByText(
      "No sources yet. Add your first one, and your posts can draw on it.",
    ),
  ).toBeVisible();
  await expect(page.getByLabel("Source title")).toHaveCount(0);
  await expect(page.getByLabel("Page address (URL)")).toHaveCount(0);
  // The empty state's own button opens the same dialog.
  await page
    .getByRole("button", { name: "Add a source", exact: true })
    .last()
    .click();
  const dialog = page.getByRole("dialog", { name: "Add a source" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button")).toHaveCount(5);
  await expect(page.locator("#choose-text")).toBeFocused();
  await expect(page.locator("#choose-url")).toHaveAccessibleDescription(
    "A public page; its main text is kept",
  );
});

test("Back returns to the choices and Escape closes, with focus following", async ({
  page,
}) => {
  await stubList(page, [source]);
  await page.goto("/he/knowledge");
  await openAddSource(page, "he", "url");
  const dialog = page.getByRole("dialog", { name: "הוספת דף אינטרנט" });
  await expect(dialog).toBeVisible();
  await expect(page.getByLabel("כתובת הדף (URL)")).toBeFocused();
  await page.getByLabel("כתובת הדף (URL)").fill("https://garden.example");
  await dialog.getByRole("button", { name: "חזרה", exact: true }).click();
  await expect(page.locator("#choose-url")).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(addSourceButton(page)).toBeFocused();
  // Closing creates nothing and keeps what was typed for the next time.
  await openAddSource(page, "he", "url");
  await expect(page.getByLabel("כתובת הדף (URL)")).toHaveValue(
    "https://garden.example",
  );
  await page.getByRole("button", { name: "סגירה", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("an add in flight keeps the dialog open; success closes it and lists the source", async ({
  page,
}) => {
  let items: (typeof source)[] = [];
  let answer: () => void = () => {};
  const answered = new Promise<void>((resolve) => (answer = resolve));
  await page.route("**/api/knowledge**", async (route) => {
    if (isList(route.request().url()))
      await route.fulfill({ json: { items, total: items.length } });
    else await route.fallback();
  });
  await page.route("**/api/knowledge/text", async (route) => {
    await answered;
    items = [source];
    await route.fulfill({ status: 202, json: { ...source, duplicate: false } });
  });
  await page.goto("/en/knowledge");
  await openAddSource(page, "en", "text");
  await page.getByLabel("Source title").fill(source.title);
  await page.getByLabel("Paste your text").fill("Roses need sun.");
  await page.getByRole("button", { name: "Add to Knowledge Base" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("button", { name: "Close" })).toBeDisabled();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeVisible();
  answer();
  await expect(dialog).toHaveCount(0);
  await expect(
    page.getByText("Text saved. Preparation is queued.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("listitem").filter({ hasText: source.title }),
  ).toBeVisible();
  await expect(addSourceButton(page)).toBeFocused();
});

test("a missing title is reported inside the dialog", async ({ page }) => {
  await stubList(page);
  await page.goto("/en/knowledge");
  await openAddSource(page, "en", "text");
  await page.getByLabel("Paste your text").fill("Roses need sun.");
  await page.getByRole("button", { name: "Add to Knowledge Base" }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toHaveText(
    "Enter a title and some text.",
  );
  await expect(page.getByLabel("Source title")).toBeFocused();
  await expect(page.getByLabel("Source title")).toHaveAttribute(
    "aria-invalid",
    "true",
  );
});

test("a file dropped on the sources opens the upload step with it chosen", async ({
  page,
}) => {
  await stubList(page, [source]);
  await page.goto("/en/knowledge");
  await expect(
    page.getByText("You can also drop a PDF or text file here."),
  ).toBeVisible();
  const drop = await page.evaluateHandle(() => {
    const transfer = new DataTransfer();
    transfer.items.add(
      new File(["Opening hours"], "hours.txt", { type: "text/plain" }),
    );
    return transfer;
  });
  const list = page.locator("#sources-heading").locator("xpath=../..");
  await list.dispatchEvent("dragover", { dataTransfer: drop });
  await expect(page.getByText("Drop the file to upload it")).toBeVisible();
  await list.dispatchEvent("drop", { dataTransfer: drop });
  await expect(
    page.getByRole("dialog", { name: "Upload a file" }),
  ).toBeVisible();
  await expect
    .poll(() =>
      page
        .locator("#source-file")
        .evaluate((node: HTMLInputElement) => node.files?.[0]?.name),
    )
    .toBe("hours.txt");
  await expect(page.getByText("Drop the file to upload it")).toHaveCount(0);
});

test("on a phone the dialog fills the screen without sideways scrolling", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await stubList(page);
  await page.goto("/he/knowledge");
  await openAddSource(page, "he", "file");
  const box = await page.getByRole("dialog").boundingBox();
  expect(box?.width).toBe(375);
  expect(box?.height).toBe(812);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
});
