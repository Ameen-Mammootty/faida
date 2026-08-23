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
"""

import re
from collections.abc import Mapping, Sequence
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any

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

# Pack-size tokens: a number glued to a unit ("2.5kg", "50 KG", "30PCS").
# Digits and units discriminate pack sizes, so normalize() keeps them.
_PACK_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(kgs?|gm?s?|gr|ltr|litres?|liters?|lt|l|ml|pcs?|pkts?|dzn?|ctn)\b"
)
# Spelling variants to one canonical unit; g/ml then convert into kg/l so
# "500g" and "0.5kg" collide instead of falsely vetoing each other.
_UNIT_ALIASES = {
    "kgs": "kg",
    "gm": "g",
    "gms": "g",
    "gs": "g",
    "gr": "g",
    "ltr": "l",
    "litre": "l",
    "litres": "l",
    "liter": "l",
    "liters": "l",
    "lt": "l",
    "pcs": "pc",
    "pkts": "pkt",
    "dzn": "dz",
    "ctn": "ctn",
}
_UNIT_CONVERSIONS = {"g": (Decimal(1000), "kg"), "ml": (Decimal(1000), "l")}


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


def _similarity(a: str, b: str) -> float:
    """Fuzzy score over normalized names: the better of the whole-string ratio
    and the token-sorted ratio, so word order alone never sinks a match."""
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    whole = SequenceMatcher(None, na, nb).ratio()
    token_sorted = SequenceMatcher(
        None, " ".join(sorted(na.split())), " ".join(sorted(nb.split()))
    ).ratio()
    return max(whole, token_sorted)


def _pack_tokens(text: str) -> set[tuple[Decimal, str]]:
    """The (value, canonical unit) pack sizes named in a string: "MILK PWDR
    2.5KG" -> {(2.5, kg)}, "500g" -> {(0.5, kg)}. Empty when none are named."""
    tokens: set[tuple[Decimal, str]] = set()
    for value, unit in _PACK_RE.findall(normalize(text)):
        unit = _UNIT_ALIASES.get(unit, unit)
        quantity = Decimal(value)
        if unit in _UNIT_CONVERSIONS:
            divisor, unit = _UNIT_CONVERSIONS[unit]
            quantity /= divisor
        tokens.add((quantity, unit))
    return tokens


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
