"""Filing (CONTEXT.md): the one step that turns a normalized invoice and a
supplier's catalog into what the database stores and the reply reads - the
checks with snapped folded in, the price alerts, the derived confidence and
the line rows. It runs the same for a photo (`pipeline._persist_extracted`),
a correction from chat or the screen (`confirm._apply_correction`), a typed
invoice (`api.create_manual_invoice`) and the eval's live runner, which is
the point: the sequence is the behaviour, and until 2026-09-14 each door
carried its own copy of it and the copies had drifted (the typed path folded
snapped into the line checks but not into the validation it kept).

Pure and synchronous. The caller has already normalized the invoice
(`normalize.normalize_extracted` - it derives cash-or-credit from the printed
terms, which a typed payment kind must not go through twice), run the scoped
repair round where one applies, matched or chosen the supplier and fetched
that supplier's catalog. Nothing here reads a database or a model, so the
rules below are pinned by `tests/test_filing.py` on hand-built inputs, and
the eval scores the shipped chain rather than a copy of it.

The rules, each of which used to be prose repeated at every door:

- Snapping never recomputes a status (plan.md §5 layer 4, M1): a line's
  arithmetic stays green whether or not the catalog knew its name, because the
  catalog is empty on day one and unknown items are normal. `snapped` is
  folded onto the persisted check as a fact beside the arithmetic.
- `catalog=None` means there is no supplier to snap against and every line
  keeps `snapped=None` (neutral, per validate.py); `catalog=[]` means a
  supplier with nothing learnt yet, and every line carries `snapped=False`.
- The reply's composer sees exactly what persists, snapped flags included:
  the returned validation is the folded one.
- Price alerts (WP-23) are computed for every door and are the caller's to
  use or drop - the typed path sends no reply, so it drops them.
- Confidence is derived, never self-reported (plan.md §5 layer 5): the
  document check plus the per-line green/amber statuses.
- Every line row carries `line_kind`: the insert defaults it, the correction
  ignores it, and a door that forgot it is exactly the bug that hides in
  wiring.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..matching import Row, snap_item
from ..replies import DEFAULT_CURRENCY, PriceAlert
from .constants import PRICE_ALERT_MIN_ABS, PRICE_ALERT_MIN_PCT
from .currency import currency_differs
from .schema import ExtractedInvoice
from .validate import LineCheck, ValidationResult, validate_invoice


@dataclass(frozen=True)
class Filing:
    """What one filing produced, immutable, computed once.

    `validation` has `snapped` folded onto every line check when a catalog
    was given; `snapped_items` is the catalog row each line snapped to (None
    where it matched nothing, or where there was no catalog); `alerts` are the
    price moves against those items; `confidence` is the persisted jsonb;
    `rows` are the `invoice_lines` dicts in the shape both write doors take."""

    validation: ValidationResult
    snapped_items: list[Row | None]
    alerts: list[PriceAlert]
    confidence: dict[str, Any]
    rows: list[dict[str, Any]]

    @property
    def line_checks(self) -> list[LineCheck]:
        return self.validation.lines


def file_invoice(
    invoice: ExtractedInvoice,
    *,
    catalog: Sequence[Row] | None,
    tenant_currency: str | None,
    positions: Sequence[int] | None = None,
) -> Filing:
    """Validate, snap, fold, alert, derive confidence, render the rows.

    `catalog` is the matched or chosen supplier's items, `None` when the
    paper has no supplier. `tenant_currency` decides whether the alerts mean
    anything (WP-28). `positions` are the stored line positions for a
    correction; the default numbers lines from zero for a fresh paper. A
    positions list of the wrong length raises, the way the zips below do."""
    validation = validate_invoice(invoice)
    snapped_items: list[Row | None] = [None] * len(invoice.lines)
    line_checks = validation.lines
    if catalog is not None:
        snapped_items = [snap_item(catalog, line.raw_name) for line in invoice.lines]
        line_checks = [
            check.model_copy(update={"snapped": item is not None})
            for check, item in zip(line_checks, snapped_items, strict=True)
        ]
        validation = validation.model_copy(update={"lines": line_checks})
    alerts = price_alerts(invoice, snapped_items, tenant_currency=tenant_currency)
    confidence = {
        "document": validation.document.model_dump(mode="json"),
        "lines": [check.status.value for check in line_checks],
    }
    if positions is None:
        positions = range(len(invoice.lines))
    rows = [
        {
            "position": position,
            "raw_name": line.raw_name,
            "line_kind": line.line_kind.value,
            "supplier_item_id": str(item["id"]) if item is not None else None,
            "qty": line.qty,
            "unit": line.unit,
            "unit_price": line.unit_price,
            "line_total": line.line_total,
            "pack_size": line.pack_size,
            "checks": check.model_dump(mode="json"),
        }
        for position, line, check, item in zip(
            positions, invoice.lines, line_checks, snapped_items, strict=True
        )
    ]
    return Filing(
        validation=validation,
        snapped_items=snapped_items,
        alerts=alerts,
        confidence=confidence,
        rows=rows,
    )


def filed_names(snapped_items: list[Row | None]) -> list[str | None]:
    """WP-126: per line, the catalog name it snapped to, or None when it
    matched nothing - what the read-out lists, so the sender sees the words
    the price history will carry."""
    return [None if item is None else item["canonical_name"] for item in snapped_items]


def price_alerts(
    invoice: ExtractedInvoice,
    snapped_items: list[Row | None],
    *,
    tenant_currency: str | None = None,
) -> list[PriceAlert]:
    """WP-23 (plan.md §6 M2, the demo's money moment): one alert per snapped
    line whose extracted unit_price moved from the item's last_price by both
    >= PRICE_ALERT_MIN_ABS and >= PRICE_ALERT_MIN_PCT of it - either
    direction, falling prices are signal too. Ordered by absolute delta
    descending. The baseline itself moves only on confirm
    (Database.record_confirmed_prices), never here.

    WP-28: an invoice billed in another currency raises no alerts at all.
    The baseline is a bare number in the tenant's money, so "USD 75 against a
    baseline of AED 50" is not a price rise, it is two different questions
    subtracted from each other - and this is the one message the demo asks to
    be trusted on."""
    if currency_differs(invoice.currency, tenant_currency):
        return []
    alerts: list[PriceAlert] = []
    for line, item in zip(invoice.lines, snapped_items, strict=True):
        if item is None or line.unit_price is None or item["last_price"] is None:
            continue
        last = item["last_price"]
        delta = abs(line.unit_price - last)
        if delta >= PRICE_ALERT_MIN_ABS and delta >= PRICE_ALERT_MIN_PCT * last:
            alerts.append(
                PriceAlert(
                    item_name=item["canonical_name"],
                    prev_price=last,
                    new_price=line.unit_price,
                    currency=invoice.currency or DEFAULT_CURRENCY,
                )
            )
    alerts.sort(key=lambda alert: alert.delta, reverse=True)
    return alerts
