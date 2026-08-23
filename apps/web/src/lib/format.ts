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
