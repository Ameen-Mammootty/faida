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
  BlockedCost,
  CostBlocker,
  CostPackSource,
  CostQuality,
  Ingredient,
  IngredientMappingInput,
  IngredientProposal,
  MappedPack,
  MappingResult,
  MaterialPrice,
  PackSizeOverrideResult,
  RejectionResult,
  UnmappedSupplierItem,
} from "../types";

/** Plain English for a blocker, mirroring faida_api/costing.BLOCKED_REASONS. */
const BLOCKED_REASONS: Record<CostBlocker, string> = {
  foreign_currency: "This invoice is billed in another currency, so its prices are held back.",
  missing_unit_price: "The invoice does not show a price for this line.",
  missing_quantity: "The invoice does not show how many were bought, so nothing checks the price.",
  zero_pack: "The pack size names a unit but no amount to divide by.",
  bare_container: "Nothing on the invoice says how much one of these holds.",
  unparseable_pack: "Nothing on this line reads as a pack size.",
};

/** The blockers a person's conversion can clear (costing.OVERRIDABLE). */
const OVERRIDABLE = new Set<CostBlocker>(["zero_pack", "bare_container", "unparseable_pack"]);

/**
 * What one of these packs last cost per kilo (M5 WP-53/54). Written out rather
 * than computed, for the reason FixtureLine gives: the arithmetic is C4's, and
 * a second implementation of it in the demo mock is what plan.md section 2
 * rule 3 exists to refuse.
 *
 * The *selection* is mirrored, because that is what the screen exercises and
 * it is a sort rather than money: the material's price is the newest of these
 * among the packs mapped to it right now. `invoice_id` points at the fixture
 * invoice from the same supplier, so the drill-through to the photo works
 * offline.
 */
interface PackCost {
  per_base_unit: string;
  base_unit: BaseUnit;
  per_display_unit: string;
  display_unit: string;
  pack: string;
  /** YYYY-MM-DD, the printed invoice date this was ranked by. */
  purchased_on: string;
  invoice_id: string;
  invoice_line_id: string;
  /** The printed line position, for the invoice-row anchor. */
  position?: number;
  /** Omitted means the pack column said so, and the cost is as good as this
   * layer gets. A conversion a person entered says so instead, and drags the
   * cost to *estimated* - C9 does that automatically on the server, and
   * getting it wrong here would put a claim on the demo screen that the real
   * product would never make. */
  pack_source?: CostPackSource;
  quality?: CostQuality;
}

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
  /** Null when nothing on the invoice says how much is in one (WP-55). */
  cost: PackCost | null;
  /** Why there is no cost, when there is none. */
  blocked?: CostBlocker;
  pack_size_override?: string | null;
}

interface MockIngredient {
  id: string;
  name: string;
  base_unit: BaseUnit;
}

const DAY = 86_400_000;
const daysAgo = (days: number) => new Date(Date.now() - days * DAY).toISOString();
const dateDaysAgo = (days: number) => daysAgo(days).slice(0, 10);

/** No cost is ever verified: nothing anywhere cross-checks a pack size (C9). */
const RELIABLE: CostQuality = "reliable_with_limitations";

/** Two suppliers selling the same three materials in different packs, which is
 * the situation M5 exists to resolve. The supplier names are the fixture
 * invoices' own, so a price that says where it came from clicks through to a
 * photo from that same supplier. */
const GULF = "Al Madina Foodstuff Trading LLC";
const SEEB = "Al Seeb Trading Co LLC";

const PACKS: MockPack[] = [
  {
    id: "sitem-1",
    canonical_name: "Milk Powder 2.5kg",
    unit: "sack",
    pack_size: "2.5kg",
    supplier_name: GULF,
    last_price: "50.500",
    last_price_at: daysAgo(7),
    spend: "5050.00",
    line_count: 12,
    ingredient_id: null,
    cost: {
      per_base_unit: "0.02020000",
      base_unit: "g",
      per_display_unit: "20.20",
      display_unit: "kg",
      pack: "2.5kg",
      purchased_on: dateDaysAgo(7),
      invoice_id: "inv-1001",
      invoice_line_id: "line-1001-1",
    },
  },
  {
    id: "sitem-2",
    canonical_name: "MILK PWDR 500G NIDO",
    unit: "pouch",
    pack_size: "500g",
    supplier_name: SEEB,
    last_price: "11.750",
    last_price_at: daysAgo(4),
    spend: "1410.00",
    line_count: 8,
    ingredient_id: null,
    cost: {
      per_base_unit: "0.02350000",
      base_unit: "g",
      per_display_unit: "23.50",
      display_unit: "kg",
      pack: "500g",
      purchased_on: dateDaysAgo(4),
      invoice_id: "inv-1002",
      invoice_line_id: "line-1002-1",
    },
  },
  {
    id: "sitem-3",
    canonical_name: "Evaporated Milk 48x400ml",
    unit: "carton",
    pack_size: "48x400ml",
    supplier_name: SEEB,
    last_price: "90.000",
    last_price_at: daysAgo(7),
    spend: "2700.00",
    line_count: 6,
    ingredient_id: null,
    // WP-51's arithmetic with something dividing by it: the carton holds
    // 19,200 ml, and reading only the tail would price this 48 times too high.
    cost: {
      per_base_unit: "0.00468750",
      base_unit: "ml",
      per_display_unit: "4.69",
      display_unit: "litre",
      pack: "48x400ml",
      purchased_on: dateDaysAgo(7),
      invoice_id: "inv-1002",
      invoice_line_id: "line-1002-2",
    },
  },
  {
    id: "sitem-4",
    canonical_name: "Karak Tea Dust",
    unit: "bag",
    pack_size: "400g",
    supplier_name: GULF,
    last_price: "22.000",
    last_price_at: daysAgo(7),
    spend: "880.00",
    line_count: 9,
    ingredient_id: null,
    cost: {
      per_base_unit: "0.05500000",
      base_unit: "g",
      per_display_unit: "55.00",
      display_unit: "kg",
      pack: "400g",
      purchased_on: dateDaysAgo(7),
      invoice_id: "inv-1001",
      invoice_line_id: "line-1001-2",
    },
  },
  {
    // A bare container: units.py refuses to guess what is inside it, so
    // approving this one has to ask what it measures - and it has no cost at
    // all until a person says how much a carton holds (WP-55).
    id: "sitem-5",
    canonical_name: "Chicken Carton",
    unit: "ctn",
    pack_size: "1 ctn",
    supplier_name: GULF,
    last_price: "148.000",
    last_price_at: daysAgo(3),
    spend: "740.00",
    line_count: 5,
    ingredient_id: null,
    cost: null,
    blocked: "bare_container",
    pack_size_override: null,
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

function measureOf(text: string): { base: BaseUnit; quantity: number } | null {
  const match = SINGLE_PACK_RE.exec(text);
  if (!match) return null;
  const unit = match[3].toLowerCase();
  const amount = Number(match[2].replace(",", ".")) * Number(match[1]?.replace(",", ".") ?? 1);
  if (!(amount > 0)) return null;
  const scale: Record<string, number> = { kg: 1000, l: 1000, ltr: 1000, mg: 0.001, cl: 10, dz: 12 };
  if (/^(kgs?|kilos?|g|gm|gms|grams?|mg|lbs?|oz)$/.test(unit)) {
    return { base: "g", quantity: amount * (/^(kgs?|kilos?)$/.test(unit) ? 1000 : scale[unit] ?? 1) };
  }
  if (/^(l|ltrs?|litres?|liters?|ml|cl|gal)$/.test(unit)) {
    return { base: "ml", quantity: amount * (/^(ml)$/.test(unit) ? 1 : /^(cl)$/.test(unit) ? 10 : 1000) };
  }
  if (/^(pcs?|pieces?|nos?|dz|dozens?)$/.test(unit)) {
    return { base: "pc", quantity: amount * (/^(dz|dozens?)$/.test(unit) ? 12 : 1) };
  }
  return null;
}

function baseUnitOf(pack: MockPack): BaseUnit | null {
  return (
    measureOf(`${pack.pack_size ?? ""} ${pack.canonical_name}`)?.base ??
    // Once a person has said "one holds 10 kg" they have also said it is
    // measured by weight; asking again on the next screen is not listening.
    measureOf(pack.pack_size_override ?? "")?.base ??
    null
  );
}

/**
 * A cost from a price and a pack, for the offline demo only.
 *
 * Ordinary JavaScript arithmetic, deliberately: the screen renders two
 * decimals, so nothing here can be seen to be off, and the real answer is
 * `Decimal` throughout `faida_api/costing.py` with C4's VAT and discount
 * factors that this file has no business reproducing. This exists so a
 * consultant can walk the WP-55 flow end to end without a backend - it is
 * never the reference for what a cost is.
 */
function mockCost(price: string, packText: string): PackCost | null {
  const measure = measureOf(packText);
  if (!measure) return null;
  const perBase = Number(price) / measure.quantity;
  const factor = measure.base === "pc" ? 1 : 1000;
  return {
    per_base_unit: perBase.toFixed(8),
    base_unit: measure.base,
    per_display_unit: (perBase * factor).toFixed(2),
    display_unit: measure.base === "pc" ? "each" : measure.base === "ml" ? "litre" : "kg",
    pack: packText,
    purchased_on: dateDaysAgo(3),
    invoice_id: "inv-1001",
    invoice_line_id: "line-1001-answered",
    // No photograph shows this amount: a person did (C9).
    pack_source: "override",
    quality: "estimated",
  };
}

// -- the endpoints ----------------------------------------------------------

/** One pack's cost, in the shape the API serves a material's price. */
function toPrice(pack: MockPack): MaterialPrice | null {
  if (!pack.cost) return null;
  return {
    ...pack.cost,
    quality: pack.cost.quality ?? RELIABLE,
    asserted: [],
    pack_source: pack.cost.pack_source ?? "pack_size",
    supplier_name: pack.supplier_name,
    supplier_item_id: pack.id,
    product_name: pack.canonical_name,
    position: pack.cost.position ?? 0,
    invoice_date: pack.cost.purchased_on,
    // The D11 stale flag never fires in the mock: every fixture pack's newest
    // purchase is the costed one, so claiming otherwise would demo a warning
    // the data does not support.
    newer_uncosted: null,
  };
}

function toMappedPack(pack: MockPack): MappedPack {
  return {
    id: pack.id,
    canonical_name: pack.canonical_name,
    unit: pack.unit,
    pack_size: pack.pack_size,
    supplier_name: pack.supplier_name,
    pack_size_override: pack.pack_size_override ?? null,
    last_price: pack.last_price,
    last_price_at: pack.last_price_at,
    cost: toPrice(pack),
  };
}

export async function mockListIngredients(): Promise<Ingredient[]> {
  return INGREDIENTS.map((ingredient) => {
    const mapped = PACKS.filter((pack) => pack.ingredient_id === ingredient.id);
    // WP-54: the newest costed pack among the ones mapped right now. Latest,
    // not cheapest and not averaged - and derived on every read, which is why
    // unmapping one corrects the figure with nothing to rebuild.
    const newest = mapped
      .filter((pack) => pack.cost !== null)
      .sort((a, b) => (a.cost!.purchased_on < b.cost!.purchased_on ? 1 : -1))[0];
    return {
      ...ingredient,
      pack_count: mapped.length,
      price: newest ? toPrice(newest) : null,
      packs: mapped.map(toMappedPack),
    };
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

/** WP-55: the confirmed lines that could not be costed, grouped by product. */
export async function mockListBlockedCosts(): Promise<BlockedCost[]> {
  return PACKS.filter((pack) => pack.cost === null && pack.blocked !== undefined)
    .map((pack) => ({
      id: pack.id,
      supplier_item_id: pack.id,
      product_name: pack.canonical_name,
      supplier_name: pack.supplier_name,
      pack_size: pack.pack_size,
      unit: pack.unit,
      pack_size_override: pack.pack_size_override ?? null,
      ingredient_id: pack.ingredient_id,
      ingredient_name:
        INGREDIENTS.find((row) => row.id === pack.ingredient_id)?.name ?? null,
      blocked: pack.blocked as CostBlocker,
      reason: BLOCKED_REASONS[pack.blocked as CostBlocker],
      can_override: OVERRIDABLE.has(pack.blocked as CostBlocker),
      line_count: pack.line_count,
      spend: pack.spend,
      invoice_id: "inv-1001",
      invoice_line_id: `${pack.id}-line`,
      position: 0,
      invoice_date: dateDaysAgo(3),
    }))
    .sort((a, b) => Number(b.spend) - Number(a.spend));
}

/** WP-55: a person says how much is in one, once. */
export async function mockSetPackSizeOverride(
  itemId: string,
  packSize: string,
): Promise<PackSizeOverrideResult> {
  const pack = findPack(itemId);
  const answer = packSize.trim();
  const measure = measureOf(answer);
  if (!measure) {
    throw new ApiError(
      422,
      "Say how much is in one of these, as an amount with its unit - " +
        "like '10 kg', '750 ml' or '24 x 400 ml'.",
    );
  }
  const material = INGREDIENTS.find((row) => row.id === pack.ingredient_id);
  if (material && material.base_unit !== measure.base) {
    throw new ApiError(
      422,
      `${answer} is measured ${MEASURE_WORDS[measure.base]}, but ${material.name} is ` +
        `measured ${MEASURE_WORDS[material.base_unit]}`,
    );
  }
  pack.pack_size_override = answer;
  // Only lines with no cost yet, exactly as the server does: an answer never
  // rewrites a figure someone has already read.
  const costed = pack.cost === null ? pack.line_count : 0;
  if (pack.cost === null) pack.cost = mockCost(pack.last_price ?? "0", answer);
  return { supplier_item_id: itemId, pack_size: answer, lines_costed: costed };
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
