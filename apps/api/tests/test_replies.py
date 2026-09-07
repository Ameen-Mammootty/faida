"""Unit tests for the WP-20 reply composer (plan.md §6 M2, §7.3), in the
card look of WP-125.

Every message shape the product sends, rendered and asserted: exact strings
for the fixed set, structure plus exact money formatting for the composed
ones. Pure functions, no DB, no network.
"""

import datetime
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
    CHECK_HEADING,
    CLOSING_ALL_GREEN,
    CLOSING_TOTAL_NEEDED,
    CLOSING_WITH_AMBERS,
    DISAMBIGUATION_FOOTER,
    ICON_CHECK,
    ICON_DONE,
    ICON_DOWN,
    ICON_HELD,
    ICON_UP,
    OVERFLOW_LINE,
    PRICE_MOVES_HEADING,
    QUESTION_MISSING_DATE,
    QUESTION_MISSING_INVOICE_NO,
    READ_IT,
    REPLY_CASH_HOLD_OK,
    REPLY_CLARIFY,
    REPLY_CORRECTION_REFUSED,
    REPLY_EXTRACTION_FAILED,
    REPLY_MEDIA_RECEIVED,
    REPLY_NOT_INVOICE,
    REPLY_TEXT_ONBOARDING,
    REPLY_UNKNOWN_SENDER,
    REPLY_UNSUPPORTED_TYPE,
    REPLY_Z_REPORT,
    PendingInvoice,
    PriceAlert,
    SimilarPaper,
    compose_ambiguous_date_reply,
    compose_cash_approved_notice,
    compose_cash_hold_reply,
    compose_confirmation_ack,
    compose_disambiguation_reply,
    compose_duplicate_hold_reply,
    compose_invoice_reply,
    compose_line_out_of_range,
    compose_total_needed_reply,
    compose_vat_rate_reply,
    plain,
    render_booked_under,
    render_duplicate_note,
    render_price_alert,
    summary_block,
)

ICONS = (ICON_DONE, ICON_UP, ICON_DOWN, ICON_CHECK, ICON_HELD)


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
    invoice_no: str | None = "4471",
    invoice_date: datetime.date | None = datetime.date(2026, 7, 5),
) -> ExtractedInvoice:
    # invoice_no and invoice_date default to present: a missing one is a
    # WP-25 amber with its own question, tested explicitly below.
    return ExtractedInvoice(
        supplier_name=supplier,
        invoice_no=invoice_no,
        invoice_date=invoice_date,
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


def _header(total: str, count: int = 2, supplier: str = "Gulf Foods Trading") -> str:
    """The four header lines for a dated, numbered Gulf Foods invoice."""
    lines = "line" if count == 1 else "lines"
    return f"✅ Read it\n*{supplier}*\nInvoice 4471 · 5 Jul 2026 · {count} {lines}\nTotal {total}"


def _busy_reply() -> str:
    """Every section at once: alerts, three questions with overflow, a foreign
    currency, the filing note and the similar-paper note."""
    lines = [
        _line(None, "5.00", "10.00"),
        _line("10", "45.00", "500.00"),
        _line(None, None, "200.00"),
    ]
    invoice = _invoice(lines, currency="USD", tax=None, total="800.00")
    alerts = [
        PriceAlert(item_name="Milk", prev_price=Decimal("50.50"), new_price=Decimal("54.50")),
        PriceAlert(item_name="Tea", prev_price=Decimal("12.00"), new_price=Decimal("11.00")),
    ]
    return compose_invoice_reply(
        invoice,
        validate_invoice(invoice),
        alerts,
        tenant_currency="AED",
        booked_under="Gulf Foods Trading L.L.C.",
        similar_to=SimilarPaper(
            supplier_name="Gulf Foods Trading",
            invoice_no="4470",
            received_on=datetime.date(2026, 7, 4),
        ),
    )


def _assert_markup_balanced(text: str) -> None:
    for line in text.splitlines():
        assert line.count("*") % 2 == 0, line
        assert line.count("`") % 2 == 0, line
        assert "**" not in line and "``" not in line, line


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
    # WP-72: a phone no branch is registered to. Plain words, one ask, no
    # hint about who else is on the system.
    assert REPLY_UNKNOWN_SENDER == (
        "This number isn't set up yet, so I can't read invoices from it. "
        "Ask the owner to add this number, then forward the invoice again."
    )
    # Plan.md §5 layer 6: one message, never a dead end - and the way out is
    # the screen, because a typed total has no failed invoice to land on.
    assert REPLY_EXTRACTION_FAILED == (
        f"{ICON_CHECK} Couldn't read this one - try a straighter photo, "
        "or enter it on the review screen."
    )


def test_closings_and_headings_exact():
    assert READ_IT == "✅ Read it"
    assert PRICE_MOVES_HEADING == "*Price moves since your last purchase*"
    assert CHECK_HEADING == f"{ICON_CHECK} *Please check*"
    assert CLOSING_ALL_GREEN == "Reply *OK* to confirm."
    assert (
        CLOSING_WITH_AMBERS
        == "Reply with fixes, like `line 4 qty 16`, or *OK* to confirm the rest."
    )
    assert CLOSING_TOTAL_NEEDED == "Send me the total and I'll finish this one off."
    assert CASH_HOLD_NOTE == (
        f"{ICON_HELD} Marked cash, so it needs the owner's approval before it's recorded. "
        "I'll tell you here once the owner records it."
    )
    assert REPLY_CASH_HOLD_OK == (
        f"{CASH_HOLD_NOTE}\nIf it was actually paid on credit, reply `payment credit`."
    )


def test_no_em_or_en_dashes_in_any_message():
    fixed = [
        REPLY_MEDIA_RECEIVED,
        REPLY_TEXT_ONBOARDING,
        REPLY_UNSUPPORTED_TYPE,
        REPLY_NOT_INVOICE,
        REPLY_Z_REPORT,
        REPLY_EXTRACTION_FAILED,
        REPLY_UNKNOWN_SENDER,
        READ_IT,
        PRICE_MOVES_HEADING,
        CHECK_HEADING,
        CLOSING_ALL_GREEN,
        CLOSING_WITH_AMBERS,
        CLOSING_TOTAL_NEEDED,
        CASH_HOLD_NOTE,
        REPLY_CASH_HOLD_OK,
        REPLY_CORRECTION_REFUSED,
        REPLY_CLARIFY,
        DISAMBIGUATION_FOOTER,
        QUESTION_MISSING_DATE,
        QUESTION_MISSING_INVOICE_NO,
        OVERFLOW_LINE,
    ]
    for text in [*fixed, _busy_reply()]:
        assert "—" not in text and "–" not in text


# --- the markup rules (WP-125) ---


def test_markup_is_balanced_in_a_busy_reply():
    reply = _busy_reply()
    _assert_markup_balanced(reply)
    assert len(reply) < 4096


def test_user_text_cannot_break_the_markup():
    # A supplier called "A*B*C" must not open a bold run; a raw name with a
    # backtick or a tilde must not open code or strike-through.
    line = _line("2", "30.00", "60.00", name="x`y~z")
    invoice = _invoice([line], supplier="A*B*C", invoice_no="44*71", tax="0", total="60.00")
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
    lines = reply.splitlines()
    assert lines[1] == "*ABC*"
    assert lines[2] == "Invoice 4471 · 5 Jul 2026 · 1 line"
    assert '- *Line 1*: I couldn\'t match "xyz" to your usual items. Is it right?' in lines
    assert "A*B" not in reply
    _assert_markup_balanced(reply)
    # The sanitiser itself: item codes keep their underscores, whitespace
    # collapses, nothing left means the fallback.
    assert plain("MILK_PWDR 2.5KG", "x") == "MILK_PWDR 2.5KG"
    assert plain("Gulf\nFoods  Trading", "x") == "Gulf Foods Trading"
    assert plain("***", "Supplier unknown") == "Supplier unknown"
    assert plain(None, "fallback") == "fallback"


def test_closing_is_always_the_last_line():
    note = SimilarPaper(
        supplier_name="Gulf Foods Trading", invoice_no="4470", received_on=datetime.date(2026, 7, 4)
    )
    green = _green_invoice()
    amber = _invoice([_line(None, "5.00", "10.00")], tax="0", total="10.00")
    no_total = _invoice([_line("2", "30.00", "60.00")])
    cases = [
        (compose_invoice_reply, green, CLOSING_ALL_GREEN),
        (compose_invoice_reply, amber, CLOSING_WITH_AMBERS),
        (compose_invoice_reply, no_total, CLOSING_TOTAL_NEEDED),
        (compose_cash_hold_reply, green, CASH_HOLD_NOTE),
    ]
    for compose, invoice, closing in cases:
        reply = compose(
            invoice,
            validate_invoice(invoice),
            [],
            booked_under="Gulf Foods Trading L.L.C.",
            similar_to=note,
        )
        lines = reply.splitlines()
        assert lines[-1] == closing
        assert lines[-2] == ""
        assert lines[-3] == render_duplicate_note(note)
        assert lines[4] == render_booked_under("Gulf Foods Trading L.L.C.")


def test_icons_never_stand_alone():
    samples = [
        REPLY_EXTRACTION_FAILED,
        READ_IT,
        CHECK_HEADING,
        CASH_HOLD_NOTE,
        REPLY_CASH_HOLD_OK,
        REPLY_CORRECTION_REFUSED.format(status="confirmed"),
        compose_cash_approved_notice("Gulf Foods Trading", "4471"),
        compose_confirmation_ack("Gulf Foods Trading", "AED", Decimal("10")),
        compose_duplicate_hold_reply("Gulf", "1", "AED", Decimal("1"), datetime.date(2026, 7, 4)),
        _busy_reply(),
    ]
    for text in samples:
        for line in text.splitlines():
            assert line not in ICONS
            for icon in ICONS:
                if line.startswith(icon):
                    rest = line[len(icon) :]
                    assert rest[0] == " " and (rest[1].isalpha() or rest[1] == "*"), line


def test_empty_sections_are_omitted():
    green = _reply(_green_invoice())
    assert PRICE_MOVES_HEADING not in green
    assert CHECK_HEADING not in green
    for text in [green, _busy_reply(), compose_disambiguation_reply([])]:
        assert "\n\n\n" not in text
        assert not text.endswith("\n")


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
        f"{ICON_UP} Milk Powder 2.5kg up AED 4.00 (50.50 to 54.50, +7.9%)"
    )


def test_falling_price_alert_renders_too():
    alert = PriceAlert(
        item_name="Sugar 10kg",
        prev_price=Decimal("54.50"),
        new_price=Decimal("52.50"),
    )
    assert alert.direction == "down"
    assert (
        render_price_alert(alert) == f"{ICON_DOWN} Sugar 10kg down AED 2.00 (54.50 to 52.50, -3.7%)"
    )


def test_price_alert_percentage():
    def pct(prev: str, new: str) -> Decimal | None:
        return PriceAlert(
            item_name="x", prev_price=Decimal(prev), new_price=Decimal(new)
        ).pct_change

    assert pct("50.50", "54.50") == Decimal("7.9")
    assert pct("22.00", "18.75") == Decimal("-14.8")
    assert pct("51.90", "54.50") == Decimal("5.0")
    # A zero baseline has no share to speak of: no percentage, no exception.
    zero = PriceAlert(item_name="New", prev_price=Decimal("0"), new_price=Decimal("5"))
    assert zero.pct_change is None
    assert render_price_alert(zero) == f"{ICON_UP} New up AED 5.00 (0.00 to 5.00)"


def test_multi_alert_reply_keeps_alert_order_under_the_heading():
    alerts = [
        PriceAlert(item_name="Milk", prev_price=Decimal("50.50"), new_price=Decimal("54.50")),
        PriceAlert(item_name="Tea", prev_price=Decimal("12.00"), new_price=Decimal("11.00")),
    ]
    lines = _reply(_green_invoice(), alerts).splitlines()
    assert lines[4] == ""
    assert lines[5] == PRICE_MOVES_HEADING
    assert lines[6] == f"{ICON_UP} Milk up AED 4.00 (50.50 to 54.50, +7.9%)"
    assert lines[7] == f"{ICON_DOWN} Tea down AED 1.00 (12.00 to 11.00, -8.3%)"
    assert lines[8] == ""
    assert lines[9] == CLOSING_ALL_GREEN


# --- composed invoice reply ---


def test_all_green_reply_exact_and_ends_with_ok_prompt():
    reply = _reply(_green_invoice())
    assert reply == (
        "✅ Read it\n"
        "*Gulf Foods Trading*\n"
        "Invoice 4471 · 5 Jul 2026 · 2 lines\n"
        "Total *AED 105.00*\n"
        "\n"
        "Reply *OK* to confirm."
    )
    assert reply.endswith("Reply *OK* to confirm.")


def test_single_line_invoice_uses_singular_line_word():
    invoice = _invoice([_line("1", "54.5", "54.5")], total="54.5")
    assert summary_block(invoice) == _header("*AED 54.50*", count=1)


def test_total_with_one_decimal_renders_two():
    # Decimal("54.5") must render "54.50", never "54.5".
    invoice = _invoice([_line("1", "54.5", "54.5")], total="54.5")
    assert "Total *AED 54.50*" in _reply(invoice)


def test_default_currency_is_aed_and_invoice_currency_wins():
    no_currency = _invoice([_line("1", "10.00", "10.00")], currency=None, total="10.00")
    assert "Total *AED 10.00*" in summary_block(no_currency)
    sar = _invoice([_line("1", "10.00", "10.00")], currency="SAR", total="10.00")
    assert "Total *SAR 10.00*" in summary_block(sar)


def test_unknown_supplier_and_unreadable_total_fallbacks():
    # WP-26: with the total off the page, the reply shows the line sum, asks
    # the two facts C4 cannot derive without a total, and does NOT offer "or
    # OK to confirm the rest" - the offer that recorded a null total live.
    invoice = _invoice([_line("1", "10.00", "10.00")], supplier=None)
    reply = _reply(invoice)
    assert reply.splitlines() == [
        "✅ Read it",
        "*Supplier unknown*",
        "Invoice 4471 · 5 Jul 2026 · 1 line",
        "Total unreadable",
        "",
        CHECK_HEADING,
        "- *Total*: I couldn't read it. The lines come to AED 10.00. Is that the whole "
        "invoice, VAT included? Reply like `total 10.00 inc vat 5%` or `total 10.00 no vat`, "
        "or the printed total, like `total 976.50`.",
        "",
        CLOSING_TOTAL_NEEDED,
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
        *_header("*AED 800.00*", count=4).splitlines(),
        "",
        CHECK_HEADING,
        "- *Totals*: the lines come to 770.00 but the invoice total says 800.00. Which is right?",
        "- *Line 2*: 10 x 45.00 = 450.00 but the line says 500.00. Which is right?",
        "- *Line 4*: I couldn't read the quantity. How many were delivered? "
        "Reply like `line 4 qty 16`.",
        "...and 1 more to check on the review screen.",
        "",
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
        *_header("*AED 920.00*").splitlines(),
        "",
        CHECK_HEADING,
        "- *Line 2*: I couldn't read the line total. What does it say? "
        "Reply like `line 2 total 90.00`.",
        "- *Line 1*: I couldn't read the quantity. How many were delivered? "
        "Reply like `line 1 qty 16`.",
        "",
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
    assert body[5] == CHECK_HEADING
    assert [ln.split(":")[0] for ln in body[6:9]] == ["- *Line 3*", "- *Line 2*", "- *Line 1*"]
    assert "more to check on the review screen" not in reply
    assert body[-1] == CLOSING_WITH_AMBERS


def test_missing_unit_price_question():
    invoice = _invoice([_line("4", None, "200.00")], tax="0", total="200.00")
    assert (
        "- *Line 1*: I couldn't read the unit price. What price was charged? "
        "Reply like `line 1 price 4.50`."
    ) in _reply(invoice).splitlines()


def test_subtotal_mismatch_question_exact():
    lines = [_line("2", "30.00", "60.00"), _line("4", "10.00", "40.00")]
    invoice = _invoice(lines, subtotal="90.00", tax="5.00", total="105.00")
    assert (
        "- *Subtotal*: the lines add up to 100.00 but the subtotal says 90.00. Which is right?"
    ) in _reply(invoice).splitlines()


def test_taint_amber_document_does_not_burn_a_question_slot():
    # The totals block is amber only because a line failed; the line question
    # already covers it, so no document question is asked.
    invoice = _invoice([_line("2", "3.10", "6.26")], total="6.26")
    reply = _reply(invoice)
    assert reply.splitlines() == [
        *_header("*AED 6.26*", count=1).splitlines(),
        "",
        CHECK_HEADING,
        "- *Line 1*: 2 x 3.10 = 6.20 but the line says 6.26. Which is right?",
        "",
        CLOSING_WITH_AMBERS,
    ]


def test_fractional_qty_renders_plainly_in_the_math_question():
    invoice = _invoice([_line("2.5", "4.00", "11.00")], tax="0", total="11.00")
    lines = _reply(invoice).splitlines()
    assert "- *Line 1*: 2.5 x 4.00 = 10.00 but the line says 11.00. Which is right?" in lines


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
        '- *Line 1*: I couldn\'t match "Karak Chai Mix" to your usual items. Is it right?'
        in reply.splitlines()
    )
    assert reply.endswith(CLOSING_WITH_AMBERS)


# --- required-field ambers (WP-25) ---


def test_missing_date_and_number_each_get_their_question_and_flip_the_closing():
    invoice = _invoice(
        [_line("2", "30.00", "60.00")],
        tax="0",
        total="60.00",
        invoice_no=None,
        invoice_date=None,
    )
    reply = _reply(invoice)
    assert reply.splitlines() == [
        "✅ Read it",
        "*Gulf Foods Trading*",
        "1 line",
        "Total *AED 60.00*",
        "",
        CHECK_HEADING,
        f"- {QUESTION_MISSING_DATE}",
        f"- {QUESTION_MISSING_INVOICE_NO}",
        "",
        CLOSING_WITH_AMBERS,
    ]
    assert QUESTION_MISSING_DATE == (
        "*Date*: I couldn't read the invoice date. What does it say? Reply like `date 5/7/26`."
    )
    assert QUESTION_MISSING_INVOICE_NO == (
        "*Invoice number*: I couldn't read it. What does it say? Reply like `invoice no 4471`."
    )


def test_missing_date_question_survives_a_pile_of_line_ambers():
    # WP-27 acceptance: a null date always produces a question - line ambers
    # overflow to the review screen before the date ask ever does.
    lines = [_line(None, "5.00", str(10 * n)) for n in range(1, 5)]
    invoice = _invoice(lines, tax="0", total="100.00", invoice_date=None)
    reply = _reply(invoice)
    assert f"- {QUESTION_MISSING_DATE}" in reply.splitlines()
    assert OVERFLOW_LINE.format(count=2) in reply.splitlines()


def test_present_date_and_number_ask_nothing():
    assert QUESTION_MISSING_DATE not in _reply(_green_invoice())
    assert QUESTION_MISSING_INVOICE_NO not in _reply(_green_invoice())


def test_ambiguous_date_reply_exact():
    assert compose_ambiguous_date_reply("5/7") == (
        '"5/7" needs a year to be a date. Send it with the year, like `date 5/7/26`.'
    )


# --- cash hold ---


def test_cash_hold_reply_green_exact():
    invoice = _green_invoice()
    reply = compose_cash_hold_reply(invoice, validate_invoice(invoice), [])
    assert reply == f"{_header('*AED 105.00*')}\n\n{CASH_HOLD_NOTE}"
    assert "*OK*" not in reply and "to confirm" not in reply


def test_cash_approved_notice_exact():
    """WP-74: the sentence the branch phone gets once the owner records the
    paper - the promise the cash-hold closing makes, kept word for word."""
    assert (
        compose_cash_approved_notice("Gulf Foods Trading", "INV-1041")
        == "✅ Recorded\n*Gulf Foods Trading* INV-1041, approved by the owner."
    )
    assert (
        compose_cash_approved_notice(None, None)
        == "✅ Recorded\n*Supplier unknown*, approved by the owner."
    )
    assert (
        compose_cash_approved_notice("Al Madina", None)
        == "✅ Recorded\n*Al Madina*, approved by the owner."
    )


def test_cash_hold_reply_keeps_alerts_and_questions_but_closes_with_the_hold():
    invoice = _invoice([_line(None, "5.00", "10.00")], tax="0", total="10.00")
    alert = PriceAlert(item_name="Milk", prev_price=Decimal("50.50"), new_price=Decimal("54.50"))
    reply = compose_cash_hold_reply(invoice, validate_invoice(invoice), [alert])
    lines = reply.splitlines()
    assert lines[5] == PRICE_MOVES_HEADING
    assert lines[6] == f"{ICON_UP} Milk up AED 4.00 (50.50 to 54.50, +7.9%)"
    assert lines[8] == CHECK_HEADING
    assert lines[9] == (
        "- *Line 1*: I couldn't read the quantity. How many were delivered? "
        "Reply like `line 1 qty 16`."
    )
    assert lines[-1] == CASH_HOLD_NOTE
    assert "*OK*" not in reply and "to confirm" not in reply


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


# --- WP-21 appends: confirm-flow messages (the flow itself is confirm.py) ---


def test_confirmation_ack_exact():
    ack = compose_confirmation_ack("Gulf Foods Trading LLC", "AED", Decimal("745.76"))
    assert ack == (
        "✅ Confirmed\n*Gulf Foods Trading LLC*, AED 745.76 recorded.\n"
        "I'll watch these prices for you."
    )


def test_confirmation_ack_fallbacks():
    # One-decimal totals still render two; missing pieces use the header's
    # vocabulary and default currency.
    assert compose_confirmation_ack(None, None, Decimal("50.5")) == (
        "✅ Confirmed\n*Supplier unknown*, AED 50.50 recorded.\nI'll watch these prices for you."
    )
    assert compose_confirmation_ack("Gulf Foods Trading", "AED", None) == (
        "✅ Confirmed\n*Gulf Foods Trading* invoice recorded.\nI'll watch these prices for you."
    )


def test_correction_refused_exact():
    assert REPLY_CORRECTION_REFUSED.format(status="confirmed") == (
        f"{ICON_CHECK} This one is already confirmed, so I can't change it any more."
    )


def test_disambiguation_reply_exact():
    pending = [
        PendingInvoice(
            supplier_name="Al Madina Trading",
            currency="AED",
            total=Decimal("120.00"),
            received_at=datetime.datetime(2026, 8, 22, 11, 30),
        ),
        PendingInvoice(
            supplier_name=None,
            currency=None,
            total=None,
            received_at=datetime.datetime(2026, 8, 22, 10, 5),
        ),
    ]
    assert compose_disambiguation_reply(pending) == (
        "You have 2 invoices waiting. Which one?\n"
        "\n"
        "1. *Al Madina Trading*, AED 120.00, 22 Aug 11:30\n"
        "2. *Supplier unknown*, total unreadable, 22 Aug 10:05\n"
        "\n"
        "Reply with the number first, like `1 OK` or `1 line 2 qty 16`."
    )


def test_disambiguation_single_row_uses_singular_invoice_word():
    # Reached via an out-of-range number ("9 OK") with one invoice pending.
    pending = [
        PendingInvoice(
            supplier_name="Gulf Foods Trading",
            currency="AED",
            total=Decimal("10"),
            received_at=datetime.datetime(2026, 1, 5, 9, 0),
        )
    ]
    lines = compose_disambiguation_reply(pending).splitlines()
    assert lines[0] == "You have 1 invoice waiting. Which one?"
    assert lines[2] == "1. *Gulf Foods Trading*, AED 10.00, 5 Jan 09:00"
    assert lines[4] == DISAMBIGUATION_FOOTER


def test_line_out_of_range_message():
    assert compose_line_out_of_range(4, 2) == (
        "This invoice has 2 lines, so I can't fix line 4 - check the line number and resend."
    )
    assert compose_line_out_of_range(2, 1) == (
        "This invoice has 1 line, so I can't fix line 2 - check the line number and resend."
    )


def test_clarify_exact_and_confirm_flow_messages_have_no_em_dashes():
    assert REPLY_CLARIFY == (
        "Sorry, I didn't get that. Reply *OK* to confirm, or send a fix like:\n"
        "- `line 1 qty 16`\n"
        "- `line 2 price 4.50`\n"
        "- `line 1 name Basmati Rice`\n"
        "- `total 745.76`\n"
        "- `date 5/7/26`\n"
        "- `invoice no 4471`\n"
        "- `currency AED`\n"
        "- `payment credit`"
    )
    samples = [
        REPLY_CLARIFY,
        DISAMBIGUATION_FOOTER,
        compose_confirmation_ack(None, None, None),
        compose_line_out_of_range(3, 1),
        compose_disambiguation_reply(
            [
                PendingInvoice(
                    supplier_name=None,
                    currency=None,
                    total=None,
                    received_at=datetime.datetime(2026, 8, 22, 10, 5),
                )
            ]
        ),
    ]
    for text in samples:
        assert "—" not in text and "–" not in text
        _assert_markup_balanced(text)


# --- WP-44: the duplicate hold and the similar-paper note ---------------------


def test_duplicate_hold_reply_exact():
    reply = compose_duplicate_hold_reply(
        "Gulf Foods Trading", "4471", "AED", Decimal("745.76"), datetime.date(2026, 7, 5)
    )
    assert reply == (
        f"{ICON_HELD} Already recorded\n"
        "*Gulf Foods Trading* 4471 for AED 745.76, received 5 Jul 2026.\n"
        "I've held this copy so nothing is counted twice. "
        "If it really is a new invoice, confirm it on the review screen."
    )
    bare = compose_duplicate_hold_reply(None, None, None, None, datetime.date(2026, 7, 5))
    assert bare.splitlines()[1] == "*Supplier unknown*, received 5 Jul 2026."


def test_booked_under_and_similar_note_render_and_sit_where_they_belong():
    assert render_booked_under("Gulf Foods Trading L.L.C.") == (
        "_Booked under Gulf Foods Trading L.L.C._"
    )
    note = SimilarPaper(
        supplier_name="Al Madina", invoice_no="4471", received_on=datetime.date(2026, 7, 4)
    )
    assert render_duplicate_note(note) == (
        f"{ICON_CHECK} This looks close to Al Madina 4471, received 4 Jul 2026. "
        "Worth checking it isn't the same paper."
    )
    invoice = _green_invoice()
    reply = compose_invoice_reply(
        invoice,
        validate_invoice(invoice),
        [],
        booked_under="Gulf Foods Trading L.L.C.",
        similar_to=note,
    )
    assert reply.splitlines() == [
        *_header("*AED 105.00*").splitlines(),
        "_Booked under Gulf Foods Trading L.L.C._",
        "",
        render_duplicate_note(note),
        "",
        CLOSING_ALL_GREEN,
    ]


# --- WP-26: the totals block is off the page --------------------------------


def test_missing_total_question_shows_the_line_sum_and_asks_the_two_facts():
    # The two facts C4 derives from a total and cannot derive without one:
    # whether the line sum is the whole invoice, and whether it carries VAT.
    invoice = _invoice([_line("2", "30.00", "60.00"), _line("4", "10.00", "40.00")])
    reply = _reply(invoice)
    assert reply.splitlines() == [
        *_header("unreadable").splitlines(),
        "",
        CHECK_HEADING,
        "- *Total*: I couldn't read it. The lines come to AED 100.00. Is that the whole "
        "invoice, VAT included? Reply like `total 100.00 inc vat 5%` or `total 100.00 no vat`, "
        "or the printed total, like `total 976.50`.",
        "",
        CLOSING_TOTAL_NEEDED,
    ]


def test_missing_total_with_an_unreadable_line_asks_plainly_with_no_sum():
    # C4 says there is no line sum the moment one line total is unreadable, so
    # there is no figure worth showing - and the line question carries the gap.
    invoice = _invoice([_line("2", "30.00", "60.00"), _line("4", "10.00", None)])
    questions = _reply(invoice).splitlines()
    assert questions[6] == (
        "- *Total*: I couldn't read it. What does it say? Reply like `total 976.50`."
    )
    assert questions[-1] == CLOSING_TOTAL_NEEDED


def test_missing_total_closing_never_offers_ok():
    # The live 2026-08-25 failure in one assertion: the reply that recorded a
    # null total offered "or OK to confirm the rest".
    invoice = _invoice([_line("2", "30.00", "60.00")])
    assert CLOSING_WITH_AMBERS not in _reply(invoice)
    assert CLOSING_ALL_GREEN not in _reply(invoice)


def test_total_needed_reply_restates_the_question_with_its_reason():
    assert compose_total_needed_reply(Decimal("930"), "AED").splitlines() == [
        "I can't record this one without the invoice total.",
        "The lines come to AED 930.00. Is that the whole invoice, VAT included? "
        "Reply like `total 930.00 inc vat 5%` or `total 930.00 no vat`, "
        "or the printed total, like `total 976.50`.",
    ]
    assert compose_total_needed_reply(None, "AED") == (
        "I can't record this one without the invoice total. What does it say? "
        "Reply like `total 976.50`."
    )


def test_vat_rate_reply_asks_for_the_rate_rather_than_assuming_one():
    assert compose_vat_rate_reply(Decimal("930")) == (
        '"inc vat" needs the rate before I can work out the VAT. '
        "Send it like `total 930.00 inc vat 5%`."
    )


def test_a_reconstructed_total_reads_like_any_other_total_in_the_header():
    # The reply does not label it: the record of how it got there is C8's job
    # (provenance), and the screen is where it has to look reconstructed.
    invoice = _invoice([_line("2", "30.00", "60.00")], total="60.00", tax="0")
    assert summary_block(invoice) == _header("*AED 60.00*", count=1)


# --- WP-28: an invoice billed in someone else's money -----------------------


def test_currency_mismatch_asks_and_names_the_consequence():
    invoice = _invoice([_line("2", "30.00", "60.00")], currency="USD", total="60.00", tax="0")
    reply = compose_invoice_reply(invoice, validate_invoice(invoice), [], tenant_currency="AED")
    assert reply.splitlines() == [
        *_header("*USD 60.00*", count=1).splitlines(),
        "",
        CHECK_HEADING,
        "- *Currency*: this invoice is in USD, not your usual AED. Is that right? I'll record "
        "it as printed and keep it out of your price history. If it's a misread, reply "
        "`currency AED`.",
        "",
        CLOSING_WITH_AMBERS,
    ]


def test_matching_currency_reply_is_byte_identical_to_not_checking_at_all():
    # The acceptance test for every invoice that is not foreign: today's reply,
    # unchanged, byte for byte.
    invoice = _green_invoice()
    validation = validate_invoice(invoice)
    unchecked = compose_invoice_reply(invoice, validation, [])
    assert compose_invoice_reply(invoice, validation, [], tenant_currency="AED") == unchecked
    assert unchecked.endswith(CLOSING_ALL_GREEN)


def test_currency_question_ranks_under_the_totals_block_and_over_the_required_fields():
    invoice = _invoice(
        [_line("2", "30.00", "60.00")],
        currency="USD",
        invoice_no=None,
        invoice_date=None,
    )
    lines = compose_invoice_reply(
        invoice, validate_invoice(invoice), [], tenant_currency="AED"
    ).splitlines()
    assert lines[:6] == [
        "✅ Read it",
        "*Gulf Foods Trading*",
        "1 line",
        "Total unreadable",
        "",
        CHECK_HEADING,
    ]
    questions = lines[6:-2]
    assert questions[0].startswith("- *Total*: I couldn't read it.")
    assert questions[1].startswith("- *Currency*: this invoice is in USD")
    assert questions[2] == f"- {QUESTION_MISSING_DATE}"
    # Four header questions is one over the cap, and the invoice number is the
    # one that gives way - the review screen still shows it.
    assert questions[3] == OVERFLOW_LINE.format(count=1)
    assert lines[-2:] == ["", CLOSING_TOTAL_NEEDED]


def test_unknown_tenant_currency_asks_nothing():
    invoice = _invoice([_line("2", "30.00", "60.00")], currency="USD", total="60.00", tax="0")
    assert compose_invoice_reply(invoice, validate_invoice(invoice), []) == (
        f"{_header('*USD 60.00*', count=1)}\n\n{CLOSING_ALL_GREEN}"
    )


def test_confirmation_ack_says_a_foreign_invoice_stayed_out_of_price_history():
    assert compose_confirmation_ack(
        "Levant Specialty Foods FZCO", "USD", Decimal("250.00"), tenant_currency="AED"
    ) == (
        "✅ Confirmed\n*Levant Specialty Foods FZCO*, USD 250.00 recorded.\n"
        "It's in USD, not AED, so I've kept it out of your price history."
    )
    # Same currency: the promise stands, byte for byte.
    assert compose_confirmation_ack(
        "Gulf Foods", "AED", Decimal("745.76"), tenant_currency="AED"
    ) == compose_confirmation_ack("Gulf Foods", "AED", Decimal("745.76"))


def test_no_em_or_en_dashes_in_the_wp26_and_wp28_messages():
    invoice = _invoice([_line("2", "30.00", "60.00")], currency="USD")
    for text in [
        CLOSING_TOTAL_NEEDED,
        compose_invoice_reply(invoice, validate_invoice(invoice), [], tenant_currency="AED"),
        compose_total_needed_reply(Decimal("930"), "AED"),
        compose_total_needed_reply(None, None),
        compose_vat_rate_reply(Decimal("930")),
        compose_confirmation_ack("Levant", "USD", Decimal("250"), tenant_currency="AED"),
    ]:
        assert "—" not in text and "–" not in text
