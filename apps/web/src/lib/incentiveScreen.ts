/**
 * The pure decisions behind the `/incentive` screen - every sentence and every
 * enabling rule the component renders, kept out of React so vitest pins them
 * (the `dashboardScreen.ts` rule: a choice left inside a component would be
 * untested by construction).
 *
 * Two blocks so far: the role shares that split a pool (M13.2, issue #8) and
 * the scheme month with its per-branch targets and its push weeks (M13.3,
 * issue #9).
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
  IncentiveRead,
  PushWeek,
  RoleShares,
  RoleSharesRow,
  SchemeMonth,
  SchemeMonthInput,
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
  if (scaled === null) return "Three percentages, adding to 100, split the pool.";
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
export function canSaveShares(draft: ShareDraft, saved: RoleSharesRow | null): boolean {
  const scaled = drafted(draft);
  if (scaled === null) return false;
  if (scaled.some((value) => value < 0)) return false;
  if (total(scaled) !== WHOLE_POOL) return false;
  if (saved === null) return true;
  // Sending the same three shares again would write a row and an audit line
  // that record nothing.
  return SHARE_ROLES.some((role, index) => scaled[index] !== hundredths(saved[FIELD[role]]));
}

// --- the block's own words --------------------------------------------------

/** The heading's second line: what the shares are for. */
export const SHARES_CAPTION = "How a month's pool is split between the people who earned it.";

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
    .map((month) => ({ month, words: monthWords(month), created: created.has(month) }));
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
export function canCreateMonth(drafts: TargetDrafts, branches: IncentiveBranch[]): boolean {
  if (branches.length === 0) return false;
  return branches.every((branch) => {
    const draft = drafts[branch.id];
    return draft !== undefined && typed(draft.net) && typed(draft.pct);
  });
}

/** The wire body of the create door: the strings as typed, trimmed, with a
 * blank cap sent as no cap. */
export function schemeMonthBody(month: string, drafts: TargetDrafts, branches: IncentiveBranch[]): SchemeMonthInput {
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
export function createStanding(drafts: TargetDrafts, branches: IncentiveBranch[]): string {
  if (branches.length === 0) return "This chain has no branches to set targets for.";
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

/**
 * The month's weeks as the screen's tabs. A week that has started is frozen
 * and says why in the API's own sentence (D5); a week still coming may be
 * re-aimed, and until it has a list says so.
 *
 * Every week is empty in this ticket - the push lists land in the next one -
 * so the note is the same for every coming week today. It is written against
 * `items` rather than against the ticket, so it stops saying so on its own.
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
