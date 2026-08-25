"""The one seam where a raw extraction becomes the invoice we work with."""

from decimal import Decimal

from faida_api.extraction.normalize import blank_to_none, normalize_extracted
from faida_api.extraction.schema import ExtractedInvoice, ExtractedLine


def test_the_seam_applies_every_printed_fact_derivation():
    invoice = ExtractedInvoice(
        currency="dirhams",
        payment_terms_text="Payment terms: 14 days",
        payment_kind=None,
        lines=[ExtractedLine(raw_name="Chilled delivery", unit="service", pack_size="-")],
        total=Decimal("100.00"),
    )
    normalized = normalize_extracted(invoice)
    assert normalized.currency == "AED"
    assert normalized.payment_kind == "credit"
    # A printed dash means "nothing here"; recorded literally it becomes a pack
    # size of "-" that the catalog then has to compare against.
    assert normalized.lines[0].pack_size is None
    assert normalized.lines[0].unit == "service"


def test_placeholders_are_absences_and_real_values_survive():
    assert blank_to_none("-") is None
    assert blank_to_none("N/A") is None
    assert blank_to_none("  ") is None
    assert blank_to_none(None) is None
    assert blank_to_none(" 2 kg ") == "2 kg"
