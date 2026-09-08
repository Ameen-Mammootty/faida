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
 * string operations only; a percentage is only ever rounded to the whole
 * number the headline idiom needs ("AED 61 of every 100"), through the sales
 * screen's own lens.
 *
 * The simple screen (2026-09-08): the founder's brief was that the owners
 * this is for "are very simple, not at all sophisticated business owners, who
 * want data presented to them in a simple way which will intrigue interest
 * and action", and that the shipped screen's subtexts were "information
 * overload". So: plain words on the face of the screen (sold, kept, paid to
 * suppliers), whole numbers, one sentence a block, the to-dos as a strip of
 * links, and every qualifying sentence one tap away behind the block's or the
 * row's one icon. The formal names the contracts pin (purchases ÷ net sales,
 * contribution before overheads) are the first line behind the icon of the
 * figure they name. Nothing the API said is rewritten to get there.
 */

import { formatDate, money, quantity, roundedAed } from "./format";
import {
  QUALITY_WORD,
  daysBetween,
  ofEveryHundred,
  percent,
  shortBranchName,
  statusSentence,
  weekdayDate,
  windowWords,
} from "./salesScreen";
import type {
  Branch,
  DashboardItemRow,
  DashboardItems,
  DashboardPriceMove,
  DashboardResult,
  DashboardScope,
  DashboardSignal,
  DashboardTotal,
  DashboardUnassigned,
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

// --- the words behind the info icons ------------------------------------------

/** The h1's own sentence, behind the icon beside the title. */
export const SCREEN_ABOUT =
  "What each branch and each dish kept after ingredients and packaging, over the days you " +
  "have loaded.";

/** A run of sentences cut into the lines a tooltip prints. A split, never a
 * rewrite: the words and their order are the author's. */
function sentences(text: string): string[] {
  return text
    .split(/(?<=\.)\s+/)
    .map((part) => part.trim())
    .filter((part) => part !== "");
}

function capitalise(text: string): string {
  return `${text.charAt(0).toUpperCase()}${text.slice(1)}`;
}

/** The API's notes as tooltip lines - capitalised and closed, the shape
 * `drillNotes` has printed since WP-93. */
function noteLines(notes: string[]): string[] {
  return notes.map((note) => `${capitalise(note)}.`);
}

// --- whole numbers --------------------------------------------------------------

/** "61%" from "60.9": the headline's lens on a percentage the API sent, the
 * same rounding the API's own sentences use ("about AED 61 of every 100").
 * Never divided, never computed - one string in, one string out. */
export function wholePercent(pct: string | null): string | null {
  if (pct === null) return null;
  const value = Number(pct);
  if (!Number.isFinite(value)) return null;
  return `${Math.round(value)}%`;
}

/** "AED 61 of every 100" - the idiom the answer sentence already uses, so a
 * tile reads the way the sentence above it does. */
export function everyHundred(pct: string): string {
  return `AED ${ofEveryHundred(pct)} of every 100`;
}

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

/** Sales loaded, no menu at all: the league shows what sold, and the kept
 * column says why it is empty. */
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
}

/** "Sales loaded to Mon 31 Aug, 5 days ago." - the API's sentence, alone.
 * The day's takings moved into the Sold tile and the papers into the to-do
 * strip, so the line says one thing. */
export function freshnessLine(result: DashboardResult): FreshnessLine | null {
  const { freshness } = result;
  if (freshness.sentence === null) return null;
  return { sentence: freshness.sentence, estimated: freshness.quality === "estimated" };
}

/** The invoice list, filtered to the papers held for review - and to the
 * branch in view, so a branch link shows that branch's papers (P7). */
export function approvalsHref(scope: DashboardScope): string {
  const params = new URLSearchParams({ status: "needs_review" });
  if (scope.branch_id !== null) params.set("branch_id", scope.branch_id);
  return `/invoices?${params.toString()}`;
}

// --- the to-do strip ----------------------------------------------------------

export type TodoKey = "papers" | "names" | "dishes";

export interface Todo {
  key: TodoKey;
  /** "2 papers waiting for you" - the count and the plain noun, nothing else. */
  label: string;
  href: string;
  /** What is behind the count, one line each, for the icon beside the link. */
  tip: string[];
}

const MAP_THEM = "/sales";

/** "3 till names worth AED 8,320 have no dish yet." - the queue in the words
 * the strip has used since WP-93. */
function unmappedWords(result: DashboardResult): string {
  const { names, value } = result.unmapped;
  return `${names} till ${names === 1 ? "name" : "names"} worth ${roundedAed(value)} ${
    names === 1 ? "has" : "have"
  } no dish yet. Map them on the Sales screen.`;
}

/**
 * What the owner can do about the figures, as a strip of links under the
 * heading: the papers held for review, the till names with sales and no dish,
 * and the dishes that sold but could not be costed. Each one is a count and
 * a door, present only when there is something behind it, so a quiet week
 * shows no strip at all. The reasons stay behind each link's icon.
 */
export function todo(result: DashboardResult): Todo[] {
  const out: Todo[] = [];
  const papers = result.approvals.count;
  if (papers > 0) {
    out.push({
      key: "papers",
      label: `${papers} ${papers === 1 ? "paper" : "papers"} waiting for you`,
      href: approvalsHref(result.scope),
      tip: [],
    });
  }
  const names = result.unmapped.names;
  if (names > 0) {
    out.push({
      key: "names",
      label: `${names} till ${names === 1 ? "name" : "names"} with no dish yet`,
      href: MAP_THEM,
      tip: [unmappedWords(result)],
    });
  }
  const dishes = noMenuSentence(result) === null ? incompleteItems(result.items) : [];
  if (dishes.length > 0) {
    out.push({
      key: "dishes",
      label: `${dishes.length} ${dishes.length === 1 ? "dish" : "dishes"} cannot be costed yet`,
      href: "/menu",
      tip: dishes.map((row) => `${row.menu_item_name}: ${drillNotes(row).join(" ")}`),
    });
  }
  return out;
}

// --- the answer ---------------------------------------------------------------

export const ANSWER_EMPTY =
  "Load a week of sales and this will name the branch and the item to look at.";
export const ANSWER_NO_MENU =
  "No menu is loaded, so nothing can be costed yet. Load it and this will name the branch " +
  "and the item to look at.";

export interface Answer {
  /** The API's lines, one bullet each: the branch, then the dish. */
  lines: string[];
  /** True when the one line is the screen's own words, not the API's. */
  own: boolean;
}

/**
 * The API's two lines, framed as bullets and never re-worded (C13.5): the
 * branch to look at first, then the dish that sells and does not earn. Since
 * 2026-09-08 the API writes them bullet-short ("Look at Deira: keeps 61%,
 * the least of the three branches."), so the screen has nothing to cut.
 */
export function answer(result: DashboardResult): Answer {
  const { branch, item } = result.answer;
  if (branch === null && item === null) {
    return {
      lines: [noMenuSentence(result) === null ? ANSWER_EMPTY : ANSWER_NO_MENU],
      own: true,
    };
  }
  return { lines: [branch, item].filter((line): line is string => line !== null), own: false };
}

/** The word that rides at the end of the answer, where the answer has one to
 * carry: estimated or incomplete, never the reliable word (it would be four
 * lines of chrome saying nothing). */
export function answerChip(result: DashboardResult): PeriodQuality | null {
  const { quality, branch, item } = result.answer;
  if (branch === null && item === null) return null;
  return quality === "estimated" || quality === "incomplete" ? quality : null;
}

/** The caveat, behind the icon at the end of the answer: the API's notes one
 * to a line, or the bare word when it sent none. */
export function answerTip(result: DashboardResult): string[] {
  const { quality, notes, branch, item } = result.answer;
  if (branch === null && item === null) return [];
  if (quality === "reliable_with_limitations") return [];
  return notes.length === 0 ? [QUALITY_WORD[quality]] : noteLines(notes);
}

// --- the tiles ----------------------------------------------------------------

export type TileKey = "sold" | "kept" | "suppliers";

export interface Tile {
  key: TileKey;
  /** Plain words: "Sold", "Kept after ingredients", "Paid to suppliers". */
  label: string;
  /** The headline, rounded and ready to print; null when there is no figure. */
  figure: string | null;
  /** What stands where the figure would: the cell's own words, or the
   * no-menu sentence. */
  words: string | null;
  /** A negative contribution, printed as the loss figure with its words. */
  loss: boolean;
  /** The one line under the figure; empty when there is nothing to say. */
  line: string;
  /** The quality word beside the line, where the figure carries one. */
  status: PeriodQuality | null;
  /** The bar under the kept figure: the share of sales it covers, drawn at
   * the percentage the API sent, with its own words beside it. */
  bar: { width: number; words: string } | null;
  /** Everything that qualifies the figure, one line each: the formal name
   * the contracts pin, then the API's notes. */
  tip: string[];
  /** Whose row this is, named once under a branch filter. */
  caption: string | null;
}

/** The chip a tile carries: the word only where it is a caveat (estimated
 * or incomplete) - the answer's rule, because "reliable with limitations"
 * beside every figure on a good week is chrome saying nothing. The tip
 * still says what the word was. */
export function tileChip(quality: PeriodQuality): PeriodQuality | null {
  return quality === "estimated" || quality === "incomplete" ? quality : null;
}

/** The fields a tile reads. The chain total and every league row carry the
 * same ones, which is what lets a tile follow the filter without a second
 * shape. */
type HeadlineRow = Pick<
  LeagueRow,
  | "net_sales"
  | "purchases"
  | "ratio_pct"
  | "contribution"
  | "contribution_pct"
  | "costed_share_pct"
  | "ratio_quality"
  | "ratio_notes"
  | "contribution_quality"
  | "contribution_notes"
>;

export const SOLD_ABOUT = "From the till's own export, net of VAT.";
export const KEPT_ABOUT =
  "Contribution before overheads (estimate): what is left after ingredients and packaging, " +
  "before rent, wages and utilities. It is not profit.";
export const COST_COVERS = "Cost covers what the recipe lists.";
export const SUPPLIERS_ABOUT =
  "Confirmed papers dated in this window, less the VAT printed on them.";

/** The ratio cell's words for the chain. `total` carries no delivery count,
 * and under a branch filter the league cannot supply one, so a chain that
 * paid nothing in the window is read off its own purchases - which is the
 * "no confirmed purchases" case the words are asking about. */
function chainRatioWords(total: DashboardTotal): string {
  return noRatioWords({
    net_sales: total.net_sales,
    deliveries: isZero(total.purchases) ? 0 : 1,
  });
}

function isZero(money: string): boolean {
  return /^0+(\.0+)?$/.test(money);
}

/** The share of what sold that could be costed. Unfiltered it is the
 * chain's; under a filter it is that branch's own row, never the chain's,
 * so the tile can never print a share of somebody else's sales. */
function costedShare(result: DashboardResult): string | null {
  return result.scope.branch_id === null
    ? result.total.costed_share_pct
    : (result.league[0]?.costed_share_pct ?? null);
}

export interface LatestDay {
  /** "AED 9,493 on Mon 31 Aug" - the newest loaded day, named (P6, P8). */
  line: string;
  /** "Taken across 3 branches that day." - behind the icon, for the chain. */
  tip: string | null;
}

/** The newest loaded day's takings, the chain's or the branch's own; null
 * when that day lies outside the period or the branch had none. */
export function latestDay(result: DashboardResult): LatestDay | null {
  const { latest_day: day, scope } = result;
  if (day === null) return null;
  if (scope.branch_id === null) {
    const n = day.branches.length;
    return {
      line: `${roundedAed(day.net_sales)} on ${weekdayDate(day.date)}`,
      tip: `Taken across ${n} ${n === 1 ? "branch" : "branches"} that day.`,
    };
  }
  const own = day.branches.find((b) => b.branch_id === scope.branch_id);
  if (own === undefined) return null;
  return { line: `${roundedAed(own.net_sales)} on ${weekdayDate(own.date)}`, tip: null };
}

/**
 * The three headline tiles: what the till took, what was left after
 * ingredients and packaging, and what went to suppliers. The tiles are the
 * row in view, and they name the chain beside it: every figure is the chain's
 * unfiltered and that branch's own under `?branch=`, because a chain figure
 * above a branch sentence is a number about one thing captioned with
 * another. No tile on a first run - there is nothing to count yet, and the
 * paragraph is the screen.
 */
export function tiles(result: DashboardResult): Tile[] {
  if (isFirstRun(result)) return [];
  const filtered = result.scope.branch_id !== null;
  const branchRow = result.league[0];
  if (filtered && branchRow === undefined) return [];
  const chain = result.total;
  const row: HeadlineRow = filtered ? branchRow : chain;
  // The row is named once, on the first tile: the other two name the chain
  // in their own lines, and three captions saying the same word is noise.
  const caption = filtered
    ? shortBranchName(result.scope.branch_name ?? branchRow.branch_name)
    : null;
  const noMenu = noMenuSentence(result);
  const day = latestDay(result);

  const contribution = row.contribution;
  const loss = contribution !== null && contribution.startsWith("-");
  const chainKeeps =
    filtered && chain.contribution_pct !== null
      ? ` · chain AED ${ofEveryHundred(chain.contribution_pct)}`
      : "";
  const share = costedShare(result);

  const paid = !isZero(row.purchases);
  const ownRatioWords = filtered ? noRatioWords(branchRow) : chainRatioWords(chain);
  const chainPays =
    filtered && chain.ratio_pct !== null ? ` · chain AED ${ofEveryHundred(chain.ratio_pct)}` : "";

  return [
    {
      key: "sold",
      label: "Sold",
      figure: row.net_sales === null ? null : roundedAed(row.net_sales),
      words: row.net_sales === null ? "Nothing loaded" : null,
      loss: false,
      line: day === null ? "" : day.line,
      // Past seven days the API says estimated, and the word rides beside the
      // day it qualifies.
      status: row.net_sales !== null && result.freshness.quality === "estimated" ? "estimated" : null,
      tip: [SOLD_ABOUT, ...(day === null || day.tip === null ? [] : [day.tip])],
      bar: null,
      caption,
    },
    {
      key: "kept",
      label: "Kept after ingredients",
      figure:
        noMenu !== null || contribution === null
          ? null
          : loss
            ? `-${roundedAed(contribution.slice(1))}`
            : roundedAed(contribution),
      words:
        noMenu !== null
          ? noMenu
          : contribution === null
            ? noContributionWords(row)
            : null,
      loss,
      line:
        row.contribution_pct === null || loss
          ? ""
          : `${everyHundred(row.contribution_pct)} sold${chainKeeps}`,
      // Nothing is costed without a menu, so the word has nothing to qualify.
      status: noMenu !== null || contribution === null ? null : tileChip(row.contribution_quality),
      bar:
        noMenu !== null || share === null
          ? null
          : {
              width: keptBar(share) ?? 0,
              words: `covers ${ofEveryHundred(share)}% of what sold`,
            },
      tip: noMenu !== null ? [] : [KEPT_ABOUT, COST_COVERS, ...noteLines(row.contribution_notes)],
      caption: null,
    },
    {
      key: "suppliers",
      label: "Paid to suppliers",
      figure: paid ? roundedAed(row.purchases) : null,
      words: paid ? null : ownRatioWords,
      loss: false,
      line:
        row.ratio_pct === null
          ? paid
            ? ownRatioWords
            : ""
          : `${everyHundred(row.ratio_pct)} sold${chainPays}`,
      status: row.ratio_pct === null ? null : tileChip(row.ratio_quality),
      bar: null,
      tip: [
        SUPPLIERS_ABOUT,
        ...(row.ratio_pct === null
          ? []
          : [`Purchases ÷ net sales (cash basis): ${percent(row.ratio_pct)}.`]),
        ...noteLines(row.ratio_notes),
      ],
      caption: null,
    },
  ];
}

// --- the league ---------------------------------------------------------------

/** Where the league's own days and papers live, beside its heading. */
export const LEAGUE_LINK = { href: "/sales", label: "All on Sales" };
/** Where every plate lives, beside the dishes' heading. */
export const ITEMS_LINK = { href: "/menu", label: "All on Menu" };

/** "25-31 Aug, 7 days · 3 deliveries" behind the branch's icon. */
export function leagueLine(row: LeagueRow): string {
  const days = `${row.window.days} ${row.window.days === 1 ? "day" : "days"}`;
  const deliveries = `${row.deliveries} ${row.deliveries === 1 ? "delivery" : "deliveries"}`;
  return `${windowWords(row.window.from, row.window.to)}, ${days} · ${deliveries}`;
}

/** The money behind a row's ratio, or the words that say there is none. */
function purchasesLine(row: LeagueRow): string {
  return row.ratio_pct === null
    ? noRatioWords(row)
    : `${roundedAed(row.purchases)} paid to suppliers, ${everyHundred(row.ratio_pct)} sold`;
}

/** Everything behind a league row's one icon, in reading order: its window
 * and its deliveries, what it paid to suppliers, then the sentences that
 * earned its status word. One icon a row - two was one too many. */
export function leagueTip(row: LeagueRow): string[] {
  return [leagueLine(row), purchasesLine(row), ...statusTip(row)];
}

/** The same for the chain's row, which has no window of its own to name. */
export function totalTip(total: DashboardTotal): string[] {
  return [
    total.ratio_pct === null
      ? chainRatioWords(total)
      : `${roundedAed(total.purchases)} paid to suppliers, ${everyHundred(total.ratio_pct)} sold`,
    ...statusTip(total),
  ];
}

/** The status sentences, one to a line - the tail of both tips. */
export function statusTip(row: {
  contribution_quality: PeriodQuality;
  contribution_notes: string[];
}): string[] {
  return sentences(leagueStatus(row).sentence);
}

/** The bar beside a kept percentage: the percentage the API sent, clamped to
 * the track. Nothing is divided here - a percentage is already a width - and
 * a row that lost money gets an empty track and says so in words. */
export function keptBar(pct: string | null): number | null {
  if (pct === null) return null;
  const value = Number(pct);
  if (!Number.isFinite(value)) return null;
  return Math.min(100, Math.max(0, value));
}

/** The ratio cell's words when there is no ratio to show - `/sales`' own. */
export function noRatioWords(row: { net_sales: string | null; deliveries: number }): string {
  if (row.net_sales === null) return row.deliveries > 0 ? "No sales loaded" : "Nothing loaded";
  if (row.deliveries === 0) return "No confirmed purchases";
  return "Net sales not positive";
}

/** The kept cell's words when there is no figure: a dash for a row with
 * nothing loaded, because its sold cell has already said so. */
export function noContributionWords(row: {
  net_sales: string | null;
  contribution: string | null;
}): string {
  if (row.net_sales === null) return "-";
  return "Nothing costed";
}

/** The sold cell's words when there is no figure - `/sales`' own. */
export function noSalesWords(row: { net_sales: string | null; deliveries: number }): string {
  return noRatioWords(row);
}

/**
 * Where a league row goes: `/sales`, at that branch's own row, opened to its
 * days and its papers (WP-94). The link is the app's one anchor idiom -
 * `#branch-<id>`, the shape `/materials#material-<id>` shipped in M6 - and
 * not a query parameter of its own, so there is one thing to learn and one
 * thing to keep working.
 *
 * The branch name is the link, so the row reads exactly as it does on
 * `/sales`, and the label is what a screen reader hears: "Deira" on its own
 * does not say where clicking it leads.
 */
export function leagueLink(row: { branch_id: string; branch_name: string }): {
  href: string;
  label: string;
} {
  return {
    href: `/sales#branch-${encodeURIComponent(row.branch_id)}`,
    label: `${row.branch_name}: its days and papers on the Sales screen`,
  };
}

/** The status chip carries the contribution's word (the figure this screen
 * exists for); the ratio's own story lives behind the row's icon. */
export function leagueStatus(row: {
  contribution_quality: PeriodQuality;
  contribution_notes: string[];
}): { quality: PeriodQuality; sentence: string } {
  return {
    quality: row.contribution_quality,
    sentence: statusSentence(row.contribution_quality, row.contribution_notes),
  };
}

/**
 * The word the whole league shares, or null when the rows disagree. Four
 * rows each saying "Estimated" is one word said four times, so where every
 * row with a figure - and the chain, unfiltered - carries the same word the
 * heading says it once; where they differ, each row says its own. The
 * reliable word is never printed as a chip (the answer's rule): it is what
 * the tips say when nothing qualifies a figure.
 */
export interface LeagueChips {
  /** The one word every figure in the league carries, or null. */
  shared: PeriodQuality | null;
  /** True when the rows disagree, so each row prints its own word; false
   * when they agree or when no row has a figure for a word to qualify. */
  perRow: boolean;
}

export function leagueChips(result: DashboardResult): LeagueChips {
  const words = new Set<PeriodQuality>();
  for (const row of result.league) {
    if (row.contribution !== null) words.add(row.contribution_quality);
  }
  if (result.scope.branch_id === null && result.total.contribution !== null) {
    words.add(result.total.contribution_quality);
  }
  if (words.size === 1) return { shared: [...words][0], perRow: false };
  return { shared: null, perRow: words.size > 1 };
}

/** The chip beside the league's heading: the shared word, only where it is
 * a caveat. */
export function leagueChip(result: DashboardResult): PeriodQuality | null {
  const { shared } = leagueChips(result);
  return shared === null ? null : tileChip(shared);
}

/** The chip on one row: its own word when the rows disagree and this row
 * has a figure for the word to qualify. */
export function rowChip(
  row: { contribution: string | null; contribution_quality: PeriodQuality },
  chips: LeagueChips,
): PeriodQuality | null {
  if (!chips.perRow || row.contribution === null) return null;
  return row.contribution_quality;
}

/** The card's line under 640 px: "Kept AED 7,828 of AED 15,846 sold". */
export function cardLine(row: LeagueRow): string {
  if (row.net_sales === null) return noSalesWords(row);
  if (row.contribution === null) return `${noContributionWords(row)} · ${roundedAed(row.net_sales)} sold`;
  return `Kept ${roundedAed(row.contribution)} of ${roundedAed(row.net_sales)} sold`;
}

/** "2 invoices with no branch · AED 1,200 · counted in the total, ranked
 * nowhere" - the one line the unassigned papers get. */
export function unassignedLine(unassigned: DashboardUnassigned): string | null {
  if (unassigned.count === 0) return null;
  return (
    `${unassigned.count} ${unassigned.count === 1 ? "invoice" : "invoices"} with no branch · ` +
    `${roundedAed(unassigned.purchases)} paid to suppliers · counted in the total, ranked nowhere`
  );
}

/** What the league is, behind the icon beside its heading. */
export function leagueFootnote(result: DashboardResult): string {
  const at =
    result.period.costed_at === null
      ? ""
      : `, costed at the prices in force on ${formatDate(result.period.costed_at)}`;
  return (
    `Kept is what is left after ingredients and packaging${at}. It is not profit: ` +
    "rent, wages and utilities are not in it, and it covers the share of sales the menu can " +
    "cost. Ranked by what each branch keeps of every 100 it takes, lowest first."
  );
}

/** The footnote, one sentence to a line. */
export function footnoteTip(result: DashboardResult): string[] {
  return sentences(leagueFootnote(result));
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

/** What the list is, behind the icon beside its heading. */
export const SIGNALS_ABOUT =
  "Where the most money is at stake this window, largest first. Nothing here fires on a " +
  "figure the read does not trust.";

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

/** Behind the row's icon: the API's sentence and its detail, one to a line.
 * The face of the row draws the numbers (the track); the words that state
 * them are here, unchanged. */
export function signalTip(signal: DashboardSignal): string[] {
  return [signal.sentence, signal.detail];
}

/** The row's name, from the signal's own fields: the dish, the branch (as
 * the owner says it), or the material. */
export function signalName(signal: DashboardSignal): string {
  if (signal.menu_item_name !== null) return signal.menu_item_name;
  if (signal.branch_name !== null) return shortBranchName(signal.branch_name);
  return signal.ingredient_name ?? "";
}

/** "since 21 Aug" under a price spike's name; nothing under the others,
 * whose window is the period's. */
export function signalWhenLine(signal: DashboardSignal): string | null {
  const when = signalWhen(signal);
  return when === "this window" ? null : when;
}

/** Three rows and a toggle: the list is ranked by money, so the three that
 * matter are the three at the top. */
export const SIGNALS_SHOWN = 3;

export function signalPanel(signals: DashboardSignal[], expanded: boolean): DashboardSignal[] {
  return expanded ? signals : signals.slice(0, SIGNALS_SHOWN);
}

export function showAllSignalsLabel(count: number, expanded: boolean): string | null {
  if (count <= SIGNALS_SHOWN) return null;
  return expanded ? `Show the top ${SIGNALS_SHOWN} only` : `Show all ${count}`;
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

// --- the supplier price moves -------------------------------------------------

/**
 * M9 WP-99's web half: each material's latest move inside the window, beside
 * "worth a look" on a laptop and under it on a phone.
 *
 * Everything with meaning in it arrived composed. The API ranks the list by
 * the money the move actually moved, and `sentence`, `plates` and `evidence`
 * are its own words carried whole (C13.5). The screen's own words are the
 * mark's name for a screen reader, the toggle and the empty state - three
 * small things, each a function here rather than a string inside the
 * component, so vitest pins them. Nothing below re-ranks, re-words or divides.
 */

/** Never an empty card: the panel says there were none. */
export const NO_PRICE_MOVES = "No price moves in this window.";

/** What the list is, behind the icon beside its heading. */
export const MOVES_ABOUT =
  "Each ingredient's latest price move in this window, ranked by the money it cost or saved " +
  "on what sold since.";

/** Where the whole list lives - both directions, both packs named, and the
 * moves this panel's window left out. */
export const MOVES_LINK = { href: "/menu", label: "All on Menu" };

/** The mark's three tones: caution for a rise, the confirmed green for a
 * fall, and the quietest pair in the palette for a basis change, which is
 * evidence and not a warning. The sentence beside it carries the words ("is
 * up", "is down", "priced from a different pack") - nothing on this screen
 * means anything by colour alone, and the mark's name is what a screen
 * reader hears. */
export type PriceMoveTone = "caution" | "verified" | "stone";

export interface PriceMoveMark {
  /** What the glyph means, for a screen reader. */
  name: string;
  tone: PriceMoveTone;
  /** Which arrow the mark wears; null for a basis change, which has none. */
  direction: "up" | "down" | null;
}

export function priceMoveMark(move: DashboardPriceMove): PriceMoveMark {
  if (move.kind === "basis_changed") {
    return { name: "Price basis changed", tone: "stone", direction: null };
  }
  if (move.direction === "down") {
    return { name: "Price fell", tone: "verified", direction: "down" };
  }
  return { name: "Price rose", tone: "caution", direction: "up" };
}

export interface PriceMoveMoney {
  /** The API's signed figure, rounded for a headline off its magnitude. */
  figure: string;
  /** Which way it went, in the word the API's own evidence line uses. */
  words: string;
}

/** The money the move moved, in the signals' style: the magnitude as the
 * figure, the direction as the small word under it. A basis change carries
 * no number at all, so the column stays empty rather than printing a zero
 * that would read as "nothing happened". */
export function priceMoveMoney(move: DashboardPriceMove): PriceMoveMoney | null {
  if (move.money_at_stake === null) return null;
  const magnitude = move.money_at_stake.replace("-", "");
  // A move nothing sold after carries a zero, not a null (the API's call): the
  // figure is honest and the words say why it is zero, so "AED 0 at stake"
  // never reads as a move that cost nothing. The full sentence is in the tip.
  if (isZero(magnitude)) {
    return { figure: roundedAed(magnitude), words: "nothing sold since" };
  }
  return {
    figure: roundedAed(magnitude),
    words: move.direction === "down" ? "saved" : "at stake",
  };
}

/** Three rows and a toggle, the signals' own pattern: the list arrives
 * ranked by the money it moved, so the three at the top are the three that
 * matter. */
export const MOVES_SHOWN = 3;

export function priceMovePanel(
  moves: DashboardPriceMove[],
  expanded: boolean,
): DashboardPriceMove[] {
  return expanded ? moves : moves.slice(0, MOVES_SHOWN);
}

/** The toggle counts the rows the panel holds, never the API's whole count:
 * "show all" may not promise moves that were never sent. */
export function showAllMovesLabel(count: number, expanded: boolean): string | null {
  if (count <= MOVES_SHOWN) return null;
  return expanded ? `Show the top ${MOVES_SHOWN} only` : `Show all ${count}`;
}

/** The paper behind the move: the newest line, at the app's one anchor idiom
 * (`lib/anchor.ts`). The API sends the position with the id or neither, so
 * the id is the one thing worth asking about. */
export function priceMoveLink(
  move: DashboardPriceMove,
): { href: string; label: string } | null {
  if (!move.invoice_id) return null;
  return {
    href: `/invoices/${move.invoice_id}#line-${move.line_position}`,
    label: "See the invoice",
  };
}

/** Behind the row's icon: the API's sentence, which plates felt it and the
 * evidence for the figure beside it, all in the API's own words, one to a
 * line. The face of the row draws the two prices; the words are here. */
export function priceMoveTip(move: DashboardPriceMove): string[] {
  return [move.sentence, move.plates, move.evidence].filter(
    (line): line is string => line !== null && line !== "",
  );
}

/** "since 21 Aug" under the material's name. */
export function moveWhenLine(move: DashboardPriceMove): string {
  return `since ${shortDate(move.moved_on)}`;
}

// --- the tracks (the founder's pick, 2026-09-08) --------------------------------

/**
 * Variant C of the panels board (`dashboard-panels-20260908`, picked by the
 * founder): the insight drawn, not said. A dish or a branch is a 0-100 track
 * with its kept share filled and a gold tick where its benchmark sits - the
 * gap between the fill and the tick is the problem. A price move is the same
 * track: the fill is the price now, the tick is where it was, so a rise runs
 * past the tick and a fall stops short of it, with the change as a chip.
 *
 * Every figure printed under a track is the API's field, rounded the way the
 * headlines are; the two widths are drawing geometry and never a figure
 * anyone reads.
 */
export interface Track {
  /** The fill, 0-100: a kept share, or the price now against the larger of the two prices. */
  fill: number;
  /** The gold tick, 0-100: the benchmark's share, or the price before. */
  tick: number;
  /** A share below zero: an empty track, the figure in plum. */
  loss: boolean;
  /** A price that fell: the fill in the confirmed green, the chip too. */
  fell: boolean;
  /** Under the track, left: the figure and its word - "38%" "kept", "AED 61.40" "/kg". */
  left: { figure: string; words: string };
  /** Under the track, right, the tick's label: "menu 67%", "chain 67%", "was 58.00". */
  right: string;
  /** The change chip on a price track: "+6%", "-9%"; null on a share track. */
  change: string | null;
}

/** A dish's or a branch's kept share against its benchmark. */
export function shareTrack(
  kept: string,
  benchmark: string,
  benchmarkWord: "menu" | "chain",
): Track {
  const loss = kept.startsWith("-");
  return {
    fill: keptBar(kept) ?? 0,
    tick: keptBar(benchmark) ?? 0,
    loss,
    fell: false,
    left: { figure: wholePercent(kept) ?? kept, words: loss ? "kept · loses money" : "kept" },
    right: `${benchmarkWord} ${wholePercent(benchmark) ?? benchmark}`,
    change: null,
  };
}

/** "/kg", "/litre", "each" - the unit the price is per. */
function perUnit(unit: string): string {
  return unit === "each" ? "each" : `/${unit}`;
}

/** "+6%" from "5.9", "-9%" from "-9.1": the change the API judged the gate
 * on, as a whole number with its sign. */
export function wholeChange(pct: string): string {
  const value = Math.round(Number(pct));
  return `${value > 0 ? "+" : ""}${value}%`;
}

/** A price before and after, per display unit, on one track. The larger of
 * the two is the full width; both widths are geometry only. */
export function priceTrack(before: string, after: string, unit: string, change: string): Track {
  const was = Number(before);
  const now = Number(after);
  const base = Math.max(was, now, 0);
  const width = (value: number) => (base > 0 ? Math.min(100, Math.max(0, (value / base) * 100)) : 0);
  return {
    fill: width(now),
    tick: width(was),
    loss: false,
    fell: change.startsWith("-"),
    left: { figure: `AED ${money(after)}`, words: perUnit(unit) },
    right: `was ${money(before)}`,
    change: wholeChange(change),
  };
}

/** A signal's track, from its own fields: a share for a dish or a branch,
 * a price pair for a spike; null when the API sent no figures to draw, in
 * which case the row prints the sentence instead. */
export function signalTrack(signal: DashboardSignal): Track | null {
  if (signal.kept_pct !== null && signal.benchmark_pct !== null) {
    return shareTrack(
      signal.kept_pct,
      signal.benchmark_pct,
      signal.kind === "branch_gap" ? "chain" : "menu",
    );
  }
  if (
    signal.price_before !== null &&
    signal.price_after !== null &&
    signal.unit !== null &&
    signal.change_pct !== null
  ) {
    return priceTrack(signal.price_before, signal.price_after, signal.unit, signal.change_pct);
  }
  return null;
}

/** A move's track; null for a basis change, whose row prints the API's
 * sentence in the track's place ("no before and after to show"). */
export function moveTrack(move: DashboardPriceMove): Track | null {
  if (
    move.kind !== "moved" ||
    move.price_before === null ||
    move.price_after === null ||
    move.unit === null ||
    move.change_pct === null
  ) {
    return null;
  }
  return priceTrack(move.price_before, move.price_after, move.unit, move.change_pct);
}

/** The panel's chip: the estimated word said once in the heading when every
 * row carries it, on each row when they differ, and never the reliable word
 * (the league's rule, `leagueChips`). */
export function signalsChips(signals: DashboardSignal[]): LeagueChips {
  const words = new Set(signals.map((signal) => signal.quality));
  if (signals.length === 0) return { shared: null, perRow: false };
  if (words.size === 1) return { shared: [...words][0], perRow: false };
  return { shared: null, perRow: true };
}

// --- the dishes ---------------------------------------------------------------

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

/** The two lists' headings when the panel is split. */
export const BEST_HEADING = "Best earners";
export const WORST_HEADING = "Weakest earners";

/** The rows with no numbers (an incomplete plate, lines with no quantity):
 * they leave the ranking and go to the to-do strip. */
export function incompleteItems(items: DashboardItems): DashboardItemRow[] {
  return items.all.filter((row) => row.contribution === null);
}

export function showAllLabel(count: number, expanded: boolean): string {
  return expanded ? "Show the top 5 and bottom 5 only" : `Show all ${count} dishes`;
}

export const NO_ITEMS = "No item-wise sales in this window.";

/** "412 sold · 2 refunded", or null for a row with no quantity. */
export function portionsWords(row: DashboardItemRow): string | null {
  if (row.qty_sold === null) return null;
  const sold = `${quantity(row.qty_sold)} sold`;
  if (row.qty_refunded === null || isZero(row.qty_refunded)) return sold;
  return `${sold} · ${quantity(row.qty_refunded)} refunded`;
}

/** "1,980" for 1980.000 - a count, grouped, never money. */
export function soldCount(value: string): string {
  return quantity(value).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/** "412 sold" beside the name, or the words for a row with no quantity. */
export function soldWords(row: DashboardItemRow): string {
  return row.qty_sold === null ? "no quantity" : `${soldCount(row.qty_sold)} sold`;
}

export function isLoss(row: DashboardItemRow): boolean {
  return (row.contribution ?? "").startsWith("-");
}

/** The API's own notes, capitalised and closed - the discount sentence, the
 * costing date, the recipe version, today's plate, the missing pieces. */
export function drillNotes(row: DashboardItemRow): string[] {
  return row.notes.map((note) => `${capitalise(note)}.`);
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

/** What kept is and is not for a dish, behind the icon beside the heading. */
export const ITEMS_NOTE =
  "Kept is the till's own net takings for the dish less what its recipe costs at the " +
  "prices in force on the period's last day; it is not profit, and " +
  `${COST_COVERS.charAt(0).toLowerCase()}${COST_COVERS.slice(1)}`;

export function itemsTip(): string[] {
  return sentences(ITEMS_NOTE);
}

// --- dates --------------------------------------------------------------------

/** Whole days inclusive between two ISO dates, for a mock or a caption. */
export function daysInclusive(from: string, to: string): number {
  return daysBetween(from, to) + 1;
}
