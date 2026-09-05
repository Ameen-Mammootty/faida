import { beforeEach, describe, expect, it, vi } from "vitest";
import type { SalesDayInput } from "../types";

/**
 * M8 WP-84: the mock of the two sales reads and the three till-name doors
 * keeps `ratio.py`'s decisions word for word against the days the mock door
 * loaded and the mock store's own papers, so offline QA of the screen
 * exercises what the API will answer: the labels and their sentences, the
 * ranking, the "No branch" group, the chain total, the period refusals, and
 * coverage moving on a keystroke and moving back on the reverse gear.
 */

async function fresh() {
  vi.resetModules();
  return import("../mock/sales");
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

const SOURCE = { sha256: "b".repeat(64), filename: "qa-week.csv" };

function day(
  branch: string,
  date: string,
  lines: { name: string; code?: string; amount: string }[],
): SalesDayInput {
  return {
    branch_id: branch,
    business_date: date,
    granularity: "item",
    amount_basis: "inclusive",
    layout_id: null,
    source: SOURCE,
    lines: lines.map((line, position) => ({
      position,
      name: line.name,
      code: line.code ?? null,
      qty: null,
      amount: line.amount,
    })),
  };
}

const WEEK = ["2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21", "2026-08-22", "2026-08-23"];

async function loadWeek(door: Awaited<ReturnType<typeof fresh>>) {
  await door.mockPostSalesDays({
    days: [
      ...WEEK.map((date) => day("br-01", date, [{ name: "KARAK TEA CUP", code: "101", amount: "3150.00" }])),
      day("br-03", "2026-08-19", [
        { name: "NIDO SHAKE", code: "103", amount: "1050.00" },
        { name: "DELIVERY CHARGE", code: "DLV", amount: "5.25" },
        { name: "FLASK 1L", code: "F1", amount: "10.50" },
        { name: "NIDO SHAKE", code: "103", amount: "-10.50" },
      ]),
    ],
  });
}

describe("the branch read in mock mode", () => {
  it("answers the empty state before anything is loaded: today's 28 days, no newest day, no ratio anywhere", async () => {
    const door = await fresh();
    const read = await door.mockGetSalesBranches();
    // `sales_through` null is the one fact the screen's empty state is decided
    // on. A branch with confirmed papers inside today's window still reads
    // incomplete ("no sales loaded ..."), exactly as the API does; the rows
    // are not asserted by label here because the fixtures' dates are fixed
    // and today moves.
    expect(read.period).toMatchObject({ days: 28, default: true, sales_through: null, months: [] });
    expect(read.rows).toHaveLength(3);
    expect(read.rows.every((row) => row.net_sales === null && row.ratio_pct === null)).toBe(true);
    expect(["incomplete", "unavailable"]).toContain(read.total.quality);
    expect(read.total.ratio_pct).toBeNull();
  });

  it("ranks the branches, labels each by its gaps in the API's words, and reconciles the total", async () => {
    const door = await fresh();
    await loadWeek(door);
    const read = await door.mockGetSalesBranches("2026-08-17", "2026-08-23");
    expect(read.period).toMatchObject({ from: "2026-08-17", to: "2026-08-23", days: 7, default: false, sales_through: "2026-08-23", months: ["2026-08"] });

    expect(read.rows.map((row) => row.branch_name)).toEqual(["Deira", "Al Quoz", "Karama"]);

    const [deira, alQuoz, karama] = read.rows;
    // Deira: one loaded day, one confirmed paper dated that day, nothing pending.
    expect(deira).toMatchObject({
      window: { from: "2026-08-19", to: "2026-08-19", days: 1 },
      net_sales: "1005.00",
      takings: "1055.25",
      purchases: "540.00",
      ratio_pct: "53.7",
      quality: "reliable_with_limitations",
      notes: ["1 delivery in this window"],
      deliveries: 1,
    });
    expect(deira.days[0].invoices[0]).toMatchObject({
      invoice_id: "inv-1007",
      net_purchase: "540.00",
      total: "567.00",
      tax: "27.00",
      quality: "reliable_with_limitations",
    });

    // Al Quoz: seven days, one confirmed paper, four papers on their way.
    expect(alQuoz).toMatchObject({
      window: { from: "2026-08-17", to: "2026-08-23", days: 7 },
      net_sales: "21000.00",
      purchases: "1255.00",
      ratio_pct: "6.0",
      quality: "estimated",
      notes: ["1 invoice awaiting confirm", "3 invoices held for review", "1 delivery in this window"],
      days_loaded: 7,
      days_missing: 0,
    });
    expect(alQuoz.pending.map((p) => [p.invoice_id, p.status, p.placed_on])).toEqual([
      ["inv-1001", "awaiting_confirm", "2026-08-21"],
      ["inv-1004", "needs_review", "2026-08-21"],
      ["inv-1003", "needs_review", "2026-08-22"],
      ["inv-1005", "needs_review", "2026-08-22"],
    ]);
    expect(alQuoz.days.find((d) => d.business_date === "2026-08-18")?.invoices[0]).toMatchObject({
      invoice_id: "inv-1006",
      net_purchase: "1255.00",
      total: "1317.75",
      tax: "62.75",
    });

    // Karama: nothing loaded, a paper awaiting confirm riding along.
    expect(karama).toMatchObject({
      net_sales: null,
      purchases: "0.00",
      ratio_pct: null,
      quality: "unavailable",
      notes: ["no sales loaded and no confirmed purchases 17-23 Aug", "1 invoice awaiting confirm"],
    });

    // The paper with no branch is counted in the total and ranked nowhere.
    expect(read.unassigned).toMatchObject({ count: 1, purchases: "200.00" });
    // A market receipt with no VAT line: the tax is null on the wire, as the API sends it.
    expect(read.unassigned.invoices[0]).toMatchObject({ invoice_id: "inv-1008", net_purchase: "200.00", total: "200.00", tax: null });
    expect(read.total).toEqual({
      net_sales: "22005.00",
      purchases: "1995.00",
      ratio_pct: "9.1",
      quality: "incomplete",
      notes: ["1 of 3 branches with nothing loaded", "1 invoice on no branch, counted in the total"],
    });
  });

  it("defaults to the 28 days ending on the newest loaded day, and a branch with sales but no papers reads incomplete", async () => {
    const door = await fresh();
    await loadWeek(door);
    await door.mockPostSalesDays({ days: [day("br-02", "2026-08-23", [{ name: "KARAK TEA CUP", amount: "105.00" }])] });
    const read = await door.mockGetSalesBranches();
    expect(read.period).toMatchObject({ from: "2026-07-27", to: "2026-08-23", days: 28, default: true, months: ["2026-08"] });
    const karama = read.rows.find((row) => row.branch_name === "Karama");
    // One loaded day clips the window to 23 Aug, so the paper placed on 22 Aug
    // is outside it and not pending here - the API's rule.
    expect(karama).toMatchObject({
      quality: "incomplete",
      ratio_pct: null,
      window: { from: "2026-08-23", to: "2026-08-23", days: 1 },
      notes: ["no confirmed purchases 23 Aug"],
    });
    expect(read.total.notes).toEqual(["1 of 3 branches incomplete", "1 invoice on no branch, counted in the total"]);
  });

  it("moves when a paper is confirmed on the review screen - the stage's own gesture", async () => {
    const door = await fresh();
    const store = await import("../mock/store");
    await loadWeek(door);
    await door.mockPostSalesDays({ days: [day("br-02", "2026-08-22", [{ name: "KARAK TEA CUP", amount: "2100.00" }])] });
    await store.mockConfirmInvoice("inv-1002");
    const karama = (await door.mockGetSalesBranches("2026-08-17", "2026-08-23")).rows.find((row) => row.branch_name === "Karama");
    expect(karama).toMatchObject({ purchases: "270.25", ratio_pct: "13.5", quality: "reliable_with_limitations" });
  });

  it("refuses the ranges the API refuses, in its words", async () => {
    const door = await fresh();
    await expect(door.mockGetSalesBranches("2026-08-01")).rejects.toMatchObject({ status: 422, message: "send both 'from' and 'to', or neither" });
    await expect(door.mockGetSalesBranches("2026-08-31", "2026-08-01")).rejects.toMatchObject({ status: 422, message: "'from' is after 'to'" });
    await expect(door.mockGetSalesBranches("2026-01-01", "2026-06-30")).rejects.toMatchObject({ status: 422, message: expect.stringContaining("at most 92") });
  });
});

describe("coverage and the three doors in mock mode", () => {
  it("proposes but never maps, and the costed share follows an approval, an unmap and an exclusion", async () => {
    const door = await fresh();
    await loadWeek(door);
    const before = await door.mockGetSalesCoverage("2026-08-17", "2026-08-23");
    // 7 x 3000.00 of cups + 1000.00 of shakes + 5.00 delivery + 10.00 flask; the refund apart.
    expect(before).toMatchObject({
      sales_value: "22015.00",
      costed_value: "0.00",
      costed_pct: "0.0",
      uncosted: { incomplete_plate: "0.00", unmapped: "22015.00" },
      beside: { refunds: "-10.00", not_menu_items: "0.00" },
      mapped: [],
      excluded: [],
    });
    expect(before.queue.map((item) => item.name)).toEqual(["KARAK TEA CUP", "NIDO SHAKE", "FLASK 1L", "DELIVERY CHARGE"]);
    const cup = before.queue[0];
    expect(cup.proposals[0]).toMatchObject({ menu_item_id: "menu-1", name: "Karak Tea (Cup)" });
    expect(Number(cup.proposals[0].score)).toBeGreaterThanOrEqual(0.72);
    expect(before.queue.find((item) => item.name === "FLASK 1L")?.proposals).toEqual([]);
    expect(before.queue.find((item) => item.name === "NIDO SHAKE")?.proposals[0].name).toBe("Nido Shake");

    const mapped = await door.mockMapTillItem(cup.till_item_id, "menu-1");
    expect(mapped).toMatchObject({ id: cup.till_item_id, menu_item_id: "menu-1", menu_item_name: "Karak Tea (Cup)", excluded_at: null });
    const after = await door.mockGetSalesCoverage("2026-08-17", "2026-08-23");
    expect(after).toMatchObject({ costed_value: "21000.00", costed_pct: "95.4", estimated_points: "0.0" });
    expect(after.mapped[0]).toMatchObject({ name: "KARAK TEA CUP", menu_item_name: "Karak Tea (Cup)", plate_quality: "reliable_with_limitations" });
    expect(after.queue.map((item) => item.name)).toEqual(["NIDO SHAKE", "FLASK 1L", "DELIVERY CHARGE"]);

    // An estimated plate counts as costed and is named as estimated.
    const shake = after.queue[0];
    await door.mockMapTillItem(shake.till_item_id, "menu-3");
    expect(await door.mockGetSalesCoverage("2026-08-17", "2026-08-23")).toMatchObject({ costed_pct: "99.9", estimated_points: "4.5" });

    const delivery = after.queue.find((item) => item.name === "DELIVERY CHARGE")!;
    await door.mockExcludeTillItem(delivery.till_item_id);
    const excluded = await door.mockGetSalesCoverage("2026-08-17", "2026-08-23");
    expect(excluded.excluded.map((item) => item.name)).toEqual(["DELIVERY CHARGE"]);
    expect(excluded).toMatchObject({ sales_value: "22010.00", beside: { not_menu_items: "5.00" } });

    await door.mockUnmapTillItem(cup.till_item_id);
    const back = await door.mockGetSalesCoverage("2026-08-17", "2026-08-23");
    expect(back.queue.map((item) => item.name)).toEqual(["KARAK TEA CUP", "FLASK 1L"]);
    expect(back.costed_pct).toBe("4.5");
  });

  it("scores word order the API's way: the token-sorted arm lifts a swapped name to an exact match", async () => {
    const door = await fresh();
    await door.mockPostSalesDays({ days: [day("br-02", "2026-08-20", [{ name: "MANDI CHICKEN", amount: "105.00" }, { name: "TEA KARAK CUP", amount: "3.00" }])] });
    const coverage = await door.mockGetSalesCoverage("2026-08-17", "2026-08-23");
    expect(coverage.queue.find((item) => item.name === "MANDI CHICKEN")?.proposals[0]).toMatchObject({ name: "Chicken Mandi", score: "1.00" });
    expect(coverage.queue.find((item) => item.name === "TEA KARAK CUP")?.proposals[0]).toMatchObject({ name: "Karak Tea (Cup)", score: "1.00" });
  });

  it("refuses what the doors refuse: a foreign row, an archived item, an unmap of the unmapped, an exclusion of the mapped", async () => {
    const door = await fresh();
    const menu = await import("../mock/menu");
    await loadWeek(door);
    const queue = (await door.mockGetSalesCoverage("2026-08-17", "2026-08-23")).queue;
    const cup = queue[0];
    await expect(door.mockMapTillItem("till-9999", "menu-1")).rejects.toMatchObject({ status: 404 });
    await expect(door.mockMapTillItem(cup.till_item_id, "menu-9999")).rejects.toMatchObject({ status: 404 });
    await menu.mockArchiveMenuItem("menu-5");
    await expect(door.mockMapTillItem(cup.till_item_id, "menu-5")).rejects.toMatchObject({
      status: 409,
      message: "'Honey Cake' is archived: unarchive it on the menu first, or pick a live item",
    });
    await expect(door.mockUnmapTillItem(cup.till_item_id)).rejects.toMatchObject({ status: 409, message: "'KARAK TEA CUP' is not mapped to a menu item" });
    await door.mockMapTillItem(cup.till_item_id, "menu-1");
    await expect(door.mockExcludeTillItem(cup.till_item_id)).rejects.toMatchObject({
      status: 409,
      message: "'KARAK TEA CUP' is mapped to Karak Tea (Cup): unmap it first if it is not a menu item",
    });
  });
});
