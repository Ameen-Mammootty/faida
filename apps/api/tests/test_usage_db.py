"""M12 WP-120: `db.list_period_material_purchases` against real Postgres.

The pure roll-up lives in `usage.py` and is proven without a database. This
file is the SQL underneath it: which confirmed stock lines a period holds,
what travels on each one, and - the half that matters more - what the read
must never quietly leave out. C14.3's rule is that price and currency are not
filters and nothing unplaceable is dropped, because a read that silently drops
a line presents part of what was bought as the whole of it.

Everything is staged through the real doors: papers confirmed through
`db.confirm_invoice`, so a line's frozen cost factor is written by the same
transaction that confirmed it, and the pack-size override typed at
`POST /api/supplier-items/{id}/pack-size`, the screen a person actually uses.
"""

import datetime
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI

from faida_api.api import router as api_router
from faida_api.menu import router as menu_router

from .conftest import AUTH, DEMO_TENANT_ID, requires_db, wire_auth
from .test_plates import _catalog_item, _material, _menu_item, _recipe, _supplier

pytestmark = requires_db

TENANT = DEMO_TENANT_ID
BRANCH = "00000000-0000-0000-0000-000000000011"  # seed.sql's branch
BRANCH_2 = "00000000-0000-0000-0000-000000000012"

OTHER_TENANT = "00000000-0000-0000-0000-0000000000ff"
OTHER_BRANCH = "00000000-0000-0000-0000-0000000000fe"

FROM = datetime.date(2026, 8, 4)
TO = datetime.date(2026, 8, 31)

INSIDE = datetime.date(2026, 8, 10)
INSIDE_LATER = datetime.date(2026, 8, 20)
DAY_BEFORE = FROM - datetime.timedelta(days=1)
DAY_AFTER = TO + datetime.timedelta(days=1)


@pytest.fixture
def api(settings, db):
    app = FastAPI()
    app.include_router(api_router)
    app.include_router(menu_router)
    app.state.settings = settings
    wire_auth(app)
    app.state.db = db
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


# --- staging, through the real doors ----------------------------------------


def _line(
    raw_name: str,
    *,
    supplier_item_id: str | None = None,
    qty: str | None = "1",
    unit: str | None = None,
    pack_size: str | None = None,
    unit_price: str | None = "10.00",
    line_total: str | None = None,
    line_kind: str = "stock_item",
) -> dict:
    return {
        "raw_name": raw_name,
        "supplier_item_id": supplier_item_id,
        "qty": None if qty is None else Decimal(qty),
        "unit": unit,
        "pack_size": pack_size,
        "unit_price": None if unit_price is None else Decimal(unit_price),
        "line_total": None if line_total is None else Decimal(line_total),
        "line_kind": line_kind,
    }


async def _paper(
    db,
    lines: list[dict],
    *,
    supplier_id: str | None,
    tenant_id: str = TENANT,
    branch_id: str | None = BRANCH,
    invoice_date: datetime.date | None = INSIDE,
    confirmed_on: datetime.date | None = None,
    currency: str = "AED",
    invoice_no: str | None = "INV-1",
    total: str = "100.00",
    confirm: bool = True,
) -> str:
    """One paper with its lines, confirmed through the real confirm path so
    every cost the confirm transaction can freeze is frozen the way a real
    delivery freezes it. `confirm=False` leaves it awaiting confirm - a paper
    that is nobody's purchases yet."""
    document_id = await db.pool.fetchval(
        "insert into documents (tenant_id, source, status) values ($1, 'manual', 'extracted') "
        "returning id",
        tenant_id,
    )
    invoice_id = await db.pool.fetchval(
        """
        insert into invoices (tenant_id, branch_id, document_id, supplier_id, status,
                              total, invoice_date, currency, invoice_no)
        values ($1, $2, $3, $4, 'awaiting_confirm', $5, $6, $7, $8)
        returning id::text
        """,
        tenant_id,
        branch_id,
        document_id,
        supplier_id,
        Decimal(total),
        invoice_date,
        currency,
        invoice_no,
    )
    for position, line in enumerate(lines):
        await db.pool.execute(
            """
            insert into invoice_lines (tenant_id, invoice_id, position, raw_name,
                                       supplier_item_id, qty, unit, pack_size, unit_price,
                                       line_total, line_kind)
            values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
            tenant_id,
            invoice_id,
            position,
            line["raw_name"],
            line["supplier_item_id"],
            line["qty"],
            line["unit"],
            line["pack_size"],
            line["unit_price"],
            line["line_total"],
            line["line_kind"],
        )
    if confirm:
        assert await db.confirm_invoice(invoice_id, tenant_id=tenant_id, actor="console") is True, (
            invoice_id
        )
        if confirmed_on is not None:
            await db.pool.execute(
                "update invoices set confirmed_at = $2 where id = $1",
                invoice_id,
                datetime.datetime.combine(confirmed_on, datetime.time(9, 0), datetime.UTC),
            )
    return invoice_id


async def _second_branch(db) -> None:
    await db.pool.execute(
        "insert into branches (id, tenant_id, name, timezone) values ($1, $2, $3, 'Asia/Dubai')",
        BRANCH_2,
        TENANT,
        "Rolla Branch",
    )


async def _read(db, date_from: datetime.date = FROM, date_to: datetime.date = TO) -> list:
    return await db.list_period_material_purchases(
        tenant_id=TENANT, date_from=date_from, date_to=date_to
    )


def _by_name(rows) -> dict:
    return {row["raw_name"]: row for row in rows}


@pytest.fixture
async def stage(db, api):
    """Two branches, three packs - two mapped to materials, one with no
    material yet - and a pack-size override typed for a bare carton."""
    await _second_branch(db)
    supplier_id = await _supplier(db, "Gulf Foods Trading L.L.C.")
    tea = await _catalog_item(db, supplier_id, "CTC TEA 5KG", "5kg")
    milk = await _catalog_item(db, supplier_id, "EVAP MILK 1L", "1l")
    carton = await _catalog_item(db, supplier_id, "Chicken Carton", "1 ctn")
    return {
        "supplier_id": supplier_id,
        "tea": tea,
        "milk": milk,
        "carton": carton,
        "tea_material": await _material(db, tea, "CTC Black Tea", "g"),
        "milk_material": await _material(db, milk, "Evaporated Milk", "ml"),
    }


# --- the period boundary ----------------------------------------------------


@requires_db
async def test_the_period_holds_its_own_days_and_neither_neighbour(db, stage):
    """The window is inclusive at both ends, and a paper printed the day
    before or the day after belongs to another period's figures."""
    for printed, name in (
        (DAY_BEFORE, "TOO EARLY"),
        (FROM, "FIRST DAY"),
        (INSIDE, "MIDDLE"),
        (TO, "LAST DAY"),
        (DAY_AFTER, "TOO LATE"),
    ):
        await _paper(
            db,
            [_line(name, supplier_item_id=stage["tea"], pack_size="5kg")],
            supplier_id=stage["supplier_id"],
            invoice_date=printed,
        )

    rows = await _read(db)
    assert [row["raw_name"] for row in rows] == ["FIRST DAY", "MIDDLE", "LAST DAY"]
    assert [row["purchased_on"] for row in rows] == [FROM, INSIDE, TO]


@requires_db
async def test_a_paper_that_printed_no_date_sits_on_the_day_it_was_confirmed(db, stage):
    """`purchased_on` is the printed date with confirm time in UTC as the
    tie-breaker - the same coalesce costing ranks by and the ratio reads
    periods by, so one paper sits in the same week on every screen."""
    await _paper(
        db,
        [_line("UNDATED SACK", supplier_item_id=stage["tea"], pack_size="5kg")],
        supplier_id=stage["supplier_id"],
        invoice_date=None,
        confirmed_on=INSIDE_LATER,
    )

    rows = await _read(db)
    assert [(row["raw_name"], row["purchased_on"]) for row in rows] == [
        ("UNDATED SACK", INSIDE_LATER)
    ]

    # And the same paper is outside a period that ends before its confirm day.
    assert await _read(db, FROM, INSIDE) == []


# --- price and currency are not filters (C14.3) -----------------------------


@requires_db
async def test_a_line_the_camera_missed_the_price_of_still_delivered_goods(db, stage):
    """C14.3. The sack arrived whatever the photo said about its price, so
    the line comes back - with no frozen factor, because a cost is the one
    thing a missing price does prevent."""
    await _paper(
        db,
        [
            _line("PRICED SACK", supplier_item_id=stage["tea"], pack_size="5kg", unit_price="90"),
            _line("NO PRICE SACK", supplier_item_id=stage["tea"], pack_size="5kg", unit_price=None),
        ],
        supplier_id=stage["supplier_id"],
    )

    rows = _by_name(await _read(db))
    assert set(rows) == {"PRICED SACK", "NO PRICE SACK"}
    assert rows["NO PRICE SACK"]["unit_price"] is None
    assert rows["NO PRICE SACK"]["frozen_factor"] is None
    assert rows["PRICED SACK"]["frozen_factor"] == Decimal("5000")


@requires_db
async def test_the_frozen_factor_is_the_one_the_cost_was_divided_by(db, stage):
    """D2: the stored factor is the fact. It is `cost_basis`'s own
    `pack_base_quantity` - what one unit price bought, in base units - so a
    line's quantity and its cost can never come from two readings of one box."""
    invoice_id = await _paper(
        db,
        [_line("CTC TEA 5KG", supplier_item_id=stage["tea"], pack_size="5kg", unit_price="90")],
        supplier_id=stage["supplier_id"],
    )
    basis = await db.pool.fetchval(
        "select cost_basis->>'pack_base_quantity' from invoice_lines where invoice_id = $1",
        invoice_id,
    )

    (row,) = await _read(db)
    assert row["frozen_factor"] == Decimal(basis)
    assert row["frozen_factor"] == Decimal("5000")


@requires_db
async def test_a_paper_billed_in_another_currency_is_counted_by_quantity(db, stage):
    """WP-28 holds the *prices* of a USD paper, not its goods: the milk
    arrived. It comes back with its currency on it, so the caller can name
    the paper rather than drop it, and with no frozen factor, because the
    confirm transaction costs no foreign line at all.

    D3's own case rides on the same paper: `record_confirmed_prices` returns
    before its line loop on a foreign paper, so a line extraction did not snap
    to a known product never gets one - an orphan, in no row and no queue."""
    await _paper(
        db,
        [
            _line("EVAP MILK 1L", supplier_item_id=stage["milk"], pack_size="1l", unit_price="20"),
            _line("UNKNOWN PASTE 800G", supplier_item_id=None, unit_price="12"),
        ],
        supplier_id=stage["supplier_id"],
        currency="USD",
    )

    rows = _by_name(await _read(db))
    assert set(rows) == {"EVAP MILK 1L", "UNKNOWN PASTE 800G"}
    assert [row["currency"] for row in rows.values()] == ["USD", "USD"]
    milk = rows["EVAP MILK 1L"]
    assert milk["qty"] == Decimal("1.000")
    assert milk["frozen_factor"] is None
    assert milk["ingredient_id"] == stage["milk_material"]
    assert rows["UNKNOWN PASTE 800G"]["supplier_item_id"] is None


@requires_db
async def test_a_return_travels_with_the_sign_the_paper_printed(db, stage):
    """A credit line is a negative quantity; the read hands it over as
    printed and `usage.py` nets it, so a return is never counted as a
    purchase and never silently dropped."""
    await _paper(
        db,
        [
            _line("CTC TEA 5KG", supplier_item_id=stage["tea"], pack_size="5kg", qty="4"),
            _line(
                "CTC TEA 5KG Credit: one sack returned",
                supplier_item_id=stage["tea"],
                pack_size="5kg",
                qty="-1",
                line_total="-90.00",
            ),
        ],
        supplier_id=stage["supplier_id"],
    )

    rows = await _read(db)
    assert [row["qty"] for row in rows] == [Decimal("4.000"), Decimal("-1.000")]


# --- nothing unplaceable is dropped -----------------------------------------


@requires_db
async def test_a_pack_with_no_material_is_still_a_purchase_of_something(db, stage):
    """Codex 3. A pack nobody has merged onto a material yet comes back with
    `ingredient_id` null and its product id set: a real purchase, reported
    beside the panel with a link to the materials queue rather than presented
    as if it never happened."""
    await _paper(
        db,
        [_line("Chicken Carton", supplier_item_id=stage["carton"], pack_size="1 ctn")],
        supplier_id=stage["supplier_id"],
    )

    (row,) = await _read(db)
    assert row["ingredient_id"] is None
    assert row["supplier_item_id"] == stage["carton"]
    assert row["canonical_name"] == "Chicken Carton"


@requires_db
async def test_a_line_that_reached_no_product_comes_back_as_an_orphan(db, stage):
    """D3. `record_confirmed_prices` skips a line with no quantity or no
    price, so no catalog product is created for it - and a product is the only
    path to a material. The read returns it with `supplier_item_id` null so
    the caller can count it under `orphans` with its paper, in no row and no
    queue, instead of a material row quietly missing a delivery."""
    await _paper(
        db,
        [
            _line("MYSTERY SACK", supplier_item_id=None, unit_price=None, pack_size="5kg"),
            _line("NO QTY SACK", supplier_item_id=None, qty=None, pack_size="5kg"),
        ],
        supplier_id=stage["supplier_id"],
    )

    rows = _by_name(await _read(db))
    assert set(rows) == {"MYSTERY SACK", "NO QTY SACK"}
    for row in rows.values():
        assert row["supplier_item_id"] is None
        assert row["ingredient_id"] is None
        assert row["canonical_name"] is None
        assert row["frozen_factor"] is None
    # The paper is still named, so the owner can open the photo and look.
    assert rows["MYSTERY SACK"]["invoice_no"] == "INV-1"
    assert rows["MYSTERY SACK"]["supplier_name"] == "Gulf Foods Trading L.L.C."


@requires_db
async def test_a_paper_nobodys_phone_sent_comes_back_with_no_branch(db, stage):
    """C14.9. A confirmed paper with no branch belongs to no branch's shelf
    and no clipped window, so it is listed under `unassigned` and summed into
    no row - which it can only be if the read hands it over saying so."""
    await _paper(
        db,
        [_line("CTC TEA 5KG", supplier_item_id=stage["tea"], pack_size="5kg")],
        supplier_id=stage["supplier_id"],
        branch_id=None,
    )

    (row,) = await _read(db)
    assert row["branch_id"] is None


# --- what the read must not return ------------------------------------------


@requires_db
async def test_a_paper_still_awaiting_confirm_is_nobodys_purchase(db, stage):
    """Nothing unconfirmed moves a figure, here as everywhere else: a paper
    waiting for someone to say OK has not been checked by a human yet."""
    await _paper(
        db,
        [_line("PENDING SACK", supplier_item_id=stage["tea"], pack_size="5kg")],
        supplier_id=stage["supplier_id"],
        confirm=False,
    )

    assert await _read(db) == []


@requires_db
async def test_a_delivery_charge_delivers_nothing(db, stage):
    """WP-18: a charge line is cost, not stock. Counting a cool-box hire as a
    quantity of anything would put a fee on a material's shelf."""
    await _paper(
        db,
        [
            _line("CTC TEA 5KG", supplier_item_id=stage["tea"], pack_size="5kg"),
            _line("Delivery charge", unit_price="25.00", line_kind="charge"),
        ],
        supplier_id=stage["supplier_id"],
    )

    assert [row["raw_name"] for row in await _read(db)] == ["CTC TEA 5KG"]


@requires_db
async def test_another_tenants_deliveries_are_never_in_this_tenants_period(db, stage):
    """Every console-reachable read is scoped by tenant; a chain must never
    see another chain's purchases on its own shelf."""
    await db.pool.execute(
        "insert into tenants (id, name, currency) values ($1, 'Other Group', 'AED')", OTHER_TENANT
    )
    await db.pool.execute(
        "insert into branches (id, tenant_id, name, timezone) "
        "values ($1, $2, 'Other', 'Asia/Dubai')",
        OTHER_BRANCH,
        OTHER_TENANT,
    )
    other_supplier = await db.pool.fetchval(
        "insert into suppliers (tenant_id, name) values ($1, 'Other Foods') returning id::text",
        OTHER_TENANT,
    )
    other_pack = await db.pool.fetchval(
        "insert into supplier_items (tenant_id, supplier_id, canonical_name, pack_size) "
        "values ($1, $2, 'OTHER TEA 5KG', '5kg') returning id::text",
        OTHER_TENANT,
        other_supplier,
    )
    await _paper(
        db,
        [_line("OTHER TEA 5KG", supplier_item_id=other_pack, pack_size="5kg")],
        supplier_id=other_supplier,
        tenant_id=OTHER_TENANT,
        branch_id=OTHER_BRANCH,
    )
    await _paper(
        db,
        [_line("CTC TEA 5KG", supplier_item_id=stage["tea"], pack_size="5kg")],
        supplier_id=stage["supplier_id"],
    )

    assert [row["raw_name"] for row in await _read(db)] == ["CTC TEA 5KG"]


# --- the person's answer, and the names beside it ---------------------------


@requires_db
async def test_the_pack_size_a_person_typed_travels_with_that_packs_lines(db, api, stage):
    """WP-55 through its own door. `units.py` refuses to guess what a carton
    holds, so a person answers once on the blocked-costs screen - and that
    answer has to reach every line of that product, including the ones bought
    before it was given, or the same box measures two ways."""
    await _paper(
        db,
        [
            _line("Chicken Carton", supplier_item_id=stage["carton"], pack_size="1 ctn"),
            _line("CTC TEA 5KG", supplier_item_id=stage["tea"], pack_size="5kg"),
        ],
        supplier_id=stage["supplier_id"],
    )

    before = _by_name(await _read(db))
    assert before["Chicken Carton"]["pack_size_override"] is None
    assert before["Chicken Carton"]["frozen_factor"] is None  # nothing on it read as an amount

    answered = await api.post(
        f"/api/supplier-items/{stage['carton']}/pack-size",
        json={"pack_size": "10 kg"},
        headers=AUTH,
    )
    assert answered.status_code == 200, answered.text
    assert answered.json()["lines_costed"] == 1

    after = _by_name(await _read(db))
    assert after["Chicken Carton"]["pack_size_override"] == "10 kg"
    assert after["Chicken Carton"]["frozen_factor"] == Decimal("10000")
    # The answer to one question moves nothing about a different box.
    assert after["CTC TEA 5KG"]["pack_size_override"] is None
    assert after["CTC TEA 5KG"]["frozen_factor"] == before["CTC TEA 5KG"]["frozen_factor"]


@requires_db
async def test_every_line_carries_the_printed_cells_and_the_names_around_it(db, stage):
    """What the drill and the resolver both need on one row: the printed
    cells `costing.resolve_pack` reads where there is no frozen factor, the
    paper the line is on, and the two names a person recognises."""
    invoice_id = await _paper(
        db,
        [
            _line(
                "CTC TEA 5KG",
                supplier_item_id=stage["tea"],
                qty="3",
                unit="ctn",
                pack_size="5kg",
                unit_price="90.00",
                line_total="270.00",
            )
        ],
        supplier_id=stage["supplier_id"],
        invoice_no="GF-88213",
    )

    (row,) = await _read(db)
    # The column names are the contract `usage.py` is written against, so a
    # rename here is a break there and this is where it gets caught.
    assert set(row.keys()) == {
        "invoice_id",
        "invoice_no",
        "line_position",
        "branch_id",
        "purchased_on",
        "supplier_name",
        "raw_name",
        "qty",
        "unit",
        "pack_size",
        "unit_price",
        "line_total",
        "currency",
        "frozen_factor",
        "supplier_item_id",
        "ingredient_id",
        "pack_size_override",
        "canonical_name",
    }
    assert row["invoice_id"] == invoice_id
    assert row["invoice_no"] == "GF-88213"
    assert row["line_position"] == 0
    assert row["branch_id"] == BRANCH
    assert row["raw_name"] == "CTC TEA 5KG"
    assert row["qty"] == Decimal("3.000")
    assert row["unit"] == "ctn"
    assert row["pack_size"] == "5kg"
    assert row["unit_price"] == Decimal("90.000")
    assert row["line_total"] == Decimal("270.00")
    assert row["currency"] == "AED"
    assert row["canonical_name"] == "CTC TEA 5KG"
    assert row["supplier_name"] == "Gulf Foods Trading L.L.C."
    assert row["ingredient_id"] == stage["tea_material"]


# --- the roll-up the read exists for ----------------------------------------


@requires_db
async def test_one_branchs_purchases_of_one_material_add_up_by_hand(db, stage):
    """The whole point of the read, summed the way `usage.py` will sum it:
    quantity times the frozen factor, over one branch's costed lines for one
    material. Three sacks of 5 kg and two more is 25,000 g of tea dust at Al
    Barsha, and Rolla's sack is not in it."""
    await _paper(
        db,
        [_line("CTC TEA 5KG", supplier_item_id=stage["tea"], pack_size="5kg", qty="3")],
        supplier_id=stage["supplier_id"],
        invoice_date=INSIDE,
    )
    await _paper(
        db,
        [
            _line("CTC TEA 5KG", supplier_item_id=stage["tea"], pack_size="5kg", qty="2"),
            _line("EVAP MILK 1L", supplier_item_id=stage["milk"], pack_size="1l", qty="6"),
        ],
        supplier_id=stage["supplier_id"],
        invoice_date=INSIDE_LATER,
    )
    await _paper(
        db,
        [_line("CTC TEA 5KG", supplier_item_id=stage["tea"], pack_size="5kg", qty="4")],
        supplier_id=stage["supplier_id"],
        branch_id=BRANCH_2,
        invoice_date=INSIDE_LATER,
    )

    rows = await _read(db)
    tea_at_al_barsha = sum(
        row["qty"] * row["frozen_factor"]
        for row in rows
        if row["branch_id"] == BRANCH and row["ingredient_id"] == stage["tea_material"]
    )
    assert tea_at_al_barsha == Decimal("25000")

    milk_at_al_barsha = sum(
        row["qty"] * row["frozen_factor"]
        for row in rows
        if row["branch_id"] == BRANCH and row["ingredient_id"] == stage["milk_material"]
    )
    assert milk_at_al_barsha == Decimal("6000")

    tea_at_rolla = sum(
        row["qty"] * row["frozen_factor"]
        for row in rows
        if row["branch_id"] == BRANCH_2 and row["ingredient_id"] == stage["tea_material"]
    )
    assert tea_at_rolla == Decimal("20000")


@requires_db
async def test_the_rows_come_back_oldest_paper_first_and_in_printed_line_order(db, stage):
    """A stable order, because the drill lists lines in the order they sit on
    the paper and a roll-up that shuffled between runs would be unreadable."""
    await _paper(
        db,
        [
            _line("SECOND PAPER LINE 0", supplier_item_id=stage["tea"], pack_size="5kg"),
            _line("SECOND PAPER LINE 1", supplier_item_id=stage["milk"], pack_size="1l"),
        ],
        supplier_id=stage["supplier_id"],
        invoice_date=INSIDE_LATER,
    )
    await _paper(
        db,
        [_line("FIRST PAPER", supplier_item_id=stage["tea"], pack_size="5kg")],
        supplier_id=stage["supplier_id"],
        invoice_date=INSIDE,
    )

    assert [row["raw_name"] for row in await _read(db)] == [
        "FIRST PAPER",
        "SECOND PAPER LINE 0",
        "SECOND PAPER LINE 1",
    ]


# --- the recipe's date, on the read that already carries the menu -----------


@requires_db
async def test_the_menu_read_says_when_a_recipe_was_written(db, api, stage):
    """D14: a recipe written after the period is a guess about what the
    kitchen did then, so the row it feeds reads estimated. That is only
    knowable if the date travels - it is null for an item nobody has written
    a recipe for, which is a different thing from a recipe with no date."""
    with_recipe = await _menu_item(api, "Karak Cup", "10.00")
    await _recipe(
        api, with_recipe, [{"ingredient_id": stage["tea_material"], "qty": "4", "unit": "g"}]
    )
    without_recipe = await _menu_item(api, "Zaatar Manakish", "8.00")

    items = {row["id"]: row for row in await db.list_menu_items(tenant_id=TENANT)}
    assert items[with_recipe]["recipe_created_at"] is not None
    assert items[with_recipe]["recipe_created_at"].date() == datetime.date.today()
    assert items[without_recipe]["recipe_created_at"] is None
