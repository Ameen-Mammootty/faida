"""M12 WP-120, phase one's consumer: the printed comparison (D22).

    python -m faida_api.usage_report --tenant <id> --from 2026-08-04 --to 2026-08-31

What the period's sales needed of each material, against what was bought of
it, one section per branch and then the chain - the same rows, the same lists
and the same words the dashboard panel will carry in phase two (§3.1), from
the same functions. The founder runs it weekly and hands the printout to the
pilot's owner; when the owner has acted on it twice, WP-121 puts the identical
block on the dashboard read (D22).

Read-only. It opens a pool on `DATABASE_URL` the way the app does, makes the
reads the dashboard already makes plus the one M12 adds, and writes nothing.

**Three layers, so phase two reuses the first two unchanged:**

    usage_inputs(db, ...)   the reads, and the rows adapted into `usage.py`'s
                            inputs. WP-121 calls the same adaptation from
                            `dashboard.py` over the rows that read already
                            holds - which is why every helper it needs is
                            imported from `dashboard.py` rather than copied.
    usage_blocks(inputs)    pure: `usage.py`'s functions, once, into §3.1's
                            block. `usage_payload(blocks)` serialises it in
                            the API's conventions, ready for the wire.
    render(blocks, ...)     the printout.

Nothing is computed here. Every quantity, every difference and every sentence
is `usage.py`'s (C14.6, C14.11); this module reads, adapts, and lays out. The
one thing it composes is the layout itself - headings, the section rules, the
list titles and the "left out" line's counts - and none of those qualifies a
figure. There is no headline sentence anywhere (D9).
"""

import argparse
import asyncio
import datetime
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import asyncpg

from . import contribution, ratio, usage
from .api import _dec, _iso
from .config import get_settings
from .contribution import _price_words
from .dashboard import _branch_ratio_rows, _item_sales, _menu_items
from .db import Database
from .menu import _menu_context
from .ratio import _plural, window_words
from .sales import _invoice_input, _sales_day_input

#: The width of a section rule. Wide enough for the figures line and narrow
#: enough to paste into a WhatsApp message on a phone.
_RULE = 78


# --- layer one: the reads, adapted into `usage.py`'s inputs ------------------


@dataclass(frozen=True)
class UsageInputs:
    """Everything `usage.py` needs for one tenant, one period and one scope.

    Exactly what `dashboard.py` will hold in memory on a request when WP-121
    lands, which is the point of the split: phase two builds this from the
    reads it already makes and calls `usage_blocks` on it.
    """

    tenant_id: str
    period: ratio.Period
    branch_id: str | None
    branch_names: dict[str, str]
    currency: str
    item_rows: tuple[contribution.ItemRow, ...]
    sales: tuple[contribution.ItemSales, ...]
    menu: dict[str, contribution.MenuItem]
    lines: tuple[usage.PurchaseLine, ...]
    windows: tuple[usage.BranchWindow, ...]
    materials: dict[str, usage.Material]
    prices: dict[str, usage.MaterialPrice]
    stale_ingredient_ids: frozenset[str]


def _purchase_line(row: asyncpg.Record) -> usage.PurchaseLine:
    """One row of `db.list_period_material_purchases`, field for field. The
    read was shaped for this, so nothing is decided here."""
    return usage.PurchaseLine(
        invoice_id=row["invoice_id"],
        invoice_no=row["invoice_no"],
        line_position=row["line_position"],
        branch_id=row["branch_id"],
        purchased_on=row["purchased_on"],
        supplier_name=row["supplier_name"],
        raw_name=row["raw_name"],
        qty=row["qty"],
        unit=row["unit"],
        pack_size=row["pack_size"],
        unit_price=row["unit_price"],
        line_total=row["line_total"],
        currency=row["currency"],
        frozen_factor=row["frozen_factor"],
        supplier_item_id=row["supplier_item_id"],
        ingredient_id=row["ingredient_id"],
        pack_size_override=row["pack_size_override"],
        canonical_name=row["canonical_name"],
    )


def _materials(
    components_by_item: Mapping[str, Sequence[asyncpg.Record]],
    prices: Mapping[str, asyncpg.Record],
) -> dict[str, usage.Material]:
    """Every material this read can name, with how it is measured and whether
    any supplier product is mapped to it.

    A material a recipe names comes off `db.list_current_recipe_components`'
    own row - the ingredient's `base_unit` and the `has_packs` subquery
    `plates` already reads - so a material with no pack mapped gets a row with
    what its recipes needed and no bought figure instead of one reading zero
    (C14.1, rule 8).

    A material **no recipe names** is the gloves case (D11): bought, listed
    apart, out of the ranking. Nothing the dashboard read holds carries its
    ingredient name, so it is named the way `usage.py` names one it has never
    heard of - by the catalog product the lines were booked under - and the
    one fact taken from the price row is how it is measured, without which
    "2,000" would print with no unit beside it and its money could not be
    computed at all. Giving these rows the material's own name is one column
    on `db.list_mapped_pack_costs`, and it is WP-121's call whether to add it.
    """
    materials: dict[str, usage.Material] = {}
    for components in components_by_item.values():
        for row in components:
            materials.setdefault(
                row["ingredient_id"],
                usage.Material(
                    ingredient_id=row["ingredient_id"],
                    name=row["ingredient_name"],
                    base_unit=row["base_unit"],
                    has_packs=row["has_packs"],
                ),
            )
    for ingredient_id, row in prices.items():
        materials.setdefault(
            ingredient_id,
            usage.Material(
                ingredient_id=ingredient_id,
                name=row["canonical_name"],
                base_unit=row["cost_base_unit"],
                has_packs=True,
            ),
        )
    return materials


def _material_prices(prices: Mapping[str, asyncpg.Record]) -> dict[str, usage.MaterialPrice]:
    """Each material's price in force on the period's last day, as
    `_menu_context` read it (C14.7): the newest costed line among its packs,
    with the day it was bought and the quality its cost basis recorded, so a
    money figure valued at an estimated price says so."""
    out: dict[str, usage.MaterialPrice] = {}
    for ingredient_id, row in prices.items():
        basis = row["cost_basis"] or {}
        out[ingredient_id] = usage.MaterialPrice(
            ingredient_id=ingredient_id,
            cost_per_base_unit=row["cost_per_base_unit"],
            cost_base_unit=row["cost_base_unit"],
            priced_on=row["purchased_on"],
            quality=basis.get("quality"),
            invoice_id=row["invoice_id"],
            line_position=row["position"],
        )
    return out


def _branch_window(row: ratio.BranchRow) -> usage.BranchWindow:
    """`ratio.period_row`'s answer as `usage.py` reads it: the branch's own
    clipped window, whether it loaded any sales at all, the papers still
    awaiting confirm inside it, and the sales half of its label with the
    sentences that made it. `ratio.py` is untouched (C14.11)."""
    return usage.BranchWindow(
        branch_id=row.branch_id,
        name=row.branch_name,
        window_from=row.window.start,
        window_to=row.window.end,
        sales_loaded=row.days_loaded > 0,
        pending=row.pending,
        sales_quality=row.sales_quality.value,
        sales_notes=row.sales_notes,
    )


async def usage_inputs(
    db: Database,
    *,
    tenant_id: str,
    date_from: datetime.date,
    date_to: datetime.date,
    branch_id: str | None = None,
) -> UsageInputs:
    """The reads, then the adaptation. The reads are the dashboard's own -
    the same branches, the same clipped windows, the same menu costed as of
    the period's end, the same raw item sales - plus the one query M12 adds,
    `db.list_period_material_purchases` (§3.2).

    Every window, every portion and every price therefore comes from the
    function that already owns it, so this printout and the dashboard above it
    cannot disagree about a figure they both show.
    """
    period = ratio.Period(date_from, date_to)
    newest_by_branch = await db.newest_sales_dates(tenant_id=tenant_id)
    currency = await db.tenant_currency(tenant_id) or ""
    branches = await db.list_branches(tenant_id=tenant_id)
    names = {branch["id"]: branch["name"] for branch in branches}

    days = [
        _sales_day_input(row)
        for row in await db.list_sales_days(
            tenant_id=tenant_id, date_from=period.start, date_to=period.end
        )
    ]
    invoices = [
        _invoice_input(row)
        for row in await db.list_period_invoices(
            tenant_id=tenant_id, date_from=period.start, date_to=period.end
        )
    ]
    rows = _branch_ratio_rows(
        branches,
        days=days,
        invoices=invoices,
        period=period,
        currency=currency,
        newest_by_branch=newest_by_branch,
    )

    menu_rows, components_by_item, plate_by_item, vat_rate, prices, stale = await _menu_context(
        db, tenant_id, as_of=period.end
    )
    menu = _menu_items(menu_rows, components_by_item, plate_by_item, prices, vat_rate)

    sales = [
        _item_sales(row)
        for row in await db.list_period_item_sales(
            tenant_id=tenant_id, date_from=period.start, date_to=period.end
        )
    ]
    lines = [
        _purchase_line(row)
        for row in await db.list_period_material_purchases(
            tenant_id=tenant_id, date_from=period.start, date_to=period.end
        )
    ]

    return UsageInputs(
        tenant_id=tenant_id,
        period=period,
        branch_id=branch_id,
        branch_names=names,
        currency=currency,
        item_rows=tuple(
            contribution.item_rows(sales, menu, costed_at=period.end, currency=currency)
        ),
        sales=tuple(sales),
        menu=menu,
        lines=tuple(lines),
        windows=tuple(_branch_window(rows[branch["id"]]) for branch in branches),
        materials=_materials(components_by_item, prices),
        prices=_material_prices(prices),
        stale_ingredient_ids=frozenset(stale),
    )


# --- layer two: the block (§3.1) --------------------------------------------


@dataclass(frozen=True)
class UsageBlocks:
    """§3.1's `usage` block, in `usage.py`'s own types.

    `rows` is the scope's ranked comparison rows - the chain rows unfiltered,
    the branch's own rows under a branch filter - and `branch_rows` is every
    branch's rows with the drill, present only unfiltered (D10). `window` and
    `branch_id` are the scope this was computed for; they are not on the wire,
    because the payload's period and filter are the request's own.
    """

    rows: tuple[usage.MaterialRow, ...]
    branch_rows: tuple[usage.MaterialRow, ...]
    count: int
    coverage: usage.Coverage
    unused_materials: tuple[usage.UnusedMaterial, ...]
    unmapped_packs: usage.UnmappedPacks
    orphans: usage.Orphans
    unassigned: tuple[usage.UnassignedRow, ...]
    left_out: usage.LeftOut
    standing: str
    window: ratio.Window
    branch_id: str | None


def usage_blocks(inputs: UsageInputs) -> UsageBlocks:
    """Every figure on the panel, from `usage.py`, once (C14.11).

    The comparison rows are always computed over **every** branch, and the
    scope narrows what is shown afterwards, because the set of materials a
    sold recipe names is the chain's: a branch that bought a material and sold
    none of it keeps its purchase-only row that way (D12), and the chain row
    can sum the branches it names.

    The lists beside the panel are the scope's: under a branch filter they are
    that branch's lines, and unfiltered they are the chain's, with the papers
    that named no branch listed only there (C14.9).
    """
    period = inputs.period
    branch_id = inputs.branch_id
    materials, prices = inputs.materials, inputs.prices
    stale, currency = inputs.stale_ingredient_ids, inputs.currency

    branch_rows = usage.material_rows(
        inputs.item_rows,
        inputs.menu,
        inputs.lines,
        inputs.windows,
        materials=materials,
        prices=prices,
        stale_ingredient_ids=stale,
        date_from=period.start,
        date_to=period.end,
        currency=currency,
    )
    unassigned = usage.unassigned_rows(inputs.lines, materials=materials)

    if branch_id is None:
        rows = usage.chain_material_rows(
            branch_rows,
            materials=materials,
            prices=prices,
            branch_names=inputs.branch_names,
            unassigned=unassigned,
            stale_ingredient_ids=stale,
            date_from=period.start,
            date_to=period.end,
            currency=currency,
        )
        shown_branch_rows = tuple(branch_rows)
        held = tuple(unassigned)
        scope_words = "the chain's"
    else:
        rows = [row for row in branch_rows if row.branch_id == branch_id]
        shown_branch_rows = ()
        held = ()
        scope_words = "this branch's"

    in_scope = [line for line in inputs.lines if branch_id is None or line.branch_id == branch_id]
    item_rows = [r for r in inputs.item_rows if branch_id is None or r.branch_id == branch_id]
    sales = [r for r in inputs.sales if branch_id is None or r.branch_id == branch_id]
    windows = [w for w in inputs.windows if branch_id is None or w.branch_id == branch_id]

    orphans = usage.orphans(in_scope, currency=currency)
    named = {c.ingredient_id for item in inputs.menu.values() for c in item.components}
    return UsageBlocks(
        rows=tuple(rows),
        branch_rows=shown_branch_rows,
        count=sum(1 for row in rows if row.used_base is not None and row.bought_base is not None),
        coverage=usage.recipe_coverage(
            sales, inputs.menu, orphan_lines=orphans.lines, scope_words=scope_words
        ),
        unused_materials=tuple(
            usage.unused_materials(
                inputs.lines,
                named,
                materials=materials,
                prices=prices,
                windows=inputs.windows,
                branch_id=branch_id,
                date_from=period.start,
                date_to=period.end,
            )
        ),
        unmapped_packs=usage.unmapped_packs(in_scope, currency=currency),
        orphans=orphans,
        unassigned=held,
        left_out=usage.left_out(item_rows, in_scope, windows, inputs.menu),
        standing=usage.STANDING_SENTENCE,
        window=ratio.Window(period.start, period.end),
        branch_id=branch_id,
    )


# --- the wire (WP-121 puts this dict straight on the payload) ---------------


def _line_json(entry: usage.LineEntry) -> dict:
    return {
        "invoice_id": entry.invoice_id,
        "invoice_no": entry.invoice_no,
        "line_position": entry.line_position,
        "purchased_on": _iso(entry.purchased_on),
        "supplier_name": entry.supplier_name,
        "product_name": entry.product_name,
        "qty": _dec(entry.qty),
        "pack": entry.pack,
        "pack_source": entry.pack_source,
        "factor": _dec(entry.factor),
        "factor_source": entry.factor_source,
        "base_qty": _dec(entry.base_qty),
        "base_words": entry.base_words,
        "measured": entry.measured,
        "currency": entry.currency,
        "blocked": entry.blocked,
    }


def _dish_json(dish: usage.DishEntry) -> dict:
    return {
        "menu_item_id": dish.menu_item_id,
        "menu_item_name": dish.menu_item_name,
        "branch_id": dish.branch_id,
        "portions": _dec(dish.portions),
        "per_portion_base": _dec(dish.per_portion_base),
        "usable_share": _dec(dish.usable_share),
        "base_qty": _dec(dish.base_qty),
    }


def _row_json(row: usage.MaterialRow) -> dict:
    """§3.1's `MaterialRow`. Money, quantities and percentages are strings and
    dates ISO, the API's convention since C4; the words are already words."""
    return {
        "ingredient_id": row.ingredient_id,
        "ingredient_name": row.ingredient_name,
        "base_unit": row.base_unit,
        "branch_id": row.branch_id,
        "window": {
            "from": _iso(row.window.start),
            "to": _iso(row.window.end),
            "days": row.window.days,
        },
        "used_base": _dec(row.used_base),
        "bought_base": _dec(row.bought_base),
        "gap_base": _dec(row.gap_base),
        "used_measured": _dec(row.used_measured),
        "bought_measured": _dec(row.bought_measured),
        "used_words": row.used_words,
        "bought_words": row.bought_words,
        "gap_words": row.gap_words,
        "used_measured_words": row.used_measured_words,
        "bought_measured_words": row.bought_measured_words,
        "used_hole": row.used_hole,
        "bought_hole": row.bought_hole,
        "direction": row.direction,
        "money": _dec(row.money),
        "price_per_display_unit": _dec(row.price_per_display_unit),
        "display_unit": row.display_unit,
        "priced_on": _iso(row.priced_on),
        "price_quality": row.price_quality,
        "purchases": row.purchases,
        "purchase_dates": row.purchase_dates,
        "returns": row.returns,
        "foreign_papers": row.foreign_papers,
        "unmeasured_lines": row.unmeasured_lines,
        "dishes_counted": row.dishes_counted,
        "refunded_portions": _dec(row.refunded_portions),
        "recipe_after_period": row.recipe_after_period,
        "quality": row.quality.value,
        "notes": list(row.notes),
        "lines": [_line_json(entry) for entry in row.lines],
        "dishes": [_dish_json(dish) for dish in row.dishes],
    }


def usage_payload(blocks: UsageBlocks) -> dict:
    """The block as it will ride on `GET /api/dashboard` (§3.1, C6 extended).

    Not routed today: phase two is WP-121, and it will serialise this same
    dict from the same `usage_blocks` call, so the printout below and the
    panel can never be built from two arithmetics.
    """
    return {
        "standing": blocks.standing,
        "rows": [_row_json(row) for row in blocks.rows],
        "branch_rows": [_row_json(row) for row in blocks.branch_rows],
        "count": blocks.count,
        "coverage": {
            "recipes_pct": _dec(blocks.coverage.recipes_pct),
            "covered_value": _dec(blocks.coverage.covered_value),
            "sales_value": _dec(blocks.coverage.sales_value),
            "dishes_without_recipe": blocks.coverage.dishes_without_recipe,
            "unmapped_names": blocks.coverage.unmapped_names,
            "sentence": blocks.coverage.sentence,
        },
        "unused_materials": [
            {
                "ingredient_id": material.ingredient_id,
                "ingredient_name": material.ingredient_name,
                "base_unit": material.base_unit,
                "branch_id": material.branch_id,
                "bought_base": _dec(material.bought_base),
                "bought_words": material.bought_words,
                "money": _dec(material.money),
                "purchases": material.purchases,
                "sentence": material.sentence,
            }
            for material in blocks.unused_materials
        ],
        "unmapped_packs": {
            "lines": blocks.unmapped_packs.lines,
            "packs": blocks.unmapped_packs.packs,
            "spend": _dec(blocks.unmapped_packs.spend),
            "foreign_lines": blocks.unmapped_packs.foreign_lines,
            "sentence": blocks.unmapped_packs.sentence,
        },
        "orphans": {
            "lines": blocks.orphans.lines,
            "foreign": blocks.orphans.foreign,
            "no_price": blocks.orphans.no_price,
            "unmatched": blocks.orphans.unmatched,
            "sentence": blocks.orphans.sentence,
            "papers": [
                {
                    "invoice_id": paper.invoice_id,
                    "invoice_no": paper.invoice_no,
                    "supplier_name": paper.supplier_name,
                    "currency": paper.currency,
                    "lines": paper.lines,
                }
                for paper in blocks.orphans.papers
            ],
        },
        "unassigned": [
            {
                "ingredient_id": held.ingredient_id,
                "ingredient_name": held.ingredient_name,
                "base_unit": held.base_unit,
                "bought_base": _dec(held.bought_base),
                "bought_words": held.bought_words,
                "papers": held.papers,
                "lines": [_line_json(entry) for entry in held.lines],
            }
            for held in blocks.unassigned
        ],
        "left_out": {
            "items_without_quantity": blocks.left_out.items_without_quantity,
            "items_without_recipe": blocks.left_out.items_without_recipe,
            "unmeasured_lines": blocks.left_out.unmeasured_lines,
            "branches_without_sales": blocks.left_out.branches_without_sales,
        },
    }


# --- layer three: the printout ----------------------------------------------


def _quality_word(quality: ratio.Quality) -> str:
    """The C9 vocabulary as a person reads it: "reliable with limitations",
    "estimated", "incomplete", "unavailable". The words are the enum's own -
    the underscores are how it is stored, not how it is said."""
    return quality.value.replace("_", " ")


def _figure(words: str | None, hole: str | None) -> str:
    """A figure, or its reason in the hole and no number - never a dash on its
    own where a reader could take it for zero (§3.1)."""
    if words is not None:
        return words
    return f"- ({hole})" if hole else "-"


def _row_lines(row: usage.MaterialRow, *, position: str, currency: str) -> list[str]:
    """One material, in the panel's own words: the two figures, the recorded
    difference, what it costs, the quality word, and every sentence that made
    them beneath it.

    Nothing here is computed. `used_words`, `bought_words` and `gap_words` are
    the API's (C14.6, the screen divides nothing), the money is the row's own
    `Decimal` printed to the fil beside its currency, and the notes - the
    direction sentence, the price sentence with the day it was priced, the
    single-delivery sentence, the recipe sentence - are printed in the order
    `usage.py` composed them.
    """
    out = [f"{position} {row.ingredient_name} - {_quality_word(row.quality)}"]
    figures = [
        f"recipes needed {_figure(row.used_words, row.used_hole)}",
        f"bought {_figure(row.bought_words, row.bought_hole)}",
        row.gap_words or "-",
    ]
    if row.money is not None:
        figures.append(_price_words(row.money, currency))
    out.append("      " + " | ".join(figures))
    out.extend(f"      - {note}" for note in row.notes)
    return out


def _measured_lines(row: usage.MaterialRow) -> list[str]:
    """What could be added up on the side of a figure that has a hole, under
    its own name so a partial sum is never mistaken for the whole (C14.8)."""
    out = []
    if row.used_measured_words is not None:
        out.append(f"      the part that could be summed: {row.used_measured_words} needed")
    if row.bought_measured_words is not None:
        out.append(f"      the part that could be summed: {row.bought_measured_words} bought")
    return out


def _left_out_line(left_out: usage.LeftOut) -> str | None:
    """The four counts on one line, and nothing when there were none."""
    parts = []
    if left_out.items_without_quantity:
        parts.append(_plural(left_out.items_without_quantity, "dish with no quantity on the till"))
    if left_out.items_without_recipe:
        parts.append(_plural(left_out.items_without_recipe, "dish sold with no recipe"))
    if left_out.unmeasured_lines:
        parts.append(_plural(left_out.unmeasured_lines, "purchase line that could not be measured"))
    if left_out.branches_without_sales:
        parts.append(_plural(left_out.branches_without_sales, "branch with no sales loaded"))
    return None if not parts else "Left out: " + ", ".join(parts) + "."


def _lists(blocks: UsageBlocks, *, currency: str) -> list[str]:
    """The four lists beside the panel, then the recipe-coverage line and what
    was left out. They are the scope's, so unfiltered they close the chain
    section and under `--branch` they close that branch's."""
    out: list[str] = []
    if blocks.unused_materials:
        out.append("")
        out.append("  Bought, not in any sold recipe")
        for material in blocks.unused_materials:
            money = "" if material.money is None else f", {_price_words(material.money, currency)}"
            out.append(
                f"    - {material.ingredient_name}: {material.bought_words}"
                f" on {_plural(material.purchases, 'paper')}{money}"
            )
    if blocks.unmapped_packs.sentence is not None:
        out.append("")
        out.append("  Purchases with no material yet")
        out.append(f"    - {blocks.unmapped_packs.sentence}")
    if blocks.orphans.sentence is not None:
        out.append("")
        out.append("  Purchase lines that reached no product")
        out.append(f"    - {blocks.orphans.sentence}")
        for paper in blocks.orphans.papers:
            named = paper.invoice_no or paper.invoice_id
            out.append(
                f"      {named}, {paper.supplier_name or 'no supplier named'}"
                f" ({paper.currency}): {_plural(paper.lines, 'line')}"
            )
    if blocks.unassigned:
        out.append("")
        out.append("  Papers that named no branch, counted in no row")
        for held in blocks.unassigned:
            out.append(
                f"    - {held.ingredient_name}: {held.bought_words}"
                f" on {_plural(held.papers, 'paper')}"
            )
            for entry in held.lines:
                named = entry.invoice_no or entry.invoice_id
                out.append(
                    f"      {named} line {entry.line_position},"
                    f" {entry.product_name}: {entry.base_words or 'not measured'}"
                )
    out.append("")
    out.append(f"  {blocks.coverage.sentence}")
    left_out = _left_out_line(blocks.left_out)
    if left_out is not None:
        out.append(f"  {left_out}")
    return out


def _section(
    title: str,
    window: ratio.Window,
    rows: Sequence[usage.MaterialRow],
    *,
    currency: str,
    standing: str,
    tail: Sequence[str] = (),
) -> list[str]:
    """One branch, or the chain: its heading, its ranked rows, the rows with a
    hole beneath them, whatever lists close it, and the standing sentence
    last - which is the one sentence that must never be cut, because it is
    what stops a difference being read as a loss."""
    out = ["", "=" * _RULE, f"{title} - {window_words(window)}", "=" * _RULE, ""]
    ranked = [r for r in rows if r.used_base is not None and r.bought_base is not None]
    holed = [r for r in rows if r.used_base is None or r.bought_base is None]
    if not rows:
        out.append("  Nothing to compare in this window.")
    for position, row in enumerate(ranked, start=1):
        out.extend(_row_lines(row, position=f" {position:>2}.", currency=currency))
        out.append("")
    if holed:
        out.append("  Rows with a figure that could not be summed")
        out.append("")
        for row in holed:
            out.extend(_row_lines(row, position="   -", currency=currency))
            out.extend(_measured_lines(row))
            out.append("")
    out.extend(tail)
    out.append("")
    out.append(f"  {standing}")
    return out


def render(blocks: UsageBlocks, *, branch_names: Mapping[str, str], currency: str) -> str:
    """The whole printout: one section per branch, then the chain.

    Branches first and the chain last, so the reader meets each shelf before
    the sum of them and the last thing on the page is the total they have just
    been walked through. Under `--branch` there is one section, that branch's,
    and it carries the lists.
    """
    per_branch: dict[str, list[usage.MaterialRow]] = {}
    source = blocks.branch_rows or [r for r in blocks.rows if r.branch_id is not None]
    for row in source:
        per_branch.setdefault(row.branch_id or "", []).append(row)

    out: list[str] = []
    for branch_id, name in sorted(branch_names.items(), key=lambda pair: (pair[1], pair[0])):
        if blocks.branch_id is not None and branch_id != blocks.branch_id:
            continue
        rows = per_branch.get(branch_id, [])
        window = next((r.window for r in rows), blocks.window)
        out.extend(
            _section(
                name,
                window,
                rows,
                currency=currency,
                standing=blocks.standing,
                tail=_lists(blocks, currency=currency) if blocks.branch_id is not None else (),
            )
        )
    if blocks.branch_id is None:
        chain = [r for r in blocks.rows if r.branch_id is None]
        out.extend(
            _section(
                "Every branch together",
                blocks.window,
                chain,
                currency=currency,
                standing=blocks.standing,
                tail=_lists(blocks, currency=currency),
            )
        )
    return "\n".join(out).rstrip() + "\n"


# --- the command ------------------------------------------------------------


HEADING = "Faida - what the recipes needed against what was bought"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m faida_api.usage_report",
        description=(
            "Print, for one tenant and one period, every material a sold recipe names "
            "with what the recipes needed, what was bought, the recorded difference and "
            "what it costs - one section per branch and then the chain. Read-only: it "
            "makes no change to any row."
        ),
        epilog=(
            "The period defaults to the ratio's 28 days: --to today and --from 27 days "
            "before it. The difference between bought and what the recipes needed is on "
            "the shelf, in the bin or unrecorded; no count says which."
        ),
    )
    parser.add_argument("--tenant", help="the tenant to print (required)")
    parser.add_argument("--from", dest="date_from", help="first day, YYYY-MM-DD")
    parser.add_argument("--to", dest="date_to", help="last day, YYYY-MM-DD")
    parser.add_argument("--branch", help="one branch only; omit for every branch and the chain")
    return parser


def _refuse(sentence: str) -> int:
    print(sentence, file=sys.stderr)
    return 2


def _date(value: str | None, fallback: datetime.date) -> datetime.date | None:
    if value is None:
        return fallback
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None


async def _print(args: argparse.Namespace, period: ratio.Period) -> int:
    """Open a pool on `DATABASE_URL` the way `main.py` does, read, print,
    close. Nothing here writes."""
    db = Database(get_settings().database_url)
    await db.connect()
    try:
        branches = await db.list_branches(tenant_id=args.tenant)
        if not branches:
            return _refuse(f"Tenant {args.tenant} has no branches, so there is nothing to compare.")
        names = {branch["id"]: branch["name"] for branch in branches}
        if args.branch is not None and args.branch not in names:
            return _refuse(f"Branch {args.branch} is not one of this tenant's branches.")

        inputs = await usage_inputs(
            db,
            tenant_id=args.tenant,
            date_from=period.start,
            date_to=period.end,
            branch_id=args.branch,
        )
        blocks = usage_blocks(inputs)
        scope = names[args.branch] if args.branch is not None else "every branch"
        print(HEADING)
        print(
            f"{args.tenant}, {window_words(blocks.window)} ({_plural(period.days, 'day')}), {scope}"
        )
        print(render(blocks, branch_names=names, currency=inputs.currency), end="")
    finally:
        await db.close()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """The command. Returns the exit code rather than raising, so a refusal is
    one plain sentence on stderr and a test can read it."""
    args = _parser().parse_args(list(argv) if argv is not None else None)
    if not args.tenant:
        return _refuse("Say which tenant to print: --tenant <id>.")

    today = datetime.datetime.now(datetime.UTC).date()
    date_to = _date(args.date_to, today)
    if date_to is None:
        return _refuse(f"'{args.date_to}' is not a date. Write it as YYYY-MM-DD, like 2026-08-31.")
    default_from = date_to - datetime.timedelta(days=ratio.DEFAULT_PERIOD_DAYS - 1)
    date_from = _date(args.date_from, default_from)
    if date_from is None:
        return _refuse(
            f"'{args.date_from}' is not a date. Write it as YYYY-MM-DD, like 2026-08-04."
        )
    try:
        # The shipped rule, so a period this refuses is a period `/sales` and
        # the dashboard refuse in the same words (C11.6).
        period, _ = ratio.resolve_period(None, date_from, date_to, today=today)
    except ratio.PeriodError as error:
        return _refuse(f"{error}.")

    return asyncio.run(_print(args, period))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
