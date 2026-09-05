/**
 * M9 WP-93: the pure decisions behind the owner dashboard - every choice the
 * component renders, kept out of React so vitest pins them (there is no
 * component-rendering test capability, `vitest.config.ts`, so whatever the
 * component decided for itself would be untested by construction).
 *
 * The line this module sits on is C13.5's: the API composes every sentence
 * that states a fact or a number and owns every ordering; this module frames
 * and joins those sentences and owns only the words about the screen itself -
 * a control's label, an empty state, a heading, a link. No percentage is ever
 * divided here, no list re-ranked, no money computed. Money stays a verbatim
 * string from the API and is only ever rounded for a headline by `roundedAed`,
 * string operations only.
 *
 * The words are the design review's (Docs/M9_DECOMPOSITION.md §4.1, Variant A
 * "Branch first", approved by the founder 2026-09-05).
 */

import { formatDate, points, quantity, roundedAed } from "./format";
import {
  QUALITY_WORD,
  daysBetween,
  shortBranchName,
  statusSentence,
  windowWords,
} from "./salesScreen";
import type {
  Branch,
  DashboardItemRow,
  DashboardItems,
  DashboardResult,
  DashboardScope,
  DashboardSignal,
  ItemComponent,
  LeagueRow,
  PeriodQuality,
} from "./types";

// The period picker is `/sales`' segmented control, unchanged: the choices,
// their keys and labels, the range a choice asks the API for and the months
// the API offers all come from the sales screen's own module.
export {
  DEFAULT_CHOICE,
  QUALITY_WORD,
  choiceKey,
  choiceLabel,
  monthOptions,
  percent,
  periodBounds,
  shortBranchName,
  statusSentence,
  windowWords,
  type PeriodChoice,
} from "./salesScreen";
export { points };

// --- which screen -------------------------------------------------------------

/** The one fact the first-run state is decided on: nothing was ever loaded. */
export function isFirstRun(result: DashboardResult): boolean {
  return result.period.sales_through === null;
}

export interface FirstRun {
  heading: string;
  body: string;
  /** What is already true, from the same read: the menu's costed count. */
  menuSentence: string;
  primary: { href: string; label: string };
  secondary: { href: string; label: string };
}

/** The first-run paragraph (design review): what the screen will do once a
 * week is loaded, what is already true, and the two actions that change the
 * state. A menu with no sales and sales with no menu each get their own
 * second sentence. */
export function firstRun(result: DashboardResult): FirstRun {
  const { items, costed } = result.menu;
  let menuSentence: string;
  if (items === 0) {
    menuSentence = "No menu is loaded yet, so nothing can be costed until one is.";
  } else if (costed === items) {
    menuSentence = `Your menu is costed: every one of its ${items} items has a price for every ingredient.`;
  } else {
    menuSentence = `Your menu is costed: ${costed} of ${items} items have a price for every ingredient.`;
  }
  return {
    heading: "No sales loaded yet.",
    body:
      "Load a week of the till's export and this screen will name the branch and the dish to " +
      "look at first, with every number one click from the paper it came from.",
    menuSentence,
    primary: { href: "/sales/load", label: "Load sales from a CSV" },
    secondary:
      items === 0
        ? { href: "/menu/load", label: "Load the menu from a spreadsheet" }
        : { href: "/menu", label: "See the menu's margins" },
  };
}

/** Sales loaded, no menu at all: the league shows net sales and the ratio,
 * and the contribution column says why it is empty. */
export function noMenuSentence(result: DashboardResult): string | null {
  if (isFirstRun(result) || result.menu.items > 0) return null;
  return "No menu is loaded, so nothing can be costed yet.";
}

/** Under a branch filter, a branch with nothing loaded in the window. */
export function filteredEmpty(result: DashboardResult): string | null {
  if (result.scope.branch_id === null) return null;
  const [row] = result.league;
  if (row === undefined || row.net_sales === null) {
    return "This branch has no sales in this window.";
  }
  return null;
}

// --- the freshness line -------------------------------------------------------

export interface FreshnessLine {
  sentence: string;
  /** Past seven days the API says estimated, and the line carries the word. */
  estimated: boolean;
  /** "AED 9,856 taken that day across 3 branches", or that branch's own day. */
  takings: string | null;
  papers: { label: string; href: string } | null;
}

/** The invoice list, filtered to the papers held for review - and to the
 * branch in view, so a branch link shows that branch's papers (P7). */
export function approvalsHref(scope: DashboardScope): string {
  const params = new URLSearchParams({ status: "needs_review" });
  if (scope.branch_id !== null) params.set("branch_id", scope.branch_id);
  return `/invoices?${params.toString()}`;
}

export function freshnessLine(result: DashboardResult): FreshnessLine | null {
  const { freshness, latest_day: day, approvals, scope } = result;
  if (freshness.sentence === null) return null;
  let takings: string | null = null;
  if (day !== null) {
    if (scope.branch_id === null) {
      const n = day.branches.length;
      takings = `${roundedAed(day.net_sales)} taken that day across ${n} ${n === 1 ? "branch" : "branches"}`;
    } else {
      const own = day.branches.find((b) => b.branch_id === scope.branch_id);
      takings = own
        ? `${roundedAed(own.net_sales)} taken that day at ${shortBranchName(own.branch_name)}`
        : null;
    }
  }
  const count = approvals.count;
  return {
    sentence: freshness.sentence,
    estimated: freshness.quality === "estimated",
    takings,
    papers:
      count === 0
        ? null
        : {
            label: `${count} ${count === 1 ? "paper" : "papers"} waiting for you`,
            href: approvalsHref(scope),
          },
  };
}

// --- the answer ---------------------------------------------------------------

export const ANSWER_EMPTY =
  "Load a week of sales and this will name the branch and the item to look at.";
export const ANSWER_NO_MENU =
  "No menu is loaded, so nothing can be costed yet. Load it and this will name the branch " +
  "and the item to look at.";

export interface AnswerLines {
  /** The API's own sentences; either may be null when that side cannot be answered. */
  branch: string | null;
  item: string | null;
  /** The screen's own sentence, only when neither side can be answered. */
  empty: string | null;
}

export function answerLines(result: DashboardResult): AnswerLines {
  const { branch, item } = result.answer;
  if (branch !== null || item !== null) return { branch, item, empty: null };
  return { branch, item, empty: noMenuSentence(result) === null ? ANSWER_EMPTY : ANSWER_NO_MENU };
}

/** "Estimated: 1 invoice awaiting confirm · 2 of 7 days have no sales" under
 * the answer - the quality word and the API's notes, only when the word is
 * not reliable. */
export function answerCaveat(result: DashboardResult): string | null {
  const { quality, notes, branch, item } = result.answer;
  if (branch === null && item === null) return null;
  if (quality === "reliable_with_limitations") return null;
  const word = QUALITY_WORD[quality];
  return notes.length === 0 ? word : `${word}: ${notes.join(" · ")}`;
}

// --- the league ---------------------------------------------------------------

/** "25-31 Aug, 7 days · 3 deliveries" under the branch name. */
export function leagueLine(row: LeagueRow): string {
  const days = `${row.window.days} ${row.window.days === 1 ? "day" : "days"}`;
  const deliveries = `${row.deliveries} ${row.deliveries === 1 ? "delivery" : "deliveries"}`;
  return `${windowWords(row.window.from, row.window.to)}, ${days} · ${deliveries}`;
}

/** The ratio cell's words when there is no ratio to show - `/sales`' own. */
export function noRatioWords(row: { net_sales: string | null; deliveries: number }): string {
  if (row.net_sales === null) return row.deliveries > 0 ? "No sales loaded" : "Nothing loaded";
  if (row.deliveries === 0) return "No confirmed purchases";
  return "Net sales not positive";
}

/** The contribution cell's words when there is no figure. */
export function noContributionWords(row: {
  net_sales: string | null;
  contribution: string | null;
}): string {
  if (row.net_sales === null) return "Nothing loaded";
  return "Nothing costed";
}

/** The status chip carries the contribution's word (the figure this screen
 * exists for); the ratio's own story lives in the ratio cell. */
export function leagueStatus(row: {
  contribution_quality: PeriodQuality;
  contribution_notes: string[];
}): { quality: PeriodQuality; sentence: string } {
  return {
    quality: row.contribution_quality,
    sentence: statusSentence(row.contribution_quality, row.contribution_notes),
  };
}

/** The card's caption under 640 px: "Kept AED 9,483 of AED 17,960 · purchases
 * ÷ net sales 39.3%". */
export function cardLine(row: LeagueRow): string {
  if (row.net_sales === null) return noRatioWords(row);
  const kept =
    row.contribution === null
      ? noContributionWords(row)
      : `Kept ${roundedAed(row.contribution)} of ${roundedAed(row.net_sales)}`;
  const ratio =
    row.ratio_pct === null ? noRatioWords(row).toLowerCase() : `purchases ÷ net sales ${row.ratio_pct}%`;
  return `${kept} · ${ratio}`;
}

/** The footnote under the league: always visible, never a tooltip. */
export function leagueFootnote(result: DashboardResult): string {
  const at =
    result.period.costed_at === null
      ? ""
      : `, costed at the prices in force on ${formatDate(result.period.costed_at)}`;
  return (
    `Contribution is what is left after ingredients and packaging${at}. It is not profit: ` +
    "rent, wages and utilities are not in it, and it covers the share of sales the menu can " +
    "cost. Ranked by Kept, lowest first; the Sales screen ranks the same branches by " +
    "purchases ÷ net sales."
  );
}

/** The screen's select: every branch, the chain first. */
export function branchOptions(branches: Branch[]): { id: string; label: string }[] {
  return [
    { id: "", label: "All branches" },
    ...branches.map((branch) => ({ id: branch.id, label: branch.name })),
  ];
}

/** The `?branch=` parameter, the one piece of state the URL carries so a
 * link to one branch's view can be sent to a person today (P7). */
export function branchParam(search: string): string | null {
  const value = new URLSearchParams(search).get("branch");
  return value === null || value === "" ? null : value;
}

/** The query string with the branch written in (or taken out), every other
 * parameter kept. Returned without the leading "?", empty when nothing is left. */
export function withBranch(search: string, branchId: string | null): string {
  const params = new URLSearchParams(search);
  if (branchId === null || branchId === "") params.delete("branch");
  else params.set("branch", branchId);
  return params.toString();
}

// --- the signals --------------------------------------------------------------

export const NO_SIGNALS = "Nothing stands out this window.";
export const NO_CHAIN_AVERAGE = "Load or map sales and this will name items.";

export function signalsCount(signals: DashboardSignal[]): string | null {
  if (signals.length === 0) return null;
  return `${signals.length} this window, largest first`;
}

export function signalMoney(signal: DashboardSignal): string {
  return roundedAed(signal.money_at_stake);
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function shortDate(iso: string): string {
  return `${Number(iso.slice(8, 10))} ${MONTHS[Number(iso.slice(5, 7)) - 1]}`;
}

/** "this window", or "since 25 Aug" for a price move, under the money. */
export function signalWhen(signal: DashboardSignal): string {
  if (signal.kind === "price_spike" && signal.moved_on !== null) {
    return `since ${shortDate(signal.moved_on)}`;
  }
  return "this window";
}

/** Where a signal's sentence leads: the item's plate, the invoice behind a
 * move, or the branch's own view. */
export function signalHref(signal: DashboardSignal): string | null {
  if (signal.kind === "popular_low_margin" && signal.menu_item_id !== null) {
    return `/menu#item-${signal.menu_item_id}`;
  }
  if (signal.kind === "price_spike" && signal.invoice_id !== null) {
    return `/invoices/${signal.invoice_id}`;
  }
  if (signal.kind === "branch_gap" && signal.branch_id !== null) {
    return `/dashboard?branch=${encodeURIComponent(signal.branch_id)}`;
  }
  return null;
}

/** "Based on 2 branches; Rolla has no sales loaded." under the list, or the
 * sentence for a chain whose average is undefined. */
export function signalsFootnote(result: DashboardResult): string | null {
  if (result.scope.branch_id !== null) return null;
  const missing = result.league.filter((row) => row.net_sales === null);
  if (result.total.contribution_pct === null && result.league.some((row) => row.net_sales !== null)) {
    return NO_CHAIN_AVERAGE;
  }
  if (missing.length === 0 || missing.length === result.league.length) return null;
  const based = result.league.length - missing.length;
  const names = missing.map((row) => shortBranchName(row.branch_name));
  const list =
    names.length === 1
      ? names[0]
      : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
  return `Based on ${based} ${based === 1 ? "branch" : "branches"}; ${list} ${
    names.length === 1 ? "has" : "have"
  } no sales loaded.`;
}

// --- the items ----------------------------------------------------------------

/** Top five and bottom five only when there are more than ten costed rows;
 * a shorter menu is shown whole, ranked as the API ranked it. */
export const SPLIT_AT = 10;

export type ItemPanel =
  | { kind: "none" }
  | { kind: "all"; rows: DashboardItemRow[] }
  | { kind: "split"; top: DashboardItemRow[]; bottom: DashboardItemRow[]; hidden: number };

function costedRows(items: DashboardItems): DashboardItemRow[] {
  return items.all.filter((row) => row.contribution !== null);
}

/** Which rows the panel shows. `top` and `bottom` are the API's own slices;
 * nothing here re-orders anything. */
export function itemPanel(items: DashboardItems, expanded: boolean): ItemPanel {
  const costed = costedRows(items);
  if (costed.length === 0) return { kind: "none" };
  if (expanded || costed.length <= SPLIT_AT) return { kind: "all", rows: costed };
  return {
    kind: "split",
    top: items.top,
    bottom: items.bottom,
    hidden: costed.length - items.top.length - items.bottom.length,
  };
}

/** The rows listed under the ranking with no numbers (an incomplete plate,
 * lines with no quantity), the `/menu` pattern. */
export function incompleteItems(items: DashboardItems): DashboardItemRow[] {
  return items.all.filter((row) => row.contribution === null);
}

/** "Best" above the first name, "Worst" above the first of the bottom five
 * (or the last row when the panel is shown whole). */
export function itemCaption(
  where: "top" | "bottom" | "all",
  index: number,
  total: number,
): "Best" | "Worst" | null {
  if (index === 0 && where !== "bottom") return "Best";
  if (where === "bottom" && index === 0) return "Worst";
  if (where === "all" && index === total - 1 && total > 1) return "Worst";
  return null;
}

export function showAllLabel(count: number, expanded: boolean): string {
  return expanded ? "Show the top 5 and bottom 5 only" : `Show all ${count} items`;
}

export function itemsHeading(items: DashboardItems): string {
  const listed = items.all.length;
  if (listed === 0) return "";
  if (items.count === listed) return `${items.count} costed`;
  return `${items.count} costed of ${listed}`;
}

export const NO_ITEMS = "No item-wise sales in this window.";

/** "412 sold · 2 refunded", or null for a row with no quantity. */
export function portionsWords(row: DashboardItemRow): string | null {
  if (row.qty_sold === null) return null;
  const sold = `${quantity(row.qty_sold)} sold`;
  if (row.qty_refunded === null || /^0+(\.0+)?$/.test(row.qty_refunded)) return sold;
  return `${sold} · ${quantity(row.qty_refunded)} refunded`;
}

/** "1,980" for 1980.000 - a count, grouped, never money. */
export function soldCount(value: string): string {
  return quantity(value).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

export function isLoss(row: DashboardItemRow): boolean {
  return (row.contribution ?? "").startsWith("-");
}

/** The API's own notes, capitalised and closed - the discount sentence, the
 * costing date, the recipe version, today's plate, the missing pieces. */
export function drillNotes(row: DashboardItemRow): string[] {
  return row.notes.map((note) => `${note.charAt(0).toUpperCase()}${note.slice(1)}.`);
}

export function tillNamesWords(row: DashboardItemRow): string {
  return row.till_items.map((till) => till.name).join(", ");
}

/** "Milk Powder · 0.03 kg" and its cost line. */
export function componentWords(component: ItemComponent): string {
  return `${component.ingredient_name} · ${quantity(component.qty)} ${component.unit}`;
}

export function componentCost(component: ItemComponent): string {
  if (component.cost_per_portion === null) return "no price yet";
  return `AED ${component.cost_per_portion} a plate`;
}

/** The invoice line behind the as-of price, in the shipped anchor shape. */
export function componentLink(component: ItemComponent): { href: string; label: string } | null {
  if (component.invoice_id === null || component.line_position === null) return null;
  const when = component.purchased_on === null ? "" : `, ${formatDate(component.purchased_on)}`;
  return {
    href: `/invoices/${component.invoice_id}#line-${component.line_position}`,
    label: `Invoice line ${component.line_position + 1}${when}`,
  };
}

/** The second door, today's plate on the menu screen (WP-94 lands the
 * anchor). Not rendered for a row that has no live plate. */
export function todaysPlateLink(row: DashboardItemRow): { href: string; label: string } | null {
  if (row.archived) return null;
  return { href: `/menu#item-${row.menu_item_id}`, label: "See today's plate" };
}

export const COST_COVERS = "Cost covers what the recipe lists.";

// --- the coverage strip -------------------------------------------------------

export interface CoverageStrip {
  lead: string;
  rest: string;
  link: { href: string; label: string } | null;
}

export function coverageStrip(result: DashboardResult): CoverageStrip {
  // Under a branch filter the figures on the screen are that branch's, so
  // the share quoted beside them is that branch's row, never the chain's.
  const share =
    result.scope.branch_id === null
      ? result.total.costed_share_pct
      : (result.league[0]?.costed_share_pct ?? null);
  const { names, value } = result.unmapped;
  const lead =
    share === null
      ? "Nothing sold here can be costed yet."
      : `These figures cover ${share}% of what was sold.`;
  const rest =
    names === 0
      ? "Every till name is mapped."
      : `${names} till ${names === 1 ? "name" : "names"} worth ${roundedAed(value)} ${
          names === 1 ? "has" : "have"
        } no dish yet.`;
  return {
    lead,
    rest,
    link: names === 0 ? null : { href: "/sales", label: "Map them on Sales" },
  };
}

// --- dates --------------------------------------------------------------------

/** Whole days inclusive between two ISO dates, for a mock or a caption. */
export function daysInclusive(from: string, to: string): number {
  return daysBetween(from, to) + 1;
}
