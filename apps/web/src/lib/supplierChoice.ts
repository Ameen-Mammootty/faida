/**
 * Every decision the review screen's supplier block renders (M9 WP-87), as
 * pure functions over the API's own payload, so each one has a vitest case:
 * there is no component-rendering test capability, and a choice left inside
 * React would be untested by construction.
 *
 * The block is two header fields of the evidence card. "Supplier" is the
 * printed name as read, never rewritten by anything here. "Booked under" is
 * where the paper is filed - a picker while the paper is editable, listing
 * the tenant's suppliers with the printed names each already answers to and
 * "New supplier" last; plain text once it is not, and then only when the two
 * names differ. Under the fields, one sentence says what the confirm will
 * teach, exactly when the API says it will.
 *
 * Nothing here decides whether a name is "the same" as a catalog name in the
 * API's sense. That test (`matching.known_as`) lives on the API, which sends
 * its answer as `booked_under.learns_printed_name`; the one comparison made
 * here is a display rule for whether printing the catalog name under the
 * printed one would merely repeat it.
 */

import { ApiError } from "./errors";
import type {
  BookedUnder,
  Correction,
  InvoiceDetail,
  InvoiceStatus,
  InvoiceSummary,
  Supplier,
} from "./types";

/** The picker's value for "New supplier": never a supplier id, so it can
 * never be sent as one. */
export const NEW_SUPPLIER = "new";

/** The picker's value while the paper has no supplier: the disabled
 * placeholder, the way "Paid by" offers "Not read". */
export const NOT_BOOKED = "";

export interface PickerOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface Picker {
  /** The current selection: the booked-under supplier's id, or NOT_BOOKED. */
  value: string;
  options: PickerOption[];
}

export interface SupplierBlock {
  /** The printed name, as read. Null when the photo gave none. */
  printed: string | null;
  /** The catalog name to show as a plain "Booked under" field: only once the
   * paper is no longer editable (the picker carries it before that), and
   * only when it differs from the printed name. */
  bookedUnder: string | null;
  /** The "Booked under" picker, while the paper is editable. */
  picker: Picker | null;
  /** "When you confirm, ..." - exactly when the API says the confirm would
   * teach the printed name to the chosen supplier, and never after. */
  sentence: string | null;
}

const EDITABLE: ReadonlySet<InvoiceStatus> = new Set<InvoiceStatus>([
  "awaiting_confirm",
  "needs_review",
]);

export function isEditable(status: InvoiceStatus): boolean {
  return EDITABLE.has(status);
}

/** A sentence that ends in a catalog name ends in one full stop, whether or
 * not the name carries its own ("Al Madina Trading Co."). */
function sentence(text: string): string {
  return text.endsWith(".") ? text : `${text}.`;
}

/** Whether two names read as the same words on a screen: case and spacing
 * aside. A display rule only - the API's `same_name` decides the chat line
 * and `known_as` decides what a confirm learns; this only decides whether
 * writing the catalog name under the printed one would repeat it. */
function readsTheSame(a: string | null, b: string): boolean {
  if (a === null) return false;
  const fold = (name: string) => name.toLowerCase().split(/\s+/).filter(Boolean).join(" ");
  return fold(a) === fold(b);
}

/**
 * "Booked under <catalog name>" for a list row, or null when the paper has
 * no supplier or is printed the way its supplier is named. The list shows
 * nothing else about the supplier.
 */
export function bookedUnderLine(
  invoice: Pick<InvoiceSummary, "supplier_name" | "booked_under">,
): string | null {
  const booked = invoice.booked_under;
  if (booked === null || readsTheSame(invoice.supplier_name, booked.name)) return null;
  return `Booked under ${booked.name}`;
}

/** A supplier's label in the picker: its catalog name, and in brackets the
 * printed names it already answers to, so two lookalike companies can be
 * told apart by the papers each has been receiving. */
export function optionLabel(supplier: Pick<Supplier, "name" | "aliases">): string {
  return supplier.aliases.length === 0
    ? supplier.name
    : `${supplier.name} (also ${supplier.aliases.join(", ")})`;
}

/**
 * The picker's options: the placeholder while nothing is booked, the tenant's
 * suppliers in the API's order (by name), and "New supplier" last. A
 * booked-under supplier the list does not carry - one just minted through
 * "New supplier", or a list that has not arrived - is slotted in by name so
 * the picker can always show the paper's own filing.
 */
export function pickerOptions(suppliers: Supplier[], booked: BookedUnder | null): PickerOption[] {
  const rows: Pick<Supplier, "id" | "name" | "aliases">[] = [...suppliers];
  if (booked !== null && !rows.some((supplier) => supplier.id === booked.id)) {
    const at = rows.findIndex((supplier) => supplier.name.localeCompare(booked.name) > 0);
    rows.splice(at === -1 ? rows.length : at, 0, { ...booked, aliases: [] });
  }
  const options: PickerOption[] = rows.map((supplier) => ({
    value: supplier.id,
    label: optionLabel(supplier),
  }));
  if (booked === null) {
    options.unshift({ value: NOT_BOOKED, label: "Not booked yet", disabled: true });
  }
  options.push({ value: NEW_SUPPLIER, label: "New supplier" });
  return options;
}

export function pickerValue(booked: BookedUnder | null): string {
  return booked === null ? NOT_BOOKED : booked.id;
}

/**
 * The correction a pick sends, or null when the pick is not a supplier:
 * "New supplier" reveals the name field instead, the placeholder is not a
 * choice, and re-picking the supplier the paper is already under sends
 * nothing (the API would stamp a correction that changed nothing).
 */
export function correctionForPick(value: string, booked: BookedUnder | null): Correction | null {
  if (value === NEW_SUPPLIER || value === NOT_BOOKED) return null;
  if (booked !== null && value === booked.id) return null;
  return { line_index: null, field: "supplier", value };
}

/** The correction "New supplier" sends, or null for a blank name. The API
 * trims the name the way a catalog name is trimmed; here only the blank is
 * refused, so the button stays disabled rather than earning a 422. */
export function correctionForName(name: string): Correction | null {
  const trimmed = name.trim();
  return trimmed === "" ? null : { line_index: null, field: "supplier_name", value: trimmed };
}

/** What the "New supplier" name field starts with: the printed name, which
 * is the name a new vendor almost always has. */
export function newSupplierDefault(invoice: Pick<InvoiceDetail, "supplier_name">): string {
  return invoice.supplier_name ?? "";
}

/**
 * The one sentence about what confirming teaches. Shown only while the paper
 * is still editable and only when the API says the confirm would learn the
 * printed name for the chosen supplier - never composed from a name
 * comparison made here.
 */
export function learnSentence(
  invoice: Pick<InvoiceDetail, "status" | "supplier_name" | "booked_under">,
): string | null {
  const booked = invoice.booked_under;
  if (!isEditable(invoice.status) || booked === null || !booked.learns_printed_name) return null;
  if (invoice.supplier_name === null) return null;
  return sentence(
    `When you confirm, "${invoice.supplier_name}" will be learnt as a name for ${booked.name}`,
  );
}

/** The whole block, from one detail payload and the suppliers list. */
export function supplierBlock(invoice: InvoiceDetail, suppliers: Supplier[]): SupplierBlock {
  const editable = isEditable(invoice.status);
  return {
    printed: invoice.supplier_name,
    bookedUnder: editable ? null : (bookedUnderLine(invoice) && invoice.booked_under!.name),
    picker: editable
      ? {
          value: pickerValue(invoice.booked_under),
          options: pickerOptions(suppliers, invoice.booked_under),
        }
      : null,
    sentence: learnSentence(invoice),
  };
}

/**
 * What the status strip says after a supplier correction saved. The API
 * re-snapped the lines against the chosen supplier's catalog and re-asked
 * whether the paper is a copy, so the sentence names the filing and, when
 * the status moved, why.
 */
export function savedNotice(updated: Pick<InvoiceDetail, "status" | "booked_under" | "payment_kind" | "duplicate_of_invoice_id">): string {
  const filed = sentence(`Booked under ${updated.booked_under?.name ?? "a new supplier"}`);
  if (updated.status === "needs_review" && updated.duplicate_of_invoice_id !== null) {
    return `${filed} Held: it reads as a copy of a paper already under that supplier.`;
  }
  if (updated.status === "needs_review" && updated.payment_kind === "cash") {
    return `${filed} Still held for the owner's approval.`;
  }
  return `${filed} Its lines were matched against that supplier's usual items.`;
}

/** The API's own sentence, word for word, or the fallback for anything that
 * was not an API answer - the same rule the rest of the screen follows for
 * every refusal, including the 422 a confirm gives when the printed name is
 * already another supplier's. */
export function refusalText(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}
