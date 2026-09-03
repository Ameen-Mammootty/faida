import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * M7 WP-74: the mock store keeps the server's rules for the cash gate word
 * for word, so offline QA exercises the same sentences and the same status
 * moves the API makes. Money is never computed here - only status,
 * payment_kind and the refusal sentences are asserted.
 */

async function freshStore() {
  vi.resetModules();
  return import("../mock/store");
}

const CASH_HOLD = "inv-1003"; // Gulf Fresh, cash, needs_review
const CASH_COPY = "inv-1005"; // the same paper again: cash and a held duplicate
const CREDIT_COPY = "inv-1004"; // Al Madina's double-send, credit
const AWAITING = "inv-1002"; // Al Seeb, credit, awaiting_confirm

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

describe("the approve door in mock mode", () => {
  it("approves a cash hold with a reason and refuses a second click with the fresh status", async () => {
    const store = await freshStore();
    const detail = await store.mockApproveInvoice(CASH_HOLD, "Paid from the till, slip attached");
    expect(detail.status).toBe("confirmed");
    expect(detail.confirmed_at).not.toBeNull();
    expect(detail.payment_kind).toBe("cash");

    await expect(store.mockApproveInvoice(CASH_HOLD, "again")).rejects.toMatchObject({
      status: 409,
      message: "invoice is already confirmed",
    });
  });

  it("refuses a blank reason and writes nothing", async () => {
    const store = await freshStore();
    await expect(store.mockApproveInvoice(CASH_HOLD, "   ")).rejects.toMatchObject({
      status: 422,
    });
    expect((await store.mockGetInvoice(CASH_HOLD)).status).toBe("needs_review");
  });

  it("refuses anything that is not cash, naming confirm", async () => {
    const store = await freshStore();
    await expect(store.mockApproveInvoice(AWAITING, "why not")).rejects.toMatchObject({
      status: 409,
      message: "invoice is paid by credit, not cash; confirm it instead",
    });
    await store.mockDismissInvoice(CASH_COPY);
    await expect(store.mockApproveInvoice(CASH_COPY, "late")).rejects.toMatchObject({
      status: 409,
      message: "invoice is dismissed; a dismissed copy cannot be approved",
    });
  });

  it("approves a cash paper that is also a held duplicate", async () => {
    const store = await freshStore();
    const before = await store.mockGetInvoice(CASH_COPY);
    expect(before.duplicate_of_invoice_id).toBe(CASH_HOLD);
    expect(before.payment_kind).toBe("cash");
    const detail = await store.mockApproveInvoice(CASH_COPY, "Second delivery the same day");
    expect(detail.status).toBe("confirmed");
    // The original is untouched.
    expect((await store.mockGetInvoice(CASH_HOLD)).status).toBe("needs_review");
  });
});

describe("confirm and the cash gate in mock mode", () => {
  it("refuses a cash hold and names the approve door", async () => {
    const store = await freshStore();
    await expect(store.mockConfirmInvoice(CASH_HOLD)).rejects.toMatchObject({
      status: 409,
      message: "invoice is paid in cash; approve it with a reason instead",
    });
  });

  it("still confirms a credit duplicate hold", async () => {
    const store = await freshStore();
    expect((await store.mockConfirmInvoice(CREDIT_COPY)).status).toBe("confirmed");
  });
});

describe("payment_kind as a correction in mock mode", () => {
  const paidBy = (value: string) => [{ line_index: null, field: "payment_kind" as const, value }];

  it("cash to credit lifts a cash hold back to awaiting_confirm, stamped as a screen correction", async () => {
    const store = await freshStore();
    const detail = await store.mockPatchInvoiceFields(CASH_HOLD, paidBy("credit"));
    expect(detail.payment_kind).toBe("credit");
    expect(detail.status).toBe("awaiting_confirm");
    expect(detail.provenance.payment_kind.origin).toBe("corrected_screen");
    expect(detail.provenance.total.origin).toBe("extracted");
    // An ordinary paper now: confirm works, approve does not.
    await expect(store.mockApproveInvoice(CASH_HOLD, "x")).rejects.toMatchObject({ status: 409 });
    expect((await store.mockConfirmInvoice(CASH_HOLD)).status).toBe("confirmed");
  });

  it("credit to cash holds an awaiting paper", async () => {
    const store = await freshStore();
    const detail = await store.mockPatchInvoiceFields(AWAITING, paidBy("Cash"));
    expect(detail.payment_kind).toBe("cash");
    expect(detail.status).toBe("needs_review");
    await expect(store.mockConfirmInvoice(AWAITING)).rejects.toMatchObject({ status: 409 });
  });

  it("a cash duplicate corrected to credit stays held", async () => {
    const store = await freshStore();
    const detail = await store.mockPatchInvoiceFields(CASH_COPY, paidBy("credit"));
    expect(detail.payment_kind).toBe("credit");
    expect(detail.status).toBe("needs_review");
  });

  it("refuses anything but cash or credit, and a line_index on the header field", async () => {
    const store = await freshStore();
    await expect(store.mockPatchInvoiceFields(AWAITING, paidBy("cheque"))).rejects.toMatchObject({
      status: 422,
      message: `'cheque' is not a payment kind: send "cash" or "credit"`,
    });
    await expect(
      store.mockPatchInvoiceFields(AWAITING, [
        { line_index: 0, field: "payment_kind", value: "cash" },
      ]),
    ).rejects.toMatchObject({ status: 422 });
    expect((await store.mockGetInvoice(AWAITING)).status).toBe("awaiting_confirm");
  });
});
