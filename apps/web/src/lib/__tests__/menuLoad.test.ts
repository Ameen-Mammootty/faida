import { describe, expect, it } from "vitest";
import { parseCsv } from "../csv";
import { loadInput, planLoad, readMenuCsv, shareWords, type LoadItem } from "../menuLoad";
import type { Ingredient, MenuItemDetail, MenuItemSummary } from "../types";

/**
 * M12 WP-119 (D13): the optional conversion yield, from the consultant's cell
 * to the wire.
 *
 * The column is the milestone's one compatibility risk - a sheet written
 * before it existed must load byte for byte as it did yesterday - so the
 * first case here is the column's absence, and the rest are the three
 * spellings a real sheet uses for the same fact and the four cells that stop
 * an item rather than being guessed at.
 */

const HEADER_WITHOUT = "item,category,selling price,yield portions,ingredient,qty,unit";
const KARAK_WITHOUT =
  `${HEADER_WITHOUT}\n` +
  "Karak Tea,Tea Corner,5.00,40,CTC black tea,220,g\n" +
  "Karak Tea,Tea Corner,5.00,40,White sugar,400,g\n";

function read(text: string) {
  const parsed = parseCsv(text);
  if (!parsed.ok) throw new Error(parsed.error);
  const result = readMenuCsv(parsed.header, parsed.rows);
  if (!result.ok) throw new Error(result.error);
  return result;
}

/** One item, one ingredient, with whatever the share column says. */
function oneShare(cell: string, header = "usable share") {
  const { items } = read(
    `item,category,selling price,yield portions,ingredient,qty,unit,${header}\n` +
      `Chicken Mandi,Mandi,22.00,4,Chicken,1200,g,${cell}\n`,
  );
  return items[0].lines[0];
}

describe("the usable share column", () => {
  it("is optional - a sheet without it reads exactly as it did before", () => {
    const { items, ignoredColumns } = read(KARAK_WITHOUT);
    expect(ignoredColumns).toEqual([]);
    expect(items).toHaveLength(1);
    expect(items[0].problems).toEqual([]);
    expect(items[0].lines.map((line) => line.problem)).toEqual([null, null]);
    expect(items[0].lines.map((line) => line.usableShare)).toEqual([null, null]);
  });

  it("reads a percent, a bare number and a fraction as the same share", () => {
    expect(oneShare("85%").usableShare).toBe("0.85");
    expect(oneShare("85").usableShare).toBe("0.85");
    expect(oneShare("0.85").usableShare).toBe("0.85");
    expect(oneShare(" 85 % ").usableShare).toBe("0.85");
    expect(oneShare("0.8500").usableShare).toBe("0.85");
  });

  it("reads a whole yield as one, and keeps four places of a fine one", () => {
    expect(oneShare("100%").usableShare).toBe("1");
    expect(oneShare("100").usableShare).toBe("1");
    expect(oneShare("1").usableShare).toBe("1");
    expect(oneShare("92.5%").usableShare).toBe("0.925");
    expect(oneShare("33.33%").usableShare).toBe("0.3333");
    // numeric(5,4) is all that survives the trip, so the screen, the wire and
    // the column agree on one number rather than three roundings of it.
    expect(oneShare("0.333333").usableShare).toBe("0.3333");
  });

  it("takes a blank cell as no share at all", () => {
    expect(oneShare("").usableShare).toBeNull();
    expect(oneShare("   ").usableShare).toBeNull();
  });

  it("answers to the spellings a real sheet uses", () => {
    const spellings = ["usable_share", "usable", "usable_pct", "usable %", "yield_pct", "yield %"];
    for (const header of spellings) {
      expect(oneShare("85%", header).usableShare).toBe("0.85");
    }
  });

  it("leaves 'yield' alone - on its own it has meant portions since M6", () => {
    const { items } = read(
      "item,category,selling price,yield,ingredient,qty,unit\n" +
        "Karak Tea,Tea Corner,5.00,40,CTC black tea,220,g\n",
    );
    expect(items[0].yieldPortions).toBe("40");
    expect(items[0].lines[0].usableShare).toBeNull();
    expect(items[0].problems).toEqual([]);
  });

  it("stops the item on a cell that is not a share, naming the line and the value", () => {
    const shape = "write it as a percent like 85% or a fraction like 0.85";
    expect(oneShare("abc").problem).toBe(
      `"abc" is not a usable share for Chicken - ${shape}`,
    );
    expect(oneShare("-5").problem).toBe(`"-5" is not a usable share for Chicken - ${shape}`);
    expect(oneShare("0").problem).toBe(
      "the usable share for Chicken is zero - it must be above 0 and at most 100%",
    );
    expect(oneShare("0%").problem).toBe(
      "the usable share for Chicken is zero - it must be above 0 and at most 100%",
    );
    expect(oneShare("120").problem).toBe(
      'the usable share for Chicken is "120" - it must be above 0 and at most 100%',
    );
    expect(oneShare("120%").problem).toBe(
      'the usable share for Chicken is "120%" - it must be above 0 and at most 100%',
    );
    // Four places is the whole of what the column keeps, so a share that
    // rounds away is stopped here rather than sent as a zero the door refuses.
    expect(oneShare("0.00001").problem).toBe(
      'the usable share for Chicken is "0.00001" - the smallest share Faida keeps is 0.0001, ' +
        "a hundredth of a percent",
    );
    expect(oneShare("0.001%").problem).toContain("the smallest share Faida keeps");
  });

  it("reads any bare number above one as a percent, and shows it back", () => {
    // "1.5" can only be 1.5%, since 150% of a sack cannot reach the pot - so
    // it is read that way rather than refused, and the preview says
    // "1.5% usable" beside the quantity, where a consultant who meant
    // something else will see it.
    expect(oneShare("1.5").usableShare).toBe("0.015");
    expect(shareWords("0.015")).toBe("1.5% usable");
  });

  it("says the quantity's own problem first when a line has both", () => {
    // The measure is what a person fixes first, and a row shows one sentence.
    expect(oneShare("120%").problem).toContain("usable share");
    const { items } = read(
      "item,category,selling price,yield portions,ingredient,qty,unit,usable share\n" +
        "Chicken Mandi,Mandi,22.00,4,Chicken,0,g,120%\n",
    );
    expect(items[0].lines[0].problem).toBe("the quantity is zero");
  });

  it("puts it in the preview's words as the sheet meant it", () => {
    expect(shareWords("0.85")).toBe("85% usable");
    expect(shareWords("0.925")).toBe("92.5% usable");
    expect(shareWords("0.3333")).toBe("33.33% usable");
    expect(shareWords("1")).toBe("100% usable");
    expect(shareWords("0.05")).toBe("5% usable");
    // The API's four-place form says the same thing, whoever hands it over.
    expect(shareWords("0.8500")).toBe("85% usable");
  });
});

// --- what the door is told --------------------------------------------------

const MATERIALS: Ingredient[] = [
  { id: "ing-chicken", name: "Chicken", base_unit: "g", pack_count: 1, price: null, packs: [] },
];

const MENU: MenuItemSummary[] = [
  {
    id: "menu-4",
    name: "Chicken Mandi",
    category: "Mandi",
    selling_price: "22.000",
    archived_at: null,
    created_at: "2026-09-01T00:00:00Z",
    plate: {
      quality: "incomplete",
      missing: [],
      cost_per_portion: null,
      net_price: null,
      vat_rate: null,
      margin: null,
      margin_pct: null,
    },
    recipe: {
      id: "recipe-4",
      version: 1,
      yield_portions: "4.000",
      yield_label: null,
      component_count: 1,
    },
  },
];

/** The stored recipe: the same 1200 g of chicken, with no share on it. */
function stored(share: string | null): Map<string, MenuItemDetail> {
  return new Map([
    [
      "menu-4",
      {
        id: "menu-4",
        name: "Chicken Mandi",
        category: "Mandi",
        selling_price: "22.000",
        archived_at: null,
        created_at: "2026-09-01T00:00:00Z",
        plate: MENU[0].plate,
        recipe: {
          id: "recipe-4",
          version: 1,
          yield_portions: "4.000",
          yield_label: null,
          created_at: "2026-09-01T00:00:00Z",
          components: [
            {
              position: 0,
              ingredient_id: "ing-chicken",
              ingredient_name: "Chicken",
              base_unit: "g" as const,
              qty: "1200.0000",
              unit: "g",
              source_text: null,
              usable_share: share,
              usable_words: null,
              cost: null,
              missing: null,
            },
          ],
        },
      },
    ],
  ]);
}

function planned(cell: string, share: string | null): LoadItem {
  const { items } = read(
    "item,category,selling price,yield portions,ingredient,qty,unit,usable share\n" +
      `Chicken Mandi,Mandi,22.00,4,Chicken,1200,g,${cell}\n`,
  );
  return planLoad(items, MATERIALS, MENU, stored(share))[0];
}

describe("the share on the wire", () => {
  it("travels on every component, null when the sheet said nothing", () => {
    const withShare = planned("85%", null);
    expect(loadInput(withShare).components).toEqual([
      {
        ingredient_id: "ing-chicken",
        qty: "1200",
        unit: "g",
        usable_share: "0.85",
        source_text: null,
      },
    ]);
    expect(loadInput(planned("", null)).components[0].usable_share).toBeNull();
  });

  it("makes a new version when only the share moved, and no change when it did not", () => {
    expect(planned("85%", null).plan).toMatchObject({ kind: "new_version", version: 2 });
    expect(planned("", null).plan).toMatchObject({ kind: "unchanged", version: 1 });
    expect(planned("", "0.8500").plan).toMatchObject({ kind: "new_version", version: 2 });
  });

  it("reads the share the API hands back as the same share that was sent", () => {
    // The column keeps four places, so "0.85" goes out and "0.8500" comes
    // home - the round trip `qty` already makes. A re-upload of the same
    // sheet must still read "no change", whichever way each side spells it.
    for (const cell of ["85%", "85", "0.85", "0.8500"]) {
      expect(planned(cell, "0.8500").plan).toMatchObject({ kind: "unchanged", version: 1 });
    }
  });
});
