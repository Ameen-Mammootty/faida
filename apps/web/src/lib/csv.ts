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
 * It also runs in the browser rather than the API on purpose. The loader has
 * to work in mock mode, offline, with no backend at all - that is how the demo
 * and every QA pass run it - so the file is read where it is dropped. Nothing
 * here decides anything: parsing produces rows of text, and every judgement
 * about what those rows mean belongs to `menuLoad.ts` and, finally, to the
 * write door, which refuses in its own words whatever this failed to catch.
 */

/** A parse either produced rows, or has one plain sentence for the person. */
export type CsvResult =
  | { ok: true; header: string[]; rows: string[][] }
  | { ok: false; error: string };

/**
 * Split CSV text into rows of raw cells. Handles quoted fields (commas,
 * newlines and doubled quotes inside them), CRLF and LF, and a leading BOM.
 * Trailing blank lines are dropped - a spreadsheet export almost always has
 * one and it is not an empty recipe row.
 */
function splitRows(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
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
  return rows;
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
  const rows = splitRows(text);
  if (rows.length === 0) {
    return { ok: false, error: "That file is empty." };
  }
  const header = rows[0].map((name) => name.trim());
  if (header.length < 2) {
    return {
      ok: false,
      error:
        "That does not look like a CSV: the first line has no comma-separated column " +
        "names. Download the template and paste the recipes into it.",
    };
  }
  return { ok: true, header, rows: rows.slice(1) };
}
