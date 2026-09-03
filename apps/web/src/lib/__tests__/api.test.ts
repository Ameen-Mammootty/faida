import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * M7 WP-71: api.ts in live mode attaches the session's access token to every
 * request, reads it fresh each time, and turns a 401 into a trip to /login
 * that remembers the current screen. `fetch`, `window` and the Supabase
 * browser client are stubbed; nothing else is.
 */

const getAccessToken = vi.fn<() => Promise<string | null>>();

vi.mock("../supabase/browser", () => ({
  getAccessToken: () => getAccessToken(),
}));

const fetchMock = vi.fn<typeof fetch>();
const assign = vi.fn<(url: string) => void>();

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function liveApi() {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_MOCK_API", "false");
  vi.stubEnv("NEXT_PUBLIC_API_BASE", "https://api.example.test");
  return import("../api");
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("window", {
    location: { pathname: "/invoices", search: "?status=needs_review", assign },
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.clearAllMocks();
});

describe("api.ts in live mode", () => {
  it("attaches the session's access token as a bearer on every request", async () => {
    getAccessToken.mockResolvedValue("token-1");
    fetchMock.mockImplementation(async () => jsonResponse(200, { invoices: [] }));
    const api = await liveApi();

    await expect(api.listInvoices()).resolves.toEqual([]);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("https://api.example.test/api/invoices");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer token-1");
    expect(assign).not.toHaveBeenCalled();
  });

  it("reads the token fresh for each request, so a refresh mid-run is picked up", async () => {
    getAccessToken.mockResolvedValueOnce("token-1").mockResolvedValueOnce("token-2");
    fetchMock.mockImplementation(async () => jsonResponse(200, { menu_items: [] }));
    const api = await liveApi();

    await api.listMenuItems();
    await api.listMenuItems();

    const bearers = fetchMock.mock.calls.map(([, init]) =>
      new Headers(init?.headers).get("Authorization"),
    );
    expect(bearers).toEqual(["Bearer token-1", "Bearer token-2"]);
  });

  it("passes money through as the strings the API sent", async () => {
    getAccessToken.mockResolvedValue("token-1");
    fetchMock.mockImplementation(async () =>
      jsonResponse(200, { invoices: [{ id: "inv-1", total: "1234.50", currency: "AED" }] }),
    );
    const api = await liveApi();

    const rows = await api.listInvoices();
    expect(rows[0]).toMatchObject({ total: "1234.50" });
  });

  it("sends a 401 to /login, remembering the current screen", async () => {
    getAccessToken.mockResolvedValue("token-stale");
    fetchMock.mockImplementation(async () => jsonResponse(401, { detail: "Not authenticated" }));
    const api = await liveApi();

    await expect(api.listInvoices()).rejects.toMatchObject({ name: "ApiError", status: 401 });
    expect(assign).toHaveBeenCalledWith("/login?next=%2Finvoices%3Fstatus%3Dneeds_review");
  });

  it("goes to /login without calling the API when there is no session at all", async () => {
    getAccessToken.mockResolvedValue(null);
    const api = await liveApi();

    await expect(api.listInvoices()).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(assign).toHaveBeenCalledWith("/login?next=%2Finvoices%3Fstatus%3Dneeds_review");
  });

  it("surfaces the API's own detail for any other failure and stays on the screen", async () => {
    getAccessToken.mockResolvedValue("token-1");
    fetchMock.mockImplementation(async () => jsonResponse(404, { detail: "No such invoice" }));
    const api = await liveApi();

    await expect(api.getInvoice("nope")).rejects.toMatchObject({
      status: 404,
      message: "No such invoice",
    });
    expect(assign).not.toHaveBeenCalled();
  });
});

describe("api.ts in mock mode", () => {
  it("never asks for a token and never calls fetch", async () => {
    vi.resetModules();
    vi.stubEnv("NEXT_PUBLIC_MOCK_API", "true");
    const api = await import("../api");

    const rows = await api.listInvoices();
    expect(rows.length).toBeGreaterThan(0);
    expect(getAccessToken).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
