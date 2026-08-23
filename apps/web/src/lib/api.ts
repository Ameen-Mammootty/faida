/**
 * The typed client for the C6 web API surface as implemented (apps/api
 * src/faida_api/api.py, pinned by tests/test_api.py):
 *
 *   GET   /api/invoices                     {"invoices": [...]}, branch/supplier/status filters
 *   GET   /api/invoices/{id}                detail + checks + confidence + signed image URL
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
 * The bearer token is the demo's shared secret (real auth arrives in M6).
 * The mock serves byte-identical shapes, so components cannot tell the modes
 * apart.
 *
 * Money values are strings end to end and pass through this module verbatim.
 */

import { ApiError } from "./errors";
import {
  mockConfirmInvoice,
  mockGetInvoice,
  mockGetSupplierItemPrices,
  mockListInvoices,
  mockPatchInvoiceFields,
  mockUploadDocument,
} from "./mock/store";
import type {
  Correction,
  InvoiceDetail,
  InvoiceFilters,
  InvoiceSummary,
  PriceHistory,
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

export async function uploadDocument(file: File): Promise<UploadResult> {
  if (MOCK) return mockUploadDocument(file);
  const body = new FormData();
  body.append("file", file);
  return request<UploadResult>("/api/documents", { method: "POST", body });
}

export async function getSupplierItemPrices(supplierItemId: string): Promise<PriceHistory> {
  if (MOCK) return mockGetSupplierItemPrices(supplierItemId);
  return request<PriceHistory>(`/api/supplier-items/${encodeURIComponent(supplierItemId)}/prices`);
}
