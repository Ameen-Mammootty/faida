"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getIngredient, unmapSupplierItem } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { formatDate, money } from "@/lib/format";
import type { IngredientDetail as Detail } from "@/lib/types";
import CostBadge from "./CostBadge";

/**
 * One raw material: what it costs per kilo, which packs make up that answer,
 * and every confirmed price behind it - each row linking to the invoice it
 * was read off, so a cost per kilo drills back to a photo (plan.md §8 M5).
 */
export default function IngredientDetail({ ingredientId }: { ingredientId: string }) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const loaded = await getIngredient(ingredientId);
        if (!cancelled) {
          setDetail(loaded);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Couldn't load this material.");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [ingredientId, reloadKey]);

  if (error !== null) {
    return (
      <p role="alert" className="rounded-md border border-caution/30 bg-gold-soft p-4 text-sm">
        {error}
      </p>
    );
  }
  if (detail === null) {
    return (
      <p role="status" aria-busy="true" className="text-sm text-stone">
        Loading
      </p>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <Link href="/materials" className="text-sm font-medium text-palm hover:text-palm-deep">
          &larr; Raw materials
        </Link>
        <h1 className="mt-2 font-display text-2xl font-semibold tracking-[-0.02em] text-ink">
          {detail.name}
        </h1>
      </div>

      <section className="rounded-md border border-ink/10 bg-paper p-5">
        <h2 className="text-sm font-semibold text-ink">What it costs</h2>
        <div className="mt-2">
          <CostBadge
            cost={detail.cost}
            blocked={detail.cost === null ? "no_price" : null}
            quality={detail.cost?.quality ?? null}
            reasons={detail.cost?.estimated_because ?? []}
            showBasis={false}
          />
        </div>
        {detail.cost !== null ? (
          <p className="mt-2 text-sm text-stone">
            Your most recent purchase: {detail.cost.pack_name} from{" "}
            {detail.cost.supplier_name ?? "an unknown supplier"} on{" "}
            {formatDate(detail.cost.as_of)}. Not an average &mdash; what you pay for it now.
          </p>
        ) : (
          <p className="mt-2 text-sm text-stone">
            No pack here has a confirmed price with a readable pack size yet.
          </p>
        )}
      </section>

      <section aria-labelledby="packs-heading" className="space-y-3">
        <h2 id="packs-heading" className="text-sm font-semibold text-ink">
          Bought as
        </h2>
        <ul className="space-y-3">
          {detail.packs.map((pack) => (
            <li
              key={pack.id}
              className="flex flex-wrap items-start justify-between gap-4 rounded-md border border-ink/10 bg-paper p-4"
            >
              <div>
                <p className="font-medium text-ink">{pack.canonical_name}</p>
                <p className="mt-0.5 text-sm text-stone">
                  {pack.supplier_name ?? "Unknown supplier"}
                  {pack.last_price ? ` · AED ${money(pack.last_price)} each` : ""}
                  {pack.last_price_at ? ` · ${formatDate(pack.last_price_at)}` : ""}
                </p>
                {pack.conversion !== null ? (
                  <p className="mt-1 text-xs text-stone">
                    {pack.conversion.note ??
                      `1 pack = ${pack.conversion.base_quantity} ${pack.conversion.base_unit}`}{" "}
                    &middot; stated by {pack.conversion.actor}
                  </p>
                ) : null}
              </div>
              <div className="flex items-start gap-4">
                <CostBadge
                  cost={pack.cost}
                  blocked={pack.blocked}
                  quality={pack.quality}
                  reasons={pack.estimated_because}
                />
                <button
                  type="button"
                  onClick={async () => {
                    try {
                      await unmapSupplierItem(pack.id);
                      setReloadKey((key) => key + 1);
                    } catch (err) {
                      setError(
                        err instanceof ApiError ? err.message : "Couldn't unmap that pack.",
                      );
                    }
                  }}
                  className="text-sm font-medium text-stone hover:text-caution"
                >
                  Not this
                </button>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="prices-heading" className="space-y-3">
        <h2 id="prices-heading" className="text-sm font-semibold text-ink">
          Every price behind that number
        </h2>
        {detail.prices.length === 0 ? (
          <p className="rounded-md border border-dashed border-ink/15 p-4 text-sm text-stone">
            No confirmed purchases yet.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-md border border-ink/10">
            <table className="w-full min-w-[36rem] text-sm">
              <thead className="bg-mist text-left text-xs font-semibold text-stone">
                <tr>
                  <th className="px-4 py-2">Date</th>
                  <th className="px-4 py-2">Pack</th>
                  <th className="px-4 py-2">Supplier</th>
                  <th className="px-4 py-2 text-right">Price</th>
                  <th className="px-4 py-2">Invoice</th>
                </tr>
              </thead>
              <tbody>
                {detail.prices.map((price, index) => (
                  <tr key={`${price.supplier_item_id}-${index}`} className="border-t border-ink/10">
                    <td className="px-4 py-2 text-stone">{formatDate(price.observed_at)}</td>
                    <td className="px-4 py-2 text-ink">{price.canonical_name}</td>
                    <td className="px-4 py-2 text-stone">{price.supplier_name ?? "-"}</td>
                    <td className="px-4 py-2 text-right tabular-nums text-ink">
                      AED {money(price.price)}
                    </td>
                    <td className="px-4 py-2">
                      {price.invoice_id ? (
                        <Link
                          href={`/invoices/${price.invoice_id}`}
                          className="font-medium text-palm hover:text-palm-deep"
                        >
                          {price.invoice_no ?? "See the photo"}
                        </Link>
                      ) : (
                        <span className="text-stone">-</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
