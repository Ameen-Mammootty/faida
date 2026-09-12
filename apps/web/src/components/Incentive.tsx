"use client";

import { useEffect, useState } from "react";
import {
  createSchemeMonth,
  getIncentive,
  setPushList,
  setRoleShares,
} from "@/lib/api";
import { groupedMoney } from "@/lib/format";
import {
  LIST_CAPTION,
  MONTH_CAPTION,
  MONTH_FROZEN_NOTE,
  OFF_THE_MENU,
  SHARES_APPLIES_NOTE,
  SHARES_CAPTION,
  SHARE_LABEL,
  SHARE_ROLES,
  WEEKS_CAPTION,
  canCreateMonth,
  canSavePushList,
  canSaveShares,
  capWords,
  createStanding,
  draftGroups,
  guidanceWords,
  menuIndex,
  monthOptions,
  pickerGroups,
  pickerLabel,
  pushDraft,
  pushListBody,
  pushRowFor,
  pushStanding,
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
  type MenuEntry,
  type PushRow,
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
 * Each week tab opens that week's push list (M13.4, D6, D7): the dishes the
 * team is asked to push, what a portion above target earns with what the plate
 * keeps beside the box, and a portion target per branch. A week under way is
 * shown and not editable; every branch's statement lands in the ticket that
 * follows, out of this same one read.
 */
/** What a dish says beside its name on the list: what its plate keeps, or
 * why it cannot be counted at all. The API's own words in both cases; the
 * third case is a dish that has left the menu since the list was set. */
function keptNote(dish: MenuEntry | undefined): string {
  if (dish === undefined) return OFF_THE_MENU;
  return dish.item.mapped ? dish.item.kept_words : "no till name mapped";
}

export default function Incentive() {
  const [read, setRead] = useState<IncentiveRead | null>(null);
  const [month, setMonth] = useState<string | null>(null);
  const [draft, setDraft] = useState<ShareDraft>(shareDraft(null));
  const [targets, setTargets] = useState<TargetDrafts>({});
  const [week, setWeek] = useState<string | null>(null);
  const [rows, setRows] = useState<PushRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [creating, setCreating] = useState(false);
  const [savingList, setSavingList] = useState(false);
  // Try again is a bump of this, so the one effect below is the only place
  // that reads - the shipped Dashboard's pattern, and what keeps the
  // cancelled guard on every read rather than on the first one.
  const [reloadKey, setReloadKey] = useState(0);
  const [feedback, setFeedback] = useState<{
    kind: "error" | "done";
    text: string;
  } | null>(null);

  function landed(result: IncentiveRead) {
    setRead(result);
    setDraft(shareDraft(result.shares));
    setTargets(targetDrafts(result.branches));
    setWeek(null);
    // The draft is dropped on every read: what came back is what the week
    // holds, and a half-typed row kept across a save would be a figure on the
    // screen that no longer matches the one behind it.
    setRows(null);
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
        setLoadError(
          error instanceof Error
            ? error.message
            : "Could not load the incentive.",
        );
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
      const result = await createSchemeMonth(
        schemeMonthBody(read.month, targets, read.branches),
      );
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
  const tab = tabs.find((each) => each.id === openWeek) ?? null;
  const index = menuIndex(read.menu);
  // Held in a const so the handlers below close over the narrowed read: a
  // closure re-widens `read` to null, and an assertion there would be a
  // promise instead of a proof.
  const branches = read.branches;
  // The week's own list until the owner touches it, and their draft after -
  // so a week opened, read and left alone saves back exactly what it held.
  const stored = scheme?.weeks.find((each) => each.id === openWeek) ?? null;
  const rowsInView = rows ?? pushDraft(stored, read.branches);
  const groups = draftGroups(rowsInView, index, read.menu);
  const picker = pickerGroups(read.menu, rowsInView);

  function openTab(id: string) {
    setFeedback(null);
    setRows(null);
    setWeek(id);
  }

  function edit(menuItemId: string, change: (row: PushRow) => PushRow) {
    setFeedback(null);
    setRows(
      rowsInView.map((row) =>
        row.menu_item_id === menuItemId ? change(row) : row,
      ),
    );
  }

  function add(menuItemId: string) {
    if (menuItemId === "") return;
    setFeedback(null);
    setRows([...rowsInView, pushRowFor(menuItemId, branches)]);
  }

  function drop(menuItemId: string) {
    setFeedback(null);
    setRows(rowsInView.filter((row) => row.menu_item_id !== menuItemId));
  }

  async function saveList(weekId: string) {
    setSavingList(true);
    setFeedback(null);
    try {
      const result = await setPushList(
        weekId,
        pushListBody(rowsInView, read!.branches),
      );
      landed(result);
      setWeek(weekId);
      setFeedback({ kind: "done", text: "The week's list is saved." });
    } catch (error) {
      setFeedback({
        kind: "error",
        text: error instanceof Error ? error.message : "That did not work.",
      });
    } finally {
      setSavingList(false);
    }
  }

  return (
    <div className="space-y-8">
      <p className="max-w-3xl text-base leading-relaxed text-ink">
        {standing(read)}
      </p>

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
              <label
                key={role}
                className="flex flex-col gap-1 text-xs font-medium text-ink"
              >
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
            <p className="text-xs text-stone">
              {sharesUpdatedWords(read.shares)}
            </p>
          </div>

          <p className="max-w-xl text-xs leading-relaxed text-stone">
            {SHARES_APPLIES_NOTE}
          </p>
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
            Set the three shares above first: a month is created with the shares
            in force that day.
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
                setTargets({
                  ...targets,
                  [branch.id]: { ...row, [field]: value },
                });
              };
              return (
                // Spacing and not a rule between the branches: a `legend`
                // renders inside its `fieldset`'s border and cuts it, which
                // left the second branch's name sitting on a two-pixel stub of
                // a line.
                <fieldset key={branch.id} className="space-y-2">
                  <legend className="pb-1 text-sm font-semibold text-ink">
                    {branch.name}
                  </legend>
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
                      <span
                        id={`advice-${branch.id}`}
                        className="text-xs font-normal text-stone"
                      >
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
              <p
                role="status"
                aria-live="polite"
                className="text-sm text-stone"
              >
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
              <caption className="sr-only">
                Targets for {scheme.words}, one row per branch
              </caption>
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
                      <th
                        scope="row"
                        className="py-2 pr-3 text-left font-medium text-ink"
                      >
                        {branch.name}
                      </th>
                      <td className="py-2 pr-3 text-right tabular-nums text-ink">
                        {target === null
                          ? "No target"
                          : groupedMoney(target.net_sales_target)}
                      </td>
                      <td className="py-2 pr-3 text-right tabular-nums text-ink">
                        {target === null ? "-" : `${target.above_target_pct}%`}
                      </td>
                      <td className="py-2 text-right tabular-nums text-ink">
                        {capWords(target)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            <p className="text-xs leading-relaxed text-stone">
              {MONTH_FROZEN_NOTE}
            </p>

            <div className="space-y-3 border-t border-ink/10 pt-4">
              <h3 className="text-sm font-semibold text-ink">Push weeks</h3>
              <p className="text-sm text-stone">{WEEKS_CAPTION}</p>
              <div
                role="tablist"
                aria-label="Push weeks"
                className="flex flex-wrap gap-2 pt-1"
              >
                {tabs.map((tab) => (
                  <button
                    key={tab.id}
                    type="button"
                    role="tab"
                    aria-selected={tab.id === openWeek}
                    onClick={() => openTab(tab.id)}
                    className={`min-h-11 rounded-sm border px-3 py-2 text-sm ${
                      tab.id === openWeek
                        ? "border-palm bg-palm/10 font-medium text-ink"
                        : "border-ink/20 text-stone hover:border-palm/50"
                    }`}
                  >
                    {tab.label}
                    {tab.state === "running" ? (
                      <span className="pl-1.5 text-xs text-palm">
                        this week
                      </span>
                    ) : null}
                  </button>
                ))}
              </div>

              {tab === null ? null : (
                <div className="space-y-4 pt-1">
                  <p className="max-w-2xl text-sm text-stone">{LIST_CAPTION}</p>

                  {/* A week under way or over is read, not typed into: the list
                      it holds is a fact now, and a form the owner cannot use
                      would say otherwise. One table for the whole week, in the
                      targets table's own shape, with a row per category so the
                      column headings are said once. */}
                  {tab.frozen ? (
                    groups.length === 0 ? null : (
                      <table className="w-full text-sm">
                        <caption className="sr-only">
                          The push list for {tab.label}, by category
                        </caption>
                        <thead>
                          <tr className="text-left text-xs font-medium text-stone">
                            <th scope="col" className="pb-2 pr-3">
                              Dish
                            </th>
                            <th scope="col" className="pb-2 pr-3 text-right">
                              Rate per portion
                            </th>
                            {read.branches.map((branch) => (
                              <th
                                key={branch.id}
                                scope="col"
                                className="pb-2 pl-3 text-right"
                              >
                                {branch.name}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        {groups.map((group) => (
                          <tbody key={group.category}>
                            <tr className="border-t border-ink/10">
                              <th
                                scope="colgroup"
                                colSpan={read.branches.length + 2}
                                className="pt-3 pb-1 text-left text-sm font-semibold text-ink"
                              >
                                {group.category}
                                <span className="pl-2 text-xs font-normal text-stone">
                                  {guidanceWords(
                                    group.items.length,
                                    group.guidance,
                                  )}
                                </span>
                              </th>
                            </tr>
                            {group.items.map((row) => {
                              const dish = index[row.menu_item_id];
                              return (
                                <tr key={row.menu_item_id}>
                                  <th
                                    scope="row"
                                    className="py-1 pr-3 text-left font-normal text-ink"
                                  >
                                    {dish?.item.name ?? row.menu_item_id}
                                    <span className="block text-xs text-stone">
                                      {keptNote(dish)}
                                    </span>
                                  </th>
                                  <td className="py-1 pr-3 text-right align-top tabular-nums text-ink">
                                    {row.rate}
                                  </td>
                                  {read.branches.map((branch) => (
                                    <td
                                      key={branch.id}
                                      className="py-1 pl-3 text-right align-top tabular-nums text-ink"
                                    >
                                      {row.targets[branch.id] ?? "-"}
                                    </td>
                                  ))}
                                </tr>
                              );
                            })}
                          </tbody>
                        ))}
                      </table>
                    )
                  ) : (
                    groups.map((group) => (
                      <div key={group.category} className="space-y-2">
                        <h4 className="text-sm font-semibold text-ink">
                          {group.category}
                          <span className="pl-2 text-xs font-normal text-stone">
                            {guidanceWords(group.items.length, group.guidance)}
                          </span>
                        </h4>
                        <div className="space-y-3">
                          {group.items.map((row) => {
                            const dish = index[row.menu_item_id];
                            return (
                              <div
                                key={row.menu_item_id}
                                className="space-y-2 rounded-sm border border-ink/10 p-3"
                              >
                                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                                  <span className="text-sm font-medium text-ink">
                                    {dish?.item.name ?? row.menu_item_id}
                                  </span>
                                  <span className="text-xs text-stone">
                                    {keptNote(dish)}
                                  </span>
                                  <button
                                    type="button"
                                    onClick={() => drop(row.menu_item_id)}
                                    className="ml-auto min-h-11 text-xs text-stone underline underline-offset-2 hover:text-plum"
                                  >
                                    Take off this week
                                  </button>
                                </div>
                                <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
                                  <label className="flex flex-col gap-1 text-xs font-medium text-ink">
                                    Rate per portion
                                    <input
                                      type="text"
                                      inputMode="decimal"
                                      value={row.rate}
                                      onChange={(event) =>
                                        edit(row.menu_item_id, (draft) => ({
                                          ...draft,
                                          rate: event.target.value,
                                        }))
                                      }
                                      aria-label={`${dish?.item.name ?? "Dish"} rate per portion above target`}
                                      className="min-h-11 w-full rounded-sm border border-ink/20 bg-paper px-3 text-sm text-ink"
                                    />
                                  </label>
                                  {read.branches.map((branch) => (
                                    <label
                                      key={branch.id}
                                      className="flex flex-col gap-1 text-xs font-medium text-ink"
                                    >
                                      {branch.name}, portions
                                      <input
                                        type="text"
                                        inputMode="decimal"
                                        value={row.targets[branch.id] ?? ""}
                                        onChange={(event) =>
                                          edit(row.menu_item_id, (draft) => ({
                                            ...draft,
                                            targets: {
                                              ...draft.targets,
                                              [branch.id]: event.target.value,
                                            },
                                          }))
                                        }
                                        aria-label={`${dish?.item.name ?? "Dish"} portion target for ${branch.name}`}
                                        className="min-h-11 w-full rounded-sm border border-ink/20 bg-paper px-3 text-sm text-ink"
                                      />
                                    </label>
                                  ))}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    ))
                  )}

                  <p
                    role="status"
                    aria-live="polite"
                    className="text-sm text-stone"
                  >
                    {pushStanding(rowsInView, read.branches, index, tab)}
                  </p>

                  {tab.frozen ? null : (
                    <div className="flex flex-wrap items-end gap-3">
                      <label className="flex flex-col gap-1 text-xs font-medium text-ink">
                        Add a dish
                        <select
                          value=""
                          onChange={(event) => add(event.target.value)}
                          className="min-h-11 rounded-sm border border-ink/20 bg-paper px-3 text-sm text-ink"
                        >
                          <option value="">Pick a dish to push</option>
                          {picker.map((group) => (
                            <optgroup
                              key={group.category}
                              label={group.category}
                            >
                              {group.items.map((item) => (
                                <option
                                  key={item.id}
                                  value={item.id}
                                  disabled={!item.mapped}
                                >
                                  {pickerLabel(item)}
                                </option>
                              ))}
                            </optgroup>
                          ))}
                        </select>
                      </label>
                      <button
                        type="button"
                        disabled={
                          !canSavePushList(
                            rowsInView,
                            read.branches,
                            index,
                            tab,
                          ) || savingList
                        }
                        onClick={() => void saveList(tab.id)}
                        className="min-h-11 rounded-sm bg-palm px-4 py-2 text-sm font-medium text-cream disabled:opacity-60"
                      >
                        {savingList ? "Saving" : `Save ${tab.label}`}
                      </button>
                    </div>
                  )}
                </div>
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
            <span className="font-medium">
              {feedback.kind === "error" ? "Not done: " : "Done. "}
            </span>
            {feedback.text}
          </p>
        ) : null}
      </section>
    </div>
  );
}
