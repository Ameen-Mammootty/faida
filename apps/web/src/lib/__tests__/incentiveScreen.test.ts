import { describe, expect, it } from "vitest";

import {
  SHARES_APPLIES_NOTE,
  canSaveShares,
  plainPct,
  shareBody,
  shareDraft,
  sharesStanding,
  sharesUpdatedWords,
  sumWords,
} from "../incentiveScreen";
import type { RoleSharesRow } from "../types";

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
    expect(sharesStanding(null)).toContain("Set the three shares first");
  });

  it("points at the scheme month once they are set", () => {
    expect(sharesStanding(SAVED)).toContain("scheme month");
  });

  it("promises a running month is untouched", () => {
    expect(SHARES_APPLIES_NOTE).toContain("keeps the shares it started with");
  });
});
