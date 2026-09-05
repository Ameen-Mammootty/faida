"""Regenerate the dashboard mock's fixtures (M9 WP-93): the JSON files beside
this script, one per scenario, one payload per scope (the chain and each
sample branch).

Every figure the mock serves is produced here by the *shipped* Python modules
(contribution.py, signals.py, ratio.py, plates.py, menu.price_moves) over a
hand-built week of the three sample branches and the sample menu, then
written out as JSON literals. The TypeScript mock computes nothing: it picks a
scenario and a scope and returns the literal. That is the mock/menu.ts rule
("every figure written out and hand-checked") in its strongest form - the
checker is the real arithmetic - and it is why the fixtures must be
regenerated whenever the wording or the arithmetic in those modules moves.

Run from apps/api with its venv (the modules are imported from src):

    .venv/bin/python ../web/src/lib/mock/dashboard/generate.py \
        ../web/src/lib/mock/dashboard src

The answer and freshness sentences here are copies of dashboard.py's; a
change there is a change here.
"""

import datetime
import json
import sys
from decimal import ROUND_HALF_UP, Decimal as D

sys.path.insert(0, sys.argv[2] if len(sys.argv) > 2 else "src")
from faida_api import contribution as C  # noqa: E402
from faida_api import menu as M  # noqa: E402
from faida_api import plates as P  # noqa: E402
from faida_api import ratio as R  # noqa: E402
from faida_api import signals as S  # noqa: E402
from faida_api.ratio import Quality  # noqa: E402

OUT = sys.argv[1]
CURRENCY = "AED"
VAT = D("0.05")
PERIOD = R.Period(datetime.date(2026, 8, 4), datetime.date(2026, 8, 31))
WEEK = [datetime.date(2026, 8, 25) + datetime.timedelta(days=i) for i in range(7)]
BRANCHES = [("br-01", "Al Quoz"), ("br-02", "Karama"), ("br-03", "Deira")]
NAMES = dict(BRANCHES)
MARCH = datetime.date(2026, 3, 12)


def fils(x: D) -> D:
    return x.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def net_price(price: str) -> D:
    return P.net_of_vat(D(price), VAT)


# --- the menu ---------------------------------------------------------------
# (id, name, category, price, recipe_version, quality, missing, components)
# component: (ingredient_id, ingredient_name, qty, unit, batch_cost | None, invoice_id, line_position, purchased_on)
A21 = datetime.date(2026, 8, 21)
A22 = datetime.date(2026, 8, 22)
A25 = datetime.date(2026, 8, 25)
A28 = datetime.date(2026, 8, 28)

REL = P.PlateQuality.RELIABLE
EST = P.PlateQuality.ESTIMATED
INC = P.PlateQuality.INCOMPLETE

MENU_SPEC = [
    ("menu-1", "Karak Tea (Cup)", "Tea Corner", "5.00", 2, REL, (), [
        ("ing-dust", "Karak Tea Dust", "4", "g", "0.048", "inv-1001", 2, A21),
        ("ing-evap", "Evaporated Milk", "60", "ml", "0.288", "inv-1002", 2, A22),
        ("ing-nido", "Milk Powder", "5", "g", "0.307", "inv-1001", 1, A21),
        ("ing-sugar", "White Sugar", "8", "g", "0.032", "inv-1003", 1, A22),
        ("ing-cup", "Paper cup small + lid", "1", "pc", "0.137", "inv-1005", 1, A22),
    ]),
    ("menu-2", "Karak Tea (Flask 1 L)", "Tea Corner", "35.00", 1, REL, (), [
        ("ing-nido", "Milk Powder", "30", "g", "1.842", "inv-1001", 1, A21),
        ("ing-evap", "Evaporated Milk", "500", "ml", "2.400", "inv-1002", 2, A22),
        ("ing-dust", "Karak Tea Dust", "30", "g", "0.360", "inv-1001", 2, A21),
        ("ing-sugar", "White Sugar", "80", "g", "0.320", "inv-1003", 1, A22),
        ("ing-flask", "Flask lid + seal", "1", "pc", "1.282", "inv-1005", 2, A22),
    ]),
    ("menu-3", "Nido Shake", "Shakes", "12.00", 1, REL, (), [
        ("ing-nido", "Milk Powder", "40", "g", "2.456", "inv-1001", 1, A21),
        ("ing-evap", "Evaporated Milk", "200", "ml", "0.960", "inv-1002", 2, A22),
        ("ing-sugar", "White Sugar", "20", "g", "0.080", "inv-1003", 1, A22),
        ("ing-ghee", "Ghee", "5", "g", "0.180", "inv-1001", 3, A21),
        ("ing-cup-l", "Paper cup large + lid", "1", "pc", "0.424", "inv-1005", 3, A22),
    ]),
    ("menu-4", "Chicken Mandi", "Rice", "28.00", 1, INC, ("no supplier product is mapped to Chicken yet",), [
        ("ing-chicken", "Chicken", "250", "g", None, None, None, None),
        ("ing-rice", "Basmati Rice", "200", "g", "1.600", "inv-1002", 1, A22),
        ("ing-ghee", "Ghee", "15", "g", "0.540", "inv-1001", 3, A21),
    ]),
    ("menu-5", "Honey Cake", "Bakery", "9.00", None, INC, ("no recipe yet",), []),
    ("menu-6", "Sulaimani", "Tea Corner", "3.00", 1, REL, (), [
        ("ing-blacktea", "Black Tea", "3", "g", "0.036", "inv-1001", 4, A21),
        ("ing-sugar", "White Sugar", "10", "g", "0.040", "inv-1003", 1, A22),
        ("ing-lemon", "Lemon", "10", "g", "0.060", "inv-1003", 2, A22),
        ("ing-cup", "Paper cup small + lid", "1", "pc", "0.084", "inv-1005", 1, A22),
    ]),
    ("menu-7", "Butter Chicken", "Special Gravy", "25.00", 1, REL, (), [
        ("ing-boneless", "Boneless Chicken", "150", "g", "4.500", "inv-1005", 4, A22),
        ("ing-butter", "Butter", "20", "g", "0.680", "inv-1002", 3, A22),
        ("ing-cream", "Cream", "50", "ml", "0.750", "inv-1002", 4, A22),
        ("ing-tomato", "Tomato", "100", "g", "0.450", "inv-1003", 3, A22),
        ("ing-spices", "Spice mix", "10", "g", "0.400", "inv-1001", 5, A21),
        ("ing-box", "Paper container + lid", "1", "pc", "1.740", "inv-1005", 5, A22),
    ]),
    ("menu-8", "Paneer Butter Masala", "Special Gravy", "22.50", 1, REL, (), [
        ("ing-paneer", "Paneer", "120", "g", "3.600", "inv-1002", 5, A22),
        ("ing-butter", "Butter", "20", "g", "0.680", "inv-1002", 3, A22),
        ("ing-cream", "Cream", "50", "ml", "0.750", "inv-1002", 4, A22),
        ("ing-tomato", "Tomato", "100", "g", "0.450", "inv-1003", 3, A22),
        ("ing-spices", "Spice mix", "10", "g", "0.400", "inv-1001", 5, A21),
        ("ing-box", "Paper container + lid", "1", "pc", "1.410", "inv-1005", 5, A22),
    ]),
    ("menu-9", "Chicken 65 Dry", "Starters", "45.00", 2, EST, (), [
        ("ing-boneless", "Boneless Chicken", "510", "g", "15.300", "inv-1005", 4, A22),
        ("ing-ghee", "Ghee", "45", "g", "4.120", "inv-1001", 3, A21),
        ("ing-cornflour", "Corn Flour", "60", "g", "0.900", "inv-1003", 4, A22),
        ("ing-spices", "Spice mix", "25", "g", "1.250", "inv-1001", 5, A21),
        ("ing-curry", "Curry Leaves", "10", "g", "0.500", "inv-1003", 5, A22),
        ("ing-box", "Paper container + lid", "1", "pc", "1.100", "inv-1005", 5, A22),
        ("ing-oil", "Sunflower Oil", "60", "ml", "0.600", "inv-1002", 6, A22),
        ("ing-lemon", "Lemon", "20", "g", "0.120", "inv-1003", 2, A22),
        ("ing-gg", "Ginger Garlic Paste", "30", "g", "0.480", "inv-1002", 7, A22),
        ("ing-yogurt", "Yogurt", "50", "ml", "0.500", "inv-1002", 8, A22),
    ]),
    ("menu-10", "Mutter Mushroom", "Special Gravy", "30.00", 1, REL, (), [
        ("ing-mushroom", "Mushroom", "150", "g", "7.500", "inv-1003", 6, A22),
        ("ing-peas", "Green Peas", "80", "g", "1.200", "inv-1003", 7, A22),
        ("ing-cream", "Cream", "50", "ml", "0.750", "inv-1002", 4, A22),
        ("ing-onion", "Onion", "80", "g", "0.240", "inv-1003", 8, A22),
        ("ing-tomato", "Tomato", "100", "g", "0.450", "inv-1003", 3, A22),
        ("ing-spices", "Spice mix", "10", "g", "0.400", "inv-1001", 5, A21),
        ("ing-box", "Paper container + lid", "1", "pc", "1.740", "inv-1005", 5, A22),
        ("ing-butter", "Butter", "20", "g", "0.680", "inv-1002", 3, A22),
        ("ing-cashew", "Cashew", "20", "g", "2.470", "inv-1001", 6, A21),
    ]),
    ("menu-11", "Egg Paratha", "Breads", "5.00", 1, REL, (), [
        ("ing-egg", "Egg", "1", "pc", "0.550", "inv-1003", 9, A22),
        ("ing-flour", "Wheat Flour", "80", "g", "0.240", "inv-1001", 7, A21),
        ("ing-oil", "Sunflower Oil", "15", "ml", "0.150", "inv-1002", 6, A22),
        ("ing-onion", "Onion", "30", "g", "0.090", "inv-1003", 8, A22),
        ("ing-ghee", "Ghee", "12", "g", "1.100", "inv-1001", 3, A21),
        ("ing-wrap", "Paper wrap", "1", "pc", "0.203", "inv-1005", 6, A22),
    ]),
    ("menu-12", "Veg Biryani", "Rice", "20.00", 1, REL, (), [
        ("ing-rice", "Basmati Rice", "200", "g", "1.600", "inv-1002", 1, A22),
        ("ing-veg", "Mixed Vegetables", "150", "g", "1.800", "inv-1003", 10, A22),
        ("ing-ghee", "Ghee", "25", "g", "2.290", "inv-1001", 3, A21),
        ("ing-spices", "Spice mix", "15", "g", "0.600", "inv-1001", 5, A21),
        ("ing-onion", "Onion", "100", "g", "0.300", "inv-1003", 8, A22),
        ("ing-yogurt", "Yogurt", "50", "ml", "0.500", "inv-1002", 8, A22),
        ("ing-box-l", "Paper container large + lid", "1", "pc", "1.860", "inv-1005", 7, A22),
    ]),
    ("menu-13", "Mint Lemonade", "Drinks", "8.00", 1, REL, (), [
        ("ing-lemon", "Lemon", "60", "g", "0.360", "inv-1003", 2, A22),
        ("ing-mint", "Mint", "20", "g", "1.200", "inv-1003", 11, A22),
        ("ing-syrup", "Sugar Syrup", "40", "ml", "0.560", "inv-1002", 9, A22),
        ("ing-soda", "Soda Water", "250", "ml", "1.750", "inv-1002", 10, A22),
        ("ing-ice", "Ice", "200", "g", "0.400", "inv-1005", 8, A22),
        ("ing-cup-s", "Cup + lid + straw", "1", "pc", "3.750", "inv-1005", 9, A22),
    ]),
    ("menu-14", "Masala Chai", "Tea Corner", "4.00", 1, REL, (), [
        ("ing-blacktea", "Black Tea", "4", "g", "0.048", "inv-1001", 4, A21),
        ("ing-nido", "Milk Powder", "6", "g", "0.368", "inv-1001", 1, A21),
        ("ing-sugar", "White Sugar", "10", "g", "0.040", "inv-1003", 1, A22),
        ("ing-spices", "Spice mix", "2", "g", "0.080", "inv-1001", 5, A21),
        ("ing-cup", "Paper cup small + lid", "1", "pc", "0.104", "inv-1005", 1, A22),
    ]),
]

#: Today's plate where it differs from the period's (a paper dated after 31 Aug).
TODAY_COST = {"menu-9": D("25.400")}


def build_menu(ids=None) -> dict[str, C.MenuItem]:
    menu = {}
    for mid, name, cat, price, rv, quality, missing, comps in MENU_SPEC:
        if ids is not None and mid not in ids:
            continue
        components = tuple(
            C.RecipeComponent(
                ingredient_id=cid, ingredient_name=cname, qty=D(qty), unit=unit,
                batch_cost=None if cost is None else D(cost),
                invoice_id=inv, line_position=pos, purchased_on=on,
            )
            for cid, cname, qty, unit, cost, inv, pos, on in comps
        )
        if quality is INC:
            plate = P.Plate(quality=INC, missing=missing)
        else:
            cost = sum((c.batch_cost for c in components), D(0)).quantize(P.PLATE_QUANTUM)
            net = net_price(price)
            margin = net - cost
            plate = P.Plate(
                quality=quality, cost_per_portion=cost, net_price=net, vat_rate=VAT,
                margin=margin,
                margin_pct=(margin / net * 100).quantize(P.PCT_QUANTUM, rounding=ROUND_HALF_UP),
            )
        menu[mid] = C.MenuItem(
            menu_item_id=mid, name=name, plate=plate, selling_price=D(price),
            yield_portions=D(1), vat_rate=VAT, category=cat, recipe_version=rv,
            components=components,
        )
    return menu


def today_plates(menu):
    out = {}
    for mid, item in menu.items():
        if mid in TODAY_COST and item.plate.cost_per_portion is not None:
            out[mid] = P.Plate(quality=item.plate.quality, cost_per_portion=TODAY_COST[mid])
        else:
            out[mid] = item.plate
    return out


# --- the week ---------------------------------------------------------------
# weekly quantity per (item, branch); nets default to qty x net price.
WEEKLY = {
    "menu-1": (980, 700, 300),
    "menu-2": (240, 112, 60),
    "menu-3": (84, 56, 35),
    "menu-4": (35, 21, 14),
    "menu-5": (28, 14, 0),
    "menu-6": (420, 350, 250),
    "menu-7": (140, 105, 73),
    "menu-8": (105, 84, 52),
    "menu-9": (35, 21, 40),
    "menu-10": (42, 35, 45),
    "menu-11": (140, 105, 60),
    "menu-12": (56, 42, 60),
    "menu-13": (98, 70, 98),
    "menu-14": (210, 140, 105),
}
EXPLICIT_NET = {("menu-2", "br-01"): D("7999.92"), ("menu-2", "br-02"): D("3733.30"), ("menu-2", "br-03"): D("2000.11")}
DISCOUNT_NET_PER_PORTION = {"menu-9": D("40.152")}  # sold at an average under today's menu price
TILL_NAMES = {
    "menu-1": ("KARAK TEA", "12"), "menu-2": ("KARAK TEA FLASK 1L", "52a"), "menu-3": ("NIDO SHAKE", "31"),
    "menu-4": ("CHKN MANDI", "77"), "menu-5": ("HONEY CAKE", "90"), "menu-6": ("SULAIMANI", "14"),
    "menu-7": ("BUTTER CHKN", "61"), "menu-8": ("PNR BTR MSL", "63"), "menu-9": ("CHKN 65 DRY", "41"),
    "menu-10": ("MTR MSHRM", "66"), "menu-11": ("EGG PARATHA", "22"), "menu-12": ("VEG BIRYANI", "71"),
    "menu-13": ("MINT LEMONADE", "35"), "menu-14": ("MASALA CHAI", "13"),
}
UNMAPPED = [("t-thali", "SPL THALI", "88", "br-01", 78, D("3120.00")),
            ("t-combo", "MTR MSHRM CMBO", "67", "br-02", 70, D("2800.00")),
            ("t-family", "FAMILY PACK", "99", "br-03", 40, D("2400.00"))]


def split(total: int, parts: int) -> list[int]:
    base, rem = divmod(total, parts)
    return [base + (1 if i < rem else 0) for i in range(parts)]


def build_sales(menu, *, branches=BRANCHES, days=WEEK, weekly=WEEKLY, skip=None, unmapped=UNMAPPED, mapped=True):
    """One ItemSales per (branch, item, day)."""
    rows = []
    skip = skip or set()
    for mid, (qa, qb, qc) in weekly.items():
        if mid not in [m for m, *_ in MENU_SPEC]:
            continue
        spec = next(s for s in MENU_SPEC if s[0] == mid)
        price = spec[3]
        per_portion = DISCOUNT_NET_PER_PORTION.get(mid, net_price(price))
        for (bid, _), qty in zip(BRANCHES, (qa, qb, qc)):
            if bid not in dict(branches) or qty == 0:
                continue
            branch_days = [d for d in days if (bid, d) not in skip]
            if not branch_days:
                continue
            qtys = split(qty, len(branch_days))
            total_net = EXPLICIT_NET.get((mid, bid), fils(per_portion * qty))
            nets = [fils(total_net * q / qty) for q in qtys]
            nets[-1] = total_net - sum(nets[:-1])
            till_name, code = TILL_NAMES[mid]
            for i, (d, q, n) in enumerate(zip(branch_days, qtys, nets)):
                refunded, refund_value = D(0), D(0)
                if mid == "menu-9" and bid == "br-01" and i == 3:
                    refunded, refund_value = D(2), fils(-2 * per_portion)
                rows.append(C.ItemSales(
                    branch_id=bid, business_date=d, till_item_id=f"t-{mid}", name=till_name, code=code,
                    menu_item_id=mid if mapped else None, excluded=False,
                    qty_sold=D(q), qty_refunded=refunded, positive_value=n, refund_value=refund_value,
                    no_qty_lines=0,
                ))
    for tid, name, code, bid, qty, value in unmapped:
        if bid not in dict(branches):
            continue
        branch_days = [d for d in days if (bid, d) not in skip]
        if not branch_days:
            continue
        qtys = split(qty, len(branch_days))
        nets = [fils(value * q / qty) for q in qtys]
        nets[-1] = value - sum(nets[:-1])
        for d, q, n in zip(branch_days, qtys, nets):
            rows.append(C.ItemSales(bid, d, tid, name, code, None, False, D(q), D(0), n, D(0), 0))
    # DELIVERY CHARGE, not a menu item, every branch, every day.
    for bid, _ in branches:
        for d in days:
            if (bid, d) in skip:
                continue
            rows.append(C.ItemSales(bid, d, "t-delivery", "DELIVERY CHARGE", None, None, True, D(6), D(0), D("30.00"), D(0), 0))
    return rows


def sales_days(sales) -> list[R.SalesDay]:
    by = {}
    for s in sales:
        by[(s.branch_id, s.business_date)] = by.get((s.branch_id, s.business_date), D(0)) + s.net_item_sales
    return [R.SalesDay(b, d, fils(n), fils(n * (1 + VAT))) for (b, d), n in sorted(by.items())]


def inv(iid, bid, status, on, total, tax, supplier, no):
    return R.Invoice(invoice_id=iid, branch_id=bid, status=status, currency=CURRENCY,
                     total=D(total), tax=D(tax), invoice_date=on, purchased_on=on, placed_on=on,
                     supplier_name=supplier, invoice_no=no)


FULL_INVOICES = [
    inv("inv-c1", "br-01", "confirmed", datetime.date(2026, 8, 25), "5335.79", "254.09", "Al Madina Trading Co.", "AMT-26-1203"),
    inv("inv-c2", "br-01", "confirmed", datetime.date(2026, 8, 28), "2415.00", "115.00", "Gulf Fresh Vegetables & Fruits", "GFT-2026-0908"),
    inv("inv-c3", "br-01", "confirmed", datetime.date(2026, 8, 31), "4742.33", "225.83", "Al Madina Trading Co.", "AMT-26-1274"),
    inv("inv-c4", "br-03", "confirmed", datetime.date(2026, 8, 27), "4326.63", "206.03", "Emirates Pack", "ES-4471"),
    inv("inv-1002", "br-02", "awaiting_confirm", datetime.date(2026, 8, 29), "283.76", "13.51", "Al Seeb Trading Co LLC", "INV-7731"),
]
QUIET_INVOICES = [
    inv("inv-c1", "br-01", "confirmed", datetime.date(2026, 8, 25), "5335.79", "254.09", "Al Madina Trading Co.", "AMT-26-1203"),
    inv("inv-c3", "br-01", "confirmed", datetime.date(2026, 8, 31), "4742.33", "225.83", "Al Madina Trading Co.", "AMT-26-1274"),
    inv("inv-c5", "br-02", "confirmed", datetime.date(2026, 8, 26), "2100.00", "100.00", "Al Seeb Trading Co LLC", "INV-7740"),
    inv("inv-c4", "br-03", "confirmed", datetime.date(2026, 8, 27), "4326.63", "206.03", "Emirates Pack", "ES-4471"),
]

FULL_APPROVALS = {
    "": {"count": 2, "duplicates": 1, "awaiting_confirm": 2},
    "br-01": {"count": 2, "duplicates": 1, "awaiting_confirm": 1},
    "br-02": {"count": 0, "duplicates": 0, "awaiting_confirm": 1},
    "br-03": {"count": 0, "duplicates": 0, "awaiting_confirm": 0},
}
FULL_PAPERS = [
    {"invoice_id": "inv-1003", "supplier_name": "Gulf Fresh Vegetables & Fruits", "invoice_no": "2214",
     "total": "101.00", "invoice_date": "2026-08-22", "branch_name": "Al Quoz", "status": "needs_review", "is_duplicate": False},
    {"invoice_id": "inv-1004", "supplier_name": "Al Madina Foodstuff Trading LLC", "invoice_no": "INV-10482",
     "total": "716.89", "invoice_date": "2026-08-21", "branch_name": "Al Quoz", "status": "needs_review", "is_duplicate": True},
]
NO_APPROVALS = {k: {"count": 0, "duplicates": 0, "awaiting_confirm": 0} for k in ("", "br-01", "br-02", "br-03")}


# --- price moves --------------------------------------------------------------


def line(cost, on, *, pack, product, supplier, invoice, position, unit, quality=None):
    per_display, display_unit = M.costing.per_display_unit(D(cost), unit)
    return M.MoveLine(supplier_item_id=pack, product_name=product, supplier_name=supplier, pack_size=None,
                      cost_per_base_unit=D(cost), per_display_unit=per_display, display_unit=display_unit,
                      invoice_id=invoice, invoice_line_id=f"{invoice}-{position}", position=position,
                      purchased_on=on, invoice_date=on, quality=quality)


def move(ingredient_id, name, unit, previous, current, items):
    delta = current.cost_per_base_unit - previous.cost_per_base_unit
    factor = M.costing.DISPLAY_UNITS[unit][1]
    return M.PriceMove(ingredient_id=ingredient_id, ingredient_name=name, base_unit=unit, kind="moved",
                       current=current, previous=previous, delta_per_base_unit=delta,
                       delta_per_display_unit=(delta * factor).quantize(M.costing.DISPLAY_QUANTUM),
                       items=tuple(items))


def impact(mid, name, per_portion):
    return M.MoveImpact(menu_item_id=mid, name=name, impact_per_portion=D(per_portion),
                        margin_before=D(0), margin_after=D(0), margin_pct_before=D(0), margin_pct_after=D(0))


FULL_MOVES = [
    move("ing-nido", "Milk Powder", "g",
         line("0.0580", MARCH, pack="sitem-1", product="Milk Powder 2.5kg", supplier="Al Madina Foodstuff Trading LLC", invoice="inv-0912", position=1, unit="g"),
         line("0.0614", A21, pack="sitem-1", product="Milk Powder 2.5kg", supplier="Al Madina Foodstuff Trading LLC", invoice="inv-1001", position=1, unit="g"),
         [impact("menu-3", "Nido Shake", "0.136"), impact("menu-2", "Karak Tea (Flask 1 L)", "0.102"),
          impact("menu-14", "Masala Chai", "0.020"), impact("menu-1", "Karak Tea (Cup)", "0.017")]),
    move("ing-sugar", "White Sugar", "g",
         line("0.0038", datetime.date(2026, 8, 10), pack="sitem-7", product="White Sugar 25kg", supplier="Gulf Fresh Vegetables & Fruits", invoice="inv-0998", position=1, unit="g"),
         line("0.0040", A28, pack="sitem-7", product="White Sugar 25kg", supplier="Gulf Fresh Vegetables & Fruits", invoice="inv-1005", position=1, unit="g"),
         [impact("menu-2", "Karak Tea (Flask 1 L)", "0.016"), impact("menu-3", "Nido Shake", "0.004"),
          impact("menu-1", "Karak Tea (Cup)", "0.002"), impact("menu-6", "Sulaimani", "0.002"),
          impact("menu-14", "Masala Chai", "0.002")]),
]


# --- words the route will compose (ported verbatim into dashboard.py) ------------

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
NUMBER_WORDS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}


def weekday_date(d):
    return f"{WEEKDAYS[d.weekday()]} {d.day} {d.strftime('%b')}"


def freshness_sentence(newest, today):
    if newest is None:
        return None
    ago = (today - newest).days
    when = "today" if ago <= 0 else "yesterday" if ago == 1 else f"{ago} days ago"
    return f"Sales loaded to {weekday_date(newest)}, {when}."


def short_branch(name):
    words = name.split()
    return " ".join(words[:-1]) if len(words) > 1 and words[-1].lower() == "branch" else name


def branch_answer(ranked_league, scope_name=None):
    rated = [c for c in ranked_league if c.contribution_pct is not None]
    if not rated:
        return None, None
    top = rated[0]
    kept = top.contribution_pct.quantize(D("1"), rounding=ROUND_HALF_UP)
    name = short_branch(top.branch_name or "")
    if scope_name is not None:
        sentence = f"{name} keeps about AED {kept} of every 100 it takes."
    elif len(rated) == 1:
        sentence = f"Look at {name} first: it keeps about AED {kept} of every 100 it takes, the only branch with a figure."
    else:
        n = NUMBER_WORDS.get(len(rated), str(len(rated)))
        sentence = f"Look at {name} first: it keeps about AED {kept} of every 100 it takes, the least of the {n}."
    if top.quality is Quality.INCOMPLETE:
        sentence += " Its figure is incomplete - its row says why."
    return sentence, top


def item_answer(rows, chain, scope):
    fired = S.popular_low_margin(rows, chain, scope=scope, currency=CURRENCY)
    if not fired:
        return None, None
    by_id = {r.menu_item_id: r for r in rows if r.branch_id == scope.branch_id}
    best = max(fired, key=lambda s: by_id[s.menu_item_id].net_item_sales)
    where = "" if scope.branch_name is None else f" at {short_branch(scope.branch_name)}"
    return (f"{best.menu_item_name} sells more than any item{where} that earns under the menu's average.",
            by_id[best.menu_item_id])


# --- serialisation ------------------------------------------------------------


def s(v):
    return None if v is None else str(v)


def iso(d):
    return None if d is None else d.isoformat()


def item_row_json(r: C.ItemRow):
    return {
        "menu_item_id": r.menu_item_id, "menu_item_name": r.menu_item_name, "category": r.category,
        "branch_id": r.branch_id, "qty_sold": s(r.qty_sold), "qty_refunded": s(r.qty_refunded),
        "net_item_sales": s(r.net_item_sales), "cost_per_portion": s(r.cost_per_portion), "cost": s(r.cost),
        "cost_per_portion_today": s(r.cost_per_portion_today), "contribution": s(r.contribution),
        "contribution_pct": s(r.contribution_pct), "avg_sold_at": s(r.avg_sold_at), "net_price": s(r.net_price),
        "plate_quality": r.plate_quality, "quality": r.quality.value, "notes": list(r.notes),
        "recipe_version": r.recipe_version,
        "till_items": [{"till_item_id": t.till_item_id, "name": t.name, "code": t.code} for t in r.till_items],
        "components": [
            {"ingredient_id": c.ingredient_id, "ingredient_name": c.ingredient_name, "qty": s(c.qty), "unit": c.unit,
             "cost_per_portion": s(c.cost_per_portion), "invoice_id": c.invoice_id, "line_position": c.line_position,
             "purchased_on": iso(c.purchased_on)}
            for c in r.components
        ],
        "archived": r.archived,
    }


def league_row_json(row: R.BranchRow, c: C.Contribution):
    return {
        "branch_id": row.branch_id, "branch_name": row.branch_name,
        "window": {"from": iso(row.window.start), "to": iso(row.window.end), "days": row.window.days},
        "net_sales": s(row.net_sales), "takings": s(row.takings), "purchases": s(row.purchases),
        "ratio_pct": s(row.ratio_pct), "contribution": s(c.contribution), "contribution_pct": s(c.contribution_pct),
        "costed_share_pct": s(c.costed_share_pct), "ratio_quality": row.quality.value, "ratio_notes": list(row.notes),
        "contribution_quality": c.quality.value, "contribution_notes": list(c.notes),
        "days_loaded": row.days_loaded, "days_missing": row.days_missing, "deliveries": row.deliveries,
        "sales_through": iso(row.sales_through), "last_purchase_on": iso(row.last_purchase_on),
    }


def signal_json(sig: S.Signal):
    return {
        "kind": sig.kind, "money_at_stake": s(sig.money_at_stake), "quality": sig.quality.value,
        "sentence": sig.sentence, "detail": sig.detail, "branch_id": sig.branch_id, "branch_name": sig.branch_name,
        "menu_item_id": sig.menu_item_id, "menu_item_name": sig.menu_item_name, "ingredient_id": sig.ingredient_id,
        "ingredient_name": sig.ingredient_name, "invoice_id": sig.invoice_id, "moved_on": iso(sig.moved_on),
    }


def worse(a, b):
    rank = {Quality.UNAVAILABLE: 0, Quality.INCOMPLETE: 1, Quality.ESTIMATED: 2, Quality.RELIABLE: 3}
    return a if rank[a] <= rank[b] else b


# --- one payload ---------------------------------------------------------------


def payload(*, menu, sales, invoices, today, approvals, papers, moves, scope_id=None, branches=BRANCHES,
            menu_counts=None):
    scope = S.Scope(scope_id, NAMES.get(scope_id)) if scope_id else S.CHAIN
    days = sales_days(sales)
    newest_by_branch = {}
    for d in days:
        newest_by_branch[d.branch_id] = max(newest_by_branch.get(d.branch_id, d.business_date), d.business_date)
    newest = max(newest_by_branch.values()) if newest_by_branch else None
    if newest is None:
        period = R.Period(today - datetime.timedelta(days=27), today)
    else:
        period = PERIOD
    plates_today = today_plates(menu)
    costed_at = period.end

    # the league, ratio side
    ratio_rows = {
        bid: R.period_row(branch_id=bid, branch_name=name, days=days, invoices=invoices, period=period,
                          tenant_currency=CURRENCY, latest_sales_day=newest_by_branch.get(bid))
        for bid, name in branches
    }
    unassigned = R.unassigned_group(invoices, period, CURRENCY)
    ratio_total = R.chain_total(list(ratio_rows.values()), unassigned)

    # contribution
    period_sales = C.days_in_period(sales, period)
    branch_rows = C.item_rows(period_sales, menu, today_plates=plates_today, costed_at=costed_at, currency=CURRENCY)
    chain_rows = C.chain_item_rows(branch_rows, menu, branch_names=NAMES, today_plates=plates_today, costed_at=costed_at, currency=CURRENCY)
    all_rows = [*branch_rows, *chain_rows]
    contributions = {}
    for bid, name in branches:
        rr = ratio_rows[bid]
        contributions[bid] = C.branch_contribution(
            [r for r in branch_rows if r.branch_id == bid], branch_id=bid, branch_name=name,
            sales_quality=rr.sales_quality, sales_notes=rr.sales_notes,
            unmapped=C.unmapped(period_sales, branch_id=bid))
    chain = C.chain_contribution(list(contributions.values()), unmapped=C.unmapped(period_sales))
    ranked = C.rank(list(contributions.values()))
    figures = [S.BranchFigure(window=ratio_rows[c.branch_id].window, contribution=c) for c in ranked]
    sigs = S.compute(rows=all_rows, chain=chain, branches=figures, moves=moves, sales=period_sales,
                     menu=menu, period=period, scope=scope, currency=CURRENCY)

    in_scope_league = [c for c in ranked if scope_id is None or c.branch_id == scope_id]
    branch_sentence, top_branch = branch_answer(in_scope_league, scope.branch_name)
    item_sentence, top_item = item_answer(all_rows, chain, scope)
    answer_quality = Quality.RELIABLE
    notes = []
    if top_branch is not None:
        answer_quality = worse(answer_quality, top_branch.quality)
        notes.extend(top_branch.notes)
    if top_item is not None:
        answer_quality = worse(answer_quality, top_item.quality)
    if top_branch is None and top_item is None:
        answer_quality = Quality.UNAVAILABLE

    age = None if newest is None else (today - newest).days
    last_purchase = max((i.purchased_on for i in invoices if i.status == "confirmed" and i.purchased_on and period.start <= i.purchased_on <= period.end), default=None)
    latest_day = None
    if newest is not None and period.start <= newest <= period.end:
        on_day = [d for d in days if d.business_date == newest]
        latest_day = {
            "date": iso(newest), "net_sales": s(fils(sum((d.net_sales for d in on_day), D(0)))),
            "branches": [{"branch_id": d.branch_id, "branch_name": NAMES[d.branch_id], "date": iso(d.business_date), "net_sales": s(d.net_sales)} for d in on_day],
        }

    scope_rows = [r for r in all_rows if r.branch_id == scope_id]
    costed = [r for r in scope_rows if r.costed]
    return {
        "period": {"from": iso(period.start), "to": iso(period.end), "days": period.days, "default": True,
                   "sales_through": iso(newest), "sales_age_days": age,
                   "months": ["2026-08"] if newest else [], "costed_at": iso(costed_at)},
        "answer": {"branch": branch_sentence, "item": item_sentence, "quality": answer_quality.value, "notes": notes},
        "freshness": {"sales_through": iso(newest), "sales_age_days": age, "last_purchase_on": iso(last_purchase),
                      "branches_without_sales": sum(1 for r in ratio_rows.values() if r.net_sales is None),
                      "quality": "estimated" if age is not None and age > 7 else "reliable_with_limitations",
                      "sentence": freshness_sentence(newest, today)},
        "latest_day": latest_day,
        "approvals": {**approvals[scope_id or ""], "invoices": papers if approvals[scope_id or ""]["count"] else []},
        "league": [league_row_json(ratio_rows[c.branch_id], c) for c in in_scope_league],
        "unassigned": {"count": unassigned.count, "purchases": s(unassigned.purchases)},
        "scope": {"branch_id": scope_id, "branch_name": NAMES.get(scope_id)},
        "total": {"net_sales": s(ratio_total.net_sales), "purchases": s(ratio_total.purchases), "ratio_pct": s(ratio_total.ratio_pct),
                  "contribution": s(chain.contribution), "contribution_pct": s(chain.contribution_pct),
                  "costed_share_pct": s(chain.costed_share_pct), "ratio_quality": ratio_total.quality.value,
                  "ratio_notes": list(ratio_total.notes), "contribution_quality": chain.quality.value,
                  "contribution_notes": list(chain.notes)},
        "items": {"top": [item_row_json(r) for r in costed[:5]], "bottom": [item_row_json(r) for r in costed[-5:]] if len(costed) > 5 else [],
                  "all": [item_row_json(r) for r in scope_rows], "count": len(costed)},
        "signals": [signal_json(x) for x in sigs],
        "unmapped": {"names": C.unmapped(period_sales, branch_id=scope_id).names, "value": s(C.unmapped(period_sales, branch_id=scope_id).value)},
        "menu": menu_counts or {"items": len(menu), "costed": sum(1 for m in menu.values() if m.plate.cost_per_portion is not None)},
    }


def scenario(name, **kw):
    out = {}
    for sid in [None, "br-01", "br-02", "br-03"]:
        out[sid or ""] = payload(scope_id=sid, **kw)
    with open(f"{OUT}/{name}.json", "w") as f:
        json.dump(out, f, separators=(",", ":"), ensure_ascii=False)
        f.write("\n")
    chain = out[""]
    print(name, "signals:", [(x["kind"], x["money_at_stake"]) for x in chain["signals"]])
    print("  answer:", chain["answer"])
    print("  total:", chain["total"]["contribution"], chain["total"]["contribution_pct"], chain["total"]["contribution_quality"])
    for row in chain["league"]:
        print("  ", row["branch_name"], row["net_sales"], row["ratio_pct"], row["contribution"], row["contribution_pct"], row["contribution_quality"], row["contribution_notes"])


TODAY = datetime.date(2026, 9, 5)
menu_full = build_menu()
sales_full = build_sales(menu_full)
scenario("full", menu=menu_full, sales=sales_full, invoices=FULL_INVOICES, today=TODAY,
         approvals=FULL_APPROVALS, papers=FULL_PAPERS, moves=FULL_MOVES)

# partial: Deira never loaded, Karama missing 27 Aug, sales twelve days old.
skip = {("br-03", d) for d in WEEK} | {("br-02", datetime.date(2026, 8, 27))}
sales_partial = build_sales(menu_full, skip=skip)
scenario("partial", menu=menu_full, sales=sales_partial, invoices=FULL_INVOICES, today=datetime.date(2026, 9, 12),
         approvals=FULL_APPROVALS, papers=FULL_PAPERS, moves=FULL_MOVES)

# quiet: the tea menu, proportional mixes, every paper confirmed, nothing moved.
quiet_ids = {"menu-1", "menu-2", "menu-6", "menu-14"}
menu_quiet = build_menu(quiet_ids)
quiet_weekly = {"menu-1": (980, 700, 490), "menu-2": (240, 171, 120), "menu-6": (420, 300, 210), "menu-14": (210, 150, 105)}
sales_quiet = build_sales(menu_quiet, weekly=quiet_weekly, unmapped=[])
scenario("quiet", menu=menu_quiet, sales=sales_quiet, invoices=QUIET_INVOICES, today=TODAY,
         approvals=NO_APPROVALS, papers=[], moves=[])

# empty: the menu exists, nothing loaded.
scenario("empty", menu=menu_full, sales=[], invoices=[], today=TODAY, approvals=NO_APPROVALS, papers=[], moves=[])

# nomenu: the week loaded, no menu at all.
sales_nomenu = build_sales(menu_full, mapped=False)
scenario("nomenu", menu={}, sales=sales_nomenu, invoices=FULL_INVOICES, today=TODAY,
         approvals=FULL_APPROVALS, papers=FULL_PAPERS, moves=[], menu_counts={"items": 0, "costed": 0})
