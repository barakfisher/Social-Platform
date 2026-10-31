import { test, expect } from "@playwright/test";
const sourceDocument = {
  id: "11111111-1111-4111-8111-111111111111",
  title: "מקור לדוגמה",
  source_type: "text",
  filename: null as string | null,
  created_at: "2026-10-30T09:15:00Z",
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
  await page
    .getByRole("button", { name: "מחיקה: מקור לדוגמה", exact: true })
    .click();
  await expect(
    page.getByText("למחוק את המקור ואת המקטעים שהוכנו ממנו?"),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "מחיקת המקור: מקור לדוגמה", exact: true })
    .click();
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
    .getByRole("button", { name: "Process again: מקור לדוגמה", exact: true })
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
    page.getByRole("button", {
      name: "Enable AI search: מקור לדוגמה",
      exact: true,
    }),
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
    .getByRole("button", { name: "Enable AI search: מקור לדוגמה", exact: true })
    .click();
  await expect(
    page.getByText("AI search preparation failed", { exact: true }),
  ).toBeVisible();
  fail = false;
  await page
    .getByRole("button", { name: "Enable AI search: מקור לדוגמה", exact: true })
    .click();
  await expect(page.getByText("Ready", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: "Enable AI search: מקור לדוגמה",
      exact: true,
    }),
  ).toHaveCount(0);
});

const pdfBytes = Buffer.from("%PDF-1.4\n% test file\n");

test("a PDF upload shows progress, its type and file name, then a processing failure", async ({
  page,
}) => {
  let item: typeof sourceDocument | null = null;
  let sent: { type: string | null; query: string; body: string } | null = null;
  await page.route("**/api/knowledge**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname.endsWith("/configuration")) {
      await route.fulfill({
        json: {
          configured: true,
          upload_max_bytes: 5 * 1024 * 1024,
          pdf_max_pages: 120,
        },
      });
      return;
    }
    if (request.method() === "POST" && url.pathname.endsWith("/files")) {
      sent = {
        type: request.headers()["content-type"] ?? null,
        query: url.search,
        body: request.postDataBuffer()?.toString() ?? "",
      };
      item = {
        ...sourceDocument,
        title: "Opening hours",
        source_type: "pdf",
        filename: "garden-guide.pdf",
      };
      await route.fulfill({ status: 202, json: { ...item, duplicate: false } });
      return;
    }
    await route.fulfill({
      json: { items: item ? [item] : [], total: item ? 1 : 0 },
    });
  });
  await page.goto("/en/knowledge");
  await expect(page.locator("#upload-limit")).toHaveText(
    "PDF, TXT or Markdown (UTF-8), up to 5 MB and 120 pages. Scanned PDFs need text recognition (OCR) first.",
  );
  await page.getByLabel("PDF or text file", { exact: true }).setInputFiles({
    name: "garden-guide.pdf",
    mimeType: "application/pdf",
    buffer: pdfBytes,
  });
  await page
    .getByLabel("File title (optional)", { exact: true })
    .fill("Opening hours");
  await page.getByRole("button", { name: "Upload file", exact: true }).click();
  await expect(
    page.getByText("File uploaded. Preparation is queued.", { exact: true }),
  ).toBeVisible();
  expect(sent).toEqual({
    type: "application/octet-stream",
    query: "?filename=garden-guide.pdf&title=Opening+hours",
    body: pdfBytes.toString(),
  });
  const entry = page.getByRole("listitem").filter({ hasText: "Opening hours" });
  await expect(entry).toContainText("PDF · garden-guide.pdf · Added");
  await expect(entry.locator("time")).toHaveAttribute(
    "datetime",
    sourceDocument.created_at,
  );
  await expect(page.getByLabel("File title (optional)")).toHaveValue("");
  item = {
    ...item!,
    status: "Failed",
    stage: "failed",
    error_code: "pdf_requires_ocr",
  };
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(entry).toContainText(
    "This PDF has no text layer (it looks scanned). Run text recognition (OCR) and upload it again.",
  );
  // Processing the same scanned file again cannot succeed, so it is not offered.
  await expect(
    entry.getByRole("button", { name: /^Process again/ }),
  ).toHaveCount(0);
});

test("unsupported and oversized files are refused before upload", async ({
  page,
}) => {
  let uploads = 0;
  await page.route("**/api/knowledge**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/configuration")) {
      await route.fulfill({
        json: { configured: true, upload_max_bytes: 1024, pdf_max_pages: 300 },
      });
      return;
    }
    if (url.pathname.endsWith("/files")) uploads += 1;
    await route.fulfill({ json: { items: [], total: 0 } });
  });
  await page.goto("/en/knowledge");
  const input = page.getByLabel("PDF or text file", { exact: true });
  const upload = page.getByRole("button", { name: "Upload file", exact: true });
  await upload.click();
  await expect(page.locator("section [role=alert]")).toHaveText(
    "Choose a file to upload.",
  );
  await input.setInputFiles({
    name: "notes.docx",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("PK"),
  });
  await upload.click();
  await expect(page.locator("section [role=alert]")).toHaveText(
    "Only PDF, TXT and Markdown files are supported.",
  );
  await input.setInputFiles({
    name: "big.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.alloc(2048, 1),
  });
  await upload.click();
  await expect(page.locator("section [role=alert]")).toHaveText(
    "The file is larger than the upload limit.",
  );
  await expect(input).toHaveAttribute("aria-invalid", "true");
  expect(uploads).toBe(0);
});

test("a rejected Hebrew text file keeps the choice and explains the fix", async ({
  page,
}) => {
  let attempts = 0;
  await page.route("**/api/knowledge**", async (route) => {
    const request = route.request();
    if (request.method() === "POST") {
      attempts += 1;
      await route.fulfill({
        status: 422,
        json: { error: { code: "http_error", message: "file_not_utf8" } },
      });
      return;
    }
    await route.fulfill({ json: { items: [], total: 0 } });
  });
  await page.goto("/he/knowledge");
  const input = page.getByLabel("קובץ PDF או טקסט", { exact: true });
  await input.setInputFiles({
    name: "הערות.txt",
    mimeType: "text/plain",
    buffer: Buffer.from([0xff, 0xfe, 0x00]),
  });
  await page.getByRole("button", { name: "העלאת הקובץ", exact: true }).click();
  await expect(page.locator("section [role=alert]")).toHaveText(
    "קובץ הטקסט לא בקידוד UTF-8. יש לשמור אותו כ־UTF-8 ולהעלות שוב.",
  );
  expect(attempts).toBe(1);
  expect(
    await input.evaluate((node: HTMLInputElement) => node.files?.[0]?.name),
  ).toBe("הערות.txt");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
});

test("a web page is added, shown with its link, and explains a fetch failure", async ({
  page,
}) => {
  let item: typeof sourceDocument | null = null;
  let sent: Record<string, unknown> | null = null;
  await page.route("**/api/knowledge**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === "POST" && url.pathname.endsWith("/url")) {
      sent = request.postDataJSON();
      item = {
        ...sourceDocument,
        title: "garden.example/hours",
        source_type: "url",
        filename: null,
        url: "https://garden.example/hours",
      } as typeof sourceDocument;
      await route.fulfill({ status: 202, json: { ...item, duplicate: false } });
      return;
    }
    await route.fulfill({
      json: { items: item ? [item] : [], total: item ? 1 : 0 },
    });
  });
  await page.goto("/en/knowledge");
  await page
    .getByLabel("Page address (URL)", { exact: true })
    .fill(" https://garden.example/hours ");
  await page.getByRole("button", { name: "Add web page", exact: true }).click();
  await expect(
    page.getByText("Web page added. It will be fetched and prepared.", {
      exact: true,
    }),
  ).toBeVisible();
  expect(sent).toEqual({ url: "https://garden.example/hours", title: "" });
  await expect(page.getByLabel("Page address (URL)")).toHaveValue("");
  const entry = page
    .getByRole("listitem")
    .filter({ hasText: "garden.example/hours" });
  await expect(entry).toContainText("Web link · https://garden.example/hours");
  const link = entry.getByRole("link", {
    name: "https://garden.example/hours",
  });
  await expect(link).toHaveAttribute("rel", "noopener noreferrer");
  item = {
    ...item!,
    status: "Failed",
    stage: "failed",
    error_code: "url_no_content",
  };
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(entry).toContainText("No readable text was found on this page.");
  await expect(
    entry.getByRole("button", {
      name: "Process again: garden.example/hours",
      exact: true,
    }),
  ).toBeVisible();
});

test("web addresses are checked in Hebrew before and after sending", async ({
  page,
}) => {
  let posts = 0;
  await page.route("**/api/knowledge**", async (route) => {
    if (route.request().method() === "POST") {
      posts += 1;
      await route.fulfill({
        status: 422,
        json: { error: { code: "http_error", message: "url_blocked_address" } },
      });
      return;
    }
    await route.fulfill({ json: { items: [], total: 0 } });
  });
  await page.goto("/he/knowledge");
  const input = page.getByLabel("כתובת הדף (URL)", { exact: true });
  const add = page.getByRole("button", { name: "הוספת הדף", exact: true });
  const alert = page.locator("section [role=alert]");
  await input.fill("ftp://garden.example/file");
  await add.click();
  await expect(alert).toHaveText("אפשר להוסיף רק כתובות http או https.");
  await input.fill("garden");
  await add.click();
  await expect(alert).toHaveText(
    "יש להזין כתובת מלאה, למשל https://example.com/page.",
  );
  expect(posts).toBe(0);
  await input.fill("http://10.0.0.5/admin");
  await add.click();
  await expect(alert).toHaveText(
    "הכתובת מפנה לרשת פרטית או מקומית, ואי אפשר לטעון אותה.",
  );
  expect(posts).toBe(1);
  await expect(input).toHaveValue("http://10.0.0.5/admin");
  await expect(input).toHaveAttribute("aria-invalid", "true");
});

const webPage = {
  ...sourceDocument,
  title: "Garden hours",
  source_type: "url",
  url: "https://garden.example/hours",
  status: "Ready",
  stage: "ready",
  chunk_count: 2,
  embedded_chunk_count: 2,
  fetched_at: "2026-10-30T09:15:00Z",
  refresh_result: null as string | null,
  refresh: null as {
    status: string;
    stage: string;
    error_code: string | null;
  } | null,
};

test("a changed web page shows its changes and the owner chooses to add them", async ({
  page,
}) => {
  let item = { ...webPage };
  const decisions: unknown[] = [];
  await page.route("**/api/knowledge**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith("/refresh")) {
      item = {
        ...item,
        refresh: { status: "Processing", stage: "fetching", error_code: null },
      };
      await route.fulfill({ status: 202, json: item });
      return;
    }
    if (path.endsWith("/refresh-changes")) {
      await route.fulfill({
        json: {
          added: ["Seed library opens on Sunday."],
          removed: ["Open until seven."],
          added_count: 3,
          removed_count: 1,
        },
      });
      return;
    }
    if (path.endsWith("/refresh-decision")) {
      decisions.push(request.postDataJSON());
      item = {
        ...item,
        refresh: null,
        refresh_result: "appended",
        fetched_at: "2026-10-30T11:00:00Z",
      };
      await route.fulfill({ status: 202, json: item });
      return;
    }
    await route.fulfill({ json: { items: [item], total: 1 } });
  });
  await page.goto("/en/knowledge");
  const entry = page.getByRole("listitem").filter({ hasText: "Garden hours" });
  await expect(entry.locator("time").nth(1)).toHaveAttribute(
    "datetime",
    webPage.fetched_at,
  );
  await entry
    .getByRole("button", {
      name: "Load again from the site: Garden hours",
      exact: true,
    })
    .click();
  await expect(entry).toContainText("Loading again…");
  await expect(entry.getByText("Ready", { exact: true })).toBeVisible();
  item = {
    ...item,
    refresh: {
      status: "Processing",
      stage: "awaiting_decision",
      error_code: null,
      added_count: 3,
      removed_count: 1,
    } as typeof item.refresh,
  };
  await expect(entry).toContainText(
    "The page changed: 3 new paragraphs, 1 no longer on the site.",
    { timeout: 10000 },
  );
  await expect(
    entry.getByRole("button", { name: "Load again from the site" }),
  ).toHaveCount(0);
  await entry
    .getByRole("button", { name: "Show changes: Garden hours", exact: true })
    .click();
  await expect(
    entry.getByText("New on the site", { exact: true }),
  ).toBeVisible();
  await expect(entry).toContainText("Seed library opens on Sunday.");
  await expect(entry).toContainText("Open until seven.");
  await expect(entry).toContainText("…and 2 more");
  await entry
    .getByRole("button", {
      name: "Add the new paragraphs: Garden hours",
      exact: true,
    })
    .click();
  await expect(entry).toContainText("New paragraphs from the site were added.");
  expect(decisions).toEqual([{ action: "append" }]);
  await expect(entry.locator("time").nth(1)).toHaveAttribute(
    "datetime",
    "2026-10-30T11:00:00Z",
  );
});

test("the Hebrew choice panel offers replace, add and keep", async ({
  page,
}) => {
  let item = {
    ...webPage,
    refresh: {
      status: "Processing",
      stage: "awaiting_decision",
      error_code: null,
      added_count: 0,
      removed_count: 2,
    } as typeof webPage.refresh,
  };
  const decisions: unknown[] = [];
  await page.route("**/api/knowledge**", async (route) => {
    const request = route.request();
    if (new URL(request.url()).pathname.endsWith("/refresh-decision")) {
      decisions.push(request.postDataJSON());
      item = { ...item, refresh: null, refresh_result: "kept" };
      await route.fulfill({ status: 202, json: item });
      return;
    }
    await route.fulfill({ json: { items: [item], total: 1 } });
  });
  await page.goto("/he/knowledge");
  const entry = page.getByRole("listitem").filter({ hasText: "Garden hours" });
  await expect(entry).toContainText(
    "הדף השתנה: 0 פסקאות חדשות, 2 שכבר לא באתר.",
  );
  await expect(
    entry.getByRole("button", {
      name: "הוספת הפסקאות החדשות: Garden hours",
      exact: true,
    }),
  ).toBeDisabled();
  await expect(
    entry.getByRole("button", {
      name: "החלפה בגרסה החדשה: Garden hours",
      exact: true,
    }),
  ).toBeEnabled();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await entry
    .getByRole("button", {
      name: "השארת הגרסה הנוכחית: Garden hours",
      exact: true,
    })
    .click();
  await expect(entry).toContainText("הגרסה הנוכחית נשמרה.");
  expect(decisions).toEqual([{ action: "keep" }]);
});

test("a failed reload in Hebrew says the previous version is still used", async ({
  page,
}) => {
  await page.route("**/api/knowledge**", async (route) => {
    await route.fulfill({
      json: {
        items: [
          {
            ...webPage,
            refresh: {
              status: "Failed",
              stage: "failed",
              error_code: "url_timeout",
            },
          },
        ],
        total: 1,
      },
    });
  });
  await page.goto("/he/knowledge");
  const entry = page.getByRole("listitem").filter({ hasText: "Garden hours" });
  await expect(entry).toContainText(
    "הטעינה מחדש לא הסתיימה: האתר לא ענה בזמן. אפשר לנסות לעבד שוב מאוחר יותר. הגרסה הקודמת עדיין בשימוש.",
  );
  await expect(entry).toContainText("נטען לאחרונה");
  await expect(
    entry.getByRole("button", {
      name: "טעינה מחדש מהאתר: Garden hours",
      exact: true,
    }),
  ).toBeVisible();
});
