"""Thin asyncpg layer. Plain SQL, no ORM — the database holds data and constraints,
the application holds the logic (plan §2 rule 3)."""

import datetime
import json
from decimal import Decimal
from typing import Any

import asyncpg

from .contracts import InvoiceStatus
from .matching import clean_name

RETRY_LIMIT = 3
RETRY_BACKOFF_SECONDS = 30


async def _init_conn(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


class Database:
    def __init__(self, dsn: str):
        self._dsn = dsn
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=5, init=_init_conn)

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()

    async def ping(self) -> bool:
        try:
            await self.pool.fetchval("select 1")
            return True
        except Exception:
            return False

    # -- WhatsApp messages ---------------------------------------------------

    async def record_inbound_message(
        self, message_id: str, from_phone: str | None, msg_type: str | None, payload: dict
    ) -> bool:
        """Insert an inbound message; returns False if we've already seen message_id."""
        row = await self.pool.fetchrow(
            """
            insert into wa_messages (message_id, direction, from_phone, msg_type, payload)
            values ($1, 'in', $2, $3, $4)
            on conflict (message_id) do nothing
            returning id
            """,
            message_id,
            from_phone,
            msg_type,
            payload,
        )
        return row is not None

    async def record_outbound_message(self, message_id: str, to_phone: str, body: str) -> None:
        await self.pool.execute(
            """
            insert into wa_messages (message_id, direction, to_phone, msg_type, payload, status)
            values ($1, 'out', $2, 'text', $3, 'sent')
            on conflict (message_id) do nothing
            """,
            message_id,
            to_phone,
            {"text": body},
        )

    async def get_inbound_message(self, message_id: str) -> asyncpg.Record | None:
        return await self.pool.fetchrow(
            "select * from wa_messages where message_id = $1 and direction = 'in'", message_id
        )

    # -- Tenancy -------------------------------------------------------------

    async def branch_for_phone(self, phone: str) -> asyncpg.Record | None:
        return await self.pool.fetchrow(
            "select id, tenant_id from branches where wa_phone_e164 = $1", phone
        )

    async def default_tenant_id(self) -> str | None:
        return await self.pool.fetchval("select id::text from tenants order by created_at limit 1")

    async def get_branch(self, branch_id: str) -> asyncpg.Record | None:
        return await self.pool.fetchrow(
            "select id, tenant_id, name from branches where id = $1", branch_id
        )

    # -- Public waitlist -----------------------------------------------------

    async def insert_waitlist_signup(self, email: str) -> bool:
        """Store one normalized address; duplicates are a successful no-op."""
        row = await self.pool.fetchrow(
            """
            insert into waitlist_signups (email)
            values ($1)
            on conflict (email) do nothing
            returning id
            """,
            email,
        )
        return row is not None

    # -- Documents -----------------------------------------------------------

    async def get_document_by_wa_message(self, wa_message_id: str) -> asyncpg.Record | None:
        return await self.pool.fetchrow(
            "select * from documents where wa_message_id = $1", wa_message_id
        )

    async def insert_document(
        self,
        tenant_id: str,
        branch_id: str | None,
        wa_message_id: str,
        mime: str,
        sha256: str,
    ) -> str:
        return await self.pool.fetchval(
            """
            insert into documents (tenant_id, branch_id, source, wa_message_id, mime, sha256)
            values ($1, $2, 'whatsapp', $3, $4, $5)
            returning id::text
            """,
            tenant_id,
            branch_id,
            wa_message_id,
            mime,
            sha256,
        )

    async def insert_uploaded_document(
        self, tenant_id: str, branch_id: str | None, mime: str, sha256: str
    ) -> str:
        """A manually uploaded original (C6 POST /api/documents): same document
        row as the WhatsApp path minus the message, source 'upload'."""
        return await self.pool.fetchval(
            """
            insert into documents (tenant_id, branch_id, source, mime, sha256)
            values ($1, $2, 'upload', $3, $4)
            returning id::text
            """,
            tenant_id,
            branch_id,
            mime,
            sha256,
        )

    async def set_document_storage_path(self, document_id: str, storage_path: str) -> None:
        await self.pool.execute(
            "update documents set storage_path = $2 where id = $1", document_id, storage_path
        )

    async def get_document(self, document_id: str) -> asyncpg.Record | None:
        return await self.pool.fetchrow("select * from documents where id = $1", document_id)

    async def set_document_status(
        self, document_id: str, status: str, classification: str | None = None
    ) -> None:
        """C1 transition, worker-owned. A classification (invoice/z_report/other)
        sticks once recorded; passing None leaves it untouched."""
        await self.pool.execute(
            "update documents set status = $2, classification = coalesce($3, classification) "
            "where id = $1",
            document_id,
            status,
            classification,
        )

    # -- Invoices (WP-13) ----------------------------------------------------

    async def get_invoice_by_document(self, document_id: str) -> asyncpg.Record | None:
        return await self.pool.fetchrow(
            "select * from invoices where document_id = $1", document_id
        )

    async def insert_draft_invoice(
        self,
        *,
        tenant_id: str,
        branch_id: str | None,
        document_id: str,
        supplier_id: str | None,
        supplier_name: str | None,
        invoice_no: str | None,
        invoice_date: datetime.date | None,
        currency: str,
        subtotal: Decimal | None,
        tax: Decimal | None,
        total: Decimal | None,
        payment_kind: str | None,
        status: str = InvoiceStatus.AWAITING_CONFIRM,
        confidence: dict,
        lines: list[dict],
    ) -> str:
        """Draft invoice + lines + the document transition, one transaction:
        C1 says 'extracted' means a draft invoice with checks exists, so the
        two can never be observed apart. The insert takes the post-transition
        status directly (C1 permits draft -> awaiting_confirm; cash invoices
        pass needs_review, WP-24)."""
        async with self.pool.acquire() as conn, conn.transaction():
            invoice_id = await conn.fetchval(
                """
                insert into invoices (tenant_id, branch_id, document_id, supplier_id,
                                      supplier_name, invoice_no, invoice_date, currency,
                                      subtotal, tax, total, payment_kind, status, confidence)
                values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                returning id::text
                """,
                tenant_id,
                branch_id,
                document_id,
                supplier_id,
                supplier_name,
                invoice_no,
                invoice_date,
                currency,
                subtotal,
                tax,
                total,
                payment_kind,
                status,
                confidence,
            )
            await conn.executemany(
                """
                insert into invoice_lines (invoice_id, position, raw_name, supplier_item_id,
                                           qty, unit, unit_price, line_total, pack_size, checks)
                values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                [
                    (
                        invoice_id,
                        line["position"],
                        line["raw_name"],
                        line["supplier_item_id"],
                        line["qty"],
                        line["unit"],
                        line["unit_price"],
                        line["line_total"],
                        line["pack_size"],
                        line["checks"],
                    )
                    for line in lines
                ],
            )
            await conn.execute(
                "update documents set status = 'extracted', classification = 'invoice' "
                "where id = $1",
                document_id,
            )
        return invoice_id

    # -- Review screen API (WP-30, C6) ---------------------------------------

    async def list_invoices(
        self,
        *,
        branch_id: str | None = None,
        supplier_id: str | None = None,
        status: str | None = None,
    ) -> list[asyncpg.Record]:
        """C6 invoice list, newest first; every filter optional. Carries the
        branch name (WP-32: the list shows names, not UUIDs)."""
        return await self.pool.fetch(
            """
            select i.id, i.supplier_name, i.supplier_id, i.invoice_no, i.invoice_date,
                   i.currency, i.total, i.status, i.created_at, i.branch_id, i.document_id,
                   b.name as branch_name
            from invoices i
            left join branches b on b.id = i.branch_id
            where ($1::uuid is null or i.branch_id = $1)
              and ($2::uuid is null or i.supplier_id = $2)
              and ($3::text is null or i.status = $3)
            order by i.created_at desc, i.id desc
            """,
            branch_id,
            supplier_id,
            status,
        )

    async def get_supplier_item(self, item_id: str) -> asyncpg.Record | None:
        return await self.pool.fetchrow(
            """
            select id, canonical_name, unit, pack_size, last_price, prev_price, last_price_at
            from supplier_items where id = $1
            """,
            item_id,
        )

    async def list_item_prices(self, item_id: str) -> list[asyncpg.Record]:
        """One item's confirmed price history, oldest first (the C6 sparkline
        draws left to right)."""
        return await self.pool.fetch(
            """
            select price, observed_at, invoice_id
            from supplier_item_prices
            where supplier_item_id = $1
            order by observed_at, id
            """,
            item_id,
        )

    # -- Supplier memory (WP-22, plan.md §5 layer 4) -------------------------

    async def list_suppliers(self, tenant_id: str) -> list[asyncpg.Record]:
        return await self.pool.fetch(
            "select id, name, name_aliases from suppliers where tenant_id = $1", tenant_id
        )

    async def list_supplier_items(self, supplier_id: str) -> list[asyncpg.Record]:
        return await self.pool.fetch(
            """
            select id, canonical_name, unit, pack_size, last_price, prev_price, last_price_at
            from supplier_items where supplier_id = $1
            """,
            supplier_id,
        )

    async def record_confirmed_prices(self, invoice_id: str) -> None:
        """On confirm (called by the WP-21 flow), one transaction: the catalog
        self-builds and the price baseline moves - never before confirm, so an
        unconfirmed invoice can't pollute it (plan.md §5 layer 4, §6 M2).

        For each line with qty and unit_price: create the supplier item when
        the line didn't snap (canonical_name = cleaned raw_name; the supplier
        itself is created from the raw extracted supplier_name when the invoice
        has none), append the price observation (idempotent per invoice via
        the 0003 partial unique index), and shift prev/last price only when
        this invoice's observation is new AND the price actually changed -
        re-running for the same invoice is a no-op."""
        async with self.pool.acquire() as conn, conn.transaction():
            invoice = await conn.fetchrow(
                "select tenant_id, supplier_id, supplier_name from invoices where id = $1",
                invoice_id,
            )
            if invoice is None:
                raise ValueError(f"invoice {invoice_id} not found")

            supplier_id = invoice["supplier_id"]
            if supplier_id is None:
                supplier_name = clean_name(invoice["supplier_name"] or "")
                if not supplier_name:
                    return  # no supplier and no name to create one from
                supplier_id = await conn.fetchval(
                    """
                    insert into suppliers (tenant_id, name) values ($1, $2)
                    on conflict (tenant_id, name) do update set name = excluded.name
                    returning id
                    """,
                    invoice["tenant_id"],
                    supplier_name,
                )
                await conn.execute(
                    "update invoices set supplier_id = $2 where id = $1", invoice_id, supplier_id
                )

            lines = await conn.fetch(
                """
                select id, raw_name, supplier_item_id, qty, unit, pack_size, unit_price
                from invoice_lines where invoice_id = $1 order by position
                """,
                invoice_id,
            )
            for line in lines:
                if line["qty"] is None or line["unit_price"] is None:
                    continue
                item_id = line["supplier_item_id"]
                if item_id is None:
                    canonical_name = clean_name(line["raw_name"])
                    if not canonical_name:
                        continue
                    item_id = await conn.fetchval(
                        """
                        insert into supplier_items (tenant_id, supplier_id, canonical_name,
                                                    unit, pack_size)
                        values ($1, $2, $3, $4, $5)
                        on conflict (supplier_id, canonical_name)
                          do update set canonical_name = excluded.canonical_name
                        returning id
                        """,
                        invoice["tenant_id"],
                        supplier_id,
                        canonical_name,
                        line["unit"],
                        line["pack_size"],
                    )
                    await conn.execute(
                        "update invoice_lines set supplier_item_id = $2 where id = $1",
                        line["id"],
                        item_id,
                    )
                # The history append doubles as the idempotency marker: when
                # this (item, invoice) observation already exists, a re-run
                # must not shuffle prev_price either.
                observed = await conn.fetchval(
                    """
                    insert into supplier_item_prices (supplier_item_id, price, invoice_id)
                    values ($1, $2, $3)
                    on conflict (supplier_item_id, invoice_id) where invoice_id is not null
                      do nothing
                    returning id
                    """,
                    item_id,
                    line["unit_price"],
                    invoice_id,
                )
                if observed is None:
                    continue
                await conn.execute(
                    """
                    update supplier_items
                    set prev_price = last_price, last_price = $2, last_price_at = now()
                    where id = $1 and last_price is distinct from $2
                    """,
                    item_id,
                    line["unit_price"],
                )

    # -- Confirm flow (WP-21, C5) --------------------------------------------

    async def awaiting_confirm_invoices_for_phone(self, phone: str) -> list[asyncpg.Record]:
        """C5: the awaiting_confirm invoices whose document traces back to
        sender phone, newest first (the flow's default target and the
        disambiguation list order). Cash invoices are needs_review and never
        appear here - chat cannot confirm them (M6 owns approvals)."""
        return await self.pool.fetch(
            """
            select i.id, i.supplier_name, i.currency, i.total, i.created_at, b.timezone
            from invoices i
            join documents d on d.id = i.document_id
            join wa_messages m on m.message_id = d.wa_message_id and m.direction = 'in'
            left join branches b on b.id = i.branch_id
            where m.from_phone = $1 and i.status = 'awaiting_confirm'
            order by i.created_at desc, i.id desc
            """,
            phone,
        )

    async def latest_confirmed_invoice_for_phone(
        self, phone: str, confirmed_after: datetime.datetime | None = None
    ) -> asyncpg.Record | None:
        """The newest confirmed invoice traced to sender phone, optionally
        only when confirmed at/after a moment. With the inbound message's
        arrival time, that answers 'did this text already confirm something?'
        - the confirm flow's retry guard (job re-runs must not double-confirm)
        and its duplicate-OK re-ack."""
        return await self.pool.fetchrow(
            """
            select i.id, i.supplier_name, i.currency, i.total, i.confirmed_at
            from invoices i
            join documents d on d.id = i.document_id
            join wa_messages m on m.message_id = d.wa_message_id and m.direction = 'in'
            where m.from_phone = $1
              and i.status = 'confirmed'
              and ($2::timestamptz is null or i.confirmed_at >= $2)
            order by i.confirmed_at desc nulls last, i.id desc
            limit 1
            """,
            phone,
            confirmed_after,
        )

    async def get_invoice(self, invoice_id: str) -> asyncpg.Record | None:
        """One invoice row plus its branch name (C6 detail shows names)."""
        return await self.pool.fetchrow(
            """
            select i.*, b.name as branch_name
            from invoices i
            left join branches b on b.id = i.branch_id
            where i.id = $1
            """,
            invoice_id,
        )

    async def get_invoice_lines(self, invoice_id: str) -> list[asyncpg.Record]:
        return await self.pool.fetch(
            "select * from invoice_lines where invoice_id = $1 order by position", invoice_id
        )

    async def confirm_invoice(self, invoice_id: str) -> bool:
        """C1, one transaction: invoice awaiting_confirm -> confirmed (stamping
        confirmed_at) and its document extracted -> confirmed. Returns False
        without touching anything when the invoice was not awaiting_confirm
        (already confirmed, or held needs_review) - safe to re-run."""
        async with self.pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                """
                update invoices set status = 'confirmed', confirmed_at = now()
                where id = $1 and status = 'awaiting_confirm'
                returning document_id
                """,
                invoice_id,
            )
            if row is None:
                return False
            await conn.execute(
                "update documents set status = 'confirmed' where id = $1", row["document_id"]
            )
            return True

    async def confirm_reviewed_invoice(self, invoice_id: str) -> bool:
        """C1, the review-screen path (WP-30): invoice needs_review ->
        confirmed (stamping confirmed_at) and its document extracted ->
        confirmed, one transaction. The review screen is the cash approval
        path until M6 (plan.md §6 M2). Returns False without touching
        anything when the invoice was not needs_review - safe to re-run."""
        async with self.pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                """
                update invoices set status = 'confirmed', confirmed_at = now()
                where id = $1 and status = 'needs_review'
                returning document_id
                """,
                invoice_id,
            )
            if row is None:
                return False
            await conn.execute(
                "update documents set status = 'confirmed' where id = $1", row["document_id"]
            )
            return True

    async def apply_invoice_correction(
        self,
        invoice_id: str,
        *,
        subtotal: Decimal | None,
        tax: Decimal | None,
        total: Decimal | None,
        confidence: dict,
        lines: list[dict],
    ) -> None:
        """Persist a chat correction (WP-21), one transaction: header money
        fields + refreshed confidence on the invoice, and per line the fields
        the grammar can change plus the re-derived checks. Status is not
        touched - corrections keep the invoice awaiting_confirm (C1)."""
        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute(
                """
                update invoices set subtotal = $2, tax = $3, total = $4, confidence = $5
                where id = $1
                """,
                invoice_id,
                subtotal,
                tax,
                total,
                confidence,
            )
            await conn.executemany(
                """
                update invoice_lines
                set raw_name = $3, supplier_item_id = $4, qty = $5, unit_price = $6,
                    line_total = $7, checks = $8
                where invoice_id = $1 and position = $2
                """,
                [
                    (
                        invoice_id,
                        line["position"],
                        line["raw_name"],
                        line["supplier_item_id"],
                        line["qty"],
                        line["unit_price"],
                        line["line_total"],
                        line["checks"],
                    )
                    for line in lines
                ],
            )

    # -- Extraction runs (WP-13) ---------------------------------------------

    async def insert_extraction_run(
        self,
        document_id: str,
        *,
        model_id: str,
        prompt_version: str,
        input_tokens: int | None,
        output_tokens: int | None,
        latency_ms: int | None,
        repair_applied: bool,
        outcome: str,
    ) -> None:
        await self.pool.execute(
            """
            insert into extraction_runs (document_id, model_id, prompt_version, input_tokens,
                                         output_tokens, latency_ms, repair_applied, outcome)
            values ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            document_id,
            model_id,
            prompt_version,
            input_tokens,
            output_tokens,
            latency_ms,
            repair_applied,
            outcome,
        )

    # -- Jobs ----------------------------------------------------------------

    async def enqueue(self, kind: str, payload: dict[str, Any]) -> int:
        return await self.pool.fetchval(
            "insert into jobs (kind, payload) values ($1, $2) returning id", kind, payload
        )

    async def claim_job(self) -> asyncpg.Record | None:
        """Claim one queued job (SKIP LOCKED so multiple workers stay safe later)."""
        async with self.pool.acquire() as conn, conn.transaction():
            job = await conn.fetchrow(
                """
                select * from jobs
                where status = 'queued' and run_after <= now()
                order by id
                limit 1
                for update skip locked
                """
            )
            if job is None:
                return None
            await conn.execute(
                """
                update jobs
                set status = 'running', attempts = attempts + 1, updated_at = now()
                where id = $1
                """,
                job["id"],
            )
            return job

    async def finish_job(self, job_id: int, *, ok: bool, error: str | None = None) -> None:
        if ok:
            await self.pool.execute(
                "update jobs set status = 'done', last_error = null, updated_at = now() "
                "where id = $1",
                job_id,
            )
            return
        await self.pool.execute(
            f"""
            update jobs
            set status = case when attempts >= $2 then 'failed' else 'queued' end,
                run_after = now() + interval '{RETRY_BACKOFF_SECONDS} seconds',
                last_error = $3,
                updated_at = now()
            where id = $1
            """,
            job_id,
            RETRY_LIMIT,
            error,
        )
