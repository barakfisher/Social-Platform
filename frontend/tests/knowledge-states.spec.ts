import { test, expect } from "@playwright/test";

const source = {
  id: "11111111-1111-4111-8111-111111111111",
  title: "Alpha",
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
const second = {
  ...source,
  id: "22222222-2222-4222-8222-222222222222",
  title: "Beta",
};
const webPage = {
  ...source,
  title: "Garden hours",
  source_type: "url",
  url: "https://garden.example/hours",
  fetched_at: "2026-10-30T09:15:00Z",
};
const isList = (url: string) => new URL(url).pathname === "/api/knowledge";

test("deleting with the keyboard keeps focus in the page, in Hebrew", async ({
  page,
}) => {
  let items = [source, second];
  await page.route("**/api/knowledge**", async (route) => {
    if (route.request().method() === "DELETE") {
      items = items.filter((item) => item.id !== second.id);
      await route.fulfill({ json: { deleted: true } });
      return;
    }
    await route.fulfill({ json: { items, total: items.length } });
  });
  await page.goto("/he/knowledge");
  // Every row's buttons say which source they act on.
  await expect(
    page.getByRole("button", { name: "מחיקה: Alpha", exact: true }),
  ).toBeVisible();
  const remove = page.getByRole("button", { name: "מחיקה: Beta", exact: true });
  await remove.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator(":focus")).toHaveText(
    "למחוק את המקור ואת המקטעים שהוכנו ממנו?",
  );
  await page.keyboard.press("Escape");
  await expect(remove).toBeFocused();
  await page.keyboard.press("Enter");
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("button", { name: "מחיקת המקור: Beta", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByText("המקור נמחק.", { exact: true })).toBeVisible();
  await expect(page.locator("#sources-heading")).toBeFocused();
  await expect(page.getByRole("listitem")).toHaveCount(1);
});

test("a cancelled confirmation returns focus to its Delete button", async ({
  page,
}) => {
  await page.route("**/api/knowledge**", (route) =>
    route.fulfill({ json: { items: [source], total: 1 } }),
  );
  await page.goto("/en/knowledge");
  const remove = page.getByRole("button", { name: "Delete: Alpha" });
  await remove.click();
  await page
    .getByRole("button", { name: "Cancel: Alpha", exact: true })
    .click();
  await expect(remove).toBeFocused();
});

test("a web address error is tied to its field and focus stays there", async ({
  page,
}) => {
  let refuse = true;
  await page.route("**/api/knowledge**", async (route) => {
    if (new URL(route.request().url()).pathname.endsWith("/url")) {
      if (refuse) {
        await route.fulfill({
          status: 422,
          json: {
            error: { code: "validation_error", message: "url_blocked_address" },
          },
        });
        return;
      }
      await route.fulfill({
        status: 202,
        json: { ...webPage, duplicate: false },
      });
      return;
    }
    await route.fulfill({ json: { items: [], total: 0 } });
  });
  await page.goto("/en/knowledge");
  const input = page.getByLabel("Page address (URL)", { exact: true });
  await expect(input).toHaveAttribute("aria-describedby", "link-limit");
  await input.fill("http://10.0.0.5/admin");
  await input.press("Enter");
  await expect(page.locator("#link-error")).toHaveText(
    "This address points to a private or local network, which can’t be fetched.",
  );
  await expect(input).toBeFocused();
  await expect(input).toHaveAttribute("aria-invalid", "true");
  await expect(input).toHaveAttribute(
    "aria-describedby",
    "link-limit link-error",
  );
  refuse = false;
  await input.fill("https://garden.example/hours");
  await page.getByRole("button", { name: "Add web page", exact: true }).click();
  await expect(
    page.getByText("Web page added. It will be fetched and prepared.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(input).toBeFocused();
  await expect(input).toHaveAttribute("aria-invalid", "false");
});

test("a reload choice keeps focus on the source", async ({ page }) => {
  let item = {
    ...webPage,
    refresh: {
      status: "Processing",
      stage: "awaiting_decision",
      error_code: null,
      added_count: 1,
      removed_count: 0,
    },
  } as typeof webPage;
  await page.route("**/api/knowledge**", async (route) => {
    if (new URL(route.request().url()).pathname.endsWith("/refresh-decision")) {
      item = { ...item, refresh: null, refresh_result: "kept" };
      await route.fulfill({ status: 202, json: item });
      return;
    }
    await route.fulfill({ json: { items: [item], total: 1 } });
  });
  await page.goto("/en/knowledge");
  const keep = page.getByRole("button", {
    name: "Keep the current version: Garden hours",
  });
  await keep.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("Kept the current version.")).toBeVisible();
  await expect(page.locator(`#source-${source.id}`)).toBeFocused();
});

test("AI search refused during a reload explains why and keeps focus", async ({
  page,
}) => {
  // Started in another tab: this one still offers AI search.
  const item = { ...webPage, status: "Processing", stage: "text_prepared" };
  await page.route("**/api/knowledge**", async (route) => {
    if (new URL(route.request().url()).pathname.endsWith("/embed")) {
      await route.fulfill({
        status: 409,
        json: { error: { code: "conflict", message: "refresh_in_progress" } },
      });
      return;
    }
    if (new URL(route.request().url()).pathname.endsWith("/configuration")) {
      await route.fulfill({ json: { configured: true } });
      return;
    }
    await route.fulfill({ json: { items: [item], total: 1 } });
  });
  await page.goto("/en/knowledge");
  const embed = page.getByRole("button", {
    name: "Enable AI search: Garden hours",
  });
  await embed.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("section > [role=alert]")).toContainText(
    "This page is already loading again. Try again when it finishes.",
  );
  await expect(embed).toBeFocused();
});

test("a choice made elsewhere is explained and the list is reloaded", async ({
  page,
}) => {
  let item = {
    ...webPage,
    refresh: {
      status: "Processing",
      stage: "awaiting_decision",
      error_code: null,
      added_count: 1,
      removed_count: 0,
    },
  } as typeof webPage;
  await page.route("**/api/knowledge**", async (route) => {
    if (new URL(route.request().url()).pathname.endsWith("/refresh-decision")) {
      // Another tab already chose to keep the current version.
      item = { ...item, refresh: null, refresh_result: "kept" };
      await route.fulfill({
        status: 409,
        json: { error: { code: "conflict", message: "refresh_not_awaiting" } },
      });
      return;
    }
    await route.fulfill({ json: { items: [item], total: 1 } });
  });
  await page.goto("/he/knowledge");
  await page
    .getByRole("button", { name: "החלפה בגרסה החדשה: Garden hours" })
    .click();
  await expect(page.locator("section > [role=alert]")).toContainText(
    "הבחירה כבר נעשתה או שהטעינה מחדש הסתיימה. הרשימה עודכנה.",
  );
  await expect(page.getByText("הגרסה הנוכחית נשמרה.")).toBeVisible();
});

test("a reload of a page that is not prepared yet is explained in Hebrew", async ({
  page,
}) => {
  await page.route("**/api/knowledge**", async (route) => {
    if (new URL(route.request().url()).pathname.endsWith("/refresh")) {
      await route.fulfill({
        status: 409,
        json: { error: { code: "conflict", message: "refresh_not_ready" } },
      });
      return;
    }
    await route.fulfill({ json: { items: [webPage], total: 1 } });
  });
  await page.goto("/he/knowledge");
  await page
    .getByRole("button", { name: "טעינה מחדש מהאתר: Garden hours" })
    .click();
  await expect(page.locator("section > [role=alert]")).toContainText(
    "אפשר לטעון את הדף מחדש אחרי שהטקסט שלו הוכן.",
  );
});

test("upload progress is separate from checking the file and from preparation", async ({
  page,
}) => {
  let item: typeof source | null = null;
  let answer: () => void = () => {};
  const answered = new Promise<void>((resolve) => (answer = resolve));
  // Requests held by page.route never report upload progress, so the test plays
  // the browser's part and fires the upload events itself.
  await page.addInitScript(() => {
    const sent: XMLHttpRequest[] = [];
    const send = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.send = function (body) {
      sent.push(this);
      return send.call(this, body);
    };
    Object.assign(window, {
      uploadEvent: (type: string, loaded: number) =>
        sent.forEach((request) =>
          request.upload.dispatchEvent(
            new ProgressEvent(type, {
              lengthComputable: true,
              loaded,
              total: 100,
            }),
          ),
        ),
    });
  });
  const uploadEvent = (type: string, loaded: number) =>
    page.evaluate(
      ([type, loaded]) =>
        (
          window as unknown as {
            uploadEvent: (type: string, loaded: number) => void;
          }
        ).uploadEvent(type as string, loaded as number),
      [type, loaded],
    );
  await page.route("**/api/knowledge**", async (route) => {
    const request = route.request();
    if (new URL(request.url()).pathname.endsWith("/files")) {
      // The server is still checking and storing the file.
      await answered;
      item = {
        ...source,
        title: "Guide",
        source_type: "txt",
        filename: "guide.txt",
        status: "Pending",
        stage: "pending",
        chunk_count: 0,
      };
      await route.fulfill({ status: 202, json: { ...item, duplicate: false } });
      return;
    }
    await route.fulfill({
      json: { items: item ? [item] : [], total: item ? 1 : 0 },
    });
  });
  await page.goto("/en/knowledge");
  await page.getByLabel("PDF or text file", { exact: true }).setInputFiles({
    name: "guide.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Opening hours are nine to five.\n".repeat(2000)),
  });
  await page.getByRole("button", { name: "Upload file", exact: true }).click();
  await uploadEvent("progress", 42);
  await expect(
    page.getByRole("progressbar", { name: "Uploading" }),
  ).toHaveAttribute("aria-valuenow", "42");
  await expect(page.getByText("Uploading 42%", { exact: true })).toBeVisible();
  await uploadEvent("load", 100);
  const saving = page.getByRole("progressbar", {
    name: "Upload complete. Checking and saving the file…",
  });
  await expect(saving).toBeVisible();
  await expect(saving).not.toHaveAttribute("aria-valuenow");
  await expect(
    page.getByText("Upload complete. Checking and saving the file…", {
      exact: true,
    }),
  ).toBeVisible();
  answer();
  await expect(
    page.getByText("File uploaded. Preparation is queued.", { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("progressbar")).toHaveCount(0);
  const badge = page.getByRole("listitem").getByText("Queued", { exact: true });
  await expect(badge.locator("svg.animate-spin")).toHaveCount(1);
  await expect(page.getByLabel("PDF or text file")).toBeFocused();
});

test("an upload that loses a race with a delete says to upload again", async ({
  page,
}) => {
  await page.route("**/api/knowledge**", async (route) => {
    if (new URL(route.request().url()).pathname.endsWith("/files")) {
      await route.fulfill({
        status: 409,
        json: { error: { code: "conflict", message: "upload_conflict" } },
      });
      return;
    }
    await route.fulfill({ json: { items: [], total: 0 } });
  });
  await page.goto("/he/knowledge");
  const input = page.getByLabel("קובץ PDF או טקסט", { exact: true });
  await input.setInputFiles({
    name: "guide.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("שעות פתיחה"),
  });
  await page.getByRole("button", { name: "העלאת הקובץ", exact: true }).click();
  await expect(page.locator("#upload-error")).toHaveText(
    "קובץ זהה נמחק בזמן ההעלאה. אפשר להעלות את הקובץ שוב.",
  );
  await expect(input).toBeFocused();
  await expect(input).toHaveAttribute(
    "aria-describedby",
    "upload-limit upload-error",
  );
});

const resting = [
  {
    name: "text prepared",
    change: { status: "Processing", stage: "text_prepared", chunk_count: 3 },
    announced: "Alpha: Text prepared",
  },
  {
    name: "Ready",
    change: { status: "Ready", stage: "ready", chunk_count: 3 },
    announced: "Alpha: Ready",
  },
  {
    name: "Failed",
    change: { status: "Failed", stage: "failed", error_code: "url_timeout" },
    announced: "Alpha: Preparation failed",
  },
  {
    name: "a reload waiting for a choice",
    start: {
      ...webPage,
      title: "Alpha",
      refresh: { status: "Processing", stage: "fetching", error_code: null },
    },
    change: {
      refresh: {
        status: "Processing",
        stage: "awaiting_decision",
        error_code: null,
        added_count: 2,
        removed_count: 1,
      },
    },
    announced:
      "Alpha: The page changed: 2 new paragraphs, 1 no longer on the site. The current version stays in use until you choose.",
  },
  {
    name: "a finished reload",
    start: {
      ...webPage,
      title: "Alpha",
      refresh: { status: "Processing", stage: "fetching", error_code: null },
    },
    change: { refresh: null, refresh_result: "unchanged" },
    announced: "Alpha: No changes since the last load.",
  },
];
for (const { name, start, change, announced } of resting)
  test(`status refreshes without a reload and polling stops at ${name}`, async ({
    page,
  }) => {
    // A fake clock: the test does not depend on how often the list is polled.
    await page.clock.install();
    let item: object = start ?? {
      ...source,
      status: "Pending",
      stage: "pending",
      chunk_count: 0,
    };
    let polls = 0;
    await page.route("**/api/knowledge**", async (route) => {
      if (isList(route.request().url())) polls++;
      await route.fulfill({ json: { items: [item], total: 1 } });
    });
    await page.goto("/en/knowledge");
    await expect(page.getByRole("listitem")).toHaveCount(1);
    const before = polls;
    await page.clock.runFor(60_000);
    await expect.poll(() => polls).toBeGreaterThan(before);
    item = { ...item, ...change };
    await page.clock.runFor(60_000);
    await expect(page.locator("p.sr-only[role=status]")).toHaveText(announced);
    const settled = polls;
    await page.clock.runFor(10 * 60_000);
    expect(polls).toBe(settled);
  });

test("the same failure after Process again is announced again", async ({
  page,
}) => {
  await page.clock.install();
  const failed = {
    ...source,
    status: "Failed",
    stage: "failed",
    chunk_count: 0,
    error_code: "url_timeout",
  };
  let item: object = { ...failed, status: "Pending", stage: "pending" };
  await page.route("**/api/knowledge**", async (route) => {
    if (new URL(route.request().url()).pathname.endsWith("/retry")) {
      item = { ...failed, status: "Pending", stage: "pending" };
      await route.fulfill({ status: 202, json: item });
      return;
    }
    await route.fulfill({ json: { items: [item], total: 1 } });
  });
  await page.goto("/en/knowledge");
  const live = page.locator("p.sr-only[role=status]");
  await expect(page.getByText("Queued", { exact: true })).toBeVisible();
  item = failed;
  await page.clock.runFor(60_000);
  await expect(live).toHaveText("Alpha: Preparation failed");
  // toHaveText normalizes whitespace, which hides the difference a screen
  // reader needs, so the raw text is compared.
  const raw = () => live.evaluate((element) => element.textContent);
  const first = await raw();
  await page.getByRole("button", { name: "Process again: Alpha" }).click();
  await expect(page.getByText("Queued", { exact: true })).toBeVisible();
  item = failed;
  await page.clock.runFor(60_000);
  await expect.poll(raw).not.toBe(first);
  await expect(live).toHaveText(/^Alpha: Preparation failed/);
});

test("a failed first load is not shown as an empty Knowledge Base", async ({
  page,
}) => {
  let fail = true;
  let answerConfiguration: () => void = () => {};
  const configurationAnswered = new Promise<void>(
    (resolve) => (answerConfiguration = resolve),
  );
  await page.route("**/api/knowledge**", async (route) => {
    const url = route.request().url();
    if (new URL(url).pathname.endsWith("/configuration")) {
      await configurationAnswered;
      await route.fulfill({ json: { configured: true } });
      return;
    }
    if (fail) {
      await route.fulfill({ status: 500, json: {} });
      return;
    }
    await route.fulfill({ json: { items: [], total: 0 } });
  });
  await page.goto("/en/knowledge");
  const failure = page.getByText(
    "We couldn’t load your sources. Check the connection and try again.",
  );
  await expect(failure).toBeVisible();
  await expect(page.getByText("No sources yet.")).toHaveCount(0);
  // The connection message waits for the configuration instead of guessing.
  await expect(page.getByText("AI search is not connected yet.")).toHaveCount(
    0,
  );
  answerConfiguration();
  await expect(
    page.getByText("AI search can now be enabled for prepared sources."),
  ).toBeVisible();
  fail = false;
  await page
    .getByRole("alert")
    .filter({ hasText: "couldn’t load" })
    .getByRole("button", { name: "Refresh", exact: true })
    .click();
  await expect(failure).toHaveCount(0);
  await expect(
    page.getByText("No sources yet. Add your first text above."),
  ).toBeVisible();
});

test("sources show a loading state while the list is on its way", async ({
  page,
}) => {
  let answer: () => void = () => {};
  const answered = new Promise<void>((resolve) => (answer = resolve));
  await page.route("**/api/knowledge**", async (route) => {
    if (isList(route.request().url())) await answered;
    await route.fulfill({ json: { items: [source], total: 1 } });
  });
  await page.goto("/he/knowledge");
  await expect(page.getByText("טוען מקורות…", { exact: true })).toBeVisible();
  answer();
  await expect(page.getByText("טוען מקורות…")).toHaveCount(0);
  await expect(page.getByRole("listitem")).toHaveCount(1);
});

test("a Hebrew web address is shown readable and linked as sent", async ({
  page,
}) => {
  const encoded = "https://he.wikipedia.org/wiki/%D7%92%D7%99%D7%A0%D7%94";
  await page.route("**/api/knowledge**", (route) =>
    route.fulfill({
      json: { items: [{ ...webPage, url: encoded }], total: 1 },
    }),
  );
  await page.goto("/he/knowledge");
  const link = page.getByRole("link", {
    name: "https://he.wikipedia.org/wiki/גינה",
  });
  await expect(link).toHaveAttribute("href", encoded);
});

test("final processing errors offer no retry, retryable ones do", async ({
  page,
}) => {
  const failed = (id: string, title: string, error_code: string) => ({
    ...source,
    id,
    title,
    status: "Failed",
    stage: "failed",
    chunk_count: 0,
    error_code,
  });
  await page.route("**/api/knowledge**", (route) =>
    route.fulfill({
      json: {
        items: [
          failed(source.id, "Locked", "pdf_encrypted"),
          failed(second.id, "Slow site", "url_timeout"),
        ],
        total: 2,
      },
    }),
  );
  await page.goto("/en/knowledge");
  await expect(
    page.getByRole("button", { name: "Process again: Slow site" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Process again: Locked" }),
  ).toHaveCount(0);
  await expect(page.getByRole("listitem").first()).toContainText(
    "This PDF is password-protected.",
  );
});
