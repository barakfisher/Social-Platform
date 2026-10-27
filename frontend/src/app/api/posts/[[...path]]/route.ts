import { NextRequest, NextResponse } from "next/server";
export const dynamic = "force-dynamic";
export const maxDuration = 120;
async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path?: string[] }> },
) {
  const { path = [] } = await context.params;
  // One segment, or "{id}/review" for "Check again" (POST only).
  const review =
    path.length === 2 && path[1] === "review" && request.method === "POST";
  if (
    (path.length > 1 && !review) ||
    path.some((p) => !/^[a-zA-Z0-9-]+$/.test(p))
  )
    return NextResponse.json(
      { error: { message: "invalid_path" } },
      { status: 400 },
    );
  try {
    const body = ["POST", "PUT"].includes(request.method);
    if (
      body &&
      !request.headers.get("content-type")?.includes("application/json")
    )
      return NextResponse.json(
        { error: { message: "invalid_content_type" } },
        { status: 415 },
      );
    const response = await fetch(
      `${process.env.API_URL ?? "http://127.0.0.1:58073"}/posts${path.length ? "/" + path.join("/") : ""}${request.nextUrl.search}`,
      {
        method: request.method,
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(await request.json()) : undefined,
        cache: "no-store",
        signal: AbortSignal.timeout(110000),
      },
    );
    return NextResponse.json(await response.json(), {
      status: response.status,
    });
  } catch {
    return NextResponse.json(
      { error: { message: "api_unavailable" } },
      { status: 503 },
    );
  }
}
export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const DELETE = proxy;
