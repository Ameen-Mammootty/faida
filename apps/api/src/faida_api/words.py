"""How Faida writes a figure in English: money, percentages, quantities,
counts, lists of names, dates, branches and units.

The one place each rule lives (the 2026-09-24 architecture review, spec 4).
Before this module every rule sat in whichever file needed it first and the
others borrowed it by its private name, and two of them had already split:
one plate cost read AED 6.41 on `/menu` and AED 6.42 in a dashboard note.
A screen, a sentence, the morning brief and the printout that quote the same
figure call the same function here, so they cannot write it two ways.

Imports nothing from `faida_api`, so any module can use it without a cycle.
The dates spell their months from a fixed table rather than `strftime`, so
the words do not move with the host's locale."""

import datetime
from collections.abc import Sequence
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

_WHOLE = Decimal("1")
_FILS = Decimal("0.01")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


# --- money -------------------------------------------------------------------


def money(amount: Decimal, currency: str) -> str:
    """A headline figure: whole dirhams rounded half up, thousands separated
    (the display rule, `roundedAed` on the web, decided 2026-09-05). Exact
    figures belong in the invoice detail."""
    return f"{currency} {amount.quantize(_WHOLE, rounding=ROUND_HALF_UP):,}"


def plate_money(amount: Decimal, currency: str) -> str:
    """A per-plate cost or margin: fils, cut and never rounded, exactly as
    `/menu` prints it (`summaryMoney`, D9 of 2026-09-24). The stored plate
    carries three decimals and the third is storage precision, not
    information. Never whole dirhams: a plate margin rounded to AED 0 at karak
    prices says nothing (the 2026-08-30 design review)."""
    return f"{currency} {amount.quantize(_FILS, rounding=ROUND_DOWN):,}"


def price(amount: Decimal, currency: str) -> str:
    """A price per unit of a material - per kg, per litre, each: fils,
    rounded half up."""
    return f"{currency} {amount.quantize(_FILS, rounding=ROUND_HALF_UP):,}"


def per_unit(unit: str) -> str:
    """ "per kg", "per litre", "each" - the display unit as a price is read
    aloud, never "per each"."""
    return "each" if unit == "each" else f"per {unit}"


# --- numbers -----------------------------------------------------------------


def pct(value: Decimal) -> str:
    """A whole percentage, rounded half up: "61%"."""
    return f"{value.quantize(_WHOLE, rounding=ROUND_HALF_UP)}%"


def qty(value: Decimal) -> str:
    """ "2" for 2.000, "2.5" for 2.500 - the till's trailing zeros are its
    own, not information."""
    normalized = value.normalize()
    if normalized == normalized.to_integral_value():
        normalized = normalized.to_integral_value()
    return f"{normalized:f}"


def portions(value: Decimal) -> str:
    """ "1,240" for 1240.000, "2.5" for 2.500 - `qty` with the separator a
    thousand portions reads with."""
    normalized = value.normalize()
    if normalized == normalized.to_integral_value():
        return f"{int(normalized):,}"
    return f"{normalized:,f}"


def count(n: int, singular: str, plural: str | None = None) -> str:
    """ "1 invoice", "3 invoices"; `plural` for a word that is not an -s."""
    word = singular if n == 1 else (plural or singular + "s")
    return f"{n} {word}"


def names(items: Sequence[str]) -> str:
    """ "A", "A and B", "A, B and C"."""
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} and {items[-1]}"


# --- dates -------------------------------------------------------------------


def short_date(day: datetime.date) -> str:
    """ "31 Aug"."""
    return f"{day.day} {_MONTHS[day.month - 1]}"


def long_date(day: datetime.date) -> str:
    """ "31 Aug 2026" - the year included, for a figure read months after the
    period it covers."""
    return f"{short_date(day)} {day.year}"


def weekday_date(day: datetime.date) -> str:
    """ "Mon 31 Aug"."""
    return f"{_WEEKDAYS[day.weekday()]} {short_date(day)}"


# --- places ------------------------------------------------------------------


def short_branch(name: str) -> str:
    """ "Rolla" from "Rolla Branch": a sentence says the place the way the
    owner does; the field keeps the branch's full name."""
    parts = name.split()
    if len(parts) > 1 and parts[-1].lower() == "branch":
        return " ".join(parts[:-1])
    return name
