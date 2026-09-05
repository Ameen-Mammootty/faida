/**
 * The owner dashboard, offline (M9 WP-93 against WP-92's `GET /api/dashboard`,
 * Docs/M9_DECOMPOSITION.md §3.1).
 *
 * Every figure here is written out, never computed - the `mock/menu.ts` rule,
 * because a second implementation of the money in a demo mock is what
 * plan.md §2 rule 3 refuses. The literals in `./dashboard/*.json` were
 * produced by running the shipped Python modules (`contribution.py`,
 * `signals.py`, `ratio.py`, `plates.py`) over a hand-built week of the three
 * sample branches and the sample menu, one payload per scope (the chain and
 * each branch), then written out; this file picks a scenario and a scope and
 * returns the literal. Nothing is summed, divided or ranked in TypeScript.
 *
 * Named scenarios, reachable by URL for QA and design reviews (second review,
 * D11): `?scenario=full|partial|quiet|empty|nomenu|error`, read **here** from
 * `window.location` and nowhere else - `api.ts` and the component never see
 * the word - lazily at fetch time, guarded for the server, defaulting to
 * `full`, so the first paint and the client agree.
 *
 *   full     three branches, a week each; a branch keeping less than the
 *            chain; an item sold at a discount on an estimated plate; an item
 *            that loses money; two dishes that cannot be costed; five signals
 *            (the cap); three till names with no dish; two papers waiting
 *   partial  one branch never loaded, one missing a day (incomplete), sales
 *            twelve days old (the freshness word), a price spike in the list
 *   quiet    the tea menu, every plate reliable, every paper confirmed,
 *            nothing moved: no signals, no papers, every name mapped
 *   empty    the menu exists and nothing was ever loaded (first run)
 *   nomenu   a week loaded and no menu at all
 *   error    the read fails
 */

import empty from "./dashboard/empty.json";
import full from "./dashboard/full.json";
import nomenu from "./dashboard/nomenu.json";
import partial from "./dashboard/partial.json";
import quiet from "./dashboard/quiet.json";
import { ApiError } from "../errors";
import { daysInclusive } from "../dashboardScreen";
import type { DashboardResult } from "../types";

export const SCENARIOS = ["full", "partial", "quiet", "empty", "nomenu", "error"] as const;
export type Scenario = (typeof SCENARIOS)[number];
export const DEFAULT_SCENARIO: Scenario = "full";

/** One payload per scope: "" is the chain, "br-01" and so on each branch. */
type ScopeMap = Record<string, DashboardResult>;

const DATA: Record<Exclude<Scenario, "error">, ScopeMap> = {
  full: full as unknown as ScopeMap,
  partial: partial as unknown as ScopeMap,
  quiet: quiet as unknown as ScopeMap,
  empty: empty as unknown as ScopeMap,
  nomenu: nomenu as unknown as ScopeMap,
};

const LATENCY_MS = 120;

function isScenario(value: string | null): value is Scenario {
  return value !== null && (SCENARIOS as readonly string[]).includes(value);
}

/** Read lazily, at fetch time, and never on the server. */
function scenarioFromLocation(): Scenario {
  if (typeof window === "undefined") return DEFAULT_SCENARIO;
  const value = new URLSearchParams(window.location.search).get("scenario");
  return isScenario(value) ? value : DEFAULT_SCENARIO;
}

export async function mockGetDashboard(
  from?: string,
  to?: string,
  branchId?: string,
): Promise<DashboardResult> {
  await new Promise((resolve) => setTimeout(resolve, LATENCY_MS));
  const scenario = scenarioFromLocation();
  if (scenario === "error") {
    throw new ApiError(
      503,
      "The dashboard could not be read: the sales tables are being reloaded. Try again in a minute.",
    );
  }
  const payload = DATA[scenario][branchId ?? ""];
  if (payload === undefined) throw new ApiError(404, "No such branch.");
  if (from && to) {
    // A chosen range: the fixture's figures stand, the period block says
    // what was asked for. Dates, not money.
    return {
      ...payload,
      period: { ...payload.period, from, to, days: daysInclusive(from, to), default: false },
    };
  }
  return payload;
}
