import { describe, expect, it } from "vitest";
import { parseCsv } from "../csv";
import {
  applyLayout,
  committable,
  dayKey,
  driftSentence,
  guessColumns,
  guessDateOrder,
  headerKey,
  layoutKey,
  planDays,
  readDate,
  readSalesCsv,
  requestGroups,
  toDayInput,
  type PlannedDay,
  type ReadDay,
} from "../salesLoad";
import type { Branch, SalesDay, SalesLayout } from "../types";

/**
 * M8 WP-83: the loader's predictions, one case per row of the acceptance -
 * the header key, the saved layout applied by name and the drift stop, the
 * dates that read one way and the ones that stop, grouping and the
 * one-shape rule, and `planDays` against stored days.
 */

const BRANCHES: Branch[] = [
  { id: "b1", name: "Al Qusais Branch", timezone: "Asia/Dubai", aliases: ["QUSAIS 1"] },
  { id: "b2", name: "Al Nahda Branch", timezone: "Asia/Dubai", aliases: [] },
  { id: "b3", name: "Rolla Branch", timezone: "Asia/Dubai", aliases: [] },
];

const HEADER = ["Outlet", "Date", "PLU", "Item", "Qty", "Amount"];
const COLUMNS = { branch: "Outlet", date: "Date", code: "PLU", item: "Item", qty: "Qty", amount: "Amount" };

const LAYOUT: SalesLayout = {
  id: "l1",
  name: "Main till",
  header_key: "amount|date|item|outlet|plu|qty",
  columns: COLUMNS,
  amount_basis: "inclusive",
  date_order: "dmy",
  updated_at: "2026-09-03T18:00:00Z",
};

const TODAY = "2026-09-04";

function read(text: string, options: Partial<Parameters<typeof readSalesCsv>[3]> = {}) {
  const parsed = parseCsv(text);
  if (!parsed.ok) throw new Error(parsed.error);
  return readSalesCsv(parsed.header, parsed.rows, parsed.ragged, {
    columns: COLUMNS,
    dateOrder: "dmy",
    branches: BRANCHES,
    fileBranchId: null,
    today: TODAY,
    ...options,
  });
}

const WEEK =
  "Outlet,Date,PLU,Item,Qty,Amount\n" +
  "Al Qusais Branch,25/08/2026,52a,KARAK TEA FLASK 1L,14,490.00\n" +
  "Al Qusais Branch,25/08/2026,126,CHKN 65 DRY,9,405.00\n" +
  "Al Qusais Branch,26/08/2026,52a,KARAK TEA FLASK 1L,10,350.00\n" +
  "Al Nahda Branch,25/08/2026,52a,KARAK TEA FLASK 1L,3,105.00\n" +
  "Al Nahda Branch,27/08/2026,52a,KARAK TEA FLASK 1L,2,70.00\n" +
  "Total,,,,,1420.00\n";

describe("headerKey", () => {
  it("is order- and case-insensitive, and matches the API's key over the mapped names", () => {
    expect(headerKey(HEADER)).toBe("amount|date|item|outlet|plu|qty");
    expect(headerKey(["amount", "QTY", "Item", "plu", "date", "outlet"])).toBe(
      "amount|date|item|outlet|plu|qty",
    );
    expect(layoutKey(COLUMNS)).toBe("amount|date|item|outlet|plu|qty");
    expect(headerKey(["Net Sales (AED)", "Date", ""])).toBe("date|net sales aed");
  });

  it("guesses the pinned header's six columns", () => {
    expect(guessColumns(HEADER)).toEqual(COLUMNS);
  });
});

describe("applyLayout", () => {
  it("applies the saved layout to a matching file, reordered or not", () => {
    expect(applyLayout(HEADER, [LAYOUT])).toMatchObject({ kind: "apply", extras: [] });
    expect(applyLayout(["Amount", "Item", "Qty", "PLU", "Date", "Outlet"], [LAYOUT])).toMatchObject({
      kind: "apply",
    });
  });

  it("lets an extra unmapped column through and names it", () => {
    const decision = applyLayout([...HEADER, "Cashier"], [LAYOUT]);
    expect(decision).toMatchObject({ kind: "apply", extras: ["Cashier"] });
  });

  it("stops on a renamed mapped column and names what disappeared and what appeared", () => {
    const decision = applyLayout(["Outlet", "Date", "PLU", "Item", "Qty", "Net"], [LAYOUT]);
    expect(decision).toMatchObject({ kind: "drift", missing: ["Amount"], appeared: ["Net"] });
    if (decision.kind !== "drift") return;
    const sentence = driftSentence(decision);
    expect(sentence).toContain('"Amount"');
    expect(sentence).toContain('"Net"');
    expect(sentence).toContain("Main till");
  });

  it("asks which till when two layouts fit", () => {
    const second = { ...LAYOUT, id: "l2", name: "Second till", updated_at: "2026-09-04T00:00:00Z" };
    const decision = applyLayout(HEADER, [LAYOUT, second]);
    expect(decision.kind).toBe("choose");
    if (decision.kind !== "choose") return;
    expect(decision.layouts.map((layout) => layout.name)).toEqual(["Second till", "Main till"]);
  });

  it("is the mapping step with no layout saved", () => {
    expect(applyLayout(HEADER, [])).toEqual({ kind: "none" });
  });
});

describe("readDate", () => {
  it("reads 25/08/2026, 2026-08-25 and 25-08-2026 as one date", () => {
    for (const text of ["25/08/2026", "2026-08-25", "25-08-2026", "25.08.2026", "25 Aug 2026", "2026-08-25 14:02"]) {
      expect(readDate(text, "dmy")).toEqual({ ok: true, iso: "2026-08-25" });
    }
  });

  it("stops 5/7/26 because it reads two ways", () => {
    const result = readDate("5/7/26", "dmy");
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.problem).toContain("reads two ways");
  });

  it("stops 2026-25-08 because there is no month 25", () => {
    const result = readDate("2026-25-08", "ymd");
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.problem).toContain("no month 25");
  });

  it("stops a year-last date under a year-first layout, naming the fix", () => {
    const result = readDate("25/08/2026", "ymd");
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.problem).toContain("date order");
  });

  it("guesses the order from the first four-digit part", () => {
    expect(guessDateOrder(["25/08/2026", "26/08/2026"])).toBe("dmy");
    expect(guessDateOrder(["2026-08-25"])).toBe("ymd");
  });
});

describe("readSalesCsv", () => {
  it("groups rows into branch-days, sums takings exactly, skips the footer and counts it", () => {
    const result = read(WEEK);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.granularity).toBe("item");
    expect(result.skippedNoDate).toBe(1);
    const qusais25 = result.days.find((day) => day.key === "b1|2026-08-25");
    expect(qusais25).toMatchObject({ branchName: "Al Qusais Branch", takings: "895.00" });
    expect(qusais25?.lines.map((line) => line.name)).toEqual(["KARAK TEA FLASK 1L", "CHKN 65 DRY"]);
    expect(qusais25?.rows).toEqual([2, 3]);
  });

  it("fills an interior gap for a branch as the zero day it will load", () => {
    const result = read(WEEK);
    if (!result.ok) throw new Error(result.error);
    // The file runs 25-27 Aug; Al Qusais has no 27th, Al Nahda has no 26th.
    const gaps = result.days.filter((day) => day.gap).map((day) => day.key);
    expect(gaps).toEqual(["b1|2026-08-27", "b2|2026-08-26"]);
    const gap = result.days.find((day) => day.key === "b1|2026-08-27");
    expect(gap).toMatchObject({ granularity: "summary", amount: "0.00", takings: "0.00", problems: [] });
  });

  it("resolves a branch through its alias and blocks the rows of an unknown label", () => {
    const text =
      "Outlet,Date,PLU,Item,Qty,Amount\n" +
      "QUSAIS 1,25/08/2026,52a,KARAK TEA FLASK 1L,14,490.00\n" +
      "MUWAILAH,25/08/2026,52a,KARAK TEA FLASK 1L,1,35.00\n";
    const result = read(text);
    if (!result.ok) throw new Error(result.error);
    expect(result.days.find((day) => day.branchId === "b1")).toBeTruthy();
    expect(result.unknownBranches).toEqual(["MUWAILAH"]);
    const unknown = result.days.find((day) => day.branchLabel === "MUWAILAH");
    expect(unknown?.branchId).toBeNull();
    expect(unknown?.problems[0]).toContain('"MUWAILAH"');
  });

  it("stops a file with no item column at the mapping step, with the sentence", () => {
    // Item-wise only (the founder's call, 2026-09-04): a day-totals export
    // waits for the pilot, and the loader says so rather than guessing.
    const text =
      "Outlet,Date,Amount\n" +
      "Al Qusais Branch,25/08/2026,4525.50\n" +
      "Al Qusais Branch,26/08/2026,4100.00\n";
    const result = read(text, { columns: { branch: "Outlet", date: "Date", amount: "Amount" } });
    expect(result.ok).toBe(false);
    if (result.ok) throw new Error("a file with no item column read as sales");
    expect(result.error).toContain("item-wise exports for now");
    expect(result.error).toContain("comes with the pilot");
  });

  it("reads a closed-day row as a summary zero day, and a whole-file branch when there is no branch column", () => {
    const text = "Date,Item,Amount\n25/08/2026,KARAK,35.00\n26/08/2026,,0\n";
    const result = read(text, {
      columns: { date: "Date", item: "Item", amount: "Amount" },
      fileBranchId: "b3",
    });
    if (!result.ok) throw new Error(result.error);
    expect(result.days.map((day) => [day.key, day.granularity, day.takings])).toEqual([
      ["b3|2026-08-25", "item", "35.00"],
      ["b3|2026-08-26", "summary", "0.00"],
    ]);
  });

  it("blocks a row dated after tomorrow and one that reads two ways, by line", () => {
    const text =
      "Outlet,Date,PLU,Item,Qty,Amount\n" +
      "Al Qusais Branch,08/12/2026,52a,KARAK,1,35.00\n" +
      "Al Qusais Branch,5/7/26,52a,KARAK,1,35.00\n";
    const result = read(text);
    if (!result.ok) throw new Error(result.error);
    const future = result.days.find((day) => day.date === "2026-12-08");
    expect(future?.problems[0]).toContain("after tomorrow");
    const ambiguous = result.days.find((day) => day.date === "5/7/26");
    expect(ambiguous?.problems[0]).toContain("line 3");
    expect(ambiguous?.problems[0]).toContain("reads two ways");
  });

  it("refuses a file with a ragged row, naming the line", () => {
    const text = "Outlet,Date,PLU,Item,Qty,Amount\nAl Qusais Branch,25/08/2026,52a,KARAK,1\n";
    const result = read(text);
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.error).toContain("line 2");
  });

  it("refuses a negative-looking thousands separator and takes a refund row", () => {
    const text =
      "Outlet,Date,PLU,Item,Qty,Amount\n" +
      "Al Qusais Branch,25/08/2026,52a,KARAK,-1,-35.00\n" +
      "Al Qusais Branch,25/08/2026,52a,KARAK,40,\"1,400.00\"\n";
    const result = read(text);
    if (!result.ok) throw new Error(result.error);
    const day = result.days[0];
    expect(day.lines[0].amount).toBe("-35.00");
    expect(day.problems[0]).toContain("thousands separator");
  });
});

// --- planDays ---------------------------------------------------------------

function storedDay(overrides: Partial<SalesDay> = {}): SalesDay {
  return {
    id: "d1",
    branch_id: "b1",
    business_date: "2026-08-25",
    granularity: "item",
    amount_basis: "inclusive",
    vat_rate: "0.05",
    takings: "895.00",
    net_sales: "852.38",
    line_count: 2,
    layout_id: "l1",
    source_sha256: "abc",
    source_filename: "sales-week.csv",
    loaded_by: "user:1",
    loaded_at: "2026-09-03T18:00:00+00:00",
    lines: [
      { position: 0, name: "CHKN 65 DRY", code: "126", qty: "9.000", amount: "405.00", net_amount: "385.71", till_item_id: "t2" },
      { position: 1, name: "KARAK TEA FLASK 1L", code: "52a", qty: "14.000", amount: "490.00", net_amount: "466.67", till_item_id: "t1" },
    ],
    ...overrides,
  };
}

function week(): ReadDay[] {
  const result = read(WEEK);
  if (!result.ok) throw new Error(result.error);
  return result.days;
}

describe("planDays", () => {
  it("predicts unchanged for the same rows stored in another order and format", () => {
    const planned = planDays(week(), [storedDay()], "inclusive");
    const day = planned.find((row) => row.key === "b1|2026-08-25");
    expect(day?.plan).toMatchObject({ kind: "unchanged", shrinking: false });
    expect(dayKey("item", "inclusive", storedDay().lines, null)).toBe(
      dayKey("item", "inclusive", day?.lines ?? [], null),
    );
  });

  it("predicts replaced for a changed amount and shows before and after", () => {
    const planned = planDays(week(), [storedDay({ takings: "880.00", net_sales: "838.10", lines: [
      { position: 0, name: "CHKN 65 DRY", code: "126", qty: "9", amount: "390.00", net_amount: "371.43", till_item_id: "t2" },
      { position: 1, name: "KARAK TEA FLASK 1L", code: "52a", qty: "14", amount: "490.00", net_amount: "466.67", till_item_id: "t1" },
    ] })], "inclusive");
    const day = planned.find((row) => row.key === "b1|2026-08-25");
    expect(day?.plan).toMatchObject({
      kind: "replaced",
      shrinking: false,
      previous: { takings: "880.00", net_sales: "838.10", line_count: 2 },
    });
    expect(committable(day as PlannedDay)).toBe(true);
  });

  it("flags a shrinking day and holds it until its tick", () => {
    // The stored day is the full one: three rows, AED 4,310. The file's is
    // the half-day export: two rows, AED 895.
    const full = storedDay({
      takings: "4310.00",
      net_sales: "4104.76",
      line_count: 3,
      lines: [
        ...storedDay().lines,
        { position: 2, name: "PARATHA PLAIN", code: "131", qty: "100", amount: "3415.00", net_amount: "3252.38", till_item_id: "t3" },
      ],
    });
    const planned = planDays(week(), [full], "inclusive");
    const day = planned.find((row) => row.key === "b1|2026-08-25") as PlannedDay;
    expect(day.plan).toMatchObject({
      kind: "replaced",
      shrinking: true,
      previous: { takings: "4310.00", line_count: 3 },
    });
    expect(committable(day)).toBe(false);
    expect(committable({ ...day, confirmed: true })).toBe(true);
  });

  it("predicts new for a day Faida has never seen, the gap zero day included", () => {
    const planned = planDays(week(), [], "inclusive");
    expect(planned.every((day) => day.plan.kind === "new")).toBe(true);
    expect(planned.find((day) => day.gap)?.plan.kind).toBe("new");
  });

  it("a different basis is a different day", () => {
    const planned = planDays(week(), [storedDay()], "exclusive");
    expect(planned.find((row) => row.key === "b1|2026-08-25")?.plan.kind).toBe("replaced");
  });
});

describe("requestGroups and toDayInput", () => {
  it("posts one branch-month per request, in the grid's order, only committable days", () => {
    const planned = planDays(week(), [], "inclusive");
    const groups = requestGroups(planned);
    expect(groups.map((group) => group.map((day) => day.key))).toEqual([
      ["b1|2026-08-25", "b1|2026-08-26", "b1|2026-08-27"],
      ["b2|2026-08-25", "b2|2026-08-26", "b2|2026-08-27"],
    ]);
    const body = toDayInput(groups[0][0], "inclusive", "l1", { sha256: "abc", filename: "w.csv" });
    expect(body).toEqual({
      branch_id: "b1",
      business_date: "2026-08-25",
      granularity: "item",
      amount_basis: "inclusive",
      layout_id: "l1",
      source: { sha256: "abc", filename: "w.csv" },
      lines: [
        { position: 0, name: "KARAK TEA FLASK 1L", code: "52a", qty: "14", amount: "490.00" },
        { position: 1, name: "CHKN 65 DRY", code: "126", qty: "9", amount: "405.00" },
      ],
    });
    const zero = toDayInput(groups[0][2], "inclusive", "l1", { sha256: "abc", filename: "w.csv" });
    expect(zero).toMatchObject({ granularity: "summary", amount: "0.00" });
    expect("lines" in zero).toBe(false);
  });
});
