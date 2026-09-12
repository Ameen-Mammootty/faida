import { describe, expect, it } from "vitest";

import {
  MONTH_FROZEN_NOTE,
  OFF_THE_MENU,
  SHARES_APPLIES_NOTE,
  canCreateMonth,
  canSavePushList,
  canSaveShares,
  capWords,
  createStanding,
  draftGroups,
  guidanceWords,
  loadedThrough,
  menuIndex,
  monthOf,
  monthOptions,
  monthWords,
  pickerGroups,
  pickerLabel,
  plainPct,
  pushDraft,
  pushListBody,
  pushRowFor,
  pushStanding,
  schemeMonthBody,
  shareBody,
  shareDraft,
  sharesUpdatedWords,
  soFar,
  standing,
  statementFigures,
  statementWeeks,
  sumWords,
  targetDrafts,
  targetOf,
  weekInView,
  weekTabs,
} from "../incentiveScreen";
import created from "../mock/incentive/created.json";
import empty from "../mock/incentive/empty.json";
import full from "../mock/incentive/full.json";
import type { IncentiveRead, RoleSharesRow } from "../types";

// The fixtures the mock serves, produced by the shipped Python module
// (`mock/incentive/generate.py`): September 2026 read on 16 Sep, with a full
// month, a month just created, and no month at all.
const FULL = full as unknown as IncentiveRead;
const CREATED = created as unknown as IncentiveRead;
const EMPTY = empty as unknown as IncentiveRead;

const SAVED: RoleSharesRow = {
  manager_pct: "40.00",
  supervisor_pct: "25.00",
  sales_pct: "35.00",
  updated_at: "2026-08-28T09:12:00+00:00",
};

const draft = (manager: string, supervisor: string, sales: string) => ({
  manager,
  supervisor,
  sales,
});

describe("the three boxes", () => {
  it("opens on the shares on file, as plain percentages", () => {
    expect(shareDraft(SAVED)).toEqual({
      manager: "40",
      supervisor: "25",
      sales: "35",
    });
  });

  it("keeps a fractional share", () => {
    expect(plainPct("12.50")).toBe("12.5");
  });

  it("leaves what is not a number alone, so the box shows what was typed", () => {
    expect(plainPct("forty")).toBe("forty");
  });

  it("opens empty when nothing is set", () => {
    expect(shareDraft(null)).toEqual({
      manager: "",
      supervisor: "",
      sales: "",
    });
  });

  it("sends the three strings as typed, trimmed - the API parses them", () => {
    expect(shareBody(draft(" 40 ", "25", "35"))).toEqual({
      manager_pct: "40",
      supervisor_pct: "25",
      sales_pct: "35",
    });
  });
});

describe("the running total", () => {
  it("says the pool is whole when it is", () => {
    expect(sumWords(draft("40", "25", "35"))).toBe(
      "The three shares split the whole pool.",
    );
  });

  it("says how much is left", () => {
    expect(sumWords(draft("40", "25", "30"))).toBe(
      "95% of the pool allocated, 5% left.",
    );
  });

  it("says how much too much", () => {
    expect(sumWords(draft("40", "30", "35"))).toBe(
      "105% of the pool allocated, 5% more than the pool.",
    );
  });

  it("adds fractional shares exactly, where floats would not", () => {
    // 10 + 58.01 + 31.99 is 99.99999999999999 as JavaScript numbers, which
    // read as a whole pool the owner could not save.
    expect(sumWords(draft("10", "58.01", "31.99"))).toBe(
      "The three shares split the whole pool.",
    );
    expect(canSaveShares(draft("10", "58.01", "31.99"), SAVED)).toBe(true);
  });

  it("keeps two decimals in the sentence", () => {
    expect(sumWords(draft("10", "58.01", "31.98"))).toBe(
      "99.99% of the pool allocated, 0.01% left.",
    );
  });

  it("asks for a percentage when a share is written to a third decimal, as the API does", () => {
    expect(sumWords(draft("33.334", "33.333", "33.333"))).toBe(
      "Three percentages, adding to 100, split the pool.",
    );
    expect(canSaveShares(draft("33.334", "33.333", "33.333"), SAVED)).toBe(
      false,
    );
  });

  it("counts a fractional share to one decimal", () => {
    expect(sumWords(draft("33.3", "33.3", "33.3"))).toBe(
      "99.9% of the pool allocated, 0.1% left.",
    );
  });

  it("asks for three percentages while a box is empty or half-typed", () => {
    expect(sumWords(draft("40", "", "35"))).toBe(
      "Three percentages, adding to 100, split the pool.",
    );
    expect(sumWords(draft("40", "25.", "35"))).toBe(
      "Three percentages, adding to 100, split the pool.",
    );
  });

  it("never words a refusal - that sentence is the API's", () => {
    for (const bad of [
      draft("40", "25", "30"),
      draft("-10", "60", "50"),
      draft("", "", ""),
    ]) {
      expect(sumWords(bad)).not.toContain("cannot");
      expect(sumWords(bad)).not.toContain("not 100%");
    }
  });
});

describe("whether Save is offered", () => {
  it("is offered when the three add to a hundred and differ from what is saved", () => {
    expect(canSaveShares(draft("50", "20", "30"), SAVED)).toBe(true);
    expect(canSaveShares(draft("50", "20", "30"), null)).toBe(true);
  });

  it("is not offered for the shares already on file", () => {
    expect(canSaveShares(draft("40", "25", "35"), SAVED)).toBe(false);
    expect(canSaveShares(draft("40.0", "25", "35"), SAVED)).toBe(false);
  });

  it("is not offered while the three do not add to a hundred", () => {
    expect(canSaveShares(draft("40", "25", "30"), SAVED)).toBe(false);
    expect(canSaveShares(draft("40", "25", "40"), SAVED)).toBe(false);
  });

  it("is not offered for a negative share, whatever it adds to", () => {
    expect(canSaveShares(draft("-10", "60", "50"), SAVED)).toBe(false);
  });

  it("is not offered while a box is empty or half-typed", () => {
    expect(canSaveShares(draft("40", "", "35"), SAVED)).toBe(false);
    expect(canSaveShares(draft("40", "25.", "35"), SAVED)).toBe(false);
  });
});

describe("the block's words", () => {
  it("dates the last change", () => {
    expect(sharesUpdatedWords(SAVED)).toBe("Last set 28 Aug 2026.");
  });

  it("says plainly when nothing is set", () => {
    expect(sharesUpdatedWords(null)).toBe("Not set yet.");
  });

  it("asks for the shares first when there are none", () => {
    expect(standing({ ...EMPTY, shares: null })).toContain(
      "Set the three shares first",
    );
  });

  it("points at the month to create once they are set", () => {
    expect(standing(EMPTY)).toContain("No scheme month for September 2026 yet");
  });

  it("points at the push lists once the month exists", () => {
    expect(standing(FULL)).toContain("September 2026 is set");
  });

  it("promises a running month is untouched", () => {
    expect(SHARES_APPLIES_NOTE).toContain("keeps the shares it started with");
  });
});

// --- the scheme month (M13.3, issue #9) -------------------------------------

describe("the month picker", () => {
  it("offers this month and the two ahead of it, newest first", () => {
    // The fixtures are read on 16 September 2026 with a September month on
    // file: November, October, September, and September is the one created.
    expect(monthOptions(FULL).map((option) => option.month)).toEqual([
      "2026-11",
      "2026-10",
      "2026-09",
    ]);
    expect(monthOptions(FULL).map((option) => option.created)).toEqual([
      false,
      false,
      true,
    ]);
  });

  it("keeps a month already created, however old", () => {
    const old = {
      ...EMPTY,
      months: [{ id: "sm-1", month: "2025-03", words: "March 2025" }],
    };
    expect(monthOptions(old).map((option) => option.month)).toContain(
      "2025-03",
    );
  });

  it("keeps the month in view even when it is neither", () => {
    expect(
      monthOptions({ ...EMPTY, month: "2027-04" }).map((o) => o.month),
    ).toContain("2027-04");
  });

  it("names a month the way the API names it", () => {
    expect(monthWords("2026-07")).toBe("July 2026");
    expect(monthWords("2026-12")).toBe("December 2026");
    expect(monthOf("2026-09-16")).toBe("2026-09");
  });
});

describe("the create form", () => {
  it("opens with empty boxes, so last month is advice and never the baseline", () => {
    const drafts = targetDrafts(EMPTY.branches);
    expect(Object.keys(drafts)).toEqual(
      EMPTY.branches.map((branch) => branch.id),
    );
    expect(Object.values(drafts)).toEqual(
      EMPTY.branches.map(() => ({ net: "", pct: "", cap: "" })),
    );
    // The advice is there to read, beside the box it never fills.
    expect(EMPTY.branches[0].previous_month_words).toBe(
      "AED 58,210 last month",
    );
    expect(EMPTY.branches[2].previous_month_words).toBe(
      "no sales loaded last month",
    );
  });

  it("offers Create only once every branch has a target and a percentage", () => {
    const branches = EMPTY.branches;
    const drafts = targetDrafts(branches);
    expect(canCreateMonth(drafts, branches)).toBe(false);

    const filled = Object.fromEntries(
      branches.map((branch) => [
        branch.id,
        { net: "50000", pct: "10", cap: "" },
      ]),
    );
    expect(canCreateMonth(filled, branches)).toBe(true);

    // One branch left out is not a month.
    const partial = {
      ...filled,
      [branches[1].id]: { net: "", pct: "10", cap: "" },
    };
    expect(canCreateMonth(partial, branches)).toBe(false);
  });

  it("leaves a figure the API refuses to the API, so the owner reads why", () => {
    const branches = EMPTY.branches;
    const wrong = Object.fromEntries(
      branches.map((branch) => [branch.id, { net: "-1", pct: "101", cap: "" }]),
    );
    expect(canCreateMonth(wrong, branches)).toBe(true);
  });

  it("sends the strings as typed, with a blank cap as no cap", () => {
    const branches = EMPTY.branches;
    const drafts = {
      [branches[0].id]: { net: " 60000 ", pct: "10", cap: "" },
      [branches[1].id]: { net: "40000", pct: "10", cap: "1500" },
      [branches[2].id]: { net: "30000", pct: "8", cap: "  " },
    };
    expect(schemeMonthBody("2026-09", drafts, branches)).toEqual({
      month: "2026-09",
      targets: [
        {
          branch_id: branches[0].id,
          net_sales_target: "60000",
          above_target_pct: "10",
          cap: null,
        },
        {
          branch_id: branches[1].id,
          net_sales_target: "40000",
          above_target_pct: "10",
          cap: "1500",
        },
        {
          branch_id: branches[2].id,
          net_sales_target: "30000",
          above_target_pct: "8",
          cap: null,
        },
      ],
    });
  });

  it("says what is still needed, then what creating commits to", () => {
    const branches = EMPTY.branches;
    expect(createStanding(targetDrafts(branches), branches)).toContain(
      "for every branch",
    );
    const filled = Object.fromEntries(
      branches.map((branch) => [
        branch.id,
        { net: "50000", pct: "10", cap: "" },
      ]),
    );
    expect(createStanding(filled, branches)).toContain(
      "frozen when you create it",
    );
  });

  it("says so when the chain has no branches at all", () => {
    expect(canCreateMonth({}, [])).toBe(false);
    expect(createStanding({}, [])).toContain("no branches");
  });
});

describe("the weeks as tabs", () => {
  // September 2026 starts on a Tuesday, so the first week is six days and the
  // last is three; read on 16 September, the week of 14-20 Sep is running.
  const tabs = weekTabs(CREATED.scheme_month!.weeks, CREATED.today);

  it("is one tab per week, labelled the way the API labels it", () => {
    expect(tabs.map((tab) => tab.label)).toEqual([
      "1-6 Sep",
      "7-13 Sep",
      "14-20 Sep",
      "21-27 Sep",
      "28-30 Sep",
    ]);
  });

  it("places each week against today", () => {
    expect(tabs.map((tab) => tab.state)).toEqual([
      "ended",
      "ended",
      "running",
      "coming",
      "coming",
    ]);
  });

  it("frozen is the API's own sentence, and a coming week says what it still needs", () => {
    expect(tabs[0].frozen).toBe(true);
    expect(tabs[0].note).toBe("The week of 1-6 Sep has ended and is frozen.");
    expect(tabs[2].frozen).toBe(true);
    expect(tabs[2].note).toBe(
      "The week of 14-20 Sep has started and is frozen.",
    );
    expect(tabs[3].frozen).toBe(false);
    expect(tabs[3].note).toBe("No push list yet.");
  });

  it("counts a list once there is one", () => {
    const filled = weekTabs(FULL.scheme_month!.weeks, FULL.today);
    expect(filled[3].note).toBe("2 dishes on the list.");
  });

  it("opens on the week running today", () => {
    expect(weekInView(tabs)).toBe(tabs[2].id);
  });

  // The API computes `frozen` against the same day it sends as `today`, so a
  // payload read on another day is rebuilt here rather than pretending one
  // day's freeze arrived with another day's date.
  const readOn = (today: string) =>
    weekTabs(
      CREATED.scheme_month!.weeks.map((week) => ({
        ...week,
        frozen: week.start <= today,
        frozen_words:
          week.start <= today ? `the week of ${week.words} is frozen` : null,
      })),
      today,
    );

  it("opens on the first week still to come when none is running", () => {
    const early = readOn("2026-08-30");
    expect(early.map((tab) => tab.state)).toEqual([
      "coming",
      "coming",
      "coming",
      "coming",
      "coming",
    ]);
    expect(weekInView(early)).toBe(early[0].id);
  });

  it("opens on the last week of a month that has ended", () => {
    const over = readOn("2026-10-05");
    expect(over.map((tab) => tab.state)).toEqual([
      "ended",
      "ended",
      "ended",
      "ended",
      "ended",
    ]);
    expect(weekInView(over)).toBe(over[4].id);
    expect(weekInView([])).toBeNull();
  });
});

describe("the month once it exists", () => {
  const scheme = CREATED.scheme_month!;

  it("finds each branch's own targets", () => {
    const target = targetOf(scheme, CREATED.branches[1].id);
    expect(target?.net_sales_target).toBe("40000.00");
    expect(target?.above_target_pct).toBe("10.00");
    expect(targetOf(scheme, "no-such-branch")).toBeNull();
  });

  it("says a blank cap is no cap, because blank was a decision", () => {
    expect(capWords(targetOf(scheme, CREATED.branches[0].id))).toBe("No cap");
    expect(capWords(targetOf(scheme, CREATED.branches[1].id))).toBe("1,500.00");
    expect(capWords(null)).toBe("No target");
  });

  it("carries the shares it was created with", () => {
    expect(scheme.shares).toEqual(
      CREATED.shares && {
        manager_pct: CREATED.shares.manager_pct,
        supervisor_pct: CREATED.shares.supervisor_pct,
        sales_pct: CREATED.shares.sales_pct,
      },
    );
    expect(MONTH_FROZEN_NOTE).toContain("frozen");
  });
});

describe("the week's push list", () => {
  const scheme = FULL.scheme_month!;
  const index = menuIndex(FULL.menu);
  const tabs = weekTabs(scheme.weeks, FULL.today);
  // 21-27 Sep: the week still to come with two dishes on it, so a draft read
  // off it is a filled list that can still be edited.
  const coming = scheme.weeks[3];
  const comingTab = tabs[3];
  const emptyTab = tabs[4];

  it("reads a stored list back into the boxes the way a person would have typed it", () => {
    const rows = pushDraft(coming, FULL.branches);
    expect(rows.map((row) => index[row.menu_item_id].item.name)).toEqual([
      "Karak Tea (Flask 1 L)",
      "Veg Biryani",
    ]);
    const flask = rows[0];
    expect(flask.rate).toBe("1.5");
    expect(flask.targets[FULL.branches[0].id]).toBe("240");
    expect(flask.targets[FULL.branches[2].id]).toBe("60");
    expect(pushDraft(null, FULL.branches)).toEqual([]);
  });

  it("saving a stored list back unchanged sends what the week already holds", () => {
    const body = pushListBody(pushDraft(coming, FULL.branches), FULL.branches);
    expect(body.items).toHaveLength(2);
    expect(body.items[0].rate_per_portion).toBe("1.5");
    expect(body.items[0].targets.map((target) => target.branch_id)).toEqual(
      FULL.branches.map((branch) => branch.id),
    );
  });

  it("groups the list the menu's own way, in the menu's own order", () => {
    const groups = draftGroups(
      pushDraft(coming, FULL.branches),
      index,
      FULL.menu,
    );
    expect(groups.map((group) => group.category)).toEqual(
      coming.categories.map((category) => category.category),
    );
    expect(groups.map((group) => group.items.length)).toEqual(
      coming.categories.map((category) => category.items.length),
    );
  });

  it("puts a dish that has left the menu last, under a heading no menu has", () => {
    const rows = [
      ...pushDraft(coming, FULL.branches),
      pushRowFor("menu-gone", FULL.branches),
    ];
    const groups = draftGroups(rows, index, FULL.menu);
    expect(groups[groups.length - 1].category).toBe(OFF_THE_MENU);
    expect(FULL.menu.map((group) => group.category)).not.toContain(
      OFF_THE_MENU,
    );
  });

  it("counts a category's dishes, and adds the API's guidance outside one to three", () => {
    const guidance = FULL.menu[0].guidance;
    expect(guidanceWords(1, guidance)).toBe("1 dish");
    expect(guidanceWords(3, guidance)).toBe("3 dishes");
    expect(guidanceWords(4, guidance)).toBe(`4 dishes - ${guidance}`);
    expect(guidanceWords(0, guidance)).toBe(`0 dishes - ${guidance}`);
    expect(guidance).toBe("one to three per category, as a guide");
  });

  it("offers every live dish the list does not already hold, with its own words", () => {
    const rows = pushDraft(coming, FULL.branches);
    const offered = pickerGroups(FULL.menu, rows).flatMap(
      (group) => group.items,
    );
    const taken = new Set(rows.map((row) => row.menu_item_id));
    expect(offered.some((item) => taken.has(item.id))).toBe(false);
    const karak = FULL.menu
      .flatMap((group) => group.items)
      .find((item) => item.name === "Karak Tea (Cup)")!;
    expect(pickerLabel(karak)).toBe(
      "Karak Tea (Cup) - keeps AED 3.95 per plate",
    );
    const cake = FULL.menu
      .flatMap((group) => group.items)
      .find((item) => item.name === "Honey Cake")!;
    expect(cake.mapped).toBe(false);
    expect(pickerLabel(cake)).toBe("Honey Cake - no till name mapped");
  });

  it("offers Save only for a week still open with every rate and every branch typed", () => {
    const rows = pushDraft(coming, FULL.branches);
    expect(canSavePushList(rows, FULL.branches, index, comingTab)).toBe(true);
    // A week under way is shown and never saved, however finished the form.
    expect(canSavePushList(rows, FULL.branches, index, tabs[2])).toBe(false);
    expect(canSavePushList(rows, FULL.branches, index, null)).toBe(false);
    // An empty week is a decision, and saving it is how the owner makes it.
    expect(canSavePushList([], FULL.branches, index, emptyTab)).toBe(true);
  });

  it("will not save a row with a rate or a branch's portions still empty", () => {
    const [first, ...rest] = pushDraft(coming, FULL.branches);
    expect(
      canSavePushList(
        [{ ...first, rate: "" }, ...rest],
        FULL.branches,
        index,
        comingTab,
      ),
    ).toBe(false);
    const blank = {
      ...first,
      targets: { ...first.targets, [FULL.branches[2].id]: "" },
    };
    expect(
      canSavePushList([blank, ...rest], FULL.branches, index, comingTab),
    ).toBe(false);
    expect(canSavePushList(rest, [], index, comingTab)).toBe(false);
  });

  it("will not save a dish that can only ever score zero", () => {
    const cake = FULL.menu
      .flatMap((group) => group.items)
      .find((item) => !item.mapped)!;
    const rows = [
      ...pushDraft(coming, FULL.branches),
      {
        ...pushRowFor(cake.id, FULL.branches),
        rate: "1",
        targets: filled(FULL, "10"),
      },
    ];
    expect(canSavePushList(rows, FULL.branches, index, comingTab)).toBe(false);
    expect(pushStanding(rows, FULL.branches, index, comingTab)).toContain(
      "no till name mapped to it any more",
    );
  });

  it("says what the week still needs, and what saving it commits to", () => {
    expect(pushStanding([], FULL.branches, index, emptyTab)).toContain(
      "Nothing on this week yet",
    );
    const [first, ...rest] = pushDraft(coming, FULL.branches);
    expect(
      pushStanding(
        [{ ...first, rate: "" }, ...rest],
        FULL.branches,
        index,
        comingTab,
      ),
    ).toBe("Type a rate per portion and a portion target for every branch.");
    expect(
      pushStanding(
        pushDraft(coming, FULL.branches),
        FULL.branches,
        index,
        comingTab,
      ),
    ).toContain("every portion above the branch's target");
    expect(pushStanding([], FULL.branches, index, null)).toBe("");
  });

  it("a week under way says the API's own frozen sentence and nothing else", () => {
    expect(
      pushStanding(
        pushDraft(scheme.weeks[2], FULL.branches),
        FULL.branches,
        index,
        tabs[2],
      ),
    ).toBe(tabs[2].note);
    expect(tabs[2].note).toBe(
      "The week of 14-20 Sep has started and is frozen.",
    );
  });

  it("a new row starts empty, with a box for every branch", () => {
    const row = pushRowFor("menu-4", FULL.branches);
    expect(row.rate).toBe("");
    expect(Object.keys(row.targets)).toEqual(
      FULL.branches.map((branch) => branch.id),
    );
    expect(Object.values(row.targets)).toEqual(["", "", ""]);
  });

  it("the menu index files an uncategorised dish where the API filed it", () => {
    const cake = FULL.menu
      .flatMap((group) => group.items)
      .find((item) => !item.mapped)!;
    expect(cake.category).toBeNull();
    expect(index[cake.id].category).toBe("Other");
    expect(index["no-such-dish"]).toBeUndefined();
  });

  it("sends the strings as typed, trimmed", () => {
    const body = pushListBody(
      [
        {
          menu_item_id: "menu-4",
          rate: " 1.50 ",
          targets: filled(FULL, " 40 "),
        },
      ],
      FULL.branches,
    );
    expect(body).toEqual({
      items: [
        {
          menu_item_id: "menu-4",
          rate_per_portion: "1.50",
          targets: FULL.branches.map((branch) => ({
            branch_id: branch.id,
            portion_target: "40",
          })),
        },
      ],
    });
  });
});

/** A portion target typed into every branch's box. */
function filled(read: IncentiveRead, value: string): Record<string, string> {
  return Object.fromEntries(read.branches.map((branch) => [branch.id, value]));
}

// --- the statement (M13.5, issue #11) ---------------------------------------

describe("a branch's statement", () => {
  const scheme = FULL.scheme_month!;
  const quoz = scheme.statements[0];
  const karama = scheme.statements[1];

  it("says so far on every figure that is still moving", () => {
    expect(quoz.status).toBe("provisional");
    const labels = statementFigures(quoz).map((row) => row.label);
    expect(labels).toContain("Net sales so far");
    expect(labels).toContain("Pool so far");
    expect(soFar({ ...quoz, status: "final" }, "Pool")).toBe("Pool");
  });

  it("quotes the API's own words for the net sales and the pool", () => {
    const rows = statementFigures(quoz);
    expect(rows.map((row) => [row.key, row.value])).toEqual([
      ["net", "AED 36,750 of AED 60,000"],
      ["items", "AED 136.50"],
      ["above", "AED 0.00"],
      ["pool", "AED 137"],
    ]);
    expect(rows[2].label).toBe("Earned on sales above target (10%)");
  });

  it("draws no cap row for a month that set no cap", () => {
    expect(quoz.figures.cap).toBeNull();
    expect(statementFigures(quoz).some((row) => row.key === "cap")).toBe(false);
  });

  it("says a cap has been reached and leaves the figure before it to the API", () => {
    const cap = statementFigures(karama).find((row) => row.key === "cap")!;
    expect(cap.label).toBe("Cap, reached");
    expect(cap.value).toBe("AED 1,500.00");
    // The pool beside it is the cap, and what the portions actually earned is
    // the API's own note under the block.
    expect(statementFigures(karama).at(-1)!.value).toBe("AED 1,500");
    expect(karama.notes).toContain(
      "capped at AED 1,500; AED 2,018 earned before the cap",
    );
  });

  it("a cap that has not bound is a figure and not a warning", () => {
    const under = {
      ...karama,
      figures: { ...karama.figures, capped: false },
    };
    expect(
      statementFigures(under).find((row) => row.key === "cap")!.label,
    ).toBe("Cap");
  });

  it("never turns a pool it does not have into a nought", () => {
    const nothing = {
      ...quoz,
      newest_loaded: null,
      figures: {
        ...quoz.figures,
        pool: null,
        pool_rounded: null,
        split: null,
        pool_words: "nothing loaded yet",
      },
    };
    expect(statementFigures(nothing).at(-1)!.value).toBe("nothing loaded yet");
    expect(loadedThrough(nothing)).toBe(
      "No day of this month is loaded for this branch yet.",
    );
  });

  it("labels a scored week the way the month's own tab labels it", () => {
    const weeks = statementWeeks(scheme, quoz);
    expect(weeks.map((week) => week.label)).toEqual(
      weekTabs(scheme.weeks, FULL.today).map((tab) => tab.label),
    );
    expect(weeks[0].words).toBe("2 on the list");
    expect(weeks[0].earned).toBe("AED 54.00");
  });

  it("a week the owner left empty carries its own sentence and no rows", () => {
    const last = statementWeeks(scheme, quoz).at(-1)!;
    expect(last.empty).toBe(true);
    expect(last.words).toBe("no push list");
    expect(last.rows).toEqual([]);
  });

  it("shows a dish's portions against its target in the API's words", () => {
    const karak = statementWeeks(scheme, quoz)[0].rows[0];
    expect(karak.name).toBe("Karak Tea (Cup)");
    expect(karak.words).toBe("1,020 of 900 portions");
    expect(karak.earned).toBe("30.00");
    expect(karak.hole).toBe(false);
  });

  it("a dish that cannot be counted carries its sentence and no figure", () => {
    const cake = statementWeeks(scheme, quoz)[1].rows[2];
    expect(cake.hole).toBe(true);
    expect(cake.earned).toBeNull();
    expect(cake.words).toBe(
      "Honey Cake cannot be counted: no till name is mapped to it",
    );
  });

  it("says which day the figures were read up to", () => {
    expect(loadedThrough(quoz)).toBe("Read up to 15 Sep 2026.");
  });
});
