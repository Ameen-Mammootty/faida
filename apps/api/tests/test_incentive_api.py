"""M13.2 (issue #8): the role shares door on `/api/incentive`, against real
Postgres.

The arithmetic and every refusal sentence are proven in `test_incentive.py`
over the pure module; here the proof is that the route stores what the owner
typed, writes the one audit row naming them, refuses the shares the module
refuses in the module's own words, and reads only its own tenant's row.
"""

import httpx
import pytest
from fastapi import FastAPI

from faida_api.incentive_api import router as incentive_router

from .conftest import AUTH, DEMO_TENANT_ID, TEST_ACTOR, requires_db, wire_auth
from .test_sales_load import TENANT_B, _audit, _other_tenant

pytestmark = requires_db

TENANT = DEMO_TENANT_ID

SHARES = {"manager_pct": "40", "supervisor_pct": "25", "sales_pct": "35"}


@pytest.fixture
def api(settings, db):
    app = FastAPI()
    app.include_router(incentive_router)
    app.state.settings = settings
    wire_auth(app)
    app.state.db = db
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_read_before_anything_is_set_says_no_shares(api):
    async with api as client:
        response = await client.get("/api/incentive", headers=AUTH)
    assert response.status_code == 200
    assert response.json() == {"shares": None}


async def test_put_stores_the_three_shares_and_reads_them_back(api):
    async with api as client:
        put = await client.put("/api/incentive/shares", json=SHARES, headers=AUTH)
        get = await client.get("/api/incentive", headers=AUTH)
    assert put.status_code == 200
    shares = put.json()["shares"]
    assert shares["manager_pct"] == "40.00"
    assert shares["supervisor_pct"] == "25.00"
    assert shares["sales_pct"] == "35.00"
    assert shares["updated_at"]
    assert get.json()["shares"] == shares


async def test_put_writes_one_audit_row_naming_the_actor(api, db):
    async with api as client:
        await client.put("/api/incentive/shares", json=SHARES, headers=AUTH)
    rows = await _audit(db, "incentive.role_shares_set")
    assert len(rows) == 1
    assert rows[0]["actor"] == TEST_ACTOR
    assert rows[0]["subject_id"] == TENANT
    assert rows[0]["detail"]["manager_pct"] == "40"


async def test_a_second_put_replaces_the_row_and_leaves_a_second_audit_row(api, db):
    async with api as client:
        await client.put("/api/incentive/shares", json=SHARES, headers=AUTH)
        again = await client.put(
            "/api/incentive/shares",
            json={"manager_pct": "50", "supervisor_pct": "20", "sales_pct": "30"},
            headers=AUTH,
        )
    assert again.json()["shares"]["manager_pct"] == "50.00"
    assert await db.pool.fetchval("select count(*) from role_shares") == 1
    assert len(await _audit(db, "incentive.role_shares_set")) == 2


@pytest.mark.parametrize(
    "body,fragment",
    [
        ({"manager_pct": "40", "supervisor_pct": "25", "sales_pct": "30"}, "sum to 95%"),
        ({"manager_pct": "-10", "supervisor_pct": "60", "sales_pct": "50"}, "cannot be negative"),
        (
            {"manager_pct": "40", "supervisor_pct": "25", "sales_pct": "x"},
            "is not a sales team share",
        ),
    ],
)
async def test_shares_that_do_not_add_up_are_refused_in_words(api, db, body, fragment):
    async with api as client:
        response = await client.put("/api/incentive/shares", json=body, headers=AUTH)
    assert response.status_code == 422
    assert fragment in response.json()["detail"]
    assert await db.pool.fetchval("select count(*) from role_shares") == 0
    assert await _audit(db, "incentive.role_shares_set") == []


async def test_three_shares_with_a_third_decimal_are_refused_in_words_not_by_sql(api, db):
    """They sum to exactly 100 as typed. Stored, each would round to two
    decimals and the row would hold 99.99, which the table's own check
    refuses - a 500 where the owner should have been told, in words, that a
    share is kept to two decimals."""
    async with api as client:
        response = await client.put(
            "/api/incentive/shares",
            json={"manager_pct": "33.334", "supervisor_pct": "33.333", "sales_pct": "33.333"},
            headers=AUTH,
        )
    assert response.status_code == 422
    assert "more decimals than a share is kept to" in response.json()["detail"]
    assert await db.pool.fetchval("select count(*) from role_shares") == 0


async def test_two_decimals_are_stored(api, db):
    async with api as client:
        response = await client.put(
            "/api/incentive/shares",
            json={"manager_pct": "33.34", "supervisor_pct": "33.33", "sales_pct": "33.33"},
            headers=AUTH,
        )
    assert response.status_code == 200
    assert response.json()["shares"]["manager_pct"] == "33.34"


async def test_a_missing_share_is_refused_and_nothing_is_written(api, db):
    async with api as client:
        response = await client.put(
            "/api/incentive/shares", json={"manager_pct": "40"}, headers=AUTH
        )
    assert response.status_code == 422
    assert "the supervisor share is missing" in response.json()["detail"]
    assert await db.pool.fetchval("select count(*) from role_shares") == 0


async def test_another_tenants_shares_are_not_this_tenants(api, db):
    await _other_tenant(db)
    await db.pool.execute(
        "insert into role_shares (tenant_id, manager_pct, supervisor_pct, sales_pct) "
        "values ($1, 10, 10, 80)",
        TENANT_B,
    )
    async with api as client:
        response = await client.get("/api/incentive", headers=AUTH)
    assert response.status_code == 200
    assert response.json() == {"shares": None}


async def test_a_signed_out_visit_is_refused(api):
    async with api as client:
        read = await client.get("/api/incentive")
        write = await client.put("/api/incentive/shares", json=SHARES)
    assert read.status_code == 401
    assert write.status_code == 401
