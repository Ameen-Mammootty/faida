"""Render the five demo papers to A4 HTML, for rasterising to PNG.

**Why a render and not an image model.** These invoices exist to make the
on-stage reply predetermined: the totals, the VAT and the per-base-unit deltas
are all load-bearing, and the alert thresholds are computed off them to the
fils. A generative image model rewrites digits - that is why the corpus prompts
have to shout "reproduce every character exactly" at it, and why every
generated paper needs proofreading afterwards. A render cannot get a digit
wrong, so the paper on the phone is the paper the arithmetic was checked
against.

The numbers come from `build_prompts.py`, imported rather than copied, so the
generator prompt and the printed document can never drift apart.

    apps/api/.venv/bin/python Docs/demo-invoices/koukh-al-shay/render_papers.py

writes KAS-*.html beside this file. Rasterise each with the browse skill:

    $B viewport 1055x1491 --scale 2
    $B load-html Docs/demo-invoices/koukh-al-shay/KAS-1.html
    $B screenshot Docs/demo-invoices/koukh-al-shay/KAS-1.png --selector .page

A4 proportions at 1055x1491 match the DEMO-1..3 papers already in this folder.
"""

import pathlib
from decimal import ROUND_HALF_UP, Decimal

from build_prompts import D, SUPPLIERS

HERE = pathlib.Path(__file__).resolve().parent

CSS = """
* { box-sizing: border-box; }
body { margin: 0; background: #fff; }
.page {
  width: 1055px; min-height: 1491px; background: #fff; color: #111;
  padding: 62px 58px 48px; font-family: "Helvetica Neue", Arial, sans-serif;
  font-size: 13px; line-height: 1.45; position: relative;
}
.masthead { display: flex; justify-content: space-between; align-items: flex-start; }
.supplier { font-size: 21px; font-weight: 700; letter-spacing: -0.01em; }
.supplier-meta { margin-top: 6px; font-size: 12px; color: #333; line-height: 1.5; }
.title { text-align: right; }
.title h1 {
  margin: 0; font-size: 24px; font-weight: 700; letter-spacing: 0.12em; color: #111;
}
.title .rule { margin-top: 6px; height: 3px; background: #111; width: 190px; margin-left: auto; }
.meta {
  margin-top: 30px; display: flex; justify-content: space-between; gap: 40px;
  border-top: 1px solid #111; border-bottom: 1px solid #111; padding: 14px 0;
}
.meta dl { margin: 0; font-size: 12.5px; }
.meta dt { color: #555; }
.meta dd { margin: 0 0 7px; font-weight: 600; }
table { width: 100%; border-collapse: collapse; margin-top: 26px; font-size: 12.5px; }
thead th {
  text-align: left; border-bottom: 2px solid #111; padding: 7px 6px;
  font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase; color: #111;
}
tbody td { padding: 6px; border-bottom: 1px solid #e2e2e2; vertical-align: top; }
tbody tr:nth-child(even) td { background: #fafafa; }
.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.totals { margin-top: 26px; display: flex; justify-content: flex-end; }
.totals table { width: 320px; margin: 0; }
.totals td { padding: 6px 6px; border: none; font-size: 13px; }
.totals tr.grand td {
  border-top: 2px solid #111; font-weight: 700; font-size: 15px; padding-top: 9px;
}
.note { margin-top: 22px; font-size: 12px; color: #333; }
.foot {
  position: absolute; left: 58px; right: 58px; bottom: 34px;
  border-top: 1px solid #ccc; padding-top: 10px; font-size: 11px; color: #666;
  display: flex; justify-content: space-between;
}
"""

ROW = (
    '<tr><td class="num">{i}</td><td>{code}</td><td>{desc}</td>'
    '<td class="num">{qty}</td><td>{unit}</td><td>{pack}</td>'
    '<td class="num">{price}</td><td class="num">{amount}</td></tr>'
)

PAGE = """<title>{number}</title>
<style>{css}</style>
<div class="page">
  <div class="masthead">
    <div>
      <div class="supplier">{supplier}</div>
      <div class="supplier-meta">{address}<br>Tel {phone}<br>TRN {trn}</div>
    </div>
    <div class="title"><h1>TAX INVOICE</h1><div class="rule"></div></div>
  </div>

  <div class="meta">
    <dl>
      <dt>Invoice number</dt><dd>{number}</dd>
      <dt>Date</dt><dd>{date}</dd>
    </dl>
    <dl>
      <dt>Bill to</dt><dd>Koukh Al Shay Cafeteria LLC</dd>
      <dt>Customer TRN</dt><dd>100662310500003</dd>
    </dl>
    <dl>
      <dt>Deliver to</dt>
      <dd>Koukh Al Shay, Al Qusais Branch<br>Damascus Street, Al Qusais, Dubai, UAE</dd>
    </dl>
    <dl>
      <dt>Payment terms</dt><dd>30 days credit</dd>
      <dt>Currency</dt><dd>AED</dd>
    </dl>
  </div>

  <table>
    <thead><tr>
      <th class="num">#</th><th>Item code</th><th>Description</th><th class="num">Qty</th>
      <th>Unit</th><th>Pack size</th><th class="num">Unit price AED</th>
      <th class="num">Amount AED</th>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table>

  <div class="totals"><table>
    <tr><td>Subtotal</td><td class="num">AED {subtotal}</td></tr>
    <tr><td>VAT 5%</td><td class="num">AED {vat}</td></tr>
    <tr class="grand"><td>TOTAL DUE</td><td class="num">AED {total}</td></tr>
  </table></div>

  <p class="note">The printed prices are exclusive of VAT. Goods remain the property of the
  seller until paid in full.</p>

  <div class="foot"><span>{supplier}</span><span>Invoice {number}</span></div>
</div>
"""


def money(value: Decimal) -> str:
    return f"{value.quantize(D('0.01'), rounding=ROUND_HALF_UP):,.2f}"


def render(key: str) -> pathlib.Path:
    supplier, address, phone, trn, number, date, rows, _look = SUPPLIERS[key]
    body, subtotal = [], D(0)
    for index, (code, desc, qty, unit, pack, price) in enumerate(rows, 1):
        amount = (D(qty) * D(price)).quantize(D("0.01"), rounding=ROUND_HALF_UP)
        subtotal += amount
        body.append(
            ROW.format(
                i=index, code=code, desc=desc, qty=qty, unit=unit, pack=pack,
                price=f"{D(price):.2f}", amount=money(amount),
            )
        )
    vat = (subtotal * D("0.05")).quantize(D("0.01"), rounding=ROUND_HALF_UP)
    path = HERE / f"{key}.html"
    path.write_text(
        PAGE.format(
            css=CSS, supplier=supplier, address=address, phone=phone, trn=trn,
            number=number, date=date, rows="".join(body),
            subtotal=money(subtotal), vat=money(vat), total=money(subtotal + vat),
        )
    )
    return path


if __name__ == "__main__":
    for key in SUPPLIERS:
        print("wrote", render(key).relative_to(pathlib.Path.cwd()))
