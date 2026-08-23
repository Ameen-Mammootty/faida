"""Unit tests for the WP-20 reply composer (plan.md §6 M2, §7.3).

Every message shape the product sends, rendered and asserted: exact strings
for the fixed set, structure plus exact money formatting for the composed
ones. Pure functions, no DB, no network.
"""

from decimal import Decimal

from faida_api.extraction.schema import ExtractedInvoice, ExtractedLine
from faida_api.extraction.validate import (
    CheckStatus,
    DocumentCheck,
    FieldStatus,
    LineCheck,
    ValidationResult,
    validate_invoice,
)
from faida_api.replies import (
    CASH_HOLD_NOTE,
    CLOSING_ALL_GREEN,
    CLOSING_WITH_AMBERS,
    OVERFLOW_LINE,
    REPLY_EXTRACTION_FAILED,
    REPLY_MEDIA_RECEIVED,
    REPLY_NOT_INVOICE,
    REPLY_TEXT_ONBOARDING,
    REPLY_UNSUPPORTED_TYPE,
    REPLY_Z_REPORT,
    PriceAlert,
    compose_cash_hold_reply,
    compose_invoice_reply,
    render_price_alert,
    summary_line,
)


def _line(
    qty: str | None, price: str | None, total: str | None, name: str = "item"
) -> ExtractedLine:
    return ExtractedLine(
        raw_name=name,
        qty=Decimal(qty) if qty is not None else None,
        unit_price=Decimal(price) if price is not None else None,
        line_total=Decimal(total) if total is not None else None,
    )


def _invoice(
    lines: list[ExtractedLine],
    supplier: str | None = "Gulf Foods Trading",
    currency: str | None = "AED",
    subtotal: str | None = None,
    tax: str | None = None,
    total: str | None = None,
) -> ExtractedInvoice:
    return ExtractedInvoice(
        supplier_name=supplier,
        currency=currency,
        lines=lines,
        subtotal=Decimal(subtotal) if subtotal is not None else None,
        tax=Decimal(tax) if tax is not None else None,
        total=Decimal(total) if total is not None else None,
    )


def _green_invoice() -> ExtractedInvoice:
    lines = [_line("2", "30.00", "60.00"), _line("4", "10.00", "40.00")]
    return _invoice(lines, subtotal="100.00", tax="5.00", total="105.00")


def _reply(invoice: ExtractedInvoice, alerts: list[PriceAlert] | None = None) -> str:
    return compose_invoice_reply(invoice, validate_invoice(invoice), alerts or [])


# --- the fixed message set (exact strings) ---


def test_fixed_messages_exact():
    assert REPLY_MEDIA_RECEIVED == (
        "Got it - invoice received and saved. I'll reply with the details here soon."
    )
    assert REPLY_TEXT_ONBOARDING == (
        "Hi! Forward a supplier invoice photo here and I'll read it for you."
    )
    assert REPLY_UNSUPPORTED_TYPE == (
        "I can only read photos or PDF invoices for now - please forward the invoice as a photo."
    )
    assert REPLY_NOT_INVOICE == (
        "That doesn't look like a supplier invoice, so I'll leave it - forward an "
        "invoice photo and I'll read it."
    )
    assert REPLY_Z_REPORT == "I read supplier invoices for now - sales reports are coming soon."
    # Plan.md §5 layer 6 wording: one message, never a dead end.
    assert REPLY_EXTRACTION_FAILED == (
        "Couldn't read this one - try a straighter photo, or type the total."
    )


def test_no_em_or_en_dashes_in_any_message():
    fixed = [
        REPLY_MEDIA_RECEIVED,
        REPLY_TEXT_ONBOARDING,
        REPLY_UNSUPPORTED_TYPE,
        REPLY_NOT_INVOICE,
        REPLY_Z_REPORT,
        REPLY_EXTRACTION_FAILED,
        CLOSING_ALL_GREEN,
        CLOSING_WITH_AMBERS,
        CASH_HOLD_NOTE,
        OVERFLOW_LINE,
    ]
    busy = _invoice(
        [_line(None, "5.00", "10.00"), _line("10", "45.00", "500.00")],
        supplier=None,
        tax="0",
        total="600.00",
    )
    alert = PriceAlert(prev_price=Decimal("1"), new_price=Decimal("2"), item_name="Tea")
    composed = compose_invoice_reply(busy, validate_invoice(busy), [alert])
    for text in [*fixed, composed]:
        assert "—" not in text and "–" not in text


# --- price alerts ---


def test_rising_price_alert_renders_the_spec_sentence():
    alert = PriceAlert(
        item_name="Milk Powder 2.5kg",
        prev_price=Decimal("50.50"),
        new_price=Decimal("54.50"),
        currency="AED",
    )
    assert alert.direction == "up"
    assert alert.delta == Decimal("4.00")
    assert render_price_alert(alert) == (
        "Milk Powder 2.5kg up AED 4.00 (50.50 to 54.50) since your last purchase."
    )


def test_falling_price_alert_renders_too():
    alert = PriceAlert(
        item_name="Sugar 10kg",
        prev_price=Decimal("54.50"),
        new_price=Decimal("52.50"),
    )
    assert alert.direction == "down"
    assert render_price_alert(alert) == (
        "Sugar 10kg down AED 2.00 (54.50 to 52.50) since your last purchase."
    )


def test_multi_alert_reply_keeps_alert_order_after_the_summary():
    alerts = [
        PriceAlert(item_name="Milk", prev_price=Decimal("50.50"), new_price=Decimal("54.50")),
        PriceAlert(item_name="Tea", prev_price=Decimal("12.00"), new_price=Decimal("11.00")),
    ]
    lines = _reply(_green_invoice(), alerts).splitlines()
    assert lines[1] == "Milk up AED 4.00 (50.50 to 54.50) since your last purchase."
    assert lines[2] == "Tea down AED 1.00 (12.00 to 11.00) since your last purchase."
    assert lines[3] == CLOSING_ALL_GREEN


# --- composed invoice reply ---


def test_all_green_reply_exact_and_ends_with_ok_prompt():
    reply = _reply(_green_invoice())
    assert reply == "Read it: Gulf Foods Trading, 2 lines, total AED 105.00.\nReply OK to confirm."
    assert reply.endswith("Reply OK to confirm.")


def test_single_line_invoice_uses_singular_line_word():
    invoice = _invoice([_line("1", "54.5", "54.5")], total="54.5")
    assert summary_line(invoice) == "Read it: Gulf Foods Trading, 1 line, total AED 54.50."


def test_total_with_one_decimal_renders_two():
    # Decimal("54.5") must render "54.50", never "54.5".
    invoice = _invoice([_line("1", "54.5", "54.5")], total="54.5")
    assert "total AED 54.50." in _reply(invoice)


def test_default_currency_is_aed_and_invoice_currency_wins():
    no_currency = _invoice([_line("1", "10.00", "10.00")], currency=None, total="10.00")
    assert "total AED 10.00." in summary_line(no_currency)
    sar = _invoice([_line("1", "10.00", "10.00")], currency="SAR", total="10.00")
    assert "total SAR 10.00." in summary_line(sar)


def test_unknown_supplier_and_unreadable_total_fallbacks():
    invoice = _invoice([_line("1", "10.00", "10.00")], supplier=None)
    reply = _reply(invoice)
    assert reply.splitlines() == [
        "Read it: supplier unknown, 1 line, total unreadable.",
        "I couldn't read the invoice total - what does it say?",
        CLOSING_WITH_AMBERS,
    ]


# --- amber questions: content, ordering, cap, overflow ---


def test_amber_ordering_doc_first_then_lines_by_materiality_with_cap_and_overflow():
    lines = [
        _line(None, "5.00", "10.00"),  # amber, least material
        _line("10", "45.00", "500.00"),  # amber (math fails), most material line
        _line("2", "30.00", "60.00"),  # green
        _line(None, None, "200.00"),  # amber (qty asked first)
    ]
    # Line sum 770.00 vs stated 800.00: the totals question comes first.
    invoice = _invoice(lines, tax=None, total="800.00")
    reply = _reply(invoice)
    assert reply.splitlines() == [
        "Read it: Gulf Foods Trading, 4 lines, total AED 800.00.",
        "The totals don't add up (lines plus tax come to 770.00 "
        "but the invoice says 800.00) - which is right?",
        "Line 2: the math doesn't add up (10 x 45.00 = 450.00 "
        "but the line says 500.00) - which is right?",
        "Line 4: I couldn't read the quantity - how many were delivered?",
        "...and 1 more to check on the review screen.",
        CLOSING_WITH_AMBERS,
    ]


def test_unreadable_line_total_is_most_material():
    lines = [
        _line(None, "5.00", "900.00"),  # amber, big but readable total
        _line("2", "10.00", None),  # amber, unreadable total: asked first
    ]
    invoice = _invoice(lines, total="920.00")
    reply = _reply(invoice)
    assert reply.splitlines() == [
        "Read it: Gulf Foods Trading, 2 lines, total AED 920.00.",
        "Line 2: I couldn't read the line total - what does it say?",
        "Line 1: I couldn't read the quantity - how many were delivered?",
        CLOSING_WITH_AMBERS,
    ]


def test_exactly_three_ambers_ask_all_three_with_no_overflow_line():
    lines = [
        _line(None, "5.00", "10.00"),
        _line(None, "5.00", "20.00"),
        _line(None, "5.00", "30.00"),
    ]
    # Delivery-note style: the document reconciles, every line stays amber.
    invoice = _invoice(lines, tax="0", total="60.00")
    reply = _reply(invoice)
    body = reply.splitlines()
    assert [ln.split(":")[0] for ln in body[1:4]] == ["Line 3", "Line 2", "Line 1"]
    assert "more to check on the review screen" not in reply
    assert body[-1] == CLOSING_WITH_AMBERS


def test_missing_unit_price_question():
    invoice = _invoice([_line("4", None, "200.00")], tax="0", total="200.00")
    assert (
        "Line 1: I couldn't read the unit price - what price was charged?"
        in _reply(invoice).splitlines()
    )


def test_subtotal_mismatch_question_exact():
    lines = [_line("2", "30.00", "60.00"), _line("4", "10.00", "40.00")]
    invoice = _invoice(lines, subtotal="90.00", tax="5.00", total="105.00")
    assert (
        "The subtotal doesn't match the lines (they add up to 100.00 "
        "but the subtotal says 90.00) - which is right?"
    ) in _reply(invoice).splitlines()


def test_taint_amber_document_does_not_burn_a_question_slot():
    # The totals block is amber only because a line failed; the line question
    # already covers it, so no document question is asked.
    invoice = _invoice([_line("2", "3.10", "6.26")], total="6.26")
    reply = _reply(invoice)
    assert reply.splitlines() == [
        "Read it: Gulf Foods Trading, 1 line, total AED 6.26.",
        "Line 1: the math doesn't add up (2 x 3.10 = 6.20 "
        "but the line says 6.26) - which is right?",
        CLOSING_WITH_AMBERS,
    ]


def test_fractional_qty_renders_plainly_in_the_math_question():
    invoice = _invoice([_line("2.5", "4.00", "11.00")], tax="0", total="11.00")
    assert (
        "Line 1: the math doesn't add up (2.5 x 4.00 = 10.00 "
        "but the line says 11.00) - which is right?"
    ) in _reply(invoice).splitlines()


def test_snapping_failure_fallback_question():
    # WP-22 will set snapped=False on lines that pass arithmetic but match no
    # known item at a plausible price; the composer must already handle it.
    line = _line("2", "30.00", "60.00", name="Karak Chai Mix")
    invoice = _invoice([line], tax="0", total="60.00")
    validation = ValidationResult(
        lines=[
            LineCheck(
                line_index=0, arith=CheckStatus.PASSED, snapped=False, status=FieldStatus.AMBER
            )
        ],
        document=DocumentCheck(
            arith=CheckStatus.PASSED,
            subtotal_check=CheckStatus.INDETERMINATE,
            line_sum=Decimal("60.00"),
            status=FieldStatus.GREEN,
        ),
    )
    reply = compose_invoice_reply(invoice, validation, [])
    assert (
        'Line 1: I couldn\'t match "Karak Chai Mix" to your usual items - is it right?'
        in reply.splitlines()
    )
    assert reply.endswith(CLOSING_WITH_AMBERS)


# --- cash hold ---


def test_cash_hold_reply_green_exact():
    invoice = _green_invoice()
    reply = compose_cash_hold_reply(invoice, validate_invoice(invoice), [])
    assert reply == (
        "Read it: Gulf Foods Trading, 2 lines, total AED 105.00.\n"
        "This one is marked cash, so it needs the owner's approval before it's recorded."
    )
    assert "Reply OK" not in reply


def test_cash_hold_reply_keeps_alerts_and_questions_but_closes_with_the_hold():
    invoice = _invoice([_line(None, "5.00", "10.00")], tax="0", total="10.00")
    alert = PriceAlert(item_name="Milk", prev_price=Decimal("50.50"), new_price=Decimal("54.50"))
    reply = compose_cash_hold_reply(invoice, validate_invoice(invoice), [alert])
    lines = reply.splitlines()
    assert lines[1] == "Milk up AED 4.00 (50.50 to 54.50) since your last purchase."
    assert lines[2] == "Line 1: I couldn't read the quantity - how many were delivered?"
    assert lines[-1] == CASH_HOLD_NOTE
    assert "Reply" not in reply


# --- determinism ---


def test_same_inputs_same_bytes():
    invoice = _invoice(
        [_line(None, "5.00", "10.00"), _line("10", "45.00", "500.00")],
        tax="0",
        total="600.00",
    )
    alerts = [PriceAlert(item_name="Milk", prev_price=Decimal("50.50"), new_price=Decimal("54.50"))]
    first = compose_invoice_reply(invoice, validate_invoice(invoice), alerts)
    second = compose_invoice_reply(invoice, validate_invoice(invoice), alerts)
    assert first == second
