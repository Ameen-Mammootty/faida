/**
 * In-memory mock of the M5 WP-52 raw-materials endpoints, answering with the
 * same shapes the real API serves (apps/api src/faida_api/api.py, pinned by
 * tests/test_raw_materials.py) so the screen cannot tell the modes apart.
 *
 * It reproduces the behaviour that matters, not just the shape: proposals are
 * scored with pack sizes stripped (a 2.5 kg sack and a 500 g pouch are one
 * material), a rejected pair stops being proposed, a dimension mismatch is
 * refused, and unmapping puts a pack straight back in the queue.
 *
 * Lives in module memory: edits persist for the length of the browser session
 * and reset on reload, which is what a demo without a backend needs.
 */

import { ApiError } from "../errors";
import type {
  BaseUnit,
  Ingredient,
  IngredientMappingInput,
  IngredientProposal,
  MappedPack,
  MappingResult,
  RejectionResult,
  UnmappedSupplierItem,
} from "../types";

interface MockPack {
  id: string;
  canonical_name: string;
  unit: string | null;
  pack_size: string | null;
  supplier_name: string;
  last_price: string | null;
  last_price_at: string | null;
  spend: string;
  line_count: number;
  ingredient_id: string | null;
}

interface MockIngredient {
  id: string;
  name: string;
  base_unit: BaseUnit;
}

const DAY = 86_400_000;
const daysAgo = (days: number) => new Date(Date.now() - days * DAY).toISOString();

/** Two suppliers selling the same three materials in different packs, which is
 * the situation M5 exists to resolve. */
const PACKS: MockPack[] = [
  {
    id: "sitem-1",
    canonical_name: "Milk Powder 2.5kg",
    unit: "sack",
    pack_size: "2.5kg",
    supplier_name: "Gulf Foods Trading L.L.C.",
    last_price: "50.500",
    last_price_at: daysAgo(7),
    spend: "5050.00",
    line_count: 12,
    ingredient_id: null,
  },
  {
    id: "sitem-2",
    canonical_name: "MILK PWDR 500G NIDO",
    unit: "pouch",
    pack_size: "500g",
    supplier_name: "Al Madina Trading Co.",
    last_price: "11.750",
    last_price_at: daysAgo(4),
    spend: "1410.00",
    line_count: 8,
    ingredient_id: null,
  },
  {
    id: "sitem-3",
    canonical_name: "Evaporated Milk 48x400ml",
    unit: "carton",
    pack_size: "48x400ml",
    supplier_name: "Al Madina Trading Co.",
    last_price: "90.000",
    last_price_at: daysAgo(7),
    spend: "2700.00",
    line_count: 6,
    ingredient_id: null,
  },
  {
    id: "sitem-4",
    canonical_name: "Karak Tea Dust",
    unit: "bag",
    pack_size: "400g",
    supplier_name: "Gulf Foods Trading L.L.C.",
    last_price: "22.000",
    last_price_at: daysAgo(7),
    spend: "880.00",
    line_count: 9,
    ingredient_id: null,
  },
  {
    // A bare container: units.py refuses to guess what is inside it, so
    // approving this one has to ask what it measures.
    id: "sitem-5",
    canonical_name: "Chicken Carton",
    unit: "ctn",
    pack_size: "1 ctn",
    supplier_name: "Gulf Foods Trading L.L.C.",
    last_price: "148.000",
    last_price_at: daysAgo(3),
    spend: "740.00",
    line_count: 5,
    ingredient_id: null,
  },
];

const INGREDIENTS: MockIngredient[] = [];
/** supplier item id -> materials a person already said it is not. */
const REJECTED = new Map<string, Set<string>>();

let nextId = 1;

// -- proposal scoring, mirroring matching.propose_ingredients ----------------

const PACK_RE =
  /(?:(\d+(?:[.,]\d+)?)\s*[xX*×]\s*)?(\d+(?:[.,]\d+)?)\s*(kgs?|kilos?|g|gm|gms|grams?|mg|lbs?|oz|l|ltrs?|litres?|liters?|ml|cl|gal|pcs?|pieces?|nos?|dz|dozens?|ctns?|cartons?|pkts?|packets?|box(?:es)?|bags?|cans?|tins?|tubs?|jars?|btls?|bottles?|cases?|trays?|sachets?|rolls?|packs?)(?![\w])/gi;

/** Pack sizes discriminate packs; they get in the way when the question is
 * which material a pack is. */
function stripPacks(text: string): string {
  return text.replace(PACK_RE, " ").replace(/\s+/g, " ").trim().toLowerCase();
}

/** Longest-common-subsequence ratio, close enough to difflib for a mock. */
function ratio(a: string, b: string): number {
  if (a === b) return 1;
  if (!a || !b) return 0;
  const rows = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0));
  for (let i = 1; i <= a.length; i += 1) {
    for (let j = 1; j <= b.length; j += 1) {
      rows[i][j] =
        a[i - 1] === b[j - 1] ? rows[i - 1][j - 1] + 1 : Math.max(rows[i - 1][j], rows[i][j - 1]);
    }
  }
  return (2 * rows[a.length][b.length]) / (a.length + b.length);
}

const PROPOSAL_THRESHOLD = 0.7;

/** Plain English for a base unit, matching api.py's MEASURE_WORDS. These reach
 * the screen inside refusal messages, where the no-jargon rule applies. */
const MEASURE_WORDS: Record<BaseUnit, string> = {
  g: "by weight",
  ml: "by volume",
  pc: "by the piece",
};

function proposalsFor(pack: MockPack): IngredientProposal[] {
  const rejected = REJECTED.get(pack.id) ?? new Set<string>();
  const name = stripPacks(pack.canonical_name);
  return INGREDIENTS.filter((ingredient) => !rejected.has(ingredient.id))
    .map((ingredient) => ({
      ingredient,
      score: ratio(name, stripPacks(ingredient.name)),
    }))
    .filter((scored) => scored.score >= PROPOSAL_THRESHOLD)
    .sort((a, b) => b.score - a.score)
    .slice(0, 3)
    .map(({ ingredient }) => ({ ...ingredient }));
}

/** Which base unit a printed pack reduces to, or null for a bare container.
 * Its own non-global copy of the pattern: sharing a `g`-flagged regex across
 * functions carries `lastIndex` between them, which is a bug waiting for a
 * second caller. */
const SINGLE_PACK_RE = new RegExp(PACK_RE.source, "i");

function baseUnitOf(pack: MockPack): BaseUnit | null {
  const text = `${pack.pack_size ?? ""} ${pack.canonical_name}`;
  const match = SINGLE_PACK_RE.exec(text);
  if (!match) return null;
  const unit = match[3].toLowerCase();
  if (/^(kgs?|kilos?|g|gm|gms|grams?|mg|lbs?|oz)$/.test(unit)) return "g";
  if (/^(l|ltrs?|litres?|liters?|ml|cl|gal)$/.test(unit)) return "ml";
  if (/^(pcs?|pieces?|nos?|dz|dozens?)$/.test(unit)) return "pc";
  return null;
}

// -- the endpoints ----------------------------------------------------------

function toMappedPack(pack: MockPack): MappedPack {
  return {
    id: pack.id,
    canonical_name: pack.canonical_name,
    unit: pack.unit,
    pack_size: pack.pack_size,
    supplier_name: pack.supplier_name,
    last_price: pack.last_price,
    last_price_at: pack.last_price_at,
  };
}

export async function mockListIngredients(): Promise<Ingredient[]> {
  return INGREDIENTS.map((ingredient) => {
    const packs = PACKS.filter((pack) => pack.ingredient_id === ingredient.id).map(toMappedPack);
    return { ...ingredient, pack_count: packs.length, packs };
  }).sort((a, b) => a.name.localeCompare(b.name));
}

export async function mockListUnmappedSupplierItems(): Promise<UnmappedSupplierItem[]> {
  return PACKS.filter((pack) => pack.ingredient_id === null)
    .map((pack) => ({
      id: pack.id,
      canonical_name: pack.canonical_name,
      unit: pack.unit,
      pack_size: pack.pack_size,
      supplier_id: `sup-${pack.supplier_name.slice(0, 3).toLowerCase()}`,
      supplier_name: pack.supplier_name,
      spend: pack.spend,
      line_count: pack.line_count,
      base_unit: baseUnitOf(pack),
      proposals: proposalsFor(pack),
    }))
    .sort((a, b) => Number(b.spend) - Number(a.spend));
}

function findPack(itemId: string): MockPack {
  const pack = PACKS.find((row) => row.id === itemId);
  if (!pack) throw new ApiError(404, "supplier item not found");
  return pack;
}

export async function mockMapSupplierItem(
  itemId: string,
  body: IngredientMappingInput,
): Promise<MappingResult> {
  const pack = findPack(itemId);
  const packBaseUnit = baseUnitOf(pack);
  let ingredient: MockIngredient;

  if (body.ingredient_id) {
    const found = INGREDIENTS.find((row) => row.id === body.ingredient_id);
    if (!found) throw new ApiError(404, "ingredient not found");
    ingredient = found;
  } else {
    const name = (body.name ?? "").trim();
    if (!name) throw new ApiError(422, "give an ingredient_id or a name");
    const baseUnit = body.base_unit ?? packBaseUnit;
    if (!baseUnit) {
      throw new ApiError(
        422,
        `'${pack.canonical_name}' does not say how much is in it, so say whether ${name} is ` +
          "measured by weight, by volume or by the piece",
      );
    }
    const existing = INGREDIENTS.find((row) => row.name.toLowerCase() === name.toLowerCase());
    ingredient = existing ?? { id: `ing-${nextId++}`, name, base_unit: baseUnit };
    if (!existing) INGREDIENTS.push(ingredient);
  }

  if (packBaseUnit !== null && packBaseUnit !== ingredient.base_unit) {
    throw new ApiError(
      422,
      `'${pack.canonical_name}' is measured ${MEASURE_WORDS[packBaseUnit]}, but ` +
        `${ingredient.name} is measured ${MEASURE_WORDS[ingredient.base_unit]}`,
    );
  }

  pack.ingredient_id = ingredient.id;
  return { supplier_item_id: itemId, ingredient: { ...ingredient } };
}

export async function mockUnmapSupplierItem(itemId: string): Promise<MappingResult> {
  const pack = findPack(itemId);
  if (pack.ingredient_id === null) throw new ApiError(409, "supplier item is not mapped");
  pack.ingredient_id = null;
  return { supplier_item_id: itemId, ingredient: null };
}

export async function mockRejectIngredient(
  itemId: string,
  ingredientId: string,
): Promise<RejectionResult> {
  findPack(itemId);
  const rejected = REJECTED.get(itemId) ?? new Set<string>();
  rejected.add(ingredientId);
  REJECTED.set(itemId, rejected);
  return { supplier_item_id: itemId, rejected_ingredient_id: ingredientId };
}
