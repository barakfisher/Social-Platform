import { test, expect } from "@playwright/test";

test("Hebrew profile saves, persists, and switches language without losing content", async ({
  page,
}) => {
  let stored: Record<string, string | number> | null = null;
  await page.route("**/api/brand", async (route) => {
    if (route.request().method() === "PUT")
      stored = { ...route.request().postDataJSON(), version: 1 };
    await route.fulfill({ json: stored });
  });
  await page.goto("/he/brand");
  await page.getByLabel("שם המותג", { exact: true }).fill("מותג לדוגמה");
  await page.getByLabel("קהל יעד", { exact: true }).fill("Founders בישראל");
  await page.getByLabel("טון וסגנון", { exact: true }).fill("חם וברור");
  await page.getByRole("button", { name: "שמירת זהות המותג" }).click();
  await expect(
    page.getByText("זהות המותג נשמרה", { exact: true }),
  ).toBeVisible();
  expect(stored).toMatchObject({
    name: "מותג לדוגמה",
    audience: "Founders בישראל",
    voice: "חם וברור",
    version: 1,
  });
  await page.reload();
  await expect(page.getByLabel("שם המותג", { exact: true })).toHaveValue(
    "מותג לדוגמה",
  );
  await page.getByRole("link", { name: "Switch to English" }).click();
  await expect(page.getByLabel("Brand name", { exact: true })).toHaveValue(
    "מותג לדוגמה",
  );
  await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
});

test("loading and save failures retain edits and offer retry", async ({
  page,
}) => {
  let failLoad = true;
  let failSave = true;
  await page.route("**/api/brand", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ status: failLoad ? 503 : 200, json: null });
    } else {
      await route.fulfill({
        status: failSave ? 503 : 200,
        json: { ...route.request().postDataJSON(), version: 1 },
      });
    }
  });
  await page.goto("/en/brand");
  await expect(page.locator("section [role=alert]")).toContainText(
    "couldn’t load",
  );
  failLoad = false;
  await page.getByRole("button", { name: "Try again" }).click();
  await page.getByLabel("Brand name", { exact: true }).fill("Test brand");
  await page.getByRole("button", { name: "Save Brand DNA" }).click();
  await expect(page.locator("section [role=alert]")).toContainText(
    "couldn’t save",
  );
  await expect(page.getByLabel("Brand name", { exact: true })).toHaveValue(
    "Test brand",
  );
  failSave = false;
  await page.getByRole("button", { name: "Save Brand DNA" }).click();
  await expect(
    page.getByText("Brand DNA saved", { exact: true }),
  ).toBeVisible();
});

test("version conflict keeps edits and offers an explicit reload", async ({
  page,
}) => {
  let name = "Original";
  await page.route("**/api/brand", async (route) => {
    if (route.request().method() === "PUT") {
      name = "Updated elsewhere";
      await route.fulfill({
        status: 409,
        json: { error: { code: "http_error" } },
      });
    } else
      await route.fulfill({
        json: {
          name,
          audience: "",
          positioning: "",
          voice: "",
          guidelines: "",
          prohibited_claims: "",
          version: 1,
        },
      });
  });
  await page.goto("/en/brand");
  await page.getByLabel("Brand name", { exact: true }).fill("My edits");
  await page.getByRole("button", { name: "Save Brand DNA" }).click();
  await expect(page.locator("section [role=alert]")).toContainText(
    "updated elsewhere",
  );
  await expect(page.getByLabel("Brand name", { exact: true })).toHaveValue(
    "My edits",
  );
  await page.getByRole("button", { name: "Reload saved profile" }).click();
  await expect(page.getByLabel("Brand name", { exact: true })).toHaveValue(
    "Updated elsewhere",
  );
});
