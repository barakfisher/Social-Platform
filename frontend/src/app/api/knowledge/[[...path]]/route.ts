import { NextRequest, NextResponse } from "next/server";
import { rejectUnsafeWrite } from "@/lib/csrf-guard";
export const dynamic = "force-dynamic";
// The largest UPLOAD_MAX_BYTES the backend settings allow.
const MAX_PROXY_UPLOAD_BYTES = 50 * 1024 * 1024;
async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path?: string[] }> },
) {
  const requestId = crypto.randomUUID();
  const { path = [] } = await context.params;
  const body =
    (request.method === "POST" &&
      ((path.length === 1 &&
        (path[0] === "text" ||
          path[0] === "url" ||
          // Connecting a Google Drive folder (SP-30).
          path[0] === "drive-folders")) ||
        (path.length === 2 && path[1] === "refresh-decision"))) ||
    // Changing a document's kind (SP-29).
    (request.method === "PATCH" && path.length === 1);
  // Raw file bytes (SP-9): application/octet-stream needs a CORS preflight, unlike
  // multipart form data, and the backend accepts it only on this route.
  const upload = request.method === "POST" && path.join("/") === "files";
  const rejected = rejectUnsafeWrite(request, { jsonBody: body });
  if (rejected) return rejected;
  if (
    upload &&
    request.headers.get("content-type")?.split(";")[0].trim().toLowerCase() !==
      "application/octet-stream"
  ) {
    return NextResponse.json(
      { error: { code: "invalid_content_type", request_id: requestId } },
      { status: 415 },
    );
  }
  // The backend enforces the configured limit; this only bounds what the proxy buffers.
  const declared = Number(request.headers.get("content-length") ?? NaN);
  if (upload && !(declared <= MAX_PROXY_UPLOAD_BYTES)) {
    return NextResponse.json(
      { error: { code: "file_too_large", request_id: requestId } },
      { status: 413 },
    );
  }
  // A Drive folder's Refresh is the one three-part path (SP-30).
  const folderSync =
    path.length === 3 && path[0] === "drive-folders" && path[2] === "sync";
  if (
    (path.length > 2 && !folderSync) ||
    path.some((part) => !/^[a-zA-Z0-9-]+$/.test(part))
  ) {
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
        headers: {
          "Content-Type": upload
            ? "application/octet-stream"
            : "application/json",
        },
        body: upload
          ? await request.arrayBuffer()
          : body
            ? JSON.stringify(await request.json())
            : undefined,
        cache: "no-store",
        // Connecting a Drive folder asks Google for a token and the folder (30 s each).
        signal: AbortSignal.timeout(
          upload ||
            (request.method === "POST" && path.join("/") === "drive-folders")
            ? 60000
            : 10000,
        ),
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
export const PATCH = proxy;
