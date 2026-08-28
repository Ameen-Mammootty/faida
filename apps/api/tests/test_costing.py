"""M5: cost per base unit (costing.py).

Pure arithmetic over the shapes price memory actually stores, so every case
here is a real invoice line pattern from the corpus: a delivery note that
prices per kilo, a cash-and-carry receipt that prices per carton and prints
the pack in the name, a tray of eggs with no unit anyone can convert.
"""

from decimal import Decimal

from faida_api.costing import Blocked, Conversion, UnitCost, unit_cost


def d(value: str) -> Decimal:
    return Decimal(value)


# --- priced per measure: the unit column is the answer -----------------------


def test_price_per_kilo_becomes_price_per_gram():
    cost = unit_cost(d("12.00"), unit="kg")
    assert isinstance(cost, UnitCost)
    assert cost.per_base == d("0.01200000")
    assert cost.base_unit == "g"
    assert cost.basis == "unit"


def test_a_pack_size_never_divides_a_price_that_is_already_per_unit():
    """ "12.00 per kg" of a 2.5 kg bag is 12.00 per kg, not 4.80. Dividing
    twice is the silent error this module exists to prevent."""
    cost = unit_cost(d("12.00"), unit="kg", pack_size="2.5kg")
    assert isinstance(cost, UnitCost)
    assert cost.per_base == d("0.01200000")


def test_litres_and_pieces_reduce_to_their_own_bases():
    litre = unit_cost(d("9.00"), unit="L")
    piece = unit_cost(d("1.50"), unit="pcs")
    assert isinstance(litre, UnitCost) and litre.base_unit == "ml"
    assert litre.per_base == d("0.00900000")
    assert isinstance(piece, UnitCost) and piece.base_unit == "pc"
    assert piece.per_base == d("1.50000000")


def test_arabic_unit_words_are_units_too():
    cost = unit_cost(d("12.00"), unit="كجم")
    assert isinstance(cost, UnitCost) and cost.base_unit == "g"


# --- priced per pack: the pack size is the answer ----------------------------


def test_carton_of_a_stated_pack_size_divides_by_the_pack():
    cost = unit_cost(d("50.50"), unit="ctn", pack_size="2.5kg")
    assert isinstance(cost, UnitCost)
    assert cost.per_base == d("0.02020000")
    assert cost.basis == "pack_size"
    assert cost.pack_display == "2.5 kg"


def test_pack_size_printed_in_the_item_name_counts():
    """A till receipt has no pack-size column and puts the pack in the name -
    the same rule matching.snap_item already applies."""
    cost = unit_cost(d("25.00"), unit=None, pack_size=None, item_name="RICE BASM 5KG")
    assert isinstance(cost, UnitCost)
    assert cost.per_base == d("0.00500000")
    assert cost.basis == "item_name"


def test_pack_size_column_wins_over_the_name():
    cost = unit_cost(d("25.00"), unit="bag", pack_size="5kg", item_name="RICE BASM 20KG")
    assert isinstance(cost, UnitCost)
    assert cost.per_base == d("0.00500000")
    assert cost.basis == "pack_size"


def test_two_kilos_and_two_thousand_grams_cost_the_same():
    """The harmonization the whole layer rests on: one shelf, one cost,
    whatever the supplier printed."""
    printed_kg = unit_cost(d("20.00"), unit="ctn", pack_size="2kg")
    printed_g = unit_cost(d("20.00"), unit="ctn", pack_size="2000 g")
    assert isinstance(printed_kg, UnitCost) and isinstance(printed_g, UnitCost)
    assert printed_kg.per_base == printed_g.per_base


# --- blocked, never guessed --------------------------------------------------


def test_a_carton_of_nothing_stated_is_blocked_not_guessed():
    assert unit_cost(d("50.50"), unit="ctn") is Blocked.UNKNOWN_PACK


def test_two_containers_never_cancel():
    """'1 box' inside a carton says nothing about mass: containers keep their
    own dimension in units.py precisely so this stays blocked."""
    assert unit_cost(d("50.50"), unit="ctn", pack_size="1 box") is Blocked.UNKNOWN_PACK


def test_a_name_naming_two_different_packs_asks_rather_than_picks():
    cost = unit_cost(d("30.00"), item_name="OIL 5L CASE OF 4 x 1L")
    assert cost is Blocked.AMBIGUOUS_PACK


def test_the_same_pack_twice_in_a_name_is_not_ambiguous():
    cost = unit_cost(d("10.00"), item_name="MILK 2KG POWDER 2000G")
    assert isinstance(cost, UnitCost)
    assert cost.per_base == d("0.00500000")


def test_no_price_means_no_cost():
    assert unit_cost(None, unit="kg") is Blocked.NO_PRICE
    assert unit_cost(d("0"), unit="kg") is Blocked.NO_PRICE


def test_an_unknown_unit_word_falls_through_to_the_pack_size():
    cost = unit_cost(d("50.00"), unit="qintar", pack_size="10kg")
    assert isinstance(cost, UnitCost)
    assert cost.per_base == d("0.00500000")


# --- a human's conversion outranks everything --------------------------------


def test_a_stated_conversion_unblocks_a_carton():
    cost = unit_cost(d("120.00"), unit="ctn", conversion=Conversion(d("10000"), "g"))
    assert isinstance(cost, UnitCost)
    assert cost.per_base == d("0.01200000")
    assert cost.basis == "conversion"
    assert "stated" in cost.pack_display


def test_a_stated_conversion_beats_a_printed_pack_size():
    """A carton printed '1 kg' that actually holds twelve of them is exactly
    the case a human is here to correct."""
    cost = unit_cost(
        d("120.00"), unit="ctn", pack_size="1kg", conversion=Conversion(d("12000"), "g")
    )
    assert isinstance(cost, UnitCost)
    assert cost.per_base == d("0.01000000")


def test_costs_stay_decimal_and_never_go_float():
    cost = unit_cost(d("0.35"), unit="ctn", pack_size="3kg")
    assert isinstance(cost, UnitCost)
    assert isinstance(cost.per_base, Decimal)
    # 0.35 / 3000 = 0.0001166..., quantized rather than left to grow digits.
    assert cost.per_base == d("0.00011667")
