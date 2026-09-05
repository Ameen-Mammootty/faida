import { describe, expect, it } from "vitest";
import { needsSession, gateDecision, isGatedPath, isMockMode, loginPath, safeNextPath } from "../gate";

/**
 * M7 WP-71: the login gate's decisions, one row per path the app actually
 * serves. The list is the acceptance: every console screen is behind the
 * gate, and the landing page, the login page, the waitlist post and Next's
 * assets are not.
 */

const GATED = [
  "/dashboard",
  "/invoices",
  "/invoices/inv-1001",
  "/invoices/new",
  "/invoices/manual",
  "/materials",
  "/menu",
  "/menu/load",
  "/menu/mi-0001",
  "/sales",
  "/sales/load",
];

const OPEN = [
  "/",
  "/login",
  "/api/waitlist",
  "/_next/static/chunks/main.js",
  "/_next/image",
  "/favicon.ico",
  "/icon.svg",
  "/brand/faida-mark.svg",
  "/faida-menu-template.csv",
  "/faida-sales-template.csv",
  "/fixtures/inv-1001.svg",
  // Lookalike prefixes are not the console.
  "/dashboards",
  "/menus",
  "/invoicesx",
  "/materialsheet",
  "/salesman",
];

describe("isGatedPath", () => {
  it.each(GATED)("gates %s", (path) => {
    expect(isGatedPath(path)).toBe(true);
  });

  it.each(OPEN)("leaves %s open", (path) => {
    expect(isGatedPath(path)).toBe(false);
  });
});

describe("isMockMode", () => {
  it("is on unless the value is exactly the string false", () => {
    expect(isMockMode(undefined)).toBe(true);
    expect(isMockMode("")).toBe(true);
    expect(isMockMode("true")).toBe(true);
    expect(isMockMode("FALSE")).toBe(true);
    expect(isMockMode("0")).toBe(true);
    expect(isMockMode("false")).toBe(false);
  });
});

describe("gateDecision", () => {
  it.each(GATED)("sends a signed-out visitor to /login from %s, remembering the path", (path) => {
    const decision = gateDecision({ pathname: path, hasSession: false, mockMode: false });
    expect(decision).toEqual({ kind: "login", to: loginPath(path) });
  });

  it("keeps the query string on the way to /login", () => {
    const decision = gateDecision({
      pathname: "/invoices",
      search: "?status=needs_review",
      hasSession: false,
      mockMode: false,
    });
    expect(decision).toEqual({
      kind: "login",
      to: "/login?next=%2Finvoices%3Fstatus%3Dneeds_review",
    });
  });

  it.each(GATED)("serves %s to a signed-in visitor", (path) => {
    expect(gateDecision({ pathname: path, hasSession: true, mockMode: false })).toEqual({
      kind: "allow",
    });
  });

  it.each(OPEN)("serves %s to a signed-out visitor", (path) => {
    expect(gateDecision({ pathname: path, hasSession: false, mockMode: false })).toEqual({
      kind: "allow",
    });
  });

  it("sends a signed-in visitor on /login to the dashboard (M9 P10)", () => {
    expect(gateDecision({ pathname: "/login", hasSession: true, mockMode: false })).toEqual({
      kind: "console",
      to: "/dashboard",
    });
  });

  it("round-trips a bookmark to /invoices through ?next= after the landing change", () => {
    // Signed out on the bookmark: to /login, the path remembered - where
    // before the change the bare /login would have done, because /invoices
    // was the default.
    const out = gateDecision({ pathname: "/invoices", hasSession: false, mockMode: false });
    expect(out).toEqual({ kind: "login", to: "/login?next=%2Finvoices" });
    // Signed in on that login URL: back to the bookmark, not the dashboard.
    const back = gateDecision({
      pathname: "/login",
      search: "?next=%2Finvoices",
      hasSession: true,
      mockMode: false,
    });
    expect(back).toEqual({ kind: "console", to: "/invoices" });
  });

  it("keeps a branch link to the dashboard through the gate", () => {
    const decision = gateDecision({
      pathname: "/dashboard",
      search: "?branch=br-03",
      hasSession: false,
      mockMode: false,
    });
    expect(decision).toEqual({ kind: "login", to: "/login?next=%2Fdashboard%3Fbranch%3Dbr-03" });
  });

  it("sends a signed-in visitor on /login to the screen they were heading for", () => {
    expect(
      gateDecision({
        pathname: "/login",
        search: "?next=%2Fmenu%2Fload",
        hasSession: true,
        mockMode: false,
      }),
    ).toEqual({ kind: "console", to: "/menu/load" });
  });

  it.each([...GATED, ...OPEN])("bypasses the gate in mock mode for %s", (path) => {
    expect(gateDecision({ pathname: path, hasSession: false, mockMode: true })).toEqual({
      kind: "allow",
    });
  });
});

describe("safeNextPath", () => {
  it("follows a path on this site", () => {
    expect(safeNextPath("/menu/load")).toBe("/menu/load");
    expect(safeNextPath("/invoices?status=needs_review")).toBe("/invoices?status=needs_review");
  });

  it.each([
    null,
    undefined,
    "",
    "https://evil.example/",
    "//evil.example/",
    "/\\evil.example",
    "invoices",
    "/login",
    "/login?next=%2Fmenu",
  ])("falls back to the dashboard for %s", (value) => {
    expect(safeNextPath(value)).toBe("/dashboard");
  });

  it("still follows a bookmark to the invoice list", () => {
    expect(safeNextPath("/invoices")).toBe("/invoices");
  });
});

describe("loginPath", () => {
  it("omits next when the destination is the default", () => {
    expect(loginPath("/dashboard")).toBe("/login");
  });

  it("carries next for the invoice list now that it is not the default", () => {
    expect(loginPath("/invoices")).toBe("/login?next=%2Finvoices");
  });

  it("encodes the destination otherwise", () => {
    expect(loginPath("/menu/load")).toBe("/login?next=%2Fmenu%2Fload");
  });
});

describe("needsSession", () => {
  it("is true for every gated path and for /login itself", () => {
    for (const path of [
      "/login",
      "/dashboard",
      "/invoices",
      "/invoices/abc",
      "/materials",
      "/menu",
      "/menu/load",
      "/sales",
      "/sales/load",
    ]) {
      expect(needsSession(path)).toBe(true);
    }
  });

  it("is false for the public site, so no Supabase client is ever built there", () => {
    for (const path of ["/", "/api/waitlist", "/menus", "/dashboards", "/nowhere", "/login-help"]) {
      expect(needsSession(path)).toBe(false);
    }
  });
});
