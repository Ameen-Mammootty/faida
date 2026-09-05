/**
 * Display helpers. Money is rendered verbatim from the API's string values,
 * padded to two decimals by string operations only - never parsed to a
 * number, never rounded, never truncated (plan.md section 3).
 */

import type { InvoiceStatus, PaymentKind } from "./types";

/**
 * "682.75" stays "682.75"; "54.5" renders "54.50"; "12" renders "12.00";
 * "54.500" renders "54.50" - the database stores three decimals and that
 * padding is storage precision, not information (found in rehearsal
 * 2026-08-29: the screen read "54.500" beside a paper printing "54.50").
 * A real third decimal ("52.905", a net-canonical price) is kept: only
 * trailing zeros beyond two decimals are trimmed, so no value ever changes.
 */
export function money(value: string): string {
  const dot = value.indexOf(".");
  if (dot === -1) return `${value}.00`;
  let end = value.length;
  while (end - dot - 1 > 2 && value[end - 1] === "0") end -= 1;
  const trimmed = value.slice(0, end);
  const decimals = end - dot - 1;
  if (decimals >= 2) return trimmed;
  return trimmed + "0".repeat(2 - decimals);
}

/**
 * money(), with thousands separators: "52250.00" renders "52,250.00". String
 * operations only, like everything else here. Costs per kilo reach five
 * figures for real ingredients - a gram of saffron is not a rounding error -
 * and an ungrouped run of digits is the kind of number a reader mis-reads by a
 * factor of ten without noticing.
 */
export function groupedMoney(value: string): string {
  const padded = money(value);
  const dot = padded.indexOf(".");
  const whole = padded.slice(0, dot);
  const sign = whole.startsWith("-") ? "-" : "";
  const digits = sign ? whole.slice(1) : whole;
  return sign + digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",") + padded.slice(dot);
}

/** Quantities are not money: "12.000" is "12", "2.500" is "2.5", "12" stays "12". */
export function quantity(value: string): string {
  if (!value.includes(".")) return value;
  return value.replace(/0+$/, "").replace(/\.$/, "");
}

/**
 * A headline figure, rounded to whole dirhams (plan.md section 3: rounded
 * headline numbers, exact figures only in detail). String operations only -
 * money is never parsed to a number on these screens. Lived in RawMaterials
 * until the menu screen needed it too.
 *
 * It rounds half up, the way every sentence the API composes already rounds
 * (M9 D7, decided by the founder 2026-09-05). It truncated until then, which
 * put a headline a dirham under the sentence printed beside it, and made a
 * loss read smaller than it is. The sign is decided first and the magnitude
 * rounds, so "-411.50" is 412 short of nothing, never 411.
 */
export function roundedAed(value: string): string {
  const negative = value.startsWith("-");
  const magnitude = negative ? value.slice(1) : value;
  const dot = magnitude.indexOf(".");
  const whole = dot === -1 ? magnitude : magnitude.slice(0, dot);
  const firstDecimal = dot === -1 ? "" : magnitude.slice(dot + 1, dot + 2);
  const rounded = firstDecimal >= "5" && firstDecimal <= "9" ? addOneDirham(whole) : whole;
  const grouped = rounded.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `AED ${negative ? "-" : ""}${grouped}`;
}

/** "999" plus a dirham is "1000", carried digit by digit so no headline is
 * ever parsed into a number. */
function addOneDirham(whole: string): string {
  const digits = whole.split("");
  let at = digits.length - 1;
  while (at >= 0 && digits[at] === "9") {
    digits[at] = "0";
    at -= 1;
  }
  if (at < 0) return `1${digits.join("")}`;
  digits[at] = String.fromCharCode(digits[at].charCodeAt(0) + 1);
  return digits.join("");
}

/** Plain English for the header fields C8 keys provenance by. */
const FIELD_WORDS: Record<string, string> = {
  supplier_name: "the supplier name",
  invoice_no: "the invoice number",
  invoice_date: "the invoice date",
  currency: "the currency",
  payment_kind: "the payment terms",
  subtotal: "the subtotal",
  tax: "the VAT",
  total: "the invoice total",
  discount_total: "the discount",
  rounding_amount: "the rounding",
  qty: "quantity",
  unit: "unit",
  unit_price: "price",
  line_total: "total",
  pack_size: "pack size",
  raw_name: "name",
};

/**
 * A C8 field path as something a person reads: "total" becomes "the invoice
 * total", "lines.2.unit_price" becomes "line 3's price".
 *
 * These strings exist because C9 has to *name* what dragged a derived number
 * down. "This cost is estimated" with nothing after it is the kind of warning
 * people learn to scroll past; "it leans on the invoice total, which someone
 * supplied" is a thing to go and check. Line numbers are 1-based here and
 * 0-based on the wire, exactly as they are everywhere else on this screen.
 */
export function describeField(path: string): string {
  const parts = path.split(".");
  if (parts.length === 3 && parts[0] === "lines") {
    const field = FIELD_WORDS[parts[2]] ?? parts[2];
    return `line ${Number(parts[1]) + 1}'s ${field}`;
  }
  return FIELD_WORDS[path] ?? path;
}

/** "the invoice total", "the invoice total and line 3's price", "..., and 2 more". */
export function describeFields(paths: string[]): string {
  const named = paths.slice(0, 2).map(describeField);
  const rest = paths.length - named.length;
  const listed = named.length === 2 ? `${named[0]} and ${named[1]}` : named[0];
  return rest > 0 ? `${listed}, and ${rest} more` : listed;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-08-21" renders "21 Aug 2026". String ops only - no timezone drift. */
export function formatDate(isoDate: string): string {
  const [year, month, day] = isoDate.split("T")[0].split("-");
  const monthIndex = Number(month) - 1;
  if (!year || !day || !MONTHS[monthIndex]) return isoDate;
  return `${Number(day)} ${MONTHS[monthIndex]} ${year}`;
}

/**
 * "7.2 points" for a gap between two percentages the API already subtracted
 * (M9 WP-93). String operations only, like everything else here: the API's
 * one-decimal string rides through, and nothing is parsed or divided.
 */
export function points(value: string): string {
  const one = value === "1" || value === "1.0" || value === "-1" || value === "-1.0";
  return `${value} ${one ? "point" : "points"}`;
}

export const STATUS_LABEL: Record<InvoiceStatus, string> = {
  draft: "Draft",
  awaiting_confirm: "To confirm",
  confirmed: "Confirmed",
  needs_review: "Needs approval",
  dismissed: "Dismissed",
};

export const PAYMENT_LABEL: Record<PaymentKind, string> = {
  credit: "Credit",
  cash: "Cash",
};
