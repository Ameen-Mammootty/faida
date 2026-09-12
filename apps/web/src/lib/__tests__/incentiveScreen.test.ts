import { describe, expect, it } from "vitest";

import {
  MONTH_FROZEN_NOTE,
  SHARES_APPLIES_NOTE,
  canCreateMonth,
  canSaveShares,
  capWords,
  createStanding,
  monthOf,
  monthOptions,
  monthWords,
  plainPct,
  schemeMonthBody,
  shareBody,
  shareDraft,
  sharesUpdatedWords,
  standing,
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
    expect(sumWords(draft("40", "25", "35"))).toBe("The three shares split the whole pool.");
  });

  it("says how much is left", () => {
    expect(sumWords(draft("40", "25", "30"))).toBe("95% of the pool allocated, 5% left.");
  });

  it("says how much too much", () => {
    expect(sumWords(draft("40", "30", "35"))).toBe(
      "105% of the pool allocated, 5% more than the pool.",
    );
  });

  it("adds fractional shares exactly, where floats would not", () => {
    // 10 + 58.01 + 31.99 is 99.99999999999999 as JavaScript numbers, which
    // read as a whole pool the owner could not save.
    expect(sumWords(draft("10", "58.01", "31.99"))).toBe("The three shares split the whole pool.");
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
    expect(canSaveShares(draft("33.334", "33.333", "33.333"), SAVED)).toBe(false);
  });

  it("counts a fractional share to one decimal", () => {
    expect(sumWords(draft("33.3", "33.3", "33.3"))).toBe("99.9% of the pool allocated, 0.1% left.");
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
    for (const bad of [draft("40", "25", "30"), draft("-10", "60", "50"), draft("", "", "")]) {
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
    expect(standing({ ...EMPTY, shares: null })).toContain("Set the three shares first");
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
    expect(monthOptions(FULL).map((option) => option.created)).toEqual([false, false, true]);
  });

  it("keeps a month already created, however old", () => {
    const old = { ...EMPTY, months: [{ id: "sm-1", month: "2025-03", words: "March 2025" }] };
    expect(monthOptions(old).map((option) => option.month)).toContain("2025-03");
  });

  it("keeps the month in view even when it is neither", () => {
    expect(monthOptions({ ...EMPTY, month: "2027-04" }).map((o) => o.month)).toContain("2027-04");
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
    expect(Object.keys(drafts)).toEqual(EMPTY.branches.map((branch) => branch.id));
    expect(Object.values(drafts)).toEqual(
      EMPTY.branches.map(() => ({ net: "", pct: "", cap: "" })),
    );
    // The advice is there to read, beside the box it never fills.
    expect(EMPTY.branches[0].previous_month_words).toBe("AED 58,210 last month");
    expect(EMPTY.branches[2].previous_month_words).toBe("no sales loaded last month");
  });

  it("offers Create only once every branch has a target and a percentage", () => {
    const branches = EMPTY.branches;
    const drafts = targetDrafts(branches);
    expect(canCreateMonth(drafts, branches)).toBe(false);

    const filled = Object.fromEntries(
      branches.map((branch) => [branch.id, { net: "50000", pct: "10", cap: "" }]),
    );
    expect(canCreateMonth(filled, branches)).toBe(true);

    // One branch left out is not a month.
    const partial = { ...filled, [branches[1].id]: { net: "", pct: "10", cap: "" } };
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
        { branch_id: branches[0].id, net_sales_target: "60000", above_target_pct: "10", cap: null },
        {
          branch_id: branches[1].id,
          net_sales_target: "40000",
          above_target_pct: "10",
          cap: "1500",
        },
        { branch_id: branches[2].id, net_sales_target: "30000", above_target_pct: "8", cap: null },
      ],
    });
  });

  it("says what is still needed, then what creating commits to", () => {
    const branches = EMPTY.branches;
    expect(createStanding(targetDrafts(branches), branches)).toContain(
      "for every branch",
    );
    const filled = Object.fromEntries(
      branches.map((branch) => [branch.id, { net: "50000", pct: "10", cap: "" }]),
    );
    expect(createStanding(filled, branches)).toContain("frozen when you create it");
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
    expect(tabs[2].note).toBe("The week of 14-20 Sep has started and is frozen.");
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
        frozen_words: week.start <= today ? `the week of ${week.words} is frozen` : null,
      })),
      today,
    );

  it("opens on the first week still to come when none is running", () => {
    const early = readOn("2026-08-30");
    expect(early.map((tab) => tab.state)).toEqual(["coming", "coming", "coming", "coming", "coming"]);
    expect(weekInView(early)).toBe(early[0].id);
  });

  it("opens on the last week of a month that has ended", () => {
    const over = readOn("2026-10-05");
    expect(over.map((tab) => tab.state)).toEqual(["ended", "ended", "ended", "ended", "ended"]);
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
    expect(scheme.shares).toEqual(CREATED.shares && {
      manager_pct: CREATED.shares.manager_pct,
      supervisor_pct: CREATED.shares.supervisor_pct,
      sales_pct: CREATED.shares.sales_pct,
    });
    expect(MONTH_FROZEN_NOTE).toContain("frozen");
  });
});
