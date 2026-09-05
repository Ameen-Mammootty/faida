/**
 * The typed client for the C6 web API surface as implemented (apps/api
 * src/faida_api/api.py, pinned by tests/test_api.py):
 *
 *   GET   /api/invoices                     {"invoices": [...]}, branch/supplier/status filters
 *   GET   /api/invoices/{id}                detail + checks + confidence + signed image URL
 *   POST  /api/invoices/manual              typed-in invoice (WP-34); returns the detail, 201
 *   PATCH /api/invoices/{id}/fields         {"corrections": [...]}; returns the re-validated detail
 *   POST  /api/invoices/{id}/confirm        confirm; refuses a cash hold (409); returns the detail
 *   POST  /api/invoices/{id}/approve        approve a cash hold with a reason (WP-74); the detail
 *   POST  /api/invoices/{id}/dismiss        a duplicate copy leaves the working list; the detail
 *   POST  /api/documents                    manual upload (multipart file [+ branch_id])
 *   GET   /api/supplier-items/{id}/prices   item header + confirmed prices, oldest first
 *
 * PATCH and confirm return the full updated detail payload - callers use it
 * directly and never refetch after a write.
 *
 * Mock mode is the default: set NEXT_PUBLIC_MOCK_API=false plus
 * NEXT_PUBLIC_API_BASE and the two Supabase values to talk to the real thing.
 * The mock serves byte-identical shapes, so components cannot tell the modes
 * apart.
 *
 * Auth (M7 WP-71, decision D5): the browser calls the API directly and every
 * request carries the signed-in user's Supabase access token as
 * `Authorization: Bearer <token>`. The token is read per request, never
 * cached here, so a refresh in the middle of a long run (the 45-recipe
 * loader) is picked up by the next call. A 401 means the session is gone:
 * the visitor is sent to /login with the current path remembered, and comes
 * back to it after signing in. This module is the single chokepoint - no
 * component knows there is a token.
 *
 * Money values are strings end to end and pass through this module verbatim.
 */

import { ApiError } from "./errors";
import { isMockMode as mockModeFrom, loginPath } from "./gate";
import { getAccessToken } from "./supabase/browser";
import {
  mockListBlockedCosts,
  mockListIngredients,
  mockListUnmappedSupplierItems,
  mockCreateIngredient,
  mockMapSupplierItem,
  mockRejectIngredient,
  mockSetPackSizeOverride,
  mockUnmapSupplierItem,
} from "./mock/materials";
import {
  mockArchiveMenuItem,
  mockGetMenuItem,
  mockListMenuItems,
  mockListPriceMoves,
  mockLoadMenuItem,
  mockUnarchiveMenuItem,
} from "./mock/menu";
import {
  mockAddBranchAlias,
  mockExcludeTillItem,
  mockGetBranches,
  mockGetSalesBranches,
  mockGetSalesCoverage,
  mockGetSalesDays,
  mockGetSalesLayouts,
  mockMapTillItem,
  mockPostSalesDays,
  mockPostSalesFile,
  mockSaveSalesLayout,
  mockUnmapTillItem,
} from "./mock/sales";
import { mockGetDashboard } from "./mock/dashboard";
import {
  mockApproveInvoice,
  mockConfirmInvoice,
  mockDismissInvoice,
  mockCreateManualInvoice,
  mockGetInvoice,
  mockGetSupplierItemPrices,
  mockListInvoices,
  mockPatchInvoiceFields,
  mockUploadDocument,
} from "./mock/store";
import type {
  BlockedCost,
  Branch,
  BranchAlias,
  Correction,
  DashboardResult,
  Ingredient,
  IngredientCreateInput,
  IngredientMappingInput,
  IngredientProposal,
  InvoiceDetail,
  InvoiceFilters,
  InvoiceListRow,
  ManualInvoiceInput,
  MappingResult,
  MenuItemDetail,
  MenuItemLoadInput,
  MenuItemSummary,
  MenuLoadResult,
  PackSizeOverrideResult,
  PriceHistory,
  PriceMove,
  RejectionResult,
  SalesBranchesResult,
  SalesCoverageResult,
  SalesDay,
  SalesDaysInput,
  SalesDaysResult,
  SalesFileResult,
  SalesLayout,
  SalesLayoutInput,
  TillItem,
  UnmappedSupplierItem,
  UploadResult,
} from "./types";

const MOCK = mockModeFrom(process.env.NEXT_PUBLIC_MOCK_API);
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

export function isMockMode(): boolean {
  return MOCK;
}

const SESSION_ENDED = "Your session has ended. Sign in again to continue.";

/**
 * Send the visitor to /login, remembering where they were. A full navigation
 * rather than the router: the interceptor must see the (absent) session on
 * the way back, and any screen state built on the old session is stale.
 */
function sendToLogin(): void {
  if (typeof window === "undefined") return;
  window.location.assign(loginPath(`${window.location.pathname}${window.location.search}`));
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (!API_BASE) {
    throw new ApiError(
      0,
      "NEXT_PUBLIC_API_BASE is not set. Set it (plus the Supabase values) or run in mock mode.",
    );
  }
  const token = await getAccessToken();
  if (!token) {
    sendToLogin();
    throw new ApiError(401, SESSION_ENDED);
  }
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "Couldn't reach the Faida API. Check that it is running.");
  }
  if (response.status === 401) {
    sendToLogin();
    throw new ApiError(401, SESSION_ENDED);
  }
  if (!response.ok) {
    let message = `The API returned ${response.status}.`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (typeof body.detail === "string" && body.detail) message = body.detail;
    } catch {
      // keep the status-based message
    }
    throw new ApiError(response.status, message);
  }
  return (await response.json()) as T;
}

function jsonInit(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export async function listInvoices(filters: InvoiceFilters = {}): Promise<InvoiceListRow[]> {
  if (MOCK) return mockListInvoices(filters);
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.branch_id) params.set("branch_id", filters.branch_id);
  if (filters.supplier_id) params.set("supplier_id", filters.supplier_id);
  const query = params.size > 0 ? `?${params.toString()}` : "";
  const body = await request<{ invoices: InvoiceListRow[] }>(`/api/invoices${query}`);
  return body.invoices;
}

export async function getInvoice(id: string): Promise<InvoiceDetail> {
  if (MOCK) return mockGetInvoice(id);
  return request<InvoiceDetail>(`/api/invoices/${encodeURIComponent(id)}`);
}

/** Apply one or more field corrections; resolves to the re-validated detail. */
export async function patchInvoiceFields(
  id: string,
  corrections: Correction[],
): Promise<InvoiceDetail> {
  if (MOCK) return mockPatchInvoiceFields(id, corrections);
  return request<InvoiceDetail>(
    `/api/invoices/${encodeURIComponent(id)}/fields`,
    jsonInit("PATCH", { corrections }),
  );
}

export async function confirmInvoice(id: string): Promise<InvoiceDetail> {
  if (MOCK) return mockConfirmInvoice(id);
  return request<InvoiceDetail>(`/api/invoices/${encodeURIComponent(id)}/confirm`, {
    method: "POST",
  });
}

/**
 * The cash gate (M7 WP-74, PRD §21): the owner approves a held cash paper with
 * a reason. The server requires the reason non-empty (422 otherwise) and
 * refuses anything that is not a held cash paper (409 with the sentence
 * saying why); the screen never sends a blank one. Resolves to the updated
 * detail, exactly like confirm - the same write, a different audit row.
 */
export async function approveInvoice(id: string, reason: string): Promise<InvoiceDetail> {
  if (MOCK) return mockApproveInvoice(id, reason);
  return request<InvoiceDetail>(
    `/api/invoices/${encodeURIComponent(id)}/approve`,
    jsonInit("POST", { reason }),
  );
}

/** Resolve a WP-44 duplicate hold: the copy leaves the working list. Held
 * duplicates only - the endpoint refuses anything else, including the original
 * the copy points at. Resolves to the updated detail, like confirm. */
export async function dismissInvoice(id: string): Promise<InvoiceDetail> {
  if (MOCK) return mockDismissInvoice(id);
  return request<InvoiceDetail>(`/api/invoices/${encodeURIComponent(id)}/dismiss`, {
    method: "POST",
  });
}

export async function uploadDocument(file: File, branchId?: string): Promise<UploadResult> {
  if (MOCK) return mockUploadDocument(file, branchId);
  const body = new FormData();
  body.append("file", file);
  if (branchId) body.append("branch_id", branchId);
  return request<UploadResult>("/api/documents", { method: "POST", body });
}

/**
 * The typed fallback (WP-34): create an invoice with no photo and no AI.
 * Resolves to the created invoice's full detail - green/amber already derived
 * by the same deterministic checks extraction uses.
 */
export async function createManualInvoice(body: ManualInvoiceInput): Promise<InvoiceDetail> {
  if (MOCK) return mockCreateManualInvoice(body);
  return request<InvoiceDetail>("/api/invoices/manual", jsonInit("POST", body));
}

export async function getSupplierItemPrices(supplierItemId: string): Promise<PriceHistory> {
  if (MOCK) return mockGetSupplierItemPrices(supplierItemId);
  return request<PriceHistory>(`/api/supplier-items/${encodeURIComponent(supplierItemId)}/prices`);
}

/**
 * M5 WP-52: raw materials.
 *
 *   GET    /api/ingredients                              materials + their packs
 *   GET    /api/supplier-items/unmapped                  the queue, most money first
 *   POST   /api/supplier-items/{id}/ingredient           approve a merge, or remap
 *   DELETE /api/supplier-items/{id}/ingredient           undo one
 *   POST   /api/supplier-items/{id}/ingredient/reject    not that material
 *
 * The matcher proposes; these are the four things a person can decide. Every
 * one of them writes an audit row naming who did it, because a wrong merge
 * corrupts the cost of every menu item using that material and there is no
 * photo to check it against.
 */

export async function listIngredients(): Promise<Ingredient[]> {
  if (MOCK) return mockListIngredients();
  const body = await request<{ ingredients: Ingredient[] }>("/api/ingredients");
  return body.ingredients;
}

/**
 * M6 WP-64: create a raw material a recipe names before any invoice does.
 * One click per material, never bulk - a CSV that mints twelve materials in
 * one keystroke is M5's forbidden auto-merge coming in through a side door.
 */
export async function createIngredient(
  body: IngredientCreateInput,
): Promise<IngredientProposal> {
  if (MOCK) return mockCreateIngredient(body);
  return request<IngredientProposal>("/api/ingredients", jsonInit("POST", body));
}

export async function listUnmappedSupplierItems(): Promise<UnmappedSupplierItem[]> {
  if (MOCK) return mockListUnmappedSupplierItems();
  const body = await request<{ items: UnmappedSupplierItem[] }>("/api/supplier-items/unmapped");
  return body.items;
}

/** Approve the merge, or remap a pack that is already mapped elsewhere. */
export async function mapSupplierItem(
  itemId: string,
  body: IngredientMappingInput,
): Promise<MappingResult> {
  if (MOCK) return mockMapSupplierItem(itemId, body);
  return request<MappingResult>(
    `/api/supplier-items/${encodeURIComponent(itemId)}/ingredient`,
    jsonInit("POST", body),
  );
}

/** The reverse gear: an approval gate with no undo is not one. */
export async function unmapSupplierItem(itemId: string): Promise<MappingResult> {
  if (MOCK) return mockUnmapSupplierItem(itemId);
  return request<MappingResult>(`/api/supplier-items/${encodeURIComponent(itemId)}/ingredient`, {
    method: "DELETE",
  });
}

export async function rejectIngredient(
  itemId: string,
  ingredientId: string,
): Promise<RejectionResult> {
  if (MOCK) return mockRejectIngredient(itemId, ingredientId);
  return request<RejectionResult>(
    `/api/supplier-items/${encodeURIComponent(itemId)}/ingredient/reject`,
    jsonInit("POST", { ingredient_id: ingredientId }),
  );
}

/**
 * M5 WP-55: the costs that could not be computed, and the sentence that clears
 * one.
 *
 *   GET  /api/blocked-costs                     grouped by product, most money first
 *   POST /api/supplier-items/{id}/pack-size     "one of these holds 10 kg"
 *
 * The list is derived from the invoice lines - there is no issues table - and
 * the answer writes one audit row, costs the lines that have no cost yet, and
 * never rewrites one that has.
 */

export async function listBlockedCosts(): Promise<BlockedCost[]> {
  if (MOCK) return mockListBlockedCosts();
  const body = await request<{ blocked: BlockedCost[] }>("/api/blocked-costs");
  return body.blocked;
}

export async function setPackSizeOverride(
  itemId: string,
  packSize: string,
): Promise<PackSizeOverrideResult> {
  if (MOCK) return mockSetPackSizeOverride(itemId, packSize);
  return request<PackSizeOverrideResult>(
    `/api/supplier-items/${encodeURIComponent(itemId)}/pack-size`,
    jsonInit("POST", { pack_size: packSize }),
  );
}

/**
 * M6 WP-61/62: the menu, costed.
 *
 *   GET /api/menu-items         every item + its plate answer (cost, margin, or what is missing)
 *   GET /api/menu-items/{id}    the drill: the current recipe, each component's cost and the
 *                               invoice line its price came from
 *
 * Plate costs are derived on every read from the same material prices the
 * materials screen shows - nothing stored, nothing to invalidate, so a newly
 * confirmed invoice moves these numbers on the next load.
 */

export async function listMenuItems(): Promise<MenuItemSummary[]> {
  if (MOCK) return mockListMenuItems();
  const body = await request<{ menu_items: MenuItemSummary[] }>("/api/menu-items");
  return body.menu_items;
}

export async function getMenuItem(id: string): Promise<MenuItemDetail> {
  if (MOCK) return mockGetMenuItem(id);
  return request<MenuItemDetail>(`/api/menu-items/${encodeURIComponent(id)}`);
}

/**
 * M6 WP-63: the money moment. Each material's latest price move and what it
 * did to every plate using it - or "price basis changed" with both packs
 * named and no delta, when the winning pack itself switched.
 */
export async function listPriceMoves(): Promise<PriceMove[]> {
  if (MOCK) return mockListPriceMoves();
  const body = await request<{ moves: PriceMove[] }>("/api/price-moves");
  return body.moves;
}

/**
 * M6 WP-64: the batch loader.
 *
 *   POST /api/menu-items/load            one recipe, one transaction
 *   POST /api/menu-items/{id}/archive    off the menu, never deleted
 *   POST /api/menu-items/{id}/unarchive  the click back
 *
 * The loader drives `loadMenuItem` once per recipe rather than posting the
 * whole file, for the reason the transaction exists: a row that fails leaves
 * the other forty-four alone, and the grid can restamp each row as its answer
 * arrives instead of after the last one.
 *
 * Archiving is always a person's click. A CSV missing half the menu must not
 * vaporize it, so the loader names what is absent and archives nothing.
 */
export async function loadMenuItem(body: MenuItemLoadInput): Promise<MenuLoadResult> {
  if (MOCK) return mockLoadMenuItem(body);
  return request<MenuLoadResult>("/api/menu-items/load", jsonInit("POST", body));
}

export async function archiveMenuItem(id: string): Promise<MenuItemDetail> {
  if (MOCK) return mockArchiveMenuItem(id);
  return request<MenuItemDetail>(`/api/menu-items/${encodeURIComponent(id)}/archive`, {
    method: "POST",
  });
}

export async function unarchiveMenuItem(id: string): Promise<MenuItemDetail> {
  if (MOCK) return mockUnarchiveMenuItem(id);
  return request<MenuItemDetail>(`/api/menu-items/${encodeURIComponent(id)}/unarchive`, {
    method: "POST",
  });
}

/**
 * M8 WP-83: the sales loader (Docs/M8_DECOMPOSITION.md §3.1, C11).
 *
 *   GET  /api/branches                     the tenant's branches with their till aliases
 *   POST /api/branches/{id}/aliases        teach the till's label for a branch, once
 *   POST /api/sales/files                  the raw CSV, kept under its server-computed hash
 *   GET  /api/sales/layouts                the saved column layouts, one per till
 *   POST /api/sales/layouts                save or update a layout, by name
 *   GET  /api/sales/days?from&to           stored branch-days with their lines (the preview reads them)
 *   POST /api/sales/days                   at most 31 branch-days, one transaction and one outcome each
 *
 * The loader posts the file first so every day it loads carries the hash of
 * the bytes it came from, then one branch-month per request: a refresh
 * mid-run resumes, and the door answers "unchanged" for anything that
 * already landed. Net figures come back from the door; the browser never
 * divides money.
 */

export async function getBranches(): Promise<Branch[]> {
  if (MOCK) return mockGetBranches();
  const body = await request<{ branches: Branch[] }>("/api/branches");
  return body.branches;
}

/** 409 when the alias already names another branch - surfaced as the
 * door's sentence, like every refusal. */
export async function addBranchAlias(branchId: string, alias: string): Promise<BranchAlias> {
  if (MOCK) return mockAddBranchAlias(branchId, alias);
  const body = await request<{ alias: BranchAlias }>(
    `/api/branches/${encodeURIComponent(branchId)}/aliases`,
    jsonInit("POST", { alias }),
  );
  return body.alias;
}

export async function postSalesFile(file: File): Promise<SalesFileResult> {
  if (MOCK) return mockPostSalesFile(file);
  const body = new FormData();
  body.append("file", file);
  return request<SalesFileResult>("/api/sales/files", { method: "POST", body });
}

export async function getSalesLayouts(): Promise<SalesLayout[]> {
  if (MOCK) return mockGetSalesLayouts();
  const body = await request<{ layouts: SalesLayout[] }>("/api/sales/layouts");
  return body.layouts;
}

export async function saveSalesLayout(input: SalesLayoutInput): Promise<SalesLayout> {
  if (MOCK) return mockSaveSalesLayout(input);
  const body = await request<{ layout: SalesLayout }>("/api/sales/layouts", jsonInit("POST", input));
  return body.layout;
}

export async function getSalesDays(from: string, to: string): Promise<SalesDay[]> {
  if (MOCK) return mockGetSalesDays(from, to);
  const params = new URLSearchParams({ from, to });
  const body = await request<{ days: SalesDay[] }>(`/api/sales/days?${params.toString()}`);
  return body.days;
}

export async function postSalesDays(input: SalesDaysInput): Promise<SalesDaysResult> {
  if (MOCK) return mockPostSalesDays(input);
  return request<SalesDaysResult>("/api/sales/days", jsonInit("POST", input));
}

/**
 * M8 WP-81/82/84: the sales screen (Docs/M8_DECOMPOSITION.md §3.1).
 *
 *   GET    /api/sales/branches?from&to       purchases ÷ net sales per branch, ranked and labelled
 *   GET    /api/sales/coverage?from&to       recipe coverage by sales value, with the mapping queue
 *   POST   /api/till-items/{id}/menu-item    approve a proposal, or remap
 *   DELETE /api/till-items/{id}/menu-item    unmap - the name goes back to the queue
 *   POST   /api/till-items/{id}/exclude      not a menu item
 *
 * Both reads take the same optional range; with neither the API answers the
 * 28 days ending on the tenant's newest loaded day (C11.6). The ratio is
 * derived on every read and never stored, so a manual reload after a paper
 * is confirmed is the whole refresh story. The three doors each write one
 * audit row on the server; a till name is never mapped without a keystroke.
 */

function rangeQuery(from?: string, to?: string): string {
  if (from === undefined || to === undefined) return "";
  const params = new URLSearchParams({ from, to });
  return `?${params.toString()}`;
}

/** GET /api/dashboard?from&to&branch_id - the whole owner screen in one read
 * (M9 C6 extended). `branchId` filters the league, the items and the signals;
 * the total always stays the chain. */
export async function getDashboard(
  from?: string,
  to?: string,
  branchId?: string,
): Promise<DashboardResult> {
  if (MOCK) return mockGetDashboard(from, to, branchId);
  const params = new URLSearchParams();
  if (from) params.set("from", from);
  if (to) params.set("to", to);
  if (branchId) params.set("branch_id", branchId);
  const query = params.size > 0 ? `?${params.toString()}` : "";
  return request<DashboardResult>(`/api/dashboard${query}`);
}

export async function getSalesBranches(from?: string, to?: string): Promise<SalesBranchesResult> {
  if (MOCK) return mockGetSalesBranches(from, to);
  return request<SalesBranchesResult>(`/api/sales/branches${rangeQuery(from, to)}`);
}

export async function getSalesCoverage(from?: string, to?: string): Promise<SalesCoverageResult> {
  if (MOCK) return mockGetSalesCoverage(from, to);
  return request<SalesCoverageResult>(`/api/sales/coverage${rangeQuery(from, to)}`);
}

export async function mapTillItem(tillItemId: string, menuItemId: string): Promise<TillItem> {
  if (MOCK) return mockMapTillItem(tillItemId, menuItemId);
  const body = await request<{ till_item: TillItem }>(
    `/api/till-items/${encodeURIComponent(tillItemId)}/menu-item`,
    jsonInit("POST", { menu_item_id: menuItemId }),
  );
  return body.till_item;
}

export async function unmapTillItem(tillItemId: string): Promise<TillItem> {
  if (MOCK) return mockUnmapTillItem(tillItemId);
  const body = await request<{ till_item: TillItem }>(
    `/api/till-items/${encodeURIComponent(tillItemId)}/menu-item`,
    { method: "DELETE" },
  );
  return body.till_item;
}

export async function excludeTillItem(tillItemId: string): Promise<TillItem> {
  if (MOCK) return mockExcludeTillItem(tillItemId);
  const body = await request<{ till_item: TillItem }>(
    `/api/till-items/${encodeURIComponent(tillItemId)}/exclude`,
    { method: "POST" },
  );
  return body.till_item;
}
