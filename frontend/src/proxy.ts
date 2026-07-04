import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Public marketing + auth routes. Everything else is app and requires login.
const PUBLIC_PATHS = ["/", "/contact", "/terms", "/privacy", "/login", "/get-started"];

// Presence-based route gating using the `hd_authed` cookie. The real security
// boundary is the backend, which verifies the JWT on every API call; this only
// keeps unauthenticated users from landing on app pages (and vice versa).
// (Next 16 renamed the "middleware" convention to "proxy".)
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const authed = request.cookies.get("hd_authed")?.value === "1";
  const isPublic = PUBLIC_PATHS.some(
    (path) => pathname === path || (path !== "/" && pathname.startsWith(`${path}/`)),
  );

  if (!authed && !isPublic) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }

  // Logged-in users skip the marketing landing and the login page.
  if (authed && (pathname === "/" || pathname === "/login")) {
    const url = request.nextUrl.clone();
    url.pathname = "/dashboard";
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|ico)$).*)"],
};
