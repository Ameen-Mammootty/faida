"""The quality word - the one owner of PRD §24's vocabulary (C9).

Every derived figure the product shows carries one of four words, and this
module is the only place that knows the words, their precedence and their
English. A cost per base unit, a plate, a period row, a contribution, a usage
row, a signal, the brief and the dashboard's freshness all ask here, so a
reader's own test asserts only that the worst input's word came through and
never restates the order.

`verified` is absent on purpose and a test pins its absence: nothing anywhere
corroborates a pack size or cross-checks a till's figures, so a figure that
claimed to be verified would be the old platform's dominant failure - a
confidently wrong number nobody was invited to check - reappearing in the
layer C9 exists to protect.

Which of the four a layer may produce is that layer's rule, pinned by its own
tests: a cost is reliable or estimated; a plate is never unavailable (that is
a fact about a branch's sales); a signal never fires on a word it does not
trust. Coverage says *costed*, never *complete* (C11.8); that word is not
this module's.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum


class Quality(StrEnum):
    """PRD §24's vocabulary minus the word we cannot earn. The values are the
    wire's and the database's; `word` is how a person reads them."""

    RELIABLE = "reliable_with_limitations"
    ESTIMATED = "estimated"
    INCOMPLETE = "incomplete"
    UNAVAILABLE = "unavailable"


#: Precedence, worst first (C9 amended): a derived number is never greener
#: than its worst input.
WORST_FIRST: tuple[Quality, ...] = (
    Quality.UNAVAILABLE,
    Quality.INCOMPLETE,
    Quality.ESTIMATED,
    Quality.RELIABLE,
)

_RANK = {quality: rank for rank, quality in enumerate(WORST_FIRST)}


def worst(*qualities: Quality) -> Quality:
    """The word a figure derived from these inputs carries (C9). At least one
    input: a figure with no inputs has no word, and asking for one is a bug."""
    if not qualities:
        raise ValueError("worst() of no qualities")
    return min(qualities, key=_RANK.__getitem__)


def total_of(qualities: Iterable[Quality]) -> Quality:
    """The word a total over rows carries (the 2026-09-04 call, Decision Log):
    *unavailable* only when every row is - or there are none - *incomplete*
    when any row is unavailable or incomplete among others, because a row with
    nothing loaded is a hole in the total the way a missing day is a hole in a
    row, and otherwise the worst of the rows."""
    rows = list(qualities)
    if not rows or all(q is Quality.UNAVAILABLE for q in rows):
        return Quality.UNAVAILABLE
    if any(q in (Quality.UNAVAILABLE, Quality.INCOMPLETE) for q in rows):
        return Quality.INCOMPLETE
    return worst(*rows)


def word(quality: Quality) -> str:
    """The C9 vocabulary as a person reads it: "reliable with limitations",
    "estimated", "incomplete", "unavailable". The underscores are how it is
    stored, not how it is said."""
    return quality.value.replace("_", " ")
