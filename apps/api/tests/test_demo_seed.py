"""WP-40: supabase/demo_seed.sql (plan.md §6 M4), against a real Postgres.

The demo seed is also the between-rehearsals reset: applying it must stage the
exact demo state, applying it twice must change nothing, and applying it after
a rehearsal must wipe every trace of that rehearsal for the demo chain while
leaving every other tenant's rows (seed.sql's demo tenant is the canary)
untouched. The staged catalog must actually snap the curated invoice's raw
names and fire the intended alert lines - that is the demo.
"""

import csv
import datetime
import importlib.util
import os
import pathlib
import subprocess
import sys
from decimal import Decimal

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from faida_api import costing, plates, takings
from faida_api.extraction.pipeline import price_alerts
from faida_api.extraction.schema import ExtractedInvoice, ExtractedLine
from faida_api.matching import match_supplier, snap_item
from faida_api.replies import render_price_alert
from faida_api.sales import router as sales_router
from faida_api.storage import Storage

from .conftest import (
    AUTH,
    DEMO_TENANT_ID,
    JWKS,
    TEST_DATABASE_URL,
    FakeStorage,
    requires_db,
    wire_auth,
)

pytestmark = requires_db

DEMO_SEED_FILE = pathlib.Path(__file__).resolve().parents[3] / "supabase" / "demo_seed.sql"
LOOP_RESET_FILE = pathlib.Path(__file__).resolve().parents[3] / "supabase" / "demo_reset_loop.sql"

# Fixed UUIDs pinned by demo_seed.sql ('d' prefix = the M4 demo chain).
CHAIN_TENANT_ID = "d0000000-0000-0000-0000-000000000001"
FLAGSHIP_BRANCH_ID = "d0000000-0000-0000-0000-000000000011"
GULF_FOODS_ID = "d0000000-0000-0000-0000-000000000021"
AL_MADINA_ID = "d0000000-0000-0000-0000-000000000022"
MILK_POWDER_ID = "d0000000-0000-0000-0000-000000000101"
KARAK_TEA_ID = "d0000000-0000-0000-0000-000000000102"
ATTA_FLOUR_PACK_ID = "d0000000-0000-0000-0000-000000000106"
ATTA_FLOUR_ID = "d0000000-0000-0000-0000-000000000206"

DEMO_HANDSET = "971509999999"  # stand-in for the founder's demo phone
DAY = datetime.timedelta(days=1)


async def apply_demo_seed(db) -> None:
    await db.pool.execute(DEMO_SEED_FILE.read_text())


async def chain_counts(db) -> dict[str, int]:
    """Row counts scoped to the demo chain tenant, the reset's whole world."""
    queries = {
        "branches": "select count(*) from branches where tenant_id = $1",
        "suppliers": "select count(*) from suppliers where tenant_id = $1",
        "supplier_items": "select count(*) from supplier_items where tenant_id = $1",
        "prices": """
            select count(*) from supplier_item_prices
            where supplier_item_id in (select id from supplier_items where tenant_id = $1)
            """,
        "documents": "select count(*) from documents where tenant_id = $1",
        "invoices": "select count(*) from invoices where tenant_id = $1",
    }
    return {name: await db.pool.fetchval(sql, CHAIN_TENANT_ID) for name, sql in queries.items()}


async def test_staged_state_snaps_and_fires_the_demo_alerts(db):
    await apply_demo_seed(db)

    branches = await db.pool.fetch(
        "select name, wa_phone_e164 from branches where tenant_id = $1 order by id",
        CHAIN_TENANT_ID,
    )
    assert [b["name"] for b in branches] == ["Al Qusais Branch", "Al Nahda Branch", "Rolla Branch"]
    assert all(b["wa_phone_e164"] is None for b in branches)  # founder sets the real one

    suppliers = await db.list_suppliers(CHAIN_TENANT_ID)
    assert len(suppliers) == 2

    # The curated invoice's extracted supplier name must match the staged row.
    supplier = match_supplier(suppliers, "Gulf Foods Trading LLC")
    assert supplier is not None and str(supplier["id"]) == GULF_FOODS_ID

    items = await db.list_supplier_items(GULF_FOODS_ID)
    assert len(items) == 4
    assert (
        await db.pool.fetchval(
            "select count(*) from supplier_items where tenant_id = $1", CHAIN_TENANT_ID
        )
        == 6
    )

    # Staged baselines, exact (the alert math depends on them).
    milk = await db.get_supplier_item(MILK_POWDER_ID, tenant_id=CHAIN_TENANT_ID)
    assert (milk["last_price"], milk["prev_price"]) == (Decimal("50.50"), Decimal("49.75"))
    karak = await db.get_supplier_item(KARAK_TEA_ID, tenant_id=CHAIN_TENANT_ID)
    assert (karak["last_price"], karak["prev_price"]) == (Decimal("22.00"), Decimal("21.50"))

    # The curated raw names snap to the staged catalog rows.
    milk_snap = snap_item(items, "MILK PWDR 2.5KG NIDO")
    karak_snap = snap_item(items, "KARAK TEA DUST")
    assert milk_snap is not None and str(milk_snap["id"]) == MILK_POWDER_ID
    assert karak_snap is not None and str(karak_snap["id"]) == KARAK_TEA_ID

    # And the demo invoice prices fire exactly the intended alert lines.
    invoice = ExtractedInvoice(
        supplier_name="Gulf Foods Trading LLC",
        currency="AED",
        lines=[
            ExtractedLine(
                raw_name="MILK PWDR 2.5KG NIDO",
                qty=Decimal("12"),
                unit_price=Decimal("54.50"),
                line_total=Decimal("654.00"),
            ),
            ExtractedLine(
                raw_name="KARAK TEA DUST",
                qty=Decimal("3"),
                unit_price=Decimal("18.75"),
                line_total=Decimal("56.25"),
            ),
        ],
        total=Decimal("745.76"),
    )
    alerts = price_alerts(invoice, [milk_snap, karak_snap])
    assert [render_price_alert(a) for a in alerts] == [
        "Milk Powder 2.5kg up AED 4.00 (50.50 to 54.50) since your last purchase.",
        "Karak Tea Dust down AED 3.25 (22.00 to 18.75) since your last purchase.",
    ]

    # Three weeks of history: 3 observations per item, oldest ~21 days back,
    # newest ~7 days back (matching last_price_at).
    per_item = await db.pool.fetch(
        """
        select supplier_item_id, count(*) as n, min(observed_at) as oldest,
               max(observed_at) as newest
        from supplier_item_prices
        where supplier_item_id in (select id from supplier_items where tenant_id = $1)
        group by supplier_item_id
        """,
        CHAIN_TENANT_ID,
    )
    assert len(per_item) == 6
    now = datetime.datetime.now(datetime.UTC)
    for row in per_item:
        assert row["n"] == 3
        assert now - 22 * DAY <= row["oldest"] <= now - 20 * DAY
        assert now - 8 * DAY <= row["newest"] <= now - 6 * DAY
    assert now - 8 * DAY <= milk["last_price_at"] <= now - 6 * DAY

    # The history ends at the staged last_price (the sparkline's story).
    history = [
        p["price"] for p in await db.list_item_prices(MILK_POWDER_ID, tenant_id=CHAIN_TENANT_ID)
    ]
    assert history == [Decimal("49.25"), Decimal("49.75"), Decimal("50.50")]


async def test_double_apply_is_idempotent(db):
    await apply_demo_seed(db)
    before = await chain_counts(db)
    items_before = await db.pool.fetch(
        "select id, canonical_name, unit, pack_size, last_price, prev_price "
        "from supplier_items where tenant_id = $1 order by id",
        CHAIN_TENANT_ID,
    )

    await apply_demo_seed(db)

    assert await chain_counts(db) == before
    items_after = await db.pool.fetch(
        "select id, canonical_name, unit, pack_size, last_price, prev_price "
        "from supplier_items where tenant_id = $1 order by id",
        CHAIN_TENANT_ID,
    )
    assert [tuple(r) for r in items_after] == [tuple(r) for r in items_before]


async def test_reapply_resets_a_rehearsal_and_spares_other_tenants(db):
    await apply_demo_seed(db)
    baseline = await chain_counts(db)

    # The founder's one manual step: the demo handset on the flagship branch.
    await db.pool.execute(
        "update branches set wa_phone_e164 = $2 where id = $1", FLAGSHIP_BRANCH_ID, DEMO_HANDSET
    )

    # --- a rehearsal run for the demo chain, end to end -----------------------
    await db.record_inbound_message("wamid.demo1", DEMO_HANDSET, "image", {"type": "image"})
    doc_id = await db.insert_document(
        CHAIN_TENANT_ID, FLAGSHIP_BRANCH_ID, "wamid.demo1", "image/jpeg", "deadbeef"
    )
    await db.enqueue("process_wa_message", {"message_id": "wamid.demo1"})
    await db.enqueue("extract_document", {"document_id": doc_id})
    invoice_id = await db.pool.fetchval(
        """
        insert into invoices (tenant_id, branch_id, document_id, supplier_id, total, status)
        values ($1, $2, $3, $4, 745.76, 'confirmed') returning id
        """,
        CHAIN_TENANT_ID,
        FLAGSHIP_BRANCH_ID,
        doc_id,
        GULF_FOODS_ID,
    )
    await db.pool.execute(
        """
        insert into invoice_lines (tenant_id, invoice_id, raw_name, supplier_item_id, qty,
                                   unit_price)
        values ($1, $2, 'MILK PWDR 2.5KG NIDO', $3, 12, 54.50)
        """,
        CHAIN_TENANT_ID,
        invoice_id,
        MILK_POWDER_ID,
    )
    await db.insert_extraction_run(
        doc_id,
        model_id="fake-model",
        prompt_version="v0",
        input_tokens=1,
        output_tokens=1,
        latency_ms=1,
        repair_applied=False,
        outcome="extracted",
    )
    # The confirm moved the baseline and appended history (what breaks re-runs).
    await db.pool.execute(
        "insert into supplier_item_prices (tenant_id, supplier_item_id, price, invoice_id) "
        "values ($1, $2, 54.50, $3)",
        CHAIN_TENANT_ID,
        MILK_POWDER_ID,
        invoice_id,
    )
    await db.pool.execute(
        "update supplier_items set prev_price = last_price, last_price = 54.50 where id = $1",
        MILK_POWDER_ID,
    )
    # A confirm also self-built an unknown supplier and item.
    stray_supplier = await db.pool.fetchval(
        "insert into suppliers (tenant_id, name) values ($1, 'Souq Al Haraj Veg') returning id",
        CHAIN_TENANT_ID,
    )
    await db.pool.execute(
        "insert into supplier_items (tenant_id, supplier_id, canonical_name) "
        "values ($1, $2, 'Mint Bunch')",
        CHAIN_TENANT_ID,
        stray_supplier,
    )
    await db.record_outbound_message("wamid.demo.out1", DEMO_HANDSET, "Reply OK to confirm.")

    # --- canary: seed.sql's original demo tenant gets rows of every kind ------
    await db.record_inbound_message("wamid.keep1", "971500000000", "image", {"type": "image"})
    keep_doc = await db.insert_document(
        DEMO_TENANT_ID,
        "00000000-0000-0000-0000-000000000011",
        "wamid.keep1",
        "image/jpeg",
        "cafef00d",
    )
    keep_job = await db.enqueue("extract_document", {"document_id": keep_doc})
    keep_invoice = await db.pool.fetchval(
        "insert into invoices (tenant_id, document_id, total) values ($1, $2, 10.00) returning id",
        DEMO_TENANT_ID,
        keep_doc,
    )
    keep_supplier = await db.pool.fetchval(
        "insert into suppliers (tenant_id, name) values ($1, 'Keep Trading Co') returning id",
        DEMO_TENANT_ID,
    )
    keep_item = await db.pool.fetchval(
        "insert into supplier_items (tenant_id, supplier_id, canonical_name, last_price) "
        "values ($1, $2, 'Keep Item', 9.99) returning id",
        DEMO_TENANT_ID,
        keep_supplier,
    )
    await db.pool.execute(
        "insert into supplier_item_prices (tenant_id, supplier_item_id, price) "
        "values ($1, $2, 9.99)",
        DEMO_TENANT_ID,
        keep_item,
    )

    # --- the one-command reset ------------------------------------------------
    await apply_demo_seed(db)

    # The rehearsal is gone and the staged state is back, byte for byte.
    assert await chain_counts(db) == baseline
    milk = await db.get_supplier_item(MILK_POWDER_ID, tenant_id=CHAIN_TENANT_ID)
    assert (milk["last_price"], milk["prev_price"]) == (Decimal("50.50"), Decimal("49.75"))
    assert (
        await db.pool.fetchval(
            "select count(*) from suppliers where name = $1", "Souq Al Haraj Veg"
        )
        == 0
    )
    for message_id in ("wamid.demo1", "wamid.demo.out1"):
        assert (
            await db.pool.fetchval(
                "select count(*) from wa_messages where message_id = $1", message_id
            )
            == 0
        )
    assert (
        await db.pool.fetchval(
            "select count(*) from jobs where payload->>'document_id' = $1 "
            "or payload->>'message_id' = 'wamid.demo1'",
            doc_id,
        )
        == 0
    )
    assert (
        await db.pool.fetchval(
            "select count(*) from extraction_runs where document_id = $1", doc_id
        )
        == 0
    )

    # The founder's phone survives the reset (it is the one manual step).
    assert (
        await db.pool.fetchval(
            "select wa_phone_e164 from branches where id = $1", FLAGSHIP_BRANCH_ID
        )
        == DEMO_HANDSET
    )

    # The canary tenant kept every row: the reset cannot reach other tenants.
    assert await db.get_document(keep_doc, tenant_id=DEMO_TENANT_ID) is not None
    assert await db.get_invoice(str(keep_invoice), tenant_id=DEMO_TENANT_ID) is not None
    assert (await db.get_supplier_item(keep_item, tenant_id=DEMO_TENANT_ID))[
        "last_price"
    ] == Decimal("9.99")
    assert len(await db.list_item_prices(str(keep_item), tenant_id=DEMO_TENANT_ID)) == 1
    assert await db.pool.fetchval("select count(*) from jobs where id = $1", keep_job) == 1
    assert await db.get_inbound_message("wamid.keep1") is not None


# -- act two: the staged menu (WP-66) -----------------------------------------
#
# The seed rehearses; the real menu gates. These hold the staged half honest:
# every hand-written cost in the SQL is re-derived through the shipped
# arithmetic, and the plate figures are hand-checked to the fils, so a seed
# that drifted from `costing.py` or `plates.py` fails here rather than on stage.


async def _plate(db, name: str) -> plates.Plate:
    """One menu item's answer, assembled exactly the way menu.py assembles it -
    material prices derived on read, joined to the current recipe version."""
    item = await db.pool.fetchrow(
        "select id::text as id, selling_price from menu_items where tenant_id = $1 and name = $2",
        CHAIN_TENANT_ID,
        name,
    )
    recipe = await db.get_current_recipe(item["id"], tenant_id=CHAIN_TENANT_ID)
    components = await db.get_recipe_components(recipe["id"], tenant_id=CHAIN_TENANT_ID)
    prices = {}
    for row in await db.list_mapped_pack_costs(tenant_id=CHAIN_TENANT_ID):
        prices.setdefault(row["ingredient_id"], row)
    costed = [
        plates.cost_component(
            position=c["position"],
            qty=c["qty"],
            unit=c["unit"],
            ingredient_name=c["ingredient_name"],
            has_packs=c["has_packs"],
            price=None
            if c["ingredient_id"] not in prices
            else plates.Priced(
                cost_per_base_unit=prices[c["ingredient_id"]]["cost_per_base_unit"],
                base_unit=prices[c["ingredient_id"]]["cost_base_unit"],
                quality=(prices[c["ingredient_id"]]["cost_basis"] or {}).get("quality"),
                stale=False,
            ),
        )
        for c in components
    ]
    return plates.plate(
        costed,
        yield_portions=recipe["yield_portions"],
        selling_price=item["selling_price"],
        vat_rate=Decimal("0.05"),
    )


async def test_every_hand_written_cost_matches_the_shipped_arithmetic(db):
    """The seed writes `cost_per_base_unit` by hand because it is pure SQL and
    cannot call `costing.py`. This is the check that keeps the two the same
    number: each staged line is re-costed through the shipped code, and the
    columns must agree exactly."""
    await apply_demo_seed(db)
    lines = await db.pool.fetch(
        """
        select l.position, l.raw_name, l.qty, l.unit, l.unit_price, l.pack_size,
               l.cost_per_base_unit, l.cost_base_unit, l.cost_basis
        from invoice_lines l join invoices i on i.id = l.invoice_id
        where i.tenant_id = $1 order by l.invoice_id, l.position
        """,
        CHAIN_TENANT_ID,
    )
    assert len(lines) == 10
    for line in lines:
        derived = costing.cost_line(
            position=line["position"],
            qty=line["qty"],
            unit_price=line["unit_price"],
            pack_size=line["pack_size"],
            raw_name=line["raw_name"],
            unit=line["unit"],
        )
        assert derived.cost == line["cost_per_base_unit"], line["raw_name"]
        assert derived.base_unit == line["cost_base_unit"], line["raw_name"]
        assert derived.basis() == line["cost_basis"], line["raw_name"]


async def test_the_staged_menu_costs_to_the_fils(db):
    """Hand arithmetic on the staged stage, at the newest staged purchase
    (four weeks back since the 35/28-day dating).
    A karak cup: 220 g dust at 0.055 + 2200 ml evaporated milk at 0.0046875 +
    1600 g sugar at 0.0023 + 20 g cardamom at 0.048 = AED 27.0525 a pot, over
    40 cups = 0.676 a cup, against 5.00 net of 5% VAT = 4.762."""
    await apply_demo_seed(db)
    expected = {
        "Karak Tea (Cup)": ("0.676", "4.762", "4.086", "85.8"),
        "Karak Tea (Flask 1 L)": ("4.782", "33.333", "28.551", "85.7"),
        "Cardamom Chai (Flask 2 L)": ("9.797", "52.381", "42.584", "81.3"),
        "Nido Milk Tea": ("1.304", "7.619", "6.315", "82.9"),
    }
    for name, (cost, net, margin, pct) in expected.items():
        answer = await _plate(db, name)
        assert answer.quality is plates.PlateQuality.RELIABLE, name
        assert answer.cost_per_portion == Decimal(cost), name
        assert answer.net_price == Decimal(net), name
        assert answer.margin == Decimal(margin), name
        assert answer.margin_pct == Decimal(pct), name


async def test_the_top_earner_is_the_one_the_script_names(db):
    """Callout one narrates the ranking's own top row, so the staged menu has
    to have an unambiguous one - the flask that earns AED 42.58 a serving."""
    await apply_demo_seed(db)
    margins = {}
    for name in (
        "Karak Tea (Cup)",
        "Karak Tea (Flask 1 L)",
        "Cardamom Chai (Flask 2 L)",
        "Nido Milk Tea",
    ):
        margins[name] = (await _plate(db, name)).margin
    assert max(margins, key=lambda n: margins[n]) == "Cardamom Chai (Flask 2 L)"


async def test_the_paratha_shows_no_cost_and_names_what_it_is_waiting_for(db):
    """The seed leaves Chakki Atta Flour unmapped on purpose: one real row in
    the materials queue, and one menu item that reads *incomplete* with its
    menu price and no numbers at all - never a cheap plate."""
    await apply_demo_seed(db)
    answer = await _plate(db, "Paratha")
    assert answer.quality is plates.PlateQuality.INCOMPLETE
    assert answer.cost_per_portion is None and answer.margin is None
    assert answer.missing == ("no supplier product is mapped to Atta Flour yet",)
    assert (
        await db.pool.fetchval(
            "select ingredient_id from supplier_items where id = $1", ATTA_FLOUR_PACK_ID
        )
        is None
    )


async def test_confirming_a_dearer_milk_invoice_moves_the_plates(db):
    """The money moment, end to end on the staged stage: the on-stage demo
    invoice puts milk powder up from 50.50 to 54.50 a sack, and every plate
    using it earns less on the next screen read - with **zero writes to any
    menu table**, because the cost derives from the invoice line."""
    await apply_demo_seed(db)
    before = {
        name: (await _plate(db, name)).margin for name in ("Nido Milk Tea", "Karak Tea (Cup)")
    }
    menu_writes = await db.pool.fetchval(
        "select count(*) from recipes where tenant_id = $1", CHAIN_TENANT_ID
    )

    # 54.50 a 2.5 kg sack = 0.02180000 per gram, up 0.00160000.
    doc_id = await db.pool.fetchval(
        "insert into documents (tenant_id, source, status) values ($1, 'manual', 'extracted') "
        "returning id",
        CHAIN_TENANT_ID,
    )
    invoice_id = await db.pool.fetchval(
        """
        insert into invoices (tenant_id, document_id, supplier_id, invoice_no, invoice_date,
                              currency, status, confirmed_at)
        values ($1, $2, 'd0000000-0000-0000-0000-000000000021', 'GF-20990', current_date,
                'AED', 'confirmed', now())
        returning id
        """,
        CHAIN_TENANT_ID,
        doc_id,
    )
    await db.pool.execute(
        """
        insert into invoice_lines (tenant_id, invoice_id, position, raw_name, supplier_item_id,
                                   qty, unit, unit_price, line_total, pack_size,
                                   cost_per_base_unit, cost_base_unit, cost_basis)
        values ($1, $2, 0, 'MILK PWDR 2.5KG NIDO', $3, 4, 'sack', 54.50, 218.00, '2.5kg',
                0.02180000, 'g',
                '{"quality": "reliable_with_limitations", "asserted": [], "pack": "2.5kg",
                  "pack_base_quantity": "2500", "pack_source": "pack_size"}'::jsonb)
        """,
        CHAIN_TENANT_ID,
        invoice_id,
        MILK_POWDER_ID,
    )

    # Nido Milk Tea draws 40 g: 40 x 0.0016 = 0.064 off the margin.
    # The karak cup draws no milk powder at all and must not move by a fils.
    after = {name: (await _plate(db, name)).margin for name in before}
    assert before["Nido Milk Tea"] - after["Nido Milk Tea"] == Decimal("0.064")
    assert after["Karak Tea (Cup)"] == before["Karak Tea (Cup)"]
    assert (
        await db.pool.fetchval("select count(*) from recipes where tenant_id = $1", CHAIN_TENANT_ID)
        == menu_writes
    )


# -- the real stage: demo_reset_loop.sql --------------------------------------
#
# Once F7's real menu is loaded through /menu/load, demo_seed.sql must never
# run against that database again - its reset deletes the menu, its materials
# and every mapping. The between-rehearsals reset becomes demo_reset_loop.sql,
# whose scope is the props: rehearsal residue is any demo-chain invoice
# printing one of the four prop numbers (DEMO-1..3 and KAS-5), so the loaded
# menu, the mappings, and the KAS-1..4 preparation purchases - which share
# suppliers with the props ON PURPOSE - are out of reach by construction.
# These tests prove the split from both sides.


async def apply_loop_reset(db) -> None:
    await db.pool.execute(LOOP_RESET_FILE.read_text())


async def _build_a_real_stage(db) -> dict:
    """A slice of what the consultant and the chain's own papers put on the
    live database: a loaded menu item with its material, the staged atta pack
    mapped (real work through the M5 door), and one real supplier's confirmed
    invoice with a costed line and its price history."""
    saffron = await db.create_ingredient(
        tenant_id=CHAIN_TENANT_ID, name="Saffron", base_unit="g", actor="console"
    )
    item = await db.create_menu_item(
        tenant_id=CHAIN_TENANT_ID,
        name="Saffron Chai",
        selling_price=Decimal("12"),
        actor="console",
        category="Tea Corner",
    )
    recipe = await db.create_recipe_version(
        str(item["id"]),
        tenant_id=CHAIN_TENANT_ID,
        yield_portions=Decimal("10"),
        yield_label="cups",
        components=[{"ingredient_id": str(saffron["id"]), "qty": Decimal("2"), "unit": "g"}],
        actor="console",
    )
    await db.map_supplier_item(
        ATTA_FLOUR_PACK_ID,
        tenant_id=CHAIN_TENANT_ID,
        ingredient_id=ATTA_FLOUR_ID,
        actor="console",
    )
    supplier = await db.pool.fetchval(
        "insert into suppliers (tenant_id, name) values ($1, 'Koukh Veg Traders') returning id",
        CHAIN_TENANT_ID,
    )
    pack = await db.pool.fetchval(
        "insert into supplier_items (tenant_id, supplier_id, canonical_name, last_price) "
        "values ($1, $2, 'Saffron 10g Tin', 42.00) returning id",
        CHAIN_TENANT_ID,
        supplier,
    )
    doc = await db.pool.fetchval(
        "insert into documents (tenant_id, source, status) values ($1, 'manual', 'extracted') "
        "returning id",
        CHAIN_TENANT_ID,
    )
    invoice = await db.pool.fetchval(
        """
        insert into invoices (tenant_id, document_id, supplier_id, supplier_name, invoice_no,
                              invoice_date, currency, status, confirmed_at)
        values ($1, $2, $3, 'Koukh Veg Traders', 'KV-101', current_date - 2, 'AED',
                'confirmed', now())
        returning id
        """,
        CHAIN_TENANT_ID,
        doc,
        supplier,
    )
    await db.pool.execute(
        """
        insert into invoice_lines (tenant_id, invoice_id, position, raw_name, supplier_item_id,
                                   qty, unit, unit_price, line_total, pack_size,
                                   cost_per_base_unit, cost_base_unit)
        values ($1, $2, 0, 'SAFFRON 10G TIN', $3, 1, 'tin', 42.00, 42.00, '10g', 4.20000000, 'g')
        """,
        CHAIN_TENANT_ID,
        invoice,
        pack,
    )
    await db.pool.execute(
        "insert into supplier_item_prices (tenant_id, supplier_item_id, price, invoice_id) "
        "values ($1, $2, 42.00, $3)",
        CHAIN_TENANT_ID,
        pack,
        invoice,
    )

    # The KAS-3-shaped preparation purchase: a NEW pack minted under the SAME
    # staged supplier the on-stage prop names (Al Madina), with a different
    # invoice number - the sharpest thing the reset's scope must spare.
    kas_doc = await db.pool.fetchval(
        "insert into documents (tenant_id, source, status) values ($1, 'manual', 'extracted') "
        "returning id",
        CHAIN_TENANT_ID,
    )
    kas_pack = await db.pool.fetchval(
        "insert into supplier_items (tenant_id, supplier_id, canonical_name, pack_size, "
        "last_price, last_price_at) "
        "values ($1, $2, 'Milk Powder 25kg', '25kg', 395.00, now() - interval '6 days') "
        "returning id",
        CHAIN_TENANT_ID,
        AL_MADINA_ID,
    )
    kas_invoice = await db.pool.fetchval(
        """
        insert into invoices (tenant_id, document_id, supplier_id, supplier_name, invoice_no,
                              invoice_date, currency, status, confirmed_at)
        values ($1, $2, $3, 'Al Madina Trading Co.', 'AMT-26-1203', current_date - 6, 'AED',
                'confirmed', now() - interval '6 days')
        returning id
        """,
        CHAIN_TENANT_ID,
        kas_doc,
        AL_MADINA_ID,
    )
    await db.pool.execute(
        """
        insert into invoice_lines (tenant_id, invoice_id, position, raw_name, supplier_item_id,
                                   qty, unit, unit_price, line_total, pack_size,
                                   cost_per_base_unit, cost_base_unit)
        values ($1, $2, 0, 'MILK POWDER 25 KG', $3, 2, 'bag', 395.00, 790.00, '25kg',
                0.01580000, 'g')
        """,
        CHAIN_TENANT_ID,
        kas_invoice,
        kas_pack,
    )
    await db.pool.execute(
        "insert into supplier_item_prices (tenant_id, supplier_item_id, price, invoice_id, "
        "observed_at) values ($1, $2, 395.00, $3, now() - interval '6 days')",
        CHAIN_TENANT_ID,
        kas_pack,
        kas_invoice,
    )
    return {
        "ingredient": str(saffron["id"]),
        "menu_item": str(item["id"]),
        "recipe": str(recipe["id"]),
        "supplier": str(supplier),
        "pack": str(pack),
        "document": str(doc),
        "invoice": str(invoice),
        "kas_pack": str(kas_pack),
        "kas_invoice": str(kas_invoice),
    }


async def _forward_and_confirm_a_prop(
    db,
    *,
    wamid: str,
    supplier_id: str,
    supplier_name: str,
    invoice_no: str,
    pack_id: str,
    raw_name: str,
    price: str,
) -> dict:
    """The residue one forwarded prop leaves: the photo's rows end to end, the
    confirm's price append and moved baseline, and the audit row the confirm
    wrote against its invoice."""
    await db.record_inbound_message(wamid, DEMO_HANDSET, "image", {"type": "image"})
    doc_id = await db.insert_document(
        CHAIN_TENANT_ID, FLAGSHIP_BRANCH_ID, wamid, "image/jpeg", "hash-" + wamid
    )
    await db.enqueue("process_wa_message", {"message_id": wamid})
    await db.enqueue("extract_document", {"document_id": doc_id})
    invoice_id = await db.pool.fetchval(
        """
        insert into invoices (tenant_id, branch_id, document_id, supplier_id, supplier_name,
                              invoice_no, invoice_date, total, status, confirmed_at)
        values ($1, $2, $3, $4, $5, $6, current_date, 745.76, 'confirmed', now())
        returning id
        """,
        CHAIN_TENANT_ID,
        FLAGSHIP_BRANCH_ID,
        doc_id,
        supplier_id,
        supplier_name,
        invoice_no,
    )
    await db.pool.execute(
        """
        insert into invoice_lines (tenant_id, invoice_id, raw_name, supplier_item_id, qty,
                                   unit_price)
        values ($1, $2, $3, $4, 12, $5::numeric)
        """,
        CHAIN_TENANT_ID,
        invoice_id,
        raw_name,
        pack_id,
        price,
    )
    await db.insert_extraction_run(
        doc_id,
        model_id="fake-model",
        prompt_version="v0",
        input_tokens=1,
        output_tokens=1,
        latency_ms=1,
        repair_applied=False,
        outcome="extracted",
    )
    await db.pool.execute(
        "insert into supplier_item_prices (tenant_id, supplier_item_id, price, invoice_id) "
        "values ($1, $2, $3::numeric, $4)",
        CHAIN_TENANT_ID,
        pack_id,
        price,
        invoice_id,
    )
    await db.pool.execute(
        "update supplier_items set prev_price = last_price, last_price = $2::numeric, "
        "last_price_at = now() where id = $1",
        pack_id,
        price,
    )
    await db.pool.execute(
        """
        insert into audit_events (tenant_id, actor, action, subject_type, subject_id)
        values ($1, 'whatsapp:971509999999', 'invoice.confirmed', 'invoice', $2)
        """,
        CHAIN_TENANT_ID,
        invoice_id,
    )
    await db.record_outbound_message("out-" + wamid, DEMO_HANDSET, "Reply OK to confirm.")
    return {"document": str(doc_id), "invoice": str(invoice_id)}


async def test_the_loop_reset_spares_a_loaded_menu_and_its_real_evidence(db):
    await apply_demo_seed(db)
    await db.pool.execute(
        "update branches set wa_phone_e164 = $2 where id = $1", FLAGSHIP_BRANCH_ID, DEMO_HANDSET
    )
    real = await _build_a_real_stage(db)

    # A rehearsal forwards and confirms the props: act one's DEMO-1 on the
    # staged milk pack, and the real stage's KAS-5 on the KAS-3 pack.
    demo1 = await _forward_and_confirm_a_prop(
        db,
        wamid="wamid.loop1",
        supplier_id=GULF_FOODS_ID,
        supplier_name="Gulf Foods Trading LLC",
        invoice_no="GFT-2026-0834",
        pack_id=MILK_POWDER_ID,
        raw_name="MILK PWDR 2.5KG NIDO",
        price="54.50",
    )
    kas5 = await _forward_and_confirm_a_prop(
        db,
        wamid="wamid.loop2",
        supplier_id=AL_MADINA_ID,
        supplier_name="Al Madina Trading Co.",
        invoice_no="AMT-26-1274",
        pack_id=real["kas_pack"],
        raw_name="MILK POWDER 25 KG",
        price="432.00",
    )

    # Canary rows for seed.sql's tenant, same as the full-reset test.
    keep_doc = await db.pool.fetchval(
        "insert into documents (tenant_id, source, status) values ($1, 'manual', 'extracted') "
        "returning id",
        DEMO_TENANT_ID,
    )
    keep_invoice = await db.pool.fetchval(
        "insert into invoices (tenant_id, document_id, total) values ($1, $2, 10.00) returning id",
        DEMO_TENANT_ID,
        keep_doc,
    )

    audit_before = await db.pool.fetchval(
        "select count(*) from audit_events where tenant_id = $1", CHAIN_TENANT_ID
    )

    await apply_loop_reset(db)

    # Both props are gone and both alerts are re-armed: the staged pack back
    # to its staged baselines, the KAS pack back to its preparation purchase.
    milk = await db.get_supplier_item(MILK_POWDER_ID, tenant_id=CHAIN_TENANT_ID)
    assert (milk["last_price"], milk["prev_price"]) == (Decimal("50.50"), Decimal("49.75"))
    history = [
        p["price"] for p in await db.list_item_prices(MILK_POWDER_ID, tenant_id=CHAIN_TENANT_ID)
    ]
    assert history == [Decimal("49.25"), Decimal("49.75"), Decimal("50.50")]
    kas_pack = await db.get_supplier_item(real["kas_pack"], tenant_id=CHAIN_TENANT_ID)
    assert (kas_pack["last_price"], kas_pack["prev_price"]) == (Decimal("395.00"), None)
    assert [
        p["price"] for p in await db.list_item_prices(real["kas_pack"], tenant_id=CHAIN_TENANT_ID)
    ] == [Decimal("395.00")]

    for rehearsal in (demo1, kas5):
        assert await db.get_invoice(rehearsal["invoice"], tenant_id=CHAIN_TENANT_ID) is None
        assert await db.get_document(rehearsal["document"], tenant_id=CHAIN_TENANT_ID) is None
        assert (
            await db.pool.fetchval(
                "select count(*) from extraction_runs where document_id = $1",
                rehearsal["document"],
            )
            == 0
        )
    for message_id in ("wamid.loop1", "wamid.loop2"):
        assert (
            await db.pool.fetchval(
                "select count(*) from wa_messages where message_id = $1", message_id
            )
            == 0
        )
        assert (
            await db.pool.fetchval(
                "select count(*) from jobs where payload->>'message_id' = $1", message_id
            )
            == 0
        )
    assert (
        await db.pool.fetchval(
            "select count(*) from jobs where payload->>'document_id' in ($1, $2)",
            demo1["document"],
            kas5["document"],
        )
        == 0
    )
    assert (
        await db.pool.fetchval(
            "select count(*) from audit_events where tenant_id = $1", CHAIN_TENANT_ID
        )
        == audit_before - 2
    )  # exactly the two prop confirms' rows went

    # The staged purchase evidence survives untouched, dated safely behind
    # any printed paper (the 35/28-day rule in demo_seed's header).
    staged = await db.pool.fetch(
        """
        select invoice_no, invoice_date from invoices
        where tenant_id = $1
          and invoice_no in ('AM-7731', 'AM-7902', 'GF-20418', 'GF-20655')
        order by invoice_no
        """,
        CHAIN_TENANT_ID,
    )
    assert [r["invoice_no"] for r in staged] == ["AM-7731", "AM-7902", "GF-20418", "GF-20655"]
    today = datetime.date.today()
    assert all(today - r["invoice_date"] >= 27 * DAY for r in staged)

    # Everything real survived: the loaded menu, its material, the mapping,
    # the KAS-3-shaped preparation purchase on a PROP supplier, and the real
    # supplier's invoice, line and price history.
    assert (
        await db.pool.fetchval(
            "select count(*) from menu_items where tenant_id = $1", CHAIN_TENANT_ID
        )
        == 6  # the five staged items plus Saffron Chai - no menu row touched
    )
    assert (
        await db.pool.fetchval(
            "select count(*) from recipe_components where recipe_id = $1", real["recipe"]
        )
        == 1
    )
    assert (
        await db.pool.fetchval("select name from ingredients where id = $1", real["ingredient"])
        == "Saffron"
    )
    assert (
        str(
            await db.pool.fetchval(
                "select ingredient_id from supplier_items where id = $1", ATTA_FLOUR_PACK_ID
            )
        )
        == ATTA_FLOUR_ID
    )
    assert await db.get_invoice(real["kas_invoice"], tenant_id=CHAIN_TENANT_ID) is not None
    assert await db.get_invoice(real["invoice"], tenant_id=CHAIN_TENANT_ID) is not None
    assert (
        await db.pool.fetchval(
            "select count(*) from invoice_lines where invoice_id = $1", real["invoice"]
        )
        == 1
    )
    assert len(await db.list_item_prices(real["pack"], tenant_id=CHAIN_TENANT_ID)) == 1
    assert (
        await db.pool.fetchval(
            "select count(*) from suppliers where tenant_id = $1", CHAIN_TENANT_ID
        )
        == 3  # the two staged props and Koukh Veg Traders, nothing minted or lost
    )

    # The founder's phone and the canary tenant are untouched.
    assert (
        await db.pool.fetchval(
            "select wa_phone_e164 from branches where id = $1", FLAGSHIP_BRANCH_ID
        )
        == DEMO_HANDSET
    )
    assert await db.get_document(str(keep_doc), tenant_id=DEMO_TENANT_ID) is not None
    assert await db.get_invoice(str(keep_invoice), tenant_id=DEMO_TENANT_ID) is not None


async def test_the_loop_reset_is_idempotent(db):
    await apply_demo_seed(db)
    await apply_loop_reset(db)
    before = await chain_counts(db)
    items_before = await db.pool.fetch(
        "select id, canonical_name, unit, pack_size, last_price, prev_price "
        "from supplier_items where tenant_id = $1 order by id",
        CHAIN_TENANT_ID,
    )

    await apply_loop_reset(db)

    assert await chain_counts(db) == before
    items_after = await db.pool.fetch(
        "select id, canonical_name, unit, pack_size, last_price, prev_price "
        "from supplier_items where tenant_id = $1 order by id",
        CHAIN_TENANT_ID,
    )
    assert [tuple(r) for r in items_after] == [tuple(r) for r in items_before]


async def test_a_curated_paper_printed_days_ago_still_moves_the_plates(db):
    """The landmine the 35/28-day dating defuses: costing ranks purchases by
    the PRINTED invoice date, and a curated prop ages between demos. A confirm
    whose paper prints a date from a week and a half back must still become
    the newest milk purchase and move the plates - if the staged purchases
    ever creep forward again, this fails before the stage does."""
    await apply_demo_seed(db)
    before = (await _plate(db, "Nido Milk Tea")).margin

    doc_id = await db.pool.fetchval(
        "insert into documents (tenant_id, source, status) values ($1, 'manual', 'extracted') "
        "returning id",
        CHAIN_TENANT_ID,
    )
    invoice_id = await db.pool.fetchval(
        """
        insert into invoices (tenant_id, document_id, supplier_id, invoice_no, invoice_date,
                              currency, status, confirmed_at)
        values ($1, $2, 'd0000000-0000-0000-0000-000000000021', 'GF-20991', current_date - 11,
                'AED', 'confirmed', now())
        returning id
        """,
        CHAIN_TENANT_ID,
        doc_id,
    )
    await db.pool.execute(
        """
        insert into invoice_lines (tenant_id, invoice_id, position, raw_name, supplier_item_id,
                                   qty, unit, unit_price, line_total, pack_size,
                                   cost_per_base_unit, cost_base_unit, cost_basis)
        values ($1, $2, 0, 'MILK PWDR 2.5KG NIDO', $3, 4, 'sack', 54.50, 218.00, '2.5kg',
                0.02180000, 'g',
                '{"quality": "reliable_with_limitations", "asserted": [], "pack": "2.5kg",
                  "pack_base_quantity": "2500", "pack_source": "pack_size"}'::jsonb)
        """,
        CHAIN_TENANT_ID,
        invoice_id,
        MILK_POWDER_ID,
    )

    after = (await _plate(db, "Nido Milk Tea")).margin
    assert before - after == Decimal("0.064")  # 40 g x 0.0016 per gram


async def test_demo_seed_refuses_to_run_over_a_real_menu(db):
    """The tripwire in demo_seed.sql itself: a database whose demo chain
    carries dozens of menu items looks like a real menu, and the file must
    refuse to vaporize it rather than reset it."""
    await apply_demo_seed(db)
    await db.pool.execute(
        """
        insert into menu_items (tenant_id, name, selling_price)
        select $1, 'Real Item ' || n, 5.00 from generate_series(1, 41) n
        """,
        CHAIN_TENANT_ID,
    )

    with pytest.raises(asyncpg.PostgresError, match="demo_reset_loop"):
        await apply_demo_seed(db)

    assert (
        await db.pool.fetchval(
            "select count(*) from menu_items where tenant_id = $1", CHAIN_TENANT_ID
        )
        == 46  # nothing was deleted on the refused run
    )


async def test_the_reset_clears_a_rehearsals_menu_edits(db):
    """A rehearsal that renamed an item, added a recipe version or approved a
    mapping must leave nothing behind - the audit trail included."""
    await apply_demo_seed(db)
    item_id = await db.pool.fetchval(
        "select id::text from menu_items where tenant_id = $1 and name = 'Paratha'",
        CHAIN_TENANT_ID,
    )
    await db.set_menu_item_price(
        item_id, tenant_id=CHAIN_TENANT_ID, selling_price=Decimal("4.00"), actor="console"
    )
    await db.create_menu_item(
        tenant_id=CHAIN_TENANT_ID,
        name="Rehearsal Special",
        selling_price=Decimal("9"),
        actor="console",
    )
    await db.map_supplier_item(
        ATTA_FLOUR_PACK_ID,
        tenant_id=CHAIN_TENANT_ID,
        ingredient_id=ATTA_FLOUR_ID,
        actor="console",
    )

    await apply_demo_seed(db)

    assert await db.pool.fetchval(
        "select selling_price from menu_items where tenant_id = $1 and name = 'Paratha'",
        CHAIN_TENANT_ID,
    ) == Decimal("3.000")
    assert (
        await db.pool.fetchval(
            "select count(*) from menu_items where tenant_id = $1 and name = 'Rehearsal Special'",
            CHAIN_TENANT_ID,
        )
        == 0
    )
    assert (
        await db.pool.fetchval(
            "select ingredient_id from supplier_items where id = $1", ATTA_FLOUR_PACK_ID
        )
        is None
    )
    assert (
        await db.pool.fetchval(
            "select count(*) from audit_events where tenant_id = $1", CHAIN_TENANT_ID
        )
        == 0
    )


# -- act three: the sales week (WP-85) ----------------------------------------
#
# The demo's sales are invented; its purchases are not. The generator in
# Docs/demo-invoices/koukh-al-shay/build_sales_week.py writes a till export
# from the shipped code, and these prove the week loads through the same door
# a pilot would use, that the screen agrees with the generator to the tenth,
# and that the two resets treat the week the way the runbook says: the
# practice reset clears it, the loop reset spares it.

GENERATOR = (
    pathlib.Path(__file__).resolve().parents[3]
    / "Docs"
    / "demo-invoices"
    / "koukh-al-shay"
    / "build_sales_week.py"
)
REAL_WEEK_CSV = GENERATOR.parent / "sales-week.csv"
SALES_TABLES = ("sales_daily", "sales_lines", "till_items", "sales_layouts", "branch_aliases")

#: A second console user, a member of the demo chain: the door scopes every day
#: by the token's tenant, and the demo chain is not seed.sql's tenant.
CHAIN_USER_ID = "00000000-0000-4000-8000-0000000000cc"
CHAIN_AUTH = {"Authorization": f"Bearer {JWKS.mint(sub=CHAIN_USER_ID)}"}

#: seed.sql's tenant, with two more branches for the committed week's three outlets.
FIXTURE_BRANCHES = {
    "AL QUSAIS": "00000000-0000-0000-0000-000000000011",
    "AL NAHDA": "00000000-0000-0000-0000-000000000012",
    "ROLLA": "00000000-0000-0000-0000-000000000013",
}


def _generator():
    """The generator as a module, imported from its path (it is a demo script, not a
    package), so the practice week is built in-process against the seed just applied."""
    spec = importlib.util.spec_from_file_location("build_sales_week", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def sales_api(settings, db):
    app = FastAPI()
    app.include_router(sales_router)
    app.state.settings = settings
    wire_auth(app)
    app.state.db = db
    app.state.storage = Storage(settings, transport=FakeStorage().transport())
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _chain_member(db) -> None:
    await db.pool.execute(
        "insert into memberships (tenant_id, user_id) values ($1, $2)",
        CHAIN_TENANT_ID,
        CHAIN_USER_ID,
    )


def _days_from_rows(rows: list[list[str]], branch_ids: dict[str, str]) -> list[dict]:
    """The loader's grouping, mirrored for the pinned header only: one item day per
    outlet and date, lines in file order, day-first dates, a row with no date (the
    totals footer) skipped. The outlet's till label resolves to a branch the way the
    mapping step's taught aliases do."""
    days: dict[tuple[str, str], dict] = {}
    for outlet, date_text, code, item, qty, amount in rows:
        if date_text == "":
            continue
        day, month, year = date_text.split("/")
        iso = f"{year}-{month}-{day}"
        entry = days.setdefault(
            (outlet, iso),
            {
                "branch_id": branch_ids[outlet],
                "business_date": iso,
                "granularity": "item",
                "amount_basis": "inclusive",
                "lines": [],
            },
        )
        entry["lines"].append(
            {
                "position": len(entry["lines"]),
                "name": item,
                "code": code,
                "qty": qty,
                "amount": amount,
            }
        )
    return [days[key] for key in sorted(days)]


async def _post_week(client, days: list[dict], headers: dict) -> list[str]:
    """One branch per request, as the loader posts a branch-month; the outcomes in order."""
    by_branch: dict[str, list[dict]] = {}
    for day in days:
        by_branch.setdefault(day["branch_id"], []).append(day)
    outcomes: list[str] = []
    for branch_days in by_branch.values():
        response = await client.post("/api/sales/days", json={"days": branch_days}, headers=headers)
        assert response.status_code == 200, response.text
        outcomes.extend(day["outcome"] for day in response.json()["days"])
    return outcomes


async def _sales_counts(db, tenant_id: str = CHAIN_TENANT_ID) -> dict[str, int]:
    return {
        table: await db.pool.fetchval(
            f"select count(*) from {table} where tenant_id = $1", tenant_id
        )
        for table in SALES_TABLES
    }


def _read_csv(path: pathlib.Path) -> tuple[list[str], list[list[str]]]:
    with path.open(newline="") as handle:
        rows = list(csv.reader(handle))
    return rows[0], rows[1:]


async def test_the_practice_week_loads_through_the_door_and_the_screen_agrees(sales_api, db):
    """The rehearsal week: generated in-process after the seed runs, on the days the
    seed staged its purchases (read from the database, never computed from today),
    loaded through POST /api/sales/days - 21 days, all loaded; the same week again is
    21 unchanged - and /api/sales/branches shows Al Qusais at the ratio the generator
    printed, to the tenth, with the two other branches incomplete because they have
    sales and no papers (the founder's P3)."""
    await apply_demo_seed(db)
    await _chain_member(db)
    gen = _generator()

    stage = await gen.read_practice_stage(TEST_DATABASE_URL)
    newest = await db.pool.fetchval(
        "select max(coalesce(invoice_date, (confirmed_at at time zone 'UTC')::date)) "
        "from invoices where tenant_id = $1 and status = 'confirmed'",
        CHAIN_TENANT_ID,
    )
    assert stage.end == newest
    week = gen.practice_week(stage.end)
    branch_ids = {branch.till_label: branch.branch_id for branch in gen.BRANCHES}
    rows = [row.csv() for row in week.rows] + [["TOTAL", "", "", "", "", str(week.total)]]
    days = _days_from_rows(rows, branch_ids)
    assert len(days) == 21

    assert await _post_week(sales_api, days, CHAIN_AUTH) == ["loaded"] * 21
    assert await _post_week(sales_api, days, CHAIN_AUTH) == ["unchanged"] * 21

    expected = {row.branch_name: row for row in gen.figures(week, stage.invoices)}
    response = await sales_api.get(
        "/api/sales/branches",
        params={"from": week.start.isoformat(), "to": week.end.isoformat()},
        headers=CHAIN_AUTH,
    )
    assert response.status_code == 200, response.text
    table = {row["branch_name"]: row for row in response.json()["rows"]}
    flagship = table["Al Qusais Branch"]
    assert flagship["ratio_pct"] == str(expected["Al Qusais Branch"].ratio_pct)
    assert flagship["net_sales"] == str(expected["Al Qusais Branch"].net_sales)
    assert flagship["purchases"] == str(expected["Al Qusais Branch"].purchases)
    assert flagship["quality"] == "reliable_with_limitations"
    assert Decimal("30") <= Decimal(flagship["ratio_pct"]) <= Decimal("40")
    for name in ("Al Nahda Branch", "Rolla Branch"):
        assert table[name]["quality"] == "incomplete", name
        assert table[name]["ratio_pct"] is None, name
        assert any("no confirmed purchases" in note for note in table[name]["notes"]), name
    # The screen's default period ends on the week's last day - nothing to type on stage.
    default = await sales_api.get("/api/sales/branches", headers=CHAIN_AUTH)
    assert default.json()["period"]["to"] == week.end.isoformat()

    # demo_seed.sql clears the week: a complete practice reset.
    assert (await _sales_counts(db))["sales_daily"] == 21
    await apply_demo_seed(db)
    assert all(count == 0 for count in (await _sales_counts(db)).values())

    # demo_reset_loop.sql spares it: the week is consultant work, not rehearsal residue.
    assert await _post_week(sales_api, days, CHAIN_AUTH) == ["loaded"] * 21
    before = await _sales_counts(db)
    await apply_loop_reset(db)
    assert await _sales_counts(db) == before


async def test_the_committed_real_week_loads_on_the_fixture_tenant(sales_api, db):
    """The file the founder uploads on the real stage, loaded through the door on
    seed.sql's tenant: 21 days, idempotent, and the stored takings add up to the
    file's own footer. The footer is what a till prints - takings, VAT inside - so
    the equality is on takings; the net is the door's division, per line, and the
    stored net equals the file's rows divided the shipped way."""
    gen = _generator()
    header, rows = _read_csv(REAL_WEEK_CSV)
    assert header == list(gen.HEADER)
    footer = rows[-1]
    assert footer[0] == "TOTAL" and footer[1] == ""  # no date: skipped and counted by the loader
    for branch_id, name in (
        (FIXTURE_BRANCHES["AL NAHDA"], "Al Nahda Branch"),
        (FIXTURE_BRANCHES["ROLLA"], "Rolla Branch"),
    ):
        await db.pool.execute(
            "insert into branches (id, tenant_id, name, timezone) "
            "values ($1, $2, $3, 'Asia/Dubai')",
            branch_id,
            DEMO_TENANT_ID,
            name,
        )
    days = _days_from_rows(rows, FIXTURE_BRANCHES)
    assert len(days) == 21
    assert days[0]["business_date"] == gen.week_ending(gen.real_week_end())[0].isoformat()

    assert await _post_week(sales_api, days, AUTH) == ["loaded"] * 21
    assert await _post_week(sales_api, days, AUTH) == ["unchanged"] * 21

    stored = await db.pool.fetchrow(
        "select sum(takings) as takings, sum(net_sales) as net, sum(line_count) as lines "
        "from sales_daily where tenant_id = $1",
        DEMO_TENANT_ID,
    )
    assert stored["takings"] == Decimal(footer[5])
    assert stored["lines"] == len(rows) - 1
    expected_net = sum(
        (
            takings.net_amount(Decimal(row[5]), amount_basis="inclusive", vat_rate=Decimal("0.05"))
            for row in rows[:-1]
        ),
        Decimal(0),
    )
    assert stored["net"] == expected_net
    # One "not a menu item" line a day, minted once as a till item under its code.
    assert (
        await db.pool.fetchval(
            "select count(*) from till_items where tenant_id = $1 and code = $2",
            DEMO_TENANT_ID,
            gen.DELIVERY_CODE,
        )
        == 1
    )


def test_the_generator_runs_with_no_database_and_no_key_and_is_reproducible(tmp_path):
    """The real week needs no database and no API key: a menu CSV in the loader's
    shape in, a till export out, the same bytes every run. The founder's real menu
    lives outside the repo, so the committed file is compared only where it exists."""
    menu = tmp_path / "menu.csv"
    menu.write_text(
        "category,item_code,item_name,selling_price_aed,yield_portions,yield_label,"
        "ingredient,qty_as_purchased,unit,source_text\n"
        "Tea Corner,52a,Karak Tea - Flask 1 L,35.00,1,serving,CTC black tea,27.5,g,\n"
        "Tea Corner,52a,Karak Tea - Flask 1 L,35.00,1,serving,White sugar,60,g,\n"
        "Special Gravy,128,Chicken 65 Dry,17.00,4,portions,Chicken boneless,600,g,\n"
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"TEST_DATABASE_URL", "DATABASE_URL", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"}
    }
    outputs = []
    for run in ("first", "second"):
        out = tmp_path / f"{run}.csv"
        result = subprocess.run(
            [sys.executable, str(GENERATOR), "--csv", str(menu), "--out", str(out)],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert "Al Qusais Branch" in result.stdout and "ratio" in result.stdout
        outputs.append(out.read_bytes())
    assert outputs[0] == outputs[1]
    header, rows = _read_csv(tmp_path / "first.csv")
    assert header == ["Outlet", "Date", "PLU", "Item", "Qty", "Amount"]
    assert rows[-1][0] == "TOTAL" and rows[-1][1] == ""
    assert len({(row[0], row[1]) for row in rows[:-1]}) == 21

    gen = _generator()
    if gen.DEFAULT_CSV.exists():
        regenerated = tmp_path / "committed.csv"
        gen.write_csv(gen.real_week(gen.DEFAULT_CSV), regenerated)
        assert regenerated.read_bytes() == REAL_WEEK_CSV.read_bytes()


# --- act four (WP-95) ---------------------------------------------------------
#
# `DEMO_RUNBOOK.md` §H is the dashboard read straight after act three, and every
# figure in it is printed by `Docs/demo-invoices/koukh-al-shay/act_four.py`,
# never typed. These are the assertions that keep the script true: what act four
# says on each stage, so a change that quietly breaks the script fails here
# instead of on stage.
#
# Two stages, because they say different things (C13.3a). The **practice** stage
# is `demo_seed.sql`'s five costed items and the rehearsal week - all of it
# inside this repository, so it runs everywhere - and it is a five-item tea menu
# where every dish keeps between 81% and 86%. No dish can sit ten points below
# an average made of those dishes, no branch can sit five points below a chain
# selling the same five, and the seed's own price history moves nothing by 5%,
# so **no signal can fire on it** and act four must not promise one there. The
# **real** stage is the one the demo runs on - the 45-item menu, the five KAS
# papers, the committed week - and it is where the league, the low-margin dish
# and the milk moves live. It needs the founder's menu CSV, which lives outside
# the repository, so it is skipped where that file is not.

ACT_FOUR = GENERATOR.parent / "act_four.py"


def _act_four():
    """The script as a module, imported from its path the way `_generator` is."""
    spec = importlib.util.spec_from_file_location("act_four", ACT_FOUR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def act_four(db):
    """The script's own app over the test database: the shipped routers, the
    real doors, and the token check replaced by a fixed context."""
    module = _act_four()
    app = module._app(db, TEST_DATABASE_URL)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://act-four")
    return module, client


def _every_money_is_a_string(payload: dict) -> None:
    for row in payload["league"] + [payload["total"]]:
        for field in ("net_sales", "purchases", "contribution", "contribution_pct"):
            assert row.get(field) is None or isinstance(row[field], str), field
    for row in payload["items"]["all"]:
        for field in ("net_item_sales", "contribution", "contribution_pct", "cost_per_portion"):
            assert row[field] is None or isinstance(row[field], str), field


async def test_act_four_on_the_practice_stage_says_only_what_is_there(act_four, db):
    """The rehearsal stage: a contribution figure for every branch, the league
    ordered by what each keeps and the sentence naming its top row, the chain
    reconciling to its branches, the Paratha carrying no numbers and saying
    why - and **no signal at all**, which is the honest answer on a five-item
    menu whose dishes all keep within five points of each other."""
    module, client = act_four
    async with client:
        reads = await module.practice_stage(client, db, TEST_DATABASE_URL)
    [(title, payload)] = reads
    assert title == "the practice stage"

    kept = [Decimal(row["contribution_pct"]) for row in payload["league"]]
    assert len(kept) == 3 and kept == sorted(kept)
    first = payload["league"][0]["branch_name"]
    assert payload["answer"]["branch"] == (
        f"Look at {first.removesuffix(' Branch')} first: it keeps about AED "
        f"{Decimal(payload['league'][0]['contribution_pct']).quantize(Decimal('1'))} "
        "of every 100 it takes, the least of the three."
    )
    assert Decimal(payload["total"]["contribution"]) == sum(
        Decimal(row["contribution"]) for row in payload["league"]
    )

    assert payload["menu"] == {"items": 5, "costed": 4}
    assert payload["items"]["count"] == 4
    assert payload["items"]["bottom"] == []  # four costed rows do not make two fives
    paratha = next(r for r in payload["items"]["all"] if r["menu_item_name"] == "Paratha")
    assert paratha["contribution"] is None and paratha["contribution_pct"] is None
    assert "no supplier product is mapped to Atta Flour yet" in paratha["notes"]
    _every_money_is_a_string(payload)

    # The whole week is mapped, so nothing is waiting and nothing is unnamed.
    assert payload["unmapped"] == {"names": 0, "value": "0.00"}

    # No signal, and therefore no dish sentence: act four's panel is empty here
    # and §H says so rather than promising a money moment the stage cannot show.
    assert payload["signals"] == []
    assert payload["answer"]["item"] is None

    # C12.4: the dashboard's plate equals /menu's only while no confirmed paper
    # is dated after the period's last day. On the committed stage none is.
    assert all(row["cost_per_portion_today"] is None for row in payload["items"]["all"])


async def test_act_four_speaks_the_figures_the_runbook_quotes(act_four, db):
    """The stage the demo runs on, read twice: the 45-item menu costed off the
    four preparation papers, the committed week loaded through the door, every
    till name mapped - then the same read again after the paper the founder
    forwards on stage. These are §H's figures, and this is what keeps them
    true: the branch the league puts first, the chain's kept percentage before
    and after, the dish that sells and does not earn, the item at the bottom of
    the five, and the two milk moves with their money and their date."""
    module, client = act_four
    if not module.DEFAULT_CSV.exists():
        pytest.skip("the founder's 45-item menu lives outside the repository")
    async with client:
        reads = await module.real_stage(client, db, module.DEFAULT_CSV)
    (before_title, before), (after_title, after) = reads
    assert before_title == "the real stage, before KAS-5"
    assert after_title == "the real stage, after KAS-5 is confirmed on stage"

    # The period is the week's own, whatever day the demo runs on: 28 days
    # ending on the newest loaded day, and the plates costed at that day.
    for payload in (before, after):
        assert payload["period"]["from"] == "2026-08-04"
        assert payload["period"]["to"] == "2026-08-31"
        assert payload["period"]["days"] == 28 and payload["period"]["default"] is True
        assert payload["period"]["costed_at"] == "2026-08-31"
        assert payload["menu"] == {"items": 45, "costed": 45}
        assert payload["items"]["count"] == 45
        assert payload["unmapped"] == {"names": 0, "value": "0.00"}
        _every_money_is_a_string(payload)
        # C12.4 again: no paper is dated after 31 Aug - KAS-5 is printed on it -
        # so the dashboard's plate is today's plate, and no row carries a second
        # cost. Print a paper dated 1 Sep and this changes, which is why §H
        # states it as a condition and never as a promise.
        assert all(row["cost_per_portion_today"] is None for row in payload["items"]["all"])

        # The one sentence, named and worded.
        assert payload["answer"]["branch"] == (
            "Look at Al Nahda first: it keeps about AED 66 of every 100 it takes, "
            "the least of the three."
        )
        assert payload["answer"]["item"] == (
            "Hot Chocolate - Large 250 ml sells more than any item that earns under "
            "the menu's average."
        )
        assert [row["branch_name"] for row in payload["league"]] == [
            "Al Nahda Branch",
            "Rolla Branch",
            "Al Qusais Branch",
        ]

    # The league and the chain, before the on-stage paper and after it. Act
    # three's own ratio is the row underneath, and it moves the way §G says.
    assert [row["contribution_pct"] for row in before["league"]] == ["65.7", "65.8", "66.0"]
    assert [row["contribution_pct"] for row in after["league"]] == ["65.5", "65.6", "65.8"]
    assert before["total"]["contribution"] == "47020.76"
    assert before["total"]["contribution_pct"] == "65.8"
    assert after["total"]["contribution"] == "46908.73"
    assert after["total"]["contribution_pct"] == "65.7"
    assert before["league"][-1]["ratio_pct"] == "30.3"
    assert after["league"][-1]["ratio_pct"] == "39.3"

    # The item that sells and does not earn, and the bottom of the five.
    assert [row["menu_item_name"] for row in after["items"]["bottom"]] == [
        "Lotus Cake - slice",
        "Honey Cake - slice",
        "Karak Delivery - Large 400 ml",
        "Karak Delivery - Medium 250 ml",
        "Karak Delivery - Small 120 ml",
    ]
    worst = after["items"]["bottom"][-1]
    assert (worst["contribution"], worst["contribution_pct"]) == ("116.40", "16.6")
    assert (worst["qty_sold"], worst["net_item_sales"]) == ("492.000", "702.86")

    # The signals, in the order the panel reads them. Before the on-stage paper
    # there is no move to compare, so the panel is the two low-margin dishes.
    assert [(s["kind"], s["money_at_stake"]) for s in before["signals"]] == [
        ("popular_low_margin", "406.29"),
        ("popular_low_margin", "245.64"),
    ]
    assert [
        (s["kind"], s["money_at_stake"], s["menu_item_name"] or s["ingredient_name"])
        for s in after["signals"]
    ] == [
        ("popular_low_margin", "403.28", "Hot Chocolate - Large 250 ml"),
        ("popular_low_margin", "243.66", "Hot Chocolate - Small 150 ml"),
        ("price_spike", "25.93", "Evaporated milk"),
        ("price_spike", "1.11", "Milk powder"),
    ]

    # The drill §H opens on that row: its plate to the fils, and the one
    # component the on-stage paper moved, each naming the invoice line behind it.
    def _evaporated(payload: dict) -> dict:
        row = payload["items"]["bottom"][-1]
        return next(c for c in row["components"] if c["ingredient_name"] == "Evaporated milk")

    assert (worst["cost_per_portion"], worst["net_price"], worst["avg_sold_at"]) == (
        "1.192",
        "1.429",
        "1.429",
    )
    assert (_evaporated(before)["cost_per_portion"], _evaporated(before)["purchased_on"]) == (
        "0.541",
        "2026-08-25",
    )
    assert (_evaporated(after)["cost_per_portion"], _evaporated(after)["purchased_on"]) == (
        "0.580",
        "2026-08-31",
    )
    assert before["items"]["bottom"][-1]["contribution"] == "135.58"

    spikes = {s["ingredient_name"]: s for s in after["signals"] if s["kind"] == "price_spike"}
    assert spikes["Milk powder"]["sentence"] == "Milk powder is up AED 1.06 per kg since 31 Aug."
    assert spikes["Milk powder"]["moved_on"] == "2026-08-31"
    assert spikes["Evaporated milk"]["sentence"] == (
        "Evaporated milk is up AED 0.83 per litre since 31 Aug."
    )
    assert spikes["Evaporated milk"]["moved_on"] == "2026-08-31"
