"""Supplier memory: matching and snapping (plan.md §5 layer 4, WP-22).

Pure normalization and scoring, no I/O - the pipeline feeds it supplier and
item rows, db.py owns the queries and the on-confirm price machinery
(Database.record_confirmed_prices). Fuzzy matching is difflib only: at demo
volume a dependency buys nothing, and the thresholds below were tuned against
messy corpus-style names (see tests/test_matching.py).

Tuning notes (SequenceMatcher over normalized names, best of whole-string and
token-sorted ratios):
- SUPPLIER_MATCH_THRESHOLD 0.85: genuine variants clear it ("GULF FOODS
  TRADING L.L.C." 0.96, "AL MADEENA TRADING" vs "Al Madina Trading" 0.91)
  while different companies stay out ("National Trading" vs "International
  Trading Co" 0.80, "Al Ain Dairy" vs "Al Ain Poultry" 0.69). A missed match
  just means no snapping; a wrong match corrupts another supplier's price
  history - so the threshold sits high and known far-off variants belong in
  name_aliases.
- SNAP_THRESHOLD 0.80: abbreviations clear it ("MILK PWDR 2.5KG NIDO" vs
  "Milk Powder 2.5kg" 0.81) and the pack-size veto - never snap across pack
  sizes - carries the trap cases the ratio alone would miss ("Chicken 10kg"
  vs "Chickpeas 1kg" scores exactly 0.80; "BASMATI RICE 5KG" vs "Basmati
  Rice 20kg" scores 0.91).

The veto compares harmonized pack sizes from `extraction.units`, so "2kg" and
"2000g" are one pack and one catalog item. Splitting them would split the
price history too, and a supplier who only changed their printing would fire
the price alert.

Delivery notes (WP-65, EDGE-01): a clerk writes "Credit: one box returned,
soft fruit" in the margin beside a line, the model reads the note as part of
the product name, and "Avocado Credit: one box returned, soft fruit" scores
0.29 against the catalog's "Avocado" - so the snap misses and confirm mints a
*second* Avocado. By M6 that is not cosmetic: the mapped row goes stale while
the new row collects the prices, and the plate margin quietly freezes at an
old cost with nothing on any screen looking wrong. `strip_delivery_note` is
the answer, and it is deliberately a **second chance rather than a rewrite** -
see `snap_item`.

Bilingual names (WP-29): GCC suppliers print bilingual letterheads, and the
model copies both scripts joined on some runs and one script on others. Scoring
is script-aware (see _similarity) so a joined "English / عربى" name still
matches a single-script catalog entry on the half they share - one read variant
no longer splits a supplier or an item into two.
"""

import re
from collections.abc import Mapping, Sequence
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any, NamedTuple

from .extraction import units

# A row from suppliers / supplier_items: an asyncpg.Record or a plain dict.
Row = Mapping[str, Any]

SUPPLIER_MATCH_THRESHOLD = 0.85
SNAP_THRESHOLD = 0.80
# INGREDIENT_PROPOSAL_THRESHOLD 0.70, measured with pack sizes stripped from
# both sides (see propose_ingredients). Real matches clear it - "Milk Powder
# 2.5kg" 1.00, "MILK PWDR 2.5KG NIDO" 0.72, "EVAP MILK 48x400ML" vs
# "Evaporated Milk" 0.75, "Chakki Atta Flour 25kg" vs "Atta Flour" 0.74 -
# while the near misses stay out: "Chicken Breast 10kg" vs "Basmati Rice"
# 0.615, "Cardamom Powder 500g" vs "Milk Powder" 0.615.
#
# It does not go lower, and the reason is one pair: "Chickpeas 1kg" vs
# "Chicken Breast" scores 0.696, the same as the genuine "Cardamom Powder
# 500g" vs "Cardamom". There is no threshold that keeps that cardamom match
# and drops the chickpeas one, so the tie is broken toward silence. Two
# confusable foods offered as the same material is precisely the merge a tired
# consultant approves and nobody catches afterwards - it corrupts the cost of
# every dish using either, with no photo to check against. A material we fail
# to propose costs someone typing a name.
INGREDIENT_PROPOSAL_THRESHOLD = 0.70
MAX_INGREDIENT_PROPOSALS = 3

# A dot survives only between digits ("2.5kg"); every other one becomes a
# space ("L.L.C." -> "l l c").
_DOT_RE = re.compile(r"(?<!\d)\.|\.(?!\d)")
# Everything that is not a word character, whitespace, or a (kept) dot.
# \w keeps Arabic script - invoices are mixed Arabic/English (plan.md §3).
_PUNCT_RE = re.compile(r"[^\w\s.]|_")

# Arabic script blocks (main, Supplement, Extended-A, Presentation Forms A/B),
# as inclusive (low, high) code-point pairs. A GCC letterhead prints the trade
# name in both scripts and the model copies whichever half it reads; _similarity
# compares each script to its own so the matching half is never diluted by the
# other language.
_ARABIC_RANGES = (
    (0x0600, 0x06FF),
    (0x0750, 0x077F),
    (0x08A0, 0x08FF),
    (0xFB50, 0xFDFF),
    (0xFE70, 0xFEFF),
)
_ARABIC = "".join(f"{chr(lo)}-{chr(hi)}" for lo, hi in _ARABIC_RANGES)
_ARABIC_CHAR_RE = re.compile(f"[{_ARABIC}]")
_NON_ARABIC_RE = re.compile(f"[^{_ARABIC}\\s]")


def normalize(name: str) -> str:
    """Casefold, collapse whitespace, strip punctuation - keeping digits and
    units ("2.5kg") because pack sizes discriminate items names alone don't."""
    text = _DOT_RE.sub(" ", name.casefold())
    text = _PUNCT_RE.sub(" ", text)
    return " ".join(text.split())


def clean_name(name: str) -> str:
    """Display-safe cleanup for a raw extracted name that becomes a catalog
    name (suppliers.name, supplier_items.canonical_name): collapse whitespace
    and trim stray edge punctuation, keep case and inner marks ("L.L.C")."""
    return " ".join(name.split()).strip(" .,;:-_")


def normalize_invoice_no(invoice_no: str | None) -> str | None:
    """One comparable form for an invoice number (WP-44): lowercase, every
    non-alphanumeric stripped, so "AAF 2214", "aaf-2214" and "AAF#2214" are
    the same paper. None (and a number that is all punctuation) stays None -
    an absent number must never equal another absent number."""
    if invoice_no is None:
        return None
    normalized = "".join(ch for ch in invoice_no.casefold() if ch.isalnum())
    return normalized or None


def _latin_view(text: str) -> str:
    """The normalized name with Arabic runs dropped - Latin letters, digits and
    units kept. Empty when the name is written entirely in Arabic."""
    return " ".join(_ARABIC_CHAR_RE.sub(" ", text).split())


def _arabic_view(text: str) -> str:
    """The normalized name with everything but Arabic runs dropped. Empty when
    the name carries no Arabic."""
    return " ".join(_NON_ARABIC_RE.sub(" ", text).split())


def _ratio(na: str, nb: str) -> float:
    """difflib score over two already-normalized strings: the better of the
    whole-string ratio and the token-sorted ratio, so word order never sinks a
    match."""
    if na == nb:
        return 1.0
    whole = SequenceMatcher(None, na, nb).ratio()
    token_sorted = SequenceMatcher(
        None, " ".join(sorted(na.split())), " ".join(sorted(nb.split()))
    ).ratio()
    return max(whole, token_sorted)


def _similarity(a: str, b: str) -> float:
    """Fuzzy score over normalized names, script-aware.

    The whole-string ratio is the floor. On top of it, when one name is written
    in a single script and the other joins both (the GCC bilingual letterhead,
    "Dairy House Foodstuff LLC / بيت الألبان..."), the shared script is compared
    to itself so the matching half is not diluted by the other language. The
    boost is gated on one side being single-script (view == whole name): when
    *both* names carry both scripts the whole-string compare is already
    apples-to-apples, and an unguarded per-script split would let two different
    suppliers match on their shared Arabic legal boilerplate ("... للمواد
    الغذائية ذ.م.م") alone.
    """
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    score = _ratio(na, nb)
    for view in (_latin_view, _arabic_view):
        va, vb = view(na), view(nb)
        if va and vb and (va == na or vb == nb):
            score = max(score, _ratio(va, vb))
    return score


# The words a clerk writes in the margin about *this delivery* - never about
# the goods. Each is a token sequence matched whole against the normalized
# name, so no substring can fire it.
#
# The list is short on purpose, and what is missing from it matters more than
# what is in it. "free" is absent: the corpus prints "Garlic Whole Peeled
# Free", "Eggs Free Range Large Tray 30" and "Large Free-Range Egg", and
# trimming any of those would break a name that snaps correctly today. Bare
# "short" is absent for "Cucumber Local Short"; only the phrases a note uses
# ("short supplied", "short delivered", "shortage") are here. Every one of the
# 125 names in the corpus is checked against this list by a test, because the
# hard part of this rule is not catching notes - it is never catching a
# product (WP-65's acceptance is measured, not asserted).
_NOTE_PHRASES: tuple[tuple[str, ...], ...] = tuple(
    tuple(phrase.split())
    for phrase in (
        "credit",
        "credited",
        "credit note",
        "return",
        "returns",
        "returned",
        "damaged",
        "damage",
        "breakage",
        "broken",
        "leaking",
        "leaked",
        "spoiled",
        "spoilt",
        "rotten",
        "expired",
        "expiry",
        "short supplied",
        "short delivered",
        "short shipped",
        "shortage",
        "replaced",
        "replacement",
        "rejected",
        "refused",
        "not delivered",
        "not supplied",
        "out of stock",
        "no stock",
        "as per",
        "see note",
        "per note",
        "handwritten",
        "complimentary",
        "goodwill",
        "wrong item",
        "wrong size",
    )
)


def strip_delivery_note(name: str) -> str | None:
    """The product half of "Avocado Credit: one box returned, soft fruit", or
    None when the name carries no delivery note (WP-65, EDGE-01).

    Two guards keep this from eating a real product name. The note must begin
    at a phrase from `_NOTE_PHRASES`, matched as whole tokens; and it may
    never begin at the **first** token, because a name that is nothing but a
    note is not a name this can rescue - it is a line for a person to look at.

    Returns the normalized head, which is all a comparison needs. The stored
    catalog name is not touched: renaming what a supplier printed is a
    different decision, with a screen and an audit row behind it."""
    tokens = normalize(name).split()
    for index in range(1, len(tokens)):
        for phrase in _NOTE_PHRASES:
            if tuple(tokens[index : index + len(phrase)]) == phrase:
                return " ".join(tokens[:index])
    return None


def _pack_tokens(text: str) -> set[tuple[str, str, Decimal]]:
    """The harmonized pack sizes named in a string: "MILK PWDR 2.5KG" and
    "Milk Powder 2500 g" produce the same token, so they never veto each
    other. The dictionary lives in extraction.units - one implementation, so
    the eval and the catalog agree on what a pack is."""
    return {pack.key for pack in units.find_all(normalize(text))}


def propose_ingredients(
    ingredients: Sequence[Row],
    canonical_name: str,
    *,
    rejected_ids: Sequence[str] = (),
) -> list[Row]:
    """The raw materials this pack might be, best first. Proposes; never
    decides (plan.md §8 M5 - never auto-merged).

    **Pack-blind on purpose**, and this is the one place it must differ from
    `snap_item`. Snapping asks "is this the same pack?", where a 2.5 kg sack
    and a 500 g pouch are two catalog rows with two price histories. Mapping
    asks "is this the same material?", where they are one shelf. So the pack
    sizes come out of both names before scoring, and there is no veto.

    The bar sits just below SNAP_THRESHOLD rather than far below it. A
    proposal is read by a person before it does anything, which argues for
    offering more - but the measured scores say otherwise for the pairs that
    matter, and the constant above carries that evidence.

    `rejected_ids` are materials this pack was already said not to be. They are
    dropped rather than ranked last: re-offering a rejected answer is how an
    approval queue teaches people to stop reading it.
    """
    stripped = units.strip_packs(normalize(canonical_name))
    if not stripped:
        return []
    rejected = {str(item) for item in rejected_ids}
    scored: list[tuple[float, Row]] = []
    for ingredient in ingredients:
        if str(ingredient["id"]) in rejected:
            continue
        score = _similarity(stripped, units.strip_packs(normalize(ingredient["name"])))
        if score >= INGREDIENT_PROPOSAL_THRESHOLD:
            scored.append((score, ingredient))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [ingredient for _, ingredient in scored[:MAX_INGREDIENT_PROPOSALS]]


# MENU_ITEM_PROPOSAL_THRESHOLD 0.72, measured over normalized names with the
# pack sizes KEPT on both sides (see propose_menu_items) against the staged
# five-item menu and the real 45-item one, spelt the way a till prints them.
# Real matches clear it - "CHKN 65 DRY" vs "Chicken 65 Dry" 0.88, "KARAK
# FLASK 1L" vs "Karak Tea (Flask 1 L)" 0.848, "GOBI MSL" vs "Gobi Masala"
# 0.842, "HONEY CAKE" vs "Honey Cake - slice" 0.769, "NIDO TEA" vs "Nido Milk
# Tea" 0.762, "CAPPUCCINO SML" vs "Cappuccino - Small 150 ml" 0.757 (its
# large sibling 0.703, below), "CHAI FLASK 2L" vs "Cardamom Chai (Flask 2 L)"
# 0.722 - while a bare word stays out: "MASALA" vs "Gobi Masala" 0.706,
# "CHICKEN" vs "Chicken Wings" and "Chicken Kadai" 0.700 (a tie, and a tie
# between two dishes is exactly the choice a proposal must not make), "FLASK
# 1 L" vs "Karak Tea - Flask 1 L" 0.643, "DELIVERY CHARGE" vs "Karak
# Delivery - Large 400 ml" 0.619.
#
# It sits at 0.72 and not at the ingredient bar of 0.70 because of "MASALA"
# at 0.706: one word of a dish's name is not the dish, and the two-point
# margin is what keeps it out. A size word alone ("LARGE 250ML" scores 0.759
# against every large drink) clears any bar a real abbreviation clears, so
# that case is not a threshold at all: a name with nothing but size and pack
# words in it proposes nothing (see _dish_words).
MENU_ITEM_PROPOSAL_THRESHOLD = 0.72
MAX_MENU_ITEM_PROPOSALS = 3

# Words that say how big or how served, never what. A till name made only of
# these ("LARGE 250ML", "FLASK 1 L", "SLICE") names no dish and gets no
# proposal, whatever a size-heavy menu scores it.
_SIZE_WORDS = frozenset(
    "small medium large sml sm med md lrg lg xl xs regular reg mini jumbo "
    "cup flask slice piece pc pcs half full pot glass mug bottle can".split()
)


class MenuProposal(NamedTuple):
    """One ranked answer from `propose_menu_items`: the menu item and the
    score that put it there, so the queue can show both."""

    item: Row
    score: float


def _dish_words(name: str) -> list[str]:
    """The normalized name with pack sizes and size words taken out - what is
    left must name a dish for a proposal to be worth making."""
    return [word for word in units.strip_packs(normalize(name)).split() if word not in _SIZE_WORDS]


def propose_menu_items(
    menu_items: Sequence[Row], till_name: str, *, limit: int = MAX_MENU_ITEM_PROPOSALS
) -> list[MenuProposal]:
    """The menu items a till name might be, best first. Proposes; never
    decides (C11.7 - an exact name still needs its keystroke).

    **Pack-aware on purpose**, the one way this must differ from
    `propose_ingredients`. A supplier's 2.5 kg and 500 g of milk powder are one
    material, so that proposer strips the sizes. A menu's "Karak Tea - Flask
    1 L" and "- Flask 2 L" are two items with two prices, and stripped they
    score 1.00 against each other (measured: 0.947 kept, 1.00 stripped), so the
    till's "KARAK FLASK 1L" could never tell them apart. Here the size stays in
    the score, and the 1 L flask wins 0.848 to 0.595 on the staged menu and
    0.973 to 0.919 on the real one - never a tie.

    Archived items are not offered: an archived dish is out of the ranking and
    the coverage figure, and mapping sales onto it would put value where
    nobody looks. Ties on the score break on the name, so the order is stable.
    """
    if not _dish_words(till_name):
        return []
    scored: list[MenuProposal] = []
    for item in menu_items:
        if item.get("archived_at") is not None:
            continue
        score = _similarity(till_name, item["name"])
        if score >= MENU_ITEM_PROPOSAL_THRESHOLD:
            scored.append(MenuProposal(item, score))
    scored.sort(key=lambda proposal: (-proposal.score, normalize(proposal.item["name"])))
    return scored[:limit]


def match_supplier(suppliers: Sequence[Row], extracted_name: str | None) -> Row | None:
    """The supplier whose name or alias best matches the extracted supplier
    name, or None when nothing clears SUPPLIER_MATCH_THRESHOLD."""
    if not extracted_name:
        return None
    best: Row | None = None
    best_score = 0.0
    for supplier in suppliers:
        names = [supplier["name"], *(supplier["name_aliases"] or [])]
        score = max(_similarity(extracted_name, name) for name in names)
        if score > best_score:
            best, best_score = supplier, score
    return best if best_score >= SUPPLIER_MATCH_THRESHOLD else None


def _best_item(items: Sequence[Row], raw_name: str, *, strip_notes: bool) -> Row | None:
    """One scoring pass over the catalog. `strip_notes` also trims a delivery
    note off each *catalog* name, which is how a catalog already split by one
    bad read stops splitting further instead of growing a third row."""
    raw_packs = _pack_tokens(raw_name)
    best: Row | None = None
    best_score = 0.0
    for item in items:
        name = item["canonical_name"]
        if strip_notes:
            name = strip_delivery_note(name) or name
        item_packs = _pack_tokens(name) | _pack_tokens(item.get("pack_size") or "")
        if raw_packs and item_packs and not (raw_packs & item_packs):
            continue
        score = _similarity(raw_name, name)
        if score > best_score:
            best, best_score = item, score
    return best if best_score >= SNAP_THRESHOLD else None


def snap_item(items: Sequence[Row], raw_name: str) -> Row | None:
    """The supplier item whose canonical_name best matches a line's raw_name,
    or None when nothing clears SNAP_THRESHOLD. A snap across pack sizes never
    happens: when both sides name pack sizes (canonical_name or the item's
    pack_size column) and share none, the item is out regardless of score.

    **The delivery-note pass is a second chance, never a rewrite** (WP-65).
    The name as printed is scored first, against the catalog as stored; only
    when *nothing* clears the threshold is the note trimmed off and the
    catalog asked again. That ordering is the whole safety argument: a name
    that snaps correctly today cannot be changed by this, because the trimmed
    pass never runs for it. The rule can add a match; it can never move one."""
    if not raw_name:
        return None
    match = _best_item(items, raw_name, strip_notes=False)
    if match is not None:
        return match
    # The note can be on either side: on the line, when the clerk annotated
    # this delivery, or on the catalog row, when a tenant's very first read of
    # that product carried one. Both are trimmed here, so a catalog already
    # split by one bad read attracts the next clean read instead of growing a
    # third row.
    return _best_item(items, strip_delivery_note(raw_name) or raw_name, strip_notes=True)
