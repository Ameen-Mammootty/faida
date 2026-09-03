"""M5 WP-53: cost per base unit (plan.md §8 M5).

The first number this product shows that no photograph shows back. Everything
before it sat beside its image and a person could catch it; a cost per gram is
two divisions away from the page and by M6 it is folded four sums deep into a
plate margin, so a wrong one is not visible anywhere.

Which is what these tests are about. They check the arithmetic, and they check
the two things that stop a wrong cost passing for a right one: that the label
never claims more than the inputs support (nothing anywhere cross-checks a pack
size, so no cost is ever *verified*), and that each cost is measured against its
own line's history rather than the line above it.
"""

from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI

from faida_api import costing
from faida_api.api import router as api_router
from faida_api.costing import Blocked, PackSource, Quality

from .conftest import AUTH, DEMO_TENANT_ID, requires_db, wire_auth


def cost_of(**kwargs) -> costing.LineCost:
    """A line's cost with the boring fields defaulted. Every test below sets
    only what it is actually about."""
    line = {
        "position": 0,
        "qty": Decimal("1"),
        "unit_price": Decimal("10.00"),
        "pack_size": "1kg",
        "raw_name": "Something",
        "unit": None,
    }
    return costing.cost_line(**{**line, **kwargs})


# -- the arithmetic ------------------------------------------------------------


def test_a_sack_reads_a_price_per_kilo_a_person_recognizes():
    """AED 50.50 for a 2.5 kg sack is AED 20.20 a kilo. Stored per gram,
    because that is what a recipe consumes; shown per kilo, because that is
    what a person buys."""
    cost = cost_of(unit_price=Decimal("50.50"), pack_size="2.5kg")
    assert cost.cost == Decimal("0.02020000")
    assert cost.base_unit == "g"
    assert costing.per_display_unit(cost.cost, "g") == (Decimal("20.20"), "kg")


def test_the_division_is_deep_enough_to_survive_a_sack_of_flour():
    """Flour at AED 43.50 per 25 kg is 0.00174 AED a gram. The precision the
    price columns use - fils, numeric(12,3) - would store that as 0.002: a 15%
    error on every plate of biryani, arriving with no photograph beside it and
    nothing downstream able to notice."""
    cost = cost_of(unit_price=Decimal("43.50"), pack_size="25kg")
    assert cost.cost == Decimal("0.00174000")
    assert cost.cost != Decimal("0.002")
    assert costing.per_display_unit(cost.cost, "g") == (Decimal("1.74"), "kg")


def test_a_vat_inclusive_invoice_costs_ex_vat():
    """C4's net-canonical rule, applied to a cost through the same factor price
    memory uses. A gross cost per gram would fold 5% VAT into every plate."""
    inclusive = cost_of(
        unit_price=Decimal("105.00"),
        pack_size="1kg",
        # (total - tax) / total for a 5% invoice: 100/105.
        net_factor=Decimal("100") / Decimal("105"),
    )
    assert inclusive.cost == Decimal("0.10000000")


def test_a_discounted_invoice_costs_what_was_actually_paid():
    """A supplier who holds list prices and quietly stops discounting has
    raised your cost. Storing the list price would draw a flat line through
    exactly that."""
    discounted = cost_of(
        unit_price=Decimal("100.00"), pack_size="1kg", discount_factor=Decimal("0.95")
    )
    assert discounted.cost == Decimal("0.09500000")


def test_a_credit_line_costs_what_the_box_was_billed_at():
    """EDGE-01 returns one box of avocados: quantity -1, unit price 92.00, a
    4 kg box. The return does not change what a box costs, and a negative
    quantity must not turn into a negative cost or a refusal."""
    cost = cost_of(
        qty=Decimal("-1"), unit_price=Decimal("92.00"), pack_size="4kg", raw_name="Avocado"
    )
    assert cost.cost == Decimal("0.02300000")
    assert costing.per_display_unit(cost.cost, "g") == (Decimal("23.00"), "kg")


# -- where the pack size is read from ------------------------------------------


def test_the_pack_column_is_read_first():
    cost = cost_of(pack_size="2kg", raw_name="MILK PWDR 500G")
    assert cost.pack.printed == "2kg"
    assert cost.pack.source is PackSource.PACK_COLUMN
    assert cost.pack.base_quantity == Decimal("2000")


def test_a_till_receipt_prints_the_pack_inside_the_name():
    """TH-01 has no pack-size column at all: "RICE BASM 5KG" is the whole row.
    `matching.snap_item` already trusts a pack printed there, so costing does
    too - it is a pack size wherever it is printed."""
    cost = cost_of(pack_size=None, raw_name="RICE BASM 5KG", unit_price=Decimal("25.00"))
    assert cost.pack.source is PackSource.ITEM_NAME
    assert cost.pack.printed == "5KG"
    assert cost.cost == Decimal("0.00500000")


def test_a_line_priced_by_the_kilo_needs_no_pack_at_all():
    """Produce invoices have no pack column because the pack is the kilo: 25 KG
    of tomatoes at AED 3.50 is AED 3.50 a kilo, and the unit column says so."""
    cost = cost_of(
        qty=Decimal("25"), unit_price=Decimal("3.50"), pack_size=None, raw_name="Tomato", unit="KG"
    )
    assert cost.pack.source is PackSource.LINE_UNIT
    assert cost.cost == Decimal("0.00350000")
    assert costing.per_display_unit(cost.cost, "g") == (Decimal("3.50"), "kg")


def test_a_bare_container_in_the_pack_column_does_not_end_the_search():
    """A bare carton is not an amount, but it is not a refusal either: if the
    name beside it says 2.5 kg, the name is the answer. Stopping at the first cell
    that named something would throw away a pack size printed on the page."""
    cost = cost_of(pack_size="1 ctn", raw_name="MILK PWDR 2.5KG NIDO")
    assert cost.pack.source is PackSource.ITEM_NAME
    assert cost.pack.base_quantity == Decimal("2500")


def test_a_multiplier_carton_costs_by_the_whole_carton():
    """WP-51's arithmetic, now with something dividing by it: 48 x 400 ml is
    19,200 ml, and reading only the tail would make this cost 48 times too
    much."""
    cost = cost_of(unit_price=Decimal("90.00"), pack_size="48x400ml", raw_name="Evaporated Milk")
    assert cost.base_unit == "ml"
    assert cost.cost == Decimal("0.00468750")
    assert costing.per_display_unit(cost.cost, "ml") == (Decimal("4.69"), "litre")


# -- the lines that cannot be costed (each with its own reason, WP-55) ---------


def test_a_pack_of_nothing_is_not_a_pack():
    """`units.parse("0kg")` refuses, so nothing here divides by zero. The line
    gets no cost, its own reason, and no exception."""
    cost = cost_of(pack_size="0kg", raw_name="Chicken")
    assert cost.cost is None
    assert cost.blocked is Blocked.ZERO_PACK


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ({"unit_price": None}, Blocked.MISSING_UNIT_PRICE),
        ({"qty": None}, Blocked.MISSING_QUANTITY),
        ({"pack_size": "1 ctn", "raw_name": "Chicken", "unit": "CTN"}, Blocked.BARE_CONTAINER),
        ({"pack_size": "0 KG", "raw_name": "Chicken"}, Blocked.ZERO_PACK),
        ({"pack_size": "assorted", "raw_name": "Chicken", "unit": None}, Blocked.UNPARSEABLE_PACK),
    ],
)
def test_every_way_a_line_refuses_to_cost_says_which_one_it_was(line, expected):
    """Five different sentences to a consultant and five different things to do
    about them. A single "could not cost this" would send someone to look at
    the wrong half of the invoice."""
    cost = cost_of(**line)
    assert cost.cost is None
    assert cost.blocked is expected
    assert costing.BLOCKED_REASONS[expected]


def test_the_reason_is_the_same_answer_the_cost_gave():
    """One implementation: whether a line can be costed does not depend on the
    invoice's VAT or discount factors, so the screens ask the same function the
    confirm did."""
    assert (
        costing.blocked_reason_for(
            qty=Decimal("1"),
            unit_price=Decimal("10.00"),
            pack_size="1 ctn",
            raw_name="Chicken",
            unit="CTN",
        )
        is Blocked.BARE_CONTAINER
    )
    assert (
        costing.blocked_reason_for(
            qty=Decimal("1"),
            unit_price=Decimal("10.00"),
            pack_size="2kg",
            raw_name="Chicken",
            unit=None,
        )
        is None
    )
    # WP-28's hold is the invoice's, not the line's, and it outranks everything
    # the line itself could say: a USD price in an AED cost is meaningless.
    assert (
        costing.blocked_reason_for(
            qty=Decimal("1"),
            unit_price=Decimal("10.00"),
            pack_size="2kg",
            raw_name="Chicken",
            unit=None,
            foreign_currency=True,
        )
        is Blocked.FOREIGN_CURRENCY
    )


# -- C9: never greener than the worst input ------------------------------------


def test_no_cost_can_ever_read_verified():
    """The sharpest thing said in the M5 review, pinned so it cannot be
    softened back. C4's arithmetic proves qty x unit_price = line_total, so the
    unit price is corroborated by two other numbers on the page - but pack size
    appears in **no identity at all**. A supplier prints 25 kg, the model reads
    2.5 kg, every check we have still passes, and the cost is ten times too
    high. A green badge on that is the old platform's dominant failure in a new
    place."""
    assert "verified" not in {quality.value for quality in Quality}
    assert cost_of().quality is Quality.RELIABLE


def test_a_cost_resting_on_a_number_a_person_supplied_reads_estimated():
    """WP-26 lets an owner type a total that was off the edge of the photo.
    On a VAT-inclusive invoice that total is what makes the price ex-VAT, so
    the cost leans on it - and says which field it was."""
    cost = cost_of(
        unit_price=Decimal("105.00"),
        net_factor=Decimal("100") / Decimal("105"),
        asserted={"total"},
    )
    assert cost.quality is Quality.ESTIMATED
    assert cost.asserted == ("total",)


def test_the_same_correction_is_no_business_of_an_exclusive_invoice():
    """The negative control, and the reason the input set is derived rather
    than listed. An exclusive invoice's cost never touches `total`, so a
    reconstructed total there does not make it an estimate - C9 propagates the
    real dependency, not everything nearby."""
    cost = cost_of(asserted={"total", "tax", "subtotal"})
    assert cost.quality is Quality.RELIABLE
    assert cost.asserted == ()


def test_a_discount_makes_every_stock_line_an_input_to_every_other():
    """The allocation is pro rata over the stock-line sum, so correcting line 3
    changes what line 1 cost. Nothing on line 1's own row shows that, which is
    exactly why the input set is computed from the arithmetic instead of read
    off the line."""
    tainted = cost_of(
        discount_factor=Decimal("0.95"),
        asserted={"lines.2.line_total"},
        stock_positions=[0, 1, 2],
    )
    assert tainted.quality is Quality.ESTIMATED
    assert tainted.asserted == ("lines.2.line_total",)

    # Without a discount there is no allocation and no shared dependency.
    assert cost_of(asserted={"lines.2.line_total"}, stock_positions=[0, 1, 2]).quality is (
        Quality.RELIABLE
    )


def test_a_pack_read_from_the_name_leans_on_the_name():
    """The pack column is always an input; the *other* two sources are inputs
    only when they were used. A corrected product name that carries the pack
    size is a human-supplied pack size."""
    from_name = cost_of(pack_size=None, raw_name="RICE BASM 5KG", asserted={"lines.0.raw_name"})
    assert from_name.quality is Quality.ESTIMATED
    # The same correction on a line whose pack came off the pack column is
    # nothing to do with the cost.
    assert cost_of(pack_size="5kg", asserted={"lines.0.raw_name"}).quality is Quality.RELIABLE


def test_the_basis_records_what_the_price_was_divided_by():
    """C8's shape: the record travels with the number. A cost with no note of
    what it was divided by is a number nobody can argue with later."""
    assert cost_of(unit_price=Decimal("50.50"), pack_size="2.5kg").basis() == {
        "quality": "reliable_with_limitations",
        "asserted": [],
        "pack": "2.5kg",
        "pack_base_quantity": "2500.0",
        "pack_source": "pack_size",
    }
    assert cost_of(pack_size="1 ctn", raw_name="Chicken", unit="CTN").basis() == {}


# -- the confirm transaction (real Postgres) -----------------------------------


@pytest.fixture
def api(settings, db):
    app = FastAPI()
    app.include_router(api_router)
    app.state.settings = settings
    wire_auth(app)
    app.state.db = db
    app.state.storage = _NoStorage()
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


class _NoStorage:
    """The detail payload signs an image URL; these invoices have no original."""

    async def sign_url(self, path: str) -> str:
        raise FileNotFoundError(path)


async def _seed_invoice(
    db,
    *,
    lines: list[dict],
    status: str = "awaiting_confirm",
    tax_treatment: str | None = None,
    tax: Decimal | None = None,
    total: Decimal = Decimal("100.00"),
    discount_total: Decimal | None = None,
    provenance: dict | None = None,
    currency: str = "AED",
) -> str:
    supplier_id = await db.pool.fetchval(
        "insert into suppliers (tenant_id, name) values ($1, 'Gulf Foods Trading L.L.C.') "
        "returning id",
        DEMO_TENANT_ID,
    )
    document_id = await db.pool.fetchval(
        "insert into documents (tenant_id, source, status) values ($1, 'manual', 'extracted') "
        "returning id",
        DEMO_TENANT_ID,
    )
    invoice_id = await db.pool.fetchval(
        """
        insert into invoices (tenant_id, document_id, supplier_id, status, currency,
                              tax_treatment, tax, total, discount_total, provenance,
                              invoice_date)
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, date '2026-07-06')
        returning id::text
        """,
        DEMO_TENANT_ID,
        document_id,
        supplier_id,
        status,
        currency,
        tax_treatment,
        tax,
        total,
        discount_total,
        provenance or {},
    )
    for position, line in enumerate(lines):
        await db.pool.execute(
            """
            insert into invoice_lines (tenant_id, invoice_id, position, raw_name, qty, unit,
                                       unit_price, pack_size, line_total, line_kind)
            values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            DEMO_TENANT_ID,
            invoice_id,
            position,
            line["raw_name"],
            line.get("qty"),
            line.get("unit"),
            line.get("unit_price"),
            line.get("pack_size"),
            line.get("line_total"),
            line.get("line_kind", "stock_item"),
        )
    return invoice_id


async def _costs(db, invoice_id: str) -> list:
    return await db.pool.fetch(
        """
        select position, raw_name, cost_per_base_unit, cost_base_unit, cost_basis
        from invoice_lines where invoice_id = $1 order by position
        """,
        invoice_id,
    )


@requires_db
async def test_confirming_freezes_a_cost_on_every_stock_line(db):
    """The cost is written inside the confirm transaction (WP-50), so a
    confirmed invoice with no costs is unreachable rather than merely unlikely
    - and every cost has the photo that produced it one join away."""
    invoice_id = await _seed_invoice(
        db,
        total=Decimal("176.00"),
        lines=[
            {
                "raw_name": "Milk Powder",
                "qty": Decimal("2"),
                "pack_size": "2.5kg",
                "unit_price": Decimal("50.50"),
                "line_total": Decimal("101.00"),
            },
            {
                "raw_name": "Flour",
                "qty": Decimal("1"),
                "pack_size": "25kg",
                "unit_price": Decimal("43.50"),
                "line_total": Decimal("43.50"),
            },
            {
                "raw_name": "Chilled delivery and cool box hire",
                "qty": Decimal("1"),
                "unit": "service",
                "unit_price": Decimal("25.00"),
                "line_total": Decimal("25.00"),
                "line_kind": "charge",
            },
        ],
    )
    assert (
        await db.confirm_invoice(
            invoice_id, tenant_id=DEMO_TENANT_ID, actor="whatsapp:+971500000000"
        )
        is True
    )

    rows = await _costs(db, invoice_id)
    assert [row["cost_per_base_unit"] for row in rows] == [
        Decimal("0.02020000"),
        Decimal("0.00174000"),
        None,  # a delivery charge is not a thing you cook with (WP-18)
    ]
    assert [row["cost_base_unit"] for row in rows] == ["g", "g", None]
    assert rows[0]["cost_basis"]["quality"] == "reliable_with_limitations"
    assert rows[0]["cost_basis"]["pack"] == "2.5kg"
    assert rows[1]["cost_basis"]["pack_source"] == "pack_size"


@requires_db
async def test_a_delivery_charge_in_line_one_does_not_shift_every_cost_onto_the_wrong_line(db):
    """The trap this milestone was warned about, in the smallest form that
    catches it.

    The stock-line query drops charge lines, so a loop counter is *not* where a
    line sits on the invoice. Provenance is keyed by that position. With a
    delivery charge printed first, counting would read every stock line's
    quality off the row above it: here the charge line was corrected by a
    person, and the avocados were not - so counting marks the avocados
    estimated, and the herbs (whose own price a person really did supply) come
    out reliable. Exactly backwards, on the number nothing downstream can
    check.
    """
    invoice_id = await _seed_invoice(
        db,
        total=Decimal("205.00"),
        provenance={
            "lines.0.unit_price": {"origin": "corrected_screen", "actor": "console", "at": "x"},
            "lines.2.unit_price": {"origin": "corrected_chat", "actor": "whatsapp:+971", "at": "x"},
        },
        lines=[
            {
                "raw_name": "Chilled delivery",
                "qty": Decimal("1"),
                "unit": "service",
                "unit_price": Decimal("25.00"),
                "line_total": Decimal("25.00"),
                "line_kind": "charge",
            },
            {
                "raw_name": "Avocado",
                "qty": Decimal("1"),
                "pack_size": "4kg",
                "unit_price": Decimal("92.00"),
                "line_total": Decimal("92.00"),
            },
            {
                "raw_name": "Mixed Fresh Herbs",
                "qty": Decimal("1"),
                "pack_size": "500g",
                "unit_price": Decimal("20.00"),
                "line_total": Decimal("20.00"),
            },
        ],
    )
    assert (
        await db.confirm_invoice(
            invoice_id, tenant_id=DEMO_TENANT_ID, actor="whatsapp:+971500000000"
        )
        is True
    )

    rows = await _costs(db, invoice_id)
    assert rows[0]["cost_per_base_unit"] is None  # the charge line
    assert rows[1]["cost_basis"]["quality"] == "reliable_with_limitations"
    assert rows[1]["cost_basis"]["asserted"] == []
    assert rows[2]["cost_basis"]["quality"] == "estimated"
    assert rows[2]["cost_basis"]["asserted"] == ["lines.2.unit_price"]


@requires_db
async def test_a_line_with_no_readable_pack_costs_nothing_and_confirms_anyway(db):
    """A zero pack divides, so WP-51 refuses to call it a pack. What matters
    here is what happens next: the line gets no cost, nothing throws, and the
    rest of the invoice confirms and costs normally. A cost this layer cannot
    compute is a line on a screen (WP-55), never a failed confirmation."""
    invoice_id = await _seed_invoice(
        db,
        total=Decimal("70.00"),
        lines=[
            {
                "raw_name": "Chicken",
                "qty": Decimal("1"),
                "pack_size": "0kg",
                "unit_price": Decimal("40.00"),
                "line_total": Decimal("40.00"),
            },
            {
                "raw_name": "Kale",
                "qty": Decimal("1"),
                "pack_size": "1kg",
                "unit_price": Decimal("18.00"),
                "line_total": Decimal("18.00"),
            },
            {
                "raw_name": "Cardamom",
                "qty": None,
                "pack_size": "500g",
                "unit_price": Decimal("12.00"),
                "line_total": None,
            },
        ],
    )
    assert await db.confirm_invoice(invoice_id, tenant_id=DEMO_TENANT_ID, actor="console") is True

    rows = await _costs(db, invoice_id)
    assert rows[0]["cost_per_base_unit"] is None
    assert rows[0]["cost_basis"] == {}
    assert rows[1]["cost_per_base_unit"] == Decimal("0.01800000")
    assert rows[2]["cost_per_base_unit"] is None


@requires_db
async def test_a_second_price_run_never_wipes_a_cost_it_cannot_recompute(db):
    """The retried WhatsApp ack calls the price write again on an invoice that
    is already confirmed. From WP-55 a person can supply the amount a container
    never printed, and that cost has to survive the re-run - so the absence of
    a cost is not a value this write ever stores."""
    invoice_id = await _seed_invoice(
        db,
        total=Decimal("40.00"),
        lines=[
            {
                "raw_name": "Chicken Carton",
                "qty": Decimal("1"),
                "pack_size": "1 ctn",
                "unit_price": Decimal("40.00"),
                "line_total": Decimal("40.00"),
            }
        ],
    )
    assert await db.confirm_invoice(invoice_id, tenant_id=DEMO_TENANT_ID, actor="console") is True
    assert (await _costs(db, invoice_id))[0]["cost_per_base_unit"] is None

    # Stand in for WP-55's override: a human's conversion, costed by hand.
    await db.pool.execute(
        """
        update invoice_lines set cost_per_base_unit = 0.004, cost_base_unit = 'g',
                                 cost_basis = '{"quality": "estimated"}'
        where invoice_id = $1
        """,
        invoice_id,
    )
    await db.record_confirmed_prices(invoice_id, tenant_id=DEMO_TENANT_ID)

    row = (await _costs(db, invoice_id))[0]
    assert row["cost_per_base_unit"] == Decimal("0.00400000")
    assert row["cost_basis"]["quality"] == "estimated"


@requires_db
async def test_a_foreign_currency_invoice_records_no_cost_at_all(db):
    """WP-28: a USD price against an AED tenant is not slightly wrong, it is
    meaningless - and as a cost per gram nothing downstream could tell."""
    invoice_id = await _seed_invoice(
        db,
        currency="USD",
        total=Decimal("40.00"),
        lines=[
            {
                "raw_name": "Saffron",
                "qty": Decimal("1"),
                "pack_size": "10g",
                "unit_price": Decimal("40.00"),
                "line_total": Decimal("40.00"),
            }
        ],
    )
    assert await db.confirm_invoice(invoice_id, tenant_id=DEMO_TENANT_ID, actor="console") is True
    assert (await _costs(db, invoice_id))[0]["cost_per_base_unit"] is None


@requires_db
async def test_the_review_screen_shows_the_cost_and_the_reason_there_is_none(api, db):
    """The vertical slice: nothing is computed that nobody can see. Before
    confirming there is no cost and the screen is told so; after, each stock
    line carries its figure, its quality and the pack it was divided by, and
    the line that could not be costed says why in a sentence."""
    invoice_id = await _seed_invoice(
        db,
        total=Decimal("141.00"),
        lines=[
            {
                "raw_name": "Milk Powder",
                "qty": Decimal("2"),
                "pack_size": "2.5kg",
                "unit_price": Decimal("50.50"),
                "line_total": Decimal("101.00"),
            },
            {
                "raw_name": "Chicken Carton",
                "qty": Decimal("1"),
                "unit": "CTN",
                "pack_size": "1 ctn",
                "unit_price": Decimal("40.00"),
                "line_total": Decimal("40.00"),
            },
        ],
    )
    before = (await api.get(f"/api/invoices/{invoice_id}", headers=AUTH)).json()
    assert [line["cost"] for line in before["lines"]] == [None, None]

    await api.post(f"/api/invoices/{invoice_id}/confirm", headers=AUTH)
    after = (await api.get(f"/api/invoices/{invoice_id}", headers=AUTH)).json()

    powder, carton = (line["cost"] for line in after["lines"])
    assert powder["per_display_unit"] == "20.20"
    assert powder["display_unit"] == "kg"
    assert powder["per_base_unit"] == "0.02020000"
    assert powder["quality"] == "reliable_with_limitations"
    assert powder["pack"] == "2.5kg"
    assert powder["blocked"] is None

    assert carton["per_base_unit"] is None
    assert carton["blocked"] == "bare_container"
    # Plain English, no unit codes: this sentence lands on a screen.
    assert carton["reason"] == "Nothing on the invoice says how much one of these holds."
