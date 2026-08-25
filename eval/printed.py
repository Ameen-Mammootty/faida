"""What the generated invoices actually print (WP-15/F8).

`<CASE>.expected.json` is the generator's *model* of an invoice: it carries
inventory codes, base-unit conversions and unit vocabulary that the page never
shows. `<CASE>.prompt.txt` is the human-authored specification the image was
generated from, so for anything C3 defines as a printed fact - raw_name, unit,
pack_size - the prompt is the ground truth and the model file is not.

Conflating the two is not hypothetical. Until this module existed the
converter mapped `pack_quantity` (grams) into `pack_size` and
`purchase_unit_text` into `unit`, so ground truth claimed "2000" where the
page prints "2 kg", and claimed `unit: 'bag'` for TH-01, a till receipt with
no unit column anywhere on it. The first live eval scored pack_size at 19%
and unit at 90% against a >=95% gate, entirely on those two mistakes: the
model had read every one of those cells correctly.

The prompts share one shape - a `COLUMNS, left to right:` header naming the
printed columns, then pipe-delimited rows - and a receipt like TH-01 has no
table at all, which is itself the fact worth recording: no unit column means
truth carries no unit.
"""

import pathlib
import re
from decimal import Decimal, InvalidOperation

from faida_api.extraction.normalize import PLACEHOLDERS

COLUMNS_MARKER = "COLUMNS, left to right:"
PAYMENT_TERMS = re.compile(r"^payment terms:\s*(?P<terms>.+)$", re.IGNORECASE | re.MULTILINE)
# AR-01 renders the second script as a parenthetical note inside the
# description cell: "Unsalted Butter  (Arabic line directly under it: ...)".
BILINGUAL_NOTE = re.compile(r"\((?:arabic|english)[^:]*:\s*(?P<other>[^)]+)\)", re.IGNORECASE)


class PrintedPageError(RuntimeError):
    """The prompt could not be read as the page it describes. Raised rather
    than guessed at: silently wrong ground truth is what this module exists to
    stop."""


# "Nothing here" is written the same way on a page as it is returned by a model
# copying that page, so the set lives with the pipeline and the eval imports it.


def _normalize(name: str) -> str:
    return " ".join(name.split()).casefold()


def _cell_value(raw: str | None) -> str | None:
    """A placeholder is an absence, and truth records it as one."""
    if raw is None:
        return None
    value = " ".join(raw.split())
    return None if value.casefold() in PLACEHOLDERS else value


def parse_columns(text: str) -> list[str] | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(COLUMNS_MARKER):
            rest = stripped[len(COLUMNS_MARKER) :]
            return [cell.strip() for cell in rest.split("|")]
    return None


def parse_rows(text: str, columns: list[str]) -> list[dict[str, str]]:
    """Every pipe row whose first cell is a line number and whose width matches
    the header. Anything else in the prompt (prose, notes, totals blocks) is
    left alone."""
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if "|" not in stripped:
            continue
        cells = [cell.strip() for cell in stripped.split("|")]
        if len(cells) != len(columns) or not cells[0].isdigit():
            continue
        rows.append(dict(zip(columns, cells, strict=True)))
    return rows


def _column_for(columns: list[str], *wanted: str) -> str | None:
    """Match a column by its printed heading. Exact-normalized first, so
    "Unit" never resolves to "Unit price AED"."""
    normalized = {_normalize(c): c for c in columns}
    for candidate in wanted:
        if candidate in normalized:
            return normalized[candidate]
    return None


def split_description(cell: str) -> str:
    """The description exactly as the page shows it. Where the page prints two
    scripts, both belong in raw_name - that is what a reader sees and what the
    extraction returns."""
    note = BILINGUAL_NOTE.search(cell)
    if note is None:
        return " ".join(cell.split())
    primary = " ".join(cell[: note.start()].split())
    other = " ".join(note.group("other").split())
    return f"{primary} {other}".strip()


def _amount(cell: str) -> Decimal | None:
    try:
        return Decimal(cell.replace(",", ""))
    except (InvalidOperation, AttributeError):
        return None


class PrintedPage:
    """The printed columns of one case, or the explicit absence of them."""

    def __init__(self, columns: list[str] | None, rows: list[dict[str, str]], terms: str | None):
        self.columns = columns
        self.rows = rows
        self.terms = terms
        self._description = _column_for(columns or [], "description", "item", "particulars")
        self._unit = _column_for(columns or [], "unit")
        self._pack = _column_for(columns or [], "pack size", "pack", "size")
        self._amount = _column_for(columns or [], "amount aed", "amount", "line total")

    @property
    def has_table(self) -> bool:
        return self.columns is not None and bool(self.rows)

    def cell(self, index: int, column: str | None) -> str | None:
        if column is None or index >= len(self.rows):
            return None
        return _cell_value(self.rows[index].get(column))

    def unit(self, index: int) -> str | None:
        """None when the page has no unit column at all (TH-01), which is a
        fact about the page, not missing data."""
        return self.cell(index, self._unit)

    def pack_size(self, index: int) -> str | None:
        return self.cell(index, self._pack)

    def description(self, index: int) -> str | None:
        raw = self.cell(index, self._description)
        return None if raw is None else split_description(raw)

    def amount(self, index: int) -> Decimal | None:
        cell = self.cell(index, self._amount)
        return None if cell is None else _amount(cell)

    def payment_kind(self) -> str | None:
        """Read off the printed terms: "Cash on delivery" is a cash purchase,
        a due period ("14 days") is credit."""
        if self.terms is None:
            return None
        terms = self.terms.casefold()
        if "cash" in terms:
            return "cash"
        if "credit" in terms or "days" in terms or "net" in terms:
            return "credit"
        return None


def read(case_dir: pathlib.Path) -> PrintedPage:
    path = case_dir / f"{case_dir.name}.prompt.txt"
    if not path.exists():
        raise PrintedPageError(f"{case_dir.name}: no prompt to read the printed page from")
    text = path.read_text()
    columns = parse_columns(text)
    rows = parse_rows(text, columns) if columns else []
    terms_match = PAYMENT_TERMS.search(text)
    return PrintedPage(columns, rows, terms_match.group("terms").strip() if terms_match else None)
