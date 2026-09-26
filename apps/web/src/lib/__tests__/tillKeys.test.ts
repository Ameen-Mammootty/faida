import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import type { AmountBasis, Branch, SalesGranularity } from "../types";
import { aliasRowFor, amountProblem, branchFor, dayKey, headerKey, nameKey } from "../salesLoad";

/**
 * The answer key for reading a till export, from the loader's side. The API
 * owns every rule in `apps/api/tests/fixtures/till_keys.json` and pins it in
 * `test_till_keys.py`; this file pins that the loader's copy agrees, so the
 * preview says what the door will do. The copy exists because the file is
 * read here, in the browser, before the API sees any of it.
 */

interface Day {
  granularity: SalesGranularity;
  basis: AmountBasis;
  amount: string | null;
  lines: { name: string; code: string | null; qty: string | null; amount: string }[];
}

const KEY = JSON.parse(
  readFileSync(
    fileURLToPath(new URL("../../../../api/tests/fixtures/till_keys.json", import.meta.url)),
    "utf8",
  ),
) as {
  names: { name: string; key: string; why: string }[];
  days: { why: string; same: boolean; a: Day; b: Day }[];
  numbers: { value: string; what: "amount" | "quantity"; accepted: boolean }[];
};

const keyOf = (day: Day) => dayKey(day.granularity, day.basis, day.lines, day.amount);

describe("the loader's copy of the API's till rules", () => {
  it.each(KEY.names)("keys $name as the API does ($why)", ({ name, key }) => {
    expect(nameKey(name)).toBe(key);
  });

  it.each(KEY.days)("calls two days the same exactly when the API does: $why", ({ a, b, same }) => {
    expect(keyOf(a) === keyOf(b)).toBe(same);
  });

  it.each(KEY.numbers)("accepts the $what $value exactly when the API does", ({ value, what, accepted }) => {
    expect(amountProblem(value, what) === null).toBe(accepted);
  });

  it("keys a header the way the API keys a layout's header", () => {
    expect(headerKey(["Qty #", "\ufeffOutlet", "Net Sales (AED)"])).toBe("net sales aed|outlet|qty");
  });
});

describe("a till label the owner taught, printed with different punctuation", () => {
  /** The loop reproduced on 2026-09-26: BARSHA 01 taught, the next export
   * printed BARSHA-01, and teaching it again changed nothing. */
  const TAUGHT: Branch[] = [
    {
      id: "b1",
      name: "Al Barsha Branch",
      timezone: "Asia/Dubai",
      aliases: ["BARSHA 01"],
      alias_rows: [{ id: "a1", branch_id: "b1", alias: "BARSHA 01", alias_key: "barsha 01" }],
    },
  ];

  it("reads as the branch it was taught to", () => {
    expect(branchFor("BARSHA-01", TAUGHT)?.id).toBe("b1");
  });

  it("resolves through the same alias row, so it can still be un-taught", () => {
    expect(aliasRowFor("BARSHA-01", TAUGHT)?.row.id).toBe("a1");
  });
});
