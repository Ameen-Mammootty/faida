import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * M9 WP-87: the mock store keeps the API's supplier door word for word - the
 * pointer on every paper, the picker's source, the two spellings of one
 * correction through PATCH, the alias learnt on confirm and the collision
 * refused in the API's own sentence - so offline QA walks the same path the
 * screen walks against the real thing. No money is computed here; what is
 * asserted is where a paper is filed, what its lines snap to, and the words.
 */

async function freshStore() {
  vi.resetModules();
  return import("../mock/store");
}

const LOOKALIKE_PAPER = "inv-1009"; // printed "AL MADINA FOODSTUFF TRDG LLC", booked under the lookalike
const SEEB_PAPER = "inv-1002"; // printed exactly its supplier's catalog name
const UNBOOKED_PAPER = "inv-1003"; // Gulf Fresh: no supplier attached
const MADINA = "sup-01";
const LOOKALIKE = "sup-03";

const pick = (supplierId: string) => [{ line_index: null, field: "supplier" as const, value: supplierId }];
const name = (text: string) => [{ line_index: null, field: "supplier_name" as const, value: text }];

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

describe("the supplier on every paper", () => {
  it("is on the list without the flag and on the detail with it", async () => {
    const store = await freshStore();
    const listed = (await store.mockListInvoices()).find((row) => row.id === LOOKALIKE_PAPER);
    expect(listed?.booked_under).toEqual({ id: LOOKALIKE, name: "Al Madina Trading Co." });
    expect(listed?.supplier_name).toBe("AL MADINA FOODSTUFF TRDG LLC");
    const detail = await store.mockGetInvoice(LOOKALIKE_PAPER);
    // The machine booked it: nothing a confirm would teach.
    expect(detail.booked_under).toEqual({
      id: LOOKALIKE,
      name: "Al Madina Trading Co.",
      learns_printed_name: false,
    });
    expect((await store.mockGetInvoice(UNBOOKED_PAPER)).booked_under).toBeNull();
  });

  it("lists the catalog by name with the printed names each answers to", async () => {
    const store = await freshStore();
    expect(await store.mockGetSuppliers()).toEqual([
      { id: MADINA, name: "Al Madina Foodstuff Trading LLC", aliases: ["Al Madina Foodstuff"] },
      { id: LOOKALIKE, name: "Al Madina Trading Co.", aliases: ["AL MADINA TRADING"] },
      { id: "sup-02", name: "Al Seeb Trading Co LLC", aliases: ["AL SEEB TRADING"] },
    ]);
  });
});

describe("the correction door", () => {
  it("re-points a paper and its lines find their items under the right vendor", async () => {
    const store = await freshStore();
    const before = await store.mockGetInvoice(LOOKALIKE_PAPER);
    expect(before.lines.map((line) => line.supplier_item_id)).toEqual([null, null]);

    const moved = await store.mockPatchInvoiceFields(LOOKALIKE_PAPER, pick(MADINA));
    expect(moved.booked_under).toEqual({
      id: MADINA,
      name: "Al Madina Foodstuff Trading LLC",
      learns_printed_name: true,
    });
    expect(moved.supplier_id).toBe(MADINA);
    // The printed name is evidence and is never overwritten by the choice.
    expect(moved.supplier_name).toBe("AL MADINA FOODSTUFF TRDG LLC");
    expect(moved.lines.map((line) => line.supplier_item_id)).toEqual(["si-2001", "si-2002"]);
    expect(moved.lines.map((line) => line.checks.snapped)).toEqual([true, true]);
    expect(moved.provenance.supplier_id).toMatchObject({ origin: "corrected_screen" });
    expect(moved.status).toBe("awaiting_confirm");

    // Moved to a vendor whose catalog has none of them: no items, and the
    // snap state says so.
    const back = await store.mockPatchInvoiceFields(LOOKALIKE_PAPER, pick(LOOKALIKE));
    expect(back.lines.map((line) => line.supplier_item_id)).toEqual([null, null]);
    expect(back.lines.map((line) => line.checks.snapped)).toEqual([false, false]);
  });

  it("says nothing will be learnt when the pick already answers to the printed name", async () => {
    const store = await freshStore();
    // A person picks the supplier the paper is printed as: known already.
    const same = await store.mockPatchInvoiceFields(SEEB_PAPER, pick("sup-02"));
    expect(same.booked_under?.learns_printed_name).toBe(false);
    const elsewhere = await store.mockPatchInvoiceFields(SEEB_PAPER, pick(LOOKALIKE));
    expect(elsewhere.booked_under?.learns_printed_name).toBe(true);
  });

  it("mints a new supplier by name and recognises the same name typed again", async () => {
    const store = await freshStore();
    const minted = await store.mockPatchInvoiceFields(UNBOOKED_PAPER, name("  Al Rawabi Dairy "));
    expect(minted.booked_under).toEqual({
      id: "sup-04",
      name: "Al Rawabi Dairy",
      learns_printed_name: true,
    });
    const again = await store.mockPatchInvoiceFields(UNBOOKED_PAPER, name("AL RAWABI DAIRY"));
    expect(again.booked_under?.id).toBe("sup-04");
    expect((await store.mockGetSuppliers()).map((supplier) => supplier.id)).toEqual([
      MADINA,
      LOOKALIKE,
      "sup-04",
      "sup-02",
    ]);
  });

  it("refuses the API's malformed corrections in the API's words", async () => {
    const store = await freshStore();
    await expect(
      store.mockPatchInvoiceFields(LOOKALIKE_PAPER, [
        { line_index: 0, field: "supplier", value: MADINA },
      ]),
    ).rejects.toMatchObject({
      status: 422,
      message: "field 'supplier' is a header field; line_index must be null",
    });
    await expect(store.mockPatchInvoiceFields(LOOKALIKE_PAPER, name("  "))).rejects.toMatchObject({
      status: 422,
      message: "field 'supplier_name' needs a value: a supplier id, or a name",
    });
    await expect(store.mockPatchInvoiceFields(LOOKALIKE_PAPER, pick("sup-99"))).rejects.toMatchObject({
      status: 404,
      message: "supplier sup-99 not found",
    });
  });

  it("is closed once the paper is confirmed", async () => {
    const store = await freshStore();
    await store.mockConfirmInvoice(LOOKALIKE_PAPER);
    await expect(store.mockPatchInvoiceFields(LOOKALIKE_PAPER, pick(MADINA))).rejects.toMatchObject({
      status: 409,
      message: "invoice is confirmed; only awaiting_confirm or needs_review invoices can be edited",
    });
  });
});

describe("what confirm teaches", () => {
  it("learns the printed name for a person's pick, and only then", async () => {
    const store = await freshStore();
    await store.mockPatchInvoiceFields(LOOKALIKE_PAPER, pick(MADINA));
    const confirmed = await store.mockConfirmInvoice(LOOKALIKE_PAPER);
    expect(confirmed.status).toBe("confirmed");
    expect(confirmed.booked_under).toEqual({
      id: MADINA,
      name: "Al Madina Foodstuff Trading LLC",
      learns_printed_name: false,
    });
    const madina = (await store.mockGetSuppliers()).find((supplier) => supplier.id === MADINA);
    expect(madina?.aliases).toEqual(["Al Madina Foodstuff", "AL MADINA FOODSTUFF TRDG LLC"]);
  });

  it("teaches nothing for a misclick put right, or for the machine's own booking", async () => {
    const store = await freshStore();
    await store.mockPatchInvoiceFields(LOOKALIKE_PAPER, pick(MADINA));
    await store.mockPatchInvoiceFields(LOOKALIKE_PAPER, pick(LOOKALIKE));
    // Back under the lookalike by a person's hand: that pick does teach,
    // because the lookalike has never seen this name either.
    expect((await store.mockConfirmInvoice(LOOKALIKE_PAPER)).booked_under?.learns_printed_name).toBe(false);
    const suppliers = await store.mockGetSuppliers();
    expect(suppliers.find((supplier) => supplier.id === MADINA)?.aliases).toEqual(["Al Madina Foodstuff"]);
    expect(suppliers.find((supplier) => supplier.id === LOOKALIKE)?.aliases).toEqual([
      "AL MADINA TRADING",
      "AL MADINA FOODSTUFF TRDG LLC",
    ]);

    // Untouched by anyone: the machine's booking, confirmed as it came.
    const fresh = await freshStore();
    await fresh.mockConfirmInvoice("inv-1001");
    const madina = (await fresh.mockGetSuppliers()).find((supplier) => supplier.id === MADINA);
    expect(madina?.aliases).toEqual(["Al Madina Foodstuff"]);
  });

  it("refuses to teach a name another supplier answers to, naming the holder, and writes nothing", async () => {
    const store = await freshStore();
    await store.mockPatchInvoiceFields(SEEB_PAPER, pick(LOOKALIKE));
    await expect(store.mockConfirmInvoice(SEEB_PAPER)).rejects.toMatchObject({
      status: 422,
      message:
        '"Al Seeb Trading Co LLC" is already how Al Seeb Trading Co LLC is known, so this paper ' +
        "cannot teach it as another supplier's name. Correct the supplier on the paper, or rename it.",
    });
    const after = await store.mockGetInvoice(SEEB_PAPER);
    expect(after.status).toBe("awaiting_confirm");
    expect(after.confirmed_at).toBeNull();
    expect(after.booked_under?.id).toBe(LOOKALIKE);
    const lookalike = (await store.mockGetSuppliers()).find((supplier) => supplier.id === LOOKALIKE);
    expect(lookalike?.aliases).toEqual(["AL MADINA TRADING"]);
  });
});
