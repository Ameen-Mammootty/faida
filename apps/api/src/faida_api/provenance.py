"""C8: where every stored number came from (plan.md §7.2).

Green-or-amber (`invoices.confidence`) says whether a number survived the
arithmetic. This says how it got here in the first place, which is a different
question and the one nothing could answer before: a total the model read off
the page and a total the owner typed into WhatsApp because the paper was out
of frame are both honest, and until now they were the same number in the same
column.

That is survivable while an invoice is a page you can pull up next to it. It
stops being survivable at M5/M6, where a figure is divided into a cost per
base unit and folded into a plate cost - by then nothing downstream can tell
that a margin rests on something somebody remembered rather than something a
camera saw. Hence C8's rule: the record travels with the number.

Shape: one flat dict on `invoices.provenance`, keyed by field path -
`"total"`, `"lines.3.qty"` - each carrying `origin`, `actor` and `at`. Flat
because every write here is a merge over some subset of fields (a correction
touches three keys and must leave the rest alone), and a nested shape makes
that a recursive walk for no gain.

Pure module: no I/O, no DB, no knowledge of the confirm grammar. Callers map
their own edits onto keys with `line_key`.
"""

import datetime
from enum import StrEnum
from typing import Any

from .extraction.schema import ExtractedInvoice

# Header fields carrying a value a person could later correct or supply. Money
# and the two facts the approval gate and the analytics depend on (date, no),
# plus the printed-fact fields C3 reads. `tax_treatment`/`vat_rate` are absent
# on purpose: C4 derives them from the arithmetic rather than reading them, so
# their origin is always "derived from the fields below" and recording it per
# invoice would be noise.
HEADER_FIELDS: tuple[str, ...] = (
    "supplier_name",
    "invoice_no",
    "invoice_date",
    "currency",
    "payment_kind",
    "subtotal",
    "tax",
    "total",
    "discount_total",
    "rounding_amount",
)

# Per-line fields the same applies to. `line_kind` is C3's classification of
# the row, not a transcribed value, so it is left out for the same reason.
LINE_FIELDS: tuple[str, ...] = (
    "raw_name",
    "qty",
    "unit",
    "unit_price",
    "line_total",
    "pack_size",
)


class Origin(StrEnum):
    """How a stored value got there. The split that matters downstream is
    read-off-a-photo versus asserted-by-a-person, not the six labels."""

    EXTRACTED = "extracted"  # the model read it off the image, first pass
    REPAIRED = "repaired"  # the model re-read it in the scoped repair round
    CORRECTED_CHAT = "corrected_chat"  # a person fixed it over WhatsApp
    CORRECTED_SCREEN = "corrected_screen"  # a person fixed it on the review screen
    RECONSTRUCTED = "reconstructed"  # never on the page; a person supplied it (WP-26)
    MANUAL = "manual"  # typed in wholesale, no model involved (WP-34)


#: Origins where a camera saw the value and the arithmetic could check it.
READ_ORIGINS: frozenset[Origin] = frozenset({Origin.EXTRACTED, Origin.REPAIRED})

#: Origins where a person asserted the value. Not worse - `reconstructed` is
#: exactly what WP-26 asks for, and a correction is a human fixing a misread -
#: but not checkable against the photo, which is what C9 propagates.
ASSERTED_ORIGINS: frozenset[Origin] = frozenset(Origin) - READ_ORIGINS


def line_key(index: int, field: str) -> str:
    """Field path for one line's field. `index` is 0-based - the chat grammar's
    1-based line numbers are converted before they reach here."""
    return f"lines.{index}.{field}"


def field_keys(invoice: ExtractedInvoice) -> list[str]:
    """Every field path this invoice has a slot for, whether or not it holds a
    value. A null total that a person later supplies must arrive as
    `reconstructed`, so its key exists from the start."""
    keys = list(HEADER_FIELDS)
    for index in range(len(invoice.lines)):
        keys.extend(line_key(index, field) for field in LINE_FIELDS)
    return keys


def stamp(origin: Origin, actor: str, at: datetime.datetime) -> dict[str, str]:
    """One field's record. `at` is stored ISO-8601; `actor` is free text until
    M7 brings real accounts - `whatsapp:+9715...`, `console`, or the model id."""
    return {"origin": origin.value, "actor": actor, "at": at.isoformat()}


def initial(
    invoice: ExtractedInvoice, *, origin: Origin, actor: str, at: datetime.datetime
) -> dict[str, Any]:
    """Every field of a freshly created invoice from one origin: the whole
    document off the model (`extracted`), or the whole document typed by hand
    (`manual`)."""
    record = stamp(origin, actor, at)
    return {key: dict(record) for key in field_keys(invoice)}


def mark(
    provenance: dict[str, Any],
    keys: list[str],
    *,
    origin: Origin,
    actor: str,
    at: datetime.datetime,
) -> dict[str, Any]:
    """Re-stamp just these fields, leaving every other one alone. Returns a new
    dict; the input is never mutated."""
    merged = dict(provenance)
    for key in keys:
        merged[key] = stamp(origin, actor, at)
    return merged


def changed_fields(before: ExtractedInvoice, after: ExtractedInvoice) -> list[str]:
    """Which field paths hold a different value after a merge than before it.

    This is how the repair round is attributed without the repair code having
    to report what it touched: a scoped re-read may be asked for three cells
    and return the same value for two of them, and only the one that actually
    moved was re-read to any effect. Lines added or removed by the merge (the
    schema permits it; the merge in repair.py does not do it) count as changed
    across every field of the affected index.
    """
    changed: list[str] = []
    for field in HEADER_FIELDS:
        if getattr(before, field, None) != getattr(after, field, None):
            changed.append(field)
    for index in range(max(len(before.lines), len(after.lines))):
        old = before.lines[index] if index < len(before.lines) else None
        new = after.lines[index] if index < len(after.lines) else None
        if old is None or new is None:
            changed.extend(line_key(index, field) for field in LINE_FIELDS)
            continue
        changed.extend(
            line_key(index, field)
            for field in LINE_FIELDS
            if getattr(old, field, None) != getattr(new, field, None)
        )
    return changed


def asserted_fields(provenance: dict[str, Any]) -> list[str]:
    """Field paths whose value a person asserted rather than a camera saw.

    The seed of C9: a derived number (M5's cost per base unit, M6's plate cost)
    is never greener than its worst input, and this is how a derivation asks
    which of its inputs cannot be checked against a photo.
    """
    asserted = {origin.value for origin in ASSERTED_ORIGINS}
    return sorted(
        key
        for key, record in provenance.items()
        if isinstance(record, dict) and record.get("origin") in asserted
    )
