import { describe, expect, it } from "vitest";
import {
  ANSWER_EMPTY,
  ANSWER_NO_MENU,
  BEST_HEADING,
  COST_COVERS,
  ITEMS_LINK,
  KEPT_ABOUT,
  LEAGUE_LINK,
  MOVES_ABOUT,
  MOVES_LINK,
  NO_CHAIN_AVERAGE,
  NO_PRICE_MOVES,
  SCREEN_ABOUT,
  SIGNALS_ABOUT,
  SOLD_ABOUT,
  SPLIT_AT,
  SUPPLIERS_ABOUT,
  WORST_HEADING,
  answer,
  answerChip,
  answerTip,
  approvalsHref,
  branchOptions,
  branchParam,
  cardLine,
  componentLink,
  daysInclusive,
  everyHundred,
  filteredEmpty,
  firstRun,
  footnoteTip,
  freshnessLine,
  incompleteItems,
  isFirstRun,
  itemPanel,
  itemsTip,
  keptBar,
  latestDay,
  leagueChip,
  leagueChips,
  leagueFootnote,
  leagueLine,
  leagueLink,
  leagueStatus,
  leagueTip,
  noContributionWords,
  noMenuSentence,
  noRatioWords,
  noSalesWords,
  portionsWords,
  priceMoveLink,
  priceMoveMark,
  priceMoveMoney,
  priceMovePanel,
  priceMoveTip,
  rowChip,
  showAllLabel,
  showAllMovesLabel,
  showAllSignalsLabel,
  signalHref,
  signalMoney,
  signalPanel,
  signalTip,
  signalWhen,
  signalsFootnote,
  soldWords,
  statusTip,
  tileChip,
  tiles,
  todaysPlateLink,
  todo,
  totalTip,
  unassignedLine,
  wholePercent,
  withBranch,
} from "../dashboardScreen";
import { anchorBranchId, anchorItemId } from "../anchor";
import { points } from "../format";
import { SCENARIOS, mockGetDashboard } from "../mock/dashboard";
import type {
  DashboardItemRow,
  DashboardPriceMove,
  DashboardResult,
  DashboardSignal,
  LeagueRow,
} from "../types";

/**
 * M9 WP-93: the pure decisions behind the owner dashboard - the first-run
 * paragraph, the freshness line, the to-do strip, the framing of the API's
 * answer sentences, the three tiles, the league's words and chips, the
 * five-and-five slicing, the signals' and the price moves' framing, the
 * branch filter's URL round trip - pinned here so the component stays a
 * renderer. Nothing here composes a sentence about a number the API did not
 * already say, and nothing re-ranks: C13.5 puts both in Python, and a test
 * pinning a second copy would be pinning the bug.
 *
 * The simple screen (2026-09-08) is pinned in the same file: plain labels
 * on the face, the formal names the contracts pin as the first line behind
 * the icon, whole numbers, and a chip only where the word is a caveat.
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

/**
 * A price move of this test's own making, never the mock's words: the lane
 * that owns `mock/dashboard` regenerates its sentences, and a test that
 * pinned one of them would be pinning that lane's prose rather than this
 * screen's decisions. What is asserted against the mock below is counts,
 * kinds, ordering and the empty state.
 */
function priceMove(overrides: Partial<DashboardPriceMove> = {}): DashboardPriceMove {
  return {
    ingredient_id: "ing-nido",
    ingredient_name: "Milk Powder",
    kind: "moved",
    direction: "up",
    moved_on: "2026-08-21",
    invoice_id: "inv-1001",
    line_position: 1,
    money_at_stake: "108.58",
    sentence: "A sentence the API composed.",
    plates: "A plates clause the API composed.",
    evidence: "An evidence line the API composed.",
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
  it("is the API's sentence alone, with the word past seven days", async () => {
    expect(freshnessLine(await scenario("full"))).toEqual({
      sentence: "Sales loaded to Mon 31 Aug, 5 days ago.",
      estimated: false,
    });
    expect(freshnessLine(await scenario("partial"))).toEqual({
      sentence: "Sales loaded to Mon 31 Aug, 12 days ago.",
      estimated: true,
    });
  });

  it("is absent when nothing was ever loaded", async () => {
    expect(freshnessLine(await scenario("empty"))).toBeNull();
    expect(approvalsHref({ branch_id: null, branch_name: null })).toBe("/invoices?status=needs_review");
  });
});

// The simple screen: the newest day's takings, the papers and the queue
// left the freshness line for the Sold tile and the to-do strip.
describe("the to-do strip", () => {
  it("is a count and a door each: the papers, the names, the dishes", async () => {
    const full = await scenario("full");
    const items = todo(full);
    expect(items.map((item) => item.key)).toEqual(["papers", "names", "dishes"]);
    expect(items[0]).toEqual({
      key: "papers",
      label: "2 papers waiting for you",
      href: "/invoices?status=needs_review",
      tip: [],
    });
    expect(items[1]).toEqual({
      key: "names",
      label: "3 till names with no dish yet",
      href: "/sales",
      tip: ["3 till names worth AED 8,320 have no dish yet. Map them on the Sales screen."],
    });
    expect(items[2].label).toBe("2 dishes cannot be costed yet");
    expect(items[2].href).toBe("/menu");
    // The reasons, in the API's own notes, one dish to a line.
    expect(items[2].tip.map((line) => line.split(":")[0]).sort()).toEqual([
      "Chicken Mandi",
      "Honey Cake",
    ]);
    expect(items[2].tip.find((line) => line.startsWith("Chicken Mandi"))).toMatch(
      /^Chicken Mandi: No supplier product is mapped to Chicken yet\./,
    );
  });

  it("follows the branch filter to that branch's papers and its own queue", async () => {
    const quoz = todo(await scenario("full", "br-01"));
    expect(quoz[0].href).toBe("/invoices?status=needs_review&branch_id=br-01");
    expect(quoz[1].label).toBe("1 till name with no dish yet");
    expect(quoz[1].tip).toEqual([
      "1 till name worth AED 3,120 has no dish yet. Map them on the Sales screen.",
    ]);
  });

  it("is nothing at all on a quiet week, and never counts dishes without a menu", async () => {
    expect(todo(await scenario("quiet"))).toEqual([]);
    const nomenu = todo(await scenario("nomenu"));
    expect(nomenu.map((item) => item.key)).toEqual(["papers", "names"]);
    expect(nomenu[1].label).toBe("17 till names with no dish yet");
  });
});

describe("the answer", () => {
  it("cuts the branch sentence at its colon for a headline and never re-words it", async () => {
    const full = await scenario("full");
    expect(answer(full)).toEqual({
      lead: "Look at Deira first",
      lines: [
        "It keeps about AED 61 of every 100 it takes, the least of the three.",
        "Chicken 65 Dry sells more than any item that earns under the menu's average.",
      ],
      own: false,
    });
    // Cut and capital only: the words join back into the API's sentence.
    const [rest] = answer(full).lines;
    expect(`${answer(full).lead}: ${rest.charAt(0).toLowerCase()}${rest.slice(1)}`).toBe(
      full.answer.branch,
    );
  });

  it("keeps a sentence with no colon whole, and shows one side when only one can be answered", async () => {
    expect(answer(await scenario("full", "br-01"))).toEqual({
      lead: "Al Quoz keeps about AED 70 of every 100 it takes.",
      lines: ["Chicken 65 Dry sells more than any item at Al Quoz that earns under the menu's average."],
      own: false,
    });
    const quiet = answer(await scenario("quiet"));
    expect(quiet.lead).toBe("Look at Deira first");
    expect(quiet.lines).toHaveLength(1);
    expect(quiet.own).toBe(false);
  });

  it("uses its own sentence only when neither side can be answered", async () => {
    const nomenu = await scenario("nomenu");
    expect(answer(nomenu)).toEqual({ lead: ANSWER_NO_MENU, lines: [], own: true });
    expect(answer({ ...nomenu, menu: { items: 3, costed: 0 } }).lead).toBe(ANSWER_EMPTY);
  });

  it("says incomplete inside the sentence when the top row is", async () => {
    const partial = answer(await scenario("partial"));
    expect(partial.lead).toBe("Look at Karama first");
    expect(partial.lines[0]).toMatch(/Its figure is incomplete - its row says why\.$/);
  });
});

describe("the league", () => {
  it("puts the window and the deliveries behind the name", () => {
    expect(leagueLine(leagueRow())).toBe("25-31 Aug, 7 days · 1 delivery");
    expect(leagueLine(leagueRow({ deliveries: 3, window: { from: "2026-08-28", to: "2026-09-03", days: 7 } }))).toBe(
      "28 Aug-3 Sep, 7 days · 3 deliveries",
    );
  });

  it("puts words in a cell that has no figure, never 0%, and says them once a row", () => {
    expect(noRatioWords(leagueRow({ ratio_pct: null, deliveries: 0 }))).toBe("No confirmed purchases");
    expect(noSalesWords(leagueRow({ net_sales: null, deliveries: 0 }))).toBe("Nothing loaded");
    expect(noSalesWords(leagueRow({ net_sales: null, deliveries: 2 }))).toBe("No sales loaded");
    expect(noRatioWords(leagueRow({ ratio_pct: null, deliveries: 2 }))).toBe("Net sales not positive");
    // The sold cell has already said "Nothing loaded"; the kept cell does not say it again.
    expect(noContributionWords(leagueRow({ net_sales: null, contribution: null }))).toBe("-");
    expect(noContributionWords(leagueRow({ contribution: null }))).toBe("Nothing costed");
  });

  it("puts the contribution's word in the status chip and the ratio's story behind the icon", () => {
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

  it("says the shared word once, each row's own when they differ, and none with nothing costed", async () => {
    const full = await scenario("full");
    expect(leagueChips(full)).toEqual({ shared: "estimated", perRow: false });
    expect(leagueChip(full)).toBe("estimated");
    expect(rowChip(full.league[0], leagueChips(full))).toBeNull();

    const partial = await scenario("partial");
    const chips = leagueChips(partial);
    expect(chips).toEqual({ shared: null, perRow: true });
    expect(leagueChip(partial)).toBeNull();
    expect(partial.league.map((row) => rowChip(row, chips))).toEqual([
      "incomplete",
      "estimated",
      null, // Deira has nothing loaded, so there is no figure for a word to qualify
    ]);
    expect(rowChip(partial.total, chips)).toBe("incomplete");

    // A good week shares the reliable word, and the heading prints no chip for it.
    const quiet = await scenario("quiet");
    expect(leagueChips(quiet)).toEqual({ shared: "reliable_with_limitations", perRow: false });
    expect(leagueChip(quiet)).toBeNull();

    // Nothing costed anywhere: no word, no column.
    expect(leagueChips(await scenario("nomenu"))).toEqual({ shared: null, perRow: false });
  });

  it("writes the card's line from the row's own figures", () => {
    expect(cardLine(leagueRow())).toBe("Kept AED 7,828 of AED 15,846 sold");
    expect(cardLine(leagueRow({ contribution: null, contribution_pct: null }))).toBe(
      "Nothing costed · AED 15,846 sold",
    );
    expect(
      cardLine(leagueRow({ net_sales: null, ratio_pct: null, contribution: null, contribution_pct: null, deliveries: 0 })),
    ).toBe("Nothing loaded");
    expect(
      cardLine(leagueRow({ net_sales: null, ratio_pct: null, contribution: null, contribution_pct: null, deliveries: 2 })),
    ).toBe("No sales loaded");
  });

  it("gives the papers with no branch one line, and none when there are none", () => {
    expect(unassignedLine({ count: 0, purchases: "0.00" })).toBeNull();
    expect(unassignedLine({ count: 1, purchases: "412.40" })).toBe(
      "1 invoice with no branch · AED 412 paid to suppliers · counted in the total, ranked nowhere",
    );
    expect(unassignedLine({ count: 2, purchases: "1200.00" })).toMatch(/^2 invoices with no branch/);
  });

  it("names the costing date in the footnote and says what kept is not", async () => {
    const note = leagueFootnote(await scenario("full"));
    expect(note).toMatch(/^Kept is what is left after ingredients and packaging, costed at the prices in force on 31 Aug 2026\./);
    expect(note).toMatch(/It is not profit/);
    expect(note).toMatch(/Ranked by what each branch keeps of every 100 it takes, lowest first\.$/);
    expect(note).not.toMatch(/food cost/i);
    expect(LEAGUE_LINK).toEqual({ href: "/sales", label: "All on Sales" });
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
    expect(SIGNALS_ABOUT).toMatch(/largest first/);
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

describe("the supplier price moves", () => {
  it("marks the kind with a glyph, a tone and a name for a screen reader", () => {
    expect(priceMoveMark(priceMove())).toEqual({
      name: "Price rose",
      tone: "caution",
      direction: "up",
    });
    expect(priceMoveMark(priceMove({ direction: "down" }))).toEqual({
      name: "Price fell",
      tone: "verified",
      direction: "down",
    });
    expect(
      priceMoveMark(priceMove({ kind: "basis_changed", direction: null })),
    ).toEqual({ name: "Price basis changed", tone: "stone", direction: null });
    expect(MOVES_ABOUT).toMatch(/latest price move/);
  });

  it("prints the money off its magnitude and lets the direction choose the word", () => {
    expect(priceMoveMoney(priceMove())).toEqual({ figure: "AED 109", words: "at stake" });
    expect(
      priceMoveMoney(priceMove({ direction: "down", money_at_stake: "-43.65" })),
    ).toEqual({ figure: "AED 44", words: "saved" });
    // A move nothing sold after still moved: the API sent a zero, not a null,
    // and the words say why the figure is zero.
    expect(priceMoveMoney(priceMove({ money_at_stake: "0.00" }))).toEqual({
      figure: "AED 0",
      words: "nothing sold since",
    });
    // A basis change carries no number at all, so the column is empty.
    expect(
      priceMoveMoney(priceMove({ kind: "basis_changed", direction: null, money_at_stake: null })),
    ).toBeNull();
  });

  it("shows three then all, in the order the API ranked them", () => {
    const five = ["a", "b", "c", "d", "e"].map((id) => priceMove({ ingredient_id: id }));
    expect(priceMovePanel(five, false)).toEqual(five.slice(0, 3));
    expect(priceMovePanel(five, true)).toEqual(five);
    expect(showAllMovesLabel(five.length, false)).toBe("Show all 5");
    expect(showAllMovesLabel(five.length, true)).toBe("Show the top 3 only");
    expect(showAllMovesLabel(3, false)).toBeNull();
    expect(showAllMovesLabel(0, false)).toBeNull();
  });

  it("links the newest line on its paper, at the app's one anchor idiom", () => {
    expect(priceMoveLink(priceMove())).toEqual({
      href: "/invoices/inv-1001#line-1",
      label: "See the invoice",
    });
    expect(priceMoveLink(priceMove({ line_position: 0 }))?.href).toBe("/invoices/inv-1001#line-0");
    expect(priceMoveLink(priceMove({ invoice_id: "" }))).toBeNull();
    expect(MOVES_LINK).toEqual({ href: "/menu", label: "All on Menu" });
  });

  it("puts the plates and the evidence behind the icon, in the API's own words", () => {
    const move = priceMove();
    expect(priceMoveTip(move)).toEqual([move.plates, move.evidence]);
    expect(priceMoveTip(priceMove({ plates: null }))).toEqual([move.evidence]);
  });

  it("arrives with every kind the panel has to render, ranked, the basis change last", async () => {
    const full = await scenario("full");
    const moves = full.price_moves.moves;
    expect(full.price_moves.count).toBe(moves.length);
    expect(moves.length).toBeGreaterThanOrEqual(3);
    const names = moves.map((move) => priceMoveMark(move).name);
    expect(new Set(names)).toEqual(new Set(["Price rose", "Price fell", "Price basis changed"]));
    expect(names[names.length - 1]).toBe("Price basis changed");
    // Ranked by the money it moved whichever way, with the moneyless last.
    const weighed = moves
      .filter((move) => move.money_at_stake !== null)
      .map((move) => Math.abs(Number(move.money_at_stake)));
    expect(weighed).toEqual([...weighed].sort((a, b) => b - a));
    // A move nothing sold after: no plates to name, and the panel still lists it.
    expect(moves.some((move) => move.plates === null)).toBe(true);
    expect(moves.some((move) => priceMoveMoney(move) === null)).toBe(true);
    // The panel never re-orders what it was given.
    expect(priceMovePanel(moves, false)).toEqual(moves.slice(0, 3));
  });

  it("says there were none on a quiet week rather than showing an empty card", async () => {
    for (const name of ["quiet", "nomenu", "empty"] as const) {
      const result = await scenario(name);
      expect(result.price_moves).toEqual({ count: 0, moves: [] });
      expect(priceMovePanel(result.price_moves.moves, false)).toEqual([]);
    }
    expect(NO_PRICE_MOVES).toBe("No price moves in this window.");
  });

  it("renders what the branch filter sent, weighed by the API and never here", async () => {
    const chain = await scenario("full");
    const rolla = await scenario("full", "br-01");
    // Same materials in the same order - the screen weighs nothing itself.
    expect(rolla.price_moves.moves.map((move) => move.ingredient_id)).toEqual(
      chain.price_moves.moves.map((move) => move.ingredient_id),
    );
    // One branch's portions can never carry more money than the chain's.
    for (const [at, move] of rolla.price_moves.moves.entries()) {
      const whole = chain.price_moves.moves[at].money_at_stake;
      if (move.money_at_stake === null || whole === null) continue;
      expect(Math.abs(Number(move.money_at_stake))).toBeLessThanOrEqual(Math.abs(Number(whole)));
    }
  });
});

describe("the dishes", () => {
  it("shows five and five from the API's own slices when there are more than ten, and all otherwise", async () => {
    const full = await scenario("full");
    const split = itemPanel(full.items, false);
    expect(split.kind).toBe("split");
    if (split.kind !== "split") throw new Error("expected a split");
    expect(split.top).toEqual(full.items.top);
    expect(split.bottom).toEqual(full.items.bottom);
    expect(split.hidden).toBe(full.items.count - 10);
    expect(SPLIT_AT).toBe(10);
    expect([BEST_HEADING, WORST_HEADING]).toEqual(["Best earners", "Weakest earners"]);

    const all = itemPanel(full.items, true);
    expect(all.kind).toBe("all");
    if (all.kind !== "all") throw new Error("expected all");
    expect(all.rows.map((r) => r.menu_item_id)).toEqual(
      full.items.all.filter((r) => r.contribution !== null).map((r) => r.menu_item_id),
    );

    const quiet = await scenario("quiet");
    expect(itemPanel(quiet.items, false).kind).toBe("all");
    expect(itemPanel((await scenario("nomenu")).items, false).kind).toBe("none");
    expect(ITEMS_LINK).toEqual({ href: "/menu", label: "All on Menu" });
  });

  it("takes the rows with no numbers out of the ranking and into the to-dos", async () => {
    const full = await scenario("full");
    const holes = incompleteItems(full.items);
    expect(holes.map((r) => r.menu_item_name).sort()).toEqual(["Chicken Mandi", "Honey Cake"]);
    expect(holes.every((r) => r.contribution === null && r.cost === null)).toBe(true);
    expect(showAllLabel(12, false)).toBe("Show all 12 dishes");
    expect(showAllLabel(12, true)).toBe("Show the top 5 and bottom 5 only");
  });

  it("frames the drill from the row's fields and the API's notes", () => {
    expect(soldWords(itemRow())).toBe("412 sold");
    expect(soldWords(itemRow({ qty_sold: "1980.000" }))).toBe("1,980 sold");
    expect(soldWords(itemRow({ qty_sold: null }))).toBe("no quantity");
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

  it("marks a dish that loses money by its own figure, and the mock carries one", async () => {
    const full = await scenario("full");
    const lemonade = full.items.all.find((r) => r.menu_item_name === "Mint Lemonade");
    expect(lemonade?.contribution?.startsWith("-")).toBe(true);
    expect(lemonade?.notes).toContain("this item costs more than it sells for");
    expect(wholePercent(lemonade?.contribution_pct ?? null)).toBe("-5%");
    const chicken = full.items.all.find((r) => r.menu_item_name === "Chicken 65 Dry");
    expect(chicken?.quality).toBe("estimated");
    expect(chicken?.cost_per_portion_today).toBe("25.400");
    expect(chicken?.notes.join(" ")).toMatch(/sold at an average AED 40\.15 against today's menu price of AED 42\.86/);
  });
});

// The simple screen (2026-09-08): three tiles in plain words, the formal
// name the contract pins as the first line behind the icon, a chip only
// where the word is a caveat.
describe("the headline tiles", () => {
  it("is sold, kept and paid to suppliers, in plain words with one line each", async () => {
    const full = await scenario("full");
    const [sold, kept, suppliers] = tiles(full);
    expect(tiles(full)).toHaveLength(3);

    expect(sold).toEqual({
      key: "sold",
      label: "Sold",
      figure: "AED 67,471",
      words: null,
      loss: false,
      line: "AED 9,493 on Mon 31 Aug",
      status: null,
      bar: null,
      tip: [SOLD_ABOUT, "Taken across 3 branches that day."],
      caption: null,
    });

    expect(kept.label).toBe("Kept after ingredients");
    expect(kept.figure).toBe("AED 37,952");
    expect(kept.line).toBe("AED 67 of every 100 sold");
    expect(kept.status).toBe("estimated");
    expect(kept.bar).toEqual({ width: 84.2, words: "covers 84% of what sold" });
    // The formal name first, then what the cost covers, then the API's notes.
    expect(kept.tip).toEqual([
      KEPT_ABOUT,
      COST_COVERS,
      "Covers 84% of the chain's sales value.",
      "5 branch items left out of the figure.",
      "3 till names with sales are not mapped to a menu item.",
      "Waste and variable fees are not recorded anywhere, so they are not subtracted.",
    ]);
    expect(KEPT_ABOUT).toMatch(/^Contribution before overheads \(estimate\)/);
    expect(KEPT_ABOUT).toMatch(/It is not profit\.$/);

    expect(suppliers.label).toBe("Paid to suppliers");
    expect(suppliers.figure).toBe("AED 16,019");
    expect(suppliers.line).toBe("AED 24 of every 100 sold");
    expect(suppliers.status).toBe("incomplete");
    expect(suppliers.tip).toEqual([
      SUPPLIERS_ABOUT,
      "Purchases ÷ net sales (cash basis): 23.7%.",
      "1 of 3 branches incomplete.",
    ]);
    // Never the forbidden words, anywhere on a tile.
    for (const tile of tiles(full)) {
      const words = [tile.label, tile.line, ...tile.tip].join(" ");
      expect(words).not.toMatch(/food cost|net profit/i);
    }
  });

  it("carries a chip only where the word is a caveat", async () => {
    expect(tileChip("estimated")).toBe("estimated");
    expect(tileChip("incomplete")).toBe("incomplete");
    expect(tileChip("reliable_with_limitations")).toBeNull();
    expect(tileChip("unavailable")).toBeNull();
    const [sold, kept, suppliers] = tiles(await scenario("quiet"));
    expect([sold.status, kept.status, suppliers.status]).toEqual([null, null, null]);
    expect(kept.bar).toEqual({ width: 100, words: "covers 100% of what sold" });
  });

  it("carries the word beside the day when the sales are old", async () => {
    const [sold, kept, suppliers] = tiles(await scenario("partial"));
    expect(sold.figure).toBe("AED 51,595");
    expect(sold.line).toBe("AED 7,726 on Mon 31 Aug");
    expect(sold.status).toBe("estimated");
    expect(sold.tip).toEqual([SOLD_ABOUT, "Taken across 2 branches that day."]);
    expect(kept.status).toBe("incomplete");
    expect(suppliers.status).toBe("incomplete");
    expect(suppliers.line).toBe("AED 31 of every 100 sold");
  });

  it("is the branch's own row under the filter, with the chain named beside it", async () => {
    const quoz = await scenario("full", "br-01");
    const [sold, kept, suppliers] = tiles(quoz);
    // The branch's figures, never the chain's - the league row on the same
    // screen says the same numbers - and the branch named once.
    expect(sold.caption).toBe("Al Quoz");
    expect(sold.figure).toBe("AED 30,719");
    expect(sold.line).toBe("AED 4,385 on Mon 31 Aug");
    expect(sold.tip).toEqual([SOLD_ABOUT]);
    expect(kept.caption).toBeNull();
    expect(kept.figure).toBe("AED 18,319");
    expect(kept.line).toBe("AED 70 of every 100 sold · chain AED 67");
    expect(kept.bar).toEqual({ width: 86, words: "covers 86% of what sold" });
    // Not the chain's 84.2%, which the same read still carries.
    expect(quoz.total.costed_share_pct).toBe("84.2");
    expect(suppliers.figure).toBe("AED 11,898");
    expect(suppliers.line).toBe("AED 39 of every 100 sold · chain AED 24");
    expect(suppliers.status).toBeNull();
    expect(suppliers.tip).toEqual([
      SUPPLIERS_ABOUT,
      "Purchases ÷ net sales (cash basis): 38.7%.",
      "3 deliveries in this window.",
    ]);
  });

  it("says why the kept tile is empty when there is no menu, and still counts the papers", async () => {
    const [sold, kept, suppliers] = tiles(await scenario("nomenu"));
    expect(sold.figure).toBe("AED 67,471");
    expect(kept.figure).toBeNull();
    expect(kept.words).toBe("No menu is loaded, so nothing can be costed yet.");
    expect(kept.line).toBe("");
    expect(kept.status).toBeNull();
    expect(kept.bar).toBeNull();
    expect(kept.tip).toEqual([]);
    expect(suppliers.figure).toBe("AED 16,019");
    const filtered = tiles(await scenario("nomenu", "br-01"));
    expect(filtered[0].caption).toBe("Al Quoz");
    expect(filtered[1].words).toBe("No menu is loaded, so nothing can be costed yet.");
  });

  it("shows no tile at all on a first run", async () => {
    expect(tiles(await scenario("empty"))).toEqual([]);
    expect(tiles(await scenario("empty", "br-01"))).toEqual([]);
  });

  it("names a loss as a loss, rounded up by its size, with no share beside it", async () => {
    const quiet = await scenario("quiet");
    const losing = {
      ...quiet,
      total: { ...quiet.total, contribution: "-411.50", contribution_pct: "-1.4" },
    };
    const [, kept] = tiles(losing);
    expect(kept.loss).toBe(true);
    expect(kept.figure).toBe("-AED 412");
    expect(kept.line).toBe("");
  });

  it("says no confirmed purchases in words rather than printing AED 0", async () => {
    const full = await scenario("full");
    const nothing = { ...full, total: { ...full.total, purchases: "0.00", ratio_pct: null } };
    const [, , suppliers] = tiles(nothing);
    expect(suppliers.figure).toBeNull();
    expect(suppliers.words).toBe("No confirmed purchases");
    expect(suppliers.line).toBe("");
    expect(suppliers.status).toBeNull();
  });

  it("names the newest loaded day, the chain's or the branch's own", async () => {
    const full = await scenario("full");
    expect(latestDay(full)).toEqual({
      line: "AED 9,493 on Mon 31 Aug",
      tip: "Taken across 3 branches that day.",
    });
    expect(latestDay({ ...full, latest_day: null })).toBeNull();
    expect(latestDay(await scenario("full", "br-02"))).toEqual({
      line: "AED 2,987 on Mon 31 Aug",
      tip: null,
    });
  });
});

// The founder's redesign (2026-09-07). Every line a tooltip prints is a
// sentence the API sent or a join this module already made: these cases pin
// that the words survived the move off the flow, and that a bar is a
// percentage the API sent and never a division done here.
describe("the info tips", () => {
  it("holds the screen's own subtitle behind the icon beside the title", () => {
    expect(SCREEN_ABOUT).toBe(
      "What each branch and each dish kept after ingredients and packaging, over the days you have loaded.",
    );
  });

  it("puts the answer's word inline and the API's notes behind the icon", async () => {
    const full = await scenario("full");
    expect(answerChip(full)).toBe("estimated");
    expect(answerTip(full)).toEqual([
      "Covers 82% of this branch's sales value.",
      "1 item cannot be costed yet.",
      "1 till name with sales is not mapped to a menu item.",
    ]);

    const partial = await scenario("partial");
    expect(answerChip(partial)).toBe("incomplete");
    expect(answerTip(partial)[0]).toBe("1 of 7 days has no sales.");

    const quiet = await scenario("quiet");
    expect(answerChip(quiet)).toBeNull();
    expect(answerTip(quiet)).toEqual([]);
    expect(answerChip(await scenario("nomenu"))).toBeNull();
  });

  it("puts a league row's whole story behind its one icon", async () => {
    const full = await scenario("full");
    const [deira, karama] = full.league;
    expect(leagueTip(deira)).toEqual([
      "25-31 Aug, 7 days · 1 delivery",
      "AED 4,121 paid to suppliers, AED 26 of every 100 sold",
      "Covers 82% of this branch's sales value.",
      "1 item cannot be costed yet.",
      "1 till name with sales is not mapped to a menu item.",
    ]);
    // Karama bought nothing in the window, and the line says so in the cell's
    // own words rather than printing AED 0.
    expect(karama.ratio_pct).toBeNull();
    expect(leagueTip(karama).slice(0, 2)).toEqual([leagueLine(karama), "No confirmed purchases"]);
    expect(leagueTip(karama).slice(2)).toEqual(statusTip(karama));
    // The chain has no window of its own to name.
    expect(totalTip(full.total)).toEqual([
      "AED 16,019 paid to suppliers, AED 24 of every 100 sold",
      ...statusTip(full.total),
    ]);
    const nothing = { ...full.total, purchases: "0.00", ratio_pct: null };
    expect(totalTip(nothing)[0]).toBe("No confirmed purchases");
  });

  it("cuts the status sentences and the footnote into one line each", async () => {
    const full = await scenario("full");
    expect(statusTip(full.league[0])).toEqual([
      "Covers 82% of this branch's sales value.",
      "1 item cannot be costed yet.",
      "1 till name with sales is not mapped to a menu item.",
    ]);
    // Nothing is dropped in the cutting: the lines join back into the sentence.
    expect(statusTip(full.total)).toHaveLength(4);
    expect(statusTip(full.total).join(" ")).toBe(leagueStatus(full.total).sentence);
    const tip = footnoteTip(full);
    expect(tip).toHaveLength(3);
    expect(tip.join(" ")).toBe(leagueFootnote(full));
    expect(tip[1]).toMatch(/^It is not profit/);
  });

  it("puts a signal's detail behind the icon, and the date a price moved on", () => {
    const popular = signal();
    expect(signalTip(popular)).toEqual([popular.detail]);
    const spike = signal({
      kind: "price_spike",
      invoice_id: "inv-1001",
      moved_on: "2026-08-21",
      menu_item_id: null,
      detail: "Milk Powder is AED 2.10 a kg dearer than the last paper. (estimated)",
    });
    expect(signalTip(spike)).toEqual([spike.detail, "since 21 Aug"]);
  });

  it("keeps the dishes' paragraph, word for word, behind its heading", () => {
    expect(itemsTip()).toEqual([
      "Kept is the till's own net takings for the dish less what its recipe costs at the prices in force on the period's last day; it is not profit, and cost covers what the recipe lists.",
    ]);
  });

  it("shows three signals, then the rest", async () => {
    const full = await scenario("full");
    expect(signalPanel(full.signals, false)).toHaveLength(3);
    expect(signalPanel(full.signals, false)).toEqual(full.signals.slice(0, 3));
    expect(signalPanel(full.signals, true)).toEqual(full.signals);
    expect(showAllSignalsLabel(5, false)).toBe("Show all 5");
    expect(showAllSignalsLabel(5, true)).toBe("Show the top 3 only");
    expect(showAllSignalsLabel(3, false)).toBeNull();
    expect(showAllSignalsLabel(0, false)).toBeNull();
  });

  it("draws a bar from the percentage the API sent, and never divides one", () => {
    expect(keptBar("60.9")).toBe(60.9);
    expect(keptBar("100.0")).toBe(100);
    expect(keptBar("0.0")).toBe(0);
    // A branch that lost money gets an empty track; the figure beside it says so.
    expect(keptBar("-1.4")).toBe(0);
    expect(keptBar("140.2")).toBe(100);
    expect(keptBar(null)).toBeNull();
    expect(keptBar("not a number")).toBeNull();
  });
});

describe("the whole numbers", () => {
  it("round a percentage the way the API's own sentences do, and never divide", () => {
    expect(wholePercent("60.9")).toBe("61%");
    expect(wholePercent("67.4")).toBe("67%");
    expect(wholePercent("100.0")).toBe("100%");
    expect(wholePercent("-5.3")).toBe("-5%");
    expect(wholePercent(null)).toBeNull();
    expect(wholePercent("not a number")).toBeNull();
    expect(everyHundred("23.7")).toBe("AED 24 of every 100");
    expect(everyHundred("60.9")).toBe("AED 61 of every 100");
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
