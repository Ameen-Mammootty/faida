"""M13.8: the morning - the tick, the job, the pause door, the kill switch
and the rehearsal, against real Postgres (issue #14; the spec's test seam 2).

The card's words and its picture are proven in `test_scoreboard.py` and
`test_scoreboard_card.py`. What is proven here is everything around them:
that the morning comes once per branch per local day, at seven in the
branch's own timezone and never late; that a branch with no scheme month,
or paused, gets nothing; that the job stores the card before the upload and
the send, sends one template with the picture as header and two slots, and
records one outbound row Meta's receipts land on; that every way the send
can fail leaves the queue and the record honest; that Monday's card carries
the new week's list; and that the rehearsal goes through the job's own path.

Meta and storage are mocked at the transport layer as in every flow test,
and the clock is passed into the tick rather than read inside it. The chain
is staged the way the statement tests stage it: July 2026 through its own
door, the lists on its weeks, the sales through the branch-day door.
"""

import asyncio
import datetime
import logging
from io import StringIO

import httpx
import pytest
from fastapi import FastAPI

from faida_api import scoreboard, scoreboard_card, scoreboard_cli, worker
from faida_api.contracts import JobKind
from faida_api.incentive_api import router as incentive_router
from faida_api.menu import router as menu_router
from faida_api.sales import router as sales_router
from faida_api.storage import Storage
from faida_api.wa import WhatsAppClient
from faida_api.worker import read_scoreboard, run_one_job, send_scoreboard, tick_scoreboards

from .conftest import AUTH, DEMO_PHONE, FakeMeta, FakeStorage, requires_db, wire_auth
from .test_extraction_flow import drain_jobs
from .test_incentive_api import (
    BRANCH,
    BRANCH_2,
    BRANCH_3,
    TENANT,
    _approve,
    _audit,
    _july,
    _july_with_sales,
    _rest_of_july,
)
from .test_sales_load import BRANCH_B, TENANT_B, _other_tenant

pytestmark = requires_db

#: The phones the other two branches are registered to for these tests; the
#: seeded branch already has `DEMO_PHONE`.
PHONE_2 = "971500000002"
PHONE_3 = "971500000003"
FOUNDER = "971559990009"

#: Wednesday 8 July 2026: Al Barsha's newest loaded day is the 7th, and the
#: second push week (6-12 Jul, mandi) is in view.
DAY = datetime.date(2026, 7, 8)
#: The first Sunday and Monday of July 2026: the week boundary.
SUNDAY = datetime.date(2026, 7, 5)
MONDAY = datetime.date(2026, 7, 6)


def _utc(day: datetime.date, hour: int, minute: int = 0) -> datetime.datetime:
    return datetime.datetime(day.year, day.month, day.day, hour, minute, tzinfo=datetime.UTC)


@pytest.fixture
def rig(settings, db):
    """One app over the test database with the incentive, menu and sales
    doors for staging, Meta and storage faked at the transport layer."""
    fake_meta = FakeMeta()
    fake_storage = FakeStorage()
    app = FastAPI()
    app.include_router(incentive_router)
    app.include_router(menu_router)
    app.include_router(sales_router)
    app.state.settings = settings
    wire_auth(app)
    app.state.db = db
    app.state.wa = WhatsAppClient(settings, transport=fake_meta.transport())
    app.state.storage = Storage(settings, transport=fake_storage.transport())
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    return app, client, fake_meta, fake_storage


async def _phones(db, *, timezone_2: str = "Asia/Dubai") -> None:
    """The two staged branches given phones (the seed's has one already), the
    second in the timezone asked for."""
    await db.pool.execute(
        "update branches set wa_phone_e164 = $2, timezone = $3 where id = $1",
        BRANCH_2,
        PHONE_2,
        timezone_2,
    )
    await db.pool.execute("update branches set wa_phone_e164 = $2 where id = $1", BRANCH_3, PHONE_3)


async def _stage(client, db, **phones) -> dict:
    ids = await _july_with_sales(client, db)
    await _phones(db, **phones)
    return ids


async def _jobs(db) -> list:
    return await db.pool.fetch(
        "select * from jobs where kind = $1 order by id", JobKind.SEND_SCOREBOARD
    )


async def _outbound(db) -> list:
    return await db.pool.fetch(
        "select * from wa_messages where direction = 'out' and msg_type = 'template' order by id"
    )


def _card_path(branch: str, day: datetime.date = DAY, *, variant: str = "daily") -> str:
    """Where the card is stored (D15). Spelled out here rather than imported,
    so a path the code changes quietly fails a test loudly."""
    suffix = "" if variant == "daily" else f"-{variant}"
    return f"{TENANT}/scoreboards/{day.isoformat()}/{branch}{suffix}.png"


async def _enqueue(db, branch: str = BRANCH, day: datetime.date = DAY, *, variant="daily") -> int:
    scheme = await db.scheme_month_for(day, tenant_id=TENANT)
    job_id = await db.enqueue_scoreboard_once(
        {
            "tenant_id": TENANT,
            "branch_id": branch,
            "day": day.isoformat(),
            "variant": variant,
            "scheme_month_id": scheme["id"] if scheme else None,
        }
    )
    assert job_id is not None
    return job_id


# --- the tick: whose morning has come -------------------------------------------


async def test_the_tick_enqueues_one_job_per_branch_per_local_day_and_a_second_tick_none(rig, db):
    """Three branches with phones and a scheme month covering July: three
    jobs at 07:00 Dubai (03:00 UTC), and none a minute later or an hour on."""
    _, client, _, _ = rig
    async with client:
        await _stage(client, db)

    assert await tick_scoreboards(db, _utc(DAY, 3)) == 3
    assert await tick_scoreboards(db, _utc(DAY, 3, 1)) == 0
    assert await tick_scoreboards(db, _utc(DAY, 8)) == 0

    jobs = await _jobs(db)
    scheme = await db.scheme_month_for(DAY, tenant_id=TENANT)
    assert sorted(job["payload"]["branch_id"] for job in jobs) == sorted(
        [BRANCH, BRANCH_2, BRANCH_3]
    )
    assert {job["payload"]["day"] for job in jobs} == {DAY.isoformat()}
    assert {job["payload"]["variant"] for job in jobs} == {scoreboard.DAILY}
    assert {job["payload"]["tenant_id"] for job in jobs} == {TENANT}
    assert {job["payload"]["scheme_month_id"] for job in jobs} == {scheme["id"]}
    assert all(job["status"] == "queued" for job in jobs)


async def test_the_morning_is_the_branchs_own_seven_oclock(rig, db):
    """07:00 in Dubai is 03:00 UTC: due then and not a minute before; a
    branch in London waits three more hours and then has its own morning."""
    _, client, _, _ = rig
    async with client:
        await _stage(client, db, timezone_2="Europe/London")

    assert await tick_scoreboards(db, _utc(DAY, 2, 59)) == 0
    assert await _jobs(db) == []

    assert await tick_scoreboards(db, _utc(DAY, 3)) == 2
    assert sorted(job["payload"]["branch_id"] for job in await _jobs(db)) == sorted(
        [BRANCH, BRANCH_3]
    )

    assert await tick_scoreboards(db, _utc(DAY, 5, 59)) == 0
    assert await tick_scoreboards(db, _utc(DAY, 6)) == 1
    assert [job["payload"]["branch_id"] for job in await _jobs(db)][-1] == BRANCH_2


async def test_past_noon_the_day_is_skipped_said_once_and_never_sent_late(rig, db, caplog):
    """A scoreboard at noon is as stale as a brief at noon: skipped with one
    log line per branch per day, and tomorrow's is next."""
    _, client, _, _ = rig
    async with client:
        await _stage(client, db)
    spoken: set = set()

    with caplog.at_level(logging.INFO, logger="faida_api.worker"):
        assert await tick_scoreboards(db, _utc(DAY, 9), spoken=spoken) == 0
        assert await tick_scoreboards(db, _utc(DAY, 10), spoken=spoken) == 0
    assert await _jobs(db) == []
    skipped = [r for r in caplog.records if "scoreboard skipped" in r.getMessage()]
    assert len(skipped) == 3
    assert all("past 12:00" in r.getMessage() for r in skipped)

    next_day = DAY + datetime.timedelta(days=1)
    assert await tick_scoreboards(db, _utc(next_day, 3), spoken=spoken) == 3


async def test_a_branch_with_no_scheme_month_gets_nothing_and_one_log_line(rig, db, caplog):
    """June has no scheme month, so a June morning wakes nobody (D13), and
    the reason is said once per branch per day."""
    _, client, _, _ = rig
    async with client:
        await _stage(client, db)
    spoken: set = set()
    june = datetime.date(2026, 6, 8)

    with caplog.at_level(logging.INFO, logger="faida_api.worker"):
        assert await tick_scoreboards(db, _utc(june, 3), spoken=spoken) == 0
        assert await tick_scoreboards(db, _utc(june, 4), spoken=spoken) == 0
    assert await _jobs(db) == []
    said = [r.getMessage() for r in caplog.records if "no scheme month" in r.getMessage()]
    assert len(said) == 3 and BRANCH in " ".join(said)


async def test_a_paused_branch_has_no_morning_and_a_resumed_one_has_the_next(rig, db, caplog):
    _, client, _, _ = rig
    async with client:
        await _stage(client, db)
    assert await db.pause_incentive_branch(BRANCH, tenant_id=TENANT, actor="console") is True

    with caplog.at_level(logging.INFO, logger="faida_api.worker"):
        assert await tick_scoreboards(db, _utc(DAY, 3)) == 2
    assert BRANCH not in {job["payload"]["branch_id"] for job in await _jobs(db)}
    assert any("paused" in r.getMessage() and BRANCH in r.getMessage() for r in caplog.records)

    assert await db.resume_incentive_branch(BRANCH, tenant_id=TENANT, actor="console") is True
    assert await tick_scoreboards(db, _utc(DAY, 3)) == 1
    assert BRANCH in {job["payload"]["branch_id"] for job in await _jobs(db)}


async def test_a_branch_with_no_registered_phone_is_skipped_and_the_others_are_not(rig, db, caplog):
    _, client, _, _ = rig
    async with client:
        await _july_with_sales(client, db)  # the seed's branch alone has a phone

    with caplog.at_level(logging.INFO, logger="faida_api.worker"):
        assert await tick_scoreboards(db, _utc(DAY, 3)) == 1
    (job,) = await _jobs(db)
    assert job["payload"]["branch_id"] == BRANCH
    said = [r.getMessage() for r in caplog.records if "no registered phone" in r.getMessage()]
    assert len(said) == 2


async def test_a_timezone_that_does_not_resolve_is_skipped_and_the_next_is_enqueued(
    rig, db, caplog
):
    _, client, _, _ = rig
    async with client:
        await _stage(client, db, timezone_2="Mars/Phobos")

    with caplog.at_level(logging.WARNING, logger="faida_api.worker"):
        assert await tick_scoreboards(db, _utc(DAY, 3)) == 2
    assert BRANCH_2 not in {job["payload"]["branch_id"] for job in await _jobs(db)}
    said = " ".join(r.getMessage() for r in caplog.records)
    assert BRANCH_2 in said and "Mars/Phobos" in said


async def test_another_chains_month_wakes_none_of_this_chains_branches(rig, db):
    """The join is by tenant: tenant B's scheme month is not July for tenant
    A's branches, and B's branch without a month of its own sleeps."""
    _, client, _, _ = rig
    async with client:
        await _stage(client, db)
    await _other_tenant(db)
    await db.pool.execute(
        "update branches set wa_phone_e164 = '971500000099' where id = $1", BRANCH_B
    )

    assert await tick_scoreboards(db, _utc(DAY, 3)) == 3
    assert {job["payload"]["tenant_id"] for job in await _jobs(db)} == {TENANT}
    assert TENANT_B != TENANT


# --- the job: one card, one message, one row ------------------------------------


async def test_the_job_sends_the_template_with_the_card_as_header_and_records_it(rig, db):
    app, client, fake_meta, fake_storage = rig
    async with client:
        await _stage(client, db)
    card = await read_scoreboard(db, TENANT, BRANCH, today=DAY)
    assert card is not None

    await _enqueue(db)
    assert await run_one_job(db, app.state.wa, app.state.storage) is True

    (sent,) = fake_meta.sent
    assert sent["to"] == DEMO_PHONE
    assert sent["type"] == "template"
    assert sent["template"]["name"] == scoreboard.TEMPLATE_NAME
    assert sent["template"]["language"] == {"code": scoreboard.TEMPLATE_LANGUAGE}
    header, body = sent["template"]["components"]
    assert header["type"] == "header"
    assert header["parameters"][0]["image"]["id"] == "media-up1"
    assert body["type"] == "body"
    assert [part["text"] for part in body["parameters"]] == list(card.parameters)
    assert len(body["parameters"]) == scoreboard.PARAMETER_COUNT
    assert card.parameters[0] == "Al Barsha scoreboard, Wed 8 Jul"
    assert card.parameters[1] == "Sales loaded to Tue 7 Jul, yesterday."

    # The picture in storage is the one the phone got, byte for byte.
    assert fake_storage.objects == {_card_path(BRANCH): scoreboard_card.render_card(card)}
    (upload,) = fake_meta.uploads
    assert upload["file"] == scoreboard_card.render_card(card)

    (row,) = await _outbound(db)
    assert row["message_id"] == "wamid.out1"
    assert row["to_phone"] == DEMO_PHONE
    assert row["status"] == "sent"
    assert row["payload"] == {
        "template": scoreboard.TEMPLATE_NAME,
        "language": scoreboard.TEMPLATE_LANGUAGE,
        "parameters": list(card.parameters),
        "card_path": _card_path(BRANCH),
        "tenant_id": TENANT,
        "branch_id": BRANCH,
        "day": DAY.isoformat(),
        "variant": scoreboard.DAILY,
        "rehearsal": False,
        "error": None,
    }
    assert (
        await db.outbound_scoreboard_exists(
            branch_id=BRANCH, day=DAY.isoformat(), variant=scoreboard.DAILY
        )
        is True
    )
    (job,) = await _jobs(db)
    assert job["status"] == "done"


async def test_the_card_is_stored_then_uploaded_then_sent(rig, db, monkeypatch):
    """The order is the contract (D15): the evidence exists before the
    message does, and Meta holds the picture before the template names it."""
    app, client, _, _ = rig
    async with client:
        await _stage(client, db)
    order: list[str] = []

    def note(target, name: str, step: str) -> None:
        real = getattr(target, name)

        async def wrapped(*args, **kwargs):
            order.append(step)
            return await real(*args, **kwargs)

        monkeypatch.setattr(target, name, wrapped)

    note(app.state.storage, "put", "store")
    note(app.state.wa, "upload_media", "upload")
    note(app.state.wa, "send_template", "send")

    await _enqueue(db)
    assert await run_one_job(db, app.state.wa, app.state.storage) is True
    assert order == ["store", "upload", "send"]


async def test_a_receipt_that_beats_the_record_leaves_a_stub_the_record_completes(rig, db):
    """Meta's `delivered` can reach the webhook before the job has written
    what it sent: the receipt leaves a stub, the record upserts into it, and
    neither order loses a fact."""
    app, client, _, _ = rig
    async with client:
        await _stage(client, db)
    # FakeMeta names the first message wamid.out1; its receipt lands first.
    assert await db.stamp_outbound_status("wamid.out1", "delivered", to_phone=DEMO_PHONE) is True

    await _enqueue(db)
    assert await run_one_job(db, app.state.wa, app.state.storage) is True

    (row,) = await _outbound(db)
    assert row["message_id"] == "wamid.out1"
    assert row["status"] == "delivered"  # the receipt is further along than our own 'sent'
    assert row["payload"]["branch_id"] == BRANCH
    assert row["payload"]["card_path"] == _card_path(BRANCH)
    assert "stub" not in row["payload"]


async def test_the_same_payload_run_twice_sends_once(rig, db):
    """The outbound row is the second guard, under the index: a job replayed
    by hand costs no second card."""
    app, client, fake_meta, _ = rig
    async with client:
        await _stage(client, db)
    await _enqueue(db)
    assert await run_one_job(db, app.state.wa, app.state.storage) is True
    (job,) = await _jobs(db)

    assert await db.enqueue_scoreboard_once(dict(job["payload"])) is None
    await send_scoreboard(db, app.state.wa, app.state.storage, dict(job["payload"]))
    assert len(fake_meta.sent) == 1
    assert len(await _outbound(db)) == 1


async def test_a_send_failure_leaves_the_job_to_retry_and_the_retry_meets_its_own_card(rig, db):
    """Meta down: the job is requeued, nothing is recorded, and the card is
    already in storage. Meta back: the retry finds its own card at that key
    (storage answers 409), carries on, sends once and records once."""
    app, client, fake_meta, fake_storage = rig
    async with client:
        await _stage(client, db)
    fake_meta.fail_sends = True

    await _enqueue(db)
    assert await run_one_job(db, app.state.wa, app.state.storage) is True
    (job,) = await _jobs(db)
    assert job["status"] == "queued" and job["attempts"] == 1
    assert "500" in job["last_error"]
    assert fake_meta.sent == [] and await _outbound(db) == []
    stored = dict(fake_storage.objects)
    assert list(stored) == [_card_path(BRANCH)]

    fake_meta.fail_sends = False
    await db.pool.execute("update jobs set run_after = now() where status = 'queued'")
    assert await run_one_job(db, app.state.wa, app.state.storage) is True

    (job,) = await _jobs(db)
    assert job["status"] == "done" and job["attempts"] == 2
    assert len(fake_meta.sent) == 1
    assert len(await _outbound(db)) == 1
    assert fake_storage.objects == stored


async def test_a_meta_outage_is_retried_three_times_and_then_failed(rig, db):
    app, client, fake_meta, _ = rig
    async with client:
        await _stage(client, db)
    fake_meta.fail_sends = True

    await _enqueue(db)
    await drain_jobs(db, app, None, release_backoff=True)

    (job,) = await _jobs(db)
    assert job["status"] == "failed" and job["attempts"] == 3
    assert fake_meta.sent == [] and await _outbound(db) == []


async def test_a_template_meta_has_not_approved_fails_with_metas_own_reason(rig, db):
    """Until the founder's submission (issue #16) is approved, Meta answers
    132001 and the job row says so in Meta's words."""
    app, client, fake_meta, _ = rig
    async with client:
        await _stage(client, db)
    fake_meta.template_error = 132001

    await _enqueue(db)
    await drain_jobs(db, app, None, release_backoff=True)

    (job,) = await _jobs(db)
    assert job["status"] == "failed"
    assert "code 132001" in job["last_error"]
    assert fake_meta.sent == []


async def test_an_upload_meta_refuses_fails_the_job_before_any_send(rig, db):
    app, client, fake_meta, fake_storage = rig
    async with client:
        await _stage(client, db)
    fake_meta.fail_uploads = True

    await _enqueue(db)
    assert await run_one_job(db, app.state.wa, app.state.storage) is True

    (job,) = await _jobs(db)
    assert job["status"] == "queued"
    assert fake_meta.sent == [] and await _outbound(db) == []
    assert list(fake_storage.objects) == [_card_path(BRANCH)]  # stored, as the order says


async def test_a_branch_paused_after_the_tick_is_not_sent_to(rig, db, caplog):
    app, client, fake_meta, _ = rig
    async with client:
        await _stage(client, db)
    await _enqueue(db)
    assert await db.pause_incentive_branch(BRANCH, tenant_id=TENANT, actor="console") is True

    with caplog.at_level(logging.INFO, logger="faida_api.worker"):
        assert await run_one_job(db, app.state.wa, app.state.storage) is True
    (job,) = await _jobs(db)
    assert job["status"] == "done"
    assert fake_meta.sent == [] and await _outbound(db) == []
    assert any("paused" in r.getMessage() for r in caplog.records)


async def test_a_branch_that_is_not_the_tenants_fails_the_job_rather_than_guessing(rig, db):
    """C2: the job carries a tenant, and a branch outside it is a refusal
    on the job row, never a card to whichever phone the row names."""
    app, client, fake_meta, _ = rig
    async with client:
        await _stage(client, db)
    await _other_tenant(db)
    await db.pool.execute(
        "update branches set wa_phone_e164 = '971500000099' where id = $1", BRANCH_B
    )
    assert (
        await db.enqueue_scoreboard_once(
            {
                "tenant_id": TENANT,
                "branch_id": BRANCH_B,
                "day": DAY.isoformat(),
                "variant": scoreboard.DAILY,
                "scheme_month_id": None,
            }
        )
        is not None
    )
    await drain_jobs(db, app, None, release_backoff=True)

    (job,) = await _jobs(db)
    assert job["status"] == "failed"
    assert "C2" in job["last_error"] and BRANCH_B in job["last_error"]
    assert fake_meta.sent == []


async def test_a_daily_card_on_a_month_that_went_final_is_a_skip_and_not_a_failure(rig, db, caplog):
    """The owner approved July between the tick and the send: the daily card
    is not composed on a closed month, and the job is done with one log line
    rather than three failed attempts (issue #15's last criterion, from the
    job's side)."""
    app, client, fake_meta, _ = rig
    async with client:
        await _stage(client, db)
        await _rest_of_july(client)
        await _enqueue(db, day=datetime.date(2026, 7, 20))
        approved = await _approve(client, await _july(client))
        assert approved.status_code == 200, approved.text

    with caplog.at_level(logging.INFO, logger="faida_api.worker"):
        # The daily job is the older row and is claimed first; the final one
        # the approval enqueued stays queued behind it.
        assert await run_one_job(db, app.state.wa, app.state.storage) is True
    daily, final = await _jobs(db)
    assert daily["payload"]["variant"] == scoreboard.DAILY
    assert daily["status"] == "done"
    assert final["payload"]["variant"] == scoreboard.FINAL
    assert final["status"] == "queued"
    assert fake_meta.sent == []
    assert any("closed" in r.getMessage() for r in caplog.records)


async def test_approval_enqueues_one_final_job_and_a_second_approval_enqueues_nothing(rig, db):
    """The owner approves Al Barsha's July through the door: exactly one
    `send_scoreboard` job of the final kind for that branch and month, keyed
    on the month's first day and carrying the tenant and the scheme month
    (issue #15's first criterion). A second approval is refused, and the
    queue is as it was; so is a job for the same key enqueued by hand, because
    the index is the guard either way."""
    _, client, _, _ = rig
    async with client:
        await _stage(client, db)
        await _rest_of_july(client)
        read = await _july(client)
        approved = await _approve(client, read)
        assert approved.status_code == 200, approved.text
        (job,) = await _jobs(db)
        assert job["status"] == "queued"
        assert job["payload"] == {
            "tenant_id": TENANT,
            "branch_id": BRANCH,
            "day": "2026-07-01",
            "variant": scoreboard.FINAL,
            "scheme_month_id": read["scheme_month"]["id"],
        }

        again = await _approve(client, read, reason="again, by mistake")
        assert again.status_code == 422, again.text
    assert len(await _jobs(db)) == 1
    assert (
        await db.enqueue_scoreboard_once(
            {**job["payload"], "scheme_month_id": read["scheme_month"]["id"]}
        )
        is None
    )
    assert len(await _jobs(db)) == 1


async def test_an_approval_that_fails_after_its_row_leaves_no_final_job(rig, db, monkeypatch):
    """The approval row, its audit row and the final card's job are one
    transaction: an audit table that refuses leaves none of the three, so a
    card can never go out for a statement that is not final."""
    from faida_api import db as db_module

    async def refuse(*args, **kwargs):
        raise RuntimeError("audit table unavailable")

    _, client, _, _ = rig
    async with client:
        await _stage(client, db)
        await _rest_of_july(client)
        read = await _july(client)
        monkeypatch.setattr(db_module, "_insert_audit_event", refuse)
        with pytest.raises(RuntimeError):
            await _approve(client, read)
    assert await db.pool.fetchval("select count(*) from statement_approvals") == 0
    assert await _jobs(db) == []


async def test_the_approved_card_is_sent_final_and_a_paused_branch_still_receives_it(rig, db):
    """The job the approval enqueued draws the final card - the month named
    as closed, the split by role summing to the pool - stores it under the
    `-final` suffix, sends it with the template and records one outbound row
    on the day's key; the pause does not stop it, because the month is closed
    and the money named (issue #15). The card is byte-identical to the one
    the module draws for the same approved statement, so what the phone gets
    is what the screen shows."""
    app, client, fake_meta, fake_storage = rig
    july = datetime.date(2026, 7, 1)
    async with client:
        await _stage(client, db)
        await _rest_of_july(client)
        approved = await _approve(client, await _july(client))
        assert approved.status_code == 200, approved.text
    assert await db.pause_incentive_branch(BRANCH, tenant_id=TENANT, actor="console") is True

    await drain_jobs(db, app, None)

    (sent,) = fake_meta.sent
    _, body = sent["template"]["components"]
    assert body["parameters"][0]["text"] == "Al Barsha: July 2026 bonus, final"
    (row,) = await _outbound(db)
    assert row["payload"]["variant"] == scoreboard.FINAL
    assert row["payload"]["day"] == "2026-07-01"
    assert row["payload"]["branch_id"] == BRANCH
    assert list(fake_storage.objects) == [_card_path(BRANCH, july, variant="final")]
    (job,) = await _jobs(db)
    assert job["status"] == "done"

    # The stored picture is the module's own drawing of the same approved
    # statement (its words and the split are pinned in `test_scoreboard.py`).
    card = await read_scoreboard(
        db,
        TENANT,
        BRANCH,
        today=worker._local_today("Asia/Dubai"),
        variant=scoreboard.FINAL,
        month=july,
    )
    assert card is not None
    assert fake_storage.objects[_card_path(BRANCH, july, variant="final")] == (
        scoreboard_card.render_card(card)
    )


async def test_the_tick_enqueues_no_morning_card_for_a_branch_whose_month_is_final(rig, db, caplog):
    """Al Barsha's July is approved on the 20th: from then on the tick wakes
    the other two branches and not Al Barsha, with one log line, so a closed
    month costs no job a day to be skipped (issue #15's last criterion, from
    the tick's side)."""
    _, client, _, _ = rig
    async with client:
        await _stage(client, db)
        await _rest_of_july(client)
        approved = await _approve(client, await _july(client))
        assert approved.status_code == 200, approved.text

    later = datetime.date(2026, 7, 21)
    with caplog.at_level(logging.INFO, logger="faida_api.worker"):
        assert await tick_scoreboards(db, _utc(later, 4), spoken=set()) == 2
    jobs = await _jobs(db)
    daily = [j for j in jobs if j["payload"]["variant"] == scoreboard.DAILY]
    assert sorted(j["payload"]["branch_id"] for j in daily) == sorted([BRANCH_2, BRANCH_3])
    assert [j["payload"]["branch_id"] for j in jobs if j["payload"]["variant"] == "final"] == [
        BRANCH
    ]
    assert any("is final" in r.getMessage() for r in caplog.records)


async def test_mondays_card_carries_the_new_weeks_list(rig, db):
    """Two mornings across the week boundary: Sunday's card is the first
    week's list (karak, 1-5 Jul) and Monday's the second's (mandi, 6-12
    Jul), each stored under its own day (D13)."""
    app, client, fake_meta, fake_storage = rig
    async with client:
        await _july_with_sales(client, db)  # the seed's branch alone has a phone

    assert await tick_scoreboards(db, _utc(SUNDAY, 3)) == 1
    assert await run_one_job(db, app.state.wa, app.state.storage) is True
    assert await tick_scoreboards(db, _utc(MONDAY, 3)) == 1
    assert await run_one_job(db, app.state.wa, app.state.storage) is True

    sunday = await read_scoreboard(db, TENANT, BRANCH, today=SUNDAY)
    monday = await read_scoreboard(db, TENANT, BRANCH, today=MONDAY)
    assert [item.name for item in sunday.weeks[0].items] == ["Karak Cup"]
    assert [item.name for item in monday.weeks[0].items] == ["Chicken Mandi"]
    assert sunday.list_title == "This week's push list, 1-5 Jul"
    assert monday.list_title == "This week's push list, 6-12 Jul"

    assert fake_storage.objects == {
        _card_path(BRANCH, SUNDAY): scoreboard_card.render_card(sunday),
        _card_path(BRANCH, MONDAY): scoreboard_card.render_card(monday),
    }
    assert [s["template"]["components"][1]["parameters"][0]["text"] for s in fake_meta.sent] == [
        "Al Barsha scoreboard, Sun 5 Jul",
        "Al Barsha scoreboard, Mon 6 Jul",
    ]
    assert [row["payload"]["day"] for row in await _outbound(db)] == [
        SUNDAY.isoformat(),
        MONDAY.isoformat(),
    ]


# --- the pause door ------------------------------------------------------------------


async def test_the_pause_door_writes_its_audit_row_and_the_read_shows_the_pause(rig, db):
    _, client, _, _ = rig
    async with client:
        await _stage(client, db)
        paused = await client.post(
            f"/api/incentive/branches/{BRANCH}/pause?month=2026-07", headers=AUTH
        )
        assert paused.status_code == 200, paused.text
        branch = next(b for b in paused.json()["branches"] if b["id"] == BRANCH)
        assert branch["paused_at"] is not None
        assert paused.json()["scheme_month"]["month"] == "2026-07"

        # A second click is not a second decision.
        again = await client.post(f"/api/incentive/branches/{BRANCH}/pause", headers=AUTH)
        assert again.status_code == 200
        assert len(await _audit(db, "incentive.branch_paused")) == 1

        resumed = await client.post(
            f"/api/incentive/branches/{BRANCH}/resume?month=2026-07", headers=AUTH
        )
        assert resumed.status_code == 200, resumed.text
        branch = next(b for b in resumed.json()["branches"] if b["id"] == BRANCH)
        assert branch["paused_at"] is None
        assert len(await _audit(db, "incentive.branch_resumed")) == 1

        unknown = await client.post(f"/api/incentive/branches/{BRANCH_B}/pause", headers=AUTH)
        assert unknown.status_code == 404

    (paused_row,) = await _audit(db, "incentive.branch_paused")
    assert paused_row["subject_id"] == BRANCH
    assert paused_row["actor"].startswith("user:")


# --- the kill switch --------------------------------------------------------------


async def test_the_loop_ticks_the_scoreboard_beside_the_brief_and_not_when_switched_off(
    rig, db, monkeypatch
):
    """`INCENTIVE_ENABLED=false` stops every morning card in one variable
    (D18); on, the scoreboard tick runs on the loop's minute beside the
    brief's, and the brief's own switch does not touch it."""
    app, _, _, _ = rig
    briefs: list = []
    scoreboards: list = []

    async def fake_briefs(database, now_utc, *, spoken=None):
        briefs.append(now_utc)
        return 0

    async def fake_scoreboards(database, now_utc, *, spoken=None):
        scoreboards.append(now_utc)
        return 0

    monkeypatch.setattr(worker, "tick_briefs", fake_briefs)
    monkeypatch.setattr(worker, "tick_scoreboards", fake_scoreboards)

    async def spin(**kwargs) -> None:
        stop = asyncio.Event()
        task = asyncio.create_task(
            worker.worker_loop(db, app.state.wa, app.state.storage, None, stop, 0.01, **kwargs)
        )
        await asyncio.sleep(0.05)
        stop.set()
        await task

    await spin(incentive_enabled=False)
    assert scoreboards == [] and len(briefs) == 1

    briefs.clear()
    await spin(brief_enabled=False)
    assert briefs == [] and len(scoreboards) == 1

    scoreboards.clear()
    await spin()
    assert len(briefs) == 1 and len(scoreboards) == 1 and briefs == scoreboards


# --- the rehearsal ---------------------------------------------------------------


async def test_a_rehearsal_sends_once_through_the_jobs_path_and_stays_outside_the_days_key(rig, db):
    """`--send --to` on the print command: one real send to the founder's
    phone through `send_scoreboard_card`, Meta's message id printed, the row
    marked as a rehearsal - so the morning's own card still goes."""
    app, client, fake_meta, fake_storage = rig
    async with client:
        await _stage(client, db)
    out = StringIO()

    card = await scoreboard_cli.run(
        db,
        app.state.wa,
        app.state.storage,
        tenant_id=TENANT,
        branch_id=BRANCH,
        today=DAY,
        send_to=FOUNDER,
        out=out,
    )
    assert card is not None
    assert "sent to 971559990009 as wamid.out1 (rehearsal)" in out.getvalue()
    (sent,) = fake_meta.sent
    assert sent["to"] == FOUNDER
    assert sent["template"]["name"] == scoreboard.TEMPLATE_NAME
    assert sent["template"]["components"][1]["parameters"][0]["text"] == card.parameters[0]

    rehearsal_path = f"{TENANT}/scoreboards/{DAY.isoformat()}/rehearsal-{BRANCH}-{FOUNDER}.png"
    assert fake_storage.objects == {rehearsal_path: scoreboard_card.render_card(card)}
    (row,) = await _outbound(db)
    assert row["payload"]["rehearsal"] is True
    assert row["payload"]["card_path"] == rehearsal_path
    assert row["payload"]["branch_id"] == BRANCH and row["payload"]["day"] == DAY.isoformat()
    assert (
        await db.outbound_scoreboard_exists(
            branch_id=BRANCH, day=DAY.isoformat(), variant=scoreboard.DAILY
        )
        is False
    )

    # The morning is not silenced by the rehearsal.
    await _enqueue(db)
    assert await run_one_job(db, app.state.wa, app.state.storage) is True
    assert len(fake_meta.sent) == 2 and fake_meta.sent[1]["to"] == DEMO_PHONE
    assert set(fake_storage.objects) == {rehearsal_path, _card_path(BRANCH)}


async def test_a_rehearsal_with_nothing_to_draw_sends_nothing(rig, db):
    app, client, fake_meta, _ = rig
    async with client:
        await _stage(client, db)
    out = StringIO()
    card = await scoreboard_cli.run(
        db,
        app.state.wa,
        app.state.storage,
        tenant_id=TENANT,
        branch_id=BRANCH,
        today=datetime.date(2026, 6, 2),
        send_to=FOUNDER,
        out=out,
    )
    assert card is None
    assert fake_meta.sent == []
    assert "nothing to draw" in out.getvalue()


def test_the_command_line_insists_on_a_phone_for_a_send():
    with pytest.raises(SystemExit):
        scoreboard_cli.parse_args(["--tenant", "t", "--branch", "b", "--send"])
    with pytest.raises(SystemExit):
        scoreboard_cli.parse_args(["--tenant", "t", "--branch", "b", "--to", "971"])
    args = scoreboard_cli.parse_args(["--tenant", "t", "--branch", "b", "--send", "--to", "971"])
    assert args.send is True and args.to == "971"
