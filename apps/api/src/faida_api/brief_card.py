"""M10 WP-106: the picture card - the morning brief drawn as one picture
(Docs/M10_DECOMPOSITION.md §3 C15.4, §3.1 "Template A", §4 row 106, §4.1, §7;
plan.md §7.3).

A WhatsApp template variable cannot hold a line break, so the branch table the
founder asked for cannot travel as text (P15, decided 2026-09-08). It travels
as the template's image header instead: a 1080 by 1350 PNG - 4:5, the tallest
ratio WhatsApp shows whole in the bubble - carrying the four figures, one row
per branch, the two item lists and the price spikes. The same four figures
stay in the message's text under it, so the chat-list preview and a screen
reader get them without opening the picture.

**This module invents no facts and re-words no sentence.** Every string it
draws comes off the `Brief` that `brief.py` composed - `day`, each `Kpi`'s
three pieces, each `BranchRow`'s four words (already carrying `-` where the
read has a hole), each `ItemLine`, each `SpikeLine`'s sentence and its money
clause, `no_spikes` and `card_footer`. What is composed here is only what the
picture itself needs and the message has no place for: the column headings,
the two panel titles, the count of the items that could not be costed, and the
line that says how many branches did not fit. Those are named below, in one
place each.

Two layers, because a picture is untestable and a plan is not:

1. `layout(brief) -> Layout` is a pure function: it reads the brief, measures
   the bundled fonts, and returns every drawn thing - a `Box`, a `Rule` or a
   `Text` - with its own rectangle, in drawing order. No image is made and
   nothing is written. That is what the tests read: every line of the brief
   appears once, every rectangle sits inside the canvas, the rows keep the
   brief's order, a name too long for its column is shortened with an ellipsis
   rather than run over the edge.
2. `render_card(brief) -> bytes` walks that plan with Pillow once and hands
   back the PNG. Deterministic: the same `Brief` gives byte-identical PNGs, so
   a card can be stored, re-sent and compared. Nothing dated goes into the
   file (no `pnginfo`, `optimize=False`).

The drawing itself - the canvas, the palette, the bundled fonts, the fit and
wrap helpers, the scale ladder and the renderer - is `card.py`, the sheet
every card is drawn on since the scoreboard became the second one (M13
WP-130). This module holds only the brief's own blocks and their measures.

The card fits by scaling, not by dropping. Every vertical measure and every
font size comes off one `card.Scale`, and `layout` takes the largest scale
whose plan fits the canvas: a chain of one gets generous type, a chain of ten
gets a dense but whole table. Past `CARD_MAX_ROWS` branches the table says how
many are not on it and the dashboard carries the rest - the one place the card
drops anything, and it says so.

The look is the brand's (`Docs/brand/faida-brand-guidelines.md`) and the
committed sample the founder approved (`Docs/brief/faida_daily_brief_sample.png`):
warm cream ground, Date Palm headings, a Karak Gold rule, white panels on Mist
borders, Slate for everything that qualifies a figure, and Critical Plum for a
money value below nought - never colour alone, because every one of those
numbers carries its own sign and its own words. Manrope Bold is the brand
voice (the wordmark, the four figures, the panel titles) and Inter is the
product voice (everything else).

The display rules hold on a picture as they do on a screen (CLAUDE.md §3):
whole dirhams as `brief.py` rounded them, the materials column qualified by
the card's own footer sentence and never called food cost, contribution never
called profit, nothing called verified, and a hole drawn as `brief.HOLE` and
never as a nought.
"""

import math

from .brief import HOLE, BranchRow, Brief, ItemLine, Kpi, SpikeLine
from .card import (
    BORDER,
    BOTTOM_MARGIN,
    BRAND,
    CANVAS_H,
    CANVAS_W,
    CONTENT_W,
    DATE_PALM,
    ELLIPSIS,
    INK,
    KARAK_GOLD,
    MARGIN,
    MEDIUM,
    MIST,
    PLUM,
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

__all__ = [
    "BORDER",
    "BRAND",
    "CANVAS_H",
    "CANVAS_W",
    "CARD_MAX_ROWS",
    "CONTENT_W",
    "DATE_PALM",
    "ELLIPSIS",
    "INK",
    "KARAK_GOLD",
    "MARGIN",
    "MEDIUM",
    "MIST",
    "PLUM",
    "RADIUS",
    "REGULAR",
    "SLATE",
    "WHITE",
    "Box",
    "Layout",
    "Rule",
    "Text",
    "layout",
    "render_card",
]

#: The most branch rows the table draws. Past it the card says how many are
#: not on it (`_more_words`) and the dashboard carries them: a card that
#: silently stopped at ten would be a chain of twelve reading as a chain of
#: ten, which is the one thing a table must never do.
CARD_MAX_ROWS = 10

# --- the words the picture needs and the message has no place for ---------------

COL_BRANCH = "Branch"
COL_LATEST = "Latest day"
COL_MONTH = "Month"
COL_MATERIALS = "Materials"
TITLE_MOST = "Earning most"
TITLE_LEAST = "Earning least"
TITLE_SPIKES = "Price spikes"


def _uncosted_words(count: int) -> str:
    """What the card says under the two lists when the menu has sales the read
    could not cost: a short list is short for a reason, and the reason belongs
    beside it (C12.7's habit, in the card's own words)."""
    return f"{count} item{'' if count == 1 else 's'} cannot be costed yet"


def _more_words(count: int) -> str:
    """What the table says when the chain is longer than the card."""
    return f"and {count} more on the dashboard"


# --- the measures, at scale 1.0 -------------------------------------------------

HEADER_TOP = 44
BRAND_SIZE = 40
DAY_SIZE = 21
DAY_LINE = 26
DAY_MAX_LINES = 2
RULE_GAP = 16
RULE_H = 3

TILE_GAP = 16
TILE_PAD = 23
TILE_LABEL_SIZE = 20
TILE_VALUE_SIZE = 42
TILE_SUB_SIZE = 18
TILE_SUB_LINE = 23
TILE_SUB_MAX_LINES = 2

TABLE_PAD_X = 25
TABLE_HEAD_H = 40
TABLE_HEAD_SIZE = 19
TABLE_ROW_H = 55
TABLE_ROW_SIZE = 21
TABLE_COL_W = 176
TABLE_COL_GAP = 21
TABLE_MORE_SIZE = 19

#: A long chain pays for its length in the one measure that can give it: the
#: white space around a row, which tapers from the fourth branch to the tenth.
#: The type does not taper with it - a row is one line of words and a figure,
#: and a tighter row is still a row, where smaller type is a worse card.
TABLE_ROW_MIN_H = 38
TABLE_ROW_TAPER_FROM = 4

PANEL_PAD = 21
PANEL_GAP = 18
PANEL_TITLE_SIZE = 21
PANEL_TITLE_GAP = 11
PANEL_LINE = 30
PANEL_SIZE = 20

UNCOSTED_GAP = 9
UNCOSTED_SIZE = 19

SPIKE_LINE = 28
SPIKE_SIZE = 19
SPIKE_BULLET_X = 11
SPIKE_TEXT_X = 30

FOOTER_SIZE = 19
FOOTER_LINE = 26
FOOTER_MAX_LINES = 3


# --- the blocks -----------------------------------------------------------------


def _header(sheet: Sheet, brief: Brief) -> int:
    """The wordmark and the day, on one line with a Karak Gold rule under
    them (`card.header`). The day is the read's own sentence and can run long
    on a stale morning, so it wraps to a second line rather than being cut."""
    return header(
        sheet,
        brief.day,
        top=HEADER_TOP,
        brand_size=BRAND_SIZE,
        text_size=DAY_SIZE,
        text_line=DAY_LINE,
        max_lines=DAY_MAX_LINES,
        rule_gap=RULE_GAP,
        rule_h=RULE_H,
    )


def _tiles(sheet: Sheet, kpis: tuple[Kpi, ...], top: int) -> int:
    """The four figures as a two by two grid, each the label, the figure and
    the words that qualify it - the same three pieces the message's line is
    built from, so the tile and the line are one number."""
    if not kpis:
        return top
    scale = sheet.scale
    pad = scale.px(TILE_PAD)
    label_size = scale.px(TILE_LABEL_SIZE)
    value_size = scale.px(TILE_VALUE_SIZE)
    sub_size = scale.px(TILE_SUB_SIZE)
    sub_line = scale.px(TILE_SUB_LINE)
    gap = scale.px(TILE_GAP)
    tile_w = (CONTENT_W - gap) // 2
    inner_w = tile_w - 2 * pad
    subs = [wrap(kpi.sub, REGULAR, sub_size, inner_w, TILE_SUB_MAX_LINES) for kpi in kpis]
    label_h = text_height(REGULAR, label_size)
    value_h = text_height(BRAND, value_size)
    sub_rows = max((len(lines) for lines in subs), default=0)
    tile_h = pad + label_h + scale.px(6) + value_h + scale.px(4) + sub_rows * sub_line + pad
    for index, (kpi, sub_lines) in enumerate(zip(kpis, subs, strict=True)):
        x = MARGIN + (index % 2) * (tile_w + gap)
        y = top + (index // 2) * (tile_h + gap)
        sheet.add(Box(x, y, tile_w, tile_h, WHITE, BORDER, scale.px(RADIUS)))
        sheet.text(x + pad, y + pad, kpi.label, REGULAR, label_size, SLATE)
        value_y = y + pad + label_h + scale.px(6)
        sheet.text(
            x + pad,
            value_y,
            shorten(kpi.value, BRAND, value_size, inner_w),
            BRAND,
            value_size,
            DATE_PALM,
        )
        sub_y = value_y + value_h + scale.px(4)
        for line, text in enumerate(sub_lines):
            sheet.text(x + pad, sub_y + line * sub_line, text, REGULAR, sub_size, SLATE)
    rows = math.ceil(len(kpis) / 2)
    return top + rows * tile_h + (rows - 1) * gap


def _row_height(scale: Scale, count: int) -> int:
    """The height of one branch row: full until the fourth branch, then
    tapering to `TABLE_ROW_MIN_H` at the tenth, so a chain of ten keeps its
    whole table without the rest of the card shrinking around it."""
    if count <= TABLE_ROW_TAPER_FROM:
        return scale.px(TABLE_ROW_H)
    span = max(CARD_MAX_ROWS - TABLE_ROW_TAPER_FROM, 1)
    over = min(count - TABLE_ROW_TAPER_FROM, span)
    return scale.px(TABLE_ROW_H - (TABLE_ROW_H - TABLE_ROW_MIN_H) * over / span)


def _table(sheet: Sheet, rows: tuple[BranchRow, ...], top: int) -> int:
    """One row per branch, in the league's own order - kept share lowest
    first, the order the dashboard ranks them in, so the card and the screen
    read the same way down the page. Every figure is the row's own words, so a
    branch that loaded nothing shows `brief.HOLE` and never a nought."""
    if not rows:
        return top
    scale = sheet.scale
    head_h = scale.px(TABLE_HEAD_H)
    row_h = _row_height(scale, len(rows))
    head_size = scale.px(TABLE_HEAD_SIZE)
    row_size = scale.px(TABLE_ROW_SIZE)
    pad_x = scale.px(TABLE_PAD_X)
    col_w = scale.px(TABLE_COL_W)
    radius = scale.px(RADIUS)
    drawn = rows[:CARD_MAX_ROWS]
    rest = len(rows) - len(drawn)
    more_h = scale.px(TABLE_MORE_SIZE) + scale.px(24) if rest else 0
    height = head_h + len(drawn) * row_h + more_h

    sheet.add(Box(MARGIN, top, CONTENT_W, height, WHITE, None, radius))
    sheet.add(Box(MARGIN, top, CONTENT_W, head_h, MIST, None, radius, (True, True, False, False)))

    right_materials = CANVAS_W - MARGIN - pad_x
    right_month = right_materials - col_w
    right_latest = right_month - col_w
    name_x = MARGIN + pad_x
    name_w = right_latest - col_w - name_x - scale.px(TABLE_COL_GAP)

    head_y = top + (head_h - text_height(MEDIUM, head_size)) // 2
    sheet.text(name_x, head_y, COL_BRANCH, MEDIUM, head_size, SLATE)
    for right, label in (
        (right_latest, COL_LATEST),
        (right_month, COL_MONTH),
        (right_materials, COL_MATERIALS),
    ):
        sheet.right(right, head_y, label, MEDIUM, head_size, SLATE)

    row_top = top + head_h
    for index, row in enumerate(drawn):
        y = row_top + index * row_h
        if index:
            sheet.add(Rule(MARGIN, y, CONTENT_W, 1, BORDER))
        text_y = y + (row_h - text_height(REGULAR, row_size)) // 2
        sheet.text(
            name_x, text_y, shorten(row.name, REGULAR, row_size, name_w), REGULAR, row_size, INK
        )
        for right, words in (
            (right_latest, row.latest_day_words),
            (right_month, row.month_words),
            (right_materials, row.materials_share_words),
        ):
            sheet.right(right, text_y, words, REGULAR, row_size, INK)
    if rest:
        y = row_top + len(drawn) * row_h
        sheet.add(Rule(MARGIN, y, CONTENT_W, 1, BORDER))
        more_size = scale.px(TABLE_MORE_SIZE)
        sheet.text(
            name_x,
            y + (more_h - text_height(REGULAR, more_size)) // 2,
            _more_words(rest),
            REGULAR,
            more_size,
            SLATE,
        )
    sheet.add(Box(MARGIN, top, CONTENT_W, height, None, BORDER, radius))
    return top + height


def _item_lines(sheet: Sheet, items: tuple[ItemLine, ...]) -> list[tuple[str, str, str]]:
    """A numbered item as three pieces - the number and name, the money, and
    the money's colour. The name is shortened before the money is, because the
    money is the point of the list and a truncated dirham figure would be a
    wrong number."""
    scale = sheet.scale
    size = scale.px(PANEL_SIZE)
    pad = scale.px(PANEL_PAD)
    inner = (CONTENT_W - scale.px(PANEL_GAP)) // 2 - 2 * pad
    lines = []
    for index, item in enumerate(items, start=1):
        money = f" {item.money_words}"
        room = inner - text_width(money, REGULAR, size)
        name = shorten(f"{index}. {item.name}", REGULAR, size, room)
        lines.append((name, money, PLUM if item.money < 0 else SLATE))
    return lines


def _panels(sheet: Sheet, brief: Brief, top: int) -> int:
    """The two lists side by side, and under them - when the read could not
    cost everything the till sold - how many items are missing from them."""
    scale = sheet.scale
    pad = scale.px(PANEL_PAD)
    gap = scale.px(PANEL_GAP)
    title_size = scale.px(PANEL_TITLE_SIZE)
    size = scale.px(PANEL_SIZE)
    line_h = scale.px(PANEL_LINE)
    panel_w = (CONTENT_W - gap) // 2
    most = _item_lines(sheet, brief.earning_most)
    least = _item_lines(sheet, brief.earning_least)
    rows = max(len(most), len(least), 1)
    title_h = text_height(BRAND, title_size)
    height = pad + title_h + scale.px(PANEL_TITLE_GAP) + rows * line_h + pad
    for index, (title, lines) in enumerate(((TITLE_MOST, most), (TITLE_LEAST, least))):
        x = MARGIN + index * (panel_w + gap)
        sheet.add(Box(x, top, panel_w, height, WHITE, BORDER, scale.px(RADIUS)))
        sheet.text(x + pad, top + pad, title, BRAND, title_size, DATE_PALM)
        line_y = top + pad + title_h + scale.px(PANEL_TITLE_GAP)
        if not lines:
            sheet.text(x + pad, line_y, HOLE, REGULAR, size, SLATE)
            continue
        for row, (name, money, colour) in enumerate(lines):
            y = line_y + row * line_h
            end = sheet.text(x + pad, y, name, REGULAR, size, INK)
            sheet.text(end, y, money, REGULAR, size, colour)
    bottom = top + height
    if brief.uncosted:
        uncosted_size = scale.px(UNCOSTED_SIZE)
        y = bottom + scale.px(UNCOSTED_GAP)
        sheet.text(MARGIN + pad, y, _uncosted_words(brief.uncosted), REGULAR, uncosted_size, SLATE)
        bottom = y + text_height(REGULAR, uncosted_size)
    return bottom


def _spikes(sheet: Sheet, spikes: tuple[SpikeLine, ...], no_spikes: str | None, top: int) -> int:
    """The biggest supplier price rises: the panel's own sentence and the
    brief's own money clause, the two kept apart in colour because one is the
    fact and the other is what it is worth. The clause follows the sentence on
    the same line when it fits and drops under it when it does not, so neither
    is ever shortened."""
    scale = sheet.scale
    pad = scale.px(PANEL_PAD)
    title_size = scale.px(PANEL_TITLE_SIZE)
    size = scale.px(SPIKE_SIZE)
    line_h = scale.px(SPIKE_LINE)
    text_x = MARGIN + pad + scale.px(SPIKE_TEXT_X)
    inner = CANVAS_W - MARGIN - pad - text_x
    drawn: list[tuple[bool, list[tuple[str, str]]]] = []
    for spike in spikes:
        one = f"{spike.sentence} {spike.money_clause}"
        if text_width(one, REGULAR, size) <= inner:
            drawn.append((True, [(spike.sentence + " ", INK), (spike.money_clause, SLATE)]))
        else:
            drawn.append((True, [(shorten(spike.sentence, REGULAR, size, inner), INK)]))
            drawn.append((False, [(shorten(spike.money_clause, REGULAR, size, inner), SLATE)]))
    if not drawn and no_spikes is not None:
        drawn = [(False, [(line, SLATE)]) for line in wrap(no_spikes, REGULAR, size, inner, 2)]
    title_h = text_height(BRAND, title_size)
    height = pad + title_h + scale.px(PANEL_TITLE_GAP) + max(len(drawn), 1) * line_h + pad
    sheet.add(Box(MARGIN, top, CONTENT_W, height, WHITE, BORDER, scale.px(RADIUS)))
    sheet.text(MARGIN + pad, top + pad, TITLE_SPIKES, BRAND, title_size, DATE_PALM)
    line_y = top + pad + title_h + scale.px(PANEL_TITLE_GAP)
    bullet_x = MARGIN + pad + scale.px(SPIKE_BULLET_X)
    for index, (bulleted, runs) in enumerate(drawn):
        y = line_y + index * line_h
        if bulleted:
            sheet.text(bullet_x, y, "•", REGULAR, size, SLATE)
        x = text_x if spikes else MARGIN + pad
        for text, colour in runs:
            x = sheet.text(x, y, text, REGULAR, size, colour)
    return top + height


def _footer(sheet: Sheet, footer: str, top: int) -> int:
    """The one qualification the whole card needs, in `brief.py`'s words: the
    materials share is of the sales that are costed, and every figure opens to
    its source on the dashboard."""
    scale = sheet.scale
    size = scale.px(FOOTER_SIZE)
    line_h = scale.px(FOOTER_LINE)
    lines = wrap(footer, REGULAR, size, CONTENT_W, FOOTER_MAX_LINES)
    for index, line in enumerate(lines):
        sheet.text(MARGIN, top + index * line_h, line, REGULAR, size, SLATE)
    return top + max(len(lines), 1) * line_h


def _plan(brief: Brief, factor: float, extra_gap: int) -> tuple[Sheet, int]:
    """The whole card at one scale, top down, and the y its last line ends
    at. Nothing is anchored to the bottom: the fit is decided by the scale,
    and the slack is shared out by `layout`."""
    sheet = Sheet(Scale(factor), extra_gap)
    y = _header(sheet, brief)
    y = _tiles(sheet, brief.kpis, sheet.gap(y))
    y = _table(sheet, brief.rows, sheet.gap(y))
    y = _panels(sheet, brief, sheet.gap(y))
    y = _spikes(sheet, brief.spikes, brief.no_spikes, sheet.gap(y))
    y = _footer(sheet, brief.card_footer, sheet.gap(y))
    return sheet, y + sheet.scale.px(BOTTOM_MARGIN)


def layout(brief: Brief) -> Layout:
    """Every drawn thing on the card, in drawing order, at the largest scale
    that fits the canvas (`card.fit`).

    A quiet brief raises: nothing is sent on a morning with nothing loaded
    (C15.7), so there is nothing to draw either, and a blank card sent by
    mistake would be worse than no card.
    """
    if brief.quiet:
        raise ValueError("a quiet brief has nothing to draw: no message is sent (C15.7)")
    return fit(
        lambda factor, extra: _plan(brief, factor, extra),
        what=f"the brief ({len(brief.rows)} branches, {len(brief.spikes)} spikes)",
    )


# --- the picture ----------------------------------------------------------------


def render_card(brief: Brief) -> bytes:
    """The card as PNG bytes, ready to upload to Meta as the template's image
    header. Deterministic for the same `Brief` (`card.render`): nothing dated
    is written into the file, so the same morning re-rendered is the same
    picture and a stored card can be compared with what was sent."""
    return render(layout(brief))
