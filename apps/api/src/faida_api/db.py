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


PRICE_QUANTUM = Decimal("0.001")  # supplier_items.last_price is numeric(12,3)


def _net_price_factor(
    tax_treatment: str | None, tax: Decimal | None, total: Decimal | None
) -> Decimal | None:
    """C4 net-canonical price memory: the multiplier that turns this invoice's
    as-printed unit prices into ex-VAT ones.

    None means "already net, leave it alone" - which covers every exclusive
    invoice and anything we could not resolve. The factor is derived from the
    invoice's own totals, not from the stored vat_rate, so a rounded rate can
    never shift a recorded price.

    This exists because PRICE_ALERT_MIN_PCT is 5% and UAE VAT is 5%: mixing
    gross and net in the same item's history makes a supplier changing invoice
    format fire a full-threshold alert when no price moved.
    """
    if tax_treatment != "inclusive" or tax is None or total is None:
        return None
    if total <= 0 or tax <= 0 or tax >= total:
        return None
    return (total - tax) / total


def _discount_factor(discount: Decimal | None, stock_sum: Decimal | None) -> Decimal | None:
    """Allocate an invoice-level trade discount pro rata across the stock lines.

    A discount is quoted against the goods, not the delivery charge, so the
    base is the stock line sum. None means nothing to allocate.

    The recorded price has to be what was actually paid: a supplier who holds
    list prices and quietly stops discounting has raised your cost, and price
    memory that stored the list price would show a flat line through it."""
    if discount is None or discount <= 0 or stock_sum is None or stock_sum <= 0:
        return None
    if discount >= stock_sum:
        return None
    return (stock_sum - discount) / stock_sum


def _to_net_price(unit_price: Decimal | None, factor: Decimal | None) -> Decimal | None:
    if unit_price is None or factor is None:
        return unit_price
    return (unit_price * factor).quantize(PRICE_QUANTUM)


async def _insert_audit_event(
    conn: asyncpg.Connection,
    *,
    tenant_id: str,
    actor: str,
    action: str,
    subject_type: str,
    subject_id: str | None = None,
    detail: dict | None = None,
) -> None:
    """One audit row on the caller's connection, so it commits with whatever
    it is recording. Takes a connection rather than the pool for exactly that
    reason: a confirmed invoice with no note of who confirmed it is the state
    this table exists to make unreachable."""
    await conn.execute(
        """
        insert into audit_events (tenant_id, actor, action, subject_type, subject_id, detail)
        values ($1, $2, $3, $4, $5, $6)
        """,
        tenant_id,
        actor,
        action,
        subject_type,
        subject_id,
        detail or {},
    )


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

    async def insert_manual_document(self, tenant_id: str, branch_id: str | None) -> str:
        """A typed-in invoice's anchor row (C6 extension POST /api/invoices/manual,
        WP-34): source 'manual', no stored original, no message, no mime/sha256 -
        the evidence is the operator's keyboard, not a photo."""
        return await self.pool.fetchval(
            """
            insert into documents (tenant_id, branch_id, source)
            values ($1, $2, 'manual')
            returning id::text
            """,
            tenant_id,
            branch_id,
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
        tax_treatment: str | None = None,
        vat_rate: Decimal | None = None,
        discount_total: Decimal | None = None,
        rounding_amount: Decimal | None = None,
        status: str = InvoiceStatus.AWAITING_CONFIRM,
        confidence: dict,
        provenance: dict,
        lines: list[dict],
        document_classification: str | None = "invoice",
        created_by: str | None = None,
    ) -> str:
        """Draft invoice + lines + the document transition, one transaction:
        C1 says 'extracted' means a draft invoice with checks exists, so the
        two can never be observed apart. The insert takes the post-transition
        status directly (C1 permits draft -> awaiting_confirm; cash invoices
        pass needs_review, WP-24).

        `document_classification` defaults to 'invoice' (the pipeline persists
        only after the model classified the document as one). The manual-entry
        path (WP-34) passes None: no AI ran, so no classification is claimed -
        the document still lands 'extracted', because a draft invoice with
        checks now exists for it.

        `provenance` is C8's per-field record of where each value came from.
        `created_by` names a *person* who created this invoice by hand, and
        writes the audit event in the same transaction; the pipeline leaves it
        None because a model run is recorded in extraction_runs instead - the
        two tables split machine actions from human decisions and neither
        duplicates the other."""
        async with self.pool.acquire() as conn, conn.transaction():
            invoice_id = await conn.fetchval(
                """
                insert into invoices (tenant_id, branch_id, document_id, supplier_id,
                                      supplier_name, invoice_no, invoice_date, currency,
                                      subtotal, tax, total, payment_kind, status, confidence,
                                      tax_treatment, vat_rate, discount_total, rounding_amount,
                                      provenance)
                values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16,
                        $17, $18, $19)
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
                tax_treatment,
                vat_rate,
                discount_total,
                rounding_amount,
                provenance,
            )
            await conn.executemany(
                """
                insert into invoice_lines (tenant_id, invoice_id, position, raw_name,
                                           supplier_item_id, qty, unit, unit_price, line_total,
                                           pack_size, checks, line_kind)
                values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                """,
                [
                    (
                        tenant_id,
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
                        line.get("line_kind", "stock_item"),
                    )
                    for line in lines
                ],
            )
            await conn.execute(
                "update documents set status = 'extracted', classification = $2 where id = $1",
                document_id,
                document_classification,
            )
            if created_by is not None:
                await _insert_audit_event(
                    conn,
                    tenant_id=tenant_id,
                    actor=created_by,
                    action="invoice.created_by_hand",
                    subject_type="invoice",
                    subject_id=invoice_id,
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
                """
                select tenant_id, supplier_id, supplier_name, tax_treatment, tax, total,
                       discount_total
                from invoices where id = $1
                """,
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

            # C4 net-canonical price memory: an inclusive invoice's unit prices
            # are gross, so they are converted once here before they reach the
            # catalog. The factor comes from this invoice's own totals rather
            # than from vat_rate, so no rounding of the rate can move a price.
            net_factor = _net_price_factor(
                invoice["tax_treatment"], invoice["tax"], invoice["total"]
            )
            # WP-18: charges (delivery, cool-box hire) are cost, not stock, so
            # they are excluded from the discount base and never reach the
            # catalog at all.
            stock_sum = await conn.fetchval(
                """
                select sum(line_total) from invoice_lines
                where invoice_id = $1 and line_kind = 'stock_item'
                """,
                invoice_id,
            )
            discount_factor = _discount_factor(invoice["discount_total"], stock_sum)

            lines = await conn.fetch(
                """
                select id, raw_name, supplier_item_id, qty, unit, pack_size, unit_price
                from invoice_lines
                where invoice_id = $1 and line_kind = 'stock_item' order by position
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
                net_price = _to_net_price(
                    _to_net_price(line["unit_price"], net_factor), discount_factor
                )
                # tenant_id comes from the item rather than the invoice: the
                # observation belongs to the catalog row it prices.
                observed = await conn.fetchval(
                    """
                    insert into supplier_item_prices (tenant_id, supplier_item_id, price,
                                                      invoice_id)
                    select tenant_id, id, $2, $3 from supplier_items where id = $1
                    on conflict (supplier_item_id, invoice_id) where invoice_id is not null
                      do nothing
                    returning id
                    """,
                    item_id,
                    net_price,
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
                    net_price,
                )

    # -- Raw materials (M5) ---------------------------------------------------

    async def list_ingredients(self, tenant_id: str) -> list[asyncpg.Record]:
        """Every raw material for the tenant with how many purchasable packs
        map to it, name order. `packs` is the count the mapping screen shows:
        a material with one pack has one supplier's price, not a market."""
        return await self.pool.fetch(
            """
            select i.id, i.name, i.base_unit, i.category, i.created_at,
                   count(si.id) as packs
            from ingredients i
            left join supplier_items si on si.ingredient_id = i.id
            where i.tenant_id = $1
            group by i.id
            order by i.name
            """,
            tenant_id,
        )

    async def get_ingredient(self, ingredient_id: str) -> asyncpg.Record | None:
        return await self.pool.fetchrow(
            "select id, tenant_id, name, base_unit, category, created_at "
            "from ingredients where id = $1",
            ingredient_id,
        )

    async def create_ingredient(
        self, tenant_id: str, name: str, base_unit: str, category: str | None = None
    ) -> asyncpg.Record:
        """Create the material, or return the existing one of that name.
        Idempotent because the mapping screen creates materials as a side
        effect of approving a pack, and a double-submit must not become an
        error the consultant has to think about."""
        row = await self.pool.fetchrow(
            """
            insert into ingredients (tenant_id, name, base_unit, category)
            values ($1, $2, $3, $4)
            on conflict (tenant_id, name) do update set name = excluded.name
            returning id, tenant_id, name, base_unit, category, created_at
            """,
            tenant_id,
            clean_name(name),
            base_unit,
            category,
        )
        assert row is not None
        return row

    async def mapped_supplier_items(self, tenant_id: str) -> list[asyncpg.Record]:
        """Packs already mapped, with their material - the second candidate
        pool for a proposal (matching.propose_ingredient) and the rows the
        ingredient detail costs."""
        return await self.pool.fetch(
            """
            select si.id, si.canonical_name, si.unit, si.pack_size,
                   si.last_price, si.prev_price, si.last_price_at,
                   si.ingredient_id, si.mapped_at, si.mapped_by,
                   i.name as ingredient_name, i.base_unit,
                   s.id as supplier_id, s.name as supplier_name
            from supplier_items si
            join ingredients i on i.id = si.ingredient_id
            join suppliers s on s.id = si.supplier_id
            where si.tenant_id = $1
            order by i.name, s.name, si.canonical_name
            """,
            tenant_id,
        )

    async def unmapped_supplier_items(self, tenant_id: str) -> list[asyncpg.Record]:
        """The mapping queue: packs with no material yet, **ranked by money
        spent on them**, biggest first.

        Ranking by spend rather than by age is the whole point of the screen.
        A catalog that self-builds from invoices grows a long tail of
        one-off purchases, and an alphabetical queue spends a consultant's
        afternoon on a jar of food colouring while the rice nobody mapped
        holds up every recipe that uses it. Spend counts confirmed invoices
        only - an unconfirmed draft is not a purchase (plan.md §5 layer 4).
        """
        return await self.pool.fetch(
            """
            select si.id, si.canonical_name, si.unit, si.pack_size,
                   si.last_price, si.last_price_at, si.created_at,
                   s.id as supplier_id, s.name as supplier_name,
                   coalesce(sum(l.line_total) filter (where inv.status = 'confirmed'), 0) as spend,
                   count(distinct inv.id) filter (where inv.status = 'confirmed') as invoices
            from supplier_items si
            join suppliers s on s.id = si.supplier_id
            left join invoice_lines l on l.supplier_item_id = si.id
            left join invoices inv on inv.id = l.invoice_id
            where si.tenant_id = $1 and si.ingredient_id is null
            group by si.id, s.id
            order by spend desc, si.last_price desc nulls last, si.canonical_name
            """,
            tenant_id,
        )

    async def map_supplier_item(self, item_id: str, ingredient_id: str, actor: str) -> bool:
        """Record an approved mapping. Returns False when the item does not
        exist. The tenant check is the caller's (api.py); it is repeated in
        the predicate so a mapping can never cross tenants even if it isn't."""
        result = await self.pool.execute(
            """
            update supplier_items si
            set ingredient_id = $2, mapped_at = now(), mapped_by = $3
            from ingredients i
            where si.id = $1 and i.id = $2 and i.tenant_id = si.tenant_id
            """,
            item_id,
            ingredient_id,
            actor,
        )
        return result.endswith(" 1")

    async def unmap_supplier_item(self, item_id: str) -> bool:
        """Undo a mapping. The pack returns to the queue; nothing about its
        price history changes, because the mapping never touched it."""
        result = await self.pool.execute(
            "update supplier_items set ingredient_id = null, mapped_at = null, "
            "mapped_by = null where id = $1 and ingredient_id is not null",
            item_id,
        )
        return result.endswith(" 1")

    async def get_supplier_item_with_supplier(self, item_id: str) -> asyncpg.Record | None:
        return await self.pool.fetchrow(
            """
            select si.id, si.tenant_id, si.canonical_name, si.unit, si.pack_size,
                   si.last_price, si.prev_price, si.last_price_at,
                   si.ingredient_id, si.mapped_at, si.mapped_by,
                   s.id as supplier_id, s.name as supplier_name,
                   i.name as ingredient_name, i.base_unit
            from supplier_items si
            join suppliers s on s.id = si.supplier_id
            left join ingredients i on i.id = si.ingredient_id
            where si.id = $1
            """,
            item_id,
        )

    async def insert_conversion(
        self,
        *,
        tenant_id: str,
        supplier_item_id: str,
        base_quantity: Decimal,
        base_unit: str,
        actor: str,
        note: str | None = None,
    ) -> asyncpg.Record:
        """State what one purchase unit contains ("1 carton = 10 kg"). Append
        only: the newest row wins and the older ones stay, so a cost computed
        before somebody corrected a conversion is still reconstructible."""
        row = await self.pool.fetchrow(
            """
            insert into supplier_item_conversions
                (tenant_id, supplier_item_id, base_quantity, base_unit, note, actor)
            values ($1, $2, $3, $4, $5, $6)
            returning id, supplier_item_id, base_quantity, base_unit, note, actor, created_at
            """,
            tenant_id,
            supplier_item_id,
            base_quantity,
            base_unit,
            note,
            actor,
        )
        assert row is not None
        return row

    async def latest_conversions(self, tenant_id: str) -> dict[str, asyncpg.Record]:
        """The current conversion per item: newest row per supplier_item_id."""
        rows = await self.pool.fetch(
            """
            select distinct on (supplier_item_id)
                   supplier_item_id, base_quantity, base_unit, note, actor, created_at
            from supplier_item_conversions
            where tenant_id = $1
            order by supplier_item_id, created_at desc, id desc
            """,
            tenant_id,
        )
        return {str(row["supplier_item_id"]): row for row in rows}

    async def ingredient_price_lineage(self, ingredient_id: str) -> list[asyncpg.Record]:
        """Every confirmed price observation behind a material's cost, newest
        first, each carrying the invoice and document it came from - so a cost
        per kilo drills back to the photo it was read off (plan.md §8 M5)."""
        return await self.pool.fetch(
            """
            select p.price, p.observed_at, p.supplier_item_id,
                   si.canonical_name, si.unit, si.pack_size,
                   s.name as supplier_name,
                   inv.id as invoice_id, inv.invoice_no, inv.invoice_date, inv.currency,
                   inv.document_id
            from supplier_item_prices p
            join supplier_items si on si.id = p.supplier_item_id
            join suppliers s on s.id = si.supplier_id
            left join invoices inv on inv.id = p.invoice_id
            where si.ingredient_id = $1
            order by p.observed_at desc, p.id desc
            """,
            ingredient_id,
        )

    # -- Confirm flow (WP-21, C5) --------------------------------------------

    async def awaiting_confirm_invoices_for_phone(self, phone: str) -> list[asyncpg.Record]:
        """C5: the awaiting_confirm invoices whose document traces back to
        sender phone, newest first (the flow's default target and the
        disambiguation list order). Cash invoices are needs_review and never
        appear here - chat cannot confirm them (M7 owns approvals)."""
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

    async def confirm_invoice(self, invoice_id: str, *, actor: str) -> bool:
        """C1: invoice awaiting_confirm -> confirmed, stamping confirmed_at.
        The document is left at 'extracted' - its status tracks ingest only,
        and confirmation is read back through invoices.document_id. Returns
        False without touching anything when the invoice was not
        awaiting_confirm (already confirmed, or held needs_review) - safe to
        re-run.

        `actor` is who said OK. The audit event is written inside the same
        transaction and only when the status actually flipped, so a retried
        job re-sending its ack cannot leave a second confirmation in the
        trail."""
        return await self._confirm(invoice_id, from_status="awaiting_confirm", actor=actor)

    async def confirm_reviewed_invoice(self, invoice_id: str, *, actor: str) -> bool:
        """C1, the review-screen path (WP-30): invoice needs_review ->
        confirmed, stamping confirmed_at. The review screen is the cash
        approval path until M7 (plan.md §6 M2). Returns False without touching
        anything when the invoice was not needs_review - safe to re-run."""
        return await self._confirm(invoice_id, from_status="needs_review", actor=actor)

    async def _confirm(self, invoice_id: str, *, from_status: str, actor: str) -> bool:
        """The one confirm write, shared by both paths: flip the status if it
        is still the expected one, and record who did it in the same
        transaction. One gate, one trail entry, whichever door it came in."""
        async with self.pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                """
                update invoices set status = 'confirmed', confirmed_at = now()
                where id = $1 and status = $2
                returning tenant_id::text
                """,
                invoice_id,
                from_status,
            )
            if row is None:
                return False
            await _insert_audit_event(
                conn,
                tenant_id=row["tenant_id"],
                actor=actor,
                action="invoice.confirmed",
                subject_type="invoice",
                subject_id=invoice_id,
                detail={"from_status": from_status},
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
        provenance: dict,
        lines: list[dict],
        actor: str,
        corrected_fields: list[str],
        message_id: str | None = None,
    ) -> None:
        """Persist a correction (WP-21), one transaction: header money fields,
        refreshed confidence and C8 provenance on the invoice, and per line the
        fields the grammar can change plus the re-derived checks. Status is not
        touched - corrections keep the invoice awaiting_confirm (C1).

        `actor` and `corrected_fields` write the audit event in the same
        transaction, so a stored correction and the note of who made it cannot
        be observed apart."""
        async with self.pool.acquire() as conn, conn.transaction():
            tenant_id = await conn.fetchval(
                """
                update invoices set subtotal = $2, tax = $3, total = $4, confidence = $5,
                                    provenance = $6
                where id = $1
                returning tenant_id::text
                """,
                invoice_id,
                subtotal,
                tax,
                total,
                confidence,
                provenance,
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
            if tenant_id is not None:
                await _insert_audit_event(
                    conn,
                    tenant_id=tenant_id,
                    actor=actor,
                    action="invoice.corrected",
                    subject_type="invoice",
                    subject_id=invoice_id,
                    detail={"fields": corrected_fields, "message_id": message_id},
                )

    # -- Audit trail (C8, plan.md §8 M5) -------------------------------------

    async def record_audit_event(
        self,
        *,
        tenant_id: str,
        actor: str,
        action: str,
        subject_type: str,
        subject_id: str | None = None,
        detail: dict | None = None,
    ) -> None:
        """One human decision, on the record. The writes that must not be
        observable without their trail entry (confirm, correct, hand-entry) go
        through the private helper inside their own transaction instead; this
        is for callers with nothing to be atomic with - M5's material merges
        among them."""
        async with self.pool.acquire() as conn:
            await _insert_audit_event(
                conn,
                tenant_id=tenant_id,
                actor=actor,
                action=action,
                subject_type=subject_type,
                subject_id=subject_id,
                detail=detail,
            )

    async def audit_events_for_subject(
        self, subject_type: str, subject_id: str
    ) -> list[asyncpg.Record]:
        """The history of one invoice or one raw material, newest first."""
        return list(
            await self.pool.fetch(
                """
                select * from audit_events
                where subject_type = $1 and subject_id = $2
                order by created_at desc, id desc
                """,
                subject_type,
                subject_id,
            )
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
        """The run's tenant is the document's, read in the insert - so a run row
        can never claim a tenant its document does not. A document_id with no
        row records nothing, which only happens if the document was deleted
        between the pipeline reading it and the run finishing."""
        await self.pool.execute(
            """
            insert into extraction_runs (tenant_id, document_id, model_id, prompt_version,
                                         input_tokens, output_tokens, latency_ms, repair_applied,
                                         outcome)
            select tenant_id, id, $2, $3, $4, $5, $6, $7, $8 from documents where id = $1
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
