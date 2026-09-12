"""The incentive doors on `/api/incentive`, against real Postgres: the role
shares (M13.2, issue #8) and the scheme month with its per-branch targets and
its clipped push weeks (M13.3, issue #9).

The arithmetic and every refusal sentence are proven in `test_incentive.py`
over the pure module; here the proof is that the route stores what the owner
typed, lays out the weeks the month spans, snapshots the shares in force,
writes the one audit row naming the actor, refuses in the module's own words,
and reads only its own tenant's rows.
"""

import datetime
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI

from faida_api.incentive_api import router as incentive_router

from .conftest import AUTH, DEMO_TENANT_ID, TEST_ACTOR, requires_db, wire_auth
from .test_plates import _CountingPool
from .test_sales_api import BRANCH, BRANCH_2, BRANCH_3, _branches
from .test_sales_load import TENANT_B, _audit, _other_tenant

pytestmark = requires_db

TENANT = DEMO_TENANT_ID

SHARES = {"manager_pct": "40", "supervisor_pct": "25", "sales_pct": "35"}

#: July 2026 starts on a Wednesday, so its first push week is five days.
JULY = "2026-07"
#: March 2027 is 31 days from a Monday: five push weeks, the last three days.
MARCH = "2027-03"

#: What the owner types into the three branches' boxes: a different figure
#: each, so a target stored under the wrong branch would show.
TARGETS = [
    {"branch_id": BRANCH, "net_sales_target": "60000", "above_target_pct": "10", "cap": None},
    {"branch_id": BRANCH_2, "net_sales_target": "40000", "above_target_pct": "10", "cap": "1500"},
    {"branch_id": BRANCH_3, "net_sales_target": "30000", "above_target_pct": "8", "cap": None},
]


async def _sales_day(db, branch: str, date: str, net: str) -> None:
    """One loaded till day, staged straight into the table: the loader's own
    door is proven in `test_sales_load.py`, and what is under test here is
    the advice figure the incentive read makes out of the days."""
    await db.pool.execute(
        """
        insert into sales_daily (tenant_id, branch_id, business_date, granularity, amount_basis,
                                 takings, net_sales, line_count, loaded_by)
        values ($1, $2, $3, 'item', 'inclusive', $4, $5, 1, 'test')
        """,
        TENANT,
        branch,
        datetime.date.fromisoformat(date),
        Decimal(net) * Decimal("1.05"),
        Decimal(net),
    )


async def _set_up(client, db, *, shares=SHARES) -> None:
    """Three branches and the shares in force: what the owner has before they
    can create a month at all."""
    await _branches(db)
    if shares is not None:
        response = await client.put("/api/incentive/shares", json=shares, headers=AUTH)
        assert response.status_code == 200, response.text


async def _create(client, month: str, targets=None):
    return await client.post(
        "/api/incentive/months",
        json={"month": month, "targets": TARGETS if targets is None else targets},
        headers=AUTH,
    )


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
    read = response.json()
    assert read["shares"] is None
    assert read["scheme_month"] is None
    assert read["months"] == []


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
    assert response.json()["shares"] is None


async def test_a_signed_out_visit_is_refused(api):
    async with api as client:
        read = await client.get("/api/incentive")
        shares = await client.put("/api/incentive/shares", json=SHARES)
        month = await client.post("/api/incentive/months", json={"month": JULY, "targets": []})
    assert read.status_code == 401
    assert shares.status_code == 401
    assert month.status_code == 401


# --- the scheme month (M13.3, issue #9) -------------------------------------------


async def test_creating_a_month_stores_its_targets_weeks_and_shares_snapshot(api, db):
    """One request carries everything the month is scored against, and Faida
    lays out the weeks it spans: July 2026 starts on a Wednesday, so the
    first week is five days and the last is five days, and no week waits for
    a day in June or August (D4, D5)."""
    async with api as client:
        await _set_up(client, db)
        response = await _create(client, JULY)
    assert response.status_code == 201, response.text
    read = response.json()
    assert read["month"] == "2026-07"
    assert read["month_words"] == "July 2026"

    month = read["scheme_month"]
    assert month["month"] == "2026-07"
    assert month["words"] == "July 2026"
    assert month["shares"] == {
        "manager_pct": "40.00",
        "supervisor_pct": "25.00",
        "sales_pct": "35.00",
    }
    assert [(week["start"], week["end"]) for week in month["weeks"]] == [
        ("2026-07-01", "2026-07-05"),
        ("2026-07-06", "2026-07-12"),
        ("2026-07-13", "2026-07-19"),
        ("2026-07-20", "2026-07-26"),
        ("2026-07-27", "2026-07-31"),
    ]
    assert month["weeks"][1]["words"] == "6-12 Jul"
    assert all(week["items"] == [] for week in month["weeks"])
    assert {
        target["branch_id"]: (
            target["net_sales_target"],
            target["above_target_pct"],
            target["cap"],
        )
        for target in month["targets"]
    } == {
        BRANCH: ("60000.00", "10.00", None),
        BRANCH_2: ("40000.00", "10.00", "1500.00"),
        BRANCH_3: ("30000.00", "8.00", None),
    }
    assert read["months"] == [{"id": month["id"], "month": "2026-07", "words": "July 2026"}]


async def test_creating_a_month_writes_one_audit_row_naming_the_actor(api, db):
    async with api as client:
        await _set_up(client, db)
        response = await _create(client, JULY)
    rows = await _audit(db, "incentive.scheme_month_created")
    assert len(rows) == 1
    assert rows[0]["actor"] == TEST_ACTOR
    assert rows[0]["subject_id"] == response.json()["scheme_month"]["id"]
    assert rows[0]["detail"]["month"] == "2026-07-01"
    assert rows[0]["detail"]["shares"]["manager_pct"] == "40.00"
    assert len(rows[0]["detail"]["weeks"]) == 5
    assert len(rows[0]["detail"]["targets"]) == 3
    assert await db.pool.fetchval("select count(*) from scheme_month_targets") == 3
    assert await db.pool.fetchval("select count(*) from push_weeks") == 5


async def test_a_31_day_month_starting_on_a_monday_gets_five_whole_and_part_weeks(api, db):
    async with api as client:
        await _set_up(client, db)
        response = await _create(client, MARCH)
    weeks = response.json()["scheme_month"]["weeks"]
    assert [(week["start"], week["end"]) for week in weeks] == [
        ("2027-03-01", "2027-03-07"),
        ("2027-03-08", "2027-03-14"),
        ("2027-03-15", "2027-03-21"),
        ("2027-03-22", "2027-03-28"),
        ("2027-03-29", "2027-03-31"),
    ]


async def test_a_second_month_is_refused_with_a_sentence_naming_the_month(api, db):
    """A month is frozen when it is created (D4), so a second create is not
    an edit by another name - it is refused, and the first month stands."""
    async with api as client:
        await _set_up(client, db)
        first = await _create(client, JULY)
        again = await _create(
            client,
            JULY,
            [{**target, "net_sales_target": "1"} for target in TARGETS],
        )
    assert first.status_code == 201
    assert again.status_code == 422
    assert "July 2026 already has a scheme month" in again.json()["detail"]
    assert await db.pool.fetchval("select count(*) from scheme_months") == 1
    assert await db.pool.fetchval(
        "select net_sales_target from scheme_month_targets where branch_id = $1", BRANCH
    ) == Decimal("60000.00")
    assert len(await _audit(db, "incentive.scheme_month_created")) == 1


def _but(branch: str, **fields) -> list[dict]:
    return [{**target, **fields} if target["branch_id"] == branch else target for target in TARGETS]


@pytest.mark.parametrize(
    "targets,fragment",
    [
        (_but(BRANCH, net_sales_target="-1"), "Al Barsha Branch: a net sales target cannot be"),
        (_but(BRANCH_2, above_target_pct="101"), "Al Nahda Branch: the percentage"),
        (_but(BRANCH_3, cap="-5"), "Rolla Branch: a cap cannot be negative"),
        (_but(BRANCH_2, net_sales_target=""), "Al Nahda Branch: a net sales target is needed"),
        (_but(BRANCH, above_target_pct=None), "Al Barsha Branch: the percentage"),
        (TARGETS[:2], "Rolla Branch has no target"),
        ([], "Al Barsha Branch, Al Nahda Branch and Rolla Branch have no target"),
        (TARGETS + [TARGETS[0]], "Al Barsha Branch was sent two targets"),
        (
            [
                {
                    "branch_id": "00000000-0000-0000-0000-0000000000ff",
                    "net_sales_target": "1",
                    "above_target_pct": "1",
                    "cap": None,
                }
            ],
            "not in this chain",
        ),
    ],
)
async def test_a_target_that_is_not_a_target_is_refused_by_the_branch_it_came_from(
    api, db, targets, fragment
):
    async with api as client:
        await _set_up(client, db)
        response = await _create(client, JULY, targets)
    assert response.status_code == 422, response.text
    assert fragment in response.json()["detail"]
    assert await db.pool.fetchval("select count(*) from scheme_months") == 0
    assert await db.pool.fetchval("select count(*) from push_weeks") == 0
    assert await _audit(db, "incentive.scheme_month_created") == []


async def test_a_figure_that_is_not_a_number_is_refused_as_the_wires_own_complaint(api, db):
    async with api as client:
        await _set_up(client, db)
        response = await _create(client, JULY, _but(BRANCH, net_sales_target="sixty thousand"))
    assert response.status_code == 422
    assert "is not a net sales target" in response.json()["detail"]


async def test_a_month_cannot_be_created_before_the_shares_are_set(api, db):
    """A month is created *with* the shares in force that day (D2, D4), so
    there is nothing to snapshot until they are set."""
    async with api as client:
        await _set_up(client, db, shares=None)
        response = await _create(client, JULY)
    assert response.status_code == 422
    assert "the role shares are not set" in response.json()["detail"]
    assert await db.pool.fetchval("select count(*) from scheme_months") == 0


async def test_a_month_key_that_is_not_a_month_is_refused_on_both_doors(api, db):
    async with api as client:
        await _set_up(client, db)
        created = await _create(client, "july")
        read = await client.get("/api/incentive?month=2026-13-01", headers=AUTH)
    assert created.status_code == 422
    assert "is not a month" in created.json()["detail"]
    assert read.status_code == 422
    assert "is not a month" in read.json()["detail"]


async def test_the_month_is_read_back_by_its_key_and_another_month_reads_empty(api, db):
    async with api as client:
        await _set_up(client, db)
        await _create(client, JULY)
        july = await client.get("/api/incentive?month=2026-07", headers=AUTH)
        august = await client.get("/api/incentive?month=2026-08", headers=AUTH)
    assert july.json()["scheme_month"]["month"] == "2026-07"
    assert august.json()["scheme_month"] is None
    # The picker still offers the month that exists, from the month that does not.
    assert august.json()["months"] == [
        {"id": july.json()["scheme_month"]["id"], "month": "2026-07", "words": "July 2026"}
    ]
    assert august.json()["month_words"] == "August 2026"


async def test_a_month_may_be_created_after_it_has_begun_and_its_started_weeks_are_frozen(api, db):
    """A late start still scores the whole calendar month (D4); the weeks
    that have already begun are frozen from the day they started (D5), and
    say so."""
    async with api as client:
        await _set_up(client, db)
        today = datetime.date.today()
        response = await _create(client, f"{today.year:04d}-{today.month:02d}")
    assert response.status_code == 201, response.text
    read = response.json()
    assert read["today"] == today.isoformat()
    weeks = read["scheme_month"]["weeks"]
    assert weeks[0]["start"] == today.replace(day=1).isoformat()
    assert weeks[0]["frozen"] is True
    assert "is frozen" in weeks[0]["frozen_words"]
    in_view = [week for week in weeks if week["start"] <= today.isoformat() <= week["end"]]
    assert len(in_view) == 1
    later = [week for week in weeks if week["start"] > today.isoformat()]
    assert all(week["frozen"] is False and week["frozen_words"] is None for week in later)


async def test_last_months_net_sales_sit_beside_the_target_box_and_a_branch_with_none_says_so(
    api, db
):
    """Advice, never the baseline (D3): the figure comes from the loaded
    sales days of the month before the one in view, and a branch with none
    says so in words rather than reading as a zero it did not earn."""
    async with api as client:
        await _set_up(client, db)
        await _sales_day(db, BRANCH, "2026-06-10", "1200.00")
        await _sales_day(db, BRANCH, "2026-06-11", "800.50")
        # July's own days are not last month's, and nor are May's.
        await _sales_day(db, BRANCH, "2026-07-02", "5000.00")
        await _sales_day(db, BRANCH, "2026-05-31", "9000.00")
        await _sales_day(db, BRANCH_2, "2026-06-11", "640.00")
        response = await client.get("/api/incentive?month=2026-07", headers=AUTH)
    branches = {branch["id"]: branch for branch in response.json()["branches"]}
    assert branches[BRANCH]["previous_month_net_sales"] == "2000.50"
    assert branches[BRANCH]["previous_month_words"] == "AED 2,001 last month"
    assert branches[BRANCH_2]["previous_month_net_sales"] == "640.00"
    assert branches[BRANCH_3]["previous_month_net_sales"] is None
    assert branches[BRANCH_3]["previous_month_words"] == "no sales loaded last month"
    assert [branch["name"] for branch in response.json()["branches"]] == [
        "Al Barsha Branch",
        "Al Nahda Branch",
        "Rolla Branch",
    ]


async def test_another_tenants_month_is_not_this_tenants_and_does_not_take_the_month(api, db):
    """The one month per tenant rule is per tenant: another chain's July is
    invisible here, and it does not stop this chain creating its own."""
    await _other_tenant(db)
    await db.pool.execute(
        "insert into role_shares (tenant_id, manager_pct, supervisor_pct, sales_pct) "
        "values ($1, 10, 10, 80)",
        TENANT_B,
    )
    await db.create_scheme_month(
        tenant_id=TENANT_B,
        month=datetime.date(2026, 7, 1),
        shares={
            "manager_pct": Decimal("10"),
            "supervisor_pct": Decimal("10"),
            "sales_pct": Decimal("80"),
        },
        targets=[],
        weeks=[(datetime.date(2026, 7, 1), datetime.date(2026, 7, 5))],
        actor="user:b",
    )
    async with api as client:
        await _set_up(client, db)
        before = await client.get("/api/incentive?month=2026-07", headers=AUTH)
        created = await _create(client, JULY)
    assert before.json()["scheme_month"] is None
    assert before.json()["months"] == []
    assert created.status_code == 201, created.text
    assert await db.pool.fetchval("select count(*) from scheme_months") == 2


#: The reads the incentive route makes, in order, as `db.py` names them. The
#: maximum is the length of this list, derived rather than typed: a new read
#: must be added here, and one taken out must leave.
READS = [
    "membership_tenant_id",  # require_context, on every request (WP-70)
    "tenant_currency",
    "list_incentive_branches",
    "list_scheme_months",
    "list_sales_days",  # last month's, for the advice figure
    "list_scheme_month_targets",
    "list_push_weeks",
    "get_role_shares",
]


async def test_the_read_makes_the_enumerated_queries_whatever_the_chains_size(api, db):
    """The dashboard's rule (M9): a screen's read is flat whatever the
    chain's size, so three branches and a five-week month cost what one
    branch does."""
    async with api as client:
        await _set_up(client, db)
        await _create(client, JULY)
        counting = _CountingPool(db.pool)
        db.pool = counting
        try:
            response = await client.get("/api/incentive?month=2026-07", headers=AUTH)
        finally:
            db.pool = counting._inner
    assert response.status_code == 200, response.text
    assert len(response.json()["scheme_month"]["weeks"]) == 5
    assert counting.queries == len(READS)
