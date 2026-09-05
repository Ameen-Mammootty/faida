"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { getBranches, getDashboard } from "@/lib/api";
import {
  COST_COVERS,
  DEFAULT_CHOICE,
  NO_ITEMS,
  NO_SIGNALS,
  answerCaveat,
  answerLines,
  branchOptions,
  branchParam,
  cardLine,
  choiceKey,
  choiceLabel,
  componentCost,
  componentLink,
  componentWords,
  coverageStrip,
  drillNotes,
  filteredEmpty,
  firstRun,
  freshnessLine,
  incompleteItems,
  isFirstRun,
  isLoss,
  itemCaption,
  itemPanel,
  itemsHeading,
  leagueFootnote,
  leagueLine,
  leagueStatus,
  monthOptions,
  noContributionWords,
  noMenuSentence,
  noRatioWords,
  percent,
  periodBounds,
  portionsWords,
  showAllLabel,
  soldCount,
  signalHref,
  signalMoney,
  signalWhen,
  signalsCount,
  signalsFootnote,
  tillNamesWords,
  todaysPlateLink,
  withBranch,
  type PeriodChoice,
} from "@/lib/dashboardScreen";
import { roundedAed } from "@/lib/format";
import type {
  Branch,
  DashboardItemRow,
  DashboardResult,
  DashboardSignal,
  LeagueRow,
} from "@/lib/types";
import { AlertIcon, ChevronIcon } from "./icons";
import QualityChip from "./QualityChip";

/**
 * M9 WP-93: the owner dashboard - Variant A, "Branch first" (design review
 * 2026-09-05, approved by the founder).
 *
 * Reader order: the freshness line (the newest loaded day, its takings, the
 * papers waiting); the two answer sentences; the branch league with
 * contribution beside the ratio; what to look at, ranked by money; the items
 * five and five, expanding in place with the in-row drill to each
 * ingredient's invoice line; the coverage strip as a link to the queue on
 * `/sales`. One screen with a branch filter that writes `?branch=` into the
 * URL (P7); the chain total never follows the filter.
 *
 * Everything here is framing: every sentence that states a fact or a number
 * arrived composed from the API (C13.5), and every decision about which to
 * show lives in `lib/dashboardScreen.ts`, where vitest pins it. Never
 * "profit", never "food cost"; a status is a word and a sentence, never a
 * colour alone.
 */

/** The table and the card rows are both always in the DOM - only one is
 * displayed - so a ref shared between them keeps whichever React attached
 * last. This keeps only the copy that is actually on screen. */
function onScreen(el: HTMLElement | null): boolean {
  return el !== null && el.offsetParent !== null;
}

/** A negative contribution, `/menu`'s `LossFigure` verbatim: the glyph, the
 * figure and the words on one line, never colour alone. */
function LossFigure({
  value,
  layout,
}: {
  value: string;
  layout: "table" | "card";
}) {
  return (
    <span
      className={`inline-flex flex-wrap items-center gap-x-1.5 font-medium text-plum ${
        layout === "table" ? "justify-end" : ""
      }`}
    >
      <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
        <AlertIcon className="h-3.5 w-3.5" />
        <span className="tabular-nums">
          -{roundedAed(value.replace("-", ""))}
        </span>
      </span>
      <span className="text-xs font-normal">this item loses money</span>
    </span>
  );
}

function ContributionFigure({
  row,
  layout,
}: {
  row: DashboardItemRow;
  layout: "table" | "card";
}) {
  if (row.contribution === null)
    return <span className="text-xs text-stone">-</span>;
  if (isLoss(row))
    return <LossFigure value={row.contribution} layout={layout} />;
  return (
    <span className="font-display text-[15px] font-semibold text-ink tabular-nums">
      {roundedAed(row.contribution)}
    </span>
  );
}

function KeptFigure({ value }: { value: string | null }) {
  if (value === null) return <span className="text-xs text-stone">-</span>;
  return (
    <span
      className={`tabular-nums ${value.startsWith("-") ? "text-plum" : "text-ink"}`}
    >
      {percent(value)}
    </span>
  );
}

// --- the league ---------------------------------------------------------------

function LeagueTableRow({ row }: { row: LeagueRow }) {
  const status = leagueStatus(row);
  return (
    <tr className="border-b border-ink/5 align-top">
      <td className="px-4 py-3">
        <p className="font-medium text-ink">{row.branch_name}</p>
        <p className="text-xs text-stone">{leagueLine(row)}</p>
      </td>
      <td className="px-4 py-3 text-right tabular-nums">
        {row.net_sales === null ? "-" : roundedAed(row.net_sales)}
      </td>
      <td className="px-4 py-3 text-right">
        {row.ratio_pct === null ? (
          <span className="text-xs text-stone">{noRatioWords(row)}</span>
        ) : (
          <>
            <span className="font-display text-[15px] font-semibold text-ink tabular-nums">
              {percent(row.ratio_pct)}
            </span>
            <p className="text-xs text-stone tabular-nums">
              {roundedAed(row.purchases)} purchases
            </p>
          </>
        )}
      </td>
      <td className="px-4 py-3 text-right">
        {row.contribution === null ? (
          <span className="text-xs text-stone">{noContributionWords(row)}</span>
        ) : (
          <span className="font-display text-[15px] font-semibold text-ink tabular-nums">
            {roundedAed(row.contribution)}
          </span>
        )}
      </td>
      <td className="px-4 py-3 text-right font-display text-[15px] font-semibold">
        <KeptFigure value={row.contribution_pct} />
      </td>
      <td className="px-4 py-3">
        <QualityChip quality={status.quality} />
        <p className="mt-1 text-xs text-stone">{status.sentence}</p>
      </td>
    </tr>
  );
}

function LeagueCard({ row }: { row: LeagueRow }) {
  const status = leagueStatus(row);
  return (
    <li className="rounded-md border border-ink/10 bg-paper p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="min-h-11 py-1 font-medium text-ink">
            {row.branch_name}
          </p>
          <p className="text-xs text-stone">{leagueLine(row)}</p>
        </div>
        <div className="pt-1 text-right">
          {row.contribution_pct === null ? (
            <span className="text-xs text-stone">
              {noContributionWords(row)}
            </span>
          ) : (
            <span
              className={`font-display text-xl font-semibold tabular-nums ${
                row.contribution_pct.startsWith("-") ? "text-plum" : "text-ink"
              }`}
            >
              {percent(row.contribution_pct)}
            </span>
          )}
        </div>
      </div>
      <p className="mt-0.5 text-xs text-stone tabular-nums">{cardLine(row)}</p>
      <p className="mt-2 text-xs text-stone">
        <QualityChip quality={status.quality} />{" "}
        <span className="align-middle">{status.sentence}</span>
      </p>
    </li>
  );
}

// --- the items ------------------------------------------------------------------

interface ItemRowProps {
  row: DashboardItemRow;
  caption: "Best" | "Worst" | null;
  open: boolean;
  drillRef: React.RefObject<HTMLDivElement | null>;
  rowButtons: React.RefObject<Map<string, HTMLButtonElement>>;
  onToggle: () => void;
}

/** The in-row drill: the facts, the API's notes, the till names, and every
 * component with the invoice line behind its price - the stacked list the
 * design review asked for on a phone, and the same list on a wide screen. */
function ItemDrill({ row }: { row: DashboardItemRow }) {
  const portions = portionsWords(row);
  const plate = todaysPlateLink(row);
  return (
    <div className="space-y-2 pt-2 text-sm">
      <dl className="grid gap-x-6 gap-y-1 sm:grid-cols-3">
        <div>
          <dt className="text-[11px] font-medium tracking-wider text-stone uppercase">
            Portions
          </dt>
          <dd className="text-ink tabular-nums">
            {portions ?? "no quantity printed"}
          </dd>
        </div>
        <div>
          <dt className="text-[11px] font-medium tracking-wider text-stone uppercase">
            Costed
          </dt>
          <dd className="text-ink tabular-nums">
            {row.cost_per_portion === null
              ? "-"
              : `AED ${row.cost_per_portion} a plate`}
            {row.cost_per_portion_today !== null ? (
              <span className="text-stone">
                {" "}
                · today AED {row.cost_per_portion_today}
              </span>
            ) : null}
          </dd>
        </div>
        <div>
          <dt className="text-[11px] font-medium tracking-wider text-stone uppercase">
            Till names
          </dt>
          <dd className="text-ink">{tillNamesWords(row)}</dd>
        </div>
      </dl>
      {drillNotes(row).length > 0 ? (
        <ul className="space-y-0.5">
          {drillNotes(row).map((note) => (
            <li
              key={note}
              className={`text-xs ${row.contribution === null ? "text-plum" : "text-stone"}`}
            >
              {note}
            </li>
          ))}
        </ul>
      ) : null}
      {row.components.length > 0 ? (
        <ul className="divide-y divide-ink/5 border-t border-ink/10">
          {row.components.map((component) => {
            const link = componentLink(component);
            return (
              <li
                key={`${component.ingredient_id}-${component.invoice_id ?? ""}`}
                className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5 py-1.5"
              >
                <span className="text-ink">{componentWords(component)}</span>
                <span className="text-xs text-stone tabular-nums">
                  {componentCost(component)}
                  {link ? (
                    <>
                      {" · "}
                      <Link
                        href={link.href}
                        className="font-medium text-palm underline-offset-2 hover:underline"
                      >
                        {link.label}
                      </Link>
                    </>
                  ) : null}
                </span>
              </li>
            );
          })}
        </ul>
      ) : null}
      <p className="text-xs text-stone">
        {COST_COVERS}
        {plate ? (
          <>
            {" "}
            <Link
              href={plate.href}
              className="font-medium text-palm underline-offset-2 hover:underline"
            >
              {plate.label}
            </Link>
          </>
        ) : null}
      </p>
    </div>
  );
}

function ItemTableRow({
  row,
  caption,
  open,
  drillRef,
  rowButtons,
  onToggle,
}: ItemRowProps) {
  return (
    <>
      <tr
        className={`border-b border-ink/5 align-middle ${caption === "Worst" ? "border-t border-t-ink/15" : ""}`}
      >
        <td className="px-4 py-2">
          {caption ? (
            <p className="text-[11px] font-medium tracking-wider text-stone uppercase">
              {caption}
            </p>
          ) : null}
          <button
            type="button"
            ref={(el) => {
              if (onScreen(el)) rowButtons.current.set(row.menu_item_id, el!);
            }}
            onClick={onToggle}
            aria-expanded={open}
            className="group inline-flex min-h-11 items-center gap-1.5 rounded-sm py-1 text-left font-medium text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-palm/30"
          >
            <ChevronIcon
              className={`h-3 w-3 shrink-0 text-stone transition-transform ${open ? "rotate-90" : ""}`}
            />
            <span className="underline-offset-2 group-hover:underline">
              {row.menu_item_name}
            </span>
            {row.quality === "estimated" ? (
              <span className="ml-1.5">
                <QualityChip quality="estimated" />
              </span>
            ) : null}
          </button>
        </td>
        <td className="px-4 py-3 text-right text-stone tabular-nums">
          {row.qty_sold === null ? "-" : soldCount(row.qty_sold)}
        </td>
        <td className="px-4 py-3 text-right tabular-nums">
          {roundedAed(row.net_item_sales)}
        </td>
        <td className="px-4 py-3 text-right">
          <ContributionFigure row={row} layout="table" />
        </td>
        <td className="px-4 py-3 text-right font-display text-[15px] font-semibold">
          <KeptFigure value={row.contribution_pct} />
        </td>
      </tr>
      {open ? (
        <tr className="border-b border-ink/5">
          <td colSpan={5} className="px-4 pb-3">
            <div
              ref={(el) => {
                if (onScreen(el)) drillRef.current = el;
              }}
              tabIndex={-1}
              className="focus:outline-none"
            >
              <ItemDrill row={row} />
            </div>
          </td>
        </tr>
      ) : null}
    </>
  );
}

function ItemCard({
  row,
  caption,
  open,
  drillRef,
  rowButtons,
  onToggle,
}: ItemRowProps) {
  const sold = row.qty_sold === null ? null : soldCount(row.qty_sold);
  return (
    <li className="rounded-md border border-ink/10 bg-paper p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          {caption ? (
            <p className="text-[11px] font-medium tracking-wider text-stone uppercase">
              {caption}
            </p>
          ) : null}
          <button
            type="button"
            ref={(el) => {
              if (onScreen(el)) rowButtons.current.set(row.menu_item_id, el!);
            }}
            onClick={onToggle}
            aria-expanded={open}
            className="group inline-flex min-h-11 items-center gap-1.5 rounded-sm py-1 text-left font-medium text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-palm/30"
          >
            <ChevronIcon
              className={`h-3 w-3 shrink-0 text-stone transition-transform ${open ? "rotate-90" : ""}`}
            />
            <span className="underline-offset-2 group-hover:underline">
              {row.menu_item_name}
            </span>
          </button>
        </div>
        <div className="pt-1 text-right">
          <ContributionFigure row={row} layout="card" />
        </div>
      </div>
      <p className="mt-0.5 text-xs text-stone tabular-nums">
        {sold === null ? "no quantity" : `${sold} sold`} ·{" "}
        {roundedAed(row.net_item_sales)} net · kept{" "}
        {row.contribution_pct === null ? "-" : percent(row.contribution_pct)}
        {row.quality === "estimated" ? (
          <>
            {" · "}
            <QualityChip quality="estimated" />
          </>
        ) : null}
      </p>
      {open ? (
        <div
          ref={(el) => {
            if (onScreen(el)) drillRef.current = el;
          }}
          tabIndex={-1}
          className="mt-2 border-t border-ink/10 focus:outline-none"
        >
          <ItemDrill row={row} />
        </div>
      ) : null}
    </li>
  );
}

// --- the signals ----------------------------------------------------------------

function SignalLine({ signal }: { signal: DashboardSignal }) {
  const href = signalHref(signal);
  return (
    <li className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 py-3 first:pt-0 last:pb-0">
      <div className="min-w-0 flex-1">
        <p className="text-sm text-ink">
          {href ? (
            <Link href={href} className="underline-offset-2 hover:underline">
              {signal.sentence}
            </Link>
          ) : (
            signal.sentence
          )}
        </p>
        <p className="text-xs text-stone">{signal.detail}</p>
      </div>
      <div className="text-right">
        <p className="font-display text-[15px] font-semibold text-ink tabular-nums">
          {signalMoney(signal)}
        </p>
        <p className="text-xs text-stone">{signalWhen(signal)}</p>
      </div>
    </li>
  );
}

// --- the screen -----------------------------------------------------------------

export default function Dashboard() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const branch = branchParam(searchParams.toString());

  const [choice, setChoice] = useState<PeriodChoice>(DEFAULT_CHOICE);
  const [result, setResult] = useState<DashboardResult | null>(null);
  const [branches, setBranches] = useState<Branch[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const drillRef = useRef<HTMLDivElement>(null);
  const rowButtons = useRef<Map<string, HTMLButtonElement>>(new Map());
  const lastOpened = useRef<string | null>(null);
  // The tenant's newest loaded day, learned from the first read and read back
  // by later ones - a ref, not a dep, so the read that learns it does not
  // re-run itself (the sales screen's rule).
  const salesThroughRef = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const range = periodBounds(choice, salesThroughRef.current);
    (async () => {
      try {
        const [read, list] = await Promise.all([
          getDashboard(range?.from, range?.to, branch ?? undefined),
          getBranches(),
        ]);
        if (cancelled) return;
        salesThroughRef.current = read.period.sales_through;
        setResult(read);
        setBranches(list);
        setLoadError(null);
      } catch (error) {
        if (cancelled) return;
        setLoadError(
          error instanceof Error
            ? error.message
            : "Could not load the dashboard.",
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [choice, branch, reloadKey]);

  // Focus follows the drill: into the expansion when it opens, back to the
  // row's own button when it collapses.
  useEffect(() => {
    if (open !== null) {
      lastOpened.current = open;
      drillRef.current?.focus();
    } else if (lastOpened.current !== null) {
      rowButtons.current.get(lastOpened.current)?.focus();
      lastOpened.current = null;
    }
  }, [open]);

  const header = (
    <header>
      <h1 className="font-display text-2xl font-semibold tracking-[-0.02em] text-ink">
        Dashboard
      </h1>
      <p className="mt-1 max-w-2xl text-sm text-stone">
        What each branch and each dish kept after ingredients and packaging,
        over the days you have loaded.
      </p>
    </header>
  );

  if (loadError) {
    return (
      <div className="space-y-6">
        {header}
        <div
          role="alert"
          className="rounded-md border border-ink/10 bg-paper p-6"
        >
          <p className="text-sm font-medium text-ink">
            Could not load the dashboard
          </p>
          <p className="mt-1 text-sm text-stone">{loadError}</p>
          <button
            type="button"
            onClick={() => {
              setLoading(true);
              setReloadKey((key) => key + 1);
            }}
            className="mt-4 min-h-11 rounded-sm border border-palm/30 px-3 py-1.5 text-sm font-medium text-palm hover:border-palm"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  if (result === null || branches === null) {
    return (
      <div className="space-y-6">
        {header}
        <div
          aria-busy="true"
          className="rounded-md border border-ink/10 bg-paper p-6"
        >
          <p role="status" className="text-sm text-stone">
            Loading the dashboard
          </p>
        </div>
      </div>
    );
  }

  if (isFirstRun(result)) {
    const first = firstRun(result);
    return (
      <div className="space-y-6">
        {header}
        <section className="rounded-md border border-ink/10 bg-paper p-5">
          <h2 className="font-display text-lg font-semibold text-ink">
            {first.heading}
          </h2>
          <p className="mt-1 max-w-2xl text-sm text-stone">
            {first.body} {first.menuSentence}
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Link
              href={first.primary.href}
              className="inline-flex min-h-11 items-center rounded-sm bg-palm px-4 py-2 text-sm font-medium text-cream hover:bg-palm-deep"
            >
              {first.primary.label}
            </Link>
            <Link
              href={first.secondary.href}
              className="inline-flex min-h-11 items-center rounded-sm border border-palm/30 px-4 py-2 text-sm font-medium text-palm hover:border-palm"
            >
              {first.secondary.label}
            </Link>
          </div>
        </section>
      </div>
    );
  }

  const fresh = freshnessLine(result);
  const answer = answerLines(result);
  const caveat = answerCaveat(result);
  const emptyBranch = filteredEmpty(result);
  const noMenu = noMenuSentence(result);
  const months = monthOptions(result.period);
  const choices: PeriodChoice[] = [
    { kind: "last28" },
    { kind: "last7" },
    ...months.map((option): PeriodChoice => ({
      kind: "month",
      year: option.year,
      month: option.month,
    })),
  ];
  const options = branchOptions(branches);
  const panel = itemPanel(result.items, expanded);
  const incomplete = incompleteItems(result.items);
  const strip = coverageStrip(result);
  const footnote = signalsFootnote(result);
  const toggle = (id: string) =>
    setOpen((current) => (current === id ? null : id));

  const pickBranch = (id: string) => {
    const query = withBranch(searchParams.toString(), id === "" ? null : id);
    setLoading(true);
    setOpen(null);
    router.replace(query === "" ? pathname : `${pathname}?${query}`);
  };

  const renderRows = (
    rows: DashboardItemRow[],
    where: "top" | "bottom" | "all",
  ) =>
    rows.map((row, index) => ({
      row,
      caption: itemCaption(where, index, rows.length),
    }));
  const visible =
    panel.kind === "none"
      ? []
      : panel.kind === "all"
        ? renderRows(panel.rows, "all")
        : [
            ...renderRows(panel.top, "top"),
            ...renderRows(panel.bottom, "bottom"),
          ];

  return (
    <div className="space-y-6">
      {header}

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-stone">
        <div
          role="group"
          aria-label="Period"
          className="inline-flex overflow-hidden rounded-sm border border-ink/15"
        >
          {choices.map((option) => {
            const on = choiceKey(option) === choiceKey(choice);
            return (
              <button
                key={choiceKey(option)}
                type="button"
                aria-pressed={on}
                disabled={loading}
                onClick={() => {
                  if (on) return;
                  setLoading(true);
                  setChoice(option);
                  setOpen(null);
                }}
                className={`min-h-9 px-3 py-1 text-xs font-medium ${
                  on ? "bg-palm text-cream" : "text-stone hover:text-palm"
                } disabled:opacity-60`}
              >
                {choiceLabel(option)}
              </button>
            );
          })}
        </div>
        <label className="inline-flex items-center gap-2 text-xs font-medium text-stone">
          <span className="sr-only">Branch</span>
          <select
            value={branch ?? ""}
            disabled={loading}
            onChange={(event) => pickBranch(event.target.value)}
            className="min-h-9 rounded-sm border border-ink/15 bg-paper px-2 py-1 text-xs font-medium text-ink disabled:opacity-60"
          >
            {options.map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <p role="status" aria-live="polite" className="text-sm text-stone">
        {loading ? (
          `Loading ${choiceLabel(choice)}`
        ) : fresh ? (
          <>
            {fresh.sentence}
            {fresh.estimated ? (
              <>
                {" "}
                <QualityChip quality="estimated" />
              </>
            ) : null}
            {fresh.takings ? (
              <span className="tabular-nums"> · {fresh.takings}</span>
            ) : null}
            {fresh.papers ? (
              <>
                {" · "}
                <Link
                  href={fresh.papers.href}
                  className="font-medium text-palm underline-offset-2 hover:underline"
                >
                  {fresh.papers.label}
                </Link>
              </>
            ) : null}
          </>
        ) : null}
      </p>

      {emptyBranch ? (
        <section className="rounded-md border border-ink/10 bg-paper p-5">
          <p className="text-sm font-medium text-ink">{emptyBranch}</p>
          <button
            type="button"
            onClick={() => pickBranch("")}
            className="mt-3 min-h-11 rounded-sm border border-palm/30 px-3 py-1.5 text-sm font-medium text-palm hover:border-palm"
          >
            See all branches
          </button>
        </section>
      ) : null}

      {emptyBranch ? null : (
        <section
          aria-busy={loading}
          className={`space-y-6 ${loading ? "opacity-60" : ""}`}
        >
          <div className="max-w-3xl space-y-1">
            <p className="text-base leading-relaxed text-ink">
              {answer.empty ?? (
                <>
                  {answer.branch ? <span>{answer.branch}</span> : null}
                  {answer.branch && answer.item ? " " : null}
                  {answer.item ? <span>{answer.item}</span> : null}
                </>
              )}
            </p>
            {caveat ? <p className="text-xs text-stone">{caveat}</p> : null}
          </div>

          {/* The league: one fixed grid so every row lines up (the sales screen's rule). */}
          <div className="hidden overflow-hidden rounded-md border border-ink/10 bg-paper sm:block">
            <table className="w-full table-fixed text-sm">
              <caption className="sr-only">
                Branches ranked by what they kept, lowest first
              </caption>
              <colgroup>
                <col className="w-[23%]" />
                <col className="w-[13%]" />
                <col className="w-[16%]" />
                <col className="w-[16%]" />
                <col className="w-[11%]" />
                <col className="w-[21%]" />
              </colgroup>
              <thead>
                <tr className="border-b border-ink/10 text-left text-xs font-medium tracking-wider text-stone uppercase">
                  <th scope="col" className="px-4 py-2 font-medium">
                    Branch
                  </th>
                  <th scope="col" className="px-4 py-2 text-right font-medium">
                    Net sales
                  </th>
                  <th scope="col" className="px-4 py-2 text-right font-medium">
                    Purchases ÷ net sales (cash basis)
                  </th>
                  <th scope="col" className="px-4 py-2 text-right font-medium">
                    Contribution (est.)
                  </th>
                  <th scope="col" className="px-4 py-2 text-right font-medium">
                    Kept
                  </th>
                  <th scope="col" className="px-4 py-2 font-medium">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody>
                {result.league.map((row) => (
                  <LeagueTableRow key={row.branch_id} row={row} />
                ))}
                {result.unassigned.count > 0 ? (
                  <tr className="border-b border-ink/5 align-top text-stone">
                    <td className="px-4 py-3">
                      <p className="font-medium">No branch</p>
                      <p className="text-xs">
                        {result.unassigned.count}{" "}
                        {result.unassigned.count === 1 ? "invoice" : "invoices"}{" "}
                        with no branch
                      </p>
                    </td>
                    <td className="px-4 py-3 text-right">-</td>
                    <td className="px-4 py-3 text-right text-xs tabular-nums">
                      {roundedAed(result.unassigned.purchases)} purchases
                    </td>
                    <td className="px-4 py-3 text-right">-</td>
                    <td className="px-4 py-3 text-right">-</td>
                    <td className="px-4 py-3 text-xs">
                      Counted in the total, ranked nowhere.
                    </td>
                  </tr>
                ) : null}
                <tr className="border-t border-ink/15 align-top font-semibold">
                  <td className="px-4 py-3">All branches</td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {roundedAed(result.total.net_sales)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {result.total.ratio_pct === null ? (
                      <span className="text-xs font-normal text-stone">
                        Not rated
                      </span>
                    ) : (
                      <>
                        <span className="font-display text-[15px] tabular-nums">
                          {percent(result.total.ratio_pct)}
                        </span>
                        <p className="text-xs font-normal text-stone tabular-nums">
                          {roundedAed(result.total.purchases)} purchases
                        </p>
                      </>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {result.total.contribution === null ? (
                      <span className="text-xs font-normal text-stone">
                        {noMenu ?? "Nothing costed"}
                      </span>
                    ) : (
                      <span className="font-display text-[15px] tabular-nums">
                        {roundedAed(result.total.contribution)}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right font-display text-[15px]">
                    <KeptFigure value={result.total.contribution_pct} />
                  </td>
                  <td className="px-4 py-3 font-normal">
                    <QualityChip quality={result.total.contribution_quality} />
                    <p className="mt-1 text-xs text-stone">
                      {leagueStatus(result.total).sentence}
                    </p>
                  </td>
                </tr>
              </tbody>
            </table>
            <p className="border-t border-ink/10 px-4 py-3 text-xs text-stone">
              {leagueFootnote(result)}
            </p>
          </div>

          {/* Cards under 640 px: the kept percentage as the large figure. */}
          <ul className="space-y-2 sm:hidden">
            {result.league.map((row) => (
              <LeagueCard key={row.branch_id} row={row} />
            ))}
            <li className="rounded-md border border-ink/15 bg-paper p-3">
              <div className="flex items-start justify-between gap-3">
                <p className="min-h-11 py-1 font-semibold text-ink">
                  All branches
                </p>
                <div className="pt-1 text-right">
                  {result.total.contribution_pct === null ? (
                    <span className="text-xs text-stone">
                      {noMenu ?? "Nothing costed"}
                    </span>
                  ) : (
                    <span className="font-display text-xl font-semibold text-ink tabular-nums">
                      {percent(result.total.contribution_pct)}
                    </span>
                  )}
                </div>
              </div>
              <p className="mt-0.5 text-xs text-stone tabular-nums">
                {result.total.contribution === null
                  ? `Net sales ${roundedAed(result.total.net_sales)}`
                  : `Kept ${roundedAed(result.total.contribution)} of ${roundedAed(result.total.net_sales)}`}
                {result.total.ratio_pct === null
                  ? ""
                  : ` · purchases ÷ net sales ${percent(result.total.ratio_pct)}`}
              </p>
              <p className="mt-2 text-xs text-stone">
                <QualityChip quality={result.total.contribution_quality} />{" "}
                <span className="align-middle">
                  {leagueStatus(result.total).sentence}
                </span>
              </p>
            </li>
            <li className="px-1 text-xs text-stone">
              {leagueFootnote(result)}
            </li>
          </ul>

          {/* What to look at: prose, ranked by money, never a widget. */}
          <section className="space-y-2">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="font-display text-lg font-semibold text-ink">
                What to look at
              </h2>
              {signalsCount(result.signals) ? (
                <span className="text-xs text-stone">
                  {signalsCount(result.signals)}
                </span>
              ) : null}
            </div>
            <div className="rounded-md border border-ink/10 bg-paper px-4 py-3">
              {result.signals.length === 0 ? (
                <p className="text-sm text-stone">{footnote ?? NO_SIGNALS}</p>
              ) : (
                <>
                  <ul className="divide-y divide-ink/5">
                    {result.signals.map((signal) => (
                      <SignalLine
                        key={`${signal.kind}-${signal.sentence}`}
                        signal={signal}
                      />
                    ))}
                  </ul>
                  {footnote ? (
                    <p className="mt-2 text-xs text-stone">{footnote}</p>
                  ) : null}
                </>
              )}
            </div>
          </section>

          {/* The items: five and five, expanding in place. */}
          <section className="space-y-2">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="font-display text-lg font-semibold text-ink">
                Items: what each one contributed
              </h2>
              {itemsHeading(result.items) ? (
                <span className="text-xs text-stone">
                  {itemsHeading(result.items)}
                </span>
              ) : null}
            </div>
            {panel.kind === "none" ? (
              <div className="rounded-md border border-ink/10 bg-paper px-4 py-3">
                <p className="text-sm text-stone">{noMenu ?? NO_ITEMS}</p>
              </div>
            ) : (
              <>
                <div className="hidden overflow-hidden rounded-md border border-ink/10 bg-paper sm:block">
                  <table className="w-full table-fixed text-sm">
                    <caption className="sr-only">
                      Items ranked by what they contributed
                    </caption>
                    <colgroup>
                      <col className="w-[38%]" />
                      <col className="w-[12%]" />
                      <col className="w-[16%]" />
                      <col className="w-[20%]" />
                      <col className="w-[14%]" />
                    </colgroup>
                    <thead>
                      <tr className="border-b border-ink/10 text-left text-xs font-medium tracking-wider text-stone uppercase">
                        <th scope="col" className="px-4 py-2 font-medium">
                          Item
                        </th>
                        <th
                          scope="col"
                          className="px-4 py-2 text-right font-medium"
                        >
                          Sold
                        </th>
                        <th
                          scope="col"
                          className="px-4 py-2 text-right font-medium"
                        >
                          Net sales
                        </th>
                        <th
                          scope="col"
                          className="px-4 py-2 text-right font-medium"
                        >
                          Contribution
                        </th>
                        <th
                          scope="col"
                          className="px-4 py-2 text-right font-medium"
                        >
                          Kept
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {visible.map(({ row, caption }) => (
                        <ItemTableRow
                          key={row.menu_item_id}
                          row={row}
                          caption={caption}
                          open={open === row.menu_item_id}
                          drillRef={drillRef}
                          rowButtons={rowButtons}
                          onToggle={() => toggle(row.menu_item_id)}
                        />
                      ))}
                    </tbody>
                  </table>
                </div>
                <ul className="space-y-2 sm:hidden">
                  {visible.map(({ row, caption }) => (
                    <ItemCard
                      key={row.menu_item_id}
                      row={row}
                      caption={caption}
                      open={open === row.menu_item_id}
                      drillRef={drillRef}
                      rowButtons={rowButtons}
                      onToggle={() => toggle(row.menu_item_id)}
                    />
                  ))}
                </ul>
                {panel.kind === "split" || expanded ? (
                  <button
                    type="button"
                    onClick={() => {
                      setExpanded((value) => !value);
                      setOpen(null);
                    }}
                    aria-expanded={expanded}
                    className="min-h-11 rounded-sm border border-palm/30 px-3 py-1.5 text-sm font-medium text-palm hover:border-palm"
                  >
                    {showAllLabel(result.items.count, expanded)}
                  </button>
                ) : null}
              </>
            )}
            {incomplete.length > 0 ? (
              <div className="rounded-md bg-mist p-4">
                <p className="text-sm font-medium text-ink">
                  {incomplete.length}{" "}
                  {incomplete.length === 1 ? "item is" : "items are"} listed
                  here with no numbers
                </p>
                <ul className="mt-2 divide-y divide-ink/10">
                  {incomplete.map((row) => (
                    <li
                      key={row.menu_item_id}
                      className="py-2 first:pt-0 last:pb-0"
                    >
                      <p className="text-sm font-medium text-ink">
                        {row.menu_item_name}
                        <span className="font-normal text-stone tabular-nums">
                          {" "}
                          · {roundedAed(row.net_item_sales)} net
                        </span>
                      </p>
                      <ul className="mt-0.5 space-y-0.5">
                        {drillNotes(row).map((note) => (
                          <li key={note} className="text-xs text-plum">
                            {note}
                          </li>
                        ))}
                      </ul>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {panel.kind !== "none" ? (
              <p className="max-w-2xl text-xs text-stone">
                Contribution is the till&apos;s own net takings for the item
                less what its recipe costs at the prices in force on the
                period&apos;s last day; it is not profit, and{" "}
                {COST_COVERS.charAt(0).toLowerCase() + COST_COVERS.slice(1)}
              </p>
            ) : null}
          </section>

          {/* The consultant's queue: a link, not a second queue. */}
          <section className="flex flex-wrap items-center justify-between gap-3 rounded-md bg-mist p-4">
            <p className="text-sm text-ink">
              <span className="font-medium">{strip.lead}</span> {strip.rest}
            </p>
            {strip.link ? (
              <Link
                href={strip.link.href}
                className="inline-flex min-h-11 items-center rounded-sm border border-palm/30 px-3 py-1.5 text-sm font-medium text-palm hover:border-palm"
              >
                {strip.link.label} &rarr;
              </Link>
            ) : null}
          </section>
        </section>
      )}
    </div>
  );
}
