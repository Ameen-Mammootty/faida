"""The answer key for reading a till export, from the API's side.

`fixtures/till_keys.json` is shared with the web loader's own test
(`apps/web/src/lib/__tests__/tillKeys.test.ts`): the API owns every rule in
it, and the loader carries a copy so its preview is instant. This file pins
that the key says what the API does; the web test pins that the copy agrees.
A drift is a failing test in one language or the other, never a loader that
asks the same question forever (2026-09-26: "AL-NAHDA" after "AL NAHDA").
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import HTTPException

from faida_api import takings
from faida_api.sales import _signed_number

KEY = json.loads((Path(__file__).parent / "fixtures" / "till_keys.json").read_text("utf-8"))

PLACES = {"amount": 2, "quantity": 3}


def _day(day: dict) -> tuple:
    return takings.day_key(
        day["granularity"],
        day["basis"],
        [
            (
                line["name"],
                line["code"],
                None if line["qty"] is None else Decimal(line["qty"]),
                Decimal(line["amount"]),
            )
            for line in day["lines"]
        ],
        None if day["amount"] is None else Decimal(day["amount"]),
    )


@pytest.mark.parametrize("case", KEY["names"], ids=lambda case: case["why"])
def test_a_name_keys_as_the_answer_key_says(case):
    assert takings.name_key(case["name"]) == case["key"]


@pytest.mark.parametrize("case", KEY["days"], ids=lambda case: case["why"])
def test_two_days_are_the_same_day_exactly_when_the_answer_key_says(case):
    assert (_day(case["a"]) == _day(case["b"])) is case["same"]


@pytest.mark.parametrize("case", KEY["numbers"], ids=lambda case: f"{case['what']} {case['value']}")
def test_a_number_is_accepted_exactly_when_the_answer_key_says(case):
    try:
        _signed_number(case["value"], what=case["what"], places=PLACES[case["what"]], example="1")
        accepted = True
    except HTTPException:
        accepted = False
    assert accepted is case["accepted"]
