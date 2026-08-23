"""Supplier memory (plan.md §5 layer 4, WP-22): unit tests for normalization,
supplier matching, and item snapping over messy corpus-style names, plus
real-Postgres tests for the on-confirm price machinery
(Database.record_confirmed_prices - the WP-21 confirm flow calls it)."""

from decimal import Decimal

from faida_api.matching import clean_name, match_supplier, normalize, snap_item

from .conftest import DEMO_TENANT_ID, requires_db

# -- normalize / clean_name ----------------------------------------------------


def test_normalize_casefolds_collapses_and_strips_punctuation():
    assert normalize("  GULF Foods   Trading L.L.C. ") == "gulf foods trading l l c"
    assert normalize("Tomato Paste, (Tin)") == "tomato paste tin"


def test_normalize_keeps_digits_and_units():
    # Pack sizes discriminate items: the decimal point inside a number stays.
    assert normalize("MILK PWDR 2.5KG NIDO") == "milk pwdr 2.5kg nido"
    assert normalize("SUGAR 50 KG.") == "sugar 50 kg"


def test_normalize_keeps_arabic_script():
    assert normalize("مؤسسة الخليج للمواد الغذائية") == "مؤسسة الخليج للمواد الغذائية"


def test_clean_name_keeps_case_trims_edges():
    assert clean_name("  MILK PWDR  2.5KG NIDO ,") == "MILK PWDR 2.5KG NIDO"
    assert clean_name("Al Madeena Foodstuff Tr.") == "Al Madeena Foodstuff Tr"
    assert clean_name(" . ") == ""


# -- match_supplier ------------------------------------------------------------


def _supplier(name: str, aliases: list[str] | None = None, id: int = 0) -> dict:
    return {"id": id, "name": name, "name_aliases": aliases or []}


SUPPLIERS = [
    _supplier("Gulf Foods Trading LLC", id=1),
    _supplier("Al Madina Foodstuff Trading", ["Almadina Foodstuff"], id=2),
    _supplier("Al Ain Poultry", id=3),
]


def test_match_supplier_exact_and_messy_variants():
    assert match_supplier(SUPPLIERS, "Gulf Foods Trading LLC")["id"] == 1
    # ALL-CAPS, dotted abbreviation: 0.96 against the stored name.
    assert match_supplier(SUPPLIERS, "GULF FOODS TRADING L.L.C.")["id"] == 1
    # Dropped legal suffix: 0.90.
    assert match_supplier(SUPPLIERS, "Gulf Foods Trading")["id"] == 1


def test_match_supplier_arabic_transliteration_variant():
    # Madina/Madeena is the classic transliteration drift: 0.91.
    suppliers = [_supplier("Al Madina Trading", id=1), _supplier("Gulf Foods Trading LLC", id=2)]
    assert match_supplier(suppliers, "AL MADEENA TRADING")["id"] == 1


def test_match_supplier_via_alias():
    # "Almadina Foodstuff" scores only 0.80 against the full stored name -
    # far transliterations are exactly what name_aliases is for.
    assert match_supplier(SUPPLIERS, "ALMADINA FOODSTUFF")["id"] == 2


def test_match_supplier_arabic_alias():
    suppliers = [
        _supplier("Gulf Foods Trading LLC", ["مؤسسة الخليج للمواد الغذائية"], id=1),
        _supplier("Al Ain Poultry", id=2),
    ]
    assert match_supplier(suppliers, "مؤسسة الخليج للمواد الغذائية")["id"] == 1


def test_match_supplier_rejects_different_companies():
    assert match_supplier(SUPPLIERS, "Emirates Poultry Farm") is None
    # Al Ain Dairy vs Al Ain Poultry scores 0.69: shared prefix is not a match.
    assert match_supplier(SUPPLIERS, "Al Ain Dairy") is None
    # 0.80 - the honest tuning case for the 0.85 threshold: a lookalike name
    # must not attach the invoice to the wrong supplier's price history.
    assert match_supplier([_supplier("International Trading Co")], "National Trading") is None


def test_match_supplier_no_name_or_no_suppliers():
    assert match_supplier(SUPPLIERS, None) is None
    assert match_supplier(SUPPLIERS, "") is None
    assert match_supplier([], "Gulf Foods Trading LLC") is None


# -- snap_item -----------------------------------------------------------------


def _item(name: str, pack_size: str | None = None, id: int = 0) -> dict:
    return {"id": id, "canonical_name": name, "pack_size": pack_size}


CATALOG = [
    _item("Milk Powder 2.5kg", "2.5kg", id=1),
    _item("Karak Tea Dust 400g", "400g", id=2),
    _item("Sunflower Oil 1.5l", "1.5l", id=3),
    _item("Chickpeas 1kg", "1kg", id=4),
]


def test_snap_item_messy_abbreviated_names():
    # Abbreviation + brand suffix: 0.81, and the 2.5kg packs agree.
    assert snap_item(CATALOG, "MILK PWDR 2.5KG NIDO")["id"] == 1
    assert snap_item(CATALOG, "KARAK TEA DUST 400G")["id"] == 2
    # Spaced pack and a ltr/l spelling variant both canonicalize.
    assert snap_item(CATALOG, "SUNFLOWER OIL 1.5 LTR")["id"] == 3


def test_snap_item_never_snaps_across_pack_sizes():
    # 0.80 string score - exactly at threshold - but 10kg vs 1kg is vetoed.
    assert snap_item([_item("Chickpeas 1kg", "1kg")], "Chicken 10kg") is None
    # 0.91 string score; the veto picks the right size, not the best string.
    catalog = [_item("Basmati Rice 20kg", "20kg", id=1), _item("Basmati Rice 5kg", "5kg", id=2)]
    assert snap_item(catalog, "BASMATI RICE 5KG")["id"] == 2


def test_snap_item_pack_size_column_vetoes_when_name_has_no_pack():
    # "MILK POWDER 500G" vs canonical "Milk Powder" scores 0.82 - only the
    # item's pack_size column (2.5kg vs 0.5kg) blocks the wrong-size snap.
    assert snap_item([_item("Milk Powder", "2.5kg")], "MILK POWDER 500G") is None
    assert snap_item([_item("Milk Powder", "500g")], "MILK POWDER 500G")["id"] == 0


def test_snap_item_gram_kilogram_equivalence_is_not_a_veto():
    # 500g and 0.5kg are the same pack, spelled differently.
    assert snap_item([_item("Milk Powder 0.5kg", "0.5kg")], "MILK POWDER 500G")["id"] == 0


def test_snap_item_below_threshold_or_empty():
    # 0.68 - an abbreviation this deep needs the catalog to learn the raw
    # name on confirm, not a looser threshold.
    assert snap_item(CATALOG, "EVAP MILK 170ML RAINBOW") is None
    assert snap_item(CATALOG, "Onion Bag 25kg") is None
    assert snap_item([], "MILK PWDR 2.5KG NIDO") is None
    assert snap_item(CATALOG, "") is None


# -- record_confirmed_prices (real Postgres) -----------------------------------


async def _seed_supplier(db, name: str) -> str:
    return str(
        await db.pool.fetchval(
            "insert into suppliers (tenant_id, name) values ($1, $2) returning id",
            DEMO_TENANT_ID,
            name,
        )
    )


async def _seed_item(
    db,
    supplier_id: str,
    canonical_name: str,
    *,
    last_price: Decimal | None = None,
    prev_price: Decimal | None = None,
) -> str:
    return str(
        await db.pool.fetchval(
            """
            insert into supplier_items (tenant_id, supplier_id, canonical_name,
                                        last_price, prev_price, last_price_at)
            values ($1, $2, $3, $4, $5,
                    case when $4::numeric is null then null else now() end)
            returning id
            """,
            DEMO_TENANT_ID,
            supplier_id,
            canonical_name,
            last_price,
            prev_price,
        )
    )


async def _seed_invoice(
    db,
    *,
    supplier_id: str | None = None,
    supplier_name: str | None = None,
    lines: list[dict],
    tax_treatment: str | None = None,
    tax: Decimal | None = None,
    total: Decimal | None = None,
    discount_total: Decimal | None = None,
) -> str:
    document_id = await db.pool.fetchval(
        "insert into documents (tenant_id, source, status) values ($1, 'manual', 'extracted') "
        "returning id",
        DEMO_TENANT_ID,
    )
    invoice_id = await db.pool.fetchval(
        """
        insert into invoices (tenant_id, document_id, supplier_id, supplier_name, status,
                              tax_treatment, tax, total, discount_total)
        values ($1, $2, $3, $4, 'confirmed', $5, $6, $7, $8)
        returning id::text
        """,
        DEMO_TENANT_ID,
        document_id,
        supplier_id,
        supplier_name,
        tax_treatment,
        tax,
        total,
        discount_total,
    )
    for position, line in enumerate(lines):
        await db.pool.execute(
            """
            insert into invoice_lines (invoice_id, position, raw_name, supplier_item_id,
                                       qty, unit, unit_price, pack_size, line_total, line_kind)
            values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            invoice_id,
            position,
            line["raw_name"],
            line.get("supplier_item_id"),
            line.get("qty"),
            line.get("unit"),
            line.get("unit_price"),
            line.get("pack_size"),
            line.get("line_total"),
            line.get("line_kind", "stock_item"),
        )
    return invoice_id


async def _item_row(db, item_id: str):
    return await db.pool.fetchrow("select * from supplier_items where id = $1", item_id)


async def _history(db) -> list:
    return await db.pool.fetch(
        "select supplier_item_id, price, invoice_id from supplier_item_prices order by id"
    )


@requires_db
async def test_confirm_self_builds_catalog_from_unknown_supplier(db):
    invoice_id = await _seed_invoice(
        db,
        supplier_name="AL MADEENA FOODSTUFF TR.",
        lines=[
            {
                "raw_name": "MILK PWDR 2.5KG NIDO",
                "qty": Decimal("12"),
                "unit": "sack",
                "unit_price": Decimal("54.50"),
                "pack_size": "2.5kg",
            },
            {"raw_name": "KARAK TEA DUST", "qty": Decimal("3"), "unit_price": Decimal("18.75")},
            # No unit_price: never becomes a catalog item or a price point.
            {"raw_name": "DELIVERY CHARGE", "qty": Decimal("1")},
        ],
    )

    await db.record_confirmed_prices(invoice_id)

    # The supplier self-built from the cleaned raw name and got attached.
    supplier = await db.pool.fetchrow(
        "select * from suppliers where name = $1", "AL MADEENA FOODSTUFF TR"
    )
    assert supplier is not None
    invoice = await db.pool.fetchrow("select * from invoices where id = $1", invoice_id)
    assert invoice["supplier_id"] == supplier["id"]

    # Two items (not three): canonical_name = cleaned raw_name, unit and
    # pack_size from the line, last_price set, no prev yet.
    items = await db.pool.fetch("select * from supplier_items order by canonical_name")
    assert [item["canonical_name"] for item in items] == [
        "KARAK TEA DUST",
        "MILK PWDR 2.5KG NIDO",
    ]
    milk = items[1]
    assert (milk["unit"], milk["pack_size"]) == ("sack", "2.5kg")
    assert milk["last_price"] == Decimal("54.50")
    assert milk["prev_price"] is None
    assert milk["last_price_at"] is not None

    # Lines link back to the created items; the skipped line stays unlinked.
    lines = await db.pool.fetch(
        "select * from invoice_lines where invoice_id = $1 order by position", invoice_id
    )
    assert lines[0]["supplier_item_id"] == milk["id"]
    assert lines[1]["supplier_item_id"] == items[0]["id"]
    assert lines[2]["supplier_item_id"] is None

    # History: one observation per priced line, tied to this invoice.
    history = await _history(db)
    assert [(row["price"], row["invoice_id"]) for row in history] == [
        (Decimal("54.500"), invoice["id"]),
        (Decimal("18.750"), invoice["id"]),
    ]


@requires_db
async def test_confirm_price_change_shifts_prev_and_last(db):
    supplier_id = await _seed_supplier(db, "Gulf Foods Trading LLC")
    item_id = await _seed_item(
        db,
        supplier_id,
        "Milk Powder 2.5kg",
        last_price=Decimal("54.50"),
        prev_price=Decimal("52.00"),
    )
    before = await _item_row(db, item_id)
    invoice_id = await _seed_invoice(
        db,
        supplier_id=supplier_id,
        lines=[
            {
                "raw_name": "MILK PWDR 2.5KG NIDO",
                "supplier_item_id": item_id,
                "qty": Decimal("12"),
                "unit_price": Decimal("58.50"),
            }
        ],
    )

    await db.record_confirmed_prices(invoice_id)

    item = await _item_row(db, item_id)
    assert item["last_price"] == Decimal("58.50")
    assert item["prev_price"] == Decimal("54.50")  # the old last_price
    assert item["last_price_at"] > before["last_price_at"]
    history = await _history(db)
    assert len(history) == 1
    assert history[0]["price"] == Decimal("58.500")


@requires_db
async def test_confirm_rerun_is_a_noop(db):
    invoice_id = await _seed_invoice(
        db,
        supplier_name="Gulf Foods Trading LLC",
        lines=[
            {
                "raw_name": "MILK PWDR 2.5KG NIDO",
                "qty": Decimal("12"),
                "unit_price": Decimal("54.50"),
            },
            {"raw_name": "KARAK TEA DUST", "qty": Decimal("3"), "unit_price": Decimal("18.75")},
        ],
    )
    await db.record_confirmed_prices(invoice_id)
    items_before = await db.pool.fetch("select * from supplier_items order by canonical_name")
    history_before = await _history(db)

    # WP-21 may re-run confirm (retries, repeated "OK"): prev_price must not
    # shuffle and the history must not grow.
    await db.record_confirmed_prices(invoice_id)

    assert await db.pool.fetch("select * from supplier_items order by canonical_name") == (
        items_before
    )
    assert await _history(db) == history_before
    assert await db.pool.fetchval("select count(*) from suppliers") == 1


@requires_db
async def test_confirm_same_price_keeps_baseline_but_appends_history(db):
    supplier_id = await _seed_supplier(db, "Gulf Foods Trading LLC")
    item_id = await _seed_item(
        db,
        supplier_id,
        "Milk Powder 2.5kg",
        last_price=Decimal("54.50"),
        prev_price=Decimal("52.00"),
    )
    before = await _item_row(db, item_id)
    invoice_id = await _seed_invoice(
        db,
        supplier_id=supplier_id,
        lines=[
            {
                "raw_name": "MILK PWDR 2.5KG NIDO",
                "supplier_item_id": item_id,
                "qty": Decimal("12"),
                "unit_price": Decimal("54.50"),  # unchanged price
            }
        ],
    )

    await db.record_confirmed_prices(invoice_id)

    # A same-price invoice is a new observation but not a baseline move:
    # prev_price keeps the last *different* price for the alert math.
    item = await _item_row(db, item_id)
    assert item["last_price"] == Decimal("54.50")
    assert item["prev_price"] == Decimal("52.00")
    assert item["last_price_at"] == before["last_price_at"]
    assert len(await _history(db)) == 1


@requires_db
async def test_confirm_without_supplier_or_name_does_nothing(db):
    invoice_id = await _seed_invoice(
        db,
        lines=[
            {
                "raw_name": "MILK PWDR 2.5KG NIDO",
                "qty": Decimal("12"),
                "unit_price": Decimal("54.50"),
            }
        ],
    )

    await db.record_confirmed_prices(invoice_id)

    assert await db.pool.fetchval("select count(*) from suppliers") == 0
    assert await db.pool.fetchval("select count(*) from supplier_items") == 0
    assert await _history(db) == []


# -- C4 net-canonical price memory (WP-17) -------------------------------------


@requires_db
async def test_inclusive_invoice_records_price_net_of_vat(db):
    """An inclusive invoice's unit prices are gross. Price memory is
    net-canonical, so what lands in the catalog is ex-VAT."""
    supplier_id = await _seed_supplier(db, "Deira Cold Store & General Trading")
    invoice_id = await _seed_invoice(
        db,
        supplier_id=supplier_id,
        lines=[{"raw_name": "RICE BASM 5KG", "qty": Decimal("2"), "unit_price": Decimal("33.600")}],
        tax_treatment="inclusive",
        tax=Decimal("33.65"),
        total=Decimal("706.65"),
    )

    await db.record_confirmed_prices(invoice_id)

    items = await db.pool.fetch("select * from supplier_items")
    assert len(items) == 1
    # 33.600 / 1.05 = 32.000 exactly, at the real invoice's rate.
    assert items[0]["last_price"] == Decimal("32.000")
    history = await _history(db)
    assert [row["price"] for row in history] == [Decimal("32.000")]
    # The as-printed price is untouched: the review screen still traces to the photo.
    line = await db.pool.fetchrow(
        "select unit_price from invoice_lines where invoice_id = $1", invoice_id
    )
    assert line["unit_price"] == Decimal("33.600")


@requires_db
async def test_supplier_switching_vat_format_fires_no_price_alert(db):
    """The reason net-canonical exists. PRICE_ALERT_MIN_PCT is 5% and UAE VAT
    is 5%, so a supplier moving from VAT-exclusive to VAT-inclusive invoicing
    would otherwise look exactly like a full-threshold price rise on an item
    whose price never moved."""
    supplier_id = await _seed_supplier(db, "Gulf Foods Trading LLC")
    item_id = await _seed_item(db, supplier_id, "Milk Powder 2.5kg")

    # Week 1: exclusive invoice, net 100.00 on the page.
    first = await _seed_invoice(
        db,
        supplier_id=supplier_id,
        lines=[
            {
                "raw_name": "Milk Powder 2.5kg",
                "supplier_item_id": item_id,
                "qty": Decimal("1"),
                "unit_price": Decimal("100.000"),
            }
        ],
        tax_treatment="exclusive",
        tax=Decimal("5.00"),
        total=Decimal("105.00"),
    )
    await db.record_confirmed_prices(first)

    # Week 2: same real price, now invoiced inclusive - 105.00 on the page.
    second = await _seed_invoice(
        db,
        supplier_id=supplier_id,
        lines=[
            {
                "raw_name": "Milk Powder 2.5kg",
                "supplier_item_id": item_id,
                "qty": Decimal("1"),
                "unit_price": Decimal("105.000"),
            }
        ],
        tax_treatment="inclusive",
        tax=Decimal("5.00"),
        total=Decimal("105.00"),
    )
    await db.record_confirmed_prices(second)

    item = await _item_row(db, item_id)
    assert item["last_price"] == Decimal("100.000")
    # prev_price never shifted, because nothing changed: no alert can fire.
    assert item["prev_price"] is None
    assert [row["price"] for row in await _history(db)] == [Decimal("100.000")] * 2


# -- C4 discounts and charges in price memory (WP-18) --------------------------


@requires_db
async def test_charge_lines_never_enter_the_catalog(db):
    """Delivery and cool-box hire are cost, not stock. If they became supplier
    items the price catalog would fill with charges and alerts would start
    firing on delivery fees."""
    supplier_id = await _seed_supplier(db, "Fresh Fields Produce LLC")
    invoice_id = await _seed_invoice(
        db,
        supplier_id=supplier_id,
        lines=[
            {
                "raw_name": "Avocado",
                "qty": Decimal("5"),
                "unit_price": Decimal("92.00"),
                "line_total": Decimal("460.00"),
            },
            {
                "raw_name": "Chilled delivery and cool box hire",
                "qty": Decimal("1"),
                "unit_price": Decimal("25.00"),
                "line_total": Decimal("25.00"),
                "line_kind": "charge",
            },
        ],
    )

    await db.record_confirmed_prices(invoice_id)

    items = await db.pool.fetch("select canonical_name from supplier_items")
    assert [row["canonical_name"] for row in items] == ["Avocado"]


@requires_db
async def test_trade_discount_reaches_the_recorded_price(db):
    """Price memory records what was paid. A supplier who holds list prices and
    quietly stops discounting has raised your cost, and storing the list price
    would draw a flat line straight through that."""
    supplier_id = await _seed_supplier(db, "Fresh Fields Produce LLC")
    item_id = await _seed_item(db, supplier_id, "Avocado")
    invoice_id = await _seed_invoice(
        db,
        supplier_id=supplier_id,
        lines=[
            {
                "raw_name": "Avocado",
                "supplier_item_id": item_id,
                "qty": Decimal("5"),
                "unit_price": Decimal("92.00"),
                "line_total": Decimal("460.00"),
            },
            {
                "raw_name": "Chilled delivery and cool box hire",
                "qty": Decimal("1"),
                "unit_price": Decimal("25.00"),
                "line_total": Decimal("25.00"),
                "line_kind": "charge",
            },
        ],
        discount_total=Decimal("23.00"),  # 5% of the 460.00 of goods
    )

    await db.record_confirmed_prices(invoice_id)

    # 92.00 less its pro-rata share of the discount, not the 92.00 on the page.
    # The charge is outside the discount base, so it cannot dilute the rate.
    assert (await _item_row(db, item_id))["last_price"] == Decimal("87.400")
