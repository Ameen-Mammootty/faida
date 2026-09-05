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

import { ZERO, add, cmp, dec, divTo, fmt, mul, sub, sumStrings, type Dec } from "./decimal";
import { MOCK_BRANCHES } from "./fixtures";
import { mockListMenuItems } from "./menu";
import { mockGetInvoice, mockListInvoices } from "./store";
import { ApiError } from "../errors";
import { dayKey, headerKey, isoAddDays, isoToday, nameKey, numberKey } from "../salesLoad";
import type {
  Branch,
  BranchAlias,
  BranchRow,
  CoverageItem,
  CoverageMappedItem,
  CoverageProposal,
  CoverageQueueItem,
  DayFigure,
  ExcludedPaper,
  InvoiceDetail,
  InvoiceFigure,
  PendingPaper,
  PeriodQuality,
  SalesBranchesResult,
  SalesCoverageResult,
  SalesDay,
  SalesDayResult,
  SalesDaysInput,
  SalesDaysResult,
  SalesFileResult,
  SalesLayout,
  SalesLayoutInput,
  SalesLine,
  SalesPeriod,
  SalesTotal,
  SalesUnassigned,
  TillItem,
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
 * one, by the normalised name otherwise (C11.7). The mapping state the three
 * doors below move lives on the same record (WP-82). */
interface TillItemRecord {
  id: string;
  name: string;
  code: string | null;
  menu_item_id: string | null;
  excluded_at: string | null;
}

const tillItems = new Map<string, TillItemRecord>();

function tillItemFor(name: string, code: string | null): string {
  const key = code !== null && code !== "" ? `code:${code}` : `name:${nameKey(name)}`;
  let item = tillItems.get(key);
  if (!item) {
    item = { id: nextId("till"), name, code: code || null, menu_item_id: null, excluded_at: null };
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

// --- the reads and the till-name doors (M8 WP-81/82/84) ---------------------
//
// The sales screen has to run with no backend at all, so this reproduces the
// two reads' *decisions* in `ratio.py`'s own words: the window clipped to the
// branch's loaded range, the four labels with their precedence and the
// sentences that made them, purchases as the printed total less the printed
// VAT by the paper's printed date, pending papers placed by arrival, the "No
// branch" group and the chain total that reconciles the table, and coverage
// over the positive net value with *costed* never *complete*. It reads the
// days the mock door loaded above and the mock store's own invoices - their
// statuses live, so a paper confirmed on the review screen moves the ratio on
// the next read, exactly as the stage's KAS-5 does. The proposer is the API's
// whole-string ratio over normalised names at the same 0.72 bar with the same
// size-word rule. Nothing here is the product's number: the real figure is
// derived by the API from Postgres on every read.

const DEFAULT_PERIOD_DAYS = 28;
const MAX_PERIOD_DAYS = 92;
const TENANT_CURRENCY = "AED";
const PENDING_STATUSES = new Set<string>(["awaiting_confirm", "needs_review"]);
/** provenance.ASSERTED_ORIGINS - every origin but `extracted` and `repaired`:
 * a figure a person supplied, not one a camera saw and the arithmetic checked. */
const ASSERTED_ORIGINS = new Set<string>([
  "corrected_chat",
  "corrected_screen",
  "manual",
  "reconstructed",
]);

/** Precedence, worst first (C9 amended). */
const QUALITY_RANK: Record<PeriodQuality, number> = {
  unavailable: 0,
  incomplete: 1,
  estimated: 2,
  reliable_with_limitations: 3,
};

const MONTH_WORDS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function daysInclusive(from: string, to: string): number {
  const [fy, fm, fd] = from.split("-").map(Number);
  const [ty, tm, td] = to.split("-").map(Number);
  return Math.round((Date.UTC(ty, tm - 1, td) - Date.UTC(fy, fm - 1, fd)) / 86_400_000) + 1;
}

function shortDate(iso: string): string {
  const [, month, day] = iso.split("-");
  return `${Number(day)} ${MONTH_WORDS[Number(month) - 1]}`;
}

/** "25-31 Aug", or "28 Aug-3 Sep" across a month end, or "31 Aug" alone. */
function windowWords(from: string, to: string): string {
  if (from === to) return shortDate(from);
  if (from.slice(0, 7) === to.slice(0, 7)) return `${Number(from.slice(8))}-${shortDate(to)}`;
  return `${shortDate(from)}-${shortDate(to)}`;
}

function plural(count: number, singular: string, pluralWord?: string): string {
  return `${count} ${count === 1 ? singular : (pluralWord ?? `${singular}s`)}`;
}

const toDec = (value: string): Dec => dec(value) ?? ZERO;

/** Quantized to a fil, the way every stored money figure is. */
const fils = (value: Dec): string => fmt(divTo(value, toDec("1"), 2));

/** `purchases / net_sales` to a tenth of a percent, half up; withheld (null,
 * never 0%) when net sales are absent or not positive (C11.6). */
function ratioPct(purchases: string, netSales: string | null): string | null {
  if (netSales === null) return null;
  const net = toDec(netSales);
  if (cmp(net, ZERO) <= 0) return null;
  return fmt(divTo(mul(toDec(purchases), toDec("100")), net, 1));
}

function newestLoadedDay(): string | null {
  let newest: string | null = null;
  for (const day of days.values()) {
    if (newest === null || day.business_date > newest) newest = day.business_date;
  }
  return newest;
}

/** The calendar months holding a loaded day, newest first, as "YYYY-MM" -
 * `db.sales_months`, the picker's choices. */
function monthsLoaded(): string[] {
  const months = new Set<string>();
  for (const day of days.values()) months.add(day.business_date.slice(0, 7));
  return [...months].sort().reverse();
}

/** The period a read covers: the caller's range, or 28 days ending on the
 * newest loaded day (today when nothing is loaded) - `sales.py`'s `_period`
 * with its three refusals, word for word. */
function periodFor(from?: string, to?: string): SalesPeriod {
  const newest = newestLoadedDay();
  const months = monthsLoaded();
  if ((from === undefined) !== (to === undefined)) {
    throw new ApiError(422, "send both 'from' and 'to', or neither");
  }
  if (from === undefined || to === undefined) {
    const end = newest ?? isoToday();
    return {
      from: isoAddDays(end, -(DEFAULT_PERIOD_DAYS - 1)),
      to: end,
      days: DEFAULT_PERIOD_DAYS,
      default: true,
      sales_through: newest,
      months,
    };
  }
  if (from > to) throw new ApiError(422, "'from' is after 'to'");
  const count = daysInclusive(from, to);
  if (count > MAX_PERIOD_DAYS) {
    throw new ApiError(
      422,
      `${count} days is longer than one read covers: at most ${MAX_PERIOD_DAYS}`,
    );
  }
  return { from, to, days: count, default: false, sales_through: newest, months };
}

// --- papers -----------------------------------------------------------------

/** One paper as `db.list_period_invoices` returns it: `purchased_on` is the
 * costing rule (printed date, confirm time as the tie-breaker) and
 * `placed_on` is where a pending paper sits (printed date, or arrival). */
interface Paper {
  invoice_id: string;
  branch_id: string | null;
  status: string;
  currency: string;
  total: string | null;
  tax: string | null;
  invoice_date: string | null;
  purchased_on: string;
  placed_on: string;
  supplier_name: string | null;
  invoice_no: string | null;
  asserted: boolean;
}

function paperOf(detail: InvoiceDetail): Paper {
  const provenance = detail.provenance ?? {};
  return {
    invoice_id: detail.id,
    branch_id: detail.branch_id,
    status: detail.status,
    currency: detail.currency,
    total: detail.total,
    tax: detail.tax,
    invoice_date: detail.invoice_date,
    purchased_on: detail.invoice_date ?? (detail.confirmed_at ?? detail.created_at).slice(0, 10),
    placed_on: detail.invoice_date ?? detail.created_at.slice(0, 10),
    supplier_name: detail.supplier_name,
    invoice_no: detail.invoice_no,
    asserted: ["total", "tax"].some((field) =>
      ASSERTED_ORIGINS.has(provenance[field]?.origin ?? ""),
    ),
  };
}

/** The papers a period reads: confirmed ones by `purchased_on`, pending ones
 * by `placed_on`; dismissed and draft papers are nobody's purchases. */
async function periodPapers(period: SalesPeriod): Promise<Paper[]> {
  const rows = await mockListInvoices();
  const wanted = rows.filter(
    (row) => row.status === "confirmed" || PENDING_STATUSES.has(row.status),
  );
  const details = await Promise.all(wanted.map((row) => mockGetInvoice(row.id)));
  return details
    .map(paperOf)
    .filter((paper) => {
      const sits = paper.status === "confirmed" ? paper.purchased_on : paper.placed_on;
      return sits >= period.from && sits <= period.to;
    })
    .sort((a, b) => a.placed_on.localeCompare(b.placed_on) || a.invoice_id.localeCompare(b.invoice_id));
}

/** C11.5: the printed total less the printed VAT - the whole paper. */
function netPurchase(paper: Paper): string {
  return fils(sub(toDec(paper.total ?? "0"), toDec(paper.tax ?? "0")));
}

function figureOf(paper: Paper): InvoiceFigure {
  return {
    invoice_id: paper.invoice_id,
    supplier_name: paper.supplier_name,
    invoice_no: paper.invoice_no,
    purchased_on: paper.purchased_on,
    net_purchase: netPurchase(paper),
    // The two printed figures pass through as the API's `_dec` does: null
    // when the paper printed none. Only the net figure treats null as zero.
    total: paper.total === null ? null : fils(toDec(paper.total)),
    tax: paper.tax === null ? null : fils(toDec(paper.tax)),
    quality: paper.asserted ? "estimated" : "reliable_with_limitations",
  };
}

const within = (day: string | null, from: string, to: string): boolean =>
  day !== null && day >= from && day <= to;

function pendingSentences(pending: Paper[]): string[] {
  const counts = new Map<string, number>();
  for (const paper of pending) {
    const key = `${paper.status}|${paper.invoice_date === null ? "undated" : "dated"}`;
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const words: Record<string, string> = {
    awaiting_confirm: "awaiting confirm",
    needs_review: "held for review",
  };
  return [...counts.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, count]) => {
      const [status, dated] = key.split("|");
      const noun = dated === "undated" ? "undated invoice" : "invoice";
      return `${plural(count, noun)} ${words[status] ?? status}`;
    });
}

function currencySentences(excluded: Paper[]): string[] {
  const counts = new Map<string, number>();
  for (const paper of excluded) counts.set(paper.currency, (counts.get(paper.currency) ?? 0) + 1);
  return [...counts.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([currency, count]) => `${plural(count, "invoice")} in ${currency} not counted`);
}

// --- the branch row ---------------------------------------------------------

/** `ratio.period_row`, decision for decision. */
function periodRow(
  branch: Branch,
  period: SalesPeriod,
  allDays: SalesDay[],
  papers: Paper[],
  latestSalesDay: string | null,
): BranchRow {
  const ownDays = allDays
    .filter(
      (day) =>
        day.branch_id === branch.id &&
        day.business_date >= period.from &&
        day.business_date <= period.to,
    )
    .sort((a, b) => a.business_date.localeCompare(b.business_date));
  const own = papers.filter((paper) => paper.branch_id === branch.id);

  const from = ownDays.length > 0 ? ownDays[0].business_date : period.from;
  const to = ownDays.length > 0 ? ownDays[ownDays.length - 1].business_date : period.to;
  const windowDays = daysInclusive(from, to);

  const byPurchase = (a: Paper, b: Paper) =>
    a.purchased_on.localeCompare(b.purchased_on) || a.invoice_id.localeCompare(b.invoice_id);
  const counted = own
    .filter(
      (p) => p.status === "confirmed" && p.currency === TENANT_CURRENCY && within(p.purchased_on, from, to),
    )
    .sort(byPurchase);
  const excluded = own
    .filter(
      (p) => p.status === "confirmed" && p.currency !== TENANT_CURRENCY && within(p.purchased_on, from, to),
    )
    .sort(byPurchase);
  const pending = own
    .filter((p) => PENDING_STATUSES.has(p.status) && within(p.placed_on, from, to))
    .sort((a, b) => a.placed_on.localeCompare(b.placed_on) || a.invoice_id.localeCompare(b.invoice_id));

  const netSales = ownDays.length > 0 ? sumStrings(ownDays.map((d) => d.net_sales)) : null;
  const takings = ownDays.length > 0 ? sumStrings(ownDays.map((d) => d.takings)) : null;
  const purchases = sumStrings(counted.map(netPurchase));
  const loadedDates = new Set(ownDays.map((d) => d.business_date));
  const daysMissing = ownDays.length > 0 ? windowDays - loadedDates.size : 0;

  const notes: string[] = [];
  let quality: PeriodQuality;
  if (ownDays.length === 0 && counted.length === 0) {
    quality = "unavailable";
    notes.push(`no sales loaded and no confirmed purchases ${windowWords(from, to)}`);
  } else {
    let incomplete = false;
    if (daysMissing > 0) {
      incomplete = true;
      notes.push(`${daysMissing} of ${windowDays} days ${daysMissing === 1 ? "has" : "have"} no sales`);
    }
    if (counted.length > 0 && ownDays.length === 0) {
      incomplete = true;
      notes.push(`no sales loaded ${windowWords(from, to)}`);
    }
    if (ownDays.length > 0 && counted.length === 0) {
      incomplete = true;
      notes.push(`no confirmed purchases ${windowWords(from, to)}`);
    }
    if (ownDays.length > 0 && netSales !== null && cmp(toDec(netSales), ZERO) <= 0) {
      incomplete = true;
      notes.push("net sales are not positive this period");
    }
    const estimated = pending.length > 0 || excluded.length > 0 || counted.some((p) => p.asserted);
    quality = incomplete ? "incomplete" : estimated ? "estimated" : "reliable_with_limitations";
  }
  notes.push(...pendingSentences(pending), ...currencySentences(excluded));
  const assertedCount = counted.filter((p) => p.asserted).length;
  if (assertedCount > 0) {
    notes.push(`${plural(assertedCount, "invoice")} with a total or VAT entered by hand`);
  }
  if (counted.length > 0) notes.push(`${plural(counted.length, "delivery", "deliveries")} in this window`);

  const ratio = ownDays.length > 0 && counted.length > 0 ? ratioPct(purchases, netSales) : null;

  const byDate = new Map<string, Paper[]>();
  for (const paper of counted) byDate.set(paper.purchased_on, [...(byDate.get(paper.purchased_on) ?? []), paper]);
  const dayByDate = new Map(ownDays.map((d) => [d.business_date, d] as const));
  const dates = [...new Set([...dayByDate.keys(), ...byDate.keys()])].sort();
  const figures: DayFigure[] = dates.map((date) => {
    const day = dayByDate.get(date);
    const dated = byDate.get(date) ?? [];
    return {
      business_date: date,
      net_sales: day ? day.net_sales : null,
      granularity: day ? day.granularity : null,
      purchases: sumStrings(dated.map(netPurchase)),
      invoices: dated.map(figureOf),
    };
  });

  return {
    branch_id: branch.id,
    branch_name: branch.name,
    window: { from, to, days: windowDays },
    net_sales: netSales,
    takings,
    purchases,
    ratio_pct: ratio,
    quality,
    notes,
    days_loaded: loadedDates.size,
    days_missing: daysMissing,
    deliveries: counted.length,
    sales_through: ownDays.length > 0 ? ownDays[ownDays.length - 1].business_date : latestSalesDay,
    last_purchase_on: counted.length > 0 ? counted[counted.length - 1].purchased_on : null,
    days: figures,
    pending: pending.map(
      (p): PendingPaper => ({
        invoice_id: p.invoice_id,
        supplier_name: p.supplier_name,
        invoice_no: p.invoice_no,
        status: p.status as PendingPaper["status"],
        placed_on: p.placed_on,
        undated: p.invoice_date === null,
      }),
    ),
    excluded: excluded.map(
      (p): ExcludedPaper => ({
        invoice_id: p.invoice_id,
        supplier_name: p.supplier_name,
        invoice_no: p.invoice_no,
        currency: p.currency,
        total: p.total === null ? null : fils(toDec(p.total)),
      }),
    ),
  };
}

/** Confirmed papers with no branch, in the tenant's currency: counted in no
 * row, never dropped. */
function unassignedGroup(papers: Paper[], period: SalesPeriod): SalesUnassigned {
  const group = papers
    .filter(
      (p) =>
        p.branch_id === null &&
        p.status === "confirmed" &&
        p.currency === TENANT_CURRENCY &&
        within(p.purchased_on, period.from, period.to),
    )
    .sort((a, b) => a.purchased_on.localeCompare(b.purchased_on) || a.invoice_id.localeCompare(b.invoice_id));
  return {
    count: group.length,
    purchases: sumStrings(group.map(netPurchase)),
    invoices: group.map(figureOf),
  };
}

/** Highest ratio first, unrated rows last, ties by branch name. */
function rank(rows: BranchRow[]): BranchRow[] {
  return [...rows].sort((a, b) => {
    if ((a.ratio_pct === null) !== (b.ratio_pct === null)) return a.ratio_pct === null ? 1 : -1;
    if (a.ratio_pct !== null && b.ratio_pct !== null && a.ratio_pct !== b.ratio_pct) {
      return cmp(toDec(b.ratio_pct), toDec(a.ratio_pct));
    }
    return a.branch_name.localeCompare(b.branch_name) || a.branch_id.localeCompare(b.branch_id);
  });
}

/** The row that reconciles the table: every branch plus the unassigned group. */
function chainTotal(rows: BranchRow[], unassigned: SalesUnassigned): SalesTotal {
  const netSales = sumStrings(rows.map((r) => r.net_sales ?? "0"));
  const purchases = sumStrings([...rows.map((r) => r.purchases), unassigned.purchases]);
  const withSales = rows.filter((r) => r.net_sales !== null);
  const ratio = withSales.length > 0 ? ratioPct(purchases, netSales) : null;
  let quality: PeriodQuality;
  if (rows.length === 0 || rows.every((r) => r.quality === "unavailable")) {
    quality = "unavailable";
  } else if (rows.some((r) => r.quality === "unavailable" || r.quality === "incomplete")) {
    quality = "incomplete";
  } else {
    quality = rows.reduce<PeriodQuality>(
      (worst, r) => (QUALITY_RANK[r.quality] < QUALITY_RANK[worst] ? r.quality : worst),
      "reliable_with_limitations",
    );
  }
  const notes: string[] = [];
  const unavailable = rows.filter((r) => r.quality === "unavailable").length;
  if (unavailable > 0) notes.push(`${unavailable} of ${rows.length} branches with nothing loaded`);
  const incomplete = rows.filter((r) => r.quality === "incomplete").length;
  if (incomplete > 0) notes.push(`${incomplete} of ${rows.length} branches incomplete`);
  if (unassigned.count > 0) {
    notes.push(`${plural(unassigned.count, "invoice")} on no branch, counted in the total`);
  }
  if (withSales.length > 0 && cmp(toDec(netSales), ZERO) <= 0) {
    notes.push("net sales are not positive this period");
  }
  return { net_sales: netSales, purchases, ratio_pct: ratio, quality, notes };
}

/** GET /api/sales/branches?from&to */
export async function mockGetSalesBranches(from?: string, to?: string): Promise<SalesBranchesResult> {
  const period = periodFor(from, to);
  const papers = await periodPapers(period);
  const allDays = [...days.values()];
  const newestByBranch = new Map<string, string>();
  for (const day of allDays) {
    const known = newestByBranch.get(day.branch_id);
    if (known === undefined || day.business_date > known) newestByBranch.set(day.branch_id, day.business_date);
  }
  const rows = rank(
    branches.map((branch) =>
      periodRow(branch, period, allDays, papers, newestByBranch.get(branch.id) ?? null),
    ),
  );
  const unassigned = unassignedGroup(papers, period);
  return respond({ period, rows, unassigned, total: chainTotal(rows, unassigned) });
}

// --- coverage by sales value ------------------------------------------------

/** matching.normalize: casefold, punctuation to spaces, whitespace collapsed,
 * digits and units kept. */
function normalizeName(name: string): string {
  return name
    .toLowerCase()
    .replace(/[.\-_/()[\],;:'"#&+*]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** difflib's 2M/T over two strings, the matched characters counted along
 * the longest common subsequence. */
function lcsRatio(na: string, nb: string): number {
  const previous = new Array<number>(nb.length + 1).fill(0);
  for (let i = 1; i <= na.length; i += 1) {
    let diagonal = 0;
    for (let j = 1; j <= nb.length; j += 1) {
      const above = previous[j];
      previous[j] = na[i - 1] === nb[j - 1] ? diagonal + 1 : Math.max(above, previous[j - 1]);
      diagonal = above;
    }
  }
  return (2 * previous[nb.length]) / (na.length + nb.length);
}

/** `matching._ratio`: the better of the whole-string ratio and the
 * token-sorted ratio over normalised names, so word order never sinks a
 * match ("SHAWARMA CHICKEN" is "Chicken Shawarma"). */
function similarity(a: string, b: string): number {
  const na = normalizeName(a);
  const nb = normalizeName(b);
  if (!na || !nb) return 0;
  if (na === nb) return 1;
  const sortedA = na.split(" ").sort().join(" ");
  const sortedB = nb.split(" ").sort().join(" ");
  return Math.max(lcsRatio(na, nb), lcsRatio(sortedA, sortedB));
}

const MENU_ITEM_PROPOSAL_THRESHOLD = 0.72;
const MAX_MENU_ITEM_PROPOSALS = 3;

/** Words that say how big or how served, never what (matching._SIZE_WORDS). */
const SIZE_WORDS = new Set(
  "small medium large sml sm med md lrg lg xl xs regular reg mini jumbo cup flask slice piece pc pcs half full pot glass mug bottle can".split(
    " ",
  ),
);
const PACK_RE = /\b\d+(?:\.\d+)?\s?(?:kg|g|gm|gms|l|ltr|ml|oz|lb|lbs|pc|pcs|x)\b/g;

function dishWords(name: string): string[] {
  return normalizeName(name)
    .replace(PACK_RE, " ")
    .split(" ")
    .filter((word) => word !== "" && !SIZE_WORDS.has(word));
}

/** `matching.propose_menu_items`: pack-aware, archived items never offered,
 * a name of nothing but size words proposes nothing. Proposes; never
 * decides - the keystroke is the door below. */
function proposeMenuItems(
  items: { id: string; name: string; archived_at: string | null }[],
  tillName: string,
): CoverageProposal[] {
  if (dishWords(tillName).length === 0) return [];
  return items
    .filter((item) => item.archived_at === null)
    .map((item) => ({ item, score: similarity(tillName, item.name) }))
    .filter(({ score }) => score >= MENU_ITEM_PROPOSAL_THRESHOLD)
    .sort(
      (a, b) => b.score - a.score || normalizeName(a.item.name).localeCompare(normalizeName(b.item.name)),
    )
    .slice(0, MAX_MENU_ITEM_PROPOSALS)
    .map(({ item, score }) => ({ menu_item_id: item.id, name: item.name, score: score.toFixed(2) }));
}

/** `db.list_period_sales_lines`: every till item with its positive net value
 * and its refund value over the period's days, apart. Every till item is a
 * row, so a name the period never sold shows with a value of 0. */
function periodValues(period: SalesPeriod) {
  const positive = new Map<string, Dec>();
  const refund = new Map<string, Dec>();
  for (const day of days.values()) {
    if (day.business_date < period.from || day.business_date > period.to) continue;
    for (const line of day.lines) {
      const net = toDec(line.net_amount);
      const side = cmp(net, ZERO) > 0 ? positive : cmp(net, ZERO) < 0 ? refund : null;
      if (side) side.set(line.till_item_id, add(side.get(line.till_item_id) ?? ZERO, net));
    }
  }
  return [...tillItems.values()]
    .map((item) => ({
      item,
      positive: fils(positive.get(item.id) ?? ZERO),
      refund: fils(refund.get(item.id) ?? ZERO),
    }))
    .sort(
      (a, b) =>
        cmp(toDec(b.positive), toDec(a.positive)) ||
        a.item.name.localeCompare(b.item.name) ||
        a.item.id.localeCompare(b.item.id),
    );
}

/** GET /api/sales/coverage?from&to - `ratio.coverage`, decision for decision. */
export async function mockGetSalesCoverage(from?: string, to?: string): Promise<SalesCoverageResult> {
  const period = periodFor(from, to);
  const menu = await mockListMenuItems();
  const plates = new Map(menu.map((item) => [item.id, item] as const));
  let salesValue = ZERO;
  let costedValue = ZERO;
  let estimatedValue = ZERO;
  let incompleteValue = ZERO;
  let unmappedValue = ZERO;
  let refunds = ZERO;
  let notMenu = ZERO;
  const queue: CoverageQueueItem[] = [];
  const mapped: CoverageMappedItem[] = [];
  const excluded: CoverageItem[] = [];
  const live = menu.filter((item) => item.archived_at === null);

  for (const { item, positive, refund } of periodValues(period)) {
    refunds = add(refunds, toDec(refund));
    const entry: CoverageItem = { till_item_id: item.id, name: item.name, code: item.code, value: positive };
    if (item.excluded_at !== null) {
      notMenu = add(notMenu, toDec(positive));
      excluded.push(entry);
      continue;
    }
    salesValue = add(salesValue, toDec(positive));
    const plate = item.menu_item_id === null ? undefined : plates.get(item.menu_item_id);
    if (!plate) {
      unmappedValue = add(unmappedValue, toDec(positive));
      queue.push({ ...entry, proposals: proposeMenuItems(live, item.name) });
      continue;
    }
    mapped.push({
      ...entry,
      menu_item_id: plate.id,
      menu_item_name: plate.name,
      plate_quality: plate.plate.quality,
    });
    if (plate.plate.quality === "incomplete") {
      incompleteValue = add(incompleteValue, toDec(positive));
    } else {
      costedValue = add(costedValue, toDec(positive));
      if (plate.plate.quality === "estimated") estimatedValue = add(estimatedValue, toDec(positive));
    }
  }

  const pct = (part: Dec): string | null =>
    cmp(salesValue, ZERO) <= 0 ? null : fmt(divTo(mul(part, toDec("100")), salesValue, 1));
  return respond({
    period,
    sales_value: fils(salesValue),
    costed_value: fils(costedValue),
    costed_pct: pct(costedValue),
    estimated_points: pct(estimatedValue),
    uncosted: { incomplete_plate: fils(incompleteValue), unmapped: fils(unmappedValue) },
    beside: { refunds: fils(refunds), not_menu_items: fils(notMenu) },
    queue,
    mapped,
    excluded,
  });
}

// --- the three doors (WP-82) --------------------------------------------------

function tillItemById(id: string): TillItemRecord {
  const item = [...tillItems.values()].find((row) => row.id === id);
  if (!item) throw new ApiError(404, "till item not found");
  return item;
}

async function tillItemJson(item: TillItemRecord): Promise<TillItem> {
  const menu = item.menu_item_id === null ? null : (await mockListMenuItems()).find((row) => row.id === item.menu_item_id);
  return {
    id: item.id,
    name: item.name,
    code: item.code,
    menu_item_id: item.menu_item_id,
    menu_item_name: menu?.name ?? null,
    excluded_at: item.excluded_at,
  };
}

/** POST /api/till-items/{id}/menu-item: approve the mapping, or move the
 * name to another menu item. An archived item is 409 with the API's
 * sentence; mapping clears a "not a menu item" mark, as the door does. */
export async function mockMapTillItem(tillItemId: string, menuItemId: string): Promise<TillItem> {
  const item = tillItemById(tillItemId);
  const menuItem = (await mockListMenuItems()).find((row) => row.id === menuItemId);
  if (!menuItem) throw new ApiError(404, "menu item not found");
  if (menuItem.archived_at !== null) {
    throw new ApiError(
      409,
      `'${menuItem.name}' is archived: unarchive it on the menu first, or pick a live item`,
    );
  }
  item.menu_item_id = menuItem.id;
  item.excluded_at = null;
  return respond(await tillItemJson(item));
}

/** DELETE /api/till-items/{id}/menu-item: the reverse gear. */
export async function mockUnmapTillItem(tillItemId: string): Promise<TillItem> {
  const item = tillItemById(tillItemId);
  if (item.menu_item_id === null) {
    throw new ApiError(409, `'${item.name}' is not mapped to a menu item`);
  }
  item.menu_item_id = null;
  return respond(await tillItemJson(item));
}

/** POST /api/till-items/{id}/exclude: not a menu item - it stays in net
 * sales and leaves the queue. A mapped name is 409: unmap it first. */
export async function mockExcludeTillItem(tillItemId: string): Promise<TillItem> {
  const item = tillItemById(tillItemId);
  if (item.menu_item_id !== null) {
    const menuItem = (await mockListMenuItems()).find((row) => row.id === item.menu_item_id);
    throw new ApiError(
      409,
      `'${item.name}' is mapped to ${menuItem?.name ?? "a menu item"}: unmap it first if it is not a menu item`,
    );
  }
  item.excluded_at = nowIso();
  return respond(await tillItemJson(item));
}
