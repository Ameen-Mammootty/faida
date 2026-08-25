"""Cash-or-credit derivation (plan.md §5 layer 5).

This field decides which purchases need owner approval (WP-24), so the rules
are pinned here rather than left to prompt wording.
"""

import pytest

from faida_api.extraction.normalize import normalize_extracted
from faida_api.extraction.payment import derive_payment_kind, kind_from_terms
from faida_api.extraction.schema import ExtractedInvoice


@pytest.mark.parametrize(
    ("terms", "expected"),
    [
        ("Payment terms: 14 days", "credit"),
        ("14 days", "credit"),
        ("Net 30", "credit"),
        ("Net 30 days from invoice date", "credit"),
        ("End of month", "credit"),
        ("EOM", "credit"),
        ("On account", "credit"),
        ("Credit", "credit"),
        ("صافي 30 يوم", "credit"),
        ("Cash on delivery", "cash"),
        ("CASH", "cash"),
        ("C.O.D.", "cash"),
        ("Paid in full", "cash"),
        ("نقدا", "cash"),
        # Nothing we recognize stays null rather than guessing: an unmarked
        # document must not be routed around the cash approval gate.
        ("See agreement", None),
        ("", None),
        (None, None),
    ],
)
def test_printed_terms_decide_the_arrangement(terms, expected):
    assert kind_from_terms(terms) == expected


def test_cash_on_delivery_is_never_read_as_a_due_period():
    """ "Cash on delivery" contains a word the credit rules also look for, so
    the cash markers are checked first. Getting this backwards would send
    every COD purchase past the approval gate."""
    assert kind_from_terms("Cash on delivery within 2 days") == "cash"


def test_printed_terms_outrank_the_model_and_the_model_fills_the_gap():
    # The page is the harder evidence when the two disagree.
    assert derive_payment_kind("Payment terms: 14 days", "cash") == "credit"
    # A till receipt prints no terms; the model's own reading carries it.
    assert derive_payment_kind(None, "cash") == "cash"
    assert derive_payment_kind(None, None) is None


def test_the_seam_derives_payment_kind_the_pipeline_will_persist():
    """The regression this exists for: the model read "Payment terms: 14 days"
    correctly, returned payment_kind null because the page never prints the
    word "credit", and the invoice was recorded with no arrangement at all."""
    extracted = ExtractedInvoice(
        payment_terms_text="Payment terms: 14 days", payment_kind=None, currency="dirhams"
    )
    normalized = normalize_extracted(extracted)
    assert normalized.payment_kind == "credit"
    # The same seam still derives the ISO currency code.
    assert normalized.currency == "AED"
