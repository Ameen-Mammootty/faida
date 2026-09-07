"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { getBranches, getDashboard } from "@/lib/api";
import {
  COST_COVERS,
  DEFAULT_CHOICE,
  ITEMS_LINK,
  LEAGUE_LINK,
  NO_ITEMS,
  NO_SIGNALS,
  SCREEN_ABOUT,
  answerChip,
  answerLines,
  answerTip,
  branchOptions,
  branchParam,
  cardLine,
  choiceKey,
  choiceLabel,
  componentCost,
  componentLink,
  componentWords,
  drillNotes,
  filteredEmpty,
  firstRun,
  footnoteTip,
  freshnessLine,
  incompleteItems,
  isFirstRun,
  isLoss,
  itemCaption,
  itemPanel,
  itemsHeading,
  itemsTip,
  keptBar,
  leagueLink,
  leagueStatus,
  leagueTip,
  monthOptions,
  noContributionWords,
  noMenuSentence,
  noRatioWords,
  percent,
  periodBounds,
  portionsWords,
  showAllLabel,
  showAllSignalsLabel,
  soldCount,
  signalHref,
  signalMoney,
  signalPanel,
  signalTip,
  signalsCount,
  signalsFootnote,
  tillNamesWords,
  tiles,
  todaysPlateLink,
  totalTip,
  withBranch,
  type PeriodChoice,
  type Tile,
} from "@/lib/dashboardScreen";
import { roundedAed } from "@/lib/format";
import type {
  Branch,
  DashboardItemRow,
  DashboardResult,
  DashboardSignal,
  LeagueRow,
} from "@/lib/types";
import { ChevronIcon } from "./icons";
import InfoTip from "./InfoTip";
import LossFigure from "./LossFigure";
import QualityChip from "./QualityChip";

/**
 * M9 WP-93: the owner dashboard - Variant A, "Branch first" (design review
 * 2026-09-05, approved by the founder).
 *
 * Reader order: the freshness line (the newest loaded day, its takings, the
 * papers waiting); the two answer sentences; the branch league with
 * contribution beside the ratio; what to look at, ranked by money; the items
 * five and five, expanding in place with the in-row drill to each
 * ingredient's invoice line. One screen with a branch filter that writes
 * `?branch=` into the URL (P7); the chain total never follows the filter.
 *
 * The founder's redesign (2026-09-07): the answer, the four figures and the
 * whole league sit above the fold on a 1366x768 laptop and on a 1229x691 one,
 * because every sentence that qualifies a figure moved behind a circled "i"
 * beside it. Nothing was rewritten to get there - a tooltip prints the
 * sentence the API sent or the join `lib/dashboardScreen.ts` already made -
 * and nothing is left to colour: the kept bar and the costed-share bar each
 * stand beside their own number.
 *
 * Everything here is framing: every sentence that states a fact or a number
 * arrived composed from the API (C13.5), and every decision about which to
 * show lives in `lib/dashboardScreen.ts`, where vitest pins it. Never
 * "profit", never "food cost"; a status is a word and a sentence, never a
 * colour alone.
 *
 * WP-94, the drill: every number on this screen reaches the paper it came
 * from. A league row's branch name opens `/sales` at that branch's own row,
 * days and papers and all; an item row opens in place and links onward to
 * `/menu#item-<id>` for today's plate and to `/invoices/<id>#line-<n>` for the
 * line behind each ingredient's price. All three are the same anchor idiom
 * (`lib/anchor.ts`), so the app has one thing to learn.
 */

/** The table and the card rows are both always in the DOM - only one is
 * displayed - so a ref shared between them keeps whichever React attached
 * last. This keeps only the copy that is actually on screen. */
function onScreen(el: HTMLElement | null): boolean {
  return el !== null && el.offsetParent !== null;
}

/** A negative contribution: the shared loss figure with this screen's own
 * noun (M9 WP-98), the glyph, the figure and the words on one line. */
function ItemLoss({
  value,
  layout,
}: {
  value: string;
  layout: "table" | "card";
}) {
  return (
    <LossFigure
      figure={`-${roundedAed(value.replace("-", ""))}`}
      noun="this item"
      align={layout === "table" ? "end" : "start"}
    />
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
    return <ItemLoss value={row.contribution} layout={layout} />;
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

/** The share bar: mist track, palm fill, the width the API's percentage
 * already is. It never stands alone - the number it draws is always beside
 * it (the display rules). */
function ShareBar({
  width,
  className = "w-full",
}: {
  width: number;
  className?: string;
}) {
  return (
    <span
      className={`block h-1.5 overflow-hidden rounded-full bg-mist ${className}`}
    >
      <span
        className="block h-full rounded-full bg-palm"
        style={{ width: `${width}%` }}
      />
    </span>
  );
}

/** A league row's Kept cell: the bar and its percentage on one line, so the
 * figure sits on the row's own baseline with every other figure. A row that
 * kept nothing shows the loss words and an empty track. */
function KeptCell({ value, noun }: { value: string | null; noun: string }) {
  const width = keptBar(value);
  if (value === null || width === null)
    return <span className="text-xs font-normal text-stone">-</span>;
  return (
    <span className="flex items-center justify-end gap-2">
      <ShareBar width={width} className="max-w-[90px] shrink flex-1" />
      {value.startsWith("-") ? (
        <LossFigure
          figure={percent(value)}
          noun={noun}
          align="end"
          figureClass="font-display text-[15px] font-semibold tabular-nums"
        />
      ) : (
        <span className="shrink-0 font-display text-[15px] font-semibold text-ink tabular-nums">
          {percent(value)}
        </span>
      )}
    </span>
  );
}

// --- the tiles ----------------------------------------------------------------

/** The quiet link at the right of a section's heading: where the whole of
 * that section lives. */
function SectionLink({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      className="text-xs font-medium text-palm underline-offset-2 hover:underline"
    >
      {label} &rarr;
    </Link>
  );
}

/** A section's heading with the sentences that explain it behind one icon. */
function SectionHeading({
  title,
  tip,
  label,
}: {
  title: string;
  tip: string[];
  label: string;
}) {
  return (
    <h2 className="flex items-center gap-1.5 font-display text-lg font-semibold text-ink">
      {title}
      <InfoTip lines={tip} label={label} />
    </h2>
  );
}

/**
 * One headline: the label, the figure with its quality word and its icon on
 * the same line, and one short line beneath. Everything that qualifies the
 * figure - the standing clause, the note behind the word, the money the
 * queue is worth - is behind the icon.
 */
function HeadlineTile({ tile }: { tile: Tile }) {
  return (
    <dl className="rounded-md border border-ink/10 bg-paper p-4">
      {/* Two labels of the four run to a second line in a quarter-width
          column, so the label reserves both and the four figures sit on one
          line across the row. */}
      <dt className="min-h-7 text-[11px] leading-[14px] font-medium tracking-wider text-stone uppercase">
        {tile.label}
      </dt>
      {/* The figure keeps the whole line - a money headline and a chip beside
          it do not both fit a quarter column - so the icon rides the figure's
          right and the quality word leads the line it qualifies, the way the
          league's status cell reads. */}
      <dd className="mt-1.5 flex min-h-7 items-center justify-between gap-2">
        <span className="min-w-0">
          {tile.figure === null ? (
            <span className="text-sm text-stone">{tile.words}</span>
          ) : tile.loss ? (
            <LossFigure
              figure={tile.figure}
              noun="the costed sales"
              plural
              figureClass="font-display text-[26px] leading-7 font-semibold tabular-nums"
            />
          ) : (
            <span className="font-display text-[26px] leading-7 font-semibold whitespace-nowrap text-ink tabular-nums">
              {tile.figure}
            </span>
          )}
        </span>
        <span className="shrink-0">
          <InfoTip lines={tile.tip} label={`More about ${tile.label}`} />
        </span>
      </dd>
      {tile.bar === null ? null : (
        <dd className="mt-1.5">
          <ShareBar width={tile.bar} />
        </dd>
      )}
      {/* The word gets a row of its own, and only where there is one: beside
          the sentence it pushed "AED" away from the number after it, and
          under a figure it left a tile with no word looking like a tile with
          a hole in it. */}
      {tile.status === null ? null : (
        <dd className="mt-1.5">
          <QualityChip quality={tile.status.quality} />
        </dd>
      )}
      {tile.line === "" && tile.caption === null ? null : (
        <dd className="mt-1 text-[12.5px] leading-snug text-stone">
          {tile.caption === null ? null : <>{tile.caption} &middot; </>}
          {tile.line}
          {tile.link ? (
            <>
              {" · "}
              <Link
                href={tile.link.href}
                className="font-medium text-palm underline-offset-2 hover:underline"
              >
                {tile.link.label} &rarr;
              </Link>
            </>
          ) : null}
        </dd>
      )}
    </dl>
  );
}

// --- the league ---------------------------------------------------------------

/** The branch name, and nothing else: the row's one icon is in its status
 * cell, and the whole of what the row has to say is behind it. */
function BranchName({ row, tall = false }: { row: LeagueRow; tall?: boolean }) {
  const link = leagueLink(row);
  return (
    <Link
      href={link.href}
      aria-label={link.label}
      // The card keeps the 44 px target a thumb needs; the table's row is
      // 42 px tall and the link is one of six cells on it.
      className={`rounded-sm font-medium text-ink underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-palm/30 ${
        tall ? "inline-flex min-h-11 items-center py-1" : ""
      }`}
    >
      {row.branch_name}
    </Link>
  );
}

/** The status cell everywhere it appears: the word, and behind the row's one
 * icon its window, the money behind its ratio and the sentences that earned
 * the word. */
function StatusCell({
  quality,
  tip,
  label,
}: {
  quality: LeagueRow["contribution_quality"];
  tip: string[];
  label: string;
}) {
  return (
    // "Reliable with limitations" is 179 px of unbreakable chip and the
    // narrow end of a six-column table has 118: the cell lets the word wrap
    // rather than clip it, and the icon after it stays reachable.
    <span className="flex flex-wrap items-center gap-x-1.5 gap-y-1 [&_span]:whitespace-normal">
      <QualityChip quality={quality} />
      <InfoTip lines={tip} label={label} />
    </span>
  );
}

function LeagueTableRow({ row }: { row: LeagueRow }) {
  return (
    <tr className="border-b border-ink/5">
      <td className="px-4 py-2.5">
        <BranchName row={row} />
      </td>
      <td className="px-4 py-2.5 text-right tabular-nums">
        {row.net_sales === null ? "-" : roundedAed(row.net_sales)}
      </td>
      <td className="px-4 py-2.5 text-right">
        {row.ratio_pct === null ? (
          <span className="text-xs text-stone">{noRatioWords(row)}</span>
        ) : (
          <span className="font-display text-[15px] font-semibold text-ink tabular-nums">
            {percent(row.ratio_pct)}
          </span>
        )}
      </td>
      <td className="px-4 py-2.5 text-right">
        {row.contribution === null ? (
          <span className="text-xs text-stone">{noContributionWords(row)}</span>
        ) : (
          <span className="font-display text-[15px] font-semibold text-ink tabular-nums">
            {roundedAed(row.contribution)}
          </span>
        )}
      </td>
      <td className="px-4 py-2.5 text-right">
        <KeptCell value={row.contribution_pct} noun="this branch" />
      </td>
      <td className="px-4 py-2.5">
        <StatusCell
          quality={leagueStatus(row).quality}
          tip={leagueTip(row)}
          label={`More about ${row.branch_name}`}
        />
      </td>
    </tr>
  );
}

function LeagueCard({ row }: { row: LeagueRow }) {
  return (
    <li className="rounded-md border border-ink/10 bg-paper p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <BranchName row={row} tall />
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
      <p className="mt-2">
        <StatusCell
          quality={leagueStatus(row).quality}
          tip={leagueTip(row)}
          label={`More about ${row.branch_name}`}
        />
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
        <td className="px-4 py-2.5">
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
            className="group inline-flex items-center gap-1.5 rounded-sm text-left font-medium text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-palm/30"
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
        <td className="px-4 py-2.5 text-right text-stone tabular-nums">
          {row.qty_sold === null ? "-" : soldCount(row.qty_sold)}
        </td>
        <td className="px-4 py-2.5 text-right tabular-nums">
          {roundedAed(row.net_item_sales)}
        </td>
        <td className="px-4 py-2.5 text-right">
          <ContributionFigure row={row} layout="table" />
        </td>
        <td className="px-4 py-2.5 text-right font-display text-[15px] font-semibold">
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
    <li className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 py-2 first:pt-0 last:pb-0">
      <p className="flex min-w-0 flex-1 items-center gap-1.5 text-sm text-ink">
        <span className="min-w-0">
          {href ? (
            <Link href={href} className="underline-offset-2 hover:underline">
              {signal.sentence}
            </Link>
          ) : (
            signal.sentence
          )}
        </span>
        <InfoTip lines={signalTip(signal)} label="More about this" />
      </p>
      <p className="font-display text-[15px] font-semibold text-ink tabular-nums">
        {signalMoney(signal)}
      </p>
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
  const [allSignals, setAllSignals] = useState(false);
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

  // One line, always: the name of the screen and what it is, the second
  // behind the icon.
  const title = (
    <h1 className="flex items-center gap-1.5 font-display text-[22px] font-semibold tracking-[-0.02em] text-ink">
      Dashboard
      <InfoTip lines={[SCREEN_ABOUT]} label="What this screen shows" />
    </h1>
  );
  const header = <header>{title}</header>;

  if (loadError) {
    return (
      <div className="space-y-5">
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
      <div className="space-y-5">
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
      <div className="space-y-5">
        {header}
        <section className="rounded-md border border-ink/10 bg-paper p-4">
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
  const chip = answerChip(result);
  const caveat = answerTip(result);
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
  const headlines = tiles(result);
  const panel = itemPanel(result.items, expanded);
  const incomplete = incompleteItems(result.items);
  const footnote = signalsFootnote(result);
  const signals = signalPanel(result.signals, allSignals);
  const moreSignals = showAllSignalsLabel(result.signals.length, allSignals);
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
    <div className="space-y-5">
      {/* The heading row and the freshness line read as one block, so they
          share a gap of their own rather than the section gap. */}
      <div>
        <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          {title}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
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
        </header>

        <p
          role="status"
          aria-live="polite"
          className="mt-1 flex flex-wrap items-center gap-x-1.5 text-[13px] text-stone"
        >
          {loading ? (
            `Loading ${choiceLabel(choice)}`
          ) : fresh ? (
            <>
              <span>{fresh.sentence}</span>
              {fresh.estimated ? <QualityChip quality="estimated" /> : null}
              {fresh.takings ? (
                <span className="tabular-nums">· {fresh.takings}</span>
              ) : null}
              {fresh.papers ? (
                <span>
                  {"· "}
                  <Link
                    href={fresh.papers.href}
                    className="font-medium text-palm underline-offset-2 hover:underline"
                  >
                    {fresh.papers.label}
                  </Link>
                </span>
              ) : null}
            </>
          ) : null}
        </p>
      </div>

      {emptyBranch ? (
        <section className="rounded-md border border-ink/10 bg-paper p-4">
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
          className={`space-y-5 ${loading ? "opacity-60" : ""}`}
        >
          {/* The answer, the hero: two sentences, its word, and the notes
              that qualify them behind the icon at the end. */}
          <p className="max-w-4xl text-[17px] leading-snug font-medium text-ink">
            {answer.empty ?? (
              <>
                {answer.branch ? <span>{answer.branch}</span> : null}
                {answer.branch && answer.item ? " " : null}
                {answer.item ? <span>{answer.item}</span> : null}
              </>
            )}
            {chip !== null ? (
              <>
                {" "}
                <QualityChip quality={chip} />
              </>
            ) : null}{" "}
            <InfoTip lines={caveat} label="What qualifies this answer" />
          </p>

          {/* The four headlines: the row in view, with the chain named beside
              it. One column on a phone, two by two on a tablet, one row on a
              laptop. */}
          {headlines.length > 0 ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {headlines.map((tile) => (
                <HeadlineTile key={tile.key} tile={tile} />
              ))}
            </div>
          ) : null}

          <section className="space-y-2">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <SectionHeading
                title="Branch league"
                tip={footnoteTip(result)}
                label="How to read the league"
              />
              <SectionLink href={LEAGUE_LINK.href} label={LEAGUE_LINK.label} />
            </div>

            {/* The league: one fixed grid so every row lines up (the sales screen's rule). */}
            <div className="hidden overflow-hidden rounded-md border border-ink/10 bg-paper sm:block">
              <table className="w-full table-fixed text-sm">
                <caption className="sr-only">
                  Branches ranked by what they kept, lowest first
                </caption>
                <colgroup>
                  <col className="w-[18%]" />
                  <col className="w-[14%]" />
                  <col className="w-[16%]" />
                  <col className="w-[16%]" />
                  <col className="w-[16%]" />
                  <col className="w-[20%]" />
                </colgroup>
                <thead>
                  <tr className="border-b border-ink/10 text-left text-[11px] leading-4 font-medium tracking-wider text-stone uppercase">
                    <th scope="col" className="px-4 py-1.5 font-medium">
                      Branch
                    </th>
                    <th scope="col" className="px-4 py-1.5 text-right font-medium">
                      Net sales
                    </th>
                    <th scope="col" className="px-4 py-1.5 text-right font-medium">
                      Purchases ÷ net sales (cash basis)
                    </th>
                    <th scope="col" className="px-4 py-1.5 text-right font-medium">
                      Contribution (est.)
                    </th>
                    <th scope="col" className="px-4 py-1.5 text-right font-medium">
                      Kept
                    </th>
                    <th scope="col" className="px-4 py-1.5 font-medium">
                      Status
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {result.league.map((row) => (
                    <LeagueTableRow key={row.branch_id} row={row} />
                  ))}
                  {result.unassigned.count > 0 ? (
                    <tr className="border-b border-ink/5 text-stone">
                      <td className="px-4 py-2.5">
                        <span className="font-medium">No branch</span>
                        <p className="text-xs">
                          {result.unassigned.count}{" "}
                          {result.unassigned.count === 1
                            ? "invoice"
                            : "invoices"}{" "}
                          with no branch
                        </p>
                      </td>
                      <td className="px-4 py-2.5 text-right">-</td>
                      <td className="px-4 py-2.5 text-right text-xs tabular-nums">
                        {roundedAed(result.unassigned.purchases)} purchases
                      </td>
                      <td className="px-4 py-2.5 text-right">-</td>
                      <td className="px-4 py-2.5 text-right">-</td>
                      <td className="px-4 py-2.5 text-xs">
                        Counted in the total, ranked nowhere.
                      </td>
                    </tr>
                  ) : null}
                  <tr className="border-t border-ink/15 font-semibold">
                    <td className="px-4 py-2.5">All branches</td>
                    <td className="px-4 py-2.5 text-right tabular-nums">
                      {roundedAed(result.total.net_sales)}
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      {result.total.ratio_pct === null ? (
                        <span className="text-xs font-normal text-stone">
                          Not rated
                        </span>
                      ) : (
                        <span className="font-display text-[15px] tabular-nums">
                          {percent(result.total.ratio_pct)}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-right">
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
                    <td className="px-4 py-2.5 text-right">
                      <KeptCell
                        value={result.total.contribution_pct}
                        noun="the chain"
                      />
                    </td>
                    <td className="px-4 py-2.5 font-normal">
                      <StatusCell
                        quality={result.total.contribution_quality}
                        tip={totalTip(result.total)}
                        label="More about all branches"
                      />
                    </td>
                  </tr>
                </tbody>
              </table>
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
                <p className="mt-2">
                  <StatusCell
                    quality={result.total.contribution_quality}
                    tip={totalTip(result.total)}
                    label="More about all branches"
                  />
                </p>
              </li>
            </ul>
          </section>

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
                    {signals.map((signal) => (
                      <SignalLine
                        key={`${signal.kind}-${signal.sentence}`}
                        signal={signal}
                      />
                    ))}
                  </ul>
                  {moreSignals ? (
                    <button
                      type="button"
                      onClick={() => setAllSignals((value) => !value)}
                      aria-expanded={allSignals}
                      className="mt-2 text-xs font-medium text-palm underline-offset-2 hover:underline"
                    >
                      {moreSignals}
                    </button>
                  ) : null}
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
              <SectionHeading
                title="Items: what each one contributed"
                tip={itemsTip()}
                label="What contribution counts"
              />
              <span className="flex flex-wrap items-baseline gap-x-3">
                {itemsHeading(result.items) ? (
                  <span className="text-xs text-stone">
                    {itemsHeading(result.items)}
                  </span>
                ) : null}
                <SectionLink href={ITEMS_LINK.href} label={ITEMS_LINK.label} />
              </span>
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
          </section>
        </section>
      )}
    </div>
  );
}
