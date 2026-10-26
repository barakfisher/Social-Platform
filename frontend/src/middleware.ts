import { NextResponse, type NextRequest } from "next/server";
export function middleware(request: NextRequest) {
  const headers = new Headers(request.headers);
  headers.set(
    "x-locale",
    request.nextUrl.pathname.split("/")[1] === "he" ? "he" : "en",
  );
  return NextResponse.next({ request: { headers } });
}
export const config = { matcher: ["/((?!api|_next|favicon.ico).*)"] };
