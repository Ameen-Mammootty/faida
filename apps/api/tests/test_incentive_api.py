"""The incentive doors on `/api/incentive`, against real Postgres: the role
shares (M13.2, issue #8), the scheme month with its per-branch targets and
its clipped push weeks (M13.3, issue #9), each week's push list (M13.4, issue
#10) and each branch's statement for the month (M13.5, issue #11).

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

from faida_api import incentive, incentive_api
from faida_api.incentive_api import router as incentive_router
from faida_api.menu import router as menu_router
from faida_api.sales import router as sales_router
from faida_api.storage import Storage

from .conftest import AUTH, DEMO_TENANT_ID, TEST_ACTOR, FakeStorage, requires_db, wire_auth
from .test_plates import _CountingPool, _karak, _menu_item
from .test_sales_api import BRANCH, BRANCH_2, BRANCH_3, _branches
from .test_sales_load import BRANCH_B, TENANT_B, _audit, _item_day, _line, _other_tenant

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
    # The menu's own door, for staging: a push list is built out of costed
    # dishes, and they are created the way the owner creates them. The sales
    # door for the same reason: a statement is read out of loaded days, and a
    # day staged by hand would prove a sum this product never makes.
    app.include_router(menu_router)
    app.include_router(sales_router)
    app.state.settings = settings
    wire_auth(app)
    app.state.db = db
    app.state.storage = Storage(settings, transport=FakeStorage().transport())
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
    # _menu, for the kept-per-plate figure and the picker: _menu_context's
    # five (its own currency read included) and the till mapping.
    "tenant_currency",
    "list_mapped_pack_costs",
    "list_newest_purchases",
    "list_current_recipe_components",
    "list_menu_items",
    "mapped_menu_item_ids",
    # Only when a month exists for the month in view.
    "list_scheme_month_targets",
    "list_push_weeks",
    "list_push_items",
    "list_push_item_targets",
    # The statements: the month's loaded days, its item-days and its
    # approvals, one read each for the whole chain (issue #11).
    "list_sales_days",
    "list_period_item_sales",
    "list_statement_approvals",
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


# --- the push list (M13.4, issue #10) ---------------------------------------------


def _key(day: datetime.date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


#: A month that has not begun: every one of its weeks can still be re-aimed.
#: Derived from today rather than typed, because the freeze rule is measured
#: against today and a typed month would start failing on a date.
NEXT_MONTH = _key(datetime.date.today().replace(day=1) + datetime.timedelta(days=32))
#: A month under way: its first week has started and is frozen.
THIS_MONTH = _key(datetime.date.today())
#: A month already over: every week of it has ended.
LAST_MONTH = _key(datetime.date.today().replace(day=1) - datetime.timedelta(days=1))

#: What the owner types into the three branches' portion boxes for one dish.
PORTIONS = {BRANCH: "1000", BRANCH_2: "750", BRANCH_3: "300.5"}


async def _till_name(db, name: str, menu_item_id: str) -> None:
    """A till name already mapped to a menu item. The mapping door itself is
    proven in `test_sales_api.py`; what is under test here is what the push
    list does with a dish that has one and a dish that has none."""
    await db.pool.execute(
        "insert into till_items (tenant_id, name, name_key, menu_item_id) values ($1, $2, $3, $4)",
        TENANT,
        name,
        name.lower(),
        menu_item_id,
    )


async def _menu(db, client) -> dict:
    """A small menu with one of each kind of dish a push list meets: the
    seeded karak, costed to the fil and mapped; a mandi with no recipe, so
    nothing is known about what its plate keeps; a cake no till name maps to;
    and a dish archived off the menu."""
    scenario = await _karak(db, client)
    karak = scenario["item_id"]
    mandi = await _menu_item(client, "Chicken Mandi", "28.00")
    cake = await _menu_item(client, "Honey Cake", "12.00")
    gone = await _menu_item(client, "Ramadan Harees", "18.00")
    for item_id, category in ((karak, "Tea Corner"), (mandi, "Rice"), (gone, "Rice")):
        await db.set_menu_item_category(
            item_id, tenant_id=TENANT, category=category, actor=TEST_ACTOR
        )
    await _till_name(db, "KARAK", karak)
    await _till_name(db, "MANDI", mandi)
    await _till_name(db, "HAREES", gone)
    await db.archive_menu_item(gone, tenant_id=TENANT, actor=TEST_ACTOR)
    return {"karak": karak, "mandi": mandi, "cake": cake, "gone": gone}


def _push(menu_item_id: str, rate: str = "0.25", targets=None) -> dict:
    return {
        "menu_item_id": menu_item_id,
        "rate_per_portion": rate,
        "targets": [
            {"branch_id": branch, "portion_target": target}
            for branch, target in (PORTIONS if targets is None else targets).items()
        ],
    }


async def _save(client, week_id: str, items: list[dict]):
    return await client.put(f"/api/incentive/weeks/{week_id}", json={"items": items}, headers=AUTH)


def _weeks(read: dict) -> list[dict]:
    return read["scheme_month"]["weeks"]


async def _month_with_menu(client, db, month: str = NEXT_MONTH) -> tuple[dict, dict]:
    """The owner's starting point for every push-list test: the shares set,
    the month created, the menu costed. Returns the menu's ids and the
    created month's read."""
    await _set_up(client, db)
    ids = await _menu(db, client)
    created = await _create(client, month)
    assert created.status_code == 201, created.text
    return ids, created.json()


async def test_a_list_on_a_coming_week_is_stored_with_its_rates_and_targets(api, db):
    """The owner filled next month's first week: the dishes, what a portion
    above target earns and how many portions each branch is held to, read
    back off the same request that saved them."""
    async with api as client:
        ids, read = await _month_with_menu(client, db)
        week = _weeks(read)[0]
        assert week["frozen"] is False
        saved = await _save(client, week["id"], [_push(ids["karak"]), _push(ids["mandi"], "1.50")])
    assert saved.status_code == 200, saved.text
    week = _weeks(saved.json())[0]
    assert [item["name"] for item in week["items"]] == ["Chicken Mandi", "Karak Cup"]
    karak = next(item for item in week["items"] if item["name"] == "Karak Cup")
    assert karak["rate_per_portion"] == "0.25"
    assert karak["hole"] is None
    assert karak["targets"] == [
        {"branch_id": BRANCH, "portion_target": "1000.000"},
        {"branch_id": BRANCH_2, "portion_target": "750.000"},
        {"branch_id": BRANCH_3, "portion_target": "300.500"},
    ]
    assert [week["items"] for week in _weeks(saved.json())[1:]] == [
        [] for _ in _weeks(saved.json())[1:]
    ]


async def test_the_list_is_grouped_by_the_menus_own_category_with_what_each_plate_keeps(api, db):
    """The list reads the way the menu reads (D6), and every rate box has
    what that plate keeps beside it (D7) - fils-precise off the menu's own
    costing, or the honest word for a dish nobody has costed."""
    async with api as client:
        ids, read = await _month_with_menu(client, db)
        saved = await _save(
            client, _weeks(read)[0]["id"], [_push(ids["karak"]), _push(ids["mandi"])]
        )
    assert saved.status_code == 200, saved.text
    week = _weeks(saved.json())[0]
    assert [group["category"] for group in week["categories"]] == ["Rice", "Tea Corner"]
    assert [group["guidance"] for group in week["categories"]] == [
        "one to three per category, as a guide",
        "one to three per category, as a guide",
    ]
    karak = week["categories"][1]["items"][0]
    assert karak["kept_per_plate"] == "8.772"
    assert karak["kept_words"] == "keeps AED 8.77 per plate"
    mandi = week["categories"][0]["items"][0]
    assert mandi["kept_per_plate"] is None
    assert mandi["kept_words"] == "not costed"


async def test_the_picker_offers_the_live_menu_and_leaves_the_archived_out(api, db):
    """What the owner picks from: every live dish grouped the menu's own way,
    each saying what it keeps and whether a till name maps to it. An archived
    dish is not offered - it could only ever be refused."""
    async with api as client:
        ids, _ = await _month_with_menu(client, db)
        read = (await client.get(f"/api/incentive?month={NEXT_MONTH}", headers=AUTH)).json()
    menu = {item["id"]: item for group in read["menu"] for item in group["items"]}
    assert ids["gone"] not in menu
    assert [group["category"] for group in read["menu"]] == ["Rice", "Tea Corner", "Other"]
    assert menu[ids["karak"]]["mapped"] is True
    assert menu[ids["karak"]]["kept_per_plate"] == "8.772"
    assert menu[ids["cake"]]["mapped"] is False
    assert menu[ids["cake"]]["category"] is None
    assert menu[ids["mandi"]]["kept_words"] == "not costed"


async def test_saving_again_replaces_the_week_and_leaves_a_second_audit_row(api, db):
    """Setting a list replaces the week's, never merges into it (D6): what
    the owner sees on the screen is what the week ends up with."""
    async with api as client:
        ids, read = await _month_with_menu(client, db)
        week = _weeks(read)[0]["id"]
        await _save(client, week, [_push(ids["karak"]), _push(ids["mandi"])])
        again = await _save(client, week, [_push(ids["mandi"], "2.00")])
    assert again.status_code == 200, again.text
    assert [item["name"] for item in _weeks(again.json())[0]["items"]] == ["Chicken Mandi"]
    assert _weeks(again.json())[0]["items"][0]["rate_per_portion"] == "2.00"
    rows = await _audit(db, "incentive.push_list_set")
    assert len(rows) == 2
    assert [row["actor"] for row in rows] == [TEST_ACTOR, TEST_ACTOR]
    assert [row["subject_id"] for row in rows] == [week, week]
    assert len(rows[1]["detail"]["items"]) == 1
    assert await db.pool.fetchval("select count(*) from push_items") == 1
    assert await db.pool.fetchval("select count(*) from push_item_targets") == 3


async def test_an_empty_list_clears_the_week(api, db):
    """A week the owner takes off the scheme is a decision, not a refusal
    (D5): the card still goes out with the month's net sales on it."""
    async with api as client:
        ids, read = await _month_with_menu(client, db)
        week = _weeks(read)[0]["id"]
        await _save(client, week, [_push(ids["karak"])])
        cleared = await _save(client, week, [])
    assert cleared.status_code == 200, cleared.text
    assert _weeks(cleared.json())[0]["items"] == []
    assert _weeks(cleared.json())[0]["categories"] == []
    assert await db.pool.fetchval("select count(*) from push_item_targets") == 0


async def test_a_week_under_way_and_a_week_already_over_are_both_refused_by_name(api, db):
    """Nobody finds the dish they pushed on Wednesday dropped on Thursday
    (D5), and no list is backdated onto a month the team has already been
    scored on."""
    async with api as client:
        ids, this_month = await _month_with_menu(client, db, THIS_MONTH)
        today = datetime.date.today().isoformat()
        running = next(w for w in _weeks(this_month) if w["start"] <= today <= w["end"])
        started = await _save(client, running["id"], [_push(ids["karak"])])
        last = await _create(client, LAST_MONTH)
        ended = await _save(client, _weeks(last.json())[0]["id"], [_push(ids["karak"])])
    assert started.status_code == 422, started.text
    assert started.json()["detail"] == f"the week of {running['words']} has started and is frozen"
    assert ended.status_code == 422, ended.text
    assert "has ended and is frozen" in ended.json()["detail"]
    assert await db.pool.fetchval("select count(*) from push_items") == 0


async def test_the_freeze_reads_the_chains_own_local_date_and_not_the_servers(api, db, monkeypatch):
    """The freeze is a rule about a date, and the date is the chain's own
    (D5). At eight in the evening on Sunday 12 July in London it is already
    Monday the 13th in a branch fourteen hours ahead, whose staff are pushing
    that week's dishes - so the same week, at the same instant, is open to a
    chain on UTC and frozen to a chain that straddles the date line.
    """
    moment = datetime.datetime(2026, 7, 12, 20, 0, tzinfo=datetime.UTC)
    monkeypatch.setattr(incentive_api, "_now", lambda: moment)
    async with api as client:
        ids, read = await _month_with_menu(client, db, "2026-07")
        await db.pool.execute("update branches set timezone = 'UTC' where tenant_id = $1", TENANT)
        read = (await client.get("/api/incentive?month=2026-07", headers=AUTH)).json()
        assert read["today"] == "2026-07-12"
        week = next(w for w in _weeks(read) if w["start"] == "2026-07-13")
        on_utc = await _save(client, week["id"], [_push(ids["karak"])])

        await db.pool.execute(
            "update branches set timezone = 'Pacific/Kiritimati' where id = $1", BRANCH_3
        )
        ahead = (await client.get("/api/incentive?month=2026-07", headers=AUTH)).json()
        refused = await _save(client, week["id"], [_push(ids["karak"])])
    assert on_utc.status_code == 200, on_utc.text
    assert ahead["today"] == "2026-07-13"
    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"] == "the week of 13-19 Jul has started and is frozen"


@pytest.mark.parametrize(
    ("items", "fragment"),
    [
        pytest.param(
            [{"menu_item_id": "{gone}", "rate_per_portion": "1.00", "targets": "{all}"}],
            "Ramadan Harees is archived from the menu and cannot be pushed",
            id="archived",
        ),
        pytest.param(
            [{"menu_item_id": "{cake}", "rate_per_portion": "1.00", "targets": "{all}"}],
            "Honey Cake has no till name mapped to it, so it could only ever score zero",
            id="unmapped",
        ),
        pytest.param(
            [{"menu_item_id": "{karak}", "rate_per_portion": None, "targets": "{all}"}],
            "Karak Cup has no rate per portion",
            id="no rate",
        ),
        pytest.param(
            [{"menu_item_id": "{karak}", "rate_per_portion": "-1", "targets": "{all}"}],
            "Karak Cup: a rate per portion cannot be negative",
            id="negative rate",
        ),
        pytest.param(
            [{"menu_item_id": "{karak}", "rate_per_portion": "0.255", "targets": "{all}"}],
            "Karak Cup: a rate per portion is kept to the fil",
            id="a third decimal on a rate",
        ),
        pytest.param(
            [{"menu_item_id": "{karak}", "rate_per_portion": "1.00", "targets": "{two}"}],
            "Karak Cup has no portion target for Rolla Branch",
            id="a branch with no target",
        ),
        pytest.param(
            [{"menu_item_id": "{karak}", "rate_per_portion": "1.00", "targets": "{blank}"}],
            "Karak Cup has no portion target for Rolla Branch",
            id="a target box left empty",
        ),
        pytest.param(
            [{"menu_item_id": "{karak}", "rate_per_portion": "1.00", "targets": "{negative}"}],
            "Karak Cup: a portion target cannot be negative",
            id="a negative target",
        ),
        pytest.param(
            [
                {"menu_item_id": "{karak}", "rate_per_portion": "1.00", "targets": "{all}"},
                {"menu_item_id": "{karak}", "rate_per_portion": "2.00", "targets": "{all}"},
            ],
            "Karak Cup is on the list twice: one row per dish",
            id="the same dish twice",
        ),
    ],
)
async def test_a_list_that_would_pay_the_team_on_nothing_is_refused_in_the_modules_own_words(
    api, db, items, fragment
):
    """Every refusal names the dish, and a missing target names the branch
    whose box it came from - the pure module's sentence, so the screen and
    the door say the same thing (D6, D7)."""
    async with api as client:
        ids, read = await _month_with_menu(client, db)
        shapes = {
            "{all}": PORTIONS,
            "{two}": {BRANCH: "10", BRANCH_2: "10"},
            "{blank}": {BRANCH: "10", BRANCH_2: "10", BRANCH_3: None},
            "{negative}": {BRANCH: "10", BRANCH_2: "10", BRANCH_3: "-5"},
        }
        body = [
            {
                "menu_item_id": ids[item["menu_item_id"].strip("{}")],
                "rate_per_portion": item["rate_per_portion"],
                "targets": [
                    {"branch_id": branch, "portion_target": target}
                    for branch, target in shapes[item["targets"]].items()
                ],
            }
            for item in items
        ]
        refused = await _save(client, _weeks(read)[0]["id"], body)
    assert refused.status_code == 422, refused.text
    assert fragment in refused.json()["detail"]
    assert await db.pool.fetchval("select count(*) from push_items") == 0


async def test_a_dish_unmapped_after_the_list_was_set_reads_as_a_named_hole(api, db):
    """A mapping removed after the fact is never read as a team that sold
    none (D7): the item stays on the list and says why it cannot be counted.
    """
    async with api as client:
        ids, read = await _month_with_menu(client, db)
        await _save(client, _weeks(read)[0]["id"], [_push(ids["karak"])])
        await db.pool.execute("delete from till_items where menu_item_id = $1", ids["karak"])
        after = (await client.get(f"/api/incentive?month={NEXT_MONTH}", headers=AUTH)).json()
    item = _weeks(after)[0]["items"][0]
    assert item["hole"] == "Karak Cup cannot be counted: no till name is mapped to it"
    assert item["rate_per_portion"] == "0.25"


async def test_another_tenants_week_is_not_this_tenants(api, db):
    """A week outside the tenant is not found, never forbidden (M7): the API
    does not confirm that another chain has a week at all."""
    await _other_tenant(db)
    await db.pool.execute(
        "insert into role_shares (tenant_id, manager_pct, supervisor_pct, sales_pct) "
        "values ($1, 10, 10, 80)",
        TENANT_B,
    )
    scheme_month_id = await db.create_scheme_month(
        tenant_id=TENANT_B,
        month=datetime.date(2027, 5, 1),
        shares={
            "manager_pct": Decimal("10"),
            "supervisor_pct": Decimal("10"),
            "sales_pct": Decimal("80"),
        },
        targets=[],
        weeks=[(datetime.date(2027, 5, 3), datetime.date(2027, 5, 9))],
        actor="user:b",
    )
    theirs = (await db.list_push_weeks(scheme_month_id, tenant_id=TENANT_B))[0]["id"]
    async with api as client:
        ids, _ = await _month_with_menu(client, db)
        refused = await _save(client, theirs, [_push(ids["karak"])])
    assert refused.status_code == 404, refused.text
    assert await db.pool.fetchval("select count(*) from push_items") == 0


async def test_a_dish_from_another_tenants_menu_is_not_on_this_menu(api, db):
    """The menu the list is checked against is this tenant's, so another
    chain's dish is refused before the composite keys ever see it."""
    await _other_tenant(db)
    theirs = str(
        await db.pool.fetchval(
            "insert into menu_items (tenant_id, name, selling_price) values ($1, $2, $3) "
            "returning id",
            TENANT_B,
            "Their Karak",
            Decimal("10.00"),
        )
    )
    async with api as client:
        _, read = await _month_with_menu(client, db)
        refused = await _save(client, _weeks(read)[0]["id"], [_push(theirs)])
    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"] == "a dish was sent that is not on this menu"


async def test_a_rate_that_is_not_a_number_is_refused_as_the_wires_own_complaint(api, db):
    """ "That is not a number" is the wire's complaint, not a product rule -
    the same place `menu.py` and `sales.py` word theirs."""
    async with api as client:
        ids, read = await _month_with_menu(client, db)
        refused = await _save(client, _weeks(read)[0]["id"], [_push(ids["karak"], "half a dirham")])
    assert refused.status_code == 422, refused.text
    assert "is not a rate per portion" in refused.json()["detail"]


# --- the statement (M13.5, issue #11) ---------------------------------------------
#
# What the owner reads under the month: what each branch's push weeks scored,
# what it sold, what the pool has earned so far, and how much of the month is
# loaded. Every figure is derived on the request out of the branch's own sales
# days and stored nowhere (C16), which is what these tests are really about:
# the portions on the screen are the till's own printed quantities, net of
# what it refunded, and the day count is the honest one.
#
# The arithmetic itself - the cap, the split's remainder, the hole, the banned
# words - is proven over the pure module in `test_incentive.py`, with no
# database in the room. What is proven here is the wiring: the right days, the
# right lines, the right branch.

#: Al Quoz's own days. July 2026 begins on a Wednesday, so the month's first
#: push week is 1 to 5 July and its second 6 to 12 - fixed dates, which is
#: what lets a test say which week a portion was sold in.
QUOZ_DAYS = [
    ("2026-07-01", [("KARAK", "400.00", "80")]),
    # The refund the till printed on the 2nd: 76 karak sold, 6 given back.
    ("2026-07-02", [("KARAK", "380.00", "76"), ("KARAK", "-30.00", "6")]),
    # The second week: mandi, 14 against a target of 10.
    ("2026-07-07", [("MANDI", "392.00", "14")]),
]


async def _push_item(
    db, week_id: str, menu_item_id: str, *, rate: str, targets: dict[str, str]
) -> str:
    """A dish on one week's list, staged straight into the tables.

    The list door is proven above and it refuses a week already under way -
    which every week with a day of sales in it is, by definition. A statement
    test that went through the door could therefore only ever score an empty
    list."""
    item_id = str(
        await db.pool.fetchval(
            "insert into push_items (tenant_id, push_week_id, menu_item_id, rate_per_portion) "
            "values ($1, $2, $3, $4) returning id",
            TENANT,
            week_id,
            menu_item_id,
            Decimal(rate),
        )
    )
    for branch_id, target in targets.items():
        await db.pool.execute(
            "insert into push_item_targets (tenant_id, push_item_id, branch_id, portion_target) "
            "values ($1, $2, $3, $4)",
            TENANT,
            item_id,
            branch_id,
            Decimal(target),
        )
    return item_id


def _day(date: str, lines: list[tuple[str, str, str]], *, branch: str = BRANCH) -> dict:
    """One branch-day as the till's own file says it: names, money and
    printed quantities, VAT out of the amounts so the day's net sales are the
    sum on the page."""
    return _item_day(
        date,
        [
            _line(position, name, amount, qty=qty)
            for position, (name, amount, qty) in enumerate(lines)
        ],
        branch=branch,
        basis="exclusive",
    )


async def _load(client, days: list[dict]) -> dict:
    """Sales through the branch-day door itself (M8), so what a statement is
    read from is what a real till export would have written."""
    response = await client.post("/api/sales/days", json={"days": days}, headers=AUTH)
    assert response.status_code == 200, response.text
    return response.json()


async def _july_with_sales(client, db) -> dict:
    """Where every statement test starts: July 2026 created after it was over,
    karak on its first push week and mandi on its second, and three branches
    that loaded what they loaded - Al Quoz three days, Karama one, and Deira
    nothing at all."""
    ids, read = await _month_with_menu(client, db, JULY)
    weeks = _weeks(read)
    await _push_item(
        db,
        weeks[0]["id"],
        ids["karak"],
        rate="0.25",
        targets={BRANCH: "100", BRANCH_2: "50", BRANCH_3: "10"},
    )
    await _push_item(
        db,
        weeks[1]["id"],
        ids["mandi"],
        rate="2.00",
        targets={BRANCH: "10", BRANCH_2: "5", BRANCH_3: "2"},
    )
    await _load(
        client,
        [_day(date, lines) for date, lines in QUOZ_DAYS]
        + [_day("2026-07-01", [("KARAK", "100.00", "20")], branch=BRANCH_2)],
    )
    return ids


def _statement(read: dict, branch_id: str) -> dict:
    return next(s for s in read["scheme_month"]["statements"] if s["branch_id"] == branch_id)


async def _july(client) -> dict:
    response = await client.get(f"/api/incentive?month={JULY}", headers=AUTH)
    assert response.status_code == 200, response.text
    return response.json()


async def test_each_branch_reads_its_own_portions_net_of_refunds_and_its_own_days(api, db):
    """Three branches, three different months on one screen: the branch that
    loaded three days, the branch that loaded one, and the branch that loaded
    none. A portion is what the till printed less what it gave back (D9)."""
    async with api as client:
        await _july_with_sales(client, db)
        read = await _july(client)

    quoz = _statement(read, BRANCH)
    assert quoz["branch_name"] == "Al Barsha Branch"
    assert quoz["status"] == "provisional"
    assert quoz["status_words"] == "provisional, 3 of 31 days loaded"
    assert quoz["newest_loaded"] == "2026-07-07"
    # 400 + 380 - 30 + 392: the days themselves, summed.
    assert quoz["figures"]["net_sales"] == "1142.00"
    assert quoz["figures"]["net_words"] == "AED 1,142 of AED 60,000"
    first, second = quoz["figures"]["weeks"][0], quoz["figures"]["weeks"][1]
    # 80 on the 1st, 76 less the 6 refunded on the 2nd: 150, not 156.
    assert [(item["name"], item["portions"], item["words"]) for item in first["items"]] == [
        ("Karak Cup", "150.000", "150 of 100 portions")
    ]
    assert first["earned"] == "12.50"
    assert [(item["name"], item["portions"], item["earned"]) for item in second["items"]] == [
        ("Chicken Mandi", "14.000", "8.00")
    ]

    karama = _statement(read, BRANCH_2)
    assert karama["status_words"] == "provisional, 1 of 31 days loaded"
    assert karama["figures"]["net_sales"] == "100.00"
    # Karama's own 20 karak, not Al Quoz's 150, and its own target of 50.
    assert [
        (item["portions"], item["portion_target"], item["earned"])
        for item in karama["figures"]["weeks"][0]["items"]
    ] == [("20.000", "50.000", "0.00")]
    assert karama["figures"]["weeks"][1]["items"][0]["portions"] == "0.000"


async def test_a_branch_with_no_day_loaded_has_no_pool_rather_than_a_pool_of_nothing(api, db):
    """A branch that loaded nothing has earned nothing *so far as anyone
    knows*, which is not the same as having earned zero - and a zero on the
    screen beside a team's name would be read as the second."""
    async with api as client:
        await _july_with_sales(client, db)
        read = await _july(client)

    deira = _statement(read, BRANCH_3)
    assert deira["status_words"] == "provisional, 0 of 31 days loaded"
    assert deira["newest_loaded"] is None
    assert deira["figures"]["pool"] is None
    assert deira["figures"]["pool_rounded"] is None
    assert deira["figures"]["split"] is None
    assert deira["figures"]["pool_words"] == "nothing loaded yet"
    assert deira["figures"]["net_sales"] == "0.00"


async def test_the_pool_is_a_string_to_the_fil_with_a_whole_dirham_headline(api, db):
    """Money is a string on the wire, never a JSON number, and the headline
    is the rounded one with the exact figure beneath it (the display rule,
    2026-09-05): 50 karak above target at 0.25 and 4 mandi at 2.00 is 20.50,
    which reads as 21 in the headline and 20.50 everywhere it is added up."""
    async with api as client:
        await _july_with_sales(client, db)
        read = await _july(client)

    figures = _statement(read, BRANCH)["figures"]
    assert figures["pool"] == "20.50"
    assert figures["pool_rounded"] == "21"
    # The sentence beside the figure is the rounded one, which is why the
    # headline has to round the same way: a truncated 21 beside "AED 21"
    # would read a dirham under what the team earned.
    assert figures["pool_words"] == "AED 21"
    # 40 / 25 / 35 of 20.50, the remainder on the sales team's share so the
    # three add to the pool exactly.
    split = figures["split"]
    assert (split["manager"], split["supervisor"], split["sales"]) == ("8.20", "5.13", "7.17")
    assert Decimal(split["manager"]) + Decimal(split["supervisor"]) + Decimal(split["sales"]) == (
        Decimal(figures["pool"])
    )
    assert all(
        isinstance(figures[field], str)
        for field in ("pool", "pool_rounded", "net_sales", "net_earned", "net_sales_target")
    )


async def test_a_dish_unmapped_after_its_week_was_scored_is_a_named_hole_on_the_statement(api, db):
    """The founder's rule (D10): a broken mapping is never read as nothing
    sold. The dish is named, its portions are blank, and it pays nothing -
    the same sentence the week's list carries."""
    async with api as client:
        ids, read = await _month_with_menu(client, db, JULY)
        await _push_item(
            db,
            _weeks(read)[0]["id"],
            ids["karak"],
            rate="0.25",
            targets={BRANCH: "100", BRANCH_2: "50", BRANCH_3: "10"},
        )
        await _load(client, [_day(date, lines) for date, lines in QUOZ_DAYS])
        before = _statement(await _july(client), BRANCH)
        till_item = await db.pool.fetchval(
            "select id::text from till_items where tenant_id = $1 and name_key = 'karak'", TENANT
        )
        await db.unmap_till_item(till_item, tenant_id=TENANT, actor=TEST_ACTOR)
        after = _statement(await _july(client), BRANCH)

    assert before["figures"]["weeks"][0]["items"][0]["portions"] == "150.000"
    item = after["figures"]["weeks"][0]["items"][0]
    assert item["portions"] is None
    assert item["earned"] == "0.00"
    assert item["hole"] == "Karak Cup cannot be counted: no till name is mapped to it"
    assert after["figures"]["pool"] == "0.00"
    assert item["hole"] in after["notes"][0]


async def test_another_tenants_days_are_never_this_tenants_portions(api, db):
    """The tenancy rule at the one place it could go wrong quietly: a
    statement is a sum over rows, and a sum that reached across tenants would
    look like a good month."""
    await _other_tenant(db)
    async with api as client:
        await _july_with_sales(client, db)
        await db.pool.execute(
            """
            insert into sales_daily (tenant_id, branch_id, business_date, granularity,
                                     amount_basis, takings, net_sales, line_count, loaded_by)
            select $1, id, '2026-07-03', 'item', 'exclusive', 9999, 9999, 1, 'test'
            from branches where tenant_id = $1 limit 1
            """,
            TENANT_B,
        )
        read = await _july(client)

    quoz = _statement(read, BRANCH)
    assert quoz["figures"]["net_sales"] == "1142.00"
    assert quoz["status_words"] == "provisional, 3 of 31 days loaded"


# --- the approval (M13.6, issue #12) ----------------------------------------------
#
# The only door to a final statement (D11, D12). What is proven here is the
# door itself: it refuses a month with a day missing, a blank reason and a
# second approval in the module's own words; it writes the approval and the
# audit row together or not at all; and a day re-uploaded afterwards is
# accepted by the sales-day door as before, with the approved figures standing
# and the note beside them. The wording of the refusals and the arithmetic of
# "the till now says otherwise" are proven over the pure module in
# `test_incentive.py`.


def _approve_url(read: dict, branch_id: str = BRANCH) -> str:
    return f"/api/incentive/months/{read['scheme_month']['id']}/branches/{branch_id}/approve"


async def _approve(client, read: dict, reason: str | None = "July paid on 2 August", **kw):
    body = {} if reason is None else {"reason": reason}
    return await client.post(_approve_url(read, **kw), json=body, headers=AUTH)


async def _rest_of_july(client) -> None:
    """The twenty-eight July days Al Quoz has not loaded yet, so the month is
    complete for that branch and that branch alone."""
    loaded = {date for date, _ in QUOZ_DAYS}
    await _load(
        client,
        [
            _day(f"2026-07-{day:02d}", [("KARAK", "100.00", "20")])
            for day in range(1, 32)
            if f"2026-07-{day:02d}" not in loaded
        ],
    )


async def test_approving_a_complete_month_writes_the_approval_and_the_audit_row_together(api, db):
    """The owner approved Al Quoz's July: the read now says final, the
    approval names the actor and the reason, the split by role is on the
    statement, and the audit row carries the figures as approved."""
    async with api as client:
        await _july_with_sales(client, db)
        await _rest_of_july(client)
        before = await _july(client)
        assert _statement(before, BRANCH)["status_words"] == "provisional, 31 of 31 days loaded"

        response = await _approve(client, before)
        assert response.status_code == 200, response.text
        read = response.json()

    quoz = _statement(read, BRANCH)
    assert quoz["status"] == "final"
    assert quoz["status_words"] == "final"
    assert quoz["approval"]["actor"] == TEST_ACTOR
    assert quoz["approval"]["reason"] == "July paid on 2 August"
    assert quoz["till_now_says_otherwise"] is False
    assert quoz["recomputed"] is None
    assert quoz["figures"] == _statement(before, BRANCH)["figures"]
    split = quoz["figures"]["split"]
    assert split["shares"] == {
        "manager_pct": "40.00",
        "supervisor_pct": "25.00",
        "sales_pct": "35.00",
    }
    assert Decimal(split["manager"]) + Decimal(split["supervisor"]) + Decimal(
        split["sales"]
    ) == Decimal(quoz["figures"]["pool"])
    # The other two branches are untouched: Karama is still one day in.
    assert _statement(read, BRANCH_2)["status"] == "provisional"

    rows = await _audit(db, "incentive.statement_approved")
    assert len(rows) == 1
    assert rows[0]["actor"] == TEST_ACTOR
    assert rows[0]["subject_id"] == read["scheme_month"]["id"]
    assert rows[0]["detail"]["branch_id"] == BRANCH
    assert rows[0]["detail"]["reason"] == "July paid on 2 August"
    assert rows[0]["detail"]["figures"] == quoz["figures"]
    stored = await db.pool.fetch("select branch_id::text as branch_id from statement_approvals")
    assert [row["branch_id"] for row in stored] == [BRANCH]


async def test_a_failed_audit_row_leaves_no_approval(api, db, monkeypatch):
    """One transaction: an approval with no note of who approved it is the
    state the audit table exists to make unreachable."""
    from faida_api import db as db_module

    async def refuse(*args, **kwargs):
        raise RuntimeError("audit table unavailable")

    async with api as client:
        await _july_with_sales(client, db)
        await _rest_of_july(client)
        read = await _july(client)
        monkeypatch.setattr(db_module, "_insert_audit_event", refuse)
        with pytest.raises(RuntimeError):
            await _approve(client, read)
        monkeypatch.undo()
        after = await _july(client)

    assert await db.pool.fetchval("select count(*) from statement_approvals") == 0
    assert _statement(after, BRANCH)["status"] == "provisional"


async def test_a_provisional_month_is_refused_with_the_day_count(api, db):
    async with api as client:
        await _july_with_sales(client, db)
        read = await _july(client)
        response = await _approve(client, read)
    assert response.status_code == 422, response.text
    assert response.json()["detail"] == (
        "the month is provisional, 3 of 31 days loaded: load every day before approving"
    )
    assert await db.pool.fetchval("select count(*) from statement_approvals") == 0
    assert await _audit(db, "incentive.statement_approved") == []


async def test_a_blank_reason_and_a_missing_one_are_both_refused(api, db):
    async with api as client:
        await _july_with_sales(client, db)
        await _rest_of_july(client)
        read = await _july(client)
        blank = await _approve(client, read, reason="   ")
        missing = await _approve(client, read, reason=None)
    assert blank.status_code == 422, blank.text
    assert blank.json()["detail"] == incentive.REASON_REQUIRED
    assert missing.status_code == 422, missing.text
    assert await db.pool.fetchval("select count(*) from statement_approvals") == 0


async def test_a_second_approval_is_refused_naming_the_first(api, db):
    async with api as client:
        await _july_with_sales(client, db)
        await _rest_of_july(client)
        read = await _july(client)
        first = await _approve(client, read)
        assert first.status_code == 200, first.text
        second = await _approve(client, read, reason="again, by mistake")
    assert second.status_code == 422, second.text
    assert second.json()["detail"] == (
        f"this statement is already final: approved by {TEST_ACTOR} on "
        f"{datetime.date.today().isoformat()}"
    )
    assert await db.pool.fetchval("select count(*) from statement_approvals") == 1
    assert len(await _audit(db, "incentive.statement_approved")) == 1


async def test_a_day_re_uploaded_after_approval_is_accepted_and_the_statement_says_so(api, db):
    """D12: the till's truth outranks the bonus paid on it. The sales-day door
    replaces the day exactly as before; the statement keeps the figures as
    approved, says the till now says otherwise, and puts the recomputed
    figures beside them."""
    async with api as client:
        await _july_with_sales(client, db)
        await _rest_of_july(client)
        read = await _july(client)
        approved = (await _approve(client, read)).json()
        paid = _statement(approved, BRANCH)["figures"]

        # The 7th re-uploaded: 9 mandi, not 14 - under the target of 10 now.
        result = await _load(client, [_day("2026-07-07", [("MANDI", "252.00", "9")])])
        assert [day["outcome"] for day in result["days"]] == ["replaced"]
        after = await _july(client)

    quoz = _statement(after, BRANCH)
    assert quoz["status"] == "final"
    assert quoz["status_words"] == "final; the till now says otherwise"
    assert quoz["till_now_says_otherwise"] is True
    assert quoz["figures"] == paid
    assert quoz["recomputed"]["net_sales"] == str(Decimal(paid["net_sales"]) - Decimal("140.00"))
    assert quoz["recomputed"]["weeks"][1]["items"][0]["portions"] == "9.000"
    assert Decimal(quoz["recomputed"]["pool"]) < Decimal(paid["pool"])
    assert quoz["notes"][-1].startswith("the till now says otherwise")


async def test_another_tenant_cannot_approve_the_month(api, db):
    """A month that is not this tenant's is not found, never forbidden (M7),
    and a branch of another chain is no statement of this month."""
    await _other_tenant(db)
    await db.pool.execute(
        "insert into role_shares (tenant_id, manager_pct, supervisor_pct, sales_pct) "
        "values ($1, 10, 10, 80)",
        TENANT_B,
    )
    theirs = await db.create_scheme_month(
        tenant_id=TENANT_B,
        month=datetime.date(2027, 5, 1),
        shares={
            "manager_pct": Decimal("10"),
            "supervisor_pct": Decimal("10"),
            "sales_pct": Decimal("80"),
        },
        targets=[],
        weeks=[(datetime.date(2027, 5, 3), datetime.date(2027, 5, 9))],
        actor="user:b",
    )
    async with api as client:
        await _july_with_sales(client, db)
        await _rest_of_july(client)
        read = await _july(client)
        their_month = await client.post(
            f"/api/incentive/months/{theirs}/branches/{BRANCH_B}/approve",
            json={"reason": "x"},
            headers=AUTH,
        )
        their_branch = await _approve(client, read, branch_id=BRANCH_B)
    assert their_month.status_code == 404, their_month.text
    assert their_branch.status_code == 404, their_branch.text
    assert await db.pool.fetchval("select count(*) from statement_approvals") == 0
