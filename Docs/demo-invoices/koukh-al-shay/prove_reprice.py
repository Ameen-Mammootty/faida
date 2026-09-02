"""Prove supabase/apply_kas_reprice.sql on a local replica of the real stage.

Builds a stage shaped like the live demo project - the chain tenant, the four
KAS suppliers, KAS-1..4 confirmed at the OLD prices through the real
`record_confirmed_prices` door, every catalog row mapped to a material, and a
menu row on top - then runs the adoption script and checks the things that
must survive and the things that must go. Finally it re-confirms the NEW
papers and proves every line snapped back onto its ORIGINAL catalog row, which
is the claim the script's comment makes.

    TEST_DATABASE_URL=postgresql://localhost:5432/faida_test \
      apps/api/.venv/bin/python <this file>
"""

import asyncio
import datetime
import json
import os
import pathlib
import subprocess
import sys
from decimal import Decimal

sys.path.insert(0, "apps/api/src")
sys.path.insert(0, "Docs/demo-invoices/koukh-al-shay")

import asyncpg  # noqa: E402
from build_prompts import SUPPLIERS as NEW  # noqa: E402

from faida_api.db import Database  # noqa: E402

DB_URL = os.environ["TEST_DATABASE_URL"]
TENANT = "d0000000-0000-0000-0000-000000000001"
BRANCH = "d0000000-0000-0000-0000-0000000000b1"
# Read once, synchronously: the SQL is an input to this script, not something
# an async function should block on mid-run.
MIGRATIONS = [m.read_text() for m in sorted(pathlib.Path("supabase/migrations").glob("*.sql"))]
SEED = pathlib.Path("supabase/seed.sql").read_text()
SCRIPT = pathlib.Path("supabase/apply_kas_reprice.sql").read_text()

PAPERS = ("KAS-1", "KAS-2", "KAS-3", "KAS-4")

old_src = subprocess.run(
    ["git", "show", "master:Docs/demo-invoices/koukh-al-shay/build_prompts.py"],
    capture_output=True,
    text=True,
    check=True,
).stdout
_ns: dict = {}
exec(old_src.split("if __name__")[0], _ns)
OLD = _ns["SUPPLIERS"]


async def fresh_schema() -> None:
    conn = await asyncpg.connect(DB_URL)
    await conn.execute("drop schema public cascade; create schema public;")
    for migration in MIGRATIONS:
        await conn.execute(migration)
    await conn.execute(SEED)
    await conn.close()


async def stage(db: Database, table) -> dict[str, str]:
    """The chain tenant with its four suppliers and one branch."""
    await db.pool.execute(
        "insert into tenants (id, name, currency) values ($1, 'Koukh Al Shay', 'AED') "
        "on conflict do nothing",
        TENANT,
    )
    await db.pool.execute(
        "insert into branches (id, tenant_id, name) values ($1, $2, 'Al Qusais Branch') "
        "on conflict do nothing",
        BRANCH,
        TENANT,
    )
    suppliers = {}
    for paper in PAPERS:
        name = table[paper][0]
        suppliers[paper] = await db.pool.fetchval(
            "insert into suppliers (tenant_id, name) values ($1, $2) returning id::text",
            TENANT,
            name,
        )
    return suppliers


async def confirm_paper(db: Database, paper: str, supplier_id: str, table) -> str:
    """One paper through the real confirm door: rows the pipeline would write,
    then `record_confirmed_prices`, which is what builds the catalog."""
    _sup, _addr, _ph, _trn, number, date, rows, _look = table[paper]
    day, month, year = date.split("/")
    doc = await db.pool.fetchval(
        "insert into documents (tenant_id, branch_id, source, status) "
        "values ($1, $2, 'whatsapp', 'extracted') returning id::text",
        TENANT,
        BRANCH,
    )
    subtotal = sum(
        (Decimal(str(q)) * Decimal(str(p))).quantize(Decimal("0.01"))
        for *_, q, _u, _pk, p in ((r[0], r[1], r[2], r[3], r[4], r[5]) for r in rows)
    )
    tax = (subtotal * Decimal("0.05")).quantize(Decimal("0.01"))
    invoice = await db.pool.fetchval(
        """
        insert into invoices (tenant_id, branch_id, document_id, supplier_id, supplier_name,
                              invoice_no, invoice_date, currency, subtotal, tax, total,
                              payment_kind, status, tax_treatment, vat_rate)
        values ($1,$2,$3,$4,$5,$6,$7,'AED',$8,$9,$10,'credit','confirmed','exclusive',0.05)
        returning id::text
        """,
        TENANT,
        BRANCH,
        doc,
        supplier_id,
        table[paper][0],
        number,
        datetime.date(int(year), int(month), int(day)),
        subtotal,
        tax,
        subtotal + tax,
    )
    await db.pool.executemany(
        """
        insert into invoice_lines (tenant_id, invoice_id, position, raw_name, qty, unit,
                                   unit_price, line_total, pack_size, checks, line_kind)
        values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'stock_item')
        """,
        [
            (
                TENANT,
                invoice,
                i,
                desc,
                Decimal(str(qty)),
                unit,
                Decimal(str(price)),
                (Decimal(str(qty)) * Decimal(str(price))).quantize(Decimal("0.01")),
                pack,
                json.dumps({}),
            )
            for i, (code, desc, qty, unit, pack, price) in enumerate(rows)
        ],
    )
    await db.record_confirmed_prices(invoice)
    return invoice


async def catalog(db: Database) -> dict[str, dict]:
    rows = await db.pool.fetch(
        "select id::text, canonical_name, pack_size, ingredient_id::text, last_price "
        "from supplier_items where tenant_id = $1",
        TENANT,
    )
    return {r["canonical_name"]: dict(r) for r in rows}


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' - ' + detail) if detail else ''}")
    return ok


async def main() -> None:
    await fresh_schema()
    db = Database(DB_URL)
    await db.connect()
    ok = True

    # ---- build the stage as it stands live today: OLD papers confirmed ----
    suppliers = await stage(db, OLD)
    for paper in PAPERS:
        await confirm_paper(db, paper, suppliers[paper], OLD)

    before = await catalog(db)
    # Every catalog row mapped to a material, as the /materials queue would.
    for name in before:
        ing = await db.pool.fetchval(
            "insert into ingredients (tenant_id, name, base_unit) values ($1, $2, 'g') "
            "returning id::text",
            TENANT,
            f"material for {name}",
        )
        await db.pool.execute(
            "update supplier_items set ingredient_id = $2 where id = $1::uuid",
            before[name]["id"],
            ing,
        )
    # A menu row, standing in for the 45 the live project holds.
    await db.pool.execute(
        "insert into menu_items (tenant_id, name, selling_price) values ($1, 'Karak', 3.00)",
        TENANT,
    )

    before = await catalog(db)
    counts_before = {
        "supplier_items": len(before),
        "ingredients": await db.pool.fetchval(
            "select count(*) from ingredients where tenant_id = $1", TENANT
        ),
        "menu_items": await db.pool.fetchval(
            "select count(*) from menu_items where tenant_id = $1", TENANT
        ),
        "mapped": sum(1 for r in before.values() if r["ingredient_id"]),
    }
    print(f"\nStage built: {counts_before}")
    print(f"  chicken baseline before: {before['CHICKEN BONELESS']['last_price']}")

    # ---- run the adoption script ----
    print("\nRunning supabase/apply_kas_reprice.sql")
    conn = await asyncpg.connect(DB_URL)
    await conn.execute(SCRIPT)
    await conn.close()

    after = await catalog(db)
    ok &= check(
        "every catalog row survives",
        len(after) == counts_before["supplier_items"],
        f"{len(after)} of {counts_before['supplier_items']}",
    )
    ok &= check(
        "every mapping survives",
        sum(1 for r in after.values() if r["ingredient_id"]) == counts_before["mapped"],
        f"{sum(1 for r in after.values() if r['ingredient_id'])} mapped",
    )
    ok &= check(
        "ingredients untouched",
        await db.pool.fetchval("select count(*) from ingredients where tenant_id = $1", TENANT)
        == counts_before["ingredients"],
    )
    ok &= check(
        "menu untouched",
        await db.pool.fetchval("select count(*) from menu_items where tenant_id = $1", TENANT)
        == counts_before["menu_items"],
    )
    ok &= check(
        "the four invoices are gone",
        await db.pool.fetchval("select count(*) from invoices where tenant_id = $1", TENANT) == 0,
    )
    ok &= check(
        "their documents are gone",
        await db.pool.fetchval("select count(*) from documents where tenant_id = $1", TENANT) == 0,
    )
    ok &= check(
        "no price history left",
        await db.pool.fetchval(
            "select count(*) from supplier_item_prices p join supplier_items s "
            "on s.id = p.supplier_item_id where s.tenant_id = $1",
            TENANT,
        )
        == 0,
    )
    ok &= check("every baseline cleared", all(r["last_price"] is None for r in after.values()))
    ok &= check(
        "stale packs corrected",
        after["GARLIC PEELED"]["pack_size"] == "1 kg"
        and after["CURRY LEAVES"]["pack_size"] == "100 g"
        and after["TOOR DAL"]["pack_size"] == "15 kg"
        and after["LIGHT SOY SAUCE"]["pack_size"] == "4 l"
        and after["INSTANT COFFEE"]["pack_size"] == "200 g",
        f"garlic={after['GARLIC PEELED']['pack_size']}",
    )
    ok &= check(
        "habbat renamed to the seed",
        "HABBAT AL HAMRA SEEDS" in after and "HABBAT AL HAMRA BLEND" not in after,
    )

    # ---- idempotence ----
    conn = await asyncpg.connect(DB_URL)
    await conn.execute(SCRIPT)
    await conn.close()
    ok &= check("running it twice is a no-op", len(await catalog(db)) == len(after))

    # ---- re-forward the NEW papers: the claim that matters ----
    print("\nRe-confirming the NEW papers")
    ids_before = {n: r["id"] for n, r in after.items()}
    for paper in PAPERS:
        await confirm_paper(db, paper, suppliers[paper], NEW)
    final = await catalog(db)

    ok &= check(
        "no new catalog rows minted",
        len(final) == len(after),
        f"{len(final)} vs {len(after)}",
    )
    moved = [n for n, r in final.items() if n in ids_before and r["id"] != ids_before[n]]
    ok &= check("every line snapped back to its ORIGINAL row", not moved, str(moved))
    ok &= check(
        "every row still mapped",
        all(r["ingredient_id"] for r in final.values()),
        f"{sum(1 for r in final.values() if not r['ingredient_id'])} unmapped",
    )
    ok &= check(
        "chicken now carries the researched price",
        final["CHICKEN BONELESS"]["last_price"] == Decimal("180.00"),
        str(final["CHICKEN BONELESS"]["last_price"]),
    )
    ok &= check(
        "evaporated milk too",
        final["EVAP MILK 48X400ML"]["last_price"] == Decimal("221.00"),
        str(final["EVAP MILK 48X400ML"]["last_price"]),
    )

    await db.close()
    print("\n" + ("ALL CHECKS PASSED" if ok else "SOMETHING FAILED"))
    sys.exit(0 if ok else 1)


asyncio.run(main())
