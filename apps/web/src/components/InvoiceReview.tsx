"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { confirmInvoice, getInvoice, patchInvoiceFields } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { formatDate, PAYMENT_LABEL } from "@/lib/format";
import type { Correction, DocumentSource, InvoiceDetail } from "@/lib/types";
import { AlertIcon } from "./icons";
import FieldBadge from "./FieldBadge";
import InvoicePhoto from "./InvoicePhoto";
import LinesTable from "./LinesTable";
import PriceWatch from "./PriceWatch";
import StatusChip from "./StatusChip";
import TotalsBlock from "./TotalsBlock";

const SOURCE_LABEL: Record<DocumentSource, string> = {
  whatsapp: "WhatsApp",
  upload: "Uploaded",
  manual: "Manual entry",
};

interface LoadResult {
  key: string;
  invoice?: InvoiceDetail;
  error?: string;
}

function HeaderField({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <dt className="text-[11px] font-medium tracking-wider text-stone uppercase">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium text-ink">
        {value ?? <FieldBadge status="amber" label="Not read" />}
      </dd>
    </div>
  );
}

export default function InvoiceReview({ id }: { id: string }) {
  const [result, setResult] = useState<LoadResult | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [confirming, setConfirming] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const imageRefreshedAt = useRef(0);

  const key = `${id}:${reloadKey}`;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const detail = await getInvoice(id);
        if (!cancelled) setResult({ key, invoice: detail });
      } catch (err) {
        if (!cancelled) {
          setResult({
            key,
            error:
              err instanceof ApiError ? err.message : "Couldn't load this invoice. Try again.",
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [key, id]);

  const current = result?.key === key ? result : null;
  const invoice = current?.invoice ?? null;
  const loadError = current?.error ?? null;

  function applyUpdate(updated: InvoiceDetail) {
    setResult((prev) =>
      prev && prev.key === key && prev.invoice ? { ...prev, invoice: updated } : prev,
    );
  }

  // PATCH returns the full re-validated detail - use it directly, no refetch.
  async function saveCorrections(corrections: Correction[]) {
    applyUpdate(await patchInvoiceFields(id, corrections));
  }

  async function confirm() {
    setConfirming(true);
    setConfirmError(null);
    try {
      applyUpdate(await confirmInvoice(id));
    } catch (err) {
      setConfirmError(
        err instanceof ApiError ? err.message : "Couldn't confirm the invoice. Try again.",
      );
    } finally {
      setConfirming(false);
    }
  }

  // The signed image URL lives ~600 s. When a long-open photo starts failing,
  // refetch the detail quietly for a fresh URL - at most once every 10 s so a
  // permanently broken image can't loop.
  async function refreshExpiredImage() {
    const now = Date.now();
    if (now - imageRefreshedAt.current < 10_000) return;
    imageRefreshedAt.current = now;
    try {
      applyUpdate(await getInvoice(id));
    } catch {
      // keep the current view; the photo shows its fallback
    }
  }

  if (loadError) {
    return (
      <div className="rounded-md border border-plum/30 bg-paper p-6">
        <p className="text-sm text-ink">{loadError}</p>
        <button
          type="button"
          onClick={() => setReloadKey((value) => value + 1)}
          className="mt-3 rounded-sm bg-palm px-3 py-1.5 text-sm font-medium text-white hover:bg-palm-deep"
        >
          Try again
        </button>
      </div>
    );
  }

  if (!invoice) {
    return (
      <div aria-busy="true" className="rounded-md border border-ink/10 bg-paper p-6">
        <p role="status" className="text-sm text-stone">
          Loading invoice
        </p>
      </div>
    );
  }

  const confirmed = invoice.status === "confirmed";
  const cashHold = invoice.status === "needs_review" && invoice.payment_kind === "cash";
  const editable = invoice.status === "awaiting_confirm" || invoice.status === "needs_review";
  const watchItemIds = [
    ...new Set(
      invoice.lines
        .map((line) => line.supplier_item_id)
        .filter((itemId): itemId is string => itemId !== null),
    ),
  ];

  return (
    <div className="space-y-5">
      <nav>
        <Link href="/invoices" className="text-sm font-medium text-palm hover:text-palm-deep">
          &larr; All invoices
        </Link>
      </nav>

      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-[-0.02em] text-ink">
            {invoice.supplier_name ?? "Supplier not read"}
          </h1>
          <p className="mt-1 text-sm text-stone">
            {[
              invoice.invoice_no ? `Invoice ${invoice.invoice_no}` : "No invoice number",
              invoice.branch_name,
              invoice.document ? `via ${SOURCE_LABEL[invoice.document.source]}` : null,
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <StatusChip status={invoice.status} />
          {/* The chip above already says "Confirmed"; a disabled button saying
              it again was two labels for one fact. The date is the thing a
              reader actually wants next. */}
          {confirmed ? (
            invoice.confirmed_at ? (
              <p className="text-xs text-stone">on {formatDate(invoice.confirmed_at)}</p>
            ) : null
          ) : cashHold ? (
            <button
              type="button"
              onClick={() => void confirm()}
              disabled={confirming}
              className="rounded-sm border-2 border-palm bg-paper px-4 py-2 text-sm font-semibold text-palm hover:bg-mist disabled:opacity-60"
            >
              {confirming ? "Approving" : "Approve cash invoice"}
            </button>
          ) : (
            <button
              type="button"
              onClick={() => void confirm()}
              disabled={confirming}
              className="rounded-sm bg-palm px-4 py-2 text-sm font-semibold text-white hover:bg-palm-deep disabled:opacity-60"
            >
              {confirming ? "Confirming" : "Confirm invoice"}
            </button>
          )}
          {confirmError ? (
            <p className="max-w-xs text-right text-xs font-medium text-plum">{confirmError}</p>
          ) : null}
        </div>
      </header>

      {cashHold ? (
        <p className="flex items-center gap-2 rounded-md border border-caution/20 bg-gold-soft px-3 py-2.5 text-sm text-caution">
          <AlertIcon />
          Paid in cash, so it needs the owner&apos;s approval before it counts.
        </p>
      ) : null}

      <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <div className="self-start lg:sticky lg:top-6">
          <InvoicePhoto
            src={invoice.image_url}
            alt={`Invoice photo from ${invoice.supplier_name ?? "unknown supplier"}`}
            onExpired={() => void refreshExpiredImage()}
          />
        </div>

        <div className="space-y-5">
          <section className="rounded-md border border-ink/10 bg-paper p-4 sm:p-5">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
              <HeaderField label="Supplier" value={invoice.supplier_name} />
              <HeaderField label="Invoice no" value={invoice.invoice_no} />
              <HeaderField
                label="Date"
                value={invoice.invoice_date ? formatDate(invoice.invoice_date) : null}
              />
              <HeaderField
                label="Payment"
                value={invoice.payment_kind ? PAYMENT_LABEL[invoice.payment_kind] : null}
              />
            </dl>
            <div className="mt-4 border-t border-ink/10 pt-1">
              <LinesTable
                lines={invoice.lines}
                editable={editable}
                onSaveLine={saveCorrections}
              />
            </div>
            <div className="mt-4">
              <TotalsBlock
                subtotal={invoice.subtotal}
                tax={invoice.tax}
                total={invoice.total}
                currency={invoice.currency}
                doc={invoice.confidence.document}
                editable={editable}
                onSaveTotals={saveCorrections}
              />
            </div>
          </section>

          <PriceWatch itemIds={watchItemIds} confirmed={confirmed} />
        </div>
      </div>
    </div>
  );
}
