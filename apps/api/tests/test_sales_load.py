"""M8 WP-80: the sales tables and the one write door (Docs/M8_DECOMPOSITION.md
§3 C11, row 80).

The door's whole promise is PRD §13's: one consolidated report per
branch-day, so re-uploading a file is a no-op, a corrected file replaces
exactly the days it carries, and nothing is ever double-counted. Every test
here is one of those promises against real Postgres, plus the arithmetic the
ratio will stand on: net sales is the exact sum of the stored lines, to the
fil, and the till's figure is stored as printed beside it.
"""

import asyncio
import datetime
from decimal import Decimal

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from faida_api import takings
from faida_api.sales import router as sales_router
from faida_api.storage import Storage

from .conftest import (
    AUTH,
    DEMO_TENANT_ID,
    JWKS,
    TEST_ACTOR,
    FakeStorage,
    requires_db,
    wire_auth,
)

pytestmark = requires_db

TENANT = DEMO_TENANT_ID
BRANCH = "00000000-0000-0000-0000-000000000011"  # seed.sql's branch
BRANCH_2 = "00000000-0000-0000-0000-000000000012"
TENANT_B = "b0000000-0000-0000-0000-000000000001"
BRANCH_B = "b0000000-0000-0000-0000-000000000011"

TODAY = datetime.date.today()
DAY = TODAY - datetime.timedelta(days=10)


def _on(offset: int) -> str:
    return (DAY + datetime.timedelta(days=offset)).isoformat()


@pytest.fixture
def api(settings, db):
    fake_storage = FakeStorage()
    app = FastAPI()
    app.include_router(sales_router)
    app.state.settings = settings
    wire_auth(app)
    app.state.db = db
    app.state.storage = Storage(settings, transport=fake_storage.transport())
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    return client, fake_storage


async def _second_branch(db) -> None:
    await db.pool.execute(
        "insert into branches (id, tenant_id, name, timezone) values ($1, $2, 'Al Nahda', "
        "'Asia/Dubai')",
        BRANCH_2,
        TENANT,
    )


async def _other_tenant(db) -> None:
    await db.pool.execute(
        "insert into tenants (id, name, currency) values ($1, 'Other Chain', 'AED')", TENANT_B
    )
    await db.pool.execute(
        "insert into branches (id, tenant_id, name, timezone) values ($1, $2, 'Elsewhere', "
        "'Asia/Dubai')",
        BRANCH_B,
        TENANT_B,
    )


def _line(position: int, name: str, amount: str, code: str | None = None, qty: str | None = None):
    return {"position": position, "name": name, "code": code, "qty": qty, "amount": amount}


def _item_day(date: str, lines: list[dict], *, branch: str = BRANCH, basis="inclusive", **extra):
    return {
        "branch_id": branch,
        "business_date": date,
        "granularity": "item",
        "amount_basis": basis,
        "lines": lines,
        **extra,
    }


def _summary_day(date: str, amount: str, *, branch: str = BRANCH, basis="inclusive", **extra):
    return {
        "branch_id": branch,
        "business_date": date,
        "granularity": "summary",
        "amount_basis": basis,
        "amount": amount,
        **extra,
    }


async def _post(client, days: list[dict], headers=AUTH) -> httpx.Response:
    return await client.post("/api/sales/days", json={"days": days}, headers=headers)


async def _audit(db, action: str) -> list[asyncpg.Record]:
    return await db.pool.fetch(
        "select actor, subject_id::text as subject_id, detail from audit_events "
        "where action = $1 order by created_at, id",
        action,
    )


async def _audit_count(db) -> int:
    return await db.pool.fetchval("select count(*) from audit_events")


async def _stored_days(client, date_from: str, date_to: str) -> list[dict]:
    response = await client.get(
        "/api/sales/days", params={"from": date_from, "to": date_to}, headers=AUTH
    )
    assert response.status_code == 200, response.text
    return response.json()["days"]


# --- the three outcomes -------------------------------------------------------


async def test_a_first_load_is_loaded_with_one_audit_row_naming_the_person(api, db):
    client, _ = api
    response = await _post(
        client,
        [
            _item_day(
                _on(0),
                [
                    _line(0, "KARAK TEA FLASK 1L", "490.00", code="52a", qty="14"),
                    _line(1, "CHAI PAROTTA", "63.00", code="61", qty="6"),
                ],
                source={"sha256": "a" * 64, "filename": "sales-week.csv"},
            )
        ],
    )
    assert response.status_code == 200, response.text
    [outcome] = response.json()["days"]
    assert outcome["outcome"] == "loaded" and outcome["previous"] is None
    day = outcome["day"]
    assert day["branch_id"] == BRANCH and day["business_date"] == _on(0)
    assert day["takings"] == "553.00" and day["net_sales"] == "526.67"  # 466.67 + 60.00
    assert day["line_count"] == 2 and day["vat_rate"] == "0.05"
    assert day["source_sha256"] == "a" * 64 and day["source_filename"] == "sales-week.csv"
    assert day["loaded_by"] == TEST_ACTOR and "lines" not in day

    [event] = await _audit(db, "sales_day.loaded")
    assert event["actor"] == TEST_ACTOR and event["subject_id"] == day["id"]
    assert event["detail"]["net_sales"] == "526.67" and event["detail"]["line_count"] == 2

    [stored] = await _stored_days(client, _on(0), _on(0))
    assert [(line["name"], line["amount"], line["net_amount"]) for line in stored["lines"]] == [
        ("KARAK TEA FLASK 1L", "490.00", "466.67"),
        ("CHAI PAROTTA", "63.00", "60.00"),
    ]
    assert stored["lines"][0]["qty"] == "14.000" and stored["lines"][0]["code"] == "52a"


async def test_the_same_day_again_is_unchanged_and_writes_nothing(api, db):
    client, _ = api
    lines = [_line(0, "KARAK", "10.50", qty="3"), _line(1, "SAMOSA", "4.00", qty="2")]
    assert (await _post(client, [_item_day(_on(0), lines)])).status_code == 200
    before = await _audit_count(db)

    response = await _post(client, [_item_day(_on(0), lines)])
    assert response.status_code == 200, response.text
    [outcome] = response.json()["days"]
    assert outcome["outcome"] == "unchanged" and outcome["previous"] is None
    assert await _audit_count(db) == before
    assert await db.pool.fetchval("select count(*) from sales_daily") == 1


async def test_the_same_rows_reordered_are_unchanged(api, db):
    client, _ = api
    first = [_line(0, "KARAK", "10.50", qty="3"), _line(1, "SAMOSA", "4.00", qty="2")]
    reordered = [_line(0, "Samosa", "4.00", qty="2.000"), _line(1, "karak", "10.50", qty="3")]
    assert (await _post(client, [_item_day(_on(0), first)])).status_code == 200
    before = await _audit_count(db)

    response = await _post(client, [_item_day(_on(0), reordered)])
    assert response.json()["days"][0]["outcome"] == "unchanged", response.text
    assert await _audit_count(db) == before


async def test_a_changed_qty_is_replaced_with_both_figures_and_both_hashes(api, db):
    client, _ = api
    first = _item_day(
        _on(0),
        [_line(0, "KARAK", "10.50", qty="3"), _line(1, "SAMOSA", "4.00", qty="2")],
        source={"sha256": "a" * 64, "filename": "monday.csv"},
    )
    assert (await _post(client, [first])).status_code == 200
    corrected = _item_day(
        _on(0),
        [_line(0, "KARAK", "14.00", qty="4"), _line(1, "SAMOSA", "4.00", qty="2")],
        source={"sha256": "b" * 64, "filename": "monday-fixed.csv"},
    )
    response = await _post(client, [corrected])
    assert response.status_code == 200, response.text
    [outcome] = response.json()["days"]
    assert outcome["outcome"] == "replaced"
    assert outcome["previous"] == {
        "takings": "14.50",
        "net_sales": "13.81",  # 10.00 + 3.81
        "line_count": 2,
        "source_sha256": "a" * 64,
    }
    assert outcome["day"]["takings"] == "18.00" and outcome["day"]["net_sales"] == "17.14"
    assert outcome["day"]["source_sha256"] == "b" * 64

    [event] = await _audit(db, "sales_day.replaced")
    assert event["detail"]["previous"]["source_sha256"] == "a" * 64
    assert event["detail"]["new"]["source_sha256"] == "b" * 64
    assert event["detail"]["previous"]["net_sales"] == "13.81"
    assert event["detail"]["new"]["net_sales"] == "17.14"

    [stored] = await _stored_days(client, _on(0), _on(0))
    assert [(line["name"], line["qty"], line["amount"]) for line in stored["lines"]] == [
        ("KARAK", "4.000", "14.00"),
        ("SAMOSA", "2.000", "4.00"),
    ]
    assert await db.pool.fetchval("select count(*) from sales_lines") == 2


# --- the arithmetic -------------------------------------------------------------


async def test_inclusive_and_exclusive_store_net_to_the_fil(api, db):
    client, _ = api
    response = await _post(
        client,
        [
            _item_day(_on(0), [_line(0, "KARAK", "105.00")], basis="inclusive"),
            _item_day(_on(1), [_line(0, "KARAK", "100.00")], basis="exclusive"),
        ],
    )
    assert response.status_code == 200, response.text
    inclusive, exclusive = response.json()["days"]
    assert inclusive["day"]["takings"] == "105.00" and inclusive["day"]["net_sales"] == "100.00"
    assert exclusive["day"]["takings"] == "100.00" and exclusive["day"]["net_sales"] == "100.00"
    assert inclusive["day"]["vat_rate"] == "0.05" and exclusive["day"]["vat_rate"] == "0.05"


async def test_the_day_equals_the_sum_of_its_lines_over_a_hundred_non_exact_divisions(api, db):
    """1.00 inclusive is 0.952..., stored 0.95; a hundred of them are 95.00,
    not 100 / 1.05 = 95.24. The day is the sum of what is stored (Codex 10)."""
    client, _ = api
    lines = [_line(i, f"ITEM {i}", "1.00") for i in range(100)]
    response = await _post(client, [_item_day(_on(0), lines)])
    assert response.status_code == 200, response.text
    day = response.json()["days"][0]["day"]
    assert day["takings"] == "100.00" and day["net_sales"] == "95.00"
    stored_sum = await db.pool.fetchval("select sum(net_amount) from sales_lines")
    assert stored_sum == Decimal("95.00")


async def test_a_negative_refund_row_reduces_the_day(api, db):
    client, _ = api
    response = await _post(
        client,
        [
            _item_day(
                _on(0),
                [_line(0, "KARAK", "21.00", qty="6"), _line(1, "REFUND KARAK", "-3.50", qty="-1")],
            )
        ],
    )
    assert response.status_code == 200, response.text
    day = response.json()["days"][0]["day"]
    assert day["takings"] == "17.50" and day["net_sales"] == "16.67"  # 20.00 - 3.33
    [stored] = await _stored_days(client, _on(0), _on(0))
    assert stored["lines"][1]["net_amount"] == "-3.33" and stored["lines"][1]["qty"] == "-1.000"


async def test_a_summary_day_stores_net_sales_and_zero_lines_and_a_closed_day_is_a_day(api, db):
    client, _ = api
    response = await _post(client, [_summary_day(_on(0), "4525.50"), _summary_day(_on(1), "0.00")])
    assert response.status_code == 200, response.text
    open_day, closed_day = (outcome["day"] for outcome in response.json()["days"])
    assert open_day["granularity"] == "summary" and open_day["line_count"] == 0
    assert open_day["takings"] == "4525.50" and open_day["net_sales"] == "4310.00"
    assert closed_day["takings"] == "0.00" and closed_day["net_sales"] == "0.00"
    stored = await _stored_days(client, _on(0), _on(1))
    assert [day["lines"] for day in stored] == [[], []]
    assert await db.pool.fetchval("select count(*) from sales_lines") == 0

    # The same summary again is unchanged; a different figure replaces it.
    again = await _post(client, [_summary_day(_on(0), "4525.50")])
    assert again.json()["days"][0]["outcome"] == "unchanged"
    moved = await _post(client, [_summary_day(_on(0), "4600.00")])
    assert moved.json()["days"][0]["outcome"] == "replaced"
    assert moved.json()["days"][0]["previous"]["net_sales"] == "4310.00"


# --- the refusal set --------------------------------------------------------------


async def test_two_rows_for_one_branch_day_in_a_summary_body_are_refused_with_the_sentence(api, db):
    client, _ = api
    response = await _post(client, [_summary_day(_on(0), "100.00"), _summary_day(_on(0), "200.00")])
    assert response.status_code == 422, response.text
    assert f"{_on(0)} appears twice for one branch" in response.json()["detail"]
    assert await db.pool.fetchval("select count(*) from sales_daily") == 0


async def test_a_body_mixing_item_and_summary_days_is_refused(api, db):
    client, _ = api
    response = await _post(
        client, [_item_day(_on(0), [_line(0, "KARAK", "1.00")]), _summary_day(_on(1), "5.00")]
    )
    assert response.status_code == 422, response.text
    assert "one shape throughout" in response.json()["detail"]


async def test_a_date_after_tomorrow_or_before_2020_is_refused_with_the_sentence(api, db):
    client, _ = api
    future = (TODAY + datetime.timedelta(days=2)).isoformat()
    response = await _post(client, [_summary_day(future, "10.00")])
    assert response.status_code == 422, response.text
    assert f"day 1 ({future}): {future} is after tomorrow" in response.json()["detail"]
    assert "swapped day and month" in response.json()["detail"]

    response = await _post(client, [_summary_day("2019-12-31", "10.00")])
    assert response.status_code == 422, response.text
    assert "before 2020" in response.json()["detail"]

    # Tomorrow itself is allowed: a till east of UTC closes before the server.
    tomorrow = (TODAY + datetime.timedelta(days=1)).isoformat()
    assert (await _post(client, [_summary_day(tomorrow, "10.00")])).status_code == 200


async def test_a_bad_row_is_refused_naming_the_day_and_the_position(api, db):
    client, _ = api
    response = await _post(
        client, [_item_day(_on(0), [_line(0, "KARAK", "1.00"), _line(1, "SAMOSA", "abc")])]
    )
    assert response.status_code == 422, response.text
    assert f"day 1 ({_on(0)}) row 1" in response.json()["detail"]

    response = await _post(client, [_item_day(_on(0), [_line(0, "KARAK", "1.005")])])
    assert response.status_code == 422 and "more than 2 decimals" in response.text

    response = await _post(client, [_item_day(_on(0), [_line(0, "   ", "1.00")])])
    assert response.status_code == 422 and "a line needs a name" in response.text

    response = await _post(client, [_item_day(_on(0), [])])
    assert response.status_code == 422 and "at least one line" in response.text

    response = await _post(client, [_summary_day(_on(0), "1.00", lines=[_line(0, "K", "1")])])
    assert response.status_code == 422 and "not lines" in response.text
    assert await db.pool.fetchval("select count(*) from sales_daily") == 0


async def test_a_31_day_body_answers_31_outcomes_and_a_32_day_body_is_422(api, db):
    client, _ = api
    start = TODAY - datetime.timedelta(days=40)
    days = [
        _summary_day((start + datetime.timedelta(days=i)).isoformat(), "10.00") for i in range(32)
    ]
    response = await _post(client, days)
    assert response.status_code == 422, response.text
    assert "32 days in one request: send at most 31" in response.json()["detail"]
    assert await db.pool.fetchval("select count(*) from sales_daily") == 0

    response = await _post(client, days[:31])
    assert response.status_code == 200, response.text
    assert [d["outcome"] for d in response.json()["days"]] == ["loaded"] * 31


# --- identity: till items -----------------------------------------------------------


async def test_a_till_name_seen_on_three_days_is_one_till_item(api, db):
    client, _ = api
    response = await _post(
        client,
        [
            _item_day(_on(0), [_line(0, "Karak Tea - Flask 1L", "35.00")]),
            _item_day(_on(1), [_line(0, "KARAK TEA FLASK 1L", "70.00")]),
            _item_day(_on(2), [_line(0, "karak tea flask 1l", "35.00")]),
        ],
    )
    assert response.status_code == 200, response.text
    items = await db.pool.fetch("select name, name_key, code from till_items")
    assert len(items) == 1 and items[0]["name_key"] == "karak tea flask 1l"
    stored = await _stored_days(client, _on(0), _on(2))
    assert len({day["lines"][0]["till_item_id"] for day in stored}) == 1
    # The printed name is kept on every line as the evidence.
    assert [day["lines"][0]["name"] for day in stored] == [
        "Karak Tea - Flask 1L",
        "KARAK TEA FLASK 1L",
        "karak tea flask 1l",
    ]


async def test_a_renamed_item_under_a_known_code_keeps_its_mapping_and_writes_renamed(api, db):
    client, _ = api
    assert (
        await _post(client, [_item_day(_on(0), [_line(0, "CHKN 65", "20.00", code="131")])])
    ).status_code == 200
    item = await db.create_menu_item(
        tenant_id=TENANT, name="Chicken 65 Dry", selling_price=Decimal("20.00"), actor="test"
    )
    await db.pool.execute(
        "update till_items set menu_item_id = $1 where tenant_id = $2", item["id"], TENANT
    )

    response = await _post(
        client, [_item_day(_on(1), [_line(0, "CHICKEN 65 DRY", "40.00", code="131")])]
    )
    assert response.status_code == 200, response.text
    [till_item] = await db.pool.fetch(
        "select name, name_key, code, menu_item_id::text as menu_item_id from till_items"
    )
    assert till_item["name"] == "CHICKEN 65 DRY" and till_item["code"] == "131"
    assert till_item["menu_item_id"] == item["id"]
    [event] = await _audit(db, "till_item.renamed")
    assert event["detail"] == {"code": "131", "previous_name": "CHKN 65", "name": "CHICKEN 65 DRY"}

    # Two codes, one printed name: two till items. Code is the identity.
    response = await _post(
        client, [_item_day(_on(2), [_line(0, "CHICKEN 65 DRY", "40.00", code="131b")])]
    )
    assert response.status_code == 200, response.text
    assert await db.pool.fetchval("select count(*) from till_items") == 2


# --- concurrency and idempotency -------------------------------------------------------


async def test_two_clients_posting_the_same_new_day_at_once_both_succeed(api, db):
    """The refresh-mid-run case: the branch-day is held under a transaction
    lock before the row exists, so the second poster reads `unchanged`
    rather than a unique violation, and one day and one audit row exist."""
    client, _ = api
    day = _item_day(_on(0), [_line(0, "KARAK", "10.50", qty="3")])
    first, second = await asyncio.gather(_post(client, [day]), _post(client, [day]))
    assert first.status_code == 200 and second.status_code == 200, (first.text, second.text)
    outcomes = sorted([first.json()["days"][0]["outcome"], second.json()["days"][0]["outcome"]])
    assert outcomes == ["loaded", "unchanged"]
    assert await db.pool.fetchval("select count(*) from sales_daily") == 1
    assert len(await _audit(db, "sales_day.loaded")) == 1


async def test_the_day_is_unique_per_branch_date_in_postgres(db):
    await db.pool.execute(
        """
        insert into sales_daily (tenant_id, branch_id, business_date, granularity, amount_basis,
                                 takings, net_sales, line_count, loaded_by)
        values ($1, $2, $3, 'summary', 'inclusive', 0, 0, 0, 'test')
        """,
        TENANT,
        BRANCH,
        DAY,
    )
    with pytest.raises(asyncpg.UniqueViolationError):
        await db.pool.execute(
            """
            insert into sales_daily (tenant_id, branch_id, business_date, granularity,
                                     amount_basis, takings, net_sales, line_count, loaded_by)
            values ($1, $2, $3, 'summary', 'inclusive', 0, 0, 0, 'test')
            """,
            TENANT,
            BRANCH,
            DAY,
        )
    for table in ("sales_layouts", "till_items", "sales_daily", "sales_lines", "branch_aliases"):
        assert await db.pool.fetchval(
            "select relrowsecurity from pg_class where relname = $1", table
        ), table


# --- tenancy ---------------------------------------------------------------------------


async def test_a_foreign_branch_is_404_from_the_api_and_refused_by_postgres(api, db):
    client, _ = api
    await _other_tenant(db)
    response = await _post(client, [_summary_day(_on(0), "10.00", branch=BRANCH_B)])
    assert response.status_code == 404, response.text
    assert await db.pool.fetchval("select count(*) from sales_daily") == 0

    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await db.pool.execute(
            """
            insert into sales_daily (tenant_id, branch_id, business_date, granularity,
                                     amount_basis, takings, net_sales, line_count, loaded_by)
            values ($1, $2, $3, 'summary', 'inclusive', 0, 0, 0, 'test')
            """,
            TENANT,
            BRANCH_B,
            DAY,
        )


async def test_a_foreign_menu_item_on_a_till_item_is_refused_by_postgres(api, db):
    client, _ = api
    await _other_tenant(db)
    assert (
        await _post(client, [_item_day(_on(0), [_line(0, "KARAK", "10.50")])])
    ).status_code == 200
    other = await db.create_menu_item(
        tenant_id=TENANT_B, name="Karak", selling_price=Decimal("5.00"), actor="test"
    )
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await db.pool.execute(
            "update till_items set menu_item_id = $1 where tenant_id = $2", other["id"], TENANT
        )


async def test_a_layout_of_another_tenant_does_not_exist_here(api, db):
    client, _ = api
    await _other_tenant(db)
    layout_id = await db.pool.fetchval(
        """
        insert into sales_layouts (tenant_id, name, header_key, columns, amount_basis, date_order)
        values ($1, 'Their till', 'amount|date', '{"date": "Date", "amount": "Amount"}',
                'inclusive', 'dmy')
        returning id::text
        """,
        TENANT_B,
    )
    response = await _post(client, [_summary_day(_on(0), "10.00", layout_id=layout_id)])
    assert response.status_code == 404, response.text
    assert "layout not found" in response.text


# --- layouts -------------------------------------------------------------------------------


async def test_the_layout_upsert_saves_once_updates_on_the_second_call_and_is_tenant_wide(api, db):
    client, _ = api
    body = {
        "name": "Main till",
        "columns": {
            "branch": "Outlet",
            "date": "Date",
            "item": "Item",
            "code": "PLU",
            "qty": "Qty",
            "amount": "Amount",
        },
        "amount_basis": "inclusive",
        "date_order": "dmy",
    }
    response = await client.post("/api/sales/layouts", json=body, headers=AUTH)
    assert response.status_code == 201, response.text
    layout = response.json()["layout"]
    assert layout["header_key"] == "amount|date|item|outlet|plu|qty"
    assert layout["columns"] == body["columns"] and layout["amount_basis"] == "inclusive"

    body["columns"]["code"] = "Code"
    body["amount_basis"] = "exclusive"
    response = await client.post("/api/sales/layouts", json=body, headers=AUTH)
    assert response.status_code == 200, response.text
    updated = response.json()["layout"]
    assert updated["id"] == layout["id"] and updated["amount_basis"] == "exclusive"
    assert updated["header_key"] == "amount|code|date|item|outlet|qty"
    assert await db.pool.fetchval("select count(*) from sales_layouts") == 1
    events = await _audit(db, "sales_layout.saved")
    assert [event["detail"]["created"] for event in events] == [True, False]

    # Another member of the same tenant reads it: the layout is the chain's.
    other_user = "00000000-0000-4000-8000-0000000000bb"
    await db.pool.execute(
        "insert into memberships (tenant_id, user_id) values ($1, $2)", TENANT, other_user
    )
    response = await client.get(
        "/api/sales/layouts", headers={"Authorization": f"Bearer {JWKS.mint(sub=other_user)}"}
    )
    assert response.status_code == 200, response.text
    assert [row["name"] for row in response.json()["layouts"]] == ["Main till"]

    # A day loaded under it carries its id.
    response = await _post(client, [_summary_day(_on(0), "10.00", layout_id=layout["id"])])
    assert response.json()["days"][0]["day"]["layout_id"] == layout["id"], response.text


async def test_a_layout_refuses_what_the_loader_could_not_apply(api, db):
    client, _ = api

    async def save(columns: dict) -> httpx.Response:
        return await client.post(
            "/api/sales/layouts",
            json={
                "name": "Till",
                "columns": columns,
                "amount_basis": "inclusive",
                "date_order": "dmy",
            },
            headers=AUTH,
        )

    response = await save({"date": "Date", "amount": "Amount", "till": "Till"})
    assert response.status_code == 422 and "'till' is not a column" in response.text
    response = await save({"date": "Date", "item": "Item"})
    assert response.status_code == 422 and "needs a amount column" in response.text
    response = await save({"date": "Date", "amount": "Date"})
    assert response.status_code == 422 and "same header name" in response.text
    response = await save({"date": "Date", "amount": "  "})
    assert response.status_code == 422 and "needs a header name" in response.text
    assert await db.pool.fetchval("select count(*) from sales_layouts") == 0


# --- branches and aliases ----------------------------------------------------------------


async def test_branches_lists_the_tenant_and_its_aliases_and_none_of_the_other_tenant(api, db):
    client, _ = api
    await _second_branch(db)
    await _other_tenant(db)
    response = await client.get("/api/branches", headers=AUTH)
    assert response.status_code == 200, response.text
    branches = response.json()["branches"]
    assert [b["name"] for b in branches] == ["Al Barsha Branch", "Al Nahda"]
    assert all(b["timezone"] == "Asia/Dubai" and b["aliases"] == [] for b in branches)
    assert BRANCH_B not in response.text

    response = await client.post(
        f"/api/branches/{BRANCH}/aliases", json={"alias": "  Barsha 1 "}, headers=AUTH
    )
    assert response.status_code == 201, response.text
    assert response.json()["alias"] == {
        "id": response.json()["alias"]["id"],
        "branch_id": BRANCH,
        "alias": "Barsha 1",
        "alias_key": "barsha 1",
    }
    [event] = await _audit(db, "branch_alias.saved")
    assert event["actor"] == TEST_ACTOR and event["detail"]["alias"] == "Barsha 1"

    # The same label again, differently cased: 200, the existing row, no write.
    response = await client.post(
        f"/api/branches/{BRANCH}/aliases", json={"alias": "BARSHA 1"}, headers=AUTH
    )
    assert response.status_code == 200, response.text
    assert response.json()["alias"]["alias"] == "Barsha 1"
    assert len(await _audit(db, "branch_alias.saved")) == 1

    # The same label for another branch: 409, naming who holds it.
    response = await client.post(
        f"/api/branches/{BRANCH_2}/aliases", json={"alias": "barsha 1"}, headers=AUTH
    )
    assert response.status_code == 409, response.text
    assert "already names Al Barsha Branch" in response.json()["detail"]

    response = await client.post(
        f"/api/branches/{BRANCH_B}/aliases", json={"alias": "Elsewhere"}, headers=AUTH
    )
    assert response.status_code == 404, response.text
    response = await client.post(
        f"/api/branches/{BRANCH}/aliases", json={"alias": " - "}, headers=AUTH
    )
    assert response.status_code == 422, response.text

    response = await client.get("/api/branches", headers=AUTH)
    assert response.json()["branches"][0]["aliases"] == ["Barsha 1"]


# --- the raw file ---------------------------------------------------------------------------


async def test_a_posted_file_is_stored_once_under_its_server_computed_hash(api, db):
    client, fake_storage = api
    data = b"Outlet,Date,PLU,Item,Qty,Amount\r\nAl Qusais,25/08/2026,52a,KARAK,14,490.00\r\n"
    response = await client.post(
        "/api/sales/files",
        files={"file": ("sales-week.csv", data, "text/csv")},
        headers=AUTH,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    sha256 = body["sha256"]
    assert len(sha256) == 64 and body["filename"] == "sales-week.csv"
    assert body["bytes"] == len(data)
    assert fake_storage.objects == {f"{TENANT}/sales/{sha256}.csv": data}

    response = await client.post(
        "/api/sales/files",
        files={"file": ("renamed.csv", data, "application/octet-stream")},
        headers=AUTH,
    )
    assert response.status_code == 200, response.text
    assert response.json()["sha256"] == sha256
    assert len(fake_storage.objects) == 1

    response = await client.post(
        "/api/sales/files", files={"file": ("empty.csv", b"", "text/csv")}, headers=AUTH
    )
    assert response.status_code == 422, response.text


# --- the pure rules --------------------------------------------------------------------


def test_the_header_key_is_order_and_case_insensitive():
    assert takings.header_key(["Outlet", "Date", "Item"]) == "date|item|outlet"
    assert takings.header_key(["item", "  OUTLET ", "Date"]) == "date|item|outlet"


def test_interior_gaps_are_the_missing_days_strictly_inside_the_range():
    d = datetime.date(2026, 8, 25)
    dates = [d, d + datetime.timedelta(days=1), d + datetime.timedelta(days=4)]
    assert takings.interior_gaps(dates) == [
        d + datetime.timedelta(days=2),
        d + datetime.timedelta(days=3),
    ]
    assert takings.interior_gaps([d]) == [] and takings.interior_gaps([]) == []


def test_net_amount_divides_once_and_rounds_half_up_to_a_fil():
    rate = Decimal("0.05")
    assert takings.net_amount(Decimal("105.00"), amount_basis="inclusive", vat_rate=rate) == (
        Decimal("100.00")
    )
    assert takings.net_amount(Decimal("1.00"), amount_basis="inclusive", vat_rate=rate) == (
        Decimal("0.95")
    )
    assert takings.net_amount(Decimal("0.01"), amount_basis="inclusive", vat_rate=rate) == (
        Decimal("0.01")
    )
    assert takings.net_amount(Decimal("100"), amount_basis="exclusive", vat_rate=rate) == (
        Decimal("100.00")
    )
    assert takings.net_amount(Decimal("105.00"), amount_basis="inclusive", vat_rate=None) == (
        Decimal("105.00")
    )


def test_the_day_key_ignores_order_and_the_till_item_key_prefers_the_code():
    lines_a = [
        ("KARAK", "52a", Decimal("14"), Decimal("490.00")),
        ("SAMOSA", None, None, Decimal("4")),
    ]
    lines_b = [
        ("samosa", None, None, Decimal("4.00")),
        ("Karak", "52a", Decimal("14.000"), Decimal("490")),
    ]
    assert takings.day_key("item", "inclusive", lines_a) == takings.day_key(
        "item", "inclusive", lines_b
    )
    assert takings.day_key("item", "inclusive", lines_a) != takings.day_key(
        "item", "exclusive", lines_a
    )
    assert takings.till_item_key("Karak Tea", "52a") == ("code", "52a")
    assert takings.till_item_key("Karak Tea", "  ") == ("name", "karak tea")
