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


def test_unit_words_canonicalize():
    assert canonical_unit("cartons") == "ctn"
    assert canonical_unit("KGS") == "kg"
    assert canonical_unit("Litres") == "l"
    assert canonical_unit("كجم") == "kg"
    assert canonical_unit(None) is None
