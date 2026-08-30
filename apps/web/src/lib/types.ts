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

/**
 * M5 WP-53: what one gram of a line cost.
 *
 * The quality vocabulary is PRD 24's, one word short: there is no `verified`.
 * C4's arithmetic proves qty x unit_price = line_total, so two other numbers
 * on the page corroborate the unit price - but pack size appears in no
 * identity at all. A supplier prints 25kg, the model reads 2.5kg, every check
 * still passes, and the cost is ten times too high. A green badge on that is
 * the failure this whole layer is built to avoid, so the screen must never
 * render one.
 */
export type CostQuality = "reliable_with_limitations" | "estimated";

/** Where the amount the price was divided by was read. */
export type CostPackSource = "pack_size" | "raw_name" | "unit" | "override";

/** Why a line has no cost. Each is a different sentence and a different fix. */
export type CostBlocker =
  | "foreign_currency"
  | "missing_unit_price"
  | "missing_quantity"
  | "zero_pack"
  | "bare_container"
  | "unparseable_pack";

/**
 * Either a cost or the reason there is none - `blocked` says which. The whole
 * field is null when the question has not been asked: costs are frozen at
 * confirm, and a delivery charge never gets one.
 */
export interface LineCost {
  /** AED per gram / millilitre / piece, eight decimals. Money string. */
  per_base_unit: string | null;
  base_unit: BaseUnit | null;
  /** The same cost per kilo / per litre / each, two decimals. Money string. */
  per_display_unit: string | null;
  display_unit: string | null;
  quality: CostQuality | null;
  /** C8 field paths a person asserted that this cost leans on (C9). */
  asserted: string[];
  /** The pack size divided by, exactly as the invoice printed it. */
  pack: string | null;
  pack_source: CostPackSource | null;
  blocked: CostBlocker | null;
  /** Plain English for `blocked`, straight from the API. */
  reason: string | null;
}

/** Stock, or a charge (delivery, cool-box hire) that never becomes an item. */
export type LineKind = "stock_item" | "charge";

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
  line_kind: LineKind;
  checks: LineCheck;
  cost: LineCost | null;
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
  | "pack_size"
  | "subtotal"
  | "tax"
  | "total";

/**
 * One field fix for PATCH /api/invoices/{id}/fields, exactly the chat
 * grammar's field set (api.py Correction). line_index (0-based) targets a
 * line field; null targets the totals block (subtotal/tax/total). Values are
 * strings: unsigned decimals for numbers ("16", "4.50" - no sign, no
 * exponent), free text for "name" and "pack_size". Only "pack_size" can be
 * cleared, and only by value: a blank or placeholder value ("", "-", "n/a";
 * lib/placeholders.ts mirrors the vocabulary) stores null, because "the pack
 * we hold is wrong and I do not know the right one" is a real answer to the
 * one line field no arithmetic can cross-check. Every other field can never
 * be cleared.
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

/**
 * M5 WP-52: raw materials.
 *
 * The catalog fills itself from invoices but is scoped to a supplier, so the
 * same material bought from two suppliers is two `supplier_items` rows with
 * two price histories. An *ingredient* is the culinary concept (milk powder);
 * a *supplier item* is the purchasable pack (Gulf Foods' 2.5 kg sack). One
 * material, many packs (PRD 17-18).
 *
 * The matcher proposes and never decides: a person approves each merge, one
 * keystroke at a time. A wrong merge corrupts the cost of every menu item
 * using that material and there is no photo to check it against, which is why
 * the screen also has to be able to undo one.
 */

/** The dimension a material is measured in: grams, millilitres or pieces. */
export type BaseUnit = "g" | "ml" | "pc";

/**
 * M5 WP-54: one material, one price per kilo - **derived, never stored**.
 *
 * The newest costed line among the packs mapped to this material right now,
 * ranked by printed invoice date with confirm time only as a tie-breaker
 * (PRD 19's "most recent purchase"). Latest, not cheapest and not averaged.
 *
 * There is no `ingredient_costs` table and there is not going to be one: a
 * stored copy would need refreshing on confirm, approve, reject, remap, unmap
 * and pack-size override. Because it is derived, unmapping a wrong merge
 * corrects every figure above it with nothing to rebuild - and the answer
 * carries the invoice line it came from, which is what puts the photo one
 * click away.
 */
export interface MaterialPrice {
  per_base_unit: string | null;
  base_unit: BaseUnit | null;
  /** Per kilo / per litre / each, two decimals. Money string. */
  per_display_unit: string | null;
  display_unit: string | null;
  quality: CostQuality | null;
  asserted: string[];
  pack: string | null;
  pack_source: CostPackSource | null;
  supplier_name: string;
  supplier_item_id: string;
  product_name: string;
  invoice_id: string;
  invoice_line_id: string;
  /** The date this was ranked by: the printed one, or the confirm date. */
  purchased_on: string | null;
  /** The date the invoice actually printed, null when it printed none - so
   * "bought on" and "recorded on" are never confused for each other. */
  invoice_date: string | null;
  /** M6 WP-61 (D11): set when this material's newest confirmed purchase could
   * not be costed. The figure above is real but not current - the quality is
   * already capped at "estimated" by the API - and this names the delivery
   * that is the unanswered question. */
  newer_uncosted: NewerUncosted | null;
}

/** The blocked newer purchase behind a stale-capped price (WP-61, D11). */
export interface NewerUncosted {
  invoice_line_id: string;
  invoice_id: string;
  position: number;
  raw_name: string;
  purchased_on: string | null;
  /** The WP-55 sentence: why that line has no cost. */
  reason: string;
}

/** A purchasable pack that has been mapped onto a material. */
export interface MappedPack {
  id: string;
  canonical_name: string;
  unit: string | null;
  pack_size: string | null;
  supplier_name: string;
  /** Ex-VAT unit price, C4 net-canonical. Money string. */
  last_price: string | null;
  last_price_at: string | null;
  /** How much is in one of these, said by a person because the invoice never
   * did (WP-55). Kept visible so the sentence does not disappear the moment it
   * takes effect. */
  pack_size_override: string | null;
  /** This pack's own newest cost per kilo - what makes two suppliers'
   * different pack sizes comparable at all. Null until one is confirmed. */
  cost: MaterialPrice | null;
}

/**
 * M5 WP-55: a confirmed line this layer could not turn into a cost.
 *
 * Derived from the data, not an `issues` table: the fact is already on the
 * line, and asking the same function that refused says which of six things
 * went wrong. Grouped by product, because a carton bought twelve times is one
 * question a person answers once.
 */
export interface BlockedCost {
  id: string;
  supplier_item_id: string | null;
  product_name: string;
  supplier_name: string | null;
  pack_size: string | null;
  unit: string | null;
  pack_size_override: string | null;
  ingredient_id: string | null;
  ingredient_name: string | null;
  blocked: CostBlocker;
  /** Plain English, straight from the API. */
  reason: string;
  /** True only for a pack problem: no conversion supplies a price or a
   * quantity the invoice never printed, so no box is offered for those. */
  can_override: boolean;
  line_count: number;
  /** Money spent on the blocked lines. Money string. */
  spend: string;
  /** The newest example, for the drill-through to the photo. */
  invoice_id: string;
  invoice_line_id: string;
  position: number;
  invoice_date: string | null;
}

/** What answering the question returns: how many lines it costed. */
export interface PackSizeOverrideResult {
  supplier_item_id: string;
  pack_size: string;
  lines_costed: number;
}

export interface Ingredient {
  id: string;
  name: string;
  base_unit: BaseUnit;
  pack_count: number;
  /** The one price per kilo, or null until something has been confirmed. */
  price: MaterialPrice | null;
  packs: MappedPack[];
}

/** A material the matcher suggests for a pack. Ranked, never applied. */
export interface IngredientProposal {
  id: string;
  name: string;
  base_unit: BaseUnit;
}

/** One row of the mapping queue: a pack with no material yet. */
export interface UnmappedSupplierItem {
  id: string;
  canonical_name: string;
  unit: string | null;
  pack_size: string | null;
  supplier_id: string;
  supplier_name: string;
  /** Money spent on this pack across confirmed invoices only. Money string. */
  spend: string;
  line_count: number;
  /** What the pack measures in, when it can be read. Null for a bare carton. */
  base_unit: BaseUnit | null;
  proposals: IngredientProposal[];
}

/**
 * POST body for approving a merge: an existing material's id, or a name to
 * create one under. `base_unit` is inferred from the pack when it can be, and
 * required when it cannot ("1 ctn" says nothing about what is inside it).
 */
export interface IngredientMappingInput {
  ingredient_id?: string;
  name?: string;
  base_unit?: BaseUnit;
}

export interface MappingResult {
  supplier_item_id: string;
  ingredient: IngredientProposal | null;
}

/**
 * A rejection changes no mapping - it records that a person said this pack is
 * not that material, which is what stops the queue offering it again. Its own
 * shape rather than a MappingResult, because answering "ingredient: null"
 * would read as "this pack is now unmapped", which is a different event.
 */
export interface RejectionResult {
  supplier_item_id: string;
  rejected_ingredient_id: string;
}

/**
 * M6 WP-61/62: the menu, costed.
 *
 * A plate cost is **derived on every read** from the same material prices the
 * materials screen shows - nothing is stored, so confirming a cheaper milk
 * invoice moves every karak on the next load with nothing to invalidate.
 *
 * The quality vocabulary is the cost one plus "incomplete", and the word
 * "verified" still does not exist. An incomplete item carries **no numbers at
 * all** - only its list of what is missing - because a half-costed dish
 * showing a fat margin is a lie the ranking would repeat.
 *
 * The word on every screen is *margin*: labour, rent and waste are absent, so
 * it is never "profit", and it is never "food cost %" (plan.md section 3).
 */
export type PlateQuality = "reliable_with_limitations" | "estimated" | "incomplete";

/** The whole answer for one menu item. Numbers are null iff incomplete. */
export interface Plate {
  quality: PlateQuality;
  /** What stands between this item and a margin, in plain words. */
  missing: string[];
  /** Money strings, three decimals. */
  cost_per_portion: string | null;
  /** The margin base: selling price net of VAT. */
  net_price: string | null;
  /** The VAT rate inside the menu price ("0.05"), null when unknown - the
   * screen says the basis in words either way. */
  vat_rate: string | null;
  /** Margin in AED per portion - what the ranking orders by. */
  margin: string | null;
  /** Margin as a percentage of the net price, one decimal ("64.1"). */
  margin_pct: string | null;
}

/** The current recipe version, as the list endpoint summarizes it. */
export interface MenuRecipeSummary {
  id: string;
  version: number;
  /** The batch divisor: one pot makes this many portions. Decimal string. */
  yield_portions: string;
  /** Display text only ("cups"); nothing ever converts against it. */
  yield_label: string | null;
  component_count: number;
}

/** One row of GET /api/menu-items (envelope {"menu_items": [...]}). */
export interface MenuItemSummary {
  id: string;
  name: string;
  /** As the owner states it, VAT inside it. Money string. */
  selling_price: string;
  archived_at: string | null;
  created_at: string;
  plate: Plate;
  recipe: MenuRecipeSummary | null;
}

/** One component's cost and its full forensics: the material price it
 * multiplied, down to the invoice line and the photo behind it. */
export interface MenuComponentCost {
  /** This component's share of one portion's cost. Money string. */
  amount: string;
  quality: CostQuality;
  price: MaterialPrice;
}

/** One line of the current recipe, in the detail payload. */
export interface MenuComponent {
  position: number;
  ingredient_id: string;
  ingredient_name: string;
  base_unit: BaseUnit;
  /** The consultant's converted number. Decimal string. */
  qty: string;
  unit: string;
  /** The recipe card's own words ("1 cup"), kept beside the conversion -
   * the only audit a typed quantity will ever have. */
  source_text: string | null;
  /** Exactly one of these is set. */
  cost: MenuComponentCost | null;
  missing: string | null;
}

export interface MenuRecipeDetail {
  id: string;
  version: number;
  yield_portions: string;
  yield_label: string | null;
  created_at: string | null;
  components: MenuComponent[];
}

/** GET /api/menu-items/{id}: the drill behind one ranked row. */
export interface MenuItemDetail {
  id: string;
  name: string;
  selling_price: string;
  archived_at: string | null;
  created_at: string;
  plate: Plate;
  recipe: MenuRecipeDetail | null;
}
