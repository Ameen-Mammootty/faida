"""M9 WP-90: the contribution rules, pure (Docs/M9_DECOMPOSITION.md §3 C12,
C9 extended, row 90).

No database: every case builds a branch's item days and its costed menu by
hand and checks the figure, the label and the sentence that made it. The SQL
behind `ItemSales` is proven against real Postgres in `test_contribution_db.py`,
and the routes that will serialise these rows arrive with WP-92.

The karak in `test_the_karak_contributes_to_the_fil_by_hand` is the worked
example from §3.1's pinned wire shape, reproduced number for number, so the
web lane's mock and this module cannot drift apart.
"""

import datetime
from decimal import Decimal

from faida_api import contribution, plates, ratio

D = Decimal
QUSAIS = "b-qusais"
ROLLA = "b-rolla"
BRANCH_NAMES = {QUSAIS: "Al Qusais Branch", ROLLA: "Rolla Branch"}

DAY_ONE = datetime.date(2026, 8, 25)
PERIOD = ratio.Period(datetime.date(2026, 8, 4), datetime.date(2026, 8, 31))
WEEK = ratio.Window(DAY_ONE, datetime.date(2026, 8, 31))
COSTED_AT = datetime.date(2026, 8, 31)


def _on(offset: int) -> datetime.date:
    return DAY_ONE + datetime.timedelta(days=offset)


def _plate(
    cost: str | None = "6.204",
    *,
    quality: plates.PlateQuality = plates.PlateQuality.RELIABLE,
    missing: tuple[str, ...] = (),
) -> plates.Plate:
    if cost is None:
        return plates.Plate(quality=plates.PlateQuality.INCOMPLETE, missing=missing)
    return plates.Plate(quality=quality, cost_per_portion=D(cost))


def _item(
    menu_item_id: str = "m-karak",
    name: str = "Karak Tea - Flask 1 L",
    *,
    cost: str | None = "6.204",
    price: str = "35.00",
    quality: plates.PlateQuality = plates.PlateQuality.RELIABLE,
    missing: tuple[str, ...] = (),
    components: tuple[contribution.RecipeComponent, ...] = (),
    recipe_version: int | None = 1,
    archived: bool = False,
    archived_on: datetime.date | None = None,
    category: str | None = "Tea Corner",
) -> contribution.MenuItem:
    return contribution.MenuItem(
        menu_item_id=menu_item_id,
        name=name,
        plate=_plate(cost, quality=quality, missing=missing),
        selling_price=D(price),
        yield_portions=D("1"),
        vat_rate=D("0.05"),
        category=category,
        recipe_version=recipe_version,
        components=components,
        archived=archived,
        archived_on=archived_on,
    )


def _menu(*items: contribution.MenuItem) -> dict[str, contribution.MenuItem]:
    return {item.menu_item_id: item for item in items}


def _day(
    *,
    branch: str = QUSAIS,
    offset: int = 0,
    till_item_id: str = "t-karak",
    name: str = "KARAK TEA FLASK 1L",
    code: str | None = "52a",
    menu_item_id: str | None = "m-karak",
    excluded: bool = False,
    qty_sold: str = "10",
    qty_refunded: str = "0",
    positive: str = "333.33",
    refund: str = "0.00",
    no_qty_lines: int = 0,
) -> contribution.ItemSales:
    return contribution.ItemSales(
        branch_id=branch,
        business_date=_on(offset),
        till_item_id=till_item_id,
        name=name,
        code=code,
        menu_item_id=menu_item_id,
        excluded=excluded,
        qty_sold=D(qty_sold),
        qty_refunded=D(qty_refunded),
        positive_value=D(positive),
        refund_value=D(refund),
        no_qty_lines=no_qty_lines,
    )


def _from_lines(lines: list[tuple[str | None, str]], **kwargs) -> contribution.ItemSales:
    """One item day built the way `db.list_period_item_sales`' filters build
    it, from (qty, net_amount) pairs as the till printed them (C12.6a).

    Written out rather than hidden behind the read, because the whole point
    of the rule is that the *printing* differs and the answer does not: the
    sign that decides which bucket a line falls into is the amount's, never
    the quantity's.
    """
    qty_sold = sum((D(qty) for qty, amount in lines if qty is not None and D(amount) >= 0), D(0))
    qty_refunded = sum(
        (abs(D(qty)) for qty, amount in lines if qty is not None and D(amount) < 0), D(0)
    )
    positive = sum((D(amount) for _, amount in lines if D(amount) > 0), D(0))
    refund = sum((D(amount) for _, amount in lines if D(amount) < 0), D(0))
    return _day(
        qty_sold=str(qty_sold),
        qty_refunded=str(qty_refunded),
        positive=str(positive),
        refund=str(refund),
        no_qty_lines=sum(1 for qty, _ in lines if qty is None),
        **kwargs,
    )


def _rows(days, menu=None, **kwargs) -> list[contribution.ItemRow]:
    return contribution.item_rows(days, menu or _menu(_item()), costed_at=COSTED_AT, **kwargs)


def _branch(
    rows,
    *,
    branch_id: str = QUSAIS,
    quality: ratio.Quality = ratio.Quality.RELIABLE,
    notes: tuple[str, ...] = (),
    unmapped: contribution.Unmapped | None = None,
) -> contribution.Contribution:
    return contribution.branch_contribution(
        [r for r in rows if r.branch_id == branch_id],
        branch_id=branch_id,
        branch_name=BRANCH_NAMES[branch_id],
        sales_quality=quality,
        sales_notes=notes,
        unmapped=unmapped,
    )


# --- the figure -------------------------------------------------------------


def test_the_karak_contributes_to_the_fil_by_hand():
    """§3.1's worked row, by hand: 412 portions x AED 6.204 is AED 2,556.05 of
    ingredients and packaging, and AED 13,733.33 of net item sales leaves
    AED 11,177.28 - 81.4% of what the till took."""
    rows = _rows([_day(qty_sold="412", positive="13733.33")])

    (row,) = rows
    assert row.qty_sold == D("412.000")
    assert row.net_item_sales == D("13733.33")
    assert row.cost_per_portion == D("6.204")
    assert row.cost == D("2556.05")  # 412 x 6.204 = 2556.048, to the fil
    assert row.contribution == D("11177.28")  # 13733.33 - 2556.05
    assert row.contribution_pct == D("81.4")
    assert row.avg_sold_at == D("33.333")
    assert row.net_price == D("33.333")  # 35.00 inclusive of 5% VAT
    assert row.quality is ratio.Quality.RELIABLE
    assert row.notes == (
        "costed at the prices in force on 31 Aug 2026",
        "recipe version 1",
    )


def test_the_figures_on_a_row_reconcile_when_a_reader_subtracts_them():
    """Rounded once, at the cost, so net item sales minus cost is exactly the
    contribution on screen - not a fil away from it."""
    (row,) = _rows([_day(qty_sold="7", positive="100.07")])
    assert row.net_item_sales - row.cost == row.contribution


def test_two_till_names_on_one_menu_item_make_one_row_with_both_names():
    """A rename is not two dishes (C12.1): the till's old and new PLUs map to
    one menu item, so they sum into one row that lists both."""
    rows = _rows(
        [
            _day(till_item_id="t-old", name="KARAK 1L", code="52a", qty_sold="4"),
            _day(till_item_id="t-new", name="KARAK TEA FLASK 1L", code="53a", qty_sold="6"),
        ]
    )

    (row,) = rows
    assert row.qty_sold == D("10.000")
    assert row.net_item_sales == D("666.66")
    assert [t.name for t in row.till_items] == ["KARAK 1L", "KARAK TEA FLASK 1L"]


def test_an_archived_item_still_sold_last_month_and_keeps_its_row():
    """A dish removed from the menu is exactly the kind of thing an owner asks
    about, so the row is kept and marked (C12.5)."""
    menu = _menu(_item(archived=True, archived_on=datetime.date(2026, 8, 28)))
    (row,) = _rows([_day()], menu)

    assert row.archived is True
    assert "archived 28 Aug" in row.notes
    assert row.contribution is not None


def test_an_item_that_costs_more_than_it_sells_for_says_so_in_words():
    """Never colour alone (§3): the sentence is on the row, and the figure is
    negative rather than hidden."""
    menu = _menu(_item(cost="40.000"))
    (row,) = _rows([_day(qty_sold="10", positive="333.33")], menu)

    assert row.cost == D("400.00")
    assert row.contribution == D("-66.67")
    assert "this item costs more than it sells for" in row.notes


# --- refunds (C12.6a) -------------------------------------------------------


def test_both_ways_a_till_prints_a_refund_give_the_identical_figure():
    """A till that prints a refund as `qty 1, amount -20` and one that prints
    `qty -1` must cost the chain the same one plate back, not two and not
    none (C12.6a)."""
    positive_qty = _from_lines([("10", "200.00"), ("1", "-20.00")])
    negative_qty = _from_lines([("10", "200.00"), ("-1", "-20.00")])
    assert positive_qty == negative_qty

    (as_printed,) = _rows([positive_qty])
    (as_signed,) = _rows([negative_qty])
    assert as_printed.qty_sold == D("10.000")
    assert as_printed.qty_refunded == D("1.000")
    assert as_printed.cost == D("55.84")  # 9 portions x 6.204
    assert as_printed.contribution == D("124.16")  # 180.00 - 55.84
    assert as_printed.contribution == as_signed.contribution
    assert "1 portion refunded" in as_printed.notes


def test_a_refund_heavy_item_shows_no_margin_percentage_and_says_why():
    """Never a negative ratio dressed as a margin (the failure table)."""
    (row,) = _rows([_day(qty_sold="10", qty_refunded="12", positive="333.33", refund="-400.00")])

    assert row.net_item_sales == D("-66.67")
    assert row.contribution_pct is None
    assert "net sales are not positive for this item this period" in row.notes


def test_avg_sold_at_is_withheld_when_portions_net_of_refunds_are_not_positive():
    """Dividing by nothing, or by a negative count, would print a price no
    customer ever paid."""
    (nothing_left,) = _rows(
        [_day(qty_sold="4", qty_refunded="4", positive="133.33", refund="-133.33")]
    )
    assert nothing_left.avg_sold_at is None

    (still_selling,) = _rows([_day(qty_sold="4", qty_refunded="1", positive="133.33")])
    assert still_selling.avg_sold_at == D("44.443")


# --- what cannot be costed, and what it must not do -------------------------


def test_a_line_with_no_quantity_leaves_the_row_incomplete_with_no_numbers():
    """A counted line with a null quantity cannot be multiplied, and a
    quantity is never derived from money ÷ menu price (C12.6)."""
    (row,) = _rows([_from_lines([("10", "200.00"), (None, "60.00")])])

    assert row.quality is ratio.Quality.INCOMPLETE
    assert row.qty_sold is None
    assert row.qty_refunded is None
    assert row.cost_per_portion is None
    assert row.cost is None
    assert row.contribution is None
    assert row.contribution_pct is None
    assert row.avg_sold_at is None
    assert "1 sales line has no quantity" in row.notes
    # What the till did take is still a fact, and the plate is still the
    # tenant's: the hole is the multiplication, not the money.
    assert row.net_item_sales == D("260.00")
    assert row.plate_quality == "reliable_with_limitations"


def test_three_lines_with_no_quantity_are_counted_in_the_sentence():
    (row,) = _rows([_day(no_qty_lines=3)])
    assert "3 sales lines have no quantity" in row.notes


def test_an_incomplete_plate_produces_one_row_with_every_number_null():
    """`/menu`'s rule verbatim (C12.5): never "no row", never an estimate, and
    never a cost of zero that would read as the menu's best margin."""
    menu = _menu(_item(cost=None, missing=("no supplier product is mapped to Cardamom yet",)))
    (row,) = _rows([_day(qty_sold="412", positive="13733.33")], menu)

    assert row.plate_quality == "incomplete"
    assert row.quality is ratio.Quality.INCOMPLETE
    assert row.cost_per_portion is None
    assert row.cost is None
    assert row.contribution is None
    assert row.contribution_pct is None
    assert "no supplier product is mapped to Cardamom yet" in row.notes
    # The quantities and the money stay: what an uncosted dish sold is the
    # fact that makes it worth mapping.
    assert row.qty_sold == D("412.000")
    assert row.net_item_sales == D("13733.33")


def test_an_incomplete_row_enters_no_aggregate_and_lowers_the_share():
    menu = _menu(
        _item(cost="6.204"),
        _item("m-chicken", "Chicken 65 Dry", cost=None, missing=("no recipe yet",)),
    )
    rows = _rows(
        [
            _day(qty_sold="412", positive="13733.33"),
            _day(till_item_id="t-chicken", menu_item_id="m-chicken", positive="4000.00"),
        ],
        menu,
    )
    branch = _branch(rows)

    assert branch.contribution == D("11177.28")  # the karak alone
    assert branch.net_item_sales == D("13733.33")
    assert branch.items == 1
    assert branch.items_without_numbers == 1
    assert branch.costed_share_pct == D("77.4")  # 13733.33 / 17733.33
    assert "covers 77% of this branch's sales value" in branch.notes
    assert "1 item cannot be costed yet" in branch.notes


def test_an_unmapped_till_name_is_a_note_and_not_a_label():
    """C9 extended: sales on a name nobody has mapped lower the costed share
    and are named; they never downgrade the word."""
    days = [
        _day(qty_sold="412", positive="13733.33"),
        _day(till_item_id="t-shawarma", name="SHAWARMA", menu_item_id=None, positive="2000.00"),
    ]
    rows = _rows(days)

    assert len(rows) == 1  # the unmapped name produces no row at all
    branch = _branch(rows, unmapped=contribution.unmapped(days))
    assert branch.quality is ratio.Quality.RELIABLE
    assert branch.unmapped == contribution.Unmapped(names=1, value=D("2000.00"))
    assert "1 till name with sales is not mapped to a menu item" in branch.notes
    assert branch.costed_share_pct == D("87.3")  # 13733.33 / 15733.33


def test_a_name_marked_not_a_menu_item_leaves_the_denominator_entirely():
    """A delivery charge is takings, never menu sales (C12.7a), so it is not
    an uncosted dish and must not drag the share down."""
    days = [
        _day(qty_sold="412", positive="13733.33"),
        _day(
            till_item_id="t-delivery",
            name="DELIVERY",
            menu_item_id=None,
            excluded=True,
            positive="900.00",
        ),
    ]
    branch = _branch(_rows(days), unmapped=contribution.unmapped(days))

    assert branch.unmapped.names == 0
    assert branch.costed_share_pct == D("100.0")


def test_one_plu_with_no_quantity_lowers_the_share_and_not_the_label():
    """The rule the second review corrected: one till line with no quantity
    must not mark a whole branch incomplete until the till fixes its export."""
    menu = _menu(_item(), _item("m-chicken", "Chicken 65 Dry", cost="9.100"))
    rows = _rows(
        [
            _day(qty_sold="412", positive="13733.33"),
            _day(
                till_item_id="t-chicken",
                menu_item_id="m-chicken",
                positive="4000.00",
                no_qty_lines=1,
            ),
        ],
        menu,
    )
    branch = _branch(rows)

    assert branch.quality is ratio.Quality.RELIABLE
    assert branch.contribution == D("11177.28")
    assert branch.costed_share_pct == D("77.4")
    assert "covers 77% of this branch's sales value" in branch.notes
    assert "1 item has lines with no quantity" in branch.notes


def test_one_estimated_plate_makes_the_whole_branch_estimated():
    """The other half of C9 extended: a row that *did* produce numbers carries
    its plate's label up."""
    menu = _menu(
        _item(),
        _item("m-chicken", "Chicken 65 Dry", cost="9.100", quality=plates.PlateQuality.ESTIMATED),
    )
    rows = _rows(
        [
            _day(qty_sold="412", positive="13733.33"),
            _day(
                till_item_id="t-chicken",
                menu_item_id="m-chicken",
                qty_sold="100",
                positive="4000.00",
            ),
        ],
        menu,
    )
    branch = _branch(rows)

    assert branch.cost_quality is ratio.Quality.ESTIMATED
    assert branch.quality is ratio.Quality.ESTIMATED


def test_the_branch_label_is_the_worse_of_its_sales_side_and_its_plates():
    """And the sales side comes from `ratio.period_row`, verbatim."""
    rows = _rows([_day()])
    gapped = _branch(
        rows,
        quality=ratio.Quality.INCOMPLETE,
        notes=("2 of 7 days have no sales",),
    )

    assert gapped.quality is ratio.Quality.INCOMPLETE
    assert "2 of 7 days have no sales" in gapped.notes


def test_a_branch_with_nothing_loaded_reads_unavailable():
    branch = _branch(
        [],
        quality=ratio.Quality.UNAVAILABLE,
        notes=("no sales loaded 25-31 Aug",),
    )
    assert branch.quality is ratio.Quality.UNAVAILABLE
    assert branch.contribution is None
    assert branch.contribution_pct is None


# --- the costed share (C12.7a) ----------------------------------------------


def test_the_costed_share_stays_within_0_and_100_on_a_refund_heavy_branch():
    """Both halves are the *positive* value only, so a week of refunds cannot
    push the share past 100% the way dividing by net sales would."""
    rows = _rows([_day(qty_sold="10", qty_refunded="12", positive="333.33", refund="-400.00")])
    branch = _branch(rows)

    assert branch.net_item_sales == D("-66.67")
    assert branch.costed_share_pct == D("100.0")
    assert D(0) <= branch.costed_share_pct <= D(100)
    assert branch.contribution_pct is None


def test_the_costed_share_is_zero_when_nothing_could_be_costed():
    days = [_day(till_item_id="t-shawarma", menu_item_id=None, positive="2000.00")]
    branch = _branch(_rows(days), unmapped=contribution.unmapped(days))

    assert branch.costed_share_pct == D("0.0")
    assert branch.contribution is None
    assert "covers 0% of this branch's sales value" in branch.notes


# --- the chain (C12.8) ------------------------------------------------------


def _two_branch_chain():
    menu = _menu(_item(), _item("m-chicken", "Chicken 65 Dry", cost="9.100"))
    days = [
        _day(branch=QUSAIS, qty_sold="412", positive="13733.33"),
        _day(
            branch=QUSAIS,
            till_item_id="t-chicken",
            menu_item_id="m-chicken",
            qty_sold="140",
            positive="4900.00",
        ),
        _day(branch=ROLLA, qty_sold="180", positive="6000.00"),
        _day(
            branch=ROLLA,
            till_item_id="t-chicken",
            menu_item_id="m-chicken",
            qty_sold="60",
            positive="2100.00",
        ),
    ]
    return menu, days, _rows(days, menu)


def test_the_chain_equals_the_sum_of_the_branches_and_of_the_chain_wide_rows():
    """C12.8's pinned invariant, both halves of it."""
    menu, days, rows = _two_branch_chain()
    branches = [
        _branch(rows, branch_id=QUSAIS, unmapped=contribution.unmapped(days, branch_id=QUSAIS)),
        _branch(rows, branch_id=ROLLA, unmapped=contribution.unmapped(days, branch_id=ROLLA)),
    ]
    chain = contribution.chain_contribution(branches, unmapped=contribution.unmapped(days))
    chain_rows = contribution.chain_item_rows(
        rows, menu, branch_names=BRANCH_NAMES, costed_at=COSTED_AT
    )

    assert chain.contribution == sum(b.contribution for b in branches)
    assert chain.contribution == sum(r.contribution for r in chain_rows)
    assert chain.contribution == sum(r.contribution for r in rows)
    assert len(chain_rows) == 2
    assert all(r.branch_id is None for r in chain_rows)


def test_a_chain_row_sums_only_the_pairs_that_produced_numbers_and_names_the_rest():
    """Completeness is per branch-item: the same dish can carry numbers in Al
    Qusais and none in Rolla, because a null quantity is a fact about one
    branch's file."""
    menu = _menu(_item())
    days = [
        _day(branch=QUSAIS, qty_sold="412", positive="13733.33"),
        _day(branch=ROLLA, positive="6000.00", no_qty_lines=2),
    ]
    rows = _rows(days, menu)
    (chain_row,) = contribution.chain_item_rows(
        rows, menu, branch_names=BRANCH_NAMES, costed_at=COSTED_AT
    )

    assert chain_row.qty_sold == D("412.000")
    assert chain_row.net_item_sales == D("13733.33")
    assert chain_row.contribution == D("11177.28")
    assert chain_row.quality is ratio.Quality.RELIABLE
    assert "Rolla Branch not included in this row, holding AED 6,000 of sales" in chain_row.notes


def test_a_chain_row_with_no_numbered_pair_carries_none_and_says_why():
    menu = _menu(_item(cost=None, missing=("no recipe yet",)))
    days = [
        _day(branch=QUSAIS, qty_sold="412", positive="13733.33"),
        _day(branch=ROLLA, qty_sold="180", positive="6000.00"),
    ]
    (chain_row,) = contribution.chain_item_rows(
        _rows(days, menu), menu, branch_names=BRANCH_NAMES, costed_at=COSTED_AT
    )

    assert chain_row.contribution is None
    assert chain_row.qty_sold == D("592.000")
    assert chain_row.net_item_sales == D("19733.33")
    assert "no recipe yet" in chain_row.notes


def test_the_chain_label_follows_the_sales_side_and_the_worst_plate():
    menu, days, rows = _two_branch_chain()
    branches = [
        _branch(rows, branch_id=QUSAIS),
        _branch(rows, branch_id=ROLLA, quality=ratio.Quality.UNAVAILABLE),
    ]
    chain = contribution.chain_contribution(branches)

    assert chain.sales_quality is ratio.Quality.INCOMPLETE
    assert chain.quality is ratio.Quality.INCOMPLETE
    assert "1 of 2 branches with nothing loaded" in chain.notes
    assert contribution.OVERHEADS_NOTE in chain.notes


# --- the cost basis (C12.4, C12.4a) -----------------------------------------


def test_cost_per_portion_today_is_carried_only_when_it_differs():
    """A reader is never shown two costs without being told which is which -
    and never shown the same cost twice."""
    menu = _menu(_item())
    same = _rows([_day()], menu, today_plates={"m-karak": _plate("6.204")})
    moved = _rows([_day()], menu, today_plates={"m-karak": _plate("6.410")})

    assert same[0].cost_per_portion_today is None
    assert not [n for n in same[0].notes if n.startswith("today's plate")]
    assert moved[0].cost_per_portion_today == D("6.410")
    assert "costed at the prices in force on 31 Aug 2026" in moved[0].notes
    assert "today's plate is AED 6.41" in moved[0].notes


def test_a_row_with_no_cost_of_its_own_is_never_given_todays():
    """A hole never renders as a fat margin, and least of all somebody else's
    margin: an uncosted period row shows no cost at all."""
    menu = _menu(_item(cost=None, missing=("no recipe yet",)))
    (row,) = _rows([_day()], menu, today_plates={"m-karak": _plate("6.410")})

    assert row.cost_per_portion is None
    assert row.cost_per_portion_today is None


def test_every_component_names_the_invoice_line_behind_its_price():
    """C12.4a: "every number traces to source" for a period figure needs no
    second read - the row carries the invoice line the price came from."""
    menu = _menu(
        _item(
            components=(
                contribution.RecipeComponent(
                    ingredient_id="i-milk",
                    ingredient_name="Milk Powder",
                    qty=D("0.030"),
                    unit="kg",
                    batch_cost=D("1.8423"),
                    invoice_id="inv-7",
                    line_position=3,
                    purchased_on=datetime.date(2026, 8, 25),
                ),
                contribution.RecipeComponent(
                    ingredient_id="i-cup",
                    ingredient_name="Paper Cup",
                    qty=D("1"),
                    unit="ea",
                    batch_cost=None,
                ),
            )
        )
    )
    (row,) = _rows([_day()], menu)

    milk, cup = row.components
    assert milk.ingredient_name == "Milk Powder"
    assert milk.cost_per_portion == D("1.842")
    assert (milk.invoice_id, milk.line_position) == ("inv-7", 3)
    assert milk.purchased_on == datetime.date(2026, 8, 25)
    assert cup.cost_per_portion is None


def test_the_todays_menu_price_sentence_appears_only_past_a_fil_of_difference():
    """The word *today's* is the point (C12.2): there is no price history, so
    a menu price raised since a closed period must never read as a discount.
    A fil either way is the per-line rounding, not a discount."""
    menu = _menu(_item())
    at_price = _rows([_day(qty_sold="10", positive="333.33")], menu)
    a_fil_off = _rows([_day(qty_sold="10", positive="333.43")], menu)
    discounted = _rows([_day(qty_sold="10", positive="300.00")], menu)

    def _sentence(rows):
        return [n for n in rows[0].notes if n.startswith("sold at an average")]

    assert _sentence(at_price) == []
    assert _sentence(a_fil_off) == []
    assert _sentence(discounted) == [
        "sold at an average AED 30.00 against today's menu price of AED 33.33"
    ]


# --- rolling the days up (C12.1, C12.6b) ------------------------------------


def _spread() -> list[contribution.ItemSales]:
    return [
        _day(offset=0, qty_sold="10", positive="333.33"),
        _day(offset=3, qty_sold="20", positive="666.66"),
        _day(offset=6, qty_sold="30", positive="999.99"),
        _day(branch=ROLLA, offset=6, qty_sold="5", positive="166.67"),
    ]


def test_the_period_and_the_branches_clipped_window_give_the_same_sum():
    """C12.6b: a day outside the loaded range has no sales rows at all, so the
    league's contribution and the item rows can never drift by a day."""
    days = _spread()
    over_period = _rows(contribution.days_in_period(days, PERIOD, branch_id=QUSAIS))
    over_window = _rows(contribution.days_in_window(days, WEEK, branch_id=QUSAIS))

    assert over_period[0].qty_sold == D("60.000")
    assert over_period[0].net_item_sales == D("1999.98")
    assert over_window[0].net_item_sales == over_period[0].net_item_sales
    assert over_window[0].contribution == over_period[0].contribution


def test_the_since_a_date_roll_up_takes_only_the_days_on_or_after_it():
    """What a price move is weighted by (C13.2): multiplying by the whole
    window would charge the owner for plates sold at the old price."""
    days = _spread()
    since = contribution.days_since(days, _on(3), branch_id=QUSAIS)
    (row,) = _rows(since)

    assert row.qty_sold == D("50.000")  # the 20 on day 3 and the 30 on day 6
    assert row.net_item_sales == D("1666.65")


def test_a_branch_filter_on_the_roll_ups_keeps_the_other_branch_out():
    days = _spread()
    assert len(contribution.days_in_period(days, PERIOD)) == 4
    assert len(contribution.days_in_period(days, PERIOD, branch_id=ROLLA)) == 1
    assert len(contribution.days_since(days, _on(6))) == 2


def test_a_day_outside_the_period_is_not_summed():
    days = [*_spread(), _day(offset=40, qty_sold="99", positive="9999.00")]
    (row,) = _rows(contribution.days_in_period(days, PERIOD, branch_id=QUSAIS))
    assert row.qty_sold == D("60.000")


# --- the league's order (C12.9) ---------------------------------------------


def _contribution(name: str, pct: str | None) -> contribution.Contribution:
    return contribution.Contribution(
        branch_id=f"b-{name.lower()}",
        branch_name=name,
        contribution=None if pct is None else D("100.00"),
        contribution_pct=None if pct is None else D(pct),
        net_item_sales=D("1000.00"),
        cost=None,
        costed_value=D("1000.00"),
        sales_value=D("1000.00"),
        costed_share_pct=D("100.0"),
        quality=ratio.Quality.RELIABLE,
        notes=(),
        sales_quality=ratio.Quality.RELIABLE,
        cost_quality=ratio.Quality.RELIABLE,
        items=1,
        items_without_numbers=0,
        unmapped=contribution.Unmapped(0, D(0)),
    )


def test_the_league_ranks_by_kept_percentage_lowest_first():
    """Not `ratio.rank`, which orders by purchases ÷ net sales (C12.9): the
    answer sentence names the top row, so the wrong key names the wrong
    branch."""
    ranked = contribution.rank(
        [
            _contribution("Al Nahda", "72.0"),
            _contribution("Rolla", "52.8"),
            _contribution("Deira", None),
            _contribution("Al Qusais", "60.9"),
        ]
    )
    assert [c.branch_name for c in ranked] == ["Rolla", "Al Qusais", "Al Nahda", "Deira"]


def test_the_league_breaks_a_tie_on_the_branch_name():
    ranked = contribution.rank(
        [_contribution("Zabeel", "60.0"), _contribution("Al Barsha", "60.0")]
    )
    assert [c.branch_name for c in ranked] == ["Al Barsha", "Zabeel"]
