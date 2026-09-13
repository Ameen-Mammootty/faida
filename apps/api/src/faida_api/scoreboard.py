"""M13.7: the scoreboard, composed - one branch's card for one day out of
its statement and nothing else (plan.md §8 M13 D13 to D16; issue #6's
scoreboard paragraph; issue #13).

The scoreboard is the staff loop: one card a morning to the branch's
registered WhatsApp phone, forwarded by the manager to the team, carrying
this week's push list with each item's portions so far against target, the
month's net sales so far against target, the pool so far marked "so far",
and the first line naming the newest loaded day and its age. A final card
follows the owner's approval with the month named as closed and the pool
split by role, "bonus" as the word (D11, issue #15).

**This module invents no figure and re-words no sentence.** Every number and
every sentence about a number comes off the `Statement` that `incentive.py`
composed - the same read the owner's screen shows, so the card on the phone
and the statement on the screen can never disagree (C16). What is composed
here is only what the card needs and the statement has no place for: the
headline, the labels, the footer, the line that says how many items did not
fit. The first line is `dashboard.freshness_sentence` byte for byte, the
brief's own idiom, so "yesterday" is printed only on a morning when it is
true (D16).

Pure, in `brief.py`'s shape: no clock, no database, no HTTP. The read
(`worker.read_scoreboard`) hands it the statement, the branch's name, the
branch's own local date and the variant, and it hands back words. The card
(`scoreboard_card.py`) draws those words and nothing else, and the two text
slots of the template are the headline and the freshness line (D15).

The variant is the job's own (`jobs_send_scoreboard_uidx`): `daily` for the
morning card, `final` for the card the approval enqueues. A card is what its
statement is: a daily card is refused on a final statement and a final card
on a provisional one, because a final card that was never approved, or a
"so far" card for a month already paid, is the one thing this module must
never compose.

`BANNED_WORDS` holds here as it does on the statement: no composed sentence
says profit, profit share, commission, verified or food cost, and the
staff-facing word is `incentive.BONUS`.
"""

import datetime
from dataclasses import dataclass
from decimal import Decimal

from . import incentive
from .contribution import _price_words
from .dashboard import _weekday_date, freshness_sentence
from .incentive import ItemScore, Statement, WeekScore
from .signals import _short_branch

DAILY = "daily"
FINAL = "final"
VARIANTS = (DAILY, FINAL)

#: The Meta template the card is sent as (D15): a picture header and two
#: text slots, one template for the daily card and the final one. The name
#: is the founder's own submission (issue #16); until Meta approves it a
#: send fails with Meta's 132001 and the job says so, which is the honest
#: state (the brief's `TEMPLATE_NAME` is the precedent).
TEMPLATE_NAME = "faida_scoreboard"
TEMPLATE_LANGUAGE = "en"

#: The template's two text slots (D15): the headline and the freshness line.
PARAMETER_COUNT = 2
PARAMETER_MAX_CHARS = 160

#: What the first line says for a branch with no day of the month loaded:
#: there is no newest day to name, and a card that said nothing would read as
#: a card about nothing.
NO_SALES_LOADED = "No sales loaded yet for {month}."

#: The card's one qualification, ADR 0001 in the staff's own words: the score
#: is the till's, portions and net sales, and nothing else.
CARD_FOOTER = "Scored on what the till prints: portions and net sales."

ROLE_WORDS = (("manager", "Manager"), ("supervisor", "Supervisor"), ("sales", "Sales team"))


def _more_words(count: int) -> str:
    """What the list says when it is longer than the card."""
    return f"and {count} more on the list"


@dataclass(frozen=True)
class ItemLine:
    """One push item as the card draws it: the name, the statement's own
    words for its count, the share of target reached for the bar (None for
    a hole, which draws no bar), whether the target is reached (said in the
    words, and only then also in colour), and the notes that qualify it."""

    name: str
    words: str
    share: Decimal | None
    reached: bool
    hole: str | None
    note: str | None


@dataclass(frozen=True)
class WeekBlock:
    title: str
    items: tuple[ItemLine, ...]
    #: The statement's own note for a week the owner left empty, else None.
    empty_words: str | None


@dataclass(frozen=True)
class FigureLine:
    label: str
    words: str


@dataclass(frozen=True)
class Scoreboard:
    variant: str
    branch_name: str
    title: str
    subtitle: str
    headline: str
    freshness: str
    list_title: str
    weeks: tuple[WeekBlock, ...]
    figures: tuple[FigureLine, ...]
    notes: tuple[str, ...]
    footer: str
    parameters: tuple[str, ...]


# --- the words ------------------------------------------------------------------


def _share(item: ItemScore) -> Decimal | None:
    """How much of the target the portions reach, clipped to the bar: a hole
    has no share, portions below nought (a week of refunds) read as none, and
    a target of nought is reached by the first portion."""
    if item.portions is None:
        return None
    if item.portion_target <= 0:
        return Decimal(1) if item.portions > 0 else Decimal(0)
    return max(Decimal(0), min(Decimal(1), item.portions / item.portion_target))


def _item_line(item: ItemScore) -> ItemLine:
    return ItemLine(
        name=item.name,
        words=item.words,
        share=_share(item),
        reached=item.portions is not None and item.portions >= item.portion_target,
        hole=item.hole,
        note=incentive.no_qty_note(item),
    )


def _week_block(week: WeekScore) -> WeekBlock:
    return WeekBlock(
        title=incentive.week_words(week.window),
        items=tuple(_item_line(item) for item in week.items),
        empty_words=incentive.empty_week_note(week.window) if week.empty else None,
    )


def _split_lines(figures: incentive.Figures, currency: str) -> tuple[FigureLine, ...]:
    """The pool by role, each amount to the fil beside the share it is (D2):
    what each part of the team is owed, on the final card alone."""
    split = figures.split
    if split is None:
        return ()
    amounts = {"manager": split.manager, "supervisor": split.supervisor, "sales": split.sales}
    shares = {
        "manager": split.shares.manager_pct,
        "supervisor": split.shares.supervisor_pct,
        "sales": split.shares.sales_pct,
    }
    return tuple(
        FigureLine(
            f"{words} share, {incentive._pct_plain(shares[role])}%",
            _price_words(amounts[role], currency),
        )
        for role, words in ROLE_WORDS
    )


def _check(name: str, text: str) -> str:
    """A template slot holds one line of at most `PARAMETER_MAX_CHARS`; a
    sentence that broke either would be refused by Meta at send time, which
    is the wrong time to find out."""
    if "\n" in text:
        raise ValueError(f"the {name} slot carries a line break: {text!r}")
    if len(text) > PARAMETER_MAX_CHARS:
        raise ValueError(f"the {name} slot is {len(text)} characters, over {PARAMETER_MAX_CHARS}")
    return text


def compose(
    statement: Statement,
    *,
    branch_name: str,
    today: datetime.date,
    variant: str = DAILY,
    currency: str = "AED",
) -> Scoreboard:
    """One branch's card for one day, out of its statement.

    `today` is the branch's own local date (D13): the day the newest loaded
    day is aged against, and the day whose push week is in view. A daily
    card for a day outside the statement's month raises, because no morning
    enqueues one - the tick only wakes a branch whose scheme month covers
    the date - and a card about a week the month does not hold would be a
    card about nothing.
    """
    if variant not in VARIANTS:
        raise ValueError(f"{variant!r} is not a scoreboard variant: one of {VARIANTS}")
    if variant == FINAL and statement.status != incentive.FINAL:
        raise ValueError("a final card needs an approved statement: nothing is final by accident")
    if variant == DAILY and statement.status == incentive.FINAL:
        raise ValueError("a daily card is not composed on a final statement: the month is closed")

    figures = statement.figures
    short = _short_branch(branch_name)
    month_words = incentive.month_words(statement.month)
    freshness = freshness_sentence(statement.newest_loaded, today) or NO_SALES_LOADED.format(
        month=month_words
    )
    title = f"{short} scoreboard"
    subtitle = f"{month_words}, {statement.status_words}"
    notes: list[str] = []

    if variant == DAILY:
        week = next((w for w in figures.weeks if w.window.start <= today <= w.window.end), None)
        if week is None:
            raise ValueError(f"no push week of {month_words} holds {today.isoformat()}")
        headline = f"{short} scoreboard, {_weekday_date(today)}"
        list_title = f"This week's push list, {incentive.week_words(week.window)}"
        weeks = (_week_block(week),)
        lines = (
            FigureLine(f"Net sales, {statement.month.strftime('%B')} so far", figures.net_words),
            FigureLine(f"{incentive.BONUS.capitalize()} pool so far", figures.pool_words),
        )
    else:
        headline = f"{short}: {month_words} {incentive.BONUS}, final"
        list_title = "The month's push lists"
        weeks = tuple(_week_block(week) for week in figures.weeks)
        lines = (
            FigureLine(f"Net sales, {month_words}", figures.net_words),
            FigureLine(f"{incentive.BONUS.capitalize()} pool", figures.pool_words),
            *_split_lines(figures, currency),
        )
        if statement.till_now_says_otherwise:
            notes.append(incentive.TILL_NOTE)
    if (cap := incentive.cap_note(figures, currency)) is not None:
        notes.append(cap)

    return Scoreboard(
        variant=variant,
        branch_name=branch_name,
        title=title,
        subtitle=subtitle,
        headline=headline,
        freshness=freshness,
        list_title=list_title,
        weeks=weeks,
        figures=lines,
        notes=tuple(notes),
        footer=CARD_FOOTER,
        parameters=(_check("headline", headline), _check("freshness", freshness)),
    )


def sentences(card: Scoreboard) -> list[str]:
    """Every string the card carries, for the banned-words test and the
    printed card."""
    out = [card.title, card.subtitle, card.headline, card.freshness, card.list_title]
    for week in card.weeks:
        out.append(week.title)
        if week.empty_words is not None:
            out.append(week.empty_words)
        for item in week.items:
            out += [item.name, item.words]
            out += [text for text in (item.hole, item.note) if text is not None]
    for line in card.figures:
        out += [line.label, line.words]
    out += [*card.notes, card.footer, *card.parameters]
    return out


def render(card: Scoreboard) -> str:
    """The card as lines of text: what the print command shows beside the
    picture, and what a test reads to prove the words."""
    lines = [card.headline, card.freshness, "", card.title, card.subtitle, "", card.list_title]
    for week in card.weeks:
        if len(card.weeks) > 1:
            lines.append(week.title)
        if week.empty_words is not None:
            lines.append(f"  {week.empty_words}")
        for item in week.items:
            lines.append(f"  {item.name}: {item.words}")
            if item.note is not None:
                lines.append(f"    {item.note}")
    lines.append("")
    for line in card.figures:
        lines.append(f"{line.label}: {line.words}")
    if card.notes:
        lines.append("")
        lines += card.notes
    lines += ["", card.footer]
    return "\n".join(lines)


def card_path(tenant_id: str, day: datetime.date, branch_id: str, *, variant: str = DAILY) -> str:
    """Where a card is stored, immutably, before anything leaves the building
    (D15): under the tenant, the day and the branch, the final card named as
    such so the morning's own key on the approval day is never taken."""
    suffix = "" if variant == DAILY else f"-{variant}"
    return f"{tenant_id}/scoreboards/{day.isoformat()}/{branch_id}{suffix}.png"
