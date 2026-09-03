/**
 * M7 WP-71: the decisions behind the login gate, with no framework in them.
 *
 * `src/proxy.ts` (the Next request interceptor) and `api.ts` both consult
 * this module and do nothing clever of their own, so every path in the gated
 * list can be proven in vitest without a browser, a cookie jar or Supabase.
 *
 * The shape of the rule, pinned by the M7 decomposition:
 *
 * - The console screens - /invoices, /materials, /menu and everything under
 *   them, /menu/load included - need a signed-in user.
 * - The landing page, /login, the waitlist post and Next's own static assets
 *   stay open. The landing page is the marketing site; a redirect there
 *   would hide the product from the people it is for.
 * - In mock mode (NEXT_PUBLIC_MOCK_API anything but the exact string
 *   "false") the gate is bypassed and a fake signed-in owner is presented, so
 *   every gated screen still renders offline for QA and design reviews.
 */

/** The gated prefixes. A prefix matches itself and any path beneath it,
 * never a sibling that merely starts with the same letters (`/menus`). */
const GATED_PREFIXES = ["/invoices", "/materials", "/menu"] as const;

export const LOGIN_PATH = "/login";

/** Where a fresh sign-in lands when nothing asked for a particular screen. */
export const DEFAULT_AFTER_LOGIN = "/invoices";

/** Mock mode is the default; only the exact string "false" turns it off. */
export function isMockMode(value: string | undefined): boolean {
  return value !== "false";
}

/**
 * Whether the interceptor needs to know who is signed in for this path at
 * all: the gated screens, and /login itself (a signed-in visitor there goes
 * to the console). Every other path - the landing page, the waitlist post,
 * a 404 - is served without building a Supabase client, so a missing or
 * wrong Supabase env can never take the public site down, and a marketing
 * page view costs no auth call.
 */
export function needsSession(pathname: string): boolean {
  return pathname === LOGIN_PATH || isGatedPath(pathname);
}

export function isGatedPath(pathname: string): boolean {
  return GATED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

/** The login URL that remembers where the visitor was going. Query strings
 * ride along so a filtered invoice list survives the round trip. */
export function loginPath(next: string): string {
  const target = safeNextPath(next);
  return target === DEFAULT_AFTER_LOGIN
    ? LOGIN_PATH
    : `${LOGIN_PATH}?next=${encodeURIComponent(target)}`;
}

/**
 * The only `next` values the login form will follow: a path on this site.
 * Anything else - an absolute URL, a protocol-relative `//evil`, an empty
 * string, a path back to /login itself - falls back to the invoice list, so
 * a crafted link cannot bounce a signed-in owner off the site.
 */
export function safeNextPath(next: string | null | undefined): string {
  if (!next) return DEFAULT_AFTER_LOGIN;
  if (!next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) {
    return DEFAULT_AFTER_LOGIN;
  }
  if (next === LOGIN_PATH || next.startsWith(`${LOGIN_PATH}?`) || next.startsWith(`${LOGIN_PATH}/`)) {
    return DEFAULT_AFTER_LOGIN;
  }
  return next;
}

export type GateDecision =
  /** Serve the page as asked. */
  | { kind: "allow" }
  /** No session on a gated path: to /login, remembering the path. */
  | { kind: "login"; to: string }
  /** A signed-in visitor on /login: straight to the console. */
  | { kind: "console"; to: string };

export function gateDecision({
  pathname,
  search = "",
  hasSession,
  mockMode,
}: {
  pathname: string;
  /** The query string including its leading "?", or "" for none. */
  search?: string;
  hasSession: boolean;
  mockMode: boolean;
}): GateDecision {
  if (mockMode) return { kind: "allow" };
  if (pathname === LOGIN_PATH) {
    if (!hasSession) return { kind: "allow" };
    const params = new URLSearchParams(search);
    return { kind: "console", to: safeNextPath(params.get("next")) };
  }
  if (isGatedPath(pathname) && !hasSession) {
    return { kind: "login", to: loginPath(`${pathname}${search}`) };
  }
  return { kind: "allow" };
}
