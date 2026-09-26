"""How a value goes out on the JSON wire. Money goes out as a string and never
a float, so the screen shows the digits the database holds; a date or a time
goes out as ISO 8601. None stays None: a missing figure is null, never 0.

Imports nothing from `faida_api`."""

from decimal import Decimal


def dec(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def iso(value) -> str | None:
    return None if value is None else value.isoformat()
