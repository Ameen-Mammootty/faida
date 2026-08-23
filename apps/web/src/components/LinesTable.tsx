"use client";

import { useState } from "react";
import { ApiError } from "@/lib/errors";
import { money, quantity } from "@/lib/format";
import type { InvoiceLine, LineFieldPatch } from "@/lib/types";
import FieldBadge from "./FieldBadge";

interface Props {
  lines: InvoiceLine[];
  editable: boolean;
  onSaveLine: (patch: LineFieldPatch) => Promise<void>;
}

interface Draft {
  qty: string;
  unit_price: string;
  line_total: string;
}

const NUMBER_RE = /^\d+(\.\d+)?$/;

/** Why this line needs review, in the reader's language - from the persisted check. */
function amberReason(line: InvoiceLine): string {
  const { checks } = line;
  if (
    checks.arith === "failed" &&
    line.qty !== null &&
    line.unit_price !== null &&
    checks.expected !== null &&
    checks.extracted !== null
  ) {
    return `Doesn't add up: ${quantity(line.qty)} × ${money(line.unit_price)} = ${money(
      checks.expected,
    )}, but the line says ${money(checks.extracted)}.`;
  }
  if (line.qty === null) return "Couldn't read the quantity on the photo.";
  if (line.unit_price === null) return "Couldn't read the unit price on the photo.";
  if (line.line_total === null) return "Couldn't read the line total on the photo.";
  if (checks.snapped === false) return "Doesn't match this supplier's usual items.";
  return "Check this line against the photo.";
}

function NotRead() {
  return <span className="text-xs font-medium text-caution">Not read</span>;
}

export default function LinesTable({ lines, editable, onSaveLine }: Props) {
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState<Draft>({ qty: "", unit_price: "", line_total: "" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function startEdit(line: InvoiceLine) {
    setEditing(line.position);
    setDraft({
      qty: line.qty ?? "",
      unit_price: line.unit_price ?? "",
      line_total: line.line_total ?? "",
    });
    setError(null);
  }

  function cancelEdit() {
    setEditing(null);
    setError(null);
  }

  async function save(position: number) {
    const fields = [draft.qty, draft.unit_price, draft.line_total].map((value) => value.trim());
    if (fields.some((value) => value !== "" && !NUMBER_RE.test(value))) {
      setError("Enter plain numbers, like 12 or 4.50.");
      return;
    }
    const [qty, unitPrice, lineTotal] = fields;
    const patch: LineFieldPatch = {
      position,
      qty: qty === "" ? null : qty,
      unit_price: unitPrice === "" ? null : unitPrice,
      line_total: lineTotal === "" ? null : lineTotal,
    };
    setSaving(true);
    setError(null);
    try {
      await onSaveLine(patch);
      setEditing(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save the change. Try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-ink/10 text-left text-[11px] font-medium tracking-wider text-stone uppercase">
            <th scope="col" className="py-2 pr-3 font-medium">
              Line
            </th>
            <th scope="col" className="py-2 pr-3 font-medium">
              Item
            </th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">
              Qty
            </th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">
              Unit price
            </th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">
              Line total
            </th>
            <th scope="col" className="py-2 font-medium">
              <span className="sr-only">Check result</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {lines.map((line) => {
            const amber = line.checks.status === "amber";
            const isEditing = editing === line.position;
            return (
              <LineRows
                key={line.id}
                line={line}
                amber={amber}
                editable={editable}
                isEditing={isEditing}
                draft={draft}
                saving={saving}
                error={error}
                onDraftChange={setDraft}
                onStartEdit={() => startEdit(line)}
                onCancel={cancelEdit}
                onSave={() => save(line.position)}
              />
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function LineRows({
  line,
  amber,
  editable,
  isEditing,
  draft,
  saving,
  error,
  onDraftChange,
  onStartEdit,
  onCancel,
  onSave,
}: {
  line: InvoiceLine;
  amber: boolean;
  editable: boolean;
  isEditing: boolean;
  draft: Draft;
  saving: boolean;
  error: string | null;
  onDraftChange: (draft: Draft) => void;
  onStartEdit: () => void;
  onCancel: () => void;
  onSave: () => void;
}) {
  const n = line.position + 1;
  return (
    <>
      <tr className={`border-b text-ink ${amber ? "border-caution/15 bg-gold-soft/50" : "border-ink/5"}`}>
        <td className="py-2.5 pr-3 text-stone tabular-nums">{n}</td>
        <td className="py-2.5 pr-3">
          {line.raw_name}
          {line.unit ? <span className="ml-1.5 text-xs text-stone">per {line.unit}</span> : null}
        </td>
        <td className="py-2.5 pr-3 text-right tabular-nums">
          {line.qty === null ? <NotRead /> : quantity(line.qty)}
        </td>
        <td className="py-2.5 pr-3 text-right tabular-nums">
          {line.unit_price === null ? <NotRead /> : money(line.unit_price)}
        </td>
        <td className="py-2.5 pr-3 text-right font-medium tabular-nums">
          {line.line_total === null ? <NotRead /> : money(line.line_total)}
        </td>
        <td className="py-2.5 text-right">
          <span className="inline-flex items-center gap-2">
            <FieldBadge status={line.checks.status} />
            {amber && editable && !isEditing ? (
              <button
                type="button"
                onClick={onStartEdit}
                aria-label={`Fix line ${n}`}
                className="rounded-sm border border-palm/30 px-2 py-0.5 text-xs font-medium text-palm hover:border-palm hover:bg-mist"
              >
                Fix
              </button>
            ) : null}
          </span>
        </td>
      </tr>
      {amber ? (
        <tr className="border-b border-caution/15 bg-gold-soft/50">
          <td />
          <td colSpan={5} className="pb-2.5 pr-3">
            <p className="text-xs text-caution">{amberReason(line)}</p>
            {isEditing ? (
              <form
                className="mt-2 flex flex-wrap items-end gap-3"
                onSubmit={(event) => {
                  event.preventDefault();
                  onSave();
                }}
              >
                <label className="flex flex-col gap-1 text-xs font-medium text-ink">
                  Quantity
                  <input
                    type="text"
                    inputMode="decimal"
                    value={draft.qty}
                    onChange={(event) => onDraftChange({ ...draft, qty: event.target.value })}
                    className="w-24 rounded-sm border border-ink/20 bg-paper px-2 py-1.5 text-sm tabular-nums"
                    autoFocus
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs font-medium text-ink">
                  Unit price (AED)
                  <input
                    type="text"
                    inputMode="decimal"
                    value={draft.unit_price}
                    onChange={(event) =>
                      onDraftChange({ ...draft, unit_price: event.target.value })
                    }
                    className="w-28 rounded-sm border border-ink/20 bg-paper px-2 py-1.5 text-sm tabular-nums"
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs font-medium text-ink">
                  Line total (AED)
                  <input
                    type="text"
                    inputMode="decimal"
                    value={draft.line_total}
                    onChange={(event) =>
                      onDraftChange({ ...draft, line_total: event.target.value })
                    }
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
                    onClick={onCancel}
                    disabled={saving}
                    className="px-2 py-1.5 text-sm font-medium text-stone hover:text-ink"
                  >
                    Cancel
                  </button>
                </div>
                {error ? <p className="w-full text-xs font-medium text-plum">{error}</p> : null}
              </form>
            ) : null}
          </td>
        </tr>
      ) : null}
    </>
  );
}
