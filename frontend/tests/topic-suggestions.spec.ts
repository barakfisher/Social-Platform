import { test, expect, type Page } from "@playwright/test";

const suggestions = {
  suggestions: [
    {
      topic: "How Cedar Garden grows sage",
      rationale: "The garden page describes the herbs it grows.",
      sources: [{ chunk_id: "c1", document_id: "d1", title: "Garden page" }],
    },
    {
      topic: "Why volunteers meet on Thursdays",
      rationale: "The schedule is the most concrete fact in your sources.",
      sources: [
        { chunk_id: "c2", document_id: "d1", title: "Garden page" },
        { chunk_id: "c3", document_id: "d2", title: "Volunteer guide" },
      ],
    },
  ],
  reason: null,
  metadata: {},
};
const models = {
  default: "openai/gpt-4.1",
  models: [
    {
      id: "openai/gpt-4.1",
      available: true,
      typical_usd: 0.007,
      max_usd: 0.04,
    },
  ],
};

async function mockApi(
  page: Page,
  {
    readyDocuments = 1,
    onSuggest = () => ({ status: 200, json: suggestions as object }),
  }: {
    readyDocuments?: number;
    onSuggest?: (body: Record<string, unknown>) => {
      status: number;
      json: object;
    };
  } = {},
) {
  const sent: Record<string, unknown>[] = [];
  await page.route("**/api/generation**", async (route) => {
    const url = route.request().url();
    if (route.request().method() === "GET") {
      await route.fulfill({
        json: url.includes("models")
          ? models
          : {
              configured: true,
              brand_ready: true,
              ready_documents: readyDocuments,
              topic_suggestions: true,
            },
      });
      return;
    }
    if (url.endsWith("/topic-suggestions")) {
      const body = route.request().postDataJSON();
      sent.push(body);
      const reply = onSuggest(body);
      await route.fulfill({ status: reply.status, json: reply.json });
      return;
    }
    await route.abort();
  });
  return sent;
}

test("a suggested topic fills the topic field and the request matches the form", async ({
  page,
}) => {
  const sent = await mockApi(page);
  await page.goto("/en/create");
  await page.getByLabel("Platform").selectOption("facebook");
  await page.getByLabel("Goal").fill("Invite volunteers");
  await page.getByRole("button", { name: "Suggest topics" }).click();
  const dialog = page.getByRole("dialog", { name: "Topic ideas" });
  const list = dialog.getByTestId("topic-suggestions");
  await expect(list.getByRole("listitem")).toHaveCount(2);
  await expect(list).toContainText(
    "Sources it cites: Garden page, Volunteer guide",
  );
  await list
    .getByRole("listitem")
    .nth(1)
    .getByRole("button", { name: "Use this topic" })
    .click();
  await expect(dialog).toBeHidden();
  const topic = page.getByLabel("What would you like to write about?");
  await expect(topic).toHaveValue("Why volunteers meet on Thursdays");
  await expect(topic).toBeFocused();
  // The rest of the form is untouched.
  await expect(page.getByLabel("Platform")).toHaveValue("facebook");
  await expect(page.getByLabel("Goal")).toHaveValue("Invite volunteers");
  expect(sent).toEqual([
    {
      platform: "facebook",
      language: "en",
      goal: "Invite volunteers",
      count: 3,
      writer_model: null,
    },
  ]);
});

test("no grounded topic shows an actionable empty state in Hebrew", async ({
  page,
}) => {
  await mockApi(page, {
    onSuggest: () => ({
      status: 200,
      json: {
        suggestions: [],
        reason: "no_grounded_suggestions",
        metadata: {},
      },
    }),
  });
  await page.goto("/he/create");
  await page.getByRole("button", { name: "הצעת נושאים" }).click();
  await expect(page.getByRole("status").last()).toContainText(
    "לא נמצא נושא שאפשר לקשר למקורות שלך",
  );
  await expect(page.getByTestId("topic-suggestions")).toHaveCount(0);
});

for (const [code, text] of [
  ["insufficient_context", "Your Knowledge Base has no ready sources yet."],
  ["generation_spending_limit", "per-request AI cost limit"],
  ["generation_unavailable", "Topic ideas couldn’t be loaded. Try again."],
]) {
  test(`${code} explains what to do and keeps the topic`, async ({ page }) => {
    await mockApi(page, {
      onSuggest: () => ({
        status: code === "insufficient_context" ? 409 : 503,
        json: { error: { message: code } },
      }),
    });
    await page.goto("/en/create");
    const topic = page.getByLabel("What would you like to write about?");
    await topic.fill("My own idea");
    await page.getByRole("button", { name: "Suggest topics" }).click();
    await expect(page.getByRole("alert").first()).toContainText(text);
    await expect(topic).toHaveValue("My own idea");
  });
}

test("suggestions wait for a ready Knowledge Base", async ({ page }) => {
  await mockApi(page, { readyDocuments: 0 });
  await page.goto("/en/create");
  await expect(
    page.getByRole("button", { name: "Suggest topics" }),
  ).toBeDisabled();
});

test("suggestions fit a phone screen in Hebrew", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await mockApi(page);
  await page.goto("/he/create");
  await page.getByRole("button", { name: "הצעת נושאים" }).click();
  await expect(
    page.getByTestId("topic-suggestions").getByRole("listitem"),
  ).toHaveCount(2);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
});

test("the dialog shows progress while ideas load and the chosen writer is sent", async ({
  page,
}) => {
  let release: () => void = () => {};
  const held = new Promise<void>((resolve) => (release = resolve));
  const sent: Record<string, unknown>[] = [];
  await page.route("**/api/generation**", async (route) => {
    const url = route.request().url();
    if (route.request().method() === "GET") {
      await route.fulfill({
        json: url.includes("models")
          ? {
              default: "openai/gpt-4.1",
              models: [
                ...models.models,
                {
                  id: "google/gemini-3.8-flash",
                  available: true,
                  typical_usd: 0.006,
                  max_usd: 0.03,
                },
              ],
            }
          : {
              configured: true,
              brand_ready: true,
              ready_documents: 1,
              topic_suggestions: true,
            },
      });
      return;
    }
    sent.push(route.request().postDataJSON());
    await held;
    await route.fulfill({ json: suggestions });
  });
  await page.goto("/en/create");
  await page.getByRole("tab", { name: "Models and cost" }).click();
  await page
    .getByLabel("Writing model")
    .selectOption("google/gemini-3.8-flash");
  await page.getByRole("tab", { name: "Post details" }).click();
  await page.getByRole("button", { name: "Suggest topics" }).click();
  const dialog = page.getByRole("dialog", { name: "Topic ideas" });
  await expect(dialog.getByRole("status")).toHaveText(
    "Finding topics in your sources…",
  );
  await expect(
    dialog.getByRole("button", { name: "Suggest other ideas" }),
  ).toBeDisabled();
  release();
  await expect(
    page.getByTestId("topic-suggestions").getByRole("listitem"),
  ).toHaveCount(2);
  expect(sent[0]).toMatchObject({ writer_model: "google/gemini-3.8-flash" });
});

test("reopening keeps the ideas without another paid request", async ({
  page,
}) => {
  const sent = await mockApi(page);
  await page.goto("/en/create");
  const open = page.getByRole("button", { name: "Suggest topics" });
  const dialog = page.getByRole("dialog", { name: "Topic ideas" });
  await open.click();
  await expect(dialog.getByRole("listitem")).toHaveCount(2);
  await dialog.getByRole("button", { name: "Close" }).click();
  await expect(dialog).toBeHidden();
  await expect(open).toBeFocused();
  await open.click();
  await expect(dialog.getByRole("listitem")).toHaveCount(2);
  expect(sent).toHaveLength(1);
  await dialog.getByRole("button", { name: "Suggest other ideas" }).click();
  await expect.poll(() => sent.length).toBe(2);
});

test("Escape closes the dialog and leaves the topic as it was", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto("/he/create");
  const topic = page.getByLabel("על מה נכתוב?");
  await topic.fill("הרעיון שלי");
  await page.getByRole("button", { name: "הצעת נושאים" }).click();
  const dialog = page.getByRole("dialog", { name: "רעיונות לנושאים" });
  await expect(dialog.getByRole("listitem")).toHaveCount(2);
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(topic).toHaveValue("הרעיון שלי");
});

test("ideas are cleared when the post language changes", async ({ page }) => {
  const sent = await mockApi(page);
  await page.goto("/en/create");
  const open = page.getByRole("button", { name: "Suggest topics" });
  const dialog = page.getByRole("dialog", { name: "Topic ideas" });
  await open.click();
  await expect(dialog.getByTestId("topic-suggestions")).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByLabel("Post language").selectOption("he");
  await open.click();
  await expect(dialog.getByTestId("topic-suggestions")).toBeVisible();
  expect(sent.map((body) => body.language)).toEqual(["en", "he"]);
});

test("ideas that arrive after the form changed are not shown", async ({
  page,
}) => {
  let release: () => void = () => {};
  const held = new Promise<void>((resolve) => (release = resolve));
  let calls = 0;
  const sent = await mockApi(page);
  await page.route("**/api/generation/topic-suggestions", async (route) => {
    sent.push(route.request().postDataJSON());
    // Only the first request is held, so it lands after the language changed.
    if (calls++ === 0) await held;
    await route.fulfill({ json: suggestions });
  });
  await page.goto("/en/create");
  const open = page.getByRole("button", { name: "Suggest topics" });
  const dialog = page.getByRole("dialog", { name: "Topic ideas" });
  await open.click();
  await expect(dialog.getByRole("status")).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByLabel("Post language").selectOption("he");
  const late = page.waitForResponse("**/api/generation/topic-suggestions");
  release();
  await late;
  await open.click();
  await expect(dialog.getByTestId("topic-suggestions")).toBeVisible();
  expect(sent.map((body) => body.language)).toEqual(["en", "he"]);
});

test("no grounded topic shows the English empty state", async ({ page }) => {
  await mockApi(page, {
    onSuggest: () => ({
      status: 200,
      json: {
        suggestions: [],
        reason: "no_grounded_suggestions",
        metadata: {},
      },
    }),
  });
  await page.goto("/en/create");
  await page.getByRole("button", { name: "Suggest topics" }).click();
  await expect(page.getByRole("status").last()).toContainText(
    "No topic could be tied to your sources this time.",
  );
});

for (const [code, text] of [
  ["generation_prompt_limit", "זהות המותג ארוכה מדי להצעת נושאים"],
  ["writer_model_unavailable", "מודל הכתיבה שנבחר כבר לא זמין"],
]) {
  test(`${code} has its own Hebrew message`, async ({ page }) => {
    await mockApi(page, {
      onSuggest: () => ({
        status: code === "generation_prompt_limit" ? 409 : 422,
        json: { error: { message: code } },
      }),
    });
    await page.goto("/he/create");
    await page.getByRole("button", { name: "הצעת נושאים" }).click();
    await expect(page.getByRole("alert").first()).toContainText(text);
  });
}
