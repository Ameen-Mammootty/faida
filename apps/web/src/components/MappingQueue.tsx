"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  addConversion,
  listIngredients,
  listRawMaterialQueue,
  mapSupplierItem,
} from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { money, roundedMoney } from "@/lib/format";
import type { BaseUnit, IngredientSummary, QueueItem } from "@/lib/types";
import CostBadge from "./CostBadge";
import { CheckIcon } from "./icons";

const BASE_UNITS: { value: BaseUnit; label: string }[] = [
  { value: "g", label: "Weight (kg)" },
  { value: "ml", label: "Volume (litres)" },
  { value: "pc", label: "Count (pieces)" },
];

const inputClasses =
  "rounded-sm border border-ink/20 bg-paper px-2 py-1.5 text-sm text-ink hover:border-palm/50 focus:border-palm focus:outline-none";

/**
 * The M5 mapping screen: every pack the catalog built from invoices that has
 * no raw material yet, biggest spend first, each with the cost per kilo it
 * would contribute and a suggestion when one is near-certain.
 *
 * The screen proposes; the person decides. Nothing here maps anything on its
 * own, because a wrong merge quietly changes the cost of every menu item
 * above it and there is no photo to check that against.
 */
export default function MappingQueue() {
  const [items, setItems] = useState<QueueItem[] | null>(null);
  const [ingredients, setIngredients] = useState<IngredientSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<{ name: string; material: string } | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [queue, materials] = await Promise.all([listRawMaterialQueue(), listIngredients()]);
        if (cancelled) return;
        setItems(queue);
        setIngredients(materials);
        setError(null);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Couldn't load the raw materials.");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  function reload() {
    setReloadKey((key) => key + 1);
  }

  function onMapped(item: QueueItem, materialName: string) {
    setDone({ name: item.canonical_name, material: materialName });
    reload();
  }

  if (error !== null) {
    return (
      <p role="alert" className="rounded-md border border-caution/30 bg-gold-soft p-4 text-sm">
        {error}
      </p>
    );
  }
  if (items === null) {
    return (
      <p role="status" aria-busy="true" className="text-sm text-stone">
        Loading raw materials
      </p>
    );
  }

  const totalSpend = items.reduce((sum, item) => sum + Number(item.spend), 0);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-display text-2xl font-semibold tracking-[-0.02em] text-ink">
          Raw materials
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-stone">
          Every pack you buy belongs to something you cook with. Put each one on its shelf and the
          same ingredient bought from two suppliers, in two pack sizes, reads as one price per
          kilo.
        </p>
      </header>

      {done !== null ? (
        <p
          role="status"
          className="inline-flex items-center gap-2 rounded-sm bg-mist px-3 py-2 text-sm text-verified"
        >
          <CheckIcon />
          {done.name} is now {done.material}.
        </p>
      ) : null}

      <section aria-labelledby="materials-heading" className="space-y-3">
        <div className="flex items-baseline justify-between gap-4">
          <h2 id="materials-heading" className="text-sm font-semibold text-ink">
            Materials on the shelf
          </h2>
          <span className="text-xs text-stone">{ingredients.length} so far</span>
        </div>
        {ingredients.length === 0 ? (
          <p className="rounded-md border border-dashed border-ink/15 p-4 text-sm text-stone">
            None yet. Map the first pack below and its material is created with it.
          </p>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {ingredients.map((ingredient) => (
              <li key={ingredient.id} className="rounded-md border border-ink/10 bg-paper p-4">
                <Link href={`/materials/${ingredient.id}`} className="block">
                  <p className="font-medium text-ink">{ingredient.name}</p>
                  <div className="mt-2">
                    <CostBadge
                      cost={ingredient.cost}
                      blocked={ingredient.cost === null ? "no_price" : null}
                      showBasis={false}
                    />
                  </div>
                  <p className="mt-2 text-xs text-stone">
                    {ingredient.packs} {ingredient.packs === 1 ? "pack" : "packs"}
                    {ingredient.blocked_packs > 0
                      ? ` · ${ingredient.blocked_packs} still need a pack size`
                      : ""}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="queue-heading" className="space-y-3">
        <div className="flex items-baseline justify-between gap-4">
          <h2 id="queue-heading" className="text-sm font-semibold text-ink">
            To map
          </h2>
          <span className="text-xs text-stone">
            {items.length} {items.length === 1 ? "pack" : "packs"}
            {totalSpend > 0 ? ` · AED ${roundedMoney(String(totalSpend))} spent` : ""}
          </span>
        </div>
        {items.length === 0 ? (
          <p className="rounded-md border border-dashed border-ink/15 p-6 text-sm text-stone">
            Nothing waiting. Every pack on a confirmed invoice has a material.
          </p>
        ) : (
          <ul className="space-y-3">
            {items.map((item) => (
              <QueueRow
                key={item.id}
                item={item}
                ingredients={ingredients}
                onMapped={onMapped}
                onChanged={reload}
              />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function QueueRow({
  item,
  ingredients,
  onMapped,
  onChanged,
}: {
  item: QueueItem;
  ingredients: IngredientSummary[];
  onMapped: (item: QueueItem, materialName: string) => void;
  onChanged: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [rowError, setRowError] = useState<string | null>(null);

  async function run(action: () => Promise<string | null>) {
    setBusy(true);
    setRowError(null);
    try {
      const materialName = await action();
      if (materialName !== null) onMapped(item, materialName);
      else onChanged();
    } catch (err) {
      setRowError(err instanceof ApiError ? err.message : "That didn't work. Try again.");
    } finally {
      setBusy(false);
    }
  }

  const packLine = [item.unit, item.pack_size].filter(Boolean).join(" · ");

  return (
    <li className="rounded-md border border-ink/10 bg-paper p-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="font-medium text-ink">{item.canonical_name}</p>
          <p className="mt-0.5 text-sm text-stone">
            {item.supplier_name ?? "Unknown supplier"}
            {packLine ? ` · ${packLine}` : ""}
            {item.last_price ? ` · AED ${money(item.last_price)} each` : ""}
          </p>
          <p className="mt-1 text-xs text-stone">
            AED {roundedMoney(item.spend)} spent across {item.invoices}{" "}
            {item.invoices === 1 ? "invoice" : "invoices"}
          </p>
        </div>
        <div className="text-right">
          <CostBadge cost={item.cost} blocked={item.blocked} />
        </div>
      </div>

      {item.proposal !== null ? (
        <div className="mt-3 flex flex-wrap items-center gap-3 rounded-sm bg-mist px-3 py-2">
          <span className="text-sm text-ink">
            Looks like <strong className="font-semibold">{item.proposal.name}</strong>
            <span className="text-stone">
              {" "}
              &mdash;{" "}
              {item.proposal.via === "sibling"
                ? `you mapped "${item.proposal.evidence}" there`
                : "same name, different pack"}
            </span>
          </span>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              run(async () => {
                const result = await mapSupplierItem(item.id, {
                  ingredient_id: item.proposal?.ingredient_id,
                });
                return result.ingredient.name;
              })
            }
            className="rounded-sm bg-palm px-3 py-1.5 text-sm font-semibold text-white hover:bg-palm-deep disabled:opacity-50"
          >
            Yes, that&apos;s it
          </button>
        </div>
      ) : null}

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          className="text-sm font-medium text-palm hover:text-palm-deep"
        >
          {open ? "Close" : item.proposal ? "Something else" : "Choose a material"}
        </button>
        {item.blocked === "unknown_pack" ? (
          <span className="text-xs text-stone">
            Priced per {item.unit ?? "pack"} &mdash; say what one holds to get a cost per kilo.
          </span>
        ) : null}
      </div>

      {rowError !== null ? (
        <p role="alert" className="mt-2 text-sm text-caution">
          {rowError}
        </p>
      ) : null}

      {open ? (
        <div className="mt-3 grid gap-4 border-t border-ink/10 pt-3 sm:grid-cols-2">
          <ExistingMaterialForm
            ingredients={ingredients}
            busy={busy}
            onSubmit={(ingredientId) =>
              run(async () => {
                const result = await mapSupplierItem(item.id, { ingredient_id: ingredientId });
                return result.ingredient.name;
              })
            }
          />
          <NewMaterialForm
            defaultName={item.canonical_name}
            busy={busy}
            onSubmit={(name, baseUnit) =>
              run(async () => {
                const result = await mapSupplierItem(item.id, { name, base_unit: baseUnit });
                return result.ingredient.name;
              })
            }
          />
          {item.blocked === "unknown_pack" ? (
            <ConversionForm
              unit={item.unit}
              busy={busy}
              onSubmit={(quantity, baseUnit, note) =>
                run(async () => {
                  await addConversion(item.id, {
                    base_quantity: quantity,
                    base_unit: baseUnit,
                    note,
                  });
                  return null;
                })
              }
            />
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

function ExistingMaterialForm({
  ingredients,
  busy,
  onSubmit,
}: {
  ingredients: IngredientSummary[];
  busy: boolean;
  onSubmit: (ingredientId: string) => Promise<void>;
}) {
  const [selected, setSelected] = useState("");
  if (ingredients.length === 0) return null;
  return (
    <form
      className="space-y-2"
      onSubmit={(event) => {
        event.preventDefault();
        if (selected) void onSubmit(selected);
      }}
    >
      <label className="block text-sm font-medium text-ink" htmlFor="existing-material">
        An existing material
      </label>
      <div className="flex gap-2">
        <select
          id="existing-material"
          value={selected}
          onChange={(event) => setSelected(event.target.value)}
          className={`${inputClasses} flex-1`}
        >
          <option value="">Choose one</option>
          {ingredients.map((ingredient) => (
            <option key={ingredient.id} value={ingredient.id}>
              {ingredient.name}
            </option>
          ))}
        </select>
        <button
          type="submit"
          disabled={busy || !selected}
          className="rounded-sm border border-palm/30 px-3 py-1.5 text-sm font-medium text-palm hover:border-palm hover:bg-mist disabled:opacity-50"
        >
          Map
        </button>
      </div>
    </form>
  );
}

function NewMaterialForm({
  defaultName,
  busy,
  onSubmit,
}: {
  defaultName: string;
  busy: boolean;
  onSubmit: (name: string, baseUnit: BaseUnit) => Promise<void>;
}) {
  // The pack size is the part of a printed name that must not become the
  // material's name: "Milk Powder 2.5kg" is a pack, "Milk Powder" is a
  // material. Stripping it here is a suggestion the consultant edits.
  const suggested = defaultName
    .replace(/\d+(?:[.,]\d+)?\s*(kgs?|kg|gms?|g|ml|l|ltr|pcs?|pc|oz)\b/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
  const [name, setName] = useState(suggested || defaultName);
  const [baseUnit, setBaseUnit] = useState<BaseUnit>("g");
  return (
    <form
      className="space-y-2"
      onSubmit={(event) => {
        event.preventDefault();
        if (name.trim()) void onSubmit(name.trim(), baseUnit);
      }}
    >
      <label className="block text-sm font-medium text-ink" htmlFor="new-material">
        Or a new one
      </label>
      <div className="flex flex-wrap gap-2">
        <input
          id="new-material"
          value={name}
          onChange={(event) => setName(event.target.value)}
          className={`${inputClasses} min-w-0 flex-1`}
        />
        <select
          aria-label="Measured in"
          value={baseUnit}
          onChange={(event) => setBaseUnit(event.target.value as BaseUnit)}
          className={inputClasses}
        >
          {BASE_UNITS.map((unit) => (
            <option key={unit.value} value={unit.value}>
              {unit.label}
            </option>
          ))}
        </select>
        <button
          type="submit"
          disabled={busy || !name.trim()}
          className="rounded-sm bg-palm px-3 py-1.5 text-sm font-semibold text-white hover:bg-palm-deep disabled:opacity-50"
        >
          Create and map
        </button>
      </div>
    </form>
  );
}

function ConversionForm({
  unit,
  busy,
  onSubmit,
}: {
  unit: string | null;
  busy: boolean;
  onSubmit: (quantity: string, baseUnit: BaseUnit, note: string) => Promise<void>;
}) {
  const [quantity, setQuantity] = useState("");
  const [baseUnit, setBaseUnit] = useState<BaseUnit>("g");
  const label = unit ?? "pack";
  return (
    <form
      className="space-y-2 sm:col-span-2"
      onSubmit={(event) => {
        event.preventDefault();
        if (quantity.trim()) {
          onSubmit(quantity.trim(), baseUnit, `1 ${label} = ${quantity.trim()} ${baseUnit}`).catch(
            () => undefined,
          );
        }
      }}
    >
      <label className="block text-sm font-medium text-ink" htmlFor="conversion-quantity">
        What does one {label} hold?
      </label>
      <p className="text-xs text-stone">
        Nothing on the invoice says this, so nobody but you can. Enter it in grams, millilitres,
        or pieces &mdash; 10 kg is 10000 g.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-stone">1 {label} =</span>
        <input
          id="conversion-quantity"
          inputMode="decimal"
          value={quantity}
          onChange={(event) => setQuantity(event.target.value)}
          placeholder="10000"
          className={`${inputClasses} w-32`}
        />
        <select
          aria-label="Conversion unit"
          value={baseUnit}
          onChange={(event) => setBaseUnit(event.target.value as BaseUnit)}
          className={inputClasses}
        >
          <option value="g">grams</option>
          <option value="ml">millilitres</option>
          <option value="pc">pieces</option>
        </select>
        <button
          type="submit"
          disabled={busy || !quantity.trim()}
          className="rounded-sm border border-palm/30 px-3 py-1.5 text-sm font-medium text-palm hover:border-palm hover:bg-mist disabled:opacity-50"
        >
          Save
        </button>
      </div>
    </form>
  );
}
