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

import { ApiError } from "../errors";
import type { MaterialPrice, MenuItemDetail, MenuItemSummary, Plate } from "../types";

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
