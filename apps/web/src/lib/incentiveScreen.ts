/**
 * M13.2 (issue #8): the pure decisions behind the `/incentive` screen - every
 * sentence and every enabling rule the component renders, kept out of React so
 * vitest pins them (the `dashboardScreen.ts` rule: a choice left inside a
 * component would be untested by construction).
 *
 * This ticket is the role shares block. The screen never words a refusal: the
 * three shares are refused by `faida_api/incentive.py`'s `shares_problem` and
 * the API returns that sentence, so a refusal is written once in the whole
 * product. What lives here is the running total the owner watches while
 * typing, and the rule that Save is offered only when the three shares are
 * three percentages adding to a hundred - the same condition, decided by the
 * form rather than worded by it.
 */

import { formatDate } from "./format";
import type { RoleShares, RoleSharesRow } from "./types";

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

/** The screen's first sentence: what the owner should do next on it. This
 * ticket has one block, so there is one thing to say. */
export function sharesStanding(shares: RoleSharesRow | null): string {
  if (shares === null) {
    return "Set the three shares first: every scheme month is created with the shares in force that day.";
  }
  return "The shares are set. A scheme month can be created against them.";
}
