"""A week of till sales for the three demo branches, generated from the shipped code (M8 WP-85).

Act three closes on a ranked branch table: purchases ÷ net sales (cash basis), per branch,
every purchase one click from an invoice photo. The purchases are real - the KAS papers, or
the practice stage's staged invoices - but no till has ever exported a week for this chain,
so this script invents one. **The demo's sales are invented; its purchases are not; and the
screen's honesty claim is about the second.** The README and the runbook say so in those words.

The file it writes is what a till prints: one row per item sold per outlet per day, in the
header the loader pins (`Outlet,Date,PLU,Item,Qty,Amount`), dates day-first, amounts with the
VAT inside them, item names in the till's own upper-case shorthand with the code beside, one
`DELIVERY CHARGE` line a day so the coverage panel has a "not a menu item" to show, and a
totals footer with no date that the loader skips and counts. A fixed seed makes it
reproducible: the committed `sales-week.csv` is exactly what this script prints.

It is not a second implementation. `takings.net_amount` divides the VAT out per line the way
the door does, and `ratio.period_row` computes the row the screen will show, from the shipped
package, so the figures printed here are the figures the founder will point at. What is
simulated is only the till.

    apps/api/.venv/bin/python Docs/demo-invoices/koukh-al-shay/build_sales_week.py
    ... --csv <path to faida-loader-preview.csv>     # the real 45-item menu (default)
    ... --practice                                   # the five staged items, dates from the DB
    ... --out <path>                                 # where to write the CSV

Two weeks, two calendars. The **real week** is the seven days ending on KAS-5's printed date,
read from `build_prompts.SUPPLIERS` and never typed here, so a reprinted prop moves the week
with it; that week holds KAS-3 and KAS-4 (printed 25/08) and, once the founder forwards it on
stage, KAS-5 - so the on-stage confirm moves Al Qusais's ratio live. The **practice week**
(`--practice`) is the seven days ending on the demo tenant's newest staged purchase day, read
from the database, because `demo_seed.sql` stages its purchases relative to the moment it
runs and a date computed from "today" drifts off them within days.

The volume constant `VOLUME` is chosen so Al Qusais's ratio sits in a plausible 30-40% band:
about 30% before KAS-5 and about 40% after it. The other two branches have sales and no
papers, so they read *incomplete* on purpose (the founder's call, P3): two honest rows are the
label doing its job on stage.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import datetime
import os
import pathlib
import random
import sys
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "apps/api/src"))
sys.path.insert(0, str(HERE))

from build_prompts import SUPPLIERS, totals  # noqa: E402
from plate_costs import DEFAULT_CSV, load_recipes  # noqa: E402

from faida_api import ratio, takings  # noqa: E402
from faida_api.extraction.constants import VAT_RATE_BY_CURRENCY  # noqa: E402

CURRENCY = "AED"
VAT_RATE = VAT_RATE_BY_CURRENCY[CURRENCY]

#: The header the loader pins (Docs/M8_DECOMPOSITION.md §3.1), so the file and the
#: layout the consultant saves on the first upload agree without meeting.
HEADER = ("Outlet", "Date", "PLU", "Item", "Qty", "Amount")

#: The demo chain (supabase/demo_seed.sql), and what its till prints for each outlet -
#: deliberately not Faida's branch names, so the first upload teaches three aliases once
#: and every upload after that needs nothing (C11.1).
DEMO_TENANT_ID = "d0000000-0000-0000-0000-000000000001"


@dataclass(frozen=True)
class Branch:
    branch_id: str
    name: str
    till_label: str
    #: Relative volume: Al Qusais is the largest (P3).
    weight: Decimal


BRANCHES = (
    Branch(
        "d0000000-0000-0000-0000-000000000011", "Al Qusais Branch", "AL QUSAIS", Decimal("1.00")
    ),
    Branch("d0000000-0000-0000-0000-000000000012", "Al Nahda Branch", "AL NAHDA", Decimal("0.78")),
    Branch("d0000000-0000-0000-0000-000000000013", "Rolla Branch", "ROLLA", Decimal("0.62")),
)
FLAGSHIP = BRANCHES[0]

#: The papers, by role. Every KAS paper was forwarded from the demo phone, which resolves
#: to Al Qusais, so they are all that branch's purchases.
ON_STAGE_PAPER = "KAS-5"
PREPARATION_PAPERS = ("KAS-1", "KAS-2", "KAS-3", "KAS-4")

#: A fixed seed: the committed file is reproducible, and a test pins that it is.
SEED = 20260831

#: The one knob. Scales every quantity; chosen so the flagship's ratio sits at about 30%
#: before the on-stage paper and about 40% after it (see the module docstring).
VOLUME = Decimal("0.49")

#: The practice stage sells five items against two small staged papers (AED 840 net in
#: the week), so its week is scaled down to land in the same band: about 31%.
PRACTICE_VOLUME = Decimal("0.31")

#: Friday and Saturday sell more (weekday() 4 and 5).
WEEKEND_UPLIFT = {4: Decimal("1.20"), 5: Decimal("1.30")}

#: The "not a menu item" line: takings, not menu sales. One a day per outlet.
DELIVERY_CODE = "DLV"
DELIVERY_NAME = "DELIVERY CHARGE"
DELIVERY_CHARGE = Decimal("5.00")

FILS = Decimal("0.01")


@dataclass(frozen=True)
class MenuItem:
    code: str
    name: str
    price: Decimal  # VAT inside it, as the owner says it out loud
    till_name: str


#: How a till prints the real menu: upper case, the shorthand a cashier keys in. Most of
#: these clear the proposer's bar; a few are abbreviated enough to need the pick-from-menu
#: path on purpose (marked), because a queue where everything is proposed shows none of
#: the discipline that makes the mapping trustworthy. Keyed by item code.
TILL_NAMES: dict[str, str] = {
    "52a": "KARAK FLASK 1L",
    "52b": "KARAK FLASK 2L",
    "53a": "COFFEE MILK FLASK 1L",
    "53b": "COFFEE MILK FLASK 2L",
    "54a": "HABBAT AL HAMRA 1L",
    "54b": "HABBAT AL HAMRA 2L",
    "55a": "CAPPUCCINO SML",
    "55b": "CAPPUCCINO LRG",
    "56a": "SAHALAB SML",
    "56b": "SAHALAB LRG",
    "57a": "KASHMIRI TEA SML",
    "57b": "KASHMIRI TEA LRG",
    "58a": "BOOST SML",
    "58b": "BOOST LRG",
    "59a": "HORLICKS SML",
    "59b": "HORLICKS LRG",
    "60a": "HOT CHOC SML",
    "60b": "HOT CHOC LRG",
    "61": "HONEY CAKE",
    "62": "ZAFRAN CAKE",
    "63": "LOTUS CAKE",
    "64a": "KARAK DELIVERY S",
    "64b": "KARAK DELIVERY M",
    "64c": "KARAK DELIVERY L",
    "126": "B/CHKN",  # needs the pick-from-menu path
    "127": "CHKN WINGS",
    "128": "CHKN 65 DRY",
    "129": "DAL FRY",
    "130": "GREEN PEAS MSL",
    "131": "CHKN CHILLI",
    "132": "BEEF MSL",
    "133": "PRAWNS MSL",
    "134": "GARLIC CHKN",
    "135": "MTR MSHRM",  # needs the pick-from-menu path
    "136": "PNR KADAI",
    "137": "PALAK PNR",
    "138": "MSHRM MSL",
    "139": "CHKN KADAI",
    "140": "PNR BTR MSL",  # needs the pick-from-menu path
    "141": "PRAWNS CHILLI",
    "142": "CHILLI PNR",
    "143": "MTR PNR",
    "144": "CHKN MANCHURIAN",
    "145": "GOBI MSL",
    "146": "PEPPER CHKN",
}

#: The practice stage's five items (demo_seed.sql), with till codes the seed never had.
PRACTICE_ITEMS = (
    MenuItem("1", "Karak Tea (Cup)", Decimal("5.00"), "KARAK TEA CUP"),
    MenuItem("2", "Karak Tea (Flask 1 L)", Decimal("35.00"), "KARAK FLASK 1L"),
    MenuItem("3", "Cardamom Chai (Flask 2 L)", Decimal("55.00"), "CARDAMOM CHAI 2L"),
    MenuItem("4", "Nido Milk Tea", Decimal("8.00"), "NIDO TEA"),
    MenuItem("5", "Paratha", Decimal("3.00"), "PARATHA"),
)


def _till_name(code: str, name: str) -> str:
    """The till's shorthand for a menu item: the table above, or the name shouted."""
    return TILL_NAMES.get(code, name.upper().replace(" - ", " ").replace("(", "").replace(")", ""))


def menu_items(csv_path: pathlib.Path) -> tuple[MenuItem, ...]:
    """The real menu, one item per code in file order, through `plate_costs.load_recipes`."""
    return tuple(
        MenuItem(item["code"], item["name"], item["price"], _till_name(item["code"], item["name"]))
        for item in load_recipes(csv_path).values()
    )


def _base_rate(price: Decimal) -> int:
    """Units a weekday sells at the flagship before `VOLUME`: cheap things sell by the
    dozen, a two-litre flask a few times a day."""
    if price <= Decimal("3"):
        return 60
    if price <= Decimal("8"):
        return 45
    if price <= Decimal("14"):
        return 12
    if price <= Decimal("18"):
        return 9
    if price <= Decimal("40"):
        return 5
    return 3


# --- the week ---------------------------------------------------------------


@dataclass(frozen=True)
class Row:
    outlet: str
    date: datetime.date
    code: str
    item: str
    qty: int
    amount: Decimal  # VAT-inclusive, as the till prints it

    def csv(self) -> list[str]:
        return [
            self.outlet,
            self.date.strftime("%d/%m/%Y"),
            self.code,
            self.item,
            str(self.qty),
            f"{self.amount:.2f}",
        ]


@dataclass(frozen=True)
class Week:
    start: datetime.date
    end: datetime.date
    rows: tuple[Row, ...]

    @property
    def dates(self) -> list[datetime.date]:
        return [
            self.start + datetime.timedelta(days=i) for i in range((self.end - self.start).days + 1)
        ]

    @property
    def total(self) -> Decimal:
        """What the till's footer prints: every amount added up, VAT inside."""
        return sum((row.amount for row in self.rows), Decimal(0)).quantize(FILS)

    def sales_days(self) -> list[ratio.SalesDay]:
        """The week as the door stores it: per branch-day, takings as printed and the net
        derived per line through `takings.net_amount`, summed exactly (Codex 10)."""
        by_day: dict[tuple[str, datetime.date], list[Row]] = {}
        for row in self.rows:
            by_day.setdefault((row.outlet, row.date), []).append(row)
        label_to_id = {branch.till_label: branch.branch_id for branch in BRANCHES}
        days = []
        for (label, date), rows in sorted(by_day.items()):
            gross = sum((row.amount for row in rows), Decimal(0)).quantize(FILS)
            net = sum(
                (
                    takings.net_amount(row.amount, amount_basis="inclusive", vat_rate=VAT_RATE)
                    for row in rows
                ),
                Decimal(0),
            ).quantize(FILS)
            days.append(
                ratio.SalesDay(
                    branch_id=label_to_id[label], business_date=date, net_sales=net, takings=gross
                )
            )
        return days


def week_ending(end: datetime.date) -> tuple[datetime.date, datetime.date]:
    return end - datetime.timedelta(days=6), end


def build_week(
    items: tuple[MenuItem, ...], end: datetime.date, *, volume: Decimal = VOLUME
) -> Week:
    """Seven days ending on `end`, every branch open every day, one delivery-charge line a
    day, a fixed seed. Quantities are the base rate scaled by `volume`, the branch's
    weight, the weekend uplift and a little noise, rounded to whole units."""
    rng = random.Random(SEED)
    start, end = week_ending(end)
    rows: list[Row] = []
    for branch in BRANCHES:
        for offset in range(7):
            date = start + datetime.timedelta(days=offset)
            uplift = WEEKEND_UPLIFT.get(date.weekday(), Decimal(1))
            for item in items:
                expected = (
                    Decimal(_base_rate(item.price))
                    * volume
                    * branch.weight
                    * uplift
                    * Decimal(str(rng.uniform(0.7, 1.3)))
                )
                qty = int(expected.quantize(Decimal(1), rounding=ROUND_HALF_UP))
                if qty <= 0:
                    continue
                rows.append(
                    Row(
                        branch.till_label,
                        date,
                        item.code,
                        item.till_name,
                        qty,
                        (item.price * qty).quantize(FILS),
                    )
                )
            deliveries = int(
                (
                    Decimal(6) * branch.weight * uplift * Decimal(str(rng.uniform(0.7, 1.3)))
                ).quantize(Decimal(1), rounding=ROUND_HALF_UP)
            )
            if deliveries > 0:
                rows.append(
                    Row(
                        branch.till_label,
                        date,
                        DELIVERY_CODE,
                        DELIVERY_NAME,
                        deliveries,
                        (DELIVERY_CHARGE * deliveries).quantize(FILS),
                    )
                )
    return Week(start, end, tuple(rows))


def write_csv(week: Week, path: pathlib.Path) -> None:
    """The till's export: the pinned header, the rows, and a totals footer with no date
    (the loader skips it and says "1 row with no date ignored")."""
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(HEADER)
        for row in week.rows:
            writer.writerow(row.csv())
        writer.writerow(["TOTAL", "", "", "", "", f"{week.total:.2f}"])


# --- the purchases, and the row the screen will show ------------------------


def _printed_date(key: str) -> datetime.date:
    """A paper's own printed date, day-first, from the table the papers are rendered from."""
    day, month, year = SUPPLIERS[key][5].split("/")
    return datetime.date(int(year), int(month), int(day))


def paper(key: str) -> ratio.Invoice:
    """One KAS paper as the ratio reads a confirmed invoice: the printed total and VAT
    from `build_prompts.totals`, the printed date as `purchased_on`, on the flagship."""
    _subtotal, vat, total = totals(key)
    date = _printed_date(key)
    return ratio.Invoice(
        invoice_id=key,
        branch_id=FLAGSHIP.branch_id,
        status="confirmed",
        currency=CURRENCY,
        total=total,
        tax=vat,
        invoice_date=date,
        purchased_on=date,
        placed_on=date,
        supplier_name=SUPPLIERS[key][0],
        invoice_no=SUPPLIERS[key][4],
    )


def real_week_end() -> datetime.date:
    """KAS-5's printed date - never typed; a reprinted prop moves the week with it."""
    return _printed_date(ON_STAGE_PAPER)


def real_week(csv_path: pathlib.Path = DEFAULT_CSV) -> Week:
    """The committed week: the real menu, ending on the on-stage paper's printed date."""
    return build_week(menu_items(csv_path), real_week_end())


def practice_week(end: datetime.date) -> Week:
    """The rehearsal week: the five staged items, ending on the newest staged purchase."""
    return build_week(PRACTICE_ITEMS, end, volume=PRACTICE_VOLUME)


def figures(week: Week, invoices: list[ratio.Invoice]) -> list[ratio.BranchRow]:
    """The branch rows the screen will show for this week against these papers, ranked
    the way the screen ranks them - through `ratio.period_row`, never a copy of it."""
    period = ratio.Period(week.start, week.end)
    days = week.sales_days()
    rows = [
        ratio.period_row(
            branch_id=branch.branch_id,
            branch_name=branch.name,
            days=days,
            invoices=invoices,
            period=period,
            tenant_currency=CURRENCY,
        )
        for branch in BRANCHES
    ]
    return ratio.rank(rows)


def print_figures(title: str, rows: list[ratio.BranchRow]) -> None:
    print(title)
    print(
        f"  {'branch':18} {'net sales':>11} {'takings':>11} {'purchases':>11} {'ratio':>7}  quality"
    )
    for row in rows:
        pct = "-" if row.ratio_pct is None else f"{row.ratio_pct}%"
        print(
            f"  {row.branch_name:18} {row.net_sales or 0:>11.2f} {row.takings or 0:>11.2f} "
            f"{row.purchases:>11.2f} {pct:>7}  {row.quality.value}: {'; '.join(row.notes)}"
        )


# --- the practice stage, read from the database ----------------------------------


@dataclass(frozen=True)
class PracticeStage:
    end: datetime.date
    invoices: list[ratio.Invoice]


async def read_practice_stage(database_url: str) -> PracticeStage:
    """The demo tenant's confirmed papers as the ratio reads them, and the newest purchase
    day among them - the day the practice week ends on. Read, never computed from today:
    the seed stages its purchases relative to the moment it runs."""
    import asyncpg

    conn = await asyncpg.connect(database_url)
    try:
        rows = await conn.fetch(
            """
            select id::text as id, branch_id::text as branch_id, status, currency, total, tax,
                   invoice_date, supplier_name, invoice_no,
                   coalesce(invoice_date, (confirmed_at at time zone 'UTC')::date) as purchased_on
              from invoices
             where tenant_id = $1 and status = 'confirmed'
             order by purchased_on, id
            """,
            DEMO_TENANT_ID,
        )
    finally:
        await conn.close()
    if not rows:
        raise SystemExit("the demo tenant has no confirmed purchases: apply demo_seed.sql first")
    invoices = [
        ratio.Invoice(
            invoice_id=row["id"],
            branch_id=row["branch_id"],
            status=row["status"],
            currency=row["currency"],
            total=row["total"],
            tax=row["tax"],
            invoice_date=row["invoice_date"],
            purchased_on=row["purchased_on"],
            placed_on=row["purchased_on"],
            supplier_name=row["supplier_name"],
            invoice_no=row["invoice_no"],
        )
        for row in rows
    ]
    return PracticeStage(end=max(i.purchased_on for i in invoices), invoices=invoices)


# --- main ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=pathlib.Path, default=DEFAULT_CSV, help="the menu loader CSV")
    parser.add_argument(
        "--practice",
        action="store_true",
        help="the five staged items, for the week ending on the demo tenant's newest purchase",
    )
    parser.add_argument("--out", type=pathlib.Path, help="where to write the till export")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL"),
        help="where --practice reads the demo tenant's purchases "
        "(TEST_DATABASE_URL or DATABASE_URL)",
    )
    args = parser.parse_args()

    if args.practice:
        if not args.database_url:
            raise SystemExit(
                "--practice needs TEST_DATABASE_URL or DATABASE_URL (or --database-url)"
            )
        stage = asyncio.run(read_practice_stage(args.database_url))
        week = practice_week(stage.end)
        out = args.out or HERE / "sales-week-practice.csv"
        write_csv(week, out)
        print(
            f"wrote {out}: {len(week.rows)} rows, {week.start:%d/%m/%Y} to {week.end:%d/%m/%Y}, "
            f"footer {week.total:.2f}"
        )
        print_figures("the practice stage, as /sales will show it:", figures(week, stage.invoices))
        return

    week = real_week(args.csv)
    out = args.out or HERE / "sales-week.csv"
    write_csv(week, out)
    print(
        f"wrote {out}: {len(week.rows)} rows, {week.start:%d/%m/%Y} to {week.end:%d/%m/%Y}, "
        f"footer {week.total:.2f}"
    )
    before = [paper(key) for key in PREPARATION_PAPERS]
    print_figures(
        "before the stage (KAS-1..4 confirmed; KAS-1 and KAS-2 print before the week):",
        figures(week, before),
    )
    print_figures(
        f"after the on-stage forward ({ON_STAGE_PAPER} confirmed, "
        f"printed {real_week_end():%d/%m/%Y}):",
        figures(week, before + [paper(ON_STAGE_PAPER)]),
    )


if __name__ == "__main__":
    main()
