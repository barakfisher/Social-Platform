import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test, expect } from "@playwright/test";
import { NextRequest } from "next/server";
import {
  allowedHosts,
  isJsonContentType,
  rejectUnsafeWrite,
} from "../src/lib/csrf-guard";

// Every browser request below targets a path the proxy rejects as invalid
// after the guard, so an allowed request ends in 400 invalid_path and no
// request ever reaches the backend or a paid provider.
const INVALID_PATH = "/api/generation/csrf/probe";
const APP = "http://127.0.0.1:53073";

function write(headers: Record<string, string>, method = "POST") {
  return new NextRequest(`${APP}/api/generation`, {
    method,
    headers: { host: "127.0.0.1:53073", ...headers },
  });
}

test.describe("csrf guard rules", () => {
  test("allows a same-origin JSON write", () => {
    const request = write({
      origin: APP,
      "sec-fetch-site": "same-origin",
      "content-type": "application/json; charset=utf-8",
    });
    expect(rejectUnsafeWrite(request, { jsonBody: true })).toBeNull();
  });

  for (const [name, headers] of [
    [
      "another site",
      { origin: "https://evil.example", "sec-fetch-site": "cross-site" },
    ],
    [
      "another local port",
      { origin: "http://127.0.0.1:3000", "sec-fetch-site": "same-site" },
    ],
    ["an opaque origin", { origin: "null" }],
    ["a foreign Origin alone", { origin: "http://localhost:53073" }],
    ["Sec-Fetch-Site alone", { "sec-fetch-site": "cross-site" }],
  ] as const) {
    test(`rejects a write from ${name}`, async () => {
      const rejected = rejectUnsafeWrite(
        write({ ...headers, "content-type": "application/json" }),
        { jsonBody: true },
      );
      expect(rejected?.status).toBe(403);
      expect((await rejected?.json()).error.code).toBe("cross_site_request");
    });
  }

  test("rejects JSON hidden in a text/plain content type", async () => {
    for (const type of [
      "text/plain;application/json",
      "text/plain",
      "application/jsonx",
    ])
      expect(isJsonContentType(type)).toBe(false);
    const rejected = rejectUnsafeWrite(
      write({
        origin: APP,
        "sec-fetch-site": "same-origin",
        "content-type": "text/plain;application/json",
      }),
      { jsonBody: true },
    );
    expect(rejected?.status).toBe(415);
  });

  test("allows bodiless writes without a content type", () => {
    const request = write({ origin: APP, "sec-fetch-site": "same-origin" });
    expect(rejectUnsafeWrite(request, { jsonBody: false })).toBeNull();
  });

  test("allows non-browser clients that send neither header", () => {
    const request = write({ "content-type": "application/json" });
    expect(rejectUnsafeWrite(request, { jsonBody: true })).toBeNull();
  });

  test("leaves GET untouched", () => {
    const request = write({ origin: "https://evil.example" }, "GET");
    expect(rejectUnsafeWrite(request, { jsonBody: false })).toBeNull();
  });

  for (const method of ["POST", "GET"]) {
    test(`rejects a ${method} on a rebound Host`, async () => {
      // DNS rebinding: the attacker's own name now resolves to 127.0.0.1, and
      // its Origin matches its Host, so only an explicit Host list catches it.
      const rebound = "http://rebind.evil.example:53073";
      const request = new NextRequest(`${rebound}/api/generation`, {
        method,
        headers: {
          host: "rebind.evil.example:53073",
          origin: rebound,
          "sec-fetch-site": "same-origin",
          "content-type": "application/json",
        },
      });
      const rejected = rejectUnsafeWrite(request, {
        jsonBody: method === "POST",
      });
      expect(rejected?.status).toBe(403);
      expect((await rejected?.json()).error.code).toBe("cross_site_request");
    });
  }

  test("allows every configured Host", () => {
    for (const host of allowedHosts()) {
      const request = new NextRequest(`http://${host}/api/generation`, {
        method: "POST",
        headers: {
          host,
          origin: `http://${host}`,
          "sec-fetch-site": "same-origin",
          "content-type": "application/json",
        },
      });
      expect(rejectUnsafeWrite(request, { jsonBody: true })).toBeNull();
    }
  });

  test("every API proxy route applies the guard", () => {
    const routes = (
      readdirSync(join(__dirname, "../src/app/api"), {
        recursive: true,
      }) as string[]
    ).filter((file) => file.endsWith("route.ts"));
    expect(routes.length).toBeGreaterThan(0);
    for (const route of routes)
      expect(
        readFileSync(join(__dirname, "../src/app/api", route), "utf8"),
        route,
      ).toContain("rejectUnsafeWrite(request");
  });
});

test.describe("csrf guard in the browser", () => {
  test("same-origin POST passes the guard", async ({ page }) => {
    await page.goto("/en");
    const statuses = await page.evaluate(async (url) => {
      const send = (type: string) =>
        fetch(url, {
          method: "POST",
          headers: { "Content-Type": type },
          body: "{}",
        });
      return [
        (await send("application/json")).status,
        (await send("text/plain;application/json")).status,
      ];
    }, INVALID_PATH);
    expect(statuses).toEqual([400, 415]);
  });

  test("a source's type change is a guarded JSON write", async ({ page }) => {
    // "csrf_probe" is one path segment the proxy refuses after its guard: 400 means
    // PATCH reached the proxy and passed the guard, 405 would mean it is not routed.
    await page.goto("/en");
    const statuses = await page.evaluate(async () => {
      const send = (type: string) =>
        fetch("/api/knowledge/csrf_probe", {
          method: "PATCH",
          headers: { "Content-Type": type },
          body: JSON.stringify({ kind: "sample_posts" }),
        });
      return [
        (await send("application/json")).status,
        (await send("text/plain;application/json")).status,
      ];
    });
    expect(statuses).toEqual([400, 415]);
  });

  test("file uploads must be raw octet-stream bytes", async ({ page }) => {
    // Form data can be sent cross-site without a preflight, so it never reaches the API.
    await page.goto("/en");
    const statuses = await page.evaluate(async () => {
      const send = (body: BodyInit, type?: string) =>
        fetch("/api/knowledge/files?filename=a.pdf", {
          method: "POST",
          headers: type ? { "Content-Type": type } : {},
          body,
        });
      const form = new FormData();
      form.append("file", new Blob(["%PDF-1.4"]), "a.pdf");
      return [
        (await send(form)).status,
        (await send("%PDF-1.4", "text/plain")).status,
        (await send("{}", "application/json")).status,
      ];
    });
    expect(statuses).toEqual([415, 415, 415]);
  });

  test("cross-site no-cors POST is rejected", async ({ page, baseURL }) => {
    // localhost and 127.0.0.1 are different sites, so the app served under the
    // other hostname stands in for a malicious local page. A page Playwright
    // fulfils itself counts as public and Chromium blocks its local requests.
    const target = new URL(INVALID_PATH, baseURL);
    const attacker = new URL("/en", baseURL);
    attacker.hostname =
      attacker.hostname === "localhost" ? "127.0.0.1" : "localhost";
    await page.goto(attacker.href);
    const response = page.waitForResponse(target.href);
    await page.evaluate((url) => {
      void fetch(url, {
        method: "POST",
        mode: "no-cors",
        headers: { "Content-Type": "text/plain;application/json" },
        body: "{}",
      });
    }, target.href);
    expect((await response).status()).toBe(403);
  });

  test("cross-site POST to a Check again route is rejected", async ({
    page,
    baseURL,
  }) => {
    // The guard runs before the "{id}/review" path rule, so nothing is forwarded.
    const attacker = new URL("/en", baseURL);
    attacker.hostname =
      attacker.hostname === "localhost" ? "127.0.0.1" : "localhost";
    await page.goto(attacker.href);
    for (const route of ["generation", "posts"]) {
      const target = new URL(
        `/api/${route}/00000000-0000-4000-8000-000000000000/review`,
        baseURL,
      );
      const response = page.waitForResponse(target.href);
      await page.evaluate((url) => {
        void fetch(url, {
          method: "POST",
          mode: "no-cors",
          headers: { "Content-Type": "text/plain;application/json" },
          body: "{}",
        });
      }, target.href);
      expect((await response).status()).toBe(403);
    }
  });
});
