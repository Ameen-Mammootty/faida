"""Behavioral tests for the pinned contracts: the schema must round-trip the
eval ground-truth format (JSON with string decimals) without losing money
precision, and reject shapes the pipeline would mispersist."""

from decimal import Decimal

import asyncpg
import pytest
from pydantic import ValidationError

from faida_api.confirm import status_after_payment_kind
from faida_api.contracts import INVOICE_TRANSITIONS, InvoiceStatus
from faida_api.extraction.schema import (
    Classification,
    ExtractedLine,
    ExtractionResult,
    RepairResult,
)

from .conftest import DEMO_TENANT_ID, requires_db

INVOICE_PAYLOAD = {
    "classification": "invoice",
    "invoice": {
        "supplier_name": "Gulf Foods Trading LLC",
        "invoice_no": "INV-1041",
        "invoice_date": "2026-08-20",
        "currency": "AED",
        "payment_kind": "credit",
        "lines": [
            {
                "raw_name": "MILK PWDR 2.5KG NIDO",
                "qty": "12",
                "unit": "sack",
                "pack_size": "2.5kg",
                "unit_price": "54.50",
                "line_total": "654.00",
            },
            {
                "raw_name": "KARAK TEA DUST",
                "qty": "3",
                "unit_price": "18.75",
                "line_total": "56.25",
            },
        ],
        "subtotal": "710.25",
        "tax": "35.51",
        "total": "745.76",
    },
}


def test_invoice_json_round_trips_without_losing_money_precision():
    result = ExtractionResult.model_validate(INVOICE_PAYLOAD)
    line = result.invoice.lines[0]
    assert isinstance(line.unit_price, Decimal)
    assert line.unit_price == Decimal("54.50")
    assert result.invoice.total == Decimal("745.76")
    assert result.classification is Classification.INVOICE
    assert ExtractionResult.model_validate(result.model_dump(mode="json")) == result


def test_non_invoice_carries_no_invoice_body():
    result = ExtractionResult.model_validate({"classification": "other"})
    assert result.invoice is None


def test_unknown_fields_are_rejected():
    payload = dict(INVOICE_PAYLOAD, hallucinated_field="x")
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate(payload)


def test_repair_patch_accepts_json_line_indexes():
    # JSON object keys arrive as strings; the patch is keyed by line index.
    patch = RepairResult.model_validate(
        {"lines": {"1": {"raw_name": "KARAK TEA DUST", "qty": "4", "line_total": "75.00"}}}
    )
    assert patch.lines[1] == ExtractedLine(
        raw_name="KARAK TEA DUST", qty=Decimal("4"), line_total=Decimal("75.00")
    )
    assert patch.subtotal is None


# --- C1: the status vocabulary lives in two places ---------------------------


async def _blank_document(db, marker: str) -> str:
    return await db.pool.fetchval(
        """
        insert into documents (tenant_id, storage_path, sha256, mime, source, status)
        values ($1, $2, $3, 'image/jpeg', 'upload', 'extracted')
        returning id
        """,
        DEMO_TENANT_ID,
        f"{DEMO_TENANT_ID}/documents/{marker}/original",
        f"sha256-{marker}",
    )


@requires_db
async def test_the_database_accepts_every_invoice_status_the_enum_declares(db):
    """`InvoiceStatus` and the `invoices_status_check` constraint are two copies
    of one list, kept in step until now by a sentence in this module's own
    docstring and by nothing else.

    Drift does not surface as a red test. It surfaces as a live invoice write
    raising a constraint violation, because Python cheerfully produced a string
    Postgres refuses - on the ingest path, where the sender just gets silence.

    Behavioural on purpose: reading the constraint's SQL text back and comparing
    strings would be a test that asserts on code text, which plan.md §2 rule 6
    bans outright. Inserting one row per member asks the database the question
    directly, and survives any rewording of the constraint."""
    for index, status in enumerate(InvoiceStatus):
        document_id = await _blank_document(db, f"status-{index}")
        await db.pool.execute(
            "insert into invoices (tenant_id, document_id, status) values ($1, $2, $3)",
            DEMO_TENANT_ID,
            document_id,
            status.value,
        )

    stored = await db.pool.fetchval("select count(distinct status) from invoices")
    assert stored == len(InvoiceStatus)


@requires_db
async def test_a_status_outside_the_enum_is_refused_by_postgres(db):
    """The other half: the constraint is real, so this test cannot pass just
    because the column happens to accept anything."""
    document_id = await _blank_document(db, "junk")
    with pytest.raises(asyncpg.exceptions.CheckViolationError):
        await db.pool.execute(
            "insert into invoices (tenant_id, document_id, status) values ($1, $2, $3)",
            DEMO_TENANT_ID,
            document_id,
            "archived",
        )


# --- C1 as amended 2026-09-03: the one correction that moves a status --------


def test_correcting_cash_to_credit_lifts_a_hold_and_credit_to_cash_holds():
    lifted = status_after_payment_kind(
        InvoiceStatus.NEEDS_REVIEW, payment_kind="credit", duplicate_of_invoice_id=None
    )
    assert lifted is InvoiceStatus.AWAITING_CONFIRM
    held = status_after_payment_kind(
        InvoiceStatus.AWAITING_CONFIRM, payment_kind="cash", duplicate_of_invoice_id=None
    )
    assert held is InvoiceStatus.NEEDS_REVIEW


def test_a_cash_duplicate_corrected_to_credit_stays_held():
    # The duplicate hold still applies; its exits are confirm or dismiss.
    assert (
        status_after_payment_kind(
            InvoiceStatus.NEEDS_REVIEW, payment_kind="credit", duplicate_of_invoice_id="some-id"
        )
        is InvoiceStatus.NEEDS_REVIEW
    )


def test_every_other_payment_kind_correction_leaves_the_status_alone():
    for status in InvoiceStatus:
        for kind in ("cash", "credit"):
            for pointer in (None, "some-id"):
                result = status_after_payment_kind(
                    status, payment_kind=kind, duplicate_of_invoice_id=pointer
                )
                if result is status:
                    continue
                # The only moves: a hold lifting or a hold starting, and both
                # are transitions C1 declares.
                assert result in INVOICE_TRANSITIONS[status], (status, kind, pointer, result)
                assert {status, result} == {
                    InvoiceStatus.AWAITING_CONFIRM,
                    InvoiceStatus.NEEDS_REVIEW,
                }


def test_c1_declares_the_lift_and_no_other_way_out_of_a_terminal_state():
    assert InvoiceStatus.AWAITING_CONFIRM in INVOICE_TRANSITIONS[InvoiceStatus.NEEDS_REVIEW]
    assert INVOICE_TRANSITIONS[InvoiceStatus.CONFIRMED] == set()
    assert INVOICE_TRANSITIONS[InvoiceStatus.DISMISSED] == set()
