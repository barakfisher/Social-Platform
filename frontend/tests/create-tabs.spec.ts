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
  ],
};

async function mockApi(page: Page) {
  const generated: Record<string, unknown>[] = [];
  await page.route("**/api/generation**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith("/writer-models"))
      return route.fulfill({ json: writerModels });
    if (path.endsWith("/review-models"))
      return route.fulfill({ json: reviewModels });
    if (request.method() === "GET")
      return route.fulfill({
        json: { configured: true, brand_ready: true, ready_documents: 1 },
      });
    generated.push(request.postDataJSON());
    await route.abort();
  });
  return generated;
}

test("arrow keys move between tabs in the reading direction", async ({
  page,
}) => {
  await mockApi(page);
  for (const [locale, details, models, forward] of [
    ["en", "Post details", "Models and cost", "ArrowRight"],
    ["he", "פרטי הפוסט", "מודלים ועלות", "ArrowLeft"],
  ] as const) {
    await page.goto(`/${locale}/create`);
    const detailsTab = page.getByRole("tab", { name: details });
    const modelsTab = page.getByRole("tab", { name: models });
    await expect(detailsTab).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("tabpanel")).toHaveCount(1);
    await detailsTab.focus();
    await page.keyboard.press(forward);
    await expect(modelsTab).toBeFocused();
    await expect(modelsTab).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("tabpanel", { name: models })).toBeVisible();
    await page.keyboard.press("Home");
    await expect(detailsTab).toBeFocused();
    await page.keyboard.press("End");
    await expect(modelsTab).toBeFocused();
    // Only the selected tab is in the Tab order.
    await expect(detailsTab).toHaveAttribute("tabindex", "-1");
  }
});

test("choices survive switching tabs and are all sent", async ({ page }) => {
  const generated = await mockApi(page);
  await page.goto("/en/create");
  const topic = page.getByLabel("What would you like to write about?");
  await topic.fill("Community garden herbs");
  await page.getByRole("tab", { name: "Models and cost" }).click();
  const writer = page.getByLabel("Writing model", { exact: true });
  await writer.selectOption("google/gemini-3.8-flash");
  await page.getByRole("tab", { name: "Post details" }).click();
  await expect(topic).toHaveValue("Community garden herbs");
  await page.getByRole("tab", { name: "Models and cost" }).click();
  await expect(writer).toHaveValue("google/gemini-3.8-flash");
  await page
    .getByRole("button", { name: "Generate draft", exact: true })
    .click();
  await expect.poll(() => generated.length).toBe(1);
  expect(generated[0]).toMatchObject({
    topic: "Community garden herbs",
    writer_model: "google/gemini-3.8-flash",
  });
});

test("the estimated cost stays next to Generate and links to the models tab", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto("/en/create");
  const summary = page.getByTestId("generate-cost");
  // Writing only: the source check is charged when the owner asks for it.
  await expect(summary).toHaveText("~$0.007 per draft · up to $0.03");
  await expect(
    page.getByRole("button", { name: "Generate draft", exact: true }),
  ).toHaveAccessibleDescription(
    "Estimated cost: ~$0.007 per draft · up to $0.03",
  );
  await page.getByRole("button", { name: "Change models" }).click();
  const modelsTab = page.getByRole("tab", { name: "Models and cost" });
  await expect(modelsTab).toHaveAttribute("aria-selected", "true");
  await expect(modelsTab).toBeFocused();
  await page
    .getByLabel("Writing model", { exact: true })
    .selectOption("google/gemini-3.8-flash");
  await expect(summary).toHaveText("~$0.004 per draft · up to $0.02");
  await expect(page.getByTestId("total-draft-cost")).toHaveText(
    "~$0.004 per draft · up to $0.02",
  );
});

test("generating from the models tab with no topic shows the topic field", async ({
  page,
}) => {
  const generated = await mockApi(page);
  await page.goto("/he/create");
  await page.getByRole("tab", { name: "מודלים ועלות" }).click();
  await page.getByRole("button", { name: "יצירת טיוטה", exact: true }).click();
  await expect(page.getByRole("tab", { name: "פרטי הפוסט" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  const topic = page.getByLabel("על מה נכתוב?");
  await expect(topic).toBeFocused();
  expect(
    await topic.evaluate((el: HTMLTextAreaElement) => el.validity.valueMissing),
  ).toBe(true);
  expect(generated).toHaveLength(0);
});

for (const [width, height] of [
  [375, 812],
  [1280, 900],
]) {
  test(`tabs and the cost line fit a ${width}px screen in Hebrew`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height });
    await mockApi(page);
    await page.goto("/he/create");
    for (const name of ["פרטי הפוסט", "מודלים ועלות"]) {
      await page.getByRole("tab", { name }).click();
      await expect(page.getByTestId("generate-cost")).toBeVisible();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      ).toBe(true);
    }
  });
}
