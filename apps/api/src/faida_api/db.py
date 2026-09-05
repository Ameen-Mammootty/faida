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
from .contracts import InvoiceStatus, JobKind
from .extraction.currency import currency_differs
from .matching import clean_name, match_supplier, snap_item, strip_delivery_note
from .provenance import asserted_fields
from .recipes import RecipeKey, component_key, recipe_key, recipes_match
from .takings import FILS, code_key, day_key, name_key, till_item_key

RETRY_LIMIT = 3
RETRY_BACKOFF_SECONDS = 30

#: One sales day as every read and write returns it (M8 WP-80) - the C6 day
#: shape minus its lines, which `list_sales_lines` fetches in one query.
_SALES_DAY_COLUMNS = """
    id::text as id, branch_id::text as branch_id, business_date, granularity, amount_basis,
    vat_rate, takings, net_sales, line_count, layout_id::text as layout_id, source_sha256,
    source_filename, loaded_by, loaded_at
"""


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

    async def set_inbound_message_status(self, message_id: str, status: str) -> None:
        """Stamp an inbound row (WP-72: `ignored_unknown_sender`, written
        before any reply, so the decision is on record whether or not the
        reply ever leaves)."""
        await self.pool.execute(
            "update wa_messages set status = $2 where message_id = $1 and direction = 'in'",
            message_id,
            status,
        )

    async def inbound_status_seen_from_phone(
        self,
        phone: str,
        status: str,
        *,
        within: datetime.timedelta,
        exclude_message_id: str,
    ) -> bool:
        """Whether another inbound message from this phone was stamped with
        `status` inside the window. The current message is excluded by id,
        because it is stamped first and would otherwise silence its own
        reply (the self-silencing lookup the M7 review caught)."""
        return await self.pool.fetchval(
            """
            select exists (
                select 1 from wa_messages
                where direction = 'in'
                  and from_phone = $1
                  and status = $2
                  and message_id <> $3
                  and created_at >= now() - $4::interval
            )
            """,
            phone,
            status,
            exclude_message_id,
            within,
        )

    # -- Tenancy -------------------------------------------------------------

    async def branch_for_phone(self, phone: str) -> asyncpg.Record | None:
        return await self.pool.fetchrow(
            "select id, tenant_id from branches where wa_phone_e164 = $1", phone
        )

    async def membership_tenant_id(self, user_id: str) -> str | None:
        """The tenant a signed-in person belongs to, or None (M7 WP-70; the
        memberships table from 0018). Read on every request, so removing a
        row is an immediate revocation. One membership per person for the
        pilot; were there several, the oldest wins, deterministically."""
        return await self.pool.fetchval(
            "select tenant_id::text from memberships where user_id = $1 "
            "order by created_at, id limit 1",
            user_id,
        )

    async def tenant_currency(self, tenant_id: str) -> str | None:
        """The money this tenant keeps its books in (plan.md §4). WP-28 asks
        about an invoice billed in anything else and keeps it out of price
        memory."""
        return await self.pool.fetchval("select currency from tenants where id = $1", tenant_id)

    async def get_branch(self, branch_id: str, *, tenant_id: str) -> asyncpg.Record | None:
        """One of this tenant's branches, or None - another tenant's branch
        does not exist for the caller (WP-73)."""
        return await self.pool.fetchrow(
            "select id, tenant_id, name from branches where id = $1 and tenant_id = $2",
            branch_id,
            tenant_id,
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
        self, *, tenant_id: str, branch_id: str | None, mime: str, sha256: str
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

    async def insert_manual_document(self, *, tenant_id: str, branch_id: str | None) -> str:
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

    async def set_document_storage_path(
        self, document_id: str, storage_path: str, *, tenant_id: str
    ) -> None:
        await self.pool.execute(
            "update documents set storage_path = $2 where id = $1 and tenant_id = $3",
            document_id,
            storage_path,
            tenant_id,
        )

    async def get_document(self, document_id: str, *, tenant_id: str) -> asyncpg.Record | None:
        """The worker's read, scoped like every other (WP-72): the extract job
        carries its tenant, and a document outside it is None - the pipeline
        then refuses the job rather than reading the row to learn whose it
        is. The console never calls this: its detail path reads the document
        through the tenant-scoped `get_invoice` (WP-73)."""
        return await self.pool.fetchrow(
            "select * from documents where id = $1 and tenant_id = $2", document_id, tenant_id
        )

    async def set_document_status(
        self,
        document_id: str,
        status: str,
        classification: str | None = None,
        *,
        tenant_id: str,
    ) -> None:
        """C1 transition, worker-owned. A classification (invoice/z_report/other)
        sticks once recorded; passing None leaves it untouched."""
        await self.pool.execute(
            "update documents set status = $2, classification = coalesce($3, classification) "
            "where id = $1 and tenant_id = $4",
            document_id,
            status,
            classification,
            tenant_id,
        )

    # -- Invoices (WP-13) ----------------------------------------------------

    async def get_invoice_by_document(
        self, document_id: str, *, tenant_id: str
    ) -> asyncpg.Record | None:
        return await self.pool.fetchrow(
            "select * from invoices where document_id = $1 and tenant_id = $2",
            document_id,
            tenant_id,
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
        duplicate_of_invoice_id: str | None = None,
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
        `duplicate_of_invoice_id` is WP-44's hold, recorded rather than spent
        on the reply and thrown away: the earlier invoice this paper duplicates.
        Null on every ordinary invoice, and it is what the dismiss door keys on.

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
                                      provenance, duplicate_of_invoice_id)
                values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16,
                        $17, $18, $19, $20)
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
                duplicate_of_invoice_id,
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
        tenant_id: str,
        branch_id: str | None = None,
        supplier_id: str | None = None,
        status: str | None = None,
    ) -> list[asyncpg.Record]:
        """C6 invoice list for one tenant, newest first; every filter
        optional. Carries the branch name (WP-32: the list shows names, not
        UUIDs) and, for a held duplicate, the number of the invoice it copies
        - joined rather than fetched per row, so the list stays one query.

        The tenant filter arrived with WP-73: until then this list had none,
        which was fine only while the API had one tenant to show.

        **A dismissed invoice is not in the working list.** Asking for no status
        means every status a reviewer still has work on, which is what the
        founder wanted back: a resolved duplicate leaves. Asking for it by name
        (`?status=dismissed`) still returns it, so the record is reachable
        without a screen having to exist for it."""
        return await self.pool.fetch(
            """
            select i.id, i.supplier_name, i.supplier_id, i.invoice_no, i.invoice_date,
                   i.currency, i.total, i.status, i.created_at, i.branch_id, i.document_id,
                   i.duplicate_of_invoice_id, b.name as branch_name,
                   dup.invoice_no as duplicate_of_invoice_no
            from invoices i
            left join branches b on b.id = i.branch_id
            left join invoices dup on dup.id = i.duplicate_of_invoice_id
            where i.tenant_id = $4
              and ($1::uuid is null or i.branch_id = $1)
              and ($2::uuid is null or i.supplier_id = $2)
              and ($3::text is null or i.status = $3)
              and ($3::text is not null or i.status <> 'dismissed')
            order by i.created_at desc, i.id desc
            """,
            branch_id,
            supplier_id,
            status,
            tenant_id,
        )

    async def list_invoice_headers_for_tenant(self, tenant_id: str) -> list[asyncpg.Record]:
        """Every invoice header for one tenant, newest first - WP-44's
        duplicate check compares the incoming paper against these in Python,
        so the normalization rule (matching.normalize_invoice_no) lives once,
        never re-implemented in SQL. Fine at demo volume; revisit with an
        index and a WHERE clause when a tenant has thousands (§2 rule 8).

        Dismissed rows are excluded: `find_duplicate` takes the newest match, so
        leaving them in would hold a third send against a copy the reviewer has
        already thrown away, and the reply would read out its date."""
        return await self.pool.fetch(
            """
            select id, supplier_id, supplier_name, invoice_no, invoice_date, currency,
                   total, status, created_at
            from invoices
            where tenant_id = $1
              and status <> 'dismissed'
            order by created_at desc, id desc
            """,
            tenant_id,
        )

    async def get_supplier_item(self, item_id: str, *, tenant_id: str) -> asyncpg.Record | None:
        return await self.pool.fetchrow(
            """
            select id, canonical_name, unit, pack_size, last_price, prev_price, last_price_at
            from supplier_items where id = $1 and tenant_id = $2
            """,
            item_id,
            tenant_id,
        )

    async def list_item_prices(self, item_id: str, *, tenant_id: str) -> list[asyncpg.Record]:
        """One item's confirmed price history, oldest first (the C6 sparkline
        draws left to right)."""
        return await self.pool.fetch(
            """
            select price, observed_at, invoice_id
            from supplier_item_prices
            where supplier_item_id = $1 and tenant_id = $2
            order by observed_at, id
            """,
            item_id,
            tenant_id,
        )

    # -- Supplier memory (WP-22, plan.md §5 layer 4) -------------------------

    async def list_suppliers(self, tenant_id: str) -> list[asyncpg.Record]:
        return await self.pool.fetch(
            # Ordered so matching.match_supplier's tie-break sees the same
            # rows in the same order on every run (2026-09-05 eng review).
            "select id, name, name_aliases from suppliers where tenant_id = $1 order by name",
            tenant_id,
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

    async def list_ingredients(self, *, tenant_id: str) -> list[asyncpg.Record]:
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

    async def list_mapped_packs(self, *, tenant_id: str) -> list[asyncpg.Record]:
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

    async def list_mapped_pack_costs(self, *, tenant_id: str) -> list[asyncpg.Record]:
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

    async def list_unmapped_supplier_items(self, *, tenant_id: str) -> list[asyncpg.Record]:
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

    async def get_supplier_item_for_mapping(
        self, supplier_item_id: str, *, tenant_id: str
    ) -> asyncpg.Record | None:
        """The pack plus the material it currently points at, if any."""
        return await self.pool.fetchrow(
            """
            select s.id::text as id, s.tenant_id::text as tenant_id, s.canonical_name,
                   s.unit, s.pack_size, s.pack_size_override,
                   s.ingredient_id::text as ingredient_id,
                   i.name as ingredient_name, i.base_unit as ingredient_base_unit
            from supplier_items s
            left join ingredients i on i.id = s.ingredient_id
            where s.id = $1 and s.tenant_id = $2
            """,
            supplier_item_id,
            tenant_id,
        )

    async def get_ingredient(self, ingredient_id: str, *, tenant_id: str) -> asyncpg.Record | None:
        return await self.pool.fetchrow(
            """
            select id::text as id, tenant_id::text as tenant_id, name, base_unit, created_at
            from ingredients where id = $1 and tenant_id = $2
            """,
            ingredient_id,
            tenant_id,
        )

    async def rejected_ingredients_by_item(
        self, *, tenant_id: str, item_id: str | None = None
    ) -> dict[str, set[str]]:
        """Materials a person already said each pack is **not**, keyed by
        pack, for a whole tenant at once (or one pack of it).

        Derived from the audit trail rather than kept in a second table: a
        rejection is a human decision, and that is exactly what `audit_events`
        records (C8). A parallel table would hold the same fact twice, which is
        the drift migration 0010 was written to delete.

        The queue asks this for every row it renders, so it is one query rather
        than one per pack. `distinct on` keeps only the newest event per
        (pack, material) pair, so rejecting a material and later approving it
        reads correctly, and so does approving and later unmapping. Served by
        the 0011 subject index."""
        rows = await self.pool.fetch(
            """
            select distinct on (subject_id, detail->>'ingredient_id')
                   subject_id::text as supplier_item_id,
                   detail->>'ingredient_id' as ingredient_id, action
            from audit_events
            where subject_type = 'supplier_item'
              and tenant_id = $1
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

    async def create_ingredient(
        self, *, tenant_id: str, name: str, base_unit: str, actor: str
    ) -> asyncpg.Record:
        """A shelf with nothing on it yet - the loader's material door (WP-64).

        M5 could only ever create a material *through* a merge, because until
        M6 a material with no pack mapped to it had no reason to exist. A
        recipe gives it one: the menu names "Saffron" long before any invoice
        does, and the plate that uses it reads *incomplete* naming exactly
        that, which is the honest answer and the consultant's next task.

        Front-loading the catalog this way also makes the M5 queue easier
        rather than harder - the matcher can only propose materials that
        already exist, so a menu loaded first turns a blank mapping queue into
        a list of proposals.

        One row, one audit row, one transaction, and the tenant-name unique
        index refuses a second "Saffron" - creation stays one click per row,
        never a bulk keystroke that mints twelve materials through a side
        door (row 64)."""
        async with self.pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                """
                insert into ingredients (tenant_id, name, base_unit)
                values ($1, $2, $3)
                returning id::text as id, tenant_id::text as tenant_id, name, base_unit
                """,
                tenant_id,
                name,
                base_unit,
            )
            await _insert_audit_event(
                conn,
                tenant_id=tenant_id,
                actor=actor,
                action="ingredient.created",
                subject_type="ingredient",
                subject_id=row["id"],
                detail={"name": name, "base_unit": base_unit},
            )
        return row

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
        would be unapprovable without it.

        The link is written `where tenant_id = ...` as well as by id, and a
        pack outside the tenant raises rather than writing an audit row about
        nothing (WP-73); the 0012 composite key refuses the material half of
        a cross-tenant merge regardless."""
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
            updated = await conn.execute(
                "update supplier_items set ingredient_id = $2 where id = $1 and tenant_id = $3",
                supplier_item_id,
                ingredient_id,
                tenant_id,
            )
            if updated != "UPDATE 1":
                raise LookupError(f"supplier item {supplier_item_id} is not in tenant {tenant_id}")
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
            updated = await conn.execute(
                "update supplier_items set ingredient_id = null where id = $1 and tenant_id = $2",
                supplier_item_id,
                tenant_id,
            )
            if updated != "UPDATE 1":
                raise LookupError(f"supplier item {supplier_item_id} is not in tenant {tenant_id}")
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
            item = await conn.fetchrow(
                "select pack_size_override from supplier_items "
                "where id = $1 and tenant_id = $2 for update",
                supplier_item_id,
                tenant_id,
            )
            if item is None:
                raise LookupError(f"supplier item {supplier_item_id} is not in tenant {tenant_id}")
            previous = item["pack_size_override"]
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

    async def list_blocked_costs(self, *, tenant_id: str) -> list[asyncpg.Record]:
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

    # -- Menu and recipes (M6 WP-60) ------------------------------------------
    #
    # The one door for menu writes. Every function here is one transaction with
    # one audit_events row naming its actor (C8) - selling-price history lives
    # in those rows, not a price table, until a screen reads one (§2 rule 8).
    # Refusals with reasons happen at the API layer; the constraints in 0015
    # are the backstop, so a caller the API never met still cannot write the
    # shapes that divide by zero or cost an empty set as pure margin.

    async def list_menu_items(self, *, tenant_id: str) -> list[asyncpg.Record]:
        """Every menu item - archived ones included, flagged - with its current
        recipe version, in one query regardless of item count (the bounded-
        queries rule, eng review D10). The current recipe is the newest
        version: no pointer column to keep in sync, the table is the truth."""
        return await self.pool.fetch(
            """
            select m.id::text as id, m.name, m.category, m.selling_price, m.archived_at,
                   m.created_at,
                   r.id::text as recipe_id, r.version, r.yield_portions, r.yield_label,
                   (select count(*) from recipe_components c where c.recipe_id = r.id)
                     as component_count
            from menu_items m
            left join lateral (
                select * from recipes where menu_item_id = m.id order by version desc limit 1
            ) r on true
            where m.tenant_id = $1
            order by m.name
            """,
            tenant_id,
        )

    async def get_menu_item(self, menu_item_id: str, *, tenant_id: str) -> asyncpg.Record | None:
        return await self.pool.fetchrow(
            """
            select id::text as id, tenant_id::text as tenant_id, name, category,
                   selling_price, archived_at, created_at
            from menu_items where id = $1 and tenant_id = $2
            """,
            menu_item_id,
            tenant_id,
        )

    async def live_menu_item_by_name(self, *, tenant_id: str, name: str) -> asyncpg.Record | None:
        """The item the loader is about to write into, found the way the menu
        itself identifies one: by name, among the live rows (WP-64).

        There is no menu code column and there is not going to be one until a
        menu shows two dishes with the same name - the printed code on the
        consultant's spreadsheet identifies the row on *their* page, not ours.
        An archived namesake is deliberately not returned: bringing it back is
        a click a person makes, and a re-upload must never resurrect a dish
        somebody took off the menu."""
        return await self.pool.fetchrow(
            """
            select id::text as id, tenant_id::text as tenant_id, name, category,
                   selling_price, archived_at, created_at
            from menu_items
            where tenant_id = $1 and name = $2 and archived_at is null
            """,
            tenant_id,
            name,
        )

    async def get_current_recipe(
        self, menu_item_id: str, *, tenant_id: str
    ) -> asyncpg.Record | None:
        """The newest version - which is what 'current' means here, by schema
        rather than by a pointer that could drift."""
        return await self.pool.fetchrow(
            """
            select id::text as id, version, yield_portions, yield_label, created_at
            from recipes where menu_item_id = $1 and tenant_id = $2
            order by version desc limit 1
            """,
            menu_item_id,
            tenant_id,
        )

    async def get_recipe_components(
        self, recipe_id: str, *, tenant_id: str
    ) -> list[asyncpg.Record]:
        """One version's components. `has_packs` says whether any supplier
        product is mapped onto the ingredient yet - the difference between
        "map a product to it" and "confirm a purchase of it", which are two
        different sentences on the screen (WP-61)."""
        return await self.pool.fetch(
            """
            select c.position, c.ingredient_id::text as ingredient_id, c.qty, c.unit,
                   c.source_text, ing.name as ingredient_name, ing.base_unit,
                   exists (select 1 from supplier_items si where si.ingredient_id = ing.id)
                     as has_packs
            from recipe_components c
            join ingredients ing on ing.id = c.ingredient_id
            where c.recipe_id = $1 and c.tenant_id = $2
            order by c.position
            """,
            recipe_id,
            tenant_id,
        )

    async def list_current_recipe_components(self, *, tenant_id: str) -> list[asyncpg.Record]:
        """Every item's *current* recipe version with its components, one query
        however long the menu grows (WP-61, the bounded-queries rule D10). The
        menu screen joins this against the material prices in Python - the
        `list_mapped_pack_costs` shape one layer up."""
        return await self.pool.fetch(
            """
            with current as (
                select distinct on (menu_item_id) id, menu_item_id
                from recipes
                where tenant_id = $1
                order by menu_item_id, version desc, id desc
            )
            select cur.menu_item_id::text as menu_item_id,
                   c.position, c.ingredient_id::text as ingredient_id, c.qty, c.unit,
                   c.source_text, ing.name as ingredient_name, ing.base_unit,
                   exists (select 1 from supplier_items si where si.ingredient_id = ing.id)
                     as has_packs
            from current cur
            join recipe_components c on c.recipe_id = cur.id
            join ingredients ing on ing.id = c.ingredient_id
            order by cur.menu_item_id, c.position
            """,
            tenant_id,
        )

    async def list_newest_purchases(self, *, tenant_id: str) -> list[asyncpg.Record]:
        """The newest confirmed stock line per material - costed **or not**
        (WP-61 amendment 3, D11).

        `list_mapped_pack_costs` picks the newest *costed* line, which is the
        price. This asks the prior question: what was the newest *purchase*?
        When the two disagree - the newest purchase could not be costed (a
        bare carton, a missing price, a foreign-currency hold) - the older
        price silently looks current, which is the silent-stale-number class
        one layer up from WP-19. The caller compares: a `costed = false` row
        here caps its material and every plate above it at *estimated* and
        names this line as the reason.

        Same ordering and same qty >= 0 rule as the price query, so 'newest'
        means the same thing in both and a credit line wins neither."""
        return await self.pool.fetch(
            """
            select distinct on (ing.id)
                   ing.id::text as ingredient_id,
                   l.id::text as invoice_line_id, l.position, l.raw_name, l.qty, l.unit,
                   l.pack_size, l.unit_price,
                   (l.cost_per_base_unit is not null and l.cost_base_unit = ing.base_unit)
                     as costed,
                   s.pack_size_override,
                   inv.id::text as invoice_id, inv.invoice_date, inv.currency,
                   t.currency as tenant_currency,
                   coalesce(inv.invoice_date,
                            (inv.confirmed_at at time zone 'UTC')::date) as purchased_on
            from supplier_items s
            join ingredients ing on ing.id = s.ingredient_id
            join invoice_lines l on l.supplier_item_id = s.id
            join invoices inv on inv.id = l.invoice_id
            join tenants t on t.id = inv.tenant_id
            where s.tenant_id = $1
              and s.ingredient_id is not null
              and inv.status = 'confirmed'
              and l.line_kind = 'stock_item'
              and coalesce(l.qty, 0) >= 0
            order by ing.id, purchased_on desc, inv.confirmed_at desc,
                     l.position desc, l.id desc
            """,
            tenant_id,
        )

    async def list_price_move_pairs(self, *, tenant_id: str) -> list[asyncpg.Record]:
        """Per material, its two newest costed lines across **all** its mapped
        packs - the raw material of WP-63's money moment.

        `list_mapped_pack_costs` keeps each pack's newest line only, so the
        winning pack's *own previous* purchase - the same-pack baseline D3
        demands - is invisible there. This ranks every costed line per
        material and returns the top two: the current price and whatever set
        the price before it. The caller compares - same pack means a real
        move with a delta; a different pack means the price basis changed,
        and a delta across packs is a pack artifact wearing a percent sign,
        so none is computed (WP-28's own rule, one layer up).

        Same joins, filters and ordering as the price query, so 'newest'
        means the same thing on every screen and a credit line wins
        nothing."""
        return await self.pool.fetch(
            """
            with costed as (
                select ing.id::text as ingredient_id, ing.name as ingredient_name,
                       ing.base_unit,
                       s.id::text as supplier_item_id, s.canonical_name,
                       sup.name as supplier_name,
                       l.id as line_uuid, l.position, l.pack_size,
                       l.cost_per_base_unit, l.cost_basis,
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
            ),
            ranked as (
                select *, row_number() over (
                    partition by ingredient_id
                    order by purchased_on desc, confirmed_at desc,
                             position desc, line_uuid desc
                ) as recency
                from costed
            )
            select ingredient_id, ingredient_name, base_unit, supplier_item_id,
                   canonical_name, supplier_name, line_uuid::text as invoice_line_id,
                   position, pack_size, cost_per_base_unit, cost_basis, invoice_id,
                   invoice_date, confirmed_at, purchased_on, recency
            from ranked where recency <= 2
            order by ingredient_id, recency
            """,
            tenant_id,
        )

    async def create_menu_item(
        self,
        *,
        tenant_id: str,
        name: str,
        selling_price: Decimal,
        actor: str,
        category: str | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> asyncpg.Record:
        """One item, one audit row, one transaction. Raises UniqueViolationError
        when a live item already holds the name (the 0015 partial index); the
        API turns that into the plain sentence.

        The price is quantized to the fils before anything sees it, so the
        audit detail and the column hold the same bytes - "17" typed and
        "17.000" stored must not read as two different claims. `category` is
        the menu's own section (0016, design D9), null when the menu prints
        none."""
        selling_price = selling_price.quantize(PRICE_QUANTUM)
        async with self._txn(conn) as conn:
            row = await conn.fetchrow(
                """
                insert into menu_items (tenant_id, name, selling_price, category)
                values ($1, $2, $3, $4)
                returning id::text as id, name, category, selling_price, archived_at, created_at
                """,
                tenant_id,
                name,
                selling_price,
                category,
            )
            await _insert_audit_event(
                conn,
                tenant_id=tenant_id,
                actor=actor,
                action="menu_item.created",
                subject_type="menu_item",
                subject_id=row["id"],
                detail={"name": name, "selling_price": str(selling_price), "category": category},
            )
        return row

    async def set_menu_item_price(
        self,
        menu_item_id: str,
        *,
        tenant_id: str,
        selling_price: Decimal,
        actor: str,
        conn: asyncpg.Connection | None = None,
    ) -> bool:
        """The owner said a new price out loud. The audit row carries old and
        new - that trail *is* the selling-price history until a screen needs
        more (§2 rule 8). Returns False untouched when the price is the same,
        so re-sending a form cannot mint a history of nothing changing.
        Quantized like the insert, so detail and column never disagree."""
        selling_price = selling_price.quantize(PRICE_QUANTUM)
        async with self._txn(conn) as conn:
            previous = await conn.fetchval(
                "select selling_price from menu_items where id = $1 and tenant_id = $2 for update",
                menu_item_id,
                tenant_id,
            )
            if previous is None or previous == selling_price:
                return False
            await conn.execute(
                "update menu_items set selling_price = $2 where id = $1",
                menu_item_id,
                selling_price,
            )
            await _insert_audit_event(
                conn,
                tenant_id=tenant_id,
                actor=actor,
                action="menu_item.price_changed",
                subject_type="menu_item",
                subject_id=menu_item_id,
                detail={
                    "selling_price": str(selling_price),
                    "previous_selling_price": str(previous),
                },
            )
        return True

    async def set_menu_item_category(
        self,
        menu_item_id: str,
        *,
        tenant_id: str,
        category: str | None,
        actor: str,
        conn: asyncpg.Connection | None = None,
    ) -> bool:
        """The menu's own section moved (Tea Corner -> Hot Drinks), or the
        spreadsheet's typo in it was fixed. The price door's twin, for the
        same reason: the menu screen *groups* by this, so a category the CSV
        has corrected and Faida has not is a wrong heading on the demo's
        closing image (WP-64, D19). Returns False untouched when it already
        reads that way, so a re-upload writes no history of nothing changing."""
        async with self._txn(conn) as conn:
            row = await conn.fetchrow(
                "select category from menu_items where id = $1 and tenant_id = $2 for update",
                menu_item_id,
                tenant_id,
            )
            if row is None or row["category"] == category:
                return False
            await conn.execute(
                "update menu_items set category = $2 where id = $1", menu_item_id, category
            )
            await _insert_audit_event(
                conn,
                tenant_id=tenant_id,
                actor=actor,
                action="menu_item.category_changed",
                subject_type="menu_item",
                subject_id=menu_item_id,
                detail={"category": category, "previous_category": row["category"]},
            )
        return True

    async def archive_menu_item(self, menu_item_id: str, *, tenant_id: str, actor: str) -> bool:
        """The reverse gear the menu needs (Codex 9): out of the ranking and
        the coverage count, never deleted, one click back. Returns False when
        it was already archived - no second audit row for a no-op."""
        async with self.pool.acquire() as conn, conn.transaction():
            row = await conn.fetchval(
                """
                update menu_items set archived_at = now()
                where id = $1 and tenant_id = $2 and archived_at is null
                returning id
                """,
                menu_item_id,
                tenant_id,
            )
            if row is None:
                return False
            await _insert_audit_event(
                conn,
                tenant_id=tenant_id,
                actor=actor,
                action="menu_item.archived",
                subject_type="menu_item",
                subject_id=menu_item_id,
            )
        return True

    async def unarchive_menu_item(self, menu_item_id: str, *, tenant_id: str, actor: str) -> bool:
        """One click back. Raises UniqueViolationError when a live item has
        taken the name meanwhile - two live rows with one name is exactly what
        the 0015 partial index refuses, whichever door tries it."""
        async with self.pool.acquire() as conn, conn.transaction():
            row = await conn.fetchval(
                """
                update menu_items set archived_at = null
                where id = $1 and tenant_id = $2 and archived_at is not null
                returning id
                """,
                menu_item_id,
                tenant_id,
            )
            if row is None:
                return False
            await _insert_audit_event(
                conn,
                tenant_id=tenant_id,
                actor=actor,
                action="menu_item.unarchived",
                subject_type="menu_item",
                subject_id=menu_item_id,
            )
        return True

    async def create_recipe_version(
        self,
        menu_item_id: str,
        *,
        tenant_id: str,
        yield_portions: Decimal,
        yield_label: str | None,
        components: list[dict],
        actor: str,
        conn: asyncpg.Connection | None = None,
    ) -> asyncpg.Record:
        """Append the next version - editing never touches an old one, so
        'versioned' is a property of the schema rather than a subsystem.

        `version = max+1` is computed inside the insert, inside the
        transaction, and `unique (menu_item_id, version)` makes two concurrent
        saves fail loudly instead of minting the same number twice (D17); the
        API answers the loser with a sentence, not a stack trace.

        A component naming another tenant's ingredient raises
        ForeignKeyViolationError from the 0012-shape composite key - Postgres
        enforces tenancy at the write, whatever the application forgot."""
        async with self._txn(conn) as conn:
            recipe = await conn.fetchrow(
                """
                insert into recipes (tenant_id, menu_item_id, version, yield_portions, yield_label)
                values ($1, $2,
                        (select coalesce(max(version), 0) + 1
                         from recipes where menu_item_id = $2),
                        $3, $4)
                returning id::text as id, version, yield_portions, yield_label, created_at
                """,
                tenant_id,
                menu_item_id,
                yield_portions,
                yield_label,
            )
            await conn.executemany(
                """
                insert into recipe_components (tenant_id, recipe_id, position, ingredient_id,
                                               qty, unit, source_text)
                values ($1, $2, $3, $4, $5, $6, $7)
                """,
                [
                    (
                        tenant_id,
                        recipe["id"],
                        position,
                        component["ingredient_id"],
                        component["qty"],
                        component["unit"],
                        component.get("source_text"),
                    )
                    for position, component in enumerate(components)
                ],
            )
            await _insert_audit_event(
                conn,
                tenant_id=tenant_id,
                actor=actor,
                action="recipe.version_created",
                subject_type="menu_item",
                subject_id=menu_item_id,
                detail={
                    "recipe_id": recipe["id"],
                    "version": recipe["version"],
                    "component_count": len(components),
                },
            )
        return recipe

    async def load_menu_recipe(
        self,
        *,
        tenant_id: str,
        name: str,
        category: str | None,
        selling_price: Decimal,
        yield_portions: Decimal,
        yield_label: str | None,
        components: list[dict],
        actor: str,
    ) -> dict:
        """One row of the batch loader: **one recipe, one transaction** (WP-64).

        A CSV row that half-loads is the failure this method exists to make
        impossible - an item created with no recipe reads *incomplete* on the
        menu screen for a reason nobody can see, and a consultant re-uploading
        would not know which half landed. So the item, its price, its category
        and the recipe version commit together or not at all, and a refused
        row leaves the other 44 recipes untouched.

        It writes through the doors already here rather than beside them:
        `create_menu_item`, `set_menu_item_price`, `set_menu_item_category`
        and `create_recipe_version`, each joining this transaction and each
        still landing its own audit row naming the actor (C8). Nothing about
        a CSV upload is privileged.

        Idempotent by D8's rule (`recipes.py`): loading a file whose recipes
        already say what Faida says writes nothing at all and returns
        `unchanged`, so committing the same file twice is a no-op and a
        43-of-45-rows-unchanged re-upload costs 43 no-ops.

        An **archived** namesake is refused rather than resurrected: the
        partial unique index would happily allow a second live "Nido Shake",
        and a re-upload that quietly forks a dish somebody took off the menu
        is worse than a sentence asking for a click.
        """
        incoming = recipe_key(
            yield_portions,
            [component_key(c["ingredient_id"], c["qty"], c["unit"]) for c in components],
        )
        async with self.pool.acquire() as conn, conn.transaction():
            item = await conn.fetchrow(
                """
                select id::text as id, archived_at
                from menu_items where tenant_id = $1 and name = $2
                order by archived_at nulls first
                limit 1
                for update
                """,
                tenant_id,
                name,
            )
            if item is not None and item["archived_at"] is not None:
                return {"outcome": "archived", "menu_item_id": item["id"], "changed": []}

            if item is None:
                created = await self.create_menu_item(
                    tenant_id=tenant_id,
                    name=name,
                    selling_price=selling_price,
                    category=category,
                    actor=actor,
                    conn=conn,
                )
                recipe = await self.create_recipe_version(
                    created["id"],
                    tenant_id=tenant_id,
                    yield_portions=yield_portions,
                    yield_label=yield_label,
                    components=components,
                    actor=actor,
                    conn=conn,
                )
                return {
                    "outcome": "created",
                    "menu_item_id": created["id"],
                    "version": recipe["version"],
                    "changed": [],
                }

            menu_item_id = item["id"]
            changed: list[str] = []
            if await self.set_menu_item_price(
                menu_item_id,
                tenant_id=tenant_id,
                selling_price=selling_price,
                actor=actor,
                conn=conn,
            ):
                changed.append("selling price")
            if await self.set_menu_item_category(
                menu_item_id, tenant_id=tenant_id, category=category, actor=actor, conn=conn
            ):
                changed.append("category")

            current = await conn.fetchrow(
                """
                select id::text as id, version, yield_portions
                from recipes where menu_item_id = $1 order by version desc limit 1
                """,
                menu_item_id,
            )
            stored: RecipeKey | None = None
            if current is not None:
                rows = await conn.fetch(
                    "select ingredient_id::text as ingredient_id, qty, unit "
                    "from recipe_components where recipe_id = $1",
                    current["id"],
                )
                stored = recipe_key(
                    current["yield_portions"],
                    [component_key(r["ingredient_id"], r["qty"], r["unit"]) for r in rows],
                )

            if stored is not None and recipes_match(stored, incoming):
                return {
                    "outcome": "unchanged",
                    "menu_item_id": menu_item_id,
                    "version": current["version"],
                    "changed": changed,
                }

            recipe = await self.create_recipe_version(
                menu_item_id,
                tenant_id=tenant_id,
                yield_portions=yield_portions,
                yield_label=yield_label,
                components=components,
                actor=actor,
                conn=conn,
            )
            return {
                "outcome": "version_added",
                "menu_item_id": menu_item_id,
                "version": recipe["version"],
                "changed": changed,
            }

    # -- Sales (M8 WP-80) ------------------------------------------------------

    async def list_branches(self, *, tenant_id: str) -> list[asyncpg.Record]:
        """The tenant's branches, for the loader's branch picker and the
        sales table. The console has needed this since the upload screen and
        derived it from the invoice list instead (C6 extended, M8)."""
        return await self.pool.fetch(
            "select id::text as id, name, timezone from branches where tenant_id = $1 "
            "order by name, id",
            tenant_id,
        )

    async def list_branch_aliases(self, *, tenant_id: str) -> list[asyncpg.Record]:
        return await self.pool.fetch(
            """
            select id::text as id, branch_id::text as branch_id, alias, alias_key
            from branch_aliases where tenant_id = $1
            order by alias_key
            """,
            tenant_id,
        )

    async def save_branch_alias(
        self, branch_id: str, *, tenant_id: str, alias: str, alias_key: str, actor: str
    ) -> dict:
        """Teach the chain one till label for one branch (C11.1). Idempotent:
        the same label for the same branch answers the existing row and
        writes nothing; the same label for another branch answers that
        branch's id so the API can say which. One audit row on a write."""
        async with self.pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                """
                insert into branch_aliases (tenant_id, branch_id, alias_key, alias)
                values ($1, $2, $3, $4)
                on conflict (tenant_id, alias_key) do nothing
                returning id::text as id, branch_id::text as branch_id, alias, alias_key
                """,
                tenant_id,
                branch_id,
                alias_key,
                alias,
            )
            if row is not None:
                await _insert_audit_event(
                    conn,
                    tenant_id=tenant_id,
                    actor=actor,
                    action="branch_alias.saved",
                    subject_type="branch_alias",
                    subject_id=row["id"],
                    detail={"branch_id": branch_id, "alias": alias, "alias_key": alias_key},
                )
                return {"alias": row, "created": True, "other_branch_id": None}
            existing = await conn.fetchrow(
                """
                select id::text as id, branch_id::text as branch_id, alias, alias_key
                from branch_aliases where tenant_id = $1 and alias_key = $2
                """,
                tenant_id,
                alias_key,
            )
        if existing["branch_id"] == branch_id:
            return {"alias": existing, "created": False, "other_branch_id": None}
        return {"alias": None, "created": False, "other_branch_id": existing["branch_id"]}

    async def list_sales_layouts(self, *, tenant_id: str) -> list[asyncpg.Record]:
        return await self.pool.fetch(
            """
            select id::text as id, name, header_key, columns, amount_basis, date_order,
                   created_at, updated_at
            from sales_layouts where tenant_id = $1
            order by name
            """,
            tenant_id,
        )

    async def get_sales_layout(self, layout_id: str, *, tenant_id: str) -> asyncpg.Record | None:
        return await self.pool.fetchrow(
            """
            select id::text as id, name, header_key, columns, amount_basis, date_order,
                   created_at, updated_at
            from sales_layouts where id = $1 and tenant_id = $2
            """,
            layout_id,
            tenant_id,
        )

    async def save_sales_layout(
        self,
        *,
        tenant_id: str,
        name: str,
        header_key: str,
        columns: dict,
        amount_basis: str,
        date_order: str,
        actor: str,
    ) -> dict:
        """Upsert by name (C11.1): the till is the layout's identity, the
        header key is evidence. Saving the same layout again updates it in
        place - the consultant re-mapped a renamed column - and one audit row
        records each save with whether it created or updated."""
        async with self.pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                """
                insert into sales_layouts
                    (tenant_id, name, header_key, columns, amount_basis, date_order)
                values ($1, $2, $3, $4, $5, $6)
                on conflict (tenant_id, name) do update
                    set header_key = excluded.header_key,
                        columns = excluded.columns,
                        amount_basis = excluded.amount_basis,
                        date_order = excluded.date_order,
                        updated_at = now()
                returning id::text as id, name, header_key, columns, amount_basis, date_order,
                          created_at, updated_at, (xmax = 0) as created
                """,
                tenant_id,
                name,
                header_key,
                columns,
                amount_basis,
                date_order,
            )
            await _insert_audit_event(
                conn,
                tenant_id=tenant_id,
                actor=actor,
                action="sales_layout.saved",
                subject_type="sales_layout",
                subject_id=row["id"],
                detail={
                    "name": name,
                    "header_key": header_key,
                    "columns": columns,
                    "amount_basis": amount_basis,
                    "date_order": date_order,
                    "created": row["created"],
                },
            )
        return {"layout": row, "created": row["created"]}

    async def list_sales_days(
        self, *, tenant_id: str, date_from: datetime.date, date_to: datetime.date
    ) -> list[asyncpg.Record]:
        """The stored days in a range, every branch, so the loader can predict
        its outcomes before committing (C11.4)."""
        return await self.pool.fetch(
            f"""
            select {_SALES_DAY_COLUMNS}
            from sales_daily
            where tenant_id = $1 and business_date between $2 and $3
            order by branch_id, business_date
            """,
            tenant_id,
            date_from,
            date_to,
        )

    async def list_sales_lines(self, *, tenant_id: str, day_ids: list[str]) -> list[asyncpg.Record]:
        """The lines of the given days in one query, file order within a day."""
        if not day_ids:
            return []
        return await self.pool.fetch(
            """
            select sales_day_id::text as sales_day_id, position, till_item_id::text as till_item_id,
                   name, code, qty, amount, net_amount
            from sales_lines
            where tenant_id = $1 and sales_day_id = any($2::uuid[])
            order by sales_day_id, position
            """,
            tenant_id,
            day_ids,
        )

    # -- The ratio's reads (M8 WP-81): the period's papers and the coverage sums --

    async def newest_sales_dates(self, *, tenant_id: str) -> dict[str, datetime.date]:
        """Each branch's newest loaded day ever, keyed by branch id, so a row
        with no sales in the period still says when it last had any and the
        default period ends on the tenant's newest day (C11.6)."""
        rows = await self.pool.fetch(
            """
            select branch_id::text as branch_id, max(business_date) as newest
            from sales_daily where tenant_id = $1
            group by branch_id
            """,
            tenant_id,
        )
        return {row["branch_id"]: row["newest"] for row in rows}

    async def sales_months(self, *, tenant_id: str) -> list[datetime.date]:
        """The calendar months holding at least one loaded day, newest first,
        each as its first day: what the sales screen's period picker offers
        (WP-84 review, 2026-09-05). A month it lists always has sales, and a
        tenant's oldest month is reachable however long its history."""
        rows = await self.pool.fetch(
            """
            select distinct date_trunc('month', business_date)::date as month
            from sales_daily where tenant_id = $1
            order by month desc
            """,
            tenant_id,
        )
        return [row["month"] for row in rows]

    async def list_period_invoices(
        self, *, tenant_id: str, date_from: datetime.date, date_to: datetime.date
    ) -> list[asyncpg.Record]:
        """The papers a period's ratio reads (C11.5 and the C9 amendment):
        confirmed ones by `purchased_on` - the printed date, confirm time as
        the tie-breaker, the same `coalesce` costing ranks by, so the materials
        screen and the sales screen agree which week a paper belongs to - and
        the ones still awaiting confirm or held for review by where they sit:
        their printed date, or the day they arrived when they printed none (a
        pending paper has no confirm time, so the costing rule alone would drop
        it from every period). Dismissed and draft papers are nobody's
        purchases. `provenance` rides along for C9's asserted-origin read."""
        return await self.pool.fetch(
            """
            select i.id::text as id, i.branch_id::text as branch_id, i.status, i.currency,
                   i.total, i.tax, i.invoice_date, i.supplier_name, i.invoice_no, i.provenance,
                   coalesce(i.invoice_date, (i.confirmed_at at time zone 'UTC')::date)
                     as purchased_on,
                   coalesce(i.invoice_date, (i.created_at at time zone 'UTC')::date) as placed_on
            from invoices i
            where i.tenant_id = $1
              and i.status in ('confirmed', 'awaiting_confirm', 'needs_review')
              and coalesce(
                    i.invoice_date,
                    ((case when i.status = 'confirmed' then i.confirmed_at else i.created_at end)
                       at time zone 'UTC')::date
                  ) between $2 and $3
            order by 12, i.id
            """,
            tenant_id,
            date_from,
            date_to,
        )

    async def list_period_sales_lines(
        self, *, tenant_id: str, date_from: datetime.date, date_to: datetime.date
    ) -> list[asyncpg.Record]:
        """Every till item with its value over the period's item days, summed
        in SQL and never over lines in Python (C11.8): the positive net value
        (what coverage is measured on) and the refund value (net sales, not
        coverage) apart. Every till item is a row, so the mapping queue shows
        a name the period never sold with a value of 0 rather than hiding it."""
        return await self.pool.fetch(
            """
            select t.id::text as till_item_id, t.name, t.code,
                   t.menu_item_id::text as menu_item_id, t.excluded_at,
                   coalesce(sum(l.net_amount) filter (where l.net_amount > 0), 0)
                     as positive_value,
                   coalesce(sum(l.net_amount) filter (where l.net_amount < 0), 0)
                     as refund_value
            from till_items t
            left join (
                sales_lines l
                join sales_daily d
                  on d.id = l.sales_day_id and d.business_date between $2 and $3
            ) on l.till_item_id = t.id and l.tenant_id = t.tenant_id
            where t.tenant_id = $1
            group by t.id
            order by positive_value desc, t.name, t.id
            """,
            tenant_id,
            date_from,
            date_to,
        )

    async def load_sales_day(
        self,
        *,
        tenant_id: str,
        branch_id: str,
        business_date: datetime.date,
        granularity: str,
        amount_basis: str,
        vat_rate: Decimal | None,
        layout_id: str | None,
        source_sha256: str | None,
        source_filename: str | None,
        lines: list[dict],
        amount: Decimal | None,
        net: Decimal | None,
        actor: str,
    ) -> dict:
        """One branch-day, **one transaction**, one outcome (C11.4):

            loaded      no day stored for this branch-date: the day and its
                        lines are written, with `sales_day.loaded`
            unchanged   the stored day has the same granularity, basis and
                        multiset of lines in any order: nothing is written,
                        no audit row appears
            replaced    anything else: the lines are deleted and re-inserted
                        and the day row updated, with one `sales_day.replaced`
                        row carrying the previous and new figures and hashes

        so re-uploading the same file is a no-op, a corrected file replaces
        exactly the days it carries, and nothing is ever double-counted. The
        row is locked `for update` and the branch-day is held under a
        transaction-scoped advisory lock first, because a first load has no
        row to lock: two clients posting the same new day at once are
        serialised, and the second reads `unchanged` rather than a unique
        violation (the refresh-mid-run case).

        `lines` carry their net amounts already - the one division lives in
        `takings.net_amount`, applied by the door - and the day's takings and
        net sales are the exact sums of what is stored (Codex 10). Till items
        are minted here on first sight, by code or by normalised name, with
        `on conflict do nothing` so a race mints one row; a known code seen
        under a new name keeps its row and its mapping and writes
        `till_item.renamed`."""
        if granularity == "summary":
            takings = (amount or Decimal(0)).quantize(FILS)
            net_sales = (net or Decimal(0)).quantize(FILS)
        else:
            takings = sum((line["amount"] for line in lines), Decimal(0)).quantize(FILS)
            net_sales = sum((line["net_amount"] for line in lines), Decimal(0)).quantize(FILS)
        incoming_key = day_key(
            granularity,
            amount_basis,
            [(line["name"], line["code"], line["qty"], line["amount"]) for line in lines],
            amount,
        )

        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "select pg_advisory_xact_lock(hashtext($1))",
                f"sales_daily:{tenant_id}:{branch_id}:{business_date.isoformat()}",
            )
            existing = await conn.fetchrow(
                f"""
                select {_SALES_DAY_COLUMNS}
                from sales_daily
                where tenant_id = $1 and branch_id = $2 and business_date = $3
                for update
                """,
                tenant_id,
                branch_id,
                business_date,
            )
            previous: dict | None = None
            if existing is not None:
                stored_lines = await conn.fetch(
                    "select name, code, qty, amount from sales_lines where sales_day_id = $1",
                    existing["id"],
                )
                stored_key = day_key(
                    existing["granularity"],
                    existing["amount_basis"],
                    [(r["name"], r["code"], r["qty"], r["amount"]) for r in stored_lines],
                    existing["takings"],
                )
                if stored_key == incoming_key:
                    return {"outcome": "unchanged", "previous": None, "day": existing}
                previous = {
                    "takings": str(existing["takings"]),
                    "net_sales": str(existing["net_sales"]),
                    "line_count": existing["line_count"],
                    "source_sha256": existing["source_sha256"],
                }
                await conn.execute(
                    "delete from sales_lines where sales_day_id = $1", existing["id"]
                )
                day = await conn.fetchrow(
                    f"""
                    update sales_daily
                       set granularity = $3, amount_basis = $4, vat_rate = $5, takings = $6,
                           net_sales = $7, line_count = $8, layout_id = $9, source_sha256 = $10,
                           source_filename = $11, loaded_by = $12, loaded_at = now()
                     where tenant_id = $1 and id = $2
                    returning {_SALES_DAY_COLUMNS}
                    """,
                    tenant_id,
                    existing["id"],
                    granularity,
                    amount_basis,
                    vat_rate,
                    takings,
                    net_sales,
                    len(lines),
                    layout_id,
                    source_sha256,
                    source_filename,
                    actor,
                )
            else:
                day = await conn.fetchrow(
                    f"""
                    insert into sales_daily
                        (tenant_id, branch_id, business_date, granularity, amount_basis, vat_rate,
                         takings, net_sales, line_count, layout_id, source_sha256,
                         source_filename, loaded_by)
                    values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                    returning {_SALES_DAY_COLUMNS}
                    """,
                    tenant_id,
                    branch_id,
                    business_date,
                    granularity,
                    amount_basis,
                    vat_rate,
                    takings,
                    net_sales,
                    len(lines),
                    layout_id,
                    source_sha256,
                    source_filename,
                    actor,
                )

            till_item_ids = await self._mint_till_items(
                conn, tenant_id=tenant_id, lines=lines, actor=actor
            )
            if lines:
                await conn.executemany(
                    """
                    insert into sales_lines
                        (tenant_id, sales_day_id, position, till_item_id, name, code, qty,
                         amount, net_amount)
                    values ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    """,
                    [
                        (
                            tenant_id,
                            day["id"],
                            line["position"],
                            till_item_ids[till_item_key(line["name"], line["code"])],
                            line["name"],
                            code_key(line["code"]),
                            line["qty"],
                            line["amount"],
                            line["net_amount"],
                        )
                        for line in lines
                    ],
                )

            figures = {
                "takings": str(takings),
                "net_sales": str(net_sales),
                "line_count": len(lines),
                "source_sha256": source_sha256,
            }
            if previous is None:
                await _insert_audit_event(
                    conn,
                    tenant_id=tenant_id,
                    actor=actor,
                    action="sales_day.loaded",
                    subject_type="sales_day",
                    subject_id=day["id"],
                    detail={
                        "branch_id": branch_id,
                        "business_date": business_date.isoformat(),
                        "granularity": granularity,
                        "amount_basis": amount_basis,
                        **figures,
                    },
                )
                return {"outcome": "loaded", "previous": None, "day": day}
            await _insert_audit_event(
                conn,
                tenant_id=tenant_id,
                actor=actor,
                action="sales_day.replaced",
                subject_type="sales_day",
                subject_id=day["id"],
                detail={
                    "branch_id": branch_id,
                    "business_date": business_date.isoformat(),
                    "granularity": granularity,
                    "amount_basis": amount_basis,
                    "previous": previous,
                    "new": figures,
                },
            )
            return {"outcome": "replaced", "previous": previous, "day": day}

    async def _mint_till_items(
        self, conn: asyncpg.Connection, *, tenant_id: str, lines: list[dict], actor: str
    ) -> dict[tuple[str, str], str]:
        """Every distinct till item named by `lines`, minted on first sight
        and answered by key (C11.7). By code when the file prints one, by
        normalised name otherwise; the partial unique indexes make the race
        between two loaders mint one row. The last name a code is seen under
        in the file is its display name; a change of it under a known code
        writes `till_item.renamed` and keeps the mapping."""
        wanted: dict[tuple[str, str], str] = {}
        for line in lines:
            wanted[till_item_key(line["name"], line["code"])] = line["name"].strip()
        ids: dict[tuple[str, str], str] = {}
        for (kind, key), name in wanted.items():
            if kind == "code":
                row = await conn.fetchrow(
                    """
                    insert into till_items (tenant_id, name, name_key, code)
                    values ($1, $2, $3, $4)
                    on conflict (tenant_id, code) where code is not null do nothing
                    returning id::text as id, name
                    """,
                    tenant_id,
                    name,
                    name_key(name),
                    key,
                )
                if row is None:
                    row = await conn.fetchrow(
                        "select id::text as id, name from till_items "
                        "where tenant_id = $1 and code = $2",
                        tenant_id,
                        key,
                    )
                    if row["name"] != name:
                        await conn.execute(
                            "update till_items set name = $3, name_key = $4 "
                            "where tenant_id = $1 and id = $2",
                            tenant_id,
                            row["id"],
                            name,
                            name_key(name),
                        )
                        await _insert_audit_event(
                            conn,
                            tenant_id=tenant_id,
                            actor=actor,
                            action="till_item.renamed",
                            subject_type="till_item",
                            subject_id=row["id"],
                            detail={"code": key, "previous_name": row["name"], "name": name},
                        )
            else:
                row = await conn.fetchrow(
                    """
                    insert into till_items (tenant_id, name, name_key, code)
                    values ($1, $2, $3, null)
                    on conflict (tenant_id, name_key) where code is null do nothing
                    returning id::text as id, name
                    """,
                    tenant_id,
                    name,
                    key,
                )
                if row is None:
                    row = await conn.fetchrow(
                        "select id::text as id, name from till_items "
                        "where tenant_id = $1 and name_key = $2 and code is null",
                        tenant_id,
                        key,
                    )
            ids[(kind, key)] = row["id"]
        return ids

    # -- Till items: the mapping door (M8 WP-82) ------------------------------

    #: A till item as the doors answer it: the printed name and code, the
    #: menu item it is mapped to (by a person, never by the loader), and
    #: whether it was marked "not a menu item".
    _TILL_ITEM_SELECT = """
        select t.id::text as id, t.name, t.name_key, t.code,
               t.menu_item_id::text as menu_item_id, m.name as menu_item_name, t.excluded_at
        from till_items t
        left join menu_items m on m.tenant_id = t.tenant_id and m.id = t.menu_item_id
    """

    async def get_till_item(self, till_item_id: str, *, tenant_id: str) -> asyncpg.Record | None:
        return await self.pool.fetchrow(
            self._TILL_ITEM_SELECT + " where t.id = $1 and t.tenant_id = $2",
            till_item_id,
            tenant_id,
        )

    async def map_till_item(
        self, till_item_id: str, *, tenant_id: str, menu_item_id: str, actor: str
    ) -> asyncpg.Record:
        """Approve a till name as a menu item, or move it to another one
        (C11.7). Nothing is stored per line: every line with this name follows
        on the next coverage read, so a remap corrects every day at once.

        The link and the audit row are one transaction (C8), and the row is
        locked first so two keystrokes on one name serialise. Mapping clears
        "not a menu item" - a name that turned out to be a dish after all
        comes back into coverage with the keystroke that says so. A till item
        outside the tenant raises rather than writing an audit row about
        nothing; the 0019 composite key refuses another tenant's menu item
        whatever the API missed."""
        async with self.pool.acquire() as conn, conn.transaction():
            before = await conn.fetchrow(
                "select menu_item_id::text as menu_item_id, excluded_at from till_items "
                "where id = $1 and tenant_id = $2 for update",
                till_item_id,
                tenant_id,
            )
            if before is None:
                raise LookupError(f"till item {till_item_id} is not in tenant {tenant_id}")
            await conn.execute(
                "update till_items set menu_item_id = $3, excluded_at = null "
                "where id = $1 and tenant_id = $2",
                till_item_id,
                tenant_id,
                menu_item_id,
            )
            row = await conn.fetchrow(
                self._TILL_ITEM_SELECT + " where t.id = $1 and t.tenant_id = $2",
                till_item_id,
                tenant_id,
            )
            await _insert_audit_event(
                conn,
                tenant_id=tenant_id,
                actor=actor,
                action="till_item.mapped",
                subject_type="till_item",
                subject_id=till_item_id,
                detail={
                    "name": row["name"],
                    "code": row["code"],
                    "menu_item_id": menu_item_id,
                    "menu_item_name": row["menu_item_name"],
                    "previous_menu_item_id": before["menu_item_id"],
                    "was_excluded": before["excluded_at"] is not None,
                },
            )
        return row

    async def unmap_till_item(
        self, till_item_id: str, *, tenant_id: str, actor: str
    ) -> asyncpg.Record | None:
        """The reverse gear: the name goes back to the queue with its value,
        and every line that followed the mapping stops following it on the
        next read. None when nothing is mapped (the API answers 409) - the
        check is inside the lock, so a second tab's unmap after the first
        does not write an audit row about nothing."""
        async with self.pool.acquire() as conn, conn.transaction():
            before = await conn.fetchrow(
                "select menu_item_id::text as menu_item_id from till_items "
                "where id = $1 and tenant_id = $2 for update",
                till_item_id,
                tenant_id,
            )
            if before is None:
                raise LookupError(f"till item {till_item_id} is not in tenant {tenant_id}")
            if before["menu_item_id"] is None:
                return None
            await conn.execute(
                "update till_items set menu_item_id = null where id = $1 and tenant_id = $2",
                till_item_id,
                tenant_id,
            )
            row = await conn.fetchrow(
                self._TILL_ITEM_SELECT + " where t.id = $1 and t.tenant_id = $2",
                till_item_id,
                tenant_id,
            )
            await _insert_audit_event(
                conn,
                tenant_id=tenant_id,
                actor=actor,
                action="till_item.unmapped",
                subject_type="till_item",
                subject_id=till_item_id,
                detail={
                    "name": row["name"],
                    "code": row["code"],
                    "previous_menu_item_id": before["menu_item_id"],
                },
            )
        return row

    async def exclude_till_item(
        self, till_item_id: str, *, tenant_id: str, actor: str
    ) -> asyncpg.Record | None:
        """Mark a name as not a menu item: a delivery charge, a discount line.
        It stays in net sales - the till took the money - and leaves the queue.
        None when the name is mapped (the API answers 409: unmap first).
        Excluding an already-excluded name answers the row and writes
        nothing, so a double click is not two audit rows."""
        async with self.pool.acquire() as conn, conn.transaction():
            before = await conn.fetchrow(
                "select menu_item_id::text as menu_item_id, excluded_at from till_items "
                "where id = $1 and tenant_id = $2 for update",
                till_item_id,
                tenant_id,
            )
            if before is None:
                raise LookupError(f"till item {till_item_id} is not in tenant {tenant_id}")
            if before["menu_item_id"] is not None:
                return None
            if before["excluded_at"] is None:
                await conn.execute(
                    "update till_items set excluded_at = now() where id = $1 and tenant_id = $2",
                    till_item_id,
                    tenant_id,
                )
            row = await conn.fetchrow(
                self._TILL_ITEM_SELECT + " where t.id = $1 and t.tenant_id = $2",
                till_item_id,
                tenant_id,
            )
            if before["excluded_at"] is None:
                await _insert_audit_event(
                    conn,
                    tenant_id=tenant_id,
                    actor=actor,
                    action="till_item.excluded",
                    subject_type="till_item",
                    subject_id=till_item_id,
                    detail={"name": row["name"], "code": row["code"]},
                )
        return row

    async def record_confirmed_prices(
        self, invoice_id: str, *, tenant_id: str, conn: asyncpg.Connection | None = None
    ) -> dict:
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

        **A paper with no supplier is matched again here before one is
        created** (2026-09-05 eng review, D21). `unique (tenant_id, name)`
        collapses only byte-identical names, so two papers from a brand-new
        vendor read before either was confirmed ("Al Madina ABC LLC" and "AL
        MADINA ABC L.L.C.") used to become two suppliers with split price
        history. The same `match_supplier` as extraction, word check included,
        runs against the catalog as it stands at confirm, so the vendor's own
        earlier paper is found. The return value says when that happened -
        `{"supplier_attached_at_confirm": {"supplier_id", "name"}}`, else
        `{}` - and `_confirm` folds it into the audit row, because the person
        who said OK never saw a "Booked under" line for this attach.

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
                where i.id = $1 and i.tenant_id = $2
                """,
                invoice_id,
                tenant_id,
            )
            if invoice is None:
                raise ValueError(f"invoice {invoice_id} not found")

            supplier_id = invoice["supplier_id"]
            attached: dict = {}
            if supplier_id is None:
                supplier_name = clean_name(invoice["supplier_name"] or "")
                if not supplier_name:
                    return attached  # no supplier and no name to create one from
                suppliers = await conn.fetch(
                    "select id, name, name_aliases from suppliers where tenant_id = $1 "
                    "order by name",
                    invoice["tenant_id"],
                )
                matched = match_supplier(suppliers, invoice["supplier_name"])
                if matched is not None:
                    supplier_id = matched["id"]
                    attached = {
                        "supplier_attached_at_confirm": {
                            "supplier_id": str(supplier_id),
                            "name": matched["name"],
                        }
                    }
                else:
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
                return attached

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
            # WP-65 (EDGE-01): the catalog rows this supplier already has,
            # plus the ones this very invoice is about to create. Read once,
            # and only consulted for a line whose printed name carries a
            # delivery note - the one case where we know the name is not the
            # product's. EDGE-01 is exactly that shape: line 1 "Avocado"
            # creates the row and line 6 arrives as "Avocado Credit: one box
            # returned, soft fruit", so without this the same invoice mints
            # both of them.
            known = [
                dict(row)
                for row in await conn.fetch(
                    "select id, canonical_name, pack_size from supplier_items "
                    "where supplier_id = $1",
                    supplier_id,
                )
            ]

            for line in lines:
                if line["qty"] is None or line["unit_price"] is None:
                    continue
                item_id = line["supplier_item_id"]
                if item_id is None and strip_delivery_note(line["raw_name"] or "") is not None:
                    snapped = snap_item(known, line["raw_name"])
                    if snapped is not None:
                        item_id = snapped["id"]
                        await conn.execute(
                            "update invoice_lines set supplier_item_id = $2 where id = $1",
                            line["id"],
                            item_id,
                        )
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
                    known.append(
                        {
                            "id": item_id,
                            "canonical_name": canonical_name,
                            "pack_size": line["pack_size"],
                        }
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
            return attached

    # -- Confirm flow (WP-21, C5) --------------------------------------------

    async def pending_invoices_for_phone(self, phone: str) -> list[asyncpg.Record]:
        """C5: the invoices a text from sender phone can address, newest first
        (the flow's default target and the disambiguation list order): every
        awaiting_confirm invoice whose document traces back to the phone, plus
        the cash holds (needs_review on cash alone, WP-24) - reachable for
        corrections since WP-74 amended C5, because a misread cash has to be
        fixable from the phone that sent it, though never confirmable from
        chat (the flow answers an "OK" on one with the cash-hold reply). A
        WP-44 duplicate hold stays out: a copy's exits are the screen's."""
        return await self.pool.fetch(
            """
            select i.id, i.tenant_id::text as tenant_id, i.supplier_name, i.currency, i.total,
                   i.status, i.payment_kind, i.created_at, b.timezone,
                   t.currency as tenant_currency
            from invoices i
            join tenants t on t.id = i.tenant_id
            join documents d on d.id = i.document_id
            join wa_messages m on m.message_id = d.wa_message_id and m.direction = 'in'
            left join branches b on b.id = i.branch_id
            where m.from_phone = $1
              and (
                i.status = 'awaiting_confirm'
                or (
                  i.status = 'needs_review'
                  and i.payment_kind = 'cash'
                  and i.duplicate_of_invoice_id is null
                )
              )
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
            select i.id, i.tenant_id::text as tenant_id, i.supplier_name, i.currency, i.total,
                   i.confirmed_at, t.currency as tenant_currency
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

    async def get_invoice(self, invoice_id: str, *, tenant_id: str) -> asyncpg.Record | None:
        """One of this tenant's invoices, plus its branch name (C6 detail
        shows names), the tenant's own currency (WP-28: the reply, the ack
        and price memory all have to know whether this invoice is billed in
        the tenant's money), and its document's header columns.

        The document rides along on purpose (WP-73): the detail screen used
        to read it by id afterwards, and the storage path it carries is what
        gets signed into a URL. Reading it through the tenant-scoped invoice
        means a paper the caller cannot see is never fetched, so its URL is
        never signed - the sign call happens after this returns a row, or
        not at all."""
        return await self.pool.fetchrow(
            """
            select i.*, b.name as branch_name, t.currency as tenant_currency,
                   d.status as document_status, d.classification as document_classification,
                   d.source as document_source, d.created_at as document_created_at,
                   d.storage_path as document_storage_path
            from invoices i
            join tenants t on t.id = i.tenant_id
            join documents d on d.id = i.document_id
            left join branches b on b.id = i.branch_id
            where i.id = $1 and i.tenant_id = $2
            """,
            invoice_id,
            tenant_id,
        )

    async def get_invoice_lines(self, invoice_id: str, *, tenant_id: str) -> list[asyncpg.Record]:
        return await self.pool.fetch(
            "select * from invoice_lines where invoice_id = $1 and tenant_id = $2 "
            "order by position",
            invoice_id,
            tenant_id,
        )

    async def confirm_invoice(self, invoice_id: str, *, tenant_id: str, actor: str) -> bool:
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
        return await self._confirm(
            invoice_id, tenant_id=tenant_id, from_status="awaiting_confirm", actor=actor, cash=False
        )

    async def confirm_reviewed_invoice(
        self, invoice_id: str, *, tenant_id: str, actor: str
    ) -> bool:
        """C1, the review-screen path (WP-30): invoice needs_review ->
        confirmed, stamping confirmed_at - for a WP-44 duplicate hold the
        reviewer has decided is a real paper. Never for cash: since WP-74 a
        cash hold leaves through `approve_cash_invoice`, with a reason, and
        the write itself refuses cash so no door written later can widen it.
        Returns False without touching anything when the guard refuses - safe
        to re-run."""
        return await self._confirm(
            invoice_id, tenant_id=tenant_id, from_status="needs_review", actor=actor, cash=False
        )

    async def approve_cash_invoice(
        self, invoice_id: str, *, tenant_id: str, actor: str, reason: str, detail: dict
    ) -> bool:
        """The cash gate (M7 WP-74, PRD §21): a cash paper held needs_review
        -> confirmed, by the owner, with a reason on the record. The same
        write as a confirm - same transaction, same price baseline move - and
        the audit row is what tells the two apart: `invoice.cash_approved`,
        carrying the actor, the reason, the status it came from and the
        headline figures in `detail` (the caller's, read from the row it is
        approving), so the trail answers "who approved what, and why" without a
        join. Keyed on cash alone (D12): a cash copy that is also a duplicate
        hold approves here too, and its detail names the paper it duplicates.
        Returns False without touching anything when the guard refuses."""
        return await self._confirm(
            invoice_id,
            tenant_id=tenant_id,
            from_status="needs_review",
            actor=actor,
            cash=True,
            action="invoice.cash_approved",
            detail={"reason": reason, **detail},
        )

    async def _confirm(
        self,
        invoice_id: str,
        *,
        tenant_id: str,
        from_status: str,
        actor: str,
        cash: bool,
        action: str = "invoice.confirmed",
        detail: dict | None = None,
    ) -> bool:
        """The one confirm write, shared by every door: flip the status if it
        is still the expected one, record who did it and why, and move the
        catalog and price baseline - **all in one transaction** (WP-50). One
        gate, one trail entry, one set of prices, whichever door it came in.

        `cash` is the WP-74 guard, and it lives here for dismiss's reason -
        the rule in the one write cannot be widened by a door written later.
        True is the approve door and requires `payment_kind = 'cash'`; False
        is every confirm and refuses it. Null payment kinds count as not cash,
        which is why the comparison is spelled with `is not distinct from`: a
        plain `=` against null would make an unmarked paper unconfirmable.

        `action` and `detail` are the audit row's: `invoice.confirmed` with the
        status it came from, or `invoice.cash_approved` with the reason and
        headline figures on top. Written inside the transaction, so a cash
        paper reading confirmed with no approval record is unreachable.

        `total is not null` sits in the where clause as an invariant, not as
        the user-facing rule (WP-26): every caller checks the total first so
        it can say *why* it is refusing. It is repeated here because a
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
                where id = $1 and status = $2 and total is not null and tenant_id = $3
                  and (payment_kind is not distinct from 'cash') = $4
                returning tenant_id::text
                """,
                invoice_id,
                from_status,
                tenant_id,
                cash,
            )
            if row is None:
                return False
            # Prices first, so the trail entry can say whether the supplier was
            # attached here rather than at extraction (D21); both commit or
            # neither does, whichever order they run in.
            attached = await self.record_confirmed_prices(
                invoice_id, tenant_id=tenant_id, conn=conn
            )
            await _insert_audit_event(
                conn,
                tenant_id=row["tenant_id"],
                actor=actor,
                action=action,
                subject_type="invoice",
                subject_id=invoice_id,
                detail={"from_status": from_status, **(detail or {}), **attached},
            )
        return True

    async def dismiss_invoice(self, invoice_id: str, *, tenant_id: str, actor: str) -> bool:
        """The review screen's way out of a WP-44 duplicate hold: the held copy
        leaves the working list without being recorded and without being
        deleted. The founder, the day before the M6 gate: "the duplicate invoice
        of al madina is in my invoice list, and there is no option to mark
        duplicate and delete it."

        Guarded the way `_confirm` is guarded, and for its reason - the rule
        lives in the one write, so a door written later cannot widen it. Two
        clauses, both load-bearing:

        `status not in ('confirmed', 'dismissed')` - a confirmed invoice is a
        financial record, and dismissing twice writes no second trail entry.

        `duplicate_of_invoice_id is not null` - **a held duplicate, nothing
        else.** An ordinary invoice, a cash hold, and above all the *original*
        of a duplicated paper all carry a null pointer. That last one is why
        this clause is here rather than in the endpoint: when a copy arrives the
        original is usually still awaiting_confirm, so a wider guard would let a
        reviewer dismiss the original and then the copy, and the paper would be
        gone from the product with one WhatsApp reply as its only trace.

        `from_status` is read inside the transaction under FOR UPDATE. Not from
        RETURNING, which yields the row as it now is; and not from the caller's
        earlier read, which is exactly the stale value the 409 path stopped
        trusting.

        Returns False without touching anything when the guard refuses, so it is
        safe to re-run."""
        async with self.pool.acquire() as conn, conn.transaction():
            from_status = await conn.fetchval(
                "select status from invoices where id = $1 and tenant_id = $2 for update",
                invoice_id,
                tenant_id,
            )
            row = await conn.fetchrow(
                """
                update invoices set status = 'dismissed'
                 where id = $1
                   and tenant_id = $2
                   and status not in ('confirmed', 'dismissed')
                   and duplicate_of_invoice_id is not null
                returning tenant_id::text, duplicate_of_invoice_id::text
                """,
                invoice_id,
                tenant_id,
            )
            if row is None:
                return False
            await _insert_audit_event(
                conn,
                tenant_id=row["tenant_id"],
                actor=actor,
                action="invoice.dismissed",
                subject_type="invoice",
                subject_id=invoice_id,
                detail={
                    "from_status": from_status,
                    "duplicate_of_invoice_id": row["duplicate_of_invoice_id"],
                },
            )
        return True

    async def apply_invoice_correction(
        self,
        invoice_id: str,
        *,
        tenant_id: str,
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
        payment_kind: str | None,
        from_status: str,
        status: str,
        tax_treatment: str | None,
        vat_rate: Decimal | None,
        message_id: str | None = None,
    ) -> bool:
        """Persist a correction (WP-21/WP-25/WP-26/WP-28/WP-74), one
        transaction: header fields (invoice number, date, currency and payment
        kind included), the C4 treatment re-derived from the corrected
        arithmetic, refreshed confidence and C8 provenance on the invoice, and
        per line the fields the grammar can change plus the re-derived checks.

        `status` is the status the correction implies (C1 as amended: only a
        payment-kind edit ever changes it, through
        `confirm.status_after_payment_kind`), and `from_status` is the one the
        caller read. The write is guarded on `from_status` for the reason the
        confirm write is guarded: a correction that raced a confirm or a
        dismiss used to land on the recorded paper, and with a status of its
        own to write it could have un-confirmed one. Now it matches no row,
        nothing is written, and the caller is told (False) so it can say so.

        `tax_treatment`/`vat_rate` travel with every correction because the
        confirm path reads them to record price memory net of VAT: a total
        supplied after the fact can turn an unresolvable invoice into an
        inclusive one, and a stale treatment beside a new total would store a
        gross price under a net baseline.

        `actor` and `corrected_fields` write the audit event in the same
        transaction, so a stored correction and the note of who made it cannot
        be observed apart; when the status moved, the row says from what to
        what."""
        async with self.pool.acquire() as conn, conn.transaction():
            updated = await conn.fetchval(
                """
                update invoices
                set invoice_no = $2, invoice_date = $3, subtotal = $4, tax = $5, total = $6,
                    confidence = $7, provenance = $8,
                    currency = coalesce($9, currency), tax_treatment = $10, vat_rate = $11,
                    payment_kind = $13, status = $14
                where id = $1 and tenant_id = $12 and status = $15
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
                tenant_id,
                payment_kind,
                status,
                from_status,
            )
            if updated is None:
                return False  # not this tenant's invoice, or no longer editable: nothing written
            await conn.executemany(
                """
                update invoice_lines
                set raw_name = $3, supplier_item_id = $4, qty = $5, unit_price = $6,
                    line_total = $7, checks = $8, unit = $9, pack_size = $10
                where invoice_id = $1 and position = $2 and tenant_id = $11
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
                        tenant_id,
                    )
                    for line in lines
                ],
            )
            detail: dict = {"fields": corrected_fields, "message_id": message_id}
            if status != from_status:
                detail |= {"from_status": from_status, "to_status": status}
            await _insert_audit_event(
                conn,
                tenant_id=tenant_id,
                actor=actor,
                action="invoice.corrected",
                subject_type="invoice",
                subject_id=invoice_id,
                detail=detail,
            )
        return True

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
        self, subject_type: str, subject_id: str, *, tenant_id: str
    ) -> list[asyncpg.Record]:
        """The history of one invoice or one raw material, newest first."""
        return list(
            await self.pool.fetch(
                """
                select * from audit_events
                where subject_type = $1 and subject_id = $2 and tenant_id = $3
                order by created_at desc, id desc
                """,
                subject_type,
                subject_id,
                tenant_id,
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

    async def enqueue_once(self, kind: str, payload: dict[str, Any]) -> int | None:
        """One extract job per document, ever (WP-72, D22). Inserts against
        0018's `jobs_extract_document_uidx` and tolerates the conflict:
        returns the new job id, or None when a job for this document already
        exists in any status. No status filter, on purpose: the ingest job's
        retry after a failed ack lands 30 s later, after the first extraction
        has finished, and "live jobs only" would let it mint a second read of
        the same paper. Not a fresh flag in Python - the index is the guard."""
        if kind != JobKind.EXTRACT_DOCUMENT:
            raise ValueError(f"enqueue_once is for {JobKind.EXTRACT_DOCUMENT} jobs, not {kind!r}")
        return await self.pool.fetchval(
            """
            insert into jobs (kind, payload) values ($1, $2)
            on conflict (kind, (payload->>'document_id')) where kind = 'extract_document'
            do nothing
            returning id
            """,
            kind,
            payload,
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
