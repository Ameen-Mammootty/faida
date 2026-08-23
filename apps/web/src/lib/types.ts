/**
 * C6 contract types (plan.md section 7.2), mirroring the shapes the API
 * persists in apps/api (extraction/validate.py LineCheck / DocumentCheck and
 * pipeline.py's confidence + line dumps).
 *
 * Money is a string end to end. The API serializes Decimal values as strings;
 * this app renders them verbatim (padded to two decimals by string ops only)
 * and never parses them to a float.
 */

export type CheckStatus = "passed" | "failed" | "indeterminate";

export type FieldStatus = "green" | "amber";

export type InvoiceStatus = "draft" | "awaiting_confirm" | "confirmed" | "needs_review";

export type PaymentKind = "credit" | "cash";

export type DocumentSource = "whatsapp" | "upload" | "manual";

/** Persisted per-line check: validate.py LineCheck.model_dump(mode="json"). */
export interface LineCheck {
  line_index: number;
  arith: CheckStatus;
  /** qty x unit_price, set only when arith failed. Money string. */
  expected: string | null;
  /** The extracted line_total, set only when arith failed. Money string. */
  extracted: string | null;
  /** true = snapped to a known supplier item, false = did not snap, null = snapping unavailable. */
  snapped: boolean | null;
  status: FieldStatus;
}

/** Persisted totals-block check: validate.py DocumentCheck.model_dump(mode="json"). */
export interface DocumentCheck {
  /** Line sum + tax vs printed total. */
  arith: CheckStatus;
  /** Extracted subtotal vs line sum, when a subtotal was extracted. */
  subtotal_check: CheckStatus;
  line_sum: string | null;
  /** line_sum + tax, set only when arith failed. */
  expected: string | null;
  /** The extracted total, set only when arith failed. */
  extracted: string | null;
  notes: string[];
  status: FieldStatus;
}

/** invoices.confidence: pipeline.py's derived-confidence dump. */
export interface Confidence {
  document: DocumentCheck;
  lines: FieldStatus[];
}

export interface InvoiceLine {
  id: string;
  position: number;
  raw_name: string;
  supplier_item_id: string | null;
  qty: string | null;
  unit: string | null;
  pack_size: string | null;
  unit_price: string | null;
  line_total: string | null;
  checks: LineCheck;
}

export interface InvoiceSummary {
  id: string;
  document_id: string;
  branch_id: string | null;
  branch_name: string | null;
  supplier_id: string | null;
  supplier_name: string | null;
  invoice_no: string | null;
  /** ISO date, e.g. "2026-08-21". */
  invoice_date: string | null;
  currency: string;
  total: string | null;
  payment_kind: PaymentKind | null;
  status: InvoiceStatus;
  /** ISO datetime of the document's arrival. */
  created_at: string;
}

export interface InvoiceDetail extends InvoiceSummary {
  subtotal: string | null;
  tax: string | null;
  /** Signed URL for the stored original; null for manual entries with no photo. */
  image_url: string | null;
  source: DocumentSource;
  lines: InvoiceLine[];
  confidence: Confidence;
}

export interface InvoiceFilters {
  status?: InvoiceStatus;
  branch_id?: string;
  supplier_id?: string;
}

/** One line's editable fields; strings pass through verbatim. */
export interface LineFieldPatch {
  position: number;
  raw_name?: string;
  qty?: string | null;
  unit_price?: string | null;
  line_total?: string | null;
}

/** PATCH /api/invoices/{id}/fields body. The API re-validates and returns the new detail. */
export interface FieldPatch {
  supplier_name?: string;
  invoice_no?: string;
  invoice_date?: string;
  subtotal?: string | null;
  tax?: string | null;
  total?: string | null;
  lines?: LineFieldPatch[];
}

export interface PricePoint {
  price: string;
  /** ISO datetime the price was observed (confirmed invoice date). */
  observed_at: string;
  invoice_id: string | null;
}

/** GET /api/supplier-items/{id}/prices response. */
export interface PriceHistory {
  supplier_item_id: string;
  canonical_name: string;
  unit: string | null;
  pack_size: string | null;
  prices: PricePoint[];
}

/** POST /api/documents response. */
export interface UploadResult {
  document_id: string;
}
