"""M8 WP-82: the till-name mapping door - propose, one keystroke, reverse gear
(Docs/M8_DECOMPOSITION.md §3 C11.7, row 82).

The loader mints a till item on first sight and never maps it; a person does,
one keystroke each, from proposals the matcher ranks. The pure cases pin the
ranking on the staged five-item menu and the real menu's spellings - the
1 L flask above the 2 L one, never a tie; a size word alone proposes nothing -
and the door cases prove, against real Postgres, that every door writes its
one audit row inside its own transaction and that another tenant's rows do
not exist here.
"""

import datetime
from decimal import Decimal

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from faida_api.matching import (
    MAX_MENU_ITEM_PROPOSALS,
    MENU_ITEM_PROPOSAL_THRESHOLD,
    propose_menu_items,
)
from faida_api.sales import router as sales_router
from faida_api.storage import Storage

from .conftest import (
    AUTH,
    DEMO_TENANT_ID,
    TEST_ACTOR,
    TEST_DATABASE_URL,
    FakeStorage,
    wire_auth,
)

TENANT = DEMO_TENANT_ID
BRANCH = "00000000-0000-0000-0000-000000000011"  # seed.sql's branch
TENANT_B = "b0000000-0000-0000-0000-000000000001"

DAY = (datetime.date.today() - datetime.timedelta(days=10)).isoformat()


def _menu(*names: str, archived: str | None = None) -> list[dict]:
    return [
        {
            "id": str(index),
            "name": name,
            "archived_at": datetime.datetime.now(datetime.UTC) if name == archived else None,
        }
        for index, name in enumerate(names)
    ]


STAGED = _menu(
    "Karak Tea (Cup)",
    "Karak Tea (Flask 1 L)",
    "Cardamom Chai (Flask 2 L)",
    "Nido Milk Tea",
    "Paratha",
)
DRINKS = _menu(
    "Karak Tea - Flask 1 L",
    "Karak Tea - Flask 2 L",
    "Cappuccino - Small 150 ml",
    "Cappuccino - Large 250 ml",
    "Boost - Large 250 ml",
    "Sahalab - Large 250 ml",
    "Hot Chocolate - Large 250 ml",
)
DISHES = _menu("Chicken 65 Dry", "Chicken Chilli (Dry/Gravy)", "Gobi Masala", "Prawns Masala")


# --- the proposer, pure ------------------------------------------------------------


def _names(proposals) -> list[str]:
    return [proposal.item["name"] for proposal in proposals]


def test_an_exact_name_is_proposed_first_with_a_full_score():
    proposals = propose_menu_items(STAGED, "PARATHA")
    assert _names(proposals)[0] == "Paratha"
    assert proposals[0].score == 1.0


def test_the_one_litre_flask_beats_the_two_litre_one_and_they_never_tie():
    staged = propose_menu_items(STAGED, "KARAK FLASK 1L")
    assert _names(staged)[0] == "Karak Tea (Flask 1 L)"
    assert "Cardamom Chai (Flask 2 L)" not in _names(staged)

    real = propose_menu_items(DRINKS, "KARAK TEA FLASK 1L")
    assert _names(real)[:2] == ["Karak Tea - Flask 1 L", "Karak Tea - Flask 2 L"]
    assert real[0].score > real[1].score

    other_way = propose_menu_items(DRINKS, "KARAK FLSK 2L")
    assert _names(other_way)[:2] == ["Karak Tea - Flask 2 L", "Karak Tea - Flask 1 L"]
    assert other_way[0].score > other_way[1].score


def test_till_abbreviations_find_their_dish():
    assert _names(propose_menu_items(DISHES, "CHKN 65 DRY"))[0] == "Chicken 65 Dry"
    assert _names(propose_menu_items(DISHES, "GOBI MSL")) == ["Gobi Masala"]
    assert _names(propose_menu_items(STAGED, "NIDO TEA")) == ["Nido Milk Tea"]
    assert _names(propose_menu_items(DRINKS, "CAPPUCCINO SML"))[0] == "Cappuccino - Small 150 ml"


def test_a_size_word_alone_proposes_nothing_whatever_it_scores():
    # "LARGE 250ML" scores 0.759 against every large drink - above the bar a
    # real abbreviation clears - so this is a rule, not a threshold.
    for size_only in ("LARGE 250ML", "SMALL 150ML", "FLASK 1 L", "1L", "LARGE", "SLICE"):
        assert propose_menu_items(DRINKS, size_only) == [], size_only
        assert propose_menu_items(STAGED, size_only) == [], size_only


def test_one_word_of_a_dish_stays_below_the_threshold():
    assert propose_menu_items(DISHES, "MASALA") == []
    assert propose_menu_items(DISHES, "DELIVERY CHARGE") == []
    assert MENU_ITEM_PROPOSAL_THRESHOLD > 0.706  # "MASALA" vs "Gobi Masala", measured


def test_an_archived_item_is_never_proposed():
    menu = _menu("Karak Tea (Cup)", "Paratha", archived="Paratha")
    assert propose_menu_items(menu, "PARATHA") == []


def test_at_most_three_proposals():
    flasks = _menu(*(f"Karak Tea - Flask {n} L" for n in (1, 2, 3, 4, 5, 6)))
    assert len(propose_menu_items(flasks, "KARAK TEA FLASK")) == MAX_MENU_ITEM_PROPOSALS == 3


# --- the doors, against Postgres -------------------------------------------------------


@pytest.fixture
def api(settings, db):
    """The doors need Postgres; the proposer cases above do not, so the skip
    sits on the fixture rather than on the module."""
    if TEST_DATABASE_URL is None:
        pytest.skip("TEST_DATABASE_URL not set")
    fake_storage = FakeStorage()
    app = FastAPI()
    app.include_router(sales_router)
    app.state.settings = settings
    wire_auth(app)
    app.state.db = db
    app.state.storage = Storage(settings, transport=fake_storage.transport())
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _menu_item(db, name: str, *, tenant_id: str = TENANT) -> str:
    item = await db.create_menu_item(
        tenant_id=tenant_id, name=name, selling_price=Decimal("5.00"), actor=TEST_ACTOR
    )
    return item["id"]


async def _load(client, names: list[str], *, date: str = DAY) -> dict[str, str]:
    """Load one item day with one line per name; answer {name: till_item_id}
    - the loader mints the till items and maps none of them."""
    response = await client.post(
        "/api/sales/days",
        json={
            "days": [
                {
                    "branch_id": BRANCH,
                    "business_date": date,
                    "granularity": "item",
                    "amount_basis": "inclusive",
                    "lines": [
                        {"position": index, "name": name, "qty": "1", "amount": "10.50"}
                        for index, name in enumerate(names)
                    ],
                }
            ]
        },
        headers=AUTH,
    )
    assert response.status_code == 200, response.text
    days = await client.get("/api/sales/days", params={"from": date, "to": date}, headers=AUTH)
    return {line["name"]: line["till_item_id"] for line in days.json()["days"][0]["lines"]}


async def _net_sales(client, date: str = DAY) -> str:
    days = await client.get("/api/sales/days", params={"from": date, "to": date}, headers=AUTH)
    return days.json()["days"][0]["net_sales"]


async def _audit(db, action: str) -> list[asyncpg.Record]:
    return await db.pool.fetch(
        "select actor, subject_id::text as subject_id, detail from audit_events "
        "where action = $1 order by created_at, id",
        action,
    )


async def _audit_count(db) -> int:
    return await db.pool.fetchval("select count(*) from audit_events")


async def test_an_exact_till_name_is_proposed_and_is_not_mapped_until_the_keystroke(api, db):
    paratha = await _menu_item(db, "Paratha")
    till = await _load(api, ["Paratha"])
    stored = await db.get_till_item(till["Paratha"], tenant_id=TENANT)
    assert stored["menu_item_id"] is None  # minted, never mapped by the loader

    proposals = propose_menu_items(await db.list_menu_items(tenant_id=TENANT), "Paratha")
    assert [proposal.item["id"] for proposal in proposals] == [paratha]

    before = await _audit_count(db)
    response = await api.post(
        f"/api/till-items/{till['Paratha']}/menu-item",
        json={"menu_item_id": paratha},
        headers=AUTH,
    )
    assert response.status_code == 200, response.text
    assert response.json()["till_item"] == {
        "id": till["Paratha"],
        "name": "Paratha",
        "code": None,
        "menu_item_id": paratha,
        "menu_item_name": "Paratha",
        "excluded_at": None,
    }
    assert await _audit_count(db) == before + 1
    (row,) = await _audit(db, "till_item.mapped")
    assert row["actor"] == TEST_ACTOR and row["subject_id"] == till["Paratha"]
    assert row["detail"]["menu_item_id"] == paratha
    assert row["detail"]["previous_menu_item_id"] is None


async def test_a_remap_carries_the_previous_menu_item(api, db):
    cup = await _menu_item(db, "Karak Tea (Cup)")
    flask = await _menu_item(db, "Karak Tea (Flask 1 L)")
    till = await _load(api, ["KARAK"])
    url = f"/api/till-items/{till['KARAK']}/menu-item"
    assert (await api.post(url, json={"menu_item_id": cup}, headers=AUTH)).status_code == 200
    response = await api.post(url, json={"menu_item_id": flask}, headers=AUTH)
    assert response.status_code == 200, response.text
    assert response.json()["till_item"]["menu_item_name"] == "Karak Tea (Flask 1 L)"
    first, second = await _audit(db, "till_item.mapped")
    assert first["detail"]["previous_menu_item_id"] is None
    assert second["detail"]["previous_menu_item_id"] == cup
    assert second["detail"]["menu_item_id"] == flask


async def test_unmap_is_the_reverse_gear_and_refuses_when_nothing_is_mapped(api, db):
    cup = await _menu_item(db, "Karak Tea (Cup)")
    till = await _load(api, ["KARAK"])
    url = f"/api/till-items/{till['KARAK']}/menu-item"
    assert (await api.post(url, json={"menu_item_id": cup}, headers=AUTH)).status_code == 200

    before = await _audit_count(db)
    response = await api.delete(url, headers=AUTH)
    assert response.status_code == 200, response.text
    assert response.json()["till_item"]["menu_item_id"] is None
    assert response.json()["till_item"]["menu_item_name"] is None
    assert await _audit_count(db) == before + 1
    (row,) = await _audit(db, "till_item.unmapped")
    assert row["detail"]["previous_menu_item_id"] == cup

    again = await api.delete(url, headers=AUTH)
    assert again.status_code == 409, again.text
    assert "not mapped" in again.json()["detail"]
    assert await _audit_count(db) == before + 1


async def test_exclude_keeps_the_money_in_net_sales_and_leaves_the_queue(api, db):
    till = await _load(api, ["DELIVERY CHARGE", "KARAK"])
    net_before = await _net_sales(api)
    before = await _audit_count(db)

    response = await api.post(f"/api/till-items/{till['DELIVERY CHARGE']}/exclude", headers=AUTH)
    assert response.status_code == 200, response.text
    assert response.json()["till_item"]["excluded_at"] is not None
    assert response.json()["till_item"]["menu_item_id"] is None
    assert await _net_sales(api) == net_before  # the till took the money
    assert await _audit_count(db) == before + 1
    (row,) = await _audit(db, "till_item.excluded")
    assert row["detail"]["name"] == "DELIVERY CHARGE"

    # A double click is not two audit rows.
    again = await api.post(f"/api/till-items/{till['DELIVERY CHARGE']}/exclude", headers=AUTH)
    assert again.status_code == 200
    assert await _audit_count(db) == before + 1


async def test_exclude_refuses_a_mapped_name_and_mapping_un_excludes(api, db):
    cup = await _menu_item(db, "Karak Tea (Cup)")
    till = await _load(api, ["KARAK"])
    map_url = f"/api/till-items/{till['KARAK']}/menu-item"
    exclude_url = f"/api/till-items/{till['KARAK']}/exclude"

    assert (await api.post(map_url, json={"menu_item_id": cup}, headers=AUTH)).status_code == 200
    refused = await api.post(exclude_url, headers=AUTH)
    assert refused.status_code == 409, refused.text
    assert "unmap it first" in refused.json()["detail"]

    assert (await api.delete(map_url, headers=AUTH)).status_code == 200
    assert (await api.post(exclude_url, headers=AUTH)).status_code == 200
    stored = await db.get_till_item(till["KARAK"], tenant_id=TENANT)
    assert stored["excluded_at"] is not None

    # The name turned out to be a dish after all: the keystroke that says so
    # brings it back into coverage.
    response = await api.post(map_url, json={"menu_item_id": cup}, headers=AUTH)
    assert response.status_code == 200, response.text
    assert response.json()["till_item"]["excluded_at"] is None
    rows = await _audit(db, "till_item.mapped")
    assert rows[-1]["detail"]["was_excluded"] is True


async def test_an_archived_menu_item_is_refused_with_a_sentence(api, db):
    old = await _menu_item(db, "Old Special")
    assert await db.archive_menu_item(old, tenant_id=TENANT, actor=TEST_ACTOR)
    till = await _load(api, ["OLD SPECIAL"])
    response = await api.post(
        f"/api/till-items/{till['OLD SPECIAL']}/menu-item",
        json={"menu_item_id": old},
        headers=AUTH,
    )
    assert response.status_code == 409, response.text
    assert "archived" in response.json()["detail"]
    assert await _audit(db, "till_item.mapped") == []


async def test_another_tenants_rows_do_not_exist_here_and_postgres_refuses_the_link(api, db):
    await db.pool.execute(
        "insert into tenants (id, name, currency) values ($1, 'Other Chain', 'AED')", TENANT_B
    )
    foreign_menu_item = await _menu_item(db, "Elsewhere Tea", tenant_id=TENANT_B)
    foreign_till_item = await db.pool.fetchval(
        "insert into till_items (tenant_id, name, name_key) values ($1, 'THEIRS', 'theirs') "
        "returning id::text",
        TENANT_B,
    )
    cup = await _menu_item(db, "Karak Tea (Cup)")
    till = await _load(api, ["KARAK"])

    # Their till item is not ours: every door says 404.
    for method, url, body in (
        ("POST", f"/api/till-items/{foreign_till_item}/menu-item", {"menu_item_id": cup}),
        ("DELETE", f"/api/till-items/{foreign_till_item}/menu-item", None),
        ("POST", f"/api/till-items/{foreign_till_item}/exclude", None),
    ):
        response = await api.request(method, url, json=body, headers=AUTH)
        assert response.status_code == 404, (method, url, response.text)

    # Their menu item on our till item: 404 from the API ...
    response = await api.post(
        f"/api/till-items/{till['KARAK']}/menu-item",
        json={"menu_item_id": foreign_menu_item},
        headers=AUTH,
    )
    assert response.status_code == 404, response.text
    # ... and refused by Postgres whatever the API missed (the 0019 composite key).
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await db.pool.execute(
            "update till_items set menu_item_id = $2 where id = $1",
            till["KARAK"],
            foreign_menu_item,
        )
    assert await _audit(db, "till_item.mapped") == []
    theirs = await db.pool.fetchval(
        "select count(*) from audit_events where tenant_id = $1 and action like 'till_item.%'",
        TENANT_B,
    )
    assert theirs == 0
