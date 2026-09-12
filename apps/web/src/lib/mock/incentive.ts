/**
 * The staff incentive screen, offline (M13.2, issue #8, against
 * `GET /api/incentive` and `PUT /api/incentive/shares`).
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
 *   empty     the shares are set and no scheme month exists yet
 *   noshares  nothing is set at all - the screen's first run
 *   error     the read fails
 *
 * The shares door moves the scenario's own shares in module memory, so a save
 * holds across screens for the length of the session and resets on reload -
 * what a demo without the backend needs. It refuses nothing: the screen
 * offers Save only for three percentages adding to a hundred, and the one
 * refusal sentence lives in the Python module the real door calls.
 */

import complete from "./incentive/complete.json";
import empty from "./incentive/empty.json";
import final from "./incentive/final.json";
import full from "./incentive/full.json";
import noshares from "./incentive/noshares.json";
import { ApiError } from "../errors";
import type { IncentiveResult, RoleShares, RoleSharesRow } from "../types";

export const SCENARIOS = ["full", "final", "complete", "empty", "noshares", "error"] as const;
export type Scenario = (typeof SCENARIOS)[number];
export const DEFAULT_SCENARIO: Scenario = "full";

const DATA: Record<Exclude<Scenario, "error">, IncentiveResult> = {
  full: full as unknown as IncentiveResult,
  final: final as unknown as IncentiveResult,
  complete: complete as unknown as IncentiveResult,
  empty: empty as unknown as IncentiveResult,
  noshares: noshares as unknown as IncentiveResult,
};

const LATENCY_MS = 120;

/** What the shares door has moved this session, per scenario. */
const SAVED: Partial<Record<Scenario, RoleSharesRow>> = {};

function isScenario(value: string | null): value is Scenario {
  return value !== null && (SCENARIOS as readonly string[]).includes(value);
}

/** Read lazily, at fetch time, and never on the server. */
function scenarioFromLocation(): Scenario {
  if (typeof window === "undefined") return DEFAULT_SCENARIO;
  const value = new URLSearchParams(window.location.search).get("scenario");
  return isScenario(value) ? value : DEFAULT_SCENARIO;
}

function payloadFor(scenario: Scenario): IncentiveResult {
  if (scenario === "error") {
    throw new ApiError(
      503,
      "The incentive could not be read: the sales tables are being reloaded. Try again in a minute.",
    );
  }
  const payload = DATA[scenario];
  const saved = SAVED[scenario];
  return saved === undefined ? payload : { ...payload, shares: saved };
}

export async function mockGetIncentive(): Promise<IncentiveResult> {
  await new Promise((resolve) => setTimeout(resolve, LATENCY_MS));
  return payloadFor(scenarioFromLocation());
}

/** Two decimals, the way `numeric(5,2)` comes back off the wire. */
function stored(value: string): string {
  return Number(value).toFixed(2);
}

export async function mockSetRoleShares(body: RoleShares): Promise<IncentiveResult> {
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
