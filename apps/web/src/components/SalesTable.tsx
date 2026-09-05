"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { salesAnchorBranchId } from "@/lib/anchor";
import {
  excludeTillItem,
  getSalesBranches,
  getSalesCoverage,
  listMenuItems,
  mapTillItem,
  unmapTillItem,
} from "@/lib/api";
import { groupedMoney, roundedAed } from "@/lib/format";
import { isoToday } from "@/lib/salesLoad";
import {
  DEFAULT_CHOICE,
  answerSentence,
  bucketsLine,
  choiceKey,
  choiceLabel,
  collapseDays,
  costedSentence,
  exVatWords,
  freshnessSentence,
  headline,
  mappedWords,
  monthOptions,
  noRatioWords,
  paperName,
  percent,
  periodBounds,
  segmentWords,
  statusSentence,
  windowLine,
  type PeriodChoice,
} from "@/lib/salesScreen";
import type {
  BranchRow,
  CoverageItem,
  CoverageQueueItem,
  ExcludedPaper,
  InvoiceFigure,
  MenuItemSummary,
  PendingPaper,
  SalesBranchesResult,
  SalesCoverageResult,
} from "@/lib/types";
import { ChevronIcon } from "./icons";
import QualityChip from "./QualityChip";

/**
 * M8 WP-84: the sales screen - variant B, "Answer first" (design review
 * 2026-09-03, approved by the founder 2026-09-04).
 *
 * Reader order: the period and how fresh the sales are; one sentence naming
 * the branch to look at first in the "of every 100" lens; the ranked table
 * as the evidence, with the "No branch" row only when papers have none and
 * the chain total as its last row; the direction footnote; then, on a mist
 * panel below, the consultant's queue - recipe coverage by sales value with
 * the till names not yet mapped, one keystroke each.
 *
 * The honesty rules carry through from the menu screen: status is a word
 * and the API's own sentence, never a colour alone; a row that cannot carry
 * a ratio shows words in its place, never 0%; headline money is rounded to
 * whole dirhams and the drill shows the two printed figures a paper's photo
 * shows; the word is *costed*, never *complete*, and "food cost" appears
 * nowhere. Everything derives on read: a manual reload after confirming an
 * invoice is the demo's own gesture, and nothing here polls.
 *
 * M9 WP-94: the screen answers `/sales#branch-<id>`, the app's one anchor
 * idiom (`lib/anchor.ts`). A league row on the dashboard names a branch; this
 * is where its days and its papers are, so the link lands on that branch's
 * own row, open, in the middle of the screen and holding the focus.
 */

type Feedback = { kind: "error" | "done"; text: string } | null;

/** The table and the card rows are both always in the DOM - only one is
 * displayed - so a ref shared between them keeps whichever React attached
 * last. This keeps only the copy that is actually on screen (the menu
 * screen's rule). */
function onScreen(el: HTMLElement | null): boolean {
  return el !== null && el.offsetParent !== null;
}

function RatioFigure({ row }: { row: BranchRow }) {
  if (row.ratio_pct === null) {
    return <span className="text-xs text-stone">{noRatioWords(row)}</span>;
  }
  return (
    <span className="font-display text-[15px] font-semibold text-ink tabular-nums">
      {percent(row.ratio_pct)}
    </span>
  );
}

function InvoiceLink({ id, children = "See the invoice" }: { id: string; children?: string }) {
  return (
    <Link
      href={`/invoices/${id}`}
      className="font-medium text-palm underline-offset-2 hover:underline"
    >
      {children}
    </Link>
  );
}

/** One counted paper: its name and number, the ex-VAT arithmetic the photo
 * shows, and the link. An estimated figure says what made it so. */
function PaperLine({ figure }: { figure: InvoiceFigure }) {
  return (
    <p className="text-xs text-ink">
      <span className="font-medium">{paperName(figure)}</span>
      <span className="text-stone"> · </span>
      <span className="tabular-nums">{exVatWords(figure)}</span>
      {figure.quality === "estimated" ? (
        <span className="text-caution"> · total or VAT entered by hand</span>
      ) : null}
      <span className="text-stone"> · </span>
      <InvoiceLink id={figure.invoice_id} />
    </p>
  );
}

/** A paper on its way, in the estimated tone under the confirmed ones. */
function PendingLine({ paper }: { paper: PendingPaper }) {
  const status = paper.status === "awaiting_confirm" ? "awaiting confirm" : "held for review";
  return (
    <p className="text-xs text-caution">
      <span className="font-medium">{paperName(paper)}</span> · {status}
      {paper.undated ? ", no date printed" : ""} · not counted yet ·{" "}
      <InvoiceLink id={paper.invoice_id} />
    </p>
  );
}

function ExcludedLine({ paper }: { paper: ExcludedPaper }) {
  return (
    <p className="text-xs text-stone">
      <span className="font-medium text-ink">{paperName(paper)}</span> · {paper.currency}{" "}
      <span className="tabular-nums">{paper.total === null ? "-" : groupedMoney(paper.total)}</span>{" "}
      · in {paper.currency}, not counted · <InvoiceLink id={paper.invoice_id} />
    </p>
  );
}

/**
 * The in-row drill: every day of the window with its net sales and the
 * papers dated that day, runs of paperless days collapsed to one line; then
 * the papers still on their way and the ones in another currency. Day net
 * sales are headline figures (whole dirhams); a paper's figures are the
 * printed ones, to the fil.
 */
function BranchDrill({ row, layout }: { row: BranchRow; layout: "table" | "card" }) {
  if (row.days.length === 0 && row.pending.length === 0 && row.excluded.length === 0) {
    return <p className="pt-2 text-xs text-stone">Nothing loaded and no papers in this window.</p>;
  }
  const placed = new Set(
    row.pending.map((paper) => paper.placed_on).filter((date): date is string => date !== null),
  );
  const segments = collapseDays(row.days, placed);
  const dated = new Set(row.days.map((day) => day.business_date));
  const pendingOn = (date: string) => row.pending.filter((paper) => paper.placed_on === date);
  const unplaced = row.pending.filter(
    (paper) => paper.placed_on === null || !dated.has(paper.placed_on),
  );
  const lines = segments.map((segment) => {
    const net = segment.kind === "day" ? segment.day.net_sales : segment.net_sales;
    // A day with only pending papers has nothing counted yet: no figure, not
    // a zero - the pending line underneath says what is on its way.
    const purchases =
      segment.kind === "day" && segment.day.invoices.length > 0 ? segment.day.purchases : null;
    const papers =
      segment.kind === "day" ? (
        <>
          {segment.day.invoices.map((figure) => (
            <PaperLine key={figure.invoice_id} figure={figure} />
          ))}
          {pendingOn(segment.day.business_date).map((paper) => (
            <PendingLine key={paper.invoice_id} paper={paper} />
          ))}
          {segment.day.net_sales === null ? (
            <p className="text-xs text-stone">No sales loaded this day.</p>
          ) : null}
        </>
      ) : (
        <>
          <p className="text-xs text-stone">
            {segment.days === 1 ? "No papers dated this day." : "No papers dated these days."}
          </p>
          {segment.days === 1 ? pendingOn(segment.from).map((paper) => (
            <PendingLine key={paper.invoice_id} paper={paper} />
          )) : null}
        </>
      );
    return { key: segment.kind === "day" ? segment.day.business_date : segment.from, words: segmentWords(segment), net, purchases, papers };
  });

  const trailing =
    unplaced.length > 0 || row.excluded.length > 0 ? (
      <div className="space-y-1 pt-2">
        {unplaced.map((paper) => (
          <PendingLine key={paper.invoice_id} paper={paper} />
        ))}
        {row.excluded.map((paper) => (
          <ExcludedLine key={paper.invoice_id} paper={paper} />
        ))}
      </div>
    ) : null;

  if (layout === "card") {
    return (
      <div className="mt-2 border-t border-ink/10 pt-2">
        <ul className="divide-y divide-ink/5">
          {lines.map((line) => (
            <li key={line.key} className="space-y-1 py-2">
              <p className="text-sm font-medium text-ink">{line.words}</p>
              <p className="text-xs text-stone tabular-nums">
                Net sales {headline(line.net)}
                {line.purchases !== null ? ` · purchases AED ${groupedMoney(line.purchases)}` : ""}
              </p>
              {line.papers}
            </li>
          ))}
        </ul>
        {trailing}
      </div>
    );
  }
  return (
    <div className="border-t border-ink/10 pt-1">
      <table className="w-full table-fixed text-sm">
        <caption className="sr-only">{row.branch_name}, day by day</caption>
        <colgroup>
          <col className="w-[30%]" />
          <col className="w-[16%]" />
          <col className="w-[16%]" />
          <col className="w-[38%]" />
        </colgroup>
        <thead>
          <tr className="text-left text-[11px] font-medium tracking-wider text-stone uppercase">
            <th scope="col" className="py-1 pr-2 font-medium">
              Day
            </th>
            <th scope="col" className="py-1 text-right font-medium">
              Net sales
            </th>
            <th scope="col" className="py-1 text-right font-medium">
              Purchases
            </th>
            <th scope="col" className="py-1 pl-4 font-medium">
              Papers
            </th>
          </tr>
        </thead>
        <tbody>
          {lines.map((line) => (
            <tr key={line.key} className="border-b border-ink/5 last:border-b-0 align-top">
              <td className="py-2 pr-2 font-medium text-ink">{line.words}</td>
              <td className="py-2 text-right text-stone tabular-nums">{headline(line.net)}</td>
              <td className="py-2 text-right text-stone tabular-nums">
                {line.purchases !== null ? `AED ${groupedMoney(line.purchases)}` : "-"}
              </td>
              <td className="space-y-1 py-2 pl-4">{line.papers}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {trailing}
    </div>
  );
}

interface RowProps {
  row: BranchRow;
  open: boolean;
  drillRef: React.RefObject<HTMLDivElement | null>;
  rowButtons: React.RefObject<Map<string, HTMLButtonElement>>;
  onToggle: () => void;
}

function BranchTableRow({ row, open, drillRef, rowButtons, onToggle }: RowProps) {
  return (
    <>
      <tr className="border-b border-ink/5 align-top">
        <td className="px-4 py-2">
          <button
            type="button"
            ref={(el) => {
              if (onScreen(el)) rowButtons.current.set(row.branch_id, el!);
            }}
            onClick={onToggle}
            aria-expanded={open}
            className="group inline-flex min-h-11 items-center gap-1.5 rounded-sm py-1 text-left font-medium text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-palm/30"
          >
            <ChevronIcon
              className={`h-3 w-3 shrink-0 text-stone transition-transform ${open ? "rotate-90" : ""}`}
            />
            <span className="underline-offset-2 group-hover:underline">{row.branch_name}</span>
          </button>
          <p className="text-xs text-stone">{windowLine(row)}</p>
        </td>
        <td className="px-4 py-3 text-right tabular-nums">{headline(row.net_sales)}</td>
        <td className="px-4 py-3 text-right tabular-nums">
          {row.deliveries > 0 ? roundedAed(row.purchases) : "-"}
        </td>
        <td className="px-4 py-3 text-right">
          <RatioFigure row={row} />
        </td>
        <td className="px-4 py-3">
          <QualityChip quality={row.quality} />
          <p className="mt-1 text-xs text-stone">{statusSentence(row.quality, row.notes)}</p>
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
              <BranchDrill row={row} layout="table" />
            </div>
          </td>
        </tr>
      ) : null}
    </>
  );
}

function BranchCard({ row, open, drillRef, rowButtons, onToggle }: RowProps) {
  return (
    <li className="rounded-md border border-ink/10 bg-paper p-3">
      <div className="flex items-start justify-between gap-3">
        <button
          type="button"
          ref={(el) => {
            if (onScreen(el)) rowButtons.current.set(row.branch_id, el!);
          }}
          onClick={onToggle}
          aria-expanded={open}
          className="group inline-flex min-h-11 items-center gap-1.5 rounded-sm py-1 text-left font-medium text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-palm/30"
        >
          <ChevronIcon
            className={`h-3 w-3 shrink-0 text-stone transition-transform ${open ? "rotate-90" : ""}`}
          />
          <span className="underline-offset-2 group-hover:underline">{row.branch_name}</span>
        </button>
        <div className="pt-1 text-right">
          {row.ratio_pct === null ? (
            <span className="text-xs text-stone">{noRatioWords(row)}</span>
          ) : (
            <span className="font-display text-xl font-semibold text-ink tabular-nums">
              {percent(row.ratio_pct)}
            </span>
          )}
        </div>
      </div>
      <p className="mt-0.5 text-xs text-stone tabular-nums">
        Net sales {headline(row.net_sales)} · Purchases{" "}
        {row.deliveries > 0 ? roundedAed(row.purchases) : "-"} · {windowLine(row)}
      </p>
      <p className="mt-2 text-xs text-stone">
        <QualityChip quality={row.quality} />{" "}
        <span className="align-middle">{statusSentence(row.quality, row.notes)}</span>
      </p>
      {open ? (
        <div
          ref={(el) => {
            if (onScreen(el)) drillRef.current = el;
          }}
          tabIndex={-1}
          className="focus:outline-none"
        >
          <BranchDrill row={row} layout="card" />
        </div>
      ) : null}
    </li>
  );
}

/** The pick-from-the-menu form, shared by a queue row and a name marked not
 * a menu item (mapping is the one way such a name comes back). */
function PickForm({
  liveMenu,
  draftPick,
  onDraft,
  onSave,
  onCancel,
  busy,
  selectRef,
}: {
  liveMenu: MenuItemSummary[];
  draftPick: string;
  onDraft: (value: string) => void;
  onSave: () => void;
  onCancel: () => void;
  busy: boolean;
  selectRef: React.RefObject<HTMLSelectElement | null>;
}) {
  return (
    <form
      className="mt-3 flex flex-wrap items-end gap-2 border-t border-ink/10 pt-3"
      onSubmit={(event) => {
        event.preventDefault();
        onSave();
      }}
    >
      <label className="flex flex-col gap-1 text-sm font-medium text-stone">
        Which menu item is it?
        <select
          ref={selectRef}
          value={draftPick}
          onChange={(event) => onDraft(event.target.value)}
          className="min-h-11 w-64 rounded-sm border border-ink/20 bg-paper px-2 py-1.5 text-sm text-ink"
        >
          <option value="">Choose</option>
          {liveMenu.map((row) => (
            <option key={row.id} value={row.id}>
              {row.name}
            </option>
          ))}
        </select>
      </label>
      <button
        type="submit"
        disabled={busy || draftPick === ""}
        className="min-h-11 rounded-sm bg-palm px-3 py-1.5 text-sm font-semibold text-cream hover:bg-palm-deep disabled:opacity-50"
      >
        Save
      </button>
      <button
        type="button"
        onClick={onCancel}
        className="min-h-11 rounded-sm px-2 py-1.5 text-sm font-medium text-stone hover:text-ink"
      >
        Cancel
      </button>
    </form>
  );
}

const NO_BRANCH_ID = "(no branch)";

/** The papers the ranking could not place: counted in the total, ranked
 * nowhere, muted, and only on the screen when there are any. */
function NoBranchPapers({ result }: { result: SalesBranchesResult }) {
  return (
    <div className="space-y-1 border-t border-ink/10 pt-2">
      {result.unassigned.invoices.map((figure) => (
        <PaperLine key={figure.invoice_id} figure={figure} />
      ))}
    </div>
  );
}

export default function SalesTable() {
  const [choice, setChoice] = useState<PeriodChoice>(DEFAULT_CHOICE);
  const [result, setResult] = useState<SalesBranchesResult | null>(null);
  const [coverage, setCoverage] = useState<SalesCoverageResult | null>(null);
  const [menu, setMenu] = useState<MenuItemSummary[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [picking, setPicking] = useState<string | null>(null);
  const [draftPick, setDraftPick] = useState("");
  const [showMapped, setShowMapped] = useState(false);
  const drillRef = useRef<HTMLDivElement>(null);
  const rowButtons = useRef<Map<string, HTMLButtonElement>>(new Map());
  const lastOpened = useRef<string | null>(null);
  // WP-94: the branch the hash named and has yet to be opened, the one it
  // named (so the focus effect knows the reader arrived by link), and the
  // guard that honours a hash once per mount and never again.
  const pending = useRef<string | null>(null);
  const anchored = useRef<string | null>(null);
  const arrived = useRef(false);
  const pickSelect = useRef<HTMLSelectElement>(null);
  // The tenant's newest loaded day, learned from the first read and read back
  // by later ones - a ref, not a dep, so the read that learns it does not
  // re-run itself (the effect below fired twice per visit when it was state).
  const salesThroughRef = useRef<string | null>(null);
  // The period the screen is showing, so a coverage refresh that comes back
  // after a period switch is dropped rather than put under another window's table.
  const periodKeyRef = useRef<string>(choiceKey(DEFAULT_CHOICE));
  const queueRows = useRef<Map<string, HTMLLIElement>>(new Map());
  // Where focus goes once the coverage read after a decision lands: the queue
  // position the acted-on row held, so one keystroke per name stays one
  // keystroke per name instead of a Tab from the top of the page each time.
  const pendingFocus = useRef<number | null>(null);

  // Both reads and the menu (for the pick-from-the-menu path) are fetched
  // together and land as one, so the table and the panel below it can never
  // disagree about the period. The state lands in an async callback rather
  // than the effect body - the shipped pattern.
  useEffect(() => {
    let cancelled = false;
    periodKeyRef.current = choiceKey(choice);
    const range = periodBounds(choice, salesThroughRef.current);
    (async () => {
      try {
        const [branches, cover, items] = await Promise.all([
          getSalesBranches(range?.from, range?.to),
          getSalesCoverage(range?.from, range?.to),
          listMenuItems(),
        ]);
        if (cancelled) return;
        salesThroughRef.current = branches.period.sales_through;
        setResult(branches);
        setCoverage(cover);
        setMenu(items);
        setLoadError(null);
        // The /sales#branch-<id> anchor (WP-94), decided on the read that has
        // just landed. Once per mount: the guard is what stops the next read -
        // a period change, a mapping decision, the "try again" button - from
        // yanking the reader's focus back to the row they arrived at and have
        // since left. A hash naming no branch of this tenant opens nothing and
        // errors nothing.
        if (!arrived.current) {
          arrived.current = true;
          pending.current = salesAnchorBranchId(window.location.hash, branches.rows);
        }
      } catch (error) {
        if (cancelled) return;
        setLoadError(error instanceof Error ? error.message : "Could not load sales.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [choice, reloadKey]);

  // Focus follows the drill: into the expansion when it opens, back to the
  // row's own button when it collapses. A reader who arrived by link gets the
  // row put in the middle of the screen first, so the branch's own figures
  // are above the days rather than off the top of them.
  useEffect(() => {
    if (open !== null) {
      lastOpened.current = open;
      if (anchored.current === open) {
        anchored.current = null;
        rowButtons.current.get(open)?.scrollIntoView({ block: "center" });
        drillRef.current?.focus({ preventScroll: true });
        return;
      }
      drillRef.current?.focus();
    } else if (lastOpened.current !== null) {
      rowButtons.current.get(lastOpened.current)?.focus();
      lastOpened.current = null;
    }
  }, [open]);

  // Taking the reader to the branch the hash named, in the render that put it
  // on the screen - the DOM only, in the /materials#material-<id> shape. The
  // row is opened by pressing its own button, the same door a reader presses.
  useEffect(() => {
    const branchId = pending.current;
    if (branchId === null || result === null) return;
    pending.current = null;
    anchored.current = branchId;
    rowButtons.current.get(branchId)?.click();
  }, [result]);

  useEffect(() => {
    if (picking !== null) pickSelect.current?.focus();
  }, [picking]);

  // After a decision the acted-on row has left the queue and React removed
  // the element that held focus; move it to the row now at that position.
  useEffect(() => {
    const position = pendingFocus.current;
    if (position === null || coverage === null) return;
    pendingFocus.current = null;
    const queue = coverage.queue;
    if (queue.length === 0) return;
    const next = queue[Math.min(position, queue.length - 1)];
    queueRows.current.get(next.till_item_id)?.focus();
  }, [coverage]);

  /** Every decision goes through here: one write, then the coverage read
   * again - the value follows the mapping on the next read, and the ratio
   * above does not move (a mapping changes no purchase and no sale). The
   * write and the refresh are reported apart: a refresh that fails is said as
   * a refresh that failed, never as a write that did not happen, because the
   * server has already kept its audit row by then. */
  async function decide(
    id: string,
    action: () => Promise<unknown>,
    done: string,
    focusAfter: number | null = null,
  ) {
    setBusyId(id);
    setFeedback(null);
    try {
      await action();
    } catch (error) {
      setFeedback({
        kind: "error",
        text: error instanceof Error ? error.message : "That did not work.",
      });
      setBusyId(null);
      return;
    }
    setFeedback({ kind: "done", text: done });
    setPicking(null);
    setDraftPick("");
    const key = periodKeyRef.current;
    const range = periodBounds(choice, salesThroughRef.current);
    try {
      const fresh = await getSalesCoverage(range?.from, range?.to);
      if (periodKeyRef.current === key) {
        pendingFocus.current = focusAfter;
        setCoverage(fresh);
      }
    } catch (error) {
      setFeedback({
        kind: "done",
        text: `${done} The panel could not refresh (${
          error instanceof Error ? error.message : "no answer"
        }) - reload to see it.`,
      });
    } finally {
      setBusyId(null);
    }
  }

  const queuePosition = (id: string): number | null => {
    const position = coverage?.queue.findIndex((row) => row.till_item_id === id) ?? -1;
    return position < 0 ? null : position;
  };

  function approve(item: CoverageItem, menuItemId: string, label: string) {
    return decide(
      item.till_item_id,
      () => mapTillItem(item.till_item_id, menuItemId),
      `${item.name} is now ${label}.`,
      queuePosition(item.till_item_id),
    );
  }

  function exclude(item: CoverageItem) {
    return decide(
      item.till_item_id,
      () => excludeTillItem(item.till_item_id),
      `${item.name} is not a menu item - it stays in net sales and leaves the queue.`,
      queuePosition(item.till_item_id),
    );
  }

  function onRowKey(event: React.KeyboardEvent<HTMLLIElement>, item: CoverageQueueItem) {
    if (event.target !== event.currentTarget) return; // inside the pick form
    // A modifier means a browser or system shortcut (Cmd+X cuts, Cmd+1 switches
    // tabs), a repeat means a held key, and a write in flight means wait -
    // none of them is the one keystroke that maps a name.
    if (event.ctrlKey || event.metaKey || event.altKey || event.repeat || busyId !== null) return;
    const index = Number(event.key) - 1;
    if (index >= 0 && index < item.proposals.length) {
      event.preventDefault();
      const proposal = item.proposals[index];
      void approve(item, proposal.menu_item_id, proposal.name);
      return;
    }
    if (event.key.toLowerCase() === "p") {
      event.preventDefault();
      setPicking(item.till_item_id);
      setDraftPick("");
      return;
    }
    if (event.key.toLowerCase() === "x") {
      event.preventDefault();
      void exclude(item);
    }
  }

  const header = (
    <header>
      <h1 className="font-display text-2xl font-semibold tracking-[-0.02em] text-ink">Sales</h1>
      <p className="mt-1 max-w-2xl text-sm text-stone">
        What each branch took, set against what it paid its suppliers over the same days.
      </p>
    </header>
  );

  if (loadError) {
    return (
      <div className="space-y-6">
        {header}
        <div role="alert" className="rounded-md border border-ink/10 bg-paper p-6">
        <p className="text-sm font-medium text-ink">Could not load sales</p>
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

  if (result === null || coverage === null || menu === null) {
    return (
      <div aria-busy="true" className="rounded-md border border-ink/10 bg-paper p-6">
        <p role="status" className="text-sm text-stone">
          Loading sales
        </p>
      </div>
    );
  }


  if (result.period.sales_through === null) {
    // Nothing was ever loaded: the loader is the way in, and the only link
    // to it on the page - the panel and the footer stand down.
    return (
      <div className="space-y-6">
        {header}
        <section className="rounded-md border border-ink/10 bg-paper p-5">
          <p className="text-sm font-medium text-ink">No sales loaded yet.</p>
          <p className="mt-1 max-w-2xl text-sm text-stone">
            Upload the till&apos;s export and every branch&apos;s purchases will be set against
            what it took.
          </p>
          <Link
            href="/sales/load"
            className="mt-4 inline-flex min-h-11 items-center rounded-sm bg-palm px-4 py-2 text-sm font-medium text-cream hover:bg-palm-deep"
          >
            Load sales from a CSV
          </Link>
        </section>
      </div>
    );
  }

  const answer = answerSentence(result);
  const freshness = freshnessSentence(result.period, isoToday());
  const months = monthOptions(result.period);
  const choices: PeriodChoice[] = [
    { kind: "last28" },
    { kind: "last7" },
    ...months.map((option): PeriodChoice => ({ kind: "month", year: option.year, month: option.month })),
  ];
  const liveMenu = menu.filter((item) => item.archived_at === null);
  const toggle = (id: string) => setOpen((current) => (current === id ? null : id));
  const savePick = (item: CoverageItem) => {
    const chosen = liveMenu.find((row) => row.id === draftPick);
    if (!chosen) return;
    void approve(item, chosen.id, chosen.name);
  };
  const cancelPick = () => {
    setPicking(null);
    setDraftPick("");
  };
  const writing = busyId !== null;

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
        <p role="status" aria-live="polite">
          {loading ? `Loading ${choiceLabel(choice)}` : freshness}
        </p>
      </div>

      {answer ? (
        <p className="max-w-3xl text-base leading-relaxed text-ink">
          <strong className="font-semibold">{answer.lead}:</strong> {answer.rest}
        </p>
      ) : (
        <p className="max-w-3xl text-base leading-relaxed text-ink">
          No sales are loaded for these days.
        </p>
      )}

      <section aria-busy={loading} className="space-y-2">
        {/* The table, for screens that fit one: one fixed grid so every row
            lines up under the same five columns (the menu screen's rule). */}
        <div className="hidden overflow-hidden rounded-md border border-ink/10 bg-paper sm:block">
          <table className="w-full table-fixed text-sm">
            <caption className="sr-only">
              Branches ranked by purchases divided by net sales, cash basis
            </caption>
            <colgroup>
              <col className="w-[30%]" />
              <col className="w-[16%]" />
              <col className="w-[16%]" />
              <col className="w-[18%]" />
              <col className="w-[20%]" />
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
                  Purchases
                </th>
                <th scope="col" className="px-4 py-2 text-right font-medium">
                  Purchases ÷ net sales (cash basis)
                </th>
                <th scope="col" className="px-4 py-2 font-medium">
                  Status
                </th>
              </tr>
            </thead>
            <tbody>
              {result.rows.map((row) => (
                <BranchTableRow
                  key={row.branch_id}
                  row={row}
                  open={open === row.branch_id}
                  drillRef={drillRef}
                  rowButtons={rowButtons}
                  onToggle={() => toggle(row.branch_id)}
                />
              ))}
              {result.unassigned.count > 0 ? (
                <>
                  <tr className="border-b border-ink/5 align-top text-stone">
                    <td className="px-4 py-2">
                      <button
                        type="button"
                        ref={(el) => {
                          if (onScreen(el)) rowButtons.current.set(NO_BRANCH_ID, el!);
                        }}
                        onClick={() => toggle(NO_BRANCH_ID)}
                        aria-expanded={open === NO_BRANCH_ID}
                        className="group inline-flex min-h-11 items-center gap-1.5 rounded-sm py-1 text-left font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-palm/30"
                      >
                        <ChevronIcon
                          className={`h-3 w-3 shrink-0 transition-transform ${
                            open === NO_BRANCH_ID ? "rotate-90" : ""
                          }`}
                        />
                        <span className="underline-offset-2 group-hover:underline">No branch</span>
                      </button>
                      <p className="text-xs">
                        {result.unassigned.count}{" "}
                        {result.unassigned.count === 1 ? "invoice" : "invoices"} with no branch
                      </p>
                    </td>
                    <td className="px-4 py-3 text-right">-</td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      {roundedAed(result.unassigned.purchases)}
                    </td>
                    <td className="px-4 py-3 text-right">-</td>
                    <td className="px-4 py-3 text-xs">Counted in the total, ranked nowhere.</td>
                  </tr>
                  {open === NO_BRANCH_ID ? (
                    <tr className="border-b border-ink/5">
                      <td colSpan={5} className="px-4 pb-3">
                        <div
                          ref={(el) => {
                            if (onScreen(el)) drillRef.current = el;
                          }}
                          tabIndex={-1}
                          className="focus:outline-none"
                        >
                          <NoBranchPapers result={result} />
                        </div>
                      </td>
                    </tr>
                  ) : null}
                </>
              ) : null}
              <tr className="border-t border-ink/15 align-top font-semibold">
                <td className="px-4 py-3">All branches</td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {roundedAed(result.total.net_sales)}
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {roundedAed(result.total.purchases)}
                </td>
                <td className="px-4 py-3 text-right">
                  {result.total.ratio_pct === null ? (
                    <span className="text-xs font-normal text-stone">Not rated</span>
                  ) : (
                    <span className="font-display text-[15px] tabular-nums">
                      {percent(result.total.ratio_pct)}
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 font-normal">
                  <QualityChip quality={result.total.quality} />
                  <p className="mt-1 text-xs text-stone">
                    {statusSentence(result.total.quality, result.total.notes)}
                  </p>
                </td>
              </tr>
            </tbody>
          </table>
          <p className="border-t border-ink/10 px-4 py-3 text-xs text-stone">
            Purchases are confirmed papers dated in the window, less printed VAT, counted when
            invoiced. Higher means more of every dirham taken went to suppliers. This is not a
            food cost.
          </p>
        </div>

        {/* Card rows under 640 px: the ratio as the large figure, the status
            sentence beneath. Same drill, same button. */}
        <ul className="space-y-2 sm:hidden">
          {result.rows.map((row) => (
            <BranchCard
              key={row.branch_id}
              row={row}
              open={open === row.branch_id}
              drillRef={drillRef}
              rowButtons={rowButtons}
              onToggle={() => toggle(row.branch_id)}
            />
          ))}
          {result.unassigned.count > 0 ? (
            <li className="rounded-md border border-ink/10 bg-paper p-3 text-stone">
              <div className="flex items-start justify-between gap-3">
                <button
                  type="button"
                  ref={(el) => {
                    if (onScreen(el)) rowButtons.current.set(NO_BRANCH_ID, el!);
                  }}
                  onClick={() => toggle(NO_BRANCH_ID)}
                  aria-expanded={open === NO_BRANCH_ID}
                  className="group inline-flex min-h-11 items-center gap-1.5 rounded-sm py-1 text-left font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-palm/30"
                >
                  <ChevronIcon
                    className={`h-3 w-3 shrink-0 transition-transform ${
                      open === NO_BRANCH_ID ? "rotate-90" : ""
                    }`}
                  />
                  <span className="underline-offset-2 group-hover:underline">No branch</span>
                </button>
                <span className="pt-1 text-xs">Counted in the total</span>
              </div>
              <p className="mt-0.5 text-xs tabular-nums">
                Purchases {roundedAed(result.unassigned.purchases)} · {result.unassigned.count}{" "}
                {result.unassigned.count === 1 ? "invoice" : "invoices"} with no branch
              </p>
              {open === NO_BRANCH_ID ? (
                <div
                  ref={(el) => {
                    if (onScreen(el)) drillRef.current = el;
                  }}
                  tabIndex={-1}
                  className="mt-2 focus:outline-none"
                >
                  <NoBranchPapers result={result} />
                </div>
              ) : null}
            </li>
          ) : null}
          <li className="rounded-md border border-ink/15 bg-paper p-3">
            <div className="flex items-start justify-between gap-3">
              <p className="min-h-11 py-1 font-semibold text-ink">All branches</p>
              <div className="pt-1 text-right">
                {result.total.ratio_pct === null ? (
                  <span className="text-xs text-stone">Not rated</span>
                ) : (
                  <span className="font-display text-xl font-semibold text-ink tabular-nums">
                    {percent(result.total.ratio_pct)}
                  </span>
                )}
              </div>
            </div>
            <p className="mt-0.5 text-xs text-stone tabular-nums">
              Net sales {roundedAed(result.total.net_sales)} · Purchases{" "}
              {roundedAed(result.total.purchases)}
            </p>
            <p className="mt-2 text-xs text-stone">
              <QualityChip quality={result.total.quality} />{" "}
              <span className="align-middle">
                {statusSentence(result.total.quality, result.total.notes)}
              </span>
            </p>
          </li>
          <li className="px-1 text-xs text-stone">
            Purchases are confirmed papers dated in the window, less printed VAT, counted when
            invoiced. Higher means more of every dirham taken went to suppliers. This is not a
            food cost.
          </li>
        </ul>
      </section>

      {/* The consultant's queue, on the quieter surface below the table -
          never beside it (variant C was rejected for taking a third of the
          owner's width). Costed, never complete; the estimated points named. */}
      <section className="space-y-3 rounded-md bg-mist p-4">
        <div>
          <h2 className="font-display text-lg font-semibold text-ink">{costedSentence(coverage)}</h2>
          {coverage.costed_pct !== null ? (
            <p className="mt-1 text-sm text-stone">{bucketsLine(coverage)}</p>
          ) : (
            <p className="mt-1 text-sm text-stone">
              Coverage is measured on item-wise days; there are none in this window.
            </p>
          )}
        </div>

        {feedback ? (
          <p
            role="status"
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

        {coverage.queue.length === 0 ? (
          <p className="rounded-md bg-paper px-4 py-4 text-sm text-stone">
            Every till name is mapped.
          </p>
        ) : (
          <>
            <p className="text-sm text-stone">
              {coverage.queue.length} till {coverage.queue.length === 1 ? "name" : "names"} not yet
              mapped, most money first
            </p>
            <ul className="divide-y divide-ink/10 rounded-md bg-paper">
              {coverage.queue.map((item) => {
                const busy = writing;
                return (
                  <li
                    key={item.till_item_id}
                    ref={(el) => {
                      if (el) queueRows.current.set(item.till_item_id, el);
                      else queueRows.current.delete(item.till_item_id);
                    }}
                    tabIndex={0}
                    onKeyDown={(event) => onRowKey(event, item)}
                    aria-label={item.name}
                    className="p-3 focus:ring-2 focus:ring-palm/30 focus:ring-inset focus:outline-none"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
                      <div className="min-w-0">
                        <p className="font-medium text-ink">{item.name}</p>
                        <p className="text-xs text-stone tabular-nums">
                          {item.code ? `code ${item.code} · ` : ""}
                          {roundedAed(item.value)} this window
                        </p>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        {item.proposals.map((proposal, index) => (
                          <button
                            key={proposal.menu_item_id}
                            type="button"
                            disabled={busy}
                            onClick={() => void approve(item, proposal.menu_item_id, proposal.name)}
                            className="min-h-11 rounded-sm bg-palm px-3 py-1.5 text-sm font-semibold text-cream hover:bg-palm-deep disabled:opacity-50"
                          >
                            <span aria-hidden="true" className="mr-1.5 opacity-70">
                              {index + 1}
                            </span>
                            {proposal.name}
                          </button>
                        ))}
                        {picking === item.till_item_id ? null : (
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => {
                              setPicking(item.till_item_id);
                              setDraftPick("");
                            }}
                            className="min-h-11 rounded-sm border border-palm/30 px-3 py-1.5 text-sm font-medium text-palm hover:border-palm disabled:opacity-50"
                          >
                            <span aria-hidden="true" className="mr-1.5 opacity-70">
                              P
                            </span>
                            Pick from the menu
                          </button>
                        )}
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void exclude(item)}
                          className="min-h-11 rounded-sm border border-ink/20 px-3 py-1.5 text-sm font-medium text-stone hover:border-ink/40 hover:text-ink disabled:opacity-50"
                        >
                          <span aria-hidden="true" className="mr-1.5 opacity-70">
                            X
                          </span>
                          Not a menu item
                        </button>
                      </div>
                    </div>
                    {picking === item.till_item_id ? (
                      <PickForm
                        liveMenu={liveMenu}
                        draftPick={draftPick}
                        onDraft={setDraftPick}
                        onSave={() => savePick(item)}
                        onCancel={cancelPick}
                        busy={busy}
                        selectRef={pickSelect}
                      />
                    ) : null}
                  </li>
                );
              })}
            </ul>
            <p className="text-xs text-stone">
              With a row selected: press 1, 2 or 3 to choose a menu item, P to pick from the
              menu, X if it is not a menu item. Nothing is mapped without a keystroke.
            </p>
          </>
        )}

        {coverage.mapped.length > 0 ? (
          <div>
            <button
              type="button"
              onClick={() => setShowMapped((value) => !value)}
              aria-expanded={showMapped}
              className="inline-flex min-h-11 items-center gap-1.5 rounded-sm text-sm font-medium text-palm focus:outline-none focus-visible:ring-2 focus-visible:ring-palm/30"
            >
              <ChevronIcon
                className={`h-3 w-3 shrink-0 transition-transform ${showMapped ? "rotate-90" : ""}`}
              />
              Mapped names ({coverage.mapped.length})
            </button>
            {showMapped ? (
              <ul className="mt-1 divide-y divide-ink/10 rounded-md bg-paper">
                {coverage.mapped.map((item) => (
                  <li
                    key={item.till_item_id}
                    className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 p-3"
                  >
                    <div className="min-w-0">
                      <p className="text-sm text-ink">
                        {item.name}
                        <span className="text-stone"> · {mappedWords(item)}</span>
                      </p>
                      <p className="text-xs text-stone tabular-nums">
                        {item.code ? `code ${item.code} · ` : ""}
                        {roundedAed(item.value)} this window
                      </p>
                    </div>
                    <button
                      type="button"
                      disabled={writing}
                      onClick={() =>
                        void decide(
                          item.till_item_id,
                          () => unmapTillItem(item.till_item_id),
                          `${item.name} is back in the queue.`,
                        )
                      }
                      className="min-h-11 rounded-sm border border-ink/20 px-2.5 py-1 text-xs font-medium text-stone hover:border-ink/40 hover:text-ink disabled:opacity-50"
                    >
                      Unmap
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}

        {coverage.excluded.length > 0 ? (
          <div>
            <p className="text-xs text-stone">
              {coverage.excluded.length === 1 ? "Not a menu item" : "Not menu items"}: kept in net
              sales, counted nowhere here. Picking a menu item brings a name back.
            </p>
            <ul className="mt-1 divide-y divide-ink/10 rounded-md bg-paper">
              {coverage.excluded.map((item) => (
                <li key={item.till_item_id} className="p-3">
                  <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
                    <p className="text-sm text-ink">
                      {item.name}
                      <span className="text-xs text-stone tabular-nums">
                        {item.code ? ` · code ${item.code}` : ""} · {roundedAed(item.value)} this window
                      </span>
                    </p>
                    {picking === item.till_item_id ? null : (
                      <button
                        type="button"
                        disabled={writing}
                        onClick={() => {
                          setPicking(item.till_item_id);
                          setDraftPick("");
                        }}
                        className="min-h-11 rounded-sm border border-palm/30 px-3 py-1.5 text-sm font-medium text-palm hover:border-palm disabled:opacity-50"
                      >
                        Pick from the menu
                      </button>
                    )}
                  </div>
                  {picking === item.till_item_id ? (
                    <PickForm
                      liveMenu={liveMenu}
                      draftPick={draftPick}
                      onDraft={setDraftPick}
                      onSave={() => savePick(item)}
                      onCancel={cancelPick}
                      busy={writing}
                      selectRef={pickSelect}
                    />
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <p className="text-xs text-stone">
          <Link href="/sales/load" className="underline-offset-2 hover:underline">
            Load or update sales from the till&apos;s export
          </Link>
        </p>
      </section>
    </div>
  );
}
