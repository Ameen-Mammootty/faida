/**
 * In-memory mock of the raw-material surface (M5), answering with the same
 * shapes the real endpoints serve (apps/api src/faida_api/api.py, pinned by
 * tests/test_raw_materials.py) so the mapping screen cannot tell the modes
 * apart. Same posture as store.ts: module memory, resets on reload.
 *
 * The seeded catalog is deliberately the awkward one. Milk powder arrives
 * from two suppliers in two pack sizes (the case the whole layer exists for),
 * chicken is priced per carton with nothing stated (blocked until a human
 * says what a carton holds), and the queue is ranked by spend rather than by
 * name, so what the screen demonstrates is the real problem and not a tidy
 * version of it.
 */

import { ApiError } from "../errors";
import type {
  ConversionInput,
  EstimatedBecause,
  IngredientDetail,
  IngredientPrice,
  IngredientSummary,
  MapItemInput,
  MapItemResult,
  Pack,
  QueueItem,
  UnitCost,
} from "../types";

interface MockPack {
  id: string;
  canonical_name: string;
  unit: string | null;
  pack_size: string | null;
  supplier_id: string;
  supplier_name: string;
  last_price: string;
  last_price_at: string;
  spend: string;
  invoices: number;
  /** Base units per purchase unit, or null when nothing states it. */
  base_per_unit: number | null;
  base_unit: "g" | "ml" | "pc";
  basis: UnitCost["basis"];
  pack_display: string;
  ingredient_id: string | null;
  conversion: Pack["conversion"];
}

interface MockIngredient {
  id: string;
  name: string;
  base_unit: "g" | "ml" | "pc";
  category: string | null;
}

const PACKS: MockPack[] = [
  {
    id: "si-2001",
    canonical_name: "Rainbow Milk Powder 2.25kg",
    unit: "tin",
    pack_size: "2.25kg",
    supplier_id: "sup-1",
    supplier_name: "Al Madina Foodstuff Trading LLC",
    last_price: "50.50",
    last_price_at: "2026-08-18T10:10:00+00:00",
    spend: "1818.00",
    invoices: 6,
    base_per_unit: 2250,
    base_unit: "g",
    basis: "pack_size",
    pack_display: "2.25 kg",
    ingredient_id: null,
    conversion: null,
  },
  {
    id: "si-2106",
    canonical_name: "Rainbow Milk Powder 5kg",
    unit: "bag",
    pack_size: "5kg",
    supplier_id: "sup-2",
    supplier_name: "Al Seeb Trading Co LLC",
    last_price: "107.50",
    last_price_at: "2026-08-20T09:30:00+00:00",
    spend: "645.00",
    invoices: 2,
    base_per_unit: 5000,
    base_unit: "g",
    basis: "pack_size",
    pack_display: "5 kg",
    ingredient_id: null,
    conversion: null,
  },
  {
    id: "si-2104",
    canonical_name: "MILK PWDR 5KG NIDO",
    unit: "bag",
    pack_size: "5kg",
    supplier_id: "sup-2",
    supplier_name: "Al Seeb Trading Co LLC",
    last_price: "104.00",
    last_price_at: "2026-08-13T09:30:00+00:00",
    spend: "312.00",
    invoices: 1,
    base_per_unit: 5000,
    base_unit: "g",
    basis: "pack_size",
    pack_display: "5 kg",
    ingredient_id: null,
    conversion: null,
  },
  {
    id: "si-2105",
    canonical_name: "Chicken Fresh Whole",
    unit: "ctn",
    pack_size: null,
    supplier_id: "sup-2",
    supplier_name: "Al Seeb Trading Co LLC",
    last_price: "120.00",
    last_price_at: "2026-08-19T08:15:00+00:00",
    spend: "1440.00",
    invoices: 4,
    base_per_unit: null, // a carton of what? nobody has said yet
    base_unit: "g",
    basis: "conversion",
    pack_display: "1 ctn",
    ingredient_id: null,
    conversion: null,
  },
  {
    id: "si-2002",
    canonical_name: "Karak Tea Dust 5kg",
    unit: "bag",
    pack_size: "5kg",
    supplier_id: "sup-1",
    supplier_name: "Al Madina Foodstuff Trading LLC",
    last_price: "49.00",
    last_price_at: "2026-08-16T10:45:00+00:00",
    spend: "588.00",
    invoices: 3,
    base_per_unit: 5000,
    base_unit: "g",
    basis: "pack_size",
    pack_display: "5 kg",
    ingredient_id: null,
    conversion: null,
  },
  {
    id: "si-2103",
    canonical_name: "Sugar 10kg",
    unit: "bag",
    pack_size: "10kg",
    supplier_id: "sup-2",
    supplier_name: "Al Seeb Trading Co LLC",
    last_price: "42.00",
    last_price_at: "2026-08-16T11:20:00+00:00",
    spend: "420.00",
    invoices: 3,
    base_per_unit: 10000,
    base_unit: "g",
    basis: "pack_size",
    pack_display: "10 kg",
    ingredient_id: null,
    conversion: null,
  },
  {
    id: "si-2102",
    canonical_name: "Evaporated Milk 410ml",
    unit: "tin",
    pack_size: "410ml",
    supplier_id: "sup-2",
    supplier_name: "Al Seeb Trading Co LLC",
    last_price: "4.50",
    last_price_at: "2026-08-14T08:40:00+00:00",
    spend: "216.00",
    invoices: 2,
    base_per_unit: 410,
    base_unit: "ml",
    basis: "pack_size",
    pack_display: "410 ml",
    ingredient_id: null,
    conversion: null,
  },
  {
    id: "si-2005",
    canonical_name: "Paper Cups 8oz x1000",
    unit: "carton",
    pack_size: "1000pc",
    supplier_id: "sup-1",
    supplier_name: "Al Madina Foodstuff Trading LLC",
    last_price: "33.50",
    last_price_at: "2026-08-12T09:00:00+00:00",
    spend: "134.00",
    invoices: 1,
    base_per_unit: 1000,
    base_unit: "pc",
    basis: "pack_size",
    pack_display: "1000 pc",
    ingredient_id: null,
    conversion: null,
  },
];

const INGREDIENTS: MockIngredient[] = [];

/** Confirmed observations behind each pack's price, newest first. */
const PRICES: Record<string, IngredientPrice[]> = {
  "si-2001": [
    {
      price: "50.50",
      observed_at: "2026-08-18T10:10:00+00:00",
      supplier_item_id: "si-2001",
      canonical_name: "Rainbow Milk Powder 2.25kg",
      supplier_name: "Al Madina Foodstuff Trading LLC",
      invoice_id: "inv-0957",
      invoice_no: "AMD-2026-0957",
      invoice_date: "2026-08-18",
      document_id: "doc-0957",
    },
    {
      price: "49.25",
      observed_at: "2026-08-11T09:55:00+00:00",
      supplier_item_id: "si-2001",
      canonical_name: "Rainbow Milk Powder 2.25kg",
      supplier_name: "Al Madina Foodstuff Trading LLC",
      invoice_id: "inv-0936",
      invoice_no: "AMD-2026-0936",
      invoice_date: "2026-08-11",
      document_id: "doc-0936",
    },
  ],
  "si-2106": [
    {
      price: "107.50",
      observed_at: "2026-08-20T09:30:00+00:00",
      supplier_item_id: "si-2106",
      canonical_name: "Rainbow Milk Powder 5kg",
      supplier_name: "Al Seeb Trading Co LLC",
      invoice_id: "inv-1041",
      invoice_no: "AST-1041",
      invoice_date: "2026-08-20",
      document_id: "doc-1041",
    },
  ],
};

const DISPLAY: Record<string, { unit: "kg" | "l" | "pc"; factor: number }> = {
  g: { unit: "kg", factor: 1000 },
  ml: { unit: "l", factor: 1000 },
  pc: { unit: "pc", factor: 1 },
};

/**
 * The mock is the one place in this app allowed to do money arithmetic, and
 * only because it is standing in for the server that owns it (costing.py).
 * Everything it hands to a component is a string, exactly like the real API.
 */
function costOf(pack: MockPack): UnitCost | null {
  if (pack.base_per_unit === null) return null;
  const perBase = Number(pack.last_price) / pack.base_per_unit;
  const { unit, factor } = DISPLAY[pack.base_unit];
  return {
    per_base: perBase.toFixed(8),
    base_unit: pack.base_unit,
    per_display: (perBase * factor).toFixed(3),
    display_unit: unit,
    basis: pack.conversion ? "conversion" : pack.basis,
    pack_display: pack.conversion ? `${pack.pack_display} (stated)` : pack.pack_display,
  };
}

function packPayload(pack: MockPack): Pack {
  const cost = costOf(pack);
  // C9 in the mock: only the stated-conversion case is reachable here, since
  // the mock has no correction path - but the screen must render it the same
  // way it renders the real thing.
  const reasons: EstimatedBecause[] =
    pack.conversion === null
      ? []
      : [
          {
            field: "pack contents",
            origin: "stated_conversion",
            actor: pack.conversion.actor,
            at: pack.conversion.created_at,
            invoice_no: null,
          },
        ];
  return {
    id: pack.id,
    canonical_name: pack.canonical_name,
    unit: pack.unit,
    pack_size: pack.pack_size,
    supplier_id: pack.supplier_id,
    supplier_name: pack.supplier_name,
    last_price: pack.last_price,
    last_price_at: pack.last_price_at,
    cost,
    blocked: cost === null ? "unknown_pack" : null,
    quality: cost === null ? null : reasons.length > 0 ? "estimated" : "verified",
    estimated_because: reasons,
    conversion: pack.conversion,
  };
}

/** Names with pack sizes stripped, the way matching.propose_ingredient scores. */
function stripPack(name: string): string {
  return name
    .replace(/\d+(?:[.,]\d+)?\s*(kgs?|kg|gms?|g|ml|l|pcs?|pc|oz)\b/gi, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

function similarity(a: string, b: string): number {
  const left = new Set(stripPack(a).split(" ").filter(Boolean));
  const right = new Set(stripPack(b).split(" ").filter(Boolean));
  if (left.size === 0 || right.size === 0) return 0;
  let shared = 0;
  for (const token of left) if (right.has(token)) shared += 1;
  return shared / Math.max(left.size, right.size);
}

function proposalFor(pack: MockPack): QueueItem["proposal"] {
  let best: QueueItem["proposal"] = null;
  for (const ingredient of INGREDIENTS) {
    const score = similarity(pack.canonical_name, ingredient.name);
    if (best === null || score > best.score) {
      best = {
        ingredient_id: ingredient.id,
        name: ingredient.name,
        score,
        via: "ingredient",
        evidence: ingredient.name,
      };
    }
  }
  for (const sibling of PACKS) {
    if (sibling.ingredient_id === null || sibling.id === pack.id) continue;
    const score = similarity(pack.canonical_name, sibling.canonical_name);
    if (best === null || score > best.score) {
      const ingredient = INGREDIENTS.find((row) => row.id === sibling.ingredient_id);
      if (!ingredient) continue;
      best = {
        ingredient_id: ingredient.id,
        name: ingredient.name,
        score,
        via: "sibling",
        evidence: sibling.canonical_name,
      };
    }
  }
  // The same high threshold the real matcher uses (matching.py): a
  // suggestion that is usually right is how a wrong merge gets approved, and
  // a mock that proposes more freely than the product would teach a demo
  // audience a behaviour the product does not have.
  return best !== null && best.score >= 0.85
    ? { ...best, score: Math.round(best.score * 1000) / 1000 }
    : null;
}

function findPack(id: string): MockPack {
  const pack = PACKS.find((row) => row.id === id);
  if (!pack) throw new ApiError(404, "supplier item not found");
  return pack;
}

export async function mockRawMaterialQueue(): Promise<QueueItem[]> {
  return PACKS.filter((pack) => pack.ingredient_id === null)
    .sort((a, b) => Number(b.spend) - Number(a.spend))
    .map((pack) => ({
      ...packPayload(pack),
      spend: pack.spend,
      invoices: pack.invoices,
      proposal: proposalFor(pack),
    }));
}

function ingredientCost(packs: Pack[]): IngredientSummary["cost"] {
  const priced = packs.filter((pack) => pack.cost !== null && pack.last_price_at !== null);
  if (priced.length === 0) return null;
  const newest = priced.reduce((latest, pack) =>
    (pack.last_price_at ?? "") > (latest.last_price_at ?? "") ? pack : latest,
  );
  return {
    ...(newest.cost as UnitCost),
    quality: newest.quality ?? "verified",
    estimated_because: newest.estimated_because,
    as_of: newest.last_price_at as string,
    supplier_item_id: newest.id,
    supplier_name: newest.supplier_name,
    pack_name: newest.canonical_name,
  };
}

function packsFor(ingredientId: string): Pack[] {
  return PACKS.filter((pack) => pack.ingredient_id === ingredientId).map(packPayload);
}

export async function mockListIngredients(): Promise<IngredientSummary[]> {
  return INGREDIENTS.map((ingredient) => {
    const packs = packsFor(ingredient.id);
    return {
      ...ingredient,
      packs: packs.length,
      blocked_packs: packs.filter((pack) => pack.blocked !== null).length,
      cost: ingredientCost(packs),
    };
  });
}

export async function mockGetIngredient(id: string): Promise<IngredientDetail> {
  const ingredient = INGREDIENTS.find((row) => row.id === id);
  if (!ingredient) throw new ApiError(404, "ingredient not found");
  const packs = packsFor(id);
  const prices = packs
    .flatMap((pack) => PRICES[pack.id] ?? [])
    .sort((a, b) => (a.observed_at < b.observed_at ? 1 : -1));
  return { ...ingredient, cost: ingredientCost(packs), packs, prices };
}

export async function mockCreateIngredient(body: {
  name: string;
  base_unit: "g" | "ml" | "pc";
  category?: string | null;
}) {
  const existing = INGREDIENTS.find(
    (row) => row.name.toLowerCase() === body.name.trim().toLowerCase(),
  );
  if (existing) return existing;
  const ingredient: MockIngredient = {
    id: `ing-${INGREDIENTS.length + 1}`,
    name: body.name.trim(),
    base_unit: body.base_unit,
    category: body.category ?? null,
  };
  INGREDIENTS.push(ingredient);
  return ingredient;
}

export async function mockMapSupplierItem(
  itemId: string,
  body: MapItemInput,
): Promise<MapItemResult> {
  const pack = findPack(itemId);
  let ingredient: MockIngredient | undefined;
  if (body.ingredient_id) {
    ingredient = INGREDIENTS.find((row) => row.id === body.ingredient_id);
    if (!ingredient) throw new ApiError(404, "ingredient not found");
  } else if (body.name && body.base_unit) {
    ingredient = await mockCreateIngredient({
      name: body.name,
      base_unit: body.base_unit,
      category: body.category ?? null,
    });
  } else {
    throw new ApiError(422, "give an ingredient_id, or a name and base_unit to create one");
  }

  const cost = costOf(pack);
  if (cost !== null && cost.base_unit !== ingredient.base_unit) {
    throw new ApiError(
      409,
      `'${pack.canonical_name}' is priced per ${cost.base_unit}, but '${ingredient.name}' is measured in ${ingredient.base_unit}`,
    );
  }
  pack.ingredient_id = ingredient.id;
  return { item: packPayload(pack), ingredient };
}

export async function mockUnmapSupplierItem(itemId: string): Promise<{ item: Pack }> {
  const pack = findPack(itemId);
  if (pack.ingredient_id === null) throw new ApiError(409, "supplier item is not mapped");
  pack.ingredient_id = null;
  return { item: packPayload(pack) };
}

export async function mockAddConversion(
  itemId: string,
  body: ConversionInput,
): Promise<{ item: Pack }> {
  const pack = findPack(itemId);
  const quantity = Number(body.base_quantity);
  if (!Number.isFinite(quantity) || quantity <= 0) {
    throw new ApiError(422, "base_quantity must be greater than zero");
  }
  pack.base_per_unit = quantity;
  pack.base_unit = body.base_unit;
  pack.conversion = {
    base_quantity: body.base_quantity,
    base_unit: body.base_unit,
    note: body.note ?? null,
    actor: "shared-token",
    created_at: new Date().toISOString(),
  };
  pack.pack_display = `${quantity} ${body.base_unit}`;
  return { item: packPayload(pack) };
}
