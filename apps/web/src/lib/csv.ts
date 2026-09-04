/**
 * A CSV reader, in the browser, for the M6 WP-64 batch loader.
 *
 * The file it has to survive is a real one: a consultant's spreadsheet, saved
 * out of Excel or Numbers on a Mac in a Dubai office. That means CRLF line
 * endings, a UTF-8 byte-order mark Excel writes and never mentions, ingredient
 * names with commas in them ("Beef, boneless"), and quoted cells containing
 * the quote character itself. All four appear in the 45-recipe Koukh Al Shay
 * file this loader was built against.
 *
 * It is deliberately small and dependency-free: RFC 4180 without the parts
 * nothing here uses (no custom delimiters, no comment lines, no streaming).
 * The alternative was a parsing library in a bundle that ships to a phone.
 *
 * Hardened in place for the sales loader (M8 WP-83): an unterminated quote
 * refuses the file naming its line, two columns with one name refuse the
 * header, and a row whose cell count is not the header's is reported by line
 * so a consumer can block it rather than read a shifted column.
 *
 * It also runs in the browser rather than the API on purpose. The loader has
 * to work in mock mode, offline, with no backend at all - that is how the demo
 * and every QA pass run it - so the file is read where it is dropped. Nothing
 * here decides anything: parsing produces rows of text, and every judgement
 * about what those rows mean belongs to `menuLoad.ts` or `salesLoad.ts` and,
 * finally, to the write door, which refuses in its own words whatever this
 * failed to catch.
 */

/**
 * A row whose cell count is not the header's: a stray comma inside an
 * unquoted name, or a cell missing off the end. Reported by 1-based file line
 * so "line 14" means the spreadsheet's own row; the rows themselves are still
 * padded on read so a consumer that takes a missing cell as blank keeps
 * working. The sales loader blocks such rows by name; the menu loader reads
 * them as it always has.
 */
export interface RaggedRow {
  line: number;
  cells: number;
  expected: number;
}

/** A parse either produced rows, or has one plain sentence for the person. */
export type CsvResult =
  | { ok: true; header: string[]; rows: string[][]; ragged: RaggedRow[] }
  | { ok: false; error: string };

/**
 * Split CSV text into rows of raw cells. Handles quoted fields (commas,
 * newlines and doubled quotes inside them), CRLF and LF, and a leading BOM.
 * Trailing blank lines are dropped - a spreadsheet export almost always has
 * one and it is not an empty recipe row.
 *
 * Also says whether a quote was still open at the end of the text, and on
 * which line it opened: everything after it read as one cell, so the caller
 * refuses the file rather than half-reading it.
 */
function splitRows(text: string): { rows: string[][]; openQuoteLine: number | null } {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  // Lines are counted by every newline seen, inside quotes or not - that is
  // how the spreadsheet numbers them too.
  let line = 1;
  let quoteOpenedAt = 0;
  // The BOM is invisible in every editor and would otherwise become part of
  // the first column's name, so the header would not match anything.
  const source = text.charCodeAt(0) === 0xfeff ? text.slice(1) : text;

  const endCell = () => {
    row.push(cell);
    cell = "";
  };
  const endRow = () => {
    endCell();
    rows.push(row);
    row = [];
  };

  for (let i = 0; i < source.length; i += 1) {
    const char = source[i];
    if (char === "\n") line += 1;
    if (quoted) {
      if (char === '"') {
        if (source[i + 1] === '"') {
          cell += '"';
          i += 1;
        } else {
          quoted = false;
        }
      } else {
        cell += char;
      }
      continue;
    }
    if (char === '"' && cell === "") {
      quoted = true;
      quoteOpenedAt = line;
    } else if (char === ",") {
      endCell();
    } else if (char === "\n") {
      endRow();
    } else if (char === "\r") {
      // CRLF: the \n does the work. A bare CR (old Mac) ends the row too.
      if (source[i + 1] !== "\n") endRow();
    } else {
      cell += char;
    }
  }
  if (cell !== "" || row.length > 0) endRow();

  while (rows.length > 0 && rows[rows.length - 1].every((value) => value.trim() === "")) {
    rows.pop();
  }
  return { rows, openQuoteLine: quoted ? quoteOpenedAt : null };
}

/**
 * Parse a whole file. The only file-level refusals live here, and each is one
 * sentence a consultant can act on - never a stack trace (row 64).
 *
 * A spreadsheet handed over as .xlsx is the mistake this catches most often:
 * its bytes are a zip archive, so they contain no comma-separated header and
 * frequently no printable text at all.
 */
export function parseCsv(text: string): CsvResult {
  if (text.trim() === "") {
    return { ok: false, error: "That file is empty." };
  }
  // A binary file dropped in by mistake: zip (xlsx, numbers), old xls, PDF.
  if (/^(PK\x03\x04|\xd0\xcf\x11\xe0|%PDF)/.test(text)) {
    return {
      ok: false,
      error:
        "That is a spreadsheet file, not a CSV. Open it and use File - Save As - " +
        "CSV, then upload the .csv.",
    };
  }
  const { rows, openQuoteLine } = splitRows(text);
  if (openQuoteLine !== null) {
    return {
      ok: false,
      error:
        `Line ${openQuoteLine} opens a quote that never closes, so everything after it ` +
        "read as one cell. Close the quote or take it out, then upload the file again.",
    };
  }
  if (rows.length === 0) {
    return { ok: false, error: "That file is empty." };
  }
  const header = rows[0].map((name) => name.trim());
  if (header.length < 2) {
    return {
      ok: false,
      error:
        "That does not look like a CSV: the first line has no comma-separated column " +
        "names. Download the template and paste into it.",
    };
  }
  // Two columns with one name cannot be read by name, and by name is the only
  // way a column is ever read here. Blank names are a spreadsheet's trailing
  // empty columns, not a clash.
  const seen = new Map<string, string>();
  for (const name of header) {
    const key = name.toLowerCase().replace(/\s+/g, " ");
    if (key === "") continue;
    const first = seen.get(key);
    if (first !== undefined) {
      return {
        ok: false,
        error:
          `Two columns are both called "${first}". Rename one of them so the loader knows ` +
          "which to read, then upload the file again.",
      };
    }
    seen.set(key, name);
  }
  const ragged: RaggedRow[] = [];
  rows.slice(1).forEach((row, offset) => {
    // A blank line is a spacer, never a ragged row. Every other row with the
    // wrong number of cells is named by its file line - 1-based and past the
    // header, so "line 14" is the spreadsheet's own row.
    const blank = row.every((value) => value.trim() === "");
    if (!blank && row.length !== header.length) {
      ragged.push({ line: offset + 2, cells: row.length, expected: header.length });
    }
  });
  return { ok: true, header, rows: rows.slice(1), ragged };
}
