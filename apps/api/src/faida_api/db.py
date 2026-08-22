"""Thin asyncpg layer. Plain SQL, no ORM — the database holds data and constraints,
the application holds the logic (plan §2 rule 3)."""

import datetime
import json
from decimal import Decimal
from typing import Any

import asyncpg

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
        invoice_no: str | None,
        invoice_date: datetime.date | None,
        currency: str,
        subtotal: Decimal | None,
        tax: Decimal | None,
        total: Decimal | None,
        payment_kind: str | None,
        status: str,
        confidence: dict,
        lines: list[dict],
    ) -> str:
        """Draft invoice + lines + the document transition, one transaction:
        C1 says 'extracted' means a draft invoice with checks exists, so the
        two can never be observed apart."""
        async with self.pool.acquire() as conn, conn.transaction():
            invoice_id = await conn.fetchval(
                """
                insert into invoices (tenant_id, branch_id, document_id, invoice_no,
                                      invoice_date, currency, subtotal, tax, total,
                                      payment_kind, status, confidence)
                values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                returning id::text
                """,
                tenant_id,
                branch_id,
                document_id,
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
                insert into invoice_lines (invoice_id, position, raw_name, qty, unit,
                                           unit_price, line_total, pack_size, checks)
                values ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                [
                    (
                        invoice_id,
                        line["position"],
                        line["raw_name"],
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
