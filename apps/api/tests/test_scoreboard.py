"""M13.7: the scoreboard composed from a statement and nothing else (plan.md
§8 M13 D13 to D16; issue #13).

No database and no clock: `scoreboard.compose` is handed statements read
back off the incentive mock's fixtures - the real arithmetic of the shipped
module (`apps/web/src/lib/mock/incentive`) - through `statement_from_json`,
which is what that function was built for. What is proven is that every
word on the card is the statement's own, that the first line names the
newest loaded day and ages it the brief's way, that a hole is named and
never a nought, that the final card carries the split summing to the pool,
that a card is refused where the statement is not what the card says it
is, and that no sentence carries a banned word.
"""

import datetime
import json
from decimal import Decimal
from pathlib import Path

import pytest

from faida_api import incentive, scoreboard
from faida_api.incentive import (
    BANNED_WORDS,
    BranchTargets,
    SchemeMonth,
    Shares,
    statement_from_json,
)

MOCK = Path(__file__).resolve().parents[3] / "apps" / "web" / "src" / "lib" / "mock" / "incentive"

#: The mock's own day: September under way, the week of 14-20 Sep in view.
TODAY = datetime.date(2026, 9, 16)
AL_QUOZ, KARAMA, DEIRA = "br-01", "br-02", "br-03"


def _statement(name: str, branch_id: str) -> tuple[incentive.Statement, str]:
    payload = json.loads((MOCK / f"{name}.json").read_text())
    data = next(s for s in payload["scheme_month"]["statements"] if s["branch_id"] == branch_id)
    return statement_from_json(data), data["branch_name"]


def _daily(branch_id: str = AL_QUOZ, today: datetime.date = TODAY) -> scoreboard.Scoreboard:
    statement, name = _statement("full", branch_id)
    return scoreboard.compose(statement, branch_name=name, today=today)


def _final(branch_id: str = KARAMA) -> scoreboard.Scoreboard:
    statement, name = _statement("final", branch_id)
    return scoreboard.compose(
        statement, branch_name=name, today=datetime.date(2026, 9, 3), variant=scoreboard.FINAL
    )


def _week(statement: incentive.Statement, day: datetime.date) -> incentive.WeekScore:
    return next(w for w in statement.figures.weeks if w.window.start <= day <= w.window.end)


# --- the daily card is the statement's own words ----------------------------


def test_the_daily_card_carries_this_weeks_list_in_the_statements_words():
    statement, _ = _statement("full", AL_QUOZ)
    card = _daily()
    week = _week(statement, TODAY)

    assert card.variant == scoreboard.DAILY
    assert card.list_title == "This week's push list, 14-20 Sep"
    assert len(card.weeks) == 1
    assert [item.name for item in card.weeks[0].items] == [item.name for item in week.items]
    assert [item.words for item in card.weeks[0].items] == [item.words for item in week.items]
    assert card.weeks[0].items[0].words == "340 of 1,000 portions"
    assert card.weeks[0].empty_words is None


def test_the_figures_are_the_statements_net_words_and_pool_words_marked_so_far():
    statement, _ = _statement("full", AL_QUOZ)
    card = _daily()

    assert [line.label for line in card.figures] == [
        "Net sales, September so far",
        "Bonus pool so far",
    ]
    assert card.figures[0].words == statement.figures.net_words == "AED 36,750 of AED 60,000"
    assert card.figures[1].words == statement.figures.pool_words == "AED 137"


def test_the_title_names_the_branch_the_owners_way_and_the_statements_status():
    card = _daily()
    assert card.title == "Al Quoz scoreboard"
    assert card.subtitle == "September 2026, provisional, 15 of 30 days loaded"
    assert card.headline == "Al Quoz scoreboard, Wed 16 Sep"


def test_a_branch_named_branch_is_shortened_in_the_headline_and_kept_on_the_card():
    statement, _ = _statement("full", AL_QUOZ)
    card = scoreboard.compose(statement, branch_name="Al Quoz Branch", today=TODAY)
    assert card.headline.startswith("Al Quoz scoreboard")
    assert card.branch_name == "Al Quoz Branch"


# --- the first line ---------------------------------------------------------


def test_the_first_line_names_the_newest_loaded_day_and_says_yesterday_when_it_is():
    card = _daily(AL_QUOZ)
    assert card.freshness == "Sales loaded to Tue 15 Sep, yesterday."
    assert card.parameters == (card.headline, card.freshness)


def test_a_branch_loaded_days_ago_is_aged_and_never_told_yesterday():
    """Deira loaded to the 10th and the card is drawn on the 16th: the line
    says six days, and "yesterday" is not on the card anywhere (D16)."""
    card = _daily(DEIRA)
    assert card.freshness == "Sales loaded to Thu 10 Sep, 6 days ago."
    assert not any("yesterday" in text for text in scoreboard.sentences(card))


def test_a_branch_with_nothing_loaded_says_so_and_has_no_pool():
    scheme = SchemeMonth(
        scheme_month_id="sm-1",
        month=datetime.date(2026, 9, 1),
        shares=Shares(Decimal("50"), Decimal("20"), Decimal("30")),
        targets={"br-x": BranchTargets("br-x", Decimal("1000"), Decimal("10"), None)},
        weeks=tuple(
            incentive.PushWeek(f"pw-{i}", window, ())
            for i, window in enumerate(incentive.push_weeks(datetime.date(2026, 9, 1)))
        ),
    )
    statement = incentive.compose_statement(
        scheme, "br-x", days=(), items=(), newest_loaded=None, approval=None, currency="AED"
    )
    card = scoreboard.compose(statement, branch_name="Rolla Branch", today=TODAY)

    assert card.freshness == "No sales loaded yet for September 2026."
    assert card.figures[1].words == incentive.NO_POOL_WORDS
    assert "AED 0" not in card.figures[1].words
    assert not any("yesterday" in text for text in scoreboard.sentences(card))


# --- holes, empty weeks, the cap ---------------------------------------------


def test_a_hole_is_named_has_no_share_and_is_never_a_nought():
    """Honey Cake lost its till name after the 7-13 Sep list was set: the
    card carries the statement's own sentence for it and no bar (D7)."""
    card = _daily(DEIRA, datetime.date(2026, 9, 10))
    cake = next(item for item in card.weeks[0].items if item.name == "Honey Cake")

    assert cake.hole == "Honey Cake cannot be counted: no till name is mapped to it"
    assert cake.words == cake.hole
    assert cake.share is None
    assert cake.reached is False
    assert "0 of" not in cake.words


def test_a_week_the_owner_left_empty_carries_the_statements_note_and_no_items():
    card = _daily(AL_QUOZ, datetime.date(2026, 9, 29))
    assert card.list_title == "This week's push list, 28-30 Sep"
    assert card.weeks[0].items == ()
    assert card.weeks[0].empty_words == "28-30 Sep: no push list"
    assert card.figures[0].words == "AED 36,750 of AED 60,000"


def test_a_capped_pool_carries_the_statements_cap_note():
    card = _daily(KARAMA)
    assert card.figures[1].words == "AED 1,500"
    assert card.notes == ("capped at AED 1,500; AED 2,018 earned before the cap",)


def test_an_uncapped_pool_carries_no_note():
    assert _daily(AL_QUOZ).notes == ()


def test_the_share_of_target_is_clipped_to_the_bar():
    card = _daily(AL_QUOZ)
    karak = card.weeks[0].items[0]
    assert karak.share == Decimal("0.34")
    assert karak.reached is False
    final = _final(KARAMA)
    reached = next(item for item in final.weeks[1].items if item.name == "Karak Tea (Cup)")
    assert reached.words == "756 of 700 portions"
    assert reached.share == Decimal(1)
    assert reached.reached is True


# --- the final card ---------------------------------------------------------


def test_the_final_card_carries_every_week_and_the_split_summing_to_the_pool():
    statement, _ = _statement("final", KARAMA)
    card = _final(KARAMA)

    assert card.variant == scoreboard.FINAL
    assert card.headline == "Karama: August 2026 bonus, final"
    assert card.subtitle == "August 2026, final; the till now says otherwise"
    assert card.list_title == "The month's push lists"
    assert [week.title for week in card.weeks] == [
        "1-2 Aug",
        "3-9 Aug",
        "10-16 Aug",
        "17-23 Aug",
        "24-30 Aug",
        "31 Aug",
    ]
    assert [line.label for line in card.figures] == [
        "Net sales, August 2026",
        "Bonus pool",
        "Manager share, 50%",
        "Supervisor share, 20%",
        "Sales team share, 30%",
    ]
    assert card.figures[1].words == "AED 630"
    amounts = [Decimal(line.words.removeprefix("AED ")) for line in card.figures[2:]]
    assert amounts == [Decimal("315.00"), Decimal("126.00"), Decimal("189.00")]
    assert sum(amounts) == statement.figures.pool


def test_the_final_card_carries_the_till_note_only_when_the_till_says_otherwise():
    assert _final(KARAMA).notes == (incentive.TILL_NOTE,)
    assert _final(AL_QUOZ).notes == ()
    assert _final(AL_QUOZ).subtitle == "August 2026, final"


def test_the_final_card_is_the_approved_figures_and_not_the_recomputed_ones():
    """Karama's 20 Aug was re-uploaded after approval. The card is what was
    paid; the till's new figure is the screen's to show beside it (D12)."""
    statement, _ = _statement("final", KARAMA)
    assert statement.recomputed is not None
    card = _final(KARAMA)
    assert card.figures[1].words == statement.figures.pool_words
    assert card.figures[1].words != statement.recomputed.pool_words


# --- what is refused --------------------------------------------------------


def test_a_daily_card_is_refused_on_a_final_statement():
    statement, name = _statement("final", AL_QUOZ)
    with pytest.raises(ValueError, match="closed"):
        scoreboard.compose(statement, branch_name=name, today=datetime.date(2026, 8, 20))


def test_a_final_card_is_refused_on_a_provisional_statement():
    statement, name = _statement("full", AL_QUOZ)
    with pytest.raises(ValueError, match="approved"):
        scoreboard.compose(statement, branch_name=name, today=TODAY, variant=scoreboard.FINAL)


def test_a_day_outside_the_month_has_no_week_to_draw():
    statement, name = _statement("full", AL_QUOZ)
    with pytest.raises(ValueError, match="2026-10-01"):
        scoreboard.compose(statement, branch_name=name, today=datetime.date(2026, 10, 1))


def test_an_unknown_variant_is_refused():
    statement, name = _statement("full", AL_QUOZ)
    with pytest.raises(ValueError, match="variant"):
        scoreboard.compose(statement, branch_name=name, today=TODAY, variant="weekly")


# --- the words --------------------------------------------------------------


@pytest.mark.parametrize(
    "card",
    [
        _daily(AL_QUOZ),
        _daily(KARAMA),
        _daily(DEIRA),
        _daily(DEIRA, datetime.date(2026, 9, 10)),
        _daily(AL_QUOZ, datetime.date(2026, 9, 29)),
        _final(AL_QUOZ),
        _final(KARAMA),
        _final(DEIRA),
    ],
    ids=["quoz", "karama", "deira", "hole", "empty", "final-quoz", "final-karama", "final-deira"],
)
def test_no_composed_sentence_carries_a_banned_word(card):
    for text in scoreboard.sentences(card):
        for word in BANNED_WORDS:
            assert word not in text.lower(), f"{word!r} in {text!r}"


def test_bonus_is_the_word_on_the_card():
    assert "Bonus" in _daily().figures[1].label
    assert incentive.BONUS in _final().headline


def test_the_two_slots_are_one_line_each_and_within_metas_limit():
    for card in (_daily(), _final()):
        assert len(card.parameters) == scoreboard.PARAMETER_COUNT
        for text in card.parameters:
            assert "\n" not in text
            assert len(text) <= scoreboard.PARAMETER_MAX_CHARS


def test_the_printed_card_is_every_line_in_order():
    printed = scoreboard.render(_daily())
    assert printed.splitlines()[0] == "Al Quoz scoreboard, Wed 16 Sep"
    assert printed.splitlines()[1] == "Sales loaded to Tue 15 Sep, yesterday."
    assert "  Karak Tea (Cup): 340 of 1,000 portions" in printed
    assert "Bonus pool so far: AED 137" in printed
    assert printed.splitlines()[-1] == scoreboard.CARD_FOOTER


def test_the_card_is_stored_under_the_tenant_the_day_and_the_branch():
    day = datetime.date(2026, 9, 16)
    assert scoreboard.card_path("t-1", day, "br-01") == "t-1/scoreboards/2026-09-16/br-01.png"
    assert (
        scoreboard.card_path("t-1", day, "br-01", variant=scoreboard.FINAL)
        == "t-1/scoreboards/2026-09-16/br-01-final.png"
    )
