"""M6 WP-60: the menu write door (plan.md §7.3).

Routes, all under /api behind the same shared-secret bearer token as the rest
of C6 (real auth is M7; the API refuses client-asserted identity, so every
write here names `console` as its actor until then):

    GET   /api/menu-items                     every item + its current recipe version
    POST  /api/menu-items                     create an item (name + selling price)
    GET   /api/menu-items/{id}                item detail + current recipe
    PATCH /api/menu-items/{id}/price          the owner said a new price out loud
    POST  /api/menu-items/{id}/archive        out of ranking and coverage, one click back
    POST  /api/menu-items/{id}/unarchive      the click back
    POST  /api/menu-items/{id}/recipe         append the next recipe version

M6 invents no new numbers, so this module writes only what a consultant typed
and refuses the shapes that would later lie: the refusal set is stated, not
implied (eng review D7), and each refusal answers with its own plain sentence -

    a selling price of zero or less     margin %% divides by it
    a yield of zero or less             WP-61 divides the batch by it
    a component quantity of zero/less   a negative qty silently subtracts cost
    a version with zero components      sum over nothing costs 0 and reads as
                                        a 100%%-margin plate (D4)
    a duplicate live name               two rows, one dish, split history
    a unit units.py cannot convert      "2 cups milk" - a karak cup is a
                                        serving vessel, not a measure (PRD §16)

Editing writes a whole new version and never touches an old one; two
concurrent saves cannot mint the same version number (D17) - the loser gets a
sentence, not a stack trace. A component on another tenant's ingredient is
answered 404 here and refused by Postgres regardless (the 0012 composite-key
shape).

Money and quantities arrive as unsigned decimal strings and are serialized
back as strings, never floats (C4/C6). Writes return the full item detail,
the C6 convention.
"""

import uuid
from decimal import ROUND_HALF_UP, Decimal

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from . import plates
from .api import (
    CONSOLE_ACTOR,
    MEASURE_WORDS,
    _clean,
    _dec,
    _iso,
    _material_price,
    _tenant,
    blocked_line_reason,
    require_api_token,
)
from .confirm import _parse_number
from .db import Database
from .extraction import units
from .extraction.constants import VAT_RATE_BY_CURRENCY

router = APIRouter(prefix="/api", dependencies=[Depends(require_api_token)])


# --- request bodies ---------------------------------------------------------


class MenuItemCreate(BaseModel):
    """Name and selling price, both required - an item with no price has no
    margin to compute and nothing to show. The price is what the owner says
    out loud, VAT inside it (WP-61 margins against the net and says so)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    selling_price: str


class MenuItemPrice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selling_price: str


class RecipeComponent(BaseModel):
    """One line of the card: which material, how much, in what measure, and
    the card's own words when the consultant converted them (`source_text` -
    a typed quantity's only audit, PRD §17-18)."""

    model_config = ConfigDict(extra="forbid")

    ingredient_id: uuid.UUID
    qty: str
    unit: str
    source_text: str | None = None


class RecipeVersion(BaseModel):
    """POST /menu-items/{id}/recipe body. `components` is validated in code,
    not by the schema, so an empty list gets this module's plain sentence
    rather than a framework error."""

    model_config = ConfigDict(extra="forbid")

    yield_portions: str
    yield_label: str | None = None
    components: list[RecipeComponent] = []


# --- the refusal set (each with its own plain sentence) ----------------------


def _positive_number(value: str, *, what: str, example: str) -> "object":
    """The unsigned-decimal-string rule shared with PATCH and chat, plus the
    door's own floor: zero is refused because everything downstream divides
    by these or sums them."""
    number = _parse_number(value)
    if number is None or number <= 0:
        raise HTTPException(
            status_code=422,
            detail=f"'{value}' is not a {what}: send an amount above zero, like \"{example}\"",
        )
    return number


def _component_unit(unit_text: str, ingredient: asyncpg.Record) -> str:
    """The unit as typed, kept - after proving units.py can convert it to the
    ingredient's base unit. Kitchen measures ('cup', 'tbsp') are deliberately
    absent from that dictionary: a karak cup is a serving vessel, not a
    measure, and the consultant converts during loading (PRD §16). Containers
    parse but have no dimension, so they are refused with their own sentence -
    'a carton of flour' is not an amount of flour."""
    text = (unit_text or "").strip()
    canonical = units.canonical_unit(text)
    if canonical is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"'{text}' is not a measure this system converts: give the amount "
                "by weight (g, kg), by volume (ml, l) or in pieces"
            ),
        )
    base = units.BASE_UNITS.get(units.UNITS[canonical].dimension)
    if base is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"a {canonical} is a container, not an amount: say how much of "
                f"{ingredient['name']} goes in, by weight, volume or pieces"
            ),
        )
    if base != ingredient["base_unit"]:
        raise HTTPException(
            status_code=422,
            detail=(
                f"'{text}' is measured {MEASURE_WORDS[base]}, but {ingredient['name']} "
                f"is measured {MEASURE_WORDS[ingredient['base_unit']]}"
            ),
        )
    return text


# --- costing (WP-61) ---------------------------------------------------------
#
# Nothing below is stored. A plate cost derives on every read from the same
# WP-54 derivation the materials screen shows, so confirming a cheaper milk
# invoice moves every karak on the next screen load with zero writes to any
# menu table - no cache, no recompute job, nothing to invalidate.


async def _pricing(
    db: Database, tenant_id: str
) -> tuple[dict[str, asyncpg.Record], dict[str, asyncpg.Record], Decimal | None]:
    """The three facts every plate reads, fetched once per request whatever
    the menu's length (D10): each material's current price (the newest costed
    line among its packs, WP-54), the materials whose newest purchase could
    not be costed (the D11 stale flag), and the VAT rate inside this tenant's
    menu prices."""
    currency = await db.tenant_currency(tenant_id)
    vat_rate = VAT_RATE_BY_CURRENCY.get(currency or "")
    prices: dict[str, asyncpg.Record] = {}
    for row in await db.list_mapped_pack_costs(tenant_id):
        prices.setdefault(row["ingredient_id"], row)
    stale = {
        row["ingredient_id"]: row
        for row in await db.list_newest_purchases(tenant_id)
        if not row["costed"]
    }
    return prices, stale, vat_rate


def _cost_component(
    row: asyncpg.Record,
    prices: dict[str, asyncpg.Record],
    stale: dict[str, asyncpg.Record],
) -> plates.ComponentCost:
    ingredient_id = row["ingredient_id"]
    price_row = prices.get(ingredient_id)
    stale_line = stale.get(ingredient_id)
    if price_row is None:
        # The blocked newer purchase, when known, lends the missing sentence
        # its WP-55 reason - the same words the blocked-cost queue shows.
        reason = None if stale_line is None else blocked_line_reason(stale_line)
        return plates.cost_component(
            position=row["position"],
            qty=row["qty"],
            unit=row["unit"],
            ingredient_name=row["ingredient_name"],
            has_packs=row["has_packs"],
            price=None,
            no_price_reason=reason,
        )
    basis = price_row["cost_basis"] or {}
    return plates.cost_component(
        position=row["position"],
        qty=row["qty"],
        unit=row["unit"],
        ingredient_name=row["ingredient_name"],
        has_packs=row["has_packs"],
        price=plates.Priced(
            cost_per_base_unit=price_row["cost_per_base_unit"],
            base_unit=price_row["cost_base_unit"],
            quality=basis.get("quality"),
            stale=stale_line is not None,
        ),
    )


def _plate_payload(result: plates.Plate) -> dict:
    """The item's whole answer. Incomplete carries no numbers at all - only
    what is missing - so a hole in the data can never read as a fat margin.
    The word is *margin*, never "profit" and never "food cost %" (§3)."""
    return {
        "quality": result.quality.value,
        "missing": list(result.missing),
        "cost_per_portion": _dec(result.cost_per_portion),
        "net_price": _dec(result.net_price),
        "vat_rate": _dec(result.vat_rate),
        "margin": _dec(result.margin),
        "margin_pct": _dec(result.margin_pct),
    }


def _component_cost_payload(
    row: asyncpg.Record,
    costed: plates.ComponentCost,
    prices: dict[str, asyncpg.Record],
    stale: dict[str, asyncpg.Record],
) -> dict:
    """One component's cost with its full forensics - the material price it
    multiplied, down to the invoice line id and the photo behind it - or the
    plain-words reason there is no number."""
    if costed.cost is None:
        return {"cost": None, "missing": costed.missing}
    ingredient_id = row["ingredient_id"]
    return {
        "cost": {
            "amount": _dec(costed.cost.quantize(plates.PLATE_QUANTUM, rounding=ROUND_HALF_UP)),
            "quality": costed.quality.value,
            "price": _material_price(prices[ingredient_id], stale.get(ingredient_id)),
        },
        "missing": None,
    }


# --- serialization ----------------------------------------------------------


async def _menu_item_detail(db: Database, menu_item_id: str) -> dict:
    """The full item payload every write returns (C6): the item, its current
    recipe version, that version's components each carrying its cost and the
    invoice line the price came from, and the plate answer on top. The
    forensics of the *current* number - reproducing a past screen is M8's
    calculation-run subsystem, not this milestone."""
    item = await db.get_menu_item(menu_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="menu item not found")
    recipe = await db.get_current_recipe(menu_item_id)
    components = [] if recipe is None else await db.get_recipe_components(recipe["id"])
    prices, stale, vat_rate = await _pricing(db, item["tenant_id"])

    if recipe is None:
        result = plates.no_recipe_plate()
        costed: list[plates.ComponentCost] = []
    else:
        costed = [_cost_component(row, prices, stale) for row in components]
        result = plates.plate(
            costed,
            yield_portions=recipe["yield_portions"],
            selling_price=item["selling_price"],
            vat_rate=vat_rate,
        )

    return {
        "id": item["id"],
        "name": item["name"],
        "selling_price": _dec(item["selling_price"]),
        "archived_at": _iso(item["archived_at"]),
        "created_at": _iso(item["created_at"]),
        "plate": _plate_payload(result),
        "recipe": None
        if recipe is None
        else {
            "id": recipe["id"],
            "version": recipe["version"],
            "yield_portions": _dec(recipe["yield_portions"]),
            "yield_label": recipe["yield_label"],
            "created_at": _iso(recipe["created_at"]),
            "components": [
                {
                    "position": component["position"],
                    "ingredient_id": component["ingredient_id"],
                    "ingredient_name": component["ingredient_name"],
                    "base_unit": component["base_unit"],
                    "qty": _dec(component["qty"]),
                    "unit": component["unit"],
                    "source_text": component["source_text"],
                    **_component_cost_payload(component, cost, prices, stale),
                }
                for component, cost in zip(components, costed, strict=True)
            ],
        },
    }


async def _live_item(db: Database, menu_item_id: uuid.UUID) -> asyncpg.Record:
    """The item, provided it exists and is not archived - the two answers a
    write needs before it may touch anything. An archived item is read-only:
    bring it back first, so its history cannot grow while it is off every
    screen."""
    item = await db.get_menu_item(str(menu_item_id))
    if item is None:
        raise HTTPException(status_code=404, detail="menu item not found")
    if item["archived_at"] is not None:
        raise HTTPException(
            status_code=409,
            detail="menu item is archived; bring it back before changing it",
        )
    return item


# --- routes ------------------------------------------------------------------


@router.get("/menu-items")
async def list_menu_items(request: Request) -> dict:
    """Every item with its current recipe version and its plate answer -
    cost, margin in AED and margin %% at its own menu price, or the list of
    what is missing. Archived items are included and flagged, because the
    loader grid names them rather than pretending they are gone (WP-64).

    A fixed number of queries however long the menu grows (D10): the items,
    the current components, the material prices, the stale flags and the
    tenant currency - joined in Python, nothing stored, nothing to
    invalidate."""
    db: Database = request.app.state.db
    tenant_id = await _tenant(db)
    prices, stale, vat_rate = await _pricing(db, tenant_id)
    components_by_item: dict[str, list[asyncpg.Record]] = {}
    for row in await db.list_current_recipe_components(tenant_id):
        components_by_item.setdefault(row["menu_item_id"], []).append(row)

    items = []
    for row in await db.list_menu_items(tenant_id):
        if row["recipe_id"] is None:
            result = plates.no_recipe_plate()
        else:
            costed = [
                _cost_component(component, prices, stale)
                for component in components_by_item.get(row["id"], [])
            ]
            result = plates.plate(
                costed,
                yield_portions=row["yield_portions"],
                selling_price=row["selling_price"],
                vat_rate=vat_rate,
            )
        items.append(
            {
                "id": row["id"],
                "name": row["name"],
                "selling_price": _dec(row["selling_price"]),
                "archived_at": _iso(row["archived_at"]),
                "created_at": _iso(row["created_at"]),
                "plate": _plate_payload(result),
                "recipe": None
                if row["recipe_id"] is None
                else {
                    "id": row["recipe_id"],
                    "version": row["version"],
                    "yield_portions": _dec(row["yield_portions"]),
                    "yield_label": row["yield_label"],
                    "component_count": row["component_count"],
                },
            }
        )
    return {"menu_items": items}


@router.get("/menu-items/{menu_item_id}")
async def get_menu_item(menu_item_id: uuid.UUID, request: Request) -> dict:
    return await _menu_item_detail(request.app.state.db, str(menu_item_id))


@router.post("/menu-items", status_code=201)
async def create_menu_item(body: MenuItemCreate, request: Request) -> dict:
    db: Database = request.app.state.db
    tenant_id = await _tenant(db)
    name = _clean(body.name)
    if name is None:
        raise HTTPException(status_code=422, detail="a menu item needs a name")
    price = _positive_number(body.selling_price, what="selling price", example="17.00")
    try:
        item = await db.create_menu_item(
            tenant_id=tenant_id, name=name, selling_price=price, actor=CONSOLE_ACTOR
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(
            status_code=409, detail=f"a menu item called '{name}' already exists"
        ) from None
    return await _menu_item_detail(db, item["id"])


@router.patch("/menu-items/{menu_item_id}/price")
async def set_menu_item_price(
    menu_item_id: uuid.UUID, body: MenuItemPrice, request: Request
) -> dict:
    """The owner said a new price. The audit row carries old and new - that
    trail is the selling-price history (§2 rule 8). Sending the same price
    again changes nothing and writes nothing."""
    db: Database = request.app.state.db
    item = await _live_item(db, menu_item_id)
    price = _positive_number(body.selling_price, what="selling price", example="17.00")
    await db.set_menu_item_price(
        str(menu_item_id),
        tenant_id=item["tenant_id"],
        selling_price=price,
        actor=CONSOLE_ACTOR,
    )
    return await _menu_item_detail(db, str(menu_item_id))


@router.post("/menu-items/{menu_item_id}/archive")
async def archive_menu_item(menu_item_id: uuid.UUID, request: Request) -> dict:
    """Out of the ranking and the coverage count, never deleted. Always an
    explicit click - the loader never archives on its own (Codex 9)."""
    db: Database = request.app.state.db
    item = await db.get_menu_item(str(menu_item_id))
    if item is None:
        raise HTTPException(status_code=404, detail="menu item not found")
    archived = await db.archive_menu_item(
        str(menu_item_id), tenant_id=item["tenant_id"], actor=CONSOLE_ACTOR
    )
    if not archived:
        raise HTTPException(status_code=409, detail="menu item is already archived")
    return await _menu_item_detail(db, str(menu_item_id))


@router.post("/menu-items/{menu_item_id}/unarchive")
async def unarchive_menu_item(menu_item_id: uuid.UUID, request: Request) -> dict:
    db: Database = request.app.state.db
    item = await db.get_menu_item(str(menu_item_id))
    if item is None:
        raise HTTPException(status_code=404, detail="menu item not found")
    try:
        unarchived = await db.unarchive_menu_item(
            str(menu_item_id), tenant_id=item["tenant_id"], actor=CONSOLE_ACTOR
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(
            status_code=409,
            detail=f"another live menu item is already called '{item['name']}'; "
            "rename or archive it first",
        ) from None
    if not unarchived:
        raise HTTPException(status_code=409, detail="menu item is not archived")
    return await _menu_item_detail(db, str(menu_item_id))


@router.post("/menu-items/{menu_item_id}/recipe", status_code=201)
async def create_recipe_version(
    menu_item_id: uuid.UUID, body: RecipeVersion, request: Request
) -> dict:
    """Append the next version of this item's recipe. Editing IS appending:
    old versions are never touched, the newest is current, and the history is
    the table itself (WP-60)."""
    db: Database = request.app.state.db
    item = await _live_item(db, menu_item_id)

    yield_portions = _positive_number(body.yield_portions, what="yield", example="40")
    if not body.components:
        raise HTTPException(
            status_code=422,
            detail="a recipe needs at least one component: an empty recipe would "
            "cost nothing and read as pure margin",
        )

    components: list[dict] = []
    for index, component in enumerate(body.components):
        ingredient = await db.get_ingredient(str(component.ingredient_id))
        # 404 with the same wording for missing and cross-tenant alike (the M5
        # pattern): another tenant's materials do not exist here, and Postgres'
        # composite key refuses the write regardless of what this check missed.
        if ingredient is None or ingredient["tenant_id"] != item["tenant_id"]:
            raise HTTPException(
                status_code=404, detail=f"component {index + 1}: ingredient not found"
            )
        qty = _positive_number(component.qty, what="quantity", example="130")
        unit = _component_unit(component.unit, ingredient)
        components.append(
            {
                "ingredient_id": str(component.ingredient_id),
                "qty": qty,
                "unit": unit,
                "source_text": _clean(component.source_text),
            }
        )

    try:
        await db.create_recipe_version(
            str(menu_item_id),
            tenant_id=item["tenant_id"],
            yield_portions=yield_portions,
            yield_label=_clean(body.yield_label),
            components=components,
            actor=CONSOLE_ACTOR,
        )
    except asyncpg.UniqueViolationError:
        # Two concurrent saves computed the same max+1; the constraint let
        # exactly one through (D17).
        raise HTTPException(
            status_code=409,
            detail="someone else saved a new version of this recipe at the same "
            "moment; reload it and try again",
        ) from None
    return await _menu_item_detail(db, str(menu_item_id))
