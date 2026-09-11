/**
 * M6 WP-64: reading a consultant's spreadsheet into recipes, and working out
 * what committing it would actually change - before anything is pressed.
 *
 * The onboarding conversation this serves (PRD section 16) is a morning at a
 * cafeteria: the consultant asks "so how do you make the karak", types the
 * answer into a spreadsheet with the owner watching, and loads it. The loop
 * that follows is upload, read the rows that failed, fix those cells, upload
 * again - which only works if a re-upload of 45 recipes with two fixes shows
 * 43 no-ops before the button is pressed. That preview is what this computes.
 *
 * **It predicts; the door decides.** Every judgement here is also made by the
 * API's write door (`menu.py`), in the same words, and the grid restamps its
 * rows from what the door actually said. The duplication is deliberate and
 * one-directional: a consultant should see "line 61 says 2 cups of milk"
 * before committing, not after, and a screen that showed nothing until the
 * server answered would make the fix loop a round trip per mistake. Where the
 * two could drift, the door wins - which is why the base unit of a new
 * material is never decided here (the API sends the row's measure word to
 * `units.py`), and why no money is computed on this side at all.
 *
 * Quantities and prices stay strings from the cell to the wire. Nothing in
 * this file parses money into a number.
 */

import type { Ingredient, MenuItemDetail, MenuItemLoadInput, MenuItemSummary } from "./types";

/**
 * The template's columns, and the spellings a real export uses for them.
 *
 * Header names are normalized before matching - lowercased, brackets dropped,
 * and every run of spaces, underscores, hyphens and slashes reduced to one
 * underscore - so "Selling Price (AED)", "selling price aed" and
 * "selling_price_aed" are one column. `item_code` is deliberately absent: the
 * code printed on the consultant's own menu identifies the row on their page,
 * and Faida identifies a dish by its name. Unknown columns are ignored rather
 * than refused, so a working sheet can carry the consultant's own notes.
 */
const COLUMNS = {
  item: ["item", "item_name", "menu_item", "dish"],
  category: ["category", "section", "menu_section"],
  selling_price: ["selling_price", "selling_price_aed", "price", "price_aed", "menu_price"],
  yield_portions: ["yield_portions", "portions", "portions_per_batch", "yield"],
  yield_label: ["yield_label", "portion_label", "portion_name"],
  ingredient: ["ingredient", "raw_material", "material"],
  qty: ["qty", "qty_as_purchased", "quantity", "amount"],
  unit: ["unit", "uom", "measure"],
  /**
   * M12 WP-119 (D13): the conversion yield, optional everywhere. A sheet
   * without this column loads exactly as it did before it existed.
   *
   * "yield" on its own is deliberately absent from this list and stays with
   * `yield_portions`, where it has meant portions per batch since M6 - a
   * consultant's file that says "yield 40" means forty cups, and reading it
   * as a share would silently rewrite the recipe. The percent sign survives
   * `normalizeHeader`, so "usable %" arrives here as "usable_%".
   */
  usable_share: ["usable_share", "usable", "usable_pct", "usable_%", "yield_pct", "yield_%"],
  source_text: ["source_text", "source", "card_says", "recipe_card"],
} as const;

type ColumnName = keyof typeof COLUMNS;

/** The columns a recipe cannot be read without. */
const REQUIRED: ColumnName[] = [
  "item",
  "selling_price",
  "yield_portions",
  "ingredient",
  "qty",
  "unit",
];

const COLUMN_WORDS: Record<ColumnName, string> = {
  item: "item",
  category: "category",
  selling_price: "selling price",
  yield_portions: "yield portions",
  yield_label: "yield label",
  ingredient: "ingredient",
  qty: "qty",
  unit: "unit",
  usable_share: "usable share",
  source_text: "source text",
};

function normalizeHeader(name: string): string {
  return name
    .toLowerCase()
    .replace(/[()[\]{}.]/g, " ")
    .trim()
    .replace(/[\s\-_/]+/g, "_");
}

export type BaseMeasure = "g" | "ml" | "pc";

/**
 * A preview of `units.py`, holding only what a recipe sheet writes: the same
 * shape (a canonical unit, and the base its dimension reduces to), the same
 * spellings, and the same two refusals.
 *
 * Kitchen measures are absent from both dictionaries for the same reason - a
 * karak "cup" is a serving vessel, and converting it is the consultant's job
 * during loading, not the software's afterwards. Container words parse but
 * carry no amount: "1 ctn onion" says how many, not how much, and a plate
 * cost built on it would be a guess wearing a decimal point.
 *
 * This predicts; `units.py` decides. It is never asked what shelf to store a
 * new material on - the API is, because that answer is written down.
 */
const UNIT_WORDS: [BaseMeasure, string, string[]][] = [
  ["g", "g", ["g", "gm", "gms", "gs", "gr", "gram", "grams", "gramme", "grms"]],
  ["g", "kg", ["kg", "kgs", "kilo", "kilos", "kilogram", "kilograms", "kilogramme", "kgm"]],
  ["g", "mg", ["mg"]],
  ["g", "lb", ["lb", "lbs", "pound", "pounds"]],
  ["g", "oz", ["oz", "ozs", "ounce", "ounces"]],
  ["ml", "ml", ["ml", "mls", "millilitre", "millilitres", "cc"]],
  ["ml", "cl", ["cl"]],
  ["ml", "l", ["l", "lt", "lts", "ltr", "ltrs", "litre", "litres", "liter", "liters"]],
  ["ml", "gal", ["gal", "gals", "gallon", "gallons"]],
  ["pc", "pc", ["pc", "pcs", "pce", "pces", "piece", "pieces", "ea", "each", "no", "nos", "unit", "units"]],
  ["pc", "dz", ["dz", "dzn", "doz", "dozen", "dozens"]],
];

const UNITS = new Map<string, { canonical: string; base: BaseMeasure }>();
for (const [base, canonical, words] of UNIT_WORDS) {
  for (const word of words) UNITS.set(word, { canonical, base });
}

const CONTAINERS = new Set([
  "ctn", "ctns", "carton", "cartons", "pkt", "pkts", "packet", "packets", "pack", "packs",
  "box", "boxes", "bag", "bags", "can", "cans", "tin", "tins", "tub", "tubs", "jar", "jars",
  "btl", "btls", "bottle", "bottles", "case", "cases", "tray", "trays", "sachet", "sachets",
  "roll", "rolls", "bunch", "bunches", "block", "blocks", "loaf", "loaves", "bundle", "bundles",
]);

const MEASURE_WORDS: Record<string, string> = {
  g: "by weight",
  ml: "by volume",
  pc: "by the piece",
};

/** Which shelf a measure belongs on, or why it is not an amount at all. */
function measureOf(unit: string): { unit: { canonical: string; base: BaseMeasure } } | { problem: string } {
  const word = unit.trim().toLowerCase();
  const known = UNITS.get(word);
  if (known) return { unit: known };
  if (CONTAINERS.has(word)) {
    return {
      problem:
        `a ${word} is a container, not an amount - say how much goes in, ` +
        "by weight, volume or pieces",
    };
  }
  return {
    problem: `"${unit.trim()}" is not a measure Faida converts - use g, kg, ml, l or pieces`,
  };
}

/** The door's own rule: an unsigned decimal above zero, nothing else. */
function positiveNumber(value: string, what: string): string | null {
  const text = value.trim();
  if (text === "") return `no ${what}`;
  if (text.includes(",")) {
    return `"${text}" has a thousands separator in it - format that column as a plain number`;
  }
  if (!/^\d+(\.\d+)?$/.test(text)) return `"${text}" is not a ${what}`;
  if (/^0+(\.0+)?$/.test(text)) return `the ${what} is zero`;
  return null;
}

/** "550", "550.0000" and "0550" are one amount. String operations only. */
function numberKey(value: string): string {
  const text = value.trim();
  const whole = text.includes(".")
    ? text.replace(/0+$/, "").replace(/\.$/, "")
    : text;
  return whole.replace(/^0+(?=\d)/, "");
}

function sameNumber(a: string, b: string): boolean {
  return numberKey(a) === numberKey(b);
}

/** A decimal string against 1, without parsing it into a number. */
function aboveOne(text: string): boolean {
  const [whole, decimals = ""] = text.split(".");
  const digits = whole.replace(/^0+(?=\d)/, "");
  if (digits.length > 1) return true;
  if (digits !== "1") return false;
  return /[1-9]/.test(decimals);
}

/** A hundredth of a decimal string: the point moved two places left, "85" ->
 * "0.85". A string operation, because 33.33 divided in floating point comes
 * back with a tail of noise on it and this number is stored to four places. */
function hundredth(text: string): string {
  const [whole, decimals = ""] = text.split(".");
  const digits = `00${whole}${decimals}`;
  const point = digits.length - decimals.length - 2;
  return `${digits.slice(0, point)}.${digits.slice(point)}`;
}

/** The column the API stores is `numeric(5,4)`, so four places is all that
 * survives the trip. Cut rather than rounded, so what the screen shows, what
 * is sent and what is stored are one number - and cut *before* the range is
 * checked, so a share too small to store is stopped here rather than sent as
 * a zero the door would refuse. */
function toFourPlaces(text: string): string {
  const dot = text.indexOf(".");
  return dot === -1 ? text : numberKey(text.slice(0, dot + 5));
}

/** Every zero, however it is written: "0", "0.00", "0.0000". */
function isZero(text: string): boolean {
  return /^0+(\.0+)?$/.test(text);
}

/**
 * M12 WP-119 (D13): the conversion yield on one recipe line, read into the
 * one form the API stores - a decimal fraction - or the sentence that stops
 * the item.
 *
 * A sheet writes the same fact three ways and one consultant will use all
 * three in one file: "85%", "85" and "0.85" are the same 85% of the sack
 * reaching the pot. A bare number above 1 is therefore a percent, because a
 * share of eighty-five times the purchased amount is not something anybody
 * means. Blank is null, and null is the whole compatibility story: a recipe
 * with no share is as-purchased, exactly as every recipe written before this
 * column existed.
 *
 * The API refuses anything outside (0, 1] with a sentence of its own; a
 * blocked row never reaches it, because a fix belongs in the spreadsheet
 * before the button, not in a refusal after it.
 */
function usableShare(
  value: string,
  ingredient: string,
): { share: string | null } | { problem: string } {
  const text = value.trim();
  if (text === "") return { share: null };
  const named = ingredient.trim() === "" ? "this line" : ingredient.trim();
  const percent = text.endsWith("%");
  const written = (percent ? text.slice(0, -1) : text).trim();
  if (!/^\d+(\.\d+)?$/.test(written)) {
    return {
      problem:
        `"${text}" is not a usable share for ${named} - write it as a percent ` +
        "like 85% or a fraction like 0.85",
    };
  }
  const fraction = numberKey(percent || aboveOne(written) ? hundredth(written) : written);
  if (isZero(fraction)) {
    return {
      problem: `the usable share for ${named} is zero - it must be above 0 and at most 100%`,
    };
  }
  if (aboveOne(fraction)) {
    return {
      problem: `the usable share for ${named} is "${text}" - it must be above 0 and at most 100%`,
    };
  }
  const kept = toFourPlaces(fraction);
  if (isZero(kept)) {
    return {
      problem:
        `the usable share for ${named} is "${text}" - the smallest share Faida keeps ` +
        "is 0.0001, a hundredth of a percent",
    };
  }
  return { share: kept };
}

/**
 * The share in the words the preview shows beside a quantity: "0.85" is
 * "85% usable". The percent is the fraction with its point moved two places
 * right - a string operation, the mirror of `hundredth` above.
 *
 * This is the sheet's own cell read back, not the API's sentence: the
 * sentence on the menu screen names the purchased amount, and that amount is
 * a division nothing on this side is allowed to do.
 */
export function shareWords(share: string): string {
  const [whole, decimals = ""] = share.split(".");
  const padded = `${decimals}00`;
  const percent = numberKey(`${whole}${padded.slice(0, 2)}.${padded.slice(2)}`);
  return `${percent}% usable`;
}

/** Case- and space-insensitive, the way a person reads two names as one. */
function nameKey(name: string): string {
  return name.trim().toLowerCase().replace(/\s+/g, " ");
}

// --- what the grid shows ----------------------------------------------------

/** One CSV line, with its own problem if it has one. */
export interface LoadLine {
  /** 1-based line number in the file, so "fix line 61" means something. */
  row: number;
  ingredient: string;
  qty: string;
  unit: string;
  /** The conversion yield as the API stores it - a fraction string, "0.85"
   * being 85% usable - or null for a line whose quantity is already the
   * purchased amount (M12 WP-119). Whatever the sheet wrote, it arrives here
   * in this one form. */
  usableShare: string | null;
  sourceText: string | null;
  /** The material in Faida, once it exists. */
  ingredientId: string | null;
  base: BaseMeasure | null;
  problem: string | null;
}

/** A material this file names that Faida has never heard of. */
export interface MissingMaterial {
  name: string;
  /** The measure word from its first row - the API turns it into a shelf. */
  unit: string;
  rows: number[];
}

/**
 * Every new material in the file, each appearing once, **most items first**.
 *
 * The real menu named 82 materials across 45 recipes, with onion in 21 of
 * them - so a create button living on every row that names it would repeat
 * the same button twenty-one times and bury the grid. Deduplicated it is the
 * same rule and the same number of clicks (one per material, never a bulk
 * keystroke that mints twelve through a side door), ranked the way M5's
 * mapping queue ranks its own: the material that unblocks the most items is
 * the one to approve first.
 */
export function newMaterials(items: LoadItem[]): (MissingMaterial & { items: number })[] {
  const all = new Map<string, MissingMaterial & { items: number }>();
  for (const item of items) {
    for (const material of item.missing) {
      const key = nameKey(material.name);
      const already = all.get(key);
      if (already) {
        already.items += 1;
        already.rows.push(...material.rows);
      } else {
        all.set(key, { ...material, rows: [...material.rows], items: 1 });
      }
    }
  }
  return [...all.values()].sort(
    (a, b) => b.items - a.items || a.name.localeCompare(b.name),
  );
}

/** A row can be sent when nothing refuses it and every material it names
 * exists. The two gates are separate on purpose: a spreadsheet mistake is
 * fixed in the spreadsheet, a missing material is one click here. */
export function committable(item: LoadItem): boolean {
  return item.plan.kind !== "blocked" && item.missing.length === 0;
}

export type LoadPlanKind = "new" | "unchanged" | "new_version" | "blocked";

export interface LoadPlan {
  kind: LoadPlanKind;
  /** The version a commit would leave current, when one is known. */
  version: number | null;
  /** The item's own facts this file would move: "selling price", "category". */
  details: string[];
  /** The amounts are unchanged but the card's wording is not (D8 compares
   * amounts, never free text) - named so the two copies cannot drift apart
   * in silence. */
  rewordedOnly: boolean;
}

/** What the commit actually did, as the door reported it. */
export interface LoadResult {
  outcome: "created" | "version_added" | "unchanged" | "refused";
  version: number | null;
  details: string[];
  message: string | null;
}

export interface LoadItem {
  /** The item's name - its identity in Faida and this grid's React key. */
  name: string;
  category: string | null;
  sellingPrice: string;
  yieldPortions: string;
  yieldLabel: string | null;
  lines: LoadLine[];
  /** Sentences that stop the whole item being sent. */
  problems: string[];
  missing: MissingMaterial[];
  /** The item in Faida this row would write into, if there is one. */
  menuItemId: string | null;
  plan: LoadPlan;
  result: LoadResult | null;
}

export type ReadResult =
  | { ok: true; items: LoadItem[]; ignoredColumns: string[] }
  | { ok: false; error: string };

const BLOCKED: LoadPlan = { kind: "blocked", version: null, details: [], rewordedOnly: false };

function blankItem(name: string): LoadItem {
  return {
    name,
    category: null,
    sellingPrice: "",
    yieldPortions: "",
    yieldLabel: null,
    lines: [],
    problems: [],
    missing: [],
    menuItemId: null,
    plan: BLOCKED,
    result: null,
  };
}

// --- reading the file -------------------------------------------------------

/**
 * Group a parsed CSV into items, with each row's problems on it.
 *
 * The file is one row per ingredient with the item's own facts repeated on
 * every one of them, which is how a flattened recipe sheet exports. Rows
 * disagreeing about the same item's price, category or yield are a fill-down
 * that missed a row - a real and quiet spreadsheet error - so the item is
 * refused with both values named rather than one of them being picked.
 */
export function readMenuCsv(header: string[], rows: string[][]): ReadResult {
  const index = new Map<ColumnName, number>();
  const matched = new Set<number>();
  header.forEach((name, position) => {
    const normalized = normalizeHeader(name);
    for (const [column, aliases] of Object.entries(COLUMNS) as [ColumnName, readonly string[]][]) {
      if (!index.has(column) && aliases.includes(normalized)) {
        index.set(column, position);
        matched.add(position);
      }
    }
  });

  const absent = REQUIRED.filter((column) => !index.has(column));
  if (absent.length > 0) {
    const names = absent.map((column) => COLUMN_WORDS[column]).join(", ");
    return {
      ok: false,
      error:
        `This file has no ${names} column${absent.length === 1 ? "" : "s"}. ` +
        "The loader reads: " +
        `${Object.values(COLUMN_WORDS).join(", ")}. Download the template and paste into it.`,
    };
  }

  const cell = (row: string[], column: ColumnName): string => {
    const position = index.get(column);
    return position === undefined ? "" : (row[position] ?? "").trim();
  };

  const items = new Map<string, LoadItem>();
  rows.forEach((row, offset) => {
    // 1-based and past the header, so "line 61" is the spreadsheet's own row.
    const line = offset + 2;
    const name = cell(row, "item");
    const ingredient = cell(row, "ingredient");
    if (name === "" && ingredient === "") return; // a blank spacer row

    if (name === "") {
      // Nowhere to file this line. It gets its own row on the grid rather
      // than being folded silently into the item above it.
      const orphan = blankItem(`(no item name, line ${line})`);
      orphan.problems.push(`line ${line} names an ingredient but no menu item`);
      items.set(orphan.name, orphan);
      return;
    }

    let item = items.get(nameKey(name));
    if (!item) {
      item = blankItem(name);
      item.category = cell(row, "category") || null;
      item.sellingPrice = cell(row, "selling_price");
      item.yieldPortions = cell(row, "yield_portions");
      item.yieldLabel = cell(row, "yield_label") || null;
      items.set(nameKey(name), item);

      const price = positiveNumber(item.sellingPrice, "selling price");
      if (price) item.problems.push(price);
      const portions = positiveNumber(item.yieldPortions, "yield");
      if (portions) item.problems.push(portions);
    } else {
      const conflicts: [string, string, string][] = [
        ["selling price", item.sellingPrice, cell(row, "selling_price")],
        ["category", item.category ?? "", cell(row, "category")],
        ["yield portions", item.yieldPortions, cell(row, "yield_portions")],
      ];
      for (const [what, first, again] of conflicts) {
        if (first !== again) {
          item.problems.push(
            `line ${line} says the ${what} is "${again}", an earlier line says "${first}"`,
          );
        }
      }
    }

    const qty = cell(row, "qty");
    const unit = cell(row, "unit");
    const measure = measureOf(unit);
    const badNumber = positiveNumber(qty, "quantity");
    const share = usableShare(cell(row, "usable_share"), ingredient);
    item.lines.push({
      row: line,
      ingredient,
      qty,
      unit,
      usableShare: "share" in share ? share.share : null,
      sourceText: cell(row, "source_text") || null,
      ingredientId: null,
      base: "unit" in measure ? measure.unit.base : null,
      problem:
        ingredient === ""
          ? "no ingredient named"
          : (badNumber ??
            ("problem" in measure ? measure.problem : null) ??
            ("problem" in share ? share.problem : null)),
    });
  });

  const ignoredColumns = header.filter(
    (name, position) => !matched.has(position) && name.trim() !== "",
  );
  const list = [...items.values()];
  for (const item of list) {
    if (item.lines.length === 0) item.problems.push("no ingredients on this item");
  }
  if (list.length === 0) {
    return { ok: false, error: "That file has a header but no recipe rows under it." };
  }
  return { ok: true, items: list, ignoredColumns };
}

// --- what committing would change -------------------------------------------

/**
 * Resolve every row against what Faida holds, and say what a commit would do.
 *
 * `details` carries the current recipes of the items this file names, fetched
 * only for items that already exist - on a first load there are none, and on
 * a re-upload they are what makes 43 rows read "no change" before anything is
 * pressed.
 */
export function planLoad(
  items: LoadItem[],
  ingredients: Ingredient[],
  menuItems: MenuItemSummary[],
  details: Map<string, MenuItemDetail>,
): LoadItem[] {
  const byMaterial = new Map(ingredients.map((row) => [nameKey(row.name), row]));
  const live = new Map(
    menuItems.filter((row) => row.archived_at === null).map((row) => [nameKey(row.name), row]),
  );
  const archived = new Set(
    menuItems.filter((row) => row.archived_at !== null).map((row) => nameKey(row.name)),
  );

  return items.map((item) => {
    const missing = new Map<string, MissingMaterial>();
    const lines = item.lines.map((line) => {
      if (line.problem !== null) return line;
      const material = byMaterial.get(nameKey(line.ingredient));
      if (!material) {
        const key = nameKey(line.ingredient);
        const already = missing.get(key);
        if (already) already.rows.push(line.row);
        else missing.set(key, { name: line.ingredient, unit: line.unit, rows: [line.row] });
        return { ...line, ingredientId: null };
      }
      if (line.base !== null && material.base_unit !== line.base) {
        return {
          ...line,
          ingredientId: material.id,
          problem:
            `${material.name} is measured ${MEASURE_WORDS[material.base_unit]} in Faida, ` +
            `but this line is ${MEASURE_WORDS[line.base]}`,
        };
      }
      return { ...line, ingredientId: material.id };
    });

    const key = nameKey(item.name);
    const existing = live.get(key) ?? null;
    const problems = [...item.problems];
    if (existing === null && archived.has(key)) {
      problems.push(
        `"${item.name}" is archived in Faida - bring it back, or take this row out of the sheet`,
      );
    }

    const resolved: LoadItem = {
      ...item,
      lines,
      problems,
      missing: [...missing.values()],
      menuItemId: existing?.id ?? null,
      plan: BLOCKED,
      result: null,
    };

    if (
      problems.length > 0 ||
      lines.length === 0 ||
      lines.some((line) => line.problem !== null)
    ) {
      return resolved;
    }

    // A missing material does not stop the plan being knowable: the item is
    // either new or it is not, and a recipe naming a material Faida has never
    // heard of cannot equal a stored one. Saying "new item" now is what makes
    // the clicks below worth making.

    if (existing === null) {
      return { ...resolved, plan: { kind: "new", version: 1, details: [], rewordedOnly: false } };
    }

    const moved: string[] = [];
    if (!sameNumber(existing.selling_price, item.sellingPrice)) moved.push("selling price");
    if ((existing.category ?? "") !== (item.category ?? "")) moved.push("category");

    const current = details.get(existing.id)?.recipe ?? null;
    const same = current !== null && sameRecipe(current, item, lines);
    return {
      ...resolved,
      plan: {
        kind: same ? "unchanged" : "new_version",
        version: current === null ? 1 : same ? current.version : current.version + 1,
        details: moved,
        rewordedOnly: same && reworded(current, lines),
      },
    };
  });
}

/**
 * One recipe line's identity: which material, how much, in what measure, and
 * what share of it reaches the pot.
 *
 * The share is part of the identity because the door's own key includes it
 * (M12 WP-119): setting 85% on a line that had none changes what the recipe
 * takes out of the storeroom, so it is a new version, and a preview that
 * called it "no change" would have the consultant believe the load did
 * nothing.
 */
function lineKey(ingredientId: string, qty: string, unit: string, share: string | null): string {
  const word = unit.trim().toLowerCase();
  // The API stores the share to four places and hands it back that way, so
  // "0.8500" comes home for the "0.85" that went out - the same round trip
  // `qty` already makes ("220" out, "220.0000" back). Both sides go through
  // `numberKey` for exactly that reason: this is one value, never two.
  const yielded = share === null ? "as purchased" : numberKey(share);
  return `${ingredientId}|${numberKey(qty)}|${UNITS.get(word)?.canonical ?? word}|${yielded}`;
}

/**
 * D8's rule, as the grid predicts it: the same yield and the same multiset of
 * (ingredient, amount, measure, usable share). Order is not information - a
 * consultant who sorts their sheet has not changed a recipe - and a measure
 * spelled "mls" rather than "ml" is formatting. A magnitude is not: 1 kg and
 * 1000 g are the same amount but a different card, and the card's words are
 * the only audit a typed quantity has. Neither is the share (M12 WP-119): the
 * same 1200 g of chicken at 85% usable is a different draw on the storeroom.
 *
 * `source_text` is outside the comparison, by D8's own wording - it is free
 * text a spreadsheet reflows constantly. `reworded` names that case on the
 * row instead of letting the two copies drift apart in silence.
 */
function sameRecipe(
  current: NonNullable<MenuItemDetail["recipe"]>,
  item: LoadItem,
  lines: LoadLine[],
): boolean {
  if (!sameNumber(current.yield_portions, item.yieldPortions)) return false;
  if (current.components.length !== lines.length) return false;
  const stored = current.components
    .map((component) =>
      lineKey(component.ingredient_id, component.qty, component.unit, component.usable_share),
    )
    .sort();
  const incoming = lines
    .map((line) => lineKey(line.ingredientId ?? "", line.qty, line.unit, line.usableShare))
    .sort();
  return stored.every((value, position) => value === incoming[position]);
}

function reworded(current: NonNullable<MenuItemDetail["recipe"]>, lines: LoadLine[]): boolean {
  const stored = new Map(
    current.components.map((component) => [
      lineKey(component.ingredient_id, component.qty, component.unit, component.usable_share),
      component.source_text ?? "",
    ]),
  );
  return lines.some((line) => {
    const before = stored.get(
      lineKey(line.ingredientId ?? "", line.qty, line.unit, line.usableShare),
    );
    return before !== undefined && before !== (line.sourceText ?? "");
  });
}

/**
 * One item as the door takes it (`POST /api/menu-items/load`).
 *
 * The shape lives here rather than inside the screen so that what goes on the
 * wire has a test: a field that quietly stopped being sent would look like a
 * recipe that simply had no yield on it, and nothing on any screen would say
 * otherwise. Only a committable item is ever passed in, which is why every
 * line is known to have a material behind it.
 */
export function loadInput(item: LoadItem): MenuItemLoadInput {
  return {
    name: item.name,
    category: item.category,
    selling_price: item.sellingPrice,
    yield_portions: item.yieldPortions,
    yield_label: item.yieldLabel,
    components: item.lines.map((line) => ({
      ingredient_id: line.ingredientId as string,
      qty: line.qty,
      unit: line.unit,
      usable_share: line.usableShare,
      source_text: line.sourceText,
    })),
  };
}

/** The plain-words summary the grid puts in its "what will change" column. */
export function planWords(item: LoadItem): string {
  const moved =
    item.plan.details.length > 0 ? ` · ${item.plan.details.join(" and ")} updated` : "";
  if (item.plan.kind === "blocked") return "Not loaded";
  if (item.plan.kind === "new") return "New item";
  if (item.plan.kind === "new_version") return `New version (v${item.plan.version})${moved}`;
  return item.plan.details.length > 0 ? `Unchanged${moved}` : "No change";
}
