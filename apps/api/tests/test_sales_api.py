"""M8 WP-81: the ratio and coverage reads through the API against real
Postgres (Docs/M8_DECOMPOSITION.md row 81).

Three branches on the seeded tenant: one with a week of sales and papers,
one with sales and no papers, one with nothing. The pure rules are proven in
`test_ratio.py`; here the proof is that the routes read the right rows, the
drill's ids resolve on the invoice route, the default period ends on the
newest loaded day, and coverage reads a plate's quality from the same
function the menu screen does.
"""

import datetime
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI

from faida_api.api import router as api_router
from faida_api.menu import router as menu_router
from faida_api.sales import router as sales_router
from faida_api.storage import Storage

from .conftest import AUTH, DEMO_TENANT_ID, FakeStorage, requires_db, wire_auth
from .test_plates import _karak, _menu_item
from .test_sales_load import _item_day, _line

pytestmark = requires_db

TENANT = DEMO_TENANT_ID
BRANCH = "00000000-0000-0000-0000-000000000011"  # seed.sql's branch
BRANCH_2 = "00000000-0000-0000-0000-000000000012"
BRANCH_3 = "00000000-0000-0000-0000-000000000013"

TODAY = datetime.date.today()
DAY = TODAY - datetime.timedelta(days=20)


def _on(offset: int) -> datetime.date:
    return DAY + datetime.timedelta(days=offset)


def _iso(offset: int) -> str:
    return _on(offset).isoformat()


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


async def _branches(db) -> None:
    for branch_id, name in ((BRANCH_2, "Al Nahda Branch"), (BRANCH_3, "Rolla Branch")):
        await db.pool.execute(
            "insert into branches (id, tenant_id, name, timezone) "
            "values ($1, $2, $3, 'Asia/Dubai')",
            branch_id,
            TENANT,
            name,
        )


async def _week(api, branch: str, net_per_day: str = "1000.00") -> None:
    """Seven item days, inclusive amounts chosen so each day's net is exact."""
    gross = (Decimal(net_per_day) * Decimal("1.05")).quantize(Decimal("0.01"))
    days = [
        _item_day(_iso(offset), [_line(0, "KARAK", str(gross), code="52a", qty="1")], branch=branch)
        for offset in range(7)
    ]
    response = await api.post("/api/sales/days", json={"days": days}, headers=AUTH)
    assert response.status_code == 200, response.text


async def _paper(
    db,
    *,
    branch: str | None = BRANCH,
    date: datetime.date | None,
    total: str,
    tax: str | None = "0.00",
    status: str = "confirmed",
    currency: str = "AED",
    confirmed_at: datetime.datetime | None = None,
    created_at: datetime.datetime | None = None,
    provenance: dict | None = None,
    supplier_name: str = "Gulf Foods",
    invoice_no: str | None = None,
) -> str:
    document_id = await db.pool.fetchval(
        "insert into documents (tenant_id, source, status) values ($1, 'manual', 'extracted') "
        "returning id",
        TENANT,
    )
    if confirmed_at is None and status == "confirmed":
        confirmed_at = datetime.datetime.now(datetime.UTC)
    return await db.pool.fetchval(
        """
        insert into invoices (tenant_id, branch_id, document_id, status, total, tax, invoice_date,
                              currency, confirmed_at, created_at, supplier_name, invoice_no,
                              provenance)
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9, coalesce($10, now()), $11, $12, $13)
        returning id::text
        """,
        TENANT,
        branch,
        document_id,
        status,
        Decimal(total),
        None if tax is None else Decimal(tax),
        date,
        currency,
        confirmed_at,
        created_at,
        supplier_name,
        invoice_no,
        provenance or {},
    )


async def _branches_read(api, offset_from: int = 0, offset_to: int = 6, **params) -> dict:
    query = {"from": _iso(offset_from), "to": _iso(offset_to), **params}
    response = await api.get("/api/sales/branches", params=query, headers=AUTH)
    assert response.status_code == 200, response.text
    return response.json()


def _row(payload: dict, branch_id: str) -> dict:
    return next(row for row in payload["rows"] if row["branch_id"] == branch_id)


# --- the branch table ---------------------------------------------------------------


async def test_three_branches_answer_the_right_rows_and_the_drill_resolves(api, db):
    await _branches(db)
    await _week(api, BRANCH)
    await _week(api, BRANCH_2, "500.00")
    first = await _paper(db, date=_on(1), total="5335.79", tax="254.09", invoice_no="GF-3318")
    second = await _paper(db, date=_on(4), total="1500.00", tax="71.43", invoice_no="GF-3320")

    payload = await _branches_read(api)
    assert payload["period"] == {
        "from": _iso(0),
        "to": _iso(6),
        "days": 7,
        "default": False,
        "sales_through": _iso(6),
        "months": sorted({_iso(i)[:7] for i in range(7)}, reverse=True),
    }
    assert [row["branch_id"] for row in payload["rows"]] == [
        BRANCH,  # the only rated row
        BRANCH_2,  # sales, no papers: incomplete, unrated
        BRANCH_3,  # nothing: unavailable
    ]

    qusais = _row(payload, BRANCH)
    assert qusais["quality"] == "reliable_with_limitations"
    assert qusais["net_sales"] == "7000.00"
    assert qusais["takings"] == "7350.00"
    assert qusais["purchases"] == "6510.27"
    assert qusais["ratio_pct"] == "93.0"
    assert qusais["deliveries"] == 2
    assert qusais["days_loaded"] == 7 and qusais["days_missing"] == 0
    assert qusais["window"] == {"from": _iso(0), "to": _iso(6), "days": 7}
    assert qusais["sales_through"] == _iso(6)
    assert qusais["last_purchase_on"] == _iso(4)
    assert qusais["notes"] == ["2 deliveries in this window"]
    assert qusais["pending"] == [] and qusais["excluded"] == []
    day_one = qusais["days"][1]
    assert day_one["business_date"] == _iso(1)
    assert day_one["net_sales"] == "1000.00" and day_one["granularity"] == "item"
    assert day_one["purchases"] == "5081.70"
    assert day_one["invoices"] == [
        {
            "invoice_id": first,
            "supplier_name": "Gulf Foods",
            "invoice_no": "GF-3318",
            "purchased_on": _iso(1),
            "net_purchase": "5081.70",
            "total": "5335.79",
            "tax": "254.09",
            "quality": "reliable_with_limitations",
        }
    ]
    assert qusais["days"][4]["invoices"][0]["invoice_id"] == second

    nahda = _row(payload, BRANCH_2)
    assert nahda["quality"] == "incomplete"
    assert nahda["ratio_pct"] is None
    assert nahda["net_sales"] == "3500.00" and nahda["purchases"] == "0.00"
    assert nahda["notes"][0].startswith("no confirmed purchases ")

    rolla = _row(payload, BRANCH_3)
    assert rolla["quality"] == "unavailable"
    assert rolla["net_sales"] is None and rolla["ratio_pct"] is None
    assert rolla["sales_through"] is None

    assert payload["unassigned"] == {"count": 0, "purchases": "0.00", "invoices": []}
    total = payload["total"]
    assert total["net_sales"] == "10500.00"
    assert total["purchases"] == "6510.27"
    assert total["ratio_pct"] == "62.0"
    assert total["quality"] == "incomplete"

    # The drill: every invoice id on a day resolves on the invoice route.
    for invoice_id in (first, second):
        response = await api.get(f"/api/invoices/{invoice_id}", headers=AUTH)
        assert response.status_code == 200, response.text
        assert response.json()["id"] == invoice_id


async def test_the_default_period_is_28_days_ending_on_the_newest_sales_day(api, db):
    await _week(api, BRANCH)
    response = await api.get("/api/sales/branches", headers=AUTH)
    assert response.status_code == 200, response.text
    period = response.json()["period"]
    assert period["default"] is True
    assert period["to"] == _iso(6)
    assert period["from"] == _iso(6 - 27)
    assert period["days"] == 28
    assert period["sales_through"] == _iso(6)
    assert period["months"] == sorted({_iso(i)[:7] for i in range(7)}, reverse=True)
    coverage = await api.get("/api/sales/coverage", headers=AUTH)
    assert coverage.json()["period"] == period


async def test_with_no_sales_at_all_the_default_period_ends_today_and_rows_are_unavailable(api, db):
    await _branches(db)
    response = await api.get("/api/sales/branches", headers=AUTH)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["period"]["to"] == TODAY.isoformat()
    assert payload["period"]["days"] == 28
    assert payload["period"]["sales_through"] is None
    assert payload["period"]["months"] == []
    assert {row["quality"] for row in payload["rows"]} == {"unavailable"}
    assert payload["total"]["quality"] == "unavailable"


async def test_a_reversed_lopsided_or_over_long_range_is_refused(api, db):
    lopsided = await api.get("/api/sales/branches", params={"from": _iso(0)}, headers=AUTH)
    assert lopsided.status_code == 422
    reversed_ = await api.get(
        "/api/sales/branches", params={"from": _iso(6), "to": _iso(0)}, headers=AUTH
    )
    assert reversed_.status_code == 422
    long = await api.get(
        "/api/sales/branches", params={"from": _iso(0), "to": _iso(92)}, headers=AUTH
    )
    assert long.status_code == 422
    assert "92" in long.json()["detail"]
    quarter = await api.get(
        "/api/sales/coverage", params={"from": _iso(0), "to": _iso(91)}, headers=AUTH
    )
    assert quarter.status_code == 200


async def test_a_paper_with_no_branch_is_in_the_unassigned_group_and_in_the_total(api, db):
    await _week(api, BRANCH)
    counted = await _paper(db, date=_on(2), total="700.00")
    stray = await _paper(db, branch=None, date=_on(3), total="50.00", invoice_no="NB-1")
    payload = await _branches_read(api)
    assert _row(payload, BRANCH)["purchases"] == "700.00"
    assert all(
        invoice["invoice_id"] != stray
        for row in payload["rows"]
        for day in row["days"]
        for invoice in day["invoices"]
    )
    assert payload["unassigned"]["count"] == 1
    assert payload["unassigned"]["purchases"] == "50.00"
    assert payload["unassigned"]["invoices"][0]["invoice_id"] == stray
    assert payload["unassigned"]["invoices"][0]["invoice_no"] == "NB-1"
    assert payload["total"]["purchases"] == "750.00"
    assert "1 invoice on no branch, counted in the total" in payload["total"]["notes"]
    assert counted in [
        invoice["invoice_id"]
        for day in _row(payload, BRANCH)["days"]
        for invoice in day["invoices"]
    ]


async def test_pending_excluded_and_hand_typed_papers_make_the_row_estimated(api, db):
    await _week(api, BRANCH)
    await _paper(db, date=_on(1), total="700.00")
    undated = await _paper(
        db,
        date=None,
        total="300.00",
        status="awaiting_confirm",
        created_at=datetime.datetime.combine(_on(5), datetime.time(9), tzinfo=datetime.UTC),
    )
    held = await _paper(db, date=_on(2), total="999.00", status="needs_review")
    await _paper(db, date=_on(2), total="999.00", status="dismissed")
    usd = await _paper(db, date=_on(3), total="120.00", currency="USD", invoice_no="US-1")

    row = _row(await _branches_read(api), BRANCH)
    assert row["quality"] == "estimated"
    assert row["purchases"] == "700.00"
    assert row["ratio_pct"] == "10.0"
    assert "1 undated invoice awaiting confirm" in row["notes"]
    assert "1 invoice held for review" in row["notes"]
    assert "1 invoice in USD not counted" in row["notes"]
    assert [
        (p["invoice_id"], p["placed_on"], p["undated"], p["status"]) for p in row["pending"]
    ] == [
        (held, _iso(2), False, "needs_review"),
        (undated, _iso(5), True, "awaiting_confirm"),
    ]
    assert row["excluded"] == [
        {
            "invoice_id": usd,
            "supplier_name": "Gulf Foods",
            "invoice_no": "US-1",
            "currency": "USD",
            "total": "120.00",
        }
    ]

    # A total a person typed makes the paper - and the row - estimated (C9's read).
    typed = await _paper(
        db,
        date=_on(4),
        total="100.00",
        provenance={"total": {"origin": "manual", "actor": "user:x", "at": "2026-09-04T00:00:00Z"}},
    )
    row = _row(await _branches_read(api), BRANCH)
    assert "1 invoice with a total or VAT entered by hand" in row["notes"]
    figure = next(i for day in row["days"] for i in day["invoices"] if i["invoice_id"] == typed)
    assert figure["quality"] == "estimated"


async def test_a_paper_confirmed_today_with_a_printed_date_last_month_lands_on_that_day(api, db):
    await _week(api, BRANCH)
    await _paper(db, date=_on(3), total="400.00", confirmed_at=datetime.datetime.now(datetime.UTC))
    row = _row(await _branches_read(api), BRANCH)
    assert row["purchases"] == "400.00"
    assert row["days"][3]["purchases"] == "400.00"
    # The same paper is nobody's purchase in a period around today.
    later = await _branches_read(api, 14, 20)
    assert _row(later, BRANCH)["purchases"] == "0.00"


async def test_a_lagging_branch_counts_its_papers_to_its_own_newest_day(api, db):
    await _branches(db)
    await _week(api, BRANCH)
    three = [
        _item_day(_iso(offset), [_line(0, "KARAK", "105.00")], branch=BRANCH_2)
        for offset in range(3)
    ]
    assert (
        await api.post("/api/sales/days", json={"days": three}, headers=AUTH)
    ).status_code == 200
    await _paper(db, branch=BRANCH_2, date=_on(1), total="50.00")
    await _paper(db, branch=BRANCH_2, date=_on(5), total="9999.00")
    row = _row(await _branches_read(api), BRANCH_2)
    assert row["window"] == {"from": _iso(0), "to": _iso(2), "days": 3}
    assert row["purchases"] == "50.00"
    assert row["deliveries"] == 1
    assert row["quality"] == "reliable_with_limitations"
    assert row["sales_through"] == _iso(2)


# --- coverage -----------------------------------------------------------------------


async def test_coverage_on_a_staged_menu_reads_plates_from_the_menu_screens_function(api, db):
    karak = await _karak(db, api)  # a reliable plate: Karak Cup at 10.00
    paratha = await _menu_item(api, "Paratha", "4.00")  # no recipe: incomplete
    lines = [
        _line(0, "KARAK CUP", "63.00", code="52a", qty="6"),
        _line(1, "PARATHA", "4.20", code="60", qty="1"),
        _line(2, "CHKN 65 DRY", "21.00", code="131", qty="1"),
        _line(3, "DELIVERY CHARGE", "5.25"),
        _line(4, "KARAK CUP", "-10.50", code="52a", qty="-1"),
    ]
    response = await api.post(
        "/api/sales/days", json={"days": [_item_day(_iso(0), lines)]}, headers=AUTH
    )
    assert response.status_code == 200, response.text
    # Mapping is WP-82's door; here the rows are set by hand.
    await db.pool.execute(
        "update till_items set menu_item_id = $2 where tenant_id = $1 and code = '52a'",
        TENANT,
        karak["item_id"],
    )
    await db.pool.execute(
        "update till_items set menu_item_id = $2 where tenant_id = $1 and code = '60'",
        TENANT,
        paratha,
    )
    await db.pool.execute(
        "update till_items set excluded_at = now() "
        "where tenant_id = $1 and name = 'DELIVERY CHARGE'",
        TENANT,
    )

    response = await api.get(
        "/api/sales/coverage", params={"from": _iso(0), "to": _iso(6)}, headers=AUTH
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["sales_value"] == "84.00"  # 60 + 4 + 20; the charge is not menu sales
    assert payload["costed_value"] == "60.00"
    assert payload["costed_pct"] == "71.4"
    assert payload["estimated_points"] == "0.0"
    assert payload["uncosted"] == {"incomplete_plate": "4.00", "unmapped": "20.00"}
    assert payload["beside"] == {"refunds": "-10.00", "not_menu_items": "5.00"}
    assert [(q["name"], q["code"], q["value"], q["proposals"]) for q in payload["queue"]] == [
        ("CHKN 65 DRY", "131", "20.00", [])
    ]
    assert [
        (m["name"], m["menu_item_name"], m["plate_quality"], m["value"]) for m in payload["mapped"]
    ] == [
        ("KARAK CUP", "Karak Cup", "reliable_with_limitations", "60.00"),
        ("PARATHA", "Paratha", "incomplete", "4.00"),
    ]
    assert payload["mapped"][0]["menu_item_id"] == karak["item_id"]
    assert [(e["name"], e["value"]) for e in payload["excluded"]] == [("DELIVERY CHARGE", "5.00")]

    # The menu screen's own answer for the karak is the quality coverage read.
    detail = await api.get(f"/api/menu-items/{karak['item_id']}", headers=AUTH)
    assert detail.json()["plate"]["quality"] == "reliable_with_limitations"


async def test_coverage_with_no_sales_is_empty_not_wrong(api, db):
    response = await api.get(
        "/api/sales/coverage", params={"from": _iso(0), "to": _iso(6)}, headers=AUTH
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["sales_value"] == "0.00"
    assert payload["costed_pct"] is None
    assert payload["queue"] == [] and payload["mapped"] == [] and payload["excluded"] == []
