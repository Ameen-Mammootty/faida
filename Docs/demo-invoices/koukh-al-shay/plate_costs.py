"""What every plate on the real menu costs, and earns, off these five papers.

The demo's closing image is a ranked margin table, and every figure in it is
four sums away from the paper: invoice line -> cost per base unit (WP-53) ->
material price (WP-54, newest printed date wins) -> plate cost (WP-61) ->
margin at the menu price, net of VAT. This script runs that whole chain
locally, off `build_prompts.py` and the recipe CSV, so a price change on the
papers can be judged by what it does to the menu **before** anything is
forwarded, confirmed or deployed.

It is not a second implementation. `costing.cost_line` and `plates.plate` are
imported from the shipped package and given the same inputs `db.py` gives
them, so a number here is the number the screen will show. What is simulated
is only the database: which invoice line is newest for a material, and which
material a supplier product is mapped to.

    apps/api/.venv/bin/python Docs/demo-invoices/koukh-al-shay/plate_costs.py
    ... --csv <path to faida-loader-preview.csv>     # default: ~/Downloads/...
    ... --materials                                  # per-kilo price table
    ... --json <path>                                # machine-readable dump

Every paper prices exclusive of VAT (C4), so there is no net factor and no
discount factor to apply: the printed unit price *is* the net price.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys
from decimal import Decimal

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "apps/api/src"))
sys.path.insert(0, str(HERE))

from build_prompts import SUPPLIERS  # noqa: E402

from faida_api import costing, plates  # noqa: E402
from faida_api.extraction.constants import (  # noqa: E402
    PRICE_ALERT_MIN_ABS,
    PRICE_ALERT_MIN_PCT,
    VAT_RATE_BY_CURRENCY,
)

DEFAULT_CSV = pathlib.Path.home() / "Downloads/Menu engineer/koukh-al-shay/faida-loader-preview.csv"

CURRENCY = "AED"

#: The mapping a human approves on `/materials`, one keystroke per row: this
#: supplier product is that raw material. Written out rather than matched,
#: because the matcher's job is to *propose* and this script is not the
#: matcher - it is the state of the world after every proposal was approved.
#: Keyed by item code, so a description reword cannot silently break it.
MATERIAL_BY_CODE: dict[str, str] = {
    "VEG-ONI-10": "Onion",
    "VEG-TOM-06": "Tomato",
    "VEG-CAP-05": "Capsicum",
    "VEG-GNG-05": "Ginger",
    "VEG-GAR-01": "Garlic",
    "VEG-CHI-01": "Green chilli",
    "VEG-COR-01": "Coriander, fresh",
    "VEG-CUR-100": "Curry leaves",
    "VEG-SPO-02": "Spring onion",
    "VEG-LEM-05": "Lemon",
    "VEG-MUS-02": "Mushroom",
    "VEG-SPI-02": "Spinach",
    "VEG-CAU-06": "Cauliflower",
    "VEG-PEA-01": "Green peas",
    "VEG-COC-01": "Coconut, grated",
    "VEG-GGP-01": "Ginger-garlic paste",
    "DRY-SUG-50": "White sugar",
    "DRY-SAL-25": "Salt",
    "SPC-RCP-01": "Red chilli powder",
    "SPC-TUR-01": "Turmeric",
    "SPC-CDP-01": "Coriander powder",
    "SPC-CDS-500": "Coriander seed, crushed",
    "SPC-GAR-500": "Garam masala",
    "SPC-CUM-500": "Cumin seed",
    "SPC-KCP-500": "Kashmiri chilli powder",
    "SPC-KAS-250": "Kasuri methi",
    "SPC-BLP-500": "Black pepper, crushed",
    "SPC-WHP-500": "White pepper",
    "SPC-DRC-01": "Dried red chilli",
    "SPC-CIN-500": "Cinnamon stick",
    "SPC-CAR-500": "Green cardamom",
    "SPC-DGP-250": "Dry ginger",
    "DRY-BSD-01": "Baking soda",
    "DRY-CNF-01": "Corn flour",
    "DRY-CNS-01": "Corn starch",
    "DRY-TOR-15": "Toor dal",
    "DRY-CSH-01": "Cashew nuts",
    "DRY-PIS-500": "Pistachio, slivered",
    "DRY-DSC-01": "Desiccated coconut",
    "SPC-SAF-50": "Saffron",
    "DRY-EVP-48": "Evaporated milk",
    "DRY-CDM-48": "Condensed milk",
    "CHL-FRM-12": "Fresh milk",
    "DRY-MPW-25": "Milk powder",
    "CHL-BUT-10": "Butter",
    "CHL-GHE-05": "Ghee",
    "CHL-CRM-12": "Cream, cooking",
    "CHL-YOG-05": "Yoghurt",
    "CHL-EGG-18": "Egg",
    "CHL-PAN-01": "Paneer",
    "FRZ-CHB-10": "Chicken, boneless",
    "FRZ-CHW-10": "Chicken wings",
    "FRZ-BEF-05": "Beef, boneless",
    "FRZ-PRW-01": "Prawns, peeled",
    "BEV-CTC-05": "CTC black tea",
    "BEV-INC-200": "Instant coffee",
    "BEV-KGT-01": "Kashmiri green tea leaves",
    "BEV-HAH-01": "Habbat Al Hamra blend",
    "BEV-BST-450": "Boost powder",
    "BEV-HRL-500": "Horlicks powder",
    "BEV-DCH-01": "Drinking chocolate powder",
    "BEV-COC-01": "Cocoa powder",
    "BEV-SAH-500": "Sahlab powder",
    "BEV-ROS-500": "Rose water",
    "AMB-OIL-05": "Oil",
    "AMB-VIN-05": "Vinegar",
    "AMB-SOY-04": "Light soy sauce",
    "AMB-RCS-05": "Red chilli sauce",
    "AMB-KTC-05": "Tomato ketchup",
    "BKY-HON-01": "Honey cake, whole (10 slices)",
    "BKY-ZAF-01": "Zafran cake, whole (10 slices)",
    "BKY-LOT-01": "Lotus cake, whole (10 slices)",
    "PKG-CKB-100": "Cake box + fork",
    "PKG-DCS-100": "Delivery cup S + lid",
    "PKG-DCM-100": "Delivery cup M + lid",
    "PKG-DCL-100": "Delivery cup L + lid",
    "PKG-FL1-50": "Disposable flask 1 L",
    "PKG-FL2-50": "Disposable flask 2 L",
    "PKG-PCS-100": "Paper cup small + lid",
    "PKG-PCL-100": "Paper cup large + lid",
    "PKG-TWC-100": "Takeaway container + lid",
}


def _printed_date(key: str) -> tuple[int, int, int]:
    """The paper's own printed date, day-first, as a sort key. Costing ranks
    purchases by this and not by confirm time (WP-54), which is the whole
    reason KAS-5's repeat packs beat KAS-3's."""
    day, month, year = SUPPLIERS[key][5].split("/")
    return int(year), int(month), int(day)


def material_prices() -> dict[str, tuple[plates.Priced, str, str]]:
    """Each material's current price per base unit, as WP-54 derives it.

    The newest costed line among the packs mapped to the material wins, by
    printed invoice date. Returns the price beside the paper and pack behind
    it, so a surprising plate can be traced back to one line on one document.
    """
    winners: dict[str, tuple[tuple[int, int, int], plates.Priced, str, str]] = {}
    for key in SUPPLIERS:
        rows = SUPPLIERS[key][6]
        when = _printed_date(key)
        for position, (code, desc, qty, unit, pack, price) in enumerate(rows):
            material = MATERIAL_BY_CODE.get(code)
            if material is None:
                raise SystemExit(f"{key} line {position + 1}: {code} is mapped to no material")
            line = costing.cost_line(
                position=position,
                qty=Decimal(str(qty)),
                unit_price=Decimal(str(price)),
                pack_size=pack,
                raw_name=desc,
                unit=unit,
            )
            if line.cost is None:
                raise SystemExit(f"{key} line {position + 1}: {desc} is blocked ({line.blocked})")
            previous = winners.get(material)
            if previous is not None and previous[0] >= when:
                continue
            priced = plates.Priced(
                cost_per_base_unit=line.cost,
                base_unit=line.base_unit,
                quality=line.quality.value,
            )
            winners[material] = (when, priced, key, f"{desc} {pack} @ {price:.2f}")
    return {name: (priced, key, pack) for name, (_, priced, key, pack) in winners.items()}


def load_recipes(path: pathlib.Path) -> dict[str, dict]:
    """The recipe CSV, grouped into one menu item per code, in file order."""
    items: dict[str, dict] = {}
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            item = items.setdefault(
                row["item_code"],
                {
                    "code": row["item_code"],
                    "name": row["item_name"],
                    "category": row["category"],
                    "price": Decimal(row["selling_price_aed"]),
                    "yield_portions": Decimal(row["yield_portions"]),
                    "components": [],
                },
            )
            item["components"].append(
                (row["ingredient"], Decimal(row["qty_as_purchased"]), row["unit"])
            )
    return items


def cost_menu(csv_path: pathlib.Path) -> tuple[list[dict], dict]:
    prices = material_prices()
    vat_rate = VAT_RATE_BY_CURRENCY.get(CURRENCY)
    results = []
    for item in load_recipes(csv_path).values():
        components = [
            plates.cost_component(
                position=position,
                qty=qty,
                unit=unit,
                ingredient_name=name,
                has_packs=name in prices,
                price=prices[name][0] if name in prices else None,
            )
            for position, (name, qty, unit) in enumerate(item["components"])
        ]
        result = plates.plate(
            components,
            yield_portions=item["yield_portions"],
            selling_price=item["price"],
            vat_rate=vat_rate,
        )
        results.append({**item, "plate": result})
    return results, prices


def _per_display_unit(priced: plates.Priced) -> tuple[Decimal, str]:
    label, factor = costing.DISPLAY_UNITS[priced.base_unit]
    return (priced.cost_per_base_unit * factor).quantize(costing.DISPLAY_QUANTUM), label


def _line_cost(row: tuple) -> costing.LineCost:
    code, desc, qty, unit, pack, price = row
    return costing.cost_line(
        position=0,
        qty=Decimal(str(qty)),
        unit_price=Decimal(str(price)),
        pack_size=pack,
        raw_name=desc,
        unit=unit,
    )


def print_moves(csv_path: pathlib.Path) -> None:
    """The money moment, line by line: the WhatsApp alert and what the move
    costs each plate that draws the material (WP-63).

    The alert fires on the printed **pack** price against the same pack's last
    price - both thresholds, either direction - while the plate figure is the
    per-base-unit delta times the recipe quantity over the batch yield. The two
    are different numbers on purpose: one is what the supplier changed, the
    other is what it costs you, and the second is what the menu screen ranks by.
    """
    previous = {row[0]: row for row in SUPPLIERS["KAS-3"][6]}
    recipes = load_recipes(csv_path)

    print(f"{'line':28} {'was':>8} {'now':>8} {'alert':>22}  {'per base unit':>26}  worst plate")
    for row in SUPPLIERS["KAS-5"][6]:
        code, desc, _qty, _unit, pack, price = row
        was = previous.get(code)
        if was is None:
            print(f"{desc:28} {'-':>8} {price:>8.2f}  no same-pack previous line")
            continue
        if was[4] != pack:
            print(f"{desc:28}  PACK CHANGED {was[4]!r} -> {pack!r} - no honest delta (D3)")
            continue

        last, now = Decimal(str(was[5])), Decimal(str(price))
        delta = now - last
        fires = abs(delta) >= PRICE_ALERT_MIN_ABS and abs(delta) >= PRICE_ALERT_MIN_PCT * last
        pct = (delta / last * 100).quantize(Decimal("0.1"))
        alert = (
            f"{'up' if delta > 0 else 'down'} {abs(delta):.2f} ({pct:+.1f}%)" if fires else "SILENT"
        )

        before, after = _line_cost(was), _line_cost(row)
        label, factor = costing.DISPLAY_UNITS[after.base_unit]
        per_unit = f"{before.cost * factor:.4f} -> {after.cost * factor:.4f} /{label}"
        unit_delta = after.cost - before.cost

        material = MATERIAL_BY_CODE[code]
        impacts = []
        for item in recipes.values():
            for name, qty, unit in item["components"]:
                if name != material:
                    continue
                converted = plates.to_base_qty(qty, unit)
                if converted is None:
                    continue
                impacts.append(
                    (
                        plates.margin_impact(unit_delta, converted[0], item["yield_portions"]),
                        f"{item['code']} {item['name']}",
                    )
                )
        impacts.sort(key=lambda pair: abs(pair[0]), reverse=True)
        worst = f"{impacts[0][1]}: {impacts[0][0]:+.3f}" if impacts else "-"
        print(f"{desc:28} {last:>8.2f} {now:>8.2f} {alert:>22}  {per_unit:>26}  {worst}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=pathlib.Path, default=DEFAULT_CSV)
    parser.add_argument("--materials", action="store_true", help="print the per-kilo price table")
    parser.add_argument("--moves", action="store_true", help="the KAS-5 money moment, per plate")
    parser.add_argument("--json", type=pathlib.Path, help="dump the ranked table as JSON")
    args = parser.parse_args()

    results, prices = cost_menu(args.csv)

    if args.moves:
        print_moves(args.csv)
        print()

    if args.materials:
        print(f"{'material':32} {'price':>12}  {'paper':6} pack")
        for name in sorted(prices):
            priced, paper, pack = prices[name]
            amount, label = _per_display_unit(priced)
            print(f"{name:32} {amount:>8} /{label:<4} {paper:6} {pack}")
        print()

    costed = [r for r in results if r["plate"].cost_per_portion is not None]
    incomplete = [r for r in results if r["plate"].cost_per_portion is None]
    costed.sort(key=lambda r: r["plate"].margin, reverse=True)

    print(f"{'item':38} {'price':>7} {'cost':>8} {'margin':>8} {'%':>7}  quality")
    for row in costed:
        p = row["plate"]
        print(
            f"{row['code'] + ' ' + row['name']:38.38} {row['price']:>7.2f} "
            f"{p.cost_per_portion:>8.3f} {p.margin:>8.3f} {p.margin_pct:>6.1f}%  {p.quality.value}"
        )
    for row in incomplete:
        print(
            f"{row['code'] + ' ' + row['name']:38.38} {'INCOMPLETE':>32}  "
            f"{'; '.join(row['plate'].missing)}"
        )

    negative = [r for r in costed if r["plate"].margin < 0]
    thin = [r for r in costed if 0 <= r["plate"].margin_pct < 30]
    print()
    print(f"{len(costed)} of {len(results)} items costed, {len(incomplete)} incomplete")
    if negative:
        print(f"LOSS-MAKING: {', '.join(r['code'] + ' ' + r['name'] for r in negative)}")
    if thin:
        print(f"UNDER 30% MARGIN: {', '.join(r['code'] + ' ' + r['name'] for r in thin)}")

    if args.json:
        args.json.write_text(
            json.dumps(
                [
                    {
                        "code": r["code"],
                        "name": r["name"],
                        "category": r["category"],
                        "price": str(r["price"]),
                        "cost": str(r["plate"].cost_per_portion)
                        if r["plate"].cost_per_portion is not None
                        else None,
                        "margin": str(r["plate"].margin) if r["plate"].margin is not None else None,
                        "margin_pct": str(r["plate"].margin_pct)
                        if r["plate"].margin_pct is not None
                        else None,
                        "quality": r["plate"].quality.value,
                        "missing": list(r["plate"].missing),
                    }
                    for r in costed + incomplete
                ],
                indent=2,
            )
        )
        print(f"wrote {args.json}")


if __name__ == "__main__":
    main()
