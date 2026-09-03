import { NextResponse, type NextRequest } from "next/server";
import { gateDecision, isMockMode, needsSession } from "@/lib/gate";
import { supabaseForRequest } from "@/lib/supabase/server";

/**
 * M7 WP-71: the login gate, as Next 16's request interceptor.
 *
 * This is the `proxy` file convention (the one that used to be called
 * middleware). A leftover `src/middleware.ts` is silently ignored by this
 * Next and would unprotect every route, so none may exist.
 *
 * Two jobs, in order:
 *
 * 1. Refresh the session cookies. Supabase's server client reads the cookies
 *    off the request, refreshes an expired token, and writes the new cookies
 *    back through `setAll`, so the pass-through and the redirect below both
 *    carry them.
 * 2. Decide. `getUser()` asks Supabase whether the session is real - never
 *    `getSession()`, which trusts whatever the cookie says. A gated path with
 *    no user goes to /login with the path remembered; a signed-in visitor on
 *    /login goes straight to the console. Everything else is served as
 *    asked. The rule itself is `gateDecision` in `lib/gate.ts`, pure and
 *    tested; this file only wires it to the request.
 *
 * Public paths (the landing page, the waitlist post, anything not gated and
 * not /login) return before any client exists, so the marketing site never
 * depends on Supabase env or spends an auth call per view.
 *
 * In mock mode the whole thing steps aside: no Supabase client is built (no
 * env is needed) and every screen renders with the sample data and a fake
 * signed-in owner, for offline QA and design reviews.
 */
export async function proxy(request: NextRequest) {
  const mockMode = isMockMode(process.env.NEXT_PUBLIC_MOCK_API);
  if (mockMode) return NextResponse.next();
  // Public paths never touch Supabase: no client, no env read, no auth call.
  // The landing page and the waitlist post must keep working even when the
  // Supabase values are missing or wrong on the host.
  if (!needsSession(request.nextUrl.pathname)) return NextResponse.next();

  const bound = supabaseForRequest(request);
  const {
    data: { user },
  } = await bound.supabase.auth.getUser();

  const decision = gateDecision({
    pathname: request.nextUrl.pathname,
    search: request.nextUrl.search,
    hasSession: user !== null,
    mockMode,
  });
  if (decision.kind === "allow") return bound.response;

  const redirect = NextResponse.redirect(new URL(decision.to, request.url));
  for (const cookie of bound.response.cookies.getAll()) {
    redirect.cookies.set(cookie);
  }
  return redirect;
}

export const config = {
  // Everything except Next's own assets, the image optimizer, the app's
  // route handlers (the waitlist post needs no login), and files with an
  // extension (favicon, the brand SVGs, the CSV template, the fixtures).
  matcher: ["/((?!api/|_next/static|_next/image|.*\\..*).*)"],
};
