"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { getBranches, getDashboard } from "@/lib/api";
import {
  BEST_HEADING,
  COST_COVERS,
  DEFAULT_CHOICE,
  ITEMS_LINK,
  LEAGUE_LINK,
  MOVES_ABOUT,
  MOVES_LINK,
  NO_ITEMS,
  NO_PRICE_MOVES,
  NO_SIGNALS,
  SCREEN_ABOUT,
  SIGNALS_ABOUT,
  WORST_HEADING,
  answer,
  answerChip,
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
  isFirstRun,
  itemPanel,
  itemsTip,
  keptBar,
  leagueChip,
  leagueChips,
  leagueLink,
  leagueTip,
  monthOptions,
  noContributionWords,
  noMenuSentence,
  noSalesWords,
  periodBounds,
  portionsWords,
  moveTrack,
  moveWhenLine,
  priceMoveLink,
  priceMoveMoney,
  priceMovePanel,
  priceMoveTip,
  rowChip,
  showAllLabel,
  showAllMovesLabel,
  showAllSignalsLabel,
  signalHref,
  signalMoney,
  signalName,
  signalPanel,
  signalTip,
  signalTrack,
  signalWhenLine,
  signalsChips,
  signalsFootnote,
  soldWords,
  tiles,
  tillNamesWords,
  todaysPlateLink,
  todo,
  totalTip,
  unassignedLine,
  wholePercent,
  withBranch,
  type LeagueChips,
  type PeriodChoice,
  type Tile,
  type Track,
} from "@/lib/dashboardScreen";
import { roundedAed } from "@/lib/format";
import type {
  Branch,
  DashboardItemRow,
  DashboardPriceMove,
  DashboardResult,
  DashboardSignal,
  LeagueRow,
  PeriodQuality,
} from "@/lib/types";
import { ChevronIcon } from "./icons";
import InfoTip from "./InfoTip";
import LossFigure from "./LossFigure";
import QualityChip from "./QualityChip";

/**
 * M9 WP-93: the owner dashboard, in its simple form (2026-09-08).
 *
 * The founder's brief: the owners this is for are "very simple, not at all
 * sophisticated business owners, who want data presented to them in a simple
 * way which will intrigue interest and action", and the shipped screen's
 * subtexts were "information overload". So the screen is six blocks, each
 * one question, read top to bottom:
 *
 *   the freshness line and the to-dos     what day is this, what is waiting
 *   the answer                            which branch and which dish first
 *   three tiles                           sold, kept after ingredients, paid
 *                                         to suppliers - plain words, one
 *                                         line each
 *   branches                              name, sold, kept, and the share
 *                                         kept as a bar beside its number
 *   worth a look · supplier prices        the money at stake, largest first
 *   dishes                                best earners and weakest earners
 *
 * Every sentence that qualifies a figure is one tap away behind the block's
 * or the row's one icon (the founder's 2026-09-07 pattern, `InfoTip`), and
 * the formal names the contracts pin are the first line behind the icon of
 * the figure they name. Nothing the API said is rewritten (C13.5); every
 * decision about what to print lives in `lib/dashboardScreen.ts`, where
 * vitest pins it. Never "profit", never "food cost"; a status is a word and
 * a sentence, never a colour alone.
 *
 * WP-94, the drill: every number on this screen reaches the paper it came
 * from. A branch name opens `/sales` at that branch's own row; a dish opens
 * in place and links onward to `/menu#item-<id>` for today's plate and to
 * `/invoices/<id>#line-<n>` for the line behind each ingredient's price. All
 * three are the same anchor idiom (`lib/anchor.ts`).
 */

/** The table and the card rows are both always in the DOM - only one is
 * displayed - so a ref shared between them keeps whichever React attached
 * last. This keeps only the copy that is actually on screen. */
function onScreen(el: HTMLElement | null): boolean {
  return el !== null && el.offsetParent !== null;
}

// --- small pieces ----------------------------------------------------------------

/** The share bar: mist track, palm fill, the width the API's percentage
 * already is. It never stands alone - the number it draws is always beside
 * it (the display rules). */
function ShareBar({ width, className = "w-full" }: { width: number; className?: string }) {
  return (
    <span className={`block h-1.5 overflow-hidden rounded-full bg-mist ${className}`}>
      <span className="block h-full rounded-full bg-palm" style={{ width: `${width}%` }} />
    </span>
  );
}

/** A kept share: the bar and its whole-number percentage on one line, the
 * bar first so every percentage in a column lands on the same edge. A share
 * below zero is its own negative figure in plum over an empty track. */
function KeptShare({ value, size = "md" }: { value: string | null; size?: "md" | "lg" }) {
  const width = keptBar(value);
  const figure = wholePercent(value);
  if (value === null || width === null || figure === null)
    return <span className="text-xs text-stone">-</span>;
  const figureClass =
    size === "lg"
      ? "font-display text-xl font-semibold tabular-nums"
      : "font-display text-[15px] font-semibold tabular-nums";
  return (
    <span className="flex items-center justify-end gap-2">
      <ShareBar width={width} className="max-w-[96px] shrink flex-1" />
      <span
        className={`shrink-0 ${value.startsWith("-") ? "text-plum" : "text-ink"} ${figureClass}`}
      >
        {figure}
      </span>
    </span>
  );
}

/** A kept figure in money: the rounded headline, or the loss figure with its
 * words when it is below zero, or the words for a row that has none. The
 * share beside it prints its own negative sign and nothing more, so a losing
 * row says "loses money" once. */
function KeptMoney({
  value,
  words,
  noun,
  align = "end",
  bold = true,
}: {
  value: string | null;
  words: string;
  noun: string;
  align?: "start" | "end";
  bold?: boolean;
}) {
  if (value === null) return <span className="text-xs font-normal text-stone">{words}</span>;
  if (value.startsWith("-"))
    return (
      <LossFigure figure={`-${roundedAed(value.slice(1))}`} noun={noun} align={align} />
    );
  return (
    <span
      className={`font-display text-[15px] text-ink tabular-nums ${bold ? "font-semibold" : ""}`}
    >
      {roundedAed(value)}
    </span>
  );
}

/** The quiet link at the right of a section's heading: where the whole of
 * that section lives. */
function SectionLink({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      className="text-[13px] font-medium text-palm underline-offset-2 hover:underline"
    >
      {label} &rarr;
    </Link>
  );
}

/** A section's heading: the title, the word the whole block shares where it
 * has one, and what the block is behind one icon. */
function SectionHeading({
  title,
  tip,
  label,
  chip = null,
}: {
  title: string;
  tip: string[];
  label: string;
  chip?: PeriodQuality | null;
}) {
  return (
    <h2 className="flex flex-wrap items-center gap-x-2 gap-y-1 font-display text-lg font-semibold text-ink">
      <span className="inline-flex items-center gap-1.5">
        {title}
        <InfoTip lines={tip} label={label} />
      </span>
      {chip === null ? null : <QualityChip quality={chip} />}
    </h2>
  );
}

function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-md border border-ink/10 bg-paper ${className}`}>{children}</div>
  );
}

// --- the tiles ----------------------------------------------------------------

/**
 * One headline: a plain label, the figure large, one line under it with the
 * quality word where the figure carries one, and on the kept tile the bar
 * that says how much of the sales it covers. Everything else - the formal
 * name, the notes - is behind the icon.
 */
function HeadlineTile({ tile }: { tile: Tile }) {
  return (
    <dl className="rounded-md border border-ink/10 bg-paper px-4 py-3">
      <dt className="text-[13px] font-medium text-stone">
        {tile.label}
        {tile.caption === null ? null : <span className="text-stone/70"> · {tile.caption}</span>}
      </dt>
      <dd className="mt-0.5 flex min-h-9 items-center justify-between gap-2">
        <span className="min-w-0">
          {tile.figure === null ? (
            <span className="text-sm text-stone">{tile.words}</span>
          ) : tile.loss ? (
            <LossFigure
              figure={tile.figure}
              noun="the costed sales"
              plural
              figureClass="font-display text-[30px] leading-9 font-semibold tabular-nums"
            />
          ) : (
            <span className="font-display text-[30px] leading-9 font-semibold whitespace-nowrap text-ink tabular-nums">
              {tile.figure}
            </span>
          )}
        </span>
        <span className="shrink-0">
          <InfoTip lines={tile.tip} label={`More about ${tile.label.toLowerCase()}`} />
        </span>
      </dd>
      {tile.line === "" && tile.status === null ? null : (
        <dd className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] text-stone">
          {tile.line === "" ? null : <span>{tile.line}</span>}
          {tile.status === null ? null : <QualityChip quality={tile.status} />}
        </dd>
      )}
      {tile.bar === null ? null : (
        <dd className="mt-2 flex items-center gap-2 text-[12px] text-stone">
          <ShareBar width={tile.bar.width} className="max-w-[120px] flex-1" />
          <span className="whitespace-nowrap">{tile.bar.words}</span>
        </dd>
      )}
    </dl>
  );
}

// --- the branches -------------------------------------------------------------

/** The branch name is the link, and the row's one icon rides beside it with
 * the whole of what the row has to say. */
function BranchName({ row, tall = false }: { row: LeagueRow; tall?: boolean }) {
  const link = leagueLink(row);
  return (
    <span className="inline-flex items-center gap-1.5">
      <Link
        href={link.href}
        aria-label={link.label}
        // The card keeps the 44 px target a thumb needs; the table's row is
        // 44 px tall and the link is one of four cells on it.
        className={`rounded-sm font-medium text-ink underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-palm/30 ${
          tall ? "inline-flex min-h-11 items-center py-1" : ""
        }`}
      >
        {row.branch_name}
      </Link>
      <InfoTip lines={leagueTip(row)} label={`More about ${row.branch_name}`} />
    </span>
  );
}

function LeagueTableRow({ row, chips }: { row: LeagueRow; chips: LeagueChips }) {
  const chip = rowChip(row, chips);
  return (
    <tr className="border-b border-ink/5">
      <td className="px-4 py-2">
        <BranchName row={row} />
      </td>
      <td className="px-4 py-2 text-right tabular-nums">
        {row.net_sales === null ? (
          <span className="text-xs text-stone">{noSalesWords(row)}</span>
        ) : (
          roundedAed(row.net_sales)
        )}
      </td>
      <td className="px-4 py-2 text-right">
        <KeptMoney
          value={row.contribution}
          words={noContributionWords(row)}
          noun="this branch"
        />
      </td>
      <td className="px-4 py-2 text-right">
        <KeptShare value={row.contribution_pct} />
      </td>
      {chips.perRow ? (
        <td className="px-4 py-2">{chip === null ? null : <QualityChip quality={chip} />}</td>
      ) : null}
    </tr>
  );
}

function LeagueCard({ row, chips }: { row: LeagueRow; chips: LeagueChips }) {
  const chip = rowChip(row, chips);
  return (
    <li className="rounded-md border border-ink/10 bg-paper p-3">
      <div className="flex items-start justify-between gap-3">
        <BranchName row={row} tall />
        {/* A flex child has no width of its own to draw a bar in, so the
            share gets one: the bar and the figure, the way the table's cell
            prints them. */}
        <div className="w-44 shrink-0 pt-1 text-right">
          {row.contribution_pct === null ? (
            <span className="text-xs text-stone">{noContributionWords(row)}</span>
          ) : (
            <KeptShare value={row.contribution_pct} size="lg" />
          )}
        </div>
      </div>
      <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-stone tabular-nums">
        <span>{cardLine(row)}</span>
        {chip === null ? null : <QualityChip quality={chip} />}
      </p>
    </li>
  );
}

// --- the dishes ------------------------------------------------------------------

interface ItemRowProps {
  row: DashboardItemRow;
  open: boolean;
  drillRef: React.RefObject<HTMLDivElement | null>;
  rowButtons: React.RefObject<Map<string, HTMLButtonElement>>;
  onToggle: () => void;
}

/** The in-row drill: the facts, the API's notes, the till names, and every
 * component with the invoice line behind its price. */
function ItemDrill({ row }: { row: DashboardItemRow }) {
  const portions = portionsWords(row);
  const plate = todaysPlateLink(row);
  return (
    <div className="space-y-2 pt-2 text-sm">
      <dl className="grid gap-x-6 gap-y-1 sm:grid-cols-3">
        <div>
          <dt className="text-[12px] font-medium text-stone">Portions</dt>
          <dd className="text-ink tabular-nums">{portions ?? "no quantity printed"}</dd>
        </div>
        <div>
          <dt className="text-[12px] font-medium text-stone">Costed</dt>
          <dd className="text-ink tabular-nums">
            {row.cost_per_portion === null ? "-" : `AED ${row.cost_per_portion} a plate`}
            {row.cost_per_portion_today !== null ? (
              <span className="text-stone"> · today AED {row.cost_per_portion_today}</span>
            ) : null}
          </dd>
        </div>
        <div>
          <dt className="text-[12px] font-medium text-stone">Till names</dt>
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

function ItemName({
  row,
  open,
  rowButtons,
  onToggle,
  tall = false,
}: ItemRowProps & { tall?: boolean }) {
  return (
    <button
      type="button"
      ref={(el) => {
        if (onScreen(el)) rowButtons.current.set(row.menu_item_id, el!);
      }}
      onClick={onToggle}
      aria-expanded={open}
      className={`group inline-flex items-center gap-1.5 rounded-sm text-left font-medium text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-palm/30 ${
        tall ? "min-h-11 py-1" : ""
      }`}
    >
      <ChevronIcon
        className={`h-3 w-3 shrink-0 text-stone transition-transform ${open ? "rotate-90" : ""}`}
      />
      <span className="underline-offset-2 group-hover:underline">{row.menu_item_name}</span>
      {row.quality === "estimated" ? (
        <span className="ml-1">
          <QualityChip quality="estimated" />
        </span>
      ) : null}
    </button>
  );
}

function ItemTableRow(props: ItemRowProps) {
  const { row, open, drillRef } = props;
  return (
    <>
      <tr className="border-b border-ink/5 align-middle">
        <td className="px-4 py-2">
          <ItemName {...props} />
          <p className="text-xs text-stone tabular-nums">{soldWords(row)}</p>
        </td>
        <td className="px-4 py-2 text-right">
          <KeptMoney value={row.contribution} words="-" noun="this dish" />
        </td>
        <td className="px-4 py-2 text-right">
          <KeptShare value={row.contribution_pct} />
        </td>
      </tr>
      {open ? (
        <tr className="border-b border-ink/5">
          <td colSpan={3} className="px-4 pb-3">
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

function ItemCard(props: ItemRowProps) {
  const { row, open, drillRef } = props;
  return (
    <li className="rounded-md border border-ink/10 bg-paper p-3">
      <div className="flex items-start justify-between gap-3">
        <ItemName {...props} tall />
        <div className="pt-1 text-right">
          <KeptMoney value={row.contribution} words="-" noun="this dish" align="start" />
        </div>
      </div>
      <p className="mt-0.5 flex items-center justify-between gap-3 text-xs text-stone tabular-nums">
        <span>{soldWords(row)}</span>
        <span className="w-40 shrink-0">
          <KeptShare value={row.contribution_pct} />
        </span>
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

/** One list of dishes: a table from 640 px, cards under it. */
function ItemList({
  heading,
  rows,
  open,
  drillRef,
  rowButtons,
  toggle,
}: {
  heading: string | null;
  rows: DashboardItemRow[];
  open: string | null;
  drillRef: React.RefObject<HTMLDivElement | null>;
  rowButtons: React.RefObject<Map<string, HTMLButtonElement>>;
  toggle: (id: string) => void;
}) {
  const props = (row: DashboardItemRow): ItemRowProps => ({
    row,
    open: open === row.menu_item_id,
    drillRef,
    rowButtons,
    onToggle: () => toggle(row.menu_item_id),
  });
  return (
    <div className="space-y-2">
      {heading === null ? null : (
        <h3 className="text-[13px] font-medium text-stone">{heading}</h3>
      )}
      <Card className="hidden overflow-hidden sm:block">
        <table className="w-full table-fixed text-sm">
          <caption className="sr-only">{heading ?? "Dishes ranked by what they kept"}</caption>
          <colgroup>
            <col className="w-[48%]" />
            <col className="w-[24%]" />
            <col className="w-[28%]" />
          </colgroup>
          <thead>
            <tr className="border-b border-ink/10 text-left text-[12px] font-medium text-stone">
              <th scope="col" className="px-4 py-2 font-medium">
                Dish
              </th>
              <th scope="col" className="px-4 py-2 text-right font-medium">
                Kept
              </th>
              <th scope="col" className="px-4 py-2 text-right font-medium">
                Share kept
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <ItemTableRow key={row.menu_item_id} {...props(row)} />
            ))}
          </tbody>
        </table>
      </Card>
      <ul className="space-y-2 sm:hidden">
        {rows.map((row) => (
          <ItemCard key={row.menu_item_id} {...props(row)} />
        ))}
      </ul>
    </div>
  );
}

// --- worth a look and supplier prices -----------------------------------------------

/**
 * The tracks (the founder's pick from the panels board, 2026-09-08): one row
 * shape for both panels. The name (a link to where the row leads) with the
 * row's one icon and, where there is one, the date under it; the track with
 * its two figures under it; the money on the right. The two widths come from
 * `lib/dashboardScreen.ts` as geometry; every figure printed is the API's.
 */
function TrackFigure({ track }: { track: Track }) {
  const fillClass = track.fell ? "bg-verified" : track.loss ? "bg-plum" : "bg-palm";
  return (
    <span className="block">
      <span className="relative block h-2.5 rounded-full bg-mist">
        <span
          className={`absolute inset-y-0 left-0 rounded-full ${fillClass}`}
          style={{ width: `${track.fill}%` }}
        />
        <span
          aria-hidden="true"
          className="absolute -top-1 h-[18px] w-0.5 rounded-sm bg-gold"
          style={{ left: `calc(${track.tick}% - 1px)` }}
        />
      </span>
      <span className="mt-1 flex min-h-[19px] items-center justify-between gap-2 text-[11.5px] text-stone tabular-nums">
        <span>
          <b className={`font-semibold ${track.loss ? "text-plum" : "text-ink"}`}>
            {track.left.figure}
          </b>{" "}
          {track.left.words}
        </span>
        <span className="flex items-center gap-1 text-caution">
          {track.right}
          {track.change === null ? null : (
            <span
              className={`rounded-sm px-1.5 py-0.5 text-[11px] font-medium ${
                track.fell ? "bg-mist text-verified" : "bg-gold-soft text-caution"
              }`}
            >
              {track.change}
            </span>
          )}
        </span>
      </span>
    </span>
  );
}

function TrackRow({
  name,
  href,
  when,
  chip,
  tip,
  tipLabel,
  track,
  words,
  money,
  moneyWords,
}: {
  name: string;
  href: string | null;
  when: string | null;
  chip: PeriodQuality | null;
  tip: string[];
  tipLabel: string;
  track: Track | null;
  /** What stands in the track's place when there is nothing to draw. */
  words: string | null;
  money: string | null;
  moneyWords: string | null;
}) {
  return (
    <li className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1.5 py-2.5 first:pt-0 last:pb-0 sm:grid-cols-[9.5rem_minmax(0,1fr)_auto] sm:gap-y-0">
      <div className="col-start-1 row-start-1 min-w-0">
        {/* Inline, not a flex row: a long name wraps to a second line and
            the icon and the chip stay on its last word instead of dropping
            to a line of their own (seen live on "Hot Chocolate - Large 250
            ml", 2026-09-08). */}
        <p className="text-sm leading-5 font-semibold text-ink">
          {href ? (
            <Link href={href} className="underline-offset-2 hover:underline">
              {name}
            </Link>
          ) : (
            <span>{name}</span>
          )}
          {chip === null ? null : (
            <>
              {" "}
              <QualityChip quality={chip} />
            </>
          )}{" "}
          <InfoTip lines={tip} label={tipLabel} />
        </p>
        {when === null ? null : <p className="text-[11px] leading-tight text-stone">{when}</p>}
      </div>
      <div className="col-span-2 row-start-2 min-w-0 sm:col-span-1 sm:col-start-2 sm:row-start-1">
        {track === null ? (
          <p className="text-[12.5px] leading-snug text-stone">{words}</p>
        ) : (
          <TrackFigure track={track} />
        )}
      </div>
      <p className="col-start-2 row-start-1 shrink-0 text-right sm:col-start-3">
        {money === null ? null : (
          <span className="block font-display text-[15px] font-semibold text-ink tabular-nums">
            {money}
          </span>
        )}
        {moneyWords === null ? null : (
          <span className="block text-[11px] leading-tight text-stone">{moneyWords}</span>
        )}
      </p>
    </li>
  );
}

function SignalRow({ signal, chips }: { signal: DashboardSignal; chips: LeagueChips }) {
  return (
    <TrackRow
      name={signalName(signal)}
      href={signalHref(signal)}
      when={signalWhenLine(signal)}
      chip={chips.perRow && signal.quality === "estimated" ? "estimated" : null}
      tip={signalTip(signal)}
      tipLabel={`More about ${signalName(signal)}`}
      track={signalTrack(signal)}
      words={signal.sentence}
      money={signalMoney(signal)}
      moneyWords="at stake"
    />
  );
}

function MoveRow({ move }: { move: DashboardPriceMove }) {
  const money = priceMoveMoney(move);
  const link = priceMoveLink(move);
  return (
    <TrackRow
      name={move.ingredient_name}
      href={link === null ? null : link.href}
      when={moveWhenLine(move)}
      chip={null}
      tip={priceMoveTip(move)}
      tipLabel={`More about ${move.ingredient_name}`}
      track={moveTrack(move)}
      words={move.sentence}
      money={money === null ? null : money.figure}
      moneyWords={money === null ? null : money.words}
    />
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
  const [allMoves, setAllMoves] = useState(false);
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
          error instanceof Error ? error.message : "Could not load the dashboard.",
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
        <div role="alert" className="rounded-md border border-ink/10 bg-paper p-6">
          <p className="text-sm font-medium text-ink">Could not load the dashboard</p>
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
        <div aria-busy="true" className="rounded-md border border-ink/10 bg-paper p-6">
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
          <h2 className="font-display text-lg font-semibold text-ink">{first.heading}</h2>
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
  const todos = todo(result);
  const lead = answer(result);
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
  const chips = leagueChips(result);
  const perRow = chips.perRow;
  const unassigned = unassignedLine(result.unassigned);
  const panel = itemPanel(result.items, expanded);
  const footnote = signalsFootnote(result);
  const signals = signalPanel(result.signals, allSignals);
  const signalChips = signalsChips(result.signals);
  const moreSignals = showAllSignalsLabel(result.signals.length, allSignals);
  const moves = priceMovePanel(result.price_moves.moves, allMoves);
  const moreMoves = showAllMovesLabel(result.price_moves.moves.length, allMoves);
  const toggle = (id: string) => setOpen((current) => (current === id ? null : id));

  const pickBranch = (id: string) => {
    const query = withBranch(searchParams.toString(), id === "" ? null : id);
    setLoading(true);
    setOpen(null);
    router.replace(query === "" ? pathname : `${pathname}?${query}`);
  };

  const listProps = { open, drillRef, rowButtons, toggle };

  return (
    <div className="space-y-5">
      {/* The heading row, the freshness line and the to-dos read as one
          block, so they share a gap of their own rather than the section gap. */}
      <div className="space-y-2">
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

        {/* The day the sales run to on the left, and on the right the
            to-dos: a count and a door each, only where there is something
            behind it. One row on a laptop, wrapping under it. */}
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <p
            role="status"
            aria-live="polite"
            className="flex min-h-8 flex-wrap items-center gap-x-2 text-[13px] text-stone"
          >
            {loading ? (
              `Loading ${choiceLabel(choice)}`
            ) : fresh ? (
              <>
                <span>{fresh.sentence}</span>
                {fresh.estimated ? <QualityChip quality="estimated" /> : null}
              </>
            ) : null}
          </p>
          {todos.length === 0 ? null : (
            <ul className="flex flex-wrap gap-2">
              {todos.map((item) => (
                <li
                  key={item.key}
                  className="inline-flex items-center gap-1 rounded-sm bg-gold-soft pr-2"
                >
                  <Link
                    href={item.href}
                    className="inline-flex min-h-8 items-center gap-1.5 py-1 pr-1 pl-3 text-[13px] font-medium text-caution underline-offset-2 hover:underline"
                  >
                    {item.label} &rarr;
                  </Link>
                  {item.tip.length === 0 ? null : (
                    <span className="text-caution">
                      <InfoTip lines={item.tip} label={`More about ${item.label}`} />
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
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
        <section aria-busy={loading} className={`space-y-5 ${loading ? "opacity-60" : ""}`}>
          {/* The answer: the API's lines as bullets, the word it carries and
              the notes behind the icon at the card's right. */}
          <section className="rounded-md border border-ink/10 border-l-4 border-l-gold bg-paper px-5 py-3">
            <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
              {lead.own ? (
                <p className="max-w-3xl text-[16px] leading-snug font-medium text-ink">
                  {lead.lines[0]}
                </p>
              ) : (
                <ul className="max-w-3xl list-disc space-y-1 pl-5 font-display text-[18px] leading-7 font-semibold text-ink marker:text-gold">
                  {lead.lines.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              )}
              {chip === null && caveat.length === 0 ? null : (
                <span className="flex shrink-0 items-center gap-2 pt-1">
                  {chip !== null ? <QualityChip quality={chip} /> : null}
                  <InfoTip lines={caveat} label="What qualifies this answer" />
                </span>
              )}
            </div>
          </section>

          {/* Three headlines: one column on a phone, one row from a tablet. */}
          {headlines.length > 0 ? (
            <div className="grid gap-3 sm:grid-cols-3">
              {headlines.map((tile) => (
                <HeadlineTile key={tile.key} tile={tile} />
              ))}
            </div>
          ) : null}

          {/* The branches: name, sold, kept, and the share kept beside its bar. */}
          <section className="space-y-2">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <SectionHeading
                title="Branches"
                tip={footnoteTip(result)}
                label="How to read the branches"
                chip={leagueChip(result)}
              />
              <SectionLink href={LEAGUE_LINK.href} label={LEAGUE_LINK.label} />
            </div>

            <Card className="hidden overflow-hidden sm:block">
              <table className="w-full table-fixed text-sm">
                <caption className="sr-only">
                  Branches ranked by what they kept, lowest first
                </caption>
                <colgroup>
                  <col className={perRow ? "w-[28%]" : "w-[34%]"} />
                  <col className="w-[20%]" />
                  <col className="w-[20%]" />
                  <col className="w-[26%]" />
                  {perRow ? <col className="w-[16%]" /> : null}
                </colgroup>
                <thead>
                  <tr className="border-b border-ink/10 text-left text-[12px] font-medium text-stone">
                    <th scope="col" className="px-4 py-2 font-medium">
                      Branch
                    </th>
                    <th scope="col" className="px-4 py-2 text-right font-medium">
                      Sold
                    </th>
                    <th scope="col" className="px-4 py-2 text-right font-medium">
                      Kept
                    </th>
                    <th scope="col" className="px-4 py-2 text-right font-medium">
                      Share kept
                    </th>
                    {perRow ? (
                      <th scope="col" className="px-4 py-2 font-medium">
                        Status
                      </th>
                    ) : null}
                  </tr>
                </thead>
                <tbody>
                  {result.league.map((row) => (
                    <LeagueTableRow key={row.branch_id} row={row} chips={chips} />
                  ))}
                  <tr className="border-t border-ink/15 font-semibold">
                    <td className="px-4 py-2">
                      <span className="inline-flex items-center gap-1.5">
                        All branches
                        <InfoTip lines={totalTip(result.total)} label="More about all branches" />
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {roundedAed(result.total.net_sales)}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <KeptMoney
                        value={result.total.contribution}
                        words={noMenu ?? "Nothing costed"}
                        noun="the chain"
                        bold={false}
                      />
                    </td>
                    <td className="px-4 py-2 text-right">
                      <KeptShare value={result.total.contribution_pct} />
                    </td>
                    {perRow ? (
                      <td className="px-4 py-2 font-normal">
                        {rowChip(result.total, chips) === null ? null : (
                          <QualityChip quality={result.total.contribution_quality} />
                        )}
                      </td>
                    ) : null}
                  </tr>
                </tbody>
              </table>
              {unassigned === null ? null : (
                <p className="border-t border-ink/5 px-4 py-2 text-xs text-stone">{unassigned}</p>
              )}
            </Card>

            {/* Cards under 640 px: the share kept as the large figure. */}
            <ul className="space-y-2 sm:hidden">
              {result.league.map((row) => (
                <LeagueCard key={row.branch_id} row={row} chips={chips} />
              ))}
              <li className="rounded-md border border-ink/15 bg-paper p-3">
                <div className="flex items-start justify-between gap-3">
                  <p className="inline-flex min-h-11 items-center gap-1.5 py-1 font-semibold text-ink">
                    All branches
                    <InfoTip lines={totalTip(result.total)} label="More about all branches" />
                  </p>
                  <div className="w-44 shrink-0 pt-1 text-right">
                    {result.total.contribution_pct === null ? (
                      <span className="text-xs text-stone">{noMenu ?? "Nothing costed"}</span>
                    ) : (
                      <KeptShare value={result.total.contribution_pct} size="lg" />
                    )}
                  </div>
                </div>
                <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-stone tabular-nums">
                  <span>
                    {result.total.contribution === null
                      ? `${roundedAed(result.total.net_sales)} sold`
                      : `Kept ${roundedAed(result.total.contribution)} of ${roundedAed(result.total.net_sales)} sold`}
                  </span>
                  {rowChip(result.total, chips) === null ? null : (
                    <QualityChip quality={result.total.contribution_quality} />
                  )}
                </p>
                {unassigned === null ? null : <p className="mt-1 text-xs text-stone">{unassigned}</p>}
              </li>
            </ul>
          </section>

          {/* Two panels, side by side from a laptop and one under the other
              below it, held to one height: where the money is, and what the
              suppliers did to the prices behind it - each row a track. */}
          <div className="grid items-stretch gap-5 lg:grid-cols-2">
            <section className="flex flex-col gap-2">
              <SectionHeading
                title="Worth a look"
                tip={[SIGNALS_ABOUT]}
                label="What this list is"
                chip={signalChips.shared === "estimated" ? "estimated" : null}
              />
              <Card className="flex flex-1 flex-col px-4 py-3">
                {result.signals.length === 0 ? (
                  <p className="text-sm text-stone">{footnote ?? NO_SIGNALS}</p>
                ) : (
                  <>
                    <ul className="divide-y divide-ink/5">
                      {signals.map((signal) => (
                        <SignalRow
                          key={`${signal.kind}-${signal.sentence}`}
                          signal={signal}
                          chips={signalChips}
                        />
                      ))}
                    </ul>
                    <div className="mt-auto flex flex-wrap items-baseline gap-x-3 gap-y-1 pt-2.5">
                      {moreSignals ? (
                        <button
                          type="button"
                          onClick={() => setAllSignals((value) => !value)}
                          aria-expanded={allSignals}
                          className="text-[13px] font-medium text-palm underline-offset-2 hover:underline"
                        >
                          {moreSignals}
                        </button>
                      ) : null}
                      {footnote ? <p className="text-xs text-stone">{footnote}</p> : null}
                    </div>
                  </>
                )}
              </Card>
            </section>

            <section className="flex flex-col gap-2">
              <SectionHeading title="Supplier prices" tip={[MOVES_ABOUT]} label="What this list is" />
              <Card className="flex flex-1 flex-col px-4 py-3">
                {moves.length === 0 ? null : (
                  <ul className="divide-y divide-ink/5">
                    {moves.map((move) => (
                      <MoveRow key={move.ingredient_id} move={move} />
                    ))}
                  </ul>
                )}
                <div
                  className={`flex flex-wrap items-baseline gap-x-3 gap-y-1 ${
                    moves.length === 0 ? "" : "mt-auto pt-2.5"
                  }`}
                >
                  {moves.length === 0 ? (
                    <p className="text-sm text-stone">{NO_PRICE_MOVES}</p>
                  ) : moreMoves ? (
                    <button
                      type="button"
                      onClick={() => setAllMoves((value) => !value)}
                      aria-expanded={allMoves}
                      className="text-[13px] font-medium text-palm underline-offset-2 hover:underline"
                    >
                      {moreMoves}
                    </button>
                  ) : null}
                  <span className="ml-auto">
                    <SectionLink href={MOVES_LINK.href} label={MOVES_LINK.label} />
                  </span>
                </div>
              </Card>
            </section>
          </div>

          {/* The dishes: the best earners and the weakest, five and five,
              each opening in place to the paper behind its price. */}
          <section className="space-y-2">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <SectionHeading title="Dishes" tip={itemsTip()} label="What kept means for a dish" />
              <SectionLink href={ITEMS_LINK.href} label={ITEMS_LINK.label} />
            </div>
            {panel.kind === "none" ? (
              <Card className="px-4 py-3">
                <p className="text-sm text-stone">{noMenu ?? NO_ITEMS}</p>
              </Card>
            ) : panel.kind === "all" ? (
              <ItemList heading={null} rows={panel.rows} {...listProps} />
            ) : (
              <div className="grid gap-4 lg:grid-cols-2">
                <ItemList heading={BEST_HEADING} rows={panel.top} {...listProps} />
                <ItemList heading={WORST_HEADING} rows={panel.bottom} {...listProps} />
              </div>
            )}
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
          </section>
        </section>
      )}
    </div>
  );
}
