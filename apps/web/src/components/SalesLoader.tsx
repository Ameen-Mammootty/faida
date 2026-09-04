"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  addBranchAlias,
  getBranches,
  getSalesDays,
  getSalesLayouts,
  postSalesDays,
  postSalesFile,
  saveSalesLayout,
} from "@/lib/api";
import { formatDate, groupedMoney } from "@/lib/format";
import {
  COLUMN_HELP,
  COLUMN_WORDS,
  REQUIRED_COLUMNS,
  SALES_COLUMNS,
  applyLayout,
  committable,
  dateRange,
  driftSentence,
  guessColumns,
  guessDateOrder,
  isoToday,
  nameKey,
  normalizeHeader,
  planDays,
  planWords,
  readDate,
  readSalesCsv,
  requestGroups,
  toDayInput,
  type LayoutApply,
  type PlannedDay,
} from "@/lib/salesLoad";
import type {
  AmountBasis,
  Branch,
  DateOrder,
  SalesColumn,
  SalesColumnMap,
  SalesGranularity,
  SalesLayout,
} from "@/lib/types";
import { AlertIcon, CheckIcon, PendingIcon } from "./icons";
import { useCsvFile, type ParsedCsv } from "./useCsvFile";

/**
 * M8 WP-83: the sales loader - a till's export, mapped once, loaded in a
 * minute.
 *
 * The consultant tool at `/sales/load`, reached from the sales screen's own
 * link and never from the nav. The morning it serves: the owner exports the
 * till's item-wise report, the consultant says which column is which - once,
 * the layout is saved under the till's name - answers whether the amounts
 * carry VAT, and loads a month. Every upload after that applies the saved
 * layout by column *name*, so a reordered export loads unchanged and a
 * renamed column stops the file and names what moved (PRD §10, C11.1).
 *
 * The menu loader's four decisions hold here unchanged: the grid is
 * read-only (the CSV is the single source, the fix loop is fix-in-sheet,
 * re-upload); what-will-change is shown before anything is pressed, so the
 * same file twice previews every day unchanged and writes nothing; nothing
 * is decided in bulk - a day whose takings or row count would fall is
 * replaced only when the consultant ticks that day by name (C11.4); and
 * after the commit the grid stays, restamped from what the door answered,
 * with one summary line and a primary link onward.
 *
 * One more, this screen's own: **no net figure before commit.** The takings
 * column is an exact string sum of the file's amounts; the net - the VAT
 * taken out - is a division the browser must not own, and it appears on a
 * day only when the door has answered with it.
 *
 * Desktop-only, stated rather than discovered, like the menu loader.
 */

const TEMPLATE_HREF = "/faida-sales-template.csv";

type Phase = "idle" | "mapping" | "planning" | "ready" | "loading" | "done";

/** The mapping step's answers: which header is which column, the till's
 * name, the VAT basis, the date order, and the one branch for a file with
 * no branch column. `layoutId` is set when a saved layout was applied
 * unchanged; any edit clears it and the commit saves the layout by name. */
interface Mapping {
  columns: SalesColumnMap;
  name: string;
  amountBasis: AmountBasis;
  dateOrder: DateOrder;
  fileBranchId: string | null;
  layoutId: string | null;
}

interface ReadInfo {
  granularity: SalesGranularity;
  skippedNoDate: number;
  ignoredColumns: string[];
  unknownBranches: string[];
}

/** The one summary line. `refused` is what the door turned down; `skipped`
 * never left this screen - a fix in the sheet, a branch to name, or a tick. */
interface Summary {
  loaded: number;
  replaced: number;
  unchanged: number;
  refused: number;
  skipped: number;
}

const NOT_IN_FILE = "";

/** The status chip vocabulary, the menu loader's, shared before and after
 * the commit. Every one carries an icon and a word - colour never carries
 * meaning alone. */
function StatusChip({ tone, label }: { tone: "ready" | "wait" | "stop" | "done"; label: string }) {
  const styles = {
    ready: "bg-mist text-stone",
    wait: "bg-gold-soft text-caution",
    stop: "bg-gold-soft text-plum",
    done: "bg-mist text-verified",
  }[tone];
  const Icon = tone === "done" ? CheckIcon : tone === "ready" ? PendingIcon : AlertIcon;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-[11px] font-medium whitespace-nowrap ${styles}`}
    >
      <Icon className="h-3 w-3" />
      {label}
    </span>
  );
}

function dayStatus(day: PlannedDay): { tone: "ready" | "wait" | "stop" | "done"; label: string } {
  if (day.result) {
    if (day.result.outcome === "refused") return { tone: "stop", label: "Refused" };
    if (day.result.outcome === "unchanged") return { tone: "done", label: "Unchanged" };
    if (day.result.outcome === "replaced") return { tone: "done", label: "Replaced" };
    return { tone: "done", label: "Loaded" };
  }
  if (day.plan.kind === "blocked") {
    return day.branchId === null && day.branchLabel !== null && day.problems.length === 1
      ? { tone: "wait", label: "Needs a branch" }
      : { tone: "stop", label: "Fix the sheet" };
  }
  if (day.plan.shrinking && !day.confirmed) return { tone: "wait", label: "Tick to replace" };
  if (day.plan.kind === "unchanged") return { tone: "ready", label: "No change" };
  return { tone: "ready", label: "Ready" };
}

const aed = (value: string) => `AED ${groupedMoney(value)}`;

const BASIS_WORDS: Record<AmountBasis, string> = {
  inclusive: "VAT-inclusive, as the till prints them",
  exclusive: "VAT-exclusive, net already",
};

const ORDER_WORDS: Record<DateOrder, string> = {
  dmy: "day first (25/08/2026)",
  ymd: "year first (2026-08-25)",
};

export default function SalesLoader() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [file, setFile] = useState<File | null>(null);
  const [parsed, setParsed] = useState<ParsedCsv | null>(null);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [applied, setApplied] = useState<LayoutApply | null>(null);
  const [mapping, setMapping] = useState<Mapping | null>(null);
  const [mappingOpen, setMappingOpen] = useState(false);
  const [days, setDays] = useState<PlannedDay[] | null>(null);
  const [info, setInfo] = useState<ReadInfo | null>(null);
  const [aliasPick, setAliasPick] = useState<Record<string, string>>({});
  const [busyAlias, setBusyAlias] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  /** Only the newest plan is ever applied, and none once a commit has begun
   * (the menu loader's rule: a plan still in flight must not overwrite the
   * results the grid just restamped). */
  const planSeq = useRef(0);
  const committed = useRef(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        // The branches feed the mapping step's pickers; the layouts are read
        // fresh at every file pick, so nothing stale ever applies.
        const branchRows = await getBranches();
        if (cancelled) return;
        setBranches(branchRows);
      } catch (error) {
        if (cancelled) return;
        setLoadError(error instanceof Error ? error.message : "Could not reach Faida.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  /** Read the rows against a mapping, fetch the stored days for the file's
   * own range, and say what a commit would do. A refusal lands on the file
   * as its one sentence and reopens the mapping step. */
  async function readAndPlan(next: Mapping, branchRows: Branch[]) {
    if (!parsed) return;
    for (const column of REQUIRED_COLUMNS) {
      if (!next.columns[column]) {
        csv.setFileError(`Say which column is the ${COLUMN_WORDS[column]}.`);
        setMappingOpen(true);
        setPhase("mapping");
        return;
      }
    }
    setPhase("planning");
    csv.setFileError(null);
    const read = readSalesCsv(parsed.header, parsed.rows, parsed.ragged, {
      columns: next.columns,
      dateOrder: next.dateOrder,
      branches: branchRows,
      fileBranchId: next.columns.branch ? null : next.fileBranchId,
      today: isoToday(),
    });
    if (!read.ok) {
      csv.setFileError(read.error);
      setDays(null);
      setInfo(null);
      setMappingOpen(true);
      setPhase("mapping");
      return;
    }
    const token = (planSeq.current += 1);
    const range = dateRange(read.days);
    let stored: Awaited<ReturnType<typeof getSalesDays>> = [];
    try {
      stored = range ? await getSalesDays(range.from, range.to) : [];
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Could not reach Faida.");
    }
    if (token !== planSeq.current || committed.current) return;
    setInfo({
      granularity: read.granularity,
      skippedNoDate: read.skippedNoDate,
      ignoredColumns: read.ignoredColumns,
      unknownBranches: read.unknownBranches,
    });
    setDays(planDays(read.days, stored, next.amountBasis));
    setMapping(next);
    setMappingOpen(false);
    setPhase("ready");
  }

  const csv = useCsvFile({
    onPick: () => {
      setSummary(null);
      setDays(null);
      setInfo(null);
      setOpen(null);
      setApplied(null);
      setMappingOpen(false);
      committed.current = false;
      setPhase("idle");
    },
    onParsed: async (picked: File, rows: ParsedCsv) => {
      setFile(picked);
      setParsed(rows);
      // Fresh every time: a layout saved in another tab, an alias taught a
      // moment ago, must apply to this file.
      const [branchRows, layoutRows] = await Promise.all([getBranches(), getSalesLayouts()]);
      setBranches(branchRows);
      const decision = applyLayout(rows.header, layoutRows);
      setApplied(decision);
      const fresh = (name: string, columns: SalesColumnMap): Mapping => ({
        columns,
        name,
        amountBasis: "inclusive",
        dateOrder: guessDateOrder(dateCells(rows, columns.date)),
        fileBranchId: columns.branch ? null : (mapping?.fileBranchId ?? branchRows[0]?.id ?? null),
        layoutId: null,
      });
      if (decision.kind === "apply") {
        const next: Mapping = {
          columns: decision.layout.columns,
          name: decision.layout.name,
          amountBasis: decision.layout.amount_basis,
          dateOrder: decision.layout.date_order,
          fileBranchId: decision.layout.columns.branch
            ? null
            : (mapping?.fileBranchId ?? branchRows[0]?.id ?? null),
          layoutId: decision.layout.id,
        };
        setParsedThen(rows, () => readAndPlanWith(next, rows, branchRows));
        return;
      }
      if (decision.kind === "drift") {
        setMapping(fresh(decision.layout.name, guessColumns(rows.header)));
        setMappingOpen(true);
        setPhase("mapping");
        throw new Error(driftSentence(decision));
      }
      setMapping(fresh(decision.kind === "choose" ? "" : "Main till", guessColumns(rows.header)));
      setMappingOpen(true);
      setPhase("mapping");
    },
  });

  /** `parsed` is state, and the plan reads it; on the apply path the read
   * must run against the rows just parsed rather than the last render's. */
  function setParsedThen(rows: ParsedCsv, run: () => Promise<void>) {
    setParsed(rows);
    void run();
  }

  async function readAndPlanWith(next: Mapping, rows: ParsedCsv, branchRows: Branch[]) {
    // The same as readAndPlan, over rows handed in directly.
    for (const column of REQUIRED_COLUMNS) {
      if (!next.columns[column]) {
        csv.setFileError(`Say which column is the ${COLUMN_WORDS[column]}.`);
        setMappingOpen(true);
        setPhase("mapping");
        return;
      }
    }
    setPhase("planning");
    const read = readSalesCsv(rows.header, rows.rows, rows.ragged, {
      columns: next.columns,
      dateOrder: next.dateOrder,
      branches: branchRows,
      fileBranchId: next.columns.branch ? null : next.fileBranchId,
      today: isoToday(),
    });
    if (!read.ok) {
      csv.setFileError(read.error);
      setMapping(next);
      setMappingOpen(true);
      setPhase("mapping");
      return;
    }
    const token = (planSeq.current += 1);
    const range = dateRange(read.days);
    let stored: Awaited<ReturnType<typeof getSalesDays>> = [];
    try {
      stored = range ? await getSalesDays(range.from, range.to) : [];
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Could not reach Faida.");
    }
    if (token !== planSeq.current || committed.current) return;
    setInfo({
      granularity: read.granularity,
      skippedNoDate: read.skippedNoDate,
      ignoredColumns: read.ignoredColumns,
      unknownBranches: read.unknownBranches,
    });
    setDays(planDays(read.days, stored, next.amountBasis));
    setMapping(next);
    setMappingOpen(false);
    setPhase("ready");
  }

  /** Teach the till's label for a branch, once, then re-read the file. */
  async function onSaveAlias(label: string) {
    const branchId = aliasPick[label];
    if (!branchId || !mapping) return;
    setBusyAlias(label);
    setLoadError(null);
    try {
      await addBranchAlias(branchId, label);
      const branchRows = await getBranches();
      setBranches(branchRows);
      await readAndPlan(mapping, branchRows);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Could not save that alias.");
    } finally {
      setBusyAlias(null);
    }
  }

  function onConfirm(key: string, confirmed: boolean) {
    setDays((current) =>
      current ? current.map((day) => (day.key === key ? { ...day, confirmed } : day)) : current,
    );
  }

  /** Commit: the file first (so every day carries its hash), the layout by
   * name, then one branch-month per request in the grid's order, each day
   * restamped from what the door said. A refused request leaves the other
   * months alone. */
  async function onCommit() {
    if (!days || !file || !mapping) return;
    setPhase("loading");
    setLoadError(null);
    committed.current = true;
    const tally: Summary = { loaded: 0, replaced: 0, unchanged: 0, refused: 0, skipped: 0 };
    let current = days;
    for (const day of current) if (!committable(day)) tally.skipped += 1;
    try {
      const stored = await postSalesFile(file);
      let layoutId = mapping.layoutId;
      if (layoutId === null) {
        const layout = await saveSalesLayout({
          name: mapping.name.trim() || "Main till",
          columns: mapping.columns,
          amount_basis: mapping.amountBasis,
          date_order: mapping.dateOrder,
        });
        layoutId = layout.id;
        setMapping({ ...mapping, layoutId });
      }
      const source = { sha256: stored.sha256, filename: stored.filename };
      for (const group of requestGroups(current)) {
        try {
          const result = await postSalesDays({
            days: group.map((day) => toDayInput(day, mapping.amountBasis, layoutId, source)),
          });
          const answers = new Map(
            result.days.map((answer) => [`${answer.branch_id}|${answer.business_date}`, answer]),
          );
          current = current.map((day) => {
            const answer = answers.get(day.key);
            if (!answer) return day;
            tally[answer.outcome] += 1;
            return {
              ...day,
              result: { outcome: answer.outcome, net_sales: answer.day.net_sales, message: null },
            };
          });
        } catch (error) {
          const message =
            error instanceof Error ? error.message : "The API refused these days.";
          const keys = new Set(group.map((day) => day.key));
          current = current.map((day) => {
            if (!keys.has(day.key)) return day;
            tally.refused += 1;
            return { ...day, result: { outcome: "refused", net_sales: null, message } };
          });
        }
        setDays(current);
      }
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Could not reach Faida.");
      committed.current = false;
      setPhase("ready");
      return;
    }
    setSummary(tally);
    setPhase("done");
  }

  const ready = (days ?? []).filter(committable);
  /** Days a commit would actually write; the unchanged ones ride along so
   * the door confirms them, but they are not what the button counts. */
  const toLoad = ready.filter((day) => day.plan.kind !== "unchanged");
  const unchanged = (days ?? []).filter((day) => day.plan.kind === "unchanged");
  const broken = (days ?? []).filter(
    (day) => day.plan.kind === "blocked" && !(day.branchId === null && day.branchLabel !== null),
  );
  const needBranch = (days ?? []).filter((day) => day.branchId === null && day.branchLabel !== null);
  const ticks = (days ?? []).filter((day) => day.plan.shrinking && !day.confirmed);

  return (
    <div className="space-y-8">
      <header>
        <p className="text-sm">
          <Link href="/sales" className="font-medium text-palm underline-offset-2 hover:underline">
            &larr; Sales
          </Link>
        </p>
        <h1 className="mt-2 font-display text-2xl font-semibold tracking-[-0.02em] text-ink">
          Load sales
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-stone">
          Bring a month of sales in from the till&apos;s own export. Say which column is which
          once, and every export after that loads by the same names. Faida shows what would
          change before anything is written. Nothing here is visible to the owner.
        </p>
      </header>

      {/* Desktop-only, said rather than discovered. */}
      <p className="rounded-md border border-ink/10 bg-paper px-4 py-6 text-sm text-stone lg:hidden">
        This tool needs a wide screen - open it on a laptop, next to the till&apos;s export.
      </p>

      <div className="hidden space-y-8 lg:block">
        <section className="rounded-md border border-ink/10 bg-paper p-5">
          <h2 className="font-display text-lg font-semibold text-ink">The till&apos;s export</h2>
          <p className="mt-1 max-w-2xl text-sm text-stone">
            One row per item sold, with the outlet, the date, the item&apos;s code and name, how
            many, and the amount as the till printed it. A day with no rows inside the
            file&apos;s own dates loads as a closed day. Excel: File - Save As - CSV.
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <label className="inline-flex min-h-11 cursor-pointer items-center rounded-sm bg-palm px-4 py-2 text-sm font-medium text-cream hover:bg-palm-deep">
              Choose a CSV
              <input {...csv.inputProps} />
            </label>
            <a
              href={TEMPLATE_HREF}
              download
              className="min-h-11 rounded-sm border border-palm/30 px-3 py-2 text-sm font-medium text-palm hover:border-palm"
            >
              Download the template
            </a>
            {csv.fileName ? <span className="text-sm text-stone">{csv.fileName}</span> : null}
          </div>
          <p className="mt-3 text-xs text-stone">
            The template carries one worked day and one closed day: a row with no item and an
            amount of 0 says the branch was shut, so a missing day is never mistaken for one.
          </p>
          {csv.fileError ? (
            <p role="alert" className="mt-4 flex items-start gap-2 text-sm text-plum">
              <AlertIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              {csv.fileError}
            </p>
          ) : null}
          {csv.reading || phase === "planning" ? (
            <p role="status" className="mt-4 text-sm text-stone">
              Reading the file
            </p>
          ) : null}
          {applied?.kind === "apply" && !mappingOpen && mapping ? (
            <p className="mt-4 text-sm text-stone">
              Read with the saved layout <strong className="text-ink">{applied.layout.name}</strong>{" "}
              · amounts {BASIS_WORDS[mapping.amountBasis]} · dates {ORDER_WORDS[mapping.dateOrder]}.{" "}
              <button
                type="button"
                onClick={() => {
                  setMapping({ ...mapping, layoutId: null });
                  setMappingOpen(true);
                }}
                className="font-medium text-palm underline-offset-2 hover:underline"
              >
                Map it differently
              </button>
              {applied.extras.length > 0 ? (
                <span className="block text-xs">
                  Columns the layout does not read, left alone: {applied.extras.join(", ")}.
                </span>
              ) : null}
            </p>
          ) : null}
          {info && !mappingOpen && info.ignoredColumns.length > 0 && applied?.kind !== "apply" ? (
            <p className="mt-4 text-xs text-stone">
              Columns Faida does not read, left alone: {info.ignoredColumns.join(", ")}.
            </p>
          ) : null}
          {info && !mappingOpen && info.skippedNoDate > 0 ? (
            <p className="mt-1 text-xs text-stone">
              {info.skippedNoDate} {info.skippedNoDate === 1 ? "row" : "rows"} with no date
              ignored - a totals footer, usually.
            </p>
          ) : null}
        </section>

        {parsed && mapping && mappingOpen ? (
          <MappingStep
            parsed={parsed}
            mapping={mapping}
            branches={branches}
            choices={applied?.kind === "choose" ? applied.layouts : []}
            busy={phase === "planning"}
            onChange={setMapping}
            onChoose={(layout) =>
              setMapping({
                columns: layout.columns,
                name: layout.name,
                amountBasis: layout.amount_basis,
                dateOrder: layout.date_order,
                fileBranchId: layout.columns.branch ? null : mapping.fileBranchId,
                layoutId: layout.id,
              })
            }
            onRead={() => void readAndPlan(mapping, branches)}
          />
        ) : null}

        {loadError ? (
          <p role="alert" className="rounded-md bg-gold-soft p-4 text-sm text-plum">
            {loadError}
          </p>
        ) : null}

        {days === null || mapping === null ? null : (
          <>
            <section className="rounded-md bg-mist p-4">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  {summary ? (
                    <p className="font-medium text-ink">
                      {summary.loaded} {summary.loaded === 1 ? "day" : "days"} loaded,{" "}
                      {summary.replaced} replaced, {summary.unchanged} unchanged
                      {summary.refused > 0 ? `, ${summary.refused} refused` : ""}
                      {summary.skipped > 0 ? `, ${summary.skipped} still waiting` : ""}.
                    </p>
                  ) : (
                    <p className="font-medium text-ink">
                      {days.length} {days.length === 1 ? "day" : "days"} read · {toLoad.length} to
                      load
                      {unchanged.length > 0 ? ` · ${unchanged.length} unchanged` : ""}
                      {needBranch.length > 0
                        ? ` · ${needBranch.length} waiting on a branch name`
                        : ""}
                      {ticks.length > 0 ? ` · ${ticks.length} waiting on your tick` : ""}
                      {broken.length > 0 ? ` · ${broken.length} need a fix in the sheet` : ""}
                    </p>
                  )}
                  <p className="mt-0.5 text-sm text-stone">
                    Amounts read as {BASIS_WORDS[mapping.amountBasis]}
                    {mapping.amountBasis === "inclusive"
                      ? " - the VAT comes out at the door, and each day's net figure appears once it has."
                      : " - the door stores them as the net figure."}
                  </p>
                </div>
                {summary ? (
                  <Link
                    href="/sales"
                    className="min-h-11 rounded-sm bg-palm px-4 py-2 text-sm font-medium text-cream hover:bg-palm-deep"
                  >
                    See the branches
                  </Link>
                ) : (
                  <button
                    type="button"
                    onClick={() => void onCommit()}
                    disabled={toLoad.length === 0 || phase === "loading"}
                    className="min-h-11 rounded-sm bg-palm px-4 py-2 text-sm font-medium text-cream hover:bg-palm-deep disabled:opacity-40"
                  >
                    {phase === "loading"
                      ? "Loading"
                      : toLoad.length === 0
                        ? "Nothing to load"
                        : `Load ${toLoad.length} ${toLoad.length === 1 ? "day" : "days"}`}
                  </button>
                )}
              </div>
              {summary ? (
                <p role="status" className="mt-2 text-sm text-stone">
                  Done. The rows below say what happened to each day.
                </p>
              ) : null}
            </section>

            {info && info.unknownBranches.length > 0 && !summary ? (
              <section className="space-y-3 rounded-md bg-mist p-4">
                <h2 className="font-display text-lg font-semibold text-ink">
                  The till calls {info.unknownBranches.length === 1 ? "a branch" : "branches"} by{" "}
                  {info.unknownBranches.length === 1 ? "a name" : "names"} Faida does not know
                </h2>
                <p className="max-w-2xl text-sm text-stone">
                  Say which branch each one is. Faida remembers it, so every export after this
                  one reads the name without asking. A wrong answer files a branch&apos;s sales
                  under another - so one at a time, on purpose.
                </p>
                <ul className="space-y-2">
                  {info.unknownBranches.map((label) => (
                    <li
                      key={label}
                      className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-ink/10 bg-paper px-4 py-2"
                    >
                      <span className="text-sm text-ink">
                        &ldquo;{label}&rdquo; <span className="text-stone">is</span>
                      </span>
                      <span className="flex items-center gap-2">
                        <select
                          aria-label={`Which branch is ${label}`}
                          value={aliasPick[label] ?? ""}
                          onChange={(event) =>
                            setAliasPick({ ...aliasPick, [label]: event.target.value })
                          }
                          className="min-h-11 rounded-sm border border-ink/20 bg-paper px-2 text-sm text-ink"
                        >
                          <option value="">Choose a branch</option>
                          {branches.map((branch) => (
                            <option key={branch.id} value={branch.id}>
                              {branch.name}
                            </option>
                          ))}
                        </select>
                        <button
                          type="button"
                          onClick={() => void onSaveAlias(label)}
                          disabled={!aliasPick[label] || busyAlias !== null}
                          className="min-h-11 rounded-sm border border-palm/30 px-3 py-1.5 text-sm font-medium text-palm hover:border-palm disabled:opacity-40"
                        >
                          {busyAlias === label ? "Saving" : "Save"}
                        </button>
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}

            {ticks.length > 0 && !summary ? (
              <p className="max-w-2xl text-sm text-stone">
                {ticks.length === 1 ? "One day" : `${ticks.length} days`} in this file would
                replace a stored day with less - fewer rows, or lower takings, the shape of a
                half-day export over a full one. Each shows before and after in the grid and
                loads only with its own tick.
              </p>
            ) : null}

            <section>
              <div className="overflow-hidden rounded-md border border-ink/10 bg-paper">
                <table className="w-full text-sm">
                  <caption className="sr-only">
                    Every branch-day in the file, with its status, what loading it would change,
                    and what it is waiting on
                  </caption>
                  <thead>
                    <tr className="border-b border-ink/10 text-left text-[11px] font-medium tracking-wider text-stone uppercase">
                      <th scope="col" className="px-4 py-2 font-medium">
                        Branch
                      </th>
                      <th scope="col" className="px-4 py-2 font-medium">
                        Date
                      </th>
                      <th scope="col" className="px-4 py-2 text-right font-medium">
                        Rows
                      </th>
                      <th scope="col" className="px-4 py-2 text-right font-medium">
                        Takings
                      </th>
                      <th scope="col" className="px-4 py-2 font-medium">
                        Status
                      </th>
                      <th scope="col" className="px-4 py-2 font-medium">
                        {summary !== null ? "What changed" : "What will change"}
                      </th>
                      <th scope="col" className="px-4 py-2 font-medium">
                        The fix
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {days.map((day) => (
                      <DayRow
                        key={day.key}
                        day={day}
                        open={open === day.key}
                        onToggle={() => setOpen(open === day.key ? null : day.key)}
                        onConfirm={(confirmed) => onConfirm(day.key, confirmed)}
                        committed={summary !== null || phase === "loading"}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-2 max-w-2xl text-xs text-stone">
                The grid is read-only: the export is the source, so a fix goes in the spreadsheet
                and the file comes back up. Loading the same file twice changes nothing. Takings
                are the file&apos;s own amounts added up; the net figure is worked out at the door.
              </p>
            </section>
          </>
        )}
      </div>
    </div>
  );
}

/** The first few non-empty cells of the mapped date column, for the date
 * order's default and its preview. */
function dateCells(parsed: ParsedCsv, dateHeader: string | undefined): string[] {
  if (!dateHeader) return [];
  const index = parsed.header.findIndex(
    (name) => normalizeHeader(name) === normalizeHeader(dateHeader),
  );
  if (index < 0) return [];
  return parsed.rows
    .map((row) => (row[index] ?? "").trim())
    .filter((cell) => cell !== "")
    .slice(0, 5);
}

/**
 * The mapping step: which header is which column, by name; the till's name;
 * the VAT basis, asked once; the date order with the first date read both
 * ways; and the one branch when the file has none. Saved on commit under
 * the till's name, so the next export applies it without asking.
 */
function MappingStep({
  parsed,
  mapping,
  branches,
  choices,
  busy,
  onChange,
  onChoose,
  onRead,
}: {
  parsed: ParsedCsv;
  mapping: Mapping;
  branches: Branch[];
  choices: SalesLayout[];
  busy: boolean;
  onChange: (next: Mapping) => void;
  onChoose: (layout: SalesLayout) => void;
  onRead: () => void;
}) {
  const headers = parsed.header.filter((name) => name.trim() !== "");
  const used = new Map<string, SalesColumn>();
  for (const column of SALES_COLUMNS) {
    const name = mapping.columns[column];
    if (name) used.set(normalizeHeader(name), column);
  }
  const sample = dateCells(parsed, mapping.columns.date)[0] ?? null;
  const preview = (order: DateOrder) => {
    if (!sample) return null;
    const read = readDate(sample, order);
    return read.ok ? `reads as ${formatDate(read.iso)}` : "does not read this way";
  };
  const canRead =
    REQUIRED_COLUMNS.every((column) => Boolean(mapping.columns[column])) &&
    (Boolean(mapping.columns.branch) || mapping.fileBranchId !== null);

  const edit = (next: Partial<Mapping>) => onChange({ ...mapping, ...next, layoutId: null });
  const setColumn = (column: SalesColumn, header: string) => {
    const columns: SalesColumnMap = { ...mapping.columns };
    if (header === NOT_IN_FILE) delete columns[column];
    else columns[column] = header;
    edit({
      columns,
      fileBranchId: columns.branch ? null : (mapping.fileBranchId ?? branches[0]?.id ?? null),
      dateOrder:
        column === "date" ? guessDateOrder(dateCells(parsed, columns.date)) : mapping.dateOrder,
    });
  };

  return (
    <section className="space-y-5 rounded-md border border-ink/10 bg-paper p-5">
      <div>
        <h2 className="font-display text-lg font-semibold text-ink">Which column is which</h2>
        <p className="mt-1 max-w-2xl text-sm text-stone">
          Faida reads columns by their names, never by their position, so the till can reorder
          its export and this still holds. Answer once - the layout is saved under the
          till&apos;s name when the file loads.
        </p>
      </div>

      {choices.length > 0 ? (
        <div className="rounded-md bg-mist p-4">
          <p className="text-sm text-ink">
            More than one saved layout reads this file&apos;s columns. Which till is it?
          </p>
          <ul className="mt-2 flex flex-wrap gap-2">
            {choices.map((layout) => (
              <li key={layout.id}>
                <button
                  type="button"
                  onClick={() => onChoose(layout)}
                  aria-pressed={mapping.layoutId === layout.id}
                  className={`min-h-11 rounded-sm border px-3 py-1.5 text-sm font-medium ${
                    mapping.layoutId === layout.id
                      ? "border-palm bg-palm text-cream"
                      : "border-palm/30 bg-paper text-palm hover:border-palm"
                  }`}
                >
                  {layout.name}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <dl className="grid grid-cols-1 gap-x-8 gap-y-3 md:grid-cols-2">
        {SALES_COLUMNS.map((column) => {
          const value = mapping.columns[column] ?? NOT_IN_FILE;
          const required = REQUIRED_COLUMNS.includes(column);
          return (
            <div key={column} className="flex flex-col gap-1">
              <dt className="text-sm font-medium text-ink">
                <label htmlFor={`column-${column}`}>
                  {COLUMN_WORDS[column].charAt(0).toUpperCase() + COLUMN_WORDS[column].slice(1)}
                  {required ? null : <span className="text-stone"> · optional</span>}
                </label>
              </dt>
              <dd>
                <select
                  id={`column-${column}`}
                  value={value}
                  onChange={(event) => setColumn(column, event.target.value)}
                  className="min-h-11 w-full rounded-sm border border-ink/20 bg-paper px-2 text-sm text-ink"
                >
                  <option value={NOT_IN_FILE}>
                    {required ? "Choose a column" : "Not in this file"}
                  </option>
                  {headers.map((name) => {
                    const owner = used.get(normalizeHeader(name));
                    const taken = owner !== undefined && owner !== column;
                    return (
                      <option key={name} value={name} disabled={taken}>
                        {name}
                        {taken ? ` (the ${COLUMN_WORDS[owner]})` : ""}
                      </option>
                    );
                  })}
                </select>
                <p className="mt-1 text-xs text-stone">{COLUMN_HELP[column]}</p>
              </dd>
            </div>
          );
        })}
      </dl>

      {!mapping.columns.branch ? (
        <div className="max-w-md">
          <label htmlFor="file-branch" className="text-sm font-medium text-ink">
            This file is one branch
          </label>
          <select
            id="file-branch"
            value={mapping.fileBranchId ?? ""}
            onChange={(event) => edit({ fileBranchId: event.target.value || null })}
            className="mt-1 min-h-11 w-full rounded-sm border border-ink/20 bg-paper px-2 text-sm text-ink"
          >
            <option value="">Choose a branch</option>
            {branches.map((branch) => (
              <option key={branch.id} value={branch.id}>
                {branch.name}
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs text-stone">
            No branch column was mapped, so every row in the file is filed under this branch.
          </p>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-x-8 gap-y-4 md:grid-cols-2">
        <fieldset>
          <legend className="text-sm font-medium text-ink">The amounts are</legend>
          <div className="mt-1 space-y-1">
            {(["inclusive", "exclusive"] as AmountBasis[]).map((basis) => (
              <label key={basis} className="flex min-h-11 items-center gap-2 text-sm text-ink">
                <input
                  type="radio"
                  name="amount-basis"
                  value={basis}
                  checked={mapping.amountBasis === basis}
                  onChange={() => edit({ amountBasis: basis })}
                />
                {BASIS_WORDS[basis]}
              </label>
            ))}
          </div>
          <p className="text-xs text-stone">
            Asked once per till. The net figure - the VAT taken out - is worked out at the door
            from this answer and shown on every day after it loads.
          </p>
        </fieldset>
        <fieldset>
          <legend className="text-sm font-medium text-ink">Dates read</legend>
          <div className="mt-1 space-y-1">
            {(["dmy", "ymd"] as DateOrder[]).map((order) => (
              <label key={order} className="flex min-h-11 items-center gap-2 text-sm text-ink">
                <input
                  type="radio"
                  name="date-order"
                  value={order}
                  checked={mapping.dateOrder === order}
                  onChange={() => edit({ dateOrder: order })}
                />
                {ORDER_WORDS[order]}
                {sample ? (
                  <span className="text-xs text-stone">
                    · &ldquo;{sample}&rdquo; {preview(order)}
                  </span>
                ) : null}
              </label>
            ))}
          </div>
          <p className="text-xs text-stone">
            A date that reads two ways stops its row rather than being guessed.
          </p>
        </fieldset>
      </div>

      <div className="flex flex-wrap items-end gap-4">
        <div className="max-w-xs flex-1">
          <label htmlFor="layout-name" className="text-sm font-medium text-ink">
            This till&apos;s name
          </label>
          <input
            id="layout-name"
            type="text"
            value={mapping.name}
            onChange={(event) => edit({ name: event.target.value })}
            placeholder="Main till"
            className="mt-1 min-h-11 w-full rounded-sm border border-ink/20 bg-paper px-3 text-sm text-ink"
          />
          <p className="mt-1 text-xs text-stone">
            The layout is saved under it. Two tills with the same columns but a different date
            order or VAT basis are two names.
          </p>
        </div>
        <button
          type="button"
          onClick={onRead}
          disabled={!canRead || busy}
          className="min-h-11 rounded-sm bg-palm px-4 py-2 text-sm font-medium text-cream hover:bg-palm-deep disabled:opacity-40"
        >
          {busy ? "Reading" : "Read the file"}
        </button>
      </div>
    </section>
  );
}

/** The plain-words change column, before and after the door has spoken. */
function changeWords(day: PlannedDay): string {
  const result = day.result;
  if (result) {
    if (result.outcome === "refused") return "Not loaded";
    if (result.outcome === "unchanged") return "No change";
    const net = result.net_sales !== null ? ` · net ${aed(result.net_sales)}` : "";
    if (result.outcome === "replaced") {
      const before = day.plan.previous ? ` (was ${aed(day.plan.previous.net_sales)} net)` : "";
      return `Replaced${net}${before}`;
    }
    return `Loaded${net}`;
  }
  if (day.plan.kind === "replaced" && day.plan.previous) {
    const rows =
      day.granularity === "summary" && day.lines.length === 0
        ? `${day.plan.previous.line_count} rows to 0`
        : `${day.plan.previous.line_count} rows to ${day.lines.length}`;
    return `${aed(day.plan.previous.takings)} to ${aed(day.takings)}, ${rows}`;
  }
  return planWords(day);
}

function DayRow({
  day,
  open,
  onToggle,
  onConfirm,
  committed,
}: {
  day: PlannedDay;
  open: boolean;
  onToggle: () => void;
  onConfirm: (confirmed: boolean) => void;
  committed: boolean;
}) {
  const status = dayStatus(day);
  const sentences = day.result?.message ? [day.result.message] : day.problems;
  const isoDate = /^\d{4}-\d{2}-\d{2}$/.test(day.date);
  const rows = day.granularity === "summary" ? (day.gap ? "gap" : "closed") : String(day.lines.length);

  return (
    <>
      <tr className="border-b border-ink/5 align-top last:border-b-0">
        <td className="px-4 py-1.5">
          <span className="font-medium text-ink">
            {day.branchName ?? day.branchLabel ?? <em className="text-plum">no branch</em>}
          </span>
          {day.branchLabel && day.branchName && nameKey(day.branchLabel) !== nameKey(day.branchName) ? (
            // Only when the label was taught as an alias: a case-only
            // difference is the same name, and saying so on every row is noise.
            <span className="block text-xs text-stone">the till says &ldquo;{day.branchLabel}&rdquo;</span>
          ) : null}
        </td>
        <td className="px-4 py-1.5 whitespace-nowrap">
          {day.lines.length > 0 ? (
            <button
              type="button"
              onClick={onToggle}
              aria-expanded={open}
              className="min-h-11 rounded-sm py-1 text-left text-ink underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-palm/30"
            >
              {isoDate ? formatDate(day.date) : day.date}
            </button>
          ) : (
            <span className="text-ink">{isoDate ? formatDate(day.date) : day.date}</span>
          )}
          {day.rows.length > 0 ? (
            <span className="block text-xs text-stone">
              {day.rows.length === 1
                ? `line ${day.rows[0]}`
                : `lines ${day.rows[0]}-${day.rows[day.rows.length - 1]}`}
            </span>
          ) : null}
        </td>
        <td className="px-4 py-1.5 text-right tabular-nums text-stone">{rows}</td>
        <td className="px-4 py-1.5 text-right tabular-nums whitespace-nowrap">{aed(day.takings)}</td>
        <td className="px-4 py-1.5">
          <StatusChip tone={status.tone} label={status.label} />
        </td>
        <td className="px-4 py-1.5 text-stone">{changeWords(day)}</td>
        <td className="px-4 py-1.5">
          {sentences.length > 0 ? (
            <ul className="space-y-0.5">
              {sentences.map((sentence, index) => (
                <li
                  key={index}
                  className={
                    status.tone === "wait" && !day.result ? "text-sm text-stone" : "text-sm text-plum"
                  }
                >
                  {sentence}
                </li>
              ))}
            </ul>
          ) : day.plan.shrinking && !committed ? (
            <label className="flex min-h-11 items-center gap-2 text-sm text-ink">
              <input
                type="checkbox"
                checked={day.confirmed}
                onChange={(event) => onConfirm(event.target.checked)}
              />
              Replace {isoDate ? formatDate(day.date) : day.date} with less
            </label>
          ) : null}
        </td>
      </tr>
      {open && day.lines.length > 0 ? (
        <tr className="border-b border-ink/5 last:border-b-0">
          <td colSpan={7} className="px-4 pb-3">
            <ul className="divide-y divide-ink/5">
              {day.lines.map((line) => (
                <li key={line.line} className="flex flex-wrap justify-between gap-3 py-1.5">
                  <span className="text-sm text-ink">
                    {line.name}
                    <span className="text-stone">
                      {line.code ? ` · code ${line.code}` : ""}
                      {line.qty !== null ? ` · ${line.qty}` : ""}
                    </span>
                  </span>
                  <span className="text-xs text-stone tabular-nums">
                    {aed(line.amount)}
                    <span className="ml-2">line {line.line}</span>
                  </span>
                </li>
              ))}
            </ul>
          </td>
        </tr>
      ) : null}
    </>
  );
}
