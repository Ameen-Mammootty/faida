import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { parseCsv } from "../csv";
import { readMenuCsv } from "../menuLoad";

/**
 * M8 WP-83: `csv.ts` hardened in place, with the menu loader's own reading
 * of its template as the regression - the two loaders share one parser, so
 * a refusal added for the till's export must not change what the recipe
 * sheet reads as.
 */

const MENU_TEMPLATE = readFileSync(
  fileURLToPath(new URL("../../../public/faida-menu-template.csv", import.meta.url)),
  "utf8",
);
const SALES_TEMPLATE = readFileSync(
  fileURLToPath(new URL("../../../public/faida-sales-template.csv", import.meta.url)),
  "utf8",
);

describe("parseCsv, as it always read", () => {
  it("strips a BOM, takes CRLF, and keeps commas and quotes inside quoted cells", () => {
    const text = '﻿item,note\r\n"Beef, boneless","he said ""fresh"""\r\n';
    const parsed = parseCsv(text);
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect(parsed.header).toEqual(["item", "note"]);
    expect(parsed.rows).toEqual([["Beef, boneless", 'he said "fresh"']]);
    expect(parsed.ragged).toEqual([]);
  });

  it("still tells a spreadsheet to Save As CSV", () => {
    const parsed = parseCsv("PK\x03\x04binary");
    expect(parsed).toMatchObject({ ok: false });
    if (parsed.ok) return;
    expect(parsed.error).toContain("Save As");
  });

  it("reads the menu template into the same two recipes the menu loader loads", () => {
    const parsed = parseCsv(MENU_TEMPLATE);
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect(parsed.header).toHaveLength(9);
    expect(parsed.ragged).toEqual([]);
    const read = readMenuCsv(parsed.header, parsed.rows);
    expect(read.ok).toBe(true);
    if (!read.ok) return;
    expect(read.items.map((item) => item.name)).toEqual(["Karak Tea (Cup)", "Cappuccino"]);
    expect(read.items[0].lines).toHaveLength(5);
    expect(read.items[1].lines).toHaveLength(4);
  });

  it("reads the sales template with its closed-day row and no ragged rows", () => {
    const parsed = parseCsv(SALES_TEMPLATE);
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect(parsed.header).toEqual(["Outlet", "Date", "PLU", "Item", "Qty", "Amount"]);
    expect(parsed.rows).toHaveLength(6);
    expect(parsed.ragged).toEqual([]);
  });
});

describe("parseCsv, hardened for the till's export", () => {
  it("refuses a file whose quote never closes, naming the line it opened on", () => {
    const parsed = parseCsv('Outlet,Date,Item,Amount\nA,25/08/2026,KARAK,12\nA,25/08/2026,"CHKN 65,9\nA,26/08/2026,TEA,3\n');
    expect(parsed).toMatchObject({ ok: false });
    if (parsed.ok) return;
    expect(parsed.error).toContain("Line 3");
    expect(parsed.error).toContain("never closes");
  });

  it("names a ragged row by its file line and leaves the rest readable", () => {
    const parsed = parseCsv("Outlet,Date,Item,Amount\nA,25/08/2026,KARAK,12\nA,25/08/2026,9\nA,25/08/2026,TEA,3,extra\n\n");
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect(parsed.rows).toHaveLength(3);
    expect(parsed.ragged).toEqual([
      { line: 3, cells: 3, expected: 4 },
      { line: 4, cells: 5, expected: 4 },
    ]);
  });

  it("does not count a blank spacer line as ragged", () => {
    const parsed = parseCsv("Outlet,Date,Item,Amount\nA,25/08/2026,KARAK,12\n\nA,26/08/2026,TEA,3\n");
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect(parsed.ragged).toEqual([]);
  });

  it("refuses two columns with one name, and ignores blank trailing names", () => {
    const twice = parseCsv("Outlet,Date,Amount,amount\nA,25/08/2026,1,2\n");
    expect(twice).toMatchObject({ ok: false });
    if (twice.ok) return;
    expect(twice.error).toContain('"Amount"');

    const trailing = parseCsv("Outlet,Date,Amount,,\nA,25/08/2026,1,,\n");
    expect(trailing.ok).toBe(true);
  });
});
