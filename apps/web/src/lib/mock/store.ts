/**
 * In-memory mock of the C6 API surface, served through the same client
 * interface as the real thing. Lives in module memory, so edits and confirms
 * persist across screens for the length of the browser session and reset on
 * reload - exactly what a demo without the backend needs.
 */

import { FIXTURES, PRICE_HISTORIES, type Fixture } from "./fixtures";
import { checkDocument, checkLine, deriveConfidence } from "./validate";
import { ApiError } from "../errors";
import type {
  FieldPatch,
  InvoiceDetail,
  InvoiceFilters,
  InvoiceLine,
  InvoiceSummary,
  PriceHistory,
  UploadResult,
} from "../types";

function buildDetail(fixture: Fixture): InvoiceDetail {
  const lineChecks = fixture.lines.map((line, index) => checkLine(index, line));
  const document = checkDocument(fixture.lines, lineChecks, fixture);
  const lines: InvoiceLine[] = fixture.lines.map((line, index) => ({
    id: `${fixture.id}-line-${index}`,
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
    document_id: fixture.document_id,
    branch_id: fixture.branch_id,
    branch_name: fixture.branch_name,
    supplier_id: fixture.supplier_id,
    supplier_name: fixture.supplier_name,
    invoice_no: fixture.invoice_no,
    invoice_date: fixture.invoice_date,
    currency: fixture.currency,
    subtotal: fixture.subtotal,
    tax: fixture.tax,
    total: fixture.total,
    payment_kind: fixture.payment_kind,
    status: fixture.status,
    source: fixture.source,
    image_url: fixture.image_url,
    created_at: fixture.created_at,
    lines,
    confidence: deriveConfidence(document, lineChecks),
  };
}

const invoices = new Map<string, InvoiceDetail>(
  FIXTURES.map((fixture) => [fixture.id, buildDetail(fixture)]),
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

function summarize(detail: InvoiceDetail): InvoiceSummary {
  return {
    id: detail.id,
    document_id: detail.document_id,
    branch_id: detail.branch_id,
    branch_name: detail.branch_name,
    supplier_id: detail.supplier_id,
    supplier_name: detail.supplier_name,
    invoice_no: detail.invoice_no,
    invoice_date: detail.invoice_date,
    currency: detail.currency,
    total: detail.total,
    payment_kind: detail.payment_kind,
    status: detail.status,
    created_at: detail.created_at,
  };
}

function getOrThrow(id: string): InvoiceDetail {
  const detail = invoices.get(id);
  if (!detail) throw new ApiError(404, `No invoice with id ${id}`);
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
    .sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
  return respond(all.map(summarize));
}

export async function mockGetInvoice(id: string): Promise<InvoiceDetail> {
  return respond(getOrThrow(id));
}

export async function mockPatchInvoiceFields(
  id: string,
  patch: FieldPatch,
): Promise<InvoiceDetail> {
  const current = getOrThrow(id);
  if (current.status === "confirmed") {
    throw new ApiError(409, "This invoice is already confirmed and can no longer be edited.");
  }
  const next: InvoiceDetail = clone(current);
  if (patch.supplier_name !== undefined) next.supplier_name = patch.supplier_name;
  if (patch.invoice_no !== undefined) next.invoice_no = patch.invoice_no;
  if (patch.invoice_date !== undefined) next.invoice_date = patch.invoice_date;
  if (patch.subtotal !== undefined) next.subtotal = patch.subtotal;
  if (patch.tax !== undefined) next.tax = patch.tax;
  if (patch.total !== undefined) next.total = patch.total;
  for (const linePatch of patch.lines ?? []) {
    const line = next.lines.find((candidate) => candidate.position === linePatch.position);
    if (!line) {
      throw new ApiError(422, `This invoice has no line ${linePatch.position + 1}.`);
    }
    if (linePatch.raw_name !== undefined) line.raw_name = linePatch.raw_name;
    if (linePatch.qty !== undefined) line.qty = linePatch.qty;
    if (linePatch.unit_price !== undefined) line.unit_price = linePatch.unit_price;
    if (linePatch.line_total !== undefined) line.line_total = linePatch.line_total;
  }
  const revalidated = revalidate(next);
  invoices.set(id, revalidated);
  return respond(revalidated);
}

export async function mockConfirmInvoice(id: string): Promise<InvoiceDetail> {
  const current = getOrThrow(id);
  if (current.status === "confirmed") return respond(current);
  const confirmed: InvoiceDetail = { ...clone(current), status: "confirmed" };
  invoices.set(id, confirmed);
  return respond(confirmed);
}

export async function mockUploadDocument(file: File): Promise<UploadResult> {
  void file;
  uploadCounter += 1;
  return respond({ document_id: `doc-upload-${uploadCounter}` });
}

export async function mockGetSupplierItemPrices(supplierItemId: string): Promise<PriceHistory> {
  const history = PRICE_HISTORIES[supplierItemId];
  if (history) return respond(history);
  return respond({
    supplier_item_id: supplierItemId,
    canonical_name: "",
    unit: null,
    pack_size: null,
    prices: [],
  });
}
