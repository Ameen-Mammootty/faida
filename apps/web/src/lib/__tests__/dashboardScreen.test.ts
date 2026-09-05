import { describe, expect, it } from "vitest";
import {
  ANSWER_EMPTY,
  ANSWER_NO_MENU,
  NO_CHAIN_AVERAGE,
  SPLIT_AT,
  answerCaveat,
  answerLines,
  approvalsHref,
  branchOptions,
  branchParam,
  cardLine,
  componentLink,
  coverageStrip,
  daysInclusive,
  filteredEmpty,
  firstRun,
  freshnessLine,
  incompleteItems,
  isFirstRun,
  itemCaption,
  itemPanel,
  itemsHeading,
  leagueFootnote,
  leagueLine,
  leagueLink,
  leagueStatus,
  noContributionWords,
  noMenuSentence,
  noRatioWords,
  points,
  portionsWords,
  showAllLabel,
  signalHref,
  signalMoney,
  signalWhen,
  signalsCount,
  signalsFootnote,
  todaysPlateLink,
  withBranch,
} from "../dashboardScreen";
import { anchorBranchId, anchorItemId } from "../anchor";
import { SCENARIOS, mockGetDashboard } from "../mock/dashboard";
import type {
  DashboardItemRow,
  DashboardResult,
  DashboardSignal,
  LeagueRow,
} from "../types";

/**
 * M9 WP-93: the pure decisions behind the owner dashboard - the first-run
 * paragraph, the freshness line, the framing of the API's answer sentences,
 * the league's words, the five-and-five slicing, the signals' framing, the
 * coverage strip, the branch filter's URL round trip - pinned here so the
 * component stays a renderer. Nothing here composes a sentence about a
 * number the API did not already say, and nothing re-ranks: C13.5 puts both
 * in Python, and a test pinning a second copy would be pinning the bug.
 *
 * The fixtures are the mock's own scenarios, which were produced by the
 * shipped Python modules over a hand-built week, so a decision tested here is
 * tested on the shapes the API really serves.
 */

async function scenario(name: (typeof SCENARIOS)[number], branch?: string): Promise<DashboardResult> {
  Object.defineProperty(globalThis, "window", {
    value: { location: { search: `?scenario=${name}` } },
    configurable: true,
    writable: true,
  });
  try {
    return await mockGetDashboard(undefined, undefined, branch);
  } finally {
    delete (globalThis as { window?: unknown }).window;
  }
}

function leagueRow(overrides: Partial<LeagueRow> = {}): LeagueRow {
  return {
    branch_id: "br-03",
    branch_name: "Deira Branch",
    window: { from: "2026-08-25", to: "2026-08-31", days: 7 },
    net_sales: "15845.85",
    takings: "16638.14",
    purchases: "4120.60",
    ratio_pct: "26.0",
    contribution: "7827.84",
    contribution_pct: "60.9",
    costed_share_pct: "82.0",
    ratio_quality: "reliable_with_limitations",
    ratio_notes: ["1 delivery in this window"],
    contribution_quality: "estimated",
    contribution_notes: ["covers 82% of this branch's sales value"],
    days_loaded: 7,
    days_missing: 0,
    deliveries: 1,
    sales_through: "2026-08-31",
    last_purchase_on: "2026-08-27",
    ...overrides,
  };
}

function itemRow(overrides: Partial<DashboardItemRow> = {}): DashboardItemRow {
  return {
    menu_item_id: "menu-2",
    menu_item_name: "Karak Tea (Flask 1 L)",
    category: "Tea Corner",
    branch_id: null,
    qty_sold: "412.000",
    qty_refunded: "0.000",
    net_item_sales: "13733.33",
    cost_per_portion: "6.204",
    cost: "2556.05",
    cost_per_portion_today: null,
    contribution: "11177.28",
    contribution_pct: "81.4",
    avg_sold_at: "33.333",
    net_price: "33.333",
    plate_quality: "reliable_with_limitations",
    quality: "reliable_with_limitations",
    notes: ["costed at the prices in force on 31 Aug 2026", "recipe version 1"],
    recipe_version: 1,
    till_items: [{ till_item_id: "t-menu-2", name: "KARAK TEA FLASK 1L", code: "52a" }],
    components: [],
    archived: false,
    ...overrides,
  };
}

function signal(overrides: Partial<DashboardSignal> = {}): DashboardSignal {
  return {
    kind: "popular_low_margin",
    money_at_stake: "1473.37",
    quality: "estimated",
    sentence: "Chicken 65 Dry sold AED 3,855 and kept 38.1%; the menu keeps 67.4%.",
    detail: "At the menu's average it would have contributed AED 1,473 more. (estimated)",
    branch_id: null,
    branch_name: null,
    menu_item_id: "menu-9",
    menu_item_name: "Chicken 65 Dry",
    ingredient_id: null,
    ingredient_name: null,
    invoice_id: null,
    moved_on: null,
    ...overrides,
  };
}

describe("the mock's scenarios", () => {
  it("are the six the QA walk names, reachable by URL", () => {
    expect([...SCENARIOS]).toEqual(["full", "partial", "quiet", "empty", "nomenu", "error"]);
  });

  it("serve the chain and each branch, with the total unchanged by the filter", async () => {
    const chain = await scenario("full");
    const deira = await scenario("full", "br-03");
    expect(chain.scope.branch_id).toBeNull();
    expect(deira.scope).toEqual({ branch_id: "br-03", branch_name: "Deira" });
    expect(deira.league.map((row) => row.branch_id)).toEqual(["br-03"]);
    expect(deira.total).toEqual(chain.total);
    expect(deira.items.all.every((row) => row.branch_id === "br-03")).toBe(true);
    // Every money value and every percentage is a string, never a number.
    const MONEY = ["net_sales", "takings", "purchases", "contribution", "net_item_sales", "cost"];
    const PCT = ["ratio_pct", "contribution_pct", "costed_share_pct"];
    for (const row of [...chain.league, ...chain.items.all] as unknown as Record<string, unknown>[]) {
      for (const key of [...MONEY, ...PCT]) {
        if (key in row && row[key] !== null) expect(typeof row[key]).toBe("string");
      }
    }
    expect(typeof chain.total.contribution).toBe("string");
  });

  it("carry the three chain reconciliations the contract pins (C12.8)", async () => {
    const chain = await scenario("full");
    const branches = chain.league.reduce((sum, row) => sum + Number(row.contribution ?? 0), 0);
    const items = chain.items.all.reduce((sum, row) => sum + Number(row.contribution ?? 0), 0);
    expect(branches.toFixed(2)).toBe(chain.total.contribution);
    expect(items.toFixed(2)).toBe(chain.total.contribution);
  });

  it("fail the read for the error scenario with the API's own sentence", async () => {
    await expect(scenario("error")).rejects.toThrow(/could not be read/);
  });
});

describe("the first run", () => {
  it("is decided on the one fact: nothing was ever loaded", async () => {
    expect(isFirstRun(await scenario("empty"))).toBe(true);
    expect(isFirstRun(await scenario("full"))).toBe(false);
  });

  it("says what is already true from the same read, and offers two actions", async () => {
    const first = firstRun(await scenario("empty"));
    expect(first.heading).toBe("No sales loaded yet.");
    expect(first.menuSentence).toBe(
      "Your menu is costed: 12 of 14 items have a price for every ingredient.",
    );
    expect(first.primary).toEqual({ href: "/sales/load", label: "Load sales from a CSV" });
    expect(first.secondary).toEqual({ href: "/menu", label: "See the menu's margins" });
  });

  it("gives a menu with no sales and sales with no menu their own second sentence", async () => {
    const empty = await scenario("empty");
    const noMenuFirst = firstRun({ ...empty, menu: { items: 0, costed: 0 } });
    expect(noMenuFirst.menuSentence).toBe(
      "No menu is loaded yet, so nothing can be costed until one is.",
    );
    expect(noMenuFirst.secondary.href).toBe("/menu/load");
    const allCosted = firstRun({ ...empty, menu: { items: 5, costed: 5 } });
    expect(allCosted.menuSentence).toBe(
      "Your menu is costed: every one of its 5 items has a price for every ingredient.",
    );

    const nomenu = await scenario("nomenu");
    expect(isFirstRun(nomenu)).toBe(false);
    expect(noMenuSentence(nomenu)).toBe("No menu is loaded, so nothing can be costed yet.");
    expect(noMenuSentence(await scenario("full"))).toBeNull();
    expect(noMenuSentence(empty)).toBeNull();
  });
});

describe("the freshness line", () => {
  it("carries the API's sentence, the newest day's takings and the papers link", async () => {
    const line = freshnessLine(await scenario("full"));
    expect(line).toEqual({
      sentence: "Sales loaded to Mon 31 Aug, 5 days ago.",
      estimated: false,
      takings: "AED 9,492 taken that day across 3 branches",
      papers: { label: "2 papers waiting for you", href: "/invoices?status=needs_review" },
    });
  });

  it("carries the word past seven days, and that branch's own day under the filter", async () => {
    const partial = freshnessLine(await scenario("partial"));
    expect(partial?.sentence).toBe("Sales loaded to Mon 31 Aug, 12 days ago.");
    expect(partial?.estimated).toBe(true);
    const karama = freshnessLine(await scenario("full", "br-02"));
    expect(karama?.takings).toBe("AED 2,986 taken that day at Karama");
    expect(karama?.papers).toBeNull(); // Karama holds no paper for review
    const quoz = freshnessLine(await scenario("full", "br-01"));
    expect(quoz?.papers).toEqual({
      label: "2 papers waiting for you",
      href: "/invoices?status=needs_review&branch_id=br-01",
    });
  });

  it("is absent when nothing was ever loaded", async () => {
    expect(freshnessLine(await scenario("empty"))).toBeNull();
    expect(approvalsHref({ branch_id: null, branch_name: null })).toBe("/invoices?status=needs_review");
  });
});

describe("the answer", () => {
  it("frames the API's two sentences and never composes one of its own", async () => {
    const full = await scenario("full");
    expect(answerLines(full)).toEqual({
      branch: "Look at Deira first: it keeps about AED 61 of every 100 it takes, the least of the three.",
      item: "Chicken 65 Dry sells more than any item that earns under the menu's average.",
      empty: null,
    });
    expect(answerCaveat(full)).toBe(
      "Estimated: covers 82% of this branch's sales value · 1 item cannot be costed yet · 1 till name with sales is not mapped to a menu item",
    );
  });

  it("shows one sentence when only one side can be answered, and its own when neither can", async () => {
    const quiet = await scenario("quiet");
    const lines = answerLines(quiet);
    expect(lines.item).toBeNull();
    expect(lines.branch).toMatch(/^Look at Deira first/);
    expect(lines.empty).toBeNull();
    expect(answerCaveat(quiet)).toBeNull();

    const nomenu = await scenario("nomenu");
    expect(answerLines(nomenu)).toEqual({ branch: null, item: null, empty: ANSWER_NO_MENU });
    expect(answerCaveat(nomenu)).toBeNull();
    expect(answerLines({ ...nomenu, menu: { items: 3, costed: 0 } }).empty).toBe(ANSWER_EMPTY);
  });

  it("says incomplete inside the sentence when the top row is", async () => {
    const partial = await scenario("partial");
    expect(answerLines(partial).branch).toMatch(/Its figure is incomplete - its row says why\.$/);
    expect(answerCaveat(partial)).toMatch(/^Incomplete: 1 of 7 days has no sales/);
  });
});

describe("the league", () => {
  it("puts the window and the deliveries under the name", () => {
    expect(leagueLine(leagueRow())).toBe("25-31 Aug, 7 days · 1 delivery");
    expect(leagueLine(leagueRow({ deliveries: 3, window: { from: "2026-08-28", to: "2026-09-03", days: 7 } }))).toBe(
      "28 Aug-3 Sep, 7 days · 3 deliveries",
    );
  });

  it("puts words in a cell that has no figure, never 0%", () => {
    expect(noRatioWords(leagueRow({ ratio_pct: null, deliveries: 0 }))).toBe("No confirmed purchases");
    expect(noRatioWords(leagueRow({ net_sales: null, deliveries: 0 }))).toBe("Nothing loaded");
    expect(noRatioWords(leagueRow({ net_sales: null, deliveries: 2 }))).toBe("No sales loaded");
    expect(noRatioWords(leagueRow({ ratio_pct: null, deliveries: 2 }))).toBe("Net sales not positive");
    expect(noContributionWords(leagueRow({ net_sales: null, contribution: null }))).toBe("Nothing loaded");
    expect(noContributionWords(leagueRow({ contribution: null }))).toBe("Nothing costed");
  });

  it("puts the contribution's word in the status chip and the ratio's story in the ratio cell", () => {
    const row = leagueRow({
      ratio_quality: "unavailable",
      ratio_notes: ["no confirmed purchases 25-31 Aug"],
      contribution_quality: "reliable_with_limitations",
      contribution_notes: ["covers 83% of this branch's sales value"],
    });
    expect(leagueStatus(row)).toEqual({
      quality: "reliable_with_limitations",
      sentence: "Covers 83% of this branch's sales value.",
    });
  });

  it("writes the card's caption from the row's own figures", () => {
    expect(cardLine(leagueRow())).toBe("Kept AED 7,827 of AED 15,845 · purchases ÷ net sales 26.0%");
    expect(cardLine(leagueRow({ ratio_pct: null, deliveries: 0 }))).toBe(
      "Kept AED 7,827 of AED 15,845 · no confirmed purchases",
    );
    expect(
      cardLine(leagueRow({ net_sales: null, ratio_pct: null, contribution: null, contribution_pct: null, deliveries: 0 })),
    ).toBe("Nothing loaded");
    expect(
      cardLine(leagueRow({ net_sales: null, ratio_pct: null, contribution: null, contribution_pct: null, deliveries: 2 })),
    ).toBe("No sales loaded");
  });

  it("names the costing date in the footnote and the two screens' different keys", async () => {
    const note = leagueFootnote(await scenario("full"));
    expect(note).toMatch(/costed at the prices in force on 31 Aug 2026/);
    expect(note).toMatch(/It is not profit/);
    expect(note).toMatch(/Ranked by Kept, lowest first; the Sales screen ranks the same branches by purchases ÷ net sales\.$/);
    expect(note).not.toMatch(/food cost/i);
  });

  it("keeps the API's order and never re-ranks", async () => {
    const full = await scenario("full");
    expect(full.league.map((row) => row.branch_name)).toEqual(["Deira", "Karama", "Al Quoz"]);
  });

  it("says so under a filter for a branch with nothing loaded", async () => {
    expect(filteredEmpty(await scenario("partial", "br-03"))).toBe(
      "This branch has no sales in this window.",
    );
    expect(filteredEmpty(await scenario("full", "br-03"))).toBeNull();
    expect(filteredEmpty(await scenario("partial"))).toBeNull();
  });

  // WP-94: the row opens to /sales for its days and its papers, in the app's
  // one anchor idiom - not a query parameter of this screen's own.
  it("sends the row to that branch's own row on /sales, and says so out loud", () => {
    expect(leagueLink(leagueRow())).toEqual({
      href: "/sales#branch-br-03",
      label: "Deira Branch: its days and papers on the Sales screen",
    });
  });

  it("escapes an id that would otherwise break the fragment", () => {
    expect(leagueLink({ branch_id: "br/03 a", branch_name: "Deira" }).href).toBe(
      "/sales#branch-br%2F03%20a",
    );
  });

  it("gives every row in the mock a link, whether or not anything is loaded", async () => {
    for (const name of ["full", "partial"] as const) {
      const result = await scenario(name);
      expect(result.league.map((row) => leagueLink(row).href)).toEqual(
        result.league.map((row) => `/sales#branch-${row.branch_id}`),
      );
    }
  });
});

describe("the branch filter", () => {
  it("offers every branch with the chain first", () => {
    expect(
      branchOptions([
        { id: "br-01", name: "Al Quoz", wa_phone_e164: null, timezone: "Asia/Dubai" } as never,
      ]),
    ).toEqual([
      { id: "", label: "All branches" },
      { id: "br-01", label: "Al Quoz" },
    ]);
  });

  it("round-trips through ?branch= and keeps every other parameter", () => {
    expect(branchParam("")).toBeNull();
    expect(branchParam("?branch=")).toBeNull();
    expect(branchParam("?scenario=full&branch=br-03")).toBe("br-03");
    expect(withBranch("scenario=full", "br-03")).toBe("scenario=full&branch=br-03");
    expect(withBranch("scenario=full&branch=br-03", null)).toBe("scenario=full");
    expect(withBranch("branch=br-03", "")).toBe("");
    expect(branchParam(`?${withBranch("", "br-02")}`)).toBe("br-02");
  });
});

describe("the signals", () => {
  it("frames the money, the when and the link, and never re-words the sentence", () => {
    const popular = signal();
    expect(signalMoney(popular)).toBe("AED 1,473");
    expect(signalWhen(popular)).toBe("this window");
    expect(signalHref(popular)).toBe("/menu#item-menu-9");
    const spike = signal({
      kind: "price_spike",
      money_at_stake: "111.30",
      ingredient_id: "ing-nido",
      ingredient_name: "Milk Powder",
      invoice_id: "inv-1001",
      moved_on: "2026-08-21",
      menu_item_id: null,
      menu_item_name: null,
    });
    expect(signalWhen(spike)).toBe("since 21 Aug");
    expect(signalHref(spike)).toBe("/invoices/inv-1001");
    const gap = signal({ kind: "branch_gap", branch_id: "br-03", branch_name: "Deira", menu_item_id: null });
    expect(signalHref(gap)).toBe("/dashboard?branch=br-03");
    expect(signalsCount([popular, spike, gap])).toBe("3 this window, largest first");
    expect(signalsCount([])).toBeNull();
  });

  it("arrive ranked by money, capped at five, and the fifth shows where the tail starts", async () => {
    const full = await scenario("full");
    expect(full.signals).toHaveLength(5);
    const money = full.signals.map((s) => Number(s.money_at_stake));
    expect(money).toEqual([...money].sort((a, b) => b - a));
    expect(full.signals.map((s) => s.kind)).toContain("branch_gap");
  });

  it("names the branches the panel could not include, and the undefined average", async () => {
    expect(signalsFootnote(await scenario("partial"))).toBe("Based on 2 branches; Deira has no sales loaded.");
    expect(signalsFootnote(await scenario("full"))).toBeNull();
    expect(signalsFootnote(await scenario("nomenu"))).toBe(NO_CHAIN_AVERAGE);
    expect(signalsFootnote(await scenario("partial", "br-01"))).toBeNull();
  });

  it("is empty on a quiet week, not an empty box", async () => {
    const quiet = await scenario("quiet");
    expect(quiet.signals).toEqual([]);
    expect(signalsFootnote(quiet)).toBeNull();
  });
});

describe("the items", () => {
  it("shows five and five from the API's own slices when there are more than ten, and all otherwise", async () => {
    const full = await scenario("full");
    const split = itemPanel(full.items, false);
    expect(split.kind).toBe("split");
    if (split.kind !== "split") throw new Error("expected a split");
    expect(split.top).toEqual(full.items.top);
    expect(split.bottom).toEqual(full.items.bottom);
    expect(split.hidden).toBe(full.items.count - 10);
    expect(SPLIT_AT).toBe(10);

    const all = itemPanel(full.items, true);
    expect(all.kind).toBe("all");
    if (all.kind !== "all") throw new Error("expected all");
    expect(all.rows.map((r) => r.menu_item_id)).toEqual(
      full.items.all.filter((r) => r.contribution !== null).map((r) => r.menu_item_id),
    );

    const quiet = await scenario("quiet");
    expect(itemPanel(quiet.items, false).kind).toBe("all");
    expect(itemPanel((await scenario("nomenu")).items, false).kind).toBe("none");
  });

  it("captions the first row Best and the first of the bottom five Worst, in the name cell", () => {
    expect(itemCaption("top", 0, 5)).toBe("Best");
    expect(itemCaption("top", 1, 5)).toBeNull();
    expect(itemCaption("bottom", 0, 5)).toBe("Worst");
    expect(itemCaption("bottom", 4, 5)).toBeNull();
    expect(itemCaption("all", 0, 4)).toBe("Best");
    expect(itemCaption("all", 3, 4)).toBe("Worst");
    expect(itemCaption("all", 0, 1)).toBe("Best");
  });

  it("lists the rows with no numbers under the ranking, the /menu pattern", async () => {
    const full = await scenario("full");
    const holes = incompleteItems(full.items);
    expect(holes.map((r) => r.menu_item_name).sort()).toEqual(["Chicken Mandi", "Honey Cake"]);
    expect(holes.every((r) => r.contribution === null && r.cost === null)).toBe(true);
    expect(itemsHeading(full.items)).toBe("12 costed of 14");
    expect(showAllLabel(12, false)).toBe("Show all 12 items");
    expect(showAllLabel(12, true)).toBe("Show the top 5 and bottom 5 only");
  });

  it("frames the drill from the row's fields and the API's notes", () => {
    expect(portionsWords(itemRow())).toBe("412 sold");
    expect(portionsWords(itemRow({ qty_refunded: "2.000" }))).toBe("412 sold · 2 refunded");
    expect(portionsWords(itemRow({ qty_sold: null, qty_refunded: null }))).toBeNull();
    expect(todaysPlateLink(itemRow())).toEqual({ href: "/menu#item-menu-2", label: "See today's plate" });
    expect(todaysPlateLink(itemRow({ archived: true }))).toBeNull();
    expect(
      componentLink({
        ingredient_id: "ing-nido",
        ingredient_name: "Milk Powder",
        qty: "30.0000",
        unit: "g",
        cost_per_portion: "1.842",
        invoice_id: "inv-1001",
        line_position: 1,
        purchased_on: "2026-08-21",
      }),
    ).toEqual({ href: "/invoices/inv-1001#line-1", label: "Invoice line 2, 21 Aug 2026" });
    expect(
      componentLink({
        ingredient_id: "ing-chicken",
        ingredient_name: "Chicken",
        qty: "250.0000",
        unit: "g",
        cost_per_portion: null,
        invoice_id: null,
        line_position: null,
        purchased_on: null,
      }),
    ).toBeNull();
  });

  // WP-94: the link this screen writes is the link the other screen reads.
  // Both ends of the anchor are pinned here, in the same file, because a
  // silent mismatch is a drill that goes to the top of a page.
  it("writes plate links and invoice links the anchor module reads back", async () => {
    const full = await scenario("full");
    for (const row of full.items.all) {
      const link = todaysPlateLink(row);
      if (link === null) continue;
      expect(anchorItemId(new URL(link.href, "https://x").hash)).toBe(row.menu_item_id);
    }
    for (const row of full.league) {
      expect(anchorBranchId(new URL(leagueLink(row).href, "https://x").hash)).toBe(row.branch_id);
    }
  });

  it("marks an item that loses money by its own figure, and the mock carries one", async () => {
    const full = await scenario("full");
    const lemonade = full.items.all.find((r) => r.menu_item_name === "Mint Lemonade");
    expect(lemonade?.contribution?.startsWith("-")).toBe(true);
    expect(lemonade?.notes).toContain("this item costs more than it sells for");
    const chicken = full.items.all.find((r) => r.menu_item_name === "Chicken 65 Dry");
    expect(chicken?.quality).toBe("estimated");
    expect(chicken?.cost_per_portion_today).toBe("25.400");
    expect(chicken?.notes.join(" ")).toMatch(/sold at an average AED 40\.15 against today's menu price of AED 42\.86/);
  });
});

describe("the coverage strip", () => {
  it("is a sentence and a link to the queue, never a second queue", async () => {
    expect(coverageStrip(await scenario("full"))).toEqual({
      lead: "These figures cover 84.2% of what was sold.",
      rest: "3 till names worth AED 8,320 have no dish yet.",
      link: { href: "/sales", label: "Map them on Sales" },
    });
    expect(coverageStrip(await scenario("quiet"))).toEqual({
      lead: "These figures cover 100.0% of what was sold.",
      rest: "Every till name is mapped.",
      link: null,
    });
    const deira = coverageStrip(await scenario("full", "br-03"));
    expect(deira.lead).toBe("These figures cover 82.3% of what was sold.");
    expect(deira.rest).toBe("1 till name worth AED 2,400 has no dish yet.");
  });
});

describe("the formatter", () => {
  it("says points by string operations only", () => {
    expect(points("7.2")).toBe("7.2 points");
    expect(points("1.0")).toBe("1.0 point");
    expect(points("12.1")).toBe("12.1 points");
    expect(daysInclusive("2026-08-25", "2026-08-31")).toBe(7);
  });
});
