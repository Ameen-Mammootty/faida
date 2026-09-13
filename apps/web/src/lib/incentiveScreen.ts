/**
 * The pure decisions behind the `/incentive` screen - every sentence and every
 * enabling rule the component renders, kept out of React so vitest pins them
 * (the `dashboardScreen.ts` rule: a choice left inside a component would be
 * untested by construction).
 *
 * Four blocks: the role shares that split a pool (M13.2, issue #8), the
 * scheme month with its per-branch targets and its push weeks (M13.3, issue
 * #9), each week's push list with the menu to build it from (M13.4, issue
 * #10), and each branch's statement for the month (M13.5, issue #11).
 *
 * The screen never words a refusal. A share that does not add to a hundred, a
 * negative target, a month already created - each is refused by
 * `faida_api/incentive.py` and the API returns that sentence, so a refusal is
 * written once in the whole product. What lives here is what the owner needs
 * while typing and cannot work out by eye: the running total across three
 * share boxes, whether a form is finished, which week a month opens on.
 */

import { formatDate, groupedMoney } from "./format";
import type {
  IncentiveBranch,
  IncentiveBranchTarget,
  IncentiveCategory,
  IncentiveMenuItem,
  IncentiveRead,
  IncentiveStatement,
  PushListInput,
  PushWeek,
  RoleShares,
  RoleSharesRow,
  SchemeMonth,
  SchemeMonthInput,
  StatementFigures,
} from "./types";

// --- the three fields -------------------------------------------------------

/** The three roles a pool is split between (D2), in the order the owner
 * meets them on the screen. */
export const SHARE_ROLES = ["manager", "supervisor", "sales"] as const;
export type ShareRole = (typeof SHARE_ROLES)[number];

/** What the owner has typed into the three boxes: a string per role, because
 * a half-typed percentage is a string and rounding it while they type would
 * fight the keyboard. */
export type ShareDraft = Record<ShareRole, string>;

export const SHARE_LABEL: Record<ShareRole, string> = {
  manager: "Manager",
  supervisor: "Supervisor",
  sales: "Sales team",
};

const FIELD: Record<ShareRole, keyof RoleShares> = {
  manager: "manager_pct",
  supervisor: "supervisor_pct",
  sales: "sales_pct",
};

/** "40" for "40.00", "12.5" for "12.50" - the API's own plain percentage,
 * which is what belongs in an input box. String surgery, not arithmetic: a
 * percentage crosses the wire as a string and is never a float here (C6). */
export function plainPct(value: string): string {
  const text = value.trim();
  if (!/^-?\d+\.\d+$/.test(text)) return text;
  return text.replace(/0+$/, "").replace(/\.$/, "");
}

/** The draft a screen opens with: the shares on file, or empty boxes. */
export function shareDraft(shares: RoleSharesRow | null): ShareDraft {
  if (shares === null) return { manager: "", supervisor: "", sales: "" };
  return {
    manager: plainPct(shares[FIELD.manager]),
    supervisor: plainPct(shares[FIELD.supervisor]),
    sales: plainPct(shares[FIELD.sales]),
  };
}

/** The wire body of a draft: the three strings as typed, trimmed. The API
 * parses them; the screen does not pre-judge them. */
export function shareBody(draft: ShareDraft): RoleShares {
  return {
    manager_pct: draft.manager.trim(),
    supervisor_pct: draft.supervisor.trim(),
    sales_pct: draft.sales.trim(),
  };
}

// --- the running total ------------------------------------------------------

/**
 * One share as hundredths of a percentage point, or null when it is not a
 * share yet: empty, half-typed, not a number, or written to more decimals
 * than a share is kept to.
 *
 * Integers, because three percentages have to add to exactly a hundred and
 * floats do not add up: 10 + 58.01 + 31.99 is 99.99999999999999 in
 * JavaScript, which would leave the owner with a whole pool on the screen and
 * a Save button that never lights. Money and percentages cross the wire as
 * strings and stay exact here (C6, plan.md section 2 rule 7). Two decimals is
 * also the rule the API states in words (`incentive.shares_problem`) and the
 * row keeps (`numeric(5,2)`), so the form asks for nothing the door refuses.
 */
function hundredths(value: string): number | null {
  const match = /^(-?)(\d+)(?:\.(\d{1,2}))?$/.exec(value.trim());
  if (match === null) return null;
  const [, sign, whole, frac = ""] = match;
  const scaled = Number(whole) * 100 + Number(`${frac}00`.slice(0, 2));
  return sign === "-" ? -scaled : scaled;
}

/** Hundredths back to percentage points, without trailing zeros: 9999 is
 * "99.99", 9990 is "99.9", 10000 is "100". */
function points(scaled: number): string {
  const sign = scaled < 0 ? "-" : "";
  const size = Math.abs(scaled);
  const frac = String(size % 100)
    .padStart(2, "0")
    .replace(/0+$/, "");
  const whole = Math.trunc(size / 100);
  return frac === "" ? `${sign}${whole}` : `${sign}${whole}.${frac}`;
}

const WHOLE_POOL = 100 * 100;

/** The three shares as hundredths, or null when any of them is not a share
 * yet. */
function drafted(draft: ShareDraft): number[] | null {
  const scaled = SHARE_ROLES.map((role) => hundredths(draft[role]));
  return scaled.some((value) => value === null) ? null : (scaled as number[]);
}

function total(scaled: number[]): number {
  return scaled.reduce((sum, value) => sum + value, 0);
}

/**
 * What the screen says under the three boxes while the owner types. Not a
 * refusal - the API owns those words - but the arithmetic the owner cannot
 * do in their head across three boxes: how much of the pool is allocated,
 * and how far from a whole pool they are.
 */
export function sumWords(draft: ShareDraft): string {
  const scaled = drafted(draft);
  if (scaled === null)
    return "Three percentages, adding to 100, split the pool.";
  const sum = total(scaled);
  if (sum === WHOLE_POOL) return "The three shares split the whole pool.";
  if (sum < WHOLE_POOL) {
    return `${points(sum)}% of the pool allocated, ${points(WHOLE_POOL - sum)}% left.`;
  }
  return `${points(sum)}% of the pool allocated, ${points(sum - WHOLE_POOL)}% more than the pool.`;
}

/** Whether Save is offered: three percentages, none negative, adding to a
 * hundred, and not the three already on file. The API refuses anything else
 * in its own words, so this decides and never explains. */
export function canSaveShares(
  draft: ShareDraft,
  saved: RoleSharesRow | null,
): boolean {
  const scaled = drafted(draft);
  if (scaled === null) return false;
  if (scaled.some((value) => value < 0)) return false;
  if (total(scaled) !== WHOLE_POOL) return false;
  if (saved === null) return true;
  // Sending the same three shares again would write a row and an audit line
  // that record nothing.
  return SHARE_ROLES.some(
    (role, index) => scaled[index] !== hundredths(saved[FIELD[role]]),
  );
}

// --- the block's own words --------------------------------------------------

/** The heading's second line: what the shares are for. */
export const SHARES_CAPTION =
  "How a month's pool is split between the people who earned it.";

/** The note beside Save: a change never touches a month already created,
 * because a scheme month keeps the shares it was created with (D4). */
export const SHARES_APPLIES_NOTE =
  "A change applies to the next scheme month. A month already created keeps the shares it started with.";

/** When the shares were last set, or that they never were. */
export function sharesUpdatedWords(shares: RoleSharesRow | null): string {
  if (shares === null) return "Not set yet.";
  return `Last set ${formatDate(shares.updated_at.slice(0, 10))}.`;
}

// --- the scheme month (M13.3, issue #9) -------------------------------------

/**
 * A calendar month the picker can offer. `created` is whether a scheme month
 * exists for it: the difference between opening a month and creating one.
 */
export interface MonthOption {
  /** "2026-07" */
  month: string;
  /** "July 2026" */
  words: string;
  created: boolean;
}

const MONTH_NAMES = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

/** "2026-07" to "July 2026" - the same words as `incentive.month_words`,
 * needed here for the months in the picker that have no scheme month yet and
 * so are not in any payload the API wrote. */
export function monthWords(month: string): string {
  const [year, index] = month.split("-");
  const name = MONTH_NAMES[Number(index) - 1];
  return name === undefined ? month : `${name} ${year}`;
}

/** A month key n months on, by integer arithmetic on the key itself. */
function shift(month: string, by: number): string {
  const [year, index] = month.split("-").map(Number);
  const zero = year * 12 + (index - 1) + by;
  return `${String(Math.trunc(zero / 12)).padStart(4, "0")}-${String((zero % 12) + 1).padStart(2, "0")}`;
}

/** The month a date falls in: "2026-07-14" is "2026-07". */
export function monthOf(isoDate: string): string {
  return isoDate.slice(0, 7);
}

/**
 * The months the picker offers, newest first: every month with a scheme month
 * on file, plus this month and the next two, so the owner can always create
 * the month that is running and the ones ahead of it without typing a date.
 * The month in view is always among them, whichever way it was reached.
 */
export function monthOptions(read: IncentiveRead): MonthOption[] {
  const created = new Set(read.months.map((option) => option.month));
  const here = monthOf(read.today);
  const keys = new Set([
    ...created,
    read.month,
    here,
    shift(here, 1),
    shift(here, 2),
  ]);
  return [...keys]
    .sort()
    .reverse()
    .map((month) => ({
      month,
      words: monthWords(month),
      created: created.has(month),
    }));
}

// --- the create form --------------------------------------------------------

/** What the owner has typed into one branch's three boxes. Strings, because
 * a half-typed figure is a string and rounding it while they type would fight
 * the keyboard; money and percentages cross the wire as strings anyway (C6). */
export interface TargetDraft {
  net: string;
  pct: string;
  cap: string;
}

export type TargetDrafts = Record<string, TargetDraft>;

/**
 * The create form a screen opens with: three empty boxes per branch.
 *
 * Empty even though last month's net sales are on the read and sit beside the
 * box: last month is advice and never the baseline (D3), and a figure typed
 * into the box by Faida would be a baseline whatever it was labelled. The
 * owner types the target.
 */
export function targetDrafts(branches: IncentiveBranch[]): TargetDrafts {
  return Object.fromEntries(
    branches.map((branch) => [branch.id, { net: "", pct: "", cap: "" }]),
  );
}

/** Whether a box holds something that could be a figure. The API refuses a
 * figure that is not one, in its own words; this only asks whether the owner
 * has finished typing. */
function typed(value: string): boolean {
  return /^-?\d+(\.\d+)?$/.test(value.trim());
}

/**
 * Whether Create is offered: every branch has a net sales target and a
 * percentage. The cap is optional - blank means no cap (D8).
 *
 * Deliberately no stricter than that. A negative target and a percentage over
 * a hundred are refused by the API in sentences that name the branch, and an
 * owner who sees the sentence learns the rule; a Create button that silently
 * will not light teaches nothing. The shares block is stricter because three
 * percentages summing to a hundred is arithmetic the owner cannot check by
 * eye, and a target is not.
 */
export function canCreateMonth(
  drafts: TargetDrafts,
  branches: IncentiveBranch[],
): boolean {
  if (branches.length === 0) return false;
  return branches.every((branch) => {
    const draft = drafts[branch.id];
    return draft !== undefined && typed(draft.net) && typed(draft.pct);
  });
}

/** The wire body of the create door: the strings as typed, trimmed, with a
 * blank cap sent as no cap. */
export function schemeMonthBody(
  month: string,
  drafts: TargetDrafts,
  branches: IncentiveBranch[],
): SchemeMonthInput {
  return {
    month,
    targets: branches.map((branch) => {
      const draft = drafts[branch.id] ?? { net: "", pct: "", cap: "" };
      return {
        branch_id: branch.id,
        net_sales_target: draft.net.trim(),
        above_target_pct: draft.pct.trim(),
        cap: draft.cap.trim() === "" ? null : draft.cap.trim(),
      };
    }),
  };
}

/** The sentence under the create form: what is still needed, and once it is
 * all there, what creating the month commits to (D4). */
export function createStanding(
  drafts: TargetDrafts,
  branches: IncentiveBranch[],
): string {
  if (branches.length === 0)
    return "This chain has no branches to set targets for.";
  if (!canCreateMonth(drafts, branches)) {
    return "Type a net sales target and a percentage of sales above it for every branch. A cap is optional.";
  }
  return "The month is frozen when you create it: these targets cannot be changed afterwards.";
}

// --- the month, once it exists ----------------------------------------------

/** Where a push week sits against today. */
export type WeekState = "ended" | "running" | "coming";

export interface WeekTab {
  id: string;
  /** "6-12 Jul" */
  label: string;
  state: WeekState;
  frozen: boolean;
  /** Why the week cannot be re-aimed, or what it is still waiting for. */
  note: string;
}

const NO_PUSH_LIST = "No push list yet.";

/** What a week that has started or ended with an empty list says. */
const NO_LIST_SET = "No push list was set for it.";

/**
 * The month's weeks as the screen's tabs. A week that has started is frozen
 * and says why in the API's own sentence (D5); a week still coming may be
 * re-aimed, and until it has a list says so.
 *
 * The note is written against the week's own `items`, so a week filled in
 * this session says how many dishes are on it without the tab strip being
 * told anything about the list below it.
 */
export function weekTabs(weeks: PushWeek[], today: string): WeekTab[] {
  return weeks.map((week) => {
    const state: WeekState =
      week.end < today ? "ended" : week.start <= today ? "running" : "coming";
    const empty = week.items.length === 0;
    return {
      id: week.id,
      label: week.words,
      state,
      frozen: week.frozen,
      note: week.frozen
        ? sentence(week.frozen_words ?? "")
        : empty
          ? NO_PUSH_LIST
          : `${week.items.length} ${week.items.length === 1 ? "dish" : "dishes"} on the list.`,
    };
  });
}

/** The API composes its sentences to sit inside a refusal ("the week of 7-13
 * Sep has started and is frozen"); on the screen the same words stand alone
 * and are punctuated as a sentence. The words themselves are never rewritten. */
function sentence(words: string): string {
  if (words === "") return words;
  const capital = words[0].toUpperCase() + words.slice(1);
  return /[.!?]$/.test(capital) ? capital : `${capital}.`;
}

/** The week the screen opens on: the one running today, else the first that
 * has not started, else the last - so a month opened after it ended still
 * opens on something. */
export function weekInView(tabs: WeekTab[]): string | null {
  if (tabs.length === 0) return null;
  const running = tabs.find((tab) => tab.state === "running");
  const coming = tabs.find((tab) => tab.state === "coming");
  return (running ?? coming ?? tabs[tabs.length - 1]).id;
}

/** A branch's stored targets, looked up for the table. */
export function targetOf(
  scheme: SchemeMonth,
  branchId: string,
): IncentiveBranchTarget | null {
  return scheme.targets.find((target) => target.branch_id === branchId) ?? null;
}

/** What a stored cap says, in words, because blank is not nothing: it is a
 * decision that the pool is uncapped (D8). */
export function capWords(target: IncentiveBranchTarget | null): string {
  if (target === null) return "No target";
  return target.cap === null ? "No cap" : groupedMoney(target.cap);
}

// --- the block's own words --------------------------------------------------

export const MONTH_CAPTION =
  "The calendar month the team is scored and paid on. Its targets are frozen when the month is created.";

/** The note beside the month once it exists. */
export const MONTH_FROZEN_NOTE =
  "This month is frozen: its targets and the shares that split its pool are the ones it was created with.";

export const WEEKS_CAPTION =
  "Monday to Sunday, clipped to the month, so no week waits for another month's days.";

/** The screen's first sentence: what the owner should do next on it. */
export function standing(read: IncentiveRead): string {
  if (read.shares === null) {
    return "Set the three shares first: every scheme month is created with the shares in force that day.";
  }
  if (read.scheme_month === null) {
    return `No scheme month for ${read.month_words} yet. Type a target for each branch to create it.`;
  }
  return `${read.month_words} is set. Fill each week's push list to tell the team what to push.`;
}

// --- the week's push list ---------------------------------------------------

/** One row of the list as the owner is typing it: the dish, what a portion
 * above target earns, and a portion target per branch. Strings, because a
 * half-typed figure is a string and rounding one while the owner types would
 * fight the keyboard. */
export interface PushRow {
  menu_item_id: string;
  rate: string;
  /** Branch id to the portions typed for it. */
  targets: Record<string, string>;
}

/** The dish behind a row, and the category the API filed it under - `Other`
 * for a dish the menu gives none. */
export interface MenuEntry {
  item: IncentiveMenuItem;
  category: string;
  guidance: string;
}

export type MenuIndex = Record<string, MenuEntry>;

/**
 * The menu by dish id, carrying the category the API filed each dish under.
 *
 * The category comes off the read rather than off the dish's own `category`
 * field so that `Other` is spelt once, in Python, and the screen never has a
 * second opinion about where an uncategorised dish belongs.
 */
export function menuIndex(
  menu: IncentiveCategory<IncentiveMenuItem>[],
): MenuIndex {
  const index: MenuIndex = {};
  for (const group of menu) {
    for (const item of group.items) {
      index[item.id] = {
        item,
        category: group.category,
        guidance: group.guidance,
      };
    }
  }
  return index;
}

/** The week's stored list as a draft to edit: the rates and targets exactly
 * as the week holds them, so opening a filled week and saving it again
 * changes nothing. */
export function pushDraft(
  week: PushWeek | null,
  branches: IncentiveBranch[],
): PushRow[] {
  if (week === null) return [];
  return week.items.map((item) => ({
    menu_item_id: item.menu_item_id,
    rate: plainPct(item.rate_per_portion),
    targets: Object.fromEntries(
      branches.map((branch) => {
        const target = item.targets.find((row) => row.branch_id === branch.id);
        return [
          branch.id,
          target === undefined ? "" : trimZeros(target.portion_target),
        ];
      }),
    ),
  }));
}

/** "300.500" as "300.5", "1000.000" as "1000" - a stored portion count put
 * back in a box the way a person would have typed it. String surgery, never
 * arithmetic: a figure crosses the wire as a string and is never a float
 * here (C6). */
function trimZeros(value: string): string {
  const text = value.trim();
  if (!/^-?\d+\.\d+$/.test(text)) return text;
  return text.replace(/0+$/, "").replace(/\.$/, "");
}

/** An empty row for a dish just picked: nothing typed, so the owner types
 * the rate and every branch's portions. */
export function pushRowFor(
  menuItemId: string,
  branches: IncentiveBranch[],
): PushRow {
  return {
    menu_item_id: menuItemId,
    rate: "",
    targets: Object.fromEntries(branches.map((branch) => [branch.id, ""])),
  };
}

/** The list being typed, grouped the way the menu reads (D6). */
export function draftGroups(
  rows: PushRow[],
  index: MenuIndex,
  menu: IncentiveCategory<IncentiveMenuItem>[],
): { category: string; guidance: string; items: PushRow[] }[] {
  return groupLikeMenu(
    rows,
    (row) => index[row.menu_item_id]?.category ?? OFF_THE_MENU,
    menu,
  );
}

/**
 * Anything that belongs to a dish, grouped by the menu's own categories in
 * the menu's own order.
 *
 * The order is the read's own - the API has already sorted the categories and
 * put `Other` last - so a list being typed, a list just saved and a list read
 * back can never fall into three different orders, and the ordering rule is
 * not written a second time in TypeScript. A category the read does not carry
 * goes last, which is where a dish archived off the menu since the list was
 * set ends up: still on the week, and still to be taken off it.
 */
export function groupLikeMenu<T>(
  items: T[],
  categoryOf: (item: T) => string,
  menu: IncentiveCategory<IncentiveMenuItem>[],
): { category: string; guidance: string; items: T[] }[] {
  const order = menu.map((group) => group.category);
  const buckets = new Map<string, T[]>();
  for (const item of items) {
    const category = categoryOf(item);
    const bucket = buckets.get(category);
    if (bucket === undefined) buckets.set(category, [item]);
    else bucket.push(item);
  }
  return [...buckets.keys()]
    .sort((left, right) => bucketRank(left, order) - bucketRank(right, order))
    .map((category) => ({
      category,
      guidance:
        menu.find((group) => group.category === category)?.guidance ?? "",
      items: buckets.get(category) ?? [],
    }));
}

/** The heading a dish that has left the menu sits under: not a category the
 * menu has, so it is never confused with one. */
export const OFF_THE_MENU = "No longer on the menu";

function bucketRank(category: string, order: string[]): number {
  const at = order.indexOf(category);
  return at === -1 ? order.length : at;
}

/** What a category says beside its dishes: how many are on it, and the API's
 * own guidance when that is outside the one to three it suggests.
 *
 * Shown and never enforced (D6): Save stays open on a fourth snack, because
 * a week that needs four snacks is the owner's call. The guidance sentence is
 * the API's, passed through - it is not written twice.
 */
export function guidanceWords(count: number, guidance: string): string {
  const many = `${count} ${count === 1 ? "dish" : "dishes"}`;
  return count >= 1 && count <= 3 ? many : `${many} - ${guidance}`;
}

/** The dishes still on offer: every live dish the draft does not already
 * hold. A dish with no till name mapped to it stays in the list and is
 * offered greyed, because "not offered" teaches nothing and "offered with
 * the reason beside it" sends the owner to the Sales screen to fix it. */
export function pickerGroups(
  menu: IncentiveCategory<IncentiveMenuItem>[],
  rows: PushRow[],
): IncentiveCategory<IncentiveMenuItem>[] {
  const taken = new Set(rows.map((row) => row.menu_item_id));
  return menu
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => !taken.has(item.id)),
    }))
    .filter((group) => group.items.length > 0);
}

/** What a dish reads as in the picker: its name, then what its plate keeps -
 * or why it cannot be pushed at all. Both halves are the API's own words. */
export function pickerLabel(item: IncentiveMenuItem): string {
  return item.mapped
    ? `${item.name} - ${item.kept_words}`
    : `${item.name} - no till name mapped`;
}

/**
 * Whether Save is offered for this week's list: the week is still open, and
 * every row has a rate and a portion target for every branch.
 *
 * Stricter than the create form for the reason the shares block is: a branch
 * silently left without a target would be scored against a target of zero and
 * pay the team for every portion it sold, which is money and not a typo. A
 * dish that has lost its till name, or left the menu, blocks the save too -
 * it can only be refused, and taking it off the week is the owner's next
 * move either way.
 */
export function canSavePushList(
  rows: PushRow[],
  branches: IncentiveBranch[],
  index: MenuIndex,
  week: WeekTab | null,
): boolean {
  if (week === null || week.frozen) return false;
  if (branches.length === 0) return false;
  return rows.every((row) => {
    const entry = index[row.menu_item_id];
    if (entry === undefined || !entry.item.mapped) return false;
    if (!typed(row.rate)) return false;
    return branches.every((branch) => typed(row.targets[branch.id] ?? ""));
  });
}

/** The wire body of the push-list door: the strings as typed, trimmed. */
export function pushListBody(
  rows: PushRow[],
  branches: IncentiveBranch[],
): PushListInput {
  return {
    items: rows.map((row) => ({
      menu_item_id: row.menu_item_id,
      rate_per_portion: row.rate.trim(),
      targets: branches.map((branch) => ({
        branch_id: branch.id,
        portion_target: (row.targets[branch.id] ?? "").trim(),
      })),
    })),
  };
}

/** The sentence under the week's list: why it cannot be edited, what is
 * still needed, or what saving it does. Never a refusal - those are the
 * API's, in its own words. */
export function pushStanding(
  rows: PushRow[],
  branches: IncentiveBranch[],
  index: MenuIndex,
  week: WeekTab | null,
): string {
  if (week === null) return "";
  // A week that has ended with nothing on it says so: the frozen sentence
  // alone leaves the owner unable to tell an empty week from one whose list
  // the screen has not drawn.
  if (week.frozen)
    return rows.length === 0 ? `${week.note} ${NO_LIST_SET}` : week.note;
  const stranded = rows.filter((row) => {
    const entry = index[row.menu_item_id];
    return entry === undefined || !entry.item.mapped;
  });
  if (stranded.length > 0) {
    return "A dish on this list has no till name mapped to it any more. Take it off the week, or map a till name to it on the Sales screen.";
  }
  if (rows.length === 0) {
    return "Nothing on this week yet. Pick a dish to push, or leave the week empty - the card still goes out with the month's net sales on it.";
  }
  if (!canSavePushList(rows, branches, index, week)) {
    return "Type a rate per portion and a portion target for every branch.";
  }
  return "The team is paid this rate on every portion above the branch's target.";
}

export const LIST_CAPTION =
  "What the team is asked to push this week, what a portion above target earns, and how many portions each branch is held to.";

// --- the statement ----------------------------------------------------------

/**
 * What a branch has earned so far this month, under the targets that month
 * was created with (M13.5, issue #11).
 *
 * Every figure below is the API's own, derived on the read out of the
 * branch's loaded sales days and stored nowhere (C16). The screen adds
 * nothing up and re-words nothing: the day count, the net sales against
 * target, the pool, each dish's portions against its target and the reason a
 * dish cannot be counted at all are sentences `faida_api/incentive.py`
 * composed, so the screen, the morning card and the statement quote one
 * figure in one set of words. What is decided here is the screen's own: what
 * a figure is called, which rows a month with no cap never draws, and the one
 * word that keeps a half-loaded month from being read as a closed one.
 *
 * The rounding inside the block: the pool is a headline and reads as the API
 * worded it, rounded to whole dirhams like every headline in the product;
 * what the pool is made of - what the push lists earned, what the sales above
 * target earned, the cap, each dish's own earning - is exact to the fil,
 * because this is the detail a payout is read off and a dirham rounded away
 * here is a dirham somebody is short.
 */

/** A figure that stands on its own carries the currency, the way every
 * standalone figure on the shipped screens does; a figure inside a column
 * under a heading does not. Fils-precise, because this is the detail a
 * payout is read off. */
function exact(value: string): string {
  return `AED ${groupedMoney(value)}`;
}

/** "Pool so far" while the month is still being loaded, "Pool" once it is
 * final. Said on each figure that is still moving rather than once at the top
 * of the block: a figure read on its own out of the middle is the one that
 * gets quoted to a team. */
export function soFar(statement: IncentiveStatement, label: string): string {
  return statement.status === "provisional" ? `${label} so far` : label;
}

/** One line of the statement's figures: what it is called and what it says.
 * Both are strings by the time they are here - money is never a number on
 * these screens. `now` is the same figure as the till reads it today, on an
 * approved statement a day was replaced under (D12), and only where it
 * differs from what was approved - the row is otherwise one figure. */
export interface StatementFigure {
  key: string;
  label: string;
  value: string;
  now: string | null;
}

/** The figures' values, keyed the way the rows are, so the approved column
 * and the recomputed one are read with one rule. */
function figureValues(figures: StatementFigures): Record<string, string> {
  const values: Record<string, string> = {
    net: figures.net_words,
    items: exact(figures.items_earned),
    above: exact(figures.net_earned),
    pool: figures.pool_words,
  };
  if (figures.cap !== null) values.cap = exact(figures.cap);
  return values;
}

/**
 * The statement's figures in the order the owner reads them: what the branch
 * sold against its target, the two things the pool is made of, the cap where
 * the month set one, and the pool itself last.
 *
 * A month with no cap draws no cap row - a blank one would read as a cap of
 * nothing, which is the opposite of what an empty cap box means (D8). A cap
 * that has bound says so in its label, because the pool beside it is then the
 * cap and not what the team's portions actually earned; the API's note under
 * the block carries the figure before the cap.
 */
export function statementFigures(
  statement: IncentiveStatement,
): StatementFigure[] {
  const figures = statement.figures;
  const rows: { key: string; label: string }[] = [
    { key: "net", label: soFar(statement, "Net sales") },
    { key: "items", label: "Earned on the push lists" },
    {
      key: "above",
      label: `Earned on sales above target (${plainPct(figures.above_target_pct)}%)`,
    },
  ];
  if (figures.cap !== null) {
    rows.push({ key: "cap", label: figures.capped ? "Cap, reached" : "Cap" });
  }
  rows.push({ key: "pool", label: soFar(statement, "Pool") });
  const values = figureValues(figures);
  const now =
    statement.recomputed === null ? {} : figureValues(statement.recomputed);
  return rows.map(({ key, label }) => ({
    key,
    label,
    value: values[key],
    now: now[key] !== undefined && now[key] !== values[key] ? now[key] : null,
  }));
}

/** One role's share of a final pool: the manager's, the supervisor's and
 * the sales team's amounts each named (D2), exact to the fil, with the share
 * that made it. Nothing on a provisional statement: a split of a pool that
 * is still moving would be three figures somebody gets quoted. */
export function statementSplit(
  statement: IncentiveStatement,
): StatementFigure[] {
  const split = statement.figures.split;
  if (statement.status !== "final" || split === null) return [];
  const amount: Record<ShareRole, string> = {
    manager: split.manager,
    supervisor: split.supervisor,
    sales: split.sales,
  };
  return SHARE_ROLES.map((role) => ({
    key: role,
    label: `${SHARE_LABEL[role]} (${plainPct(split.shares[FIELD[role]])}%)`,
    value: exact(amount[role]),
    now: null,
  }));
}

/** Who closed the month and why, on a final statement: the day and the
 * reason as typed. The actor on the row is the audit trail's user id, which
 * is not a name the owner reads; the audit row keeps it. */
export function approvalWords(statement: IncentiveStatement): string | null {
  const approval = statement.approval;
  if (approval === null) return null;
  return `Approved ${formatDate(approval.approved_at)}: ${approval.reason}`;
}

/** The approval control is drawn only where the API would accept it: a
 * provisional statement with every calendar day loaded (D10). The refusal
 * for anything else is the API's own sentence, so the screen never words
 * one; this only keeps a button off a month with a hole in it. */
export function canApprove(statement: IncentiveStatement): boolean {
  return (
    statement.status === "provisional" &&
    statement.figures.days_loaded === statement.figures.days_in_month
  );
}

/** A reason is typed before the button lights: the door refuses a blank one
 * and this saves the round trip. Whitespace is not a reason. */
export function canSubmitApproval(reason: string): boolean {
  return reason.trim().length > 0;
}

export const APPROVE_CAPTION =
  "Every day of this month is loaded. Approving fixes these figures as what was paid; a day re-uploaded afterwards is shown beside them, never over them.";

export const REASON_LABEL = "Why this month is being paid";

export const APPROVE_LABEL = "Approve this statement";

/** One dish on a scored week: what it sold against its target in the API's
 * words, and what the rate paid on it - or nothing at all, because a dish
 * that cannot be counted has no figure to show and a nought would be read as
 * one (D10). */
export interface StatementItemRow {
  key: string;
  name: string;
  /** "150 of 100 portions", or the sentence saying why it cannot be counted. */
  words: string;
  /** Exact to the fil, or null for a hole. */
  earned: string | null;
  hole: boolean;
}

/** One push week as the statement scored it. */
export interface StatementWeekRow {
  key: string;
  /** "1-5 Jul", the month's own tab label for the same week. */
  label: string;
  /** "3 on the list", or "no push list" for a week the owner left empty. */
  words: string;
  earned: string;
  empty: boolean;
  rows: StatementItemRow[];
}

/**
 * The month's weeks as the statement scored them, in the month's own order.
 *
 * The label comes from the scheme month's own week, which is where the screen
 * gets every other week label: the scored week carries its dates and how many
 * dishes were on it, and a week named two ways on one screen is a week the
 * owner has to match up by eye.
 */
export function statementWeeks(
  scheme: SchemeMonth,
  statement: IncentiveStatement,
): StatementWeekRow[] {
  const labels = new Map(scheme.weeks.map((week) => [week.id, week.words]));
  return statement.figures.weeks.map((week) => ({
    key: week.push_week_id,
    label: labels.get(week.push_week_id) ?? `${week.start} - ${week.end}`,
    words: week.words,
    earned: exact(week.earned),
    empty: week.empty,
    rows: week.items.map((item) => ({
      key: item.push_item_id,
      name: item.name,
      words: item.words,
      earned: item.hole === null ? groupedMoney(item.earned) : null,
      hole: item.hole !== null,
    })),
  }));
}

/** How far into the month the figures were read: the newest day this branch
 * has loaded, or that it has loaded none of it at all. The day count itself
 * is the API's `status_words` beside it - this says which day, so a branch
 * that stopped uploading on the 10th is not read as a branch that sells
 * nothing. */
export function loadedThrough(statement: IncentiveStatement): string {
  if (statement.newest_loaded === null) {
    return "No day of this month is loaded for this branch yet.";
  }
  return `Read up to ${formatDate(statement.newest_loaded)}.`;
}

export const STATEMENT_CAPTION =
  "What each branch has earned so far, read from its loaded days every time this screen opens.";

// --- the per-branch pause (D18, issue #14) -----------------------------------

export const PAUSE_LABEL = "Pause the morning card";
export const RESUME_LABEL = "Send the morning card again";

/** What the control says about a branch's scoreboard, and which way the
 * switch faces. The card goes out at seven in the branch's own timezone,
 * so the running sentence names that timezone; the paused one names the
 * day the owner stopped it. The final card of an approved month is not
 * stopped by the pause, and the sentence says so only when there is
 * something for it to say - the API refuses nothing here, so the screen
 * words nothing but the state. */
export function pauseControl(branch: IncentiveBranch): {
  paused: boolean;
  words: string;
  label: string;
} {
  if (branch.paused_at === null) {
    return {
      paused: false,
      words: `Morning card at 07:00, ${branch.timezone}.`,
      label: PAUSE_LABEL,
    };
  }
  return {
    paused: true,
    words: `Morning card paused since ${formatDate(branch.paused_at)}.`,
    label: RESUME_LABEL,
  };
}

/** The branch a statement is about, for the control drawn on its card. */
export function branchOf(
  read: IncentiveRead,
  statement: IncentiveStatement,
): IncentiveBranch | null {
  return (
    read.branches.find((branch) => branch.id === statement.branch_id) ?? null
  );
}
