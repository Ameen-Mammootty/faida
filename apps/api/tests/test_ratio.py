"""M8 WP-81: the ratio's pure rules (Docs/M8_DECOMPOSITION.md §3 C11.5-C11.8,
the C9 amendment, row 81).

No database: every case builds a branch's days and papers by hand and checks
the figure, the label and the sentence that made it. The API tests in
`test_sales_api.py` prove the same rules through Postgres and the routes.
"""

import datetime
from decimal import Decimal

from faida_api import ratio

D = Decimal
BRANCH = "b1"
PERIOD = ratio.Period(datetime.date(2026, 8, 4), datetime.date(2026, 8, 31))
WEEK = ratio.Period(datetime.date(2026, 8, 25), datetime.date(2026, 8, 31))


def _day(offset: int, net: str, branch: str = BRANCH, takings: str | None = None) -> ratio.SalesDay:
    date = datetime.date(2026, 8, 25) + datetime.timedelta(days=offset)
    return ratio.SalesDay(
        branch_id=branch,
        business_date=date,
        net_sales=D(net),
        takings=D(takings) if takings else (D(net) * D("1.05")).quantize(D("0.01")),
    )


def _week(branch: str = BRANCH) -> list[ratio.SalesDay]:
    return [_day(i, "1000.00", branch) for i in range(7)]


_counter = iter(range(1, 10_000))


def _paper(
    date: str | None,
    total: str,
    tax: str | None = "0.00",
    *,
    branch: str | None = BRANCH,
    status: str = "confirmed",
    currency: str = "AED",
    confirmed: str | None = None,
    arrived: str = "2026-08-30",
    asserted: bool = False,
) -> ratio.Invoice:
    printed = datetime.date.fromisoformat(date) if date else None
    confirm_day = datetime.date.fromisoformat(confirmed) if confirmed else printed
    arrival = datetime.date.fromisoformat(arrived)
    number = next(_counter)
    return ratio.Invoice(
        invoice_id=f"inv-{number}",
        branch_id=branch,
        status=status,
        currency=currency,
        total=D(total),
        tax=D(tax) if tax is not None else None,
        invoice_date=printed,
        purchased_on=(printed or confirm_day) if status == "confirmed" else None,
        placed_on=printed or arrival,
        supplier_name="Gulf Foods",
        invoice_no=f"GF-{number}",
        asserted=asserted,
    )


def _row(days, invoices, period=WEEK, latest=None, branch=BRANCH, name="Al Qusais"):
    return ratio.period_row(
        branch_id=branch,
        branch_name=name,
        days=days,
        invoices=invoices,
        period=period,
        tenant_currency="AED",
        latest_sales_day=latest,
    )


# --- the figure and the reliable row -----------------------------------------


def test_a_full_week_with_confirmed_purchases_reads_reliable_to_the_tenth():
    papers = [_paper("2026-08-25", "5335.79", "254.09"), _paper("2026-08-28", "1500.00", "71.43")]
    row = _row(_week(), papers)
    assert row.quality is ratio.Quality.RELIABLE
    assert row.net_sales == D("7000.00")
    # 5081.70 + 1428.57 = 6510.27, over 7000.00 = 93.0043% -> 93.0
    assert row.purchases == D("6510.27")
    assert row.ratio_pct == D("93.0")
    assert row.deliveries == 2
    assert row.days_loaded == 7 and row.days_missing == 0
    assert row.window == ratio.Window(datetime.date(2026, 8, 25), datetime.date(2026, 8, 31))
    assert row.sales_through == datetime.date(2026, 8, 31)
    assert row.last_purchase_on == datetime.date(2026, 8, 28)
    assert row.notes == ("2 deliveries in this window",)


def test_the_purchase_figure_is_total_less_printed_tax_and_a_missing_tax_is_zero():
    assert _paper("2026-08-25", "5335.79", "254.09").net_purchase == D("5081.70")
    assert _paper("2026-08-25", "100.00", None).net_purchase == D("100.00")


def test_the_ratio_rounds_half_up_to_a_tenth():
    assert ratio.ratio_pct(D("305"), D("1000")) == D("30.5")
    assert ratio.ratio_pct(D("3005"), D("10000")) == D("30.1")  # 30.05 -> 30.1
    assert ratio.ratio_pct(D("1"), D("0")) is None
    assert ratio.ratio_pct(D("1"), None) is None


# --- incomplete: the gaps ---------------------------------------------------------


def test_two_missing_days_read_incomplete_with_the_sentence():
    days = [_day(i, "1000.00") for i in (0, 1, 2, 5, 6)]
    row = _row(days, [_paper("2026-08-26", "700.00")])
    assert row.quality is ratio.Quality.INCOMPLETE
    assert row.days_loaded == 5 and row.days_missing == 2
    assert "2 of 7 days have no sales" in row.notes
    # The figure is still there: withholding it would hide the papers.
    assert row.ratio_pct == D("14.0")


def test_one_missing_day_reads_has_not_have():
    days = [_day(i, "1000.00") for i in (0, 1, 2, 3, 4, 6)]
    row = _row(days, [_paper("2026-08-26", "700.00")])
    assert "1 of 7 days has no sales" in row.notes


def test_a_closed_day_is_a_loaded_zero_never_a_gap():
    days = [_day(i, "1000.00") for i in range(7)]
    days[4] = ratio.SalesDay(BRANCH, datetime.date(2026, 8, 29), D("0.00"), D("0.00"), "summary")
    row = _row(days, [_paper("2026-08-26", "700.00")])
    assert row.days_missing == 0
    assert row.quality is ratio.Quality.RELIABLE


def test_sales_with_no_purchases_reads_incomplete_with_no_ratio():
    row = _row(_week(), [])
    assert row.quality is ratio.Quality.INCOMPLETE
    assert row.ratio_pct is None
    assert row.net_sales == D("7000.00")
    assert row.purchases == D("0.00")
    assert "no confirmed purchases 25-31 Aug" in row.notes


def test_purchases_with_no_sales_reads_incomplete_with_the_purchases_shown():
    row = _row([], [_paper("2026-08-27", "700.00")], latest=datetime.date(2026, 8, 20))
    assert row.quality is ratio.Quality.INCOMPLETE
    assert row.ratio_pct is None
    assert row.net_sales is None
    assert row.purchases == D("700.00")
    assert "no sales loaded 25-31 Aug" in row.notes
    # The window is the whole period when nothing was loaded inside it.
    assert row.window == ratio.Window(WEEK.start, WEEK.end)
    assert row.sales_through == datetime.date(2026, 8, 20)


def test_negative_net_sales_answers_no_ratio_and_reads_incomplete():
    days = [_day(0, "-50.00", takings="-52.50")] + [
        _day(i, "0.00", takings="0.00") for i in range(1, 7)
    ]
    row = _row(days, [_paper("2026-08-26", "700.00")])
    assert row.ratio_pct is None
    assert row.quality is ratio.Quality.INCOMPLETE
    assert "net sales are not positive this period" in row.notes


def test_sales_with_only_an_excluded_purchase_reads_incomplete_and_names_the_exclusion():
    row = _row(_week(), [_paper("2026-08-26", "120.00", currency="USD")])
    assert row.quality is ratio.Quality.INCOMPLETE
    assert row.ratio_pct is None
    assert "no confirmed purchases 25-31 Aug" in row.notes
    assert "1 invoice in USD not counted" in row.notes
    assert [e.currency for e in row.excluded] == ["USD"]


# --- estimated: the papers in doubt -----------------------------------------------


def test_an_awaiting_invoice_reads_estimated_and_is_not_counted():
    papers = [
        _paper("2026-08-26", "700.00"),
        _paper("2026-08-28", "300.00", status="awaiting_confirm"),
    ]
    row = _row(_week(), papers)
    assert row.quality is ratio.Quality.ESTIMATED
    assert row.purchases == D("700.00")
    assert row.ratio_pct == D("10.0")
    assert "1 invoice awaiting confirm" in row.notes
    assert [p.placed_on for p in row.pending] == [datetime.date(2026, 8, 28)]
    assert row.pending[0].undated is False


def test_an_undated_pending_paper_is_placed_by_its_arrival_day():
    papers = [
        _paper("2026-08-26", "700.00"),
        _paper(None, "300.00", status="awaiting_confirm", arrived="2026-08-30"),
    ]
    row = _row(_week(), papers)
    assert row.quality is ratio.Quality.ESTIMATED
    assert "1 undated invoice awaiting confirm" in row.notes
    assert row.pending[0].placed_on == datetime.date(2026, 8, 30)
    assert row.pending[0].undated is True
    # Outside the window it is nobody's paper for this period.
    outside = _paper(None, "300.00", status="awaiting_confirm", arrived="2026-09-15")
    assert _row(_week(), [papers[0], outside]).quality is ratio.Quality.RELIABLE


def test_a_held_and_a_dismissed_invoice_are_not_counted():
    papers = [
        _paper("2026-08-26", "700.00"),
        _paper("2026-08-27", "999.00", status="needs_review"),
        _paper("2026-08-27", "999.00", status="dismissed"),
        _paper("2026-08-27", "999.00", status="draft"),
    ]
    row = _row(_week(), papers)
    assert row.purchases == D("700.00")
    assert row.quality is ratio.Quality.ESTIMATED
    assert "1 invoice held for review" in row.notes
    assert len(row.pending) == 1


def test_a_usd_invoice_is_excluded_and_the_row_reads_estimated_naming_it():
    papers = [_paper("2026-08-26", "700.00"), _paper("2026-08-27", "120.00", currency="USD")]
    row = _row(_week(), papers)
    assert row.quality is ratio.Quality.ESTIMATED
    assert row.purchases == D("700.00")
    assert "1 invoice in USD not counted" in row.notes
    assert row.excluded[0].total == D("120.00")


def test_a_total_typed_by_hand_reads_estimated():
    row = _row(_week(), [_paper("2026-08-26", "700.00", asserted=True)])
    assert row.quality is ratio.Quality.ESTIMATED
    assert row.purchases == D("700.00")
    assert "1 invoice with a total or VAT entered by hand" in row.notes
    assert row.days[1].invoices[0].quality == "estimated"


# --- precedence and the window ----------------------------------------------------


def test_precedence_is_unavailable_over_incomplete_over_estimated():
    nothing = _row([], [], latest=datetime.date(2026, 8, 1))
    assert nothing.quality is ratio.Quality.UNAVAILABLE
    assert nothing.ratio_pct is None and nothing.net_sales is None
    assert nothing.sales_through == datetime.date(2026, 8, 1)
    assert "no sales loaded and no confirmed purchases 25-31 Aug" in nothing.notes

    # Pending papers alone do not make a row available - nothing is counted.
    pending_only = _row([], [_paper("2026-08-26", "300.00", status="awaiting_confirm")])
    assert pending_only.quality is ratio.Quality.UNAVAILABLE
    assert "1 invoice awaiting confirm" in pending_only.notes

    # A gap and a pending paper together: incomplete wins, and both sentences ride.
    days = [_day(i, "1000.00") for i in (0, 1, 2, 3, 5, 6)]  # 30 Aug is a gap
    both = _row(
        days, [_paper("2026-08-26", "700.00"), _paper("2026-08-27", "1", status="awaiting_confirm")]
    )
    assert both.quality is ratio.Quality.INCOMPLETE
    assert "1 invoice awaiting confirm" in both.notes


def test_a_lagging_branch_counts_purchases_to_its_own_newest_day_only():
    days = [_day(i, "1000.00") for i in range(3)]  # 25-27 Aug loaded, the rest not yet
    papers = [_paper("2026-08-26", "500.00"), _paper("2026-08-30", "9999.00")]
    row = _row(days, papers)
    assert row.window == ratio.Window(datetime.date(2026, 8, 25), datetime.date(2026, 8, 27))
    assert row.purchases == D("500.00")
    assert row.deliveries == 1
    assert row.days_missing == 0
    assert row.quality is ratio.Quality.RELIABLE
    assert row.sales_through == datetime.date(2026, 8, 27)


def test_the_window_is_clipped_inside_the_period_not_to_days_outside_it():
    days = [_day(i, "1000.00") for i in range(-3, 7)]  # 22-31 Aug loaded
    row = _row(days, [_paper("2026-08-23", "500.00"), _paper("2026-08-26", "700.00")])
    assert row.window == ratio.Window(WEEK.start, WEEK.end)
    assert row.purchases == D("700.00")
    assert row.net_sales == D("7000.00")


def test_papers_confirmed_today_with_printed_dates_last_month_land_on_last_month():
    papers = [
        _paper("2026-08-26", "100.00", confirmed="2026-09-15"),
        _paper("2026-08-27", "200.00", confirmed="2026-09-15"),
        _paper("2026-08-28", "300.00", confirmed="2026-09-15"),
    ]
    row = _row(_week(), papers)
    assert row.purchases == D("600.00")
    assert [d.business_date.day for d in row.days if d.invoices] == [26, 27, 28]
    september = ratio.Period(datetime.date(2026, 9, 9), datetime.date(2026, 9, 15))
    assert _row(
        [_day(i + 15, "1000.00") for i in range(7)], papers, period=september
    ).purchases == D("0.00")


def test_a_paper_with_no_printed_date_falls_back_to_its_confirm_day():
    paper = _paper(None, "400.00", confirmed="2026-08-29")
    row = _row(_week(), [paper])
    assert row.purchases == D("400.00")
    assert row.days[4].invoices[0].purchased_on == datetime.date(2026, 8, 29)


def test_each_row_counts_its_deliveries_and_the_per_day_breakdown_carries_the_papers():
    papers = [
        _paper("2026-08-25", "100.00"),
        _paper("2026-08-25", "200.00"),
        _paper("2026-08-31", "300.00"),
    ]
    row = _row(_week(), papers)
    assert row.deliveries == 3
    assert "3 deliveries in this window" in row.notes
    first = row.days[0]
    assert first.purchases == D("300.00")
    assert [i.net_purchase for i in first.invoices] == [D("100.00"), D("200.00")]
    assert row.days[3].purchases == D("0.00") and row.days[3].net_sales == D("1000.00")


def test_a_purchase_day_with_no_sales_row_still_appears_in_the_breakdown():
    days = [_day(i, "1000.00") for i in (0, 1, 2, 3, 4, 5)]  # 31 Aug missing
    row = _row(days + [_day(6, "1000.00")], [_paper("2026-08-27", "100.00")])
    assert row.days[2].net_sales == D("1000.00")
    lagging = _row([_day(0, "1000.00"), _day(2, "1000.00")], [_paper("2026-08-26", "100.00")])
    assert [(d.business_date.day, d.net_sales, d.purchases) for d in lagging.days] == [
        (25, D("1000.00"), D("0.00")),
        (26, None, D("100.00")),
        (27, D("1000.00"), D("0.00")),
    ]


# --- the group, the total, the ranking ------------------------------------------


def test_a_confirmed_invoice_with_no_branch_lands_in_the_unassigned_group_and_no_row():
    papers = [_paper("2026-08-26", "700.00"), _paper("2026-08-27", "50.00", branch=None)]
    row = _row(_week(), papers)
    assert row.purchases == D("700.00")
    group = ratio.unassigned_group(papers, WEEK, "AED")
    assert group.count == 1 and group.purchases == D("50.00")
    assert group.invoices[0].invoice_id == papers[1].invoice_id
    # A pending or foreign-currency paper with no branch is not in the group either.
    stray = [_paper("2026-08-27", "1.00", branch=None, status="awaiting_confirm")]
    assert ratio.unassigned_group(stray, WEEK, "AED").count == 0
    foreign = [_paper("2026-08-27", "1.00", branch=None, currency="USD")]
    assert ratio.unassigned_group(foreign, WEEK, "AED").count == 0


def test_the_chain_total_equals_the_sum_of_the_rows_plus_the_group():
    papers = [
        _paper("2026-08-26", "700.00"),
        _paper("2026-08-26", "300.00", branch="b2"),
        _paper("2026-08-27", "50.00", branch=None),
    ]
    rows = [
        _row(_week(), papers),
        _row(_week("b2"), papers, branch="b2", name="Al Nahda"),
        _row([], papers, branch="b3", name="Rolla"),
    ]
    group = ratio.unassigned_group(papers, WEEK, "AED")
    total = ratio.chain_total(rows, group)
    assert total.net_sales == sum(r.net_sales or D(0) for r in rows) == D("14000.00")
    assert total.purchases == sum(r.purchases for r in rows) + group.purchases == D("1050.00")
    assert total.ratio_pct == D("7.5")
    assert total.quality is ratio.Quality.INCOMPLETE  # Rolla has nothing: a hole in the chain
    assert "1 of 3 branches with nothing loaded" in total.notes
    assert "1 invoice on no branch, counted in the total" in total.notes


def test_the_total_is_unavailable_only_when_every_row_is():
    rows = [_row([], [], branch="b1"), _row([], [], branch="b2")]
    assert (
        ratio.chain_total(rows, ratio.unassigned_group([], WEEK, "AED")).quality
        is ratio.Quality.UNAVAILABLE
    )
    mixed = [_row(_week(), [_paper("2026-08-26", "700.00")]), _row([], [], branch="b2", name="x")]
    total = ratio.chain_total(mixed, ratio.unassigned_group([], WEEK, "AED"))
    assert total.quality is ratio.Quality.INCOMPLETE
    assert "1 of 2 branches with nothing loaded" in total.notes


def test_the_ranking_puts_the_highest_ratio_first_and_unrated_rows_last():
    high = _row(_week(), [_paper("2026-08-26", "3500.00")], branch="b1", name="Rolla")
    low = _row(
        _week("b2"), [_paper("2026-08-26", "700.00", branch="b2")], branch="b2", name="Al Qusais"
    )
    none_a = _row(_week("b3"), [], branch="b3", name="Deira")
    none_b = _row(_week("b4"), [], branch="b4", name="Al Nahda")
    ranked = ratio.rank([none_a, low, none_b, high])
    assert [r.branch_name for r in ranked] == ["Rolla", "Al Qusais", "Al Nahda", "Deira"]


def test_window_words():
    assert (
        ratio.window_words(ratio.Window(datetime.date(2026, 8, 25), datetime.date(2026, 8, 31)))
        == "25-31 Aug"
    )
    assert (
        ratio.window_words(ratio.Window(datetime.date(2026, 8, 28), datetime.date(2026, 9, 3)))
        == "28 Aug-3 Sep"
    )
    assert (
        ratio.window_words(ratio.Window(datetime.date(2026, 8, 31), datetime.date(2026, 8, 31)))
        == "31 Aug"
    )


# --- coverage by sales value ---------------------------------------------------------


def _value(name, positive, refund="0", *, item_id=None, mapped=None, excluded=False, code=None):
    return ratio.TillItemValue(
        till_item_id=item_id or name.lower().replace(" ", "-"),
        name=name,
        code=code,
        menu_item_id=mapped,
        excluded=excluded,
        positive_value=D(positive),
        refund_value=D(refund),
    )


PLATES = {
    "karak": ratio.MenuPlate("karak", "Karak Tea", "reliable_with_limitations"),
    "chai": ratio.MenuPlate("chai", "Masala Chai", "estimated"),
    "paratha": ratio.MenuPlate("paratha", "Paratha", "incomplete"),
}


def test_coverage_counts_costed_plates_names_estimated_points_and_buckets_the_rest():
    values = [
        _value("KARAK TEA", "6000.00", mapped="karak"),
        _value("MASALA CHAI", "1200.00", mapped="chai"),
        _value("PARATHA", "800.00", mapped="paratha"),
        _value("CHKN 65 DRY", "2000.00", code="131"),
        _value("DELIVERY CHARGE", "640.00", excluded=True),
        _value("REFUND", "0.00", "-210.00", mapped="karak"),
    ]
    result = ratio.coverage(values, PLATES)
    assert result.sales_value == D("10000.00")  # the delivery charge is takings, not menu sales
    assert result.costed_value == D("7200.00")
    assert result.costed_pct == D("72.0")
    assert result.estimated_points == D("12.0")
    assert result.uncosted_incomplete_plate == D("800.00")
    assert result.uncosted_unmapped == D("2000.00")
    assert result.refunds == D("-210.00")
    assert result.not_menu_items == D("640.00")
    assert [q.name for q in result.queue] == ["CHKN 65 DRY"]
    assert result.queue[0].code == "131" and result.queue[0].value == D("2000.00")
    assert [(m.name, m.plate_quality) for m in result.mapped] == [
        ("KARAK TEA", "reliable_with_limitations"),
        ("MASALA CHAI", "estimated"),
        ("PARATHA", "incomplete"),
        ("REFUND", "reliable_with_limitations"),
    ]
    assert [e.name for e in result.excluded] == ["DELIVERY CHARGE"]


def test_coverage_stays_within_0_and_100_and_can_reach_both():
    everything_costed = ratio.coverage([_value("KARAK TEA", "10.00", mapped="karak")], PLATES)
    assert everything_costed.costed_pct == D("100.0")
    nothing_costed = ratio.coverage([_value("X", "10.00")], PLATES)
    assert nothing_costed.costed_pct == D("0.0")
    refunds_only = ratio.coverage([_value("X", "0.00", "-5.00", mapped="karak")], PLATES)
    assert refunds_only.costed_pct is None and refunds_only.sales_value == D("0.00")


def test_the_queue_is_ranked_by_value_most_first():
    values = [_value("A", "10.00"), _value("B", "30.00"), _value("C", "20.00"), _value("D", "0.00")]
    result = ratio.coverage(values, PLATES)
    assert [q.name for q in result.queue] == ["B", "C", "A", "D"]
