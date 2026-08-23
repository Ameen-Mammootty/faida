/**
 * The mock dataset: three invoices covering the demo states.
 *
 * inv-1001  all green, awaiting confirmation (the happy path)
 * inv-1002  amber fields: one arithmetic failure, one unreadable quantity
 * inv-1003  cash invoice held as needs_review
 *
 * Checks and confidence are computed by the store through the same
 * validation mirror a PATCH uses, so fixtures can never drift from the
 * check shapes the real API persists. The fixture photos in
 * /public/fixtures show exactly these numbers - every field traces.
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
    created_at: "2026-08-21T09:42:00Z",
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
    created_at: "2026-08-22T11:08:00Z",
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
    created_at: "2026-08-22T16:31:00Z",
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
 * Confirmed price history for one supplier item (supplier_item_prices rows).
 * The open invoice's 54.50 is deliberately absent: the baseline moves only on
 * confirm, never before.
 */
export const PRICE_HISTORIES: Record<string, PriceHistory> = {
  "si-2001": {
    supplier_item_id: "si-2001",
    canonical_name: "Rainbow Milk Powder 2.25kg",
    unit: "tin",
    pack_size: "2.25kg",
    prices: [
      { price: "48.00", observed_at: "2026-07-28T10:15:00Z", invoice_id: "inv-0894" },
      { price: "49.25", observed_at: "2026-08-05T09:50:00Z", invoice_id: "inv-0921" },
      { price: "50.50", observed_at: "2026-08-14T10:05:00Z", invoice_id: "inv-0957" },
    ],
  },
};
