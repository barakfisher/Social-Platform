import { NextResponse, type NextRequest } from "next/server";

// Cross-site request forgery defence for the same-origin API proxies. A page on
// another site can send a "simple" POST (text/plain, form or no body) without a
// CORS preflight, so every proxy write must prove it came from this app's own
// pages before it reaches the paid backend.

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

// Host values this app answers on. A DNS-rebinding page reaches 127.0.0.1 under
// its own name, so its Host (and matching Origin) is not one of these.
export function allowedHosts() {
  return (process.env.APP_HOSTS ?? "127.0.0.1:53073,localhost:53073")
    .split(",")
    .map((host) => host.trim().toLowerCase())
    .filter(Boolean);
}

function isAllowedHost(request: NextRequest) {
  const host = request.headers.get("host");
  return host !== null && allowedHosts().includes(host.toLowerCase());
}

export function isJsonContentType(value: string | null) {
  return value?.split(";")[0].trim().toLowerCase() === "application/json";
}

function isSameOrigin(request: NextRequest) {
  const fetchSite = request.headers.get("sec-fetch-site");
  if (fetchSite !== null && fetchSite !== "same-origin") return false;
  const origin = request.headers.get("origin");
  if (origin === null) return true;
  const host = request.headers.get("host");
  return host !== null && origin === `${request.nextUrl.protocol}//${host}`;
}

function reject(code: string, status: number) {
  return NextResponse.json(
    { error: { code, message: code, request_id: crypto.randomUUID() } },
    { status },
  );
}

// Returns a rejection for an unsafe request, or null when it may proceed. Any
// method on a Host outside allowedHosts() is rejected (DNS rebinding could
// otherwise read through the proxy). Otherwise GET/HEAD/OPTIONS are never
// blocked. A write without Origin and Sec-Fetch-Site comes from a non-browser
// client (curl, scripts), which cannot ride the user's browser, so it is
// allowed. jsonBody marks writes whose body is forwarded.
export function rejectUnsafeWrite(
  request: NextRequest,
  { jsonBody }: { jsonBody: boolean },
) {
  if (!isAllowedHost(request)) return reject("cross_site_request", 403);
  if (SAFE_METHODS.has(request.method)) return null;
  if (!isSameOrigin(request)) return reject("cross_site_request", 403);
  if (jsonBody && !isJsonContentType(request.headers.get("content-type")))
    return reject("invalid_content_type", 415);
  return null;
}
