import { test, expect, type Page } from "@playwright/test";
import { addSourceButton, openAddSource } from "./add-source-dialog";

// SP-30: a Google Drive folder shared with the service account syncs into the Knowledge Base.
const EMAIL = "reader@example.iam.gserviceaccount.com";
const LINK =
  "https://drive.google.com/drive/folders/1FakeFolderIdForTests0000000000000";
const folder = {
  id: "22222222-2222-4222-8222-222222222222",
  folder_id: "1FakeFolderIdForTests0000000000000",
  name: "מנטורינג",
  kind: "sample_posts",
  status: "Ready",
  error_code: null as string | null,
  synced_at: "2026-11-02T09:00:00Z",
  attempted_at: "2026-11-02T09:00:00Z",
  file_count: 1,
  skipped_count: 2,
  document_count: 1,
};
const isList = (url: string) => new URL(url).pathname === "/api/knowledge";

async function stub(
  page: Page,
  listing: { configured: boolean; items: (typeof folder)[] },
) {
  await page.route("**/api/knowledge**", async (route) => {
    if (isList(route.request().url()))
      await route.fulfill({ json: { items: [], total: 0 } });
    else await route.fallback();
  });
  await page.route("**/api/knowledge/configuration", (route) =>
    route.fulfill({ json: { configured: true } }),
  );
  await page.route("**/api/knowledge/drive-folders", async (route) => {
    if (route.request().method() === "GET")
      await route.fulfill({
        json: { ...listing, service_account_email: EMAIL },
      });
    else await route.fallback();
  });
}

test("without a key the form explains that Drive isn't set up", async ({
  page,
}) => {
  await stub(page, { configured: false, items: [] });
  await page.goto("/en/knowledge");
  await openAddSource(page, "en", "drive");
  await expect(
    page.getByText("Google Drive isn’t set up on the server yet."),
  ).toBeVisible();
  await expect(page.getByLabel("Folder link")).toHaveCount(0);
});

test("connecting shows whom to share with and sends the link and kind", async ({
  page,
}) => {
  await stub(page, { configured: true, items: [] });
  let sent: Record<string, unknown> | null = null;
  await page.route("**/api/knowledge/drive-folders", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    sent = route.request().postDataJSON();
    await route.fulfill({
      status: 202,
      json: { ...folder, status: "Pending", duplicate: false },
    });
  });
  await page.goto("/en/knowledge");
  await openAddSource(page, "en", "drive");
  await expect(page.getByText(EMAIL)).toBeVisible();
  await page.getByLabel("Folder link").fill(LINK);
  await page.locator("#drive-kind").selectOption("sample_posts");
  await page.getByRole("button", { name: "Connect folder" }).click();
  await expect.poll(() => sent).toEqual({ folder: LINK, kind: "sample_posts" });
  await expect(
    page.getByText("Folder connected. Its files are being imported."),
  ).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(addSourceButton(page)).toBeFocused();
});

test("a folder that isn't shared says what to do", async ({ page }) => {
  await stub(page, { configured: true, items: [] });
  await page.route("**/api/knowledge/drive-folders", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await route.fulfill({
      status: 404,
      json: { error: { code: "http_404", message: "drive_not_shared" } },
    });
  });
  await page.goto("/en/knowledge");
  await openAddSource(page, "en", "drive");
  await page.getByLabel("Folder link").fill(LINK);
  await page.getByRole("button", { name: "Connect folder" }).click();
  await expect(page.locator("#drive-error")).toContainText(
    "The service account can’t see this folder.",
  );
  await expect(page.getByLabel("Folder link")).toHaveAttribute(
    "aria-invalid",
    "true",
  );
});

test("a connected folder shows its sync, refreshes and disconnects", async ({
  page,
}) => {
  await stub(page, { configured: true, items: [folder] });
  const calls: string[] = [];
  await page.route(`**/api/knowledge/drive-folders/${folder.id}**`, (route) => {
    calls.push(
      `${route.request().method()} ${new URL(route.request().url()).pathname}`,
    );
    return route.fulfill({ json: { ...folder, deleted: true } });
  });
  await page.goto("/en/knowledge");
  const row = page.getByRole("listitem").filter({ hasText: "מנטורינג" });
  await expect(row).toContainText("Synced");
  await expect(row).toContainText("1 files imported · 2 skipped");
  await expect(row).toContainText("New files are added as Sample posts");

  await row.getByRole("button", { name: "Refresh: מנטורינג" }).click();
  await expect
    .poll(() => calls)
    .toContain(`POST /api/knowledge/drive-folders/${folder.id}/sync`);

  await row.getByRole("button", { name: "Disconnect: מנטורינג" }).click();
  await expect(row).toContainText("Nothing changes in Google Drive.");
  await row.getByRole("button", { name: "Disconnect and delete" }).click();
  await expect
    .poll(() => calls)
    .toContain(`DELETE /api/knowledge/drive-folders/${folder.id}`);
});

test("a failed sync says that nothing was deleted, in Hebrew too", async ({
  page,
}) => {
  await stub(page, {
    configured: true,
    items: [{ ...folder, status: "Failed", error_code: "drive_not_shared" }],
  });
  await page.goto("/he/knowledge");
  const row = page.getByRole("listitem").filter({ hasText: "מנטורינג" });
  await expect(row).toContainText("הסנכרון נכשל");
  await expect(row).toContainText("שום דבר לא נמחק.");
});

test("a syncing folder is polled until it shows when it last synced", async ({
  page,
}) => {
  let reads = 0;
  await stub(page, { configured: true, items: [] });
  await page.route("**/api/knowledge/drive-folders", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    reads += 1;
    const item =
      reads < 2 ? { ...folder, status: "Syncing", synced_at: null } : folder;
    await route.fulfill({
      json: { configured: true, service_account_email: EMAIL, items: [item] },
    });
  });
  await page.goto("/en/knowledge");
  const row = page.getByRole("listitem").filter({ hasText: "מנטורינג" });
  await expect(row).toContainText("Syncing…");
  await expect(row).toContainText("Not synced yet");
  await expect(row).toContainText("Last synced", { timeout: 10000 });
  await expect(page.getByText("מנטורינג: sync finished.")).toBeVisible();
});

test("a connect the proxy cannot finish still says so", async ({ page }) => {
  await stub(page, { configured: true, items: [] });
  await page.route("**/api/knowledge/drive-folders", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await route.fulfill({
      status: 503,
      json: { error: { code: "api_unavailable", request_id: "r" } },
    });
  });
  await page.goto("/en/knowledge");
  await openAddSource(page, "en", "drive");
  await page.getByLabel("Folder link").fill(LINK);
  await page.getByRole("button", { name: "Connect folder" }).click();
  await expect(page.locator("#drive-error")).toHaveText(
    "That didn’t work. Please try again.",
  );
});

test("Hebrew: without a key the form says Drive isn’t set up", async ({
  page,
}) => {
  await stub(page, { configured: false, items: [] });
  await page.goto("/he/knowledge");
  await openAddSource(page, "he", "drive");
  await expect(page.getByText("Google Drive עוד לא הוגדר בשרת.")).toBeVisible();
});
