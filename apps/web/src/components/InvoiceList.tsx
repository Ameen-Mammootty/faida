"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { listInvoices } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { formatDate, money } from "@/lib/format";
import { branchOptions as deriveBranches, supplierOptions as deriveSuppliers } from "@/lib/options";
import type { InvoiceFilters, InvoiceStatus, InvoiceSummary } from "@/lib/types";
import StatusChip from "./StatusChip";

const STATUS_TABS: { value: InvoiceStatus | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "awaiting_confirm", label: "To confirm" },
  { value: "needs_review", label: "Needs approval" },
  { value: "confirmed", label: "Confirmed" },
  { value: "draft", label: "Drafts" },
];

const VALID_STATUSES = new Set<string>(["draft", "awaiting_confirm", "confirmed", "needs_review"]);

type SortDir = "desc" | "asc";

/** The list's date is the invoice date, falling back to arrival. */
function sortDate(invoice: InvoiceSummary): string {
  return invoice.invoice_date ?? invoice.created_at;
}

/** Newest first by default; ISO strings compare lexicographically. */
function sortInvoices(invoices: InvoiceSummary[], dir: SortDir): InvoiceSummary[] {
  // desc: an earlier date sorts after a later one (newest first).
  const earlierFirst = dir === "desc" ? 1 : -1;
  return [...invoices].sort((a, b) => {
    const [da, db] = [sortDate(a), sortDate(b)];
    if (da !== db) return da < db ? earlierFirst : -earlierFirst;
    if (a.created_at !== b.created_at) {
      return a.created_at < b.created_at ? earlierFirst : -earlierFirst;
    }
    return a.id < b.id ? earlierFirst : -earlierFirst;
  });
}

export default function InvoiceList() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const rawStatus = searchParams.get("status") ?? "all";
  const status = VALID_STATUSES.has(rawStatus) ? (rawStatus as InvoiceStatus) : undefined;
  const branchId = searchParams.get("branch_id") ?? undefined;
  const supplierId = searchParams.get("supplier_id") ?? undefined;
  const activeTab = status ?? "all";
  const filtered = Boolean(status || branchId || supplierId);

  const [result, setResult] = useState<{
    key: string;
    invoices?: InvoiceSummary[];
    error?: string;
  } | null>(null);
  // The filter dropdowns list every branch/supplier, so their options come
  // from one unfiltered fetch - reused from the main load when possible.
  const [options, setOptions] = useState<InvoiceSummary[] | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const key = `${activeTab}:${branchId ?? ""}:${supplierId ?? ""}:${reloadKey}`;

  useEffect(() => {
    let cancelled = false;
    const filters: InvoiceFilters = {};
    if (status) filters.status = status;
    if (branchId) filters.branch_id = branchId;
    if (supplierId) filters.supplier_id = supplierId;
    (async () => {
      try {
        const data = await listInvoices(filters);
        if (!cancelled) {
          setResult({ key, invoices: data });
          if (!filtered) setOptions(data);
        }
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
  }, [key, status, branchId, supplierId, filtered]);

  useEffect(() => {
    if (options !== null || !filtered) return;
    let cancelled = false;
    (async () => {
      try {
        const data = await listInvoices({});
        if (!cancelled) setOptions(data);
      } catch {
        // The dropdowns simply stay minimal; the main list carries the error.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [options, filtered]);

  const current = result?.key === key ? result : null;
  const invoices = current?.invoices ? sortInvoices(current.invoices, sortDir) : null;
  const error = current?.error ?? null;

  const branchOptions = deriveBranches(options ?? []);
  const supplierOptions = deriveSuppliers(options ?? []);
  // A deep-linked filter id keeps its selection visible even before (or
  // without) appearing in the option rows.
  if (branchId && !branchOptions.some((option) => option.id === branchId)) {
    branchOptions.push({ id: branchId, name: "Selected branch" });
  }
  if (supplierId && !supplierOptions.some((option) => option.id === supplierId)) {
    supplierOptions.push({ id: supplierId, name: "Selected supplier" });
  }

  function hrefWith(overrides: Record<string, string | null>): string {
    const params = new URLSearchParams(searchParams.toString());
    for (const [name, value] of Object.entries(overrides)) {
      if (value === null) params.delete(name);
      else params.set(name, value);
    }
    const query = params.toString();
    return query ? `/invoices?${query}` : "/invoices";
  }

  const selectClasses =
    "rounded-sm border border-ink/20 bg-paper px-2 py-1.5 text-sm text-ink hover:border-palm/50";

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-[-0.02em] text-ink">
            Invoices
          </h1>
          <p className="mt-1 text-sm text-stone">
            Forwarded on WhatsApp, read, and checked. Every number traces to its photo.
          </p>
        </div>
        {/* WP-34: both fallback paths, one click from the list - upload a
            photo, or type the invoice in with no photo at all. */}
        <div className="flex items-center gap-2.5">
          <Link
            href="/invoices/manual"
            className="rounded-sm border border-palm/30 px-3.5 py-2 text-sm font-medium text-palm hover:border-palm hover:bg-mist"
          >
            Enter manually
          </Link>
          <Link
            href="/invoices/new"
            className="rounded-sm bg-palm px-3.5 py-2 text-sm font-semibold text-white hover:bg-palm-deep"
          >
            Upload invoice
          </Link>
        </div>
      </header>

      <nav aria-label="Filter by status" className="flex gap-5 border-b border-ink/10">
        {STATUS_TABS.map((tab) => {
          const isActive = activeTab === tab.value;
          return (
            <Link
              key={tab.value}
              href={hrefWith({ status: tab.value === "all" ? null : tab.value })}
              aria-current={isActive ? "page" : undefined}
              className={`-mb-px border-b-2 pb-2 text-sm ${
                isActive
                  ? "border-gold font-semibold text-palm"
                  : "border-transparent font-medium text-stone hover:text-palm"
              }`}
            >
              {tab.label}
            </Link>
          );
        })}
      </nav>

      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm font-medium text-stone">
          Branch
          <select
            value={branchId ?? ""}
            onChange={(event) =>
              router.replace(hrefWith({ branch_id: event.target.value || null }))
            }
            className={selectClasses}
          >
            <option value="">All branches</option>
            {branchOptions.map((option) => (
              <option key={option.id} value={option.id}>
                {option.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm font-medium text-stone">
          Supplier
          <select
            value={supplierId ?? ""}
            onChange={(event) =>
              router.replace(hrefWith({ supplier_id: event.target.value || null }))
            }
            className={selectClasses}
          >
            <option value="">All suppliers</option>
            {supplierOptions.map((option) => (
              <option key={option.id} value={option.id}>
                {option.name}
              </option>
            ))}
          </select>
        </label>
      </div>

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
          {filtered ? (
            <>
              <p className="text-sm text-ink">No invoices match these filters.</p>
              <p className="mt-1 text-sm text-stone">
                <Link href="/invoices" className="font-medium text-palm hover:text-palm-deep">
                  Clear the filters
                </Link>{" "}
                to see every invoice.
              </p>
            </>
          ) : (
            <>
              <p className="text-sm text-ink">No invoices yet.</p>
              <p className="mt-1 text-sm text-stone">
                Forward a supplier invoice photo on WhatsApp and it appears here. You can also{" "}
                <Link
                  href="/invoices/new"
                  className="font-medium text-palm hover:text-palm-deep"
                >
                  upload a photo
                </Link>{" "}
                or{" "}
                <Link
                  href="/invoices/manual"
                  className="font-medium text-palm hover:text-palm-deep"
                >
                  enter one manually
                </Link>
                .
              </p>
            </>
          )}
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
                <th
                  scope="col"
                  aria-sort={sortDir === "desc" ? "descending" : "ascending"}
                  className="px-4 py-2.5 font-medium"
                >
                  <button
                    type="button"
                    onClick={() => setSortDir((dir) => (dir === "desc" ? "asc" : "desc"))}
                    className="inline-flex items-center gap-1 tracking-wider uppercase hover:text-palm"
                  >
                    Date
                    <span aria-hidden="true">{sortDir === "desc" ? "↓" : "↑"}</span>
                    <span className="sr-only">
                      {sortDir === "desc"
                        ? "sorted newest first; activate for oldest first"
                        : "sorted oldest first; activate for newest first"}
                    </span>
                  </button>
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium">
                  Branch
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
                    {formatDate(sortDate(invoice))}
                  </td>
                  <td className="px-4 py-3 text-stone">{invoice.branch_name ?? "-"}</td>
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
