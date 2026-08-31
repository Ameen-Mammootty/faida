/**
 * The typed client for the C6 web API surface as implemented (apps/api
 * src/faida_api/api.py, pinned by tests/test_api.py):
 *
 *   GET   /api/invoices                     {"invoices": [...]}, branch/supplier/status filters
 *   GET   /api/invoices/{id}                detail + checks + confidence + signed image URL
 *   POST  /api/invoices/manual              typed-in invoice (WP-34); returns the detail, 201
 *   PATCH /api/invoices/{id}/fields         {"corrections": [...]}; returns the re-validated detail
 *   POST  /api/invoices/{id}/confirm        confirm (or approve a cash hold); returns the detail
 *   POST  /api/documents                    manual upload (multipart file [+ branch_id])
 *   GET   /api/supplier-items/{id}/prices   item header + confirmed prices, oldest first
 *
 * PATCH and confirm return the full updated detail payload - callers use it
 * directly and never refetch after a write.
 *
 * Mock mode is the default: set NEXT_PUBLIC_MOCK_API=false plus
 * NEXT_PUBLIC_API_BASE and NEXT_PUBLIC_API_TOKEN to talk to the real thing.
 * The bearer token is the demo's shared secret (real auth arrives in M7).
 * The mock serves byte-identical shapes, so components cannot tell the modes
 * apart.
 *
 * Money values are strings end to end and pass through this module verbatim.
 */

import { ApiError } from "./errors";
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
  mockConfirmInvoice,
  mockCreateManualInvoice,
  mockGetInvoice,
  mockGetSupplierItemPrices,
  mockListInvoices,
  mockPatchInvoiceFields,
  mockUploadDocument,
} from "./mock/store";
import type {
  BlockedCost,
  Correction,
  Ingredient,
  IngredientCreateInput,
  IngredientMappingInput,
  IngredientProposal,
  InvoiceDetail,
  InvoiceFilters,
  InvoiceSummary,
  ManualInvoiceInput,
  MappingResult,
  MenuItemDetail,
  MenuItemLoadInput,
  MenuItemSummary,
  MenuLoadResult,
  PackSizeOverrideResult,
  PriceMove,
  PriceHistory,
  RejectionResult,
  UnmappedSupplierItem,
  UploadResult,
} from "./types";

const MOCK = process.env.NEXT_PUBLIC_MOCK_API !== "false";
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";
const API_TOKEN = process.env.NEXT_PUBLIC_API_TOKEN ?? "";

export function isMockMode(): boolean {
  return MOCK;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (!API_BASE) {
    throw new ApiError(
      0,
      "NEXT_PUBLIC_API_BASE is not set. Set it (plus NEXT_PUBLIC_API_TOKEN) or run in mock mode.",
    );
  }
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${API_TOKEN}`);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "Couldn't reach the Faida API. Check that it is running.");
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

export async function listInvoices(filters: InvoiceFilters = {}): Promise<InvoiceSummary[]> {
  if (MOCK) return mockListInvoices(filters);
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.branch_id) params.set("branch_id", filters.branch_id);
  if (filters.supplier_id) params.set("supplier_id", filters.supplier_id);
  const query = params.size > 0 ? `?${params.toString()}` : "";
  const body = await request<{ invoices: InvoiceSummary[] }>(`/api/invoices${query}`);
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
