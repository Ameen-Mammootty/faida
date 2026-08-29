"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  listBlockedCosts,
  listIngredients,
  listUnmappedSupplierItems,
  mapSupplierItem,
  rejectIngredient,
  setPackSizeOverride,
  unmapSupplierItem,
} from "@/lib/api";
import { describeFields, formatDate, groupedMoney } from "@/lib/format";
import type {
  BaseUnit,
  BlockedCost,
  Ingredient,
  IngredientMappingInput,
  MaterialPrice,
  UnmappedSupplierItem,
} from "@/lib/types";

/**
 * M5 WP-52: one shelf per ingredient.
 *
 * Two sections, one page. The queue is packs the invoices have taught us about
 * that nobody has said what they *are* yet, most money first - because that is
 * the order in which a wrong cost hurts. Below it, the materials themselves.
 *
 * The propose-then-confirm shape is the review screen's, deliberately: the
 * matcher ranks candidates and a person decides, one keystroke at a time.
 * Nothing merges on its own at any score. A wrong merge corrupts the cost of
 * every menu item using that material, and unlike a bad extraction there is no
 * photo to check it against - which is also why every mapped pack keeps an
 * "Unmap" beside it.
 */

const BASE_UNIT_LABEL: Record<BaseUnit, string> = {
  g: "by weight",
  ml: "by volume",
  pc: "by the piece",
};

const BASE_UNIT_PER: Record<BaseUnit, string> = { g: "per kg", ml: "per litre", pc: "each" };

/** "AED 23.50 per kg", "AED 4.69 per litre", "AED 0.35 each". */
function pricePerUnit(price: MaterialPrice): string {
  const figure = `AED ${groupedMoney(price.per_display_unit ?? "0")}`;
  return price.display_unit === "each" ? `${figure} each` : `${figure} per ${price.display_unit}`;
}

/**
 * Where a material's price came from, in one sentence (M5 WP-54).
 *
 * The price is the newest purchase among the packs mapped to this material,
 * not an average and not the cheapest, so the sentence has to name the
 * purchase - otherwise a consultant looking at three suppliers cannot tell
 * which one moved it. "Bought on" and "recorded on" are kept apart: an invoice
 * that printed no date falls back to when it was confirmed, and that is a
 * weaker claim about when the money was actually spent.
 */
function priceSource(price: MaterialPrice): string {
  const when = price.invoice_date
    ? `bought ${formatDate(price.invoice_date)}`
    : price.purchased_on
      ? `recorded ${formatDate(price.purchased_on)}`
      : "date not read";
  return `${price.supplier_name} · ${when}`;
}

/**
 * What the price does not know, in the reader's language.
 *
 * Never "verified", and a reader is told why once per material rather than
 * being left to assume: the arithmetic corroborates the price on the invoice,
 * but nothing anywhere cross-checks the pack size it was divided by.
 */
function priceQuality(price: MaterialPrice): string {
  if (price.pack_source === "override") {
    return `Estimated: divided by ${price.pack}, which someone entered for this product.`;
  }
  if (price.quality === "estimated" && price.asserted.length > 0) {
    return `Estimated: leans on ${describeFields(price.asserted)}, supplied by a person.`;
  }
  return `From ${price.pack} on the invoice, which nothing cross-checks.`;
}

/**
 * A headline figure, rounded to whole dirhams (plan.md section 3: rounded
 * headline numbers, exact figures only in detail). String operations only -
 * money is never parsed to a number on this screen - so this truncates rather
 * than rounds, which can only ever understate a ranking figure by under a
 * dirham.
 */
function roundedAed(value: string): string {
  const whole = value.split(".")[0].replace("-", "");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `AED ${value.startsWith("-") ? "-" : ""}${grouped}`;
}

type Feedback = { kind: "error" | "done"; text: string } | null;

export default function RawMaterials() {
  const [queue, setQueue] = useState<UnmappedSupplierItem[] | null>(null);
  const [materials, setMaterials] = useState<Ingredient[] | null>(null);
  const [blocked, setBlocked] = useState<BlockedCost[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [naming, setNaming] = useState<string | null>(null);
  const [draftName, setDraftName] = useState("");
  const [draftUnit, setDraftUnit] = useState<BaseUnit>("g");
  const [answering, setAnswering] = useState<string | null>(null);
  const [draftPack, setDraftPack] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const nameInput = useRef<HTMLInputElement>(null);
  const packInput = useRef<HTMLInputElement>(null);

  // All three lists are fetched together and re-fetched as one, so the queue,
  // the blocked costs and the materials below them can never disagree on
  // screen about where a pack is or what it costs. The state lands in an async
  // callback rather than the effect body, which is the shipped InvoiceList
  // pattern and what React 19 wants.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [items, ingredients, blockedCosts] = await Promise.all([
          listUnmappedSupplierItems(),
          listIngredients(),
          listBlockedCosts(),
        ]);
        if (cancelled) return;
        setQueue(items);
        setMaterials(ingredients);
        setBlocked(blockedCosts);
        setLoadError(null);
      } catch (error) {
        if (cancelled) return;
        setLoadError(error instanceof Error ? error.message : "Could not load raw materials.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  useEffect(() => {
    if (naming !== null) nameInput.current?.focus();
  }, [naming]);

  useEffect(() => {
    if (answering !== null) packInput.current?.focus();
  }, [answering]);

  /** Every decision goes through here: one request, then a reload of both
   * lists. One door for approve, reject, remap and unmap alike. */
  async function decide(id: string, action: () => Promise<unknown>, done: string) {
    setBusyId(id);
    setFeedback(null);
    try {
      await action();
      setFeedback({ kind: "done", text: done });
      setNaming(null);
      setDraftName("");
      setAnswering(null);
      setDraftPack("");
      setReloadKey((key) => key + 1);
    } catch (error) {
      setFeedback({
        kind: "error",
        text: error instanceof Error ? error.message : "That did not work.",
      });
    } finally {
      setBusyId(null);
    }
  }

  function approve(item: UnmappedSupplierItem, body: IngredientMappingInput, label: string) {
    return decide(
      item.id,
      () => mapSupplierItem(item.id, body),
      `${item.canonical_name} is now ${label}.`,
    );
  }

  function onRowKey(event: React.KeyboardEvent<HTMLLIElement>, item: UnmappedSupplierItem) {
    if (event.target !== event.currentTarget) return; // typing in the name box
    const index = Number(event.key) - 1;
    if (index >= 0 && index < item.proposals.length) {
      event.preventDefault();
      const proposal = item.proposals[index];
      void approve(item, { ingredient_id: proposal.id }, proposal.name);
      return;
    }
    if (event.key.toLowerCase() === "r" && item.proposals.length > 0) {
      event.preventDefault();
      const proposal = item.proposals[0];
      void decide(
        item.id,
        () => rejectIngredient(item.id, proposal.id),
        `${item.canonical_name} is not ${proposal.name}.`,
      );
      return;
    }
    if (event.key.toLowerCase() === "n") {
      event.preventDefault();
      setNaming(item.id);
      setDraftUnit(item.base_unit ?? "g");
    }
  }

  if (loadError) {
    return (
      <div role="alert" className="rounded-md border border-ink/10 bg-paper p-6">
        <p className="text-sm font-medium text-ink">Could not load raw materials</p>
        <p className="mt-1 text-sm text-stone">{loadError}</p>
        <button
          type="button"
          onClick={() => setReloadKey((key) => key + 1)}
          className="mt-4 rounded-sm border border-palm/30 px-3 py-1.5 text-sm font-medium text-palm hover:border-palm"
        >
          Try again
        </button>
      </div>
    );
  }

  if (queue === null || materials === null || blocked === null) {
    return (
      <div aria-busy="true" className="rounded-md border border-ink/10 bg-paper p-6">
        <p role="status" className="text-sm text-stone">
          Loading raw materials
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <header>
        <h1 className="font-display text-2xl font-semibold tracking-[-0.02em] text-ink">
          Raw materials
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-stone">
          The same thing bought from two suppliers arrives as two products. Say which material each
          one is, once, and every invoice after that follows.
        </p>
      </header>

      {feedback ? (
        <p
          role="status"
          className={`rounded-sm border px-3 py-2 text-sm ${
            feedback.kind === "error"
              ? "border-clay/40 bg-clay/5 text-ink"
              : "border-palm/30 bg-mist text-ink"
          }`}
        >
          <span className="font-medium">{feedback.kind === "error" ? "Not done: " : "Done. "}</span>
          {feedback.text}
        </p>
      ) : null}

      <section className="space-y-3">
        <div className="flex items-baseline justify-between gap-4">
          <h2 className="font-display text-lg font-semibold text-ink">Needs a material</h2>
          <p className="text-sm text-stone">
            {queue.length === 0
              ? "Nothing waiting"
              : `${queue.length} ${queue.length === 1 ? "product" : "products"}, most money first`}
          </p>
        </div>

        {queue.length === 0 ? (
          <p className="rounded-md border border-ink/10 bg-paper px-4 py-6 text-sm text-stone">
            Every product on your invoices has been matched to a material.
          </p>
        ) : (
          <ul className="space-y-2">
            {queue.map((item) => {
              const busy = busyId === item.id;
              return (
                <li
                  key={item.id}
                  tabIndex={0}
                  onKeyDown={(event) => onRowKey(event, item)}
                  aria-label={`${item.canonical_name} from ${item.supplier_name}`}
                  className="rounded-md border border-ink/10 bg-paper p-4 focus:border-palm focus:outline-none focus-visible:ring-2 focus-visible:ring-palm/30"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-medium text-ink">{item.canonical_name}</p>
                      <p className="mt-0.5 text-sm text-stone">
                        {item.supplier_name}
                        {item.pack_size ? ` · ${item.pack_size}` : ""}
                        {item.base_unit ? ` · ${BASE_UNIT_LABEL[item.base_unit]}` : ""}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="font-display text-lg font-semibold text-ink">
                        {roundedAed(item.spend)}
                      </p>
                      <p className="text-xs text-stone">
                        on {item.line_count} confirmed {item.line_count === 1 ? "line" : "lines"}
                      </p>
                    </div>
                  </div>

                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    {item.proposals.map((proposal, index) => (
                      <button
                        key={proposal.id}
                        type="button"
                        disabled={busy}
                        onClick={() =>
                          void approve(item, { ingredient_id: proposal.id }, proposal.name)
                        }
                        className="rounded-sm bg-palm px-3 py-1.5 text-sm font-semibold text-white hover:bg-palm-deep disabled:opacity-50"
                      >
                        <span aria-hidden="true" className="mr-1.5 opacity-70">
                          {index + 1}
                        </span>
                        {proposal.name}
                      </button>
                    ))}
                    {item.proposals.length > 0 ? (
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() =>
                          void decide(
                            item.id,
                            () => rejectIngredient(item.id, item.proposals[0].id),
                            `${item.canonical_name} is not ${item.proposals[0].name}.`,
                          )
                        }
                        className="rounded-sm border border-ink/20 px-3 py-1.5 text-sm font-medium text-stone hover:border-clay hover:text-ink disabled:opacity-50"
                      >
                        <span aria-hidden="true" className="mr-1.5 opacity-70">
                          R
                        </span>
                        Not {item.proposals[0].name}
                      </button>
                    ) : null}
                    {naming === item.id ? null : (
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => {
                          setNaming(item.id);
                          setDraftUnit(item.base_unit ?? "g");
                        }}
                        className="rounded-sm border border-palm/30 px-3 py-1.5 text-sm font-medium text-palm hover:border-palm disabled:opacity-50"
                      >
                        <span aria-hidden="true" className="mr-1.5 opacity-70">
                          N
                        </span>
                        {item.proposals.length > 0 ? "Something else" : "Name the material"}
                      </button>
                    )}
                  </div>

                  {naming === item.id ? (
                    <form
                      className="mt-3 flex flex-wrap items-end gap-2 border-t border-ink/10 pt-3"
                      onSubmit={(event) => {
                        event.preventDefault();
                        const name = draftName.trim();
                        if (!name) return;
                        const body: IngredientMappingInput = { name };
                        if (item.base_unit === null) body.base_unit = draftUnit;
                        void approve(item, body, name);
                      }}
                    >
                      <label className="flex flex-col gap-1 text-sm font-medium text-stone">
                        What is it?
                        <input
                          ref={nameInput}
                          value={draftName}
                          onChange={(event) => setDraftName(event.target.value)}
                          placeholder="Milk powder"
                          className="w-56 rounded-sm border border-ink/20 bg-paper px-2 py-1.5 text-sm text-ink focus:border-palm focus:outline-none"
                        />
                      </label>
                      {/* Only asked when the pack cannot say: units.py refuses
                          to guess what is inside a carton, so a human says. */}
                      {item.base_unit === null ? (
                        <label className="flex flex-col gap-1 text-sm font-medium text-stone">
                          Measured
                          <select
                            value={draftUnit}
                            onChange={(event) => setDraftUnit(event.target.value as BaseUnit)}
                            className="rounded-sm border border-ink/20 bg-paper px-2 py-1.5 text-sm text-ink"
                          >
                            <option value="g">by weight</option>
                            <option value="ml">by volume</option>
                            <option value="pc">by the piece</option>
                          </select>
                        </label>
                      ) : null}
                      <button
                        type="submit"
                        disabled={busy || draftName.trim() === ""}
                        className="rounded-sm bg-palm px-3 py-1.5 text-sm font-semibold text-white hover:bg-palm-deep disabled:opacity-50"
                      >
                        Save
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setNaming(null);
                          setDraftName("");
                        }}
                        className="rounded-sm px-2 py-1.5 text-sm font-medium text-stone hover:text-ink"
                      >
                        Cancel
                      </button>
                    </form>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
        {queue.length > 0 ? (
          <p className="text-xs text-stone">
            With a row selected: press 1, 2 or 3 to choose a material, R if it is not the first
            suggestion, N to name a new one.
          </p>
        ) : null}
      </section>

      {/* M5 WP-55. A cost that cannot be computed is a line on a screen with
          its own reason, never a guessed number - and never a silence either,
          because a material with no price and no explanation looks like a bug
          in the product rather than a gap in the paperwork. Derived from the
          invoice lines; there is no issues table behind this. */}
      {blocked.length > 0 ? (
        <section className="space-y-3">
          <div className="flex items-baseline justify-between gap-4">
            <h2 className="font-display text-lg font-semibold text-ink">Can&apos;t be costed yet</h2>
            <p className="text-sm text-stone">
              {blocked.length} {blocked.length === 1 ? "product" : "products"}, most money first
            </p>
          </div>
          <ul className="space-y-2">
            {blocked.map((issue) => (
              <li key={issue.id} className="rounded-md border border-ink/10 bg-paper p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-medium text-ink">{issue.product_name}</p>
                    <p className="mt-0.5 text-sm text-stone">
                      {[issue.supplier_name, issue.pack_size, issue.ingredient_name]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                    <p className="mt-1 text-sm text-plum">{issue.reason}</p>
                  </div>
                  <div className="text-right">
                    <p className="font-display text-lg font-semibold text-ink">
                      {roundedAed(issue.spend)}
                    </p>
                    <p className="text-xs text-stone">
                      on {issue.line_count} confirmed {issue.line_count === 1 ? "line" : "lines"}
                    </p>
                    <Link
                      href={`/invoices/${issue.invoice_id}`}
                      className="text-xs font-medium text-palm underline-offset-2 hover:underline"
                    >
                      See the invoice
                    </Link>
                  </div>
                </div>

                {/* Only a pack problem has an answer a person can give. A price
                    or a quantity the invoice never printed is not something a
                    conversion supplies, and offering a box to type in there
                    would be a promise this screen cannot keep. */}
                {issue.can_override && issue.supplier_item_id ? (
                  answering === issue.id ? (
                    <form
                      className="mt-3 flex flex-wrap items-end gap-2 border-t border-ink/10 pt-3"
                      onSubmit={(event) => {
                        event.preventDefault();
                        const answer = draftPack.trim();
                        const itemId = issue.supplier_item_id;
                        if (!answer || !itemId) return;
                        void decide(
                          issue.id,
                          () => setPackSizeOverride(itemId, answer),
                          `One ${issue.product_name} holds ${answer}.`,
                        );
                      }}
                    >
                      <label className="flex flex-col gap-1 text-sm font-medium text-stone">
                        How much is in one?
                        <input
                          ref={packInput}
                          value={draftPack}
                          onChange={(event) => setDraftPack(event.target.value)}
                          placeholder="10 kg"
                          className="w-40 rounded-sm border border-ink/20 bg-paper px-2 py-1.5 text-sm text-ink focus:border-palm focus:outline-none"
                        />
                      </label>
                      <button
                        type="submit"
                        disabled={busyId === issue.id || draftPack.trim() === ""}
                        className="rounded-sm bg-palm px-3 py-1.5 text-sm font-semibold text-white hover:bg-palm-deep disabled:opacity-50"
                      >
                        Save
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setAnswering(null);
                          setDraftPack("");
                        }}
                        className="rounded-sm px-2 py-1.5 text-sm font-medium text-stone hover:text-ink"
                      >
                        Cancel
                      </button>
                      <p className="w-full text-xs text-stone">
                        Say it the way the invoice would: 10 kg, 750 ml, 24 x 400 ml. Every line of
                        this product that has no cost is worked out from it; ones already costed
                        stay as they are.
                      </p>
                    </form>
                  ) : (
                    <button
                      type="button"
                      disabled={busyId === issue.id}
                      onClick={() => {
                        setAnswering(issue.id);
                        setDraftPack(issue.pack_size_override ?? "");
                      }}
                      className="mt-3 rounded-sm border border-palm/30 px-3 py-1.5 text-sm font-medium text-palm hover:border-palm disabled:opacity-50"
                    >
                      Say how much is in one
                    </button>
                  )
                ) : null}
              </li>
            ))}
          </ul>
          <p className="max-w-2xl text-xs text-stone">
            These are confirmed purchases the arithmetic could not turn into a cost. Nothing here is
            guessed: a material has no price until every figure behind it comes from the invoice or
            from someone who said so.
          </p>
        </section>
      ) : null}

      <section className="space-y-3">
        <h2 className="font-display text-lg font-semibold text-ink">
          Materials{materials.length > 0 ? ` (${materials.length})` : ""}
        </h2>
        {materials.length === 0 ? (
          <p className="rounded-md border border-ink/10 bg-paper px-4 py-6 text-sm text-stone">
            Nothing yet. Match a product above and its material appears here.
          </p>
        ) : (
          <ul className="space-y-2">
            {materials.map((material) => (
              <li key={material.id} className="rounded-md border border-ink/10 bg-paper p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-medium text-ink">{material.name}</p>
                    {/* "priced per kg" only until there is a price: once the
                        figure above says "per kg", saying it again is noise. */}
                    <p className="mt-0.5 text-sm text-stone">
                      {BASE_UNIT_LABEL[material.base_unit]}
                      {material.price ? "" : ` · priced ${BASE_UNIT_PER[material.base_unit]}`} ·{" "}
                      {material.pack_count}{" "}
                      {material.pack_count === 1 ? "product" : "products"}
                    </p>
                  </div>
                  {/* The one number this milestone exists to produce. It is
                      derived on every read from whichever packs are mapped
                      right now, so unmapping a wrong merge corrects it here
                      with nothing to rebuild. */}
                  {material.price ? (
                    <div className="text-right">
                      <p className="font-display text-lg font-semibold text-ink">
                        {pricePerUnit(material.price)}
                      </p>
                      <p className="text-xs text-stone">{priceSource(material.price)}</p>
                      <p className="text-xs text-stone">{priceQuality(material.price)}</p>
                      <Link
                        href={`/invoices/${material.price.invoice_id}`}
                        className="text-xs font-medium text-palm underline-offset-2 hover:underline"
                      >
                        See the invoice
                      </Link>
                    </div>
                  ) : (
                    // "Nothing bought yet" and "nothing bought could be
                    // costed" are different facts, and only one of them is
                    // somebody's to fix.
                    <p className="text-sm text-stone">
                      {blocked.some((issue) => issue.ingredient_id === material.id)
                        ? "No price yet - see above"
                        : "No confirmed purchase yet"}
                    </p>
                  )}
                </div>
                <ul className="mt-3 divide-y divide-ink/5 border-t border-ink/5">
                  {material.packs.map((pack) => {
                    const setsThePrice =
                      material.price?.supplier_item_id === pack.id;
                    return (
                      <li
                        key={pack.id}
                        className="flex flex-wrap items-center justify-between gap-3 py-2"
                      >
                        <div className="min-w-0">
                          <p className="text-sm text-ink">{pack.canonical_name}</p>
                          <p className="text-xs text-stone">
                            {pack.supplier_name}
                            {pack.pack_size ? ` · ${pack.pack_size}` : ""}
                            {/* A conversion someone entered stays visible, or
                                it would vanish the moment it took effect. */}
                            {pack.pack_size_override
                              ? ` · one holds ${pack.pack_size_override}, you said`
                              : ""}
                          </p>
                        </div>
                        <div className="flex items-center gap-3">
                          {/* Each pack's own cost per kilo, which is the
                              comparison the merge above exists to make: the
                              same material from two suppliers, side by side in
                              one unit. */}
                          <div className="text-right">
                            {pack.cost ? (
                              <>
                                <p className="text-sm text-ink tabular-nums">
                                  {pricePerUnit(pack.cost)}
                                </p>
                                <p className="text-xs text-stone">
                                  {setsThePrice ? "sets the price now · " : ""}
                                  {pack.cost.invoice_date
                                    ? formatDate(pack.cost.invoice_date)
                                    : pack.cost.purchased_on
                                      ? formatDate(pack.cost.purchased_on)
                                      : ""}
                                </p>
                              </>
                            ) : (
                              <p className="text-xs text-stone">No cost yet</p>
                            )}
                          </div>
                          <button
                            type="button"
                            disabled={busyId === pack.id}
                            onClick={() =>
                              void decide(
                                pack.id,
                                () => unmapSupplierItem(pack.id),
                                `${pack.canonical_name} is back in the queue.`,
                              )
                            }
                            className="rounded-sm border border-ink/20 px-2.5 py-1 text-xs font-medium text-stone hover:border-clay hover:text-ink disabled:opacity-50"
                          >
                            Unmap
                          </button>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </li>
            ))}
          </ul>
        )}
        {materials.length > 0 ? (
          <p className="max-w-2xl text-xs text-stone">
            A material costs what you last paid for it, ex-VAT and after any discount, taken from
            the most recent invoice among the products above - not an average, and not the cheapest
            one. No purchase cost is ever marked verified: nothing on an invoice cross-checks the
            pack size a cost is divided by.
          </p>
        ) : null}
      </section>
    </div>
  );
}
