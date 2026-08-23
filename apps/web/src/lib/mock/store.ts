/**
 * In-memory mock of the C6 API surface, served through the same client
 * interface as the real thing and answering with byte-identical shapes
 * (apps/api src/faida_api/api.py, pinned by tests/test_api.py) - components
 * cannot tell the modes apart. Lives in module memory, so edits and confirms
 * persist across screens for the length of the browser session and reset on
 * reload - exactly what a demo without the backend needs.
 *
 * Error behavior mirrors the real endpoints too: the same status codes with
 * the same detail messages, thrown as ApiError exactly like the real client
 * surfaces them.
 */

import { FIXTURES, PRICE_HISTORIES, type Fixture } from "./fixtures";
import { checkDocument, checkLine, deriveConfidence } from "./validate";
import { ApiError } from "../errors";
import type {
  Correction,
  DocumentStatus,
  InvoiceDetail,
  InvoiceFilters,
  InvoiceLine,
  InvoiceStatus,
  InvoiceSummary,
  PriceHistory,
  UploadResult,
} from "../types";

const HEADER_FIELDS = new Set(["subtotal", "tax", "total"]);
const EDITABLE_STATUSES = new Set<InvoiceStatus>(["awaiting_confirm", "needs_review"]);

/** C1: the document status implied by the invoice status. */
function documentStatus(invoiceStatus: InvoiceStatus): DocumentStatus {
  return invoiceStatus === "confirmed" ? "confirmed" : "extracted";
}

function buildDetail(fixture: Fixture): InvoiceDetail {
  const lineChecks = fixture.lines.map((line, index) => checkLine(index, line));
  const document = checkDocument(fixture.lines, lineChecks, fixture);
  const lines: InvoiceLine[] = fixture.lines.map((line, index) => ({
    position: index,
    raw_name: line.raw_name,
    supplier_item_id: line.supplier_item_id,
    qty: line.qty,
    unit: line.unit,
    pack_size: line.pack_size,
    unit_price: line.unit_price,
    line_total: line.line_total,
    checks: lineChecks[index],
  }));
  return {
    id: fixture.id,
    supplier_name: fixture.supplier_name,
    supplier_id: fixture.supplier_id,
    invoice_no: fixture.invoice_no,
    invoice_date: fixture.invoice_date,
    currency: fixture.currency,
    total: fixture.total,
    status: fixture.status,
    created_at: fixture.created_at,
    branch_id: fixture.branch_id,
    branch_name: fixture.branch_name,
    document_id: fixture.document_id,
    subtotal: fixture.subtotal,
    tax: fixture.tax,
    payment_kind: fixture.payment_kind,
    confidence: deriveConfidence(document, lineChecks),
    confirmed_at: null,
    lines,
    document: {
      id: fixture.document_id,
      status: documentStatus(fixture.status),
      classification: "invoice",
      source: fixture.source,
      created_at: fixture.created_at,
    },
    image_url: fixture.image_url,
  };
}

const invoices = new Map<string, InvoiceDetail>(
  FIXTURES.map((fixture) => [fixture.id, buildDetail(fixture)]),
);

const priceHistories = new Map<string, PriceHistory>(
  Object.entries(PRICE_HISTORIES).map(([id, history]) => [id, structuredClone(history)]),
);

let uploadCounter = 0;

const LATENCY_MS = 160;

function clone<T>(value: T): T {
  return structuredClone(value);
}

async function respond<T>(value: T): Promise<T> {
  await new Promise((resolve) => setTimeout(resolve, LATENCY_MS));
  return clone(value);
}

/** Python datetime.isoformat() form: offset suffix, never "Z". */
function nowIso(): string {
  return new Date().toISOString().replace("Z", "+00:00");
}

function summarize(detail: InvoiceDetail): InvoiceSummary {
  return {
    id: detail.id,
    supplier_name: detail.supplier_name,
    supplier_id: detail.supplier_id,
    invoice_no: detail.invoice_no,
    invoice_date: detail.invoice_date,
    currency: detail.currency,
    total: detail.total,
    status: detail.status,
    created_at: detail.created_at,
    branch_id: detail.branch_id,
    branch_name: detail.branch_name,
    document_id: detail.document_id,
  };
}

function getOrThrow(id: string): InvoiceDetail {
  const detail = invoices.get(id);
  if (!detail) throw new ApiError(404, "invoice not found");
  return detail;
}

/** Re-run the deterministic checks after an edit, the way the server does. */
function revalidate(detail: InvoiceDetail): InvoiceDetail {
  const lineChecks = detail.lines.map((line, index) =>
    checkLine(index, { ...line, snapped: line.checks.snapped }),
  );
  const document = checkDocument(detail.lines, lineChecks, detail);
  return {
    ...detail,
    lines: detail.lines.map((line, index) => ({ ...line, checks: lineChecks[index] })),
    confidence: deriveConfidence(document, lineChecks),
  };
}

export async function mockListInvoices(filters: InvoiceFilters = {}): Promise<InvoiceSummary[]> {
  const all = [...invoices.values()]
    .filter((inv) => !filters.status || inv.status === filters.status)
    .filter((inv) => !filters.branch_id || inv.branch_id === filters.branch_id)
    .filter((inv) => !filters.supplier_id || inv.supplier_id === filters.supplier_id)
    .sort((a, b) => {
      // Newest first, exactly the server's order: created_at desc, id desc.
      if (a.created_at !== b.created_at) return a.created_at < b.created_at ? 1 : -1;
      return a.id < b.id ? 1 : -1;
    });
  return respond(all.map(summarize));
}

export async function mockGetInvoice(id: string): Promise<InvoiceDetail> {
  return respond(getOrThrow(id));
}

/** confirm.py _parse_number: strip trailing sentence punctuation, then accept
 * unsigned decimals only - no sign, no exponent, no NaN. */
function parseNumberValue(value: string): string | null {
  const text = value.trim().replace(/[.!?]+$/, "");
  return /^\d+(\.\d+)?$/.test(text) ? text : null;
}

type Edit =
  | {
      kind: "line_field";
      line_index: number;
      field: "qty" | "unit_price" | "line_total";
      value: string;
    }
  | { kind: "line_name"; line_index: number; name: string }
  | { kind: "totals"; field: "subtotal" | "tax" | "total"; value: string };

/** api.py _to_edit, message for message. */
function toEdit(correction: Correction): Edit {
  const { field, line_index: lineIndex, value } = correction;
  if (HEADER_FIELDS.has(field)) {
    if (lineIndex !== null) {
      throw new ApiError(
        422,
        `field '${field}' is a header field; line_index must be null ` +
          "(line totals are field 'line_total')",
      );
    }
    return {
      kind: "totals",
      field: field as "subtotal" | "tax" | "total",
      value: numericValue(correction),
    };
  }
  if (lineIndex === null || lineIndex < 0) {
    throw new ApiError(422, `field '${field}' needs a line_index (0-based)`);
  }
  if (field === "name") {
    const name = value.trim();
    if (!name) throw new ApiError(422, "a line name cannot be empty");
    return { kind: "line_name", line_index: lineIndex, name };
  }
  return {
    kind: "line_field",
    line_index: lineIndex,
    field: field as "qty" | "unit_price" | "line_total",
    value: numericValue(correction),
  };
}

function numericValue(correction: Correction): string {
  const value = parseNumberValue(correction.value);
  if (value === null) {
    throw new ApiError(
      422,
      `'${correction.value}' is not a valid ${correction.field}: ` +
        'send an unsigned decimal string like "16" or "4.50"',
    );
  }
  return value;
}

export async function mockPatchInvoiceFields(
  id: string,
  corrections: Correction[],
): Promise<InvoiceDetail> {
  const current = getOrThrow(id);
  if (!EDITABLE_STATUSES.has(current.status)) {
    throw new ApiError(
      409,
      `invoice is ${current.status}; only awaiting_confirm or needs_review invoices can be edited`,
    );
  }
  if (corrections.length === 0) {
    // The real API rejects an empty corrections list in body validation.
    throw new ApiError(422, "The API returned 422.");
  }

  const edits = corrections.map(toEdit);
  for (const edit of edits) {
    if (edit.kind !== "totals" && edit.line_index >= current.lines.length) {
      throw new ApiError(
        422,
        `line_index ${edit.line_index} out of range: ` +
          `this invoice has ${current.lines.length} lines`,
      );
    }
  }

  const next: InvoiceDetail = clone(current);
  for (const edit of edits) {
    if (edit.kind === "totals") {
      next[edit.field] = edit.value;
    } else if (edit.kind === "line_name") {
      next.lines[edit.line_index].raw_name = edit.name;
    } else {
      next.lines[edit.line_index][edit.field] = edit.value;
    }
  }
  const revalidated = revalidate(next);
  invoices.set(id, revalidated);
  return respond(revalidated);
}

/** db.record_confirmed_prices: append each line's confirmed price (idempotent
 * per invoice) and shift prev/last only when the price actually changed. */
function recordConfirmedPrices(detail: InvoiceDetail): void {
  for (const line of detail.lines) {
    if (line.supplier_item_id === null || line.qty === null || line.unit_price === null) continue;
    const history = priceHistories.get(line.supplier_item_id);
    if (!history) continue;
    if (history.prices.some((point) => point.invoice_id === detail.id)) continue;
    history.prices.push({
      price: line.unit_price,
      observed_at: nowIso(),
      invoice_id: detail.id,
    });
    if (history.last_price !== line.unit_price) {
      history.prev_price = history.last_price;
      history.last_price = line.unit_price;
    }
  }
}

export async function mockConfirmInvoice(id: string): Promise<InvoiceDetail> {
  const current = getOrThrow(id);
  if (!EDITABLE_STATUSES.has(current.status)) {
    throw new ApiError(409, `invoice is ${current.status}; cannot confirm`);
  }
  const confirmed: InvoiceDetail = {
    ...clone(current),
    status: "confirmed",
    confirmed_at: nowIso(),
  };
  if (confirmed.document) confirmed.document.status = "confirmed";
  invoices.set(id, confirmed);
  recordConfirmedPrices(confirmed);
  return respond(confirmed);
}

export async function mockUploadDocument(file: File): Promise<UploadResult> {
  void file;
  uploadCounter += 1;
  return respond({ document_id: `doc-upload-${uploadCounter}` });
}

export async function mockGetSupplierItemPrices(supplierItemId: string): Promise<PriceHistory> {
  const history = priceHistories.get(supplierItemId);
  if (!history) throw new ApiError(404, "supplier item not found");
  return respond(history);
}
