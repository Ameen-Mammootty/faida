/**
 * Display helpers. Money is rendered verbatim from the API's string values,
 * padded to two decimals by string operations only - never parsed to a
 * number, never rounded, never truncated (plan.md section 3).
 */

import type { InvoiceStatus, PaymentKind } from "./types";

/** "682.75" stays "682.75"; "54.5" renders "54.50"; "12" renders "12.00". */
export function money(value: string): string {
  const dot = value.indexOf(".");
  if (dot === -1) return `${value}.00`;
  const decimals = value.length - dot - 1;
  if (decimals >= 2) return value;
  return value + "0".repeat(2 - decimals);
}

/** Quantities are not money: render exactly as extracted. */
export function quantity(value: string): string {
  return value;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-08-21" renders "21 Aug 2026". String ops only - no timezone drift. */
export function formatDate(isoDate: string): string {
  const [year, month, day] = isoDate.split("T")[0].split("-");
  const monthIndex = Number(month) - 1;
  if (!year || !day || !MONTHS[monthIndex]) return isoDate;
  return `${Number(day)} ${MONTHS[monthIndex]} ${year}`;
}

export const STATUS_LABEL: Record<InvoiceStatus, string> = {
  draft: "Draft",
  awaiting_confirm: "To confirm",
  confirmed: "Confirmed",
  needs_review: "Needs approval",
};

export const PAYMENT_LABEL: Record<PaymentKind, string> = {
  credit: "Credit",
  cash: "Cash",
};

/**
 * Rounded AED for a headline figure (plan.md §3: rounded headline numbers,
 * exact figures only in detail). String and BigInt only - money never becomes
 * a float here. "1818.00" -> "1,818"; "42.60" -> "43".
 */
export function roundedMoney(value: string): string {
  const negative = value.startsWith("-");
  const [whole, fraction = ""] = value.replace("-", "").split(".");
  let units = BigInt(whole || "0");
  if (fraction.charCodeAt(0) >= 53) units += 1n; // first decimal digit >= 5
  const grouped = units.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return negative && units !== 0n ? `-${grouped}` : grouped;
}

/**
 * A cost per kilo / litre / piece. The API sends three decimals; a price
 * somebody says out loud has two ("AED 22.44 / kg"), but a piece cost under
 * one dirham is all decimals and rounding it to 0.03 would throw the number
 * away - so values below AED 1 keep what they were sent. String and BigInt
 * only: money never becomes a float (C4).
 */
export function unitCost(value: string): string {
  const [whole, fraction = ""] = value.split(".");
  if (whole === "0") return money(value);
  const digits = (fraction + "000").slice(0, 3);
  let cents = BigInt(whole) * 100n + BigInt(digits.slice(0, 2));
  if (digits.charCodeAt(2) >= 53) cents += 1n; // round half up, never down
  const text = cents.toString().padStart(3, "0");
  const units = text.slice(0, -2).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `${units}.${text.slice(-2)}`;
}

/** How a cost per base unit is said out loud: "/ kg", "/ litre", "each". */
export const DISPLAY_UNIT_LABEL: Record<string, string> = {
  kg: "/ kg",
  l: "/ litre",
  pc: "each",
};

/** Why a pack has no cost yet, and what to do about it - never a bare code. */
export const BLOCKED_LABEL: Record<string, string> = {
  unknown_pack: "Say what one pack holds",
  ambiguous_pack: "The name gives two pack sizes",
  no_price: "No confirmed price yet",
};

/** What the cost was derived from, for the reader who asks "says who?". */
export const BASIS_LABEL: Record<string, string> = {
  conversion: "from a stated conversion",
  unit: "priced by the unit",
  pack_size: "from the printed pack size",
  item_name: "from the pack size in the item name",
};
