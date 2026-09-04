/**
 * The sales door, offline (M8 WP-83 against WP-80's `sales.py`).
 *
 * The loader has to run with no backend at all - that is how the demo and
 * every QA pass drive it - so this reproduces the door's *decisions* in the
 * door's own words: the three outcomes and their previous figures, the
 * 31-day body, the date window, the one-shape rule, the foreign branch, the
 * alias that already names another branch, the file kept under its own
 * hash. Money is computed in exactly one place, the way the door does it
 * (C11.2: `net = amount / (1 + rate)`, half-up to a fil, the day the exact
 * sum of its lines), because a net figure is the door's answer and the grid
 * restamps from it. Nothing here is a second implementation of the ratio.
 *
 * State lives in module memory: layouts, days and aliases persist across
 * screens for the length of the browser session and reset on reload.
 */

import { add, dec, divTo, fmt, type Dec } from "./decimal";
import { MOCK_BRANCHES } from "./fixtures";
import { ApiError } from "../errors";
import { dayKey, headerKey, isoAddDays, isoToday, nameKey, numberKey } from "../salesLoad";
import type {
  Branch,
  BranchAlias,
  SalesDay,
  SalesDayResult,
  SalesDaysInput,
  SalesDaysResult,
  SalesFileResult,
  SalesLayout,
  SalesLayoutInput,
  SalesLine,
} from "../types";

/** The mock tenant is AED: the C4 table's 5 %, the same lookup the door
 * makes from `VAT_RATE_BY_CURRENCY[tenant.currency]`. */
const VAT_RATE = "0.05";
const DIVISOR: Dec = dec("1.05") as Dec;

const LATENCY_MS = 120;

function clone<T>(value: T): T {
  return structuredClone(value);
}

async function respond<T>(value: T): Promise<T> {
  await new Promise((resolve) => setTimeout(resolve, LATENCY_MS));
  return clone(value);
}

/** Python datetime.isoformat() form: offset suffix, never "Z". */
function nowIso(): string {
  return new Date().toISOString().replace("Z", "+00:00");
}

let counter = 0;
const nextId = (prefix: string) => `${prefix}-${(counter += 1).toString().padStart(4, "0")}`;

// --- branches and aliases ---------------------------------------------------

const branches: Branch[] = MOCK_BRANCHES.map((branch) => ({
  id: branch.id,
  name: branch.name,
  timezone: "Asia/Dubai",
  aliases: [],
}));

const aliases: BranchAlias[] = [];

export async function mockGetBranches(): Promise<Branch[]> {
  return respond(branches);
}

/** POST /api/branches/{id}/aliases: 201 with the alias; 409 when the alias
 * key already names another branch; the same branch again answers the
 * existing row (idempotent, like every door). */
export async function mockAddBranchAlias(branchId: string, alias: string): Promise<BranchAlias> {
  const branch = branches.find((row) => row.id === branchId);
  if (!branch) throw new ApiError(404, "branch not found");
  const key = nameKey(alias);
  if (key === "") throw new ApiError(422, "alias is empty");
  const existing = aliases.find((row) => row.alias_key === key);
  if (existing && existing.branch_id !== branchId) {
    const other = branches.find((row) => row.id === existing.branch_id);
    throw new ApiError(409, `"${alias.trim()}" already names ${other?.name ?? "another branch"}`);
  }
  if (existing) return respond(existing);
  const row: BranchAlias = { id: nextId("alias"), branch_id: branchId, alias: alias.trim(), alias_key: key };
  aliases.push(row);
  branch.aliases.push(row.alias);
  return respond(row);
}

// --- the raw file -----------------------------------------------------------

const files = new Map<string, { filename: string; bytes: number }>();

async function sha256Hex(bytes: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

/** POST /api/sales/files: the bytes kept once under their own hash. A second
 * post of the same bytes answers the same hash and stores nothing. */
export async function mockPostSalesFile(file: File): Promise<SalesFileResult> {
  const bytes = await file.arrayBuffer();
  const sha256 = await sha256Hex(bytes);
  const known = files.get(sha256);
  if (!known) files.set(sha256, { filename: file.name, bytes: bytes.byteLength });
  return respond({ sha256, filename: known?.filename ?? file.name, bytes: bytes.byteLength });
}

// --- layouts ----------------------------------------------------------------

const layouts: SalesLayout[] = [];

export async function mockGetSalesLayouts(): Promise<SalesLayout[]> {
  return respond(layouts);
}

/** POST /api/sales/layouts: upsert by name, `header_key` derived from the
 * mapped header names, sorted - never the client's word. */
export async function mockSaveSalesLayout(body: SalesLayoutInput): Promise<SalesLayout> {
  const name = body.name.trim();
  if (name === "") throw new ApiError(422, "the layout needs a name - the till, as you call it");
  if (!body.columns.date || !body.columns.amount) {
    throw new ApiError(422, "a layout maps at least the date and the amount");
  }
  const key = headerKey(
    Object.values(body.columns).filter((value): value is string => typeof value === "string"),
  );
  const existing = layouts.find((row) => nameKey(row.name) === nameKey(name));
  if (existing) {
    existing.columns = clone(body.columns);
    existing.header_key = key;
    existing.amount_basis = body.amount_basis;
    existing.date_order = body.date_order;
    existing.updated_at = nowIso();
    return respond(existing);
  }
  const layout: SalesLayout = {
    id: nextId("layout"),
    name,
    header_key: key,
    columns: clone(body.columns),
    amount_basis: body.amount_basis,
    date_order: body.date_order,
    updated_at: nowIso(),
  };
  layouts.push(layout);
  return respond(layout);
}

// --- days -------------------------------------------------------------------

const days = new Map<string, SalesDay>();

/** `till_items`, minted on first sight: by the till's code when the file has
 * one, by the normalised name otherwise (C11.7). */
const tillItems = new Map<string, { id: string; name: string; code: string | null }>();

function tillItemFor(name: string, code: string | null): string {
  const key = code !== null && code !== "" ? `code:${code}` : `name:${nameKey(name)}`;
  let item = tillItems.get(key);
  if (!item) {
    item = { id: nextId("till"), name, code: code || null };
    tillItems.set(key, item);
  }
  return item.id;
}

const MONEY = /^-?\d+(\.\d+)?$/;

/** C11.2: the net figure, taken out once per line, half-up to a fil. */
function netOf(amount: string, basis: "inclusive" | "exclusive"): string {
  const value = dec(amount) as Dec;
  if (basis === "exclusive") return fmt(divTo(value, dec("1") as Dec, 2));
  return fmt(divTo(value, DIVISOR, 2));
}

function sumOf(values: string[]): string {
  let total: Dec = { units: 0n, scale: 2 };
  for (const value of values) total = add(total, dec(value) as Dec);
  return fmt(total);
}

export async function mockGetSalesDays(from: string, to: string): Promise<SalesDay[]> {
  const rows = [...days.values()]
    .filter((day) => day.business_date >= from && day.business_date <= to)
    .sort((a, b) => a.branch_id.localeCompare(b.branch_id) || a.business_date.localeCompare(b.business_date));
  return respond(rows);
}

/**
 * POST /api/sales/days: at most 31 days, validated as a body first (a bad
 * row names its day and position and nothing lands), then one transaction
 * per day with C11.4's outcome - loaded, unchanged (nothing written) or
 * replaced (the previous figures named).
 */
export async function mockPostSalesDays(body: SalesDaysInput): Promise<SalesDaysResult> {
  if (body.days.length === 0) throw new ApiError(422, "no days in the body");
  if (body.days.length > 31) {
    throw new ApiError(422, "at most 31 days per request - one branch-month at a time");
  }
  const tomorrow = isoAddDays(isoToday(), 1);
  for (const day of body.days) {
    const branch = branches.find((row) => row.id === day.branch_id);
    if (!branch) throw new ApiError(404, "branch not found");
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day.business_date)) {
      throw new ApiError(422, `${day.business_date} is not a date`);
    }
    if (day.business_date > tomorrow) {
      throw new ApiError(
        422,
        `${day.business_date} is after tomorrow - a swapped day and month lands in the future; ` +
          "check the layout's date order",
      );
    }
    if (day.business_date < "2020-01-01") {
      throw new ApiError(422, `${day.business_date} is before 2020`);
    }
    if (day.granularity === "summary") {
      if (day.lines && day.lines.length > 0) {
        throw new ApiError(422, `${day.business_date}: a summary day carries no lines`);
      }
      if (day.amount === undefined || !MONEY.test(day.amount.trim())) {
        throw new ApiError(422, `${day.business_date}: a closed day needs an amount of 0`);
      }
      if (!/^-?0+(\.0+)?$/.test(day.amount.trim())) {
        // The door's rule since the founder's 2026-09-04 call: item-wise only.
        throw new ApiError(
          422,
          `${day.business_date}: Faida loads item-wise exports for now, so a day without item ` +
            "rows can only be a closed day (amount 0); a day-totals export comes with the pilot (M11)",
        );
      }
    } else {
      if (!day.lines || day.lines.length === 0) {
        throw new ApiError(422, `${day.business_date}: an item day needs at least one line`);
      }
      if (day.amount !== undefined) {
        throw new ApiError(422, `${day.business_date}: an item day carries lines, not an amount`);
      }
      day.lines.forEach((line) => {
        if (line.name.trim() === "") {
          throw new ApiError(422, `${day.business_date} line ${line.position}: no item name`);
        }
        if (!MONEY.test(line.amount.trim())) {
          throw new ApiError(
            422,
            `${day.business_date} line ${line.position}: "${line.amount}" is not an amount`,
          );
        }
        if (line.qty !== null && !MONEY.test(line.qty.trim())) {
          throw new ApiError(
            422,
            `${day.business_date} line ${line.position}: "${line.qty}" is not a quantity`,
          );
        }
      });
    }
  }

  const results: SalesDayResult[] = [];
  for (const posted of body.days) {
    const key = `${posted.branch_id}|${posted.business_date}`;
    const existing = days.get(key) ?? null;
    const lines: SalesLine[] =
      posted.granularity === "summary"
        ? []
        : (posted.lines ?? []).map((line) => ({
            position: line.position,
            name: line.name.trim(),
            code: line.code === null || line.code.trim() === "" ? null : line.code.trim(),
            qty: line.qty === null || line.qty.trim() === "" ? null : line.qty.trim(),
            amount: line.amount.trim(),
            net_amount: netOf(line.amount.trim(), posted.amount_basis),
            till_item_id: tillItemFor(line.name.trim(), line.code),
          }));
    const amount = posted.granularity === "summary" ? (posted.amount as string).trim() : null;
    const takings = posted.granularity === "summary" ? sumOf([amount as string]) : sumOf(lines.map((l) => l.amount));
    const net = posted.granularity === "summary"
      ? netOf(amount as string, posted.amount_basis)
      : sumOf(lines.map((line) => line.net_amount));

    const incomingKey = dayKey(posted.granularity, posted.amount_basis, lines, amount);
    if (existing) {
      const storedKey = dayKey(existing.granularity, existing.amount_basis, existing.lines, existing.takings);
      if (storedKey === incomingKey && numberKey(existing.takings) === numberKey(takings)) {
        const { lines: _lines, ...rest } = existing;
        void _lines;
        results.push({
          branch_id: existing.branch_id,
          business_date: existing.business_date,
          outcome: "unchanged",
          previous: null,
          day: rest,
        });
        continue;
      }
    }
    const day: SalesDay = {
      id: existing?.id ?? nextId("day"),
      branch_id: posted.branch_id,
      business_date: posted.business_date,
      granularity: posted.granularity,
      amount_basis: posted.amount_basis,
      vat_rate: VAT_RATE,
      takings,
      net_sales: net,
      line_count: lines.length,
      layout_id: posted.layout_id,
      source_sha256: posted.source?.sha256 ?? null,
      source_filename: posted.source?.filename ?? null,
      loaded_by: "user:mock-owner",
      loaded_at: nowIso(),
      lines,
    };
    days.set(key, day);
    const { lines: _lines, ...rest } = day;
    void _lines;
    results.push({
      branch_id: day.branch_id,
      business_date: day.business_date,
      outcome: existing ? "replaced" : "loaded",
      previous: existing ? { net_sales: existing.net_sales, line_count: existing.line_count } : null,
      day: rest,
    });
  }
  return respond({ days: results });
}
