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

/** Quantities are not money: "12.000" is "12", "2.500" is "2.5", "12" stays "12". */
export function quantity(value: string): string {
  if (!value.includes(".")) return value;
  return value.replace(/0+$/, "").replace(/\.$/, "");
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
