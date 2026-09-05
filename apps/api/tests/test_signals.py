"""M9 WP-91: the three signals, pure (Docs/M9_DECOMPOSITION.md §3 C13, row 91).

No database: every case builds a branch's item days and its costed menu by
hand, runs them through the shipped `contribution` functions so the rows are
the real arithmetic, and checks which signal fires, what it says and what it
is worth. The price moves are `menu.PriceMove` rows built by hand here and,
in the last section, produced by `menu.price_moves` itself from raw pairs -
the pure half of the route `test_price_moves.py` proves against Postgres.

The thresholds are tested on their **inclusive** boundary and one unit under
it, because a threshold that fires at 10.1 and not at 10.0 is a different
rule from the one pinned.
"""

import datetime
from decimal import Decimal

from faida_api import contribution, costing, menu, plates, ratio, signals
from faida_api.ratio import Quality

D = Decimal
QUSAIS = "b-qusais"
ROLLA = "b-rolla"
NAMES = {QUSAIS: "Al Qusais Branch", ROLLA: "Rolla Branch"}

DAY_ONE = datetime.date(2026, 8, 25)
PERIOD = ratio.Period(datetime.date(2026, 8, 4), datetime.date(2026, 8, 31))
WEEK = ratio.Window(DAY_ONE, datetime.date(2026, 8, 31))
MARCH = datetime.date(2026, 3, 12)


def _on(offset: int) -> datetime.date:
    return DAY_ONE + datetime.timedelta(days=offset)


# --- builders ---------------------------------------------------------------


def _item(
    menu_item_id: str,
    name: str,
    *,
    cost: str,
    price: str = "35.00",
    quality: plates.PlateQuality = plates.PlateQuality.RELIABLE,
) -> contribution.MenuItem:
    return contribution.MenuItem(
        menu_item_id=menu_item_id,
        name=name,
        plate=plates.Plate(quality=quality, cost_per_portion=D(cost)),
        selling_price=D(price),
        yield_portions=D("1"),
        vat_rate=D("0.05"),
        recipe_version=1,
    )


def _menu(*items: contribution.MenuItem) -> dict[str, contribution.MenuItem]:
    return {item.menu_item_id: item for item in items}


def _day(
    *,
    branch: str = QUSAIS,
    offset: int = 0,
    item: str = "m-karak",
    qty: str = "100",
    positive: str = "1000.00",
    no_qty_lines: int = 0,
) -> contribution.ItemSales:
    return contribution.ItemSales(
        branch_id=branch,
        business_date=_on(offset),
        till_item_id=f"t-{item}",
        name=item.upper(),
        code=None,
        menu_item_id=item,
        excluded=False,
        qty_sold=D(qty),
        qty_refunded=D(0),
        positive_value=D(positive),
        refund_value=D(0),
        no_qty_lines=no_qty_lines,
    )


def _week(
    *, branch: str = QUSAIS, item: str = "m-karak", qty: str = "100", positive: str = "1000.00"
) -> list[contribution.ItemSales]:
    """Seven identical days, 25-31 Aug."""
    return [_day(branch=branch, offset=i, item=item, qty=qty, positive=positive) for i in range(7)]


def _rows(sales, menu) -> list[contribution.ItemRow]:
    """Every row the read produces: each branch's, then the chain-wide ones
    (`branch_id` None) - the scope picks its own."""
    branch_rows = contribution.item_rows(sales, menu)
    return [*branch_rows, *contribution.chain_item_rows(branch_rows, menu, branch_names=NAMES)]


def _chain(pct: str | None, quality: Quality = Quality.RELIABLE) -> contribution.Contribution:
    """A chain figure with its kept percentage set by hand, so a threshold can
    be tested on its exact boundary without the candidate moving the average
    it is compared against."""
    return contribution.Contribution(
        branch_id=None,
        branch_name=None,
        contribution=None if pct is None else D("1200.00"),
        contribution_pct=None if pct is None else D(pct),
        net_item_sales=D("2000.00"),
        cost=D("800.00"),
        costed_value=D("2000.00"),
        sales_value=D("2000.00"),
        costed_share_pct=D("100.0"),
        quality=quality,
        notes=(),
        sales_quality=quality,
        cost_quality=quality,
        items=2,
        items_without_numbers=0,
        unmapped=contribution.Unmapped(names=0, value=D(0)),
    )


def _branch(
    sales,
    menu,
    branch_id: str,
    *,
    window: ratio.Window = WEEK,
    sales_quality: Quality = Quality.RELIABLE,
) -> signals.BranchFigure:
    rows = [r for r in contribution.item_rows(sales, menu) if r.branch_id == branch_id]
    return signals.BranchFigure(
        window=window,
        contribution=contribution.branch_contribution(
            rows, branch_id=branch_id, branch_name=NAMES[branch_id], sales_quality=sales_quality
        ),
    )


def _line(
    cost: str,
    on: datetime.date,
    *,
    pack: str = "s-milk-2.5kg",
    invoice: str = "inv-current",
    quality: str | None = None,
    unit: str = "g",
) -> menu.MoveLine:
    per_display, display_unit = costing.per_display_unit(D(cost), unit)
    return menu.MoveLine(
        supplier_item_id=pack,
        product_name="Milk Powder 2.5kg",
        supplier_name="Al Madina Trading Co.",
        pack_size="2.5kg",
        cost_per_base_unit=D(cost),
        per_display_unit=per_display,
        display_unit=display_unit,
        invoice_id=invoice,
        invoice_line_id=f"{invoice}-line",
        position=3,
        purchased_on=on,
        invoice_date=on,
        quality=quality,
    )


def _impact(menu_item_id: str, per_portion: str) -> menu.MoveImpact:
    return menu.MoveImpact(
        menu_item_id=menu_item_id,
        name=menu_item_id,
        impact_per_portion=D(per_portion),
        margin_before=D("9.000"),
        margin_after=D("9.000") - D(per_portion),
        margin_pct_before=D("90.0"),
        margin_pct_after=D("89.0"),
    )


def _move(
    *,
    previous: menu.MoveLine,
    current: menu.MoveLine,
    items: tuple[menu.MoveImpact, ...] = (),
    name: str = "Milk Powder",
    ingredient_id: str = "ing-milk",
    kind: str = "moved",
    unit: str = "g",
) -> menu.PriceMove:
    delta = current.cost_per_base_unit - previous.cost_per_base_unit
    factor = costing.DISPLAY_UNITS[unit][1]
    if kind == "basis_changed":
        delta_base = delta_display = None
    else:
        delta_base = delta
        delta_display = (delta * factor).quantize(costing.DISPLAY_QUANTUM)
    return menu.PriceMove(
        ingredient_id=ingredient_id,
        ingredient_name=name,
        base_unit=unit,
        kind=kind,
        current=current,
        previous=previous,
        delta_per_base_unit=delta_base,
        delta_per_display_unit=delta_display,
        items=items,
    )


def _milk_move(
    *,
    previous_cost: str = "0.040",
    current_cost: str = "0.042",
    moved_on: datetime.date = DAY_ONE,
    previous_on: datetime.date = MARCH,
    items: tuple[menu.MoveImpact, ...] = (_impact("m-karak", "0.060"),),
    **kwargs,
) -> menu.PriceMove:
    """Milk powder AED 40 a kilo to AED 42 (a 5% rise, the boundary) unless
    told otherwise; a karak uses 30 g, so 0.002 x 30 = 0.060 a cup."""
    return _move(
        previous=_line(previous_cost, previous_on, invoice="inv-march"),
        current=_line(current_cost, moved_on),
        items=items,
        **kwargs,
    )


# The two-item chain every popular-low-margin case starts from: karak at 80%
# and chicken at 40%, equal sales, so the chain keeps exactly 60.0%.
KARAK = _item("m-karak", "Karak Tea - Flask 1 L", cost="2.000", price="10.50")
CHICKEN = _item("m-chicken", "Chicken 65 Dry", cost="6.000", price="10.50")


def _two_item_week():
    """One day each: karak 100 portions for AED 1,000 net, chicken the same."""
    return [
        _day(item="m-karak", qty="100", positive="1000.00"),
        _day(item="m-chicken", qty="100", positive="1000.00"),
    ]


# --- popular and low-margin -------------------------------------------------


def test_the_chain_average_comes_from_the_shipped_arithmetic():
    """The hand-set 60.0% the boundary cases compare against is what
    `contribution` derives from the same rows, so the two cannot drift."""
    sales = _two_item_week()
    rows = contribution.item_rows(sales, _menu(KARAK, CHICKEN))
    branch = contribution.branch_contribution(
        rows, branch_id=QUSAIS, branch_name=NAMES[QUSAIS], sales_quality=Quality.RELIABLE
    )
    chain = contribution.chain_contribution([branch])
    assert chain.contribution_pct == D("60.0")


def test_an_item_at_the_chain_average_fires_nothing():
    sales = _two_item_week()
    rows = _rows(sales, _menu(KARAK, _item("m-chicken", "Chicken 65 Dry", cost="4.000")))
    assert signals.popular_low_margin(rows, _chain("60.0")) == []


def test_ten_points_below_fires_and_the_sentence_carries_both_figures():
    sales = _two_item_week()
    rows = _rows(sales, _menu(KARAK, CHICKEN))
    [signal] = signals.popular_low_margin(rows, _chain("60.0"))
    assert signal.kind == "popular_low_margin"
    assert signal.sentence == "Chicken 65 Dry sold AED 1,000 and kept 40.0%; the menu keeps 60.0%."
    # 20 points of AED 1,000, hand-checked: what the chain average would
    # have contributed on the same sales.
    assert signal.money_at_stake == D("200.00")
    assert signal.detail == "At the menu's average it would have contributed AED 200 more."
    assert signal.quality is Quality.RELIABLE
    assert signal.menu_item_id == "m-chicken"
    assert signal.branch_id is None


def test_the_low_margin_boundary_is_inclusive():
    """Exactly 10.0 points below fires; 9.9 is silent."""
    at_ten = _item("m-chicken", "Chicken 65 Dry", cost="5.000")  # 500 of 1000 -> 50.0%
    rows = _rows(_two_item_week(), _menu(KARAK, at_ten))
    [signal] = signals.popular_low_margin(rows, _chain("60.0"))
    assert signal.sentence.endswith("kept 50.0%; the menu keeps 60.0%.")
    assert signal.money_at_stake == D("100.00")

    one_under = _item("m-chicken", "Chicken 65 Dry", cost="4.990")  # 501 of 1000 -> 50.1%
    rows = _rows(_two_item_week(), _menu(KARAK, one_under))
    assert signals.popular_low_margin(rows, _chain("60.0")) == []


def test_only_the_top_ten_by_net_sales_are_candidates():
    """Eleven items at 40%: the one that sold least is not popular."""
    items = [_item(f"m-{i:02d}", f"Dish {i:02d}", cost="6.000") for i in range(11)]
    sales = [
        _day(item=item.menu_item_id, qty="100", positive=f"{1100 - 10 * i}.00")
        for i, item in enumerate(items)
    ]
    rows = _rows(sales, _menu(*items))
    fired = signals.popular_low_margin(rows, _chain("60.0"))
    assert len(fired) == 10
    assert "Dish 10" not in {s.menu_item_name for s in fired}


def test_no_chain_average_means_no_popular_signal():
    rows = _rows(_two_item_week(), _menu(KARAK, CHICKEN))
    assert signals.popular_low_margin(rows, _chain(None)) == []


def test_an_incomplete_row_never_fires_and_an_estimated_one_says_so():
    no_qty = [
        _day(item="m-karak", qty="100", positive="1000.00"),
        _day(item="m-chicken", qty="100", positive="1000.00", no_qty_lines=1),
    ]
    rows = _rows(no_qty, _menu(KARAK, CHICKEN))
    assert signals.popular_low_margin(rows, _chain("60.0")) == []

    estimated = _item(
        "m-chicken", "Chicken 65 Dry", cost="6.000", quality=plates.PlateQuality.ESTIMATED
    )
    rows = _rows(_two_item_week(), _menu(KARAK, estimated))
    [signal] = signals.popular_low_margin(rows, _chain("60.0"))
    assert signal.quality is Quality.ESTIMATED
    assert signal.detail == (
        "At the menu's average it would have contributed AED 200 more. (estimated)"
    )


def test_a_partial_chain_average_makes_the_signal_estimated():
    """The benchmark is an input too: a chain figure carrying a sibling's gap
    is a partial average, and the comparison says so (C13.3a)."""
    rows = _rows(_two_item_week(), _menu(KARAK, CHICKEN))
    [signal] = signals.popular_low_margin(rows, _chain("60.0", Quality.INCOMPLETE))
    assert signal.quality is Quality.ESTIMATED


# --- supplier price spike ---------------------------------------------------


def _karak_week():
    return _week(item="m-karak", qty="10", positive="100.00")


def test_a_five_percent_rise_fires_on_the_boundary_and_one_unit_under_is_silent():
    rows = _rows(_karak_week(), _menu(KARAK))
    # 0.040 -> 0.042 a gram is exactly 5%.
    [signal] = signals.price_spike([_milk_move()], _karak_week(), rows, period=PERIOD)
    assert signal.kind == "price_spike"
    assert signal.sentence == (
        "Milk Powder is up AED 2.00 per kg since 25 Aug, against its last purchase on 12 Mar."
    )
    # 0.060 a cup x 70 cups sold on or after 25 Aug.
    assert signal.money_at_stake == D("4.20")
    assert signal.detail == (
        "AED 4 off contribution on the 70 portions sold since it landed, across 1 item."
    )
    assert signal.invoice_id == "inv-current"
    assert signal.moved_on == DAY_ONE

    under = _milk_move(current_cost="0.0419")  # 4.75%
    assert signals.price_spike([under], _karak_week(), rows, period=PERIOD) == []


def test_a_baseline_inside_the_window_is_not_named():
    rows = _rows(_karak_week(), _menu(KARAK))
    move = _milk_move(previous_on=datetime.date(2026, 8, 20))
    [signal] = signals.price_spike([move], _karak_week(), rows, period=PERIOD)
    assert signal.sentence == "Milk Powder is up AED 2.00 per kg since 25 Aug."


def test_a_pack_change_and_a_price_fall_fire_nothing():
    rows = _rows(_karak_week(), _menu(KARAK))
    basis = _move(
        previous=_line("0.040", MARCH, pack="s-milk-500g"),
        current=_line("0.050", DAY_ONE, pack="s-milk-2.5kg"),
        kind="basis_changed",
    )
    fall = _milk_move(previous_cost="0.042", current_cost="0.030")
    assert signals.price_spike([basis, fall], _karak_week(), rows, period=PERIOD) == []


def test_a_mid_window_move_weighs_only_the_portions_sold_on_or_after_it():
    rows = _rows(_karak_week(), _menu(KARAK))
    move = _milk_move(moved_on=_on(3))  # 28 Aug: four of the seven days
    [signal] = signals.price_spike([move], _karak_week(), rows, period=PERIOD)
    assert signal.money_at_stake == D("2.40")  # 0.060 x 40
    assert "40 portions sold since it landed" in signal.detail


def test_a_september_move_is_not_compared_against_august_sales():
    rows = _rows(_karak_week(), _menu(KARAK))
    move = _milk_move(moved_on=datetime.date(2026, 9, 3))
    assert signals.price_spike([move], _karak_week(), rows, period=PERIOD) == []


def test_a_move_with_no_sales_after_it_ranks_last_with_its_own_sentence():
    sales = [_day(offset=i, item="m-karak", qty="10", positive="100.00") for i in range(6)]
    rows = _rows(sales, _menu(KARAK))
    late = _milk_move(moved_on=_on(6))  # 31 Aug; sales stop on the 30th
    early = _milk_move(name="Evaporated Milk", ingredient_id="ing-evap")
    ranked = signals.rank(signals.price_spike([late, early], sales, rows, period=PERIOD))
    assert [s.ingredient_name for s in ranked] == ["Evaporated Milk", "Milk Powder"]
    assert ranked[-1].money_at_stake == D("0.00")
    assert ranked[-1].detail == "No sales of items using it since it landed."


def test_a_cheap_material_fires_and_ranks_last_by_money_with_no_floor():
    """Sugar up 5%: two fils a plate, twenty fils across the week - still on
    the panel, still last, its small money beside it (D10)."""
    rows = _rows(_karak_week(), _menu(KARAK))
    sugar = _move(
        previous=_line("0.004", MARCH, pack="s-sugar"),
        current=_line("0.0042", DAY_ONE, pack="s-sugar"),
        items=(_impact("m-karak", "0.002"),),
        name="White Sugar",
        ingredient_id="ing-sugar",
    )
    ranked = signals.rank(
        signals.price_spike([sugar, _milk_move()], _karak_week(), rows, period=PERIOD)
    )
    assert [s.ingredient_name for s in ranked] == ["Milk Powder", "White Sugar"]
    assert ranked[-1].money_at_stake == D("0.14")
    assert ranked[-1].sentence == (
        "White Sugar is up AED 0.20 per kg since 25 Aug, against its last purchase on 12 Mar."
    )


def test_a_move_costed_through_a_typed_pack_size_is_estimated():
    rows = _rows(_karak_week(), _menu(KARAK))
    move = _move(
        previous=_line("0.040", MARCH, invoice="inv-march", quality="estimated"),
        current=_line("0.042", DAY_ONE),
        items=(_impact("m-karak", "0.060"),),
    )
    [signal] = signals.price_spike([move], _karak_week(), rows, period=PERIOD)
    assert signal.quality is Quality.ESTIMATED
    assert signal.detail.endswith("(estimated)")


def test_an_item_with_a_line_without_quantity_since_the_move_is_not_weighed():
    sales = [
        *_karak_week(),
        _day(offset=6, item="m-karak", qty="0", positive="0.00", no_qty_lines=1),
    ]
    rows = _rows(sales, _menu(KARAK))
    [signal] = signals.price_spike([_milk_move()], sales, rows, period=PERIOD)
    assert signal.money_at_stake == D("0.00")


# --- branch gap -------------------------------------------------------------

#: Qusais sells item A at 80% (AED 1,000 net); Rolla sells item B at 55%
#: (AED 4,000 net): the chain keeps (800 + 2,200) / 5,000 = 60.0%, so
#: Rolla sits exactly five points under it.
ITEM_A = _item("m-a", "Item A", cost="2.000")
ITEM_B_AT_55 = _item("m-b", "Item B", cost="18.000")


def _gap_sales():
    return [
        _day(branch=QUSAIS, item="m-a", qty="100", positive="1000.00"),
        _day(branch=ROLLA, item="m-b", qty="100", positive="4000.00"),
    ]


def test_the_branch_gap_boundary_is_inclusive():
    sales = _gap_sales()
    menu_ = _menu(ITEM_A, ITEM_B_AT_55)
    branches = [_branch(sales, menu_, QUSAIS), _branch(sales, menu_, ROLLA)]
    [signal] = signals.branch_gap(branches, _chain("60.0"), sales, menu_)
    assert signal.kind == "branch_gap"
    assert signal.sentence == "Rolla keeps 5.0 points less of every dirham than the chain."
    assert signal.detail == "55.0% against 60.0% over 25-31 Aug."
    assert signal.money_at_stake == D("200.00")  # 5% of AED 4,000
    assert signal.branch_id == ROLLA
    assert signal.branch_name == "Rolla Branch"

    # 55.5% against a chain of 60.4%: 4.9 points, silent.
    menu_ = _menu(ITEM_A, _item("m-b", "Item B", cost="17.800"))
    branches = [_branch(sales, menu_, QUSAIS), _branch(sales, menu_, ROLLA)]
    assert signals.branch_gap(branches, _chain("60.4"), sales, menu_) == []


def test_the_chain_benchmark_is_recomputed_over_the_candidates_own_window():
    """Rolla loaded 25-27 Aug; Qusais loaded the whole week and its last four
    days keep far less. Over the whole period the chain keeps 52.5% and
    Rolla's 55.0% would be no gap at all; over Rolla's own three days the
    chain keeps 67.5%, and Rolla is 12.5 points under it. Qusais keeps 51.4%
    over its own window (the whole period), 1.1 under the chain: silent."""
    item_a = _item("m-a", "Item A", cost="2.000")  # 80%
    item_b = _item("m-b", "Item B", cost="4.500")  # 55%
    item_c = _item("m-c", "Item C", cost="7.000")  # 30%
    menu_ = _menu(item_a, item_b, item_c)
    sales = [
        *[_day(branch=QUSAIS, offset=i, item="m-a") for i in range(3)],
        *[_day(branch=QUSAIS, offset=i, item="m-c") for i in range(3, 7)],
        *[_day(branch=ROLLA, offset=i, item="m-b") for i in range(3)],
    ]
    rolla_window = ratio.Window(DAY_ONE, _on(2))
    branches = [
        _branch(sales, menu_, QUSAIS),
        _branch(sales, menu_, ROLLA, window=rolla_window),
    ]
    [signal] = signals.branch_gap(branches, _chain("52.5"), sales, menu_)
    assert signal.sentence == "Rolla keeps 12.5 points less of every dirham than the chain."
    assert signal.detail == "55.0% against 67.5% over 25-27 Aug."
    assert signal.money_at_stake == D("375.00")  # 12.5% of AED 3,000


def test_an_incomplete_branch_fires_nothing():
    sales = _gap_sales()
    menu_ = _menu(ITEM_A, _item("m-b", "Item B", cost="24.000"))  # 40%: a 20-point gap
    branches = [
        _branch(sales, menu_, QUSAIS),
        _branch(sales, menu_, ROLLA, sales_quality=Quality.INCOMPLETE),
    ]
    assert signals.branch_gap(branches, _chain("60.0"), sales, menu_) == []
    branches[1] = _branch(sales, menu_, ROLLA, sales_quality=Quality.UNAVAILABLE)
    assert signals.branch_gap(branches, _chain("60.0"), sales, menu_) == []
    branches[1] = _branch(sales, menu_, ROLLA, sales_quality=Quality.ESTIMATED)
    [signal] = signals.branch_gap(branches, _chain("60.0"), sales, menu_)
    assert signal.quality is Quality.ESTIMATED
    assert signal.detail.endswith("(estimated)")


# --- ranking, the cap and the scope -----------------------------------------


def test_six_candidates_return_five_largest_money_first():
    items = [_item(f"m-{i}", f"Dish {i}", cost="6.000") for i in range(6)]
    # Every dish keeps 40% - the cost scales with the sales - so the six
    # stakes step down by AED 20 and only the money ranks them.
    sales = [
        _day(item=item.menu_item_id, qty=f"{100 - 10 * i}", positive=f"{1000 - 100 * i}.00")
        for i, item in enumerate(items)
    ]
    rows = _rows(sales, _menu(*items))
    ranked = signals.rank(signals.popular_low_margin(rows, _chain("60.0")))
    assert len(ranked) == signals.MAX_SIGNALS == 5
    assert [s.money_at_stake for s in ranked] == [
        D("200.00"),
        D("180.00"),
        D("160.00"),
        D("140.00"),
        D("120.00"),
    ]
    assert "Dish 5" not in {s.menu_item_name for s in ranked}


def test_under_a_branch_scope_the_candidates_are_the_branchs_and_the_benchmark_the_chains():
    """Chicken keeps 40% and karak 80% in both branches; Qusais sells them
    evenly (60.0%), Rolla sells four chickens to a karak (48.0%), so the
    chain keeps 57.6% and Rolla is 9.6 points under it. Under Rolla's scope
    the popular candidate is Rolla's chicken, the milk move weighs Rolla's
    seventy cups only, and only Rolla's gap is offered - all against the
    chain's figures."""
    sales = [
        *_week(branch=QUSAIS, item="m-chicken", qty="100", positive="1000.00"),
        *_week(branch=QUSAIS, item="m-karak", qty="100", positive="1000.00"),
        *_week(branch=ROLLA, item="m-chicken", qty="40", positive="400.00"),
        *_week(branch=ROLLA, item="m-karak", qty="10", positive="100.00"),
    ]
    menu_ = _menu(KARAK, CHICKEN)
    rows = _rows(sales, menu_)
    branches = [_branch(sales, menu_, QUSAIS), _branch(sales, menu_, ROLLA)]
    chain = contribution.chain_contribution([b.contribution for b in branches])
    scope = signals.Scope(branch_id=ROLLA, branch_name="Rolla Branch")

    fired = signals.compute(
        rows=rows,
        chain=chain,
        branches=branches,
        moves=[_milk_move()],
        sales=sales,
        menu=menu_,
        period=PERIOD,
        scope=scope,
    )
    by_kind = {s.kind: s for s in fired}
    assert set(by_kind) == {"popular_low_margin", "price_spike", "branch_gap"}

    assert chain.contribution_pct == D("57.6")
    popular = by_kind["popular_low_margin"]
    assert popular.branch_id == ROLLA
    # Rolla's chicken: AED 2,800 over the week, not the chain's AED 9,800.
    assert popular.sentence == (
        "Chicken 65 Dry sold AED 2,800 and kept 40.0%; the menu keeps 57.6%."
    )
    assert popular.money_at_stake == D("492.80")  # 17.6 points of AED 2,800

    spike = by_kind["price_spike"]
    assert spike.money_at_stake == D("4.20")  # 0.060 x 70 Rolla cups, not 770
    assert "70 portions" in spike.detail

    gap = by_kind["branch_gap"]
    assert gap.branch_id == ROLLA
    assert gap.sentence == "Rolla keeps 9.6 points less of every dirham than the chain."
    assert gap.detail == "48.0% against 57.6% over 25-31 Aug."

    # Unfiltered, the same read is the chain's: chain-wide rows, every cup,
    # and no branch gap for a branch that keeps more than the chain.
    unfiltered = signals.compute(
        rows=rows,
        chain=chain,
        branches=branches,
        moves=[_milk_move()],
        sales=sales,
        menu=menu_,
        period=PERIOD,
    )
    chain_kinds = {s.kind: s for s in unfiltered}
    assert chain_kinds["popular_low_margin"].branch_id is None
    assert "sold AED 9,800" in chain_kinds["popular_low_margin"].sentence
    assert chain_kinds["price_spike"].money_at_stake == D("46.20")  # 0.060 x 770
    assert "branch_gap" in chain_kinds and chain_kinds["branch_gap"].branch_id == ROLLA
    assert [s.money_at_stake for s in unfiltered] == sorted(
        (s.money_at_stake for s in unfiltered), reverse=True
    )


# --- menu.price_moves, the pure half of the route ---------------------------


def _pair_line(
    ingredient_id: str,
    cost: str,
    on: datetime.date,
    *,
    pack: str = "s-milk",
    name: str = "Evaporated Milk",
    unit: str = "ml",
) -> dict:
    return {
        "ingredient_id": ingredient_id,
        "ingredient_name": name,
        "base_unit": unit,
        "supplier_item_id": pack,
        "canonical_name": f"{name} pack",
        "supplier_name": "Al Seeb Trading",
        "invoice_line_id": f"line-{on.isoformat()}-{pack}",
        "position": 1,
        "pack_size": "1l",
        "cost_per_base_unit": D(cost),
        "cost_basis": {"quality": "reliable_with_limitations"},
        "invoice_id": f"inv-{on.isoformat()}-{pack}",
        "invoice_date": on,
        "confirmed_at": None,
        "purchased_on": on,
    }


def test_price_moves_pairs_the_same_pack_and_names_the_plate_it_moved():
    """`test_price_moves.py`'s milk hand-check, without the database: 8.00 to
    9.00 a litre on the same pack, the karak cup's 60 ml down 0.06."""
    aug_1, aug_15 = datetime.date(2026, 8, 1), datetime.date(2026, 8, 15)
    pairs = {
        "ing-milk": [
            _pair_line("ing-milk", "0.009", aug_15),
            _pair_line("ing-milk", "0.008", aug_1),
        ]
    }
    rows = [
        {"id": "m-cup", "name": "Karak Cup", "archived_at": None, "yield_portions": D("1")},
        {"id": "m-old", "name": "Old Cup", "archived_at": aug_1, "yield_portions": D("1")},
    ]
    components = {
        "m-cup": [{"ingredient_id": "ing-milk", "qty": D("60"), "unit": "ml"}],
        "m-old": [{"ingredient_id": "ing-milk", "qty": D("60"), "unit": "ml"}],
    }
    cup = plates.Plate(
        quality=plates.PlateQuality.RELIABLE,
        cost_per_portion=D("0.812"),
        net_price=D("9.524"),
        margin=D("8.712"),
        margin_pct=D("91.5"),
    )
    [move] = menu.price_moves(pairs, rows, components, {"m-cup": cup, "m-old": cup})
    assert move.kind == "moved"
    assert move.delta_per_display_unit == D("1.00")
    assert move.current.per_display_unit == D("9.00")
    assert move.previous.per_display_unit == D("8.00")
    [item] = move.items  # the archived cup is not named
    assert item.name == "Karak Cup"
    assert item.impact_per_portion == D("0.060")
    assert item.margin_before == D("8.772")
    assert item.margin_pct_before == D("92.1")
    payload = menu._move_payload(move)
    assert payload["items"][0]["impact_per_portion"] == "0.060"
    assert payload["delta_per_display_unit"] == "1.00"
    assert payload["current"]["purchased_on"] == "2026-08-15"


def test_price_moves_refuses_a_delta_across_packs_and_skips_what_did_not_move():
    aug_1, aug_15 = datetime.date(2026, 8, 1), datetime.date(2026, 8, 15)
    pairs = {
        "ing-milk": [
            _pair_line("ing-milk", "0.009", aug_15, pack="s-milk-2l"),
            _pair_line("ing-milk", "0.008", aug_1, pack="s-milk-1l"),
        ],
        "ing-tea": [
            _pair_line("ing-tea", "0.030", aug_15, pack="s-tea", name="Tea", unit="g"),
            _pair_line("ing-tea", "0.030", aug_1, pack="s-tea", name="Tea", unit="g"),
        ],
        "ing-first": [
            _pair_line("ing-first", "0.010", aug_15, pack="s-first", name="Sugar", unit="g")
        ],
        "ing-unused": [
            _pair_line("ing-unused", "0.020", aug_15, pack="s-u", name="Salt", unit="g"),
            _pair_line("ing-unused", "0.010", aug_1, pack="s-u", name="Salt", unit="g"),
        ],
    }
    rows = [{"id": "m-cup", "name": "Karak Cup", "archived_at": None, "yield_portions": D("1")}]
    components = {
        "m-cup": [
            {"ingredient_id": "ing-milk", "qty": D("60"), "unit": "ml"},
            {"ingredient_id": "ing-tea", "qty": D("4"), "unit": "g"},
            {"ingredient_id": "ing-first", "qty": D("4"), "unit": "g"},
        ]
    }
    plate = plates.Plate(
        quality=plates.PlateQuality.RELIABLE,
        cost_per_portion=D("0.812"),
        net_price=D("9.524"),
        margin=D("8.712"),
        margin_pct=D("91.5"),
    )
    moves = menu.price_moves(pairs, rows, components, {"m-cup": plate})
    assert [m.kind for m in moves] == ["basis_changed"]
    assert moves[0].delta_per_display_unit is None
    assert moves[0].items == ()
    assert menu._move_payload(moves[0])["delta_per_display_unit"] is None


def test_price_moves_orders_newest_first_then_by_what_it_costs_a_plate():
    aug_1, aug_15 = datetime.date(2026, 8, 1), datetime.date(2026, 8, 15)
    pairs = {
        "ing-sugar": [
            _pair_line("ing-sugar", "0.0045", aug_15, pack="s-sugar", name="White Sugar", unit="g"),
            _pair_line("ing-sugar", "0.004", aug_1, pack="s-sugar", name="White Sugar", unit="g"),
        ],
        "ing-milk": [
            _pair_line("ing-milk", "0.009", aug_15),
            _pair_line("ing-milk", "0.008", aug_1),
        ],
        "ing-tea": [
            _pair_line("ing-tea", "0.040", aug_1, pack="s-tea", name="Tea", unit="g"),
            _pair_line(
                "ing-tea", "0.030", datetime.date(2026, 7, 1), pack="s-tea", name="Tea", unit="g"
            ),
        ],
    }
    rows = [{"id": "m-cup", "name": "Karak Cup", "archived_at": None, "yield_portions": D("1")}]
    components = {
        "m-cup": [
            {"ingredient_id": "ing-milk", "qty": D("60"), "unit": "ml"},
            {"ingredient_id": "ing-sugar", "qty": D("10"), "unit": "g"},
            {"ingredient_id": "ing-tea", "qty": D("4"), "unit": "g"},
        ]
    }
    plate = plates.Plate(
        quality=plates.PlateQuality.RELIABLE,
        cost_per_portion=D("0.812"),
        net_price=D("9.524"),
        margin=D("8.712"),
        margin_pct=D("91.5"),
    )
    moves = menu.price_moves(pairs, rows, components, {"m-cup": plate})
    # 15 Aug before 1 Aug; on 15 Aug the milk (0.060 a cup) before the sugar (0.005).
    assert [m.ingredient_name for m in moves] == ["Evaporated Milk", "White Sugar", "Tea"]
