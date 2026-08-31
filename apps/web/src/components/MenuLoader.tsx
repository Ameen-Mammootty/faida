"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  archiveMenuItem,
  createIngredient,
  getMenuItem,
  listIngredients,
  listMenuItems,
  loadMenuItem,
  unarchiveMenuItem,
} from "@/lib/api";
import { parseCsv } from "@/lib/csv";
import { money, quantity } from "@/lib/format";
import {
  committable,
  newMaterials,
  planLoad,
  planWords,
  readMenuCsv,
  type LoadItem,
  type MissingMaterial,
} from "@/lib/menuLoad";
import type { Ingredient, MenuItemDetail, MenuItemSummary } from "@/lib/types";
import { AlertIcon, CheckIcon, PendingIcon } from "./icons";

/**
 * M6 WP-64: the batch loader - a real menu in a morning.
 *
 * The internal consultant tool (PRD section 16), at `/menu/load`, linked from
 * consultant contexts only and never from the owner's nav. The loop it serves
 * is one conversation: ask the owner how they make the karak, type it into a
 * spreadsheet while they talk, upload, read the rows that failed, fix those
 * cells, upload again.
 *
 * Four decisions shape everything below, each of them the design review's:
 *
 * - **The grid is read-only.** The CSV is the single source and the fix loop
 *   is fix-in-spreadsheet, re-upload - an editable grid would create a second
 *   copy of the menu that quietly disagrees with the consultant's own file.
 * - **What-will-change is shown before anything is pressed**, so a re-upload
 *   of 45 recipes with two fixes reads "43 no changes" up front. Committing
 *   the same file twice writes nothing at all.
 * - **Creating a material is one click per material, never bulk.** A CSV that
 *   mints twelve materials in one keystroke is M5's forbidden auto-merge
 *   coming in through a side door, and a row waiting on one does not hold up
 *   the others. They are listed once each rather than on every row that names
 *   them - the real menu put onion in 21 of its 45 recipes - and ranked by how
 *   many items each unblocks, the way M5's own queue ranks by spend.
 * - **Nothing is ever archived automatically.** A partial CSV must not
 *   vaporize half the menu, so items missing from the file are named here and
 *   removed only by an explicit click.
 *
 * After the commit the grid stays and its rows are restamped from what the
 * door actually answered - not from what this screen predicted - with one
 * summary line and a primary link to `/menu`. The loop ends on the result,
 * not on the tool.
 *
 * Desktop-only, stated rather than discovered: a 45-row grid with a fix
 * column has no honest phone layout, and the consultant doing this work has a
 * spreadsheet open beside it.
 */

const TEMPLATE_HREF = "/faida-menu-template.csv";

type Phase = "idle" | "reading" | "ready" | "loading" | "done";

/** The one summary line. `refused` is what the door turned down; `skipped`
 * is what never left this screen, because the spreadsheet still needs a fix
 * or a material - two different things to do next, so two different words. */
interface Summary {
  created: number;
  versioned: number;
  unchanged: number;
  refused: number;
  skipped: number;
}

/** The status chip vocabulary, shared before and after the commit. Every one
 * carries an icon and a word - colour never carries meaning alone. */
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
      className={`inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-[11px] font-medium ${styles}`}
    >
      <Icon className="h-3 w-3" />
      {label}
    </span>
  );
}

function rowStatus(item: LoadItem): { tone: "ready" | "wait" | "stop" | "done"; label: string } {
  if (item.result) {
    if (item.result.outcome === "refused") return { tone: "stop", label: "Refused" };
    if (item.result.outcome === "unchanged") return { tone: "done", label: "Unchanged" };
    return { tone: "done", label: "Loaded" };
  }
  if (item.plan.kind === "blocked") return { tone: "stop", label: "Fix the sheet" };
  if (item.missing.length > 0) {
    return {
      tone: "wait",
      label: item.missing.length === 1 ? "1 new material" : `${item.missing.length} new materials`,
    };
  }
  return { tone: "ready", label: "Ready" };
}

/** Everything this row is waiting on, in the order a person would fix it: a
 * spreadsheet mistake first (it is the only one that needs the file reopened),
 * then the materials, which are one click each in the section above. */
function fixes(item: LoadItem): string[] {
  if (item.result?.message) return [item.result.message];
  const lines = item.lines
    .filter((line) => line.problem !== null)
    .map((line) => `line ${line.row}: ${line.problem}`);
  const waiting =
    item.missing.length > 0 && item.problems.length === 0 && lines.length === 0
      ? [`waiting on ${item.missing.map((material) => material.name).join(", ")}`]
      : [];
  return [...item.problems, ...lines, ...waiting];
}

export default function MenuLoader() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [fileName, setFileName] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [ignored, setIgnored] = useState<string[]>([]);
  const [items, setItems] = useState<LoadItem[] | null>(null);
  const [menuItems, setMenuItems] = useState<MenuItemSummary[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [busyMaterial, setBusyMaterial] = useState<string | null>(null);
  const [busyItem, setBusyItem] = useState<string | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  /**
   * Re-planning is asynchronous (it reads the current recipes back), so two
   * clicks in quick succession leave two plans in flight and the slower one
   * would land last. Worse, one still in flight when the commit finishes would
   * overwrite the results the grid just restamped with a prediction. Only the
   * newest plan is ever applied, and none is applied once a commit has begun.
   */
  const planSeq = useRef(0);
  const committed = useRef(false);

  /** The two lists every re-plan reads: the material catalog (which grows as
   * rows are approved) and the menu as it stands. Only the menu is held in
   * state - it feeds the coverage line and the missing-from-file section;
   * the materials are handed straight to the planner. */
  const refreshMenu = useCallback(async () => {
    const [materials, menu] = await Promise.all([listIngredients(), listMenuItems()]);
    setMenuItems(menu);
    return { materials, menu };
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const menu = await listMenuItems();
        if (!cancelled) setMenuItems(menu);
      } catch (error) {
        if (cancelled) return;
        setLoadError(error instanceof Error ? error.message : "Could not reach Faida.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  /** Fetch the current recipes of the items this file names, so the grid can
   * say "no change" before anything is pressed. Only items that already
   * exist are fetched - on a first load, that is none of them. */
  const planAgainst = useCallback(
    async (parsed: LoadItem[], materials: Ingredient[], menu: MenuItemSummary[]) => {
      const names = new Set(parsed.map((item) => item.name.trim().toLowerCase()));
      const wanted = menu.filter(
        (row) => row.archived_at === null && names.has(row.name.trim().toLowerCase()),
      );
      const token = (planSeq.current += 1);
      const details = new Map<string, MenuItemDetail>();
      const fetched = await Promise.all(
        wanted.map((row) => getMenuItem(row.id).catch(() => null)),
      );
      for (const detail of fetched) if (detail) details.set(detail.id, detail);
      if (token !== planSeq.current || committed.current) return null;
      return planLoad(parsed, materials, menu, details);
    },
    [],
  );

  /** Apply a plan only if it is still the newest one (see `planSeq`). */
  const applyPlan = useCallback((planned: LoadItem[] | null) => {
    if (planned !== null) setItems(planned);
  }, []);

  async function onFile(file: File | null) {
    if (!file) return;
    setFileName(file.name);
    setFileError(null);
    setSummary(null);
    setItems(null);
    setOpen(null);
    setPhase("reading");
    try {
      const parsed = parseCsv(await file.text());
      if (!parsed.ok) {
        setFileError(parsed.error);
        setPhase("idle");
        return;
      }
      const read = readMenuCsv(parsed.header, parsed.rows);
      if (!read.ok) {
        setFileError(read.error);
        setPhase("idle");
        return;
      }
      setIgnored(read.ignoredColumns);
      committed.current = false;
      const { materials, menu } = await refreshMenu();
      applyPlan(await planAgainst(read.items, materials, menu));
      setPhase("ready");
    } catch (error) {
      setFileError(
        error instanceof Error ? error.message : "That file could not be read as a CSV.",
      );
      setPhase("idle");
    }
  }

  /** One material, one click. The rows waiting on it are re-planned; every
   * other row is untouched. */
  async function onCreateMaterial(material: MissingMaterial) {
    if (!items) return;
    setBusyMaterial(material.name);
    setLoadError(null);
    try {
      await createIngredient({ name: material.name, unit: material.unit });
      const { materials, menu } = await refreshMenu();
      applyPlan(await planAgainst(items, materials, menu));
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Could not create that material.");
    } finally {
      setBusyMaterial(null);
    }
  }

  /** Commit: one recipe per request, one transaction each, in file order.
   * A row that is refused leaves the others alone - which is the whole reason
   * fix-in-spreadsheet is a loop rather than a restart. */
  async function onCommit() {
    if (!items) return;
    setPhase("loading");
    setLoadError(null);
    // From here the grid shows what the door said, never a prediction.
    committed.current = true;
    const tally: Summary = { created: 0, versioned: 0, unchanged: 0, refused: 0, skipped: 0 };
    const done: LoadItem[] = [];
    for (const item of items) {
      if (!committable(item)) {
        done.push({ ...item, result: null });
        tally.skipped += 1;
        setItems([...done, ...items.slice(done.length)]);
        continue;
      }
      try {
        const result = await loadMenuItem({
          name: item.name,
          category: item.category,
          selling_price: item.sellingPrice,
          yield_portions: item.yieldPortions,
          yield_label: item.yieldLabel,
          components: item.lines.map((line) => ({
            ingredient_id: line.ingredientId as string,
            qty: line.qty,
            unit: line.unit,
            source_text: line.sourceText,
          })),
        });
        if (result.outcome === "created") tally.created += 1;
        else if (result.outcome === "version_added") tally.versioned += 1;
        else tally.unchanged += 1;
        done.push({
          ...item,
          menuItemId: result.menu_item.id,
          result: {
            outcome: result.outcome,
            version: result.version,
            details: result.changed,
            message: null,
          },
        });
      } catch (error) {
        tally.refused += 1;
        done.push({
          ...item,
          result: {
            outcome: "refused",
            version: null,
            details: [],
            message: error instanceof Error ? error.message : "The API refused this recipe.",
          },
        });
      }
      setItems([...done, ...items.slice(done.length)]);
    }
    setSummary(tally);
    await refreshMenu();
    setPhase("done");
  }

  async function onArchive(id: string, archived: boolean) {
    setBusyItem(id);
    setLoadError(null);
    try {
      if (archived) await unarchiveMenuItem(id);
      else await archiveMenuItem(id);
      const { materials, menu } = await refreshMenu();
      if (items) applyPlan(await planAgainst(items, materials, menu));
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "That did not work.");
    } finally {
      setBusyItem(null);
    }
  }

  const live = menuItems.filter((row) => row.archived_at === null);
  const costed = live.filter((row) => row.plate.quality !== "incomplete");
  const inFile = new Set((items ?? []).map((item) => item.name.trim().toLowerCase()));
  const absent = live.filter((row) => items !== null && !inFile.has(row.name.trim().toLowerCase()));
  const archivedItems = menuItems.filter((row) => row.archived_at !== null);
  const ready = (items ?? []).filter(committable);
  const materials = newMaterials(items ?? []);
  const broken = (items ?? []).filter((item) => item.plan.kind === "blocked");

  return (
    <div className="space-y-8">
      <header>
        <p className="text-sm">
          <Link href="/menu" className="font-medium text-palm underline-offset-2 hover:underline">
            &larr; Menu
          </Link>
        </p>
        <h1 className="mt-2 font-display text-2xl font-semibold tracking-[-0.02em] text-ink">
          Load a menu
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-stone">
          Bring a whole menu in from one spreadsheet - items, prices and recipes. Faida checks
          every row and shows what would change before anything is written. Nothing here is
          visible to the owner.
        </p>
      </header>

      {/* Desktop-only, said rather than discovered. */}
      <p className="rounded-md border border-ink/10 bg-paper px-4 py-6 text-sm text-stone lg:hidden">
        This tool needs a wide screen - open it on a laptop, next to the spreadsheet you are
        loading.
      </p>

      <div className="hidden space-y-8 lg:block">
        <section className="rounded-md border border-ink/10 bg-paper p-5">
          <h2 className="font-display text-lg font-semibold text-ink">The spreadsheet</h2>
          <p className="mt-1 max-w-2xl text-sm text-stone">
            One row per ingredient, with the item&apos;s name, category, price and portions
            repeated on each of its rows. Quantities are <strong>as purchased</strong> - what you
            would buy to make it, not what ends up on the plate - because that is what an invoice
            price multiplies.
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <label className="inline-flex min-h-11 cursor-pointer items-center rounded-sm bg-palm px-4 py-2 text-sm font-medium text-cream hover:bg-palm-deep">
              Choose a CSV
              <input
                ref={fileInput}
                type="file"
                accept=".csv,text/csv"
                className="sr-only"
                onChange={(event) => {
                  const file = event.target.files?.[0] ?? null;
                  // Clear it, or picking the *same* filename again fires no
                  // change event - and picking the same filename again is
                  // exactly the loop: fix two cells in the sheet, save over
                  // it, upload it again.
                  event.target.value = "";
                  void onFile(file);
                }}
              />
            </label>
            <a
              href={TEMPLATE_HREF}
              download
              className="min-h-11 rounded-sm border border-palm/30 px-3 py-2 text-sm font-medium text-palm hover:border-palm"
            >
              Download the template
            </a>
            {fileName ? <span className="text-sm text-stone">{fileName}</span> : null}
          </div>
          <p className="mt-3 text-xs text-stone">
            The template carries one worked example row - it doubles as the worksheet to fill in
            while the owner is talking.
          </p>
          {fileError ? (
            <p role="alert" className="mt-4 flex items-start gap-2 text-sm text-plum">
              <AlertIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              {fileError}
            </p>
          ) : null}
          {phase === "reading" ? (
            <p role="status" className="mt-4 text-sm text-stone">
              Reading the file
            </p>
          ) : null}
          {ignored.length > 0 && items !== null ? (
            <p className="mt-4 text-xs text-stone">
              Columns Faida does not read, left alone: {ignored.join(", ")}.
            </p>
          ) : null}
        </section>

        {loadError ? (
          <p role="alert" className="rounded-md bg-gold-soft p-4 text-sm text-plum">
            {loadError}
          </p>
        ) : null}

        {items === null ? null : (
          <>
            <section className="rounded-md bg-mist p-4">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  {summary ? (
                    <p className="font-medium text-ink">
                      {summary.created} loaded, {summary.versioned} re-versioned,{" "}
                      {summary.unchanged} unchanged
                      {summary.refused > 0 ? `, ${summary.refused} refused` : ""}
                      {summary.skipped > 0
                        ? `, ${summary.skipped} still waiting on a fix`
                        : ""}
                      .
                    </p>
                  ) : (
                    <p className="font-medium text-ink">
                      {items.length} recipes read · {ready.length} ready to load
                      {materials.length > 0
                        ? ` · ${items.length - ready.length - broken.length} waiting on a new material`
                        : ""}
                      {broken.length > 0 ? ` · ${broken.length} need a fix in the sheet` : ""}
                    </p>
                  )}
                  <p className="mt-0.5 text-sm text-stone">
                    {costed.length} of {live.length} items on the menu can be costed today.
                  </p>
                </div>
                {summary ? (
                  <Link
                    href="/menu"
                    className="min-h-11 rounded-sm bg-palm px-4 py-2 text-sm font-medium text-cream hover:bg-palm-deep"
                  >
                    See the margins
                  </Link>
                ) : (
                  <button
                    type="button"
                    onClick={() => void onCommit()}
                    disabled={ready.length === 0 || phase === "loading"}
                    className="min-h-11 rounded-sm bg-palm px-4 py-2 text-sm font-medium text-cream hover:bg-palm-deep disabled:opacity-40"
                  >
                    {phase === "loading"
                      ? "Loading"
                      : `Load ${ready.length} ${ready.length === 1 ? "recipe" : "recipes"}`}
                  </button>
                )}
              </div>
              {summary ? (
                <p role="status" className="mt-2 text-sm text-stone">
                  Done. The rows below say what happened to each recipe.
                </p>
              ) : null}
            </section>

            {materials.length > 0 && !summary ? (
              // Mist, not gold-soft: on a fresh tenant every material a menu
              // names is new, so this is the consultant's ordinary work queue
              // (the /menu incomplete section's own surface), not a warning.
              <section id="new-materials" className="space-y-3 rounded-md bg-mist p-4">
                <h2 className="font-display text-lg font-semibold text-ink">
                  {materials.length} raw{" "}
                  {materials.length === 1 ? "material is" : "materials are"} new to Faida
                </h2>
                <p className="max-w-2xl text-sm text-stone">
                  Add each one you recognise - most items first, so the ones holding up the
                  longest list of recipes come first. One click each, on purpose: this is the
                  shelf every future invoice for that ingredient will land on, and a wrong one
                  quietly corrupts the cost of every dish above it.
                </p>
                <ul className="flex flex-wrap gap-2">
                  {materials.map((material) => (
                    <li key={material.name}>
                      <button
                        type="button"
                        onClick={() => void onCreateMaterial(material)}
                        disabled={busyMaterial !== null}
                        className="min-h-11 rounded-sm border border-palm/30 bg-paper px-3 py-1.5 text-sm font-medium text-palm hover:border-palm disabled:opacity-40"
                      >
                        {busyMaterial === material.name ? "Adding " : "Add "}
                        {material.name}
                        <span className="ml-1.5 text-xs font-normal text-stone">
                          {material.unit} · {material.items}{" "}
                          {material.items === 1 ? "item" : "items"}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}

            <section>
              <div className="overflow-hidden rounded-md border border-ink/10 bg-paper">
                <table className="w-full text-sm">
                  <caption className="sr-only">
                    Every recipe in the file, with its status, what loading it would change, and
                    what it is waiting on
                  </caption>
                  <thead>
                    <tr className="border-b border-ink/10 text-left text-[11px] font-medium tracking-wider text-stone uppercase">
                      <th scope="col" className="px-4 py-2 font-medium">
                        Item
                      </th>
                      <th scope="col" className="px-4 py-2 text-right font-medium">
                        Sells at
                      </th>
                      <th scope="col" className="px-4 py-2 font-medium">
                        Status
                      </th>
                      <th scope="col" className="px-4 py-2 font-medium">
                        What will change
                      </th>
                      <th scope="col" className="px-4 py-2 font-medium">
                        The fix
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((item) => (
                      <LoadRow
                        key={item.name}
                        item={item}
                        open={open === item.name}
                        onToggle={() => setOpen(open === item.name ? null : item.name)}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-2 max-w-2xl text-xs text-stone">
                The grid is read-only: the spreadsheet is the source, so a fix goes in there and
                the file comes back up. Loading the same file twice changes nothing.
              </p>
            </section>

            {absent.length > 0 ? (
              <section className="space-y-3 rounded-md bg-mist p-4">
                <h2 className="font-display text-lg font-semibold text-ink">
                  {absent.length} {absent.length === 1 ? "item is" : "items are"} on the menu but
                  not in this file
                </h2>
                <p className="max-w-2xl text-sm text-stone">
                  Nothing was removed. A file covering one category should not take the rest of
                  the menu off - archive an item only if it really has gone.
                </p>
                <ul className="space-y-2">
                  {absent.map((row) => (
                    <li
                      key={row.id}
                      className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-ink/10 bg-paper px-4 py-2"
                    >
                      <span className="text-sm text-ink">
                        {row.name}
                        {row.category ? (
                          <span className="text-stone"> · {row.category}</span>
                        ) : null}
                      </span>
                      <button
                        type="button"
                        onClick={() => void onArchive(row.id, false)}
                        disabled={busyItem === row.id}
                        className="min-h-11 rounded-sm border border-palm/30 px-3 py-1.5 text-sm font-medium text-palm hover:border-palm disabled:opacity-40"
                      >
                        Archive it
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}

            {archivedItems.length > 0 ? (
              <section className="space-y-3 rounded-md bg-mist p-4">
                <h2 className="font-display text-lg font-semibold text-ink">
                  Archived, and off every screen
                </h2>
                <ul className="space-y-2">
                  {archivedItems.map((row) => (
                    <li
                      key={row.id}
                      className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-ink/10 bg-paper px-4 py-2"
                    >
                      <span className="text-sm text-stone">{row.name}</span>
                      <button
                        type="button"
                        onClick={() => void onArchive(row.id, true)}
                        disabled={busyItem === row.id}
                        className="min-h-11 rounded-sm border border-palm/30 px-3 py-1.5 text-sm font-medium text-palm hover:border-palm disabled:opacity-40"
                      >
                        Bring it back
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}

function LoadRow({
  item,
  open,
  onToggle,
}: {
  item: LoadItem;
  open: boolean;
  onToggle: () => void;
}) {
  const status = rowStatus(item);
  const sentences = fixes(item);
  const result = item.result;

  return (
    <>
      <tr className="border-b border-ink/5 align-top last:border-b-0">
        <td className="px-4 py-1.5">
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={open}
            className="min-h-11 rounded-sm py-1 text-left font-medium text-ink underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-palm/30"
          >
            {item.name}
          </button>
          <p className="text-xs text-stone">
            {item.category ?? "no category"} · {item.lines.length}{" "}
            {item.lines.length === 1 ? "ingredient" : "ingredients"}
            {item.yieldPortions && item.yieldPortions !== "1"
              ? ` · makes ${quantity(item.yieldPortions)}${
                  item.yieldLabel ? ` ${item.yieldLabel}` : ""
                }`
              : ""}
          </p>
        </td>
        <td className="px-4 py-1.5 text-right tabular-nums">
          {/^\d+(\.\d+)?$/.test(item.sellingPrice.trim())
            ? `AED ${money(item.sellingPrice.trim())}`
            : "-"}
        </td>
        <td className="px-4 py-1.5">
          <StatusChip tone={status.tone} label={status.label} />
        </td>
        <td className="px-4 py-1.5 text-stone">
          {result
            ? result.outcome === "created"
              ? "Added to the menu"
              : result.outcome === "version_added"
                ? `New version (v${result.version})${
                    result.details.length > 0 ? ` · ${result.details.join(" and ")} updated` : ""
                  }`
                : result.outcome === "unchanged"
                  ? result.details.length > 0
                    ? `${result.details.join(" and ")} updated`
                    : "No change"
                  : "Not loaded"
            : planWords(item)}
          {!result && item.plan.rewordedOnly ? (
            <span className="block text-xs">
              the wording on a line changed but the amounts did not - no new version
            </span>
          ) : null}
        </td>
        <td className="px-4 py-1.5">
          {sentences.length > 0 ? (
            <ul className="space-y-0.5">
              {sentences.map((sentence) => (
                <li
                  key={sentence}
                  className={item.missing.length > 0 && !result ? "text-sm text-stone" : "text-sm text-plum"}
                >
                  {sentence}
                </li>
              ))}
            </ul>
          ) : null}
        </td>
      </tr>
      {open ? (
        <tr className="border-b border-ink/5 last:border-b-0">
          <td colSpan={5} className="px-4 pb-3">
            <ul className="divide-y divide-ink/5">
              {item.lines.map((line) => (
                <li key={line.row} className="flex flex-wrap justify-between gap-3 py-1.5">
                  <span className="text-sm text-ink">
                    {line.ingredient || <em className="text-plum">no ingredient</em>}
                    <span className="text-stone">
                      {" "}
                      · {line.qty} {line.unit}
                    </span>
                    {line.sourceText ? (
                      <span className="block text-xs text-stone">
                        the card says &ldquo;{line.sourceText}&rdquo;
                      </span>
                    ) : null}
                  </span>
                  <span className="text-xs text-stone">
                    line {line.row}
                    {line.problem ? <span className="ml-2 text-plum">{line.problem}</span> : null}
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
