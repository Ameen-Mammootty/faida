"""The quality word: PRD §24's vocabulary minus `verified`, its precedence and
its English, owned once (C9). Every reader asks this module, so a consumer's
test asserts only that the worst input's word came through."""

import pytest

from faida_api import quality
from faida_api.quality import Quality, total_of, word, worst


def test_the_four_words_and_never_verified():
    assert [q.value for q in Quality] == [
        "reliable_with_limitations",
        "estimated",
        "incomplete",
        "unavailable",
    ]
    assert "verified" not in [q.value for q in Quality]


def test_the_precedence_is_worst_first():
    assert quality.WORST_FIRST == (
        Quality.UNAVAILABLE,
        Quality.INCOMPLETE,
        Quality.ESTIMATED,
        Quality.RELIABLE,
    )
    assert worst(Quality.RELIABLE) is Quality.RELIABLE
    assert worst(Quality.RELIABLE, Quality.ESTIMATED) is Quality.ESTIMATED
    assert worst(Quality.ESTIMATED, Quality.RELIABLE) is Quality.ESTIMATED
    assert worst(Quality.ESTIMATED, Quality.INCOMPLETE, Quality.RELIABLE) is Quality.INCOMPLETE
    assert worst(Quality.INCOMPLETE, Quality.UNAVAILABLE) is Quality.UNAVAILABLE
    assert worst(*Quality) is Quality.UNAVAILABLE


def test_worst_of_nothing_is_a_bug_not_a_word():
    with pytest.raises(ValueError):
        worst()


def test_a_total_over_rows_treats_one_hole_as_incomplete():
    """The 2026-09-04 call: a total reads unavailable only when every row is,
    incomplete when any row is a hole among others, otherwise the worst."""
    assert total_of([]) is Quality.UNAVAILABLE
    assert total_of([Quality.UNAVAILABLE, Quality.UNAVAILABLE]) is Quality.UNAVAILABLE
    assert total_of([Quality.UNAVAILABLE, Quality.RELIABLE]) is Quality.INCOMPLETE
    assert total_of([Quality.INCOMPLETE, Quality.ESTIMATED]) is Quality.INCOMPLETE
    assert total_of([Quality.ESTIMATED, Quality.RELIABLE]) is Quality.ESTIMATED
    assert total_of(q for q in [Quality.RELIABLE, Quality.RELIABLE]) is Quality.RELIABLE


def test_the_word_as_a_person_reads_it():
    assert word(Quality.RELIABLE) == "reliable with limitations"
    assert word(Quality.ESTIMATED) == "estimated"
    assert word(Quality.INCOMPLETE) == "incomplete"
    assert word(Quality.UNAVAILABLE) == "unavailable"
    assert "_" not in "".join(word(q) for q in Quality)


def test_the_wire_value_is_the_enum():
    """A word read back off a payload compares equal to its member, so a
    reader never keeps a second string literal for it."""
    assert Quality("estimated") is Quality.ESTIMATED
    assert Quality.ESTIMATED == "estimated"
