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
 */

import type { DocumentSource, InvoiceStatus, PaymentKind, PriceHistory } from "../types";

export interface FixtureLine {
  raw_name: string;
  qty: string | null;
  unit: string | null;
  pack_size: string | null;
  unit_price: string | null;
  line_total: string | null;
  supplier_item_id: string | null;
  snapped: boolean | null;
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
  image_url: string | null;
  created_at: string;
  lines: FixtureLine[];
}

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
