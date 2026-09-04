/**
 * M8 WP-83: reading a till's export into branch-days, and working out what
 * committing it would change - before anything is pressed.
 *
 * The conversation this serves (PRD §10, C11) is a consultant with the till's
 * own CSV: map its columns once, name the till, say whether the amounts carry
 * VAT, and load a month in a minute. The loop after that is the menu
 * loader's: upload, read the rows that failed, fix those cells, upload again
 * - which only works if a re-upload of 21 days with one fix shows 20 no-ops
 * before the button is pressed. That preview is what this computes.
 *
 * **It predicts; the door decides.** Every judgement here is also made by
 * the API's write door (`sales.py`, WP-80) in the same words, and the grid
 * restamps its days from what the door actually said. Three rules are
 * pinned by C11 and hold on both sides:
 *
 * - **Columns are read by name, never by position** (C11.1). A layout maps
 *   logical columns to header names; a reordered export applies unchanged,
 *   a renamed column stops the file, and no code path here indexes a row by
 *   a number it was not handed by a name.
 * - **No money is divided in the browser.** The takings column is an exact
 *   string sum of the file's own amounts; the net figure - the VAT taken out
 *   - is the door's division and appears only when the door has answered
 *   (outside voice 14).
 * - **A day is unchanged when it holds the same multiset of lines** (C11.4),
 *   in any order, on the same basis and granularity. `dayKey` mirrors
 *   `takings.day_key` on the API side; where the two could drift, the door
 *   wins and the grid shows what it said.
 *
 * Amounts and quantities stay strings from the cell to the wire.
 */

import type { RaggedRow } from "./csv";
import { sumStrings } from "./mock/decimal";
import type {
  AmountBasis,
  Branch,
  DateOrder,
  SalesColumn,
  SalesColumnMap,
  SalesDay,
  SalesDayInput,
  SalesGranularity,
  SalesLayout,
  SalesLineInput,
} from "./types";

// --- columns and layouts ----------------------------------------------------

export const SALES_COLUMNS: readonly SalesColumn[] = [
  "branch",
  "date",
  "item",
  "code",
  "qty",
  "amount",
];

/** The two a file cannot be read without. No item column is the summary
 * shape; no branch column means one branch for the whole file. */
export const REQUIRED_COLUMNS: readonly SalesColumn[] = ["date", "amount"];

export const COLUMN_WORDS: Record<SalesColumn, string> = {
  branch: "branch",
  date: "date",
  item: "item",
  code: "item code",
  qty: "quantity",
  amount: "amount",
};

/** What each column is for, in the mapping step's own words. */
export const COLUMN_HELP: Record<SalesColumn, string> = {
  branch: "which outlet the row belongs to; leave unmapped if the file is one branch",
  date: "the business date the till printed on the row",
  item: "the till's own name for what was sold; leave unmapped for a file of day totals",
  code: "the till's item code (PLU) - it survives a rename",
  qty: "how many were sold",
  amount: "the row's takings, as the till printed them",
};

/**
 * The spellings a real export uses. First match wins, each header name is
 * used once, and a miss simply leaves the column unmapped for the person to
 * pick - the guess is a head start on the mapping step, never a decision.
 */
const ALIASES: Record<SalesColumn, string[]> = {
  branch: ["branch", "outlet", "store", "location", "shop", "site", "branch name", "outlet name"],
  date: ["date", "business date", "day", "sales date", "trading date", "txn date", "bill date"],
  item: ["item", "item name", "product", "product name", "description", "menu item", "article", "name"],
  code: ["plu", "code", "item code", "sku", "product code", "plu code", "item no", "item id"],
  qty: ["qty", "quantity", "sold", "units", "qty sold", "count"],
  amount: [
    "amount",
    "net",
    "total",
    "sales",
    "value",
    "gross",
    "revenue",
    "takings",
    "net sales",
    "gross sales",
    "sales amount",
    "total amount",
    "amount aed",
    "net amount",
  ],
};

/** Lowercased, brackets dropped, every run of spaces, underscores, hyphens
 * and slashes reduced to one space - so "Net Sales (AED)", "net_sales aed"
 * and "NET-SALES AED" are one column name. */
export function normalizeHeader(name: string): string {
  return name
    .toLowerCase()
    .replace(/[()[\]{}.]/g, " ")
    .trim()
    .replace(/[\s\-_/]+/g, " ");
}

/** Column names, normalised, sorted, joined with "|": order-insensitive
 * because a till that reorders its columns has not changed its layout. Over
 * a layout's mapped header names it is exactly the `header_key` the API
 * stores (`amount|date|item|outlet|plu|qty` for the pinned demo header);
 * over a file's whole header it is the file's own identity. The layout is
 * applied by name regardless - the key is evidence, never the rule. */
export function headerKey(header: string[]): string {
  return header
    .map(normalizeHeader)
    .filter((name) => name !== "")
    .sort()
    .join("|");
}

/** The API's `header_key` for a layout: its mapped header names' key. */
export function layoutKey(columns: SalesColumnMap): string {
  return headerKey(Object.values(columns).filter((name): name is string => typeof name === "string"));
}

export function guessColumns(header: string[]): SalesColumnMap {
  const guess: SalesColumnMap = {};
  const taken = new Set<string>();
  for (const column of SALES_COLUMNS) {
    for (const alias of ALIASES[column]) {
      const hit = header.find((name) => normalizeHeader(name) === alias && !taken.has(name));
      if (hit !== undefined) {
        guess[column] = hit;
        taken.add(hit);
        break;
      }
    }
  }
  return guess;
}

export type LayoutApply =
  /** No layout saved yet: the mapping step, fresh. */
  | { kind: "none" }
  /** Exactly one saved layout fits this header by name; extras are the
   * columns it does not read, noted and left alone. */
  | { kind: "apply"; layout: SalesLayout; extras: string[] }
  /** More than one fits: ask which till this is. */
  | { kind: "choose"; layouts: SalesLayout[] }
  /** The closest layout reads columns this file no longer has - the drift
   * stop. `missing` is what disappeared, `appeared` what is new, and the
   * mapping step is offered again; nothing is ever read by position. */
  | { kind: "drift"; layout: SalesLayout; missing: string[]; appeared: string[] };

/** Which saved layout, if any, reads this file. Every column a layout maps
 * must be present by name; a reordered export still fits, a renamed mapped
 * column does not (C11.1, PRD §10). */
export function applyLayout(header: string[], layouts: SalesLayout[]): LayoutApply {
  if (layouts.length === 0) return { kind: "none" };
  const present = new Set(header.map(normalizeHeader).filter((name) => name !== ""));
  const mappedNames = (layout: SalesLayout) =>
    Object.values(layout.columns).filter((name): name is string => typeof name === "string");
  const fits = layouts.filter((layout) =>
    mappedNames(layout).every((name) => present.has(normalizeHeader(name))),
  );
  const newestFirst = (a: SalesLayout, b: SalesLayout) => (a.updated_at < b.updated_at ? 1 : -1);
  if (fits.length === 1) {
    const mapped = new Set(mappedNames(fits[0]).map(normalizeHeader));
    const extras = header.filter((name) => name !== "" && !mapped.has(normalizeHeader(name)));
    return { kind: "apply", layout: fits[0], extras };
  }
  if (fits.length > 1) return { kind: "choose", layouts: [...fits].sort(newestFirst) };
  const closest = [...layouts].sort((a, b) => {
    const score = (layout: SalesLayout) =>
      mappedNames(layout).filter((name) => present.has(normalizeHeader(name))).length;
    return score(b) - score(a) || newestFirst(a, b);
  })[0];
  const mapped = new Set(mappedNames(closest).map(normalizeHeader));
  return {
    kind: "drift",
    layout: closest,
    missing: mappedNames(closest).filter((name) => !present.has(normalizeHeader(name))),
    appeared: header.filter((name) => name !== "" && !mapped.has(normalizeHeader(name))),
  };
}

/** The drift stop's one sentence: what disappeared, what appeared, and the
 * way out. */
export function driftSentence(drift: Extract<LayoutApply, { kind: "drift" }>): string {
  const missing = drift.missing.map((name) => `"${name}"`).join(", ");
  const appeared =
    drift.appeared.length > 0
      ? ` New in this file: ${drift.appeared.map((name) => `"${name}"`).join(", ")}.`
      : "";
  return (
    `The saved layout "${drift.layout.name}" reads ${
      drift.missing.length === 1 ? "a column" : "columns"
    } this file does not have: ${missing}.${appeared} ` +
    "Map the columns again below - nothing is ever read by position."
  );
}

// --- dates ------------------------------------------------------------------

const MONTH_WORDS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];

function daysInMonth(year: number, month: number): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

const pad = (value: number) => String(value).padStart(2, "0");

export type DateRead = { ok: true; iso: string } | { ok: false; problem: string };

/**
 * Read one date cell the way a person would, and stop when two people would
 * read it differently (the `dates.py` rule, not a port of it).
 *
 * A four-digit year is the anchor: `2026-08-25` reads year-first whatever
 * the layout says (nothing else has four digits), `25/08/2026` reads
 * day-first when the layout says so, and `5/7/26` reads two ways and stops
 * the row - a till prints full years, and a two-digit one is a spreadsheet
 * that reformatted the column. A trailing time is ignored; `25 Aug 2026` is
 * taken too. A month of 25 is not a date, whichever way it was meant.
 */
export function readDate(text: string, order: DateOrder): DateRead {
  const raw = text.trim();
  const dateOnly = raw.replace(/[ T]\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$/, "").trim();
  let year: string;
  let month: number;
  let day: number;
  const numeric = /^(\d{1,4})[/\-.](\d{1,2})[/\-.](\d{1,4})$/.exec(dateOnly);
  if (numeric) {
    const [, a, b, c] = numeric;
    if (a.length === 4) {
      year = a;
      month = Number(b);
      day = Number(c);
    } else if (c.length === 4) {
      if (order === "ymd") {
        return {
          ok: false,
          problem:
            `"${raw}" has its year last, but this layout reads dates year-first - ` +
            "change the layout's date order",
        };
      }
      day = Number(a);
      month = Number(b);
      year = c;
    } else {
      return {
        ok: false,
        problem:
          `"${raw}" reads two ways - export dates with a four-digit year (25/08/2026), ` +
          "the only form this loader takes on trust",
      };
    }
  } else {
    const named = /^(\d{1,2})[ /-]+([A-Za-z]{3,})[ /,-]+(\d{4})$/.exec(dateOnly);
    if (!named) {
      return {
        ok: false,
        problem: `"${raw}" is not a date this loader reads - use 25/08/2026 or 2026-08-25`,
      };
    }
    const index = MONTH_WORDS.indexOf(named[2].slice(0, 3).toLowerCase());
    if (index < 0) {
      return { ok: false, problem: `"${raw}" is not a date: there is no month called ${named[2]}` };
    }
    day = Number(named[1]);
    month = index + 1;
    year = named[3];
  }
  if (month < 1 || month > 12) {
    return { ok: false, problem: `"${raw}" is not a date: there is no month ${month}` };
  }
  if (day < 1 || day > daysInMonth(Number(year), month)) {
    return { ok: false, problem: `"${raw}" is not a date: there is no day ${day} in that month` };
  }
  return { ok: true, iso: `${year}-${pad(month)}-${pad(day)}` };
}

/** Year-first when any date cell starts with four digits, day-first
 * otherwise - the mapping step's default, shown with the first cell read
 * both ways so the person confirms rather than trusts. */
export function guessDateOrder(cells: string[]): DateOrder {
  return cells.some((cell) => /^\d{4}[/\-.]/.test(cell.trim())) ? "ymd" : "dmy";
}

export function isoToday(): string {
  const now = new Date();
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

export function isoAddDays(iso: string, days: number): string {
  const [year, month, day] = iso.split("-").map(Number);
  const moved = new Date(Date.UTC(year, month - 1, day + days));
  return `${moved.getUTCFullYear()}-${pad(moved.getUTCMonth() + 1)}-${pad(moved.getUTCDate())}`;
}

/** Every date from `from` to `to`, inclusive - a file's own range. */
export function isoRange(from: string, to: string): string[] {
  const dates: string[] = [];
  for (let cursor = from; cursor <= to; cursor = isoAddDays(cursor, 1)) dates.push(cursor);
  return dates;
}

// --- numbers and names ------------------------------------------------------

/** The door's own rule for an amount: a signed decimal, nothing else. A
 * refund row is legal and reduces the day (C11.2). */
export function amountProblem(value: string, what: "amount" | "quantity"): string | null {
  const text = value.trim();
  if (text === "") return `no ${what}`;
  if (text.includes(",")) {
    return `"${text}" has a thousands separator in it - format that column as a plain number`;
  }
  if (!/^-?\d+(\.\d+)?$/.test(text)) {
    return `"${text}" is not ${what === "amount" ? "an amount" : "a quantity"}`;
  }
  return null;
}

/** "490", "490.00" and "0490.0" are one amount; "-0.50" and "-.5" are not
 * both accepted, but "-0.50" and "-0.5" are one. String operations only. */
export function numberKey(value: string): string {
  const text = value.trim();
  const negative = text.startsWith("-");
  const unsigned = negative ? text.slice(1) : text;
  const trimmed = unsigned.includes(".")
    ? unsigned.replace(/0+$/, "").replace(/\.$/, "")
    : unsigned;
  const magnitude = trimmed.replace(/^0+(?=\d)/, "") || "0";
  return negative && magnitude !== "0" ? `-${magnitude}` : magnitude;
}

/** Case- and space-insensitive, the way a person reads two names as one -
 * and the way `till_items.name_key` is minted. */
export function nameKey(name: string): string {
  return name.trim().toLowerCase().replace(/\s+/g, " ");
}

/** The till's own label for a branch, resolved through the chain's facts:
 * the branch's name, or an alias taught once (C11.1). Never guessed. */
export function branchFor(label: string, branches: Branch[]): Branch | null {
  const key = nameKey(label);
  if (key === "") return null;
  return (
    branches.find(
      (branch) =>
        nameKey(branch.name) === key || branch.aliases.some((alias) => nameKey(alias) === key),
    ) ?? null
  );
}

// --- reading the file -------------------------------------------------------

/** One item row, the till's own words. */
export interface ReadLine {
  /** 1-based file line, so "line 14" means the spreadsheet's own row. */
  line: number;
  name: string;
  code: string | null;
  qty: string | null;
  amount: string;
}

/** One branch-day as the file describes it, with its own problems on it. */
export interface ReadDay {
  /** `${branchId}|${date}` for a placed day; unique regardless. */
  key: string;
  branchId: string | null;
  branchName: string | null;
  /** The till's label, when the file has a branch column. */
  branchLabel: string | null;
  /** ISO, or the raw cell when it could not be read. */
  date: string;
  granularity: SalesGranularity;
  lines: ReadLine[];
  /** A summary day's amount ("0.00" for a closed or gap day); null on an
   * item day. */
  amount: string | null;
  /** The exact sum of the file's amounts for the day. Money string. */
  takings: string;
  /** The file lines that fed this day. */
  rows: number[];
  /** Sentences that stop the day being sent. */
  problems: string[];
  /** A day inside the file's own date range with no rows: loaded as a zero
   * day, because the till's export range is the till's statement of the
   * days it covers (C11.4). */
  gap: boolean;
}

export interface ReadOptions {
  columns: SalesColumnMap;
  dateOrder: DateOrder;
  branches: Branch[];
  /** The one branch for a file with no branch column. */
  fileBranchId: string | null;
  /** ISO. A business date after tomorrow is refused, because a swapped day
   * and month lands in the future (C11.4). */
  today: string;
}

export type ReadSalesResult =
  | {
      ok: true;
      days: ReadDay[];
      granularity: SalesGranularity;
      /** Footer rows and the like: no date, so skipped and counted. */
      skippedNoDate: number;
      ignoredColumns: string[];
      /** The till's labels no branch answers to, each once. */
      unknownBranches: string[];
    }
  | { ok: false; error: string };

const EARLIEST = "2020-01-01";

/**
 * Group a parsed CSV into branch-days, with each row's problems on the day it
 * belongs to.
 *
 * Item-wise (an item column is mapped): one row per till item, the day is the
 * sum. Summary (no item column): one row per branch-day, and a second row
 * for the same day stops it with a sentence rather than picking one. A file
 * is one shape throughout (C11.1). In an item-wise file, a row with no item
 * name and a zero amount is the closed-day row the template shows; any other
 * row with an amount and no name is a mistake, named by line.
 */
export function readSalesCsv(
  header: string[],
  rows: string[][],
  ragged: RaggedRow[],
  options: ReadOptions,
): ReadSalesResult {
  const { columns, dateOrder, branches, fileBranchId, today } = options;
  const position = new Map<SalesColumn, number>();
  for (const column of SALES_COLUMNS) {
    const wanted = columns[column];
    if (!wanted) continue;
    const index = header.findIndex((name) => normalizeHeader(name) === normalizeHeader(wanted));
    if (index < 0) {
      return {
        ok: false,
        error:
          `This file has no "${wanted}" column, which the layout reads as the ` +
          `${COLUMN_WORDS[column]}. Map the columns again.`,
      };
    }
    position.set(column, index);
  }
  for (const column of REQUIRED_COLUMNS) {
    if (!position.has(column)) {
      return {
        ok: false,
        error: `Say which column is the ${COLUMN_WORDS[column]} - a file cannot be read without one.`,
      };
    }
  }
  if (!position.has("branch") && fileBranchId === null) {
    return {
      ok: false,
      error: "This file has no branch column, so say which branch the whole file is for.",
    };
  }
  if (ragged.length > 0) {
    const named = ragged
      .slice(0, 3)
      .map((row) => `line ${row.line} (${row.cells} cells, the header has ${row.expected})`)
      .join(", ");
    const more = ragged.length > 3 ? ` and ${ragged.length - 3} more` : "";
    return {
      ok: false,
      error:
        `${ragged.length === 1 ? "A row has" : "Rows have"} the wrong number of cells: ` +
        `${named}${more}. A comma inside an unquoted name, or a cell missing off the end - ` +
        "fix those lines in the spreadsheet and upload the file again.",
    };
  }

  const cell = (row: string[], column: SalesColumn): string => {
    const index = position.get(column);
    return index === undefined ? "" : (row[index] ?? "").trim();
  };
  const granularity: SalesGranularity = position.has("item") ? "item" : "summary";
  const tomorrow = isoAddDays(today, 1);

  const days = new Map<string, ReadDay>();
  const branchOrder: string[] = [];
  const unknownBranches: string[] = [];
  let skippedNoDate = 0;
  let unplaced = 0;

  const dayFor = (key: string, seed: Omit<ReadDay, "key" | "lines" | "rows" | "problems" | "takings">) => {
    let day = days.get(key);
    if (!day) {
      day = { key, lines: [], rows: [], problems: [], takings: "0.00", ...seed };
      days.set(key, day);
      const branchKey = day.branchId ?? day.branchLabel ?? "";
      if (!branchOrder.includes(branchKey)) branchOrder.push(branchKey);
    }
    return day;
  };

  rows.forEach((row, offset) => {
    const line = offset + 2;
    if (row.every((value) => value.trim() === "")) return; // a spacer

    const dateText = cell(row, "date");
    if (dateText === "") {
      // A totals footer, or a subtotal line: no date, so it belongs to no
      // day. Counted, never dated by guess.
      skippedNoDate += 1;
      return;
    }

    let branchId: string | null = fileBranchId;
    let branchName: string | null = null;
    let branchLabel: string | null = null;
    const problems: string[] = [];
    if (position.has("branch")) {
      branchLabel = cell(row, "branch");
      const branch = branchLabel === "" ? null : branchFor(branchLabel, branches);
      if (branch) {
        branchId = branch.id;
        branchName = branch.name;
      } else {
        branchId = null;
        if (branchLabel === "") {
          problems.push(`line ${line} has no branch`);
        } else {
          if (!unknownBranches.includes(branchLabel)) unknownBranches.push(branchLabel);
          problems.push(
            `the till calls this branch "${branchLabel}", which is not a branch in Faida - ` +
              "say which branch it is, once, below",
          );
        }
      }
    } else {
      branchName = branches.find((branch) => branch.id === fileBranchId)?.name ?? null;
    }

    const date = readDate(dateText, dateOrder);
    if (!date.ok) {
      // Nowhere to file this row: it gets a row of its own on the grid,
      // blocked, rather than being folded into a day by guess.
      unplaced += 1;
      const day = dayFor(`unplaced|${line}`, {
        branchId,
        branchName,
        branchLabel,
        date: dateText,
        granularity,
        amount: null,
        gap: false,
      });
      day.rows.push(line);
      day.problems.push(`line ${line}: ${date.problem}`, ...problems);
      return;
    }
    if (date.iso > tomorrow) {
      problems.push(`line ${line}: ${dateText} is after tomorrow - check the layout's date order`);
    } else if (date.iso < EARLIEST) {
      problems.push(`line ${line}: ${dateText} is before 2020`);
    }

    const key = `${branchId ?? `?${nameKey(branchLabel ?? "")}`}|${date.iso}`;
    const day = dayFor(key, {
      branchId,
      branchName,
      branchLabel,
      date: date.iso,
      granularity,
      amount: null,
      gap: false,
    });
    day.rows.push(line);
    for (const problem of problems) if (!day.problems.includes(problem)) day.problems.push(problem);

    const amountText = cell(row, "amount");
    const amountBad = amountProblem(amountText, "amount");
    const qtyText = position.has("qty") ? cell(row, "qty") : "";
    const qtyBad = qtyText === "" ? null : amountProblem(qtyText, "quantity");

    if (granularity === "summary") {
      if (day.amount !== null) {
        day.problems.push(
          `line ${line} is a second row for ${date.iso} at ${
            branchName ?? branchLabel ?? "this branch"
          } - a summary file has one row per branch per day`,
        );
        return;
      }
      if (amountBad) {
        day.problems.push(`line ${line}: ${amountBad}`);
        day.amount = "0";
        return;
      }
      day.amount = amountText;
      day.takings = sumStrings([amountText]);
      return;
    }

    const name = cell(row, "item");
    const codeText = position.has("code") ? cell(row, "code") : "";
    if (name === "") {
      // The closed-day row: no item, nothing sold. Anything else with no name
      // is a row that cannot be a till item.
      if (!amountBad && numberKey(amountText) === "0" && qtyText === "") {
        day.rows.push(line);
        if (day.lines.length > 0) {
          day.problems.push(
            `line ${line} marks the day closed, but the day has ${day.lines.length} other ` +
              `${day.lines.length === 1 ? "row" : "rows"}`,
          );
        }
        day.amount = "0.00";
        return;
      }
      day.problems.push(`line ${line} has an amount but no item name`);
      return;
    }
    if (day.amount !== null) {
      day.problems.push(`line ${line} sells something on a day another row marks closed`);
    }
    if (amountBad) day.problems.push(`line ${line}: ${amountBad}`);
    if (qtyBad) day.problems.push(`line ${line}: ${qtyBad}`);
    day.lines.push({
      line,
      name,
      code: codeText === "" ? null : codeText,
      qty: qtyText === "" ? null : qtyText,
      amount: amountBad ? "0" : amountText,
    });
  });

  // Item days: the takings are the sum of the lines; a closed-day row with
  // no lines is a summary zero day.
  for (const day of days.values()) {
    if (day.granularity !== "item") continue;
    if (day.lines.length === 0 && day.amount !== null) {
      day.granularity = "summary";
      day.takings = "0.00";
    } else {
      day.amount = null;
      day.takings = sumStrings(day.lines.map((line) => line.amount));
    }
  }

  // Interior gaps: a day inside the file's own range with no rows for a
  // placed branch loads as a zero day (C11.4, Codex 8).
  const placed = [...days.values()].filter(
    (day) => day.branchId !== null && /^\d{4}-\d{2}-\d{2}$/.test(day.date),
  );
  if (placed.length > 0) {
    const from = placed.map((day) => day.date).sort()[0];
    const to = placed.map((day) => day.date).sort().at(-1) as string;
    const range = isoRange(from, to);
    for (const branchId of [...new Set(placed.map((day) => day.branchId as string))]) {
      const branch = branches.find((row) => row.id === branchId);
      for (const date of range) {
        const key = `${branchId}|${date}`;
        if (days.has(key)) continue;
        days.set(key, {
          key,
          branchId,
          branchName: branch?.name ?? null,
          branchLabel: null,
          date,
          granularity: "summary",
          lines: [],
          amount: "0.00",
          takings: "0.00",
          rows: [],
          problems: [],
          gap: true,
        });
      }
    }
  }

  if (days.size === 0) {
    return {
      ok: false,
      error:
        skippedNoDate > 0
          ? "Every row in that file has an empty date cell - nothing to load."
          : "That file has a header but no sales rows under it.",
    };
  }

  const mapped = new Set([...position.values()]);
  const ignoredColumns = header.filter((name, index) => !mapped.has(index) && name.trim() !== "");
  const orderOf = (day: ReadDay) => {
    const index = branchOrder.indexOf(day.branchId ?? day.branchLabel ?? "");
    return index < 0 ? branchOrder.length : index;
  };
  const list = [...days.values()].sort(
    (a, b) => orderOf(a) - orderOf(b) || a.date.localeCompare(b.date) || a.key.localeCompare(b.key),
  );
  void unplaced;
  return { ok: true, days: list, granularity, skippedNoDate, ignoredColumns, unknownBranches };
}

// --- what committing would change -------------------------------------------

/** One line's identity for C11.4: normalised name, code, quantity, amount. */
function lineKey(name: string, code: string | null, qty: string | null, amount: string): string {
  return [nameKey(name), code ?? "", qty === null ? "" : numberKey(qty), numberKey(amount)].join(
    "",
  );
}

/**
 * A day's identity, mirroring `takings.day_key` on the API: the granularity,
 * the basis, and the multiset of lines in any order (a summary day's one
 * amount stands in for its lines). Two days with one key are unchanged and
 * nothing is written.
 */
export function dayKey(
  granularity: SalesGranularity,
  basis: AmountBasis,
  lines: { name: string; code: string | null; qty: string | null; amount: string }[],
  amount: string | null,
): string {
  const body =
    granularity === "summary"
      ? `amount=${numberKey(amount ?? "0")}`
      : lines
          .map((line) => lineKey(line.name, line.code, line.qty, line.amount))
          .sort()
          .join("");
  return `${granularity}|${basis}|${body}`;
}

function storedKey(day: SalesDay): string {
  return dayKey(day.granularity, day.amount_basis, day.lines, day.takings);
}

export type DayPlanKind = "new" | "unchanged" | "replaced" | "blocked";

export interface DayPlan {
  kind: DayPlanKind;
  /** The stored day this would replace, so the grid shows before and after. */
  previous: { takings: string; net_sales: string; line_count: number } | null;
  /** The takings or the row count would fall - the half-day export over a
   * full one. Blocked until the consultant ticks that day by name (C11.4). */
  shrinking: boolean;
}

/** What the door actually did, as it reported it. */
export interface DayResult {
  outcome: "loaded" | "unchanged" | "replaced" | "refused";
  net_sales: string | null;
  message: string | null;
}

export interface PlannedDay extends ReadDay {
  plan: DayPlan;
  /** The consultant's tick on a shrinking day. */
  confirmed: boolean;
  result: DayResult | null;
}

/** Compare two money strings as numbers, string operations only. */
function moneyLess(a: string, b: string): boolean {
  const scale = (value: string) => {
    const [whole, frac = ""] = value.replace("-", "").split(".");
    return { whole, frac };
  };
  const negA = a.trim().startsWith("-");
  const negB = b.trim().startsWith("-");
  if (negA !== negB) return negA;
  const x = scale(a);
  const y = scale(b);
  const width = Math.max(x.frac.length, y.frac.length);
  const px = BigInt(x.whole + x.frac.padEnd(width, "0"));
  const py = BigInt(y.whole + y.frac.padEnd(width, "0"));
  return negA ? px > py : px < py;
}

/**
 * Resolve every day against what Faida holds, and say what a commit would do
 * - new, unchanged, replaced (with the before and after), or blocked.
 */
export function planDays(days: ReadDay[], stored: SalesDay[], basis: AmountBasis): PlannedDay[] {
  const held = new Map(stored.map((day) => [`${day.branch_id}|${day.business_date}`, day]));
  return days.map((day) => {
    const blocked: DayPlan = { kind: "blocked", previous: null, shrinking: false };
    if (day.problems.length > 0 || day.branchId === null) {
      return { ...day, plan: blocked, confirmed: false, result: null };
    }
    const existing = held.get(day.key) ?? null;
    if (!existing) {
      return {
        ...day,
        plan: { kind: "new", previous: null, shrinking: false },
        confirmed: false,
        result: null,
      };
    }
    const previous = {
      takings: existing.takings,
      net_sales: existing.net_sales,
      line_count: existing.line_count,
    };
    if (storedKey(existing) === dayKey(day.granularity, basis, day.lines, day.amount)) {
      return { ...day, plan: { kind: "unchanged", previous, shrinking: false }, confirmed: false, result: null };
    }
    const shrinking =
      moneyLess(day.takings, existing.takings) || day.lines.length < existing.line_count;
    return { ...day, plan: { kind: "replaced", previous, shrinking }, confirmed: false, result: null };
  });
}

/** A day can be sent when nothing refuses it and, if it shrinks a stored
 * day, the consultant has ticked it. */
export function committable(day: PlannedDay): boolean {
  return day.plan.kind !== "blocked" && (!day.plan.shrinking || day.confirmed);
}

/** The file's own date range, for the stored days the plan compares against. */
export function dateRange(days: ReadDay[]): { from: string; to: string } | null {
  const dates = days.map((day) => day.date).filter((date) => /^\d{4}-\d{2}-\d{2}$/.test(date)).sort();
  if (dates.length === 0) return null;
  return { from: dates[0], to: dates[dates.length - 1] };
}

/**
 * The door takes at most 31 days per request - one branch-month - and runs
 * one transaction per day. Groups follow the grid's order, so a year of
 * history is a few dozen requests and a refresh mid-run resumes on days the
 * door already answered as unchanged.
 */
export function requestGroups(days: PlannedDay[]): PlannedDay[][] {
  const groups = new Map<string, PlannedDay[]>();
  for (const day of days) {
    if (!committable(day)) continue;
    const key = `${day.branchId}|${day.date.slice(0, 7)}`;
    const group = groups.get(key);
    if (group) group.push(day);
    else groups.set(key, [day]);
  }
  const chunked: PlannedDay[][] = [];
  for (const group of groups.values()) {
    for (let start = 0; start < group.length; start += 31) chunked.push(group.slice(start, start + 31));
  }
  return chunked;
}

/** One day as the door takes it (§3.1). */
export function toDayInput(
  day: PlannedDay,
  basis: AmountBasis,
  layoutId: string | null,
  source: { sha256: string; filename: string },
): SalesDayInput {
  const base = {
    branch_id: day.branchId as string,
    business_date: day.date,
    granularity: day.granularity,
    amount_basis: basis,
    layout_id: layoutId,
    source,
  };
  if (day.granularity === "summary") return { ...base, amount: day.amount ?? "0.00" };
  const lines: SalesLineInput[] = day.lines.map((line, index) => ({
    position: index,
    name: line.name,
    code: line.code,
    qty: line.qty,
    amount: line.amount,
  }));
  return { ...base, lines };
}

/** The plain-words summary the grid puts in its "what will change" column. */
export function planWords(day: PlannedDay): string {
  if (day.plan.kind === "blocked") return "Not loaded";
  if (day.gap) return "No rows in the file - loads as a zero day";
  if (day.plan.kind === "new") {
    return day.granularity === "summary" && day.amount !== null && numberKey(day.amount) === "0"
      ? "New day, closed"
      : "New day";
  }
  if (day.plan.kind === "unchanged") return "No change";
  return "Replaces the stored day";
}
