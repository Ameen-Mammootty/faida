/**
 * The staff incentive screen, offline (M13.2 to M13.5, issues #8 to #11,
 * against `GET /api/incentive?month=`, `PUT /api/incentive/shares`,
 * `POST /api/incentive/months` and `PUT /api/incentive/weeks/{id}`).
 *
 * Every figure here is written out, never computed - the `mock/dashboard.ts`
 * rule. The literals in `./incentive/*.json` are produced by running the
 * shipped pure module (`faida_api/incentive.py`) over three sample branches
 * and the sample menu (`./incentive/generate.py`), one payload per scenario;
 * this file picks a scenario and returns the literal. Nothing is scored,
 * pooled or split in TypeScript.
 *
 * Named scenarios, reachable by URL for QA and design reviews:
 * `?scenario=full|final|complete|empty|noshares|error`, read **here** from
 * `window.location` and nowhere else - `api.ts` and the component never see
 * the word - lazily at fetch time, guarded for the server, defaulting to
 * `full`.
 *
 *   full      September 2026 under way on 16 Sep: the shares set, a month
 *             created, the week of 14-20 Sep in view
 *   final     August 2026 approved for every branch
 *   complete  August 2026 fully loaded and nothing approved yet
 *   created   September 2026 the moment it is created: five empty weeks
 *   empty     the shares are set and no scheme month exists yet
 *   noshares  nothing is set at all - the screen's first run
 *   error     the read fails
 *
 * The three doors move the scenario's own rows in module memory, so a save, a
 * create or a filled week holds across screens for the length of the session
 * and resets on reload - what a demo without the backend needs. None refuses
 * anything a product rule would refuse: the screen offers Save and Create only
 * for a form that is finished, and every refusal sentence lives in the Python
 * module the real doors call.
 *
 * The statements a scenario carries are scored figures, and this file will
 * not score: a week's list saved here therefore moves the list and leaves the
 * statement under it as the fixture wrote it. The real read derives both out
 * of one request and cannot disagree with itself (C16); offline, the list is
 * the thing being designed and the statement beside it is a still.
 *
 * The create and push-list doors are the two places this file substitutes
 * anything into a fixture: the targets, rates and portion targets the owner
 * typed, and - for a saved list - each dish's own name, category and kept
 * figure copied verbatim out of the same payload's menu block, which the
 * Python module wrote. Both are echoing input, never computing a figure. The
 * month the create door can lay out is the one the fixture carries, and any
 * other month is refused as the limit of an offline mock rather than as a
 * rule of the product.
 */

import complete from "./incentive/complete.json";
import created from "./incentive/created.json";
import empty from "./incentive/empty.json";
import final from "./incentive/final.json";
import full from "./incentive/full.json";
import noshares from "./incentive/noshares.json";
import { ApiError } from "../errors";
import { groupLikeMenu, monthWords } from "../incentiveScreen";
import type {
  IncentiveMenuItem,
  IncentiveRead,
  IncentiveResult,
  PushItem,
  PushListInput,
  PushWeek,
  RoleShares,
  RoleSharesRow,
  SchemeMonth,
  SchemeMonthInput,
} from "../types";

export const SCENARIOS = [
  "full",
  "final",
  "complete",
  "created",
  "empty",
  "noshares",
  "error",
] as const;
export type Scenario = (typeof SCENARIOS)[number];
export const DEFAULT_SCENARIO: Scenario = "full";

const DATA: Record<Exclude<Scenario, "error">, IncentiveResult> = {
  full: full as unknown as IncentiveResult,
  final: final as unknown as IncentiveResult,
  complete: complete as unknown as IncentiveResult,
  created: created as unknown as IncentiveResult,
  empty: empty as unknown as IncentiveResult,
  noshares: noshares as unknown as IncentiveResult,
};

/** The month the `created` fixture carries: the only month this offline mock
 * can lay push weeks out for, because laying them out is arithmetic and the
 * mock computes nothing. */
const CREATABLE_MONTH = (created as unknown as IncentiveResult).month;

const LATENCY_MS = 120;

/** What the shares door has moved this session, per scenario. */
const SAVED: Partial<Record<Scenario, RoleSharesRow>> = {};

/** What the create door has moved this session, per scenario. */
const CREATED: Partial<Record<Scenario, SchemeMonth>> = {};

/** What the push-list door has moved this session: the week's list, by week
 * id, per scenario. */
const LISTS: Partial<Record<Scenario, Record<string, PushItem[]>>> = {};

function isScenario(value: string | null): value is Scenario {
  return value !== null && (SCENARIOS as readonly string[]).includes(value);
}

/** Read lazily, at fetch time, and never on the server. */
function scenarioFromLocation(): Scenario {
  if (typeof window === "undefined") return DEFAULT_SCENARIO;
  const value = new URLSearchParams(window.location.search).get("scenario");
  return isScenario(value) ? value : DEFAULT_SCENARIO;
}

function payloadFor(scenario: Scenario, month?: string): IncentiveResult {
  if (scenario === "error") {
    throw new ApiError(
      503,
      "The incentive could not be read: the sales tables are being reloaded. Try again in a minute.",
    );
  }
  const payload = DATA[scenario];
  const saved = SAVED[scenario];
  const schemeMonth = withLists(
    CREATED[scenario] ?? payload.scheme_month,
    payload,
    scenario,
  );
  const read: IncentiveResult = {
    ...payload,
    shares: saved ?? payload.shares,
    scheme_month: schemeMonth,
    months:
      CREATED[scenario] === undefined
        ? payload.months
        : [
            {
              id: schemeMonth!.id,
              month: schemeMonth!.month,
              words: schemeMonth!.words,
            },
            ...payload.months.filter(
              (option) => option.month !== schemeMonth!.month,
            ),
          ],
  };
  // A month the fixture does not carry has no scheme month, which is what the
  // API answers for a month nothing was created for.
  if (month !== undefined && month !== read.month) {
    return {
      ...read,
      month,
      month_words: monthWords(month),
      scheme_month:
        read.scheme_month?.month === month ? read.scheme_month : null,
    };
  }
  return read;
}

export async function mockGetIncentive(month?: string): Promise<IncentiveRead> {
  await new Promise((resolve) => setTimeout(resolve, LATENCY_MS));
  return payloadFor(scenarioFromLocation(), month);
}

/** Two decimals, the way `numeric(5,2)` comes back off the wire. */
function stored(value: string): string {
  return Number(value).toFixed(2);
}

export async function mockSetRoleShares(
  body: RoleShares,
): Promise<IncentiveRead> {
  await new Promise((resolve) => setTimeout(resolve, LATENCY_MS));
  const scenario = scenarioFromLocation();
  if (scenario === "error") {
    throw new ApiError(
      503,
      "The shares could not be saved. Try again in a minute.",
    );
  }
  SAVED[scenario] = {
    manager_pct: stored(body.manager_pct),
    supervisor_pct: stored(body.supervisor_pct),
    sales_pct: stored(body.sales_pct),
    updated_at: new Date().toISOString(),
  };
  return payloadFor(scenario);
}

export async function mockCreateSchemeMonth(
  body: SchemeMonthInput,
): Promise<IncentiveRead> {
  await new Promise((resolve) => setTimeout(resolve, LATENCY_MS));
  const scenario = scenarioFromLocation();
  if (scenario === "error") {
    throw new ApiError(
      503,
      "The month could not be created. Try again in a minute.",
    );
  }
  if (body.month !== CREATABLE_MONTH) {
    throw new ApiError(
      422,
      `Offline, only ${monthWords(CREATABLE_MONTH)} can be created: the mock serves written-out payloads and does not lay out a month's weeks itself.`,
    );
  }
  const fixture = (created as unknown as IncentiveResult).scheme_month!;
  CREATED[scenario] = {
    ...fixture,
    // The one substitution: what the owner typed, echoed back the way the row
    // would hold it. Two decimals is what `numeric(12,2)` and `numeric(5,2)`
    // come back as off the wire.
    targets: body.targets.map((target) => ({
      branch_id: target.branch_id,
      net_sales_target: stored(target.net_sales_target),
      above_target_pct: stored(target.above_target_pct),
      cap: target.cap === null || target.cap === "" ? null : stored(target.cap),
    })),
  };
  return payloadFor(scenario, body.month);
}

/** The month with whatever the push-list door has moved this session laid
 * over it: the weeks the owner has filled, and the fixture's own for the
 * rest. */
function withLists(
  scheme: SchemeMonth | null,
  payload: IncentiveResult,
  scenario: Scenario,
): SchemeMonth | null {
  const lists = LISTS[scenario];
  if (scheme === null || lists === undefined) return scheme;
  return {
    ...scheme,
    weeks: scheme.weeks.map((week) => {
      const items = lists[week.id];
      return items === undefined ? week : filled(week, items, payload);
    }),
  };
}

function filled(
  week: PushWeek,
  items: PushItem[],
  payload: IncentiveResult,
): PushWeek {
  return {
    ...week,
    items,
    categories: groupLikeMenu(
      items,
      (item) => categoryOf(item.menu_item_id, payload),
      payload.menu,
    ),
  };
}

/** The category the read filed a dish under - `Other` for one the menu gives
 * none. Read off the payload rather than off the item's own field, so the
 * word `Other` is spelt once, in Python. */
function categoryOf(menuItemId: string, payload: IncentiveResult): string {
  const group = payload.menu.find((entry) =>
    entry.items.some((item) => item.id === menuItemId),
  );
  return group?.category ?? "Other";
}

function menuItemOf(
  menuItemId: string,
  payload: IncentiveResult,
): IncentiveMenuItem | undefined {
  for (const group of payload.menu) {
    const found = group.items.find((item) => item.id === menuItemId);
    if (found !== undefined) return found;
  }
  return undefined;
}

/** Three decimals, the way `numeric(12,3)` comes back off the wire. */
function portions(value: string): string {
  return Number(value).toFixed(3);
}

/**
 * The push-list door, offline: the week's list replaced by what the owner
 * typed.
 *
 * The second place this file substitutes anything into a fixture, and for the
 * create door's reason: every field of a saved item is either the owner's own
 * input - the rate and the targets - or the dish's own fields copied verbatim
 * out of the same payload's menu block, which the Python module wrote. Nothing
 * is scored, costed or worded here. The order is the API's, by dish name.
 */
export async function mockSetPushList(
  weekId: string,
  body: PushListInput,
): Promise<IncentiveRead> {
  await new Promise((resolve) => setTimeout(resolve, LATENCY_MS));
  const scenario = scenarioFromLocation();
  if (scenario === "error") {
    throw new ApiError(
      503,
      "The list could not be saved. Try again in a minute.",
    );
  }
  const payload = DATA[scenario];
  const items: PushItem[] = body.items
    .map((item, index) => {
      const dish = menuItemOf(item.menu_item_id, payload);
      return {
        id: `pi-${weekId}-${index + 1}`,
        menu_item_id: item.menu_item_id,
        name: dish?.name ?? item.menu_item_id,
        category: dish?.category ?? null,
        rate_per_portion: stored(item.rate_per_portion),
        kept_per_plate: dish?.kept_per_plate ?? null,
        kept_words: dish?.kept_words ?? "not costed",
        hole: null,
        targets: item.targets.map((target) => ({
          branch_id: target.branch_id,
          portion_target: portions(target.portion_target),
        })),
      };
    })
    .sort((left, right) => left.name.localeCompare(right.name));
  LISTS[scenario] = { ...(LISTS[scenario] ?? {}), [weekId]: items };
  return payloadFor(scenario);
}
