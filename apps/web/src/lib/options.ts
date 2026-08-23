/**
 * Filter/select options derived from the invoice list. C6 has no branches or
 * suppliers endpoint, so every screen that needs a choice (list filters, the
 * upload page, manual entry) derives distinct id -> name pairs from one
 * unfiltered GET /api/invoices - the same source in mock and real mode.
 */

import type { InvoiceSummary } from "./types";

export interface FilterOption {
  id: string;
  name: string;
}

/** Distinct id -> name pairs, sorted by name. */
export function distinctOptions(
  invoices: InvoiceSummary[],
  id: (invoice: InvoiceSummary) => string | null,
  name: (invoice: InvoiceSummary) => string | null,
  fallback: string,
): FilterOption[] {
  const seen = new Map<string, string>();
  for (const invoice of invoices) {
    const key = id(invoice);
    if (key !== null && !seen.has(key)) seen.set(key, name(invoice) ?? fallback);
  }
  return [...seen.entries()]
    .map(([optionId, optionName]) => ({ id: optionId, name: optionName }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

export function branchOptions(invoices: InvoiceSummary[]): FilterOption[] {
  return distinctOptions(
    invoices,
    (invoice) => invoice.branch_id,
    (invoice) => invoice.branch_name,
    "Unnamed branch",
  );
}

export function supplierOptions(invoices: InvoiceSummary[]): FilterOption[] {
  return distinctOptions(
    invoices,
    (invoice) => invoice.supplier_id,
    (invoice) => invoice.supplier_name,
    "Unnamed supplier",
  );
}
