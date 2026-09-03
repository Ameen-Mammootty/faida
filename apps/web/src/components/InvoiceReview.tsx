"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  approveInvoice,
  confirmInvoice,
  dismissInvoice,
  getInvoice,
  patchInvoiceFields,
} from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { formatDate, money, PAYMENT_LABEL } from "@/lib/format";
import type { Correction, DocumentSource, InvoiceDetail, PaymentKind } from "@/lib/types";
import { AlertIcon } from "./icons";
import DuplicateChip from "./DuplicateChip";
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

/** What the one status strip says after a write, success or failure alike. */
interface Notice {
  tone: "ok" | "error";
  text: string;
}

const PAYMENT_KINDS: PaymentKind[] = ["cash", "credit"];

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
  const [dismissing, setDismissing] = useState(false);
  const [approving, setApproving] = useState(false);
  const [savingPayment, setSavingPayment] = useState(false);
  const [reason, setReason] = useState("");
  // One strip for every write action, success and failure alike: only one can
  // be in flight, and whichever finished is the one the reader needs the
  // sentence for. role="status" below, so it is announced as it changes.
  const [notice, setNotice] = useState<Notice | null>(null);
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

  // A refusal names the row as it is now ("invoice is already confirmed"),
  // which is exactly when what the screen shows has gone stale - another tab
  // got there first. So a 409 also refetches, and the reader sees the sentence
  // beside the state it describes rather than beside a form for a state that
  // no longer exists.
  async function failed(err: unknown, fallback: string) {
    setNotice({ tone: "error", text: err instanceof ApiError ? err.message : fallback });
    if (err instanceof ApiError && err.status === 409) {
      try {
        applyUpdate(await getInvoice(id));
      } catch {
        // keep the current view; the sentence in the strip still stands
      }
    }
  }

  async function confirm() {
    setConfirming(true);
    setNotice(null);
    try {
      applyUpdate(await confirmInvoice(id));
      setNotice({ tone: "ok", text: "Confirmed. This invoice is now recorded." });
    } catch (err) {
      await failed(err, "Couldn't confirm the invoice. Try again.");
    } finally {
      setConfirming(false);
    }
  }

  // The cash gate (M7 WP-74, PRD §21): the owner lets a cash paper through
  // with a reason. The button is disabled until there is one, so the server's
  // 422 for a blank reason is unreachable from here; its 409s (not cash any
  // more, already recorded, dismissed under another tab) land in the strip.
  async function approve(event: React.FormEvent) {
    event.preventDefault();
    const text = reason.trim();
    if (!text) return;
    setApproving(true);
    setNotice(null);
    try {
      applyUpdate(await approveInvoice(id, text));
      setReason("");
      setNotice({ tone: "ok", text: "Approved with a reason. This cash invoice is now recorded." });
    } catch (err) {
      await failed(err, "Couldn't approve the invoice. Try again.");
    } finally {
      setApproving(false);
    }
  }

  // Stays on the page and re-renders from the response, exactly like confirm:
  // the reader watches the row they were looking at change state, instead of
  // being bounced to a list where the only evidence is an absence.
  async function dismiss() {
    setDismissing(true);
    setNotice(null);
    try {
      applyUpdate(await dismissInvoice(id));
      setNotice({ tone: "ok", text: "Dismissed this copy. Nothing was counted twice." });
    } catch (err) {
      await failed(err, "Couldn't dismiss this copy. Try again.");
    } finally {
      setDismissing(false);
    }
  }

  // "Paid by" goes through the correction door like every other field (one
  // door for everyone): a misread cash is corrected, never approved. The
  // server moves the status the way the pipeline would have - cash holds an
  // awaiting paper, credit lifts a cash hold unless it is also a duplicate -
  // and the screen re-renders from what comes back.
  async function setPaymentKind(kind: PaymentKind) {
    setSavingPayment(true);
    setNotice(null);
    try {
      const updated = await patchInvoiceFields(id, [
        { line_index: null, field: "payment_kind", value: kind },
      ]);
      applyUpdate(updated);
      const held = updated.status === "needs_review";
      setNotice({
        tone: "ok",
        text:
          kind === "cash"
            ? "Paid by set to Cash. Held for the owner's approval."
            : held
              ? "Paid by set to Credit. Still held as a duplicate copy."
              : "Paid by set to Credit. Ready to confirm.",
      });
    } catch (err) {
      await failed(err, "Couldn't change how this was paid. Try again.");
    } finally {
      setSavingPayment(false);
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
  // WP-44. The status test matters: the WhatsApp reply invites confirming a
  // copy that really is a new invoice, so a confirmed row can carry the pointer
  // too - and once it does, it is a recorded invoice and nothing else.
  const dismissed = invoice.status === "dismissed";
  // A copy is a copy for as long as it exists - dismissing resolves it, it does
  // not change what the paper is, so the banner keeps explaining the row.
  const isCopy = invoice.duplicate_of_invoice_id !== null && !confirmed;
  const heldDuplicate = isCopy && !dismissed;
  // Only these two states can be confirmed (api.py answers 409 for the rest),
  // so the button asks for them by name. Written as a bare else, `dismissed`
  // would land here and offer an action the server is guaranteed to refuse.
  // A cash hold is never confirmable: the owner approves it with a reason
  // (WP-74), and the server answers 409 to a confirm - so the button is not
  // offered at all, and the cash banner below carries the approve form.
  const confirmable =
    (invoice.status === "awaiting_confirm" || invoice.status === "needs_review") && !cashHold;
  const busy = confirming || dismissing || approving || savingPayment;
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
          {/* A held duplicate says "Duplicate" here too. Left as the status
              chip it read "Needs approval" - cash-hold language, on a row
              nobody needs to approve, contradicting the banner underneath. */}
          {heldDuplicate ? <DuplicateChip /> : <StatusChip status={invoice.status} />}
          {/* The chip above already says "Confirmed"; a disabled button saying
              it again was two labels for one fact. The date is the thing a
              reader actually wants next. */}
          {confirmed ? (
            invoice.confirmed_at ? (
              <p className="text-xs text-stone">on {formatDate(invoice.confirmed_at)}</p>
            ) : null
          ) : dismissed ? (
            <p className="max-w-xs text-right text-xs text-stone">
              Dismissed. This copy is out of the invoice list.
            </p>
          ) : (
            <div className="flex flex-wrap items-center justify-end gap-2">
              {/* On a copy this is the action that makes sense, so it leads and
                  Confirm steps back to the outline treatment. Confirming is
                  still one click away - the WhatsApp reply promised it. On a
                  cash copy both actions sit in the cash banner instead, beside
                  the reason field they belong with. */}
              {heldDuplicate && !cashHold ? (
                <button
                  type="button"
                  onClick={() => void dismiss()}
                  disabled={busy}
                  className="min-h-11 rounded-sm bg-palm px-4 py-2 text-sm font-semibold text-white hover:bg-palm-deep disabled:opacity-60"
                >
                  {dismissing ? "Dismissing" : "Dismiss this copy"}
                </button>
              ) : null}
              {confirmable ? (
                <button
                  type="button"
                  onClick={() => void confirm()}
                  disabled={busy}
                  className={
                    heldDuplicate
                      ? "min-h-11 rounded-sm border-2 border-palm bg-paper px-4 py-2 text-sm font-semibold text-palm hover:bg-mist disabled:opacity-60"
                      : "min-h-11 rounded-sm bg-palm px-4 py-2 text-sm font-semibold text-white hover:bg-palm-deep disabled:opacity-60"
                  }
                >
                  {confirming ? "Confirming" : "Confirm invoice"}
                </button>
              ) : null}
            </div>
          )}
        </div>
      </header>

      {/* The one strip every write speaks through - approve, confirm, dismiss
          and the "Paid by" change, success and failure alike. Always in the
          tree so a screen reader hears the change, never a layout jump. */}
      <p
        role="status"
        className={
          notice === null
            ? "sr-only"
            : notice.tone === "error"
              ? "rounded-md border border-plum/30 bg-paper px-3 py-2 text-sm font-medium text-plum"
              : "rounded-md border border-verified/30 bg-mist px-3 py-2 text-sm font-medium text-ink"
        }
      >
        {notice?.text ?? ""}
      </p>

      {cashHold ? (
        <form
          onSubmit={(event) => void approve(event)}
          aria-labelledby="cash-hold-heading"
          className="rounded-md border border-caution/20 bg-gold-soft px-3 py-2.5 text-sm text-caution"
        >
          <p id="cash-hold-heading" className="flex items-start gap-2">
            <span className="mt-0.5 shrink-0">
              <AlertIcon />
            </span>
            <span>
              Paid in cash, so the owner approves it with a reason before it counts. If it was
              really paid on credit, change &ldquo;Paid by&rdquo; below instead.
            </span>
          </p>
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <label className="flex min-w-0 basis-full flex-col gap-1 text-xs font-medium text-ink sm:flex-1 sm:basis-auto">
              Reason for approving
              <input
                type="text"
                name="reason"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                disabled={busy}
                placeholder="Why this cash purchase is fine"
                className="w-full rounded-sm border border-ink/20 bg-paper px-2 py-1.5 text-sm text-ink"
              />
            </label>
            <button
              type="submit"
              disabled={busy || reason.trim() === ""}
              className="min-h-11 rounded-sm bg-palm px-4 py-2 text-sm font-semibold text-white hover:bg-palm-deep disabled:opacity-60"
            >
              {approving ? "Approving" : "Approve cash invoice"}
            </button>
            {heldDuplicate ? (
              <button
                type="button"
                onClick={() => void dismiss()}
                disabled={busy}
                className="min-h-11 rounded-sm border-2 border-palm bg-paper px-4 py-2 text-sm font-semibold text-palm hover:bg-mist disabled:opacity-60"
              >
                {dismissing ? "Dismissing" : "Dismiss this copy"}
              </button>
            ) : null}
          </div>
        </form>
      ) : null}

      {/* The sentence the sender already read on WhatsApp, minus its last
          clause - "confirm it on the review screen" is nonsense on the review
          screen. Same words otherwise, so the phone and the screen agree. */}
      {isCopy && invoice.duplicate_of ? (
        <div className="flex items-start gap-2 rounded-md border border-caution/20 bg-gold-soft px-3 py-2.5 text-sm text-caution">
          {/* The icon holds the first line rather than wrapping above the text,
              which is what a bare flex item does once the sentence runs on. */}
          <span className="mt-0.5 shrink-0">
            <AlertIcon />
          </span>
          <p>
            This one is already recorded: {invoice.duplicate_of.supplier_name ?? "supplier unknown"}
            {invoice.duplicate_of.invoice_no ? ` ${invoice.duplicate_of.invoice_no}` : ""}
            {invoice.duplicate_of.total === null
              ? ""
              : ` for ${invoice.duplicate_of.currency} ${money(invoice.duplicate_of.total)}`}
            , received {formatDate(invoice.duplicate_of.created_at)}.{" "}
            {dismissed
              ? "You dismissed this copy, so nothing was counted twice."
              : "I've held this copy so nothing is counted twice."}{" "}
            <Link
              href={`/invoices/${invoice.duplicate_of.id}`}
              className="font-semibold text-caution underline underline-offset-2"
            >
              See the original
            </Link>
          </p>
        </div>
      ) : null}

      <div className="grid grid-cols-[minmax(0,1fr)] gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
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
              {editable ? (
                <div>
                  <dt className="text-[11px] font-medium tracking-wider text-stone uppercase">
                    <label htmlFor="paid-by">Paid by</label>
                  </dt>
                  <dd className="mt-0.5">
                    <select
                      id="paid-by"
                      value={invoice.payment_kind ?? ""}
                      disabled={busy}
                      onChange={(event) => {
                        const kind = event.target.value;
                        if (kind === "cash" || kind === "credit") void setPaymentKind(kind);
                      }}
                      className="w-full max-w-[9rem] rounded-sm border border-ink/20 bg-paper px-2 py-1 text-sm font-medium text-ink"
                    >
                      {invoice.payment_kind === null ? (
                        <option value="" disabled>
                          Not read
                        </option>
                      ) : null}
                      {PAYMENT_KINDS.map((kind) => (
                        <option key={kind} value={kind}>
                          {PAYMENT_LABEL[kind]}
                        </option>
                      ))}
                    </select>
                  </dd>
                </div>
              ) : (
                <HeaderField
                  label="Paid by"
                  value={invoice.payment_kind ? PAYMENT_LABEL[invoice.payment_kind] : null}
                />
              )}
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
