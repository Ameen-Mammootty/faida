"""M6 WP-65 (EDGE-01): a margin note is not part of a product name.

A clerk writes "Credit: one box returned, soft fruit" beside a line, the model
reads the note as part of the name, and "Avocado Credit: one box returned, soft
fruit" scores 0.29 against the catalog's "Avocado". The snap misses, and
confirm mints a **second** Avocado.

Before M6 that was cosmetic. Now it is a silent wrong number: the mapped row
goes stale while the new row collects every later price, so the plate margin
freezes at an old cost with nothing on any screen looking wrong - the same
class of failure as D11's blocked newer purchase, one layer up.

The rule has to catch notes without ever catching a product, so the second
half is **measured on the corpus, not asserted**: every product name in
`eval/fixtures` is run through it, and the test names what would break if the
vocabulary ever grew carelessly ("Garlic Whole Peeled Free", "Cucumber Local
Short"). `python -m eval.run` is the other half of that check and runs before
merge, per the standing §5 rule.
"""

import json
import pathlib

import pytest

from faida_api.matching import _best_item, snap_item, strip_delivery_note

from .conftest import DEMO_TENANT_ID, requires_db
from .test_matching import _item, _seed_invoice, _seed_item, _seed_supplier

FIXTURES = pathlib.Path(__file__).resolve().parents[3] / "eval" / "fixtures"

# The read that fails, exactly as EDGE-01's margin note came back in 3 of 5
# live Flash runs on 2026-08-29.
EDGE_01_READ = "Avocado Credit: one box returned, soft fruit"


def corpus_names() -> list[str]:
    """Every product name the signed ground truth carries. Read from the truth
    files rather than copied here, so a corpus that grows is a corpus this
    test covers."""
    names: set[str] = set()
    for path in sorted(FIXTURES.rglob("truth.json")):
        invoice = json.loads(path.read_text()).get("invoice")
        for line in (invoice or {}).get("lines") or []:
            if line.get("raw_name"):
                names.add(line["raw_name"])
    return sorted(names)


# -- the rule itself ----------------------------------------------------------


def test_the_measured_read_is_split_at_the_note():
    assert strip_delivery_note(EDGE_01_READ) == "avocado"


@pytest.mark.parametrize(
    "read",
    [
        "Avocado - Credit: one box returned, soft fruit",
        "Avocado (credit note, damaged in transit)",
        "Tomato Local Box 5kg - 2 boxes returned",
        "Lamb Mince / short supplied, 3 kg only",
        "Salmon Fillet [handwritten: see note on delivery docket]",
        "Kale rejected - wilted",
        "Chicken Breast replaced with fillet",
    ],
)
def test_a_note_in_any_of_its_shapes_leaves_the_product_behind(read: str):
    head = strip_delivery_note(read)
    assert head is not None and head, read
    assert not head.endswith(("-", "/", "(", "[")), head


def test_a_name_that_is_only_a_note_is_left_alone():
    """Nothing to rescue: a line whose whole name is a note is a line for a
    person to look at, not one to guess a product from."""
    assert strip_delivery_note("Credit note") is None
    assert strip_delivery_note("returned goods") is None


def test_no_product_name_in_the_corpus_looks_like_a_note():
    """The half that matters. The corpus is the evidence, not an opinion -
    and the two names below are why the vocabulary has the gaps it has:
    "free" and a bare "short" would both cut a real product in half."""
    names = corpus_names()
    assert len(names) > 100, "the corpus shrank - check the fixtures"
    assert "Garlic Whole Peeled Free" in names
    assert "Cucumber Local Short" in names
    split = {name: strip_delivery_note(name) for name in names}
    assert {name: head for name, head in split.items() if head is not None} == {}


def test_the_rule_moves_no_match_anywhere_in_the_corpus():
    """The other measured half, stated as the safety property itself: for
    every product name in the corpus, snapping answers exactly what it
    answered before this rule existed.

    Identity is deliberately *not* what is asserted. The corpus carries both
    "Halloumi Cheese جبنة حلوم" and a bare "جبنة حلوم", and WP-29 snaps the
    second onto the first on purpose - one supplier printing one product in
    one script. A test demanding each name find its own row would call that
    correct behaviour a regression."""
    names = corpus_names()
    catalog = [_item(name, id=index) for index, name in enumerate(names)]
    for name in names:
        before = _best_item(catalog, name, strip_notes=False)
        after = snap_item(catalog, name)
        assert after == before, name


def test_the_note_pass_is_a_second_chance_not_a_rewrite():
    """A name that snaps today cannot be changed by this rule, because the
    trimmed pass only runs when the printed name matched nothing at all."""
    catalog = [
        _item("Avocado", "4 kg", id=1),
        _item("Avocado Credit Card Cleaner", id=2),
    ]
    # The printed name clears the threshold against row 2 on its own merits,
    # so the note pass never runs and row 2 is what it snaps to.
    assert snap_item(catalog, "Avocado Credit Card Cleaner")["id"] == 2
    # The margin note matches nothing outright, so the trim rescues it - onto
    # the avocado, not the cleaner.
    assert snap_item(catalog, EDGE_01_READ)["id"] == 1


def test_a_catalog_already_split_by_one_bad_read_stops_splitting():
    """A tenant whose very first avocado invoice was read with the note now
    has "Avocado Credit: ..." as its only avocado row. The next plain
    "Avocado" must land on it rather than mint a third."""
    catalog = [_item(EDGE_01_READ, id=9)]
    assert snap_item(catalog, "Avocado")["id"] == 9


def test_a_note_never_snaps_a_pack_size_it_does_not_share():
    """The pack veto survives the trim: the head keeps the product's own pack,
    because a note comes after the name, not inside it."""
    catalog = [_item("Basmati Rice 20kg", "20kg", id=1)]
    assert snap_item(catalog, "Basmati Rice 5kg - two bags damaged, credit due") is None


# -- and the consequence on a real database -----------------------------------


@requires_db
async def test_confirm_mints_no_second_row_for_the_annotated_line(db):
    """EDGE-01's own shape: two lines for one product, the credit line
    carrying the margin note. One catalog row, and the credit's own price
    observation lands on it."""
    supplier_id = await _seed_supplier(db, "Fresh Fields Produce LLC")
    item_id = await _seed_item(db, supplier_id, "Avocado")

    invoice_id = await _seed_invoice(
        db,
        supplier_id=supplier_id,
        lines=[
            {
                "raw_name": "Avocado",
                "qty": 5,
                "unit_price": 92,
                "pack_size": "4 kg",
                "line_total": 460,
                "supplier_item_id": item_id,
            },
            {
                "raw_name": EDGE_01_READ,
                "qty": -1,
                "unit_price": 92,
                "pack_size": "4 kg",
                "line_total": -92,
                # Null, exactly as the pipeline leaves a line whose snap
                # missed - which is what this work package changes.
                "supplier_item_id": None,
            },
        ],
    )
    await db.record_confirmed_prices(invoice_id)

    rows = await db.pool.fetch(
        "select canonical_name from supplier_items where tenant_id = $1 order by canonical_name",
        DEMO_TENANT_ID,
    )
    assert [row["canonical_name"] for row in rows] == ["Avocado"]


@requires_db
async def test_the_very_first_invoice_for_a_supplier_still_makes_one_row(db):
    """The harder half of the same shape, and the one EDGE-01 actually is: a
    fresh supplier, so nothing snapped at extraction time and both lines
    arrive unlinked. Line 1 creates the Avocado row; line 6 must land on the
    row created moments earlier in this same transaction, not beside it."""
    supplier_id = await _seed_supplier(db, "Fresh Fields Produce LLC")
    invoice_id = await _seed_invoice(
        db,
        supplier_id=supplier_id,
        lines=[
            {"raw_name": "Avocado", "qty": 5, "unit_price": 92, "pack_size": "4 kg"},
            {"raw_name": "Kale", "qty": 5, "unit_price": 18, "pack_size": "1 kg"},
            {"raw_name": EDGE_01_READ, "qty": -1, "unit_price": 92, "pack_size": "4 kg"},
        ],
    )
    await db.record_confirmed_prices(invoice_id)

    rows = await db.pool.fetch(
        "select canonical_name from supplier_items where tenant_id = $1 order by canonical_name",
        DEMO_TENANT_ID,
    )
    assert [row["canonical_name"] for row in rows] == ["Avocado", "Kale"]

    # And the credit line points at the Avocado row, so its price history and
    # every plate above it stay on one shelf.
    linked = await db.pool.fetch(
        "select l.position, s.canonical_name from invoice_lines l "
        "join supplier_items s on s.id = l.supplier_item_id "
        "where l.invoice_id = $1 order by l.position",
        invoice_id,
    )
    assert [row["canonical_name"] for row in linked] == ["Avocado", "Kale", "Avocado"]


@requires_db
async def test_an_ordinary_unsnapped_line_is_untouched_by_this(db):
    """The blast radius, pinned: the confirm loop re-asks the catalog **only**
    for a line carrying a note. Two different products on a first invoice
    still build two rows, exactly as they did before WP-65."""
    supplier_id = await _seed_supplier(db, "Gulf Foods Trading LLC")
    invoice_id = await _seed_invoice(
        db,
        supplier_id=supplier_id,
        lines=[
            {"raw_name": "Chicken Breast", "qty": 2, "unit_price": 30, "pack_size": "1 kg"},
            {"raw_name": "Chicken Breast Fillet", "qty": 2, "unit_price": 34, "pack_size": "1 kg"},
        ],
    )
    await db.record_confirmed_prices(invoice_id)
    rows = await db.pool.fetch(
        "select canonical_name from supplier_items where tenant_id = $1 order by canonical_name",
        DEMO_TENANT_ID,
    )
    assert [row["canonical_name"] for row in rows] == ["Chicken Breast", "Chicken Breast Fillet"]
