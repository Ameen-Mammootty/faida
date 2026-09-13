"""M13 WP-131: the incentive's rules, pure - no database, no clock (plan.md
§8 M13 D2 to D12; issue #6's arithmetic; issue #11's acceptance).

Every case here hands `incentive.py` the scheme month as the rows would say
it, a branch's loaded days and the till's item days, and reads the figures
and the words back: a refund reducing portions, a cap binding, a hole named
and excluded, a week clipped to the month, the split summing exactly to the
pool, the provisional and final words, the approved figures standing beside
the recomputed ones, and the banned words absent from every sentence.
"""

import datetime
from decimal import Decimal

import pytest

from faida_api import incentive
from faida_api.incentive import (
    BANNED_WORDS,
    Approval,
    BranchTargets,
    ItemDay,
    LoadedDay,
    PushItem,
    PushWeek,
    SchemeMonth,
    Shares,
    compose_statement,
    figures_from_json,
    figures_json,
    push_weeks,
    statement_from_json,
    statement_json,
)
from faida_api.ratio import Window

SEPT = datetime.date(2026, 9, 1)
A = "br-a"
B = "br-b"
CURRENCY = "AED"
SHARES = Shares(Decimal("50"), Decimal("20"), Decimal("30"))


def _day(month: datetime.date, day: int) -> datetime.date:
    return month.replace(day=day)


def _item(
    push_item_id: str,
    name: str,
    rate: str,
    targets: dict,
    *,
    category: str | None = "Tea Corner",
    archived: bool = False,
    mapped: bool = True,
) -> PushItem:
    return PushItem(
        push_item_id=push_item_id,
        menu_item_id=f"menu-{push_item_id}",
        name=name,
        category=category,
        rate_per_portion=Decimal(rate),
        archived=archived,
        mapped=mapped,
        targets={branch: Decimal(target) for branch, target in targets.items()},
    )


def _scheme(
    weeks: dict[int, tuple[PushItem, ...]] | None = None,
    *,
    net_target: str = "50000",
    pct: str = "10",
    cap: str | None = None,
    month: datetime.date = SEPT,
) -> SchemeMonth:
    """September 2026 for two branches, the push list of week `n` (0-based)
    as given, the others empty."""
    windows = push_weeks(month)
    weeks = weeks or {}
    return SchemeMonth(
        scheme_month_id="sm-1",
        month=month,
        shares=SHARES,
        targets={
            A: BranchTargets(
                A, Decimal(net_target), Decimal(pct), None if cap is None else Decimal(cap)
            ),
            B: BranchTargets(B, Decimal("30000"), Decimal("5"), None),
        },
        weeks=tuple(
            PushWeek(f"pw-{index}", window, weeks.get(index, ()))
            for index, window in enumerate(windows)
        ),
    )


def _loaded(branch: str, days: range, net: str = "1000.00") -> list[LoadedDay]:
    return [LoadedDay(branch, _day(SEPT, d), Decimal(net)) for d in days]


def _sold(branch: str, menu_item_id: str, day: int, qty: str, *, no_qty: int = 0) -> ItemDay:
    return ItemDay(branch, _day(SEPT, day), menu_item_id, Decimal(qty), no_qty)


def _statement(scheme, branch=A, *, days=(), items=(), approval=None, newest=None):
    return compose_statement(
        scheme,
        branch,
        days=list(days),
        items=list(items),
        newest_loaded=newest,
        approval=approval,
        currency=CURRENCY,
    )


# --- the calendar --------------------------------------------------------------


def test_push_weeks_are_monday_to_sunday_clipped_to_the_month():
    """September 2026 starts on a Tuesday: a six-day first week, three whole
    weeks, and a three-day last week that never waits for October."""
    weeks = push_weeks(SEPT)
    assert [(w.start.day, w.end.day) for w in weeks] == [
        (1, 6),
        (7, 13),
        (14, 20),
        (21, 27),
        (28, 30),
    ]
    assert all(w.start.month == 9 and w.end.month == 9 for w in weeks)
    assert weeks[1].start.weekday() == 0 and weeks[1].end.weekday() == 6


def test_a_month_starting_on_a_wednesday_gets_a_first_week_of_five_days():
    weeks = push_weeks(datetime.date(2026, 7, 1))
    assert weeks[0] == Window(datetime.date(2026, 7, 1), datetime.date(2026, 7, 5))


def test_a_31_day_month_starting_on_a_monday_gets_five_weeks():
    weeks = push_weeks(datetime.date(2027, 3, 1))
    assert len(weeks) == 5
    assert weeks[-1] == Window(datetime.date(2027, 3, 29), datetime.date(2027, 3, 31))


def test_a_week_is_frozen_from_its_first_day_and_says_so():
    week = Window(datetime.date(2026, 9, 7), datetime.date(2026, 9, 13))
    assert incentive.frozen_week_sentence(week, datetime.date(2026, 9, 6)) is None
    assert incentive.frozen_week_sentence(week, datetime.date(2026, 9, 7)) == (
        "the week of 7-13 Sep has started and is frozen"
    )
    assert incentive.frozen_week_sentence(week, datetime.date(2026, 9, 20)) == (
        "the week of 7-13 Sep has ended and is frozen"
    )


def test_month_words_and_keys():
    assert incentive.month_words(SEPT) == "September 2026"
    assert incentive.month_key(SEPT) == "2026-09"
    assert incentive.parse_month_key("2026-09") == SEPT
    assert incentive.parse_month_key("september") is None
    assert incentive.days_in_month(SEPT) == 30


# --- the refusals the doors share ------------------------------------------------


#: A chain of three, as the create form knows them: the id in the box and the
#: name the refusal has to say.
BRANCH_NAMES = {"b1": "Al Quoz", "b2": "Karama", "b3": "Deira"}


def _typed(rows) -> list[incentive.TypedTarget]:
    """What the owner typed into the boxes, strings as the form holds them."""
    return [
        incentive.TypedTarget(
            branch_id=branch,
            net_sales_target=None if net is None else Decimal(net),
            above_target_pct=None if pct is None else Decimal(pct),
            cap=None if cap is None else Decimal(cap),
        )
        for branch, net, pct, cap in rows
    ]


@pytest.mark.parametrize(
    "shares, sentence",
    [
        ((Decimal("50"), Decimal("20"), Decimal("30")), None),
        ((Decimal("50"), Decimal("20"), None), "the sales team share is missing"),
        ((Decimal("-1"), Decimal("51"), Decimal("50")), "the manager share cannot be negative"),
        ((Decimal("50"), Decimal("20"), Decimal("20")), "sum to 90%, not 100%"),
        ((Decimal("33.3"), Decimal("33.3"), Decimal("33.3")), "sum to 99.9%, not 100%"),
        # A share is kept to two decimals. These three sum to exactly 100 and
        # are still refused, because the row would round each one down and
        # then hold 99.99 - which the table's own check refuses in SQL, which
        # is no way to tell an owner they typed one decimal too many.
        (
            (Decimal("33.334"), Decimal("33.333"), Decimal("33.333")),
            "the manager share is written to more decimals",
        ),
        ((Decimal("33.34"), Decimal("33.33"), Decimal("33.33")), None),
    ],
)
def test_role_shares_are_three_percentages_summing_to_one_hundred(shares, sentence):
    problem = incentive.shares_problem(*shares)
    if sentence is None:
        assert problem is None
    else:
        assert sentence in problem


@pytest.mark.parametrize(
    "targets, sentence",
    [
        ((Decimal("50000"), Decimal("10"), None), None),
        ((Decimal("50000"), Decimal("10"), Decimal("500")), None),
        ((Decimal("-1"), Decimal("10"), None), "cannot be negative"),
        ((Decimal("50000"), Decimal("101"), None), "between 0 and 100"),
        ((Decimal("50000"), Decimal("10"), Decimal("-5")), "leave it blank for no cap"),
        ((None, Decimal("10"), None), "a net sales target is needed"),
    ],
)
def test_branch_targets_are_checked_in_one_place(targets, sentence):
    problem = incentive.targets_problem(*targets)
    if sentence is None:
        assert problem is None
    else:
        assert sentence in problem


@pytest.mark.parametrize(
    "targets, sentence",
    [
        ([("b1", "50000", "10", None)], "Karama and Deira have no target"),
        ([("b1", "50000", "10", None), ("b2", "40000", "10", None)], "Deira has no target"),
        ([], "Al Quoz, Karama and Deira have no target"),
        ([("b1", "50000", "10", None), ("b1", "50000", "10", None)], "Al Quoz was sent two"),
        ([("b9", "50000", "10", None)], "not in this chain"),
        ([("b1", "-1", "10", None)], "Al Quoz: a net sales target cannot be negative"),
        ([("b1", "50000", "101", None)], "Al Quoz: the percentage"),
        ([("b1", "50000", "10", "-1")], "Al Quoz: a cap cannot be negative"),
        ([("b1", None, "10", None)], "Al Quoz: a net sales target is needed"),
    ],
)
def test_a_months_targets_cover_every_branch_and_name_the_one_that_is_wrong(targets, sentence):
    """Every branch of the chain gets exactly one target, because a scheme
    month scores every branch and one the owner typed no figure for would be
    scored against nothing; and an owner looking at three boxes is told which
    box is wrong (D3)."""
    problem = incentive.branch_targets_problem(BRANCH_NAMES, _typed(targets))
    assert problem is not None and sentence in problem


def test_a_target_for_every_branch_is_no_problem_at_all():
    whole = [("b1", "50000", "10", None), ("b2", "40000", "10", "1500"), ("b3", "30000", "8", None)]
    assert incentive.branch_targets_problem(BRANCH_NAMES, _typed(whole)) is None


def test_a_month_already_created_is_refused_by_its_own_name():
    assert incentive.month_taken_sentence(SEPT).startswith("September 2026 already has")
    assert "frozen" in incentive.month_taken_sentence(SEPT)


def test_an_unmapped_or_archived_menu_item_is_refused_by_name():
    assert incentive.push_item_problem("Sulaimani", archived=False, mapped=True) is None
    assert "Sulaimani has no till name mapped to it" in incentive.push_item_problem(
        "Sulaimani", archived=False, mapped=False
    )
    assert "Sulaimani is archived" in incentive.push_item_problem(
        "Sulaimani", archived=True, mapped=True
    )


# --- the arithmetic -------------------------------------------------------------


def test_a_refund_reduces_portions_and_the_rate_pays_above_target_only():
    """120 sold, 5 refunded, a target of 100 at 0.50 a portion: 115 portions,
    15 above, AED 7.50 earned (D8, D9)."""
    karak = _item("k", "Karak", "0.50", {A: "100", B: "50"})
    scheme = _scheme({1: (karak,)})
    statement = _statement(
        scheme,
        days=_loaded(A, range(1, 14)),
        items=[_sold(A, "menu-k", 8, "120"), _sold(A, "menu-k", 9, "-5")],
    )
    week = statement.figures.weeks[1]
    (item,) = week.items
    assert item.portions == Decimal("115.000")
    assert item.portions_above == Decimal("15.000")
    assert item.earned == Decimal("7.50")
    assert item.words == "115 of 100 portions"
    assert week.earned == Decimal("7.50")
    assert statement.figures.items_earned == Decimal("7.50")


def test_portions_below_target_earn_nothing_and_never_go_negative():
    karak = _item("k", "Karak", "0.50", {A: "100"})
    scheme = _scheme({1: (karak,)})
    statement = _statement(
        scheme, days=_loaded(A, range(1, 14)), items=[_sold(A, "menu-k", 8, "40")]
    )
    (item,) = statement.figures.weeks[1].items
    assert item.portions == Decimal("40.000")
    assert item.portions_above == Decimal("0")
    assert item.earned == Decimal("0.00")
    assert item.words == "40 of 100 portions"


def test_net_sales_above_target_earn_the_percentage_and_the_pool_sums_both():
    """13 days at 5,000: 65,000 against a 50,000 target at 10% is 1,500; plus
    the karak's 7.50 is a pool of 1,507.50, whole dirhams 1,508."""
    karak = _item("k", "Karak", "0.50", {A: "100"})
    scheme = _scheme({1: (karak,)})
    statement = _statement(
        scheme,
        days=_loaded(A, range(1, 14), net="5000.00"),
        items=[_sold(A, "menu-k", 8, "115")],
    )
    figures = statement.figures
    assert figures.net_sales == Decimal("65000.00")
    assert figures.net_above == Decimal("15000.00")
    assert figures.net_earned == Decimal("1500.00")
    assert figures.pool == Decimal("1507.50")
    assert figures.pool_rounded == Decimal("1508")
    assert figures.net_words == "AED 65,000 of AED 50,000"
    assert figures.pool_words == "AED 1,508"
    assert figures.capped is False


def test_a_cap_binds_and_is_named():
    karak = _item("k", "Karak", "0.50", {A: "100"})
    scheme = _scheme({1: (karak,)}, cap="1000")
    statement = _statement(
        scheme,
        days=_loaded(A, range(1, 14), net="5000.00"),
        items=[_sold(A, "menu-k", 8, "115")],
    )
    figures = statement.figures
    assert figures.pool_before_cap == Decimal("1507.50")
    assert figures.capped is True
    assert figures.pool == Decimal("1000.00")
    assert figures.pool_rounded == Decimal("1000")
    assert "capped at AED 1,000; AED 1,508 earned before the cap" in statement.notes


def test_a_hole_is_named_excluded_and_never_a_nought():
    """A push item whose dish was archived after the list was set, and one
    whose till name was unmapped: both are holes, both named, neither zero."""
    archived = _item("a", "Honey Cake", "1.00", {A: "10"}, archived=True)
    unmapped = _item("u", "Sulaimani", "0.25", {A: "50"}, mapped=False)
    karak = _item("k", "Karak", "0.50", {A: "100"})
    scheme = _scheme({1: (archived, unmapped, karak)})
    statement = _statement(
        scheme,
        days=_loaded(A, range(1, 14)),
        items=[
            _sold(A, "menu-a", 8, "500"),
            _sold(A, "menu-u", 8, "500"),
            _sold(A, "menu-k", 8, "110"),
        ],
    )
    cake, tea, kar = statement.figures.weeks[1].items
    assert cake.portions is None and cake.earned == Decimal("0.00")
    assert cake.hole == "Honey Cake cannot be counted: it was archived from the menu"
    assert tea.portions is None and tea.earned == Decimal("0.00")
    assert tea.hole == "Sulaimani cannot be counted: no till name is mapped to it"
    assert kar.earned == Decimal("5.00")
    assert statement.figures.items_earned == Decimal("5.00")
    assert (
        "7-13 Sep: Honey Cake cannot be counted: it was archived from the menu" in statement.notes
    )
    assert "7-13 Sep: Sulaimani cannot be counted: no till name is mapped to it" in statement.notes


def test_a_week_is_clipped_so_a_day_outside_the_month_never_counts():
    """The last week is 28-30 Sep; a line dated 1 Oct is another month's."""
    karak = _item("k", "Karak", "0.50", {A: "10"})
    scheme = _scheme({4: (karak,)})
    october = ItemDay(A, datetime.date(2026, 10, 1), "menu-k", Decimal("500"), 0)
    statement = _statement(
        scheme, days=_loaded(A, range(1, 31)), items=[_sold(A, "menu-k", 29, "12"), october]
    )
    (item,) = statement.figures.weeks[4].items
    assert item.portions == Decimal("12.000")
    assert item.earned == Decimal("1.00")


def test_a_line_in_another_week_or_another_branch_does_not_count():
    karak = _item("k", "Karak", "0.50", {A: "10", B: "10"})
    scheme = _scheme({1: (karak,)})
    statement = _statement(
        scheme,
        days=_loaded(A, range(1, 14)),
        items=[
            _sold(A, "menu-k", 8, "12"),
            _sold(A, "menu-k", 14, "50"),
            _sold(B, "menu-k", 8, "50"),
        ],
    )
    (item,) = statement.figures.weeks[1].items
    assert item.portions == Decimal("12.000")


def test_the_split_sums_exactly_to_the_pool_with_the_remainder_on_the_sales_share():
    split = incentive.split_pool(
        Decimal("100.01"), Shares(Decimal("33.33"), Decimal("33.33"), Decimal("33.34"))
    )
    assert split.manager == Decimal("33.33")
    assert split.supervisor == Decimal("33.33")
    assert split.sales == Decimal("33.35")
    assert split.manager + split.supervisor + split.sales == Decimal("100.01")


def test_the_statement_split_uses_the_snapshotted_shares():
    karak = _item("k", "Karak", "0.50", {A: "100"})
    scheme = _scheme({1: (karak,)})
    statement = _statement(
        scheme, days=_loaded(A, range(1, 14), net="5000.00"), items=[_sold(A, "menu-k", 8, "115")]
    )
    split = statement.figures.split
    assert split.shares == SHARES
    assert (split.manager, split.supervisor, split.sales) == (
        Decimal("753.75"),
        Decimal("301.50"),
        Decimal("452.25"),
    )
    assert split.manager + split.supervisor + split.sales == statement.figures.pool


def test_a_branch_with_nothing_loaded_has_no_pool_and_says_so():
    scheme = _scheme({1: (_item("k", "Karak", "0.50", {A: "100"}),)})
    statement = _statement(scheme, days=[], items=[])
    figures = statement.figures
    assert figures.days_loaded == 0
    assert figures.pool is None and figures.pool_rounded is None and figures.split is None
    assert figures.pool_words == "nothing loaded yet"
    assert statement.status == "provisional"
    assert statement.status_words == "provisional, 0 of 30 days loaded"


def test_a_week_the_owner_left_empty_is_named_and_scores_nothing():
    scheme = _scheme({})
    statement = _statement(scheme, days=_loaded(A, range(1, 14)))
    assert all(week.empty and week.words == "no push list" for week in statement.figures.weeks)
    assert statement.notes[0] == "1-6 Sep: no push list"
    assert statement.figures.items_earned == Decimal("0.00")


def test_till_lines_with_no_quantity_are_counted_apart_and_named():
    karak = _item("k", "Karak", "0.50", {A: "10"})
    scheme = _scheme({1: (karak,)})
    statement = _statement(
        scheme, days=_loaded(A, range(1, 14)), items=[_sold(A, "menu-k", 8, "12", no_qty=2)]
    )
    (item,) = statement.figures.weeks[1].items
    assert item.no_qty_lines == 2
    assert (
        "7-13 Sep: 2 till lines for Karak carried no quantity and are not counted"
        in statement.notes
    )


def test_the_headline_rounds_half_up_with_the_exact_figure_beneath():
    karak = _item("k", "Karak", "0.50", {A: "0"})
    scheme = _scheme({1: (karak,)}, net_target="0", pct="0")
    statement = _statement(
        scheme, days=_loaded(A, range(1, 14)), items=[_sold(A, "menu-k", 8, "2481")]
    )
    assert statement.figures.pool == Decimal("1240.50")
    assert statement.figures.pool_rounded == Decimal("1241")
    assert statement.figures.pool_words == "AED 1,241"


# --- provisional, final, and the till saying otherwise ---------------------------


def test_provisional_counts_the_loaded_days_against_the_calendar():
    scheme = _scheme({})
    statement = _statement(scheme, days=_loaded(A, range(1, 27)))
    assert statement.status_words == "provisional, 26 of 30 days loaded"
    assert incentive.approvable(statement.figures) == (
        "the month is provisional, 26 of 30 days loaded: load every day before approving"
    )
    complete = _statement(scheme, days=_loaded(A, range(1, 31)))
    assert complete.status_words == "provisional, 30 of 30 days loaded"
    assert incentive.approvable(complete.figures) is None


def _approval(figures) -> Approval:
    return Approval(
        approved_at=datetime.datetime(2026, 10, 2, 9, 0, tzinfo=datetime.UTC),
        actor="user:owner",
        reason="September paid on 2 October",
        figures=figures_json(figures),
    )


def test_an_approved_statement_is_final_and_reads_the_approved_figures():
    karak = _item("k", "Karak", "0.50", {A: "100"})
    scheme = _scheme({1: (karak,)})
    days = _loaded(A, range(1, 31), net="2000.00")
    items = [_sold(A, "menu-k", 8, "115")]
    live = _statement(scheme, days=days, items=items)
    final = _statement(scheme, days=days, items=items, approval=_approval(live.figures))
    assert final.status == "final"
    assert final.status_words == "final"
    assert final.till_now_says_otherwise is False
    assert final.recomputed is None
    assert final.figures == live.figures
    assert final.approval.reason == "September paid on 2 October"


def test_a_day_replaced_after_approval_keeps_the_approved_figures_and_says_the_till_differs():
    karak = _item("k", "Karak", "0.50", {A: "100"})
    scheme = _scheme({1: (karak,)})
    days = _loaded(A, range(1, 31), net="2000.00")
    items = [_sold(A, "menu-k", 8, "115")]
    approved = _statement(scheme, days=days, items=items).figures
    # The re-upload: day 8 now prints 100 karak, not 115.
    later = _statement(
        scheme, days=days, items=[_sold(A, "menu-k", 8, "100")], approval=_approval(approved)
    )
    assert later.status == "final"
    assert later.status_words == "final; the till now says otherwise"
    assert later.till_now_says_otherwise is True
    assert later.figures == approved  # what was paid stands
    assert later.recomputed is not None
    assert later.recomputed.weeks[1].items[0].portions == Decimal("100.000")
    assert later.recomputed.pool < approved.pool
    assert any(note.startswith("the till now says otherwise") for note in later.notes)


def test_the_approval_door_refuses_in_the_modules_own_words_strongest_fact_first():
    """The three refusals, worded once (D10, D11): a statement already final
    stays final whatever else is typed; a month with a day missing is refused
    with the count; a blank reason is refused. A complete month with a reason
    passes."""
    scheme = _scheme({})
    partial = _statement(scheme, days=_loaded(A, range(1, 27)))
    assert incentive.approval_problem(partial, "paid") == (
        "the month is provisional, 26 of 30 days loaded: load every day before approving"
    )
    complete = _statement(scheme, days=_loaded(A, range(1, 31)))
    assert incentive.approval_problem(complete, "   ") == incentive.REASON_REQUIRED
    assert incentive.approval_problem(complete, "September paid on 2 October") is None
    final = _statement(scheme, days=_loaded(A, range(1, 31)), approval=_approval(complete.figures))
    assert incentive.approval_problem(final, "again") == (
        "this statement is already final: approved by user:owner on 2026-10-02"
    )
    # A final statement is final even when the till now says otherwise.
    later = _statement(scheme, days=_loaded(A, range(1, 27)), approval=_approval(complete.figures))
    assert later.till_now_says_otherwise is True
    assert incentive.approval_problem(later, "again").startswith("this statement is already final")


# --- the wire ---------------------------------------------------------------------


def test_figures_round_trip_through_their_json_and_money_is_strings():
    karak = _item("k", "Karak", "0.50", {A: "100"})
    scheme = _scheme({1: (karak,)}, cap="1000")
    statement = _statement(
        scheme, days=_loaded(A, range(1, 14), net="5000.00"), items=[_sold(A, "menu-k", 8, "115")]
    )
    data = figures_json(statement.figures)
    assert figures_from_json(data) == statement.figures
    for key in ("net_sales", "net_sales_target", "pool", "pool_rounded", "cap", "pool_before_cap"):
        assert isinstance(data[key], str), key
    assert isinstance(data["weeks"][1]["items"][0]["portions"], str)
    assert isinstance(data["split"]["manager"], str)
    assert data["days_loaded"] == 13


def test_a_statement_round_trips_through_its_json():
    karak = _item("k", "Karak", "0.50", {A: "100"})
    scheme = _scheme({1: (karak,)})
    days = _loaded(A, range(1, 31), net="2000.00")
    approved = _statement(scheme, days=days, items=[_sold(A, "menu-k", 8, "115")]).figures
    statement = _statement(
        scheme,
        days=days,
        items=[_sold(A, "menu-k", 8, "100")],
        approval=_approval(approved),
        newest=datetime.date(2026, 9, 30),
    )
    data = statement_json(statement, branch_name="Al Barsha Branch")
    assert data["branch_name"] == "Al Barsha Branch"
    assert data["month"] == "2026-09"
    assert data["status"] == "final"
    assert data["approval"]["actor"] == "user:owner"
    back = statement_from_json(data)
    assert back.figures == statement.figures
    assert back.recomputed == statement.recomputed
    assert back.status_words == statement.status_words
    assert back.newest_loaded == datetime.date(2026, 9, 30)


def test_menu_items_group_by_category_with_other_last():
    grouped = incentive.group_by_category(
        [
            {"id": "1", "name": "Karak", "category": "Tea Corner"},
            {"id": "2", "name": "Honey Cake", "category": None},
            {"id": "3", "name": "Mandi", "category": "Rice"},
            {"id": "4", "name": "Sulaimani", "category": "Tea Corner"},
        ]
    )
    assert [group["category"] for group in grouped] == ["Rice", "Tea Corner", "Other"]
    assert [item["name"] for item in grouped[1]["items"]] == ["Karak", "Sulaimani"]
    assert grouped[0]["guidance"] == "one to three per category, as a guide"


def test_the_kept_and_last_month_words():
    assert incentive.kept_words(Decimal("4.123"), "AED") == "keeps AED 4.12 per plate"
    assert incentive.kept_words(None, "AED") == "not costed"
    assert incentive.previous_month_words(Decimal("41200.40"), "AED") == "AED 41,200 last month"
    assert incentive.previous_month_words(None, "AED") == "no sales loaded last month"


# --- the push list, as the owner types it -------------------------------------------


MENU = {
    "menu-k": incentive.MenuFact("Karak", archived=False, mapped=True),
    "menu-s": incentive.MenuFact("Sulaimani", archived=False, mapped=True),
    "menu-c": incentive.MenuFact("Honey Cake", archived=False, mapped=False),
    "menu-h": incentive.MenuFact("Ramadan Harees", archived=True, mapped=True),
}
PUSH_BRANCHES = {A: "Al Quoz", B: "Deira"}
BOTH = {A: "100", B: "50"}


def _row(menu_item_id: str, rate, targets) -> incentive.TypedPushItem:
    return incentive.TypedPushItem(
        menu_item_id=menu_item_id,
        rate_per_portion=None if rate is None else Decimal(rate),
        targets=[
            incentive.TypedPortionTarget(
                branch_id=branch, portion_target=None if target is None else Decimal(target)
            )
            for branch, target in targets.items()
        ],
    )


def _refusal(items) -> str | None:
    return incentive.push_list_problem(MENU, PUSH_BRANCHES, items)


def test_a_finished_push_list_is_refused_for_nothing():
    assert _refusal([_row("menu-k", "0.50", BOTH), _row("menu-s", "0.25", BOTH)]) is None


def test_an_empty_list_is_a_decision_and_not_a_refusal():
    """A week the owner takes off the scheme still brings a card with the
    month's net sales on it (D5), so there is nothing to refuse."""
    assert _refusal([]) is None


@pytest.mark.parametrize(
    ("items", "expected"),
    [
        pytest.param(
            [_row("menu-x", "0.50", BOTH)],
            "a dish was sent that is not on this menu",
            id="a dish off another menu",
        ),
        pytest.param(
            [_row("menu-c", "0.50", BOTH)],
            "Honey Cake has no till name mapped to it, so it could only ever score zero; "
            "map a till name to it on the Sales screen first",
            id="no till name maps to it",
        ),
        pytest.param(
            [_row("menu-h", "0.50", BOTH)],
            "Ramadan Harees is archived from the menu and cannot be pushed",
            id="archived off the menu",
        ),
        pytest.param(
            [_row("menu-k", "0.50", BOTH), _row("menu-k", "0.60", BOTH)],
            "Karak is on the list twice: one row per dish",
            id="the same dish twice",
        ),
        pytest.param(
            [_row("menu-k", None, BOTH)],
            "Karak has no rate per portion: type what one portion above target earns",
            id="the rate box left empty",
        ),
        pytest.param(
            [_row("menu-k", "-0.50", BOTH)],
            "Karak: a rate per portion cannot be negative",
            id="a negative rate",
        ),
        pytest.param(
            [_row("menu-k", "0.505", BOTH)],
            "Karak: a rate per portion is kept to the fil, two decimals at most, like 0.25",
            id="a rate to a third decimal",
        ),
        pytest.param(
            [_row("menu-k", "0.50", {A: "100"})],
            "Karak has no portion target for Deira: every branch of the chain needs one",
            id="a branch left out",
        ),
        pytest.param(
            [_row("menu-k", "0.50", {A: "100", B: None})],
            "Karak has no portion target for Deira: every branch needs one",
            id="a target box left empty",
        ),
        pytest.param(
            [_row("menu-k", "0.50", {A: "100", B: "-1"})],
            "Karak: a portion target cannot be negative",
            id="a negative target",
        ),
        pytest.param(
            [_row("menu-k", "0.50", {A: "100", B: "50.0001"})],
            "Karak: a portion target is counted to three decimals at most, like 250",
            id="a target to a fourth decimal",
        ),
        pytest.param(
            [_row("menu-k", "0.50", {A: "100", B: "50", "br-z": "10"})],
            "Karak was given a target for a branch that is not in this chain",
            id="a branch outside the chain",
        ),
    ],
)
def test_a_push_list_that_would_pay_the_team_on_nothing_is_refused_by_name(items, expected):
    """Every refusal names the dish, and a target names the branch whose box
    it came from (D6, D7) - the screen shows a grid, so an owner told only
    that "a target is missing" would have to hunt for it."""
    assert _refusal(items) == expected


def test_a_branch_with_no_target_is_refused_rather_than_scored_against_zero():
    """`score_item` reads a branch with no target as a target of zero, which
    would pay the team for every portion it sold. The door is where that is
    caught, so the arithmetic never has to guess."""
    item = _item("k", "Karak", "0.50", {A: "100"})
    scored = incentive.score_item(item, Window(_day(SEPT, 7), _day(SEPT, 13)), B, [])
    assert scored.portion_target == Decimal("0.000")
    assert _refusal([_row("menu-k", "0.50", {A: "100"})]) is not None


# --- the words that are never said --------------------------------------------------


def test_no_composed_sentence_says_profit_commission_verified_or_food_cost():
    archived = _item("a", "Honey Cake", "1.00", {A: "10"}, archived=True)
    unmapped = _item("u", "Sulaimani", "0.25", {A: "50"}, mapped=False)
    karak = _item("k", "Karak", "0.50", {A: "100"})
    scheme = _scheme({1: (archived, unmapped, karak)}, cap="1000")
    days = _loaded(A, range(1, 31), net="5000.00")
    live = _statement(scheme, days=days, items=[_sold(A, "menu-k", 8, "115", no_qty=1)])
    final = _statement(
        scheme, days=days, items=[_sold(A, "menu-k", 8, "100")], approval=_approval(live.figures)
    )
    empty = _statement(scheme, days=[], items=[])
    said = [
        *incentive.sentences(live),
        *incentive.sentences(final),
        *incentive.sentences(empty),
        incentive.frozen_week_sentence(scheme.weeks[0].window, datetime.date(2026, 9, 9)),
        incentive.push_item_problem("Karak", archived=False, mapped=False),
        incentive.push_item_problem("Karak", archived=True, mapped=True),
        incentive.rate_problem("Karak", None),
        incentive.rate_problem("Karak", Decimal("-1")),
        incentive.rate_problem("Karak", Decimal("0.255")),
        incentive.portion_target_problem("Karak", "Deira", None),
        incentive.portion_target_problem("Karak", "Deira", Decimal("-1")),
        incentive.portion_target_problem("Karak", "Deira", Decimal("0.0001")),
        incentive.push_list_problem({}, {}, [_row("menu-x", "1.00", {})]),
        incentive.shares_problem(Decimal("1"), Decimal("1"), Decimal("1")),
        incentive.targets_problem(Decimal("-1"), Decimal("1"), None),
        incentive.approvable(empty.figures),
        incentive.approval_problem(empty, ""),
        incentive.REASON_REQUIRED,
        incentive.already_final_sentence(_approval(empty.figures)),
        incentive.kept_words(Decimal("1"), "AED"),
        incentive.previous_month_words(None, "AED"),
        incentive.PUSH_GUIDANCE_WORDS,
        incentive.NO_POOL_WORDS,
        incentive.BONUS,
    ]
    for sentence in said:
        assert sentence is not None
        for banned in BANNED_WORDS:
            assert banned not in sentence.lower(), f"{sentence!r} says {banned!r}"


# --- the screen's blocks ----------------------------------------------------------


def test_the_scheme_month_block_carries_the_weeks_grouped_and_frozen_by_the_day():
    karak = _item("k", "Karak", "0.50", {A: "100", B: "50"})
    cake = _item("c", "Honey Cake", "1.00", {A: "10"}, category=None, archived=True)
    scheme = _scheme({1: (karak, cake)})
    block = incentive.scheme_month_json(
        scheme,
        created_at=datetime.datetime(2026, 8, 30, 8, 0, tzinfo=datetime.UTC),
        today=datetime.date(2026, 9, 9),
        kept={"menu-k": Decimal("4.123")},
        statements=[],
        currency="AED",
    )
    assert block["month"] == "2026-09" and block["words"] == "September 2026"
    assert block["shares"] == {
        "manager_pct": "50.00",
        "supervisor_pct": "20.00",
        "sales_pct": "30.00",
    }
    assert block["targets"][0] == {
        "branch_id": A,
        "net_sales_target": "50000.00",
        "above_target_pct": "10.00",
        "cap": None,
    }
    weeks = block["weeks"]
    assert [w["words"] for w in weeks] == [
        "1-6 Sep",
        "7-13 Sep",
        "14-20 Sep",
        "21-27 Sep",
        "28-30 Sep",
    ]
    assert [w["frozen"] for w in weeks] == [True, True, False, False, False]
    assert weeks[1]["frozen_words"] == "the week of 7-13 Sep has started and is frozen"
    assert weeks[2]["frozen_words"] is None
    week = weeks[1]
    assert [c["category"] for c in week["categories"]] == ["Tea Corner", "Other"]
    (karak_json,) = week["categories"][0]["items"]
    assert karak_json["rate_per_portion"] == "0.50"
    assert karak_json["kept_per_plate"] == "4.123"
    assert karak_json["kept_words"] == "keeps AED 4.12 per plate"
    assert karak_json["hole"] is None
    assert karak_json["targets"] == [
        {"branch_id": A, "portion_target": "100.000"},
        {"branch_id": B, "portion_target": "50.000"},
    ]
    (cake_json,) = week["categories"][1]["items"]
    assert cake_json["kept_words"] == "not costed"
    assert cake_json["hole"] == "Honey Cake cannot be counted: it was archived from the menu"


def test_a_menu_item_and_a_branch_on_the_wire():
    item = incentive.menu_item_json(
        menu_item_id="m-1",
        name="Karak",
        category="Tea Corner",
        kept_per_plate=None,
        mapped=False,
        currency="AED",
    )
    assert item == {
        "id": "m-1",
        "name": "Karak",
        "category": "Tea Corner",
        "kept_per_plate": None,
        "kept_words": "not costed",
        "mapped": False,
    }
    branch = incentive.branch_json(
        branch_id=A,
        name="Al Quoz",
        timezone="Asia/Dubai",
        paused_at=None,
        previous_month_net_sales=Decimal("41200.404"),
        currency="AED",
    )
    assert branch["previous_month_net_sales"] == "41200.40"
    assert branch["previous_month_words"] == "AED 41,200 last month"
    assert branch["paused_at"] is None
