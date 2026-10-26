import { test, expect } from "@playwright/test";
test("language switch preserves section and document direction", async ({
  page,
}) => {
  await page.goto("/en/knowledge");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await page.getByRole("link", { name: "Switch to Hebrew" }).click();
  await expect(page).toHaveURL(/\/he\/knowledge$/);
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(
    page.getByRole("link", { name: "מאגר ידע", exact: true }).first(),
  ).toHaveAttribute("aria-current", "page");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await page
    .getByRole("link", { name: "יצירת פוסט", exact: true })
    .first()
    .click();
  await expect(page).toHaveURL(/\/he\/create$/);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
});
