"""The filing step (extraction/filing.py, CONTEXT.md): one pure module for
what used to be four copies of the same sequence. No DB, no model. What is
pinned here is the wiring the copies used to carry as prose - the fold rule,
no-supplier versus empty-catalog, the alerts, the confidence dump and the row
shape - so a door cannot forget a step again."""

from decimal import Decimal

import pytest

from faida_api.extraction.filing import Filing, file_invoice, filed_names
from faida_api.extraction.schema import ExtractedInvoice, ExtractedLine, LineKind
from faida_api.extraction.validate import CheckStatus, FieldStatus, validate_invoice

MILK = {
    "id": "11111111-1111-1111-1111-111111111111",
    "canonical_name": "Milk Powder 2.5kg",
    "pack_size": "2.5KG",
    "last_price": Decimal("50.50"),
}
KARAK = {
    "id": "22222222-2222-2222-2222-222222222222",
    "canonical_name": "Karak Tea Dust",
    "pack_size": None,
    "last_price": None,
}
CATALOG = [MILK, KARAK]


def _invoice(*, total: str = "745.76") -> ExtractedInvoice:
    return ExtractedInvoice(
        supplier_name="Gulf Foods Trading LLC",
        currency="AED",
        lines=[
            ExtractedLine(
                raw_name="MILK PWDR 2.5KG NIDO",
                qty=Decimal("12"),
                unit="bag",
                pack_size="2.5KG",
                unit_price=Decimal("54.50"),
                line_total=Decimal("654.00"),
            ),
            ExtractedLine(
                raw_name="KARAK TEA DUST",
                qty=Decimal("3"),
                unit_price=Decimal("18.75"),
                line_total=Decimal("56.25"),
            ),
            ExtractedLine(
                raw_name="DELIVERY",
                line_kind=LineKind.CHARGE,
                qty=Decimal("1"),
                unit_price=Decimal("35.51"),
                line_total=Decimal("35.51"),
            ),
        ],
        total=Decimal(total),
    )


def test_no_supplier_leaves_every_line_neutral_and_the_validation_untouched():
    filed = file_invoice(_invoice(), catalog=None, tenant_currency="AED")
    assert isinstance(filed, Filing)
    assert filed.snapped_items == [None, None, None]
    assert [check.snapped for check in filed.line_checks] == [None, None, None]
    assert filed.validation == validate_invoice(_invoice())
    assert filed.alerts == []
    assert [row["supplier_item_id"] for row in filed.rows] == [None, None, None]


def test_an_empty_catalog_is_a_supplier_that_knows_nothing_yet():
    filed = file_invoice(_invoice(), catalog=[], tenant_currency="AED")
    assert filed.snapped_items == [None, None, None]
    assert [check.snapped for check in filed.line_checks] == [False, False, False]
    # Snapping never recomputes a status: green arithmetic stays green.
    assert [check.status for check in filed.line_checks] == [FieldStatus.GREEN] * 3
    assert filed.confidence["lines"] == ["green", "green", "green"]


def test_snapped_is_folded_into_the_validation_the_composer_sees():
    filed = file_invoice(_invoice(), catalog=CATALOG, tenant_currency="AED")
    assert [None if i is None else i["id"] for i in filed.snapped_items] == [
        MILK["id"],
        KARAK["id"],
        None,
    ]
    assert [check.snapped for check in filed.line_checks] == [True, True, False]
    # The returned validation is the folded one, not the bare arithmetic.
    assert filed.validation.lines == filed.line_checks
    assert [check.arith for check in filed.line_checks] == [CheckStatus.PASSED] * 3
    assert filed_names(filed.snapped_items) == ["Milk Powder 2.5kg", "Karak Tea Dust", None]


def test_alerts_come_from_the_snapped_items_and_the_tenant_currency():
    filed = file_invoice(_invoice(), catalog=CATALOG, tenant_currency="AED")
    assert [(a.item_name, a.prev_price, a.new_price) for a in filed.alerts] == [
        ("Milk Powder 2.5kg", Decimal("50.50"), Decimal("54.50")),
    ]
    # WP-28: a paper billed in another money raises nothing.
    abroad = file_invoice(_invoice(), catalog=CATALOG, tenant_currency="USD")
    assert abroad.alerts == []
    assert abroad.snapped_items == filed.snapped_items


def test_confidence_is_derived_from_the_folded_checks():
    filed = file_invoice(_invoice(total="700.00"), catalog=CATALOG, tenant_currency="AED")
    assert filed.confidence["document"] == filed.validation.document.model_dump(mode="json")
    assert filed.confidence["document"]["arith"] == "failed"
    assert filed.confidence["lines"] == [check.status.value for check in filed.line_checks]


def test_rows_carry_line_kind_the_snap_and_the_persisted_check():
    filed = file_invoice(_invoice(), catalog=CATALOG, tenant_currency="AED")
    assert [row["position"] for row in filed.rows] == [0, 1, 2]
    assert [row["line_kind"] for row in filed.rows] == ["stock_item", "stock_item", "charge"]
    assert [row["supplier_item_id"] for row in filed.rows] == [MILK["id"], KARAK["id"], None]
    first = filed.rows[0]
    assert first["raw_name"] == "MILK PWDR 2.5KG NIDO"
    assert (first["qty"], first["unit"], first["pack_size"]) == (Decimal("12"), "bag", "2.5KG")
    assert (first["unit_price"], first["line_total"]) == (Decimal("54.50"), Decimal("654.00"))
    assert first["checks"] == filed.line_checks[0].model_dump(mode="json")
    assert first["checks"]["snapped"] is True


def test_a_correction_keeps_the_stored_positions():
    filed = file_invoice(_invoice(), catalog=None, tenant_currency="AED", positions=[4, 7, 9])
    assert [row["position"] for row in filed.rows] == [4, 7, 9]


def test_positions_of_the_wrong_length_raise_rather_than_renumber():
    with pytest.raises(ValueError):
        file_invoice(_invoice(), catalog=None, tenant_currency="AED", positions=[0, 1])


def test_the_same_input_files_the_same_way_twice():
    once = file_invoice(_invoice(), catalog=CATALOG, tenant_currency="AED")
    twice = file_invoice(_invoice(), catalog=CATALOG, tenant_currency="AED")
    assert once == twice
