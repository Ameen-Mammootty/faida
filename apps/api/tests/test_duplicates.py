"""WP-44's pure duplicate rule, no database: same supplier + number + total
holds; number alone, or date + total, only annotates; another supplier's
coincidentally matching number is nobody's business."""

import datetime
from decimal import Decimal

from faida_api.extraction.pipeline import find_duplicate
from faida_api.extraction.schema import ExtractedInvoice


def _earlier(**overrides) -> dict:
    row = {
        "id": "earlier",
        "supplier_id": None,
        "supplier_name": "Gulf Foods Trading LLC",
        "invoice_no": "INV-1041",
        "invoice_date": datetime.date(2026, 8, 20),
        "currency": "AED",
        "total": Decimal("745.76"),
        "status": "awaiting_confirm",
        "created_at": datetime.datetime(2026, 8, 20, 9, 0, tzinfo=datetime.UTC),
    }
    row.update(overrides)
    return row


def test_same_supplier_number_and_total_is_a_duplicate():
    same_paper = ExtractedInvoice(
        supplier_name="GULF FOODS TRADING LLC",  # case never separates a supplier
        invoice_no="inv 1041",  # normalization: "INV-1041" == "inv 1041"
        total=Decimal("745.76"),
    )
    duplicate, similar = find_duplicate([_earlier()], None, same_paper)
    assert duplicate is not None and duplicate["id"] == "earlier"
    assert similar is None


def test_number_alone_or_date_plus_total_is_only_similar():
    same_number_new_total = ExtractedInvoice(
        supplier_name="Gulf Foods Trading LLC",
        invoice_no="INV-1041",
        total=Decimal("999.99"),
    )
    duplicate, similar = find_duplicate([_earlier()], None, same_number_new_total)
    assert duplicate is None and similar is not None

    same_day_same_total_new_number = ExtractedInvoice(
        supplier_name="Gulf Foods Trading LLC",
        invoice_no="INV-2077",
        invoice_date=datetime.date(2026, 8, 20),
        total=Decimal("745.76"),
    )
    duplicate, similar = find_duplicate([_earlier()], None, same_day_same_total_new_number)
    assert duplicate is None and similar is not None


def test_another_suppliers_matching_number_is_ignored():
    other_supplier = ExtractedInvoice(
        supplier_name="Al Madina Trading",
        invoice_no="INV-1041",
        total=Decimal("745.76"),
    )
    assert find_duplicate([_earlier()], None, other_supplier) == (None, None)


def test_an_absent_number_never_equals_another_absent_number():
    numberless = ExtractedInvoice(supplier_name="Gulf Foods Trading LLC", total=Decimal("1.00"))
    assert find_duplicate([_earlier(invoice_no=None)], None, numberless) == (None, None)


def test_matched_supplier_ids_decide_when_both_rows_have_one():
    earlier = _earlier(supplier_id="abc-123", supplier_name="Gulf Foods Trading L.L.C.")
    invoice = ExtractedInvoice(
        supplier_name="Gulf Foods",  # name differs; the matched id decides
        invoice_no="INV-1041",
        total=Decimal("745.76"),
    )
    duplicate, _ = find_duplicate([earlier], "abc-123", invoice)
    assert duplicate is not None
    assert find_duplicate([earlier], "different-id", invoice) == (None, None)


def test_newest_match_wins():
    older = _earlier(id="older")
    newer = _earlier(id="newer")
    same_paper = ExtractedInvoice(
        supplier_name="Gulf Foods Trading LLC",
        invoice_no="INV-1041",
        total=Decimal("745.76"),
    )
    # The query hands rows newest first; the first hit is kept.
    duplicate, _ = find_duplicate([newer, older], None, same_paper)
    assert duplicate is not None and duplicate["id"] == "newer"


def test_cross_currency_totals_never_hold_but_the_number_still_notes():
    # USD 745.76 and AED 745.76 are the same digits, not the same money -
    # found at integration when WP-28's currency test met the hold.
    usd_earlier = _earlier(currency="USD")
    aed_same_number = ExtractedInvoice(
        supplier_name="Gulf Foods Trading LLC",
        invoice_no="INV-1041",
        currency="AED",
        total=Decimal("745.76"),
    )
    duplicate, similar = find_duplicate([usd_earlier], None, aed_same_number)
    assert duplicate is None and similar is not None
