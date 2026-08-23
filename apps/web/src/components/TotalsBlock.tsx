"use client";

import { useState } from "react";
import { ApiError } from "@/lib/errors";
import { money } from "@/lib/format";
import type { DocumentCheck, FieldPatch } from "@/lib/types";
import FieldBadge from "./FieldBadge";

interface Props {
  subtotal: string | null;
  tax: string | null;
  total: string | null;
  currency: string;
  doc: DocumentCheck;
  editable: boolean;
  onSaveTotals: (patch: FieldPatch) => Promise<void>;
}

const NUMBER_RE = /^\d+(\.\d+)?$/;

/**
 * The reconciliation strip: the exact arithmetic the pipeline ran, laid out
 * as the equation it checked - line sum plus VAT against the printed total.
 * This is where the screen earns trust, so the numbers speak first and the
 * verdict (icon plus label, never colour alone) sits beside them.
 */
export default function TotalsBlock({
  subtotal,
  tax,
  total,
  currency,
  doc,
  editable,
  onSaveTotals,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({ subtotal: "", tax: "", total: "" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const green = doc.status === "green";
  const taintedByLines =
    doc.status === "amber" && doc.arith === "passed" && doc.subtotal_check !== "failed";
  const fixable =
    editable &&
    (doc.arith === "failed" || doc.subtotal_check === "failed" || total === null);

  function message(): string {
    if (green && tax === null) {
      return "No VAT line on the invoice, so it counts as 0.00. The lines match the printed total.";
    }
    if (green) return "Lines plus VAT match the printed total.";
    if (doc.arith === "failed" && doc.expected !== null && doc.extracted !== null) {
      return `Lines plus VAT come to ${money(doc.expected)}, but the invoice says ${money(
        doc.extracted,
      )}. Check the photo to see which is right.`;
    }
    if (doc.subtotal_check === "failed" && doc.line_sum !== null && subtotal !== null) {
      return `The printed subtotal says ${money(subtotal)}, but the lines add up to ${money(
        doc.line_sum,
      )}.`;
    }
    if (total === null) return "Couldn't read the printed total on the photo.";
    if (doc.line_sum === null) {
      return "Some line totals couldn't be read, so the sum can't be checked yet.";
    }
    if (taintedByLines) return "The sums agree, but a line above needs review first.";
    return "These totals need a check against the photo.";
  }

  function startEdit() {
    setDraft({ subtotal: subtotal ?? "", tax: tax ?? "", total: total ?? "" });
    setEditing(true);
    setError(null);
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    const values = [draft.subtotal, draft.tax, draft.total].map((value) => value.trim());
    if (values.some((value) => value !== "" && !NUMBER_RE.test(value))) {
      setError("Enter plain numbers, like 283.76.");
      return;
    }
    const [nextSubtotal, nextTax, nextTotal] = values;
    setSaving(true);
    setError(null);
    try {
      await onSaveTotals({
        subtotal: nextSubtotal === "" ? null : nextSubtotal,
        tax: nextTax === "" ? null : nextTax,
        total: nextTotal === "" ? null : nextTotal,
      });
      setEditing(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save the change. Try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section
      aria-labelledby="totals-heading"
      className={`rounded-md border p-4 ${
        green ? "border-ink/10 bg-mist/40" : "border-caution/20 bg-gold-soft/60"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <h3 id="totals-heading" className="text-sm font-semibold text-ink">
          Totals
        </h3>
        <FieldBadge status={doc.status} label={green ? "Adds up" : "Needs review"} />
      </div>
      <dl className="mt-3 space-y-1.5 text-sm">
        <div className="flex items-baseline justify-between gap-4">
          <dt className="text-stone">Lines ({currency})</dt>
          <dd className="font-medium tabular-nums">
            {doc.line_sum === null ? (
              <span className="text-xs font-medium text-caution">Not known</span>
            ) : (
              money(doc.line_sum)
            )}
          </dd>
        </div>
        <div className="flex items-baseline justify-between gap-4">
          <dt className="text-stone">VAT ({currency})</dt>
          <dd className="font-medium tabular-nums">
            {tax === null ? <span className="text-stone">0.00</span> : money(tax)}
          </dd>
        </div>
        {doc.subtotal_check === "failed" && subtotal !== null ? (
          <div className="flex items-baseline justify-between gap-4">
            <dt className="text-stone">Printed subtotal ({currency})</dt>
            <dd className="font-medium text-caution tabular-nums">{money(subtotal)}</dd>
          </div>
        ) : null}
        <div className="flex items-baseline justify-between gap-4 border-t border-ink/10 pt-2">
          <dt className="font-medium text-ink">Printed total ({currency})</dt>
          <dd className="text-base font-semibold tabular-nums">
            {total === null ? (
              <span className="text-xs font-medium text-caution">Not read</span>
            ) : (
              money(total)
            )}
          </dd>
        </div>
      </dl>
      <p className={`mt-3 text-xs ${green ? "text-stone" : "text-caution"}`}>{message()}</p>
      {fixable && !editing ? (
        <button
          type="button"
          onClick={startEdit}
          className="mt-3 rounded-sm border border-palm/30 px-2.5 py-1 text-xs font-medium text-palm hover:border-palm hover:bg-paper"
        >
          Fix totals
        </button>
      ) : null}
      {editing ? (
        <form className="mt-3 flex flex-wrap items-end gap-3" onSubmit={save}>
          <label className="flex flex-col gap-1 text-xs font-medium text-ink">
            Subtotal ({currency})
            <input
              type="text"
              inputMode="decimal"
              value={draft.subtotal}
              onChange={(event) => setDraft({ ...draft, subtotal: event.target.value })}
              className="w-28 rounded-sm border border-ink/20 bg-paper px-2 py-1.5 text-sm tabular-nums"
              autoFocus
            />
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium text-ink">
            VAT ({currency})
            <input
              type="text"
              inputMode="decimal"
              value={draft.tax}
              onChange={(event) => setDraft({ ...draft, tax: event.target.value })}
              className="w-24 rounded-sm border border-ink/20 bg-paper px-2 py-1.5 text-sm tabular-nums"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium text-ink">
            Total ({currency})
            <input
              type="text"
              inputMode="decimal"
              value={draft.total}
              onChange={(event) => setDraft({ ...draft, total: event.target.value })}
              className="w-28 rounded-sm border border-ink/20 bg-paper px-2 py-1.5 text-sm tabular-nums"
            />
          </label>
          <div className="flex items-center gap-2">
            <button
              type="submit"
              disabled={saving}
              className="rounded-sm bg-palm px-3 py-1.5 text-sm font-medium text-white hover:bg-palm-deep disabled:opacity-60"
            >
              {saving ? "Saving" : "Save"}
            </button>
            <button
              type="button"
              onClick={() => setEditing(false)}
              disabled={saving}
              className="px-2 py-1.5 text-sm font-medium text-stone hover:text-ink"
            >
              Cancel
            </button>
          </div>
          {error ? <p className="w-full text-xs font-medium text-plum">{error}</p> : null}
        </form>
      ) : null}
    </section>
  );
}
