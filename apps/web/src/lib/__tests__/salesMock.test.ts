import { beforeEach, describe, expect, it, vi } from "vitest";
import type { SalesDayInput } from "../types";

/**
 * M8 WP-83: the mock sales door keeps the real door's decisions word for
 * word - the three outcomes, the 31-day body, the date window, the alias
 * that already names another branch, the file kept under its hash - so
 * offline QA exercises what the API will answer. The one money computation
 * is the net figure, done the door's way (amount / 1.05, half-up to a fil).
 */

async function freshDoor() {
  vi.resetModules();
  return import("../mock/sales");
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

const SOURCE = { sha256: "a".repeat(64), filename: "sales-week.csv" };

function itemDay(date: string, lines: { name: string; code?: string; qty?: string; amount: string }[]): SalesDayInput {
  return {
    branch_id: "br-01",
    business_date: date,
    granularity: "item",
    amount_basis: "inclusive",
    layout_id: null,
    source: SOURCE,
    lines: lines.map((line, position) => ({
      position,
      name: line.name,
      code: line.code ?? null,
      qty: line.qty ?? null,
      amount: line.amount,
    })),
  };
}

describe("the sales door in mock mode", () => {
  it("loads, then answers unchanged for the same rows reordered, then replaced with the previous figures", async () => {
    const door = await freshDoor();
    const first = await door.mockPostSalesDays({
      days: [itemDay("2026-08-25", [
        { name: "KARAK TEA FLASK 1L", code: "52a", qty: "14", amount: "490.00" },
        { name: "CHKN 65 DRY", code: "126", qty: "9", amount: "405.00" },
      ])],
    });
    expect(first.days[0]).toMatchObject({ outcome: "loaded", previous: null });
    expect(first.days[0].day).toMatchObject({ takings: "895.00", net_sales: "852.38", line_count: 2, vat_rate: "0.05" });

    const again = await door.mockPostSalesDays({
      days: [itemDay("2026-08-25", [
        { name: "chkn 65 dry", code: "126", qty: "9.000", amount: "405.0" },
        { name: "KARAK TEA FLASK 1L", code: "52a", qty: "14", amount: "490.00" },
      ])],
    });
    expect(again.days[0].outcome).toBe("unchanged");

    const changed = await door.mockPostSalesDays({
      days: [itemDay("2026-08-25", [{ name: "KARAK TEA FLASK 1L", code: "52a", qty: "14", amount: "490.00" }])],
    });
    expect(changed.days[0]).toMatchObject({
      outcome: "replaced",
      previous: { net_sales: "852.38", line_count: 2 },
    });
    expect(changed.days[0].day).toMatchObject({ takings: "490.00", net_sales: "466.67", line_count: 1 });

    const stored = await door.mockGetSalesDays("2026-08-25", "2026-08-25");
    expect(stored).toHaveLength(1);
    expect(stored[0].lines).toHaveLength(1);
  });

  it("takes the VAT out the door's way: inclusive 105.00 is net 100.00, exclusive stays", async () => {
    const door = await freshDoor();
    const inclusive = await door.mockPostSalesDays({
      days: [itemDay("2026-08-25", [{ name: "TEA", amount: "105.00" }, { name: "REFUND", amount: "-10.50" }])],
    });
    expect(inclusive.days[0].day).toMatchObject({ takings: "94.50", net_sales: "90.00" });
    const exclusive = await door.mockPostSalesDays({
      days: [{ ...itemDay("2026-08-26", [{ name: "TEA", amount: "100.00" }]), amount_basis: "exclusive" }],
    });
    expect(exclusive.days[0].day).toMatchObject({ takings: "100.00", net_sales: "100.00" });
  });

  it("stores a summary zero day as a day, refuses a 32-day body, and refuses the day after tomorrow", async () => {
    const door = await freshDoor();
    const closed = await door.mockPostSalesDays({
      days: [{ branch_id: "br-02", business_date: "2026-08-29", granularity: "summary", amount_basis: "inclusive", layout_id: null, source: SOURCE, amount: "0.00" }],
    });
    expect(closed.days[0].day).toMatchObject({ granularity: "summary", takings: "0.00", net_sales: "0.00", line_count: 0 });
    // A day total with money is the door's refusal since 2026-09-04: item-wise only.
    await expect(
      door.mockPostSalesDays({
        days: [{ branch_id: "br-02", business_date: "2026-08-30", granularity: "summary", amount_basis: "inclusive", layout_id: null, source: SOURCE, amount: "4525.50" }],
      }),
    ).rejects.toMatchObject({ status: 422, message: expect.stringContaining("item-wise exports for now") });

    const many = Array.from({ length: 32 }, (_, index) =>
      itemDay(`2026-07-${String(index + 1).padStart(2, "0")}`.slice(0, 10), [{ name: "TEA", amount: "1.00" }]),
    );
    many[31].business_date = "2026-08-01";
    await expect(door.mockPostSalesDays({ days: many })).rejects.toMatchObject({ status: 422 });

    const tomorrow = new Date(Date.now() + 86_400_000).toISOString().slice(0, 10);
    const dayAfter = new Date(Date.now() + 2 * 86_400_000).toISOString().slice(0, 10);
    await expect(door.mockPostSalesDays({ days: [itemDay(tomorrow, [{ name: "TEA", amount: "1.00" }])] })).resolves.toBeTruthy();
    await expect(door.mockPostSalesDays({ days: [itemDay(dayAfter, [{ name: "TEA", amount: "1.00" }])] })).rejects.toMatchObject({
      status: 422,
      message: expect.stringContaining("after tomorrow"),
    });
    await expect(door.mockPostSalesDays({ days: [{ ...itemDay("2026-08-25", [{ name: "TEA", amount: "1.00" }]), branch_id: "br-99" }] })).rejects.toMatchObject({ status: 404 });
  });

  it("saves a layout once under the till's name with the API's header key, and updates it on the second call", async () => {
    const door = await freshDoor();
    const columns = { branch: "Outlet", date: "Date", code: "PLU", item: "Item", qty: "Qty", amount: "Amount" };
    const first = await door.mockSaveSalesLayout({ name: "Main till", columns, amount_basis: "inclusive", date_order: "dmy" });
    expect(first.header_key).toBe("amount|date|item|outlet|plu|qty");
    const second = await door.mockSaveSalesLayout({ name: "main till", columns, amount_basis: "exclusive", date_order: "dmy" });
    expect(second.id).toBe(first.id);
    expect(second.amount_basis).toBe("exclusive");
    expect(await door.mockGetSalesLayouts()).toHaveLength(1);
  });

  it("teaches an alias once and refuses one that already names another branch", async () => {
    const door = await freshDoor();
    const alias = await door.mockAddBranchAlias("br-01", "QUSAIS 1");
    expect(alias).toMatchObject({ branch_id: "br-01", alias_key: "qusais 1" });
    expect((await door.mockGetBranches()).find((branch) => branch.id === "br-01")?.aliases).toEqual(["QUSAIS 1"]);
    await expect(door.mockAddBranchAlias("br-02", "qusais 1")).rejects.toMatchObject({ status: 409 });
    expect((await door.mockAddBranchAlias("br-01", "QUSAIS 1")).id).toBe(alias.id);
  });

  it("keeps the file under its own hash and answers the same hash for the same bytes", async () => {
    const door = await freshDoor();
    const bytes = "Outlet,Date,Amount\nA,25/08/2026,1\n";
    const first = await door.mockPostSalesFile(new File([bytes], "a.csv"));
    const second = await door.mockPostSalesFile(new File([bytes], "b.csv"));
    expect(first.sha256).toMatch(/^[0-9a-f]{64}$/);
    expect(second.sha256).toBe(first.sha256);
    expect(second.filename).toBe("a.csv");
  });
});
