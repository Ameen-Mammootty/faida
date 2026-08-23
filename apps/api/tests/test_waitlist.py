"""The public waitlist writes real rows without exposing a read endpoint."""

import httpx
import pytest
from fastapi import FastAPI

from faida_api.waitlist import WAITLIST_BODY_MAX_BYTES, router

from .conftest import requires_db


def client_for(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def waitlist_app(db):
    app = FastAPI()
    app.include_router(router)
    app.state.db = db
    return app, client_for(app)


@requires_db
async def test_signup_is_normalized_persisted_and_deduplicated(waitlist_app, db):
    _, client = waitlist_app

    first = await client.post(
        "/api/waitlist",
        json={"email": "  Owner+Pilot@Example.COM  ", "website": ""},
    )
    duplicate = await client.post(
        "/api/waitlist",
        json={"email": "owner+pilot@example.com"},
    )

    assert first.status_code == 202
    assert duplicate.status_code == 202
    assert first.json() == duplicate.json() == {"ok": True}
    assert first.headers["cache-control"] == "no-store"
    rows = await db.pool.fetch("select email, source, created_at from waitlist_signups")
    assert len(rows) == 1
    assert rows[0]["email"] == "owner+pilot@example.com"
    assert rows[0]["source"] == "landing_page"
    assert rows[0]["created_at"] is not None


@requires_db
async def test_honeypot_returns_success_without_storing(waitlist_app, db):
    _, client = waitlist_app
    response = await client.post(
        "/api/waitlist",
        json={"email": "bot@example.com", "website": "https://spam.example"},
    )
    assert response.status_code == 202
    assert response.json() == {"ok": True}
    assert await db.pool.fetchval("select count(*) from waitlist_signups") == 0


@requires_db
async def test_invalid_requests_never_leave_rows(waitlist_app, db):
    _, client = waitlist_app
    invalid_bodies = [
        {"email": "not-an-email"},
        {"email": "owner@example"},
        {"email": "owner @example.com"},
        {"email": "owner@example.com", "unexpected": True},
    ]
    for body in invalid_bodies:
        response = await client.post("/api/waitlist", json=body)
        assert response.status_code == 422, body

    wrong_type = await client.post(
        "/api/waitlist",
        content="email=owner@example.com",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert wrong_type.status_code == 415

    oversized = await client.post(
        "/api/waitlist",
        content=b"x" * (WAITLIST_BODY_MAX_BYTES + 1),
        headers={"Content-Type": "application/json"},
    )
    assert oversized.status_code == 413
    assert await db.pool.fetchval("select count(*) from waitlist_signups") == 0


async def test_waitlist_has_no_public_read_route():
    app = FastAPI()
    app.include_router(router)
    client = client_for(app)
    assert (await client.get("/api/waitlist")).status_code == 405
