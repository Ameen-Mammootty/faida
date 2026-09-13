"""M13.7: the scoreboard drawn - one branch's card as a picture, the template's
image header (plan.md §8 M13 D13, D15; issue #13; issue #15 for the final
variant).

A pure layout over a composed `Scoreboard`, on the card sheet the brief is
drawn on (`card.py`, M13 WP-130): 1080 by 1350, the tallest ratio WhatsApp
shows whole in the bubble, the brand's palette and fonts, the scale ladder
that finds the largest type that fits, and the renderer that walks the plan
with Pillow once. **This module invents no facts and re-words no sentence**:
every string it draws is a field of the `Scoreboard` that `scoreboard.py`
composed, which in turn took every figure off the statement. What is decided
here is only where each thing sits and how big.

Two layers, because a picture is untestable and a plan is not:

1. `layout(card) -> Layout` is a pure function: every drawn thing - a `Box`,
   a `Rule` or a `Text` - with the rectangle it occupies, in drawing order.
   The tests read it: every line of the card is on it, nothing is off the
   edge, a long list draws what fits and says how many more, a hole is a
   named gap with no bar under it.
2. `render_card(card) -> bytes` walks that plan with Pillow and hands back
   the PNG, byte-identical for the same `Scoreboard`, so a stored card is
   the card that was sent.

The push list is the card's body: one row per item with the statement's own
words on the right ("340 of 1,000 portions") and a bar under it filled to the
share of target reached - Karak Gold on the way, Confirmed Green once the
words say the target is met, so colour never carries the meaning alone. A
hole draws its sentence where the bar would be and no bar, because a bar at
nought would read as a team that sold none (D7). Past `CARD_MAX_ROWS` items
the list says how many more are on it: a card that silently stopped would be
a list of twelve reading as a list of ten.

Under the list, the figures as a two-row panel - net sales against target,
the pool marked "so far" - and on the final card the split by role under
them; then the notes that qualify them (the cap, the till note) and the one
footer sentence.
"""

from decimal import ROUND_HALF_UP, Decimal

from .card import (
    BORDER,
    BOTTOM_MARGIN,
    BRAND,
    CANVAS_H,
    CANVAS_W,
    CONTENT_W,
    DATE_PALM,
    ELLIPSIS,
    GREEN,
    INK,
    KARAK_GOLD,
    MARGIN,
    MEDIUM,
    MIST,
    RADIUS,
    REGULAR,
    SLATE,
    WHITE,
    Box,
    Layout,
    Rule,
    Scale,
    Sheet,
    Text,
    fit,
    header,
    render,
    shorten,
    text_height,
    text_width,
    wrap,
)
from .scoreboard import DAILY, ItemLine, Scoreboard, _more_words

__all__ = [
    "CANVAS_H",
    "CANVAS_W",
    "CARD_MAX_ROWS",
    "FINAL_MAX_ROWS",
    "ELLIPSIS",
    "GREEN",
    "KARAK_GOLD",
    "MARGIN",
    "Box",
    "Layout",
    "Rule",
    "Text",
    "layout",
    "render_card",
]

#: The most item rows the list draws, over every week block on the card:
#: the daily card's rows carry a bar each; the final card's are one line
#: each, and eighteen is three a week over a six-week month - past that the
#: card says how many more and the owner's screen carries the whole month.
CARD_MAX_ROWS = 10
FINAL_MAX_ROWS = 18

# --- the measures, at scale 1.0 -------------------------------------------------

HEADER_TOP = 44
BRAND_SIZE = 40
DAY_SIZE = 21
DAY_LINE = 26
DAY_MAX_LINES = 2
RULE_GAP = 16
RULE_H = 3

TITLE_SIZE = 42
SUBTITLE_SIZE = 21
SUBTITLE_GAP = 8
SUBTITLE_MAX_LINES = 2
SUBTITLE_LINE = 26

PANEL_PAD = 24
PANEL_TITLE_SIZE = 25
PANEL_TITLE_GAP = 16
WEEK_TITLE_SIZE = 19
WEEK_TITLE_GAP = 10
WEEK_GAP = 14

ROW_NAME_SIZE = 24
ROW_WORDS_SIZE = 24
ROW_COL_GAP = 24
ROW_BAR_GAP = 11
ROW_BAR_H = 10
ROW_GAP = 24
ROW_COMPACT_GAP = 12
ROW_NOTE_SIZE = 19
ROW_NOTE_LINE = 25
ROW_NOTE_GAP = 8
ROW_NOTE_MAX_LINES = 2
EMPTY_SIZE = 21
MORE_SIZE = 19
MORE_GAP = 6

FIGURE_ROW_H = 70
FIGURE_LABEL_SIZE = 22
FIGURE_VALUE_SIZE = 30
FIGURE_SPLIT_SIZE = 21
FIGURE_PAD_X = 24

NOTE_SIZE = 19
NOTE_LINE = 25
NOTE_MAX_LINES = 2
NOTE_GAP = 6

FOOTER_SIZE = 20
FOOTER_LINE = 26
FOOTER_MAX_LINES = 2


# --- the blocks -----------------------------------------------------------------


def _header(sheet: Sheet, card: Scoreboard) -> int:
    """The wordmark and the freshness line - the first line, naming the newest
    loaded day and its age (D16) - with the Karak Gold rule under them."""
    return header(
        sheet,
        card.freshness,
        top=HEADER_TOP,
        brand_size=BRAND_SIZE,
        text_size=DAY_SIZE,
        text_line=DAY_LINE,
        max_lines=DAY_MAX_LINES,
        rule_gap=RULE_GAP,
        rule_h=RULE_H,
    )


def _title(sheet: Sheet, card: Scoreboard, top: int) -> int:
    """The branch's scoreboard by name, and under it the month with the
    statement's own quality words."""
    scale = sheet.scale
    title_size = scale.px(TITLE_SIZE)
    sub_size = scale.px(SUBTITLE_SIZE)
    sub_line = scale.px(SUBTITLE_LINE)
    sheet.text(
        MARGIN, top, shorten(card.title, BRAND, title_size, CONTENT_W), BRAND, title_size, DATE_PALM
    )
    y = top + text_height(BRAND, title_size) + scale.px(SUBTITLE_GAP)
    lines = wrap(card.subtitle, REGULAR, sub_size, CONTENT_W, SUBTITLE_MAX_LINES)
    for index, line in enumerate(lines):
        sheet.text(MARGIN, y + index * sub_line, line, REGULAR, sub_size, SLATE)
    return y + len(lines) * sub_line


def _row_note_lines(sheet: Sheet, item: ItemLine, inner: int) -> list[str]:
    """The sentence under a row: a hole's, or the no-quantity note, wrapped
    and never cut short of two lines - it is the sentence that says why the
    count is not what it looks like."""
    scale = sheet.scale
    text = item.hole if item.hole is not None else item.note
    if text is None:
        return []
    return wrap(text, REGULAR, scale.px(ROW_NOTE_SIZE), inner, ROW_NOTE_MAX_LINES)


def _row_height(sheet: Sheet, item: ItemLine, inner: int, *, bars: bool) -> int:
    scale = sheet.scale
    height = text_height(REGULAR, scale.px(ROW_NAME_SIZE))
    if bars and item.share is not None:
        height += scale.px(ROW_BAR_GAP) + scale.px(ROW_BAR_H)
    notes = _row_note_lines(sheet, item, inner)
    if notes:
        height += scale.px(ROW_NOTE_GAP) + len(notes) * scale.px(ROW_NOTE_LINE)
    return height


def _row(sheet: Sheet, item: ItemLine, x: int, y: int, inner: int, *, bars: bool) -> int:
    """One push item: the name, the statement's words on the right, the bar
    to the share reached (on the daily card), and the sentence that qualifies
    the count where there is one. Returns the y the row ends at."""
    scale = sheet.scale
    name_size = scale.px(ROW_NAME_SIZE)
    words_size = scale.px(ROW_WORDS_SIZE)
    words_colour = GREEN if item.reached else INK
    right = x + inner
    # A hole's words are its sentence, and the sentence goes under the name,
    # whole, where the bar would be: the right-hand column stays empty, so a
    # gap is what the eye meets and never a count (D7).
    words = "" if item.hole is not None else item.words
    words_w = text_width(words, MEDIUM, words_size) if words else 0
    name_w = inner - words_w - (scale.px(ROW_COL_GAP) if words else 0)
    sheet.text(x, y, shorten(item.name, REGULAR, name_size, name_w), REGULAR, name_size, INK)
    if words:
        sheet.right(right, y, words, MEDIUM, words_size, words_colour)
    y += text_height(REGULAR, name_size)
    if bars and item.share is not None:
        y += scale.px(ROW_BAR_GAP)
        bar_h = scale.px(ROW_BAR_H)
        sheet.add(Rule(x, y, inner, bar_h, MIST))
        filled = int((Decimal(inner) * item.share).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        if filled > 0:
            sheet.add(Rule(x, y, filled, bar_h, GREEN if item.reached else KARAK_GOLD))
        y += bar_h
    notes = _row_note_lines(sheet, item, inner)
    if notes:
        y += scale.px(ROW_NOTE_GAP)
        note_size = scale.px(ROW_NOTE_SIZE)
        note_line = scale.px(ROW_NOTE_LINE)
        for index, line in enumerate(notes):
            sheet.text(x, y + index * note_line, line, REGULAR, note_size, SLATE)
        y += len(notes) * note_line
    return y


def _list(sheet: Sheet, card: Scoreboard, top: int) -> int:
    """The push list: the week's items in the statement's own order, or the
    statement's own words for a week left empty. On the final card every
    week of the month, each under its dates, one line per item. Past the
    card's cap the panel says how many more are on the list, and a week
    whose every row fell past the cap is not headed over nothing."""
    scale = sheet.scale
    pad = scale.px(PANEL_PAD)
    x = MARGIN + pad
    inner = CONTENT_W - 2 * pad
    title_size = scale.px(PANEL_TITLE_SIZE)
    week_size = scale.px(WEEK_TITLE_SIZE)
    empty_size = scale.px(EMPTY_SIZE)
    more_size = scale.px(MORE_SIZE)
    bars = card.variant == DAILY
    row_gap = scale.px(ROW_GAP if bars else ROW_COMPACT_GAP)
    multi = len(card.weeks) > 1

    # Measure first: the panel's box is drawn under its contents, so its
    # height must be known before any row is placed.
    budget = CARD_MAX_ROWS if bars else FINAL_MAX_ROWS
    planned: list[tuple[str, str | None, list[ItemLine]]] = []
    left_out = 0
    for week in card.weeks:
        drawn = week.items[: max(budget, 0)]
        left_out += len(week.items) - len(drawn)
        budget -= len(drawn)
        if drawn or week.empty_words is not None:
            planned.append((week.title, week.empty_words, list(drawn)))

    height = pad + text_height(BRAND, title_size) + scale.px(PANEL_TITLE_GAP)
    for index, (_, empty_words, rows) in enumerate(planned):
        if index:
            height += scale.px(WEEK_GAP)
        if multi:
            height += text_height(MEDIUM, week_size) + scale.px(WEEK_TITLE_GAP)
        if empty_words is not None:
            height += text_height(REGULAR, empty_size)
        for row_index, item in enumerate(rows):
            if row_index:
                height += row_gap
            height += _row_height(sheet, item, inner, bars=bars)
    if left_out:
        height += scale.px(MORE_GAP) + text_height(REGULAR, more_size)
    height += pad

    sheet.add(Box(MARGIN, top, CONTENT_W, height, WHITE, BORDER, scale.px(RADIUS)))
    list_title = shorten(card.list_title, BRAND, title_size, inner)
    sheet.text(x, top + pad, list_title, BRAND, title_size, DATE_PALM)
    y = top + pad + text_height(BRAND, title_size) + scale.px(PANEL_TITLE_GAP)
    for index, (title, empty_words, rows) in enumerate(planned):
        if index:
            y += scale.px(WEEK_GAP)
        if multi:
            sheet.text(x, y, title, MEDIUM, week_size, SLATE)
            y += text_height(MEDIUM, week_size) + scale.px(WEEK_TITLE_GAP)
        if empty_words is not None:
            sheet.text(
                x, y, shorten(empty_words, REGULAR, empty_size, inner), REGULAR, empty_size, SLATE
            )
            y += text_height(REGULAR, empty_size)
        for row_index, item in enumerate(rows):
            if row_index:
                y += row_gap
            y = _row(sheet, item, x, y, inner, bars=bars)
    if left_out:
        y += scale.px(MORE_GAP)
        sheet.text(x, y, _more_words(left_out), REGULAR, more_size, SLATE)
    return top + height


def _figures(sheet: Sheet, card: Scoreboard, top: int) -> int:
    """Net sales against target and the pool, one row each with the label on
    the left and the statement's words on the right; on the final card the
    split by role under them in the product voice, each amount to the fil.
    The words are never shortened - a truncated dirham figure would be a
    wrong number - so the label gives way instead."""
    scale = sheet.scale
    row_h = scale.px(FIGURE_ROW_H)
    pad_x = scale.px(FIGURE_PAD_X)
    label_size = scale.px(FIGURE_LABEL_SIZE)
    value_size = scale.px(FIGURE_VALUE_SIZE)
    split_size = scale.px(FIGURE_SPLIT_SIZE)
    height = row_h * len(card.figures)
    sheet.add(Box(MARGIN, top, CONTENT_W, height, WHITE, BORDER, scale.px(RADIUS)))
    x = MARGIN + pad_x
    right = CANVAS_W - MARGIN - pad_x
    inner = right - x
    for index, line in enumerate(card.figures):
        y = top + index * row_h
        if index:
            sheet.add(Rule(MARGIN, y, CONTENT_W, 1, BORDER))
        headline = index < 2
        font, size, colour = (
            (BRAND, value_size, DATE_PALM) if headline else (REGULAR, split_size, INK)
        )
        words_w = text_width(line.words, font, size)
        label_w = inner - words_w - scale.px(ROW_COL_GAP)
        label_y = y + (row_h - text_height(REGULAR, label_size)) // 2
        label = shorten(line.label, REGULAR, label_size, label_w)
        sheet.text(x, label_y, label, REGULAR, label_size, SLATE)
        words_y = y + (row_h - text_height(font, size)) // 2
        sheet.right(right, words_y, line.words, font, size, colour)
    return top + height


def _notes(sheet: Sheet, notes: tuple[str, ...], top: int) -> int:
    scale = sheet.scale
    size = scale.px(NOTE_SIZE)
    line_h = scale.px(NOTE_LINE)
    y = top
    for index, note in enumerate(notes):
        if index:
            y += scale.px(NOTE_GAP)
        lines = wrap(note, REGULAR, size, CONTENT_W, NOTE_MAX_LINES)
        for line_index, line in enumerate(lines):
            sheet.text(MARGIN, y + line_index * line_h, line, REGULAR, size, SLATE)
        y += len(lines) * line_h
    return y


def _footer(sheet: Sheet, footer: str, top: int) -> int:
    scale = sheet.scale
    size = scale.px(FOOTER_SIZE)
    line_h = scale.px(FOOTER_LINE)
    lines = wrap(footer, REGULAR, size, CONTENT_W, FOOTER_MAX_LINES)
    for index, line in enumerate(lines):
        sheet.text(MARGIN, top + index * line_h, line, REGULAR, size, SLATE)
    return top + max(len(lines), 1) * line_h


def _plan(card: Scoreboard, factor: float, extra_gap: int) -> tuple[Sheet, int]:
    sheet = Sheet(Scale(factor), extra_gap)
    y = _header(sheet, card)
    y = _title(sheet, card, sheet.gap(y))
    y = _list(sheet, card, sheet.gap(y))
    y = _figures(sheet, card, sheet.gap(y))
    if card.notes:
        y = _notes(sheet, card.notes, sheet.gap(y))
    y = _footer(sheet, card.footer, sheet.gap(y))
    return sheet, y + sheet.scale.px(BOTTOM_MARGIN)


def layout(card: Scoreboard) -> Layout:
    """Every drawn thing on the card, in drawing order, at the largest scale
    that fits the canvas (`card.fit`)."""
    rows = sum(len(week.items) for week in card.weeks)
    return fit(
        lambda factor, extra: _plan(card, factor, extra),
        what=f"the {card.variant} scoreboard ({len(card.weeks)} weeks, {rows} items)",
    )


def render_card(card: Scoreboard) -> bytes:
    """The card as PNG bytes, ready to upload as the template's image header.
    Deterministic for the same `Scoreboard` (`card.render`)."""
    return render(layout(card))
