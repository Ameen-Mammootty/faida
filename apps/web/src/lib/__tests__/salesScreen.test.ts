import { describe, expect, it } from "vitest";
import {
  answerSentence,
  bucketsLine,
  collapseDays,
  costedSentence,
  exVatWords,
  freshnessSentence,
  isZero,
  monthOptions,
  noRatioWords,
  periodBounds,
  segmentWords,
  shortBranchName,
  statusSentence,
  sumFils,
  weekdayDate,
  windowLine,
} from "../salesScreen";
import type { BranchRow, DayFigure, SalesBranchesResult, SalesCoverageResult } from "../types";

/**
 * M8 WP-84: the pure decisions behind the sales screen - the sentence, the
 * picker's ranges and months, the status words, the drill's collapsed runs,
 * the coverage line - pinned here so the component stays a renderer.
 */

function row(overrides: Partial<BranchRow>): BranchRow {
  return {
    branch_id: "br-01",
    branch_name: "Al Qusais Branch",
    window: { from: "2026-08-25", to: "2026-08-31", days: 7 },
    net_sales: "30267.43",
    takings: "31780.80",
    purchases: "9162.65",
    ratio_pct: "30.3",
    quality: "reliable_with_limitations",
    notes: ["2 deliveries in this window"],
    days_loaded: 7,
    days_missing: 0,
    deliveries: 2,
    sales_through: "2026-08-31",
    last_purchase_on: "2026-08-28",
    days: [],
    pending: [],
    excluded: [],
    ...overrides,
  };
}

function result(rows: BranchRow[], salesThrough: string | null = "2026-08-31"): SalesBranchesResult {
  return {
    period: { from: "2026-08-04", to: "2026-08-31", days: 28, default: true, sales_through: salesThrough, months: ["2026-08"] },
    rows,
    unassigned: { count: 0, purchases: "0.00", invoices: [] },
    total: { net_sales: "0.00", purchases: "0.00", ratio_pct: null, quality: "incomplete", notes: [] },
  };
}

describe("the answer sentence", () => {
  it("names the top ranked branch in the of-every-100 lens and the branches that cannot be ranked", () => {
    const sentence = answerSentence(
      result([
        row({}),
        row({ branch_id: "br-02", branch_name: "Al Nahda Branch", ratio_pct: null, purchases: "0.00", deliveries: 0, quality: "incomplete", notes: ["no confirmed purchases 25-31 Aug"] }),
        row({ branch_id: "br-03", branch_name: "Rolla Branch", ratio_pct: null, purchases: "0.00", deliveries: 0, quality: "incomplete", notes: ["no confirmed purchases 25-31 Aug"] }),
      ]),
    );
    expect(sentence).toEqual({
      lead: "Look at Al Qusais first",
      rest:
        "about AED 30 of every 100 it took went to suppliers this window. Al Nahda and Rolla have sales loaded and no papers confirmed, so they cannot be ranked yet.",
    });
  });

  it("rounds to the nearest whole dirham of every hundred, and says when the top figure is incomplete", () => {
    const sentence = answerSentence(result([row({ ratio_pct: "39.5", quality: "incomplete", notes: ["2 of 7 days have no sales"] })]));
    expect(sentence?.rest).toBe(
      "about AED 40 of every 100 it took went to suppliers this window. Its figure is incomplete - its row says why.",
    );
  });

  it("says no branch can be ranked when every row with sales lacks papers, and nothing when no row has sales", () => {
    const only = answerSentence(result([row({ ratio_pct: null, deliveries: 0, quality: "incomplete" })]));
    expect(only).toEqual({
      lead: "No branch can be ranked yet",
      rest: "Al Qusais has sales loaded and no papers confirmed, so it cannot be ranked yet.",
    });
    expect(answerSentence(result([row({ ratio_pct: null, net_sales: null, takings: null, quality: "unavailable" })]))).toBeNull();
  });

  it("never tells a branch with confirmed papers that it has none: net sales that are not positive get their own clause", () => {
    const sentence = answerSentence(
      result([
        row({}),
        row({ branch_id: "br-03", branch_name: "Deira", ratio_pct: null, net_sales: "0.00", deliveries: 3, quality: "incomplete", notes: ["net sales are not positive this period", "3 deliveries in this window"] }),
      ]),
    );
    expect(sentence?.rest).toBe(
      "about AED 30 of every 100 it took went to suppliers this window. Deira's net sales are not positive this period, so it is not rated.",
    );
    expect(noRatioWords(row({ ratio_pct: null, net_sales: "0.00", deliveries: 3 }))).toBe("Net sales not positive");
  });
});

describe("the period picker", () => {
  it("asks the API for its own default on 28 days, seven days ending on the newest loaded day, or a whole month", () => {
    expect(periodBounds({ kind: "last28" }, "2026-08-31")).toBeNull();
    expect(periodBounds({ kind: "last7" }, "2026-08-31")).toEqual({ from: "2026-08-25", to: "2026-08-31" });
    expect(periodBounds({ kind: "last7" }, null)).toBeNull();
    expect(periodBounds({ kind: "month", year: 2026, month: 8 }, null)).toEqual({ from: "2026-08-01", to: "2026-08-31" });
    expect(periodBounds({ kind: "month", year: 2026, month: 12 }, null)).toEqual({ from: "2026-12-01", to: "2026-12-31" });
    expect(periodBounds({ kind: "month", year: 2028, month: 2 }, null)).toEqual({ from: "2028-02-01", to: "2028-02-29" });
  });

  it("offers exactly the months the API says hold sales, newest first, and nothing it cannot read", () => {
    const period = { from: "2026-08-04", to: "2026-08-31", days: 28, default: true, sales_through: "2026-08-31", months: ["2026-08", "2026-07", "2026-05"] };
    expect(monthOptions(period).map((m) => m.label)).toEqual(["Aug 2026", "Jul 2026", "May 2026"]);
    expect(monthOptions({ ...period, months: [] })).toEqual([]);
    expect(monthOptions({ ...period, months: ["garbage", "2026-13"] })).toEqual([]);
  });
});

describe("dates and status words", () => {
  it("says how fresh the sales are, by the calendar", () => {
    const period = { from: "2026-08-04", to: "2026-08-31", days: 28, default: true, sales_through: "2026-08-31", months: ["2026-08"] };
    expect(freshnessSentence(period, "2026-09-03")).toBe("Sales loaded to Mon 31 Aug, 3 days ago.");
    expect(freshnessSentence(period, "2026-09-01")).toBe("Sales loaded to Mon 31 Aug, yesterday.");
    expect(freshnessSentence(period, "2026-08-31")).toBe("Sales loaded to Mon 31 Aug, today.");
    expect(freshnessSentence({ ...period, sales_through: null }, "2026-09-03")).toBeNull();
    expect(weekdayDate("2026-08-25")).toBe("Tue 25 Aug");
  });

  it("puts the API's own sentences under the status word, minus the delivery count, and the one sentence for a clean row", () => {
    expect(statusSentence("reliable_with_limitations", ["2 deliveries in this window"])).toBe(
      "Every day loaded, every paper confirmed.",
    );
    expect(statusSentence("incomplete", ["no confirmed purchases 25-31 Aug"])).toBe("No confirmed purchases 25-31 Aug.");
    expect(statusSentence("estimated", ["1 invoice awaiting confirm", "3 deliveries in this window"])).toBe(
      "1 invoice awaiting confirm.",
    );
    expect(statusSentence("incomplete", ["2 of 3 branches incomplete", "1 invoice on no branch, counted in the total"])).toBe(
      "2 of 3 branches incomplete. 1 invoice on no branch, counted in the total.",
    );
    // A chip never stands alone: the chain total reads estimated with no note
    // of its own when a branch below it does.
    expect(statusSentence("estimated", [])).toBe("At least one figure behind it is estimated - see the rows.");
    expect(statusSentence("incomplete", [])).toBe("Some days or papers are missing - see the rows.");
  });

  it("writes the window line and the words that stand in for a missing ratio", () => {
    expect(windowLine(row({}))).toBe("25-31 Aug, 7 days · 2 deliveries");
    expect(windowLine(row({ window: { from: "2026-08-31", to: "2026-08-31", days: 1 }, deliveries: 1 }))).toBe("31 Aug, 1 day · 1 delivery");
    expect(windowLine(row({ window: { from: "2026-08-28", to: "2026-09-03", days: 7 } }))).toBe("28 Aug-3 Sep, 7 days · 2 deliveries");
    expect(noRatioWords(row({ ratio_pct: null, deliveries: 0 }))).toBe("No confirmed purchases");
    expect(noRatioWords(row({ ratio_pct: null, net_sales: null, deliveries: 0 }))).toBe("Nothing loaded");
    expect(noRatioWords(row({ ratio_pct: null, net_sales: null, deliveries: 2 }))).toBe("No sales loaded");
    expect(shortBranchName("Rolla Branch")).toBe("Rolla");
    expect(shortBranchName("Branch")).toBe("Branch");
  });

  it("shows a paper's two printed figures the way the photo does", () => {
    expect(
      exVatWords({ invoice_id: "x", supplier_name: "s", invoice_no: "n", purchased_on: "2026-08-25", net_purchase: "5081.70", total: "5335.79", tax: "254.09", quality: "reliable_with_limitations" }),
    ).toBe("AED 5,081.70 = 5,335.79 less VAT 254.09");
    // A market receipt with no VAT line still confirms; its tax is null on the wire.
    expect(
      exVatWords({ invoice_id: "x", supplier_name: "s", invoice_no: "n", purchased_on: "2026-08-25", net_purchase: "200.00", total: "200.00", tax: null, quality: "reliable_with_limitations" }),
    ).toBe("AED 200.00 = 200.00, no VAT printed");
    expect(
      exVatWords({ invoice_id: "x", supplier_name: "s", invoice_no: "n", purchased_on: null, net_purchase: "0.00", total: null, tax: null, quality: "reliable_with_limitations" }),
    ).toBe("AED 0.00, no total printed");
  });
});

describe("the drill", () => {
  const day = (date: string, net: string | null, invoices = 0): DayFigure => ({
    business_date: date,
    net_sales: net,
    granularity: net === null ? null : "item",
    purchases: invoices > 0 ? "100.00" : "0.00",
    invoices: Array.from({ length: invoices }, (_, i) => ({
      invoice_id: `inv-${date}-${i}`,
      supplier_name: "S",
      invoice_no: "1",
      purchased_on: date,
      net_purchase: "100.00",
      total: "105.00",
      tax: "5.00",
      quality: "reliable_with_limitations" as const,
    })),
  });

  it("keeps a day with papers on its own line and collapses a run of paperless days with their net sales added", () => {
    const segments = collapseDays([
      day("2026-08-25", "4310.00", 2),
      day("2026-08-26", "4000.00"),
      day("2026-08-27", "4100.50"),
      day("2026-08-28", "4200.00"),
      day("2026-08-30", "3900.00"),
      day("2026-08-31", "4610.00", 1),
    ]);
    expect(segments.map((s) => (s.kind === "day" ? `day ${s.day.business_date}` : `run ${s.from}..${s.to} x${s.days} ${s.net_sales}`))).toEqual([
      "day 2026-08-25",
      "run 2026-08-26..2026-08-28 x3 12300.50",
      "run 2026-08-30..2026-08-30 x1 3900.00",
      "day 2026-08-31",
    ]);
    expect(segmentWords(segments[1])).toBe("Wed 26 Aug - Fri 28 Aug");
    expect(segmentWords(segments[2])).toBe("Sun 30 Aug");
  });

  it("keeps a day a pending paper is placed on out of the run, so the paper has a line to sit under", () => {
    const segments = collapseDays(
      [day("2026-08-26", "4000.00"), day("2026-08-27", "4100.50"), day("2026-08-28", "4200.00")],
      new Set(["2026-08-27"]),
    );
    expect(segments.map((s) => (s.kind === "day" ? `day ${s.day.business_date}` : `run ${s.from}..${s.to}`))).toEqual([
      "run 2026-08-26..2026-08-26",
      "day 2026-08-27",
      "run 2026-08-28..2026-08-28",
    ]);
  });

  it("adds money exactly on fils and never through a float", () => {
    expect(sumFils(["0.10", "0.20"])).toBe("0.30");
    expect(sumFils(["4310.00", "-35.00", "0.5"])).toBe("4275.50");
    expect(sumFils([])).toBe("0.00");
  });
});

describe("the coverage line", () => {
  const coverage = (over: Partial<SalesCoverageResult>): SalesCoverageResult => ({
    period: { from: "2026-08-04", to: "2026-08-31", days: 28, default: true, sales_through: "2026-08-31", months: ["2026-08"] },
    sales_value: "52000.00",
    costed_value: "40560.00",
    costed_pct: "78.0",
    estimated_points: "12.0",
    uncosted: { incomplete_plate: "3120.00", unmapped: "8320.00" },
    beside: { refunds: "-210.00", not_menu_items: "640.00" },
    queue: [],
    mapped: [],
    excluded: [],
    ...over,
  });

  it("says costed, never complete, and names every bucket in words", () => {
    expect(costedSentence(coverage({}))).toBe("Costed: 78.0% of sales value");
    expect(bucketsLine(coverage({}))).toBe(
      "12.0 points of it on estimated plates · Not yet mapped: AED 8,320 · Cannot be costed yet: AED 3,120 · Refunds AED 210 and non-menu net sales AED 640 sit outside the figure",
    );
    expect(bucketsLine(coverage({ estimated_points: "0.0", uncosted: { incomplete_plate: "0.00", unmapped: "0.00" }, beside: { refunds: "0.00", not_menu_items: "15.00" } }))).toBe(
      "Non-menu net sales AED 15 sit outside the figure",
    );
    expect(bucketsLine(coverage({ estimated_points: "0", uncosted: { incomplete_plate: "0", unmapped: "0.000" }, beside: { refunds: "-0.00", not_menu_items: "0.0" } }))).toBe("");
    expect(costedSentence(coverage({ costed_pct: null }))).toBe("No item-wise sales in this window");
    expect([isZero("0"), isZero("0.00"), isZero("-0.00"), isZero(null), isZero("0.10"), isZero("10")]).toEqual([true, true, true, true, false, false]);
  });
});
