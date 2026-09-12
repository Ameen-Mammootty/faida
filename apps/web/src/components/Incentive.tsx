"use client";

import { useEffect, useState } from "react";
import { createSchemeMonth, getIncentive, setRoleShares } from "@/lib/api";
import { groupedMoney } from "@/lib/format";
import {
  MONTH_CAPTION,
  MONTH_FROZEN_NOTE,
  SHARES_APPLIES_NOTE,
  SHARES_CAPTION,
  SHARE_LABEL,
  SHARE_ROLES,
  WEEKS_CAPTION,
  canCreateMonth,
  canSaveShares,
  capWords,
  createStanding,
  monthOptions,
  schemeMonthBody,
  shareBody,
  shareDraft,
  sharesUpdatedWords,
  standing,
  sumWords,
  targetDrafts,
  targetOf,
  weekInView,
  weekTabs,
  type ShareDraft,
  type TargetDrafts,
} from "@/lib/incentiveScreen";
import type { IncentiveRead } from "@/lib/types";

/**
 * The staff incentive screen, sixth in the shell: the three role shares that
 * split a month's pool (M13.2, D2), and the scheme month the team is scored
 * and paid on - a net sales target, a percentage of sales above it and an
 * optional cap per branch, with the month's push weeks laid out Monday to
 * Sunday clipped to the month (M13.3, D3 to D5).
 *
 * Every choice this renders is decided in `lib/incentiveScreen.ts` and pinned
 * by vitest there - the dashboard's rule, because a choice left inside a
 * component would be untested by construction. Nothing here words a refusal:
 * a door is offered only for a form that is finished, and a refusal that gets
 * past that is the API's own sentence, shown as it came.
 *
 * The push lists inside those week tabs and each branch's statement land in
 * the tickets that follow, out of this same one read.
 */
export default function Incentive() {
  const [read, setRead] = useState<IncentiveRead | null>(null);
  const [month, setMonth] = useState<string | null>(null);
  const [draft, setDraft] = useState<ShareDraft>(shareDraft(null));
  const [targets, setTargets] = useState<TargetDrafts>({});
  const [week, setWeek] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [creating, setCreating] = useState(false);
  // Try again is a bump of this, so the one effect below is the only place
  // that reads - the shipped Dashboard's pattern, and what keeps the
  // cancelled guard on every read rather than on the first one.
  const [reloadKey, setReloadKey] = useState(0);
  const [feedback, setFeedback] = useState<{ kind: "error" | "done"; text: string } | null>(null);

  function landed(result: IncentiveRead) {
    setRead(result);
    setDraft(shareDraft(result.shares));
    setTargets(targetDrafts(result.branches));
    setWeek(null);
    setLoadError(null);
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const result = await getIncentive(month ?? undefined);
        if (cancelled) return;
        landed(result);
      } catch (error) {
        if (cancelled) return;
        setLoadError(error instanceof Error ? error.message : "Could not load the incentive.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reloadKey, month]);

  async function saveShares() {
    setSaving(true);
    setFeedback(null);
    try {
      landed(await setRoleShares(shareBody(draft)));
      setFeedback({ kind: "done", text: "The shares are saved." });
    } catch (error) {
      setFeedback({
        kind: "error",
        text: error instanceof Error ? error.message : "That did not work.",
      });
    } finally {
      setSaving(false);
    }
  }

  async function create() {
    if (read === null) return;
    setCreating(true);
    setFeedback(null);
    try {
      const result = await createSchemeMonth(schemeMonthBody(read.month, targets, read.branches));
      landed(result);
      setFeedback({ kind: "done", text: `${result.month_words} is set.` });
    } catch (error) {
      setFeedback({
        kind: "error",
        text: error instanceof Error ? error.message : "That did not work.",
      });
    } finally {
      setCreating(false);
    }
  }

  if (loading) {
    return (
      <p role="status" aria-live="polite" className="text-sm text-stone">
        Loading the incentive
      </p>
    );
  }

  if (loadError !== null || read === null) {
    return (
      <div className="space-y-3">
        <p className="max-w-3xl text-base leading-relaxed text-ink">
          {loadError ?? "Could not load the incentive."}
        </p>
        <button
          type="button"
          onClick={() => {
            setLoading(true);
            setLoadError(null);
            setReloadKey((key) => key + 1);
          }}
          className="min-h-11 rounded-sm border border-palm/30 px-3 py-2 text-sm font-medium text-palm hover:border-palm"
        >
          Try again
        </button>
      </div>
    );
  }

  const scheme = read.scheme_month;
  const tabs = scheme === null ? [] : weekTabs(scheme.weeks, read.today);
  const openWeek = week ?? weekInView(tabs);
  const note = tabs.find((tab) => tab.id === openWeek)?.note ?? null;

  return (
    <div className="space-y-8">
      <p className="max-w-3xl text-base leading-relaxed text-ink">{standing(read)}</p>

      {/* --- the role shares -------------------------------------------- */}
      <section aria-labelledby="shares-heading" className="space-y-4">
        <div className="space-y-1">
          <h2 id="shares-heading" className="text-sm font-semibold text-ink">
            Role shares
          </h2>
          <p className="max-w-2xl text-sm text-stone">{SHARES_CAPTION}</p>
        </div>

        <div className="max-w-2xl space-y-4 rounded-md border border-ink/10 bg-paper p-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {SHARE_ROLES.map((role) => (
              <label key={role} className="flex flex-col gap-1 text-xs font-medium text-ink">
                {SHARE_LABEL[role]}
                <span className="flex items-center gap-1">
                  <input
                    type="text"
                    inputMode="decimal"
                    value={draft[role]}
                    onChange={(event) => {
                      setFeedback(null);
                      setDraft({ ...draft, [role]: event.target.value });
                    }}
                    aria-label={`${SHARE_LABEL[role]} share, percent`}
                    className="min-h-11 w-full rounded-sm border border-ink/20 bg-paper px-3 text-sm text-ink"
                  />
                  <span aria-hidden="true" className="text-sm text-stone">
                    %
                  </span>
                </span>
              </label>
            ))}
          </div>

          <p role="status" aria-live="polite" className="text-sm text-stone">
            {sumWords(draft)}
          </p>

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              disabled={!canSaveShares(draft, read.shares) || saving}
              onClick={() => void saveShares()}
              className="min-h-11 rounded-sm bg-palm px-4 py-2 text-sm font-medium text-cream disabled:opacity-60"
            >
              {saving ? "Saving" : "Save shares"}
            </button>
            <p className="text-xs text-stone">{sharesUpdatedWords(read.shares)}</p>
          </div>

          <p className="max-w-xl text-xs leading-relaxed text-stone">{SHARES_APPLIES_NOTE}</p>
        </div>
      </section>

      {/* --- the scheme month ------------------------------------------- */}
      <section aria-labelledby="month-heading" className="max-w-3xl space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
          <div className="space-y-1">
            <h2 id="month-heading" className="text-sm font-semibold text-ink">
              Scheme month
            </h2>
            <p className="max-w-md text-sm text-stone">{MONTH_CAPTION}</p>
          </div>
          <label className="flex flex-col gap-1 text-xs font-medium text-ink">
            Month
            <select
              value={read.month}
              onChange={(event) => {
                setFeedback(null);
                setLoading(true);
                setMonth(event.target.value);
              }}
              className="min-h-11 rounded-sm border border-ink/20 bg-paper px-3 text-sm text-ink"
            >
              {monthOptions(read).map((option) => (
                <option key={option.month} value={option.month}>
                  {option.words}
                  {option.created ? "" : " - not set"}
                </option>
              ))}
            </select>
          </label>
        </div>

        {read.shares === null ? (
          <p className="text-sm text-stone">
            Set the three shares above first: a month is created with the shares in force that day.
          </p>
        ) : scheme === null ? (
          <div className="space-y-6 rounded-md border border-ink/10 bg-paper p-4">
            {/* One block per branch rather than one table row: three boxes and
                a line of advice do not fit a phone's four columns, and a form
                that scrolls sideways is a form half of which is not read. */}
            {read.branches.map((branch) => {
              const row = targets[branch.id] ?? { net: "", pct: "", cap: "" };
              const set = (field: "net" | "pct" | "cap", value: string) => {
                setFeedback(null);
                setTargets({ ...targets, [branch.id]: { ...row, [field]: value } });
              };
              return (
                // Spacing and not a rule between the branches: a `legend`
                // renders inside its `fieldset`'s border and cuts it, which
                // left the second branch's name sitting on a two-pixel stub of
                // a line.
                <fieldset key={branch.id} className="space-y-2">
                  <legend className="pb-1 text-sm font-semibold text-ink">{branch.name}</legend>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <label className="flex flex-col gap-1 text-xs font-medium text-ink">
                      Net sales target
                      <input
                        type="text"
                        inputMode="decimal"
                        value={row.net}
                        onChange={(event) => set("net", event.target.value)}
                        aria-label={`${branch.name} net sales target`}
                        aria-describedby={`advice-${branch.id}`}
                        className="min-h-11 w-full rounded-sm border border-ink/20 bg-paper px-3 text-sm text-ink"
                      />
                      <span id={`advice-${branch.id}`} className="text-xs font-normal text-stone">
                        {branch.previous_month_words}
                      </span>
                    </label>
                    <label className="flex flex-col gap-1 text-xs font-medium text-ink">
                      % of sales above it
                      <input
                        type="text"
                        inputMode="decimal"
                        value={row.pct}
                        onChange={(event) => set("pct", event.target.value)}
                        aria-label={`${branch.name} percentage of net sales above target`}
                        className="min-h-11 w-full rounded-sm border border-ink/20 bg-paper px-3 text-sm text-ink"
                      />
                    </label>
                    <label className="flex flex-col gap-1 text-xs font-medium text-ink">
                      Cap (optional)
                      <input
                        type="text"
                        inputMode="decimal"
                        value={row.cap}
                        onChange={(event) => set("cap", event.target.value)}
                        aria-label={`${branch.name} cap`}
                        className="min-h-11 w-full rounded-sm border border-ink/20 bg-paper px-3 text-sm text-ink"
                      />
                    </label>
                  </div>
                </fieldset>
              );
            })}

            <div className="space-y-3 border-t border-ink/10 pt-4">
              <p role="status" aria-live="polite" className="text-sm text-stone">
                {createStanding(targets, read.branches)}
              </p>
              <button
                type="button"
                disabled={!canCreateMonth(targets, read.branches) || creating}
                onClick={() => void create()}
                className="min-h-11 rounded-sm bg-palm px-4 py-2 text-sm font-medium text-cream disabled:opacity-60"
              >
                {creating ? "Creating" : `Create ${read.month_words}`}
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-4 rounded-md border border-ink/10 bg-paper p-4">
            <table className="w-full text-sm">
              <caption className="sr-only">Targets for {scheme.words}, one row per branch</caption>
              <thead>
                <tr className="text-left text-xs font-medium text-stone">
                  <th scope="col" className="pb-2 pr-3">
                    Branch
                  </th>
                  <th scope="col" className="pb-2 pr-3 text-right">
                    Net sales target
                  </th>
                  <th scope="col" className="pb-2 pr-3 text-right">
                    % above it
                  </th>
                  <th scope="col" className="pb-2 text-right">
                    Cap
                  </th>
                </tr>
              </thead>
              <tbody>
                {read.branches.map((branch) => {
                  const target = targetOf(scheme, branch.id);
                  return (
                    <tr key={branch.id} className="border-t border-ink/10">
                      <th scope="row" className="py-2 pr-3 text-left font-medium text-ink">
                        {branch.name}
                      </th>
                      <td className="py-2 pr-3 text-right tabular-nums text-ink">
                        {target === null ? "No target" : groupedMoney(target.net_sales_target)}
                      </td>
                      <td className="py-2 pr-3 text-right tabular-nums text-ink">
                        {target === null ? "-" : `${target.above_target_pct}%`}
                      </td>
                      <td className="py-2 text-right tabular-nums text-ink">{capWords(target)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            <p className="text-xs leading-relaxed text-stone">{MONTH_FROZEN_NOTE}</p>

            <div className="space-y-2 border-t border-ink/10 pt-4">
              <h3 className="text-sm font-semibold text-ink">Push weeks</h3>
              <p className="text-sm text-stone">{WEEKS_CAPTION}</p>
              <div role="tablist" aria-label="Push weeks" className="flex flex-wrap gap-2 pt-1">
                {tabs.map((tab) => (
                  <button
                    key={tab.id}
                    type="button"
                    role="tab"
                    aria-selected={tab.id === openWeek}
                    onClick={() => setWeek(tab.id)}
                    className={`min-h-11 rounded-sm border px-3 py-2 text-sm ${
                      tab.id === openWeek
                        ? "border-palm bg-palm/10 font-medium text-ink"
                        : "border-ink/20 text-stone hover:border-palm/50"
                    }`}
                  >
                    {tab.label}
                    {tab.state === "running" ? (
                      <span className="pl-1.5 text-xs text-palm">this week</span>
                    ) : null}
                  </button>
                ))}
              </div>
              {note === null ? null : (
                <p role="status" aria-live="polite" className="pt-1 text-sm text-stone">
                  {note}
                </p>
              )}
            </div>
          </div>
        )}

        {feedback !== null ? (
          <p
            role="status"
            aria-live="polite"
            className={`rounded-sm border px-3 py-2 text-sm ${
              feedback.kind === "error"
                ? "border-plum/40 bg-paper text-ink"
                : "border-palm/30 bg-paper text-ink"
            }`}
          >
            <span className="font-medium">{feedback.kind === "error" ? "Not done: " : "Done. "}</span>
            {feedback.text}
          </p>
        ) : null}
      </section>
    </div>
  );
}
