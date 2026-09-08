"""M12 WP-120: the printed comparison, end to end through Postgres.

`test_usage.py` proves the arithmetic without a database and `test_usage_db.py`
proves the SQL under it. This file is the join: a tenant staged through the
real doors - papers confirmed through the confirm path, sales days loaded
through `POST /api/sales/days`, till names mapped through the till-item door,
recipes written through the recipe door - read by `usage_report.usage_inputs`,
turned into §3.1's block by `usage_report.usage_blocks`, and printed.

Two things are pinned hardest, because they are what phase two inherits:

  * the printout's words are the rows' own words. Every `used_words`,
    `bought_words`, `gap_words`, quality word and note on a row appears in
    its section, exactly, and a figure that could not be summed shows its
    reason and no number - so the panel WP-122 renders and this printout can
    never say the same thing two ways.
  * the rows behind the printout are `usage.material_rows` called directly on
    the same adapted inputs (one arithmetic, two consumers), and the chain's
    figures are the exact sums over the branches its own notes name.
"""

import asyncio
import datetime
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI

from faida_api import usage
from faida_api.api import router as api_router
from faida_api.config import get_settings
from faida_api.menu import router as menu_router
from faida_api.sales import router as sales_router
from faida_api.storage import Storage
from faida_api.usage_report import (
    main,
    render,
    usage_blocks,
    usage_inputs,
    usage_payload,
)

from .conftest import (
    AUTH,
    DEMO_TENANT_ID,
    TEST_DATABASE_URL,
    FakeStorage,
    requires_db,
    wire_auth,
)
from .test_plates import _catalog_item, _material, _menu_item, _recipe, _supplier
from .test_sales_load import _item_day
from .test_sales_load import _line as _till_line

pytestmark = requires_db

TENANT = DEMO_TENANT_ID
BRANCH = "00000000-0000-0000-0000-000000000011"  # seed.sql's branch, "Al Barsha Branch"
NAHDA = "00000000-0000-0000-0000-000000000012"
ROLLA = "00000000-0000-0000-0000-000000000013"

OTHER_TENANT = "00000000-0000-0000-0000-0000000000ff"
OTHER_BRANCH = "00000000-0000-0000-0000-0000000000fe"

#: The period, and the week of sales inside it. The papers land on the last
#: day, which is the honest failure mode the milestone was built around: one
#: delivery in a seven-day window is a delivery, not a rate.
#:
#: The period ends today because the recipes are written today: a recipe
#: created after the period makes every row it touches *estimated* (D14), and
#: that rule has its own case in `test_usage.py`. Here it would put the word
#: on every row and hide the three the stage exists to tell apart.
TODAY = datetime.datetime.now(datetime.UTC).date()
TO = TODAY
FROM = TODAY - datetime.timedelta(days=27)
WEEK_FROM = TODAY - datetime.timedelta(days=6)
DELIVERY = TODAY

D = Decimal

#: The command's own spelling of that period.
ARGV_FROM = ("--from", FROM.isoformat())
ARGV_TO = ("--to", TO.isoformat())


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


# --- staging, through the real doors ----------------------------------------


def _purchase(
    raw_name: str,
    *,
    supplier_item_id: str | None,
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
        "qty": None if qty is None else D(qty),
        "unit": unit,
        "pack_size": pack_size,
        "unit_price": None if unit_price is None else D(unit_price),
        "line_total": None if line_total is None else D(line_total),
        "line_kind": line_kind,
    }


async def _paper(
    db,
    lines: list[dict],
    *,
    supplier_id: str | None,
    tenant_id: str = TENANT,
    branch_id: str | None = BRANCH,
    invoice_date: datetime.date | None = DELIVERY,
    currency: str = "AED",
    invoice_no: str | None = "GF-3318",
    total: str = "500.00",
) -> str:
    """One paper with its lines, confirmed through the real confirm path, so
    each line's pack factor is frozen by the transaction that confirmed it."""
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
        D(total),
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
    assert await db.confirm_invoice(invoice_id, tenant_id=tenant_id, actor="console") is True
    return invoice_id


async def _branches(db) -> None:
    for branch_id, name in ((NAHDA, "Al Nahda Branch"), (ROLLA, "Rolla Branch")):
        await db.pool.execute(
            "insert into branches (id, tenant_id, name, timezone) "
            "values ($1, $2, $3, 'Asia/Dubai')",
            branch_id,
            TENANT,
            name,
        )


async def _week(api, branch: str, lines: list[tuple[str, str, str]], days: int = 7) -> None:
    """`days` item days on a branch, each with the given (name, qty, net)
    lines - the inclusive amount chosen so the net is exact."""
    body = []
    for offset in range(days):
        printed = [
            _till_line(
                position,
                name,
                str((D(net) * D("1.05")).quantize(D("0.01"))),
                code=f"{position + 10}",
                qty=qty,
            )
            for position, (name, qty, net) in enumerate(lines)
        ]
        body.append(
            _item_day(
                (WEEK_FROM + datetime.timedelta(days=offset)).isoformat(), printed, branch=branch
            )
        )
    response = await api.post("/api/sales/days", json={"days": body}, headers=AUTH)
    assert response.status_code == 200, response.text


async def _map(api, db, till_name: str, menu_item_id: str) -> None:
    till_id = await db.pool.fetchval(
        "select id::text from till_items where tenant_id = $1 and name = $2", TENANT, till_name
    )
    response = await api.post(
        f"/api/till-items/{till_id}/menu-item",
        json={"menu_item_id": menu_item_id},
        headers=AUTH,
    )
    assert response.status_code == 200, response.text


@pytest.fixture
async def stage(db, api) -> dict:
    """Three branches on one tenant.

    Al Barsha sells a week of karak and a week of paratha and takes one paper:
    two 50 kg sacks of sugar, six 400 g bags of tea dust, a carton of gloves
    nobody's recipe names, one line on a product with no material yet, and one
    line that reached no product at all. Al Nahda sells the same karak week
    and takes no paper. Rolla loads nothing and takes a paper - the
    purchase-only branch (D12). The paratha's material has no pack mapped, so
    its row carries what the recipes needed and no bought figure. One more
    paper names no branch.
    """
    await _branches(db)
    supplier_id = await _supplier(db, "Gulf Foods Trading L.L.C.")
    sugar_pack = await _catalog_item(db, supplier_id, "SUGAR 50KG", "50kg")
    dust_pack = await _catalog_item(db, supplier_id, "KARAK TEA DUST 400G", "400g")
    gloves_pack = await _catalog_item(db, supplier_id, "NITRILE GLOVES 100S", "100 pcs")
    mystery_pack = await _catalog_item(db, supplier_id, "Chicken Carton", "1 ctn")

    sugar = await _material(db, sugar_pack, "White Sugar", "g")
    dust = await _material(db, dust_pack, "Karak Tea Dust", "g")
    await _material(db, gloves_pack, "Nitrile Gloves", "pc")
    # Atta Flour is named by a recipe and no supplier product is mapped to it.
    atta = str(
        await db.pool.fetchval(
            "insert into ingredients (tenant_id, name, base_unit) values ($1, $2, $3) returning id",
            TENANT,
            "Atta Flour",
            "g",
        )
    )

    karak = await _menu_item(api, "Karak Tea (Cup)", "5.00")
    await _recipe(
        api,
        karak,
        [
            {"ingredient_id": dust, "qty": "220", "unit": "g"},
            {"ingredient_id": sugar, "qty": "1600", "unit": "g"},
        ],
        yield_portions="40",
    )
    paratha = await _menu_item(api, "Paratha", "3.00")
    await _recipe(
        api, paratha, [{"ingredient_id": atta, "qty": "2000", "unit": "g"}], yield_portions="20"
    )

    await _week(api, BRANCH, [("KARAK", "110", "550.00"), ("PARATHA", "20", "60.00")])
    await _week(api, NAHDA, [("KARAK", "50", "250.00")])
    await _map(api, db, "KARAK", karak)
    await _map(api, db, "PARATHA", paratha)

    qusais_paper = await _paper(
        db,
        [
            _purchase(
                "SUGAR 50KG",
                supplier_item_id=sugar_pack,
                qty="2",
                pack_size="50kg",
                unit_price="115.00",
                line_total="230.00",
            ),
            _purchase(
                "KARAK TEA DUST 400G",
                supplier_item_id=dust_pack,
                qty="6",
                pack_size="400g",
                unit_price="22.00",
                line_total="132.00",
            ),
            _purchase(
                "NITRILE GLOVES 100S",
                supplier_item_id=gloves_pack,
                qty="20",
                pack_size="100 pcs",
                unit_price="9.00",
                line_total="180.00",
            ),
            _purchase(
                "Chicken Carton",
                supplier_item_id=mystery_pack,
                qty="1",
                pack_size="1 ctn",
                unit_price="187.00",
                line_total="187.00",
            ),
            _purchase(
                "MYSTERY SACK", supplier_item_id=None, qty="1", pack_size="5kg", unit_price=None
            ),
            # The camera read the pack and missed the quantity. The confirm
            # door costs no such line and creates no product for it, so it
            # comes back with nothing to place it by - and it must not be
            # counted as a delivery of nothing.
            _purchase("NO QTY SACK", supplier_item_id=None, qty=None, pack_size="50kg"),
            _purchase(
                "DELIVERY CHARGE",
                supplier_item_id=None,
                qty="1",
                unit_price="25.00",
                line_kind="charge",
            ),
        ],
        supplier_id=supplier_id,
        invoice_no="GF-3318",
    )
    rolla_paper = await _paper(
        db,
        [
            _purchase(
                "SUGAR 50KG",
                supplier_item_id=sugar_pack,
                qty="1",
                pack_size="50kg",
                unit_price="115.00",
                line_total="115.00",
            ),
        ],
        supplier_id=supplier_id,
        branch_id=ROLLA,
        invoice_no="GF-3319",
    )
    no_branch_paper = await _paper(
        db,
        [
            _purchase(
                "SUGAR 50KG",
                supplier_item_id=sugar_pack,
                qty="1",
                pack_size="50kg",
                unit_price="115.00",
                line_total="115.00",
            ),
        ],
        supplier_id=supplier_id,
        branch_id=None,
        invoice_no="GF-3320",
    )
    return {
        "supplier_id": supplier_id,
        "sugar": sugar,
        "dust": dust,
        "atta": atta,
        "karak": karak,
        "paratha": paratha,
        "papers": [qusais_paper, rolla_paper, no_branch_paper],
    }


async def _inputs(db, *, branch_id: str | None = None):
    return await usage_inputs(db, tenant_id=TENANT, date_from=FROM, date_to=TO, branch_id=branch_id)


async def _printed(db, *, branch_id: str | None = None) -> tuple[str, object]:
    inputs = await _inputs(db, branch_id=branch_id)
    blocks = usage_blocks(inputs)
    return (
        render(blocks, branch_names=inputs.branch_names, currency=inputs.currency),
        blocks,
    )


def _by(rows, ingredient_id: str, branch: str | None):
    for row in rows:
        if row.ingredient_id == ingredient_id and row.branch_id == branch:
            return row
    raise AssertionError(f"no row for {ingredient_id} at {branch}")


def _section_of(text: str, title: str) -> str:
    """The block of the printout under one heading, up to the next rule."""
    parts = text.split("=" * 78)
    for index, part in enumerate(parts):
        if part.strip().startswith(title):
            return parts[index + 1]
    raise AssertionError(f"no section for {title!r}")


# --- the printout on the staged chain ---------------------------------------


@requires_db
async def test_every_branch_and_the_chain_get_a_section_closed_by_the_standing_sentence(db, stage):
    """One section per branch, then the chain, and the sentence that says what
    a difference is and is not closes every one of them - it is the whole
    honesty of the milestone and nothing on the page may be read without it."""
    text, blocks = await _printed(db)

    for title in ("Al Nahda Branch", "Al Barsha Branch", "Rolla Branch", "Every branch together"):
        section = _section_of(text, title)
        assert usage.STANDING_SENTENCE in section, title
    assert text.count(usage.STANDING_SENTENCE) == 4
    assert blocks.standing == usage.STANDING_SENTENCE


@requires_db
async def test_each_row_prints_the_rows_own_words_and_every_note_beneath_it(db, stage):
    """C14.6: the API composes every quantity and every sentence and the
    consumer shows them. If this drifts, the panel and the printout are two
    different reports of one week."""
    text, blocks = await _printed(db)
    section = _section_of(text, "Al Barsha Branch")

    sugar = _by(blocks.branch_rows, stage["sugar"], BRANCH)
    assert sugar.used_words is not None and sugar.bought_words is not None
    assert f"recipes needed {sugar.used_words}" in section
    assert f"bought {sugar.bought_words}" in section
    assert sugar.gap_words in section
    assert "reliable with limitations" in section
    for row in blocks.branch_rows:
        if row.branch_id != BRANCH:
            continue
        for note in row.notes:
            assert note in section, (row.ingredient_name, note)

    # The two figures, the difference and the money on one line, in that order.
    line = next(
        line
        for line in section.splitlines()
        if line.strip().startswith("recipes needed") and sugar.used_words in line
    )
    assert line.index("recipes needed") < line.index("bought ")
    assert line.index("bought ") < line.index(sugar.gap_words)
    assert f"AED {sugar.money}" in line


@requires_db
async def test_a_figure_that_could_not_be_summed_prints_its_reason_and_no_number(db, stage):
    """Atta Flour is named by the paratha's recipe and no supplier product is
    mapped to it, so the row carries what the recipes needed, no bought figure
    and the sentence that names the next action - never a zero, which would
    read as a shelf that is exactly right."""
    text, blocks = await _printed(db)
    section = _section_of(text, "Al Barsha Branch")

    atta = _by(blocks.branch_rows, stage["atta"], BRANCH)
    assert atta.used_base == D("14000")  # 140 parathas at 2 kg per 20-portion batch
    assert atta.bought_base is None
    assert atta.bought_hole == "no pack mapped"
    assert atta.money is None
    assert "Rows with a figure that could not be summed" in section
    assert "bought - (no pack mapped)" in section
    assert "no supplier product is mapped to Atta Flour yet" in section
    # Its own money is absent, and nothing was printed in the hole.
    atta_line = next(line for line in section.splitlines() if "no pack mapped" in line)
    assert "AED" not in atta_line


@requires_db
async def test_the_rows_behind_the_printout_are_usage_material_rows_on_the_same_inputs(db, stage):
    """One arithmetic, two consumers (C14.11). The block is `usage.py` called
    on the adapted inputs and nothing else, so WP-121's panel is this report
    with a wire around it."""
    inputs = await _inputs(db)
    blocks = usage_blocks(inputs)

    direct = usage.material_rows(
        inputs.item_rows,
        inputs.menu,
        inputs.lines,
        inputs.windows,
        materials=inputs.materials,
        prices=inputs.prices,
        stale_ingredient_ids=inputs.stale_ingredient_ids,
        date_from=inputs.period.start,
        date_to=inputs.period.end,
        currency=inputs.currency,
    )
    assert list(blocks.branch_rows) == direct


@requires_db
async def test_the_chains_figures_are_the_exact_sums_over_the_branches_it_names(db, stage):
    """C14.9's pinned invariant. Al Barsha bought two sacks and Rolla one; the
    chain says three, and the paper that named no branch is in neither - it
    lies in the whole period while the branch rows lie in clipped windows, so
    a sum would add two spans. The chain names it instead."""
    text, blocks = await _printed(db)
    chain = _by(blocks.rows, stage["sugar"], None)
    branches = [r for r in blocks.branch_rows if r.ingredient_id == stage["sugar"]]

    assert chain.bought_base == sum(r.bought_base for r in branches if r.bought_base is not None)
    assert chain.bought_base == D("150000")
    assert chain.used_base == sum(r.used_base for r in branches if r.used_base is not None)
    assert "Rolla Branch: no sales loaded" in chain.notes
    assert "1 paper with no branch holds 50 kg of White Sugar, not counted here" in chain.notes

    section = _section_of(text, "Every branch together")
    assert "Rolla Branch: no sales loaded" in section
    assert "Papers that named no branch, counted in no row" in section
    assert "White Sugar: 50 kg on 1 paper" in section


@requires_db
async def test_a_branch_with_purchases_and_no_sales_keeps_its_purchase_only_rows(db, stage):
    """D12. Rolla loaded nothing and took a delivery: the row says what was
    bought, shows no figure on the used side, and says why."""
    text, blocks = await _printed(db)
    rolla = _by(blocks.branch_rows, stage["sugar"], ROLLA)

    assert rolla.bought_base == D("50000")
    assert rolla.used_base is None
    assert rolla.used_hole == "no sales loaded"
    assert rolla.quality is usage.Quality.UNAVAILABLE

    section = _section_of(text, "Rolla Branch")
    assert "recipes needed - (no sales loaded)" in section
    assert "unavailable" in section


@requires_db
async def test_the_four_lists_and_the_coverage_line_close_the_chain_section(db, stage):
    """The lists beside the panel: what was bought outside every sold recipe,
    the products with no material yet, the lines that reached no product with
    their papers, and the papers that named no branch - plus the recipe
    coverage line with the orphan lines named on it (D20)."""
    text, blocks = await _printed(db)
    section = _section_of(text, "Every branch together")

    # Named by the catalog product it was booked under, not by the material:
    # nothing the dashboard read holds carries an ingredient name for a
    # material no recipe mentions, so `usage.py`'s stand-in names it and the
    # adapter supplies only how it is measured (D11; the report's note).
    assert [m.ingredient_name for m in blocks.unused_materials] == ["NITRILE GLOVES 100S"]
    assert blocks.unused_materials[0].bought_words == "2,000 pieces"
    assert blocks.unused_materials[0].money == D("180.00")
    assert "Bought, not in any sold recipe" in section
    assert "NITRILE GLOVES 100S: 2,000 pieces on 1 paper, AED 180.00" in section

    assert blocks.unmapped_packs.lines == 1
    assert blocks.unmapped_packs.sentence in section
    assert "has no material yet" in blocks.unmapped_packs.sentence

    assert blocks.orphans.lines == 2
    assert (blocks.orphans.no_price, blocks.orphans.unmatched) == (1, 1)
    assert blocks.orphans.sentence in section
    assert "GF-3318, Gulf Foods Trading L.L.C. (AED): 2 lines" in section
    # A line whose quantity cell was never read is measured as nothing, named,
    # and counted as zero nowhere.
    assert "0 g" not in section.split("Purchase lines that reached no product")[1]

    assert blocks.coverage.sentence in section
    assert "2 purchase lines reached no product" in blocks.coverage.sentence
    assert "the chain's sales value" in blocks.coverage.sentence

    assert "Left out:" in section
    assert "1 branch with no sales loaded" in section


@requires_db
async def test_the_branch_filter_prints_one_section_with_that_branchs_rows(db, stage):
    """Under `--branch` the scope is the branch: its own rows, its own lists,
    its own coverage sentence, and no chain section (D10)."""
    text, blocks = await _printed(db, branch_id=BRANCH)

    assert blocks.branch_rows == ()
    assert {row.branch_id for row in blocks.rows} == {BRANCH}
    assert blocks.unassigned == ()
    assert "this branch's sales value" in blocks.coverage.sentence
    assert "Al Barsha Branch" in text
    assert "Every branch together" not in text
    assert "Rolla Branch" not in text
    assert usage.STANDING_SENTENCE in text


# --- the wire WP-121 will put this on ---------------------------------------


@requires_db
async def test_the_payload_carries_the_ten_keys_with_every_figure_a_string(db, stage):
    """§3.1's block, serialised in the API's conventions: money, quantities
    and percentages as strings, dates ISO (C4), so phase two puts this dict
    straight on `GET /api/dashboard`."""
    _, blocks = await _printed(db)
    payload = usage_payload(blocks)

    assert set(payload) == {
        "standing",
        "rows",
        "branch_rows",
        "count",
        "coverage",
        "unused_materials",
        "unmapped_packs",
        "orphans",
        "unassigned",
        "left_out",
    }
    assert payload["count"] == blocks.count
    assert payload["standing"] == usage.STANDING_SENTENCE

    quantity_keys = {
        "used_base",
        "bought_base",
        "gap_base",
        "used_measured",
        "bought_measured",
        "money",
        "price_per_display_unit",
        "refunded_portions",
        "qty",
        "factor",
        "base_qty",
        "portions",
        "per_portion_base",
        "usable_share",
        "spend",
        "covered_value",
        "sales_value",
        "recipes_pct",
    }
    date_keys = {"priced_on", "purchased_on", "from", "to"}

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if value is None or isinstance(value, (dict, list)):
                    walk(value)
                    continue
                if key in quantity_keys:
                    assert isinstance(value, str), key
                    Decimal(value)
                if key in date_keys:
                    assert isinstance(value, str), key
                    datetime.date.fromisoformat(value)
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    sugar = next(
        r
        for r in payload["branch_rows"]
        if r["branch_id"] == BRANCH and r["ingredient_id"] == stage["sugar"]
    )
    assert sugar["used_words"] and sugar["bought_words"] and sugar["gap_words"]
    assert sugar["window"] == {
        "from": WEEK_FROM.isoformat(),
        "to": TO.isoformat(),
        "days": 7,
    }
    assert sugar["lines"] and sugar["dishes"]
    assert [r["lines"] for r in payload["rows"]] == [[] for _ in payload["rows"]]


# --- tenancy ----------------------------------------------------------------


@requires_db
async def test_a_second_tenants_papers_never_reach_the_first_tenants_printout(db, stage):
    """Every read is scoped by tenant. A neighbour's delivery of the same
    material on the same day is absent from every figure and every list."""
    await db.pool.execute(
        "insert into tenants (id, name, currency) values ($1, $2, 'AED')",
        OTHER_TENANT,
        "Another Cafeteria",
    )
    await db.pool.execute(
        "insert into branches (id, tenant_id, name, timezone) values ($1, $2, $3, 'Asia/Dubai')",
        OTHER_BRANCH,
        OTHER_TENANT,
        "Somebody Else",
    )
    other_supplier = str(
        await db.pool.fetchval(
            "insert into suppliers (tenant_id, name) values ($1, $2) returning id",
            OTHER_TENANT,
            "Another Supplier",
        )
    )
    other_pack = str(
        await db.pool.fetchval(
            "insert into supplier_items (tenant_id, supplier_id, canonical_name, pack_size) "
            "values ($1, $2, 'SUGAR 50KG', '50kg') returning id",
            OTHER_TENANT,
            other_supplier,
        )
    )
    await _paper(
        db,
        [_purchase("NEIGHBOUR SUGAR", supplier_item_id=other_pack, qty="99", pack_size="50kg")],
        supplier_id=other_supplier,
        tenant_id=OTHER_TENANT,
        branch_id=OTHER_BRANCH,
        invoice_no="XX-1",
    )

    text, blocks = await _printed(db)
    assert "NEIGHBOUR SUGAR" not in text
    assert "Somebody Else" not in text
    assert _by(blocks.rows, stage["sugar"], None).bought_base == D("150000")
    for row in blocks.branch_rows:
        for entry in row.lines:
            assert entry.product_name != "NEIGHBOUR SUGAR"


# --- the command's refusals and its empty case ------------------------------


@pytest.fixture
def command(monkeypatch):
    """`main` the way a person runs it: its own pool on `DATABASE_URL`,
    pointed at the test database, and its own event loop - so the run under
    test opens and closes the same connection the founder's will.

    It goes on a thread because `main` calls `asyncio.run`, which is right for
    a command and impossible inside the loop pytest already has running.
    """
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL or "")
    get_settings.cache_clear()
    try:
        yield lambda *argv: asyncio.to_thread(main, list(argv))
    finally:
        get_settings.cache_clear()


@requires_db
async def test_the_command_refuses_without_a_tenant(command, capsys):
    """One plain sentence and a non-zero exit - never a stack trace and never
    a printout of somebody else's chain."""
    assert await command(*ARGV_FROM, *ARGV_TO) == 2
    assert capsys.readouterr().err.strip() == "Say which tenant to print: --tenant <id>."


@requires_db
async def test_the_command_refuses_a_reversed_period_in_the_shipped_words(command, capsys):
    """The period rule is `ratio.resolve_period`'s, so a period this refuses
    is one `/sales` and the dashboard refuse in the same words (C11.6). The
    refusal happens before any connection is opened."""
    reversed_period = ("--from", TO.isoformat(), "--to", FROM.isoformat())
    assert await command("--tenant", TENANT, *reversed_period) == 2
    assert capsys.readouterr().err.strip() == "'from' is after 'to'."

    assert await command("--tenant", TENANT, "--from", "not-a-date", *ARGV_TO) == 2
    assert "is not a date" in capsys.readouterr().err


@requires_db
async def test_the_command_refuses_a_tenant_with_no_branches(db, command, capsys):
    """Nothing to compare, said as a sentence rather than as an empty page."""
    await db.pool.execute(
        "insert into tenants (id, name, currency) values ($1, $2, 'AED')",
        OTHER_TENANT,
        "A Chain With No Branches",
    )
    argv = ("--tenant", OTHER_TENANT, *ARGV_FROM, *ARGV_TO)
    assert await command(*argv) == 2
    assert "has no branches, so there is nothing to compare." in capsys.readouterr().err


@requires_db
async def test_a_tenant_with_branches_and_nothing_loaded_prints_the_empty_sections(
    db, command, capsys
):
    """The failure mode §7 names: a tenant that has loaded nothing gets a
    section per branch saying so, and the standing sentence under each. The
    printout is never blank and never claims a figure it does not have."""
    await _branches(db)
    assert await command("--tenant", TENANT, *ARGV_FROM, *ARGV_TO) == 0
    out = capsys.readouterr().out

    for name in ("Al Barsha Branch", "Al Nahda Branch", "Rolla Branch", "Every branch together"):
        assert name in out
    assert out.count("Nothing to compare in this window.") == 4
    assert out.count(usage.STANDING_SENTENCE) == 4
    assert "no sales value to measure the chain's recipe coverage on" in out


@requires_db
async def test_the_command_prints_the_staged_chain(db, stage, command, capsys):
    """The command end to end: the same words, through argv and its own pool,
    with a zero exit and no chain section under `--branch`."""
    assert await command("--tenant", TENANT, *ARGV_FROM, *ARGV_TO) == 0
    out = capsys.readouterr().out
    assert out.startswith("Faida - what the recipes needed against what was bought")
    assert "White Sugar" in out
    assert usage.STANDING_SENTENCE in out

    text, _ = await _printed(db)
    assert text in out  # the command prints exactly what `render` composed

    assert await command("--tenant", TENANT, *ARGV_FROM, *ARGV_TO, "--branch", BRANCH) == 0
    branch_only = capsys.readouterr().out
    assert "Rolla Branch" not in branch_only
    assert "Every branch together" not in branch_only
