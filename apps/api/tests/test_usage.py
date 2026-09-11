"""M12 WP-120: the usage rules, pure (Docs/M12_DECOMPOSITION.md §3 C14,
plan.md §7.2, row 120).

No database: every case builds a branch's sold week, its recipes and its
confirmed purchase lines by hand and checks the figure, the label and the
sentence that made it. The SQL behind `PurchaseLine` is proven against real
Postgres in `test_usage_db.py`, and the block that will serialise these rows
arrives with WP-121.

`test_the_karak_week_to_the_gram` is the worked stage from §2's table and
§3.1's pinned wire shape reproduced number for number - Al Qusais's sugar at
5,708 g needed against 100 kg bought, a difference of 94,292 g worth
AED 216.87 - so the printout, the block and the web lane's mock cannot drift
apart from the arithmetic.
"""

import datetime
from decimal import Decimal

import pytest

from faida_api import contribution, costing, plates, ratio, usage

D = Decimal

QUSAIS = "b-qusais"
NAHDA = "b-nahda"
ROLLA = "b-rolla"
BRANCH_NAMES = {QUSAIS: "Al Qusais", NAHDA: "Al Nahda", ROLLA: "Rolla"}

SUGAR = "i-sugar"
DUST = "i-dust"
EVAP = "i-evap"
CARDAMOM = "i-cardamom"
MILK = "i-milk"
ATTA = "i-atta"
GLOVES = "i-gloves"

CUP = "m-cup"
NIDO = "m-nido"
PARATHA = "m-paratha"
LEMON_MINT = "m-lemon"

PERIOD_FROM = datetime.date(2026, 8, 4)
PERIOD_TO = datetime.date(2026, 8, 31)
WEEK_FROM = datetime.date(2026, 8, 25)
WEEK_TO = datetime.date(2026, 8, 31)
DELIVERY = datetime.date(2026, 8, 31)

MATERIALS = {
    SUGAR: usage.Material(SUGAR, "White Sugar", "g"),
    DUST: usage.Material(DUST, "Karak Tea Dust", "g"),
    EVAP: usage.Material(EVAP, "Evaporated Milk", "ml"),
    CARDAMOM: usage.Material(CARDAMOM, "Cardamom Powder", "g"),
    MILK: usage.Material(MILK, "Milk Powder", "g"),
    ATTA: usage.Material(ATTA, "Atta Flour", "g", has_packs=False),
    GLOVES: usage.Material(GLOVES, "Nitrile Gloves", "pc"),
}

#: The prices in force on the period's last day, as `_menu_context` holds
#: them: the newest costed line among each material's packs.
PRICES = {
    SUGAR: usage.MaterialPrice(SUGAR, D("0.00230000"), "g", DELIVERY, "reliable_with_limitations"),
    DUST: usage.MaterialPrice(DUST, D("0.05500000"), "g", DELIVERY, "reliable_with_limitations"),
    MILK: usage.MaterialPrice(MILK, D("0.02020000"), "g", DELIVERY, "reliable_with_limitations"),
    CARDAMOM: usage.MaterialPrice(
        CARDAMOM, D("0.04800000"), "g", DELIVERY, "reliable_with_limitations"
    ),
    EVAP: usage.MaterialPrice(EVAP, D("0.00468750"), "ml", DELIVERY, "reliable_with_limitations"),
    GLOVES: usage.MaterialPrice(GLOVES, D("0.09"), "pc", DELIVERY, "reliable_with_limitations"),
}


# --- the stage --------------------------------------------------------------


def _component(
    ingredient_id: str,
    name: str,
    qty: str,
    unit: str = "g",
    *,
    share: str | None = None,
) -> contribution.RecipeComponent:
    return contribution.RecipeComponent(
        ingredient_id=ingredient_id,
        ingredient_name=name,
        qty=D(qty),
        unit=unit,
        usable_share=None if share is None else D(share),
    )


def _item(
    menu_item_id: str,
    name: str,
    components: tuple[contribution.RecipeComponent, ...],
    *,
    yield_portions: str = "1",
    version: int | None = 1,
    created_on: datetime.date | None = None,
    price: str = "5.00",
) -> contribution.MenuItem:
    return contribution.MenuItem(
        menu_item_id=menu_item_id,
        name=name,
        plate=plates.Plate(quality=plates.PlateQuality.RELIABLE, cost_per_portion=D("1.000")),
        selling_price=D(price),
        yield_portions=D(yield_portions),
        vat_rate=D("0.05"),
        recipe_version=version,
        components=components,
        recipe_created_on=created_on,
    )


def _karak_cup(**kwargs) -> contribution.MenuItem:
    """One 40-cup pot: 220 g of dust, 2.2 L of evaporated milk, 1.6 kg of
    sugar and a pinch of cardamom (the seeded recipe, `demo_seed.sql:522`)."""
    return _item(
        CUP,
        "Karak Tea (Cup)",
        (
            _component(DUST, "Karak Tea Dust", "220"),
            _component(EVAP, "Evaporated Milk", "2200", "ml"),
            _component(SUGAR, "White Sugar", "1600"),
            _component(CARDAMOM, "Cardamom Powder", "20"),
        ),
        yield_portions="40",
        **kwargs,
    )


def _nido(**kwargs) -> contribution.MenuItem:
    return _item(
        NIDO,
        "Nido Milk Tea",
        (
            _component(MILK, "Milk Powder", "40"),
            _component(EVAP, "Evaporated Milk", "100", "ml"),
            _component(SUGAR, "White Sugar", "12"),
        ),
        price="8.00",
        **kwargs,
    )


def _paratha(**kwargs) -> contribution.MenuItem:
    return _item(
        PARATHA,
        "Paratha",
        (_component(ATTA, "Atta Flour", "2000"),),
        yield_portions="20",
        price="3.00",
        **kwargs,
    )


def _menu(*items: contribution.MenuItem) -> dict[str, contribution.MenuItem]:
    return {item.menu_item_id: item for item in items}


def _sales(
    branch: str,
    item: contribution.MenuItem | None,
    qty_sold: str,
    *,
    refunded: str = "0",
    value: str = "550.00",
    no_qty: int = 0,
    excluded: bool = False,
    till_item_id: str | None = None,
    name: str | None = None,
    day: datetime.date = WEEK_FROM,
) -> contribution.ItemSales:
    return contribution.ItemSales(
        branch_id=branch,
        business_date=day,
        till_item_id=till_item_id or (item.menu_item_id if item else "t-unknown"),
        name=name or (item.name if item else "MYSTERY ITEM"),
        code=None,
        menu_item_id=item.menu_item_id if item else None,
        excluded=excluded,
        qty_sold=D(qty_sold),
        qty_refunded=D(refunded),
        positive_value=D(value),
        refund_value=D(0),
        no_qty_lines=no_qty,
    )


def _line(
    *,
    ingredient_id: str | None,
    raw_name: str,
    qty: str | None,
    pack_size: str | None,
    unit: str | None = None,
    branch: str | None = QUSAIS,
    invoice_id: str = "inv-1",
    invoice_no: str = "GF-20655",
    position: int = 0,
    on: datetime.date = DELIVERY,
    unit_price: str | None = "115.00",
    line_total: str | None = "230.00",
    currency: str = "AED",
    frozen: str | None = None,
    supplier_item_id: str | None = "s-1",
    override: str | None = None,
    canonical_name: str | None = None,
) -> usage.PurchaseLine:
    return usage.PurchaseLine(
        invoice_id=invoice_id,
        invoice_no=invoice_no,
        line_position=position,
        branch_id=branch,
        purchased_on=on,
        supplier_name="Gulf Foods Trading L.L.C.",
        raw_name=raw_name,
        qty=None if qty is None else D(qty),
        unit=unit,
        pack_size=pack_size,
        unit_price=None if unit_price is None else D(unit_price),
        line_total=None if line_total is None else D(line_total),
        currency=currency,
        frozen_factor=None if frozen is None else D(frozen),
        supplier_item_id=supplier_item_id,
        ingredient_id=ingredient_id,
        pack_size_override=override,
        canonical_name=canonical_name,
    )


def _karak_paper() -> list[usage.PurchaseLine]:
    """The one paper inside Al Qusais's window: two sacks of sugar, six bags
    of dust, four sacks of milk powder, four tins of cardamom and two cartons
    of evaporated milk, every line costed and carrying its frozen factor."""
    return [
        _line(
            ingredient_id=SUGAR,
            raw_name="SUGAR 50KG",
            qty="2",
            pack_size="50kg",
            frozen="50000",
            supplier_item_id="s-sugar",
            position=0,
        ),
        _line(
            ingredient_id=DUST,
            raw_name="KARAK TEA DUST 400G",
            qty="6",
            pack_size="400g",
            frozen="400",
            supplier_item_id="s-dust",
            position=1,
            unit_price="22.00",
            line_total="132.00",
        ),
        _line(
            ingredient_id=MILK,
            raw_name="MILK PWDR 2.5KG NIDO",
            qty="4",
            pack_size="2.5kg",
            frozen="2500.0",
            supplier_item_id="s-milk",
            position=2,
            unit_price="50.50",
            line_total="202.00",
        ),
        _line(
            ingredient_id=CARDAMOM,
            raw_name="CARDAMOM PWD 500G",
            qty="4",
            pack_size="500g",
            frozen="500",
            supplier_item_id="s-cardamom",
            position=3,
            unit_price="24.00",
            line_total="96.00",
        ),
        _line(
            ingredient_id=EVAP,
            raw_name="EVAP MILK 48X400ML",
            qty="2",
            pack_size="48x400ml",
            frozen="19200",
            supplier_item_id="s-evap",
            invoice_id="inv-2",
            invoice_no="AM-7902",
            position=0,
            unit_price="90.00",
            line_total="180.00",
        ),
    ]


def _window(
    branch: str = QUSAIS,
    *,
    start: datetime.date | None = WEEK_FROM,
    end: datetime.date | None = WEEK_TO,
    loaded: bool = True,
    pending: tuple[ratio.PendingPaper, ...] = (),
    sales_quality: str = ratio.Quality.RELIABLE.value,
    sales_notes: tuple[str, ...] = (),
) -> usage.BranchWindow:
    return usage.BranchWindow(
        branch_id=branch,
        name=BRANCH_NAMES[branch],
        window_from=start,
        window_to=end,
        sales_loaded=loaded,
        pending=pending,
        sales_quality=sales_quality,
        sales_notes=sales_notes,
    )


def _rows(
    sales: list[contribution.ItemSales],
    menu: dict[str, contribution.MenuItem],
    lines: list[usage.PurchaseLine],
    windows: list[usage.BranchWindow],
    *,
    prices: dict[str, usage.MaterialPrice] | None = None,
    materials: dict[str, usage.Material] | None = None,
    stale: frozenset[str] = frozenset(),
) -> list[usage.MaterialRow]:
    return usage.material_rows(
        contribution.item_rows(sales, menu),
        menu,
        lines,
        windows,
        materials=materials or MATERIALS,
        prices=PRICES if prices is None else prices,
        stale_ingredient_ids=stale,
        date_from=PERIOD_FROM,
        date_to=PERIOD_TO,
    )


def _by(rows: list[usage.MaterialRow], ingredient_id: str, branch: str | None = QUSAIS):
    for row in rows:
        if row.ingredient_id == ingredient_id and row.branch_id == branch:
            return row
    raise AssertionError(f"no row for {ingredient_id} at {branch}")


def _karak_week() -> tuple[
    list[contribution.ItemSales], dict[str, contribution.MenuItem], list[usage.PurchaseLine]
]:
    menu = _menu(_karak_cup(), _nido())
    sales = [
        _sales(QUSAIS, menu[CUP], "110"),
        _sales(QUSAIS, menu[NIDO], "109", value="872.00"),
    ]
    return sales, menu, _karak_paper()


# --- the worked stage (C14.1, C14.2, C14.3, §3.1) ---------------------------


def test_the_karak_week_to_the_gram():
    """§2's worked table and §3.1's wire shape, number for number: 110 cups at
    220 g of dust per 40-cup pot is 605 g, and 5,708 g of sugar against two
    50 kg sacks is a difference of 94,292 g worth AED 216.87."""
    sales, menu, lines = _karak_week()
    rows = _rows(sales, menu, lines, [_window()])

    sugar = _by(rows, SUGAR)
    assert sugar.used_base == D("5708")
    assert sugar.bought_base == D("100000")
    assert sugar.gap_base == D("94292")
    assert sugar.used_words == "5.7 kg"
    assert sugar.bought_words == "100 kg"
    assert sugar.gap_words == "94.3 kg more bought"
    assert sugar.direction == usage.OVER
    assert sugar.money == D("216.87")
    assert sugar.price_per_display_unit == D("2.30")
    assert sugar.display_unit == "kg"
    assert sugar.priced_on == DELIVERY
    assert sugar.purchases == 1
    assert sugar.purchase_dates == 1
    assert "bought 94.3 kg more than its sales needed" in sugar.notes
    assert "at AED 2.30 per kg on 31 Aug 2026" in sugar.notes
    assert "at the current recipe (version 1), at its purchased quantities" in sugar.notes

    assert _by(rows, DUST).used_base == D("605")
    assert _by(rows, DUST).bought_base == D("2400")
    assert _by(rows, EVAP).used_base == D("16950")
    assert _by(rows, EVAP).bought_base == D("38400")
    assert _by(rows, EVAP).bought_words == "38.4 L"
    assert _by(rows, CARDAMOM).used_base == D("55")
    assert _by(rows, CARDAMOM).used_words == "55 g"
    assert _by(rows, MILK).used_base == D("4360")


def test_the_row_equals_the_exact_sum_over_its_dishes():
    """C14.9's pinned lineage: a row's used is the exact sum of its dishes'
    base quantities, each dish's portions are the items panel's."""
    sales, menu, lines = _karak_week()
    rows = _rows(sales, menu, lines, [_window()])
    sugar = _by(rows, SUGAR)

    assert sugar.used_base == sum(d.base_qty for d in sugar.dishes)
    cup = next(d for d in sugar.dishes if d.menu_item_id == CUP)
    assert cup.portions == D("110.000")
    assert cup.per_portion_base == D("40")
    assert cup.base_qty == D("4400")
    assert cup.branch_id == QUSAIS
    nido = next(d for d in sugar.dishes if d.menu_item_id == NIDO)
    assert nido.base_qty == D("1308")
    assert sugar.dishes_counted == 2

    panel = {r.menu_item_id: r.qty_sold for r in contribution.item_rows(sales, menu)}
    assert cup.portions == panel[CUP]


def test_sugar_ranks_first_by_money_with_one_purchase_date():
    """C14.10 and D15: absolute money orders the rows, and one delivery in a
    seven-day window is said to be a delivery and not a rate."""
    sales, menu, lines = _karak_week()
    rows = _rows(sales, menu, lines, [_window()])

    assert rows[0].ingredient_id == SUGAR
    assert [r.money for r in rows] == sorted((r.money for r in rows), key=lambda m: -abs(m or D(0)))
    assert "1 purchase date in this window; a single delivery is not a rate" in rows[0].notes


def test_a_row_carries_its_branchs_clipped_window():
    sales, menu, lines = _karak_week()
    rows = _rows(sales, menu, lines, [_window()])
    assert _by(rows, SUGAR).window == ratio.Window(WEEK_FROM, WEEK_TO)
    assert _by(rows, SUGAR).window.days == 7


# --- the used side (C14.2, D5, D13, D14, P9) --------------------------------


def test_a_usable_share_needs_more_than_the_recipe_asks_for():
    """D13: a component with a conversion yield of 0.85 draws 1/0.85 of its
    quantity from the storeroom, and the plate costs the same amount."""
    menu = _menu(
        _item(
            CUP,
            "Karak Tea (Cup)",
            (_component(SUGAR, "White Sugar", "1600", share="0.85"),),
            yield_portions="40",
        )
    )
    rows = _rows([_sales(QUSAIS, menu[CUP], "40")], menu, [], [_window()])
    row = _by(rows, SUGAR)
    # 40 portions of a 40-cup pot is the whole pot: 1600 / 0.85.
    assert row.used_base == (D("1600") / D("0.85")).quantize(usage.BASE_QUANTUM)
    assert row.dishes[0].usable_share == D("0.85")


def test_the_same_material_drawn_twice_is_one_dish_entry():
    """The real menu draws lemon twice in one dish - 7 g in the marinade and
    20 g as the wedge. Both draws are summed and shown once (C14.2)."""
    lemon = usage.Material("i-lemon", "Lemon", "g")
    menu = _menu(
        _item(
            LEMON_MINT,
            "Lemon Mint",
            (
                _component("i-lemon", "Lemon", "7"),
                _component("i-lemon", "Lemon", "20"),
            ),
        )
    )
    rows = _rows(
        [_sales(QUSAIS, menu[LEMON_MINT], "10")],
        menu,
        [],
        [_window()],
        materials={**MATERIALS, "i-lemon": lemon},
        prices={},
    )
    row = _by(rows, "i-lemon")
    assert len(row.dishes) == 1
    assert row.dishes[0].per_portion_base == D("27")
    assert row.used_base == D("270")


def test_a_line_with_no_quantity_makes_used_null_for_every_material_it_names():
    """C14.2, one shelf below C12.6: a pair that cannot be counted does not
    merely leave an aggregate - a smaller used figure reads as a larger
    difference - so every material that dish's recipe names goes null, with
    the rest exposed as `used_measured` and the dish named."""
    sales, menu, lines = _karak_week()
    sales[0] = _sales(QUSAIS, menu[CUP], "110", no_qty=2)
    rows = _rows(sales, menu, lines, [_window()])

    sugar = _by(rows, SUGAR)
    assert sugar.used_base is None
    assert sugar.used_measured == D("1308")  # the Nido rows that could be counted
    assert sugar.used_measured_words == "1.3 kg"
    assert sugar.gap_base is None and sugar.money is None and sugar.direction is None
    assert sugar.quality is ratio.Quality.INCOMPLETE
    assert (
        "Karak Tea (Cup) has lines with no quantity, so what the recipes needed "
        "cannot be summed" in sugar.notes
    )
    # cardamom is named only by the karak, so it has nothing measured at all
    assert _by(rows, CARDAMOM).used_base is None
    assert _by(rows, CARDAMOM).used_measured == D("0")


def test_a_component_in_cups_makes_that_materials_used_null():
    """The plates sentence, taken from the shipped function (C14.2, C14.11)."""
    menu = _menu(
        _item(
            CUP,
            "Karak Tea (Cup)",
            (
                _component(EVAP, "Evaporated Milk", "1", "cup"),
                _component(SUGAR, "White Sugar", "1600"),
            ),
            yield_portions="40",
        )
    )
    rows = _rows([_sales(QUSAIS, menu[CUP], "40")], menu, [], [_window()])
    evap = _by(rows, EVAP)
    assert evap.used_base is None
    assert "'cup' does not convert to how Evaporated Milk is measured" in evap.notes
    assert evap.quality is ratio.Quality.INCOMPLETE
    # the other material in the same recipe is unaffected
    assert _by(rows, SUGAR).used_base == D("1600")


def test_a_refund_is_named_and_not_subtracted():
    """P9: usage asks what was made, and a refunded karak was usually made and
    poured away. The row says how many were refunded and counts them."""
    menu = _menu(_karak_cup())
    rows = _rows([_sales(QUSAIS, menu[CUP], "110", refunded="2")], menu, [], [_window()])
    row = _by(rows, SUGAR)
    assert row.used_base == D("4400")  # 110, not 108
    assert row.refunded_portions == D("2.000")
    assert "2 portions refunded, counted as made" in row.notes


def test_a_recipe_written_after_the_period_makes_the_row_estimated():
    """D14: a figure computed from a recipe that did not exist yet cannot read
    reliable."""
    menu = _menu(_karak_cup(created_on=datetime.date(2026, 9, 3)))
    rows = _rows([_sales(QUSAIS, menu[CUP], "110")], menu, _karak_paper(), [_window()])
    row = _by(rows, SUGAR)
    assert row.recipe_after_period is True
    assert row.quality is ratio.Quality.ESTIMATED
    assert "recipe written after this period" in row.notes


def test_a_yield_of_three_rounds_once_at_the_dish_and_sums_exactly():
    """D5: a per-portion quantity that never ends still leaves the row equal
    to its parts to the digit."""
    menu = _menu(
        _item(
            CUP,
            "Chai Batch",
            (_component(SUGAR, "White Sugar", "100"),),
            yield_portions="3",
        )
    )
    rows = _rows([_sales(QUSAIS, menu[CUP], "7")], menu, [], [_window()])
    row = _by(rows, SUGAR)
    assert row.dishes[0].base_qty == D("233.333")  # 7 x 100/3, quantized once
    assert row.used_base == sum(d.base_qty for d in row.dishes)
    assert row.used_base == D("233.333")


# --- the bought side (C14.3, D2, D4, D15) -----------------------------------


def test_the_frozen_factor_equals_a_fresh_resolution_on_every_costed_line():
    """D2's drift alarm: the resolver reads the same printed cells `cost_line`
    read, so a costed line's measure equals its frozen basis by construction.
    The day this fails, `units.py` has learned a new spelling and every
    historical bought quantity would have moved under a frozen cost."""
    for line in _karak_paper():
        pack = costing.resolve_pack(
            pack_size=line.pack_size,
            raw_name=line.raw_name,
            unit=line.unit,
            override=line.pack_size_override,
        )
        assert pack is not None, line.raw_name
        assert pack.base_quantity == line.frozen_factor, line.raw_name


def test_the_frozen_factor_wins_when_the_two_disagree():
    """D2: the stored factor is the fact this product never rewrites."""
    line = _line(
        ingredient_id=SUGAR,
        raw_name="SUGAR 50KG",
        qty="2",
        pack_size="50kg",
        frozen="25000",
    )
    measured = usage.measure(line)
    assert measured.factor == D("25000")
    assert measured.factor_source == usage.FROZEN
    assert measured.base_qty == D("50000")
    assert measured.pack is not None and measured.pack.base_quantity == D("50000")


def test_a_line_with_no_price_is_measured_when_it_reached_a_product():
    """C14.3: price and currency are not filters - the goods arrived."""
    line = _line(
        ingredient_id=SUGAR,
        raw_name="SUGAR 50KG",
        qty="1",
        pack_size="50kg",
        unit_price=None,
        line_total=None,
        supplier_item_id="s-sugar",
    )
    rows = _rows([], _menu(), [line], [_window(loaded=False)])
    assert usage.measure(line).base_qty == D("50000")
    assert rows == []  # no sold recipe names sugar on this stage


def test_a_foreign_paper_is_counted_by_quantity_and_named():
    menu = _menu(_karak_cup())
    line = _line(
        ingredient_id=SUGAR,
        raw_name="SUGAR 50KG",
        qty="1",
        pack_size="50kg",
        frozen="50000",
        currency="USD",
        supplier_item_id="s-sugar",
        invoice_id="inv-usd",
    )
    rows = _rows([_sales(QUSAIS, menu[CUP], "40")], menu, [line], [_window()])
    row = _by(rows, SUGAR)
    assert row.bought_base == D("50000")
    assert row.foreign_papers == 1
    assert "1 paper billed in USD, counted by quantity" in row.notes
    assert usage.unmapped_packs([line]).lines == 0


def test_an_unmeasured_line_makes_bought_null_with_the_rest_measured():
    menu = _menu(_karak_cup())
    lines = [
        _line(
            ingredient_id=SUGAR,
            raw_name="SUGAR 50KG",
            qty="1",
            pack_size="50kg",
            frozen="50000",
            supplier_item_id="s-sugar",
        ),
        _line(
            ingredient_id=SUGAR,
            raw_name="SUGAR",
            qty="1",
            pack_size="1 ctn",
            position=1,
            supplier_item_id="s-sugar",
        ),
    ]
    rows = _rows([_sales(QUSAIS, menu[CUP], "40")], menu, lines, [_window()])
    row = _by(rows, SUGAR)
    assert row.bought_base is None
    assert row.bought_measured == D("50000")
    assert row.bought_measured_words == "50 kg"
    assert row.unmeasured_lines == 1
    assert row.gap_base is None and row.money is None
    assert row.quality is ratio.Quality.INCOMPLETE
    assert "1 line could not be measured - see Can't be costed yet" in row.notes
    assert row.lines[1].blocked == costing.Blocked.BARE_CONTAINER.value


def test_an_override_makes_the_purchase_half_estimated():
    menu = _menu(_karak_cup())
    line = _line(
        ingredient_id=SUGAR,
        raw_name="SUGAR",
        qty="2",
        pack_size="1 ctn",
        override="25kg",
        supplier_item_id="s-sugar",
    )
    rows = _rows([_sales(QUSAIS, menu[CUP], "40")], menu, [line], [_window()])
    row = _by(rows, SUGAR)
    assert row.bought_base == D("50000")
    assert row.quality is ratio.Quality.ESTIMATED
    assert "a pack size you entered measures 1 line" in row.notes
    assert row.lines[0].pack_source == costing.PackSource.OVERRIDE.value


def test_a_return_nets_by_its_sign_and_is_not_a_second_purchase_date():
    """D15: a sack on Monday and a credit note on Tuesday is one purchase
    date, because the rule's reason is time and a return is not a delivery."""
    menu = _menu(_karak_cup())
    lines = [
        _line(
            ingredient_id=SUGAR,
            raw_name="SUGAR 50KG",
            qty="2",
            pack_size="50kg",
            frozen="50000",
            supplier_item_id="s-sugar",
            on=datetime.date(2026, 8, 26),
        ),
        _line(
            ingredient_id=SUGAR,
            raw_name="SUGAR 50KG",
            qty="-1",
            pack_size="50kg",
            frozen="50000",
            supplier_item_id="s-sugar",
            invoice_id="inv-cn",
            invoice_no="GF-CN-1",
            on=datetime.date(2026, 8, 27),
        ),
    ]
    rows = _rows([_sales(QUSAIS, menu[CUP], "40")], menu, lines, [_window()])
    row = _by(rows, SUGAR)
    assert row.bought_base == D("50000")
    assert row.returns == 1
    assert row.purchases == 2
    assert row.purchase_dates == 1
    assert "1 return" in row.notes
    assert "1 purchase date in this window; a single delivery is not a rate" in row.notes


def test_two_papers_on_one_morning_are_one_purchase_date():
    """D4: two suppliers' papers on one morning are one delivery moment."""
    menu = _menu(_karak_cup())
    lines = [
        _line(
            ingredient_id=SUGAR,
            raw_name="SUGAR 50KG",
            qty="1",
            pack_size="50kg",
            frozen="50000",
            supplier_item_id="s-sugar",
        ),
        _line(
            ingredient_id=SUGAR,
            raw_name="SUGAR 25KG",
            qty="1",
            pack_size="25kg",
            frozen="25000",
            supplier_item_id="s-sugar",
            invoice_id="inv-b",
            invoice_no="AM-1",
        ),
    ]
    rows = _rows([_sales(QUSAIS, menu[CUP], "40")], menu, lines, [_window()])
    row = _by(rows, SUGAR)
    assert row.purchases == 2
    assert row.purchase_dates == 1
    assert "1 purchase date in this window; a single delivery is not a rate" in row.notes


def test_a_paper_outside_the_branchs_window_is_not_counted():
    menu = _menu(_karak_cup())
    line = _line(
        ingredient_id=SUGAR,
        raw_name="SUGAR 50KG",
        qty="2",
        pack_size="50kg",
        frozen="50000",
        supplier_item_id="s-sugar",
        on=datetime.date(2026, 8, 10),
    )
    rows = _rows([_sales(QUSAIS, menu[CUP], "40")], menu, [line], [_window()])
    row = _by(rows, SUGAR)
    assert row.bought_base == D("0")
    assert row.direction == usage.UNDER
    assert "no purchases in this window, 25-31 Aug" in row.notes
    assert row.quality is ratio.Quality.INCOMPLETE


# --- placement (D3, D6, D11, D12, C14.9) ------------------------------------


def test_no_pack_mapped_gives_a_row_with_used_and_no_bought():
    menu = _menu(_paratha())
    rows = _rows([_sales(QUSAIS, menu[PARATHA], "139")], menu, [], [_window()])
    row = _by(rows, ATTA)
    assert row.used_base == D("13900")
    assert row.used_words == "13.9 kg"
    assert row.bought_base is None
    assert row.gap_base is None and row.money is None and row.direction is None
    assert row.quality is ratio.Quality.INCOMPLETE
    assert "no supplier product is mapped to Atta Flour yet" in row.notes


def test_a_material_no_sold_recipe_names_is_listed_apart_and_out_of_the_ranking():
    """D11: gloves are a purchase with nothing to compare against."""
    sales, menu, lines = _karak_week()
    lines.append(
        _line(
            ingredient_id=GLOVES,
            raw_name="NITRILE GLOVES 100PC",
            qty="20",
            pack_size="100pc",
            frozen="100",
            supplier_item_id="s-gloves",
            invoice_id="inv-3",
            line_total="180.00",
        )
    )
    rows = _rows(sales, menu, lines, [_window()])
    assert all(r.ingredient_id != GLOVES for r in rows)

    listed = usage.unused_materials(
        lines,
        {c.ingredient_id for item in menu.values() for c in item.components},
        materials=MATERIALS,
        prices=PRICES,
        windows=[_window()],
        branch_id=QUSAIS,
        date_from=PERIOD_FROM,
        date_to=PERIOD_TO,
    )
    assert len(listed) == 1
    assert listed[0].ingredient_name == "Nitrile Gloves"
    assert listed[0].bought_base == D("2000")
    assert listed[0].bought_words == "2,000 pieces"
    assert listed[0].money == D("180.00")
    assert listed[0].sentence == "bought, not in any sold recipe"


def test_an_unmapped_packs_line_is_reported_with_its_printed_spend_and_never_in_a_row():
    """D6, D21: a purchase of something is never dropped, and the spend is the
    printed line totals in the tenant's currency - a foreign line is counted
    and named, never converted."""
    lines = [
        _line(
            ingredient_id=None,
            raw_name="CLEANING FLUID 5L",
            qty="2",
            pack_size="5L",
            supplier_item_id="s-clean",
            line_total="120.00",
        ),
        _line(
            ingredient_id=None,
            raw_name="CLEANING FLUID 5L",
            qty="1",
            pack_size="5L",
            supplier_item_id="s-clean",
            position=1,
            line_total="67.00",
        ),
        _line(
            ingredient_id=None,
            raw_name="OLIVE OIL 5L",
            qty="1",
            pack_size="5L",
            supplier_item_id="s-oil",
            position=2,
            line_total="200.00",
            currency="USD",
        ),
    ]
    block = usage.unmapped_packs(lines)
    assert block.lines == 3
    assert block.packs == 2
    assert block.spend == D("187.00")
    assert block.foreign_lines == 1
    assert block.sentence == (
        "3 purchase lines on 2 products have no material yet, "
        "AED 187 on the printed line totals, 1 of them billed in USD"
    )
    assert _rows([], _menu(), lines, [_window()]) == []


def test_one_unmapped_line_says_has_and_two_say_have():
    """The sentence agrees with the count it carries. It is the first line an
    owner reads about purchases the panel could not place, and "1 purchase
    line ... have no material yet" reads as a typo in the product."""
    one = usage.unmapped_packs(
        [
            _line(
                ingredient_id=None,
                raw_name="CLEANING FLUID 5L",
                qty="2",
                pack_size="5L",
                supplier_item_id="s-clean",
                line_total="120.00",
            )
        ]
    )
    assert one.sentence == (
        "1 purchase line on 1 product has no material yet, AED 120 on the printed line totals"
    )


def test_a_line_whose_quantity_cell_was_never_read_is_unmeasured_and_never_zero():
    """`invoice_lines.qty` is nullable, and the confirm door costs no line
    without one - so a paper can carry a readable pack and no quantity at all.
    The line delivered an unknown amount: the row's bought figure is withheld
    with the count named and the measured part under its own name, and nothing
    is counted as zero, which would read as a delivery of nothing."""
    sales, menu, lines = _karak_week()
    lines.append(
        _line(
            ingredient_id=SUGAR,
            raw_name="SUGAR 50KG",
            qty=None,
            pack_size="50kg",
            supplier_item_id="s-sugar",
            position=9,
            unit_price=None,
            line_total=None,
        )
    )
    rows = _rows(sales, menu, lines, [_window()])
    sugar = _by(rows, SUGAR)

    assert sugar.bought_base is None
    assert sugar.bought_measured == D("100000")
    assert sugar.bought_measured_words == "100 kg"
    assert sugar.unmeasured_lines == 1
    assert sugar.quality is ratio.Quality.INCOMPLETE
    assert "1 line could not be measured - see Can't be costed yet" in sugar.notes
    unread = next(entry for entry in sugar.lines if entry.qty is None)
    assert unread.base_qty is None
    assert unread.measured is False
    assert unread.blocked == "missing_quantity"


def test_a_line_that_reached_no_product_is_an_orphan_with_its_paper():
    """D3: the confirm door creates no product for a foreign paper and none
    for a line with no price, and a product is the only path to a material."""
    lines = [
        _line(
            ingredient_id=None,
            supplier_item_id=None,
            raw_name="SUGAR 50KG",
            qty="1",
            pack_size="50kg",
            currency="USD",
            invoice_id="inv-usd",
            invoice_no="LSF-9",
        ),
        _line(
            ingredient_id=None,
            supplier_item_id=None,
            raw_name="RICE 5KG",
            qty="1",
            pack_size="5kg",
            unit_price=None,
            line_total=None,
            invoice_id="inv-noprice",
            invoice_no="GF-7",
        ),
    ]
    block = usage.orphans(lines)
    assert block.lines == 2
    assert block.foreign == 1
    assert block.no_price == 1
    assert block.sentence == "2 lines reached no product: 1 billed in USD, 1 with no price"
    assert {p.invoice_no for p in block.papers} == {"LSF-9", "GF-7"}
    assert usage.unmapped_packs(lines).lines == 0
    assert _rows([], _menu(), lines, [_window()]) == []


def test_a_paper_with_no_branch_is_outside_every_row_and_every_chain_figure():
    """C14.9: unassigned papers lie in the whole period while branch rows lie
    in clipped windows, so a sum would add two spans."""
    sales, menu, lines = _karak_week()
    lines.append(
        _line(
            ingredient_id=SUGAR,
            raw_name="SUGAR 50KG",
            qty="1",
            pack_size="50kg",
            frozen="50000",
            supplier_item_id="s-sugar",
            branch=None,
            invoice_id="inv-nobranch",
            invoice_no="GF-NB",
        )
    )
    rows = _rows(sales, menu, lines, [_window()])
    assert _by(rows, SUGAR).bought_base == D("100000")

    held = usage.unassigned_rows(lines, materials=MATERIALS)
    assert len(held) == 1
    assert held[0].ingredient_name == "White Sugar"
    assert held[0].bought_base == D("50000")
    assert held[0].bought_words == "50 kg"
    assert held[0].papers == 1

    chain = usage.chain_material_rows(
        rows,
        materials=MATERIALS,
        prices=PRICES,
        branch_names=BRANCH_NAMES,
        unassigned=held,
        date_from=PERIOD_FROM,
        date_to=PERIOD_TO,
    )
    sugar = next(r for r in chain if r.ingredient_id == SUGAR)
    assert sugar.bought_base == D("100000")
    assert "1 paper with no branch holds 50 kg of White Sugar, not counted here" in sugar.notes


def test_a_branch_with_purchases_and_no_sales_keeps_purchase_only_rows():
    """D12: a hole is named, never dropped. The bought figure is real and the
    used side is not there to compare it against."""
    sales, menu, lines = _karak_week()
    lines.append(
        _line(
            ingredient_id=SUGAR,
            raw_name="SUGAR 50KG",
            qty="1",
            pack_size="50kg",
            frozen="50000",
            supplier_item_id="s-sugar",
            branch=ROLLA,
            invoice_id="inv-rolla",
        )
    )
    rolla = _window(
        ROLLA,
        loaded=False,
        sales_quality=ratio.Quality.UNAVAILABLE.value,
        sales_notes=("no sales loaded 25-31 Aug",),
    )
    rows = _rows(sales, menu, lines, [_window(), rolla])
    row = _by(rows, SUGAR, ROLLA)
    assert row.bought_base == D("50000")
    assert row.used_base is None and row.gap_base is None and row.money is None
    assert row.quality is ratio.Quality.UNAVAILABLE
    assert any("no sales loaded" in note for note in row.notes)

    chain = usage.chain_material_rows(
        rows,
        materials=MATERIALS,
        prices=PRICES,
        branch_names=BRANCH_NAMES,
        date_from=PERIOD_FROM,
        date_to=PERIOD_TO,
    )
    sugar = next(r for r in chain if r.ingredient_id == SUGAR)
    assert sugar.bought_base == D("150000")  # D12: the purchase-only bought is in
    assert sugar.used_base == D("5708")
    assert sugar.quality is ratio.Quality.UNAVAILABLE
    assert "Rolla: no sales loaded" in sugar.notes


# --- the gap, the money and the three halves (C14.5, C14.7, C14.8) ----------


def test_under_carries_the_two_causes_and_never_calls_it_anything_else():
    menu = _menu(_karak_cup())
    line = _line(
        ingredient_id=SUGAR,
        raw_name="SUGAR 1KG",
        qty="1",
        pack_size="1kg",
        frozen="1000",
        supplier_item_id="s-sugar",
    )
    rows = _rows([_sales(QUSAIS, menu[CUP], "105")], menu, [line], [_window()])
    row = _by(rows, SUGAR)
    assert row.used_base == D("4200")
    assert row.gap_base == D("-3200")
    assert row.direction == usage.UNDER
    assert row.gap_words == "3.2 kg more needed"
    assert (
        "its sales needed 3.2 kg more than was bought - either stock from before this "
        "window was used, or a recipe quantity or a pack size is wrong" in row.notes
    )


def test_an_even_row_says_so():
    menu = _menu(_karak_cup())
    line = _line(
        ingredient_id=SUGAR,
        raw_name="SUGAR 1KG",
        qty="4",
        pack_size="1kg",
        frozen="1000",
        supplier_item_id="s-sugar",
    )
    rows = _rows([_sales(QUSAIS, menu[CUP], "100")], menu, [line], [_window()])
    row = _by(rows, SUGAR)
    assert row.gap_base == D("0")
    assert row.direction == usage.EVEN
    assert row.gap_words == "no difference"
    assert "bought exactly what its sales needed" in row.notes


def test_a_material_with_no_price_carries_the_quantity_and_no_money():
    sales, menu, lines = _karak_week()
    rows = _rows(sales, menu, lines, [_window()], prices={})
    row = _by(rows, SUGAR)
    assert row.gap_base == D("94292")
    assert row.money is None
    assert row.price_per_display_unit is None and row.priced_on is None
    assert "no price to value it at" in row.notes
    # ranked after every row that has money - here, all of them lack it
    assert usage.rank(rows)[0].gap_base == D("94292")


def test_a_stale_price_makes_the_money_estimated_and_says_so():
    """D17: the material's newest purchase could not be costed, so the figure
    is real and not current."""
    sales, menu, lines = _karak_week()
    rows = _rows(sales, menu, lines, [_window()], stale=frozenset({SUGAR}))
    row = _by(rows, SUGAR)
    assert row.money == D("216.87")
    assert row.price_quality == ratio.Quality.ESTIMATED.value
    assert row.quality is ratio.Quality.ESTIMATED
    assert "at an estimated AED 2.30 per kg on 31 Aug 2026" in row.notes


def test_a_pending_paper_makes_the_purchase_half_estimated_in_the_ratios_words():
    sales, menu, lines = _karak_week()
    pending = (
        ratio.PendingPaper(
            invoice_id="inv-p",
            supplier_name="Gulf Foods Trading L.L.C.",
            invoice_no="GF-9",
            status="awaiting_confirm",
            placed_on=datetime.date(2026, 8, 30),
            undated=False,
        ),
    )
    rows = _rows(sales, menu, lines, [_window(pending=pending)])
    row = _by(rows, SUGAR)
    assert row.quality is ratio.Quality.ESTIMATED
    assert "1 invoice awaiting confirm" in row.notes


def test_the_three_halves_take_the_worst_word_and_never_verified():
    """C14.8: the sales half is `BranchRow`'s and is never re-worded; the
    purchase half is this module's own and is about quantities; the material
    half is about the recipe and the pack."""
    sales, menu, lines = _karak_week()
    incomplete_sales = _window(
        sales_quality=ratio.Quality.INCOMPLETE.value,
        sales_notes=("2 of 7 days have no sales",),
    )
    rows = _rows(sales, menu, lines, [incomplete_sales], stale=frozenset({SUGAR}))
    row = _by(rows, SUGAR)
    # incomplete (sales) is worse than estimated (the stale price)
    assert row.quality is ratio.Quality.INCOMPLETE
    assert "2 of 7 days have no sales" in row.notes

    clean = _rows(sales, menu, lines, [_window()])
    assert _by(clean, SUGAR).quality is ratio.Quality.RELIABLE
    assert all(r.quality.value != "verified" for r in clean)


# --- the chain (C14.9, D10, D19) --------------------------------------------


def _two_branch_stage():
    menu = _menu(_karak_cup(), _nido())
    sales = [
        _sales(QUSAIS, menu[CUP], "110"),
        _sales(QUSAIS, menu[NIDO], "109", value="872.00"),
        _sales(ROLLA, menu[CUP], "40", day=datetime.date(2026, 8, 30)),
    ]
    lines = _karak_paper() + [
        _line(
            ingredient_id=SUGAR,
            raw_name="SUGAR 50KG",
            qty="1",
            pack_size="50kg",
            frozen="50000",
            supplier_item_id="s-sugar",
            branch=ROLLA,
            invoice_id="inv-rolla",
            on=datetime.date(2026, 8, 31),
        )
    ]
    windows = [
        _window(),
        _window(ROLLA, start=datetime.date(2026, 8, 30), end=datetime.date(2026, 8, 31)),
    ]
    return sales, menu, lines, windows


def test_the_chain_sums_exactly_the_branches_it_names_and_names_their_windows():
    sales, menu, lines, windows = _two_branch_stage()
    rows = _rows(sales, menu, lines, windows)
    chain = usage.chain_material_rows(
        rows,
        materials=MATERIALS,
        prices=PRICES,
        branch_names=BRANCH_NAMES,
        date_from=PERIOD_FROM,
        date_to=PERIOD_TO,
    )
    sugar = next(r for r in chain if r.ingredient_id == SUGAR)
    branch_rows = [r for r in rows if r.ingredient_id == SUGAR]
    assert sugar.bought_base == sum(r.bought_base for r in branch_rows)
    assert sugar.used_base == sum(r.used_base for r in branch_rows)
    assert sugar.bought_base == D("150000")
    assert sugar.used_base == D("7308")  # 5,708 at Al Qusais + 1,600 at Rolla
    assert sugar.branch_id is None
    assert sugar.lines == () and sugar.dishes == ()
    assert "over 25-31 Aug at Al Qusais and 30-31 Aug at Rolla" in sugar.notes
    assert sugar.window == ratio.Window(PERIOD_FROM, PERIOD_TO)


def test_the_chain_names_a_branch_it_left_out():
    sales, menu, lines, windows = _two_branch_stage()
    sales[2] = _sales(ROLLA, menu[CUP], "40", day=datetime.date(2026, 8, 30), no_qty=1)
    rows = _rows(sales, menu, lines, windows)
    chain = usage.chain_material_rows(
        rows,
        materials=MATERIALS,
        prices=PRICES,
        branch_names=BRANCH_NAMES,
        date_from=PERIOD_FROM,
        date_to=PERIOD_TO,
    )
    sugar = next(r for r in chain if r.ingredient_id == SUGAR)
    assert sugar.used_base == D("5708")  # Al Qusais alone
    assert sugar.bought_base == D("150000")  # both branches still bought
    assert sugar.quality is ratio.Quality.INCOMPLETE
    assert "Rolla not included: lines with no quantity" in sugar.notes


# --- recipe coverage (C14.2, P4, D20) ---------------------------------------


def test_recipe_coverage_is_computed_from_the_raw_rows_and_names_the_dishes():
    menu = _menu(_karak_cup(), _item(NIDO, "Nido Milk Tea", ()))
    sales = [
        _sales(QUSAIS, menu[CUP], "110", value="940.00"),
        _sales(QUSAIS, menu[NIDO], "5", value="60.00"),
        _sales(QUSAIS, None, "3", value="0.00", till_item_id="t-mystery"),
    ]
    coverage = usage.recipe_coverage(sales, menu)
    assert coverage.recipes_pct == D("94.0")
    assert coverage.dishes_without_recipe == 1
    assert coverage.unmapped_names == 1
    assert coverage.sentence.startswith(
        "recipes cover 94% of this branch's sales value; 1 dish sold has no recipe"
    )


def test_the_coverage_line_names_the_orphan_purchases_too():
    """D20: the rows above the line admit an unplaced purchase as well as an
    unfollowed sale, so the count comes from `orphans` and the words from
    here."""
    menu = _menu(_karak_cup(), _item(NIDO, "Nido Milk Tea", ()))
    sales = [
        _sales(QUSAIS, menu[CUP], "110", value="940.00"),
        _sales(QUSAIS, menu[NIDO], "5", value="60.00"),
    ]
    orphan = _line(
        ingredient_id=None,
        supplier_item_id=None,
        raw_name="RICE 5KG",
        qty="1",
        pack_size="5kg",
        unit_price=None,
        line_total=None,
    )
    block = usage.orphans([orphan])
    coverage = usage.recipe_coverage(sales, menu, orphan_lines=block.lines)
    assert coverage.sentence == (
        "recipes cover 94% of this branch's sales value; 1 dish sold has no recipe; "
        "1 purchase line reached no product"
    )


def test_an_excluded_till_name_leaves_the_coverage_denominator():
    menu = _menu(_karak_cup())
    sales = [
        _sales(QUSAIS, menu[CUP], "110", value="940.00"),
        _sales(QUSAIS, None, "1", value="500.00", till_item_id="t-tips", excluded=True),
    ]
    assert usage.recipe_coverage(sales, menu).recipes_pct == D("100.0")


# --- what was left out, and the order of the rows ---------------------------


def test_left_out_counts_the_four_holes():
    menu = _menu(_karak_cup(), _item(NIDO, "Nido Milk Tea", ()))
    sales = [
        _sales(QUSAIS, menu[CUP], "110", no_qty=2),
        _sales(QUSAIS, menu[NIDO], "5", value="60.00"),
    ]
    lines = [
        _line(
            ingredient_id=SUGAR,
            raw_name="SUGAR",
            qty="1",
            pack_size="1 ctn",
            supplier_item_id="s-sugar",
        )
    ]
    windows = [_window(), _window(ROLLA, loaded=False)]
    block = usage.left_out(contribution.item_rows(sales, menu), lines, windows, menu)
    assert block.items_without_quantity == 1
    assert block.items_without_recipe == 1
    assert block.unmeasured_lines == 1
    assert block.branches_without_sales == 1


def test_rows_with_no_money_rank_by_quantity_and_a_hole_ranks_last():
    """C14.10: money, then the quantity when there is no price, then the rows
    that carry a hole - which show their reason and no number in its place."""
    menu = _menu(_karak_cup(), _paratha())
    sales = [
        _sales(QUSAIS, menu[CUP], "110"),
        _sales(QUSAIS, menu[PARATHA], "139", value="417.00"),
    ]
    prices = {SUGAR: PRICES[SUGAR]}
    rows = _rows(sales, menu, _karak_paper(), [_window()], prices=prices)
    assert rows[0].ingredient_id == SUGAR and rows[0].money is not None
    priced = [r for r in rows if r.money is not None]
    unpriced = [r for r in rows if r.money is None and r.gap_base is not None]
    holes = [r for r in rows if r.gap_base is None]
    assert rows[: len(priced)] == priced
    assert rows[len(priced) : len(priced) + len(unpriced)] == unpriced
    assert rows[-len(holes) :] == holes
    assert [r.ingredient_id for r in holes] == [ATTA]
    assert [abs(r.gap_base) for r in unpriced] == sorted(
        (abs(r.gap_base) for r in unpriced), reverse=True
    )


# --- the words (C14.6) ------------------------------------------------------


@pytest.mark.parametrize(
    ("qty", "unit", "expected"),
    [
        ("97", "g", "97 g"),
        ("605", "g", "605 g"),
        ("999", "g", "999 g"),
        ("1000", "g", "1 kg"),
        ("5708", "g", "5.7 kg"),
        ("100000", "g", "100 kg"),
        ("94292", "g", "94.3 kg"),
        ("450", "ml", "450 ml"),
        ("27500", "ml", "27.5 L"),
        ("38400", "ml", "38.4 L"),
        ("1200", "pc", "1,200 pieces"),
        ("1", "pc", "1 piece"),
        ("0", "g", "0 g"),
        ("-3200", "g", "-3.2 kg"),
    ],
)
def test_quantity_words(qty, unit, expected):
    assert usage.quantity_words(D(qty), unit) == expected


def test_the_standing_sentence_is_the_contracts_words():
    assert usage.STANDING_SENTENCE == (
        "The difference between bought and what the recipes needed is on the shelf, "
        "in the bin or unrecorded; no count says which."
    )


# --- the forbidden phrases (C14.5) ------------------------------------------

FORBIDDEN = (
    "variance",
    "waste",
    "theft",
    "shrinkage",
    "loss",
    "negative stock",
    "stock on hand",
    "where money is sitting",
    "verified",
)


def _every_sentence() -> list[str]:
    """A stage that exercises every branch of the module, and every sentence
    it composed on the way. This calls the module; it is not a grep of code."""
    menu = _menu(
        _karak_cup(created_on=datetime.date(2026, 9, 3)),
        _nido(),
        _paratha(),
        _item(LEMON_MINT, "Lemon Mint", ()),
    )
    sales = [
        _sales(QUSAIS, menu[CUP], "110", refunded="2"),
        _sales(QUSAIS, menu[NIDO], "109", value="872.00", no_qty=1),
        _sales(QUSAIS, menu[PARATHA], "139", value="417.00"),
        _sales(QUSAIS, menu[LEMON_MINT], "4", value="40.00"),
        _sales(QUSAIS, None, "3", value="30.00", till_item_id="t-mystery"),
        _sales(ROLLA, menu[CUP], "40", day=datetime.date(2026, 8, 30)),
    ]
    lines = _karak_paper() + [
        # a return on a second date, a bare carton, an override, a foreign
        # paper, an unmapped pack, an orphan, a no-branch paper and gloves
        _line(
            ingredient_id=SUGAR,
            raw_name="SUGAR 50KG",
            qty="-1",
            pack_size="50kg",
            frozen="50000",
            supplier_item_id="s-sugar",
            invoice_id="inv-cn",
            on=datetime.date(2026, 8, 30),
        ),
        _line(
            ingredient_id=DUST,
            raw_name="TEA DUST",
            qty="1",
            pack_size="1 ctn",
            supplier_item_id="s-dust",
            invoice_id="inv-4",
        ),
        _line(
            ingredient_id=MILK,
            raw_name="MILK PWDR",
            qty="1",
            pack_size="1 ctn",
            override="2.5kg",
            supplier_item_id="s-milk",
            invoice_id="inv-5",
        ),
        _line(
            ingredient_id=CARDAMOM,
            raw_name="CARDAMOM PWD 500G",
            qty="1",
            pack_size="500g",
            frozen="500",
            supplier_item_id="s-cardamom",
            currency="USD",
            invoice_id="inv-usd",
        ),
        _line(
            ingredient_id=None,
            raw_name="CLEANING FLUID 5L",
            qty="2",
            pack_size="5L",
            supplier_item_id="s-clean",
            line_total="187.00",
            invoice_id="inv-6",
        ),
        _line(
            ingredient_id=None,
            supplier_item_id=None,
            raw_name="RICE 5KG",
            qty="1",
            pack_size="5kg",
            unit_price=None,
            line_total=None,
            invoice_id="inv-7",
        ),
        _line(
            ingredient_id=SUGAR,
            raw_name="SUGAR 50KG",
            qty="1",
            pack_size="50kg",
            frozen="50000",
            supplier_item_id="s-sugar",
            branch=None,
            invoice_id="inv-8",
        ),
        _line(
            ingredient_id=GLOVES,
            raw_name="NITRILE GLOVES 100PC",
            qty="20",
            pack_size="100pc",
            frozen="100",
            supplier_item_id="s-gloves",
            invoice_id="inv-9",
            line_total="180.00",
        ),
        # a branch with a delivery and no sales loaded at all (D12)
        _line(
            ingredient_id=SUGAR,
            raw_name="SUGAR 50KG",
            qty="1",
            pack_size="50kg",
            frozen="50000",
            supplier_item_id="s-sugar",
            branch=NAHDA,
            invoice_id="inv-10",
        ),
    ]
    windows = [
        _window(
            pending=(
                ratio.PendingPaper(
                    invoice_id="inv-p",
                    supplier_name="Gulf Foods",
                    invoice_no="GF-9",
                    status="needs_review",
                    placed_on=datetime.date(2026, 8, 29),
                    undated=False,
                ),
            ),
            sales_quality=ratio.Quality.INCOMPLETE.value,
            sales_notes=("2 of 7 days have no sales",),
        ),
        _window(ROLLA, start=datetime.date(2026, 8, 30), end=datetime.date(2026, 8, 31)),
        _window(
            NAHDA,
            loaded=False,
            sales_quality=ratio.Quality.UNAVAILABLE.value,
            sales_notes=("no sales loaded and no confirmed purchases 25-31 Aug",),
        ),
    ]
    rows = _rows(sales, menu, lines, windows, stale=frozenset({EVAP}))
    held = usage.unassigned_rows(lines, materials=MATERIALS)
    chain = usage.chain_material_rows(
        rows,
        materials=MATERIALS,
        prices=PRICES,
        branch_names=BRANCH_NAMES,
        unassigned=held,
        stale_ingredient_ids=frozenset({EVAP}),
        date_from=PERIOD_FROM,
        date_to=PERIOD_TO,
    )
    named = {c.ingredient_id for item in menu.values() for c in item.components}
    blocks = [
        *rows,
        *chain,
        *held,
        *usage.unused_materials(
            lines,
            named,
            materials=MATERIALS,
            prices=PRICES,
            windows=windows,
            date_from=PERIOD_FROM,
            date_to=PERIOD_TO,
        ),
        usage.unmapped_packs(lines),
        usage.orphans(lines),
        usage.recipe_coverage(sales, menu),
    ]
    assert (
        usage.left_out(contribution.item_rows(sales, menu), lines, windows, menu).unmeasured_lines
        == 1
    )
    return usage.sentences(*blocks)


def test_no_sentence_the_module_can_compose_uses_a_forbidden_word():
    """C14.5: bought minus used is a recorded difference. It is not stock
    lost, it is not stock on hand, and it never claims to locate money."""
    said = _every_sentence()
    assert len(said) > 60, "the stage must exercise every branch"
    for sentence in said:
        lowered = sentence.lower()
        for phrase in FORBIDDEN:
            assert phrase not in lowered, f"{phrase!r} in {sentence!r}"


def test_the_stage_speaks_every_kind_of_sentence():
    """The guard on the guard: the forbidden-phrase test would pass on an
    empty list, so this pins that the same stage really did compose the
    sentences that matter."""
    said = " | ".join(_every_sentence())
    for phrase in (
        "The difference between bought and what the recipes needed",
        "more than its sales needed",
        "a single delivery is not a rate",
        "no supplier product is mapped to Atta Flour yet",
        "could not be measured",
        "a pack size you entered measures",
        "counted by quantity",
        "1 return",
        "portions refunded, counted as made",
        "recipe written after this period",
        "at an estimated AED",
        "recipes cover",
        "no material yet",
        "reached no product",
        "not counted here",
        "no sales loaded",
        "invoice held for review",
        "no purchases in this window",
        "bought, not in any sold recipe",
    ):
        assert phrase in said, phrase
