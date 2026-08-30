"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getMenuItem, listMenuItems } from "@/lib/api";
import { formatDate, groupedMoney, money, quantity } from "@/lib/format";
import type {
  MaterialPrice,
  MenuComponent,
  MenuItemDetail,
  MenuItemSummary,
} from "@/lib/types";

/**
 * M6 WP-62: the menu screen - the demo's closing image.
 *
 * Every costed item ranked by **margin in AED**, biggest first, with the
 * percentage beside it: the two rank differently, and a high-margin item
 * selling twice a day is worth less than a thin one selling two hundred
 * times, so the AED figure leads (D14). Incomplete items sit in their own
 * section with what each is missing and one click to the fix - never in the
 * ranking, where a missing cost would read as a fat margin.
 *
 * The word on this screen is *margin*, never "profit": labour, rent and
 * waste are absent from a plate cost. And never "food cost %" (plan.md
 * section 3). Quality is words, not colour - colour never carries meaning
 * alone.
 *
 * Every figure derives on read from the same material prices the materials
 * screen shows, so a newly confirmed invoice moves this ranking on the next
 * load - nothing here is stored or refreshed. The drill goes item ->
 * components -> each component's material price -> the invoice photo behind
 * it, in three clicks or fewer.
 */

/**
 * Summary rows show fils, not thirds of a fils: cut to two decimals by string
 * operations (a stored margin has three). Exact figures live in the drill,
 * per plan.md section 3 - rounded up top, exact in detail.
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

/** Why a figure reads *estimated*, in the reader's language - named, because
 * a bare "estimated" is a warning people learn to scroll past. */
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

/** The one-line quality sentence under an estimated ranked row. */
function plateQualityNote(detailOrNull: MenuItemDetail | null): string {
  const generic = "Estimated: one of this recipe's prices leans on something a person supplied.";
  if (!detailOrNull?.recipe) return generic;
  const culprit = detailOrNull.recipe.components.find(
    (component) => component.cost?.quality === "estimated",
  );
  if (!culprit?.cost) return generic;
  return `Estimated: ${culprit.ingredient_name}'s price - ${estimatedBecause(culprit.cost.price)}.`;
}

/** "a fix lives on the materials screen" is true for every missing piece
 * except a missing recipe, which has nowhere to click until the loader
 * arrives (WP-64). */
function fixableOnMaterials(missing: string[]): boolean {
  return missing.some((sentence) => sentence !== "no recipe yet");
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
        {/* The recipe card's own words, kept beside the conversion - the only
            audit a typed quantity has (PRD 17-18). */}
        {component.source_text ? (
          <p className="text-xs text-stone">the card says &ldquo;{component.source_text}&rdquo;</p>
        ) : null}
        {component.missing ? <p className="mt-1 text-sm text-plum">{component.missing}</p> : null}
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
            href={`/invoices/${component.cost.price.invoice_id}`}
            className="text-xs font-medium text-palm underline-offset-2 hover:underline"
          >
            See the invoice
          </Link>
        </div>
      ) : null}
    </li>
  );
}

export default function MenuMargins() {
  const [items, setItems] = useState<MenuItemSummary[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, MenuItemDetail>>({});
  const [detailError, setDetailError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const menu = await listMenuItems();
        if (cancelled) return;
        setItems(menu);
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

  if (items === null) {
    return (
      <div aria-busy="true" className="rounded-md border border-ink/10 bg-paper p-6">
        <p role="status" className="text-sm text-stone">
          Loading the menu
        </p>
      </div>
    );
  }

  // Archived items appear nowhere on this screen: they are out of the ranking
  // and out of the coverage count, and the click that brings one back lives
  // with the loader, not here.
  const live = items.filter((item) => item.archived_at === null);
  const costed = live.filter((item) => item.plate.quality !== "incomplete");
  const incomplete = live.filter((item) => item.plate.quality === "incomplete");
  // The one sanctioned parse on this screen, like the sparkline's: ordering is
  // geometry, and the parsed number is never rendered.
  const ranked = [...costed].sort(
    (a, b) => Number(b.plate.margin ?? 0) - Number(a.plate.margin ?? 0),
  );

  return (
    <div className="space-y-8">
      <header>
        <h1 className="font-display text-2xl font-semibold tracking-[-0.02em] text-ink">Menu</h1>
        <p className="mt-1 max-w-2xl text-sm text-stone">
          What each item earns after its ingredients, biggest margin first - so you know what to
          push, and what to fix.
        </p>
      </header>

      {live.length === 0 ? (
        <p className="rounded-md border border-ink/10 bg-paper px-4 py-6 text-sm text-stone">
          No menu yet. Load one and every item appears here with its margin.
        </p>
      ) : (
        <>
          <section className="space-y-3">
            <div className="flex items-baseline justify-between gap-4">
              <h2 className="font-display text-lg font-semibold text-ink">By margin</h2>
              <p className="text-sm text-stone">
                {costed.length} of {live.length} items costed
              </p>
            </div>

            {ranked.length === 0 ? (
              <p className="rounded-md border border-ink/10 bg-paper px-4 py-6 text-sm text-stone">
                Nothing costed yet - every item below is missing a piece.
              </p>
            ) : (
              <ol className="space-y-2">
                {ranked.map((item) => {
                  const detail = details[item.id] ?? null;
                  const isOpen = open === item.id;
                  return (
                    <li key={item.id} className="rounded-md border border-ink/10 bg-paper">
                      <button
                        type="button"
                        onClick={() => void toggle(item.id)}
                        aria-expanded={isOpen}
                        className="flex w-full flex-wrap items-start justify-between gap-3 rounded-md p-4 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-palm/30"
                      >
                        <div className="min-w-0">
                          <p className="font-medium text-ink">{item.name}</p>
                          <p className="mt-0.5 text-sm text-stone">
                            sells at AED {money(item.selling_price)} · costs AED{" "}
                            {summaryMoney(item.plate.cost_per_portion ?? "0")}
                            {item.recipe && item.recipe.yield_portions !== "1.000"
                              ? ` a portion (one batch makes ${quantity(item.recipe.yield_portions)}${
                                  item.recipe.yield_label ? ` ${item.recipe.yield_label}` : ""
                                })`
                              : ""}
                          </p>
                          {item.plate.quality === "estimated" ? (
                            <p className="mt-1 text-xs text-stone">{plateQualityNote(detail)}</p>
                          ) : null}
                        </div>
                        <div className="text-right">
                          <p className="font-display text-lg font-semibold text-ink">
                            AED {summaryMoney(item.plate.margin ?? "0")}
                            <span className="ml-2 text-sm font-medium text-stone">
                              {item.plate.margin_pct}%
                            </span>
                          </p>
                          <p className="text-xs text-stone">margin per item</p>
                        </div>
                      </button>

                      {isOpen ? (
                        <div className="border-t border-ink/10 px-4 pb-4">
                          {detail?.recipe ? (
                            <>
                              <p className="pt-3 text-xs text-stone">
                                Recipe version {detail.recipe.version} · earns from AED{" "}
                                {money(detail.plate.net_price ?? "0")} once the{" "}
                                {detail.plate.vat_rate === "0.05" ? "5% " : ""}VAT inside the menu
                                price is set aside
                              </p>
                              <ul className="mt-2 divide-y divide-ink/5">
                                {detail.recipe.components.map((component) => (
                                  <ComponentRow key={component.position} component={component} />
                                ))}
                              </ul>
                            </>
                          ) : detailError ? (
                            <p className="pt-3 text-sm text-plum">{detailError}</p>
                          ) : (
                            <p role="status" className="pt-3 text-sm text-stone">
                              Loading the recipe
                            </p>
                          )}
                        </div>
                      ) : null}
                    </li>
                  );
                })}
              </ol>
            )}
          </section>

          {incomplete.length > 0 ? (
            <section className="space-y-3">
              <div className="flex items-baseline justify-between gap-4">
                <h2 className="font-display text-lg font-semibold text-ink">Missing a piece</h2>
                <p className="text-sm text-stone">
                  {incomplete.length} {incomplete.length === 1 ? "item" : "items"}, no margin shown
                </p>
              </div>
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
                          {item.plate.missing.map((sentence) => (
                            <li key={sentence} className="text-sm text-plum">
                              {sentence}
                            </li>
                          ))}
                        </ul>
                      </div>
                      {fixableOnMaterials(item.plate.missing) ? (
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

          <p className="max-w-2xl text-xs text-stone">
            Margin is the menu price net of VAT minus what the ingredients cost, taken from your
            most recent confirmed invoices. It is not profit: labour, rent and waste are not in it.
            No figure here is ever marked verified - nothing on an invoice cross-checks the pack
            size a cost is divided by.
          </p>
        </>
      )}
    </div>
  );
}
