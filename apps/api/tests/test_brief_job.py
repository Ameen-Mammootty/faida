"""M10 WP-103: the recipient, the morning and the job, against Postgres
(Docs/M10_DECOMPOSITION.md §3 C15.3 to C15.7 and C15.10, §4 row 103, §7).

The filler's words are proven without a database in `test_brief.py`. What is
proven here is everything around them: that the morning comes once, in the
recipient's own timezone; that the job sends one message and records it; that
every way the send can fail leaves the queue and the record honest; and that
an owner writing back to the brief is answered rather than told to ask the
owner.

Meta and storage are mocked at the transport layer as in every flow test, and
the clock is passed into the tick rather than read inside it, so a morning in
Dubai is a fact of the test and not of the machine it runs on.

The sales the briefs are made of are staged through the real doors - the
seeded chain through `POST /api/sales/days` and the menu doors (`_stage`, the
dashboard suite's own three-branch stage), the second tenant through
`db.load_sales_day`, which is the same door the route calls - so the figures
in the message are the figures the dashboard would show for the same reads.
"""

import asyncio
import datetime
import json
import logging
from decimal import Decimal
from io import StringIO

import httpx
import pytest
from fastapi import FastAPI

from faida_api import brief, brief_cli, worker
from faida_api.api import router as api_router
from faida_api.contracts import WA_STATUS_IGNORED_BRIEF_RECIPIENT, JobKind
from faida_api.dashboard import router as dashboard_router
from faida_api.menu import router as menu_router
from faida_api.replies import REPLY_BRIEF_RECIPIENT, REPLY_MEDIA_RECEIVED
from faida_api.sales import router as sales_router
from faida_api.storage import Storage
from faida_api.wa import WhatsAppClient
from faida_api.webhook import router as webhook_router
from faida_api.worker import read_brief, run_one_job, send_brief, tick_briefs

from .conftest import (
    DEMO_PHONE,
    DEMO_TENANT_ID,
    FakeMeta,
    FakeStorage,
    requires_db,
    wa_image_payload,
    wa_text_payload,
    wire_auth,
)
from .test_dashboard import _stage
from .test_extraction_flow import drain_jobs, post_webhook

pytestmark = requires_db

TENANT = DEMO_TENANT_ID
TENANT_B = "b0000000-0000-0000-0000-000000000001"
BRANCH_B = "b0000000-0000-0000-0000-000000000011"
TENANT_C = "c0000000-0000-0000-0000-000000000001"
BRANCH_C = "c0000000-0000-0000-0000-000000000011"

#: An owner's phone: no branch is registered to it, which is the pilot's shape
#: and the case the resolver's second lookup exists for.
OWNER_PHONE = "971559990001"
OWNER_PHONE_B = "971559990002"
OWNER_PHONE_C = "971559990003"

DUBAI = "Asia/Dubai"
SEVEN = datetime.time(7, 0)
EVIDENCE = "the founder's decision of 2026-09-08, M10 P14"

#: The day every send test is about. The staged week ends a fortnight before
#: it, which is the ordinary state of a chain whose till exports weekly - the
#: header says how old the figures are and the brief goes out anyway (P4).
TODAY = datetime.date.today()


def _utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime.datetime:
    return datetime.datetime(year, month, day, hour, minute, tzinfo=datetime.UTC)


@pytest.fixture
def rig(settings, db):
    """One app over the test database: the webhook the resolver tests post to
    and the API routers the sales stage is loaded through, with Meta and
    storage faked at the transport layer."""
    fake_meta = FakeMeta()
    fake_storage = FakeStorage()
    app = FastAPI()
    app.include_router(webhook_router)
    app.include_router(api_router)
    app.include_router(menu_router)
    app.include_router(sales_router)
    app.include_router(dashboard_router)
    app.state.settings = settings
    wire_auth(app)
    app.state.db = db
    app.state.wa = WhatsAppClient(settings, transport=fake_meta.transport())
    app.state.storage = Storage(settings, transport=fake_storage.transport())
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    return app, client, fake_meta, fake_storage


async def _recipient(
    db,
    *,
    tenant_id: str = TENANT,
    phone: str = OWNER_PHONE,
    timezone: str = DUBAI,
    send_at_local: datetime.time = SEVEN,
) -> str:
    return await db.add_brief_recipient(
        tenant_id=tenant_id,
        phone_e164=phone,
        timezone=timezone,
        send_at_local=send_at_local,
        actor=f"whatsapp:{phone}",
        evidence=EVIDENCE,
    )


async def _tenant(db, tenant_id: str, name: str, branch_id: str, branch: str) -> None:
    await db.pool.execute(
        "insert into tenants (id, name, currency) values ($1, $2, 'AED')", tenant_id, name
    )
    await db.pool.execute(
        "insert into branches (id, tenant_id, name, timezone) values ($1, $2, $3, 'Asia/Dubai')",
        branch_id,
        tenant_id,
        branch,
    )


async def _sales(db, *, tenant_id: str, branch_id: str, net: str, days: int = 3) -> None:
    """A few item days for a tenant the API fixture cannot sign in to, through
    the same door the route calls (C11.4). Exclusive amounts, so the net is
    what is printed."""
    for offset in range(days):
        amount = Decimal(net)
        await db.load_sales_day(
            tenant_id=tenant_id,
            branch_id=branch_id,
            business_date=TODAY - datetime.timedelta(days=20 - offset),
            granularity="item",
            amount_basis="exclusive",
            vat_rate=None,
            layout_id=None,
            source_sha256=None,
            source_filename=None,
            lines=[
                {
                    "position": 0,
                    "name": "KARAK",
                    "code": "52",
                    "qty": Decimal("10"),
                    "amount": amount,
                    "net_amount": amount,
                }
            ],
            amount=None,
            net=None,
            actor="test",
        )


async def _jobs(db, kind: str | None = None) -> list:
    if kind is None:
        return await db.pool.fetch("select * from jobs order by id")
    return await db.pool.fetch("select * from jobs where kind = $1 order by id", kind)


async def _brief_jobs(db) -> list:
    return await _jobs(db, JobKind.SEND_BRIEF)


async def _outbound_templates(db) -> list:
    return await db.pool.fetch(
        "select * from wa_messages where direction = 'out' and msg_type = 'template' order by id"
    )


async def _enqueue_brief(db, recipient_id: str, *, tenant_id: str = TENANT, day=TODAY) -> int:
    job_id = await db.enqueue_brief_once(
        {
            "tenant_id": tenant_id,
            "recipient_id": recipient_id,
            "brief_date": day.isoformat(),
        }
    )
    assert job_id is not None
    return job_id


# --- the tick: whose morning has come -------------------------------------------


async def test_the_tick_enqueues_one_job_per_due_recipient_and_a_second_tick_none(rig, db):
    """The unique index is the guard, so a tick that runs every minute all
    morning still leaves one job per recipient per day."""
    _, _, _, _ = rig
    first = await _recipient(db)
    second = await _recipient(db, phone=OWNER_PHONE_B)

    assert await tick_briefs(db, _utc(2026, 9, 8, 3)) == 2
    assert await tick_briefs(db, _utc(2026, 9, 8, 4)) == 0
    assert await tick_briefs(db, _utc(2026, 9, 8, 8)) == 0

    jobs = await _brief_jobs(db)
    assert [job["payload"]["recipient_id"] for job in jobs] == [first, second]
    assert {job["payload"]["brief_date"] for job in jobs} == {"2026-09-08"}
    assert {job["payload"]["tenant_id"] for job in jobs} == {TENANT}
    assert all(job["status"] == "queued" for job in jobs)


async def test_the_morning_is_the_recipients_own_seven_oclock(rig, db):
    """07:00 in Dubai is 03:00 UTC: due then, and not a minute before."""
    _, _, _, _ = rig
    await _recipient(db)

    assert await tick_briefs(db, _utc(2026, 9, 8, 2, 59)) == 0
    assert await _brief_jobs(db) == []

    assert await tick_briefs(db, _utc(2026, 9, 8, 3, 0)) == 1
    (job,) = await _brief_jobs(db)
    assert job["payload"]["brief_date"] == "2026-09-08"


async def test_a_recipient_in_another_timezone_has_another_morning(rig, db):
    """Two recipients, two timezones, two mornings (C15.5). London's 07:00 is
    three hours after Dubai's on this date."""
    _, _, _, _ = rig
    dubai = await _recipient(db)
    london = await _recipient(db, phone=OWNER_PHONE_B, timezone="Europe/London")

    assert await tick_briefs(db, _utc(2026, 9, 8, 3)) == 1
    assert [job["payload"]["recipient_id"] for job in await _brief_jobs(db)] == [dubai]

    assert await tick_briefs(db, _utc(2026, 9, 8, 6)) == 1
    assert [job["payload"]["recipient_id"] for job in await _brief_jobs(db)] == [dubai, london]


async def test_past_noon_the_day_is_skipped_and_said_once(rig, db, caplog):
    """A morning brief in the evening is noise, and tomorrow's is hours away
    (P11). The log line says it once for the day, not once a minute."""
    _, _, _, _ = rig
    recipient = await _recipient(db)
    spoken: set = set()

    with caplog.at_level(logging.INFO, logger="faida_api.worker"):
        assert await tick_briefs(db, _utc(2026, 9, 8, 9), spoken=spoken) == 0
        assert await tick_briefs(db, _utc(2026, 9, 8, 10), spoken=spoken) == 0
    assert await _brief_jobs(db) == []
    skipped = [r for r in caplog.records if "brief skipped" in r.getMessage()]
    assert len(skipped) == 1
    assert recipient in skipped[0].getMessage()

    # The next morning is a new day, and it is sent.
    assert await tick_briefs(db, _utc(2026, 9, 9, 3), spoken=spoken) == 1


async def test_a_paused_recipient_has_no_morning(rig, db):
    _, _, _, _ = rig
    recipient = await _recipient(db)
    assert await db.pause_brief_recipient(recipient, tenant_id=TENANT, actor="console") is True

    assert await tick_briefs(db, _utc(2026, 9, 8, 3)) == 0
    assert await _brief_jobs(db) == []

    assert await db.resume_brief_recipient(recipient, tenant_id=TENANT, actor="console") is True
    assert await tick_briefs(db, _utc(2026, 9, 8, 3)) == 1


async def test_a_timezone_that_does_not_resolve_is_skipped_and_the_next_is_enqueued(
    rig, db, caplog
):
    """One typo must not silence every other recipient."""
    _, _, _, _ = rig
    broken = await _recipient(db, timezone="Mars/Phobos")
    good = await _recipient(db, phone=OWNER_PHONE_B)

    with caplog.at_level(logging.WARNING, logger="faida_api.worker"):
        assert await tick_briefs(db, _utc(2026, 9, 8, 3)) == 1
    (job,) = await _brief_jobs(db)
    assert job["payload"]["recipient_id"] == good
    said = " ".join(r.getMessage() for r in caplog.records)
    assert broken in said and "Mars/Phobos" in said


async def test_a_busy_queue_does_not_starve_the_morning(rig, db):
    """The tick runs on every pass and before a job is claimed, so a backlog
    of extraction cannot push the brief past its window."""
    _, _, _, _ = rig
    await _recipient(db)
    for document_id in (
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
    ):
        await db.enqueue_once(
            JobKind.EXTRACT_DOCUMENT,
            {"document_id": document_id, "tenant_id": TENANT, "branch_id": None},
        )

    assert await tick_briefs(db, _utc(2026, 9, 8, 3)) == 1
    assert len(await _jobs(db, JobKind.EXTRACT_DOCUMENT)) == 2
    assert len(await _brief_jobs(db)) == 1


# --- the job: one message, one row ----------------------------------------------


async def test_the_job_sends_the_template_and_records_what_it_sent(rig, db):
    app, client, fake_meta, _ = rig
    await _stage(client, db)
    recipient = await _recipient(db)
    morning = await read_brief(db, TENANT, today=TODAY)
    assert morning.quiet is False

    await _enqueue_brief(db, recipient)
    assert await run_one_job(db, app.state.wa, app.state.storage) is True

    (sent,) = fake_meta.sent
    assert sent["messaging_product"] == "whatsapp"
    assert sent["to"] == OWNER_PHONE
    assert sent["type"] == "template"
    assert sent["template"]["name"] == brief.TEMPLATE_NAME
    assert sent["template"]["language"] == {"code": brief.TEMPLATE_LANGUAGE}
    # The body alone: the picture header is WP-106's, and until it lands a
    # header component would be Meta's 132000.
    assert [part["type"] for part in sent["template"]["components"]] == ["body"]
    parameters = sent["template"]["components"][0]["parameters"]
    assert len(parameters) == brief.PARAMETER_COUNT
    assert [part["type"] for part in parameters] == ["text"] * brief.PARAMETER_COUNT
    assert [part["text"] for part in parameters] == list(morning.parameters)

    (row,) = await _outbound_templates(db)
    assert row["message_id"] == "wamid.out1"
    assert row["to_phone"] == OWNER_PHONE
    assert row["status"] == "sent"
    assert row["payload"] == {
        "template": brief.TEMPLATE_NAME,
        "language": brief.TEMPLATE_LANGUAGE,
        "parameters": list(morning.parameters),
        "card_path": None,
        "tenant_id": TENANT,
        "recipient_id": recipient,
        "brief_date": TODAY.isoformat(),
        "rehearsal": False,
        "error": None,
    }
    assert (
        await db.outbound_brief_exists(recipient_id=recipient, brief_date=TODAY.isoformat())
    ) is True
    (job,) = await _brief_jobs(db)
    assert job["status"] == "done"


async def test_the_same_payload_run_twice_sends_once(rig, db):
    """The outbound row is the second guard, under the index: a job replayed
    by hand costs no second template."""
    app, client, fake_meta, _ = rig
    await _stage(client, db)
    recipient = await _recipient(db)
    payload = {
        "tenant_id": TENANT,
        "recipient_id": recipient,
        "brief_date": TODAY.isoformat(),
    }

    await _enqueue_brief(db, recipient)
    assert await run_one_job(db, app.state.wa, app.state.storage) is True
    # A second job for the same morning cannot be enqueued at all...
    assert await db.enqueue_brief_once(payload) is None
    # ...and the handler run again on the same payload sends nothing.
    await send_brief(db, app.state.wa, app.state.storage, payload)
    assert len(fake_meta.sent) == 1
    assert len(await _outbound_templates(db)) == 1


async def test_a_meta_outage_is_retried_three_times_and_then_failed(rig, db):
    app, client, fake_meta, _ = rig
    await _stage(client, db)
    recipient = await _recipient(db)
    fake_meta.fail_sends = True

    await _enqueue_brief(db, recipient)
    await drain_jobs(db, app, None, release_backoff=True)

    (job,) = await _brief_jobs(db)
    assert job["status"] == "failed"
    assert job["attempts"] == 3
    assert "500" in job["last_error"]
    assert fake_meta.sent == []
    assert await _outbound_templates(db) == []


@pytest.mark.parametrize("code", [132001, 132000])
async def test_a_template_meta_refuses_fails_with_its_own_reason(rig, db, code):
    """The template not approved yet (132001) and a template edited to a
    different variable count (132000) take the same path, and the reason on
    the job row is Meta's own words rather than a status code."""
    app, client, fake_meta, _ = rig
    await _stage(client, db)
    recipient = await _recipient(db)
    fake_meta.template_error = code

    await _enqueue_brief(db, recipient)
    await drain_jobs(db, app, None, release_backoff=True)

    (job,) = await _brief_jobs(db)
    assert job["status"] == "failed"
    assert job["attempts"] == 3
    assert f"code {code}" in job["last_error"]
    assert fake_meta.sent == []
    assert await _outbound_templates(db) == []


async def test_a_record_write_that_raises_after_the_send_costs_a_second_brief(rig, db, monkeypatch):
    """C15.3's one honest limit, pinned so it is known rather than discovered:
    Meta accepts the message, the record write raises, and the retry - finding
    no row - sends the same brief again. Recording before sending would lose a
    morning instead of repeating one, and the repeat is the better failure."""
    app, client, fake_meta, _ = rig
    await _stage(client, db)
    recipient = await _recipient(db)
    real = db.record_outbound_template

    async def boom(*args, **kwargs):
        raise RuntimeError("the record write fell over")

    monkeypatch.setattr(db, "record_outbound_template", boom)
    await _enqueue_brief(db, recipient)
    assert await run_one_job(db, app.state.wa, app.state.storage) is True

    (job,) = await _brief_jobs(db)
    assert job["status"] == "queued" and job["attempts"] == 1
    assert len(fake_meta.sent) == 1  # the phone has it
    assert await _outbound_templates(db) == []  # and we have no record of it

    monkeypatch.setattr(db, "record_outbound_template", real)
    await db.pool.execute("update jobs set run_after = now() where status = 'queued'")
    assert await run_one_job(db, app.state.wa, app.state.storage) is True

    assert len(fake_meta.sent) == 2  # the same morning, twice
    assert len(await _outbound_templates(db)) == 1
    (job,) = await _brief_jobs(db)
    assert job["status"] == "done"


async def test_a_recipient_deleted_between_the_tick_and_the_send_fails_the_job(rig, db):
    """A job that cannot find its recipient inside its own tenant refuses to
    run rather than guessing a phone (C2)."""
    app, client, fake_meta, _ = rig
    await _stage(client, db)
    recipient = await _recipient(db)
    await _enqueue_brief(db, recipient)
    await db.pool.execute("delete from brief_recipients where id = $1", recipient)

    await drain_jobs(db, app, None, release_backoff=True)
    (job,) = await _brief_jobs(db)
    assert job["status"] == "failed"
    assert recipient in job["last_error"]
    assert fake_meta.sent == []


async def test_a_recipient_paused_after_the_tick_is_not_sent_to(rig, db):
    app, client, fake_meta, _ = rig
    await _stage(client, db)
    recipient = await _recipient(db)
    await _enqueue_brief(db, recipient)
    await db.pause_brief_recipient(recipient, tenant_id=TENANT, actor="console")

    assert await run_one_job(db, app.state.wa, app.state.storage) is True
    (job,) = await _brief_jobs(db)
    assert job["status"] == "done"
    assert fake_meta.sent == []
    assert await _outbound_templates(db) == []


async def test_two_tenants_each_get_their_own_figures(rig, db):
    """The one thing a brief must never do: carry one chain's money to another
    chain's phone."""
    app, client, fake_meta, _ = rig
    await _stage(client, db)
    await _tenant(db, TENANT_B, "Other Chain", BRANCH_B, "Elsewhere")
    await _sales(db, tenant_id=TENANT_B, branch_id=BRANCH_B, net="777.00")

    first = await _recipient(db)
    second = await _recipient(db, tenant_id=TENANT_B, phone=OWNER_PHONE_B)
    mine = await read_brief(db, TENANT, today=TODAY)
    theirs = await read_brief(db, TENANT_B, today=TODAY)
    assert mine.quiet is False and theirs.quiet is False
    assert mine.parameters != theirs.parameters

    await _enqueue_brief(db, first)
    await _enqueue_brief(db, second, tenant_id=TENANT_B)
    await drain_jobs(db, app, None)

    rows = {row["to_phone"]: row for row in await _outbound_templates(db)}
    assert set(rows) == {OWNER_PHONE, OWNER_PHONE_B}
    assert rows[OWNER_PHONE]["payload"]["tenant_id"] == TENANT
    assert rows[OWNER_PHONE]["payload"]["parameters"] == list(mine.parameters)
    assert rows[OWNER_PHONE_B]["payload"]["tenant_id"] == TENANT_B
    assert rows[OWNER_PHONE_B]["payload"]["parameters"] == list(theirs.parameters)
    assert "777" in rows[OWNER_PHONE_B]["payload"]["parameters"][1]
    assert "777" not in rows[OWNER_PHONE]["payload"]["parameters"][1]


async def test_a_tenant_with_nothing_loaded_sends_nothing_and_says_so(rig, db, caplog):
    """A template costs money and there is nothing to say (C15.7)."""
    app, _, fake_meta, _ = rig
    await _tenant(db, TENANT_C, "New Chain", BRANCH_C, "First Branch")
    recipient = await _recipient(db, tenant_id=TENANT_C, phone=OWNER_PHONE_C)
    await _enqueue_brief(db, recipient, tenant_id=TENANT_C)

    with caplog.at_level(logging.INFO, logger="faida_api.worker"):
        assert await run_one_job(db, app.state.wa, app.state.storage) is True

    (job,) = await _brief_jobs(db)
    assert job["status"] == "done"
    assert fake_meta.sent == []
    assert await _outbound_templates(db) == []
    assert any(
        f"brief skipped: nothing loaded for tenant {TENANT_C}" in record.getMessage()
        for record in caplog.records
    )


# --- the stranded job (P12) ------------------------------------------------------


async def test_a_job_left_running_is_reclaimed_once_it_is_stale_and_never_while_fresh(rig, db):
    """A process killed mid-job leaves its row `running`; nothing used to look
    at those rows again, and a morning brief that strands shows on no screen.
    The reclaim is for every kind, which is why an extract job is here too."""
    _, _, _, _ = rig
    recipient = await _recipient(db)
    extract_id = await db.enqueue_once(
        JobKind.EXTRACT_DOCUMENT,
        {
            "document_id": "33333333-3333-3333-3333-333333333333",
            "tenant_id": TENANT,
            "branch_id": None,
        },
    )
    brief_id = await _enqueue_brief(db, recipient)

    claimed = [await db.claim_job(), await db.claim_job()]
    assert [job["id"] for job in claimed] == [extract_id, brief_id]
    # Both are running and fresh: nothing else may take them.
    assert await db.claim_job() is None

    await db.pool.execute(
        "update jobs set updated_at = now() - interval '11 minutes' where id = any($1::bigint[])",
        [extract_id, brief_id],
    )
    reclaimed = [await db.claim_job(), await db.claim_job()]
    assert [job["id"] for job in reclaimed] == [extract_id, brief_id]
    # The attempt the handler sees is the pre-claim count plus one, as it is
    # for every other claim - so a job that strands three times fails.
    assert [job["attempts"] for job in reclaimed] == [1, 1]
    rows = await _jobs(db)
    assert [row["attempts"] for row in rows] == [2, 2]
    assert [row["status"] for row in rows] == ["running", "running"]

    # And the reclaim resets the clock: never twice in a row.
    assert await db.claim_job() is None


# --- the owner writes back (C15.10) ----------------------------------------------


async def test_a_recipient_texting_in_is_told_what_the_number_is_for_once_a_day(rig, db):
    app, client, fake_meta, fake_storage = rig
    await _recipient(db)

    await post_webhook(client, wa_text_payload("thanks", "wamid.o1", from_phone=OWNER_PHONE))
    assert await run_one_job(db, app.state.wa, app.state.storage) is True

    inbound = await db.get_inbound_message("wamid.o1")
    assert inbound["status"] == WA_STATUS_IGNORED_BRIEF_RECIPIENT
    assert [(m["to"], m["text"]["body"]) for m in fake_meta.sent] == [
        (OWNER_PHONE, REPLY_BRIEF_RECIPIENT)
    ]
    # Nothing was created for the phone, exactly as for a phone we do not know.
    assert await db.pool.fetchval("select count(*) from documents") == 0
    assert fake_storage.objects == {}
    assert await _jobs(db, JobKind.EXTRACT_DOCUMENT) == []

    # A second message the same day is stamped and answered with silence.
    await post_webhook(client, wa_text_payload("ok", "wamid.o2", from_phone=OWNER_PHONE))
    assert await run_one_job(db, app.state.wa, app.state.storage) is True
    assert (await db.get_inbound_message("wamid.o2"))["status"] == WA_STATUS_IGNORED_BRIEF_RECIPIENT
    assert len(fake_meta.sent) == 1

    # A day later it is answered again, and never with the unknown sender's
    # sentence: this is the owner's own phone.
    await db.pool.execute(
        "update wa_messages set created_at = now() - interval '25 hours' where direction = 'in'"
    )
    await post_webhook(client, wa_text_payload("hello", "wamid.o3", from_phone=OWNER_PHONE))
    assert await run_one_job(db, app.state.wa, app.state.storage) is True
    assert [m["text"]["body"] for m in fake_meta.sent] == [REPLY_BRIEF_RECIPIENT] * 2


async def test_a_phone_that_is_a_branch_and_a_recipient_is_a_branch(rig, db):
    """The founder's own handset is both, and forwarding an invoice from it
    must keep working (C5 unchanged)."""
    app, client, fake_meta, fake_storage = rig
    await _recipient(db, phone=DEMO_PHONE)

    await post_webhook(client, wa_image_payload(message_id="wamid.both"))
    assert await run_one_job(db, app.state.wa, app.state.storage) is True

    inbound = await db.get_inbound_message("wamid.both")
    assert inbound["status"] != WA_STATUS_IGNORED_BRIEF_RECIPIENT
    assert [m["text"]["body"] for m in fake_meta.sent] == [REPLY_MEDIA_RECEIVED]
    document = await db.get_document_by_wa_message("wamid.both")
    assert document is not None and str(document["tenant_id"]) == TENANT
    assert len(await _jobs(db, JobKind.EXTRACT_DOCUMENT)) == 1


# --- the record of the decision (C8 extended) ------------------------------------


async def test_adding_pausing_and_resuming_a_recipient_each_leave_one_audit_row(rig, db):
    _, _, _, _ = rig
    recipient = await _recipient(db)
    assert await db.pause_brief_recipient(recipient, tenant_id=TENANT, actor="console") is True
    # A second pause changes nothing and records nothing.
    assert await db.pause_brief_recipient(recipient, tenant_id=TENANT, actor="console") is False
    assert await db.resume_brief_recipient(recipient, tenant_id=TENANT, actor="console") is True
    assert await db.resume_brief_recipient(recipient, tenant_id=TENANT, actor="console") is False

    rows = await db.pool.fetch(
        "select * from audit_events where subject_type = 'brief_recipient' order by id"
    )
    assert [row["action"] for row in rows] == [
        "brief_recipient.added",
        "brief_recipient.paused",
        "brief_recipient.resumed",
    ]
    assert [str(row["subject_id"]) for row in rows] == [recipient] * 3
    assert [str(row["tenant_id"]) for row in rows] == [TENANT] * 3
    assert [row["actor"] for row in rows] == [f"whatsapp:{OWNER_PHONE}", "console", "console"]
    assert rows[0]["detail"] == {
        "phone_e164": OWNER_PHONE,
        "timezone": DUBAI,
        "send_at_local": "07:00",
        "evidence": EVIDENCE,
    }


async def test_another_tenants_recipient_does_not_exist_for_this_one(rig, db):
    """The scoped read every console-reachable door takes (C10): a row outside
    the tenant is None, and pausing it changes nothing."""
    _, _, _, _ = rig
    await _tenant(db, TENANT_B, "Other Chain", BRANCH_B, "Elsewhere")
    theirs = await _recipient(db, tenant_id=TENANT_B, phone=OWNER_PHONE_B)

    assert await db.get_brief_recipient(theirs, tenant_id=TENANT) is None
    assert await db.get_brief_recipient(theirs, tenant_id=TENANT_B) is not None
    assert await db.pause_brief_recipient(theirs, tenant_id=TENANT, actor="console") is False
    assert (
        await db.pool.fetchval("select paused_at from brief_recipients where id = $1", theirs)
    ) is None


# --- the dry run and the rehearsal -----------------------------------------------


async def test_the_printed_brief_is_the_brief_the_job_sends(rig, db):
    """The command line and the 07:00 job make the same two reads through the
    same function, so what the founder reads on a terminal is what the phone
    will show."""
    _, client, _, _ = rig
    await _stage(client, db)
    morning = await read_brief(db, TENANT, today=TODAY)

    out = StringIO()
    assert await brief_cli.run(db, None, tenant_id=TENANT, today=TODAY, out=out) is None
    printed = out.getvalue()

    rendered = brief.render(morning)
    assert printed.startswith(rendered + "\n\n")
    assert json.loads(printed[len(rendered) + 2 :]) == list(morning.parameters)


async def test_the_dry_run_on_an_empty_tenant_says_there_is_nothing_to_send(rig, db):
    _, _, _, _ = rig
    await _tenant(db, TENANT_C, "New Chain", BRANCH_C, "First Branch")
    out = StringIO()
    assert await brief_cli.run(db, None, tenant_id=TENANT_C, today=TODAY, out=out) is None
    assert out.getvalue().strip() == brief_cli.NOTHING_TO_SEND.format(tenant_id=TENANT_C)


async def test_a_rehearsal_sends_once_and_stays_outside_the_days_key(rig, db):
    """The founder proving the template at four in the afternoon must not
    silence the next morning's brief."""
    app, client, fake_meta, _ = rig
    await _stage(client, db)
    recipient = await _recipient(db)
    out = StringIO()

    message_id = await brief_cli.run(
        db, app.state.wa, tenant_id=TENANT, today=TODAY, send_to=OWNER_PHONE, out=out
    )
    assert message_id == "wamid.out1"
    assert message_id in out.getvalue()

    (sent,) = fake_meta.sent
    assert sent["type"] == "template"
    assert [part["type"] for part in sent["template"]["components"]] == ["body"]

    (row,) = await _outbound_templates(db)
    assert row["payload"]["rehearsal"] is True
    assert row["payload"]["recipient_id"] == recipient
    assert (
        await db.outbound_brief_exists(recipient_id=recipient, brief_date=TODAY.isoformat())
    ) is False

    # So the morning still goes out, and there are two rows for the day.
    await _enqueue_brief(db, recipient)
    assert await run_one_job(db, app.state.wa, app.state.storage) is True
    rows = await _outbound_templates(db)
    assert [r["payload"]["rehearsal"] for r in rows] == [True, False]


# --- the loop's own habit ---------------------------------------------------------


async def test_the_loop_ticks_once_a_minute_and_not_at_all_when_the_switch_is_off(
    rig, db, monkeypatch
):
    """The tick is the whole scheduler, so two promises are worth pinning: it
    happens without anything else asking, and `BRIEF_ENABLED=false` stops every
    send in one variable (C15.5). The clock is the loop's, not the test's -
    what is counted is how often the loop decides to look."""
    app, _, _, _ = rig
    looked: list[datetime.datetime] = []

    async def fake_tick(database, now_utc, *, spoken=None):
        looked.append(now_utc)
        return 0

    monkeypatch.setattr(worker, "tick_briefs", fake_tick)

    async def spin(**kwargs) -> None:
        stop = asyncio.Event()
        task = asyncio.create_task(
            worker.worker_loop(db, app.state.wa, app.state.storage, None, stop, 0.01, **kwargs)
        )
        await asyncio.sleep(0.05)  # several passes of an empty queue
        stop.set()
        await task

    await spin(brief_enabled=False)
    assert looked == []

    await spin()
    # Many passes, one look: the queue is polled every few milliseconds here
    # and the calendar is not.
    assert len(looked) == 1
