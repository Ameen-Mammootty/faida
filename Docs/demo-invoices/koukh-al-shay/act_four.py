"""Act four's figures, printed by the shipped code (M9 WP-95).

Act three closes on a branch's ratio - purchases divided by net sales. Act four
asks the question one layer up: *of what the branch took, how much did it keep,
and which dish is eating it?* That answer is `GET /api/dashboard`, and every
figure `DEMO_RUNBOOK.md` §H quotes is printed here rather than typed there.

It is not a second implementation of anything. The script stages the chain the
way a person does - the menu through the loader's door, the papers through the
typed-invoice door and the confirm, each pack mapped to its material through
the materials queue, the week through `POST /api/sales/days`, one keystroke per
till name - and then reads the shipped route. Only two things are simulated:
the browser (the app is driven in process) and the sign-in (the token check is
replaced by a fixed `AuthContext`, so a demo figure needs no key material).
Every number below came back over the wire from `dashboard.py`.

    apps/api/.venv/bin/python Docs/demo-invoices/koukh-al-shay/act_four.py --migrate \\
        --database-url postgresql://localhost:5432/faida_act_four            # the practice stage
    ... --stage real                                                        # the real menu
    ... --stage real --menu-csv <path to faida-loader-preview.csv>

`--migrate` drops and rebuilds `public` from `supabase/migrations/` first, so a
throwaway database needs no other preparation. **It destroys everything in that
database**, it refuses to run without an explicit `--database-url` or
`TEST_DATABASE_URL`, and it must never be pointed at a database anyone cares
about.

**Two stages, because they say different things.**

*practice* is `demo_seed.sql`'s five costed items and the rehearsal week
`build_sales_week.py --practice` generates against the purchases that seed
stages. It lives entirely inside the repository, so it is the stage
`tests/test_demo_seed.py` pins - and it is a five-item tea menu, where every
dish keeps over eighty per cent and nothing is ten points below the average, so
**no signal fires on it**. That is C13.3a's own warning about a relative rule on
a very short menu, not a fault.

*real* is the stage the demo runs on: the 45-item menu, the five KAS papers,
and the committed `sales-week.csv`. It needs the founder's menu CSV, which
lives outside the repository, so CI cannot reach it - but it is the only stage
whose figures act four actually speaks, and it prints them twice, before and
after the on-stage paper, which is the reload beat.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import csv
import datetime
import importlib.util
import os
import pathlib
import sys
from decimal import Decimal

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "apps/api/src"))
sys.path.insert(0, str(HERE))

import httpx  # noqa: E402
from build_prompts import SUPPLIERS, totals  # noqa: E402
from faida_api.api import router as api_router  # noqa: E402
from faida_api.auth import AuthContext, require_context  # noqa: E402
from faida_api.config import Settings  # noqa: E402
from faida_api.dashboard import router as dashboard_router  # noqa: E402
from faida_api.db import Database  # noqa: E402
from faida_api.menu import router as menu_router  # noqa: E402
from faida_api.sales import router as sales_router  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from plate_costs import DEFAULT_CSV, MATERIAL_BY_CODE, load_recipes  # noqa: E402

MIGRATIONS = REPO / "supabase" / "migrations"
DEMO_SEED = REPO / "supabase" / "demo_seed.sql"
REAL_WEEK_CSV = HERE / "sales-week.csv"

#: The demo chain (`demo_seed.sql`) and the one person signed in to it. The
#: user id is not a row anywhere: the token check is what this script replaces,
#: and every read below is still scoped by the tenant on this context (C10).
TENANT_ID = "d0000000-0000-0000-0000-000000000001"
USER_ID = "00000000-0000-4000-8000-0000000000f4"

#: What the queue asks a person, once per till name, on the practice stage.
#: The real stage's answers are read from the menu CSV instead.
PRACTICE_MENU_ITEM_BY_TILL_NAME = {
    "KARAK TEA CUP": "Karak Tea (Cup)",
    "KARAK FLASK 1L": "Karak Tea (Flask 1 L)",
    "CARDAMOM CHAI 2L": "Cardamom Chai (Flask 2 L)",
    "NIDO TEA": "Nido Milk Tea",
    "PARATHA": "Paratha",
}

#: Takings, not a menu item: it stays in net sales and leaves the queue.
NOT_A_MENU_ITEM = ("DELIVERY CHARGE",)

#: The papers, by role - the same split `build_sales_week.py` uses. KAS-1..4
#: are confirmed in preparation; KAS-5 is the one forwarded on stage, and the
#: read is taken before and after it so the reload beat has a figure.
PREPARATION_PAPERS = ("KAS-1", "KAS-2", "KAS-3", "KAS-4")
ON_STAGE_PAPER = "KAS-5"


def _generator():
    """`build_sales_week.py` as a module: it is a demo script beside this one,
    not a package, so it is imported from its path the way the seed test does."""
    path = HERE / "build_sales_week.py"
    spec = importlib.util.spec_from_file_location("build_sales_week", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(module)
    return module


GEN = _generator()


# --- the app ----------------------------------------------------------------


def _app(db: Database, database_url: str) -> FastAPI:
    """The shipped routers over a real database, with the sign-in replaced by
    a fixed context - the one thing a demo script may not carry keys for."""
    app = FastAPI()
    for router in (api_router, menu_router, sales_router, dashboard_router):
        app.include_router(router)
    app.state.settings = Settings(database_url=database_url, worker_enabled=False)
    app.state.db = db
    app.dependency_overrides[require_context] = lambda: AuthContext(
        user_id=USER_ID, tenant_id=TENANT_ID, actor=f"user:{USER_ID}"
    )
    return app


async def _migrate(database_url: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(database_url)
    try:
        await conn.execute("drop schema public cascade; create schema public;")
        for migration in sorted(MIGRATIONS.glob("*.sql")):
            await conn.execute(migration.read_text())
    finally:
        await conn.close()


async def _post(client: httpx.AsyncClient, path: str, body: dict | None = None) -> dict:
    response = await client.post(path, json=body)
    if response.status_code >= 400:
        raise SystemExit(f"POST {path} -> {response.status_code} {response.text}")
    return response.json()


async def _get(client: httpx.AsyncClient, path: str, **params) -> dict:
    response = await client.get(path, params=params or None)
    if response.status_code >= 400:
        raise SystemExit(f"GET {path} -> {response.status_code} {response.text}")
    return response.json()


# --- the sales week, through the loader's door -------------------------------


def _days(rows, label_to_id: dict[str, str]) -> list[dict]:
    """The loader's own grouping: one item day per outlet and date, lines in
    file order, the outlet resolved through the alias a first upload teaches."""
    days: dict[tuple[str, datetime.date | str], dict] = {}
    for outlet, date, code, name, qty, amount in rows:
        day = days.setdefault(
            (outlet, date),
            {
                "branch_id": label_to_id[outlet],
                "business_date": date if isinstance(date, str) else date.isoformat(),
                "granularity": "item",
                "amount_basis": "inclusive",
                "lines": [],
            },
        )
        day["lines"].append(
            {
                "position": len(day["lines"]),
                "name": name,
                "code": code,
                "qty": qty,
                "amount": amount,
            }
        )
    return [days[key] for key in sorted(days, key=lambda key: (key[0], str(key[1])))]


async def _load_week(client: httpx.AsyncClient, days: list[dict]) -> list[str]:
    """One branch per request, the way the screen posts a branch-month."""
    by_branch: dict[str, list[dict]] = {}
    for day in days:
        by_branch.setdefault(day["branch_id"], []).append(day)
    outcomes: list[str] = []
    for branch_days in by_branch.values():
        answer = await _post(client, "/api/sales/days", {"days": branch_days})
        outcomes.extend(day["outcome"] for day in answer["days"])
    return outcomes


async def _map_till_names(client: httpx.AsyncClient, answers: dict[str, str]) -> tuple[int, int]:
    """One keystroke per till name, through the doors the queue offers: this
    name is that dish, or this name is not a menu item at all."""
    menu = {
        item["name"]: item["id"] for item in (await _get(client, "/api/menu-items"))["menu_items"]
    }
    mapped = excluded = 0
    for row in (await _get(client, "/api/sales/coverage"))["queue"]:
        name = row["name"]
        if name in NOT_A_MENU_ITEM:
            await _post(client, f"/api/till-items/{row['till_item_id']}/exclude")
            excluded += 1
            continue
        item_name = answers.get(name)
        if item_name is None or item_name not in menu:
            raise SystemExit(f"the queue offers {name!r} and this script has no answer for it")
        await _post(
            client,
            f"/api/till-items/{row['till_item_id']}/menu-item",
            {"menu_item_id": menu[item_name]},
        )
        mapped += 1
    return mapped, excluded


# --- the practice stage ------------------------------------------------------


async def practice_stage(client: httpx.AsyncClient, db: Database, database_url: str) -> list[tuple]:
    """`demo_seed.sql`'s five costed items, and the rehearsal week generated
    against the purchases that seed stages (their dates are read from the
    database, never computed from today)."""
    await db.pool.execute(DEMO_SEED.read_text())
    stage = await GEN.read_practice_stage(database_url)
    week = GEN.practice_week(stage.end)
    label_to_id = {branch.till_label: branch.branch_id for branch in GEN.BRANCHES}
    rows = [
        (row.outlet, row.date, row.code, row.item, str(row.qty), f"{row.amount:.2f}")
        for row in week.rows
    ]
    outcomes = await _load_week(client, _days(rows, label_to_id))
    mapped, excluded = await _map_till_names(client, PRACTICE_MENU_ITEM_BY_TILL_NAME)
    print(
        f"staged the practice chain: {len(outcomes)} days {sorted(set(outcomes))}, "
        f"{week.start:%d/%m/%Y} to {week.end:%d/%m/%Y}, {mapped} till names mapped, "
        f"{excluded} not a menu item"
    )
    return [("the practice stage", await _get(client, "/api/dashboard"))]


# --- the real stage ----------------------------------------------------------


async def _create_chain(db: Database) -> None:
    """The chain and its three outlets. Tenants and branches have no API door -
    onboarding writes them - so this is the only door there is."""
    await db.pool.execute(
        "insert into tenants (id, name, currency) values ($1, $2, 'AED') "
        "on conflict (id) do nothing",
        TENANT_ID,
        "Karak Al Khaleej Cafeterias",
    )
    for branch in GEN.BRANCHES:
        await db.pool.execute(
            "insert into branches (id, tenant_id, name, timezone) "
            "values ($1, $2, $3, 'Asia/Dubai') on conflict (id) do nothing",
            branch.branch_id,
            TENANT_ID,
            branch.name,
        )


async def _load_menu(client: httpx.AsyncClient, recipes: dict) -> tuple[int, int]:
    """The consultant's morning: one shelf per material the menu names, then
    one recipe per dish through the loader's door."""
    units_by_material: dict[str, str] = {}
    for item in recipes.values():
        for name, _qty, unit in item["components"]:
            units_by_material.setdefault(name, unit)
    ingredients: dict[str, str] = {}
    for name, unit in units_by_material.items():
        created = await _post(client, "/api/ingredients", {"name": name, "unit": unit})
        ingredients[name] = created["id"]
    for item in recipes.values():
        await _post(
            client,
            "/api/menu-items/load",
            {
                "name": item["name"],
                "category": item["category"],
                "selling_price": f"{item['price']:.2f}",
                "yield_portions": str(item["yield_portions"]),
                "components": [
                    {"ingredient_id": ingredients[name], "qty": str(qty), "unit": unit}
                    for name, qty, unit in item["components"]
                ],
            },
        )
    return len(ingredients), len(recipes)


async def _type_and_confirm(client: httpx.AsyncClient, key: str) -> None:
    """One KAS paper through the typed-invoice door and the confirm - the same
    validation, snapping and costing a photographed one goes through, with the
    model absent. The papers print credit terms, so the confirm is allowed."""
    supplier = SUPPLIERS[key]
    day, month, year = supplier[5].split("/")
    subtotal, tax, total = totals(key)
    body = {
        "branch_id": GEN.FLAGSHIP.branch_id,
        "supplier_name": supplier[0],
        "invoice_no": supplier[4],
        "invoice_date": f"{year}-{month}-{day}",
        "currency": "AED",
        "payment_kind": "credit",
        "subtotal": f"{subtotal:.2f}",
        "tax": f"{tax:.2f}",
        "total": f"{total:.2f}",
        "lines": [
            {
                "raw_name": desc,
                "qty": str(qty),
                "unit": unit,
                "pack_size": pack,
                "unit_price": f"{Decimal(str(price)):.2f}",
                "line_total": f"{(Decimal(str(qty)) * Decimal(str(price))):.2f}",
            }
            for _code, desc, qty, unit, pack, price in supplier[6]
        ],
    }
    invoice = await _post(client, "/api/invoices/manual", body)
    await _post(client, f"/api/invoices/{invoice['id']}/confirm")


async def _map_materials(client: httpx.AsyncClient) -> int:
    """The `/materials` queue, one keystroke a row: this pack is that shelf.
    The answer key is `plate_costs.MATERIAL_BY_CODE`, the same mapping the
    plate script has always used, reached through each pack's printed
    description."""
    material_by_desc = {
        desc: MATERIAL_BY_CODE[code]
        for supplier in SUPPLIERS.values()
        for code, desc, *_ in supplier[6]
    }
    ingredients = {
        row["name"]: row["id"] for row in (await _get(client, "/api/ingredients"))["ingredients"]
    }
    mapped = 0
    for item in (await _get(client, "/api/supplier-items/unmapped"))["items"]:
        material = material_by_desc.get(item["canonical_name"])
        if material is None:
            raise SystemExit(f"no material for the pack {item['canonical_name']!r}")
        await _post(
            client,
            f"/api/supplier-items/{item['id']}/ingredient",
            {"ingredient_id": ingredients[material]},
        )
        mapped += 1
    return mapped


async def real_stage(
    client: httpx.AsyncClient, db: Database, menu_csv: pathlib.Path
) -> list[tuple]:
    """The stage the demo runs on: the 45-item menu, the five KAS papers, the
    committed week - and the read taken twice, before and after the paper the
    founder forwards on stage. The caller checks the menu CSV is there first -
    `main` below, or the seed test's own skip."""
    recipes = load_recipes(menu_csv)
    await _create_chain(db)
    materials, items = await _load_menu(client, recipes)
    for key in PREPARATION_PAPERS:
        await _type_and_confirm(client, key)
    packs = await _map_materials(client)

    with REAL_WEEK_CSV.open(newline="") as handle:
        rows = [row for row in list(csv.reader(handle))[1:] if row[1]]
    label_to_id = {branch.till_label: branch.branch_id for branch in GEN.BRANCHES}
    days = _days(
        [
            (outlet, f"{date[6:10]}-{date[3:5]}-{date[0:2]}", code, name, qty, amount)
            for outlet, date, code, name, qty, amount in rows
        ],
        label_to_id,
    )
    outcomes = await _load_week(client, days)
    answers = {GEN._till_name(code, item["name"]): item["name"] for code, item in recipes.items()}
    mapped, excluded = await _map_till_names(client, answers)
    print(
        f"staged the real chain: {materials} materials, {items} recipes, "
        f"{len(PREPARATION_PAPERS)} papers confirmed, {packs} packs mapped to a shelf, "
        f"{len(outcomes)} days {sorted(set(outcomes))}, {mapped} till names mapped, "
        f"{excluded} not a menu item"
    )
    before = await _get(client, "/api/dashboard")
    await _type_and_confirm(client, ON_STAGE_PAPER)
    after = await _get(client, "/api/dashboard")
    return [
        (f"the real stage, before {ON_STAGE_PAPER}", before),
        (f"the real stage, after {ON_STAGE_PAPER} is confirmed on stage", after),
    ]


# --- what act four says ------------------------------------------------------


def _aed(value: str | None) -> str:
    return "-" if value is None else f"AED {Decimal(value):,.2f}"


def _fils(value: str | None) -> str:
    """A per-plate figure to the fils: a karak margin rounded to whole dirhams
    carries no information (CLAUDE.md's display rules)."""
    return "-" if value is None else f"AED {Decimal(value):,.3f}"


def _pct(value: str | None) -> str:
    return "-" if value is None else f"{value}%"


def report(title: str, payload: dict) -> None:
    """Every figure §H quotes, in the order the script reads them."""
    period, answer = payload["period"], payload["answer"]
    print()
    print("=" * 96)
    print(title.upper())
    print("=" * 96)
    print("PERIOD")
    print(
        f"  {period['from']} to {period['to']} ({period['days']} days), "
        f"{'the default' if period['default'] else 'chosen'}; plates costed at the "
        f"prices in force on {period['costed_at']}"
    )
    print(f"  {payload['freshness']['sentence']}")
    print(f"  menu: {payload['menu']['items']} live items, {payload['menu']['costed']} costed")
    print()

    print("THE ONE SENTENCE")
    print(f"  {answer['branch'] or '(no branch carries a contribution figure)'}")
    print(
        f"  {answer['item'] or '(no dish sells and keeps ten points less than the menu average)'}"
    )
    print(f"  quality: {answer['quality']}")
    for note in answer["notes"]:
        print(f"    - {note}")
    print()

    print("THE LEAGUE (ordered by kept percentage, lowest first)")
    print(
        f"  {'branch':18} {'net sales':>12} {'contribution':>13} {'kept':>7} "
        f"{'costed':>7} {'ratio':>7}  contribution quality"
    )
    for row in [*payload["league"], None]:
        if row is None:
            row, name = payload["total"], "THE CHAIN"
        else:
            name = row["branch_name"]
        print(
            f"  {name:18} {_aed(row['net_sales']):>12} {_aed(row['contribution']):>13} "
            f"{_pct(row['contribution_pct']):>7} {_pct(row['costed_share_pct']):>7} "
            f"{_pct(row['ratio_pct']):>7}  {row['contribution_quality']}: "
            f"{'; '.join(row['contribution_notes'])}"
        )
    print()

    print("THE ITEMS (best five and worst five by what they contributed)")
    for caption, rows in (("best", payload["items"]["top"]), ("worst", payload["items"]["bottom"])):
        for row in rows:
            print(
                f"  {caption:5} {row['menu_item_name']:30.30} sold {row['qty_sold']:>10} "
                f"{_aed(row['net_item_sales']):>12} kept {_aed(row['contribution']):>12} "
                f"{_pct(row['contribution_pct']):>7}"
            )
    incomplete = [r for r in payload["items"]["all"] if r["contribution"] is None]
    for row in incomplete[:5]:
        print(
            f"  {'-':5} {row['menu_item_name']:30.30} {'incomplete':>10}  {'; '.join(row['notes'])}"
        )
    if len(incomplete) > 5:
        print(f"  {'-':5} and {len(incomplete) - 5} more with no numbers")
    print(f"  {payload['items']['count']} costed rows of {len(payload['items']['all'])}")
    print()

    worst = (payload["items"]["bottom"] or payload["items"]["top"])[-1:]
    for row in worst:
        print(f"THE DRILL ({row['menu_item_name']}, the row act four opens)")
        print(
            f"  sold at an average of {_fils(row['avg_sold_at'])} net of VAT against a menu price "
            f"of {_fils(row['net_price'])}; {_fils(row['cost_per_portion'])} of ingredients and "
            f"packaging; recipe version {row['recipe_version']}"
        )
        for component in row["components"]:
            print(
                f"    {component['ingredient_name']:26} {component['qty']:>10} "
                f"{component['unit']:4} {_fils(component['cost_per_portion']):>12}  "
                f"invoice line {component['line_position']}, bought {component['purchased_on']}"
            )
        print(f"  till names: {', '.join(t['name'] for t in row['till_items'])}")
        print()

    print("THE SIGNALS (ranked by the money at stake, capped at five)")
    if not payload["signals"]:
        print("  none - nothing on this stage clears a threshold")
    for position, signal in enumerate(payload["signals"], start=1):
        print(f"  {position}. [{signal['kind']}] {_aed(signal['money_at_stake'])} at stake")
        print(f"     {signal['sentence']}")
        print(f"     {signal['detail']}")
        if signal["moved_on"] is not None:
            print(f"     moved on {signal['moved_on']}, invoice {signal['invoice_id']}")
    spikes = [s for s in payload["signals"] if s["kind"] == "price_spike"]
    print(
        "  price spike: "
        + (
            ", ".join(f"{s['ingredient_name']} on {s['moved_on']}" for s in spikes)
            if spikes
            else "none on this stage"
        )
    )
    print()

    print("THE QUIET FIGURES")
    approvals = payload["approvals"]
    print(
        f"  papers held for review {approvals['count']} ({approvals['duplicates']} duplicates), "
        f"awaiting a branch's OK {approvals['awaiting_confirm']}"
    )
    print(
        f"  unmapped till names {payload['unmapped']['names']}, "
        f"worth {_aed(payload['unmapped']['value'])}"
    )
    latest = payload["latest_day"]
    print(
        "  newest loaded day: "
        + (
            "outside the period"
            if latest is None
            else f"{latest['date']}, {_aed(latest['net_sales'])}"
        )
    )


# --- the run -----------------------------------------------------------------


async def run(
    database_url: str, *, stage: str, migrate: bool, menu_csv: pathlib.Path
) -> list[tuple]:
    if migrate:
        await _migrate(database_url)
    db = Database(database_url)
    await db.connect()
    try:
        app = _app(db, database_url)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://act-four"
        ) as client:
            if stage == "practice":
                return await practice_stage(client, db, database_url)
            return await real_stage(client, db, menu_csv)
    finally:
        await db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL"),
        help="a throwaway Postgres this script may seed (TEST_DATABASE_URL or DATABASE_URL)",
    )
    parser.add_argument("--stage", choices=("practice", "real"), default="practice")
    parser.add_argument(
        "--menu-csv",
        type=pathlib.Path,
        default=DEFAULT_CSV,
        help="the real menu in the loader's shape (--stage real)",
    )
    parser.add_argument(
        "--migrate",
        action="store_true",
        help="drop and rebuild the public schema from supabase/migrations first - DESTRUCTIVE",
    )
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("no database: pass --database-url, or set TEST_DATABASE_URL")
    if args.stage == "real" and not args.menu_csv.exists():
        raise SystemExit(
            f"the real menu is not here: {args.menu_csv}\n"
            "It lives outside the repository. Pass --menu-csv, or run --stage practice."
        )
    reads = asyncio.run(
        run(args.database_url, stage=args.stage, migrate=args.migrate, menu_csv=args.menu_csv)
    )
    for title, payload in reads:
        report(title, payload)


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        main()
