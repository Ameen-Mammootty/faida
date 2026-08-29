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
from typing import Any

from .extraction import units

# A row from suppliers / supplier_items: an asyncpg.Record or a plain dict.
Row = Mapping[str, Any]

SUPPLIER_MATCH_THRESHOLD = 0.85
SNAP_THRESHOLD = 0.80

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


def _pack_tokens(text: str) -> set[tuple[str, str, Decimal]]:
    """The harmonized pack sizes named in a string: "MILK PWDR 2.5KG" and
    "Milk Powder 2500 g" produce the same token, so they never veto each
    other. The dictionary lives in extraction.units - one implementation, so
    the eval and the catalog agree on what a pack is."""
    return {pack.key for pack in units.find_all(normalize(text))}


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


def snap_item(items: Sequence[Row], raw_name: str) -> Row | None:
    """The supplier item whose canonical_name best matches a line's raw_name,
    or None when nothing clears SNAP_THRESHOLD. A snap across pack sizes never
    happens: when both sides name pack sizes (canonical_name or the item's
    pack_size column) and share none, the item is out regardless of score."""
    if not raw_name:
        return None
    raw_packs = _pack_tokens(raw_name)
    best: Row | None = None
    best_score = 0.0
    for item in items:
        item_packs = _pack_tokens(item["canonical_name"]) | _pack_tokens(
            item.get("pack_size") or ""
        )
        if raw_packs and item_packs and not (raw_packs & item_packs):
            continue
        score = _similarity(raw_name, item["canonical_name"])
        if score > best_score:
            best, best_score = item, score
    return best if best_score >= SNAP_THRESHOLD else None
