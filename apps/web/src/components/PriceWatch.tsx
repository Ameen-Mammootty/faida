import { formatDate, money } from "@/lib/format";
import type { PriceHistory } from "@/lib/types";

/**
 * Confirmed price history for the items on this invoice, verbatim from
 * GET /api/supplier-items/{id}/prices.
 *
 * WP-33 slot: the price-trend sparkline lands inside this card, replacing
 * the list below with the same data. Keep the card shell and heading.
 */
export default function PriceWatch({ histories }: { histories: PriceHistory[] }) {
  if (histories.length === 0) return null;
  return (
    <aside aria-labelledby="price-watch-heading" className="rounded-md border border-ink/10 bg-paper p-4">
      <div className="flex items-center gap-2">
        <span aria-hidden="true" className="h-3.5 w-1 rounded-full bg-gold" />
        <h3 id="price-watch-heading" className="text-sm font-semibold text-ink">
          Price history
        </h3>
      </div>
      <div className="mt-3 space-y-4">
        {histories.map((history) => (
          <div key={history.supplier_item_id}>
            <p className="text-sm font-medium text-ink">{history.canonical_name}</p>
            <table className="mt-1.5 w-full text-sm">
              <caption className="sr-only">
                Confirmed prices for {history.canonical_name}
              </caption>
              <tbody>
                {history.prices.map((point) => (
                  <tr key={point.observed_at} className="border-b border-ink/5 last:border-0">
                    <td className="py-1 text-stone">{formatDate(point.observed_at)}</td>
                    <td className="py-1 text-right font-medium tabular-nums">
                      {money(point.price)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-1.5 text-xs text-stone">
              Confirmed purchases only. This invoice joins the history when it is confirmed.
            </p>
          </div>
        ))}
      </div>
    </aside>
  );
}
