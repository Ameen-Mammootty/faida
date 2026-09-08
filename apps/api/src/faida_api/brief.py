"""M10 WP-100: the deterministic filler - the morning brief composed from two
dashboard payloads and nothing else (Docs/M10_DECOMPOSITION.md §3 C15.1, C15.2,
C15.7 and C15.9; §3.1's shapes; plan.md §7.2).

The brief says the founder's seven things in the founder's order: the day, the
latest day's sales, the month so far, what the materials cost, that cost's
share of the sales it covers, one row per branch, the items that earn most and
least, and the biggest supplier price rises.

Two payloads go in - the month-to-date read (the first of the newest loaded
day's month to that day) and the default 28-day read - and one `Brief` comes
out. The figures, the table and the items are the month's; the spikes are the
28 days', because a spike is a different question from a month and the two
reads are the same function with a different window (C15.1).

Nothing here is generated and nothing is re-worded. Where the payload carries
a sentence - `freshness.sentence`, each price move's `sentence` - the brief
uses it byte for byte; where it carries only numbers the brief composes one
fixed shape, once, and the card and the message body read the same pieces, so
one figure can never be quoted in two sets of words. The four figures are
composed as `Kpi` pieces first and the five text lines are built **from those
pieces**, so the tile on the picture card and the line under it are the same
number by construction.

Pure by design, in `signals.py`'s shape: no clock, no database, no HTTP, no
I/O. It is handed dicts exactly as `GET /api/dashboard` serialises them - money
and percentages as strings, dates ISO - and it hands back words. That is what
makes every line testable without a database and what makes the send job a
thin wrapper: read, compose, send.

The money words are `contribution._money_words`, the whole-percent words
`contribution._pct_words`, the branch name `signals._short_branch`, the dates
`ratio.window_words`, `ratio._short_date` and `dashboard._weekday_date`, and
the price gate `PRICE_ALERT_MIN_PCT` - imported and called, never copied, so a
rounding rule can only ever change in one place.

The display rules hold here as they do on a screen (CLAUDE.md §3): whole
dirhams rounded half up, percentages to a tenth, the label "materials share of
costed sales" and never food cost, contribution never called profit, nothing
called verified, and a figure the read withholds said in words with the read's
own note - never a zero, never a blank slot.
"""

import datetime
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .contribution import _money_words, _pct_words
from .dashboard import _weekday_date
from .extraction.constants import PRICE_ALERT_MIN_PCT
from .ratio import PCT_QUANTUM, Quality, Window, _short_date, window_words
from .signals import _short_branch

#: The template as Meta holds it (C15.11): one template, one language, edited
#: only through Meta's review. The name and the language travel with the body
#: so the send job never spells either of them a second time.
TEMPLATE_NAME = "faida_daily_brief"
TEMPLATE_LANGUAGE = "en"

#: Shape A of §3.1, verbatim: five body variables under bold fixed labels, the
#: branch table, the items and the spikes carried by the picture header. Fixed
#: text opens and closes it and no two variables touch, which is what Meta's
#: review asks for; the labels are `*bold*` and the values carry no markup, so
#: a supplier name with an asterisk in it cannot toggle bold mid-line.
TEMPLATE_BODY = (
    "*Faida morning brief*\n"
    "{{1}}\n"
    "\n"
    "*Latest day:* {{2}}\n"
    "*Month to date:* {{3}}\n"
    "*Materials used:* {{4}}\n"
    "*Materials share:* {{5}}\n"
    "\n"
    "The card above carries every branch, the items and the price spikes. "
    "Every figure opens to its source on the dashboard."
)

#: Asserted against the body by `render` so a template edited to a different
#: number of variables fails in a test here, rather than as Meta's 132000 at
#: seven in the morning.
PARAMETER_COUNT = 5

#: Meta's own rule for a parameter value is no newline, no tab and no run of
#: four spaces; the character cap is the filler's own, so a long supplier note
#: is a bug this module raises on rather than a message truncated on a phone.
PARAMETER_MAX_CHARS = 160

#: Meta caps the rendered body once the values are in.
BODY_MAX_CHARS = 1024

#: The line the picture card closes with: the one qualification the whole card
#: needs (C12.7 - the share is of costed sales, never grossed up) and the tap
#: that answers everything else.
CARD_FOOTER = (
    "Materials share is of the sales that are costed, never of all sales. "
    "Every figure opens to its source on the dashboard."
)

#: Past `dashboard.FRESHNESS_STALE_DAYS` the read's freshness quality turns
#: `estimated`, and the header says why in the brief's own words (P4). The
#: sentence itself is never re-worded: this is appended after it.
STALE_CLAUSE = " Figures below are estimated: the sales are older than a week."

#: What a branch row prints where it has no figure: a hole is a hole, never a
#: zero (C15.2).
HOLE = "-"

#: What the materials lines say when there is no note to give.
NO_NOTE = "no item costed yet"

_WHOLE = Decimal("1")
_PLACEHOLDER = re.compile(r"\{\{(\d+)\}\}")


# --- the pieces -----------------------------------------------------------------


@dataclass(frozen=True)
class Kpi:
    """One of the four figures, in three pieces: the fixed label, the figure
    itself, and the words that qualify it. The picture card draws it as a tile
    and the message body builds its line out of the same two strings, so the
    tile and the line can never disagree."""

    label: str
    value: str
    sub: str


@dataclass(frozen=True)
class BranchRow:
    """One branch on the card's table: the latest day, the month so far and
    the materials share, with the words beside each figure because a branch
    that loaded nothing prints a hole and not a nought."""

    name: str
    latest_day: Decimal | None
    month: Decimal | None
    materials_share: str | None
    latest_day_words: str
    month_words: str
    materials_share_words: str


@dataclass(frozen=True)
class ItemLine:
    """A menu item and the money it kept over the month, in the dashboard's own
    order and with the dashboard's own money words."""

    name: str
    money: Decimal
    money_words: str


@dataclass(frozen=True)
class SpikeLine:
    """A supplier price rise: the panel's own sentence, byte for byte, and the
    brief's own fixed clause for what is at stake on the sales since it landed.
    The two are separate because the sentence is the wire's and the clause is
    ours, and neither may be re-worded into the other."""

    sentence: str
    money_clause: str


@dataclass(frozen=True)
class Brief:
    """One morning's brief for one recipient: the five text lines that fill the
    template's variables, the four figures as pieces for the card, and the
    table, the two item lists and the spikes the card draws.

    `quiet` is the whole of it when nothing is loaded (C15.7): no message is
    sent, because there is nothing to say and a template costs money.
    """

    quiet: bool
    #: The five lines, in the template's order. Each is one parameter value.
    day: str
    latest_day: str
    month_to_date: str
    materials_used: str
    materials_share: str
    #: The same four figures the last four lines carry, as tiles.
    kpis: tuple[Kpi, ...]
    rows: tuple[BranchRow, ...]
    earning_most: tuple[ItemLine, ...]
    earning_least: tuple[ItemLine, ...]
    #: Menu items with sales the read could not cost; named on the card when
    #: it is not zero, so a short list says why it is short.
    uncosted: int
    spikes: tuple[SpikeLine, ...]
    #: The sentence that stands in for the spikes when nothing moved.
    no_spikes: str | None
    parameters: tuple[str, ...]
    card_footer: str


# --- words ----------------------------------------------------------------------


def _whole(amount: Decimal) -> Decimal:
    """Whole dirhams, rounded half up - the display rule the headline figures
    and `contribution._money_words` share."""
    return amount.quantize(_WHOLE, rounding=ROUND_HALF_UP)


def _dirhams(amount: Decimal) -> str:
    """The figure `_money_words` prints without the currency word, for a table
    cell whose column header carries the currency once. The rounding is that
    function's own: it is called and its (empty) currency word stripped, so
    the cell can never round differently from the line above it."""
    return _money_words(amount, "").lstrip()


def _money(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


def _date(value: str) -> datetime.date:
    return datetime.date.fromisoformat(value)


def _window(payload: dict) -> Window:
    return Window(_date(payload["from"]), _date(payload["to"]))


def _share_of_sales(contribution_pct: str | None) -> Decimal | None:
    """The materials share: what a hundred dirhams of costed sales left behind
    in materials, which is the complement of the share the dashboard keeps.
    Never grossed up to all sales, and never named food cost."""
    if contribution_pct is None:
        return None
    return (Decimal(100) - Decimal(contribution_pct)).quantize(PCT_QUANTUM, rounding=ROUND_HALF_UP)


def _first_note(total: dict) -> str:
    notes = total.get("contribution_notes") or []
    return notes[0] if notes else NO_NOTE


def _quality_clause(total: dict) -> str:
    """The quality word rides on the line it qualifies, in the brief's own
    fixed clause and with the read's own first note (C15.2). A withheld figure
    takes no clause: its note already says why there is no figure, and saying
    it twice reads like two different problems."""
    quality = total.get("contribution_quality")
    if quality == Quality.ESTIMATED.value:
        return " (estimated)"
    if quality == Quality.INCOMPLETE.value:
        return f" (incomplete: {_first_note(total)})"
    return ""


# --- the four figures -----------------------------------------------------------


def _latest_day_kpi(latest: dict, currency: str) -> Kpi:
    return Kpi(
        label="Latest day",
        value=_money_words(Decimal(latest["net_sales"]), currency),
        sub=_weekday_date(_date(latest["date"])),
    )


def _month_kpi(total: dict, league: list[dict], currency: str) -> Kpi:
    """The month so far, with the days the chain's clipped windows actually
    cover named beside it: the figure is only ever of the days that are loaded,
    so the line says which they are. The widest window is taken over the
    branches that loaded something; a branch whose window is not that one
    loaded fewer days, and the line says so without naming it, because a chain
    of twelve would otherwise spend the line on branch names."""
    windows = [_window(row["window"]) for row in league if row.get("net_sales") is not None]
    value = _money_words(Decimal(total["net_sales"]), currency)
    if not windows:
        return Kpi(label="Month to date", value=value, sub="")
    widest = Window(min(w.start for w in windows), max(w.end for w in windows))
    sub = f"{window_words(widest)} loaded"
    if any(_window(row["window"]) != widest for row in league):
        sub += "; some branches fewer"
    return Kpi(label="Month to date", value=value, sub=sub)


def _materials_used_kpi(total: dict, currency: str) -> Kpi:
    cost = _money(total.get("cost"))
    if cost is None:
        return Kpi(label="Materials used", value="not available", sub=_first_note(total))
    return Kpi(
        label="Materials used",
        value=_money_words(cost, currency),
        sub="at the latest prices" + _quality_clause(total),
    )


def _materials_share_kpi(total: dict, currency: str) -> Kpi:
    share = _share_of_sales(total.get("contribution_pct"))
    costed = _money(total.get("costed_sales"))
    if share is None or costed is None:
        return Kpi(label="Materials share", value="not available", sub=_first_note(total))
    covered = _pct_words(Decimal(total["costed_share_pct"]))
    return Kpi(
        label="Materials share",
        value=f"{share}%",
        sub=f"of {_money_words(costed, currency)} costed · {covered} of sales"
        + _quality_clause(total),
    )


# --- the table, the lists and the spikes ----------------------------------------


def _rows(month: dict) -> tuple[BranchRow, ...]:
    """One row per branch, in the league's order - kept share lowest first, the
    order the dashboard ranks them in, so the card and the screen read the same
    way down the page."""
    latest = month.get("latest_day") or {}
    on_day = {b["branch_id"]: b for b in (latest.get("branches") or [])}
    rows = []
    for row in month.get("league") or []:
        day_sales = _money(on_day.get(row["branch_id"], {}).get("net_sales"))
        month_sales = _money(row.get("net_sales"))
        share = _share_of_sales(row.get("contribution_pct"))
        rows.append(
            BranchRow(
                name=_short_branch(row.get("branch_name") or ""),
                latest_day=None if day_sales is None else _whole(day_sales),
                month=None if month_sales is None else _whole(month_sales),
                materials_share=None if share is None else str(share),
                latest_day_words=HOLE if day_sales is None else _dirhams(day_sales),
                month_words=HOLE if month_sales is None else _dirhams(month_sales),
                materials_share_words=HOLE if share is None else f"{share}%",
            )
        )
    return tuple(rows)


def _item_line(row: dict, currency: str) -> ItemLine:
    money = Decimal(row["contribution"])
    return ItemLine(
        name=row["menu_item_name"], money=money, money_words=_money_words(money, currency)
    )


def _items(month: dict, currency: str) -> tuple[tuple[ItemLine, ...], tuple[ItemLine, ...], int]:
    """The three that earned the most and the three that earned the least, by
    money kept, out of the dashboard's own ordering (most first).

    `items.bottom` is the tail of the same list and is empty when five or fewer
    items are costed; then the worst three come off the end of `items.top`
    instead, and an item already named among the best is never named again
    among the worst - with four costed items the second list is one item long,
    which is honest, where repeating one would read as two findings.

    Either way the worst list is printed worst first: it is read as an answer
    to "what is dragging", and the answer belongs at the top of it.
    """
    items = month.get("items") or {}
    top = [row for row in (items.get("top") or []) if row.get("contribution") is not None]
    bottom = [row for row in (items.get("bottom") or []) if row.get("contribution") is not None]
    most = tuple(_item_line(row, currency) for row in top[:3])
    named = {row["menu_item_id"] for row in top[:3]}
    tail = list(reversed(bottom[-3:])) if bottom else list(reversed(top))
    least = tuple(_item_line(row, currency) for row in tail if row["menu_item_id"] not in named)[:3]
    uncosted = len(items.get("all") or []) - int(items.get("count") or 0)
    return most, least, uncosted


def _spikes(window: dict, currency: str) -> tuple[tuple[SpikeLine, ...], str | None]:
    """The three biggest supplier price rises of the 28 days, the panel's own
    sentences and the panel's own money. The moves arrive ranked by the money
    they moved whichever way; the brief takes the rises only, keeps that
    ranking, and says in its own fixed clause what is at stake on the sales
    since each one landed. A rise nothing was sold after says so rather than
    printing a nought."""
    block = window.get("price_moves") or {}
    rises = [move for move in (block.get("moves") or []) if move.get("direction") == "up"]
    rises.sort(key=lambda move: _money(move.get("money_at_stake")) or Decimal(0), reverse=True)
    spikes = []
    for move in rises[:3]:
        money = _money(move.get("money_at_stake")) or Decimal(0)
        clause = (
            f"{_money_words(money, currency)} at stake on sales since."
            if money > 0
            else "Nothing sold since."
        )
        spikes.append(SpikeLine(sentence=move["sentence"], money_clause=clause))
    if spikes:
        return tuple(spikes), None
    gate = _pct_words(PRICE_ALERT_MIN_PCT * 100)
    since = _short_date(_date(window["period"]["from"]))
    return (), f"none of {gate} or more since {since}."


# --- the parameters -------------------------------------------------------------


def _check(name: str, text: str) -> str:
    """Meta's rules for a parameter value, checked here so a violation is a
    named failure in a test rather than a rejected send or a truncated
    message (C15.9)."""
    for bad, what in (("\n", "a line break"), ("\r", "a line break"), ("\t", "a tab")):
        if bad in text:
            raise ValueError(f"the {name} line carries {what}: {text!r}")
    if "    " in text:
        raise ValueError(f"the {name} line carries four consecutive spaces: {text!r}")
    if len(text) > PARAMETER_MAX_CHARS:
        raise ValueError(
            f"the {name} line is {len(text)} characters, over the "
            f"{PARAMETER_MAX_CHARS}-character cap: {text!r}"
        )
    return text


def _parameters(lines: dict[str, str]) -> tuple[str, ...]:
    if len(lines) != PARAMETER_COUNT:
        raise ValueError(f"the brief has {len(lines)} lines, not {PARAMETER_COUNT}")
    return tuple(_check(name, text) for name, text in lines.items())


# --- the brief ------------------------------------------------------------------


def _quiet() -> Brief:
    return Brief(
        quiet=True,
        day="",
        latest_day="",
        month_to_date="",
        materials_used="",
        materials_share="",
        kpis=(),
        rows=(),
        earning_most=(),
        earning_least=(),
        uncosted=0,
        spikes=(),
        no_spikes=None,
        parameters=(),
        card_footer=CARD_FOOTER,
    )


def compose(month: dict, window: dict, *, currency: str = "AED") -> Brief:
    """One morning's brief out of two payloads of the same read (C15.1).

    `month` is the month-to-date read - the first of the newest loaded day's
    month to that day - and gives the day, the four figures, the branch table
    and the items. `window` is the default 28-day read and gives the price
    spikes, and nothing else. Both are read for the same tenant on the same
    morning, so their freshness is the same sentence.

    When the read has nothing loaded the brief is quiet and no message is sent
    (C15.7): there is nothing to say and a template costs money.
    """
    freshness = month.get("freshness") or {}
    sentence = freshness.get("sentence")
    latest = month.get("latest_day")
    if sentence is None or latest is None:
        return _quiet()

    total = month["total"]
    league = list(month.get("league") or [])

    day = sentence + (STALE_CLAUSE if freshness.get("quality") == Quality.ESTIMATED.value else "")
    latest_kpi = _latest_day_kpi(latest, currency)
    month_kpi = _month_kpi(total, league, currency)
    used_kpi = _materials_used_kpi(total, currency)
    share_kpi = _materials_share_kpi(total, currency)

    # The lines are built out of the tiles, so a figure has one source.
    latest_line = f"{latest_kpi.value} on {latest_kpi.sub}"
    month_line = f"{month_kpi.value} ({month_kpi.sub})" if month_kpi.sub else month_kpi.value
    if used_kpi.value == "not available":
        used_line = f"{used_kpi.value} ({used_kpi.sub})"
    else:
        used_line = f"{used_kpi.value} {used_kpi.sub}"
    if share_kpi.value == "not available":
        share_line = f"{share_kpi.value} ({share_kpi.sub})"
    else:
        covered = _pct_words(Decimal(total["costed_share_pct"]))
        costed = _money_words(Decimal(total["costed_sales"]), currency)
        share_line = (
            f"{share_kpi.value} of the {costed} costed ({covered} of sales)"
            + _quality_clause(total)
        )

    most, least, uncosted = _items(month, currency)
    spikes, no_spikes = _spikes(window, currency)
    return Brief(
        quiet=False,
        day=day,
        latest_day=latest_line,
        month_to_date=month_line,
        materials_used=used_line,
        materials_share=share_line,
        kpis=(latest_kpi, month_kpi, used_kpi, share_kpi),
        rows=_rows(month),
        earning_most=most,
        earning_least=least,
        uncosted=uncosted,
        spikes=spikes,
        no_spikes=no_spikes,
        parameters=_parameters(
            {
                "day": day,
                "latest day": latest_line,
                "month to date": month_line,
                "materials used": used_line,
                "materials share": share_line,
            }
        ),
        card_footer=CARD_FOOTER,
    )


def render(brief: Brief) -> str:
    """The template body with the values in, as the phone shows it under the
    card. Not what is sent - the send passes the parameters and Meta renders
    the approved body - but the same string, which is what the dry run prints
    and what the tests read to prove the words."""
    if brief.quiet:
        raise ValueError("a quiet brief has nothing to render: nothing is sent (C15.7)")
    slots = _PLACEHOLDER.findall(TEMPLATE_BODY)
    if len(slots) != PARAMETER_COUNT:
        raise ValueError(f"the template body carries {len(slots)} variables, not {PARAMETER_COUNT}")
    if len(brief.parameters) != PARAMETER_COUNT:
        raise ValueError(
            f"the brief carries {len(brief.parameters)} parameters, not {PARAMETER_COUNT}"
        )
    body = TEMPLATE_BODY
    for index, value in enumerate(brief.parameters, start=1):
        body = body.replace(f"{{{{{index}}}}}", value)
    if len(body) > BODY_MAX_CHARS:
        raise ValueError(
            f"the rendered body is {len(body)} characters, over Meta's {BODY_MAX_CHARS}"
        )
    return body
