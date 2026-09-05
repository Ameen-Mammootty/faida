"""M9 WP-91: the three deterministic signals, derived on every read
(Docs/M9_DECOMPOSITION.md §3, C13; plan.md §7.2).

A signal is a rule, a sentence and a number. No model, no stored row, no
lifecycle, no dismissal, no snooze - C5's precedent ("derived from existing
tables until real usage demands more"). There is no `signals` table and no
`issues` table, and this module does no I/O: `dashboard.py` feeds it rows
`contribution.py` and `menu.price_moves` already computed and serialises what
comes back.

Three kinds, and only three (PRD §25.3):

    popular and low-margin   an item in the period's top ten by net item
                             sales that keeps at least ten points less than
                             the chain's own weighted average
    supplier price spike     a material's newest same-pack move, a **rise**
                             of at least 5% (`PRICE_ALERT_MIN_PCT`,
                             inherited unchanged), weighed by the portions
                             sold on or after the day it landed
    branch gap               a branch keeping at least five points less
                             than the chain over that branch's own window

The thresholds live here beside their reasons, never in a per-tenant
setting (there is no settings table and M9 adds none). They are relative
wherever a menu is involved: a cafeteria's karak runs above 90% and its
chicken dish near 50%, so any fixed cutoff would be a number about one menu
wearing the clothes of a rule. **There is no absolute money floor** (decided
2026-09-05, D10): the panel is ranked by the AED at stake and capped at
five, so the ranking and the cap already do a floor's job - a 5% rise on a
cheap material with few sales ranks last with its small money beside it,
which is information, and it appears only when fewer than five bigger
things are happening.

A signal never fires on an input it would not trust: an `incomplete` or
`unavailable` row produces nothing, and an `estimated` one produces a signal
that carries the word. Every sentence that states a fact or a number is
composed here and carried on the wire (C13.5), so M10's brief and the screen
can never word the same fact two ways; the screen frames and joins, never
computes, re-words or re-ranks.

Under a branch scope (C13.6) the candidates, the weights and the gap are
that branch's, and the benchmark in every sentence stays the chain's - a
branch is never compared to itself.
"""

import datetime
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from . import contribution
from .contribution import (
    DEFAULT_CURRENCY,
    Contribution,
    ItemRow,
    ItemSales,
    MenuItem,
    _money_words,
    _price_words,
)
from .extraction.constants import PRICE_ALERT_MIN_PCT
from .ratio import FILS, PCT_QUANTUM, Period, Quality, Window, _short_date, window_words

if TYPE_CHECKING:  # pragma: no cover - the type only; `menu.py` is a router
    from .menu import PriceMove

# --- the thresholds, each with its reason (C13.2, §5 P5) --------------------

#: "Popular" is the period's top ten by net item sales, in the scope in view.
#: Ten, because the rule is about what sells, and on a 45-item menu the top
#: ten carry most of the money; on a five-item menu it is the whole menu.
POPULAR_TOP_N = 10

#: "Low-margin" is at least this many points below the chain's own weighted
#: average contribution margin - relative, not absolute, so a karak shop and
#: a grill house need no settings screen.
LOW_MARGIN_POINTS = Decimal("10.0")

#: The spike gate is M2's price-alert percentage, inherited unchanged: 5%.
#: It is the whole gate. The shipped `PRICE_ALERT_MIN_ABS` (AED 0.25) is
#: about a **pack** price; a move here is in cost per base unit - per gram
#: or per millilitre, where AED 0.25 would mean AED 250 a kilo - and a panel
#: ranked by money and capped at five needs no floor (D10).
SPIKE_MIN_PCT = PRICE_ALERT_MIN_PCT

#: A branch gap is at least this many points below the chain's kept
#: percentage, the chain recomputed over the branch's own window.
BRANCH_GAP_POINTS = Decimal("5.0")

#: The panel shows at most five, largest money first; the fifth figure tells
#: the reader where the tail starts.
MAX_SIGNALS = 5

KIND_POPULAR_LOW_MARGIN = "popular_low_margin"
KIND_PRICE_SPIKE = "price_spike"
KIND_BRANCH_GAP = "branch_gap"

#: The one word beside a number that changes what it means (C13.3).
ESTIMATED_WORD = "estimated"

#: The labels a signal may fire on. `incomplete` and `unavailable` never do.
_TRUSTED = frozenset({Quality.RELIABLE, Quality.ESTIMATED})

#: Ties on money break by kind - the branch first, then the dish, then the
#: material - and then by name, so the order is the same on every read.
_KIND_ORDER = {KIND_BRANCH_GAP: 0, KIND_POPULAR_LOW_MARGIN: 1, KIND_PRICE_SPIKE: 2}


# --- inputs and outputs -----------------------------------------------------


@dataclass(frozen=True)
class Scope:
    """What the signals are about (C13.6): the chain when `branch_id` is
    None, otherwise the branch in view. The benchmark is the chain's either
    way."""

    branch_id: str | None = None
    branch_name: str | None = None


CHAIN = Scope()


@dataclass(frozen=True)
class BranchFigure:
    """One branch as the league knows it: its clipped window
    (`ratio.BranchRow.window`) and its contribution for the period. The
    window is what the chain benchmark is recomputed over."""

    window: Window
    contribution: Contribution


@dataclass(frozen=True)
class Signal:
    """One line of the panel (§3.1): the kind, the sentence that states the
    fact, the detail beneath it, the money at stake, the quality word, and
    the ids the screen links with. The optional fields are set by kind."""

    kind: str
    sentence: str
    detail: str
    money_at_stake: Decimal
    quality: Quality
    branch_id: str | None = None
    branch_name: str | None = None
    menu_item_id: str | None = None
    menu_item_name: str | None = None
    ingredient_id: str | None = None
    ingredient_name: str | None = None
    invoice_id: str | None = None
    moved_on: datetime.date | None = None


# --- words ------------------------------------------------------------------


def _short_branch(name: str) -> str:
    """ "Rolla" from "Rolla Branch": the sentence says the place the way the
    owner does; the field keeps the branch's full name."""
    words = name.split()
    if len(words) > 1 and words[-1].lower() == "branch":
        return " ".join(words[:-1])
    return name


def _points(value: Decimal) -> Decimal:
    return value.quantize(PCT_QUANTUM, rounding=ROUND_HALF_UP)


def _portions_words(qty: Decimal) -> str:
    """ "1,240" for 1240.000, "2.5" for 2.500 - the till's trailing zeros are
    its own, and a thousand portions reads with its separator."""
    normalized = qty.normalize()
    if normalized == normalized.to_integral_value():
        return f"{int(normalized):,}"
    return f"{normalized:,f}"


def _estimated(detail: str, quality: Quality) -> str:
    """The word rides on the detail, in the sentence's own words, when the
    signal fired on an estimated input (C13.3): the screen may show a chip
    beside it, but the wire already says it."""
    return f"{detail} ({ESTIMATED_WORD})" if quality is Quality.ESTIMATED else detail


def _quality(*inputs: Quality) -> Quality:
    """The signal's word: estimated if any input it fired on is anything but
    reliable. The benchmark is an input too - a chain figure carrying a
    sibling's gap is a partial average, and a comparison against a partial
    average is an estimate the sentence should admit (C13.3a)."""
    return Quality.ESTIMATED if any(q is not Quality.RELIABLE for q in inputs) else Quality.RELIABLE


# --- popular and low-margin (C13.2) ----------------------------------------


def popular_low_margin(
    rows: Iterable[ItemRow],
    chain: Contribution,
    *,
    scope: Scope = CHAIN,
    currency: str = DEFAULT_CURRENCY,
) -> list[Signal]:
    """Items in the scope's top ten by net item sales that keep at least
    `LOW_MARGIN_POINTS` less than the chain's weighted average.

    `rows` may hold every item row the read produced - the chain-wide ones
    (`branch_id` None) and each branch's - and the scope picks its own. The
    benchmark is `chain.contribution_pct`, the chain's own weighted average
    over costed sales, whatever the scope (C13.6); when it is undefined
    (nothing costed) nothing fires. The average is partial by construction -
    on a very short menu it is mostly the one dish that dominates - which is
    why the sentence names both figures, so a reader sees what the comparison
    is made of (C13.3a).
    """
    benchmark = chain.contribution_pct
    if benchmark is None:
        return []
    in_scope = [r for r in rows if r.branch_id == scope.branch_id and r.net_item_sales > 0]
    popular = sorted(in_scope, key=lambda r: (-r.net_item_sales, r.menu_item_name, r.menu_item_id))[
        :POPULAR_TOP_N
    ]

    out: list[Signal] = []
    for row in popular:
        if row.contribution_pct is None or row.quality not in _TRUSTED:
            continue
        points = _points(benchmark - row.contribution_pct)
        if points < LOW_MARGIN_POINTS:
            continue
        stake = (points / 100 * row.net_item_sales).quantize(FILS, rounding=ROUND_HALF_UP)
        quality = _quality(row.quality, chain.quality)
        out.append(
            Signal(
                kind=KIND_POPULAR_LOW_MARGIN,
                sentence=(
                    f"{row.menu_item_name} sold {_money_words(row.net_item_sales, currency)} "
                    f"and kept {row.contribution_pct}%; the menu keeps {benchmark}%."
                ),
                detail=_estimated(
                    f"At the menu's average it would have contributed "
                    f"{_money_words(stake, currency)} more.",
                    quality,
                ),
                money_at_stake=stake,
                quality=quality,
                branch_id=scope.branch_id,
                branch_name=scope.branch_name,
                menu_item_id=row.menu_item_id,
                menu_item_name=row.menu_item_name,
            )
        )
    return out


# --- supplier price spike (C13.2) -------------------------------------------


def price_spike(
    moves: Iterable["PriceMove"],
    sales: Iterable[ItemSales],
    rows: Iterable[ItemRow],
    *,
    period: Period,
    scope: Scope = CHAIN,
    currency: str = DEFAULT_CURRENCY,
) -> list[Signal]:
    """A material's newest same-pack move, a rise of at least `SPIKE_MIN_PCT`,
    weighed by what sold since it landed.

    `moves` is `menu.price_moves` over pairs read with the period's `as_of`
    bound (C12.4, C13.2), so the move compared is the newest at or before the
    period's end and a September delivery is never multiplied by August's
    sales; a move dated after the period is skipped here too, so the rule
    holds whatever the caller read. A fall fires nothing (it stays on
    `/menu`'s callout), and a pack change fires nothing at all: "price basis
    changed" is a sentence about evidence, not a spike.

    The money at stake is the per-plate impact (`plates.margin_impact`) times
    the portions sold **on or after the move's own purchase date**, inside
    the window, from the by-day rows - never the whole period, which would
    charge the owner for plates sold at the old price. It is a since-landed
    figure and not a component of the contribution column, which already
    charges every portion at the new price (D19); the two are never added.
    An item whose days since the move have a line with no quantity cannot be
    weighed and is left out of the money rather than guessed at.
    """
    in_scope = {r.menu_item_id: r for r in rows if r.branch_id == scope.branch_id}
    since_rows = [
        s
        for s in sales
        if s.business_date <= period.end
        and not s.excluded
        and s.menu_item_id is not None
        and (scope.branch_id is None or s.branch_id == scope.branch_id)
    ]

    out: list[Signal] = []
    for move in moves:
        if move.kind != "moved" or move.delta_per_base_unit is None:
            continue
        delta = move.delta_per_base_unit
        if delta <= 0:
            continue  # a fall is not a spike
        moved_on = move.current.purchased_on
        if moved_on is None or moved_on > period.end:
            continue
        base = move.previous.cost_per_base_unit
        if base <= 0 or delta < SPIKE_MIN_PCT * base:
            continue

        since = contribution.days_since(since_rows, moved_on)
        portions: dict[str, Decimal] = {}
        uncountable: set[str] = set()
        for day in since:
            item_id = day.menu_item_id or ""
            if day.no_qty_lines:
                uncountable.add(item_id)
            portions[item_id] = portions.get(item_id, Decimal(0)) + day.qty_sold - day.qty_refunded

        stake = Decimal(0)
        weighed: list[ItemRow] = []
        total_portions = Decimal(0)
        for impact in move.items:
            row = in_scope.get(impact.menu_item_id)
            sold = portions.get(impact.menu_item_id, Decimal(0))
            if row is None or not row.costed or impact.menu_item_id in uncountable or sold <= 0:
                continue
            stake += impact.impact_per_portion * sold
            total_portions += sold
            weighed.append(row)
        stake = stake.quantize(FILS, rounding=ROUND_HALF_UP)

        line_qualities = [
            Quality.ESTIMATED if line.quality == ESTIMATED_WORD else Quality.RELIABLE
            for line in (move.current, move.previous)
        ]
        quality = _quality(*line_qualities, *(r.quality for r in weighed))

        unit = move.current.display_unit
        per_unit = "each" if unit == "each" else f"per {unit}"
        rise = _price_words(move.delta_per_display_unit or Decimal(0), currency)
        sentence = f"{move.ingredient_name} is up {rise} {per_unit} since {_short_date(moved_on)}"
        previous_on = move.previous.purchased_on
        if previous_on is not None and previous_on < period.start:
            # A baseline older than the window is named, not thresholded:
            # a recency cutoff would be an invented number.
            sentence += f", against its last purchase on {_short_date(previous_on)}"
        sentence += "."

        if total_portions > 0:
            detail = (
                f"{_money_words(stake, currency)} off contribution on the "
                f"{_portions_words(total_portions)} portions sold since it landed, "
                f"across {len(weighed)} {'item' if len(weighed) == 1 else 'items'}."
            )
        else:
            detail = "No sales of items using it since it landed."

        out.append(
            Signal(
                kind=KIND_PRICE_SPIKE,
                sentence=sentence,
                detail=_estimated(detail, quality),
                money_at_stake=stake,
                quality=quality,
                branch_id=scope.branch_id,
                branch_name=scope.branch_name,
                ingredient_id=move.ingredient_id,
                ingredient_name=move.ingredient_name,
                invoice_id=move.current.invoice_id,
                moved_on=moved_on,
            )
        )
    return out


# --- branch gap (C13.2) -----------------------------------------------------


def branch_gap(
    branches: Iterable[BranchFigure],
    chain: Contribution,
    sales: Sequence[ItemSales],
    menu: Mapping[str, MenuItem],
    *,
    scope: Scope = CHAIN,
    currency: str = DEFAULT_CURRENCY,
) -> list[Signal]:
    """A branch keeping at least `BRANCH_GAP_POINTS` less than the chain,
    where both are at least estimated.

    The benchmark is **recomputed over the candidate branch's own window**
    from the by-day rows (C12.1), through the same `contribution` functions
    the league uses, never taken from the chain total: windows are clipped to
    each branch's loaded range (C9's amendment), so a branch that uploaded
    three days against siblings who uploaded seven would otherwise be
    compared to a different fortnight. A branch with nothing loaded is not a
    gap; it is the league's `unavailable` row, which already says so.

    `chain` lends its label only: the number comes from the window, the word
    from the chain figure the reader sees beside it.
    """
    out: list[Signal] = []
    for branch in branches:
        own = branch.contribution
        if scope.branch_id is not None and own.branch_id != scope.branch_id:
            continue
        if own.contribution_pct is None or own.quality not in _TRUSTED:
            continue
        # Every branch's rows over this branch's window, summed as one figure:
        # `branch_contribution` over the whole chain's rows is the chain's kept
        # percentage over those days (C12.7's arithmetic, one call, no second
        # implementation). Only the figure is read, so the sales-side label
        # passed is a placeholder.
        window_rows = contribution.item_rows(
            contribution.days_in_window(sales, branch.window), menu, currency=currency
        )
        benchmark = contribution.branch_contribution(
            window_rows, branch_id=None, branch_name=None, sales_quality=Quality.RELIABLE
        ).contribution_pct
        if benchmark is None:
            continue
        points = _points(benchmark - own.contribution_pct)
        if points < BRANCH_GAP_POINTS:
            continue
        stake = (points / 100 * own.net_item_sales).quantize(FILS, rounding=ROUND_HALF_UP)
        quality = _quality(own.quality, chain.quality)
        name = own.branch_name or own.branch_id or ""
        out.append(
            Signal(
                kind=KIND_BRANCH_GAP,
                sentence=(
                    f"{_short_branch(name)} keeps {points} points less of every dirham "
                    f"than the chain."
                ),
                detail=_estimated(
                    f"{own.contribution_pct}% against {benchmark}% over "
                    f"{window_words(branch.window)}.",
                    quality,
                ),
                money_at_stake=stake,
                quality=quality,
                branch_id=own.branch_id,
                branch_name=own.branch_name,
            )
        )
    return out


# --- ranking and the cap (C13.4) --------------------------------------------


def rank(signals: Iterable[Signal], *, cap: int = MAX_SIGNALS) -> list[Signal]:
    """Largest money first, capped, never floored. A move with no sales
    since it landed carries zero and ranks last, with its own sentence."""
    ordered = sorted(
        signals,
        key=lambda s: (
            -s.money_at_stake,
            _KIND_ORDER.get(s.kind, len(_KIND_ORDER)),
            s.branch_name or s.menu_item_name or s.ingredient_name or "",
            s.sentence,
        ),
    )
    return ordered[:cap]


def compute(
    *,
    rows: Sequence[ItemRow],
    chain: Contribution,
    branches: Sequence[BranchFigure],
    moves: Sequence["PriceMove"],
    sales: Sequence[ItemSales],
    menu: Mapping[str, MenuItem],
    period: Period,
    scope: Scope = CHAIN,
    currency: str = DEFAULT_CURRENCY,
) -> list[Signal]:
    """The panel: the three kinds over already-computed rows, ranked by the
    AED at stake and capped at `MAX_SIGNALS`. `rows` holds every item row
    the read produced (chain-wide and per branch) and the scope picks."""
    return rank(
        [
            *popular_low_margin(rows, chain, scope=scope, currency=currency),
            *price_spike(moves, sales, rows, period=period, scope=scope, currency=currency),
            *branch_gap(branches, chain, sales, menu, scope=scope, currency=currency),
        ]
    )
