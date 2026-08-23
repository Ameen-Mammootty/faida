"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { createManualInvoice, listInvoices } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { branchOptions, type FilterOption } from "@/lib/options";
import type { ManualInvoiceInput, ManualLineInput, PaymentKind } from "@/lib/types";

/**
 * WP-34's typed path: the vision-outage fallback. The form mirrors the
 * POST /api/invoices/manual body - header fields plus line rows - and the
 * server runs the same deterministic checks extraction runs, so the review
 * screen the user lands on shows honest green/amber with no AI involved.
 *
 * Validation here matches the API's rules exactly (unsigned decimal strings,
 * non-empty item names) so nothing valid is blocked and nothing invalid
 * round-trips just to fail.
 */

const NUMBER_RE = /^\d+(\.\d+)?$/;
const NUMBER_HINT = "Enter plain numbers, like 12 or 4.50.";

interface LineDraft {
  key: number;
  raw_name: string;
  qty: string;
  unit: string;
  pack_size: string;
  unit_price: string;
  line_total: string;
}

let nextKey = 0;

function emptyLine(): LineDraft {
  nextKey += 1;
  return { key: nextKey, raw_name: "", qty: "", unit: "", pack_size: "", unit_price: "", line_total: "" };
}

function isBlank(line: LineDraft): boolean {
  return (
    !line.raw_name.trim() &&
    !line.qty.trim() &&
    !line.unit.trim() &&
    !line.pack_size.trim() &&
    !line.unit_price.trim() &&
    !line.line_total.trim()
  );
}

/** One kept row -> the API line shape, or the reason it can't be sent. */
function toLineInput(line: LineDraft): ManualLineInput | { error: string } {
  if (!line.raw_name.trim()) {
    return { error: "Give this line the item name from the invoice." };
  }
  const input: ManualLineInput = { raw_name: line.raw_name.trim() };
  for (const field of ["qty", "unit_price", "line_total"] as const) {
    const value = line[field].trim();
    if (!value) continue;
    if (!NUMBER_RE.test(value)) return { error: NUMBER_HINT };
    input[field] = value;
  }
  if (line.unit.trim()) input.unit = line.unit.trim();
  if (line.pack_size.trim()) input.pack_size = line.pack_size.trim();
  return input;
}

const inputClasses =
  "rounded-sm border border-ink/20 bg-paper px-2 py-1.5 text-sm text-ink hover:border-palm/50";

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs font-medium text-ink">
      {label}
      {children}
    </label>
  );
}

export default function ManualEntryForm() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [branches, setBranches] = useState<FilterOption[]>([]);
  const [branchId, setBranchId] = useState(searchParams.get("branch_id") ?? "");
  const [supplierName, setSupplierName] = useState("");
  const [invoiceNo, setInvoiceNo] = useState("");
  const [invoiceDate, setInvoiceDate] = useState("");
  const [currency, setCurrency] = useState("AED");
  const [paymentKind, setPaymentKind] = useState<"" | PaymentKind>("");
  const [subtotal, setSubtotal] = useState("");
  const [tax, setTax] = useState("");
  const [total, setTotal] = useState("");
  const [lines, setLines] = useState<LineDraft[]>(() => [emptyLine(), emptyLine(), emptyLine()]);
  const [lineErrors, setLineErrors] = useState<Record<number, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const invoices = await listInvoices();
        if (!cancelled) setBranches(branchOptions(invoices));
      } catch {
        // No options; branch stays optional.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  function setLine(key: number, patch: Partial<LineDraft>) {
    setLines((current) =>
      current.map((line) => (line.key === key ? { ...line, ...patch } : line)),
    );
  }

  function removeLine(key: number) {
    setLines((current) =>
      current.length > 1 ? current.filter((line) => line.key !== key) : current,
    );
  }

  async function submit() {
    const kept = lines.filter((line) => !isBlank(line));
    if (kept.length === 0) {
      setLineErrors({});
      setFormError("Add at least one line - the items are what profit is computed from.");
      return;
    }

    const errors: Record<number, string> = {};
    const lineInputs: ManualLineInput[] = [];
    for (const line of kept) {
      const input = toLineInput(line);
      if ("error" in input) errors[line.key] = input.error;
      else lineInputs.push(input);
    }

    for (const [name, value] of [
      ["subtotal", subtotal],
      ["tax", tax],
      ["total", total],
    ] as const) {
      if (value.trim() && !NUMBER_RE.test(value.trim())) {
        errors[-1] = `${NUMBER_HINT} (${name})`;
      }
    }

    setLineErrors(errors);
    if (Object.keys(errors).length > 0) {
      setFormError(errors[-1] ?? "Fix the marked lines, then create the invoice.");
      return;
    }

    const body: ManualInvoiceInput = { lines: lineInputs };
    if (branchId) body.branch_id = branchId;
    if (supplierName.trim()) body.supplier_name = supplierName.trim();
    if (invoiceNo.trim()) body.invoice_no = invoiceNo.trim();
    if (invoiceDate) body.invoice_date = invoiceDate;
    if (currency.trim()) body.currency = currency.trim();
    if (paymentKind) body.payment_kind = paymentKind;
    if (subtotal.trim()) body.subtotal = subtotal.trim();
    if (tax.trim()) body.tax = tax.trim();
    if (total.trim()) body.total = total.trim();

    setSaving(true);
    setFormError(null);
    try {
      const detail = await createManualInvoice(body);
      router.push(`/invoices/${detail.id}`);
    } catch (err) {
      setSaving(false);
      setFormError(
        err instanceof ApiError ? err.message : "Couldn't create the invoice. Try again.",
      );
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <nav>
        <Link href="/invoices" className="text-sm font-medium text-palm hover:text-palm-deep">
          &larr; All invoices
        </Link>
      </nav>

      <header>
        <h1 className="font-display text-2xl font-semibold tracking-[-0.02em] text-ink">
          Enter an invoice
        </h1>
        <p className="mt-1 text-sm text-stone">
          Type it straight from the paper. The numbers get the same checks as a photo - anything
          that doesn&apos;t add up shows for review before it counts. Have a photo?{" "}
          <Link href="/invoices/new" className="font-medium text-palm hover:text-palm-deep">
            Upload it instead
          </Link>
          .
        </p>
      </header>

      <form
        className="space-y-5"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <section className="rounded-md border border-ink/10 bg-paper p-4 sm:p-5">
          <h2 className="text-[11px] font-medium tracking-wider text-stone uppercase">
            Invoice details
          </h2>
          <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
            <Field label="Supplier">
              <input
                type="text"
                value={supplierName}
                onChange={(event) => setSupplierName(event.target.value)}
                placeholder="Al Madina Foodstuff Trading"
                className={inputClasses}
              />
            </Field>
            <Field label="Invoice no">
              <input
                type="text"
                value={invoiceNo}
                onChange={(event) => setInvoiceNo(event.target.value)}
                className={inputClasses}
              />
            </Field>
            <Field label="Date">
              <input
                type="date"
                value={invoiceDate}
                onChange={(event) => setInvoiceDate(event.target.value)}
                className={inputClasses}
              />
            </Field>
            {branches.length > 0 ? (
              <Field label="Branch">
                <select
                  value={branchId}
                  onChange={(event) => setBranchId(event.target.value)}
                  className={inputClasses}
                >
                  <option value="">Not set</option>
                  {branches.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.name}
                    </option>
                  ))}
                </select>
              </Field>
            ) : null}
            <Field label="Payment">
              <select
                value={paymentKind}
                onChange={(event) => setPaymentKind(event.target.value as "" | PaymentKind)}
                className={inputClasses}
              >
                <option value="">Not set</option>
                <option value="credit">Credit</option>
                <option value="cash">Cash</option>
              </select>
            </Field>
            <Field label="Currency">
              <input
                type="text"
                value={currency}
                onChange={(event) => setCurrency(event.target.value)}
                className={`${inputClasses} w-20 tabular-nums`}
              />
            </Field>
          </div>
          {paymentKind === "cash" ? (
            <p className="mt-3 text-xs text-caution">
              Cash invoices wait for the owner&apos;s approval before they count.
            </p>
          ) : null}
        </section>

        <section className="rounded-md border border-ink/10 bg-paper p-4 sm:p-5">
          <h2 className="text-[11px] font-medium tracking-wider text-stone uppercase">Lines</h2>
          <div className="mt-3 space-y-3">
            {lines.map((line, index) => (
              <div key={line.key} className="border-b border-ink/5 pb-3 last:border-0 last:pb-0">
                <div className="flex flex-wrap items-end gap-x-3 gap-y-2">
                  <Field label={`Item ${index + 1}`}>
                    <input
                      type="text"
                      value={line.raw_name}
                      onChange={(event) => setLine(line.key, { raw_name: event.target.value })}
                      placeholder="Karak Tea Dust 5kg"
                      className={`${inputClasses} w-56`}
                    />
                  </Field>
                  <Field label="Qty">
                    <input
                      type="text"
                      inputMode="decimal"
                      value={line.qty}
                      onChange={(event) => setLine(line.key, { qty: event.target.value })}
                      className={`${inputClasses} w-16 tabular-nums`}
                    />
                  </Field>
                  <Field label="Unit">
                    <input
                      type="text"
                      value={line.unit}
                      onChange={(event) => setLine(line.key, { unit: event.target.value })}
                      placeholder="bag"
                      className={`${inputClasses} w-20`}
                    />
                  </Field>
                  <Field label="Pack size">
                    <input
                      type="text"
                      value={line.pack_size}
                      onChange={(event) => setLine(line.key, { pack_size: event.target.value })}
                      placeholder="5kg"
                      className={`${inputClasses} w-20`}
                    />
                  </Field>
                  <Field label="Unit price">
                    <input
                      type="text"
                      inputMode="decimal"
                      value={line.unit_price}
                      onChange={(event) => setLine(line.key, { unit_price: event.target.value })}
                      className={`${inputClasses} w-24 tabular-nums`}
                    />
                  </Field>
                  <Field label="Line total">
                    <input
                      type="text"
                      inputMode="decimal"
                      value={line.line_total}
                      onChange={(event) => setLine(line.key, { line_total: event.target.value })}
                      className={`${inputClasses} w-24 tabular-nums`}
                    />
                  </Field>
                  {lines.length > 1 ? (
                    <button
                      type="button"
                      onClick={() => removeLine(line.key)}
                      aria-label={`Remove line ${index + 1}`}
                      className="mb-0.5 px-2 py-1.5 text-sm font-medium text-stone hover:text-plum"
                    >
                      Remove
                    </button>
                  ) : null}
                </div>
                {lineErrors[line.key] ? (
                  <p className="mt-1.5 text-xs font-medium text-plum">{lineErrors[line.key]}</p>
                ) : null}
              </div>
            ))}
          </div>
          <button
            type="button"
            onClick={() => setLines((current) => [...current, emptyLine()])}
            className="mt-3 rounded-sm border border-palm/30 px-3 py-1.5 text-sm font-medium text-palm hover:border-palm hover:bg-mist"
          >
            Add line
          </button>
        </section>

        <section className="rounded-md border border-ink/10 bg-paper p-4 sm:p-5">
          <h2 className="text-[11px] font-medium tracking-wider text-stone uppercase">Totals</h2>
          <p className="mt-1 text-xs text-stone">
            Copy these from the invoice; they are checked against the lines, not computed from
            them.
          </p>
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-3">
            <Field label="Subtotal">
              <input
                type="text"
                inputMode="decimal"
                value={subtotal}
                onChange={(event) => setSubtotal(event.target.value)}
                className={`${inputClasses} w-28 tabular-nums`}
              />
            </Field>
            <Field label="VAT">
              <input
                type="text"
                inputMode="decimal"
                value={tax}
                onChange={(event) => setTax(event.target.value)}
                className={`${inputClasses} w-28 tabular-nums`}
              />
            </Field>
            <Field label="Total">
              <input
                type="text"
                inputMode="decimal"
                value={total}
                onChange={(event) => setTotal(event.target.value)}
                className={`${inputClasses} w-28 tabular-nums`}
              />
            </Field>
          </div>
        </section>

        {formError ? <p className="text-sm font-medium text-plum">{formError}</p> : null}

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={saving}
            className="rounded-sm bg-palm px-4 py-2 text-sm font-semibold text-white hover:bg-palm-deep disabled:opacity-60"
          >
            {saving ? "Creating" : "Create invoice"}
          </button>
          <Link href="/invoices" className="px-2 py-2 text-sm font-medium text-stone hover:text-ink">
            Cancel
          </Link>
        </div>
      </form>
    </div>
  );
}
