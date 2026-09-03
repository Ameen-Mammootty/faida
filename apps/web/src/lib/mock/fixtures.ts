/**
 * The mock dataset: three invoices covering the demo states.
 *
 * inv-1001  all green, awaiting confirmation (the happy path)
 * inv-1002  amber fields: one arithmetic failure, one unreadable quantity
 * inv-1003  cash invoice held as needs_review
 *
 * Checks and confidence are computed by the store through the same
 * validation mirror a PATCH uses, so fixtures can never drift from the
 * check shapes the real API persists. Timestamps use the "+00:00" offset
 * form, exactly as Python's datetime.isoformat() serializes them. The
 * fixture photos in /public/fixtures show exactly these numbers - every
 * field traces.
 *
 * Price histories (WP-33): a plausible three weeks of confirmed deliveries
 * for the items the demo sparkline shows - one rising, one steady, one
 * falling - plus catalog items with no confirmed observations yet (the real
 * endpoint's header + empty prices case). The open invoices' extracted
 * prices are deliberately absent: the baseline moves only on confirm.
 *
 * WP-34 adds the branch options and the invoice a simulated upload
 * "extracts"; the store assembles both into the same shapes at runtime.
 */

import type {
  BaseUnit,
  CostBlocker,
  DocumentClassification,
  DocumentSource,
  InvoiceStatus,
  LineCost,
  LineKind,
  PaymentKind,
  PriceHistory,
} from "../types";

export interface FixtureLine {
  raw_name: string;
  qty: string | null;
  unit: string | null;
  pack_size: string | null;
  unit_price: string | null;
  line_total: string | null;
  supplier_item_id: string | null;
  snapped: boolean | null;
  /** Omitted means stock. Charges (delivery, cool-box hire) never cost. */
  line_kind?: LineKind;
  /**
   * What the server would freeze onto this line at confirm (M5 WP-53), which
   * is the only moment a cost exists. Written out rather than computed,
   * deliberately: the arithmetic is `unit_price / pack size` with C4's two
   * factors, and reimplementing that in TypeScript would put a second money
   * implementation in the demo mock - the thing plan.md section 2 rule 3
   * exists to refuse. This keeps the *shape* honest so the screen is never
   * built against a payload the API does not send.
   */
  cost?: LineCost;
}

/** Plain English for a blocker, mirroring faida_api/costing.BLOCKED_REASONS. */
const BLOCKED_REASONS: Record<CostBlocker, string> = {
  foreign_currency: "This invoice is billed in another currency, so its prices are held back.",
  missing_unit_price: "The invoice does not show a price for this line.",
  missing_quantity:
    "The invoice does not show how many were bought, so nothing checks the price.",
  zero_pack: "The pack size names a unit but no amount to divide by.",
  bare_container: "Nothing on the invoice says how much one of these holds.",
  unparseable_pack: "Nothing on this line reads as a pack size.",
};

/** A cost the invoice's own numbers support. Never `verified`: nothing
 * anywhere cross-checks a pack size. */
function costs(
  perBaseUnit: string,
  baseUnit: BaseUnit,
  perDisplayUnit: string,
  displayUnit: string,
  pack: string,
): LineCost {
  return {
    per_base_unit: perBaseUnit,
    base_unit: baseUnit,
    per_display_unit: perDisplayUnit,
    display_unit: displayUnit,
    quality: "reliable_with_limitations",
    asserted: [],
    pack,
    pack_source: "pack_size",
    blocked: null,
    reason: null,
  };
}

function cannotCost(blocked: CostBlocker): LineCost {
  return {
    per_base_unit: null,
    base_unit: null,
    per_display_unit: null,
    display_unit: null,
    quality: null,
    asserted: [],
    pack: null,
    pack_source: null,
    blocked,
    reason: BLOCKED_REASONS[blocked],
  };
}

export interface Fixture {
  id: string;
  document_id: string;
  branch_id: string | null;
  branch_name: string | null;
  supplier_id: string | null;
  supplier_name: string | null;
  invoice_no: string | null;
  invoice_date: string | null;
  currency: string;
  subtotal: string | null;
  tax: string | null;
  total: string | null;
  payment_kind: PaymentKind | null;
  status: InvoiceStatus;
  source: DocumentSource;
  /** Omitted means "invoice" (the pipeline classified it); manual entries
   * pass null - no model looked at anything (WP-34). */
  classification?: DocumentClassification | null;
  image_url: string | null;
  created_at: string;
  /** WP-44: the fixture id of the invoice this one duplicates. Omitted on
   * every ordinary invoice - it is what marks a held copy. */
  duplicate_of_invoice_id?: string | null;
  lines: FixtureLine[];
}

/**
 * The two mock branches, for pages that offer a branch choice. C6 has no
 * branches endpoint; against the real API those pages derive options from
 * the invoice list, and these ids match the fixtures' branch_id values so
 * both modes behave alike.
 */
export const MOCK_BRANCHES: { id: string; name: string }[] = [
  { id: "br-01", name: "Al Quoz" },
  { id: "br-02", name: "Karama" },
];

/**
 * What a simulated upload "extracts" (WP-34): the mock store lands this as
 * an invoice a few seconds after POST /api/documents, so the upload page's
 * polling finds it exactly like it would against the real pipeline. The
 * numbers reconcile, so the review screen opens all green.
 */
export const UPLOADED_INVOICE_TEMPLATE = {
  supplier_name: "Barakat Vegetables & Fruits",
  invoice_no: "BV-3327",
  invoice_date: "2026-08-23",
  currency: "AED",
  subtotal: "196.50",
  tax: "9.83",
  total: "206.33",
  payment_kind: "credit" as PaymentKind,
  lines: [
    {
      raw_name: "Cucumber Box 4kg",
      qty: "3",
      unit: "box",
      pack_size: "4kg",
      unit_price: "12.50",
      line_total: "37.50",
      supplier_item_id: null,
      snapped: null,
    },
    {
      raw_name: "Lemon Bag 3kg",
      qty: "2",
      unit: "bag",
      pack_size: "3kg",
      unit_price: "16.00",
      line_total: "32.00",
      supplier_item_id: null,
      snapped: null,
    },
    {
      raw_name: "Fresh Mint Bunches",
      qty: "20",
      unit: "bunch",
      pack_size: null,
      unit_price: "1.25",
      line_total: "25.00",
      supplier_item_id: null,
      snapped: null,
    },
    {
      raw_name: "Potato Bag 10kg",
      qty: "4",
      unit: "bag",
      pack_size: "10kg",
      unit_price: "25.50",
      line_total: "102.00",
      supplier_item_id: null,
      snapped: null,
    },
  ] satisfies FixtureLine[],
};

export const FIXTURES: Fixture[] = [
  {
    id: "inv-1001",
    document_id: "doc-9001",
    branch_id: "br-01",
    branch_name: "Al Quoz",
    supplier_id: "sup-01",
    supplier_name: "Al Madina Foodstuff Trading LLC",
    invoice_no: "INV-10482",
    invoice_date: "2026-08-21",
    currency: "AED",
    subtotal: "682.75",
    tax: "34.14",
    total: "716.89",
    payment_kind: "credit",
    status: "awaiting_confirm",
    source: "whatsapp",
    image_url: "/fixtures/inv-1001.svg",
    created_at: "2026-08-21T09:42:00+00:00",
    lines: [
      {
        raw_name: "Rainbow Milk Powder 2.25kg",
        qty: "6",
        unit: "tin",
        pack_size: "2.25kg",
        unit_price: "54.50",
        line_total: "327.00",
        supplier_item_id: "si-2001",
        snapped: true,
        cost: costs("0.02422222", "g", "24.22", "kg", "2.25kg"),
      },
      {
        raw_name: "Karak Tea Dust 5kg",
        qty: "2",
        unit: "bag",
        pack_size: "5kg",
        unit_price: "49.00",
        line_total: "98.00",
        supplier_item_id: "si-2002",
        snapped: true,
        cost: costs("0.00980000", "g", "9.80", "kg", "5kg"),
      },
      {
        raw_name: "Sugar 50kg",
        qty: "1",
        unit: "sack",
        pack_size: "50kg",
        unit_price: "118.75",
        line_total: "118.75",
        supplier_item_id: "si-2003",
        snapped: true,
        cost: costs("0.00237500", "g", "2.38", "kg", "50kg"),
      },
      {
        raw_name: "Cardamom Powder 500g",
        qty: "3",
        unit: "pack",
        pack_size: "500g",
        unit_price: "24.00",
        line_total: "72.00",
        supplier_item_id: "si-2004",
        snapped: true,
        cost: costs("0.04800000", "g", "48.00", "kg", "500g"),
      },
      {
        raw_name: "Paper Cups 8oz x1000",
        qty: "2",
        unit: "carton",
        pack_size: "1000pc",
        unit_price: "33.50",
        line_total: "67.00",
        supplier_item_id: "si-2005",
        snapped: true,
        cost: costs("0.03350000", "pc", "0.03", "each", "1000pc"),
      },
    ],
  },
  {
    id: "inv-1002",
    document_id: "doc-9002",
    branch_id: "br-02",
    branch_name: "Karama",
    supplier_id: "sup-02",
    supplier_name: "Al Seeb Trading Co LLC",
    invoice_no: "INV-7731",
    invoice_date: "2026-08-22",
    currency: "AED",
    subtotal: "270.25",
    tax: "13.51",
    total: "283.76",
    payment_kind: "credit",
    status: "awaiting_confirm",
    source: "whatsapp",
    image_url: "/fixtures/inv-1002.svg",
    created_at: "2026-08-22T11:08:00+00:00",
    lines: [
      {
        raw_name: "Chapati Flour 25kg",
        qty: "2",
        unit: "sack",
        pack_size: "25kg",
        unit_price: "38.00",
        line_total: "76.00",
        supplier_item_id: "si-2101",
        snapped: true,
        cost: costs("0.00152000", "g", "1.52", "kg", "25kg"),
      },
      {
        raw_name: "Evaporated Milk 410ml",
        qty: "12",
        unit: "tin",
        pack_size: "410ml",
        unit_price: "4.50",
        line_total: "58.00",
        supplier_item_id: "si-2102",
        snapped: true,
        cost: costs("0.01097561", "ml", "10.98", "litre", "410ml"),
      },
      {
        raw_name: "Sugar 10kg",
        qty: null,
        unit: "bag",
        pack_size: "10kg",
        unit_price: "42.00",
        line_total: "84.00",
        supplier_item_id: "si-2103",
        snapped: true,
        // No quantity read, so nothing corroborates the unit price (WP-53).
        cost: cannotCost("missing_quantity"),
      },
      {
        raw_name: "Saffron Threads 1g",
        qty: "1",
        unit: "box",
        pack_size: "1g",
        unit_price: "52.25",
        line_total: "52.25",
        supplier_item_id: null,
        snapped: false,
        cost: costs("52.25000000", "g", "52250.00", "kg", "1g"),
      },
    ],
  },
  {
    id: "inv-1003",
    document_id: "doc-9003",
    branch_id: "br-01",
    branch_name: "Al Quoz",
    supplier_id: null,
    supplier_name: "Gulf Fresh Vegetables & Fruits",
    invoice_no: "2214",
    invoice_date: "2026-08-22",
    currency: "AED",
    subtotal: null,
    tax: null,
    total: "101.00",
    payment_kind: "cash",
    status: "needs_review",
    source: "whatsapp",
    image_url: "/fixtures/inv-1003.svg",
    created_at: "2026-08-22T16:31:00+00:00",
    lines: [
      {
        raw_name: "Tomatoes Box 5kg",
        qty: "4",
        unit: "box",
        pack_size: "5kg",
        unit_price: "12.50",
        line_total: "50.00",
        supplier_item_id: null,
        snapped: null,
        cost: costs("0.00250000", "g", "2.50", "kg", "5kg"),
      },
      {
        raw_name: "Onions Bag 10kg",
        qty: "2",
        unit: "bag",
        pack_size: "10kg",
        unit_price: "18.00",
        line_total: "36.00",
        supplier_item_id: null,
        snapped: null,
        cost: costs("0.00180000", "g", "1.80", "kg", "10kg"),
      },
      {
        raw_name: "Coriander Bunches",
        qty: "10",
        unit: "bunch",
        pack_size: null,
        unit_price: "1.50",
        line_total: "15.00",
        supplier_item_id: null,
        snapped: null,
        // A bunch is a container: nothing says how much coriander is in one.
        cost: cannotCost("bare_container"),
      },
    ],
  },
  // WP-44's hold: Al Madina's INV-10482 forwarded a second time, exactly the
  // double-send the founder hit. Same supplier, same number, same total as
  // inv-1001, so the pipeline holds it instead of reading it out - and the
  // review screen offers the way out. The paper is the same paper, so the
  // lines are inv-1001's line for line; no cost, because a copy is never
  // confirmed and a cost exists only from confirm (WP-53).
  {
    id: "inv-1004",
    document_id: "doc-9004",
    branch_id: "br-01",
    branch_name: "Al Quoz",
    supplier_id: "sup-01",
    supplier_name: "Al Madina Foodstuff Trading LLC",
    invoice_no: "INV-10482",
    invoice_date: "2026-08-21",
    currency: "AED",
    subtotal: "682.75",
    tax: "34.14",
    total: "716.89",
    payment_kind: "credit",
    status: "needs_review",
    source: "whatsapp",
    image_url: "/fixtures/inv-1001.svg",
    created_at: "2026-08-21T14:16:00+00:00",
    duplicate_of_invoice_id: "inv-1001",
    lines: [
      {
        raw_name: "Rainbow Milk Powder 2.25kg",
        qty: "6",
        unit: "tin",
        pack_size: "2.25kg",
        unit_price: "54.50",
        line_total: "327.00",
        supplier_item_id: "si-2001",
        snapped: true,
      },
      {
        raw_name: "Karak Tea Dust 5kg",
        qty: "2",
        unit: "bag",
        pack_size: "5kg",
        unit_price: "49.00",
        line_total: "98.00",
        supplier_item_id: "si-2002",
        snapped: true,
      },
      {
        raw_name: "Sugar 50kg",
        qty: "1",
        unit: "sack",
        pack_size: "50kg",
        unit_price: "118.75",
        line_total: "118.75",
        supplier_item_id: "si-2003",
        snapped: true,
      },
      {
        raw_name: "Cardamom Powder 500g",
        qty: "3",
        unit: "pack",
        pack_size: "500g",
        unit_price: "24.00",
        line_total: "72.00",
        supplier_item_id: "si-2004",
        snapped: true,
      },
      {
        raw_name: "Paper Cups 8oz x1000",
        qty: "2",
        unit: "carton",
        pack_size: "1000pc",
        unit_price: "33.50",
        line_total: "67.00",
        supplier_item_id: "si-2005",
        snapped: true,
      },
    ],
  },
  // WP-74's D12 case: Gulf Fresh's cash paper 2214 forwarded a second time.
  // Cash *and* a held duplicate - held on two grounds at once, so the screen
  // shows both banners, and the approve door is still open (with a reason)
  // because a cash paper that really is a second delivery needs a recording
  // door; dismissing is the copy's exit, not cash's. Lines are inv-1003's.
  {
    id: "inv-1005",
    document_id: "doc-9005",
    branch_id: "br-01",
    branch_name: "Al Quoz",
    supplier_id: null,
    supplier_name: "Gulf Fresh Vegetables & Fruits",
    invoice_no: "2214",
    invoice_date: "2026-08-22",
    currency: "AED",
    subtotal: null,
    tax: null,
    total: "101.00",
    payment_kind: "cash",
    status: "needs_review",
    source: "whatsapp",
    image_url: "/fixtures/inv-1003.svg",
    created_at: "2026-08-22T17:02:00+00:00",
    duplicate_of_invoice_id: "inv-1003",
    lines: [
      {
        raw_name: "Tomatoes Box 5kg",
        qty: "4",
        unit: "box",
        pack_size: "5kg",
        unit_price: "12.50",
        line_total: "50.00",
        supplier_item_id: null,
        snapped: null,
      },
      {
        raw_name: "Onions Bag 10kg",
        qty: "2",
        unit: "bag",
        pack_size: "10kg",
        unit_price: "18.00",
        line_total: "36.00",
        supplier_item_id: null,
        snapped: null,
      },
      {
        raw_name: "Coriander Bunches",
        qty: "10",
        unit: "bunch",
        pack_size: null,
        unit_price: "1.50",
        line_total: "15.00",
        supplier_item_id: null,
        snapped: null,
      },
    ],
  },
];

/**
 * GET /api/supplier-items/{id}/prices payloads: item header (from
 * supplier_items) plus confirmed observations ascending by observed_at (from
 * supplier_item_prices). prev_price/last_price shift only when a confirmed
 * price actually changed, so a steady item keeps prev_price null.
 */
export const PRICE_HISTORIES: Record<string, PriceHistory> = {
  // The demo's money moment: milk powder creeping up over three weeks. The
  // open invoice reads 54.50 - visibly above the confirmed 50.50 baseline.
  "si-2001": {
    id: "si-2001",
    canonical_name: "Rainbow Milk Powder 2.25kg",
    unit: "tin",
    pack_size: "2.25kg",
    last_price: "50.50",
    prev_price: "49.25",
    prices: [
      { price: "48.00", observed_at: "2026-08-01T10:15:00+00:00", invoice_id: "inv-0894" },
      { price: "48.00", observed_at: "2026-08-04T09:40:00+00:00", invoice_id: "inv-0902" },
      { price: "48.50", observed_at: "2026-08-08T10:05:00+00:00", invoice_id: "inv-0921" },
      { price: "49.25", observed_at: "2026-08-11T09:55:00+00:00", invoice_id: "inv-0936" },
      { price: "49.25", observed_at: "2026-08-15T10:20:00+00:00", invoice_id: "inv-0948" },
      { price: "50.50", observed_at: "2026-08-18T10:10:00+00:00", invoice_id: "inv-0957" },
    ],
  },
  // Steady: same price on every confirmed delivery, so prev_price never set.
  "si-2002": {
    id: "si-2002",
    canonical_name: "Karak Tea Dust 5kg",
    unit: "bag",
    pack_size: "5kg",
    last_price: "49.00",
    prev_price: null,
    prices: [
      { price: "49.00", observed_at: "2026-08-02T10:30:00+00:00", invoice_id: "inv-0896" },
      { price: "49.00", observed_at: "2026-08-09T10:25:00+00:00", invoice_id: "inv-0923" },
      { price: "49.00", observed_at: "2026-08-16T10:45:00+00:00", invoice_id: "inv-0950" },
    ],
  },
  // Falling: sugar easing off over the same three weeks.
  "si-2103": {
    id: "si-2103",
    canonical_name: "Sugar 10kg",
    unit: "bag",
    pack_size: "10kg",
    last_price: "42.00",
    prev_price: "44.50",
    prices: [
      { price: "46.00", observed_at: "2026-08-02T11:10:00+00:00", invoice_id: "inv-0897" },
      { price: "44.50", observed_at: "2026-08-09T11:05:00+00:00", invoice_id: "inv-0925" },
      { price: "42.00", observed_at: "2026-08-16T11:20:00+00:00", invoice_id: "inv-0951" },
    ],
  },
  // Catalog items with no confirmed observations yet: the endpoint still
  // returns the header, with an empty series.
  "si-2003": {
    id: "si-2003",
    canonical_name: "Sugar 50kg",
    unit: "sack",
    pack_size: "50kg",
    last_price: "118.75",
    prev_price: null,
    prices: [],
  },
  "si-2004": {
    id: "si-2004",
    canonical_name: "Cardamom Powder 500g",
    unit: "pack",
    pack_size: "500g",
    last_price: "24.00",
    prev_price: null,
    prices: [],
  },
  "si-2005": {
    id: "si-2005",
    canonical_name: "Paper Cups 8oz x1000",
    unit: "carton",
    pack_size: "1000pc",
    last_price: "33.50",
    prev_price: null,
    prices: [],
  },
  "si-2101": {
    id: "si-2101",
    canonical_name: "Chapati Flour 25kg",
    unit: "sack",
    pack_size: "25kg",
    last_price: "38.00",
    prev_price: null,
    prices: [],
  },
  "si-2102": {
    id: "si-2102",
    canonical_name: "Evaporated Milk 410ml",
    unit: "tin",
    pack_size: "410ml",
    last_price: "4.50",
    prev_price: null,
    prices: [],
  },
};
