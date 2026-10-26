import { NextRequest, NextResponse } from "next/server";
export const dynamic = "force-dynamic";
async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path?: string[] }> },
) {
  const requestId = crypto.randomUUID();
  const { path = [] } = await context.params;
  if (path.length > 2 || path.some((part) => !/^[a-zA-Z0-9-]+$/.test(part))) {
    return NextResponse.json(
      { error: { code: "invalid_path", request_id: requestId } },
      { status: 400 },
    );
  }
  try {
    if (
      request.method === "POST" &&
      path[0] === "text" &&
      !request.headers.get("content-type")?.includes("application/json")
    ) {
      return NextResponse.json(
        { error: { code: "invalid_content_type", request_id: requestId } },
        { status: 415 },
      );
    }
    const response = await fetch(
      `${process.env.API_URL ?? "http://127.0.0.1:58073"}/knowledge${path.length ? "/" + path.join("/") : ""}${request.nextUrl.search}`,
      {
        method: request.method,
        headers: { "Content-Type": "application/json" },
        body:
          request.method === "POST" && path[0] === "text"
            ? JSON.stringify(await request.json())
            : undefined,
        cache: "no-store",
        signal: AbortSignal.timeout(10000),
      },
    );
    return NextResponse.json(await response.json(), {
      status: response.status,
    });
  } catch {
    return NextResponse.json(
      { error: { code: "api_unavailable", request_id: requestId } },
      { status: 503 },
    );
  }
}
export const GET = proxy;
export const POST = proxy;
export const DELETE = proxy;
