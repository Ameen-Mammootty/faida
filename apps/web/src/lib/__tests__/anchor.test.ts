import { describe, expect, it } from "vitest";
import {
  anchorBranchId,
  anchorId,
  anchorItemId,
  anchorMaterialId,
  menuAnchor,
  menuGroupKey,
  salesAnchorBranchId,
} from "../anchor";
import type { BranchRow, MenuItemSummary, Plate } from "../types";

/**
 * M9 WP-94: the app's one anchor idiom, pinned.
 *
 * Three screens read `#<thing>-<id>` out of a URL and open the row it names.
 * What a component does with that answer - scroll, focus, once - is three
 * lines beside its own drill ref; *which row the hash names* is decided here,
 * because a component cannot be unit tested in this project and a wrong
 * answer is a link that silently goes nowhere.
 */

function plate(quality: Plate["quality"]): Plate {
  return {
    quality,
    cost_per_portion: quality === "incomplete" ? null : "6.204",
    net_price: "33.333",
    vat_rate: "0.05",
    margin: quality === "incomplete" ? null : "28.551",
    margin_pct: quality === "incomplete" ? null : "85.7",
    missing: quality === "incomplete" ? ["no recipe yet"] : [],
  };
}

function item(overrides: Partial<MenuItemSummary> = {}): MenuItemSummary {
  return {
    id: "menu-2",
    name: "Karak Tea (Flask 1 L)",
    category: "Tea Corner",
    selling_price: "35.000",
    archived_at: null,
    created_at: "2026-08-27T06:00:00+00:00",
    plate: plate("reliable_with_limitations"),
    recipe: null,
    ...overrides,
  };
}

function branchRow(overrides: Partial<BranchRow> = {}): BranchRow {
  return {
    branch_id: "br-03",
    branch_name: "Deira",
    window: { from: "2026-08-25", to: "2026-08-31", days: 7 },
    net_sales: "15845.85",
    takings: "16638.14",
    purchases: "4120.60",
    ratio_pct: "26.0",
    quality: "reliable_with_limitations",
    notes: [],
    days: [],
    pending: [],
    excluded: [],
    days_loaded: 7,
    days_missing: 0,
    deliveries: 1,
    sales_through: "2026-08-31",
    last_purchase_on: "2026-08-27",
    ...overrides,
  };
}

describe("reading a hash", () => {
  it("takes the id out of the fragment its screen wrote", () => {
    expect(anchorMaterialId("#material-ing-nido")).toBe("ing-nido");
    expect(anchorItemId("#item-menu-2")).toBe("menu-2");
    expect(anchorBranchId("#branch-br-03")).toBe("br-03");
  });

  it("keeps a hyphenated id whole, which every id in this app is", () => {
    expect(anchorItemId("#item-8f1e-44ab-9c02")).toBe("8f1e-44ab-9c02");
  });

  it("answers null for no hash, another screen's hash, and an empty id", () => {
    expect(anchorItemId("")).toBeNull();
    expect(anchorItemId("#")).toBeNull();
    expect(anchorItemId("#item-")).toBeNull();
    expect(anchorItemId("#material-ing-nido")).toBeNull();
    expect(anchorItemId("#line-3")).toBeNull();
    // "#items-..." is not "#item-...": the separator is part of the prefix.
    expect(anchorItemId("#items-menu-2")).toBeNull();
  });

  it("decodes what the link encoded, and never throws on a fragment it cannot", () => {
    expect(anchorBranchId("#branch-br%2F03")).toBe("br/03");
    expect(anchorBranchId("#branch-%E2%98%95")).toBe("☕");
    expect(anchorBranchId("#branch-100%")).toBe("100%");
  });

  it("is one function; the three named forms only fix the prefix", () => {
    expect(anchorId("#line-3", "line")).toBe("3");
  });
});

describe("which row on /menu", () => {
  it("names a costed item's row and the group to open first", () => {
    const items = [item()];
    expect(menuAnchor("#item-menu-2", items)).toEqual({
      kind: "ranked",
      id: "menu-2",
      groupKey: "Tea Corner",
    });
  });

  it("gives a menu that prints no sections the one unlabelled group's key", () => {
    const items = [item({ category: null })];
    expect(menuAnchor("#item-menu-2", items)).toEqual({
      kind: "ranked",
      id: "menu-2",
      groupKey: menuGroupKey(null),
    });
    expect(menuGroupKey(null)).toBe("(none)");
    expect(menuGroupKey("Shakes")).toBe("Shakes");
  });

  it("sends an item with no plate to the can't-be-costed-yet section, with nothing to open", () => {
    const items = [item({ id: "menu-4", plate: plate("incomplete") })];
    expect(menuAnchor("#item-menu-4", items)).toEqual({ kind: "uncosted", id: "menu-4" });
  });

  it("expands nothing for an archived item: it appears nowhere on that screen", () => {
    const items = [item({ archived_at: "2026-08-28T09:00:00+00:00" })];
    expect(menuAnchor("#item-menu-2", items)).toBeNull();
  });

  it("expands nothing for an id no item carries, and nothing for no hash at all", () => {
    const items = [item()];
    expect(menuAnchor("#item-nope", items)).toBeNull();
    expect(menuAnchor("", items)).toBeNull();
    expect(menuAnchor("#item-menu-2", [])).toBeNull();
  });

  it("still names a live item when an archived one shares the list", () => {
    const items = [item({ archived_at: "2026-08-28T09:00:00+00:00" }), item({ category: "Shakes" })];
    expect(menuAnchor("#item-menu-2", items)).toEqual({
      kind: "ranked",
      id: "menu-2",
      groupKey: "Shakes",
    });
  });
});

describe("which row on /sales", () => {
  it("names the branch when the table carries it", () => {
    expect(salesAnchorBranchId("#branch-br-03", [branchRow()])).toBe("br-03");
  });

  it("names it even with nothing loaded, because that row is the answer", () => {
    const empty = branchRow({ net_sales: null, quality: "unavailable", deliveries: 0 });
    expect(salesAnchorBranchId("#branch-br-03", [empty])).toBe("br-03");
  });

  it("opens nothing for a branch this tenant does not have, and for no hash", () => {
    expect(salesAnchorBranchId("#branch-br-99", [branchRow()])).toBeNull();
    expect(salesAnchorBranchId("", [branchRow()])).toBeNull();
    expect(salesAnchorBranchId("#material-ing-nido", [branchRow()])).toBeNull();
  });
});
