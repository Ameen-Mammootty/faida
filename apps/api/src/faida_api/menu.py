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

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from .api import CONSOLE_ACTOR, MEASURE_WORDS, _clean, _dec, _iso, _tenant, require_api_token
from .confirm import _parse_number
from .db import Database
from .extraction import units

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


# --- serialization ----------------------------------------------------------


async def _menu_item_detail(db: Database, menu_item_id: str) -> dict:
    """The full item payload every write returns (C6): the item, its current
    recipe version and that version's components, each carrying its
    ingredient's name so the screen never joins by hand."""
    item = await db.get_menu_item(menu_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="menu item not found")
    recipe = await db.get_current_recipe(menu_item_id)
    components = [] if recipe is None else await db.get_recipe_components(recipe["id"])
    return {
        "id": item["id"],
        "name": item["name"],
        "selling_price": _dec(item["selling_price"]),
        "archived_at": _iso(item["archived_at"]),
        "created_at": _iso(item["created_at"]),
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
                }
                for component in components
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
    """Every item with its current recipe version - archived ones included and
    flagged, because the loader grid names them rather than pretending they
    are gone (WP-64). One query however long the menu grows (D10)."""
    db: Database = request.app.state.db
    tenant_id = await _tenant(db)
    return {
        "menu_items": [
            {
                "id": row["id"],
                "name": row["name"],
                "selling_price": _dec(row["selling_price"]),
                "archived_at": _iso(row["archived_at"]),
                "created_at": _iso(row["created_at"]),
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
            for row in await db.list_menu_items(tenant_id)
        ]
    }


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
