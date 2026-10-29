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
  const list = page.getByTestId("topic-suggestions");
  await expect(list.getByRole("listitem")).toHaveCount(2);
  await expect(list).toContainText("Based on: Garden page, Volunteer guide");
  await list
    .getByRole("listitem")
    .nth(1)
    .getByRole("button", { name: "Use this topic" })
    .click();
  await expect(
    page.getByLabel("What would you like to write about?"),
  ).toHaveValue("Why volunteers meet on Thursdays");
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
