"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { getMenuItem, listMenuItems, listPriceMoves } from "@/lib/api";
import { formatDate, groupedMoney, money, quantity } from "@/lib/format";
import type {
  MaterialPrice,
  MenuComponent,
  MenuItemDetail,
  MenuItemSummary,
  PriceMove,
  PriceMoveLine,
} from "@/lib/types";
import { AlertIcon, TrendDownIcon, TrendUpIcon } from "./icons";

/**
 * M6 WP-62/63: the menu screen - the demo's closing image, variant C
 * ("push this, fix that", design review 2026-08-30).
 *
 * Reader order: two callout cards, then the ranking, then the incomplete
 * section. Callout one narrates the ranking's own top row - conclusion above,
 * evidence below (D6). Callout two goes by priority: a loss-making item if
 * one exists, else the newest price move (WP-63's money moment lives here,
 * never on its own route), else the callouts collapse away and the page is a
 * plain ledger. The ranking is grouped by the menu's own categories, each
 * ranked by margin in AED with the %% beside, collapsed to its top rows.
 *
 * The honesty rules carry through: incomplete items keep their menu price
 * but no cost or margin, in their own quieter section which owns the
 * coverage line; a negative margin renders in Critical Plum with icon and
 * label, never colour alone; per-plate money is fils-precise everywhere
 * (D10); *estimated* wears the gold-soft chip while *reliable with
 * limitations* is one footnote sentence, not a badge per row. The word is
 * *margin*, never "profit", and "food cost" appears nowhere.
 *
 * Everything derives on read - a manual page reload after confirming an
 * invoice is the demo's own gesture; there is no polling to build.
 */

/**
 * Summary money shows fils, not thirds of a fils: cut to two decimals by
 * string operations (a stored margin has three). Exact figures live in the
 * drill. Fils-precise everywhere - 1.28, never "AED 1" (D10).
 */
function summaryMoney(value: string): string {
  const padded = money(value);
  return padded.slice(0, padded.indexOf(".") + 3);
}

/** "AED 20.20 per kg", "AED 4.69 per litre", "AED 0.35 each". */
function pricePerUnit(price: MaterialPrice): string {
  const figure = `AED ${groupedMoney(price.per_display_unit ?? "0")}`;
  return price.display_unit === "each" ? `${figure} each` : `${figure} per ${price.display_unit}`;
}

/** Where a component's price came from: supplier and purchase date. */
function priceSource(price: MaterialPrice): string {
  const when = price.invoice_date
    ? `bought ${formatDate(price.invoice_date)}`
    : price.purchased_on
      ? `recorded ${formatDate(price.purchased_on)}`
      : "date not read";
  return `${price.supplier_name} · ${when}`;
}

/** Why a figure reads *estimated*, named - a bare label is a warning people
 * learn to scroll past. */
function estimatedBecause(price: MaterialPrice): string {
  if (price.newer_uncosted) {
    const when = price.newer_uncosted.purchased_on
      ? ` from ${formatDate(price.newer_uncosted.purchased_on)}`
      : "";
    return `a newer delivery${when} has no cost yet`;
  }
  if (price.pack_source === "override") {
    return `the pack (${price.pack}) was entered by a person, not read off an invoice`;
  }
  return "one of its inputs was supplied by a person";
}

/** "AED 4.69 per litre" for one side of a price move. */
function movePrice(line: PriceMoveLine): string {
  const figure = `AED ${money(line.per_display_unit)}`;
  return line.display_unit === "each" ? `${figure} each` : `${figure} per ${line.display_unit}`;
}

function boughtOn(line: PriceMoveLine): string {
  if (line.invoice_date) return `since ${formatDate(line.invoice_date)}`;
  if (line.purchased_on) return `since ${formatDate(line.purchased_on)}`;
  return "date not read";
}

/** The gold-soft chip for an *estimated* figure. Reliable-with-limitations
 * gets no chip - the footnote under the ranking says it once. */
function EstimatedChip() {
  return (
    <span className="inline-flex items-center gap-1 rounded-sm bg-gold-soft px-1.5 py-0.5 text-[11px] font-medium text-caution">
      <AlertIcon className="h-3 w-3" />
      Estimated
    </span>
  );
}

/** A negative margin, in Critical Plum with icon and label - never colour
 * alone, and never mistakable for a thin-but-positive figure. */
function LossFigure({ margin }: { margin: string }) {
  return (
    // The figure and its icon never split: in a fixed-width margin column the
    // label is what wraps to the next line, not "-AED 0.40" away from the
    // symbol that says it is bad news.
    <span className="inline-flex flex-wrap items-center justify-end gap-x-1.5 font-medium text-plum">
      <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
        <AlertIcon className="h-3.5 w-3.5" />
        <span className="tabular-nums">-AED {summaryMoney(margin.replace("-", ""))}</span>
      </span>
      <span className="text-xs font-normal">this plate loses money</span>
    </span>
  );
}

function marginIsLoss(item: MenuItemSummary): boolean {
  return (item.plate.margin ?? "").startsWith("-");
}

/** Callout one: the ranking's own top row, restated in the same AED lens as
 * the table - conclusion above, evidence below (D6). */
function TopEarnerCallout({ item }: { item: MenuItemSummary }) {
  return (
    <div className="rounded-md bg-mist p-4">
      <p className="flex items-center gap-1.5 text-xs font-medium text-verified">
        <TrendUpIcon className="h-3.5 w-3.5" />
        Top earner
      </p>
      <p className="mt-1.5 font-medium text-ink">
        Earns the most per plate: {item.name}, AED {summaryMoney(item.plate.margin ?? "0")} of{" "}
        {money(item.selling_price)}.
      </p>
      <p className="mt-0.5 text-sm text-stone">
        Push it - nothing else on the menu banks more per sale.
      </p>
    </div>
  );
}

/**
 * How many other affected items the price-move callout names before it counts
 * the rest - the incomplete section's own rule (MISSING_SHOWN), one layer up.
 *
 * The line was a comma-run of every item the move touched. On the real menu
 * that reached nine and read as three lines of grey: "Also Coffee Milk - Flask
 * 2 L -0.35, Habbat Al Souda Tea -0.32, ...", where the dash inside an item's
 * name is the same glyph as the minus in front of its figure, and neither
 * figure carries AED or "a portion" - so nothing in it could be compared with
 * the sentence above. Three named with their figures in brackets, the rest
 * counted; the whole list lives on the materials screen, which is where the
 * work is done.
 */
const ALSO_NAMED = 3;

/** Callout two, priority loss > price move > absent (D8). Two lines in the
 * operator voice: the finding, then the action. */
function FixCallout({ loss, move }: { loss: MenuItemSummary | null; move: PriceMove | null }) {
  if (loss) {
    return (
      <div className="rounded-md bg-gold-soft p-4">
        <p className="flex items-center gap-1.5 text-xs font-medium text-plum">
          <AlertIcon className="h-3.5 w-3.5" />
          Losing money
        </p>
        <p className="mt-1.5 font-medium text-ink">
          {loss.name} loses AED {summaryMoney((loss.plate.margin ?? "0").replace("-", ""))} on
          every plate sold.
        </p>
        <p className="mt-0.5 text-sm text-stone">
          Reprice it or trim the recipe - its ingredients cost more than its price.
        </p>
      </div>
    );
  }
  if (!move) return null;

  if (move.kind === "basis_changed") {
    // The frame stays; the arrow and the before/after go. One sentence
    // naming both packs - a delta across pack sizes would be a pack
    // artifact wearing a percent sign (D3).
    return (
      <div className="rounded-md bg-gold-soft p-4">
        <p className="flex items-center gap-1.5 text-xs font-medium text-caution">
          <AlertIcon className="h-3.5 w-3.5" />
          Price basis changed
        </p>
        <p className="mt-1.5 font-medium text-ink">
          {move.ingredient_name} is now priced from {move.current.product_name} (
          {move.current.supplier_name}), not {move.previous.product_name} (
          {move.previous.supplier_name}).
        </p>
        <p className="mt-0.5 text-sm text-stone">
          Different pack sizes - no comparison shown.{" "}
          <Link
            href={`/invoices/${move.current.invoice_id}#line-${move.current.position}`}
            className="font-medium text-palm underline-offset-2 hover:underline"
          >
            See the new invoice
          </Link>
        </p>
      </div>
    );
  }

  const up = !(move.delta_per_display_unit ?? "").startsWith("-");
  const deltaAbs = money((move.delta_per_display_unit ?? "0").replace("-", ""));
  const perUnit =
    move.current.display_unit === "each" ? "each" : `per ${move.current.display_unit}`;
  const top = move.items[0];
  const rest = move.items.slice(1);
  const Trend = up ? TrendUpIcon : TrendDownIcon;
  return (
    <div className="rounded-md bg-gold-soft p-4">
      <p className="flex items-center gap-1.5 text-xs font-medium text-caution">
        <Trend className="h-3.5 w-3.5" />
        Price moved
      </p>
      <p className="mt-1.5 font-medium text-ink">
        {move.ingredient_name} is {up ? "up" : "down"} AED {deltaAbs} {perUnit}{" "}
        {boughtOn(move.current)}.
      </p>
      {top ? (
        <p className="mt-0.5 text-sm text-stone">
          {top.name} earns AED {summaryMoney(top.impact_per_portion.replace("-", ""))}{" "}
          {up ? "less" : "more"} a portion - check the price or the recipe.
        </p>
      ) : (
        <p className="mt-0.5 text-sm text-stone">No costed menu item uses it yet.</p>
      )}
      {rest.length > 0 ? (
        <p className="mt-1 text-xs text-stone">
          Also earning {up ? "less" : "more"}:{" "}
          {rest.slice(0, ALSO_NAMED).map((item, index) => (
            <span key={item.menu_item_id}>
              {index > 0 ? ", " : ""}
              {item.name} (AED {summaryMoney(item.impact_per_portion.replace("-", ""))})
            </span>
          ))}
          {rest.length > ALSO_NAMED ? `, and ${rest.length - ALSO_NAMED} more items` : ""}.
        </p>
      ) : null}
      <p className="mt-1 text-xs text-stone">
        Was {movePrice(move.previous)} ·{" "}
        <Link
          href={`/invoices/${move.current.invoice_id}#line-${move.current.position}`}
          className="font-medium text-palm underline-offset-2 hover:underline"
        >
          See the invoice
        </Link>
      </p>
    </div>
  );
}

function ComponentRow({ component }: { component: MenuComponent }) {
  return (
    <li className="flex flex-wrap items-start justify-between gap-3 py-2">
      <div className="min-w-0">
        <p className="text-sm text-ink">
          {component.ingredient_name}
          <span className="text-stone">
            {" "}
            · {quantity(component.qty)} {component.unit}
          </span>
        </p>
        {component.source_text ? (
          <p className="text-xs text-stone">the card says &ldquo;{component.source_text}&rdquo;</p>
        ) : null}
        {component.missing ? (
          <p className="mt-1 text-sm text-plum">
            {component.missing}
            {" · "}
            <Link
              href={`/materials#material-${component.ingredient_id}`}
              className="font-medium text-palm underline-offset-2 hover:underline"
            >
              Fix on the materials screen
            </Link>
          </p>
        ) : null}
      </div>
      {component.cost ? (
        <div className="text-right">
          <p className="text-sm text-ink tabular-nums">AED {money(component.cost.amount)}</p>
          <p className="text-xs text-stone">
            {pricePerUnit(component.cost.price)} · {priceSource(component.cost.price)}
          </p>
          {component.cost.quality === "estimated" ? (
            <p className="text-xs text-stone">
              Estimated: {estimatedBecause(component.cost.price)}.
            </p>
          ) : null}
          <Link
            href={`/invoices/${component.cost.price.invoice_id}#line-${component.cost.price.position}`}
            className="text-xs font-medium text-palm underline-offset-2 hover:underline"
          >
            See the invoice
          </Link>
        </div>
      ) : null}
    </li>
  );
}

/** The in-row drill: recipe version, the VAT basis in words, then every
 * component with its cost and the invoice line behind it. */
function DrillContent({
  detail,
  error,
}: {
  detail: MenuItemDetail | null;
  error: string | null;
}) {
  if (detail?.recipe) {
    return (
      <>
        <p className="pt-3 text-xs text-stone">
          Recipe version {detail.recipe.version}
          {detail.recipe.yield_portions !== "1.000"
            ? ` · one batch makes ${quantity(detail.recipe.yield_portions)}${
                detail.recipe.yield_label ? ` ${detail.recipe.yield_label}` : ""
              }`
            : ""}
          {detail.plate.net_price
            ? ` · earns from AED ${money(detail.plate.net_price)} once the ${
                detail.plate.vat_rate === "0.05" ? "5% " : ""
              }VAT inside the menu price is set aside`
            : ""}
        </p>
        <ul className="mt-2 divide-y divide-ink/5">
          {detail.recipe.components.map((component) => (
            <ComponentRow key={component.position} component={component} />
          ))}
        </ul>
      </>
    );
  }
  if (error) return <p className="pt-3 text-sm text-plum">{error}</p>;
  return (
    <p role="status" className="pt-3 text-sm text-stone">
      Loading the recipe
    </p>
  );
}

/** Margin cell contents: the AED figure with %% beside, the loss treatment,
 * or the estimated chip - words and icons, never colour alone. */
function MarginFigure({ item }: { item: MenuItemSummary }) {
  if (marginIsLoss(item)) return <LossFigure margin={item.plate.margin ?? "0"} />;
  return (
    <span className="tabular-nums">
      <span className="font-display font-semibold text-ink">
        AED {summaryMoney(item.plate.margin ?? "0")}
      </span>
      <span className="ml-1.5 text-xs text-stone">{item.plate.margin_pct}%</span>
    </span>
  );
}

const COLLAPSED_ROWS = 5;

/**
 * The table and the card rows are both always in the DOM - only one of them is
 * ever displayed - so a ref shared between them keeps whichever React attached
 * last, which is the card. Above 640 px that made every focus call land on a
 * `display: none` element, where it silently does nothing: pressing Enter on a
 * row left focus sitting on the button instead of moving into the expansion
 * (WP-62's acceptance). This keeps only the copy that is actually on screen.
 */
function onScreen(el: HTMLElement | null): boolean {
  return el !== null && el.offsetParent !== null;
}

/**
 * How many missing pieces an incomplete item names before it counts the rest.
 *
 * The design was drawn for a handful of incomplete items; the real 45-item
 * menu arrives with **every** item incomplete and up to fifteen unmapped
 * materials each, which renders "no supplier product is mapped to ... yet"
 * some four hundred times and buries the one thing the reader wants - which
 * materials. Four named, the rest counted: the small case (the steady state,
 * once mapping is underway) is unchanged, and the big one stays readable.
 * The full list lives on the materials screen, which is where the work is
 * done and where the link already points.
 */
const MISSING_SHOWN = 4;

export default function MenuMargins() {
  const [items, setItems] = useState<MenuItemSummary[] | null>(null);
  const [moves, setMoves] = useState<PriceMove[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, MenuItemDetail>>({});
  const [detailError, setDetailError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState<Set<string>>(new Set());
  const drillRef = useRef<HTMLDivElement>(null);
  const rowButtons = useRef<Map<string, HTMLButtonElement>>(new Map());
  const lastOpened = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [menu, priceMoves] = await Promise.all([listMenuItems(), listPriceMoves()]);
        if (cancelled) return;
        setItems(menu);
        setMoves(priceMoves);
        setLoadError(null);
      } catch (error) {
        if (cancelled) return;
        setLoadError(error instanceof Error ? error.message : "Could not load the menu.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  // Focus follows the drill: into the expansion when it opens, back to the
  // row's own button when it collapses (design review - the ranking never
  // leaves the screen mid-demo, and neither does the keyboard user).
  useEffect(() => {
    if (open !== null) {
      lastOpened.current = open;
      drillRef.current?.focus();
    } else if (lastOpened.current !== null) {
      rowButtons.current.get(lastOpened.current)?.focus();
      lastOpened.current = null;
    }
  }, [open]);

  async function toggle(id: string) {
    if (open === id) {
      setOpen(null);
      return;
    }
    setOpen(id);
    setDetailError(null);
    if (details[id]) return;
    try {
      const detail = await getMenuItem(id);
      setDetails((cache) => ({ ...cache, [id]: detail }));
    } catch (error) {
      setDetailError(error instanceof Error ? error.message : "Could not load that item.");
    }
  }

  if (loadError) {
    return (
      <div role="alert" className="rounded-md border border-ink/10 bg-paper p-6">
        <p className="text-sm font-medium text-ink">Could not load the menu</p>
        <p className="mt-1 text-sm text-stone">{loadError}</p>
        <button
          type="button"
          onClick={() => setReloadKey((key) => key + 1)}
          className="mt-4 rounded-sm border border-palm/30 px-3 py-1.5 text-sm font-medium text-palm hover:border-palm"
        >
          Try again
        </button>
      </div>
    );
  }

  if (items === null || moves === null) {
    return (
      <div aria-busy="true" className="rounded-md border border-ink/10 bg-paper p-6">
        <p role="status" className="text-sm text-stone">
          Loading the menu
        </p>
      </div>
    );
  }

  // Archived items appear nowhere: out of the ranking, the callouts and the
  // coverage count. The click that brings one back lives with the loader.
  const live = items.filter((item) => item.archived_at === null);
  const costed = live.filter((item) => item.plate.quality !== "incomplete");
  const incomplete = live.filter((item) => item.plate.quality === "incomplete");
  // The one sanctioned parse on this screen, like the sparkline's: ordering
  // is geometry, and the parsed number is never rendered.
  const byMargin = (a: MenuItemSummary, b: MenuItemSummary) =>
    Number(b.plate.margin ?? 0) - Number(a.plate.margin ?? 0);
  const ranked = [...costed].sort(byMargin);

  // Callout two by priority: loss > newest price move > absent (D8). When
  // neither exists the callouts collapse away and the page is a plain ledger.
  const losses = ranked.filter(marginIsLoss);
  const worstLoss = losses.length > 0 ? losses[losses.length - 1] : null;
  const fix = worstLoss ?? null;
  const newestMove = moves.length > 0 ? moves[0] : null;
  const showCallouts = ranked.length > 0 && (fix !== null || newestMove !== null);

  // The ranking, grouped by the menu's own categories (D9) - never invented:
  // a menu that prints no sections renders as one unlabelled group. Groups
  // order by their best item, the same conclusion-first lens as everything
  // else here.
  const groups = new Map<string | null, MenuItemSummary[]>();
  for (const item of ranked) {
    const key = item.category;
    groups.set(key, [...(groups.get(key) ?? []), item]);
  }
  const orderedGroups = [...groups.entries()];
  const onlyGroup = orderedGroups.length === 1 && orderedGroups[0][0] === null;

  const renderRows = (groupKey: string, groupItems: MenuItemSummary[]) => {
    const expanded = showAll.has(groupKey);
    const visible = expanded ? groupItems : groupItems.slice(0, COLLAPSED_ROWS);
    return { visible, expanded, collapsible: groupItems.length > COLLAPSED_ROWS };
  };

  // The expander is a toggle, not a one-way door: it used to only ever add to
  // the set and then unmount itself, so a category opened mid-demo stayed open
  // until the page was reloaded - on a 45-item menu that is the closing image
  // gone for the rest of the run.
  const toggleGroup = (groupKey: string) =>
    setShowAll((set) => {
      const next = new Set(set);
      if (!next.delete(groupKey)) next.add(groupKey);
      return next;
    });

  return (
    <div className="space-y-8">
      <header>
        <h1 className="font-display text-2xl font-semibold tracking-[-0.02em] text-ink">Menu</h1>
        <p className="mt-1 max-w-2xl text-sm text-stone">
          What each item earns after its ingredients - so you know what to push, and what to fix.
        </p>
      </header>

      {live.length === 0 ? (
        // Empty state one: no menu at all. The loader is the way in.
        <p className="rounded-md border border-ink/10 bg-paper px-4 py-6 text-sm text-stone">
          No menu yet.{" "}
          <Link
            href="/menu/load"
            className="font-medium text-palm underline-offset-2 hover:underline"
          >
            The batch loader
          </Link>{" "}
          brings a whole menu in from a spreadsheet in one sitting - margins appear here the
          moment it runs.
        </p>
      ) : (
        <>
          {showCallouts ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <TopEarnerCallout item={ranked[0]} />
              <FixCallout loss={fix} move={fix ? null : newestMove} />
            </div>
          ) : null}

          {ranked.length === 0 ? (
            // Empty state two: items exist but nothing is costed yet - the
            // incomplete section below becomes the page.
            <p className="rounded-md border border-ink/10 bg-paper px-4 py-6 text-sm text-stone">
              0 of {live.length} items costed so far. Margins appear here as materials are mapped
              and invoices confirmed - the list below says what each item is waiting for.
            </p>
          ) : (
            <section className="space-y-5">
              {orderedGroups.map(([category, groupItems]) => {
                const groupKey = category ?? "(none)";
                const { visible, expanded, collapsible } = renderRows(groupKey, groupItems);
                const heading = onlyGroup ? null : (category ?? "Other items");
                return (
                  <div key={groupKey}>
                    {heading ? (
                      <h2 className="mb-2 font-display text-lg font-semibold text-ink">
                        {heading}
                      </h2>
                    ) : null}

                    {/* The table, for screens that fit one (real semantics:
                        caption, thead, a real button as the drill trigger). */}
                    <div className="hidden overflow-hidden rounded-md border border-ink/10 bg-paper sm:block">
                      <table className="w-full table-fixed text-sm">
                        <caption className="sr-only">
                          {heading ?? "Menu items"} ranked by margin in AED per item
                        </caption>
                        {/* One grid for the whole ranking. Each category is its
                            own table (its own caption and header, which is what
                            makes it readable to a screen reader), and with the
                            browser's automatic layout each one sized its columns
                            from its own rows: at 1280 the "Sells at" column
                            started 56 px further right under Shakes than under
                            Tea Corner, and a single loss row pushed it 138 px.
                            Down a 45-item menu that is a different grid per
                            section. Fixed widths make the margin column land in
                            the same place in every one. The money shares are
                            sized off the narrowest table this layout ever
                            renders (a 640 px viewport, just above the card
                            breakpoint), so "AED 35.00" and "AED 28.55 85.7%"
                            still fit on one line there; a long item name wraps
                            instead, which costs nothing. */}
                        <colgroup>
                          <col className="w-[36%]" />
                          <col className="w-[18%]" />
                          <col className="w-[18%]" />
                          <col className="w-[28%]" />
                        </colgroup>
                        <thead>
                          <tr className="border-b border-ink/10 text-left text-[11px] font-medium tracking-wider text-stone uppercase">
                            <th scope="col" className="px-4 py-2 font-medium">
                              Item
                            </th>
                            <th scope="col" className="px-4 py-2 text-right font-medium">
                              Sells at
                            </th>
                            <th scope="col" className="px-4 py-2 text-right font-medium">
                              Costs
                            </th>
                            <th scope="col" className="px-4 py-2 text-right font-medium">
                              Margin
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {visible.map((item) => (
                            <MenuRow
                              key={item.id}
                              item={item}
                              open={open === item.id}
                              detail={details[item.id] ?? null}
                              detailError={detailError}
                              drillRef={drillRef}
                              rowButtons={rowButtons}
                              onToggle={() => void toggle(item.id)}
                            />
                          ))}
                        </tbody>
                      </table>
                    </div>

                    {/* Card rows under 640 px: margin first, one caption line
                        (D11). Same drill, same button. */}
                    <ul className="space-y-2 sm:hidden">
                      {visible.map((item) => (
                        <MenuCard
                          key={item.id}
                          item={item}
                          open={open === item.id}
                          detail={details[item.id] ?? null}
                          detailError={detailError}
                          drillRef={drillRef}
                          rowButtons={rowButtons}
                          onToggle={() => void toggle(item.id)}
                        />
                      ))}
                    </ul>

                    {collapsible ? (
                      <button
                        type="button"
                        onClick={() => toggleGroup(groupKey)}
                        aria-expanded={expanded}
                        className="mt-2 min-h-11 rounded-sm border border-palm/30 px-3 py-1.5 text-sm font-medium text-palm hover:border-palm"
                      >
                        {expanded
                          ? `Show the top ${COLLAPSED_ROWS} only`
                          : `Show all ${groupItems.length} items`}
                      </button>
                    ) : null}
                  </div>
                );
              })}
              <p className="max-w-2xl text-xs text-stone">
                Margin is the menu price net of VAT minus what the ingredients cost, from your
                most recent confirmed invoices. It is not profit: labour, rent and waste are not
                in it. Unmarked figures are reliable with limitations - the invoice&apos;s own
                arithmetic supports them, but nothing cross-checks a printed pack size, so no
                figure here is ever marked verified.
              </p>
            </section>
          )}

          {incomplete.length > 0 ? (
            // The quieter section, on mist, owning the coverage line - the
            // owner's first read above is the conclusion, not the homework.
            <section className="space-y-3 rounded-md bg-mist p-4">
              <h2 className="font-display text-lg font-semibold text-ink">
                {incomplete.length} of {live.length} items can&apos;t be costed yet
              </h2>
              <ul className="space-y-2">
                {incomplete.map((item) => (
                  <li key={item.id} className="rounded-md border border-ink/10 bg-paper p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="font-medium text-ink">{item.name}</p>
                        <p className="mt-0.5 text-sm text-stone">
                          sells at AED {money(item.selling_price)}
                        </p>
                        <ul className="mt-1 space-y-0.5">
                          {item.plate.missing.slice(0, MISSING_SHOWN).map((sentence, index) => (
                            <li key={index} className="text-sm text-plum">
                              {sentence}
                            </li>
                          ))}
                          {item.plate.missing.length > MISSING_SHOWN ? (
                            <li className="text-sm text-stone">
                              and {item.plate.missing.length - MISSING_SHOWN} more
                            </li>
                          ) : null}
                        </ul>
                      </div>
                      {item.plate.missing.some((sentence) => sentence !== "no recipe yet") ? (
                        <Link
                          href="/materials"
                          className="text-xs font-medium text-palm underline-offset-2 hover:underline"
                        >
                          Fix on the materials screen
                        </Link>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
              <p className="max-w-2xl text-xs text-stone">
                An item missing anything shows no cost and no margin at all - a half-costed dish
                would read as the menu&apos;s best earner, and that is a lie the ranking would
                repeat.
              </p>
            </section>
          ) : null}
        </>
      )}

      {/* The loader is a consultant tool: reachable from here, never a fourth
          item in the nav the owner reads every morning (WP-62/64). */}
      <p className="text-xs text-stone">
        <Link href="/menu/load" className="underline-offset-2 hover:underline">
          Load or update the menu from a spreadsheet
        </Link>
      </p>
    </div>
  );
}

function MenuRow({
  item,
  open,
  detail,
  detailError,
  drillRef,
  rowButtons,
  onToggle,
}: {
  item: MenuItemSummary;
  open: boolean;
  detail: MenuItemDetail | null;
  detailError: string | null;
  drillRef: React.RefObject<HTMLDivElement | null>;
  rowButtons: React.RefObject<Map<string, HTMLButtonElement>>;
  onToggle: () => void;
}) {
  return (
    <>
      <tr className="border-b border-ink/5 last:border-b-0">
        <td className="px-4 py-1.5">
          <button
            type="button"
            ref={(el) => {
              if (onScreen(el)) rowButtons.current.set(item.id, el!);
            }}
            onClick={onToggle}
            aria-expanded={open}
            className="min-h-11 rounded-sm py-1 text-left font-medium text-ink underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-palm/30"
          >
            {item.name}
          </button>
          {item.plate.quality === "estimated" ? (
            <span className="ml-2 align-middle">
              <EstimatedChip />
            </span>
          ) : null}
        </td>
        <td className="px-4 py-1.5 text-right tabular-nums">AED {money(item.selling_price)}</td>
        <td className="px-4 py-1.5 text-right tabular-nums">
          AED {summaryMoney(item.plate.cost_per_portion ?? "0")}
        </td>
        <td className="px-4 py-1.5 text-right">
          <MarginFigure item={item} />
        </td>
      </tr>
      {open ? (
        <tr className="border-b border-ink/5 last:border-b-0">
          <td colSpan={4} className="px-4 pb-3">
            <div
              ref={(el) => {
                if (onScreen(el)) drillRef.current = el;
              }}
              tabIndex={-1}
              className="focus:outline-none"
            >
              <DrillContent detail={detail} error={detailError} />
            </div>
          </td>
        </tr>
      ) : null}
    </>
  );
}

function MenuCard({
  item,
  open,
  detail,
  detailError,
  drillRef,
  rowButtons,
  onToggle,
}: {
  item: MenuItemSummary;
  open: boolean;
  detail: MenuItemDetail | null;
  detailError: string | null;
  drillRef: React.RefObject<HTMLDivElement | null>;
  rowButtons: React.RefObject<Map<string, HTMLButtonElement>>;
  onToggle: () => void;
}) {
  return (
    <li className="rounded-md border border-ink/10 bg-paper p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <button
            type="button"
            ref={(el) => {
              // The card and the table never render at the same width, so the
              // shared ref map holds whichever button is actually on screen.
              if (onScreen(el)) rowButtons.current.set(item.id, el!);
            }}
            onClick={onToggle}
            aria-expanded={open}
            className="min-h-11 rounded-sm py-1 text-left font-medium text-ink underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-palm/30"
          >
            {item.name}
          </button>
          {item.plate.quality === "estimated" ? (
            <span className="ml-2 align-middle">
              <EstimatedChip />
            </span>
          ) : null}
        </div>
        <div className="text-right">
          <MarginFigure item={item} />
        </div>
      </div>
      <p className="mt-0.5 text-xs text-stone">
        sells at AED {money(item.selling_price)} · costs AED{" "}
        {summaryMoney(item.plate.cost_per_portion ?? "0")}
      </p>
      {open ? (
        <div
          ref={(el) => {
            if (onScreen(el)) drillRef.current = el;
          }}
          tabIndex={-1}
          className="focus:outline-none"
        >
          <DrillContent detail={detail} error={detailError} />
        </div>
      ) : null}
    </li>
  );
}
