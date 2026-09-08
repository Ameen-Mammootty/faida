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
import json
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI

from faida_api import ratio
from faida_api.api import router as api_router
from faida_api.dashboard import PRICE_MOVES_LISTED, BranchNotFound, read_dashboard
from faida_api.dashboard import router as dashboard_router
from faida_api.menu import router as menu_router
from faida_api.sales import router as sales_router
from faida_api.storage import Storage

from .conftest import AUTH, DEMO_TENANT_ID, FakeStorage, requires_db, wire_auth
from .test_plates import (
    _catalog_item,
    _CountingPool,
    _delivery,
    _karak,
    _material,
    _menu_item,
    _recipe,
)
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


# --- supplier price moves (WP-99) ------------------------------------------

#: The karak stage buys every pack once on 6 Jul, well before any window a
#: test asks for, so a second delivery is what makes a move - and the older
#: baseline is what the sentence names.
BASELINE = "6 Jul"


def _short(offset: int) -> str:
    """A date the way every sentence in this product says it: "16 Aug"."""
    day = _on(offset)
    return f"{day.day} {day.strftime('%b')}"


async def _again(db, scenario: dict, pack: str, *, pack_size: str, price: str, offset: int) -> str:
    """The same pack delivered again at a new price on a day in the period:
    the read then sees a move on that material, same basis, real confirm."""
    return await _delivery(
        db,
        pack,
        supplier_id=scenario["supplier_id"],
        pack_size=pack_size,
        unit_price=Decimal(price),
        invoice_date=_iso(offset),
        raw_name=f"REDELIVERY {pack_size}",
    )


async def _spice(db, api, scenario: dict, name: str, *, base: str, moved: str, offset: int) -> str:
    """A material bought before the window and again inside it, so a sixth
    and seventh move exist to be counted. It reaches the panel only through a
    recipe - a moved material no dish uses belongs to M2's alert, not here."""
    pack = await _catalog_item(db, scenario["supplier_id"], f"{name.upper()} 1KG", "1kg")
    for price, on in ((base, None), (moved, _iso(offset))):
        await _delivery(
            db,
            pack,
            supplier_id=scenario["supplier_id"],
            pack_size="1kg",
            unit_price=Decimal(price),
            raw_name=f"{name.upper()} 1KG",
            **({} if on is None else {"invoice_date": on}),
        )
        if on is None:
            await _material(db, pack, name, "g")
    return await db.pool.fetchval(
        "select ingredient_id::text from supplier_items where id = $1", pack
    )


async def test_a_fall_of_five_percent_is_in_the_panel_with_its_money_and_not_a_signal(api, db):
    """A fall is a fact the owner acts on and it is not a spike: the panel
    carries it with the dirhams it saved, the signals stay quiet about it."""
    scenario = await _stage(api, db)
    await _again(db, scenario, scenario["milk_pack"], pack_size="1l", price="7.00", offset=0)
    payload = await _read(api)

    panel = payload["price_moves"]
    assert panel["count"] == 1
    [move] = panel["moves"]
    assert move["kind"] == "moved"
    assert move["direction"] == "down"
    assert move["ingredient_name"] == "Evaporated Milk"
    # 0.001 a millilitre off a 60 ml cup, on all 1,050 cups sold since.
    assert move["money_at_stake"] == "-63.00"
    assert move["moved_on"] == _iso(0)
    assert move["sentence"] == (
        f"Evaporated Milk is down AED 1.00 per litre since {_short(0)}, "
        f"against its last purchase on {BASELINE}."
    )
    assert move["plates"] == "Karak Cup earns AED 0.06 more a portion."
    assert move["evidence"] == (
        f"was AED 8.00 per litre · AED 63 saved on the 1,050 portions sold since {_short(0)}."
    )
    assert move["invoice_id"] and move["line_position"] == 0

    assert "price_spike" not in [s["kind"] for s in payload["signals"]]


async def test_a_fall_under_the_gate_is_in_neither_panel(api, db):
    """Tea 90.00 to 89.64 a 5 kg sack is four tenths of a percent. Without
    the gate a 45-item menu would count twenty moves and list five rows of
    nothing."""
    scenario = await _stage(api, db)
    await _again(db, scenario, scenario["tea_pack"], pack_size="5kg", price="89.64", offset=2)
    payload = await _read(api)
    assert payload["price_moves"] == {"count": 0, "moves": []}
    assert "price_spike" not in [s["kind"] for s in payload["signals"]]


async def test_a_basis_change_carries_no_money_and_sorts_behind_every_move(api, db):
    """A carton bought after the tin: no delta can honestly be taken across
    two pack sizes, so the row carries no number and never outranks a move
    that does."""
    scenario = await _stage(api, db)
    await _again(db, scenario, scenario["tea_pack"], pack_size="5kg", price="102.50", offset=1)
    carton = await _catalog_item(db, scenario["supplier_id"], "EVAP MILK 24x400ML", "24x400ml")
    await _delivery(
        db,
        carton,
        supplier_id=scenario["supplier_id"],
        pack_size="24x400ml",
        unit_price=Decimal("45.00"),
        invoice_date=_iso(2),
        raw_name="EVAP MILK 24x400ML",
    )
    await db.map_supplier_item(
        carton, tenant_id=TENANT, ingredient_id=scenario["milk"], actor="console"
    )

    panel = (await _read(api))["price_moves"]
    assert panel["count"] == 2
    assert [m["kind"] for m in panel["moves"]] == ["moved", "basis_changed"]
    basis = panel["moves"][1]
    assert basis["direction"] is None
    assert basis["money_at_stake"] is None
    assert basis["plates"] is None
    assert basis["moved_on"] == _iso(2)
    assert basis["sentence"] == (
        "Evaporated Milk is priced from a different pack now, so there is no before "
        "and after to show."
    )
    # The supplier's own full stop closes the sentence; a second would read as
    # a typo in the owner's supplier list (`signals._stop`).
    assert basis["evidence"] == (
        "Now EVAP MILK 24x400ML from Gulf Foods Trading L.L.C., "
        "was EVAP MILK 1L from Gulf Foods Trading L.L.C."
    )


async def test_the_same_rise_is_in_both_panels_with_the_same_money_at_every_scope(api, db):
    """The panel and the spike weigh one move once (`signals.weigh_move`), so
    a reader who sees the karak's tea in both places sees one figure - and
    the branch filter narrows both the same way."""
    scenario = await _stage(api, db)
    await _again(db, scenario, scenario["tea_pack"], pack_size="5kg", price="102.50", offset=1)

    # The move lands on the second of the seven days, so six days of karak
    # (900 cups at a fil each) and six of chicken (300 plates at a dirham)
    # are weighed - never the whole window, which would charge the owner for
    # plates sold at the old price.
    for params, expected in (({}, "309.00"), ({"branch_id": BRANCH}, "306.00")):
        payload = await _read(api, **params)
        [move] = payload["price_moves"]["moves"]
        spike = next(s for s in payload["signals"] if s["kind"] == "price_spike")
        assert move["direction"] == "up"
        assert move["money_at_stake"] == spike["money_at_stake"] == expected
        assert move["sentence"] == spike["sentence"]
        assert move["ingredient_id"] == spike["ingredient_id"]
        assert move["invoice_id"] == spike["invoice_id"]
        assert move["moved_on"] == spike["moved_on"] == _iso(1)
        # The plates clause names the worst first and brackets the rest.
        assert move["plates"] == (
            "Chicken 65 earns AED 1.00 less a portion; also Karak Cup (-0.01)."
        )


async def test_a_move_from_before_the_window_is_not_in_the_panel(api, db):
    """`db.list_price_move_pairs` has no lower date bound, so a material last
    bought in March would surface a March move in an August window. The panel
    is "each material's latest move, inside this window", and the signals -
    which are about the price in force - still carry it."""
    scenario = await _stage(api, db)
    await _again(db, scenario, scenario["tea_pack"], pack_size="5kg", price="102.50", offset=-3)
    payload = await _read(api)
    assert payload["price_moves"] == {"count": 0, "moves": []}
    assert "price_spike" in [s["kind"] for s in payload["signals"]]


async def test_six_qualifying_moves_give_the_count_and_five_listed(api, db):
    """Five rows and the whole number beside them, the papers block's rule:
    the count is the truth and the list a courtesy."""
    scenario = await _stage(api, db)
    cup_pack = await db.pool.fetchval(
        "select id::text from supplier_items where tenant_id = $1 and canonical_name = $2",
        TENANT,
        "PAPER CUP 50PCS",
    )
    await _again(db, scenario, scenario["tea_pack"], pack_size="5kg", price="102.50", offset=1)
    await _again(db, scenario, scenario["milk_pack"], pack_size="1l", price="7.00", offset=0)
    await _again(db, scenario, cup_pack, pack_size="50 pcs", price="12.00", offset=2)
    spices = [
        await _spice(db, api, scenario, name, base=base, moved=moved, offset=offset)
        for name, base, moved, offset in (
            ("Saffron", "500.00", "560.00", 3),
            ("Cardamom", "80.00", "96.00", 4),
            ("Ginger", "20.00", "24.00", 5),
        )
    ]
    dish = await _menu_item(api, "Masala Karak", "14.00")
    await _recipe(api, dish, [{"ingredient_id": i, "qty": "2", "unit": "g"} for i in spices])

    panel = (await _read(api))["price_moves"]
    assert panel["count"] == 6
    assert len(panel["moves"]) == 5
    # Largest money first whichever way it moved; the three spices nothing
    # was sold of carry nothing and break their tie on the per-plate figure.
    assert [m["ingredient_name"] for m in panel["moves"]] == [
        "CTC Black Tea",
        "Evaporated Milk",
        "Paper Cup",
        "Saffron",
        "Cardamom",
    ]
    money = [abs(Decimal(m["money_at_stake"])) for m in panel["moves"]]
    assert money == sorted(money, reverse=True)
    assert panel["moves"][-1]["money_at_stake"] == "0.00"
    assert panel["moves"][-1]["evidence"].endswith("· no sales of items using it since it landed.")


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


# --- the read as a function, and the two fields the brief needs (M10 WP-101) ----


async def test_the_route_is_the_function_and_nothing_else(api, db):
    """The daily brief is composed by a worker job, which cannot present a
    token and must not - a job's tenant comes from its payload (C2) - so the
    read is a function and the route a wrapper around it. What the screen
    gets and what the brief gets are one dict, chain scope and branch scope
    alike, and the two refusals are the function's own."""
    await _stage(api, db)
    today = datetime.datetime.now(datetime.UTC).date()
    for params in ({}, {"branch_id": BRANCH_2}):
        route = await _read(api, **params)
        direct = await read_dashboard(
            db, TENANT, today=today, date_from=_on(0), date_to=_on(6), **params
        )
        assert json.loads(json.dumps(direct)) == route

    with pytest.raises(ratio.PeriodError, match="both 'from' and 'to'"):
        await read_dashboard(db, TENANT, today=today, date_from=_on(0))
    for bad in ("b0000000-0000-0000-0000-000000000011", "not-a-branch"):
        with pytest.raises(BranchNotFound):
            await read_dashboard(db, TENANT, today=today, branch_id=bad)


async def test_the_chain_and_the_league_carry_the_cost_and_the_sales_it_covered(api, db):
    """C6 extended by two fields: the brief's materials line is the cost of
    the plates that were sold and its share of the sales those plates made,
    so both numbers travel beside the contribution. Each is the sum over the
    rows that produced numbers - never the branch's whole net sales, which
    would divide by money no plate was costed against (C12.7)."""
    await _stage(api, db)
    payload = await _read(api)

    costed = [row for row in payload["items"]["all"] if row["cost"] is not None]
    assert costed
    assert Decimal(payload["total"]["cost"]) == sum(Decimal(r["cost"]) for r in costed)
    assert Decimal(payload["total"]["costed_sales"]) == sum(
        Decimal(r["net_item_sales"]) for r in costed
    )
    # The kept figure is what the two make: the sales those plates made, less
    # what they cost. A reader can subtract the printed figures and land on it.
    assert Decimal(payload["total"]["contribution"]) == Decimal(
        payload["total"]["costed_sales"]
    ) - Decimal(payload["total"]["cost"])
    # Never more than the chain took, and on this stage exactly it, because
    # every till name here is mapped and every plate costed.
    assert Decimal(payload["total"]["costed_sales"]) <= Decimal(payload["total"]["net_sales"])
    assert payload["total"]["costed_share_pct"] == "100.0"

    for row in payload["league"]:
        branch = await _read(api, branch_id=row["branch_id"])
        rows = [r for r in branch["items"]["all"] if r["cost"] is not None]
        assert _money(row["cost"]) == sum((Decimal(r["cost"]) for r in rows), Decimal(0))
        assert Decimal(row["costed_sales"]) == sum(
            (Decimal(r["net_item_sales"]) for r in rows), Decimal(0)
        )
    # The branch with nothing loaded costed nothing and sold nothing.
    assert payload["league"][-1]["cost"] is None
    assert payload["league"][-1]["costed_sales"] == "0.00"


async def test_the_price_moves_limit_lets_a_caller_look_past_the_panels_five(api, db):
    """The panel lists five because five fit beside "what to look at"; the
    brief takes three rises out of the same ranking. The limit is a slice of
    one ranking in one set of words, never a second weighing, and `count`
    stays the whole number whatever is listed."""
    scenario = await _stage(api, db)
    cup_pack = await db.pool.fetchval(
        "select id::text from supplier_items where tenant_id = $1 and canonical_name = $2",
        TENANT,
        "PAPER CUP 50PCS",
    )
    await _again(db, scenario, scenario["tea_pack"], pack_size="5kg", price="102.50", offset=1)
    await _again(db, scenario, scenario["milk_pack"], pack_size="1l", price="7.00", offset=0)
    await _again(db, scenario, cup_pack, pack_size="50 pcs", price="12.00", offset=2)
    spices = [
        await _spice(db, api, scenario, name, base=base, moved=moved, offset=offset)
        for name, base, moved, offset in (
            ("Saffron", "500.00", "560.00", 3),
            ("Cardamom", "80.00", "96.00", 4),
            ("Ginger", "20.00", "24.00", 5),
        )
    ]
    dish = await _menu_item(api, "Masala Karak", "14.00")
    await _recipe(api, dish, [{"ingredient_id": i, "qty": "2", "unit": "g"} for i in spices])

    today = datetime.datetime.now(datetime.UTC).date()

    async def read(**kw) -> dict:
        return await read_dashboard(db, TENANT, today=today, date_from=_on(0), date_to=_on(6), **kw)

    default = await read()
    assert default["price_moves"]["count"] == 6
    assert len(default["price_moves"]["moves"]) == PRICE_MOVES_LISTED
    assert default["price_moves"] == (await _read(api))["price_moves"]

    wider = await read(price_moves_limit=10)
    assert wider["price_moves"]["count"] == 6
    assert len(wider["price_moves"]["moves"]) == 6
    assert wider["price_moves"]["moves"][:PRICE_MOVES_LISTED] == default["price_moves"]["moves"]
    assert {k: v for k, v in wider.items() if k != "price_moves"} == {
        k: v for k, v in default.items() if k != "price_moves"
    }

    three = await read(price_moves_limit=3)
    assert three["price_moves"]["count"] == 6
    assert three["price_moves"]["moves"] == default["price_moves"]["moves"][:3]


async def test_a_month_to_date_period_resolves_and_still_names_the_latest_day(api, db):
    """The brief's first read is the month to date - the first of the newest
    loaded day's month to that day (C15.1) - so the newest day is inside the
    period by construction and `latest_day` is there for the brief's second
    line. The chain's sales are its branches' clipped windows added up."""
    await _stage(api, db)
    newest = _on(6)
    first = newest.replace(day=1)
    payload = await read_dashboard(
        db,
        TENANT,
        today=datetime.datetime.now(datetime.UTC).date(),
        date_from=first,
        date_to=newest,
    )

    assert payload["period"]["from"] == first.isoformat()
    assert payload["period"]["to"] == newest.isoformat()
    assert payload["period"]["default"] is False
    assert payload["period"]["sales_through"] == newest.isoformat()
    assert payload["latest_day"]["date"] == newest.isoformat()
    assert payload["freshness"]["sentence"].startswith("Sales loaded to ")
    assert Decimal(payload["total"]["net_sales"]) == sum(
        _money(row["net_sales"]) for row in payload["league"]
    )
    assert Decimal(payload["total"]["net_sales"]) > 0
