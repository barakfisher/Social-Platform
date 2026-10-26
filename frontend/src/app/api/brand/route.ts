import { NextRequest, NextResponse } from "next/server";
export const dynamic = "force-dynamic";
async function proxy(request: NextRequest) {
  const requestId = crypto.randomUUID();
  try {
    if (
      request.method === "PUT" &&
      !request.headers.get("content-type")?.includes("application/json")
    ) {
      return NextResponse.json(
        {
          error: {
            code: "invalid_content_type",
            message: "Use application/json.",
            request_id: requestId,
          },
        },
        { status: 415 },
      );
    }
    const response = await fetch(
      `${process.env.API_URL ?? "http://127.0.0.1:58073"}/brand`,
      {
        method: request.method,
        headers: { "Content-Type": "application/json" },
        body:
          request.method === "PUT"
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
      {
        error: {
          code: "api_unavailable",
          message: "The service is unavailable. Please try again.",
          request_id: requestId,
        },
      },
      { status: 503 },
    );
  }
}
export const GET = proxy;
export const PUT = proxy;
