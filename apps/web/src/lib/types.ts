/**
 * C6 contract types, mirroring the wire shapes the implemented API serves
 * (apps/api src/faida_api/api.py `_invoice_summary` / `_invoice_detail` /
 * `supplier_item_prices`, with checks and confidence persisted by
 * extraction/validate.py + pipeline.py). tests/test_api.py pins these shapes;
 * this file mirrors those assertions, field for field.
 *
 * Money is a string end to end. The API serializes Decimal values as strings
 * ("745.76", never a JSON number); this app renders them verbatim (padded to
 * two decimals by string ops only) and never parses them to a float. The one
 * sanctioned parse is geometry: scaling a sparkline's y-axis.
 */

export type CheckStatus = "passed" | "failed" | "indeterminate";

export type FieldStatus = "green" | "amber";

export type InvoiceStatus = "draft" | "awaiting_confirm" | "confirmed" | "needs_review";

export type PaymentKind = "credit" | "cash";

export type DocumentSource = "whatsapp" | "upload" | "manual";

/** C1 document machine: received -> processing -> extracted | failed, plus
 * confirmed once the invoice is confirmed. */
export type DocumentStatus = "received" | "processing" | "extracted" | "confirmed" | "failed";

export type DocumentClassification = "invoice" | "z_report" | "other";

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

/**
 * C8 origins: how a stored value got there. `extracted` and `repaired` are
 * values a camera saw and the arithmetic could check; the rest a person
 * asserted. Neither is worse - `reconstructed` is the right answer when the
 * totals block was off the edge of the photo - but only the first pair can be
 * checked against the image beside it, which is what the screen must not blur.
 */
export type FieldOrigin =
  | "extracted"
  | "repaired"
  | "corrected_chat"
  | "corrected_screen"
  | "reconstructed"
  | "manual";

export interface FieldSource {
  origin: FieldOrigin;
  /** Free text until M7 brings real accounts: "whatsapp:+9715...", "console". */
  actor: string;
  /** ISO datetime. */
  at: string;
}

/**
 * invoices.provenance: field path -> where that value came from. Flat keys,
 * "total" and "lines.3.qty", matching faida_api/provenance.py. Empty for rows
 * that predate C8 (the seeded demo data), which reads as "not recorded".
 */
export type Provenance = Record<string, FieldSource>;

/** One row of GET /api/invoices (the list envelope is {"invoices": [...]}). */
export interface InvoiceSummary {
  id: string;
  supplier_name: string | null;
  supplier_id: string | null;
  invoice_no: string | null;
  /** ISO date, e.g. "2026-08-21". */
  invoice_date: string | null;
  currency: string;
  total: string | null;
  status: InvoiceStatus;
  /** ISO datetime of the invoice row's creation, e.g. "2026-08-21T09:42:00+00:00". */
  created_at: string;
  branch_id: string | null;
  branch_name: string | null;
  document_id: string;
}

/** One line of the detail payload. No id on the wire - position is the key. */
export interface InvoiceLine {
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

/** The document block inside the detail payload. */
export interface InvoiceDocument {
  id: string;
  status: DocumentStatus;
  classification: DocumentClassification | null;
  source: DocumentSource;
  created_at: string | null;
}

/**
 * GET /api/invoices/{id}: the summary fields plus totals, confidence, lines,
 * the document, and a short-lived signed image URL (~600 s TTL - refetch the
 * detail when a long-open image starts 403ing). PATCH and confirm return this
 * same payload, so the screen never refetches after a write.
 */
export interface InvoiceDetail extends InvoiceSummary {
  subtotal: string | null;
  tax: string | null;
  payment_kind: PaymentKind | null;
  confidence: Confidence;
  provenance: Provenance;
  confirmed_at: string | null;
  lines: InvoiceLine[];
  document: InvoiceDocument | null;
  image_url: string | null;
}

export interface InvoiceFilters {
  status?: InvoiceStatus;
  branch_id?: string;
  supplier_id?: string;
}

export type CorrectionField =
  | "qty"
  | "unit_price"
  | "line_total"
  | "name"
  | "subtotal"
  | "tax"
  | "total";

/**
 * One field fix for PATCH /api/invoices/{id}/fields, exactly the chat
 * grammar's field set (api.py Correction). line_index (0-based) targets a
 * line field; null targets the totals block (subtotal/tax/total). Values are
 * strings: unsigned decimals for numbers ("16", "4.50" - no sign, no
 * exponent), free text for "name". A field can never be cleared to null.
 */
export interface Correction {
  line_index: number | null;
  field: CorrectionField;
  value: string;
}

/** PATCH body: {"corrections": [...]}, at least one. Returns InvoiceDetail. */
export interface FieldCorrections {
  corrections: Correction[];
}

/**
 * One typed line for POST /api/invoices/manual. Numbers are unsigned decimal
 * strings, the same convention corrections use; omitted fields were simply
 * not on the paper.
 */
export interface ManualLineInput {
  raw_name: string;
  qty?: string;
  unit?: string;
  pack_size?: string;
  unit_price?: string;
  line_total?: string;
}

/**
 * POST /api/invoices/manual body (WP-34, the sanctioned C6 extension): the
 * vision-outage fallback's typed path. Everything optional except at least
 * one line; the server runs the same deterministic checks the pipeline runs
 * and answers 201 with the standard InvoiceDetail. No AI is involved.
 */
export interface ManualInvoiceInput {
  branch_id?: string;
  supplier_name?: string;
  invoice_no?: string;
  /** ISO date, "YYYY-MM-DD". */
  invoice_date?: string;
  currency?: string;
  payment_kind?: PaymentKind;
  subtotal?: string;
  tax?: string;
  total?: string;
  lines: ManualLineInput[];
}

/** One confirmed price observation (supplier_item_prices row). */
export interface PricePoint {
  price: string;
  /** ISO datetime the price was observed. */
  observed_at: string;
  invoice_id: string | null;
}

/**
 * GET /api/supplier-items/{id}/prices: the item header plus confirmed
 * observations ascending by observed_at (the sparkline draws left to right).
 */
export interface PriceHistory {
  id: string;
  canonical_name: string;
  unit: string | null;
  pack_size: string | null;
  last_price: string | null;
  prev_price: string | null;
  prices: PricePoint[];
}

/** POST /api/documents response. */
export interface UploadResult {
  document_id: string;
}

/* --- raw materials (M5) ---------------------------------------------------
 *
 * The mapping layer's wire shapes (apps/api src/faida_api/api.py, pinned by
 * tests/test_raw_materials.py). Costs are strings like every other money
 * value here: `per_base` is AED per gram / millilitre / piece, `per_display`
 * the same number per kilo / litre / piece because that is how a person says
 * it. Both are computed in Python - this app never multiplies money.
 */

/** The base unit a material is measured in: g (mass), ml (volume), pc (count). */
export type BaseUnit = "g" | "ml" | "pc";

/** Why a pack has no cost per base unit. Each is a different fix. */
export type CostBlocked = "no_price" | "unknown_pack" | "ambiguous_pack";

/** How the cost was derived - a stated conversion and a printed pack size are
 * both correct and are not the same claim. */
export type CostBasis = "conversion" | "unit" | "pack_size" | "item_name";

/** C9: a derived number is never greener than its worst input. */
export type CostQuality = "verified" | "estimated";

/** One input a person asserted rather than a camera saw. */
export interface EstimatedBecause {
  field: string;
  origin: string;
  actor: string;
  at: string;
  invoice_no: string | null;
}

export interface UnitCost {
  per_base: string;
  base_unit: BaseUnit;
  per_display: string;
  display_unit: "kg" | "l" | "pc";
  basis: CostBasis;
  pack_display: string;
}

/** A material's cost: its most recent purchase, and which pack that was. */
export interface IngredientCost extends UnitCost {
  quality: CostQuality;
  estimated_because: EstimatedBecause[];
  as_of: string;
  supplier_item_id: string;
  supplier_name: string | null;
  pack_name: string;
}

export interface Conversion {
  base_quantity: string;
  base_unit: BaseUnit;
  note: string | null;
  actor: string;
  created_at: string;
}

/** One purchasable pack: a supplier_items row, costed. */
export interface Pack {
  id: string;
  canonical_name: string;
  unit: string | null;
  pack_size: string | null;
  supplier_id: string | null;
  supplier_name: string | null;
  last_price: string | null;
  last_price_at: string | null;
  cost: UnitCost | null;
  blocked: CostBlocked | null;
  /** null when there is no cost to qualify. */
  quality: CostQuality | null;
  estimated_because: EstimatedBecause[];
  conversion: Conversion | null;
}

/** A near-certain suggestion, with the evidence for it. */
export interface IngredientProposal {
  ingredient_id: string;
  name: string;
  score: number;
  via: "ingredient" | "sibling";
  evidence: string;
}

/** A queue row: a pack with nothing to cook with yet. */
export interface QueueItem extends Pack {
  spend: string;
  invoices: number;
  proposal: IngredientProposal | null;
}

export interface Ingredient {
  id: string;
  name: string;
  base_unit: BaseUnit;
  category: string | null;
}

export interface IngredientSummary extends Ingredient {
  packs: number;
  blocked_packs: number;
  cost: IngredientCost | null;
}

/** One confirmed price observation, carrying the invoice it was read off. */
export interface IngredientPrice {
  price: string;
  observed_at: string;
  supplier_item_id: string;
  canonical_name: string;
  supplier_name: string | null;
  invoice_id: string | null;
  invoice_no: string | null;
  invoice_date: string | null;
  document_id: string | null;
}

export interface IngredientDetail extends Ingredient {
  cost: IngredientCost | null;
  packs: Pack[];
  prices: IngredientPrice[];
}

export interface MapItemResult {
  item: Pack;
  ingredient: Ingredient;
}

/** Create a material, or name an existing one - the queue does both. */
export interface MapItemInput {
  ingredient_id?: string;
  name?: string;
  base_unit?: BaseUnit;
  category?: string | null;
}

export interface ConversionInput {
  base_quantity: string;
  base_unit: BaseUnit;
  note?: string | null;
}
