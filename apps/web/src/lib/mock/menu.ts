/**
 * In-memory mock of the M6 WP-61/62 menu endpoints, answering with the same
 * shapes the real API serves (apps/api src/faida_api/menu.py, pinned by
 * tests/test_plates.py) so the screen cannot tell the modes apart.
 *
 * Every figure is written out rather than computed, hand-checked against the
 * real arithmetic (plates.py: components sum at full precision, one division
 * by the batch yield, quantized once; margin against the price net of 5% VAT).
 * A second implementation of the money in a demo mock is what plan.md
 * section 2 rule 3 exists to refuse. The material prices and invoice ids
 * match the materials fixtures, so the drill-through to a photo works
 * offline.
 *
 * The behaviour that matters is reproduced, not just the shape: one
 * *estimated* input (Ghee costed through a person's pack conversion) makes
 * its plate *estimated*; an incomplete item carries no numbers at all, only
 * what is missing; and nothing anywhere says "verified".
 */

import { mockListIngredients } from "./materials";
import { ApiError } from "../errors";
import type {
  MaterialPrice,
  MenuComponent,
  MenuItemDetail,
  MenuItemLoadInput,
  MenuItemSummary,
  MenuLoadResult,
  Plate,
  PriceMove,
} from "../types";

const DAY = 86_400_000;
const dateDaysAgo = (days: number) => new Date(Date.now() - days * DAY).toISOString().slice(0, 10);
const daysAgo = (days: number) => new Date(Date.now() - days * DAY).toISOString();

const GULF = "Al Madina Foodstuff Trading LLC";
const SEEB = "Al Seeb Trading Co LLC";

/** The materials fixtures' own prices, restated per component. */
const DUST: MaterialPrice = {
  per_base_unit: "0.05500000",
  base_unit: "g",
  per_display_unit: "55.00",
  display_unit: "kg",
  quality: "reliable_with_limitations",
  asserted: [],
  pack: "400g",
  pack_source: "pack_size",
  supplier_name: GULF,
  supplier_item_id: "sitem-4",
  product_name: "Karak Tea Dust",
  invoice_id: "inv-1001",
  invoice_line_id: "line-1001-2",
  position: 1,
  purchased_on: dateDaysAgo(7),
  invoice_date: dateDaysAgo(7),
  newer_uncosted: null,
};

const EVAP: MaterialPrice = {
  per_base_unit: "0.00468750",
  base_unit: "ml",
  per_display_unit: "4.69",
  display_unit: "litre",
  quality: "reliable_with_limitations",
  asserted: [],
  pack: "48x400ml",
  pack_source: "pack_size",
  supplier_name: SEEB,
  supplier_item_id: "sitem-3",
  product_name: "Evaporated Milk 48x400ml",
  invoice_id: "inv-1002",
  invoice_line_id: "line-1002-2",
  position: 1,
  purchased_on: dateDaysAgo(7),
  invoice_date: dateDaysAgo(7),
  newer_uncosted: null,
};

const MILK_POWDER: MaterialPrice = {
  per_base_unit: "0.02020000",
  base_unit: "g",
  per_display_unit: "20.20",
  display_unit: "kg",
  quality: "reliable_with_limitations",
  asserted: [],
  pack: "2.5kg",
  pack_source: "pack_size",
  supplier_name: GULF,
  supplier_item_id: "sitem-1",
  product_name: "Milk Powder 2.5kg",
  invoice_id: "inv-1001",
  invoice_line_id: "line-1001-1",
  position: 0,
  purchased_on: dateDaysAgo(7),
  invoice_date: dateDaysAgo(7),
  newer_uncosted: null,
};

/** Costed through a person's conversion (WP-55), so *estimated* by C9 - and
 * the one plate built on it reads estimated too, automatically. */
const GHEE: MaterialPrice = {
  per_base_unit: "0.04000000",
  base_unit: "g",
  per_display_unit: "40.00",
  display_unit: "kg",
  quality: "estimated",
  asserted: [],
  pack: "800 g",
  pack_source: "override",
  supplier_name: GULF,
  supplier_item_id: "sitem-ghee",
  product_name: "Ghee Tin",
  invoice_id: "inv-1001",
  invoice_line_id: "line-1001-3",
  position: 2,
  purchased_on: dateDaysAgo(5),
  invoice_date: dateDaysAgo(5),
  newer_uncosted: null,
};

const RELIABLE_PLATE = "reliable_with_limitations" as const;

/** 4 g dust + 55 ml evap + 10 g milk powder = 0.6798125 -> 0.680 a cup. */
const KARAK_CUP_PLATE: Plate = {
  quality: RELIABLE_PLATE,
  missing: [],
  cost_per_portion: "0.680",
  net_price: "4.762",
  vat_rate: "0.05",
  margin: "4.082",
  margin_pct: "85.7",
};

/** 28 g + 390 ml + 70 g = 4.782125 -> 4.782 a flask. */
const KARAK_FLASK_PLATE: Plate = {
  quality: RELIABLE_PLATE,
  missing: [],
  cost_per_portion: "4.782",
  net_price: "33.333",
  vat_rate: "0.05",
  margin: "28.551",
  margin_pct: "85.7",
};

/** 40 g milk powder + 100 ml evap + 10 g ghee = 1.67675 -> 1.677. */
const NIDO_SHAKE_PLATE: Plate = {
  quality: "estimated",
  missing: [],
  cost_per_portion: "1.677",
  net_price: "7.619",
  vat_rate: "0.05",
  margin: "5.942",
  margin_pct: "78.0",
};

const MANDI_PLATE: Plate = {
  quality: "incomplete",
  missing: ["no supplier product is mapped to Chicken yet"],
  cost_per_portion: null,
  net_price: null,
  vat_rate: null,
  margin: null,
  margin_pct: null,
};

const CAKE_PLATE: Plate = {
  quality: "incomplete",
  missing: ["no recipe yet"],
  cost_per_portion: null,
  net_price: null,
  vat_rate: null,
  margin: null,
  margin_pct: null,
};

const DETAILS: MenuItemDetail[] = [
  {
    id: "menu-1",
    category: "Tea Corner",
    name: "Karak Tea (Cup)",
    selling_price: "5.000",
    archived_at: null,
    created_at: daysAgo(9),
    plate: KARAK_CUP_PLATE,
    recipe: {
      id: "recipe-1",
      version: 2,
      yield_portions: "1.000",
      yield_label: "cup",
      created_at: daysAgo(2),
      components: [
        {
          position: 0,
          ingredient_id: "ing-dust",
          ingredient_name: "Karak Tea Dust",
          base_unit: "g",
          qty: "4.0000",
          unit: "g",
          source_text: "70 ml concentrate",
          cost: { amount: "0.220", quality: "reliable_with_limitations", price: DUST },
          missing: null,
        },
        {
          position: 1,
          ingredient_id: "ing-evap",
          ingredient_name: "Evaporated Milk",
          base_unit: "ml",
          qty: "55.0000",
          unit: "ml",
          source_text: null,
          cost: { amount: "0.258", quality: "reliable_with_limitations", price: EVAP },
          missing: null,
        },
        {
          position: 2,
          ingredient_id: "ing-nido",
          ingredient_name: "Milk Powder",
          base_unit: "g",
          qty: "10.0000",
          unit: "g",
          source_text: "1 heaped spoon",
          cost: { amount: "0.202", quality: "reliable_with_limitations", price: MILK_POWDER },
          missing: null,
        },
      ],
    },
  },
  {
    id: "menu-2",
    category: "Tea Corner",
    name: "Karak Tea (Flask 1 L)",
    selling_price: "35.000",
    archived_at: null,
    created_at: daysAgo(9),
    plate: KARAK_FLASK_PLATE,
    recipe: {
      id: "recipe-2",
      version: 1,
      yield_portions: "1.000",
      yield_label: "flask",
      created_at: daysAgo(9),
      components: [
        {
          position: 0,
          ingredient_id: "ing-dust",
          ingredient_name: "Karak Tea Dust",
          base_unit: "g",
          qty: "28.0000",
          unit: "g",
          source_text: "500 ml concentrate",
          cost: { amount: "1.540", quality: "reliable_with_limitations", price: DUST },
          missing: null,
        },
        {
          position: 1,
          ingredient_id: "ing-evap",
          ingredient_name: "Evaporated Milk",
          base_unit: "ml",
          qty: "390.0000",
          unit: "ml",
          source_text: null,
          cost: { amount: "1.828", quality: "reliable_with_limitations", price: EVAP },
          missing: null,
        },
        {
          position: 2,
          ingredient_id: "ing-nido",
          ingredient_name: "Milk Powder",
          base_unit: "g",
          qty: "70.0000",
          unit: "g",
          source_text: null,
          cost: { amount: "1.414", quality: "reliable_with_limitations", price: MILK_POWDER },
          missing: null,
        },
      ],
    },
  },
  {
    id: "menu-3",
    category: "Shakes",
    name: "Nido Shake",
    selling_price: "8.000",
    archived_at: null,
    created_at: daysAgo(8),
    plate: NIDO_SHAKE_PLATE,
    recipe: {
      id: "recipe-3",
      version: 1,
      yield_portions: "1.000",
      yield_label: "glass",
      created_at: daysAgo(8),
      components: [
        {
          position: 0,
          ingredient_id: "ing-nido",
          ingredient_name: "Milk Powder",
          base_unit: "g",
          qty: "40.0000",
          unit: "g",
          source_text: null,
          cost: { amount: "0.808", quality: "reliable_with_limitations", price: MILK_POWDER },
          missing: null,
        },
        {
          position: 1,
          ingredient_id: "ing-evap",
          ingredient_name: "Evaporated Milk",
          base_unit: "ml",
          qty: "100.0000",
          unit: "ml",
          source_text: null,
          cost: { amount: "0.469", quality: "reliable_with_limitations", price: EVAP },
          missing: null,
        },
        {
          position: 2,
          ingredient_id: "ing-ghee",
          ingredient_name: "Ghee",
          base_unit: "g",
          qty: "10.0000",
          unit: "g",
          source_text: null,
          cost: { amount: "0.400", quality: "estimated", price: GHEE },
          missing: null,
        },
      ],
    },
  },
  {
    id: "menu-4",
    category: "Mandi & Biryani",
    name: "Chicken Mandi",
    selling_price: "22.000",
    archived_at: null,
    created_at: daysAgo(8),
    plate: MANDI_PLATE,
    recipe: {
      id: "recipe-4",
      version: 1,
      yield_portions: "4.000",
      yield_label: "plates per pot",
      created_at: daysAgo(8),
      components: [
        {
          position: 0,
          ingredient_id: "ing-chicken",
          ingredient_name: "Chicken",
          base_unit: "g",
          qty: "1200.0000",
          unit: "g",
          source_text: "one whole bird",
          cost: null,
          missing: "no supplier product is mapped to Chicken yet",
        },
        {
          position: 1,
          ingredient_id: "ing-ghee",
          ingredient_name: "Ghee",
          base_unit: "g",
          qty: "60.0000",
          unit: "g",
          source_text: null,
          cost: { amount: "0.600", quality: "estimated", price: GHEE },
          missing: null,
        },
      ],
    },
  },
  {
    id: "menu-5",
    category: "Tea Corner",
    name: "Honey Cake",
    selling_price: "11.000",
    archived_at: null,
    created_at: daysAgo(6),
    plate: CAKE_PLATE,
    recipe: null,
  },
];

export async function mockListMenuItems(): Promise<MenuItemSummary[]> {
  return DETAILS.map((detail) => ({
    id: detail.id,
    name: detail.name,
    category: detail.category,
    selling_price: detail.selling_price,
    archived_at: detail.archived_at,
    created_at: detail.created_at,
    plate: detail.plate,
    recipe:
      detail.recipe === null
        ? null
        : {
            id: detail.recipe.id,
            version: detail.recipe.version,
            yield_portions: detail.recipe.yield_portions,
            yield_label: detail.recipe.yield_label,
            component_count: detail.recipe.components.length,
          },
  }));
}

export async function mockGetMenuItem(id: string): Promise<MenuItemDetail> {
  const detail = DETAILS.find((row) => row.id === id);
  if (!detail) throw new ApiError(404, "menu item not found");
  return detail;
}

// --- the batch loader, offline (WP-64) --------------------------------------
//
// The loader has to run with no backend at all - that is how the demo and
// every QA pass drive it - so these reproduce the door's *decisions* while
// computing no money whatsoever.
//
// A recipe loaded here therefore reads **incomplete**, which is not a mock
// shortcut but the honest answer: sample data starts with an empty material
// catalog, so a freshly loaded dish is waiting on exactly the mapping work
// the materials screen exists for. Where every material a recipe names does
// have a price, the mock says plainly that it does not cost recipes loaded in
// this session rather than inventing a figure - a second implementation of
// the money in a demo mock is what plan.md section 2 rule 3 refuses.

let loadedCounter = 0;

const nameKey = (name: string) => name.trim().toLowerCase().replace(/\s+/g, " ");

/** "550" and "550.0000" are one amount; "mls" and "ml" are one measure. */
const amountKey = (value: string) => {
  const text = value.trim();
  const whole = text.includes(".") ? text.replace(/0+$/, "").replace(/\.$/, "") : text;
  return whole.replace(/^0+(?=\d)/, "");
};
const unitKey = (unit: string) => {
  const word = unit.trim().toLowerCase();
  if (/^(kgs?|kilos?|kilograms?)$/.test(word)) return "kg";
  if (/^(g|gm|gms|gs|gr|grams?|gramme|grms)$/.test(word)) return "g";
  if (/^(ml|mls|millilitres?|cc)$/.test(word)) return "ml";
  if (/^(l|lt|lts|ltrs?|litres?|liters?)$/.test(word)) return "l";
  if (/^(pcs?|pce|pces|pieces?|ea|each|nos?|units?)$/.test(word)) return "pc";
  return word;
};
const lineKey = (ingredientId: string, qty: string, unit: string) =>
  `${ingredientId}|${amountKey(qty)}|${unitKey(unit)}`;

/** D8's rule: the same yield and the same multiset of (ingredient, amount,
 * measure), in any order. Free text is outside it. */
function sameRecipe(detail: MenuItemDetail, body: MenuItemLoadInput): boolean {
  const recipe = detail.recipe;
  if (!recipe) return false;
  if (amountKey(recipe.yield_portions) !== amountKey(body.yield_portions)) return false;
  if (recipe.components.length !== body.components.length) return false;
  const stored = recipe.components
    .map((component) => lineKey(component.ingredient_id, component.qty, component.unit))
    .sort();
  const incoming = body.components
    .map((component) => lineKey(component.ingredient_id, component.qty, component.unit))
    .sort();
  return stored.every((value, position) => value === incoming[position]);
}

/** What a loaded recipe is waiting for, in the real screen's own words. */
async function plateFor(body: MenuItemLoadInput): Promise<{ plate: Plate; names: Map<string, string> }> {
  const materials = await mockListIngredients();
  const names = new Map(materials.map((row) => [row.id, row.name]));
  const missing = body.components
    .filter((component) => {
      const material = materials.find((row) => row.id === component.ingredient_id);
      return material === undefined || material.price === null;
    })
    .map((component) => {
      const material = materials.find((row) => row.id === component.ingredient_id);
      const label = material?.name ?? "this ingredient";
      return material && material.pack_count > 0
        ? `no confirmed purchase of ${label} yet`
        : `no supplier product is mapped to ${label} yet`;
    });
  const plate: Plate = {
    quality: "incomplete",
    missing:
      missing.length > 0
        ? [...new Set(missing)]
        : ["sample data does not cost recipes loaded in this session"],
    cost_per_portion: null,
    net_price: null,
    vat_rate: null,
    margin: null,
    margin_pct: null,
  };
  return { plate, names };
}

/**
 * One recipe, one transaction - reproduced by doing all of it or none of it
 * before anything is pushed. Returns the same three outcomes as the door, so
 * the grid restamps identically in both modes.
 */
export async function mockLoadMenuItem(body: MenuItemLoadInput): Promise<MenuLoadResult> {
  const name = body.name.trim();
  const key = nameKey(name);
  const archived = DETAILS.find((row) => nameKey(row.name) === key && row.archived_at !== null);
  const existing = DETAILS.find((row) => nameKey(row.name) === key && row.archived_at === null);
  if (!existing && archived) {
    throw new ApiError(
      409,
      `'${name}' is archived in Faida. Bring it back first, or take the row out of the ` +
        "spreadsheet",
    );
  }

  const { plate, names } = await plateFor(body);
  const components: MenuComponent[] = body.components.map((component, position) => ({
    position,
    ingredient_id: component.ingredient_id,
    ingredient_name: names.get(component.ingredient_id) ?? "Unknown material",
    base_unit: "g",
    qty: component.qty,
    unit: component.unit,
    source_text: component.source_text,
    cost: null,
    missing: plate.missing[0],
  }));

  if (!existing) {
    const detail: MenuItemDetail = {
      id: `menu-loaded-${(loadedCounter += 1)}`,
      name,
      category: body.category,
      selling_price: body.selling_price,
      archived_at: null,
      created_at: new Date().toISOString(),
      plate,
      recipe: {
        id: `recipe-loaded-${loadedCounter}`,
        version: 1,
        yield_portions: body.yield_portions,
        yield_label: body.yield_label,
        created_at: new Date().toISOString(),
        components,
      },
    };
    DETAILS.push(detail);
    return { outcome: "created", changed: [], version: 1, menu_item: detail };
  }

  const changed: string[] = [];
  if (amountKey(existing.selling_price) !== amountKey(body.selling_price)) {
    existing.selling_price = body.selling_price;
    changed.push("selling price");
  }
  if ((existing.category ?? "") !== (body.category ?? "")) {
    existing.category = body.category;
    changed.push("category");
  }

  if (sameRecipe(existing, body)) {
    return {
      outcome: "unchanged",
      changed,
      version: existing.recipe?.version ?? 1,
      menu_item: existing,
    };
  }

  const version = (existing.recipe?.version ?? 0) + 1;
  existing.recipe = {
    id: `recipe-loaded-${(loadedCounter += 1)}`,
    version,
    yield_portions: body.yield_portions,
    yield_label: body.yield_label,
    created_at: new Date().toISOString(),
    components,
  };
  existing.plate = plate;
  return { outcome: "version_added", changed, version, menu_item: existing };
}

/** Off the ranking and the coverage count, never deleted - always a click. */
export async function mockArchiveMenuItem(id: string): Promise<MenuItemDetail> {
  const detail = DETAILS.find((row) => row.id === id);
  if (!detail) throw new ApiError(404, "menu item not found");
  if (detail.archived_at !== null) throw new ApiError(409, "menu item is already archived");
  detail.archived_at = new Date().toISOString();
  return detail;
}

export async function mockUnarchiveMenuItem(id: string): Promise<MenuItemDetail> {
  const detail = DETAILS.find((row) => row.id === id);
  if (!detail) throw new ApiError(404, "menu item not found");
  if (detail.archived_at === null) throw new ApiError(409, "menu item is not archived");
  if (DETAILS.some((row) => row !== detail && nameKey(row.name) === nameKey(detail.name) && row.archived_at === null)) {
    throw new ApiError(
      409,
      `another live menu item is already called '${detail.name}'; rename or archive it first`,
    );
  }
  detail.archived_at = null;
  return detail;
}

/**
 * WP-63's money moment, hand-checked like everything else in this file: the
 * evaporated milk carton moved from 4.19 to 4.69 a litre (0.0005/ml), so the
 * cup (55 ml) lost 0.028, the flask (390 ml) lost 0.195 and the shake
 * (100 ml) lost 0.050 - margins before are the plates' margins plus exactly
 * those amounts. The basis-changed example carries no delta and no items, by
 * the rule the screen exists to keep: a delta across pack sizes is a pack
 * artifact wearing a percent sign.
 */
const MOVES: PriceMove[] = [
  {
    ingredient_id: "ing-evap",
    ingredient_name: "Evaporated Milk",
    base_unit: "ml",
    kind: "moved",
    current: {
      supplier_item_id: "sitem-3",
      product_name: "Evaporated Milk 48x400ml",
      supplier_name: SEEB,
      pack_size: "48x400ml",
      per_display_unit: "4.69",
      display_unit: "litre",
      invoice_id: "inv-1002",
      invoice_line_id: "line-1002-2",
      position: 1,
      purchased_on: dateDaysAgo(7),
      invoice_date: dateDaysAgo(7),
    },
    previous: {
      supplier_item_id: "sitem-3",
      product_name: "Evaporated Milk 48x400ml",
      supplier_name: SEEB,
      pack_size: "48x400ml",
      per_display_unit: "4.19",
      display_unit: "litre",
      invoice_id: "inv-1001",
      invoice_line_id: "line-1001-4",
      position: 3,
      purchased_on: dateDaysAgo(21),
      invoice_date: dateDaysAgo(21),
    },
    delta_per_display_unit: "0.50",
    items: [
      {
        menu_item_id: "menu-2",
        name: "Karak Tea (Flask 1 L)",
        impact_per_portion: "0.195",
        margin_before: "28.746",
        margin_after: "28.551",
        margin_pct_before: "86.2",
        margin_pct_after: "85.7",
      },
      {
        menu_item_id: "menu-3",
        name: "Nido Shake",
        impact_per_portion: "0.050",
        margin_before: "5.992",
        margin_after: "5.942",
        margin_pct_before: "78.6",
        margin_pct_after: "78.0",
      },
      {
        menu_item_id: "menu-1",
        name: "Karak Tea (Cup)",
        impact_per_portion: "0.028",
        margin_before: "4.110",
        margin_after: "4.082",
        margin_pct_before: "86.3",
        margin_pct_after: "85.7",
      },
    ],
  },
  {
    ingredient_id: "ing-nido",
    ingredient_name: "Milk Powder",
    base_unit: "g",
    kind: "basis_changed",
    current: {
      supplier_item_id: "sitem-1",
      product_name: "Milk Powder 2.5kg",
      supplier_name: GULF,
      pack_size: "2.5kg",
      per_display_unit: "20.20",
      display_unit: "kg",
      invoice_id: "inv-1001",
      invoice_line_id: "line-1001-1",
      position: 0,
      purchased_on: dateDaysAgo(7),
      invoice_date: dateDaysAgo(7),
    },
    previous: {
      supplier_item_id: "sitem-2",
      product_name: "MILK PWDR 500G NIDO",
      supplier_name: SEEB,
      pack_size: "500g",
      per_display_unit: "23.50",
      display_unit: "kg",
      invoice_id: "inv-1002",
      invoice_line_id: "line-1002-1",
      position: 0,
      purchased_on: dateDaysAgo(12),
      invoice_date: dateDaysAgo(12),
    },
    delta_per_display_unit: null,
    items: [],
  },
];

export async function mockListPriceMoves(): Promise<PriceMove[]> {
  return MOVES;
}
