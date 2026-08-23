"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { listInvoices } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { formatDate, money, PAYMENT_LABEL } from "@/lib/format";
import type { InvoiceStatus, InvoiceSummary } from "@/lib/types";
import StatusChip from "./StatusChip";

const FILTERS: { value: InvoiceStatus | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "awaiting_confirm", label: "To confirm" },
  { value: "needs_review", label: "Needs approval" },
  { value: "confirmed", label: "Confirmed" },
  { value: "draft", label: "Drafts" },
];

const VALID_STATUSES = new Set<string>(["draft", "awaiting_confirm", "confirmed", "needs_review"]);

export default function InvoiceList() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const rawStatus = searchParams.get("status") ?? "all";
  const status = VALID_STATUSES.has(rawStatus) ? (rawStatus as InvoiceStatus) : undefined;

  const active = status ?? "all";

  const [result, setResult] = useState<{
    key: string;
    invoices?: InvoiceSummary[];
    error?: string;
  } | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const key = `${active}:${reloadKey}`;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await listInvoices(status ? { status } : {});
        if (!cancelled) setResult({ key, invoices: data });
      } catch (err) {
        if (!cancelled) {
          setResult({
            key,
            error:
              err instanceof ApiError ? err.message : "Couldn't load the invoices. Try again.",
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [key, status]);

  const current = result?.key === key ? result : null;
  const invoices = current?.invoices ?? null;
  const error = current?.error ?? null;

  return (
    <div className="space-y-5">
      <header>
        <h1 className="font-display text-2xl font-semibold tracking-[-0.02em] text-ink">
          Invoices
        </h1>
        <p className="mt-1 text-sm text-stone">
          Forwarded on WhatsApp, read, and checked. Every number traces to its photo.
        </p>
      </header>

      <nav aria-label="Filter by status" className="flex gap-5 border-b border-ink/10">
        {FILTERS.map((filter) => {
          const isActive = active === filter.value;
          return (
            <Link
              key={filter.value}
              href={
                filter.value === "all"
                  ? "/invoices"
                  : { pathname: "/invoices", query: { status: filter.value } }
              }
              aria-current={isActive ? "page" : undefined}
              className={`-mb-px border-b-2 pb-2 text-sm ${
                isActive
                  ? "border-gold font-semibold text-palm"
                  : "border-transparent font-medium text-stone hover:text-palm"
              }`}
            >
              {filter.label}
            </Link>
          );
        })}
      </nav>

      {error ? (
        <div className="rounded-md border border-plum/30 bg-paper p-6">
          <p className="text-sm text-ink">{error}</p>
          <button
            type="button"
            onClick={() => setReloadKey((value) => value + 1)}
            className="mt-3 rounded-sm bg-palm px-3 py-1.5 text-sm font-medium text-white hover:bg-palm-deep"
          >
            Try again
          </button>
        </div>
      ) : invoices === null ? (
        <div aria-busy="true" className="rounded-md border border-ink/10 bg-paper p-6">
          <p role="status" className="text-sm text-stone">
            Loading invoices
          </p>
        </div>
      ) : invoices.length === 0 ? (
        <div className="rounded-md border border-ink/10 bg-paper p-8 text-center">
          <p className="text-sm text-ink">
            {status ? "No invoices with this status." : "No invoices yet."}
          </p>
          <p className="mt-1 text-sm text-stone">
            Forward a supplier invoice photo on WhatsApp and it appears here.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-md border border-ink/10 bg-paper">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-ink/10 text-left text-[11px] font-medium tracking-wider text-stone uppercase">
                <th scope="col" className="px-4 py-2.5 font-medium">
                  Supplier
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium">
                  Invoice
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium">
                  Date
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium">
                  Branch
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium">
                  Payment
                </th>
                <th scope="col" className="px-4 py-2.5 text-right font-medium">
                  Total
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium">
                  Status
                </th>
              </tr>
            </thead>
            <tbody>
              {invoices.map((invoice) => (
                <tr
                  key={invoice.id}
                  onClick={() => router.push(`/invoices/${invoice.id}`)}
                  className="cursor-pointer border-b border-ink/5 last:border-0 hover:bg-cream/70"
                >
                  <td className="px-4 py-3 font-medium text-ink">
                    <Link
                      href={`/invoices/${invoice.id}`}
                      className="hover:text-palm"
                      onClick={(event) => event.stopPropagation()}
                    >
                      {invoice.supplier_name ?? "Supplier not read"}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-stone tabular-nums">
                    {invoice.invoice_no ?? "-"}
                  </td>
                  <td className="px-4 py-3 text-stone tabular-nums">
                    {formatDate(invoice.invoice_date ?? invoice.created_at)}
                  </td>
                  <td className="px-4 py-3 text-stone">{invoice.branch_name ?? "-"}</td>
                  <td className="px-4 py-3 text-stone">
                    {invoice.payment_kind ? PAYMENT_LABEL[invoice.payment_kind] : "-"}
                  </td>
                  <td className="px-4 py-3 text-right font-medium text-ink tabular-nums">
                    {invoice.total === null ? (
                      <span className="text-xs font-medium text-caution">Not read</span>
                    ) : (
                      `${invoice.currency} ${money(invoice.total)}`
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <StatusChip status={invoice.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
