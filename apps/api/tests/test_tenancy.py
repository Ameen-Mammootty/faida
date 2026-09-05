"""M7 WP-73: every read and write through the API is scoped by an auth context.

The rule under test: a row outside the caller's tenant does not exist for
them. Not forbidden - absent. So the API answers 404, never 403, and a
storage URL is never signed for a paper the caller cannot see. The auth
context's source is a verified Supabase access token plus the memberships
row (WP-70): tenant A is the test user's membership, and tenant B here is a
context handed to the app through the dependency override, which is what a
second person's token would resolve to.

The matrix is driven by the app's own route table: every route is either on
the public list below, on purpose, or in the matrix with a request that
succeeds for tenant A and is refused for tenant B and for no token. A new
route that is on neither list fails CI, which is the point.
"""

import datetime
import uuid
from decimal import Decimal

import asyncpg
import httpx
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute

from faida_api.api import router as api_router
from faida_api.auth import AuthContext, require_context
from faida_api.contracts import InvoiceStatus
from faida_api.dashboard import router as dashboard_router
from faida_api.main import app as production_app
from faida_api.menu import router as menu_router
from faida_api.sales import router as sales_router
from faida_api.storage import Storage
from faida_api.waitlist import router as waitlist_router
from faida_api.webhook import router as webhook_router

from .conftest import AUTH, DEMO_TENANT_ID, TEST_ACTOR, FakeStorage, requires_db, wire_auth

pytestmark = requires_db


TENANT_A = DEMO_TENANT_ID  # seed.sql's tenant: where the test user's membership is
BRANCH_A = "00000000-0000-0000-0000-000000000011"
TENANT_B = "b0000000-0000-0000-0000-000000000001"
BRANCH_B = "b0000000-0000-0000-0000-000000000011"
#: A business date the sales door accepts whatever day the suite runs.
SALES_DAY = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()

#: Routes that take no auth context, each here on purpose. Adding a route to
#: this set is a product decision, not a convenience: everything else in the
#: app must declare the auth dependency, and the test below fails otherwise.
PUBLIC_ROUTES = {
    ("GET", "/webhook"),  # Meta's verification handshake
    ("POST", "/webhook"),  # Meta's deliveries, authenticated by HMAC signature
    ("GET", "/health"),
    ("POST", "/api/waitlist"),  # the landing page's write-only signup
}

#: Every tenant-owned table, for the "B wrote nothing into A" check.
TENANT_TABLES = (
    "branches",
    "suppliers",
    "supplier_items",
    "supplier_item_prices",
    "documents",
    "invoices",
    "invoice_lines",
    "extraction_runs",
    "ingredients",
    "menu_items",
    "recipes",
    "recipe_components",
    "audit_events",
    "sales_layouts",
    "till_items",
    "sales_daily",
    "sales_lines",
    "branch_aliases",
)


def context_for(tenant_id: str) -> AuthContext:
    return AuthContext(user_id=None, tenant_id=tenant_id, actor="console")


def routes_of(app: FastAPI) -> dict[tuple[str, str], APIRoute]:
    """(method, path) for every real route - the framework's docs routes are
    not APIRoutes and are skipped."""
    table: dict[tuple[str, str], APIRoute] = {}

    def walk(routes) -> None:
        for route in routes:
            if isinstance(route, APIRoute):
                for method in route.methods:
                    table[(method, route.path)] = route
            elif hasattr(route, "original_router"):  # an included router, nested by FastAPI
                walk(route.original_router.routes)

    walk(app.routes)
    return table


def declares_auth(route: APIRoute) -> bool:
    """Whether the auth dependency sits anywhere in the route's dependency
    tree - router-level or handler-level."""
    seen = []

    def walk(dependant) -> None:
        seen.append(dependant.call)
        for sub in dependant.dependencies:
            walk(sub)

    walk(route.dependant)
    return require_context in seen


# --- the route table itself --------------------------------------------------


def test_every_route_is_public_on_purpose_or_declares_the_auth_dependency():
    table = routes_of(production_app)
    assert PUBLIC_ROUTES <= set(table), "a public route named here is not in the app"
    for key, route in table.items():
        if key in PUBLIC_ROUTES:
            assert not declares_auth(route), f"{key} is listed public but takes an auth context"
        else:
            assert declares_auth(route), f"{key} is not public and declares no auth context"


def test_the_matrix_covers_every_non_public_route():
    """A new route joins the matrix or the public list, on purpose."""
    expected = {key for key in routes_of(production_app) if key not in PUBLIC_ROUTES}
    covered = {(case["method"], case["path"]) for case in MATRIX}
    assert covered == expected, {
        "missing from the matrix": sorted(expected - covered),
        "in the matrix but not in the app": sorted(covered - expected),
    }


# --- the harness ---------------------------------------------------------------


@pytest.fixture
async def rig(settings, db):
    """Both tenants seeded, the app with every router, storage mocked at the
    transport, and the verifier over the fake JWKS (the test user's token
    resolves to tenant A through the membership the db fixture planted)."""
    fake_storage = FakeStorage()

    app = FastAPI()
    app.include_router(webhook_router)
    app.include_router(api_router)
    app.include_router(menu_router)
    app.include_router(sales_router)
    app.include_router(dashboard_router)
    app.include_router(waitlist_router)
    app.state.settings = settings
    wire_auth(app)
    app.state.db = db
    app.state.storage = Storage(settings, transport=fake_storage.transport())

    await db.pool.execute(
        "insert into tenants (id, name, currency) values ($1, 'Other Chain', 'AED')", TENANT_B
    )
    await db.pool.execute(
        "insert into branches (id, tenant_id, name, timezone) "
        "values ($1, $2, 'Elsewhere', 'Asia/Dubai')",
        BRANCH_B,
        TENANT_B,
    )
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    return app, client, fake_storage


class Rows:
    """Tenant A's rows, created directly through the db layer so the matrix
    exercises the API's scoping and not the ingest pipeline."""

    def __init__(self):
        self.ids: dict[str, str] = {}

    def __getitem__(self, name: str) -> str:
        return self.ids[name]


async def seed_tenant_a(db, fake_storage: FakeStorage) -> Rows:
    rows = Rows()
    rows.ids["branch"] = BRANCH_A
    rows.ids["supplier"] = str(
        await db.pool.fetchval(
            "insert into suppliers (tenant_id, name) values ($1, 'Gulf Foods') returning id",
            TENANT_A,
        )
    )
    rows.ids["supplier_item"] = str(
        await db.pool.fetchval(
            """
            insert into supplier_items (tenant_id, supplier_id, canonical_name, unit, pack_size)
            values ($1, $2, 'Milk Powder', 'bag', '1 kg') returning id
            """,
            TENANT_A,
            rows["supplier"],
        )
    )
    rows.ids["ingredient"] = str(
        await db.pool.fetchval(
            "insert into ingredients (tenant_id, name, base_unit) values ($1, 'Milk powder', 'g') "
            "returning id",
            TENANT_A,
        )
    )

    # An uploaded document with a stored original, so the detail path has a
    # URL to sign - or, for the wrong tenant, to refuse to sign.
    document_id = await db.insert_uploaded_document(
        tenant_id=TENANT_A, branch_id=BRANCH_A, mime="image/jpeg", sha256="a" * 64
    )
    path = f"{TENANT_A}/documents/{document_id}/original"
    fake_storage.objects[path] = b"\xff\xd8fake"
    await db.set_document_storage_path(document_id, path, tenant_id=TENANT_A)
    rows.ids["document"] = document_id
    rows.ids["storage_path"] = path
    rows.ids["invoice"] = await db.insert_draft_invoice(
        tenant_id=TENANT_A,
        branch_id=BRANCH_A,
        document_id=document_id,
        supplier_id=rows["supplier"],
        supplier_name="Gulf Foods",
        invoice_no="GF-1",
        invoice_date=None,
        currency="AED",
        subtotal=Decimal("100.00"),
        tax=Decimal("5.00"),
        total=Decimal("105.00"),
        payment_kind="credit",
        confidence={},
        provenance={},
        lines=[
            {
                "position": 0,
                "raw_name": "Milk Powder 1kg",
                "supplier_item_id": rows["supplier_item"],
                "qty": Decimal("1"),
                "unit": "bag",
                "unit_price": Decimal("100.00"),
                "line_total": Decimal("100.00"),
                "pack_size": "1 kg",
                "checks": {},
            }
        ],
    )
    # A held duplicate of it, for the dismiss door.
    copy_document = await db.insert_manual_document(tenant_id=TENANT_A, branch_id=BRANCH_A)
    rows.ids["duplicate"] = await db.insert_draft_invoice(
        tenant_id=TENANT_A,
        branch_id=BRANCH_A,
        document_id=copy_document,
        supplier_id=rows["supplier"],
        supplier_name="Gulf Foods",
        invoice_no="GF-1",
        invoice_date=None,
        currency="AED",
        subtotal=Decimal("100.00"),
        tax=Decimal("5.00"),
        total=Decimal("105.00"),
        payment_kind="credit",
        status=InvoiceStatus.NEEDS_REVIEW,
        confidence={},
        provenance={},
        lines=[],
        document_classification=None,
        duplicate_of_invoice_id=rows["invoice"],
    )
    # A cash paper held for the owner, for the approve door (WP-74).
    cash_document = await db.insert_manual_document(tenant_id=TENANT_A, branch_id=BRANCH_A)
    rows.ids["cash"] = await db.insert_draft_invoice(
        tenant_id=TENANT_A,
        branch_id=BRANCH_A,
        document_id=cash_document,
        supplier_id=rows["supplier"],
        supplier_name="Gulf Foods",
        invoice_no="GF-2",
        invoice_date=None,
        currency="AED",
        subtotal=Decimal("100.00"),
        tax=Decimal("5.00"),
        total=Decimal("105.00"),
        payment_kind="cash",
        status=InvoiceStatus.NEEDS_REVIEW,
        confidence={},
        provenance={},
        lines=[],
        document_classification=None,
    )
    item = await db.create_menu_item(
        tenant_id=TENANT_A, name="Karak", selling_price=Decimal("5.00"), actor="test"
    )
    rows.ids["menu_item"] = item["id"]
    # A till name the loader minted, for the mapping doors (WP-82).
    rows.ids["till_item"] = str(
        await db.pool.fetchval(
            "insert into till_items (tenant_id, name, name_key, code) "
            "values ($1, 'KARAK TEA CUP', 'karak tea cup', '52') returning id",
            TENANT_A,
        )
    )
    return rows


async def counts_for(db, tenant_id: str) -> dict[str, int]:
    return {
        table: await db.pool.fetchval(
            f"select count(*) from {table} where tenant_id = $1", tenant_id
        )
        for table in TENANT_TABLES
    }


#: The matrix. `path` is the route as registered; `url` builds the concrete
#: request against tenant A's rows; `expect_b` is what tenant B's context gets
#: for the same request. A route with an id in its path answers B with 404 -
#: the row does not exist for them. A route with no id answers B like A, and
#: the harness proves separately that B's call wrote nothing into A and saw
#: none of A's ids. The order is a script: state written by one case is what
#: the next one needs.
MATRIX: list[dict] = [
    {"method": "GET", "path": "/api/invoices", "url": lambda r: "/api/invoices"},
    {
        "method": "GET",
        "path": "/api/invoices/{invoice_id}",
        "url": lambda r: f"/api/invoices/{r['invoice']}",
    },
    {
        "method": "PATCH",
        "path": "/api/invoices/{invoice_id}/fields",
        "url": lambda r: f"/api/invoices/{r['invoice']}/fields",
        "json": {"corrections": [{"line_index": 0, "field": "qty", "value": "2"}]},
    },
    {
        "method": "POST",
        "path": "/api/invoices/{invoice_id}/confirm",
        "url": lambda r: f"/api/invoices/{r['invoice']}/confirm",
    },
    {
        "method": "POST",
        "path": "/api/invoices/{invoice_id}/dismiss",
        "url": lambda r: f"/api/invoices/{r['duplicate']}/dismiss",
    },
    {
        "method": "POST",
        "path": "/api/invoices/{invoice_id}/approve",
        "url": lambda r: f"/api/invoices/{r['cash']}/approve",
        "json": {"reason": "Paid at the door"},
    },
    {
        "method": "POST",
        "path": "/api/invoices/manual",
        "url": lambda r: "/api/invoices/manual",
        "json": {"supplier_name": "Typed Supplier", "total": "10", "lines": [{"raw_name": "Tea"}]},
        "expect": 201,
    },
    {
        "method": "POST",
        "path": "/api/documents",
        "url": lambda r: "/api/documents",
        "files": {"file": ("a.jpg", b"\xff\xd8jpeg", "image/jpeg")},
        "expect": 201,
    },
    {
        "method": "GET",
        "path": "/api/supplier-items/{item_id}/prices",
        "url": lambda r: f"/api/supplier-items/{r['supplier_item']}/prices",
    },
    {"method": "GET", "path": "/api/ingredients", "url": lambda r: "/api/ingredients"},
    {
        "method": "POST",
        "path": "/api/ingredients",
        "url": lambda r: "/api/ingredients",
        "json": {"name": "Saffron", "unit": "g"},
        "expect": 201,
    },
    {
        "method": "GET",
        "path": "/api/supplier-items/unmapped",
        "url": lambda r: "/api/supplier-items/unmapped",
    },
    {
        "method": "POST",
        "path": "/api/supplier-items/{item_id}/ingredient",
        "url": lambda r: f"/api/supplier-items/{r['supplier_item']}/ingredient",
        "json": lambda r: {"ingredient_id": r["ingredient"]},
    },
    {
        "method": "POST",
        "path": "/api/supplier-items/{item_id}/pack-size",
        "url": lambda r: f"/api/supplier-items/{r['supplier_item']}/pack-size",
        "json": {"pack_size": "10 kg"},
    },
    {
        "method": "POST",
        "path": "/api/supplier-items/{item_id}/ingredient/reject",
        "url": lambda r: f"/api/supplier-items/{r['supplier_item']}/ingredient/reject",
        "json": lambda r: {"ingredient_id": r["ingredient"]},
    },
    {
        "method": "DELETE",
        "path": "/api/supplier-items/{item_id}/ingredient",
        "url": lambda r: f"/api/supplier-items/{r['supplier_item']}/ingredient",
    },
    {"method": "GET", "path": "/api/blocked-costs", "url": lambda r: "/api/blocked-costs"},
    {"method": "GET", "path": "/api/menu-items", "url": lambda r: "/api/menu-items"},
    {
        "method": "POST",
        "path": "/api/menu-items",
        "url": lambda r: "/api/menu-items",
        "json": {"name": "Chai Special", "selling_price": "7.00"},
        "expect": 201,
    },
    {
        "method": "GET",
        "path": "/api/menu-items/{menu_item_id}",
        "url": lambda r: f"/api/menu-items/{r['menu_item']}",
    },
    {
        "method": "PATCH",
        "path": "/api/menu-items/{menu_item_id}/price",
        "url": lambda r: f"/api/menu-items/{r['menu_item']}/price",
        "json": {"selling_price": "6.00"},
    },
    {
        "method": "POST",
        "path": "/api/menu-items/{menu_item_id}/recipe",
        "url": lambda r: f"/api/menu-items/{r['menu_item']}/recipe",
        "json": lambda r: {
            "yield_portions": "1",
            "components": [{"ingredient_id": r["ingredient"], "qty": "20", "unit": "g"}],
        },
        "expect": 201,
    },
    {
        # No id in the path, but the body names A's ingredient - which does not
        # exist for B, so B is refused with the same 404 a missing one gets.
        "method": "POST",
        "path": "/api/menu-items/load",
        "url": lambda r: "/api/menu-items/load",
        "json": lambda r: {
            "name": "Loaded Karak",
            "selling_price": "5.00",
            "yield_portions": "1",
            "components": [{"ingredient_id": r["ingredient"], "qty": "20", "unit": "g"}],
        },
        "expect_b": 404,
    },
    {"method": "GET", "path": "/api/price-moves", "url": lambda r: "/api/price-moves"},
    {
        "method": "POST",
        "path": "/api/menu-items/{menu_item_id}/archive",
        "url": lambda r: f"/api/menu-items/{r['menu_item']}/archive",
    },
    {
        "method": "POST",
        "path": "/api/menu-items/{menu_item_id}/unarchive",
        "url": lambda r: f"/api/menu-items/{r['menu_item']}/unarchive",
    },
    # M8 WP-80: the sales tables' door and the reads beside it.
    {"method": "GET", "path": "/api/branches", "url": lambda r: "/api/branches"},
    {
        "method": "POST",
        "path": "/api/branches/{branch_id}/aliases",
        "url": lambda r: f"/api/branches/{r['branch']}/aliases",
        "json": {"alias": "QUSAIS 1"},
        "expect": 201,
    },
    {
        "method": "POST",
        "path": "/api/sales/files",
        "url": lambda r: "/api/sales/files",
        "files": {"file": ("sales.csv", b"Outlet,Date,Item,Qty,Amount\n", "text/csv")},
        "expect": 201,
    },
    {"method": "GET", "path": "/api/sales/layouts", "url": lambda r: "/api/sales/layouts"},
    {
        "method": "POST",
        "path": "/api/sales/layouts",
        "url": lambda r: "/api/sales/layouts",
        "json": {
            "name": "Main till",
            "columns": {"date": "Date", "item": "Item", "amount": "Amount"},
            "amount_basis": "inclusive",
            "date_order": "dmy",
        },
        "expect": 201,
    },
    {
        "method": "GET",
        "path": "/api/sales/days",
        "url": lambda r: f"/api/sales/days?from={SALES_DAY}&to={SALES_DAY}",
    },
    {
        # No id in the path, but the body names A's branch - which does not
        # exist for B, so B is refused with the same 404 a missing one gets.
        "method": "POST",
        "path": "/api/sales/days",
        "url": lambda r: "/api/sales/days",
        "json": lambda r: {
            "days": [
                {
                    "branch_id": r["branch"],
                    "business_date": SALES_DAY,
                    "granularity": "item",
                    "amount_basis": "inclusive",
                    "lines": [{"position": 0, "name": "KARAK", "qty": "3", "amount": "10.50"}],
                }
            ]
        },
        "expect_b": 404,
    },
    # M8 WP-81: the ratio and coverage reads, derived per tenant on every call.
    {
        "method": "GET",
        "path": "/api/sales/branches",
        "url": lambda r: f"/api/sales/branches?from={SALES_DAY}&to={SALES_DAY}",
    },
    {
        "method": "GET",
        "path": "/api/sales/coverage",
        "url": lambda r: f"/api/sales/coverage?from={SALES_DAY}&to={SALES_DAY}",
    },
    # M9 WP-92: the one dashboard read, derived per tenant on every call.
    {
        "method": "GET",
        "path": "/api/dashboard",
        "url": lambda r: f"/api/dashboard?from={SALES_DAY}&to={SALES_DAY}",
    },
    # The till-name mapping doors (WP-82): map, then unmap, then exclude - a
    # script, because exclude refuses a mapped name.
    {
        "method": "POST",
        "path": "/api/till-items/{till_item_id}/menu-item",
        "url": lambda r: f"/api/till-items/{r['till_item']}/menu-item",
        "json": lambda r: {"menu_item_id": r["menu_item"]},
    },
    {
        "method": "DELETE",
        "path": "/api/till-items/{till_item_id}/menu-item",
        "url": lambda r: f"/api/till-items/{r['till_item']}/menu-item",
    },
    {
        "method": "POST",
        "path": "/api/till-items/{till_item_id}/exclude",
        "url": lambda r: f"/api/till-items/{r['till_item']}/exclude",
    },
]


def _request_kwargs(case: dict, rows: Rows) -> dict:
    kwargs = {}
    if "json" in case:
        body = case["json"]
        kwargs["json"] = body(rows) if callable(body) else body
    if "files" in case:
        kwargs["files"] = case["files"]
    return kwargs


async def test_every_route_answers_its_own_tenant_and_nobody_else(rig, db):
    app, client, fake_storage = rig
    rows = await seed_tenant_a(db, fake_storage)
    a_ids = {value for key, value in rows.ids.items() if key != "storage_path"}

    for case in MATRIX:
        method, url = case["method"], case["url"](rows)
        kwargs = _request_kwargs(case, rows)
        expect_a = case.get("expect", 200)
        expect_b = case.get("expect_b", 404 if "{" in case["path"] else expect_a)

        # No token: refused before any handler runs.
        app.dependency_overrides.clear()
        response = await client.request(method, url, **kwargs)
        assert response.status_code == 401, (method, url, response.text)

        # Tenant B's context: A's rows do not exist, and nothing lands in A.
        before = await counts_for(db, TENANT_A)
        app.dependency_overrides[require_context] = lambda: context_for(TENANT_B)
        response = await client.request(method, url, **kwargs)
        app.dependency_overrides.clear()
        assert response.status_code == expect_b, (method, url, response.text)
        assert await counts_for(db, TENANT_A) == before, (method, url)
        leaked = [value for value in a_ids if value in response.text]
        assert not leaked, (method, url, leaked)

        # Tenant A, through the test user's verified token: the row is theirs.
        response = await client.request(method, url, headers=AUTH, **kwargs)
        assert response.status_code == expect_a, (method, url, response.text)
        if method == "GET" and "{" in case["path"]:
            assert url.split("/")[3] in response.text, (method, url)

    # Everything B created landed in B, under B's own ids.
    b_counts = await counts_for(db, TENANT_B)
    assert b_counts["invoices"] == 1 and b_counts["documents"] == 2  # manual + upload
    assert b_counts["ingredients"] == 1 and b_counts["menu_items"] == 1


async def test_the_verified_token_resolves_to_its_membership_as_the_user(rig, db):
    """The one source: a verified token is its membership's tenant, and every
    audit row it writes carries the person's id, not a shared name."""
    app, client, _ = rig
    response = await client.post(
        "/api/ingredients", json={"name": "Cardamom", "unit": "g"}, headers=AUTH
    )
    assert response.status_code == 201, response.text
    event = await db.pool.fetchrow(
        "select tenant_id::text as tenant_id, actor from audit_events "
        "where action = 'ingredient.created'"
    )
    assert event["tenant_id"] == TENANT_A and event["actor"] == TEST_ACTOR


async def test_no_storage_url_is_signed_for_a_foreign_document(rig, db):
    app, client, fake_storage = rig
    rows = await seed_tenant_a(db, fake_storage)

    app.dependency_overrides[require_context] = lambda: context_for(TENANT_B)
    response = await client.get(f"/api/invoices/{rows['invoice']}")
    app.dependency_overrides.clear()
    assert response.status_code == 404
    assert fake_storage.signed == []

    response = await client.get(f"/api/invoices/{rows['invoice']}", headers=AUTH)
    assert response.status_code == 200, response.text
    assert response.json()["image_url"] is not None
    assert fake_storage.signed == [rows["storage_path"]]


async def test_a_cross_tenant_branch_is_refused_by_postgres_and_by_the_api(rig, db):
    """The 0018 composite keys: a document or invoice cannot claim a branch of
    another tenant, whatever the application forgot to check."""
    app, client, _ = rig
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await db.pool.execute(
            "insert into documents (tenant_id, branch_id, source) values ($1, $2, 'manual')",
            TENANT_B,
            BRANCH_A,
        )
    document_b = await db.insert_manual_document(tenant_id=TENANT_B, branch_id=BRANCH_B)
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await db.pool.execute(
            "insert into invoices (tenant_id, branch_id, document_id) values ($1, $2, $3)",
            TENANT_B,
            BRANCH_A,
            document_b,
        )

    # And the API says the branch is unknown, because for B it is.
    app.dependency_overrides[require_context] = lambda: context_for(TENANT_B)
    response = await client.post(
        "/api/invoices/manual",
        json={"branch_id": BRANCH_A, "total": "10", "lines": [{"raw_name": "Tea"}]},
    )
    app.dependency_overrides.clear()
    assert response.status_code == 422, response.text


async def test_the_schema_carries_memberships_and_the_one_extract_job_per_document(db):
    """What WP-70 and WP-72 will build on: a memberships row per (tenant,
    user), deny-all like every other table; and one extract job per document,
    refused by Postgres on the second insert."""
    user_id = str(uuid.uuid4())
    await db.pool.execute(
        "insert into memberships (tenant_id, user_id) values ($1, $2)", TENANT_A, user_id
    )
    with pytest.raises(asyncpg.UniqueViolationError):
        await db.pool.execute(
            "insert into memberships (tenant_id, user_id) values ($1, $2)", TENANT_A, user_id
        )
    with pytest.raises(asyncpg.CheckViolationError):
        await db.pool.execute(
            "insert into memberships (tenant_id, user_id, role) values ($1, $2, 'owner')",
            TENANT_A,
            str(uuid.uuid4()),
        )
    assert await db.pool.fetchval(
        "select relrowsecurity from pg_class where relname = 'memberships'"
    )

    document_id = await db.insert_manual_document(tenant_id=TENANT_A, branch_id=None)
    await db.enqueue("extract_document", {"document_id": document_id})
    with pytest.raises(asyncpg.UniqueViolationError):
        await db.enqueue("extract_document", {"document_id": document_id})
    # Other job kinds are not constrained by it.
    await db.enqueue("process_wa_message", {"document_id": document_id})
    await db.enqueue("process_wa_message", {"document_id": document_id})
