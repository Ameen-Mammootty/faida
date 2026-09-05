"""M9 WP-90: the two new reads, against real Postgres (row 90).

The pure rules are proven in `test_contribution.py`; the pure tests never
execute a line of SQL, so everything below is the SQL itself:

  - `db.list_period_item_sales` - one row per branch, till item and business
    day, with the four sums and the no-quantity count C12.6a and C12.6 need,
    and the three roll-ups `contribution.py` takes from them;
  - the `as_of` bound on the three price reads (C12.4) - what it excludes,
    what it must not exclude, and a parity check that omitting it or passing
    None gives today's answers byte for byte, since no shipped caller passes
    it.

Sales are loaded through the real door (`POST /api/sales/days`), and papers
are confirmed through the real confirm path, so what is read back is what a
branch's own file and a branch's own delivery would have written.
"""

import datetime
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI

from faida_api import contribution, ratio
from faida_api.api import router as api_router
from faida_api.menu import _menu_context, _pricing
from faida_api.menu import router as menu_router
from faida_api.sales import router as sales_router
from faida_api.storage import Storage

from .conftest import AUTH, DEMO_TENANT_ID, FakeStorage, requires_db, wire_auth
from .test_plates import _catalog_item, _karak, _material, _supplier
from .test_sales_load import _item_day, _line

pytestmark = requires_db

TENANT = DEMO_TENANT_ID
BRANCH = "00000000-0000-0000-0000-000000000011"  # seed.sql's branch
BRANCH_2 = "00000000-0000-0000-0000-000000000012"

DAY_ONE = datetime.date(2026, 8, 25)
PERIOD = ratio.Period(datetime.date(2026, 8, 4), datetime.date(2026, 8, 31))
AS_OF = datetime.date(2026, 8, 31)


def _on(offset: int) -> datetime.date:
    return DAY_ONE + datetime.timedelta(days=offset)


def _iso(offset: int) -> str:
    return _on(offset).isoformat()


@pytest.fixture
def api(settings, db):
    app = FastAPI()
    app.include_router(api_router)
    app.include_router(menu_router)
    app.include_router(sales_router)
    app.state.settings = settings
    wire_auth(app)
    app.state.db = db
    app.state.storage = Storage(settings, transport=FakeStorage().transport())
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _second_branch(db) -> None:
    await db.pool.execute(
        "insert into branches (id, tenant_id, name, timezone) values ($1, $2, $3, 'Asia/Dubai')",
        BRANCH_2,
        TENANT,
        "Rolla Branch",
    )


async def _load(api, days: list[dict]) -> dict:
    response = await api.post("/api/sales/days", json={"days": days}, headers=AUTH)
    assert response.status_code == 200, response.text
    return response.json()


async def _read(db, date_from=PERIOD.start, date_to=PERIOD.end) -> list[contribution.ItemSales]:
    return [
        contribution.ItemSales(
            branch_id=row["branch_id"],
            business_date=row["business_date"],
            till_item_id=row["till_item_id"],
            name=row["name"],
            code=row["code"],
            menu_item_id=row["menu_item_id"],
            excluded=row["excluded_at"] is not None,
            qty_sold=row["qty_sold"],
            qty_refunded=row["qty_refunded"],
            positive_value=row["positive_value"],
            refund_value=row["refund_value"],
            no_qty_lines=row["no_qty_lines"],
        )
        for row in await db.list_period_item_sales(
            tenant_id=TENANT, date_from=date_from, date_to=date_to
        )
    ]


# --- the item-day read ------------------------------------------------------


@requires_db
async def test_the_read_returns_one_row_per_branch_till_item_and_day(api, db):
    """The grain M9 needs: a period total cannot be un-summed back into the
    days two of the three signals weigh (C12.1)."""
    await _second_branch(db)
    await _load(
        api,
        [
            _item_day(
                _iso(0),
                [
                    _line(0, "KARAK", "100.00", code="52a", qty="10"),
                    _line(1, "CHICKEN 65", "200.00", code="61a", qty="4"),
                ],
                basis="exclusive",
            ),
            _item_day(
                _iso(1),
                [_line(0, "KARAK", "150.00", code="52a", qty="15")],
                basis="exclusive",
            ),
            _item_day(
                _iso(1),
                [_line(0, "KARAK", "80.00", code="52a", qty="8")],
                branch=BRANCH_2,
                basis="exclusive",
            ),
        ],
    )

    rows = await _read(db)
    assert len(rows) == 4
    assert [(r.branch_id, r.business_date, r.name, r.qty_sold) for r in rows] == [
        (BRANCH, _on(0), "CHICKEN 65", Decimal("4.000")),
        (BRANCH, _on(0), "KARAK", Decimal("10.000")),
        (BRANCH, _on(1), "KARAK", Decimal("15.000")),
        (BRANCH_2, _on(1), "KARAK", Decimal("8.000")),
    ]


@requires_db
async def test_one_till_item_selling_in_two_branches_stays_two_rows(api, db):
    """A branch is a grouping key, which `db.list_period_sales_lines` never
    had: a per-branch item figure needs it (M9 §2)."""
    await _second_branch(db)
    await _load(
        api,
        [
            _item_day(
                _iso(0), [_line(0, "KARAK", "100.00", code="52a", qty="10")], basis="exclusive"
            ),
            _item_day(
                _iso(0),
                [_line(0, "KARAK", "60.00", code="52a", qty="6")],
                branch=BRANCH_2,
                basis="exclusive",
            ),
        ],
    )

    rows = await _read(db)
    assert {r.branch_id for r in rows} == {BRANCH, BRANCH_2}
    assert len({r.till_item_id for r in rows}) == 1  # one till item, two branches


@requires_db
async def test_the_lines_with_no_quantity_are_counted_and_never_guessed(api, db):
    """A quantity is never derived from money ÷ menu price (C12.6): the read
    counts the lines that printed none and leaves the sum partial."""
    await _load(
        api,
        [
            _item_day(
                _iso(0),
                [
                    _line(0, "KARAK", "100.00", code="52a", qty="10"),
                    _line(1, "KARAK LARGE", "60.00", code="52a"),
                    _line(2, "KARAK LARGE", "40.00", code="52a"),
                ],
                basis="exclusive",
            )
        ],
    )

    (row,) = await _read(db)
    assert row.no_qty_lines == 2
    assert row.qty_sold == Decimal("10.000")  # partial, and the count says so
    assert row.positive_value == Decimal("200.00")


@requires_db
async def test_both_printings_of_a_refund_reach_the_same_two_sums(api, db):
    """C12.6a in SQL: the bucket is chosen by the **amount's** sign, so a till
    that prints `qty 1, amount -20` and a till that prints `qty -1` produce
    identical portions sold and portions refunded."""
    await _second_branch(db)
    await _load(
        api,
        [
            _item_day(
                _iso(0),
                [
                    _line(0, "KARAK", "200.00", code="52a", qty="10"),
                    _line(1, "KARAK", "-20.00", code="52a", qty="1"),
                ],
                basis="exclusive",
            ),
            _item_day(
                _iso(0),
                [
                    _line(0, "KARAK", "200.00", code="52a", qty="10"),
                    _line(1, "KARAK", "-20.00", code="52a", qty="-1"),
                ],
                branch=BRANCH_2,
                basis="exclusive",
            ),
        ],
    )

    positive_printing, negative_printing = await _read(db)
    for row in (positive_printing, negative_printing):
        assert row.qty_sold == Decimal("10.000")
        assert row.qty_refunded == Decimal("1.000")
        assert row.positive_value == Decimal("200.00")
        assert row.refund_value == Decimal("-20.00")


@requires_db
async def test_a_line_at_exactly_zero_counts_its_portions_and_no_money(api, db):
    """A comped plate still cost the kitchen its ingredients; it just took no
    money. The quantity filter is `>= 0` and the money filter `> 0`, so the
    portion is counted and the value is not."""
    await _load(
        api,
        [
            _item_day(
                _iso(0),
                [
                    _line(0, "KARAK", "0.00", code="52a", qty="2"),
                    _line(1, "KARAK", "100.00", code="52a", qty="10"),
                ],
                basis="exclusive",
            )
        ],
    )

    (row,) = await _read(db)
    assert row.qty_sold == Decimal("12.000")
    assert row.positive_value == Decimal("100.00")


@requires_db
async def test_the_menu_item_and_the_exclusion_are_read_through_the_till_item(api, db):
    """`sales_lines` carries no menu item on purpose (0019:189-190), so a
    remap corrects every past day at once - and this read must show it."""
    await _load(
        api,
        [
            _item_day(
                _iso(0),
                [
                    _line(0, "KARAK", "100.00", code="52a", qty="10"),
                    _line(1, "DELIVERY", "20.00", code="99"),
                ],
                basis="exclusive",
            )
        ],
    )
    rows = await _read(db)
    assert all(row.menu_item_id is None and not row.excluded for row in rows)

    delivery = await db.pool.fetchval(
        "select id::text from till_items where tenant_id = $1 and name = 'DELIVERY'", TENANT
    )
    await db.exclude_till_item(delivery, tenant_id=TENANT, actor="console")

    rows = await _read(db)
    assert [r.excluded for r in rows if r.name == "DELIVERY"] == [True]


# --- the roll-ups the pure module does (C12.1, C12.6b) ----------------------


@requires_db
async def test_the_period_window_and_since_roll_ups_agree_with_hand_sums(api, db):
    """The three scopes `contribution.py` takes from one read, checked against
    sums done by hand - including C12.6b's invariant that a branch's clipped
    window and the whole period give the same figure, because a day outside
    the loaded range has no sales rows at all."""
    await _load(
        api,
        [
            _item_day(
                _iso(offset), [_line(0, "KARAK", amount, code="52a", qty=qty)], basis="exclusive"
            )
            for offset, amount, qty in (
                (0, "100.00", "10"),
                (2, "200.00", "20"),
                (4, "300.00", "30"),
            )
        ],
    )
    rows = await _read(db)

    days = [
        ratio.SalesDay(
            branch_id=row["branch_id"],
            business_date=row["business_date"],
            net_sales=row["net_sales"],
            takings=row["takings"],
            granularity=row["granularity"],
        )
        for row in await db.list_sales_days(
            tenant_id=TENANT, date_from=PERIOD.start, date_to=PERIOD.end
        )
    ]
    branch_row = ratio.period_row(
        branch_id=BRANCH,
        branch_name="Al Qusais Branch",
        days=days,
        invoices=[],
        period=PERIOD,
        tenant_currency="AED",
    )
    assert branch_row.window == ratio.Window(_on(0), _on(4))

    def _total(scope) -> tuple[Decimal, Decimal]:
        return (
            sum((r.qty_sold for r in scope), Decimal(0)),
            sum((r.positive_value for r in scope), Decimal(0)),
        )

    assert _total(contribution.days_in_period(rows, PERIOD, branch_id=BRANCH)) == (
        Decimal("60.000"),
        Decimal("600.00"),
    )
    # C12.6b: clipping to the branch's own loaded range changes nothing.
    assert _total(contribution.days_in_window(rows, branch_row.window, branch_id=BRANCH)) == _total(
        contribution.days_in_period(rows, PERIOD, branch_id=BRANCH)
    )
    # The since-a-date roll-up a price move is weighted by (C13.2).
    assert _total(contribution.days_since(rows, _on(2), branch_id=BRANCH)) == (
        Decimal("50.000"),
        Decimal("500.00"),
    )


# --- `as_of` on the three price reads (C12.4) -------------------------------


async def _delivery(
    db,
    supplier_item_id: str,
    *,
    supplier_id: str,
    unit_price: Decimal,
    pack_size: str | None,
    invoice_date: datetime.date | None,
    confirmed_on: datetime.date | None = None,
    raw_name: str = "Delivery line",
) -> str:
    """One confirmed delivery through the real confirm path, with the printed
    date and the confirm day both under the test's control - the two the
    `purchased_on` coalesce chooses between."""
    document_id = await db.pool.fetchval(
        "insert into documents (tenant_id, source, status) values ($1, 'manual', 'extracted') "
        "returning id",
        TENANT,
    )
    invoice_id = await db.pool.fetchval(
        """
        insert into invoices (tenant_id, document_id, supplier_id, status, total, invoice_date)
        values ($1, $2, $3, 'awaiting_confirm', $4, $5)
        returning id::text
        """,
        TENANT,
        document_id,
        supplier_id,
        unit_price,
        invoice_date,
    )
    await db.pool.execute(
        """
        insert into invoice_lines (tenant_id, invoice_id, position, raw_name, supplier_item_id,
                                   qty, pack_size, unit_price, line_total)
        values ($1, $2, 0, $3, $4, 1, $5, $6, $6)
        """,
        TENANT,
        invoice_id,
        raw_name,
        supplier_item_id,
        pack_size,
        unit_price,
    )
    assert await db.confirm_invoice(invoice_id, tenant_id=TENANT, actor="console") is True
    if confirmed_on is not None:
        await db.pool.execute(
            "update invoices set confirmed_at = $2 where id = $1",
            invoice_id,
            datetime.datetime.combine(confirmed_on, datetime.time(9, 0), datetime.UTC),
        )
    return invoice_id


async def _tea_price(db, *, as_of=None) -> Decimal:
    rows = await db.list_mapped_pack_costs(tenant_id=TENANT, as_of=as_of)
    return next(r["cost_per_base_unit"] for r in rows if r["canonical_name"] == "CTC TEA 5KG")


@requires_db
async def test_a_paper_printed_after_the_period_is_not_in_the_periods_price(api, db):
    """The whole point of C12.4: a closed period must not move when the next
    delivery lands. July's tea is AED 90 for 5 kg; September's is AED 150."""
    scenario = await _karak(db, api)
    await _delivery(
        db,
        scenario["tea_pack"],
        supplier_id=scenario["supplier_id"],
        unit_price=Decimal("150.00"),
        pack_size="5kg",
        invoice_date=datetime.date(2026, 9, 3),
        raw_name="CTC TEA 5KG",
    )

    assert await _tea_price(db) == Decimal("0.03")  # today: 150.00 / 5000 g
    assert await _tea_price(db, as_of=AS_OF) == Decimal("0.018")  # 90.00 / 5000 g


@requires_db
async def test_a_back_dated_paper_confirmed_late_is_inside_the_period(api, db):
    """Both reads place a paper by its **printed** date (`db.py`'s coalesce),
    so a delivery that printed on 28 August and was confirmed in September
    counts in August - and the drill says why the figure moved."""
    scenario = await _karak(db, api)
    await _delivery(
        db,
        scenario["tea_pack"],
        supplier_id=scenario["supplier_id"],
        unit_price=Decimal("120.00"),
        pack_size="5kg",
        invoice_date=datetime.date(2026, 8, 28),
        confirmed_on=datetime.date(2026, 9, 9),
        raw_name="CTC TEA 5KG",
    )

    assert await _tea_price(db, as_of=AS_OF) == Decimal("0.024")  # 120.00 / 5000 g


@requires_db
async def test_a_paper_with_no_printed_date_lands_on_its_confirm_day(api, db):
    """Outside the period's prices and outside its purchases alike: with no
    printed date the confirm day is the only date there is."""
    scenario = await _karak(db, api)
    await _delivery(
        db,
        scenario["tea_pack"],
        supplier_id=scenario["supplier_id"],
        unit_price=Decimal("150.00"),
        pack_size="5kg",
        invoice_date=None,
        confirmed_on=datetime.date(2026, 9, 9),
        raw_name="CTC TEA 5KG",
    )

    assert await _tea_price(db) == Decimal("0.03")
    assert await _tea_price(db, as_of=AS_OF) == Decimal("0.018")


@requires_db
async def test_a_same_day_tie_is_broken_the_way_the_shipped_read_breaks_it(api, db):
    """Two papers printed on one day: the later confirm wins, `as_of` or no
    `as_of`, so a bounded read cannot quietly reorder the answers."""
    scenario = await _karak(db, api)
    await _delivery(
        db,
        scenario["tea_pack"],
        supplier_id=scenario["supplier_id"],
        unit_price=Decimal("100.00"),
        pack_size="5kg",
        invoice_date=datetime.date(2026, 8, 20),
        confirmed_on=datetime.date(2026, 8, 21),
        raw_name="CTC TEA 5KG",
    )
    await _delivery(
        db,
        scenario["tea_pack"],
        supplier_id=scenario["supplier_id"],
        unit_price=Decimal("110.00"),
        pack_size="5kg",
        invoice_date=datetime.date(2026, 8, 20),
        confirmed_on=datetime.date(2026, 8, 22),
        raw_name="CTC TEA 5KG",
    )

    assert await _tea_price(db) == Decimal("0.022")  # 110.00 / 5000 g
    assert await _tea_price(db, as_of=AS_OF) == Decimal("0.022")


@requires_db
async def test_a_blocked_purchase_after_the_period_does_not_mark_the_plate_stale(api, db):
    """The D11 stale flag caps a plate at *estimated* when the newest purchase
    could not be costed. Bounded by `as_of`, a bare carton that arrived in
    September must not reach back and estimate August."""
    scenario = await _karak(db, api)
    await _delivery(
        db,
        scenario["tea_pack"],
        supplier_id=scenario["supplier_id"],
        unit_price=Decimal("150.00"),
        pack_size=None,  # no pack size: a purchase that cannot be costed
        invoice_date=datetime.date(2026, 9, 3),
        raw_name="CTC TEA CARTON",
    )

    today = {
        row["ingredient_id"]: row
        for row in await db.list_newest_purchases(tenant_id=TENANT)
        if not row["costed"]
    }
    assert scenario["tea"] in today

    bounded = {
        row["ingredient_id"]: row
        for row in await db.list_newest_purchases(tenant_id=TENANT, as_of=AS_OF)
        if not row["costed"]
    }
    assert bounded == {}

    _, _, plate_by_item, _, _ = await _menu_context(db, TENANT)
    assert plate_by_item[scenario["item_id"]].quality.value == "estimated"
    _, _, as_of_plates, _, _ = await _menu_context(db, TENANT, as_of=AS_OF)
    assert as_of_plates[scenario["item_id"]].quality.value == "reliable_with_limitations"
    assert as_of_plates[scenario["item_id"]].cost_per_portion == Decimal("0.752")


@requires_db
async def test_a_price_move_pair_dated_after_the_period_is_not_compared(api, db):
    """C13.2: the move a signal reports is the newest one at or before the
    period's end, or a September delivery would be multiplied by August's
    sales and the sentence would name a rise the window never paid for."""
    scenario = await _karak(db, api)
    await _delivery(
        db,
        scenario["tea_pack"],
        supplier_id=scenario["supplier_id"],
        unit_price=Decimal("150.00"),
        pack_size="5kg",
        invoice_date=datetime.date(2026, 9, 3),
        raw_name="CTC TEA 5KG",
    )

    def _tea_pairs(rows):
        return [r for r in rows if r["ingredient_id"] == scenario["tea"]]

    today = _tea_pairs(await db.list_price_move_pairs(tenant_id=TENANT))
    assert [r["cost_per_base_unit"] for r in today] == [Decimal("0.03"), Decimal("0.018")]

    bounded = _tea_pairs(await db.list_price_move_pairs(tenant_id=TENANT, as_of=AS_OF))
    assert [r["cost_per_base_unit"] for r in bounded] == [Decimal("0.018")]
    # One line is a price, not a move: the caller needs two to compare.
    assert len(bounded) == 1


@requires_db
async def test_omitting_as_of_and_passing_none_return_the_same_rows(api, db):
    """No shipped caller passes the argument, so this is the guard that adding
    it moved nothing: `/menu`'s answers are identical either way, byte for
    byte, on a tenant with a costed menu, a blocked purchase and a price
    move."""
    scenario = await _karak(db, api)
    supplier_id = scenario["supplier_id"]
    await _delivery(
        db,
        scenario["tea_pack"],
        supplier_id=supplier_id,
        unit_price=Decimal("110.00"),
        pack_size="5kg",
        invoice_date=datetime.date(2026, 8, 20),
        raw_name="CTC TEA 5KG",
    )
    salt_pack = await _catalog_item(db, await _supplier(db), "ROCK SALT 1KG", "1kg")
    await _delivery(
        db,
        salt_pack,
        supplier_id=supplier_id,
        unit_price=Decimal("4.00"),
        pack_size=None,
        invoice_date=datetime.date(2026, 8, 22),
        raw_name="ROCK SALT CARTON",
    )
    await _material(db, salt_pack, "Rock Salt", "g")

    for read in (db.list_mapped_pack_costs, db.list_newest_purchases, db.list_price_move_pairs):
        omitted = await read(tenant_id=TENANT)
        explicit = await read(tenant_id=TENANT, as_of=None)
        assert omitted, f"{read.__name__} returned nothing to compare"
        assert [dict(row) for row in omitted] == [dict(row) for row in explicit]

    assert await _pricing(db, TENANT) == await _pricing(db, TENANT, as_of=None)

    menu = await api.get("/api/menu-items", headers=AUTH)
    moves = await api.get("/api/price-moves", headers=AUTH)
    assert menu.status_code == 200 and moves.status_code == 200
    # 4 g of tea at 110.00/5 kg + 60 ml of milk at 8.00/l + one 0.20 cup.
    assert menu.json()["menu_items"][0]["plate"]["cost_per_portion"] == "0.768"
    assert moves.json()["moves"][0]["kind"] == "moved"
