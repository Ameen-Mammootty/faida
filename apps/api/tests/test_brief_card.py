"""M10 WP-106: the picture card, drawn from the brief and nothing else
(Docs/M10_DECOMPOSITION.md §3 C15.4, §3.1 "Template A", §4 row 106, §7).

No database and no network: `brief.compose` is handed the committed mock
payloads - the real arithmetic of the shipped modules
(`apps/web/src/lib/mock/dashboard`) - and `brief_card.layout` is handed what
comes back. The plan `layout` returns is every drawn thing with the rectangle
it occupies, so the two questions a picture cannot answer for itself are
answered here: is every line of the brief on the card, and is any of it off
the edge.

The card is checked by reading its plan, never by looking at pixels. The one
thing pixels are asked is what only they can say: that the file decodes at
1080 by 1350 and that the same brief renders byte for byte the same twice, so
a stored card is the card that was sent.

The hand-built cases are the shapes the fixtures do not carry: a chain longer
than the card, a menu item and a branch named far past their column, a menu
with one item the read could not cost.
"""

import dataclasses
import io
import json
import re
from copy import deepcopy
from pathlib import Path

import pytest
from PIL import Image

from faida_api import brief, brief_card
from faida_api.brief_card import CANVAS_H, CANVAS_W, CARD_MAX_ROWS, MARGIN

MOCK = Path(__file__).resolve().parents[3] / "apps" / "web" / "src" / "lib" / "mock" / "dashboard"
FORBIDDEN = ("food cost", "net profit", "verified")


def _payload(name: str, scope: str = "") -> dict:
    return json.loads((MOCK / f"{name}.json").read_text())[scope]


def _brief(name: str = "full") -> brief.Brief:
    """One morning out of one fixture: the same payload serves as the month
    read and the 28-day read, because this file is about what is drawn, not
    about which read a figure came from (`test_brief.py` pins that)."""
    payload = _payload(name)
    return brief.compose(payload, payload)


def _flat(plan: brief_card.Layout) -> str:
    """Every string the card draws, in drawing order, joined the way the eye
    reads them: a sentence broken over two lines and a line drawn in two
    colours both come back whole, so a test can ask for the brief's own words
    without knowing where the card chose to break them."""
    return re.sub(r"\s+", " ", " ".join(plan.lines)).strip()


def _long_chain(branches: int = 12) -> brief.Brief:
    """The full fixture with its league grown to `branches`, each new branch
    with its own name and its own day, so the table has more rows than the
    card can draw."""
    month = deepcopy(_payload("full"))
    league = month["league"]
    on_day = month["latest_day"]["branches"]
    while len(league) < branches:
        index = len(league)
        row = deepcopy(league[0])
        row["branch_id"] = f"br-{index:02d}"
        row["branch_name"] = f"Muhaisnah {index}"
        row["net_sales"] = str(20000 + index)
        league.append(row)
        day = deepcopy(on_day[0])
        day["branch_id"] = row["branch_id"]
        day["net_sales"] = str(3000 + index)
        on_day.append(day)
    return brief.compose(month, _payload("full"))


# --- every line of the brief is on the card ---------------------------------


def test_the_card_draws_every_line_of_the_brief():
    """The card is the brief in a picture: the day, the four figures with the
    words that qualify them, every branch row, both lists, every spike and the
    footer."""
    morning = _brief()
    drawn = _flat(brief_card.layout(morning))

    wanted = [morning.day, morning.card_footer]
    for kpi in morning.kpis:
        wanted += [kpi.value, kpi.sub]
    for row in morning.rows:
        wanted += [row.name, row.latest_day_words, row.month_words, row.materials_share_words]
    for item in morning.earning_most + morning.earning_least:
        wanted += [item.name, item.money_words]
    for spike in morning.spikes:
        wanted += [spike.sentence, spike.money_clause]

    for text in wanted:
        assert text in drawn, f"{text!r} is not on the card"


def test_no_figure_is_drawn_twice():
    """A figure drawn twice on one card is a figure the reader has to
    reconcile. The words that qualify a figure are left out of this: the tile
    under the latest day says the same day the header's sentence does, and
    that is the same fact said once and pointed at twice."""
    morning = _brief()
    drawn = _flat(brief_card.layout(morning))

    once = [morning.day, morning.card_footer]
    once += [kpi.value for kpi in morning.kpis]
    once += [row.name for row in morning.rows]
    for item in morning.earning_most + morning.earning_least:
        once += [item.name, item.money_words]
    for spike in morning.spikes:
        once += [spike.sentence, spike.money_clause]

    for text in once:
        assert drawn.count(text) == 1, f"{text!r} is drawn {drawn.count(text)} times"


def test_the_card_says_what_the_lists_leave_out():
    morning = _brief()
    assert morning.uncosted == 2
    assert "2 items cannot be costed yet" in _flat(brief_card.layout(morning))


def test_one_item_left_out_is_said_in_the_singular():
    morning = dataclasses.replace(_brief(), uncosted=1)
    assert "1 item cannot be costed yet" in _flat(brief_card.layout(morning))


def test_a_menu_with_nothing_left_out_says_nothing_about_it():
    morning = dataclasses.replace(_brief(), uncosted=0)
    assert "cannot be costed" not in _flat(brief_card.layout(morning))


def test_the_rows_are_drawn_in_the_leagues_own_order():
    """Kept share lowest first, the order the dashboard ranks them in, so the
    card and the screen read the same way down the page."""
    morning = _brief()
    names = [row.name for row in morning.rows]
    drawn = [text.text for text in brief_card.layout(morning).texts if text.text in names]
    assert drawn == names


def test_a_branch_that_loaded_nothing_shows_a_hole_and_never_a_nought():
    """The partial fixture has a branch that stopped uploading: its three
    figures are `brief.HOLE`, and the card draws the hole rather than filling
    it with a number nobody reported."""
    morning = _brief("partial")
    empty = [row for row in morning.rows if row.latest_day is None and row.month is None]
    assert len(empty) == 1
    assert empty[0].materials_share_words == brief.HOLE
    holes = [text for text in brief_card.layout(morning).texts if text.text == brief.HOLE]
    assert len(holes) == 3
    assert len({text.y for text in holes}) == 1, "the three holes are one branch's row"


def test_a_read_that_costed_nothing_draws_the_withheld_words_and_no_item():
    """`nomenu` costs nothing at all: the two figures say so in the read's own
    words, and the lists carry the hole rather than an empty panel."""
    morning = _brief("nomenu")
    drawn = _flat(brief_card.layout(morning))
    assert morning.earning_most == () and morning.earning_least == ()
    assert drawn.count("not available") == 2
    assert f"{brief_card.TITLE_MOST} {brief.HOLE}" in drawn
    assert f"{brief_card.TITLE_LEAST} {brief.HOLE}" in drawn


def test_a_morning_with_no_rise_draws_the_reads_own_sentence():
    morning = _brief("quiet")
    assert morning.spikes == ()
    assert morning.no_spikes is not None
    assert morning.no_spikes in _flat(brief_card.layout(morning))


def test_the_card_never_says_food_cost_or_net_profit_or_verified():
    for name in ("full", "partial", "quiet", "nomenu"):
        drawn = _flat(brief_card.layout(_brief(name))).lower()
        for phrase in FORBIDDEN:
            assert phrase not in drawn, f"{name} draws {phrase!r}"


def test_a_money_value_below_nought_is_drawn_in_plum_and_keeps_its_sign():
    """Colour never carries the meaning alone: the sign is in the words, and
    the plum is beside it."""
    morning = _brief()
    losses = [item for item in morning.earning_least if item.money < 0]
    assert losses and losses[0].money_words.startswith("AED -")
    colours = {
        text.text.strip(): text.colour
        for text in brief_card.layout(morning).texts
        if text.text.strip().startswith("AED ")
    }
    assert colours[losses[0].money_words] == brief_card.PLUM
    kept = [item for item in morning.earning_most if item.money > 0][0]
    assert colours[kept.money_words] == brief_card.SLATE


# --- nothing is off the edge ------------------------------------------------


def _outside(plan: brief_card.Layout) -> list:
    return [
        item
        for item in plan.items
        if item.x < 0 or item.y < 0 or item.x + item.w > CANVAS_W or item.y + item.h > CANVAS_H
    ]


@pytest.mark.parametrize("name", ["full", "partial", "quiet", "nomenu"])
def test_every_drawn_thing_sits_inside_the_canvas(name):
    plan = brief_card.layout(_brief(name))
    assert plan.width == CANVAS_W and plan.height == CANVAS_H
    assert _outside(plan) == []


def test_every_line_of_text_stays_inside_the_margins():
    """A picture has no scrollbar: text that ran past the margin would simply
    be gone, so the plan keeps every run inside the content column."""
    for name in ("full", "partial", "quiet", "nomenu"):
        for text in brief_card.layout(_brief(name)).texts:
            assert text.x >= MARGIN, f"{name}: {text.text!r} starts at {text.x}"
            assert text.x + text.w <= CANVAS_W - MARGIN, f"{name}: {text.text!r} runs over"


def test_a_chain_longer_than_the_card_draws_what_fits_and_says_what_does_not():
    morning = _long_chain(12)
    assert len(morning.rows) == 12
    plan = brief_card.layout(morning)
    drawn = _flat(plan)
    names = [row.name for row in morning.rows]
    on_card = [text.text for text in plan.texts if text.text in names]
    assert on_card == names[:CARD_MAX_ROWS]
    assert "and 2 more on the dashboard" in drawn
    assert _outside(plan) == []


def test_a_chain_of_one_branch_draws_that_one_row():
    morning = _brief()
    one = dataclasses.replace(morning, rows=morning.rows[:1])
    plan = brief_card.layout(one)
    assert _flat(plan).count(one.rows[0].name) == 1
    assert "more on the dashboard" not in _flat(plan)
    assert _outside(plan) == []


def test_a_name_too_long_for_its_column_is_shortened_and_never_runs_over():
    """A branch or a menu item can be named anything. The name gives way, the
    money never does: a truncated dirham figure would be a wrong number."""
    morning = _brief()
    item = dataclasses.replace(
        morning.earning_most[0], name="Chicken Biryani Family Platter With Extra Raita And Salad"
    )
    row = dataclasses.replace(morning.rows[0], name="Al Quoz Industrial Area Three Cafeteria")
    long_named = dataclasses.replace(
        morning,
        earning_most=(item,) + morning.earning_most[1:],
        rows=(row,) + morning.rows[1:],
    )
    plan = brief_card.layout(long_named)
    drawn = _flat(plan)

    assert item.name not in drawn and row.name not in drawn
    assert item.name[:20] + "…" not in drawn  # shortened at the width, not at a guess
    assert brief_card.ELLIPSIS in drawn
    assert drawn.count(item.money_words) == 1
    assert drawn.count(morning.rows[0].latest_day_words) == 1
    assert _outside(plan) == []

    shortened = [text for text in plan.texts if text.text.endswith(brief_card.ELLIPSIS)]
    assert len(shortened) == 2
    figure = next(text for text in plan.texts if text.text == morning.rows[0].latest_day_words)
    name = next(text for text in shortened if text.y == figure.y)
    assert name.x + name.w < figure.x, "the branch name reaches into the figures' column"


def test_a_day_sentence_too_long_for_one_line_wraps_and_stays_whole():
    """The stale morning's header carries the read's sentence and the brief's
    own clause after it - too long for one line, and not a word of it may be
    lost, because it is the sentence that says the figures are old."""
    morning = _brief("partial")
    assert "estimated" in morning.day
    plan = brief_card.layout(morning)
    assert _flat(plan).count(morning.day) == 1
    assert brief_card.ELLIPSIS not in morning.day
    assert _outside(plan) == []


# --- the picture ------------------------------------------------------------


def test_the_png_decodes_at_the_size_whatsapp_shows_whole():
    image = Image.open(io.BytesIO(brief_card.render_card(_brief())))
    assert image.format == "PNG"
    assert image.size == (CANVAS_W, CANVAS_H)
    assert image.mode == "RGB"


def test_the_same_brief_renders_the_same_bytes():
    """A card is stored beside the message it was sent with, so the same
    morning must render to the same file: nothing dated and nothing ordered by
    chance goes into the PNG."""
    once = brief_card.render_card(_brief())
    twice = brief_card.render_card(_brief())
    assert once == twice


@pytest.mark.parametrize("name", ["full", "partial", "quiet", "nomenu"])
def test_every_fixture_renders(name):
    image = Image.open(io.BytesIO(brief_card.render_card(_brief(name))))
    assert image.size == (CANVAS_W, CANVAS_H)


def test_a_long_chain_renders():
    image = Image.open(io.BytesIO(brief_card.render_card(_long_chain(12))))
    assert image.size == (CANVAS_W, CANVAS_H)


def test_a_quiet_brief_has_nothing_to_draw():
    """Nothing is sent on a morning with nothing loaded (C15.7), so there is
    nothing to draw either: a blank card sent by mistake would be worse than
    no card."""
    payload = _payload("empty")
    quiet = brief.compose(payload, payload)
    assert quiet.quiet
    with pytest.raises(ValueError, match="quiet"):
        brief_card.layout(quiet)
    with pytest.raises(ValueError, match="quiet"):
        brief_card.render_card(quiet)
