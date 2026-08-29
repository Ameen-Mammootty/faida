"use client";

import { useState } from "react";
import { ApiError } from "@/lib/errors";
import { describeFields, groupedMoney, money, quantity } from "@/lib/format";
import { blankToNone } from "@/lib/placeholders";
import type { Correction, InvoiceLine } from "@/lib/types";
import FieldBadge from "./FieldBadge";

interface Props {
  lines: InvoiceLine[];
  editable: boolean;
  onSaveLine: (corrections: Correction[]) => Promise<void>;
}

interface Draft {
  qty: string;
  unit_price: string;
  line_total: string;
  pack_size: string;
}

const NUMBER_RE = /^\d+(\.\d+)?$/;

const LINE_NUMBER_FIELDS = ["qty", "unit_price", "line_total"] as const;

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

/**
 * What a cost's quality means, in the reader's language (M5 WP-53).
 *
 * There is no green here and there never will be. The arithmetic checks each
 * price against the quantity and the line total, so the price is corroborated
 * - but nothing anywhere cross-checks the pack size the price is divided by.
 * A supplier printing 25kg that was read as 2.5kg passes every check we have,
 * so the best a cost can honestly claim is that the invoice's own numbers
 * support it.
 */
function costNote(line: InvoiceLine, amber: boolean): string | null {
  const cost = line.cost;
  if (!cost) return null;
  if (cost.blocked) {
    // A missing quantity or price is already spelled out by the amber line
    // above ("Couldn't read the quantity on the photo"), and saying it twice
    // in two colours teaches people that neither sentence is worth reading.
    // A pack-size problem has no such twin: nothing else on this screen
    // mentions the pack.
    const alreadySaid = cost.blocked === "missing_quantity" || cost.blocked === "missing_unit_price";
    return amber && alreadySaid ? null : cost.reason;
  }
  if (cost.pack_source === "override") {
    return `Estimated: divided by ${cost.pack}, which someone entered for this product. The invoice itself does not say.`;
  }
  if (cost.quality === "estimated" && cost.asserted.length > 0) {
    return `Estimated: this cost leans on ${describeFields(
      cost.asserted,
    )}, supplied by a person rather than read off the photo.`;
  }
  return null;
}

/** The Cost cell: the figure and how much to trust it, or why there is none. */
function CostCell({ line }: { line: InvoiceLine }) {
  if (line.line_kind === "charge") {
    return <span className="text-xs text-stone">Not stock</span>;
  }
  const cost = line.cost;
  if (!cost) return null;
  if (cost.blocked || cost.per_display_unit === null) {
    return <span className="text-xs font-medium text-plum">No cost</span>;
  }
  return (
    <>
      <span className="tabular-nums">
        {groupedMoney(cost.per_display_unit)}
        <span className="ml-1 text-xs text-stone">
          {cost.display_unit === "each" ? "each" : `/${cost.display_unit}`}
        </span>
      </span>
      {/* Only the exception is labelled. Every cost here carries the same
          limitation - nothing cross-checks a pack size - and the note under
          the table says so once; repeating it on every row would bury the one
          line that is genuinely weaker than its neighbours. */}
      {cost.quality === "estimated" ? (
        <span className="block text-[11px] text-caution">estimated</span>
      ) : null}
    </>
  );
}

/**
 * Map the edit form onto C6 corrections: one {line_index, field, value} per
 * changed field. A field left as it was sends nothing; a still-unread field
 * left empty stays unread; a read number cannot be cleared (the API has no
 * "unset" for numbers - only unsigned decimal values). Pack size is the one
 * exception: free text, and blanking it is a real answer - "the pack we hold
 * is wrong and I do not know the right one" - which the API stores as null.
 */
function buildCorrections(line: InvoiceLine, draft: Draft): Correction[] | { error: string } {
  const corrections: Correction[] = [];
  for (const field of LINE_NUMBER_FIELDS) {
    const value = draft[field].trim();
    const current = line[field];
    if (value === (current ?? "")) continue; // untouched
    if (value === "") {
      if (current === null) continue; // was unread, stays unread
      return { error: "A value can't be cleared. Enter the number the photo shows." };
    }
    if (!NUMBER_RE.test(value)) {
      return { error: "Enter plain numbers, like 12 or 4.50." };
    }
    corrections.push({ line_index: line.position, field, value });
  }
  // Compare packs through the server's own blank vocabulary, so retyping the
  // stored value, or clearing an already empty field, sends nothing and
  // stamps no false corrected_screen provenance.
  if (blankToNone(draft.pack_size) !== line.pack_size) {
    corrections.push({ line_index: line.position, field: "pack_size", value: draft.pack_size });
  }
  return corrections;
}

export default function LinesTable({ lines, editable, onSaveLine }: Props) {
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState<Draft>({
    qty: "",
    unit_price: "",
    line_total: "",
    pack_size: "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function startEdit(line: InvoiceLine) {
    setEditing(line.position);
    setDraft({
      qty: line.qty ?? "",
      unit_price: line.unit_price ?? "",
      line_total: line.line_total ?? "",
      pack_size: line.pack_size ?? "",
    });
    setError(null);
  }

  function cancelEdit() {
    setEditing(null);
    setError(null);
  }

  async function save(line: InvoiceLine) {
    const corrections = buildCorrections(line, draft);
    if ("error" in corrections) {
      setError(corrections.error);
      return;
    }
    if (corrections.length === 0) {
      setEditing(null); // nothing changed
      setError(null);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSaveLine(corrections);
      setEditing(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save the change. Try again.");
    } finally {
      setSaving(false);
    }
  }

  // The column appears the moment the invoice is confirmed, because that is
  // the moment the costs exist (WP-53). Before then it would be a column of
  // blanks promising something.
  const showCost = lines.some((line) => line.cost !== null);

  return (
    <div>
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
              {showCost ? (
                <th scope="col" className="py-2 pr-3 text-right font-medium">
                  What it costs
                </th>
              ) : null}
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
                  key={line.position}
                  line={line}
                  amber={amber}
                  editable={editable}
                  isEditing={isEditing}
                  showCost={showCost}
                  draft={draft}
                  saving={saving}
                  error={error}
                  onDraftChange={setDraft}
                  onStartEdit={() => startEdit(line)}
                  onCancel={cancelEdit}
                  onSave={() => save(line)}
                />
              );
            })}
          </tbody>
        </table>
      </div>
      {showCost ? (
        <p className="mt-3 max-w-2xl text-xs text-stone">
          Costs are worked out ex-VAT and after any discount, from the price and the pack size on
          this invoice. No purchase cost is ever marked verified: the arithmetic checks each price
          against the quantity and the line total, but nothing on an invoice cross-checks the pack
          size a cost is divided by.
        </p>
      ) : null}
    </div>
  );
}

function LineRows({
  line,
  amber,
  editable,
  isEditing,
  showCost,
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
  showCost: boolean;
  draft: Draft;
  saving: boolean;
  error: string | null;
  onDraftChange: (draft: Draft) => void;
  onStartEdit: () => void;
  onCancel: () => void;
  onSave: () => void;
}) {
  const n = line.position + 1;
  const note = costNote(line, amber);
  return (
    <>
      <tr className={`border-b text-ink ${amber ? "border-caution/15 bg-gold-soft/50" : "border-ink/5"}`}>
        <td className="py-2.5 pr-3 text-stone tabular-nums">{n}</td>
        <td className="py-2.5 pr-3">
          {line.raw_name}
          {/* The pack is the number a cost divides by, and nothing arithmetic
              cross-checks it - so it has to be on screen to be checkable
              against the photo at all. */}
          {line.pack_size ? (
            <span className="ml-1.5 text-xs text-stone">{line.pack_size}</span>
          ) : null}
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
        {showCost ? (
          <td className="py-2.5 pr-3 text-right">
            <CostCell line={line} />
          </td>
        ) : null}
        <td className="py-2.5 text-right">
          <span className="inline-flex items-center gap-2">
            <FieldBadge status={line.checks.status} />
            {/* The door opens on every line, not only amber ones. A wrong
                pack size never turns a line amber - no arithmetic checks it,
                C4 anchors on the line sum - so the misread that matters most
                sits on a green row, and a door that only opened on amber
                could never reach it. Amber keeps the louder "Fix"; a green
                row offers a quiet "Edit". */}
            {editable && !isEditing ? (
              <button
                type="button"
                onClick={onStartEdit}
                aria-label={`${amber ? "Fix" : "Edit"} line ${n}`}
                className={
                  amber
                    ? "rounded-sm border border-palm/30 px-2 py-0.5 text-xs font-medium text-palm hover:border-palm hover:bg-mist"
                    : "rounded-sm border border-ink/10 px-2 py-0.5 text-xs font-medium text-stone hover:border-ink/30 hover:text-ink"
                }
              >
                {amber ? "Fix" : "Edit"}
              </button>
            ) : null}
          </span>
        </td>
      </tr>
      {amber || note || isEditing ? (
        <tr
          className={`border-b ${
            amber ? "border-caution/15 bg-gold-soft/50" : "border-ink/5"
          }`}
        >
          <td />
          <td colSpan={showCost ? 6 : 5} className="pb-2.5 pr-3">
            {amber ? <p className="text-xs text-caution">{amberReason(line)}</p> : null}
            {/* Why this line has no cost, or what its cost leans on. A cost
                nobody can question is the failure this layer exists to
                avoid, so the sentence sits under the number itself. */}
            {note ? (
              <p className={`text-xs ${amber ? "mt-1 text-caution" : "text-stone"}`}>{note}</p>
            ) : null}
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
                <label className="flex flex-col gap-1 text-xs font-medium text-ink">
                  Pack size
                  <input
                    type="text"
                    value={draft.pack_size}
                    onChange={(event) =>
                      onDraftChange({ ...draft, pack_size: event.target.value })
                    }
                    placeholder="e.g. 5kg"
                    className="w-28 rounded-sm border border-ink/20 bg-paper px-2 py-1.5 text-sm"
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
                <p className="w-full text-xs text-stone">
                  Pack size is what the paper prints, like 5kg or 6 x 400ml. If the photo
                  doesn&apos;t show one, leave it blank - that clears a wrong reading.
                </p>
              </form>
            ) : null}
          </td>
        </tr>
      ) : null}
    </>
  );
}
