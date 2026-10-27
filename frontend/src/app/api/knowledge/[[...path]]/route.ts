import { NextRequest, NextResponse } from "next/server";
import { rejectUnsafeWrite } from "@/lib/csrf-guard";
export const dynamic = "force-dynamic";
async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path?: string[] }> },
) {
  const requestId = crypto.randomUUID();
  const { path = [] } = await context.params;
  const body = request.method === "POST" && path[0] === "text";
  const rejected = rejectUnsafeWrite(request, { jsonBody: body });
  if (rejected) return rejected;
  if (path.length > 2 || path.some((part) => !/^[a-zA-Z0-9-]+$/.test(part))) {
    return NextResponse.json(
      { error: { code: "invalid_path", request_id: requestId } },
      { status: 400 },
    );
  }
  try {
    const response = await fetch(
      `${process.env.API_URL ?? "http://127.0.0.1:58073"}/knowledge${path.length ? "/" + path.join("/") : ""}${request.nextUrl.search}`,
      {
        method: request.method,
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(await request.json()) : undefined,
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
