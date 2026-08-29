"""The units dictionary and pack-size harmonizing (plan.md §5 layer 4).

Two pack sizes that describe the same pack must compare equal however they
were printed, because the catalog and the price history are keyed on that
judgement.
"""

import pytest

from faida_api.extraction.units import (
    Dimension,
    canonical_unit,
    find_all,
    first_printed,
    parse,
    same_pack_size,
)


@pytest.mark.parametrize(
    ("printed", "quantity", "unit"),
    [
        ("2 kg", "2", "kg"),
        ("2KG", "2", "kg"),
        ("500 g", "500", "g"),
        ("2.5 kg", "2.5", "kg"),
        ("1 L", "1", "l"),
        ("750ml", "750", "ml"),
        ("12 pcs", "12", "pc"),
        ("1 dozen", "1", "dz"),
        ("6 cartons", "6", "ctn"),
        ("2 كجم", "2", "kg"),
        ("500 جم", "500", "g"),
        # A thermal receipt truncates "5KG" when the column runs out. TH-01
        # prints "TOM CRUSH 2.5K" and the catalog has to see 2.5 kg.
        ("2.5K", "2.5", "kg"),
    ],
)
def test_printed_pack_sizes_parse_to_one_canonical_unit(printed, quantity, unit):
    pack = parse(printed)
    assert pack is not None
    assert str(pack.quantity) == quantity
    assert pack.unit.canonical == unit


def test_the_same_pack_printed_differently_is_one_pack():
    """The point of the whole module: read as two, the catalog doubles, the
    price history splits, and a supplier who changed only their printing fires
    a price alert."""
    assert same_pack_size("2 kg", "2000 g")
    assert same_pack_size("2.5K", "2.5 kg")
    assert same_pack_size("0.5 L", "500ml")
    assert same_pack_size("1 dozen", "12 pcs")
    assert same_pack_size("6 CTN", "6 cartons")


def test_different_packs_stay_different():
    assert not same_pack_size("5 kg", "20 kg")
    assert not same_pack_size("1 kg", "1 L")


def test_containers_never_collapse_into_counts():
    """A carton is not twelve of anything until someone says what is in it.
    Comparing 6 ctn to 6 pc as equal would silently merge two real items."""
    assert not same_pack_size("6 ctn", "6 pc")
    assert parse("6 ctn").unit.dimension is Dimension.PACKAGING
    assert parse("6 pc").unit.dimension is Dimension.COUNT


def test_an_unknown_unit_is_left_alone_rather_than_guessed():
    assert parse("30") is None
    assert parse("2 widgets") is None
    assert canonical_unit("widgets") is None
    # Unparseable on both sides still matches itself, so nothing is lost.
    assert same_pack_size("2 widgets", "2 Widgets")
    assert not same_pack_size("2 widgets", "2 kg")


def test_pack_sizes_are_found_inside_item_names():
    assert find_all("MILK PWDR 2.5KG NIDO") == {parse("2.5 kg")}
    assert first_printed("RICE BASM 5KG") == "5KG"
    assert first_printed("Tomato Plum Roma") is None


@pytest.mark.parametrize(
    ("printed", "base_quantity", "unit"),
    [
        ("48x400ml", "19200", "ml"),
        ("48X400ML", "19200", "ml"),
        ("24 x 1L", "24000", "l"),
        ("12*500g", "6000", "g"),
        ("6×2kg", "12000", "kg"),
        ("EVAP MILK 48x400ML", "19200", "ml"),
    ],
)
def test_a_multiplier_pack_reads_as_the_whole_carton(printed, base_quantity, unit):
    """WP-51. "48x400ml" is forty-eight 400 ml tins. Reading only the tail
    divides a carton's price by one of its tins, so every cost per base unit
    built on it is 48x too high - and that exact pack is staged in
    demo_seed.sql at AED 90.00, so this was on the demo stage."""
    pack = parse(printed)
    assert pack is not None
    assert str(pack.base_quantity) == base_quantity
    assert pack.unit.canonical == unit


def test_a_multiplier_pack_equals_its_expansion_and_not_its_inner_pack():
    """A carton of 48 tins and a single tin are different packs at different
    prices. Snapping them together would compare AED 90 to AED 2.10 and fire a
    nonsense price alert."""
    assert same_pack_size("48x400ml", "19200 ml")
    assert same_pack_size("48x400ml", "19.2 L")
    assert not same_pack_size("48x400ml", "400ml")


@pytest.mark.parametrize("printed", ["2x3x4kg", "2 x 3 x 4 kg", "10x2x500g"])
def test_a_nested_multiplier_chain_is_refused_rather_than_half_read(printed):
    """A chain matches from the middle: "2x3x4kg" finds "3x4kg" and reads
    12 kg where the page says 24. Both halves are wrong numbers, so the chain
    is refused entirely - the same rule that keeps a carton's contents a
    human's sentence rather than a guess."""
    assert parse(printed) is None
    assert find_all(printed) == set()
    assert first_printed(printed) is None


@pytest.mark.parametrize("printed", ["0kg", "0.0 l", "0 pcs", "48x0kg", "0x400ml"])
def test_a_pack_of_nothing_is_not_a_pack(printed):
    """A zero quantity used to parse into a real pack whose base quantity was
    0. The first thing M5 does with a pack size is divide by it, inside the
    confirm transaction - so a printed 0 would have taken down the confirm
    after the invoice had already flipped to confirmed."""
    assert parse(printed) is None


def test_the_printed_form_of_a_multiplier_pack_is_kept_whole():
    """first_printed feeds ground truth and the catalog's pack column, so it
    has to hand back what the page says, multiplier included."""
    assert first_printed("EVAP MILK 48x400ML") == "48x400ML"
    assert find_all("EVAP MILK 48x400ML") == {parse("19200 ml")}


def test_unit_words_canonicalize():
    assert canonical_unit("cartons") == "ctn"
    assert canonical_unit("KGS") == "kg"
    assert canonical_unit("Litres") == "l"
    assert canonical_unit("كجم") == "kg"
    assert canonical_unit(None) is None
