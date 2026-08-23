"use client";

import { useEffect, useState } from "react";
import { getSupplierItemPrices } from "@/lib/api";
import { formatDate, money } from "@/lib/format";
import type { PriceHistory } from "@/lib/types";
import { TrendDownIcon, TrendUpIcon } from "./icons";
import Sparkline from "./Sparkline";

/**
 * Price watch (WP-33): for every line on the invoice that carries a
 * supplier_item_id, the confirmed price history from
 * GET /api/supplier-items/{id}/prices as a sparkline plus the prev -> last
 * movement, labeled with the exact decimal strings the API served.
 *
 * Each item's history is fetched lazily, one request per item, independent
 * of the invoice detail - the review fields never wait on this card. Items
 * without confirmed observations stay hidden; the card itself appears only
 * once one item has something to show.
 */

/** No entry yet means the item is still loading. */
type ItemState = { state: "ready"; history: PriceHistory } | { state: "failed" };

function rangeLabel(history: PriceHistory): string {
  const { prices } = history;
  const first = prices[0];
  const last = prices[prices.length - 1];
  return (
    `${history.canonical_name}: ${prices.length} confirmed ` +
    `${prices.length === 1 ? "price" : "prices"}, ` +
    `${money(first.price)} on ${formatDate(first.observed_at)} to ` +
    `${money(last.price)} on ${formatDate(last.observed_at)} AED` +
    (history.unit ? ` per ${history.unit}` : "")
  );
}

/** The prev -> last movement, verbatim strings; direction (a comparison,
 * never a displayed value) picks the icon and tone. Colour never carries the
 * meaning alone - the word rides along. */
function Movement({ history }: { history: PriceHistory }) {
  const { prev_price: prev, last_price: last } = history;
  const perUnit = history.unit ? ` per ${history.unit}` : "";
  if (last === null) return null;
  if (prev === null || prev === last) {
    return (
      <p className="text-xs text-stone">
        {history.prices.length > 1
          ? `Steady at AED ${money(last)}${perUnit}.`
          : `First confirmed price: AED ${money(last)}${perUnit}.`}
      </p>
    );
  }
  const up = Number.parseFloat(last) > Number.parseFloat(prev);
  return (
    <p
      className={`flex items-center gap-1 text-xs font-medium ${
        up ? "text-caution" : "text-verified"
      }`}
    >
      {up ? <TrendUpIcon /> : <TrendDownIcon />}
      {up ? "Up" : "Down"}: AED {money(prev)} &rarr; {money(last)}
      {perUnit}
    </p>
  );
}

function HistoryRow({ history }: { history: PriceHistory }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5">
      <div className="min-w-0">
        <p className="text-sm font-medium text-ink">{history.canonical_name}</p>
        <Movement history={history} />
      </div>
      <Sparkline label={rangeLabel(history)} prices={history.prices} />
      <table className="sr-only">
        <caption>Confirmed prices for {history.canonical_name}</caption>
        <thead>
          <tr>
            <th scope="col">Date</th>
            <th scope="col">Price (AED)</th>
          </tr>
        </thead>
        <tbody>
          {history.prices.map((point) => (
            <tr key={point.observed_at}>
              <td>{formatDate(point.observed_at)}</td>
              <td>{money(point.price)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function PriceWatch({
  itemIds,
  confirmed,
}: {
  /** Unique supplier_item_ids from the invoice's lines, in line order. */
  itemIds: string[];
  /** Whether this invoice is confirmed (its prices already in the history). */
  confirmed: boolean;
}) {
  const [items, setItems] = useState<Record<string, ItemState>>({});
  const key = itemIds.join(",");

  useEffect(() => {
    let cancelled = false;
    const ids = key === "" ? [] : key.split(",");
    for (const id of ids) {
      // One independent request per item: a slow or missing history never
      // holds up the others.
      getSupplierItemPrices(id)
        .then((history) => {
          if (!cancelled) setItems((prev) => ({ ...prev, [id]: { state: "ready", history } }));
        })
        .catch(() => {
          if (!cancelled) setItems((prev) => ({ ...prev, [id]: { state: "failed" } }));
        });
    }
    return () => {
      cancelled = true;
    };
  }, [key]);

  const ready = itemIds
    .map((id) => items[id])
    .filter(
      (item): item is { state: "ready"; history: PriceHistory } => item?.state === "ready",
    )
    .map((item) => item.history)
    .filter((history) => history.prices.length > 0);

  if (ready.length === 0) return null;

  return (
    <aside
      aria-labelledby="price-watch-heading"
      className="rounded-md border border-ink/10 bg-paper p-4"
    >
      <div className="flex items-center gap-2">
        <span aria-hidden="true" className="h-3.5 w-1 rounded-full bg-gold" />
        <h3 id="price-watch-heading" className="text-sm font-semibold text-ink">
          Price history
        </h3>
      </div>
      <div className="mt-3 space-y-3">
        {ready.map((history) => (
          <HistoryRow key={history.id} history={history} />
        ))}
      </div>
      <p className="mt-3 text-xs text-stone">
        Confirmed purchases only.
        {confirmed ? "" : " This invoice joins the history when it is confirmed."}
      </p>
    </aside>
  );
}
