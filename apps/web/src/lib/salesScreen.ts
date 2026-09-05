/**
 * M8 WP-84: the pure decisions behind the sales screen - every sentence and
 * every grouping the component renders, kept out of React so vitest pins
 * them. Money stays a verbatim string from the API; the one arithmetic here
 * is the subtotal of a run of days with no papers, done exactly on fils as
 * integers, because a collapsed run still has to say what those days took.
 *
 * The words are the design review's (Docs/M8_DECOMPOSITION.md §4.1, variant
 * B "Answer first", approved 2026-09-04): the conclusion is one sentence in
 * the "of every 100" lens, the table is the evidence, status is a word plus
 * the API's own sentence, and *costed* is never *complete*.
 */

import { formatDate, roundedAed } from "./format";
import { isoAddDays } from "./salesLoad";
import type {
  BranchRow,
  DayFigure,
  InvoiceFigure,
  PeriodQuality,
  SalesBranchesResult,
  SalesCoverageResult,
  SalesPeriod,
} from "./types";

// --- the period picker ------------------------------------------------------

/** Last 28 days (the API's default), last 7 days, or one calendar month -
 * a segmented control, no free date inputs (a custom range is a TODO with
 * the trigger "a pilot asks for a range the picker lacks"). */
export type PeriodChoice =
  | { kind: "last28" }
  | { kind: "last7" }
  | { kind: "month"; year: number; month: number };

export const DEFAULT_CHOICE: PeriodChoice = { kind: "last28" };

export function choiceKey(choice: PeriodChoice): string {
  return choice.kind === "month" ? `month:${choice.year}-${pad(choice.month)}` : choice.kind;
}

const pad = (n: number) => String(n).padStart(2, "0");

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "Aug 2026" */
export function monthLabel(year: number, month: number): string {
  return `${MONTHS[month - 1]} ${year}`;
}

export function choiceLabel(choice: PeriodChoice): string {
  if (choice.kind === "last28") return "Last 28 days";
  if (choice.kind === "last7") return "Last 7 days";
  return monthLabel(choice.year, choice.month);
}

/** The range a choice asks the API for, or null for the API's own default.
 * The 7-day window ends on the tenant's newest loaded day, the same anchor
 * the 28-day default uses (C11.6). With nothing loaded there is nothing to
 * anchor on and every choice falls back to the default read. */
export function periodBounds(
  choice: PeriodChoice,
  salesThrough: string | null,
): { from: string; to: string } | null {
  if (choice.kind === "last28") return null;
  if (choice.kind === "last7") {
    if (salesThrough === null) return null;
    return { from: isoAddDays(salesThrough, -6), to: salesThrough };
  }
  const from = `${choice.year}-${pad(choice.month)}-01`;
  const to = isoAddDays(`${choice.month === 12 ? choice.year + 1 : choice.year}-${pad(choice.month === 12 ? 1 : choice.month + 1)}-01`, -1);
  return { from, to };
}

export interface MonthOption {
  year: number;
  month: number;
  label: string;
}

/** The calendar months the picker offers: the ones the API says hold loaded
 * days (`period.months`, newest first), so a month offered always has sales
 * and the oldest month is reachable however long the history. */
export function monthOptions(period: SalesPeriod): MonthOption[] {
  const options: MonthOption[] = [];
  for (const key of period.months) {
    const year = Number(key.slice(0, 4));
    const month = Number(key.slice(5, 7));
    if (!year || !month || month > 12) continue;
    options.push({ year, month, label: monthLabel(year, month) });
  }
  return options;
}

// --- dates and words --------------------------------------------------------

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/** "Mon 31 Aug" - the weekday from the calendar, the rest by string ops. */
export function weekdayDate(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  if (!year || !month || !day) return iso;
  const weekday = WEEKDAYS[new Date(Date.UTC(year, month - 1, day)).getUTCDay()];
  return `${weekday} ${day} ${MONTHS[month - 1]}`;
}

/** "25-31 Aug", "28 Aug-3 Sep", or "31 Aug" - the API's own window words. */
export function windowWords(from: string, to: string): string {
  const short = (iso: string) => `${Number(iso.slice(8, 10))} ${MONTHS[Number(iso.slice(5, 7)) - 1]}`;
  if (from === to) return short(from);
  if (from.slice(0, 7) === to.slice(0, 7)) return `${Number(from.slice(8, 10))}-${short(to)}`;
  return `${short(from)}-${short(to)}`;
}

/** Whole days between two ISO dates (to - from). */
export function daysBetween(from: string, to: string): number {
  const [fy, fm, fd] = from.split("-").map(Number);
  const [ty, tm, td] = to.split("-").map(Number);
  return Math.round((Date.UTC(ty, tm - 1, td) - Date.UTC(fy, fm - 1, fd)) / 86_400_000);
}

/** "Sales loaded to Mon 31 Aug, 3 days ago." - the freshness fact on every
 * period line. Null when nothing was ever loaded (the empty state's case). */
export function freshnessSentence(period: SalesPeriod, today: string): string | null {
  if (period.sales_through === null) return null;
  const ago = daysBetween(period.sales_through, today);
  const when =
    ago <= 0 ? "today" : ago === 1 ? "yesterday" : `${ago} days ago`;
  return `Sales loaded to ${weekdayDate(period.sales_through)}, ${when}.`;
}

/** "AED 30,120" for a headline figure; a dash when the row has none. */
export function headline(value: string | null): string {
  return value === null ? "-" : roundedAed(value);
}

/** "30.3%" */
export function percent(value: string): string {
  return `${value}%`;
}

/** The sentence's lens: a percentage to the nearest whole dirham of every
 * hundred. The one place a percentage is parsed, and it is never money. */
export function ofEveryHundred(ratioPct: string): number {
  return Math.round(Number(ratioPct));
}

/** "Al Qusais" from "Al Qusais Branch" - the sentence says the place the
 * way the owner does; the table keeps the branch's full name. */
export function shortBranchName(name: string): string {
  const trimmed = name.replace(/\s+branch$/i, "").trim();
  return trimmed === "" ? name : trimmed;
}

function listNames(names: string[]): string {
  if (names.length <= 1) return names[0] ?? "";
  if (names.length === 2) return `${names[0]} and ${names[1]}`;
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

export interface AnswerSentence {
  /** "Look at Al Qusais first" - rendered bold, the colon added by the screen. */
  lead: string;
  /** The rest of the sentence, then the unrankable branches named. */
  rest: string;
}

/**
 * The conclusion above the table, in the design review's words. The top
 * ranked row is the row to look at first, in the "of every 100" lens;
 * branches with sales but no confirmed papers are named as unrankable, so
 * the owner reads why they are not in the sentence before the table says it
 * in a chip. An incomplete top row says so in the same breath. Null when no
 * row has sales in the period (the table's own rows say the rest).
 */
export function answerSentence(result: SalesBranchesResult): AnswerSentence | null {
  const ranked = result.rows.filter((row) => row.ratio_pct !== null);
  // Two reasons a row with sales carries no ratio, and they get two different
  // sentences: no confirmed paper in its window, or net sales that are not
  // positive (a refund-heavy or zero week) - the second must never be told as
  // the first, because its row lists the papers it did confirm.
  const noPapers = result.rows.filter(
    (row) => row.ratio_pct === null && row.net_sales !== null && row.deliveries === 0,
  );
  const notPositive = result.rows.filter(
    (row) => row.ratio_pct === null && row.net_sales !== null && row.deliveries > 0,
  );
  const names = noPapers.map((row) => shortBranchName(row.branch_name));
  const unrankedNoPapers =
    names.length === 0
      ? ""
      : ` ${listNames(names)} ${names.length === 1 ? "has" : "have"} sales loaded and no papers confirmed, so ${
          names.length === 1 ? "it" : "they"
        } cannot be ranked yet.`;
  const zeroNames = notPositive.map((row) => shortBranchName(row.branch_name));
  const unrankedNotPositive =
    zeroNames.length === 0
      ? ""
      : ` ${listNames(zeroNames)}${zeroNames.length === 1 ? "'s" : "'"} net sales are not positive this period, so ${
          zeroNames.length === 1 ? "it is" : "they are"
        } not rated.`;
  const unranked = unrankedNoPapers + unrankedNotPositive;
  const top = ranked[0];
  if (top && top.ratio_pct !== null) {
    const caveat =
      top.quality === "incomplete" ? " Its figure is incomplete - its row says why." : "";
    return {
      lead: `Look at ${shortBranchName(top.branch_name)} first`,
      rest:
        `about AED ${ofEveryHundred(top.ratio_pct)} of every 100 it took went to suppliers ` +
        `this window.${caveat}${unranked}`,
    };
  }
  if (unranked) return { lead: "No branch can be ranked yet", rest: unranked.trim() };
  return null;
}

export const QUALITY_WORD: Record<PeriodQuality, string> = {
  reliable_with_limitations: "Reliable with limitations",
  estimated: "Estimated",
  incomplete: "Incomplete",
  unavailable: "Unavailable",
};

const DELIVERIES_NOTE = / in this window$/;

/** The sentence under the status word: the API's notes, minus the delivery
 * count (the branch cell carries that), capitalised and closed. A reliable
 * row with nothing else to say gets the one sentence that means it. */
export function statusSentence(quality: PeriodQuality, notes: string[]): string {
  const rest = notes.filter((note) => !DELIVERIES_NOTE.test(note));
  if (rest.length === 0) {
    // A word is never left standing alone. The chain total, for one, reads
    // estimated with no note of its own when a branch below it does.
    switch (quality) {
      case "reliable_with_limitations":
        return "Every day loaded, every paper confirmed.";
      case "estimated":
        return "At least one figure behind it is estimated - see the rows.";
      case "incomplete":
        return "Some days or papers are missing - see the rows.";
      case "unavailable":
        return "Nothing to rate.";
    }
  }
  return `${rest.map((note) => note.charAt(0).toUpperCase() + note.slice(1)).join(". ")}.`;
}

/** "25-31 Aug, 7 days · 3 deliveries" under the branch name. */
export function windowLine(row: BranchRow): string {
  const days = `${row.window.days} ${row.window.days === 1 ? "day" : "days"}`;
  const deliveries = `${row.deliveries} ${row.deliveries === 1 ? "delivery" : "deliveries"}`;
  return `${windowWords(row.window.from, row.window.to)}, ${days} · ${deliveries}`;
}

/** The ratio cell's words when there is no ratio to show. */
export function noRatioWords(row: BranchRow): string {
  if (row.net_sales === null) return row.deliveries > 0 ? "No sales loaded" : "Nothing loaded";
  if (row.deliveries === 0) return "No confirmed purchases";
  return "Net sales not positive";
}

/** "AED 5,081.70 = 5,335.79 less VAT 254.09" - the two printed figures the
 * photo shows, beside the paper (P2). A paper that printed no VAT line says
 * so; one that printed no total (it still confirmed) shows what was counted. */
export function exVatWords(figure: InvoiceFigure): string {
  if (figure.total === null) return `AED ${grouped(figure.net_purchase)}, no total printed`;
  if (figure.tax === null) {
    return `AED ${grouped(figure.net_purchase)} = ${grouped(figure.total)}, no VAT printed`;
  }
  return `AED ${grouped(figure.net_purchase)} = ${grouped(figure.total)} less VAT ${grouped(figure.tax)}`;
}

function grouped(value: string): string {
  const [whole, frac = "00"] = value.split(".");
  const sign = whole.startsWith("-") ? "-" : "";
  const digits = sign ? whole.slice(1) : whole;
  return `${sign}${digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",")}.${(frac + "00").slice(0, 2)}`;
}

/** "Al Madina Trading Co. AMT-26-1203" - the paper's own name and number. */
export function paperName(figure: { supplier_name: string | null; invoice_no: string | null }): string {
  const parts = [figure.supplier_name, figure.invoice_no].filter(
    (part): part is string => typeof part === "string" && part !== "",
  );
  return parts.length > 0 ? parts.join(" ") : "Invoice";
}

// --- the drill --------------------------------------------------------------

/** A day with papers stands alone - counted ones, or pending ones placed on
 * it (`pinned`) - and a run of consecutive days with none collapses to one
 * line with its dates, its count and its net sales added up, so a 28-day
 * drill reads as a handful of lines rather than a ledger. */
export type DrillSegment =
  | { kind: "day"; day: DayFigure }
  | { kind: "run"; from: string; to: string; days: number; net_sales: string | null };

export function collapseDays(days: DayFigure[], pinned: Set<string> = new Set()): DrillSegment[] {
  const segments: DrillSegment[] = [];
  let run: { from: string; to: string; days: number; nets: string[] } | null = null;
  const flush = () => {
    if (!run) return;
    segments.push({
      kind: "run",
      from: run.from,
      to: run.to,
      days: run.days,
      net_sales: run.nets.length > 0 ? sumFils(run.nets) : null,
    });
    run = null;
  };
  for (const day of days) {
    if (day.invoices.length > 0 || pinned.has(day.business_date)) {
      flush();
      segments.push({ kind: "day", day });
      continue;
    }
    if (run && isoAddDays(run.to, 1) === day.business_date) {
      run.to = day.business_date;
      run.days += 1;
      if (day.net_sales !== null) run.nets.push(day.net_sales);
    } else {
      flush();
      run = {
        from: day.business_date,
        to: day.business_date,
        days: 1,
        nets: day.net_sales === null ? [] : [day.net_sales],
      };
    }
  }
  flush();
  return segments;
}

/** Exact addition of two-decimal money strings on integer fils. */
export function sumFils(values: string[]): string {
  let total = 0n;
  for (const value of values) {
    const negative = value.startsWith("-");
    const [whole, frac = ""] = value.replace("-", "").split(".");
    const fils = BigInt(whole || "0") * 100n + BigInt((frac + "00").slice(0, 2));
    total += negative ? -fils : fils;
  }
  const negative = total < 0n;
  const digits = (negative ? -total : total).toString().padStart(3, "0");
  return `${negative ? "-" : ""}${digits.slice(0, -2)}.${digits.slice(-2)}`;
}

/** "Mon 25 Aug" for one day, "Wed 26 - Sun 30 Aug" for a run. */
export function segmentWords(segment: DrillSegment): string {
  if (segment.kind === "day") return weekdayDate(segment.day.business_date);
  if (segment.days === 1) return weekdayDate(segment.from);
  return `${weekdayDate(segment.from)} - ${weekdayDate(segment.to)}`;
}

// --- coverage ---------------------------------------------------------------

/** "Costed: 78% of sales value" - or the honest sentence when there is no
 * item-wise value in the window to measure against. */
export function costedSentence(coverage: SalesCoverageResult): string {
  if (coverage.costed_pct === null) return "No item-wise sales in this window";
  return `Costed: ${coverage.costed_pct}% of sales value`;
}

/** The buckets in words, on one line: the estimated points named, then what
 * is not yet costed and why, then what sits beside the figure. */
/** A money or percentage string that is zero however it is written:
 * "0", "0.0", "0.00", "-0.00". */
export function isZero(value: string | null): boolean {
  return value === null || /^-?0+(\.0+)?$/.test(value.trim());
}

export function bucketsLine(coverage: SalesCoverageResult): string {
  const parts: string[] = [];
  if (!isZero(coverage.estimated_points)) {
    parts.push(`${coverage.estimated_points} points of it on estimated plates`);
  }
  if (!isZero(coverage.uncosted.unmapped)) {
    parts.push(`Not yet mapped: ${roundedAed(coverage.uncosted.unmapped)}`);
  }
  if (!isZero(coverage.uncosted.incomplete_plate)) {
    parts.push(`Cannot be costed yet: ${roundedAed(coverage.uncosted.incomplete_plate)}`);
  }
  const beside: string[] = [];
  if (!isZero(coverage.beside.refunds)) {
    beside.push(`refunds ${roundedAed(coverage.beside.refunds.replace("-", ""))}`);
  }
  // Net of VAT, like every figure on this panel: the word is never "takings".
  if (!isZero(coverage.beside.not_menu_items)) {
    beside.push(`non-menu net sales ${roundedAed(coverage.beside.not_menu_items)}`);
  }
  if (beside.length > 0) {
    const joined = beside.length === 2 ? `${beside[0]} and ${beside[1]}` : beside[0];
    parts.push(`${joined.charAt(0).toUpperCase()}${joined.slice(1)} sit outside the figure`);
  }
  return parts.join(" · ");
}

/** "Chicken 65 Dry (estimated plate)" - the plate's quality named beside the
 * menu item a till name is mapped to. */
export function mappedWords(item: { menu_item_name: string; plate_quality: string }): string {
  if (item.plate_quality === "incomplete") return `${item.menu_item_name} - cannot be costed yet`;
  if (item.plate_quality === "estimated") return `${item.menu_item_name} - estimated plate`;
  return item.menu_item_name;
}

export { formatDate };
