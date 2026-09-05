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

export type InvoiceStatus =
  | "draft"
  | "awaiting_confirm"
  | "confirmed"
  | "needs_review"
  /** A WP-44 duplicate hold the reviewer resolved. Terminal, and out of the
   * working list - reachable only by asking for it: /invoices?status=dismissed. */
  | "dismissed";

export type PaymentKind = "credit" | "cash";

export type DocumentSource = "whatsapp" | "upload" | "manual";

/** C1 document machine: received -> processing -> extracted | failed.
 * `extracted` is terminal - migration 0010 took `confirmed` out of the document
 * vocabulary, because both tables claimed it and only application code kept the
 * pair in step. Whether the invoice was confirmed is read from the invoice. */
export type DocumentStatus = "received" | "processing" | "extracted" | "failed";

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
  /** `user:<auth user id>` from the console, `whatsapp:+9715...` from chat (M7). */
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
  /** WP-44: the invoice this one duplicates, or null on an ordinary invoice.
   * A held duplicate is this being set AND the status not being `confirmed` -
   * the WhatsApp reply invites confirming a copy that really is a new invoice,
   * so a confirmed row can carry this too. */
  duplicate_of_invoice_id: string | null;
}

/**
 * One row of the invoice list: the summary plus the duplicated invoice's
 * number, which arrives on the list query's own join.
 *
 * Deliberately NOT on InvoiceSummary, which InvoiceDetail extends - the detail
 * payload has no join on it and does not send this field. Putting it on the
 * shared shape would have the types promise something the wire never carries,
 * which is the same trap the API-side serializer split avoids.
 */
export interface InvoiceListRow extends InvoiceSummary {
  duplicate_of_invoice_no: string | null;
}

/** The paper a held duplicate copies, for the review screen's banner. */
export interface DuplicateOf {
  id: string;
  supplier_name: string | null;
  invoice_no: string | null;
  currency: string;
  total: string | null;
  created_at: string;
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
  /** Set only on a held duplicate; the detail read pays for it only then. */
  duplicate_of: DuplicateOf | null;
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
  | "total"
  | "payment_kind";

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
 * be cleared. "payment_kind" (M7 WP-74) is a header field taking exactly
 * "cash" or "credit", and it is the one correction that moves a status: cash
 * to credit lifts a cash hold back to awaiting_confirm (unless the paper is
 * also a held duplicate), credit to cash holds an awaiting paper.
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
 * POST /api/invoices/{id}/approve body (M7 WP-74, PRD §21): the owner lets a
 * cash paper through, with a reason. Required, non-empty after trimming (422
 * otherwise); the audit row carries it. Returns InvoiceDetail, like confirm.
 */
export interface Approval {
  reason: string;
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
  /** The printed line position, for the /invoices/<id>#line-<position>
   * anchor - the drill lands on the row itself. */
  position: number;
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
  /** The menu's own section (Tea Corner, Special Gravy - 0016, design D9).
   * Null when the menu prints none; the screen never invents one. */
  category: string | null;
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
  category: string | null;
  selling_price: string;
  archived_at: string | null;
  created_at: string;
  plate: Plate;
  recipe: MenuRecipeDetail | null;
}

/**
 * M6 WP-64: the batch loader.
 *
 * `POST /api/ingredients` creates a raw material a menu names before any
 * invoice does. It sends the recipe row's own measure word, never a base
 * unit, so which shelf the material sits on is decided by the API's unit
 * dictionary and nowhere else - a browser that guessed "ea" meant pieces
 * would be a second dictionary, and two dictionaries drift.
 */
export interface IngredientCreateInput {
  name: string;
  unit: string;
}

/** One whole recipe as the loader commits it: **one recipe, one transaction**
 * (`POST /api/menu-items/load`). The item is identified by name; its category
 * and selling price travel with it, because the spreadsheet is the single
 * source for those and each goes through the door a person's click uses. */
export interface MenuItemLoadInput {
  name: string;
  category: string | null;
  selling_price: string;
  yield_portions: string;
  yield_label: string | null;
  components: {
    ingredient_id: string;
    qty: string;
    unit: string;
    source_text: string | null;
  }[];
}

/**
 * What the door actually did - the grid restamps its rows from this and never
 * from what it predicted.
 *
 * `unchanged` means D8 found the same yield and the same amounts of the same
 * ingredients, in any order, so nothing was written: committing the same file
 * twice is a no-op. `changed` names any of the item's own facts that moved
 * even so ("selling price", "category").
 */
export type MenuLoadOutcome = "created" | "version_added" | "unchanged";

export interface MenuLoadResult {
  outcome: MenuLoadOutcome;
  changed: string[];
  version: number;
  menu_item: MenuItemDetail;
}

/**
 * M6 WP-63: the money moment - a price move landing on the plates.
 *
 * Each material contributes at most its latest move: its newest costed
 * purchase against whatever set the price before it. Same pack -> a real
 * move with a delta and per-plate impacts; a different pack -> the price
 * *basis* changed, both packs are named, and there is **no delta** - a delta
 * across pack sizes is a pack artifact wearing a percent sign, and the money
 * moment must not lie. Only materials on the current menu appear.
 */
export type PriceMoveKind = "moved" | "basis_changed";

/** One side of a move: which pack, from whom, at what per kilo, on which
 * invoice - so both sides drill to their photos. */
export interface PriceMoveLine {
  supplier_item_id: string;
  product_name: string;
  supplier_name: string;
  pack_size: string | null;
  /** Per kilo / litre / each, two decimals. Money string. */
  per_display_unit: string;
  display_unit: string;
  invoice_id: string;
  invoice_line_id: string;
  /** For the /invoices/<id>#line-<position> anchor. */
  position: number;
  purchased_on: string | null;
  invoice_date: string | null;
}

/** What the move did to one costed menu item. */
export interface PriceMoveItem {
  menu_item_id: string;
  name: string;
  /** Signed decimal string: positive means the margin fell by this much. */
  impact_per_portion: string;
  margin_before: string;
  margin_after: string;
  margin_pct_before: string;
  margin_pct_after: string;
}

export interface PriceMove {
  ingredient_id: string;
  ingredient_name: string;
  base_unit: BaseUnit;
  kind: PriceMoveKind;
  current: PriceMoveLine;
  previous: PriceMoveLine;
  /** Signed money string per display unit; null when the basis changed. */
  delta_per_display_unit: string | null;
  /** Empty when the basis changed - no impact can honestly be attributed. */
  items: PriceMoveItem[];
}

/**
 * M8 WP-80/83: sales from the till's own export, pinned by
 * Docs/M8_DECOMPOSITION.md §3.1 (C11, C6 extended). Money and percentages
 * are strings, dates are ISO, and the browser never divides money: the net
 * figure on a day is the door's answer, never the loader's prediction.
 */

/** GET /api/branches: the tenant's branches (envelope {"branches": [...]}).
 * The console needed this since the upload screen, which derived its
 * choices from the invoice list; the aliases are the till's own labels for
 * each branch, taught once (C11.1). */
export interface Branch {
  id: string;
  name: string;
  timezone: string;
  aliases: string[];
}

/** POST /api/branches/{id}/aliases -> 201 {"alias": {...}}; 409 when the
 * alias already names another branch. */
export interface BranchAlias {
  id: string;
  branch_id: string;
  alias: string;
  alias_key: string;
}

/** POST /api/sales/files (multipart): the raw CSV kept immutably under a
 * server-computed sha256 (C11.1, PRD §12). A second post of the same bytes
 * answers the same hash. */
export interface SalesFileResult {
  sha256: string;
  filename: string;
  bytes: number;
}

/** The logical columns a layout maps, each to a header *name* - never a
 * position, so a reordered export applies unchanged and a renamed column
 * stops the file (C11.1). `date` and `amount` are the only two a file cannot
 * be read without; no `item` column is the summary shape. */
export type SalesColumn = "branch" | "date" | "item" | "code" | "qty" | "amount";

export type SalesColumnMap = Partial<Record<SalesColumn, string>>;

/** How a layout's amounts are read: as a till prints them (VAT inside) or
 * net already. Chosen once per layout and shown on every preview after. */
export type AmountBasis = "inclusive" | "exclusive";

/** Which way a numeric date in this layout's files reads. */
export type DateOrder = "dmy" | "ymd";

/** GET /api/sales/layouts (envelope {"layouts": [...]}): a till's column
 * layout, saved once and applied by header name. `header_key` is derived
 * server-side from the mapped header names (normalised, sorted, joined with
 * "|" - `amount|date|item|outlet|plu|qty` for the pinned demo header); the
 * client never sends it. */
export interface SalesLayout {
  id: string;
  name: string;
  header_key: string;
  columns: SalesColumnMap;
  amount_basis: AmountBasis;
  date_order: DateOrder;
  updated_at: string;
}

/** POST /api/sales/layouts: upsert by name -> 201 on the first save, 200 on
 * an update, {"layout": {...}} either way with the same id. */
export interface SalesLayoutInput {
  name: string;
  columns: SalesColumnMap;
  amount_basis: AmountBasis;
  date_order: DateOrder;
}

/** Item-wise (one row per till item) or a day total with no lines. A closed
 * day is a summary day with takings 0, never inferred from a gap. */
export type SalesGranularity = "item" | "summary";

/** One line as the loader posts it: the till's own words. `qty` is optional
 * (a summary-ish item export may print none); `amount` is signed - a refund
 * row is legal and reduces the day. */
export interface SalesLineInput {
  position: number;
  name: string;
  code: string | null;
  qty: string | null;
  amount: string;
}

/** One stored line: the printed name and code stay as the evidence, the
 * till item is the identity, and `net_amount` is the door's division. */
export interface SalesLine extends SalesLineInput {
  net_amount: string;
  till_item_id: string;
}

/** One stored branch-day, as GET /api/sales/days returns it (with lines) and
 * as the door's outcome carries it (without). */
export interface SalesDay {
  id: string;
  branch_id: string;
  business_date: string;
  granularity: SalesGranularity;
  amount_basis: AmountBasis;
  /** The VAT rate the net was taken out at ("0.05"). */
  vat_rate: string;
  /** The printed total, as the till printed it. Money string. */
  takings: string;
  /** Ex-VAT, the exact sum of the lines' net amounts. Money string. */
  net_sales: string;
  line_count: number;
  layout_id: string | null;
  source_sha256: string | null;
  source_filename: string | null;
  loaded_by: string;
  loaded_at: string;
  lines: SalesLine[];
}

/** One branch-day as the loader posts it. An item day carries `lines`; a
 * summary day carries `amount` (0 for a closed day) and no lines. The door
 * takes `source` and `layout_id` as optional; the console always posts the
 * file first and sends both, so every day it loads traces to its bytes. */
export interface SalesDayInput {
  branch_id: string;
  business_date: string;
  granularity: SalesGranularity;
  amount_basis: AmountBasis;
  layout_id: string | null;
  source?: { sha256: string; filename: string } | null;
  lines?: SalesLineInput[];
  amount?: string;
}

/** POST /api/sales/days body: at most 31 days (one branch-month), one
 * transaction and one outcome each. */
export interface SalesDaysInput {
  days: SalesDayInput[];
}

/** C11.4's three outcomes: a first load, the same day again (nothing
 * written), or the day replaced with the previous figures named. */
export type SalesDayOutcome = "loaded" | "unchanged" | "replaced";

export interface SalesDayResult {
  branch_id: string;
  business_date: string;
  outcome: SalesDayOutcome;
  previous: { net_sales: string; line_count: number } | null;
  day: Omit<SalesDay, "lines">;
}

export interface SalesDaysResult {
  days: SalesDayResult[];
}

/**
 * M8 WP-81/82/84: the sales screen's reads and the till-name doors, pinned by
 * Docs/M8_DECOMPOSITION.md §3.1 (C11.5-C11.8, the C9 amendment). Money and
 * percentages are strings; the ratio is derived on every read and nothing
 * here is ever stored, so a paper confirmed from a phone moves these numbers
 * on the next load.
 */

/** PRD §24's words for a period figure. `verified` is absent on purpose:
 * nothing cross-checks a till's figures. Precedence worst first. */
export type PeriodQuality =
  | "reliable_with_limitations"
  | "estimated"
  | "incomplete"
  | "unavailable";

/** The period a read covers. `default` is true when the caller sent no
 * range and the API chose 28 days ending on the tenant's newest loaded day;
 * `sales_through` is that newest day, null when nothing was ever loaded -
 * the one fact the empty state is decided on. */
export interface SalesPeriod {
  from: string;
  to: string;
  days: number;
  default: boolean;
  sales_through: string | null;
  /** The calendar months holding at least one loaded day, newest first, as
   * "YYYY-MM": the period picker's choices, served rather than inferred so a
   * tenant's oldest month stays reachable (WP-84 review). */
  months: string[];
}

/** One confirmed paper counted in a row: `net_purchase` is `total - tax`,
 * the two printed figures the drill shows beside the photo (P2). */
export interface InvoiceFigure {
  invoice_id: string;
  supplier_name: string | null;
  invoice_no: string | null;
  purchased_on: string | null;
  net_purchase: string;
  /** The two printed figures; null when the paper printed none (a market
   * receipt with no VAT line still confirms, and its VAT is null). */
  total: string | null;
  tax: string | null;
  /** `estimated` when the total or the VAT was entered by a person. */
  quality: "reliable_with_limitations" | "estimated";
}

/** A paper on its way: awaiting confirm or held for review, placed on its
 * printed date or, when it printed none, the day it arrived. */
export interface PendingPaper {
  invoice_id: string;
  supplier_name: string | null;
  invoice_no: string | null;
  status: "awaiting_confirm" | "needs_review";
  placed_on: string | null;
  undated: boolean;
}

/** A confirmed paper in another currency: named, never counted. */
export interface ExcludedPaper {
  invoice_id: string;
  supplier_name: string | null;
  invoice_no: string | null;
  currency: string;
  total: string | null;
}

/** One day of a branch's drill: every loaded day, plus any date a counted
 * paper sits on with no sales row (`net_sales` and `granularity` null). */
export interface DayFigure {
  business_date: string;
  net_sales: string | null;
  granularity: SalesGranularity | null;
  purchases: string;
  invoices: InvoiceFigure[];
}

/** One branch's row, ranked by the API highest ratio first, unrated rows
 * last. `window` is the period clipped to the branch's own loaded range;
 * `ratio_pct` is null whenever the row cannot honestly carry one; `notes`
 * are the sentences that made the label, in the API's own words. */
export interface BranchRow {
  branch_id: string;
  branch_name: string;
  window: { from: string; to: string; days: number };
  net_sales: string | null;
  takings: string | null;
  purchases: string;
  ratio_pct: string | null;
  quality: PeriodQuality;
  notes: string[];
  days_loaded: number;
  days_missing: number;
  deliveries: number;
  sales_through: string | null;
  last_purchase_on: string | null;
  days: DayFigure[];
  pending: PendingPaper[];
  excluded: ExcludedPaper[];
}

/** Confirmed papers with no branch: counted in the total, ranked nowhere,
 * and shown as the "No branch" row only when there are any. */
export interface SalesUnassigned {
  count: number;
  purchases: string;
  invoices: InvoiceFigure[];
}

/** The row that reconciles the table: every branch plus the unassigned
 * group. Incomplete when any branch is unavailable or incomplete. */
export interface SalesTotal {
  net_sales: string;
  purchases: string;
  ratio_pct: string | null;
  quality: PeriodQuality;
  notes: string[];
}

/** GET /api/sales/branches?from&to */
export interface SalesBranchesResult {
  period: SalesPeriod;
  rows: BranchRow[];
  unassigned: SalesUnassigned;
  total: SalesTotal;
}

/** A menu item the matcher proposes for a till name, best first, at most
 * three; `score` is a two-decimal string. Proposes, never decides. */
export interface CoverageProposal {
  menu_item_id: string;
  name: string;
  score: string;
}

export interface CoverageItem {
  till_item_id: string;
  name: string;
  code: string | null;
  /** The positive net value sold in the period. Money string. */
  value: string;
}

export interface CoverageQueueItem extends CoverageItem {
  proposals: CoverageProposal[];
}

export interface CoverageMappedItem extends CoverageItem {
  menu_item_id: string;
  menu_item_name: string;
  plate_quality: PlateQuality;
}

/** GET /api/sales/coverage?from&to - recipe coverage by sales value
 * (C11.8): the share of the period's menu sales whose till item maps to a
 * plate that can be costed. The word is *costed*, never *complete*: an
 * estimated plate counts as costed and its points are named. `costed_pct`
 * and `estimated_points` are null when nothing item-wise was sold. */
export interface SalesCoverageResult {
  period: SalesPeriod;
  sales_value: string;
  costed_value: string;
  costed_pct: string | null;
  estimated_points: string | null;
  uncosted: { incomplete_plate: string; unmapped: string };
  beside: { refunds: string; not_menu_items: string };
  queue: CoverageQueueItem[];
  mapped: CoverageMappedItem[];
  excluded: CoverageItem[];
}

/** A till name as the three doors answer it: mapped (`menu_item_id` set),
 * back in the queue (null), or marked not a menu item (`excluded_at`). */
export interface TillItem {
  id: string;
  name: string;
  code: string | null;
  menu_item_id: string | null;
  menu_item_name: string | null;
  excluded_at: string | null;
}

// --- M9 WP-93: the owner dashboard (Docs/M9_DECOMPOSITION.md §3.1) ----------
//
// One read for the whole screen: the period and its freshness, the two
// answer sentences, the newest loaded day (M10's first brief slot), the
// papers waiting, the branch league with contribution beside the ratio, every
// item row, the signals ranked by money, and the unmapped count. Money and
// percentages are strings, dates ISO, exactly as the sales shapes are; every
// sentence that states a fact or a number is composed by the API (C13.5), so
// the screen frames and joins and never computes, re-words or re-ranks.

/** The dashboard's period: `/sales`' shape plus the age of the newest loaded
 * day and the date the plates were costed at (the period's last day, C12.4). */
export interface DashboardPeriod extends SalesPeriod {
  sales_age_days: number | null;
  costed_at: string | null;
}

/** The two answers, each one sentence composed by the API, null when that
 * side cannot be answered; `quality` is the worse of the two rows behind
 * them and `notes` the sentences that made it. */
export interface DashboardAnswer {
  branch: string | null;
  item: string | null;
  quality: PeriodQuality;
  notes: string[];
}

/** How fresh the sales are. `quality` is `estimated` past seven days, and the
 * screen carries the word beside the sentence, never only a tone. */
export interface DashboardFreshness {
  sales_through: string | null;
  sales_age_days: number | null;
  last_purchase_on: string | null;
  branches_without_sales: number;
  quality: "reliable_with_limitations" | "estimated";
  sentence: string | null;
}

export interface LatestDayBranch {
  branch_id: string;
  branch_name: string;
  date: string;
  net_sales: string;
}

/** The newest loaded day's net sales, chain and per branch (P6, P8): present
 * when that day lies inside the period, null otherwise. */
export interface LatestDay {
  date: string;
  net_sales: string;
  branches: LatestDayBranch[];
}

export interface ApprovalPaper {
  invoice_id: string;
  supplier_name: string | null;
  invoice_no: string | null;
  total: string | null;
  invoice_date: string | null;
  branch_name: string | null;
  status: "needs_review" | "awaiting_confirm";
  is_duplicate: boolean;
}

/** Papers waiting: `count` is the papers held for review (the owner's job),
 * `awaiting_confirm` the ones waiting for a branch's OK, both from one read;
 * `invoices` is at most five of the held ones - the count is the truth and
 * the list a courtesy. */
export interface DashboardApprovals {
  count: number;
  duplicates: number;
  awaiting_confirm: number;
  invoices: ApprovalPaper[];
}

/** One branch of the league: `/sales`' row (the same fields, the same
 * figures, matched by `branch_id`) with contribution beside the ratio. Two
 * quality words because they routinely differ (C9 extended): a branch with
 * no papers has an unavailable ratio and a perfectly reliable contribution.
 * Ranked by the API by kept percentage, lowest first (C12.9). */
export interface LeagueRow {
  branch_id: string;
  branch_name: string;
  window: { from: string; to: string; days: number };
  net_sales: string | null;
  takings: string | null;
  purchases: string;
  ratio_pct: string | null;
  contribution: string | null;
  contribution_pct: string | null;
  costed_share_pct: string | null;
  ratio_quality: PeriodQuality;
  ratio_notes: string[];
  contribution_quality: PeriodQuality;
  contribution_notes: string[];
  days_loaded: number;
  days_missing: number;
  deliveries: number;
  sales_through: string | null;
  last_purchase_on: string | null;
}

export interface DashboardUnassigned {
  count: number;
  purchases: string;
}

/** Set when `?branch_id` filters the view; the league, the items and the
 * signals follow it, `total` never does. */
export interface DashboardScope {
  branch_id: string | null;
  branch_name: string | null;
}

/** Always the chain, filter or no filter, so a branch is compared to the
 * chain and never to itself. */
export interface DashboardTotal {
  net_sales: string;
  purchases: string;
  ratio_pct: string | null;
  contribution: string | null;
  contribution_pct: string | null;
  costed_share_pct: string | null;
  ratio_quality: PeriodQuality;
  ratio_notes: string[];
  contribution_quality: PeriodQuality;
  contribution_notes: string[];
}

export interface ItemTillName {
  till_item_id: string;
  name: string;
  code: string | null;
}

/** One recipe component's share of a portion's cost and the invoice line the
 * as-of price came from (C12.4a): the drill links `/invoices/<id>#line-<n>`. */
export interface ItemComponent {
  ingredient_id: string;
  ingredient_name: string;
  qty: string;
  unit: string;
  cost_per_portion: string | null;
  invoice_id: string | null;
  line_position: number | null;
  purchased_on: string | null;
}

/** One (menu item, branch, period), or the chain when `branch_id` is null.
 * An incomplete row carries every cost number as null and its reasons in
 * `notes` - a hole never renders as a fat margin. */
export interface DashboardItemRow {
  menu_item_id: string;
  menu_item_name: string;
  category: string | null;
  branch_id: string | null;
  qty_sold: string | null;
  qty_refunded: string | null;
  net_item_sales: string;
  cost_per_portion: string | null;
  cost: string | null;
  /** Present only when today's plate differs from the one the period used. */
  cost_per_portion_today: string | null;
  contribution: string | null;
  contribution_pct: string | null;
  avg_sold_at: string | null;
  net_price: string | null;
  plate_quality: PlateQuality;
  quality: PlateQuality;
  notes: string[];
  recipe_version: number | null;
  till_items: ItemTillName[];
  components: ItemComponent[];
  archived: boolean;
}

/** `top` and `bottom` are slices of `all`, five each; `all` carries every
 * costed row plus the incomplete ones, so the panel expands with no further
 * request; `count` is how many rows carry numbers. */
export interface DashboardItems {
  top: DashboardItemRow[];
  bottom: DashboardItemRow[];
  all: DashboardItemRow[];
  count: number;
}

export type SignalKind = "popular_low_margin" | "price_spike" | "branch_gap";

/** One line of "what to look at" (C13): the sentence, the detail beneath
 * it, the AED at stake it is ranked by, and the ids the screen links with.
 * A signal that fired on an estimated input carries the word in its detail. */
export interface DashboardSignal {
  kind: SignalKind;
  money_at_stake: string;
  quality: "reliable_with_limitations" | "estimated";
  sentence: string;
  detail: string;
  branch_id: string | null;
  branch_name: string | null;
  menu_item_id: string | null;
  menu_item_name: string | null;
  ingredient_id: string | null;
  ingredient_name: string | null;
  invoice_id: string | null;
  moved_on: string | null;
}

/** Till names with sales in the window that have no dish and no exclusion,
 * and the value they hold - a note beside the figures and a link to the
 * queue on `/sales` that owns them, never a second queue. */
export interface DashboardUnmapped {
  names: number;
  value: string;
}

/** What the menu can cost today, for the first-run paragraph: live items
 * and the ones whose plate has a price for every ingredient. */
export interface DashboardMenu {
  items: number;
  costed: number;
}

/** GET /api/dashboard?from&to&branch_id */
export interface DashboardResult {
  period: DashboardPeriod;
  answer: DashboardAnswer;
  freshness: DashboardFreshness;
  latest_day: LatestDay | null;
  approvals: DashboardApprovals;
  league: LeagueRow[];
  unassigned: DashboardUnassigned;
  scope: DashboardScope;
  total: DashboardTotal;
  items: DashboardItems;
  signals: DashboardSignal[];
  unmapped: DashboardUnmapped;
  menu: DashboardMenu;
}
