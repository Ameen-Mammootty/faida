"""M9 WP-92: the one dashboard read, through Postgres and the route
(Docs/M9_DECOMPOSITION.md row 92, C6 extended).

The pure rules are proven in `test_contribution.py` and `test_signals.py`;
here the proof is that the route reads the right rows and composes them once:
the league's ratio half is `GET /api/sales/branches`' answer field for field,
matched by `branch_id` and never by position; the chain reconciles to its
branches and to its chain-wide item rows; `total` never follows the branch
filter while the league, the items and the signals do; every money value is
a string; the three period refusals are `/sales`' own sentences; the papers
block is two counts from one read; and the read makes exactly the enumerated
set of queries whatever the menu's length or the branch count (D10, D16).

Three branches on the seeded tenant, the karak stage from `test_plates.py`,
sales loaded through the real door and till names mapped through the real
door, papers confirmed through the real path.
"""

import datetime
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI

from faida_api import ratio
from faida_api.api import router as api_router
from faida_api.dashboard import router as dashboard_router
from faida_api.menu import router as menu_router
from faida_api.sales import router as sales_router
from faida_api.storage import Storage

from .conftest import AUTH, DEMO_TENANT_ID, FakeStorage, requires_db, wire_auth
from .test_plates import _CountingPool, _karak, _menu_item, _recipe
from .test_sales_api import BRANCH, BRANCH_2, DAY, _branches, _iso, _on, _paper
from .test_sales_load import _item_day, _line

pytestmark = requires_db

TENANT = DEMO_TENANT_ID

#: The reads the route makes, in order, as `db.py` names them (D16, D20).
#: The maximum a read may make is the length of this list, derived rather
#: than typed: a new read must be added here, and one taken out must leave.
READS = [
    "membership_tenant_id",  # require_context, on every request (WP-70)
    "newest_sales_dates",
    "sales_months",
    "tenant_currency",
    "list_branches",
    "list_sales_days",
    "list_period_invoices",
    # _menu_context, as of the period's end: _pricing's three, then the recipes and the items.
    "tenant_currency",
    "list_mapped_pack_costs",
    "list_newest_purchases",
    "list_current_recipe_components",
    "list_menu_items",
    # _pricing again, today, for cost_per_portion_today.
    "tenant_currency",
    "list_mapped_pack_costs",
    "list_newest_purchases",
    "list_period_item_sales",
    "list_price_move_pairs",
    "list_invoices",
]
MAX_QUERIES = len(READS)

#: The league's inherited half, enumerated so a new field cannot quietly
#: escape the parity check against `/api/sales/branches`.
RATIO_FIELDS = (
    "branch_id",
    "branch_name",
    "net_sales",
    "takings",
    "purchases",
    "ratio_pct",
    "window",
    "days_loaded",
    "days_missing",
    "deliveries",
    "sales_through",
    "last_purchase_on",
)


@pytest.fixture
def api(settings, db):
    app = FastAPI()
    app.include_router(api_router)
    app.include_router(menu_router)
    app.include_router(sales_router)
    app.include_router(dashboard_router)
    app.state.settings = settings
    wire_auth(app)
    app.state.db = db
    app.state.storage = Storage(settings, transport=FakeStorage().transport())
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _week(api, branch: str, lines: list[tuple[str, str, str]], days: int = 7) -> None:
    """`days` item days on a branch, each with the given (name, qty, net)
    lines - the inclusive amount chosen so the net is exact."""
    body = []
    for offset in range(days):
        printed = [
            _line(
                position,
                name,
                str((Decimal(net) * Decimal("1.05")).quantize(Decimal("0.01"))),
                code=f"{position + 10}",
                qty=qty,
            )
            for position, (name, qty, net) in enumerate(lines)
        ]
        body.append(_item_day(_iso(offset), printed, branch=branch))
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


async def _stage(api, db) -> dict:
    """Three branches: the seeded one with a week of karak and chicken and two
    papers, a second with a week of karak and no papers, a third with nothing.
    The chicken's recipe eats most of its price, so it keeps far less than
    the karak and the chain average sits between them - a popular-low-margin
    signal fires on it and the item answer names it."""
    await _branches(db)
    scenario = await _karak(db, api)
    chicken = await _menu_item(api, "Chicken 65", "10.00")
    await _recipe(api, chicken, [{"ingredient_id": scenario["tea"], "qty": "400", "unit": "g"}])
    await _week(api, BRANCH, [("KARAK", "100", "952.38"), ("CHKN 65", "50", "476.19")])
    await _week(api, BRANCH_2, [("KARAK", "50", "476.19")])
    await _map(api, db, "KARAK", scenario["item_id"])
    await _map(api, db, "CHKN 65", chicken)
    first = await _paper(db, date=_on(1), total="5335.79", tax="254.09", invoice_no="GF-3318")
    second = await _paper(db, date=_on(4), total="1500.00", tax="71.43", invoice_no="GF-3320")
    return {**scenario, "chicken": chicken, "papers": [first, second]}


async def _read(api, **params) -> dict:
    query = {"from": _iso(0), "to": _iso(6), **params}
    response = await api.get("/api/dashboard", params=query, headers=AUTH)
    assert response.status_code == 200, response.text
    return response.json()


def _by_branch(rows: list[dict]) -> dict[str, dict]:
    return {row["branch_id"]: row for row in rows}


def _money(value: str | None) -> Decimal:
    return Decimal(value or "0")


# --- the three-branch end-to-end ------------------------------------------------


async def test_the_league_is_the_sales_screens_row_with_contribution_beside_it(api, db):
    await _stage(api, db)
    payload = await _read(api)
    sales = (
        await api.get("/api/sales/branches", params={"from": _iso(0), "to": _iso(6)}, headers=AUTH)
    ).json()

    # The inherited half, field for field, matched by id and never by position.
    league = _by_branch(payload["league"])
    for row in sales["rows"]:
        mine = league[row["branch_id"]]
        for field in RATIO_FIELDS:
            assert mine[field] == row[field], field
        assert mine["ratio_quality"] == row["quality"]
        assert mine["ratio_notes"] == row["notes"]
    assert set(league) == {row["branch_id"] for row in sales["rows"]}
    assert payload["total"]["net_sales"] == sales["total"]["net_sales"]
    assert payload["total"]["purchases"] == sales["total"]["purchases"]
    assert payload["total"]["ratio_pct"] == sales["total"]["ratio_pct"]
    assert payload["total"]["ratio_quality"] == sales["total"]["quality"]
    assert payload["period"]["months"] == sales["period"]["months"]
    assert payload["period"]["costed_at"] == _iso(6)

    # The league's own order: kept percentage, lowest first, no-figure rows last.
    kept = [row["contribution_pct"] for row in payload["league"]]
    rated = [Decimal(k) for k in kept if k is not None]
    assert rated == sorted(rated)
    assert kept[-1] is None  # the branch with nothing loaded
    assert payload["league"][-1]["contribution_quality"] == "unavailable"
    assert payload["league"][-1]["ratio_quality"] == "unavailable"

    # Two quality words that routinely differ: a branch with sales and no
    # papers has an incomplete ratio and a reliable contribution.
    second = league[BRANCH_2]
    assert second["ratio_quality"] == "incomplete"
    assert second["contribution_quality"] == "reliable_with_limitations"
    assert second["contribution_notes"] == ["covers 100% of this branch's sales value"]


async def test_the_chain_reconciles_to_its_branches_and_to_its_item_rows(api, db):
    await _stage(api, db)
    payload = await _read(api)
    branches = sum(_money(row["contribution"]) for row in payload["league"])
    items = sum(_money(row["contribution"]) for row in payload["items"]["all"])
    assert Decimal(payload["total"]["contribution"]) == branches == items
    assert branches > 0

    # The item rows: the chain's, one per menu item sold, ranked by the API.
    rows = payload["items"]["all"]
    assert [row["branch_id"] for row in rows] == [None, None]
    assert [row["menu_item_name"] for row in rows] == ["Karak Cup", "Chicken 65"]
    assert payload["items"]["count"] == 2
    assert payload["items"]["top"] == rows[:2]
    assert payload["items"]["bottom"] == []
    karak = rows[0]
    assert karak["qty_sold"] == "1050.000"  # 700 in one branch, 350 in the other
    assert karak["cost_per_portion"] == "0.752"
    assert karak["cost_per_portion_today"] is None  # no paper dated after the period
    assert karak["recipe_version"] == 1
    assert [t["name"] for t in karak["till_items"]] == ["KARAK"]
    assert "costed at the prices in force on" in " ".join(karak["notes"])

    # Every component names the invoice line behind its as-of price.
    assert len(karak["components"]) == 3
    for component in karak["components"]:
        assert component["invoice_id"] is not None
        assert component["line_position"] is not None
        assert component["cost_per_portion"] is not None
    assert payload["unmapped"] == {"names": 0, "value": "0.00"}
    assert payload["menu"] == {"items": 2, "costed": 2}


async def test_every_money_value_is_a_string_and_the_drill_ids_resolve(api, db):
    await _stage(api, db)
    payload = await _read(api)
    money_keys = {
        "net_sales",
        "takings",
        "purchases",
        "contribution",
        "net_item_sales",
        "cost",
        "cost_per_portion",
        "cost_per_portion_today",
        "avg_sold_at",
        "net_price",
        "money_at_stake",
        "value",
        "total",
    }

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in money_keys and value is not None and not isinstance(value, (dict, list)):
                    assert isinstance(value, str), key
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    for key in ("ratio_pct", "contribution_pct", "costed_share_pct"):
        assert isinstance(payload["total"][key], str), key

    karak = payload["items"]["all"][0]
    item = await api.get(f"/api/menu-items/{karak['menu_item_id']}", headers=AUTH)
    assert item.status_code == 200
    line = karak["components"][0]
    invoice = await api.get(f"/api/invoices/{line['invoice_id']}", headers=AUTH)
    assert invoice.status_code == 200
    assert invoice.json()["lines"][line["line_position"]] is not None


async def test_the_answer_names_the_top_row_and_the_dish_that_sells_and_does_not_earn(api, db):
    await _stage(api, db)
    payload = await _read(api)
    first = payload["league"][0]
    kept = Decimal(first["contribution_pct"]).quantize(Decimal("1"))
    assert payload["answer"]["branch"] == (
        f"Look at {first['branch_name'].replace(' Branch', '')} first: it keeps about "
        f"AED {kept} of every 100 it takes, the least of the two."
    )
    assert payload["answer"]["item"] == (
        "Chicken 65 sells more than any item that earns under the menu's average."
    )
    assert payload["answer"]["quality"] == "reliable_with_limitations"
    kinds = [s["kind"] for s in payload["signals"]]
    assert "popular_low_margin" in kinds
    popular = next(s for s in payload["signals"] if s["kind"] == "popular_low_margin")
    assert popular["menu_item_name"] == "Chicken 65"
    assert popular["branch_id"] is None
    assert popular["sentence"].startswith("Chicken 65 sold AED ")
    assert Decimal(popular["money_at_stake"]) > 0


# --- the branch filter -------------------------------------------------------------


async def test_the_branch_filter_narrows_everything_but_the_total(api, db):
    await _stage(api, db)
    chain = await _read(api)
    branch = await _read(api, branch_id=BRANCH_2)

    assert branch["scope"] == {"branch_id": BRANCH_2, "branch_name": "Al Nahda Branch"}
    assert chain["scope"] == {"branch_id": None, "branch_name": None}
    assert branch["total"] == chain["total"]
    assert [row["branch_id"] for row in branch["league"]] == [BRANCH_2]
    assert branch["league"][0] == _by_branch(chain["league"])[BRANCH_2]
    assert {row["branch_id"] for row in branch["items"]["all"]} == {BRANCH_2}
    assert [row["menu_item_name"] for row in branch["items"]["all"]] == ["Karak Cup"]
    assert branch["answer"]["branch"] == "Al Nahda keeps about AED 92 of every 100 it takes."
    assert branch["answer"]["item"] is None  # only karak sold there, at the chain's best
    # The signals are the branch's, against the chain's benchmark: Al Nahda
    # keeps more than the chain, so no gap, and nothing popular is low-margin.
    assert branch["signals"] == []
    assert branch["latest_day"] == chain["latest_day"]
    assert branch["period"] == chain["period"]

    seeded = await _read(api, branch_id=BRANCH)
    popular = [s for s in seeded["signals"] if s["kind"] == "popular_low_margin"]
    assert popular and popular[0]["branch_id"] == BRANCH
    assert seeded["answer"]["item"] == (
        "Chicken 65 sells more than any item at Al Barsha that earns under the menu's average."
    )


async def test_a_foreign_or_unknown_branch_is_absent(api, db):
    await _stage(api, db)
    for bad in ("b0000000-0000-0000-0000-000000000011", "not-a-branch"):
        response = await api.get(
            "/api/dashboard",
            params={"from": _iso(0), "to": _iso(6), "branch_id": bad},
            headers=AUTH,
        )
        assert response.status_code == 404, bad


# --- freshness, the newest day, the papers ---------------------------------------


async def test_latest_day_is_present_inside_the_period_and_null_outside_it(api, db):
    await _stage(api, db)
    inside = await _read(api)
    assert inside["period"]["sales_through"] == _iso(6)
    assert inside["freshness"]["sales_through"] == _iso(6)
    assert inside["freshness"]["sales_age_days"] == (datetime.date.today() - _on(6)).days
    assert inside["freshness"]["branches_without_sales"] == 1
    assert inside["freshness"]["sentence"].startswith("Sales loaded to ")
    assert inside["freshness"]["last_purchase_on"] == _iso(4)
    day = inside["latest_day"]
    assert day["date"] == _iso(6)
    assert {b["branch_id"] for b in day["branches"]} == {BRANCH, BRANCH_2}
    assert Decimal(day["net_sales"]) == sum(Decimal(b["net_sales"]) for b in day["branches"])
    assert Decimal(day["net_sales"]) == Decimal("952.38") + Decimal("476.19") + Decimal("476.19")

    earlier = await _read(api, **{"from": _iso(-10), "to": _iso(-4)})
    assert earlier["latest_day"] is None
    assert earlier["period"]["sales_through"] == _iso(6)


async def test_freshness_past_seven_days_is_estimated(api, db):
    await _branches(db)
    await _week(api, BRANCH, [("KARAK", "10", "95.24")], days=2)
    payload = await _read(api)
    age = (datetime.date.today() - _on(1)).days
    assert payload["freshness"]["sales_age_days"] == age
    assert payload["freshness"]["quality"] == (
        "estimated" if age > 7 else "reliable_with_limitations"
    )


async def test_thirty_papers_waiting_give_the_count_and_five_listed(api, db):
    await _stage(api, db)
    for n in range(30):
        await _paper(db, date=_on(2), total="100.00", status="needs_review", invoice_no=f"H-{n}")
    for n in range(4):
        await _paper(
            db,
            branch=BRANCH_2,
            date=_on(2),
            total="100.00",
            status="awaiting_confirm",
            invoice_no=f"A-{n}",
        )
    payload = await _read(api)
    assert payload["approvals"]["count"] == 30
    assert payload["approvals"]["awaiting_confirm"] == 4
    assert payload["approvals"]["duplicates"] == 0
    assert len(payload["approvals"]["invoices"]) == 5
    assert {p["status"] for p in payload["approvals"]["invoices"]} == {"needs_review"}
    assert payload["approvals"]["invoices"][0]["branch_name"] == "Al Barsha Branch"

    narrowed = await _read(api, branch_id=BRANCH_2)
    assert narrowed["approvals"]["count"] == 0
    assert narrowed["approvals"]["awaiting_confirm"] == 4
    assert narrowed["approvals"]["invoices"] == []


# --- the period -----------------------------------------------------------------


async def test_the_default_period_and_the_three_refusals_are_the_sales_screens(api, db):
    await _stage(api, db)
    default = (await api.get("/api/dashboard", headers=AUTH)).json()
    assert default["period"]["default"] is True
    assert default["period"]["to"] == _iso(6)
    assert default["period"]["days"] == 28

    lopsided = await api.get("/api/dashboard", params={"from": _iso(0)}, headers=AUTH)
    assert lopsided.status_code == 422
    assert lopsided.json()["detail"] == "send both 'from' and 'to', or neither"
    reversed_ = await api.get(
        "/api/dashboard", params={"from": _iso(6), "to": _iso(0)}, headers=AUTH
    )
    assert reversed_.status_code == 422
    assert reversed_.json()["detail"] == "'from' is after 'to'"
    long = await api.get("/api/dashboard", params={"from": _iso(0), "to": _iso(92)}, headers=AUTH)
    assert long.status_code == 422
    assert long.json()["detail"] == "93 days is longer than one read covers: at most 92"

    # The same three through /sales, the same sentences: one rule, two callers.
    for params, detail in (
        ({"from": _iso(0)}, "send both 'from' and 'to', or neither"),
        ({"from": _iso(6), "to": _iso(0)}, "'from' is after 'to'"),
        ({"from": _iso(0), "to": _iso(92)}, "93 days is longer than one read covers: at most 92"),
    ):
        response = await api.get("/api/sales/branches", params=params, headers=AUTH)
        assert response.status_code == 422
        assert response.json()["detail"] == detail


def test_resolve_period_is_the_rule_both_routers_share():
    newest = datetime.date(2026, 8, 31)
    period, default = ratio.resolve_period(newest, None, None)
    assert (period.start, period.end, default) == (datetime.date(2026, 8, 4), newest, True)
    period, default = ratio.resolve_period(None, None, None, today=datetime.date(2026, 9, 5))
    assert (period.end, default) == (datetime.date(2026, 9, 5), True)
    period, default = ratio.resolve_period(newest, DAY, newest)
    assert (period.start, period.end, default) == (DAY, newest, False)
    with pytest.raises(ratio.PeriodError, match="both 'from' and 'to'"):
        ratio.resolve_period(newest, DAY, None)
    with pytest.raises(ratio.PeriodError, match="after"):
        ratio.resolve_period(newest, newest, DAY)
    with pytest.raises(ratio.PeriodError, match="93 days"):
        ratio.resolve_period(newest, newest - datetime.timedelta(days=92), newest)


async def test_an_empty_tenant_answers_a_well_formed_empty_payload(api, db):
    await _branches(db)
    payload = (await api.get("/api/dashboard", headers=AUTH)).json()
    assert payload["period"]["sales_through"] is None
    assert payload["freshness"]["sentence"] is None
    assert payload["latest_day"] is None
    assert payload["answer"] == {
        "branch": None,
        "item": None,
        "quality": "unavailable",
        "notes": [],
    }
    assert {row["contribution_quality"] for row in payload["league"]} == {"unavailable"}
    assert payload["total"]["contribution"] is None
    assert payload["items"] == {"top": [], "bottom": [], "all": [], "count": 0}
    assert payload["signals"] == []
    assert payload["menu"] == {"items": 0, "costed": 0}


# --- the query count (D10, D16, D20) --------------------------------------------


async def _count(api, db) -> int:
    counting = _CountingPool(db.pool)
    db.pool = counting
    try:
        response = await api.get(
            "/api/dashboard", params={"from": _iso(0), "to": _iso(6)}, headers=AUTH
        )
        assert response.status_code == 200, response.text
        return counting.queries
    finally:
        db.pool = counting._inner


async def test_the_read_makes_the_enumerated_queries_and_no_more_as_the_menu_grows(api, db):
    """Exactly the reads listed at the top of this file - the maximum derived
    from the list, not typed - with two items and three branches, and still
    that many with forty-five items."""
    scenario = await _stage(api, db)
    small = await _count(api, db)
    assert small == MAX_QUERIES

    for n in range(43):
        item = await _menu_item(api, f"Dish {n:02d}", "12.00")
        await _recipe(api, item, [{"ingredient_id": scenario["tea"], "qty": "3", "unit": "g"}])
    assert len((await api.get("/api/menu-items", headers=AUTH)).json()["menu_items"]) == 45
    large = await _count(api, db)
    assert large == MAX_QUERIES == small
