import { describe, expect, it } from "vitest";
import { ApiError } from "../errors";
import {
  NEW_SUPPLIER,
  NOT_BOOKED,
  bookedUnderLine,
  correctionForName,
  correctionForPick,
  learnSentence,
  newSupplierDefault,
  optionLabel,
  pickerOptions,
  pickerValue,
  refusalText,
  savedNotice,
  supplierBlock,
} from "../supplierChoice";
import type { InvoiceDetail, InvoiceStatus, Supplier } from "../types";

/**
 * M9 WP-87: the supplier block's decisions, one case per rule. The API's own
 * payloads are the inputs - `booked_under` with its `learns_printed_name`
 * flag - and the words asserted here are the words the screen prints.
 */

const MADINA: Supplier = {
  id: "sup-01",
  name: "Al Madina Foodstuff Trading LLC",
  aliases: ["Al Madina Foodstuff"],
};
const LOOKALIKE: Supplier = {
  id: "sup-03",
  name: "Al Madina Trading Co.",
  aliases: ["AL MADINA TRADING"],
};
const SEEB: Supplier = { id: "sup-02", name: "Al Seeb Trading Co LLC", aliases: [] };
// The API's order: by name.
const SUPPLIERS = [MADINA, LOOKALIKE, SEEB];

function detail(overrides: Partial<InvoiceDetail> = {}): InvoiceDetail {
  const status: InvoiceStatus = "awaiting_confirm";
  return {
    id: "inv-1009",
    supplier_name: "AL MADINA FOODSTUFF TRDG LLC",
    supplier_id: "sup-03",
    booked_under: { id: "sup-03", name: "Al Madina Trading Co.", learns_printed_name: false },
    invoice_no: "INV-10517",
    invoice_date: "2026-09-02",
    currency: "AED",
    total: "383.25",
    status,
    created_at: "2026-09-02T10:05:00+00:00",
    branch_id: "br-01",
    branch_name: "Al Quoz",
    document_id: "doc-9009",
    duplicate_of_invoice_id: null,
    duplicate_of: null,
    subtotal: "365.00",
    tax: "18.25",
    payment_kind: "credit",
    confidence: {
      document: {
        arith: "passed",
        subtotal_check: "passed",
        line_sum: "365.00",
        expected: null,
        extracted: null,
        notes: [],
        status: "green",
      },
      lines: [],
    },
    provenance: {},
    confirmed_at: null,
    lines: [],
    document: null,
    image_url: null,
    ...overrides,
  };
}

describe("the Booked under line", () => {
  it("names the catalog supplier only when it is not the printed name", () => {
    expect(bookedUnderLine(detail())).toBe("Booked under Al Madina Trading Co.");
    expect(
      bookedUnderLine(
        detail({
          supplier_name: "Al Seeb Trading Co LLC",
          booked_under: { id: "sup-02", name: "Al Seeb Trading Co LLC", learns_printed_name: false },
        }),
      ),
    ).toBeNull();
  });

  it("treats case and spacing as the same words, and a missing supplier as nothing to say", () => {
    expect(
      bookedUnderLine({
        supplier_name: "AL SEEB  TRADING CO LLC",
        booked_under: { id: "sup-02", name: "Al Seeb Trading Co LLC" },
      }),
    ).toBeNull();
    expect(bookedUnderLine({ supplier_name: "Gulf Fresh", booked_under: null })).toBeNull();
    // A photo that gave no name still says where the paper went.
    expect(
      bookedUnderLine({ supplier_name: null, booked_under: { id: "sup-02", name: "Al Seeb" } }),
    ).toBe("Booked under Al Seeb");
  });
});

describe("the picker", () => {
  it("labels a supplier with the printed names it already answers to", () => {
    expect(optionLabel(MADINA)).toBe("Al Madina Foodstuff Trading LLC (also Al Madina Foodstuff)");
    expect(optionLabel(SEEB)).toBe("Al Seeb Trading Co LLC");
  });

  it("lists the suppliers in the API's order with New supplier last", () => {
    expect(pickerOptions(SUPPLIERS, detail().booked_under)).toEqual([
      { value: "sup-01", label: "Al Madina Foodstuff Trading LLC (also Al Madina Foodstuff)" },
      { value: "sup-03", label: "Al Madina Trading Co. (also AL MADINA TRADING)" },
      { value: "sup-02", label: "Al Seeb Trading Co LLC" },
      { value: NEW_SUPPLIER, label: "New supplier" },
    ]);
    expect(pickerValue(detail().booked_under)).toBe("sup-03");
  });

  it("offers a disabled placeholder while the paper has no supplier", () => {
    const options = pickerOptions(SUPPLIERS, null);
    expect(options[0]).toEqual({ value: NOT_BOOKED, label: "Not booked yet", disabled: true });
    expect(options.at(-1)).toEqual({ value: NEW_SUPPLIER, label: "New supplier" });
    expect(pickerValue(null)).toBe(NOT_BOOKED);
  });

  it("slots in a booked-under supplier the list does not carry, by name", () => {
    // Just minted through "New supplier": the list in memory predates it.
    const minted = { id: "sup-04", name: "Al Rawabi Dairy" };
    expect(pickerOptions(SUPPLIERS, minted).map((option) => option.value)).toEqual([
      "sup-01",
      "sup-03",
      "sup-04",
      "sup-02",
      NEW_SUPPLIER,
    ]);
    const last = { id: "sup-05", name: "Zam Zam Traders" };
    expect(pickerOptions(SUPPLIERS, last).map((option) => option.value)).toEqual([
      "sup-01",
      "sup-03",
      "sup-02",
      "sup-05",
      NEW_SUPPLIER,
    ]);
  });

  it("maps a pick to the supplier correction, and nothing else to anything", () => {
    const booked = detail().booked_under;
    expect(correctionForPick("sup-01", booked)).toEqual({
      line_index: null,
      field: "supplier",
      value: "sup-01",
    });
    expect(correctionForPick(NEW_SUPPLIER, booked)).toBeNull();
    expect(correctionForPick(NOT_BOOKED, null)).toBeNull();
    // Re-picking the supplier the paper is already under changes nothing.
    expect(correctionForPick("sup-03", booked)).toBeNull();
  });

  it("maps a typed name to the supplier_name correction, trimmed, and refuses a blank", () => {
    expect(correctionForName("  Al Rawabi Dairy ")).toEqual({
      line_index: null,
      field: "supplier_name",
      value: "Al Rawabi Dairy",
    });
    expect(correctionForName("   ")).toBeNull();
  });

  it("starts the New supplier name at the printed name", () => {
    expect(newSupplierDefault(detail())).toBe("AL MADINA FOODSTUFF TRDG LLC");
    expect(newSupplierDefault(detail({ supplier_name: null }))).toBe("");
  });
});

describe("the sentence about what confirm learns", () => {
  const learns = { id: "sup-01", name: "Al Madina Foodstuff Trading LLC", learns_printed_name: true };

  it("is said only when the API says the confirm would learn the name", () => {
    expect(learnSentence(detail({ booked_under: learns }))).toBe(
      'When you confirm, "AL MADINA FOODSTUFF TRDG LLC" will be learnt as a name for Al Madina Foodstuff Trading LLC.',
    );
    expect(learnSentence(detail())).toBeNull();
    expect(learnSentence(detail({ booked_under: null }))).toBeNull();
  });

  it("is said on a held paper too, and never once the paper stops being editable", () => {
    expect(learnSentence(detail({ status: "needs_review", booked_under: learns }))).not.toBeNull();
    expect(learnSentence(detail({ status: "confirmed", booked_under: learns }))).toBeNull();
    expect(learnSentence(detail({ status: "dismissed", booked_under: learns }))).toBeNull();
  });

  it("has nothing to quote when the photo gave no name", () => {
    expect(learnSentence(detail({ supplier_name: null, booked_under: learns }))).toBeNull();
  });

  it("never doubles a full stop after a name that carries its own", () => {
    const dotted = { id: "sup-03", name: "Al Madina Trading Co.", learns_printed_name: true };
    expect(learnSentence(detail({ booked_under: dotted }))).toBe(
      'When you confirm, "AL MADINA FOODSTUFF TRDG LLC" will be learnt as a name for Al Madina Trading Co.',
    );
    expect(savedNotice(detail({ booked_under: dotted }))).toBe(
      "Booked under Al Madina Trading Co. Its lines were matched against that supplier's usual items.",
    );
  });
});

describe("the whole block", () => {
  it("is a picker and no plain line while the paper is editable", () => {
    const block = supplierBlock(detail(), SUPPLIERS);
    expect(block.printed).toBe("AL MADINA FOODSTUFF TRDG LLC");
    expect(block.bookedUnder).toBeNull();
    expect(block.picker?.value).toBe("sup-03");
    expect(block.picker?.options.map((option) => option.value)).toEqual([
      "sup-01",
      "sup-03",
      "sup-02",
      NEW_SUPPLIER,
    ]);
    expect(block.sentence).toBeNull();
  });

  it("is the line only, once confirmed, and only when the names differ", () => {
    const confirmed = supplierBlock(
      detail({ status: "confirmed", confirmed_at: "2026-09-02T11:00:00+00:00" }),
      SUPPLIERS,
    );
    expect(confirmed.picker).toBeNull();
    expect(confirmed.sentence).toBeNull();
    expect(confirmed.bookedUnder).toBe("Al Madina Trading Co.");

    const asPrinted = supplierBlock(
      detail({
        status: "confirmed",
        supplier_name: "Al Seeb Trading Co LLC",
        booked_under: { id: "sup-02", name: "Al Seeb Trading Co LLC", learns_printed_name: false },
      }),
      SUPPLIERS,
    );
    expect(asPrinted.bookedUnder).toBeNull();
    expect(asPrinted.picker).toBeNull();
  });

  it("shows a paper with no supplier as not booked, with the picker open to book it", () => {
    const block = supplierBlock(detail({ supplier_id: null, booked_under: null }), SUPPLIERS);
    expect(block.picker?.value).toBe(NOT_BOOKED);
    expect(block.picker?.options[0].label).toBe("Not booked yet");
    expect(block.bookedUnder).toBeNull();
  });
});

describe("what the strip says", () => {
  it("names the filing and, when the status moved, why", () => {
    const booked = { id: "sup-01", name: "Al Madina Foodstuff Trading LLC", learns_printed_name: true };
    expect(savedNotice(detail({ booked_under: booked }))).toBe(
      "Booked under Al Madina Foodstuff Trading LLC. Its lines were matched against that supplier's usual items.",
    );
    expect(
      savedNotice(
        detail({ booked_under: booked, status: "needs_review", duplicate_of_invoice_id: "inv-1001" }),
      ),
    ).toBe(
      "Booked under Al Madina Foodstuff Trading LLC. Held: it reads as a copy of a paper already under that supplier.",
    );
    expect(
      savedNotice(detail({ booked_under: booked, status: "needs_review", payment_kind: "cash" })),
    ).toBe("Booked under Al Madina Foodstuff Trading LLC. Still held for the owner's approval.");
  });

  it("surfaces the API's refusal word for word and falls back for anything else", () => {
    const collision =
      '"Al Seeb Trading Co LLC" is already how Al Seeb Trading Co LLC is known, so this paper ' +
      "cannot teach it as another supplier's name. Correct the supplier on the paper, or rename it.";
    expect(refusalText(new ApiError(422, collision), "Couldn't confirm.")).toBe(collision);
    expect(refusalText(new TypeError("Failed to fetch"), "Couldn't confirm.")).toBe(
      "Couldn't confirm.",
    );
  });
});
