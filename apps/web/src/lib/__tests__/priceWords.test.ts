import { describe, expect, it } from "vitest";
import full from "../mock/dashboard/full.json";
import partial from "../mock/dashboard/partial.json";
import {
  mockListBlockedCosts,
  mockListIngredients,
  mockListUnmappedSupplierItems,
  mockMapSupplierItem,
  mockSetPackSizeOverride,
} from "../mock/materials";
import { mockGetMenuItem, mockListMenuItems, mockListPriceMoves } from "../mock/menu";
import { mockGetInvoice, mockListInvoices } from "../mock/store";

/**
 * Spec 3 (2026-09-24): a price's words are the API's. Every screen prints
 * `unit_words` and `why_estimated` as they arrive and composes neither, so
 * the mock must carry them the way the API does, or offline QA would show a
 * blank where the live screen shows a sentence. The dashboard's JSON comes
 * from the shipped Python (`generate.py`); the hand-written mocks are held
 * to the same two rules here.
 */

const WORDS: Record<string, string> = { kg: "per kg", litre: "per litre", each: "each" };

interface Priced {
  display_unit: string | null;
  unit_words: string | null;
  quality: string | null;
  why_estimated: string | null;
}

function expectSpokenAsTheApiSpeaks(price: Priced) {
  expect(price.unit_words).toBe(price.display_unit === null ? null : WORDS[price.display_unit]);
  // A reason exactly when the word is estimated (D8: never the word alone).
  expect(price.why_estimated !== null).toBe(price.quality === "estimated");
  if (price.why_estimated !== null) expect(price.why_estimated).toMatch(/^Estimated: (?!Estimated).+\.$/);
}

describe("every mock price speaks as the API does", () => {
  it("on the materials screen, for the price and each pack", async () => {
    // The shelf starts empty: map every pack as the screen does, and answer
    // the carton nothing measures, which prices it through a person (C9).
    for (const item of await mockListUnmappedSupplierItems()) {
      await mockMapSupplierItem(item.id, {
        name: item.canonical_name,
        base_unit: item.base_unit ?? "g",
      });
    }
    for (const blocked of await mockListBlockedCosts()) {
      if (blocked.supplier_item_id) {
        await mockSetPackSizeOverride(blocked.supplier_item_id, "10 kg");
      }
    }
    const prices = (await mockListIngredients()).flatMap((material) => [
      ...(material.price ? [material.price] : []),
      ...material.packs.flatMap((pack) => (pack.cost ? [pack.cost] : [])),
    ]);
    expect(prices.length).toBeGreaterThan(0);
    expect(prices.some((price) => price.quality === "estimated")).toBe(true);
    prices.forEach(expectSpokenAsTheApiSpeaks);
  });

  it("on the menu screen, for each component and each price move", async () => {
    const items = await Promise.all(
      (await mockListMenuItems()).map((item) => mockGetMenuItem(item.id)),
    );
    const prices = items.flatMap((item) =>
      (item.recipe?.components ?? []).flatMap((c) => (c.cost ? [c.cost.price] : [])),
    );
    expect(prices.some((price) => price.quality === "estimated")).toBe(true);
    prices.forEach(expectSpokenAsTheApiSpeaks);
    for (const move of await mockListPriceMoves()) {
      for (const line of [move.current, move.previous]) {
        expect(line.unit_words).toBe(WORDS[line.display_unit]);
      }
    }
  });

  it("on the invoice screen, for every line's cost", async () => {
    const costs = (
      await Promise.all((await mockListInvoices()).map((row) => mockGetInvoice(row.id)))
    ).flatMap((invoice) => invoice.lines.flatMap((line) => (line.cost ? [line.cost] : [])));
    expect(costs.length).toBeGreaterThan(0);
    costs.forEach(expectSpokenAsTheApiSpeaks);
  });

  it("on the dashboard, for every price track", () => {
    for (const payload of [...Object.values(full), ...Object.values(partial)]) {
      for (const row of [...payload.signals, ...payload.price_moves.moves]) {
        expect(row.unit_words).toBe(row.unit === null ? null : WORDS[row.unit]);
      }
    }
  });
});
