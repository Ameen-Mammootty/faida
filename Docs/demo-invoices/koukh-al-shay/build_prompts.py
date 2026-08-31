"""Build the five Koukh Al Shay demo papers in the corpus house format."""
from decimal import Decimal, ROUND_HALF_UP
import pathlib, sys

D = lambda v: Decimal(str(v))
OUT = pathlib.Path("Docs/demo-invoices/koukh-al-shay")

# (code, description, qty, unit, pack, unit_price)  -- pack must parse in units.py
A = [  # Al Aweer produce
 ("VEG-ONI-10","ONION",6,"bag","10 kg",22.00),
 ("VEG-TOM-06","TOMATO",5,"box","6 kg",15.00),
 ("VEG-CAP-05","CAPSICUM GREEN",3,"box","5 kg",21.00),
 ("VEG-GNG-05","GINGER",1,"box","5 kg",34.00),
 ("VEG-GAR-05","GARLIC PEELED",1,"box","5 kg",46.00),
 ("VEG-CHI-01","GREEN CHILLI",2,"bag","1 kg",9.50),
 ("VEG-COR-01","CORIANDER FRESH",3,"bag","1 kg",12.00),
 ("VEG-CUR-500","CURRY LEAVES",2,"bag","500 g",11.00),
 ("VEG-SPO-02","SPRING ONION",2,"bag","2 kg",16.00),
 ("VEG-LEM-05","LEMON",2,"box","5 kg",19.50),
 ("VEG-MUS-02","MUSHROOM",2,"box","2 kg",27.00),
 ("VEG-SPI-02","SPINACH",1,"box","2 kg",13.00),
 ("VEG-CAU-06","CAULIFLOWER",1,"box","6 kg",18.00),
 ("VEG-PEA-01","GREEN PEAS",4,"bag","1 kg",8.75),
 ("VEG-COC-01","COCONUT GRATED",2,"bag","1 kg",14.00),
 ("VEG-GGP-01","GINGER GARLIC PASTE",4,"tub","1 kg",18.00),
]
B = [  # Deira dry goods and spices
 ("DRY-SUG-50","WHITE SUGAR",2,"sack","50 kg",115.00),
 ("DRY-SAL-25","SALT",2,"sack","25 kg",21.00),
 ("SPC-RCP-01","RED CHILLI POWDER",5,"pkt","1 kg",17.50),
 ("SPC-TUR-01","TURMERIC",4,"pkt","1 kg",14.00),
 ("SPC-CDP-01","CORIANDER POWDER",5,"pkt","1 kg",13.50),
 ("SPC-CDS-500","CORIANDER SEED CRUSHED",4,"pkt","500 g",9.00),
 ("SPC-GAR-500","GARAM MASALA",6,"pkt","500 g",22.00),
 ("SPC-CUM-500","CUMIN SEED",3,"pkt","500 g",16.00),
 ("SPC-KCP-500","KASHMIRI CHILLI POWDER",4,"pkt","500 g",24.00),
 ("SPC-KAS-250","KASURI METHI",4,"pkt","250 g",13.00),
 ("SPC-BLP-500","BLACK PEPPER CRUSHED",2,"pkt","500 g",42.00),
 ("SPC-WHP-500","WHITE PEPPER",1,"pkt","500 g",46.00),
 ("SPC-DRC-01","DRIED RED CHILLI",2,"pkt","1 kg",26.00),
 ("SPC-CIN-500","CINNAMON STICK",3,"pkt","500 g",31.00),
 ("SPC-CAR-500","GREEN CARDAMOM",4,"pkt","500 g",148.00),
 ("SPC-DGP-250","DRY GINGER",2,"pkt","250 g",18.00),
 ("DRY-BSD-01","BAKING SODA",1,"pkt","1 kg",9.00),
 ("DRY-CNF-01","CORN FLOUR",6,"pkt","1 kg",11.50),
 ("DRY-CNS-01","CORN STARCH",2,"pkt","1 kg",12.00),
 ("DRY-TOR-25","TOOR DAL",1,"sack","25 kg",148.00),
 ("DRY-CSH-01","CASHEW NUTS",2,"pkt","1 kg",64.00),
 ("DRY-PIS-500","PISTACHIO SLIVERED",1,"pkt","500 g",92.00),
 ("DRY-DSC-01","DESICCATED COCONUT",2,"pkt","1 kg",21.00),
 ("SPC-SAF-50","SAFFRON",1,"tin","50 g",340.00),
]
C = [  # Al Madina dairy, chilled and frozen
 ("DRY-EVP-48","EVAP MILK 48X400ML",6,"ctn","48x400ml",90.00),
 ("DRY-CDM-48","CONDENSED MILK 48X395G",3,"ctn","48x395g",145.00),
 ("CHL-FRM-12","FRESH MILK 12X1L",8,"ctn","12x1l",42.00),
 ("DRY-MPW-25","MILK POWDER",1,"sack","25 kg",395.00),
 ("CHL-BUT-10","BUTTER",1,"ctn","10 kg",235.00),
 ("CHL-GHE-05","GHEE",1,"tin","5 kg",148.00),
 ("CHL-CRM-12","CREAM COOKING 12X1L",2,"ctn","12x1l",96.00),
 ("CHL-YOG-05","YOGHURT",2,"tub","5 kg",34.00),
 ("CHL-EGG-18","EGG",4,"tray","1.8 kg",13.50),
 ("CHL-PAN-01","PANEER",6,"pkt","1 kg",26.00),
 ("FRZ-CHB-10","CHICKEN BONELESS",3,"ctn","10 kg",34.50),
 ("FRZ-CHW-10","CHICKEN WINGS",1,"ctn","10 kg",29.00),
 ("FRZ-BEF-05","BEEF BONELESS",1,"ctn","5 kg",68.00),
 ("FRZ-PRW-01","PRAWNS PEELED",2,"bag","1 kg",38.00),
]
Dsup = [  # Gulf general trading: beverages, bakery, ambient, disposables
 ("BEV-CTC-05","CTC BLACK TEA",4,"bag","5 kg",92.00),
 ("BEV-INC-01","INSTANT COFFEE",2,"tin","1 kg",78.00),
 ("BEV-KGT-01","KASHMIRI GREEN TEA LEAVES",1,"pkt","1 kg",54.00),
 ("BEV-HAH-01","HABBAT AL HAMRA BLEND",1,"pkt","1 kg",68.00),
 ("BEV-BST-450","BOOST POWDER",6,"tin","450 g",22.50),
 ("BEV-HRL-500","HORLICKS POWDER",6,"tin","500 g",24.00),
 ("BEV-DCH-01","DRINKING CHOCOLATE POWDER",2,"tin","1 kg",34.00),
 ("BEV-COC-01","COCOA POWDER",1,"tin","1 kg",42.00),
 ("BEV-SAH-500","SAHLAB POWDER",2,"pkt","500 g",28.00),
 ("BEV-ROS-500","ROSE WATER",4,"btl","500 ml",6.50),
 ("AMB-OIL-05","OIL SUNFLOWER",8,"tin","5 l",39.00),
 ("AMB-VIN-05","VINEGAR",2,"can","5 l",14.00),
 ("AMB-SOY-05","LIGHT SOY SAUCE",2,"can","5 l",32.00),
 ("AMB-RCS-05","RED CHILLI SAUCE",2,"can","5 l",29.00),
 ("AMB-KTC-05","TOMATO KETCHUP",3,"can","5 l",26.00),
 ("BEV-WTR-19","WATER 5 GALLON",12,"btl","18.9 l",7.50),
 ("BKY-HON-01","HONEY CAKE WHOLE (10 SLICES)",4,"pc","1 pc",34.00),
 ("BKY-ZAF-01","ZAFRAN CAKE WHOLE (10 SLICES)",4,"pc","1 pc",36.00),
 ("BKY-LOT-01","LOTUS CAKE WHOLE (10 SLICES)",4,"pc","1 pc",42.00),
 ("PKG-CKB-100","CAKE BOX + FORK",2,"ctn","100 pcs",38.00),
 ("PKG-DCS-100","DELIVERY CUP S + LID",4,"ctn","100 pcs",21.00),
 ("PKG-DCM-100","DELIVERY CUP M + LID",4,"ctn","100 pcs",24.00),
 ("PKG-DCL-100","DELIVERY CUP L + LID",4,"ctn","100 pcs",28.00),
 ("PKG-FL1-50","DISPOSABLE FLASK 1 L",3,"ctn","50 pcs",62.00),
 ("PKG-FL2-50","DISPOSABLE FLASK 2 L",3,"ctn","50 pcs",88.00),
 ("PKG-PCS-100","PAPER CUP SMALL + LID",8,"ctn","100 pcs",17.50),
 ("PKG-PCL-100","PAPER CUP LARGE + LID",8,"ctn","100 pcs",21.00),
 ("PKG-TWC-100","TAKEAWAY CONTAINER + LID",10,"ctn","100 pcs",33.00),
]
E = [  # the on-stage paper: Al Madina again, one week later, prices moved
 ("DRY-EVP-48","EVAP MILK 48X400ML",6,"ctn","48x400ml",99.00),
 ("DRY-MPW-25","MILK POWDER",1,"sack","25 kg",432.00),
 ("CHL-FRM-12","FRESH MILK 12X1L",8,"ctn","12x1l",42.00),
 ("FRZ-CHB-10","CHICKEN BONELESS",3,"ctn","10 kg",31.00),
]

SUPPLIERS = {
 "KAS-1": ("Al Aweer Fresh Produce LLC","Shop 214, Central Fruit & Vegetable Market, Al Aweer, Dubai, UAE",
           "+971 4 320 7714","100447821900003","AAF-2026-3318","24/08/2026",A,
           "A clean laser print on the supplier's own pre-printed letterhead."),
 "KAS-2": ("Deira Spice & Dry Foods Trading LLC","Shop 6, Naif Road, Deira, Dubai, UAE",
           "+971 4 271 8842","100226519400003","DSF-26-08-441","24/08/2026",B,
           "A clean laser print. Slight toner banding across the lower third, as a busy office printer leaves."),
 "KAS-3": ("Al Madina Trading Co.","Warehouse 7, Al Quoz Industrial 3, Dubai, UAE",
           "+971 4 339 1120","100338745600003","AMT-26-1203","25/08/2026",C,
           "A clean laser print. The chilled and frozen sections are separated by a ruled line."),
 "KAS-4": ("Gulf Foods Trading L.L.C.","Warehouse 22, Al Qusais Industrial 2, Dubai, UAE",
           "+971 4 258 9903","100115447800003","GFT-2026-0908","25/08/2026",Dsup,
           "A clean laser print. Two-column item codes, as a cash-and-carry invoice prints."),
 "KAS-5": ("Al Madina Trading Co.","Warehouse 7, Al Quoz Industrial 3, Dubai, UAE",
           "+971 4 339 1120","100338745600003","AMT-26-1274","31/08/2026",E,
           "A clean laser print, identical house style to the earlier Al Madina paper."),
}

TEMPLATE = """Produce one photorealistic image of a single real-world paper document. The image contains nothing but that document and the surface it rests on. Do not add captions, arrows, labels, borders, mock-up frames, logos of real companies, or any text of your own invention.

PHYSICAL ARTEFACT
A crisp A4 laser-printed business document, flat, evenly lit, no shadow, no skew, pure white paper, as if produced by a flatbed scanner at 300 dpi. Whole page in frame with a thin white margin.
{look}

LANGUAGE
All text is in English with western digits.

EXACT CONTENT. Reproduce every character and every digit exactly as written below. Do not round, recalculate, reorder, translate, abbreviate, expand, add or omit anything. The arithmetic below is already correct.

-- Header --
SUPPLIER NAME (top of the document): {supplier}
SUPPLIER ADDRESS: {address}
SUPPLIER PHONE: {phone}
SUPPLIER TRN: {trn}
DOCUMENT TITLE: TAX INVOICE
Invoice number: {number}
Date: {date}
Bill to: Koukh Al Shay Cafeteria LLC
Customer TRN: 100662310500003
Deliver to: Koukh Al Shay, Al Qusais Branch, Damascus Street, Al Qusais, Dubai, UAE
Payment terms: 30 days credit
Currency: AED

-- Line items, all {n} of them, in this exact order --
COLUMNS, left to right: # | Item code | Description | Qty | Unit | Pack size | Unit price AED | Amount AED

{lines}

-- Totals block, lower right --
Subtotal: AED {subtotal}
VAT 5%: AED {vat}
TOTAL DUE: AED {total}

The printed prices are exclusive of VAT.
"""

def money(v): return f"{v.quantize(D('0.01'), rounding=ROUND_HALF_UP):,.2f}"

def build(key):
    supplier, address, phone, trn, number, date, rows, look = SUPPLIERS[key]
    out, subtotal = [], D(0)
    for i, (code, desc, qty, unit, pack, price) in enumerate(rows, 1):
        amount = (D(qty) * D(price)).quantize(D("0.01"), rounding=ROUND_HALF_UP)
        subtotal += amount
        out.append(f"{i} | {code} | {desc} | {qty} | {unit} | {pack} | {D(price):.2f} | {money(amount)}")
    vat = (subtotal * D("0.05")).quantize(D("0.01"), rounding=ROUND_HALF_UP)
    total = subtotal + vat
    text = TEMPLATE.format(look=look, supplier=supplier, address=address, phone=phone, trn=trn,
                           number=number, date=date, n=len(rows), lines="\n".join(out),
                           subtotal=money(subtotal), vat=money(vat), total=money(total))
    (OUT / f"{key}.prompt.txt").write_text(text)
    return key, supplier, number, date, len(rows), money(subtotal), money(vat), money(total)

OUT.mkdir(parents=True, exist_ok=True)
print(f"{'paper':7} {'supplier':34} {'number':16} {'date':11} {'lines':>5} {'subtotal':>10} {'VAT':>8} {'total':>10}")
for k in SUPPLIERS:
    key, sup, num, date, n, sub, vat, tot = build(k)
    print(f"{key:7} {sup[:34]:34} {num:16} {date:11} {n:5d} {sub:>10} {vat:>8} {tot:>10}")
