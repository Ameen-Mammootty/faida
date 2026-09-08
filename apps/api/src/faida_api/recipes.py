"""M6 WP-64: when two recipes are the same recipe (plan.md §7.3 row 64, D8).

A consultant loads a 45-row spreadsheet, finds two errors, fixes them and
uploads the file again. If the loader treated "the file was uploaded again" as
"the recipes changed", every one of those 45 dishes would gain a second recipe
version recording nothing, the audit trail would fill with noise, and the
version number on the menu screen would stop meaning anything.

So the loader asks a narrower question than "are these bytes identical":

    a recipe is unchanged when it makes the same number of portions from the
    same amounts of the same ingredients, bought the same way, in any order.

That is `yield_portions` plus the multiset of `(ingredient, qty, unit,
usable_share)` - the same rule the design review pinned as D8, written once
here so the door and its tests cannot drift apart. The share joined it in
M12 (WP-119, D13): it decides what the line costs and what the dish draws
from the storeroom, so changing it changes the recipe.

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

# One component's identity: which material, how much, in what measure, and
# how much of what was bought reaches the pot (M12 WP-119).
ComponentKey = tuple[str, Decimal, str, Decimal | None]
# A whole recipe's identity: the batch divisor, then its lines in a fixed order.
RecipeKey = tuple[Decimal, tuple[ComponentKey, ...]]

#: No real share can be this, because 0021 and the door both floor it above
#: zero - so it orders a null share against a stated one without ever
#: colliding with one. Sorting is `sorted`'s business; equality is the tuple's,
#: and the tuple keeps the None.
_NO_SHARE_SORTS_FIRST = Decimal(-1)


def _unit_key(unit: str) -> str:
    """The measure behind the word. Falls back to the word itself when
    `units.py` does not know it - which the write door refuses anyway, so this
    only ever runs on units already proven convertible."""
    return units.canonical_unit(unit) or (unit or "").strip().lower()


def component_key(
    ingredient_id: str, qty: Decimal, unit: str, usable_share: Decimal | None = None
) -> ComponentKey:
    """`Decimal("550")` and `Decimal("550.0000")` are the same amount; the
    column stores four decimals and the spreadsheet types none, so the
    comparison is numeric, never on the printed string. The same numeric
    comparison covers the share, so `0.85` and `0.8500` are one share.

    The share is part of the identity (M12 WP-119, D13) because it changes
    what the line costs and what M12 says the dish drew from the storeroom:
    a consultant who sets chicken to 85% has edited the recipe as surely as
    one who moved 500 g to 600 g, and the re-upload must record it.

    **No share and a share of 1 are two different lines**, not one, though
    they cost the same - the D8 rule that the card's words are the only audit
    a typed quantity has. "500 g" and "500 g at 100% usable, 500 g bought"
    say different things about a kitchen, and stating that nothing is lost is
    a fact somebody entered."""
    share = None if usable_share is None else Decimal(usable_share)
    return (str(ingredient_id), Decimal(qty), _unit_key(unit), share)


def _sort_key(component: ComponentKey) -> tuple[str, Decimal, str, Decimal]:
    """`sorted` compares element by element and would reach the share only for
    two draws of the same material in the same amount and measure - where one
    may carry a share and the other None, which no Decimal will compare
    against. Null sorts first, under a value no real share can hold."""
    ingredient_id, qty, unit, share = component
    return (ingredient_id, qty, unit, _NO_SHARE_SORTS_FIRST if share is None else share)


def recipe_key(yield_portions: Decimal, components: list[ComponentKey]) -> RecipeKey:
    """Sorted, not set-ified: two identical lines are two lines. A recipe that
    draws the same material twice (rare, legal - the door allows it) must not
    quietly compare equal to one that draws it once."""
    return (Decimal(yield_portions), tuple(sorted(components, key=_sort_key)))


def recipes_match(current: RecipeKey, incoming: RecipeKey) -> bool:
    """True when loading `incoming` over `current` would write a version that
    says exactly what the stored one already says."""
    return current == incoming
