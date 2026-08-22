"""Behavioral tests for the pinned contracts: the schema must round-trip the
eval ground-truth format (JSON with string decimals) without losing money
precision, and reject shapes the pipeline would mispersist."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from faida_api.extraction.schema import (
    Classification,
    ExtractedLine,
    ExtractionResult,
    RepairResult,
)

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
