"""The one seam where a raw extraction becomes the invoice we work with."""

import datetime
from decimal import Decimal

from faida_api.extraction.normalize import blank_to_none, normalize_extracted
from faida_api.extraction.schema import ExtractedInvoice, ExtractedLine


def test_the_seam_applies_every_printed_fact_derivation():
    invoice = ExtractedInvoice(
        currency="dirhams",
        payment_terms_text="Payment terms: 14 days",
        payment_kind=None,
        invoice_date_text="5/7/26",
        invoice_date=None,
        lines=[ExtractedLine(raw_name="Chilled delivery", unit="service", pack_size="-")],
        total=Decimal("100.00"),
    )
    normalized = normalize_extracted(invoice)
    assert normalized.currency == "AED"
    assert normalized.payment_kind == "credit"
    # WP-27: the printed date resolves day-first even when the model left the
    # calendar field null - exactly the Al Aweer AAF 2214 failure.
    assert normalized.invoice_date == datetime.date(2026, 7, 5)
    # A printed dash means "nothing here"; recorded literally it becomes a pack
    # size of "-" that the catalog then has to compare against.
    assert normalized.lines[0].pack_size is None
    assert normalized.lines[0].unit == "service"


def test_an_ambiguous_printed_date_nulls_the_models_guess_at_the_seam():
    invoice = ExtractedInvoice(
        invoice_date_text="5/7",
        invoice_date=datetime.date(2026, 7, 5),
        total=Decimal("10.00"),
    )
    assert normalize_extracted(invoice).invoice_date is None


def test_no_printed_date_text_keeps_the_given_date():
    # The manual-entry path builds invoices with a form date and no text; the
    # seam must never null it.
    invoice = ExtractedInvoice(invoice_date=datetime.date(2026, 8, 20), total=Decimal("10.00"))
    assert normalize_extracted(invoice).invoice_date == datetime.date(2026, 8, 20)


def test_placeholders_are_absences_and_real_values_survive():
    assert blank_to_none("-") is None
    assert blank_to_none("N/A") is None
    assert blank_to_none("  ") is None
    assert blank_to_none(None) is None
    assert blank_to_none(" 2 kg ") == "2 kg"
