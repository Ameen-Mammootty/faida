"""M6 WP-64: when two recipes are the same recipe (plan.md §7.3 row 64, D8).

A consultant loads a 45-row spreadsheet, finds two errors, fixes them and
uploads the file again. If the loader treated "the file was uploaded again" as
"the recipes changed", every one of those 45 dishes would gain a second recipe
version recording nothing, the audit trail would fill with noise, and the
version number on the menu screen would stop meaning anything.

So the loader asks a narrower question than "are these bytes identical":

    a recipe is unchanged when it makes the same number of portions from the
    same amounts of the same ingredients, in any order.

That is `yield_portions` plus the multiset of `(ingredient, qty, unit)` - the
same rule the design review pinned as D8, written once here so the door and
its tests cannot drift apart.

Three deliberate edges, each of which decides a real spreadsheet case:

- **Order is not information.** A consultant who sorts their sheet by
  ingredient has not changed a single recipe.
- **The unit *word* is formatting; the unit *magnitude* is not.** "ml", "ML"
  and "mls" are one measure and compare equal. "1 kg" and "1000 g" are the
  same amount but not the same line, and they re-version: the card now says
  something different, and the card's words are the only audit a typed
  quantity has.
- **`source_text` is outside the comparison**, by D8's own wording. It is free
  text a spreadsheet reflows constantly, and a recipe that re-versioned on
  whitespace would defeat the whole rule. A wording-only change is therefore
  not applied - so the loader *names* it on the row rather than letting the
  two copies drift apart in silence.

Pure functions, no I/O: quantities arrive as `Decimal` and the answer is a
comparison, never a number anyone sees.
"""

from decimal import Decimal

from .extraction import units

# One component's identity: which material, how much, in what measure.
ComponentKey = tuple[str, Decimal, str]
# A whole recipe's identity: the batch divisor, then its lines in a fixed order.
RecipeKey = tuple[Decimal, tuple[ComponentKey, ...]]


def _unit_key(unit: str) -> str:
    """The measure behind the word. Falls back to the word itself when
    `units.py` does not know it - which the write door refuses anyway, so this
    only ever runs on units already proven convertible."""
    return units.canonical_unit(unit) or (unit or "").strip().lower()


def component_key(ingredient_id: str, qty: Decimal, unit: str) -> ComponentKey:
    """`Decimal("550")` and `Decimal("550.0000")` are the same amount; the
    column stores four decimals and the spreadsheet types none, so the
    comparison is numeric, never on the printed string."""
    return (str(ingredient_id), Decimal(qty), _unit_key(unit))


def recipe_key(yield_portions: Decimal, components: list[ComponentKey]) -> RecipeKey:
    """Sorted, not set-ified: two identical lines are two lines. A recipe that
    draws the same material twice (rare, legal - the door allows it) must not
    quietly compare equal to one that draws it once."""
    return (Decimal(yield_portions), tuple(sorted(components)))


def recipes_match(current: RecipeKey, incoming: RecipeKey) -> bool:
    """True when loading `incoming` over `current` would write a version that
    says exactly what the stored one already says."""
    return current == incoming
