"""M8 WP-80: the pure rules of a sales day (Docs/M8_DECOMPOSITION.md §3, C11).

Everything here is arithmetic and naming with no database and no request in
it, in one place so the door (`sales.py`), the tests, the demo week's
generator (WP-85) and - by mirroring - the browser's loader (WP-83) read the
same rule rather than four copies of it:

    name_key        the normalised item name: the identity of a till item
                    the till prints no code for
    till_item_key   code first, name second (C11.7): a code survives a rename
    net_amount      amount / (1 + rate), quantized ROUND_HALF_UP to a fil, per
                    line - its own three lines rather than plates.net_of_vat,
                    which quantizes to a tenth of a fil; a day must equal
                    the exact sum of its stored lines (Codex 10)
    day_key         what "the same day" means for the unchanged outcome
                    (C11.4): granularity, basis and the multiset of lines in
                    any order; a closed day's multiset is its one amount, 0
    duplicate_days  two entries for one branch-day in one body: refused with
                    a sentence, never merged
    interior_gaps   the days strictly inside a branch's range in a file that
                    have no rows: loaded as takings-0 days by the loader,
                    because the export range is the till's own statement of
                    the days it covers (Codex 8)
    date_problem    a business date after tomorrow or before 2020, refused
                    with a sentence - a swapped day and month lands in the
                    future (review finding 9)

Item-wise exports only (the founder's call, 2026-09-04): a `summary` day is
a closed day - amount 0, no lines - and a day-totals export waits for the
pilot (M11). The granularity stays on the row so that arrival changes the
door's refusal and nothing here.

Money is Decimal throughout. Nothing here rounds anything but the one
division it names.
"""

import datetime
from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal

from .matching import normalize

#: A fil. Every stored sales amount is numeric(12,2).
FILS = Decimal("0.01")

#: One branch-month per request (C11.4): a year of history at onboarding is
#: a few dozen requests rather than a thousand.
MAX_DAYS_PER_REQUEST = 31

#: A business date before this year is a swapped field, not a sale.
MIN_BUSINESS_YEAR = 2020

GRANULARITIES = ("item", "summary")
AMOUNT_BASES = ("inclusive", "exclusive")
DATE_ORDERS = ("dmy", "ymd")

#: The logical columns a layout may map, and the two every file must have.
LAYOUT_COLUMNS = ("branch", "date", "item", "code", "qty", "amount")
LAYOUT_REQUIRED = ("date", "amount")


def name_key(name: str) -> str:
    """The normalised name: casefolded, punctuation stripped, whitespace
    collapsed - matching.normalize, so "Karak Tea - Flask 1L" and "KARAK TEA
    FLASK 1L" are one till item when the till prints no code."""
    return normalize(name)


def code_key(code: str | None) -> str | None:
    """The till's code, trimmed. A blank code is no code."""
    if code is None:
        return None
    text = code.strip()
    return text or None


def till_item_key(name: str, code: str | None) -> tuple[str, str]:
    """Code first, name second (C11.7): ("code", "52a") or ("name", "karak
    tea flask 1l"). A code survives a rename and two products never share
    one; a name is the identity only when there is nothing better."""
    code_text = code_key(code)
    if code_text is not None:
        return ("code", code_text)
    return ("name", name_key(name))


def net_amount(amount: Decimal, *, amount_basis: str, vat_rate: Decimal | None) -> Decimal:
    """The ex-VAT figure for one printed amount, to the fil.

    Inclusive amounts are divided by (1 + rate) and rounded half up once;
    exclusive amounts are net already. A currency with no rate in the C4
    table (a null rate) is treated as net - a till exporting in a currency
    Faida has no rate for is nobody's ask (§2 rule 8), and inventing 5%%
    would be worse than storing what was printed."""
    if amount_basis == "inclusive" and vat_rate is not None and vat_rate != 0:
        return (amount / (Decimal(1) + vat_rate)).quantize(FILS, rounding=ROUND_HALF_UP)
    return amount.quantize(FILS, rounding=ROUND_HALF_UP)


def header_key(header_names: Iterable[str]) -> str:
    """The layout's compatibility evidence: the mapped header names,
    normalised, sorted, joined with "|". Order-insensitive and
    case-insensitive, so a reordered export reads as the same header."""
    return "|".join(sorted(name_key(name) for name in header_names))


def line_key(name: str, code: str | None, qty: Decimal | None, amount: Decimal) -> tuple:
    """One line as re-upload equality sees it: the normalised name, the
    code, the quantity and the printed amount - never the position."""
    return (
        name_key(name),
        code_key(code) or "",
        "" if qty is None else str(qty.normalize()),
        str(amount.quantize(FILS)),
    )


def day_key(
    granularity: str,
    amount_basis: str,
    lines: Iterable[tuple[str, str | None, Decimal | None, Decimal]],
    amount: Decimal | None = None,
) -> tuple:
    """What "the same day" means (C11.4): the same granularity, the same
    basis and the same multiset of (normalised name, code, qty, amount), in
    any order. A closed (summary) day's multiset is its one amount, 0 today;
    the key carries it so a day-totals export at M11 changes nothing here.
    Two keys equal means nothing is written and no audit row appears."""
    if granularity == "summary":
        body: tuple = ((str((amount or Decimal(0)).quantize(FILS)),),)
    else:
        body = tuple(sorted(line_key(*line) for line in lines))
    return (granularity, amount_basis, body)


def duplicate_days(days: Iterable[tuple[str, datetime.date]]) -> list[tuple[str, datetime.date]]:
    """Branch-days named more than once in one body, in first-seen order.
    Two entries for one branch-day stop the day with a sentence rather than
    being summed: the loader groups an item file's rows into days, so a
    repeat here is a file saying two things about one day."""
    seen: set[tuple[str, datetime.date]] = set()
    repeated: list[tuple[str, datetime.date]] = []
    for key in days:
        if key in seen and key not in repeated:
            repeated.append(key)
        seen.add(key)
    return repeated


def interior_gaps(dates: Iterable[datetime.date]) -> list[datetime.date]:
    """The days strictly inside the range of `dates` that are not in it.
    The loader loads each as a takings-0 day ("29 Aug: no rows in the file,
    loaded as a zero day"), because a file's date range is the till's own
    statement of the days it covers; a day outside every file's range is a
    gap and reads incomplete in the ratio."""
    present = set(dates)
    if len(present) < 2:
        return []
    first, last = min(present), max(present)
    gaps: list[datetime.date] = []
    day = first + datetime.timedelta(days=1)
    while day < last:
        if day not in present:
            gaps.append(day)
        day += datetime.timedelta(days=1)
    return gaps


def date_problem(business_date: datetime.date, today: datetime.date) -> str | None:
    """Why a business date is refused, or None. After tomorrow is a swapped
    day and month (review finding 9); before 2020 is a swapped year or a
    default a till printed for a row it never dated. Tomorrow itself is
    allowed: a till east of UTC closes its day before the server's."""
    if business_date > today + datetime.timedelta(days=1):
        return (
            f"{business_date.isoformat()} is after tomorrow: check the layout's date order, "
            "a swapped day and month lands in the future"
        )
    if business_date.year < MIN_BUSINESS_YEAR:
        return f"{business_date.isoformat()} is before {MIN_BUSINESS_YEAR}: check the date column"
    return None
