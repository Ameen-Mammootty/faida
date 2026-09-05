import { describe, expect, it } from "vitest";
import { groupedMoney, money, roundedAed } from "../format";

/**
 * M9 WP-98 (D7): the headline rounding. `roundedAed` truncated until the
 * founder decided it should round half up like every sentence the API
 * composes, so these pin the rule at the fils that decide it - and pin that
 * the exact renderers beside it did not move, because a headline rounds and
 * an invoice figure never does.
 */
describe("roundedAed", () => {
  it("keeps the dirham below half a dirham", () => {
    expect(roundedAed("411.49")).toBe("AED 411");
    expect(roundedAed("411.00")).toBe("AED 411");
    expect(roundedAed("411")).toBe("AED 411");
  });

  it("goes up at half a dirham and above", () => {
    expect(roundedAed("411.50")).toBe("AED 412");
    expect(roundedAed("411.51")).toBe("AED 412");
    expect(roundedAed("411.999")).toBe("AED 412");
  });

  it("carries through the nines", () => {
    expect(roundedAed("999.50")).toBe("AED 1,000");
    expect(roundedAed("0.50")).toBe("AED 1");
    expect(roundedAed("0.49")).toBe("AED 0");
  });

  it("groups thousands as it always did", () => {
    expect(roundedAed("67471.13")).toBe("AED 67,471");
    expect(roundedAed("1234567.80")).toBe("AED 1,234,568");
  });

  it("rounds a loss by its size, so a loss is never understated", () => {
    // The dashboard and the menu print this one as "-AED 412": the sign is
    // the screen's, the magnitude is this function's.
    expect(roundedAed("-411.50")).toBe("AED -412");
    expect(roundedAed("-411.49")).toBe("AED -411");
  });

  it("leaves the exact renderers alone", () => {
    expect(money("411.50")).toBe("411.50");
    expect(groupedMoney("67471.135")).toBe("67,471.135");
  });
});
