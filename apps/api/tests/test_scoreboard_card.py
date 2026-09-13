"""M13.7: the scoreboard drawn, from the composed card and nothing else
(plan.md §8 M13 D13, D15; issue #13; the final variant for issue #15).

The brief card's shape (`test_brief_card.py`): the card is checked by
reading its plan, never by looking at pixels. Every line of the composed
card is on it, nothing is off the edge or outside the margins, a long list
draws what fits and says what it leaves out, a hole is a named gap with no
bar under it, a reached target is said in words before it is coloured, a
name too long for its row is shortened and the count never is. The one
thing pixels are asked is what only they can say: that the file decodes at
1080 by 1350 and that the same card renders byte for byte the same twice.
"""

import dataclasses
import io
import json
import re
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest
from PIL import Image

from faida_api import incentive, scoreboard, scoreboard_card
from faida_api.incentive import BANNED_WORDS
from faida_api.scoreboard_card import (
    CANVAS_H,
    CANVAS_W,
    CARD_MAX_ROWS,
    ELLIPSIS,
    GREEN,
    KARAK_GOLD,
    MARGIN,
    Rule,
)

from .test_scoreboard import AL_QUOZ, DEIRA, KARAMA, MOCK, TODAY, _daily, _final

CASES = {
    "daily": lambda: _daily(AL_QUOZ),
    "capped": lambda: _daily(KARAMA),
    "stale": lambda: _daily(DEIRA),
    "hole": lambda: _daily(DEIRA, TODAY.replace(day=10)),
    "empty": lambda: _daily(AL_QUOZ, TODAY.replace(day=29)),
    "final": lambda: _final(AL_QUOZ),
    "final-differs": lambda: _final(KARAMA),
}


def _flat(plan: scoreboard_card.Layout) -> str:
    """Every string the card draws, in drawing order, joined the way the eye
    reads them, so a sentence the card broke over two lines comes back
    whole."""
    return re.sub(r"\s+", " ", " ".join(plan.lines)).strip()


def _outside(plan: scoreboard_card.Layout) -> list:
    return [
        item
        for item in plan.items
        if item.x < 0 or item.y < 0 or item.x + item.w > CANVAS_W or item.y + item.h > CANVAS_H
    ]


def _bars(plan: scoreboard_card.Layout) -> list[Rule]:
    """The filled bars under the rows: inside the panel, so the header's
    Karak Gold rule at the margin is not one of them."""
    return [
        item
        for item in plan.items
        if isinstance(item, Rule) and item.colour in (GREEN, KARAK_GOLD) and item.x > MARGIN
    ]


def _long_list(items: int = 14) -> scoreboard.Scoreboard:
    """The full fixture with the week in view grown to `items` push items,
    each its own dish with its own count, so the list is longer than the
    card can draw."""
    payload = json.loads((MOCK / "full.json").read_text())
    data = deepcopy(
        next(s for s in payload["scheme_month"]["statements"] if s["branch_id"] == AL_QUOZ)
    )
    week = next(w for w in data["figures"]["weeks"] if w["start"] <= TODAY.isoformat() <= w["end"])
    while len(week["items"]) < items:
        index = len(week["items"])
        item = deepcopy(week["items"][0])
        item["push_item_id"] = f"pi-long-{index}"
        item["menu_item_id"] = f"menu-long-{index}"
        item["name"] = f"Dish {index}"
        item["portions"] = f"{index}.000"
        item["words"] = f"{index} of 1,000 portions"
        week["items"].append(item)
    statement = incentive.statement_from_json(data)
    return scoreboard.compose(statement, branch_name="Al Quoz", today=TODAY)


# --- every line of the card is on the picture -------------------------------


@pytest.mark.parametrize("name", list(CASES))
def test_the_card_draws_every_line_of_the_composed_card(name):
    card = CASES[name]()
    drawn = _flat(scoreboard_card.layout(card))
    wanted = [card.freshness, card.title, card.subtitle, card.list_title, card.footer]
    for week in card.weeks:
        wanted += [text for text in (week.empty_words,) if text]
        for item in week.items:
            wanted += [item.name, item.words]
            wanted += [text for text in (item.note,) if text]
    for line in card.figures:
        wanted += [line.label, line.words]
    wanted += list(card.notes)
    for text in wanted:
        assert text in drawn, f"{name}: {text!r} is not on the card"


def test_no_figure_is_drawn_twice():
    card = _daily(AL_QUOZ)
    drawn = _flat(scoreboard_card.layout(card))
    once = [card.freshness, card.title, card.subtitle, card.list_title, card.footer]
    once += [item.words for item in card.weeks[0].items]
    once += [line.words for line in card.figures]
    for text in once:
        assert drawn.count(text) == 1, f"{text!r} is drawn {drawn.count(text)} times"


def test_a_hole_is_drawn_once_as_its_sentence_with_no_bar_under_it():
    """Honey Cake cannot be counted: the row is the name and the sentence,
    and the bar that would read as a team that sold none is not there (D7).
    Two bars for the two items that count, none for the hole."""
    card = CASES["hole"]()
    plan = scoreboard_card.layout(card)
    drawn = _flat(plan)
    cake = next(item for item in card.weeks[0].items if item.hole)

    assert drawn.count(cake.hole) == 1
    assert drawn.count("Honey Cake") == 2  # the name, and the name inside its sentence
    assert len(_bars(plan)) == len([item for item in card.weeks[0].items if not item.hole]) == 2
    assert "of 10 portions" not in drawn  # Deira's cake target, never scored as nought


def test_a_week_left_empty_draws_the_statements_note_and_the_figures_alone():
    card = CASES["empty"]()
    plan = scoreboard_card.layout(card)
    drawn = _flat(plan)
    assert "28-30 Sep: no push list" in drawn
    assert _bars(plan) == []
    assert "AED 36,750 of AED 60,000" in drawn
    assert "AED 137" in drawn


def test_a_reached_target_is_said_in_words_and_only_then_coloured_green():
    """756 of 700 portions: the words carry the fact, and the same words
    are drawn in Confirmed Green; a count short of target stays in ink."""
    card = _final(KARAMA)
    plan = scoreboard_card.layout(card)
    colours = {text.text: text.colour for text in plan.texts}
    assert colours["756 of 700 portions"] == GREEN
    assert colours["216 of 700 portions"] != GREEN


def test_the_daily_bar_fills_to_the_share_and_turns_green_at_target():
    card = _daily(AL_QUOZ)
    plan = scoreboard_card.layout(card)
    bars = _bars(plan)
    assert len(bars) == len(card.weeks[0].items) == 5
    karak = bars[0]
    track = next(
        item
        for item in plan.items
        if isinstance(item, Rule) and item.y == karak.y and item.w > karak.w
    )
    assert karak.colour == KARAK_GOLD
    assert Decimal(karak.w) / Decimal(track.w) == pytest.approx(
        Decimal("0.34"), abs=Decimal("0.002")
    )

    reached = dataclasses.replace(
        card.weeks[0].items[0], words="1,200 of 1,000 portions", share=Decimal(1), reached=True
    )
    green = dataclasses.replace(
        card,
        weeks=(dataclasses.replace(card.weeks[0], items=(reached,) + card.weeks[0].items[1:]),),
    )
    first = _bars(scoreboard_card.layout(green))[0]
    assert first.colour == GREEN and first.w == track.w


def test_the_final_card_draws_the_split_under_the_pool_and_no_bars():
    card = _final(KARAMA)
    plan = scoreboard_card.layout(card)
    drawn = _flat(plan)
    assert _bars(plan) == []
    assert "Manager share, 50% AED 315.00" in drawn
    assert "Sales team share, 30% AED 189.00" in drawn
    assert incentive.TILL_NOTE in drawn


def test_the_card_never_says_a_banned_word():
    for name, make in CASES.items():
        drawn = _flat(scoreboard_card.layout(make())).lower()
        for word in BANNED_WORDS:
            assert word not in drawn, f"{name}: {word!r} on the card"


# --- nothing is off the edge ------------------------------------------------


@pytest.mark.parametrize("name", list(CASES))
def test_every_drawn_thing_sits_inside_the_canvas(name):
    plan = scoreboard_card.layout(CASES[name]())
    assert plan.width == CANVAS_W and plan.height == CANVAS_H
    assert _outside(plan) == []


@pytest.mark.parametrize("name", list(CASES))
def test_every_line_of_text_stays_inside_the_margins(name):
    for text in scoreboard_card.layout(CASES[name]()).texts:
        assert text.x >= MARGIN, f"{name}: {text.text!r} starts at {text.x}"
        assert text.x + text.w <= CANVAS_W - MARGIN, f"{name}: {text.text!r} runs over"


def test_a_list_longer_than_the_card_draws_what_fits_and_says_what_it_leaves_out():
    card = _long_list(14)
    assert len(card.weeks[0].items) == 14
    plan = scoreboard_card.layout(card)
    drawn = _flat(plan)
    names = [item.name for item in card.weeks[0].items]
    on_card = [text.text for text in plan.texts if text.text in names]
    assert on_card == names[:CARD_MAX_ROWS]
    assert "and 4 more on the list" in drawn
    assert _outside(plan) == []


def test_a_list_that_fits_says_nothing_about_more():
    assert "more on the list" not in _flat(scoreboard_card.layout(_daily(AL_QUOZ)))


def _grown(card: scoreboard.Scoreboard, per_week: int) -> scoreboard.Scoreboard:
    """The final card with `per_week` items on every week's list, each row
    its own name, grown from the week's first item."""
    weeks = tuple(
        dataclasses.replace(
            week,
            items=tuple(
                dataclasses.replace(week.items[0], name=f"{week.items[0].name} {index}")
                for index in range(per_week)
            ),
        )
        for week in card.weeks
    )
    return dataclasses.replace(card, weeks=weeks)


def test_a_final_month_of_three_a_week_draws_every_row_and_one_more_is_said():
    """Six weeks of three items: eighteen rows, the final card's cap, all on
    the card at a smaller scale; a nineteenth is said, not dropped."""
    full = _grown(_final(AL_QUOZ), 3)
    assert sum(len(week.items) for week in full.weeks) == 18
    plan = scoreboard_card.layout(full)
    assert _outside(plan) == []
    assert "more on the list" not in _flat(plan)
    assert _flat(plan).count("Karak Tea (Cup) 2") == 6

    last = full.weeks[-1]
    extra = dataclasses.replace(
        last, items=last.items + (dataclasses.replace(last.items[0], name="One more"),)
    )
    over = dataclasses.replace(full, weeks=full.weeks[:-1] + (extra,))
    drawn = _flat(scoreboard_card.layout(over))
    assert "and 1 more on the list" in drawn
    assert "One more" not in drawn


def test_a_week_whose_rows_all_fell_past_the_cap_is_not_headed_over_nothing():
    over = _grown(_final(AL_QUOZ), 4)
    assert sum(len(week.items) for week in over.weeks) == 24
    plan = scoreboard_card.layout(over)
    drawn = _flat(plan)
    assert "and 6 more on the list" in drawn
    assert "31 Aug" not in drawn.replace("Sales loaded to Mon 31 Aug", "")
    assert _outside(plan) == []


def test_a_name_too_long_for_its_row_is_shortened_and_the_count_never_is():
    card = _daily(AL_QUOZ)
    long_named = dataclasses.replace(
        card.weeks[0].items[0],
        name="Chicken Biryani Family Platter With Extra Raita, Salad, Pickles And A Cold Drink",
    )
    week = dataclasses.replace(card.weeks[0], items=(long_named,) + card.weeks[0].items[1:])
    plan = scoreboard_card.layout(dataclasses.replace(card, weeks=(week,)))
    drawn = _flat(plan)

    assert long_named.name not in drawn
    assert ELLIPSIS in drawn
    assert drawn.count(long_named.words) == 1
    assert _outside(plan) == []
    name = next(text for text in plan.texts if text.text.endswith(ELLIPSIS))
    words = next(text for text in plan.texts if text.text == long_named.words)
    assert name.y == words.y
    assert name.x + name.w < words.x, "the name reaches into the count"


def test_a_hole_sentence_too_long_for_one_line_wraps_and_stays_whole():
    card = CASES["hole"]()
    cake = next(item for item in card.weeks[0].items if item.hole)
    name = "Honey Cake With Cream And Pistachio Topping"
    sentence = f"{name} cannot be counted: no till name is mapped to it"
    long_hole = dataclasses.replace(cake, name=name, hole=sentence, words=sentence)
    items = tuple(long_hole if item is cake else item for item in card.weeks[0].items)
    plan = scoreboard_card.layout(
        dataclasses.replace(card, weeks=(dataclasses.replace(card.weeks[0], items=items),))
    )
    assert _flat(plan).count(long_hole.hole) == 1
    assert ELLIPSIS not in _flat(plan)
    assert _outside(plan) == []


# --- the picture ------------------------------------------------------------


def test_the_png_decodes_at_the_size_whatsapp_shows_whole():
    image = Image.open(io.BytesIO(scoreboard_card.render_card(_daily(AL_QUOZ))))
    assert image.format == "PNG"
    assert image.size == (CANVAS_W, CANVAS_H)
    assert image.mode == "RGB"


@pytest.mark.parametrize("name", ["daily", "final-differs"])
def test_the_same_card_renders_the_same_bytes(name):
    once = scoreboard_card.render_card(CASES[name]())
    twice = scoreboard_card.render_card(CASES[name]())
    assert once == twice


@pytest.mark.parametrize("name", list(CASES))
def test_every_case_renders(name):
    image = Image.open(io.BytesIO(scoreboard_card.render_card(CASES[name]())))
    assert image.size == (CANVAS_W, CANVAS_H)


def test_a_long_list_renders():
    image = Image.open(io.BytesIO(scoreboard_card.render_card(_long_list(14))))
    assert image.size == (CANVAS_W, CANVAS_H)


def test_the_fixtures_this_file_reads_are_the_mocks_own():
    """The cards here are composed from the mock's fixtures, which are the
    shipped module's own arithmetic; a fixture that stopped carrying a
    provisional September and a final August would silence half this file."""
    assert (MOCK / "full.json").exists() and (MOCK / "final.json").exists()
    assert Path(__file__).with_name("test_scoreboard.py").exists()
