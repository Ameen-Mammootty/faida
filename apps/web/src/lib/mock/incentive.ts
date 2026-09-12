/**
 * The staff incentive screen, offline (M13.2 and M13.3, issues #8 and #9,
 * against `GET /api/incentive?month=`, `PUT /api/incentive/shares` and
 * `POST /api/incentive/months`).
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
 * The two doors move the scenario's own rows in module memory, so a save or a
 * create holds across screens for the length of the session and resets on
 * reload - what a demo without the backend needs. Neither refuses anything a
 * product rule would refuse: the screen offers Save and Create only for a form
 * that is finished, and every refusal sentence lives in the Python module the
 * real doors call.
 *
 * The create door is the one place this file substitutes anything into a
 * fixture: the targets the owner typed, echoed back into the generated
 * `created` payload. It is echoing input, never computing a figure - the month
 * it can create is the one the fixture carries, and any other month is
 * refused as the limit of an offline mock rather than as a rule of the
 * product.
 */

import complete from "./incentive/complete.json";
import created from "./incentive/created.json";
import empty from "./incentive/empty.json";
import final from "./incentive/final.json";
import full from "./incentive/full.json";
import noshares from "./incentive/noshares.json";
import { ApiError } from "../errors";
import { monthWords } from "../incentiveScreen";
import type {
  IncentiveRead,
  IncentiveResult,
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
  const schemeMonth = CREATED[scenario] ?? payload.scheme_month;
  const read: IncentiveResult = {
    ...payload,
    shares: saved ?? payload.shares,
    scheme_month: schemeMonth,
    months:
      CREATED[scenario] === undefined
        ? payload.months
        : [
            { id: schemeMonth!.id, month: schemeMonth!.month, words: schemeMonth!.words },
            ...payload.months.filter((option) => option.month !== schemeMonth!.month),
          ],
  };
  // A month the fixture does not carry has no scheme month, which is what the
  // API answers for a month nothing was created for.
  if (month !== undefined && month !== read.month) {
    return {
      ...read,
      month,
      month_words: monthWords(month),
      scheme_month: read.scheme_month?.month === month ? read.scheme_month : null,
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

export async function mockSetRoleShares(body: RoleShares): Promise<IncentiveRead> {
  await new Promise((resolve) => setTimeout(resolve, LATENCY_MS));
  const scenario = scenarioFromLocation();
  if (scenario === "error") {
    throw new ApiError(503, "The shares could not be saved. Try again in a minute.");
  }
  SAVED[scenario] = {
    manager_pct: stored(body.manager_pct),
    supervisor_pct: stored(body.supervisor_pct),
    sales_pct: stored(body.sales_pct),
    updated_at: new Date().toISOString(),
  };
  return payloadFor(scenario);
}

export async function mockCreateSchemeMonth(body: SchemeMonthInput): Promise<IncentiveRead> {
  await new Promise((resolve) => setTimeout(resolve, LATENCY_MS));
  const scenario = scenarioFromLocation();
  if (scenario === "error") {
    throw new ApiError(503, "The month could not be created. Try again in a minute.");
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
