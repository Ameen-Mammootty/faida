"""The period read (`period_read.read_period`, 2026-09-14): the one value
the dashboard, the sales screen and the usage printout start from.

Three facts are the door's own and pinned here: it makes exactly the reads
`period_read.READS` lists, however long the menu grows (D10, D16); it
refuses a period the rule refuses, with the rule's own sentence; and the
windows it holds are the ones the two screens draw. The consumers' suites
keep their own assertions on every figure; nothing here asserts a figure.
"""

import datetime

import pytest

from faida_api import period_read, ratio
from faida_api.period_read import READS, read_period

from .conftest import AUTH, DEMO_TENANT_ID, requires_db
from .test_dashboard import _read, _stage
from .test_dashboard import api as api  # noqa: F401 - the fixture, wired with every router
from .test_plates import _CountingPool, _menu_item, _recipe
from .test_sales_api import BRANCH, BRANCH_2, _on

pytestmark = requires_db

TENANT = DEMO_TENANT_ID
TODAY = datetime.datetime.now(datetime.UTC).date()


async def _count(db) -> tuple[int, period_read.PeriodRead]:
    counting = _CountingPool(db.pool)
    db.pool = counting
    try:
        read = await read_period(db, TENANT, today=TODAY, date_from=_on(0), date_to=_on(6))
        return counting.queries, read
    finally:
        db.pool = counting._inner


async def test_the_read_makes_exactly_the_enumerated_queries_as_the_menu_grows(api, db):
    """`READS` is the interface: the count is its length, not one more and
    not one fewer, with two items and three branches and still with
    forty-five items, so a read added or removed has to be named there."""
    scenario = await _stage(api, db)
    small, read = await _count(db)
    assert small == len(READS)
    assert len(read.branches) == 3 and set(read.ratio_rows) == set(read.names)

    for n in range(43):
        item = await _menu_item(api, f"Dish {n:02d}", "12.00")
        await _recipe(api, item, [{"ingredient_id": scenario["tea"], "qty": "3", "unit": "g"}])
    assert len((await api.get("/api/menu-items", headers=AUTH)).json()["menu_items"]) == 45
    large, read = await _count(db)
    assert large == len(READS) == small
    assert len(read.items) == 45 and len(read.menu.rows) == 45


async def test_a_period_the_rule_refuses_is_refused_at_the_door(api, db):
    """The rule is `ratio.resolve_period`, and the door raises its error
    unchanged so every route can answer the same 422 sentence."""
    await _stage(api, db)
    with pytest.raises(ratio.PeriodError, match="'from' is after 'to'"):
        await read_period(db, TENANT, today=TODAY, date_from=_on(6), date_to=_on(0))
    with pytest.raises(ratio.PeriodError, match="send both"):
        await read_period(db, TENANT, today=TODAY, date_from=_on(0), date_to=None)
    for path in ("/api/dashboard", "/api/sales/branches"):
        response = await api.get(path, params={"from": _on(6), "to": _on(0)}, headers=AUTH)
        assert response.status_code == 422
        assert response.json()["detail"] == "'from' is after 'to'"


async def test_the_two_screens_draw_the_windows_the_door_holds(api, db):
    """The league on the dashboard and the table on `/sales` are the door's
    `ratio_rows`, ranked: the same window, the same purchases, the same
    word, for every branch, read off the one value."""
    await _stage(api, db)
    _, read = await _count(db)
    dashboard = {row["branch_id"]: row for row in (await _read(api))["league"]}
    response = await api.get(
        "/api/sales/branches", params={"from": _on(0), "to": _on(6)}, headers=AUTH
    )
    assert response.status_code == 200, response.text
    sales = {row["branch_id"]: row for row in response.json()["rows"]}
    assert set(dashboard) == set(sales) == set(read.ratio_rows)
    for branch_id, row in read.ratio_rows.items():
        window = {
            "from": row.window.start.isoformat(),
            "to": row.window.end.isoformat(),
            "days": row.window.days,
        }
        assert dashboard[branch_id]["window"] == window == sales[branch_id]["window"]
        assert dashboard[branch_id]["purchases"] == sales[branch_id]["purchases"]
        assert dashboard[branch_id]["ratio_quality"] == sales[branch_id]["quality"]
    assert read.ratio_rows[BRANCH].purchases > read.ratio_rows[BRANCH_2].purchases == 0
