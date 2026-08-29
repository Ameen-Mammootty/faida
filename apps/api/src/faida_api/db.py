"""Thin asyncpg layer. Plain SQL, no ORM — the database holds data and constraints,
the application holds the logic (plan §2 rule 3)."""

import datetime
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any

import asyncpg

from . import costing
from .contracts import InvoiceStatus
from .extraction.currency import currency_differs
from .matching import clean_name
from .provenance import asserted_fields

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


async def _write_line_cost(conn: asyncpg.Connection, line_id: str, cost: costing.LineCost) -> None:
    """Freeze one line's cost per base unit and how it was made (WP-53).

    **Only ever writes a number, never a null over one.** WP-55 lets a person
    supply the amount a container never printed, which costs a line this pass
    could not; a later re-run of the confirm write - the retried WhatsApp ack
    takes that path - would recompute "no pack, no cost" and wipe it. So the
    absence of a cost is not a value this function writes. Rerunning it with
    the same invoice is otherwise a no-op: the inputs are the same and so is
    the arithmetic."""
    if cost.cost is None:
        return
    await conn.execute(
        """
        update invoice_lines
        set cost_per_base_unit = $2, cost_base_unit = $3, cost_basis = $4
        where id = $1
        """,
        line_id,
        cost.cost,
        cost.base_unit,
        cost.basis(),
    )


async def _cost_stock_lines(
    conn: asyncpg.Connection, invoice_id: str, *, only_uncosted: bool = False
) -> None:
    """Freeze the cost per base unit of an invoice's stock lines (WP-53).

    One implementation, two doors. The confirm transaction runs it over the
    whole invoice; a pack-size override (WP-55) runs it again over each invoice
    holding a line it might now be able to cost. `only_uncosted` is the plan's
    rule stated rather than implied: **an override costs the lines that have no
    cost yet and never rewrites a line already costed**, so a figure a person
    has already seen does not move under them because someone answered a
    question about a different box.

    Charge lines never get one - a delivery fee is not a thing you cook with -
    and a foreign-currency invoice gets none at all, because a USD price in an
    AED cost is not slightly wrong, it is meaningless (WP-28).
    """
    invoice = await conn.fetchrow(
        """
        select i.tax_treatment, i.tax, i.total, i.discount_total, i.currency, i.provenance,
               t.currency as tenant_currency
        from invoices i join tenants t on t.id = i.tenant_id
        where i.id = $1
        """,
        invoice_id,
    )
    if invoice is None or currency_differs(invoice["currency"], invoice["tenant_currency"]):
        return

    # The same two factors price memory uses, from the same functions: C4 has
    # one implementation, and a cost that disagreed with the price it came from
    # would be a bug no screen could show.
    net_factor = _net_price_factor(invoice["tax_treatment"], invoice["tax"], invoice["total"])
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
        select l.id, l.position, l.raw_name, l.qty, l.unit, l.pack_size, l.unit_price,
               l.cost_per_base_unit, s.pack_size_override
        from invoice_lines l
        left join supplier_items s on s.id = l.supplier_item_id
        where l.invoice_id = $1 and l.line_kind = 'stock_item'
        order by l.position
        """,
        invoice_id,
    )
    # `position` is fetched rather than counted. This query drops the charge
    # lines, so a loop counter is not where a line sits on the invoice - and
    # provenance is keyed by that position, so an invoice whose first line is a
    # delivery charge would hand every stock line the row above's history and
    # the wrong C9 label.
    #
    # C9: a cost is never greener than its worst input, and the pro rata
    # discount makes every stock line an input to every other one, so one
    # corrected line_total taints its neighbours' costs too. Every stock line's
    # position goes in, including the ones this pass will skip.
    asserted = asserted_fields(invoice["provenance"] or {})
    stock_positions = [line["position"] for line in lines]
    for line in lines:
        if only_uncosted and line["cost_per_base_unit"] is not None:
            continue
        if line["qty"] is None or line["unit_price"] is None:
            continue
        await _write_line_cost(
            conn,
            line["id"],
            costing.cost_line(
                position=line["position"],
                qty=line["qty"],
                unit_price=line["unit_price"],
                pack_size=line["pack_size"],
                raw_name=line["raw_name"],
                unit=line["unit"],
                net_factor=net_factor,
                discount_factor=discount_factor,
                asserted=asserted,
                stock_positions=stock_positions,
                override=line["pack_size_override"],
            ),
        )


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

    @asynccontextmanager
    async def _txn(self, conn: asyncpg.Connection | None) -> AsyncIterator[asyncpg.Connection]:
        """Join the caller's transaction, or open one of our own (WP-50).

        A write that must commit *with* something else takes the caller's
        connection; the same write called on its own gets a fresh one. Without
        this the two halves of a confirm were separate transactions, and the
        gap between them was not recoverable - see `_confirm`."""
        if conn is not None:
            yield conn
        else:
            async with self.pool.acquire() as owned, owned.transaction():
                yield owned

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

    async def tenant_currency(self, tenant_id: str) -> str | None:
        """The money this tenant keeps its books in (plan.md §4). WP-28 asks
        about an invoice billed in anything else and keeps it out of price
        memory."""
        return await self.pool.fetchval("select currency from tenants where id = $1", tenant_id)

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

    async def list_invoice_headers_for_tenant(self, tenant_id: str) -> list[asyncpg.Record]:
        """Every invoice header for one tenant, newest first - WP-44's
        duplicate check compares the incoming paper against these in Python,
        so the normalization rule (matching.normalize_invoice_no) lives once,
        never re-implemented in SQL. Fine at demo volume; revisit with an
        index and a WHERE clause when a tenant has thousands (§2 rule 8)."""
        return await self.pool.fetch(
            """
            select id, supplier_id, supplier_name, invoice_no, invoice_date, currency,
                   total, status, created_at
            from invoices
            where tenant_id = $1
            order by created_at desc, id desc
            """,
            tenant_id,
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

    # -- Raw materials (M5 WP-52) --------------------------------------------

    async def list_ingredients(self, tenant_id: str) -> list[asyncpg.Record]:
        """Every raw material this tenant cooks with, and how many purchasable
        packs have been mapped onto each."""
        return await self.pool.fetch(
            """
            select i.id::text as id, i.name, i.base_unit, i.created_at,
                   count(s.id) as pack_count
            from ingredients i
            left join supplier_items s on s.ingredient_id = i.id
            where i.tenant_id = $1
            group by i.id
            order by i.name
            """,
            tenant_id,
        )

    async def list_mapped_packs(self, tenant_id: str) -> list[asyncpg.Record]:
        """Every pack that has a material, with who sells it.

        One query for the whole tenant rather than one per material: the
        materials screen renders them all together, and asking per material
        would be a query per row of the page."""
        return await self.pool.fetch(
            """
            select s.id::text as id, s.ingredient_id::text as ingredient_id,
                   s.canonical_name, s.unit, s.pack_size, s.pack_size_override,
                   s.last_price, s.last_price_at, sup.name as supplier_name
            from supplier_items s
            join suppliers sup on sup.id = s.supplier_id
            where s.tenant_id = $1 and s.ingredient_id is not null
            order by sup.name, s.canonical_name
            """,
            tenant_id,
        )

    async def list_mapped_pack_costs(self, tenant_id: str) -> list[asyncpg.Record]:
        """The newest costed invoice line behind every mapped pack, grouped by
        material with **that material's current price first** (M5 WP-54).

        This is the whole of "one material, one price per kilo". There is no
        `ingredient_costs` table and there is not going to be one: the fact
        already lives on the invoice lines, and a stored copy would need
        refreshing on confirm, approve, reject-reversal, remap, unmap and
        pack-size override - six rules to get exhaustively right, where the
        first draft of the plan already missed the main one. Deriving it
        deletes the whole category of bug, and makes unmapping a wrong merge
        correct every figure above it with nothing left to rebuild.

        **Ordered by the printed invoice date, with confirm time only as a
        tie-breaker** (PRD §19's "most recent purchase"). An owner handing over
        a stack of last month's invoices during onboarding must not overwrite
        this month's real cost - silently, in the layer where nothing
        downstream can notice. An invoice that printed no date falls back to
        when it was confirmed, read in UTC so the answer does not depend on the
        server's clock settings.

        Latest, not cheapest and not averaged. The rows come back one per pack
        (its own newest costed line, which is what makes the packs comparable
        on screen), ordered so the **first row of each material is that
        material's price**.

        `cost_base_unit = ing.base_unit` is belt and braces: the approval gate
        already refuses a millilitre pack onto a gram material, and a price
        assembled across dimensions would be a number with no meaning at all.

        A negative-qty line is a return, not a purchase, so it never wins
        "newest": EDGE-01 prints a costed credit line whose unit price need
        not match its purchase, and before the qty filter the tie between the
        two broke on a random uuid (found by the 2026-08-29 M6 eng review's
        outside voice). Ties inside one invoice break on the printed line
        position - in both orderings - so the winner is the same on every run.
        """
        return await self.pool.fetch(
            """
            with newest_per_pack as (
                select distinct on (s.id)
                       s.id::text as supplier_item_id,
                       s.ingredient_id::text as ingredient_id,
                       s.canonical_name, s.pack_size as catalog_pack_size,
                       sup.name as supplier_name,
                       l.id::text as invoice_line_id, l.position, l.raw_name, l.pack_size,
                       l.cost_per_base_unit, l.cost_base_unit, l.cost_basis,
                       inv.id::text as invoice_id, inv.invoice_date, inv.confirmed_at,
                       coalesce(inv.invoice_date,
                                (inv.confirmed_at at time zone 'UTC')::date) as purchased_on
                from supplier_items s
                join ingredients ing on ing.id = s.ingredient_id
                join suppliers sup on sup.id = s.supplier_id
                join invoice_lines l on l.supplier_item_id = s.id
                join invoices inv on inv.id = l.invoice_id
                where s.tenant_id = $1
                  and s.ingredient_id is not null
                  and inv.status = 'confirmed'
                  and l.cost_per_base_unit is not null
                  and l.cost_base_unit = ing.base_unit
                  and coalesce(l.qty, 0) >= 0
                order by s.id, purchased_on desc, inv.confirmed_at desc,
                         l.position desc, l.id desc
            )
            select * from newest_per_pack
            order by ingredient_id, purchased_on desc, confirmed_at desc,
                     position desc, invoice_line_id desc
            """,
            tenant_id,
        )

    async def list_unmapped_supplier_items(self, tenant_id: str) -> list[asyncpg.Record]:
        """Packs with no material yet, **most money first**.

        Ranked by what was actually spent on them, over *confirmed* invoices
        only - an unconfirmed invoice must not move the consultant's queue any
        more than it moves price memory (plan.md §5 layer 4). Charge lines
        never reach the catalog at all (WP-18), so delivery fees cannot appear
        here either.

        The filter on the aggregate, rather than a plain join condition,
        matters: a left join whose ON clause rejects the invoice still leaves
        the line row in place, so its total would have been counted anyway."""
        return await self.pool.fetch(
            """
            select s.id::text as id, s.canonical_name, s.unit, s.pack_size,
                   s.pack_size_override,
                   s.supplier_id::text as supplier_id, sup.name as supplier_name,
                   coalesce(sum(l.line_total) filter (where inv.id is not null), 0) as spend,
                   count(l.id) filter (where inv.id is not null) as line_count
            from supplier_items s
            join suppliers sup on sup.id = s.supplier_id
            left join invoice_lines l on l.supplier_item_id = s.id
            left join invoices inv on inv.id = l.invoice_id and inv.status = 'confirmed'
            where s.tenant_id = $1 and s.ingredient_id is null
            group by s.id, sup.name
            order by spend desc, s.canonical_name
            """,
            tenant_id,
        )

    async def get_supplier_item_for_mapping(self, supplier_item_id: str) -> asyncpg.Record | None:
        """The pack plus the material it currently points at, if any."""
        return await self.pool.fetchrow(
            """
            select s.id::text as id, s.tenant_id::text as tenant_id, s.canonical_name,
                   s.unit, s.pack_size, s.pack_size_override,
                   s.ingredient_id::text as ingredient_id,
                   i.name as ingredient_name, i.base_unit as ingredient_base_unit
            from supplier_items s
            left join ingredients i on i.id = s.ingredient_id
            where s.id = $1
            """,
            supplier_item_id,
        )

    async def get_ingredient(self, ingredient_id: str) -> asyncpg.Record | None:
        return await self.pool.fetchrow(
            """
            select id::text as id, tenant_id::text as tenant_id, name, base_unit, created_at
            from ingredients where id = $1
            """,
            ingredient_id,
        )

    async def rejected_ingredient_ids(self, supplier_item_id: str) -> set[str]:
        """Materials a person already said this pack is **not**.

        Derived from the audit trail rather than kept in a second table: a
        rejection is a human decision, and that is exactly what `audit_events`
        records (C8). A parallel table would hold the same fact twice, which is
        the drift migration 0010 was written to delete.

        Latest event per pair wins, so rejecting a material and later approving
        it reads correctly, and so does approving and later unmapping. Served
        by the 0011 subject index."""
        return (await self.rejected_ingredients_by_item(None, item_id=supplier_item_id)).get(
            supplier_item_id, set()
        )

    async def rejected_ingredients_by_item(
        self, tenant_id: str | None, *, item_id: str | None = None
    ) -> dict[str, set[str]]:
        """The same read for a whole tenant at once, keyed by pack.

        The queue asks this for every row it renders, so it is one query rather
        than one per pack. `distinct on` keeps only the newest event per
        (pack, material) pair, which is what makes reject-then-approve and
        approve-then-unmap read correctly."""
        rows = await self.pool.fetch(
            """
            select distinct on (subject_id, detail->>'ingredient_id')
                   subject_id::text as supplier_item_id,
                   detail->>'ingredient_id' as ingredient_id, action
            from audit_events
            where subject_type = 'supplier_item'
              and ($1::uuid is null or tenant_id = $1)
              and ($2::uuid is null or subject_id = $2)
              and action in ('supplier_item.mapped', 'supplier_item.mapping_rejected')
              and detail->>'ingredient_id' is not null
            order by subject_id, detail->>'ingredient_id', created_at desc, id desc
            """,
            tenant_id,
            item_id,
        )
        rejected: dict[str, set[str]] = {}
        for row in rows:
            if row["action"] == "supplier_item.mapping_rejected":
                rejected.setdefault(row["supplier_item_id"], set()).add(row["ingredient_id"])
        return rejected

    async def map_supplier_item(
        self,
        supplier_item_id: str,
        *,
        tenant_id: str,
        ingredient_id: str | None = None,
        name: str | None = None,
        base_unit: str | None = None,
        actor: str,
        previous_ingredient_id: str | None = None,
    ) -> asyncpg.Record:
        """Approve a merge: point this pack at a material, creating the
        material when the approval names a new one rather than an existing id.

        The creation, the link and the audit row are **one transaction**
        (C8). A merge with nobody's name on it is the state migration 0011
        exists to make unreachable - and unlike a bad extraction there is no
        photo to check a merge against, so the actor is the only record of who
        to ask.

        Creating from a name is not a convenience: the matcher can only
        propose materials that already exist, so on a fresh tenant every queue
        would be unapprovable without it."""
        async with self.pool.acquire() as conn, conn.transaction():
            if ingredient_id is None:
                ingredient_id = await conn.fetchval(
                    """
                    insert into ingredients (tenant_id, name, base_unit)
                    values ($1, $2, $3)
                    on conflict (tenant_id, name) do update set name = excluded.name
                    returning id::text
                    """,
                    tenant_id,
                    name,
                    base_unit,
                )
            await conn.execute(
                "update supplier_items set ingredient_id = $2 where id = $1",
                supplier_item_id,
                ingredient_id,
            )
            ingredient = await conn.fetchrow(
                "select id::text as id, name, base_unit from ingredients where id = $1",
                ingredient_id,
            )
            await _insert_audit_event(
                conn,
                tenant_id=tenant_id,
                actor=actor,
                action="supplier_item.mapped",
                subject_type="supplier_item",
                subject_id=supplier_item_id,
                detail={
                    "ingredient_id": ingredient_id,
                    "ingredient_name": ingredient["name"],
                    "previous_ingredient_id": previous_ingredient_id,
                },
            )
        return ingredient

    async def unmap_supplier_item(
        self, supplier_item_id: str, *, tenant_id: str, actor: str, ingredient_id: str
    ) -> None:
        """The reverse gear. An approval gate whose worst case has no undo
        leaves a consultant asking an engineer, and a wrong merge is this
        milestone's stated worst case. Because the material's price is derived
        from whichever packs are mapped right now, unmapping corrects every
        figure above it immediately - there is no stored total to rebuild."""
        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "update supplier_items set ingredient_id = null where id = $1", supplier_item_id
            )
            await _insert_audit_event(
                conn,
                tenant_id=tenant_id,
                actor=actor,
                action="supplier_item.unmapped",
                subject_type="supplier_item",
                subject_id=supplier_item_id,
                detail={"previous_ingredient_id": ingredient_id},
            )

    async def set_pack_size_override(
        self, supplier_item_id: str, *, tenant_id: str, pack_size: str, actor: str
    ) -> int:
        """A person says how much is in one of these, once (WP-55).

        `extraction/units.py` refuses to guess what a carton holds, so the
        sentence has to come from a human - and this is the whole of clearing a
        blocked cost: the override, its audit row, and the lines it can now
        cost, all in **one transaction**. An issue that is cleared but whose
        costs did not move would be worse than one still open, because the
        screen would say it was handled.

        **It costs the lines that have no cost yet and never rewrites one that
        has.** Both halves matter. Without the first, answering the question
        changes nothing until the next delivery arrives. Without the second, a
        figure someone already read moves under them because a colleague
        answered a question about a different box, and no screen anywhere would
        show that it had.

        Returns how many lines it costed, which is what the reply tells the
        person who answered.

        `audit_events` is the version history: one row per change, naming who,
        when, and what it replaced. There is no `container_conversions` table
        because that would keep the same fact in two places (the duplication
        migration 0010 was written to delete)."""
        blocked = """
            select count(*) from invoice_lines l join invoices i on i.id = l.invoice_id
            where l.supplier_item_id = $1 and i.status = 'confirmed'
              and l.line_kind = 'stock_item' and l.cost_per_base_unit is null
            """
        async with self.pool.acquire() as conn, conn.transaction():
            previous = await conn.fetchval(
                "select pack_size_override from supplier_items where id = $1", supplier_item_id
            )
            await conn.execute(
                "update supplier_items set pack_size_override = $2 where id = $1",
                supplier_item_id,
                pack_size,
            )
            before = await conn.fetchval(blocked, supplier_item_id)
            # Only invoices with something left to cost, and inside those only
            # the lines with no cost. Both halves are the same rule at two
            # scales, and both are needed: the filter here keeps an invoice
            # whose lines are all costed out of the pass entirely, and
            # `only_uncosted` protects a line already costed **from an earlier
            # answer** when its invoice is pulled in by some *other* blocked
            # line - which is what happens when two unlabelled products share
            # one invoice and are answered on different days.
            invoices = await conn.fetch(
                """
                select distinct l.invoice_id::text as id
                from invoice_lines l join invoices i on i.id = l.invoice_id
                where l.supplier_item_id = $1 and i.status = 'confirmed'
                  and l.line_kind = 'stock_item' and l.cost_per_base_unit is null
                """,
                supplier_item_id,
            )
            for row in invoices:
                await _cost_stock_lines(conn, row["id"], only_uncosted=True)
            costed = before - await conn.fetchval(blocked, supplier_item_id)
            await _insert_audit_event(
                conn,
                tenant_id=tenant_id,
                actor=actor,
                action="supplier_item.pack_size_set",
                subject_type="supplier_item",
                subject_id=supplier_item_id,
                detail={"pack_size": pack_size, "previous_pack_size": previous},
            )
        return costed

    async def list_blocked_costs(self, tenant_id: str) -> list[asyncpg.Record]:
        """Every confirmed stock line this layer could not turn into a cost.

        **Derived, not a table.** PRD §24's first-class issue records - severity,
        impact, status, an inbox - are post-MVP, and C5's "derived until real
        usage demands more" is the standing precedent. The fact is already on
        the line: it has no cost, and re-asking the same function that refused
        says which of six things went wrong.

        Most money first, like the mapping queue, because that is the order in
        which a missing cost hurts. The supplier comes off the *invoice* rather
        than the catalog row, so a line that never became a catalog item at all
        still says who sold it."""
        return await self.pool.fetch(
            """
            select l.id::text as invoice_line_id, l.position, l.raw_name, l.qty, l.unit,
                   l.pack_size, l.unit_price, l.line_total,
                   i.id::text as invoice_id, i.invoice_date, i.currency,
                   coalesce(sup.name, i.supplier_name) as supplier_name,
                   t.currency as tenant_currency,
                   s.id::text as supplier_item_id, s.canonical_name, s.pack_size_override,
                   ing.id::text as ingredient_id, ing.name as ingredient_name
            from invoice_lines l
            join invoices i on i.id = l.invoice_id
            join tenants t on t.id = i.tenant_id
            left join suppliers sup on sup.id = i.supplier_id
            left join supplier_items s on s.id = l.supplier_item_id
            left join ingredients ing on ing.id = s.ingredient_id
            where l.tenant_id = $1
              and i.status = 'confirmed'
              and l.line_kind = 'stock_item'
              and l.cost_per_base_unit is null
            order by l.line_total desc nulls last, l.id
            """,
            tenant_id,
        )

    async def reject_ingredient_for_item(
        self, supplier_item_id: str, *, tenant_id: str, ingredient_id: str, actor: str
    ) -> None:
        """A person saying this pack is not that material. Nothing else
        changes: the rejection *is* the record, and `rejected_ingredient_ids`
        reads it back so the queue stops offering an answer already refused."""
        async with self.pool.acquire() as conn, conn.transaction():
            await _insert_audit_event(
                conn,
                tenant_id=tenant_id,
                actor=actor,
                action="supplier_item.mapping_rejected",
                subject_type="supplier_item",
                subject_id=supplier_item_id,
                detail={"ingredient_id": ingredient_id},
            )

    async def record_confirmed_prices(
        self, invoice_id: str, *, conn: asyncpg.Connection | None = None
    ) -> None:
        """The catalog self-builds and the price baseline moves - never before
        confirm, so an unconfirmed invoice can't pollute it (plan.md §5 layer
        4, §6 M2).

        For each line with qty and unit_price: create the supplier item when
        the line didn't snap (canonical_name = cleaned raw_name; the supplier
        itself is created from the raw extracted supplier_name when the invoice
        has none), append the price observation (idempotent per invoice via
        the 0003 partial unique index), and shift prev/last price only when
        this invoice's observation is new AND the price actually changed -
        re-running for the same invoice is a no-op.

        **It also freezes each line's cost per base unit** (WP-53), here rather
        than in a step of its own, because the two ex-VAT and post-discount
        factors are the same ones - C4 has one implementation, and a cost that
        disagreed with the price it came from would be a bug nothing on any
        screen could see.

        **`conn` is how this stays atomic with the status flip** (WP-50). The
        confirm paths pass their own connection so both halves commit together;
        called without one it opens its own transaction, which is the retried
        WhatsApp ack and any row confirmed before that merge existed."""
        async with self._txn(conn) as conn:
            invoice = await conn.fetchrow(
                """
                select i.tenant_id, i.supplier_id, i.supplier_name, i.tax_treatment, i.tax,
                       i.total, i.discount_total, i.currency, i.provenance,
                       t.currency as tenant_currency
                from invoices i join tenants t on t.id = i.tenant_id
                where i.id = $1
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

            # WP-28: the baseline never mixes currency bases. supplier_items.
            # last_price is one bare number with no currency beside it, so a
            # USD line recorded against an AED tenant is not slightly wrong, it
            # is meaningless - and by M5 it is a meaningless cost per gram. The
            # supplier link above is kept (identity, not price), and the ack
            # says plainly that the prices were held back.
            if currency_differs(invoice["currency"], invoice["tenant_currency"]):
                return

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
                select id, position, raw_name, supplier_item_id, qty, unit, pack_size, unit_price
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

            # Last, because a line that had not snapped only acquired its
            # catalog row in the loop above - and that row is where a person's
            # conversion for an unlabelled container lives (WP-55).
            await _cost_stock_lines(conn, invoice_id)

    # -- Confirm flow (WP-21, C5) --------------------------------------------

    async def awaiting_confirm_invoices_for_phone(self, phone: str) -> list[asyncpg.Record]:
        """C5: the awaiting_confirm invoices whose document traces back to
        sender phone, newest first (the flow's default target and the
        disambiguation list order). Cash invoices are needs_review and never
        appear here - chat cannot confirm them (M7 owns approvals)."""
        return await self.pool.fetch(
            """
            select i.id, i.supplier_name, i.currency, i.total, i.created_at, b.timezone,
                   t.currency as tenant_currency
            from invoices i
            join tenants t on t.id = i.tenant_id
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
            select i.id, i.supplier_name, i.currency, i.total, i.confirmed_at,
                   t.currency as tenant_currency
            from invoices i
            join tenants t on t.id = i.tenant_id
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
        """One invoice row plus its branch name (C6 detail shows names) and the
        tenant's own currency (WP-28: the reply, the ack and price memory all
        have to know whether this invoice is billed in the tenant's money)."""
        return await self.pool.fetchrow(
            """
            select i.*, b.name as branch_name, t.currency as tenant_currency
            from invoices i
            join tenants t on t.id = i.tenant_id
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
        is still the expected one, record who did it, and move the catalog and
        price baseline - **all in one transaction** (WP-50). One gate, one
        trail entry, one set of prices, whichever door it came in.

        `total is not null` sits in the where clause as an invariant, not as
        the user-facing rule (WP-26): both callers check the total first so
        they can say *why* they are refusing. It is repeated here because a
        third caller written a year from now would otherwise reopen the hole
        this closed - an invoice recorded with no headline number, which M5
        divides into plate costs no photograph can check.

        The price write joined this transaction for the same reason. It used to
        run in a second one, so anything that threw between them left an
        invoice reading confirmed with no prices and (from M5) no cost - and
        the review screen's confirm then answered 409 "invoice is confirmed"
        for ever, with no way back. A partial confirm is now unreachable rather
        than merely unlikely: if the prices fail, the status flip rolls back
        with them, the sender is told, and a retry genuinely retries."""
        async with self.pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                """
                update invoices set status = 'confirmed', confirmed_at = now()
                where id = $1 and status = $2 and total is not null
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
            await self.record_confirmed_prices(invoice_id, conn=conn)
        return True

    async def apply_invoice_correction(
        self,
        invoice_id: str,
        *,
        invoice_no: str | None,
        invoice_date: datetime.date | None,
        subtotal: Decimal | None,
        tax: Decimal | None,
        total: Decimal | None,
        confidence: dict,
        provenance: dict,
        lines: list[dict],
        actor: str,
        corrected_fields: list[str],
        currency: str | None,
        tax_treatment: str | None,
        vat_rate: Decimal | None,
        message_id: str | None = None,
    ) -> None:
        """Persist a correction (WP-21/WP-25/WP-26/WP-28), one transaction:
        header fields (invoice number, date and currency included), the C4
        treatment re-derived from the corrected arithmetic, refreshed
        confidence and C8 provenance on the invoice, and per line the fields
        the grammar can change plus the re-derived checks. Status is not
        touched - corrections keep the invoice awaiting_confirm (C1).

        `tax_treatment`/`vat_rate` travel with every correction because the
        confirm path reads them to record price memory net of VAT: a total
        supplied after the fact can turn an unresolvable invoice into an
        inclusive one, and a stale treatment beside a new total would store a
        gross price under a net baseline.

        `actor` and `corrected_fields` write the audit event in the same
        transaction, so a stored correction and the note of who made it cannot
        be observed apart."""
        async with self.pool.acquire() as conn, conn.transaction():
            tenant_id = await conn.fetchval(
                """
                update invoices
                set invoice_no = $2, invoice_date = $3, subtotal = $4, tax = $5, total = $6,
                    confidence = $7, provenance = $8,
                    currency = coalesce($9, currency), tax_treatment = $10, vat_rate = $11
                where id = $1
                returning tenant_id::text
                """,
                invoice_id,
                invoice_no,
                invoice_date,
                subtotal,
                tax,
                total,
                confidence,
                provenance,
                currency,
                tax_treatment,
                vat_rate,
            )
            await conn.executemany(
                """
                update invoice_lines
                set raw_name = $3, supplier_item_id = $4, qty = $5, unit_price = $6,
                    line_total = $7, checks = $8, unit = $9, pack_size = $10
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
                        line["unit"],
                        line["pack_size"],
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
