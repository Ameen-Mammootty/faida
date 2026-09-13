"""The card sheet: everything general about drawing a 1080 by 1350 picture for
a WhatsApp template header, with no knowledge of what any card says (M13
WP-130, the one prefactor the milestone allows).

`brief_card.py` was the first card and held two things at once: the brief's
own layout (the four tiles, the branch table, the two lists, the spikes) and
the general machinery any card needs - the canvas, the brand's palette, the
bundled fonts, the measuring and fitting helpers, the scale ladder that finds
the largest type that fits, and the renderer that walks a plan with Pillow.
The scoreboard (M13) is the second card, so the general part lives here and
each card's module holds only its own blocks. Nothing here names a field of
any card: a module that imports this knows how to draw, and this knows
nothing about what.

Two layers, as before, because a picture is untestable and a plan is not:

1. A card module builds a plan - `Box`, `Rule` and `Text` shapes in drawing
   order on a `Sheet` - as a pure function of its own composed figures.
   `fit(plan)` runs that function down the scale ladder and returns the first
   `Layout` that fits the canvas, then spends the slack on air between the
   blocks. The tests read the plan: every line on the card, nothing off the
   edge.
2. `render(layout)` walks the plan with Pillow once and hands back the PNG.
   Deterministic: the same plan gives byte-identical bytes, so a card can be
   stored, re-sent and compared. Nothing dated goes into the file.

The look is the brand's (`Docs/brand/faida-brand-guidelines.md`): warm cream
ground, Date Palm headings, a Karak Gold rule, white panels on Mist borders,
Slate for everything that qualifies a figure, Critical Plum for a money value
below nought - never colour alone. Manrope Bold is the brand voice and Inter
the product voice; both are bundled under the SIL Open Font License 1.1
(`fonts/README.md`) and loaded through `importlib.resources` so an installed
wheel finds them.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import resources
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

#: 4:5, which WhatsApp shows whole in the bubble; a taller picture is cropped
#: there and a table would lose its last rows to a tap nobody makes.
CANVAS_W = 1080
CANVAS_H = 1350

# --- the brand's own colours (Docs/brand/faida-brand-guidelines.md) --------------

CREAM = "#fbf6ec"
DATE_PALM = "#153e35"
KARAK_GOLD = "#e3a13b"
INK = "#172421"
SLATE = "#52625d"
MIST = "#e7efea"
PLUM = "#65415f"
WHITE = "#ffffff"
BORDER = "#d9e3dd"
#: Confirmed Green, for a figure that has reached its target: paired with
#: the words that say so, never alone.
GREEN = "#1d6d50"

# --- the two voices -------------------------------------------------------------

#: Manrope for the brand voice, Inter for the product voice - the guidelines'
#: own division. Both are variable fonts and are pinned to a named instance,
#: so a weight is a name here and never a synthetic bold.
BRAND = "brand"
REGULAR = "regular"
MEDIUM = "medium"

_FONT_FILES = {
    BRAND: ("Manrope[wght].ttf", "Bold"),
    REGULAR: ("Inter[opsz,wght].ttf", "Regular"),
    MEDIUM: ("Inter[opsz,wght].ttf", "Medium"),
}

ELLIPSIS = "…"

# --- the frame, at scale 1.0 ----------------------------------------------------

MARGIN = 60
CONTENT_W = CANVAS_W - 2 * MARGIN
BLOCK_GAP = 23
RADIUS = 12
BOTTOM_MARGIN = 40

#: The scales `fit` tries, largest first: the first plan that fits the canvas
#: is the one drawn. A fixed tuple, so the same figures always land on the
#: same scale and the same bytes. It stops at 1.0 - each card's measures are
#: its design, and a short card spends its slack on air between the blocks
#: rather than on type bigger than the design's own.
SCALES = tuple(round(1.0 - 0.02 * step, 2) for step in range(16))

#: Slack left over under the chosen scale is spread through the gaps between
#: the blocks, up to this much each, so a short card breathes instead of
#: leaving one hole above the footer.
MAX_EXTRA_GAP = 44


# --- the plan -------------------------------------------------------------------


@dataclass(frozen=True)
class Box:
    """A filled or outlined rectangle: a tile, a panel, a table's card."""

    x: int
    y: int
    w: int
    h: int
    fill: str | None = None
    border: str | None = None
    radius: int = 0
    corners: tuple[bool, bool, bool, bool] = (True, True, True, True)


@dataclass(frozen=True)
class Rule:
    """A flat bar of colour: the Karak Gold rule under a wordmark, the
    hairlines between a table's rows, a bar filled to a share."""

    x: int
    y: int
    w: int
    h: int
    colour: str


@dataclass(frozen=True)
class Text:
    """One run of text with the rectangle it occupies. `x`, `y` is its
    top-left corner - `y` at the font's ascender line, so every run on a line
    shares one baseline whatever glyphs it carries - and `w`, `h` are what the
    font measured, which is what makes "nothing is clipped" a test and not an
    opinion."""

    x: int
    y: int
    w: int
    h: int
    text: str
    font: str
    size: int
    colour: str


Shape = Box | Rule | Text


@dataclass(frozen=True)
class Layout:
    """Everything a card draws, in drawing order, on a canvas of a fixed
    size. Pure data: the tests read it, the renderer walks it."""

    width: int
    height: int
    items: tuple[Shape, ...]

    @property
    def texts(self) -> tuple[Text, ...]:
        return tuple(item for item in self.items if isinstance(item, Text))

    @property
    def lines(self) -> tuple[str, ...]:
        """Every string drawn, in drawing order."""
        return tuple(item.text for item in self.texts)


# --- the fonts ------------------------------------------------------------------


_FONT_CACHE: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """The bundled face at one size, pinned to its named instance. Cached
    because a card loads a dozen sizes and every one is measured many times;
    the object is never mutated after it is made, so the cache is safe."""
    key = (name, size)
    face = _FONT_CACHE.get(key)
    if face is None:
        file, instance = _FONT_FILES[name]
        with resources.as_file(resources.files(__package__).joinpath("fonts", file)) as path:
            face = ImageFont.truetype(str(path), size)
            face.set_variation_by_name(instance)
        _FONT_CACHE[key] = face
    return face


def text_width(text: str, name: str, size: int) -> int:
    return math.ceil(font(name, size).getlength(text))


def text_height(name: str, size: int) -> int:
    ascent, descent = font(name, size).getmetrics()
    return ascent + descent


def shorten(text: str, name: str, size: int, max_width: int) -> str:
    """The text, shortened with an ellipsis until it measures inside
    `max_width`. A branch or a menu item can be named anything, and a name
    that ran over its column would be a figure in the next column made
    unreadable."""
    if text_width(text, name, size) <= max_width:
        return text
    cut = text
    while cut and text_width(cut + ELLIPSIS, name, size) > max_width:
        cut = cut[:-1]
    return (cut.rstrip() + ELLIPSIS) if cut else ELLIPSIS


def wrap(text: str, name: str, size: int, max_width: int, max_lines: int) -> list[str]:
    """`text` broken on spaces to `max_width`, at most `max_lines` lines, the
    last one shortened with an ellipsis if the rest does not fit."""
    if not text:
        return []
    if max_lines <= 1:
        return [shorten(text, name, size, max_width)]
    words = text.split()
    lines: list[str] = []
    current = ""
    for index, word in enumerate(words):
        candidate = f"{current} {word}".strip()
        if current and text_width(candidate, name, size) > max_width:
            lines.append(current)
            if len(lines) == max_lines - 1:
                return lines + [shorten(" ".join(words[index:]), name, size, max_width)]
            current = word
        else:
            current = candidate
    if current:
        lines.append(shorten(current, name, size, max_width))
    return lines


# --- the scale and the sheet ----------------------------------------------------


@dataclass(frozen=True)
class Scale:
    """Every vertical measure and every font size on a card, at one scale.
    One knob, so a card is one design at every size rather than a roomy
    design and a cramped one."""

    factor: float

    def px(self, base: float) -> int:
        return max(1, round(base * self.factor))


@dataclass
class Sheet:
    """The plan under construction: shapes in drawing order, and the running
    count of the gaps between blocks so the slack can be shared out."""

    scale: Scale
    extra_gap: int
    items: list[Shape] = field(default_factory=list)
    gaps: int = 0

    def add(self, shape: Shape) -> None:
        self.items.append(shape)

    def gap(self, y: int) -> int:
        self.gaps += 1
        return y + self.scale.px(BLOCK_GAP) + self.extra_gap

    def text(self, x: int, y: int, text: str, name: str, size: int, colour: str) -> int:
        """One run at its top-left corner; returns the x just past it, so runs
        of two colours sit on one line without measuring twice."""
        w = text_width(text, name, size)
        self.add(Text(x, y, w, text_height(name, size), text, name, size, colour))
        return x + w

    def right(self, right: int, y: int, text: str, name: str, size: int, colour: str) -> None:
        """One run ending at `right`: a table's figures are right-aligned, so
        a column of dirhams reads down its own units."""
        self.text(right - text_width(text, name, size), y, text, name, size, colour)


def header(
    sheet: Sheet,
    text: str,
    *,
    top: int,
    brand_size: int,
    text_size: int,
    text_line: int,
    max_lines: int,
    rule_gap: int,
    rule_h: int,
) -> int:
    """The wordmark and one line of words on its right, with a Karak Gold
    rule under them: how every card opens. The words are the card's own
    sentence about its day - the brief's freshness, the scoreboard's - and
    can run long on a stale morning, so they wrap to `max_lines` rather than
    being cut. The measures are the card's, passed in at its scale; returns
    the y the rule ends at."""
    scale = sheet.scale
    brand_px = scale.px(brand_size)
    size = scale.px(text_size)
    line = scale.px(text_line)
    brand_w = text_width("Faida", BRAND, brand_px)
    brand_h = text_height(BRAND, brand_px)
    lines = wrap(text, REGULAR, size, CONTENT_W - brand_w - scale.px(40), max_lines)
    block_h = max(brand_h, len(lines) * line)
    y = scale.px(top)
    sheet.text(MARGIN, y + block_h - brand_h, "Faida", BRAND, brand_px, DATE_PALM)
    text_top = y + block_h - len(lines) * line
    for index, run in enumerate(lines):
        sheet.right(CANVAS_W - MARGIN, text_top + index * line, run, REGULAR, size, SLATE)
    rule_y = y + block_h + scale.px(rule_gap)
    sheet.add(Rule(MARGIN, rule_y, CONTENT_W, scale.px(rule_h), KARAK_GOLD))
    return rule_y + scale.px(rule_h)


#: A card's plan at one scale and one extra gap: the sheet and the y its last
#: line ends at (the bottom margin included). Nothing is anchored to the
#: bottom - the fit is decided by the scale, and the slack shared out by `fit`.
Plan = Callable[[float, int], tuple[Sheet, int]]


def fit(plan: Plan, *, what: str) -> Layout:
    """Every drawn thing on the card, in drawing order, at the largest scale
    that fits the canvas. `what` names the card in the error a card that does
    not fit at the smallest scale raises."""
    for factor in SCALES:
        sheet, drawn_height = plan(factor, 0)
        if drawn_height <= CANVAS_H:
            extra = min(MAX_EXTRA_GAP, (CANVAS_H - drawn_height) // max(sheet.gaps, 1))
            if extra:
                sheet, drawn_height = plan(factor, extra)
            return Layout(CANVAS_W, CANVAS_H, tuple(sheet.items))
    raise ValueError(
        f"{what} does not fit a {CANVAS_W} by {CANVAS_H} card at the smallest scale ({SCALES[-1]})"
    )


# --- the picture ----------------------------------------------------------------


def render(plan: Layout) -> bytes:
    """The card as PNG bytes, ready to upload to Meta as a template's image
    header. Deterministic for the same plan: nothing dated is written into
    the file, so the same figures re-rendered are the same picture and a
    stored card can be compared with what was sent."""
    image = Image.new("RGB", (plan.width, plan.height), CREAM)
    draw = ImageDraw.Draw(image)
    for item in plan.items:
        if isinstance(item, Box):
            if item.fill is None and item.border is None:  # pragma: no cover - never planned
                continue
            draw.rounded_rectangle(
                (item.x, item.y, item.x + item.w - 1, item.y + item.h - 1),
                radius=item.radius,
                fill=item.fill,
                outline=item.border,
                width=1,
                corners=item.corners,
            )
        elif isinstance(item, Rule):
            draw.rectangle(
                (item.x, item.y, item.x + item.w - 1, item.y + item.h - 1), fill=item.colour
            )
        else:
            draw.text(
                (item.x, item.y),
                item.text,
                font=font(item.font, item.size),
                fill=item.colour,
                anchor="la",
            )
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()
