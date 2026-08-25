"""Build Docs/extraction-rules.html from the extraction source.

Every prompt, threshold, marker and unit on that page is read out of the
modules that run in production, so the page cannot quietly disagree with the
code it exists to let someone verify. Re-run it after any change to the
prompts, the C4 constants, the units dictionary or the payment rules:

    apps/api/.venv/bin/python Docs/build_extraction_rules.py
"""

import html
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "apps" / "api" / "src"))

from faida_api import matching
from faida_api.extraction import constants, currency, normalize, payment, units
from faida_api.extraction.anthropic_provider import MAX_TOKENS, MODEL_ID
from faida_api.extraction.prompts import (
    EXTRACT_PROMPT,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_repair_prompt,
)
from faida_api.extraction.schema import ExtractionResult, RepairTarget
from faida_api.replies import REPLY_NOT_INVOICE, REPLY_Z_REPORT

sample_repair = build_repair_prompt(
    [
        RepairTarget(
            line_index=2,
            fields=["qty", "unit_price", "line_total"],
            reason="12 x 4.50 = 54.00, extracted line_total 58.00",
        ),
        RepairTarget(
            line_index=None,
            fields=["subtotal", "tax", "total"],
            reason="lines sum to 834.00; extracted total 858.17 matches neither identity",
        ),
    ]
)

by_dimension = {}
for unit in units.UNITS.values():
    by_dimension.setdefault(unit.dimension.value, []).append(
        {"canonical": unit.canonical, "to_base": str(unit.to_base)}
    )
aliases_by_canonical = {}
for alias, canon in units.ALIASES.items():
    aliases_by_canonical.setdefault(canon, []).append(alias)

payload = {
    "model_id": MODEL_ID,
    "max_tokens": MAX_TOKENS,
    "prompt_version": PROMPT_VERSION,
    "system_prompt": SYSTEM_PROMPT,
    "extract_prompt": EXTRACT_PROMPT,
    "repair_prompt": sample_repair,
    "schema": json.dumps(ExtractionResult.model_json_schema(), indent=2),
    "replies": {"z_report": REPLY_Z_REPORT, "not_invoice": REPLY_NOT_INVOICE},
    "constants": {
        "LINE_TOLERANCE_ABS": str(constants.LINE_TOLERANCE_ABS),
        "LINE_TOLERANCE_PCT": str(constants.LINE_TOLERANCE_PCT),
        "DOC_TOLERANCE_ABS": str(constants.DOC_TOLERANCE_ABS),
        "MAX_REPAIR_ROUNDS": constants.MAX_REPAIR_ROUNDS,
        "PRICE_ALERT_MIN_PCT": str(constants.PRICE_ALERT_MIN_PCT),
        "PRICE_ALERT_MIN_ABS": str(constants.PRICE_ALERT_MIN_ABS),
        "GCC_VAT_RATES": [str(r) for r in constants.GCC_VAT_RATES],
        "SUPPLIER_MATCH_THRESHOLD": matching.SUPPLIER_MATCH_THRESHOLD,
        "SNAP_THRESHOLD": matching.SNAP_THRESHOLD,
    },
    "payment": {
        "cash": list(payment.CASH_MARKERS),
        "credit": list(payment.CREDIT_MARKERS),
    },
    "units_by_dimension": by_dimension,
    "unit_aliases": aliases_by_canonical,
    "placeholders": sorted(p for p in normalize.PLACEHOLDERS if p),
    "currency_aliases": dict(sorted(currency._ALIASES.items())),
}

d = payload
e = html.escape
c = d["constants"]


def pre(text):
    return f'<pre class="src">{e(text)}</pre>'


def chips(values):
    return (
        '<div class="chips">'
        + "".join(f"<span>{e(str(v))}</span>" for v in values)
        + "</div>"
    )


z_reply = d["replies"]["z_report"]
other_reply = d["replies"]["not_invoice"]

units_rows = []
LABELS = {
    "mass": ("Weight", "base unit: gram"),
    "volume": ("Volume", "base unit: millilitre"),
    "count": ("Count", "base unit: piece"),
    "packaging": ("Containers", "compared only with their own kind"),
}
for dim in ("mass", "volume", "count", "packaging"):
    entries = d["units_by_dimension"].get(dim, [])
    label, note = LABELS[dim]
    rows = []
    for entry in sorted(entries, key=lambda x: x["canonical"]):
        canon = entry["canonical"]
        alias_list = sorted(d["unit_aliases"].get(canon, []))
        rows.append(
            f"<tr><td><code>{e(canon)}</code></td>"
            f'<td class="num">{e(entry["to_base"])}</td>'
            f"<td>{chips(alias_list) if alias_list else '<span class=none>none</span>'}</td></tr>"
        )
    units_rows.append(
        f"<h4>{e(label)} <span class='note'>{e(note)}</span></h4>"
        "<table class=grid><thead><tr><th>canonical</th><th>= base</th>"
        "<th>also accepted as</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )

# Grouped by the code they resolve to: 44 one-line rows told the reader
# nothing that four grouped ones do not.
by_code = {}
for alias, code in d["currency_aliases"].items():
    by_code.setdefault(code, []).append(alias)
currency_rows = "".join(
    f"<tr><td><code>{e(code)}</code></td><td>{chips(sorted(aliases))}</td></tr>"
    for code, aliases in sorted(by_code.items())
)

HTML = f"""<title>Faida Extraction Rules</title>
<style>
:root {{
  --bg:#fbf8f3; --panel:#fff; --ink:#1c1a17; --muted:#6b6459; --line:#e5ddd0;
  --accent:#8a6a2f; --accent-soft:#f5edda; --green:#2f6b४6; --code:#f7f3ec;
  --green:#2e6b45; --amber:#9a6a12; --red:#a33a2a;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg:#16150f; --panel:#1e1c16; --ink:#efe9dd; --muted:#a49b8a; --line:#332f25;
    --accent:#d9b264; --accent-soft:#2a2418; --code:#141210;
    --green:#7fc79a; --amber:#e0b45e; --red:#e08a78;
  }}
}}
:root[data-theme="dark"] {{
  --bg:#16150f; --panel:#1e1c16; --ink:#efe9dd; --muted:#a49b8a; --line:#332f25;
  --accent:#d9b264; --accent-soft:#2a2418; --code:#141210;
  --green:#7fc79a; --amber:#e0b45e; --red:#e08a78;
}}
* {{ box-sizing:border-box; }}
body {{
  background:var(--bg); color:var(--ink); margin:0;
  font:16px/1.6 ui-sans-serif,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
}}
.wrap {{ max-width:1000px; margin:0 auto; padding:40px 22px 96px; }}
header.top {{ border-bottom:2px solid var(--accent); padding-bottom:22px; margin-bottom:8px; }}
h1 {{ font-size:1.85rem; margin:0 0 6px; letter-spacing:-.02em; }}
.sub {{ color:var(--muted); margin:0; }}
.meta {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:16px; }}
.meta span {{
  background:var(--accent-soft); color:var(--accent); border:1px solid var(--line);
  padding:3px 10px; border-radius:999px; font-size:.78rem; font-weight:600;
}}
section {{ margin-top:44px; }}
h2 {{
  font-size:1.18rem; margin:0 0 4px; padding-bottom:8px; border-bottom:1px solid var(--line);
  display:flex; align-items:baseline; gap:10px;
}}
h2 .n {{ color:var(--accent); font-variant-numeric:tabular-nums; font-size:.9rem; }}
h3 {{ font-size:1rem; margin:26px 0 8px; }}
h4 {{ font-size:.9rem; margin:20px 0 8px; text-transform:uppercase; letter-spacing:.05em;
     color:var(--muted); }}
h4 .note {{ text-transform:none; letter-spacing:0; font-weight:400; }}
p {{ margin:10px 0; }}
.lede {{ color:var(--muted); margin:10px 0 0; }}
.card {{
  background:var(--panel); border:1px solid var(--line); border-radius:10px;
  padding:18px 20px; margin:16px 0;
}}
.src {{
  background:var(--code); border:1px solid var(--line); border-radius:8px;
  padding:14px 16px; overflow-x:auto; white-space:pre-wrap; word-break:break-word;
  font:13px/1.65 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; margin:0;
}}
.scroll {{ overflow-x:auto; }}
.scroll .src {{ white-space:pre; word-break:normal; max-height:460px; overflow:auto; }}
code {{
  background:var(--code); border:1px solid var(--line); border-radius:4px;
  padding:1px 5px; font:13px/1.4 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}}
table.grid {{ width:100%; border-collapse:collapse; font-size:.9rem; }}
table.grid th {{
  text-align:left; font-size:.75rem; text-transform:uppercase; letter-spacing:.05em;
  color:var(--muted); border-bottom:1px solid var(--line); padding:6px 10px 6px 0; font-weight:600;
}}
table.grid td {{ border-bottom:1px solid var(--line); padding:8px 10px 8px 0; vertical-align:top; }}
table.grid td.num {{ font-variant-numeric:tabular-nums; color:var(--muted); white-space:nowrap; }}
.chips {{ display:flex; flex-wrap:wrap; gap:5px; }}
.chips span {{
  background:var(--code); border:1px solid var(--line); border-radius:5px;
  padding:1px 7px; font:12px/1.6 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}}
.none {{ color:var(--muted); font-size:.85rem; }}
table.tight {{ margin:14px 0 4px; }}
table.tight td {{ font-size:.87rem; }}
.sub2 {{ color:var(--muted); font-size:.8rem; margin-top:3px; }}
td.quote {{ font-style:italic; }}
.rule {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:0;
         border:1px solid var(--line); border-radius:10px; overflow:hidden; margin:14px 0; }}
.rule > div {{ padding:16px 18px; }}
.rule .what {{ background:var(--panel); border-right:1px solid var(--line); }}
.rule .why {{ background:transparent; color:var(--muted); font-size:.92rem; }}
.rule h5 {{ margin:0 0 8px; font-size:.95rem; color:var(--ink); }}
@media (max-width:720px) {{
  .rule {{ grid-template-columns:1fr; }}
  .rule .what {{ border-right:0; border-bottom:1px solid var(--line); }}
}}
.formula {{
  font:14px/1.9 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  background:var(--code); border:1px solid var(--line); border-left:3px solid var(--accent);
  border-radius:6px; padding:12px 16px; margin:10px 0; overflow-x:auto;
}}
.flag {{ font-weight:600; }}
.flag.g {{ color:var(--green); }} .flag.a {{ color:var(--amber); }}
.callout {{
  border-left:3px solid var(--accent); background:var(--accent-soft);
  padding:14px 18px; border-radius:0 8px 8px 0; margin:16px 0;
}}
.callout strong {{ color:var(--accent); }}
ol.steps {{ counter-reset:s; list-style:none; padding:0; margin:18px 0; }}
ol.steps li {{ counter-increment:s; position:relative; padding:0 0 0 44px; margin:0 0 18px; }}
ol.steps li::before {{
  content:counter(s); position:absolute; left:0; top:0; width:28px; height:28px;
  border-radius:50%; background:var(--accent-soft); color:var(--accent);
  border:1px solid var(--line); display:grid; place-items:center;
  font-size:.82rem; font-weight:700;
}}
ol.steps b {{ display:block; }}
ol.steps .ai {{ color:var(--amber); }} ol.steps .det {{ color:var(--green); }}
footer {{ margin-top:56px; padding-top:18px; border-top:1px solid var(--line);
          color:var(--muted); font-size:.85rem; }}
</style>

<div class="wrap">
<header class="top">
  <h1>What we ask the model, and what we check ourselves</h1>
  <p class="sub">Every prompt and every deterministic rule in the extraction pipeline, generated
  from the source so this page cannot disagree with the code.</p>
  <div class="meta">
    <span>{e(d["model_id"])}</span>
    <span>prompt {e(d["prompt_version"])}</span>
    <span>max {d["max_tokens"]:,} tokens</span>
    <span>pre-commit review</span>
  </div>
</header>

<section>
  <h2><span class="n">00</span> The division of labour</h2>
  <p class="lede">The model reads. It never decides. Everything that turns a reading into a
  number we act on is deterministic code you can read below.</p>
  <ol class="steps">
    <li><b class="ai">The model reads the photo</b> One call decides what the photo is and, only
      if it is an invoice, copies out every printed value. It is told to copy exactly and never
      to compute.
      <table class="grid tight"><thead><tr><th>it decides</th><th>what happens</th>
      <th>what the sender gets back</th></tr></thead><tbody>
        <tr><td><code>invoice</code><div class="sub2">a supplier invoice or delivery note
          charging you for goods</div></td>
          <td>read in full, checked, saved as a draft</td>
          <td>the parsed summary, any price alert, and "Reply OK to confirm"</td></tr>
        <tr><td><code>z_report</code><div class="sub2">a till or POS end-of-day sales
          summary</div></td>
          <td>nothing extracted, photo still stored</td>
          <td class="quote">{e(z_reply)}</td></tr>
        <tr><td><code>other</code><div class="sub2">memes, chat screenshots, anything
          else</div></td>
          <td>nothing extracted, photo stored and marked failed</td>
          <td class="quote">{e(other_reply)}</td></tr>
      </tbody></table>
      <p class="lede">Only an invoice is read. For the other two the model returns the verdict
      alone, so we never pay to extract line items off a meme. It is deliberately one call and
      not a cheap classifier followed by an extraction: a separate first call would add a round
      trip of cost and latency to every genuine invoice in order to catch the occasional one that
      is not.</p></li>
    <li><b class="det">We derive the printed facts</b> The currency word becomes an ISO code,
      the payment terms become cash or credit, a printed dash becomes an absence.</li>
    <li><b class="det">We check the arithmetic</b> Every line, then the invoice, against fixed
      tolerances. Nothing is trusted because the model sounded confident.</li>
    <li><b class="ai">One scoped re-read, at most</b> Only the exact cells that failed, once.
      Never a re-extraction of the whole document.</li>
    <li><b class="det">We match the supplier and snap the items</b> Fuzzy name match with a hard
      pack-size veto, then the price comparison that produces an alert.</li>
    <li><b class="det">We colour the fields</b> Green only when the arithmetic passed. Anything
      else is amber and asks a question.</li>
  </ol>
  <div class="callout">
    <strong>The one invariant:</strong> a wrong value can never come out green. When a check
    cannot be completed, the field goes amber and asks. Silence is not an option and neither is
    a confident guess.
  </div>
</section>

<section>
  <h2><span class="n">01</span> The system prompt</h2>
  <p class="lede">Sent with every extraction call, verbatim below.</p>
  {pre(d["system_prompt"])}
  <h3>The instruction that accompanies the image</h3>
  {pre(d["extract_prompt"])}
</section>

<section>
  <h2><span class="n">02</span> The repair prompt</h2>
  <p class="lede">Built only when a check fails, and only for the cells that failed. This is a
  real example with one bad line and a totals block that matched neither identity.</p>
  {pre(d["repair_prompt"])}
  <div class="callout">
    <strong>Capped at {c["MAX_REPAIR_ROUNDS"]} round.</strong> Whatever still fails after it
    stays amber and becomes a question in chat. We never loop the model until it agrees with us.
  </div>
</section>

<section>
  <h2><span class="n">03</span> The arithmetic checks</h2>
  <p class="lede">Deterministic, in exact decimals, never floating point.</p>

  <div class="rule">
    <div class="what">
      <h5>Every line</h5>
      <div class="formula">| qty × unit_price − line_total |<br>&nbsp;&nbsp;≤ max({e(c["LINE_TOLERANCE_ABS"])}, {e(c["LINE_TOLERANCE_PCT"])} × line_total)</div>
    </div>
    <div class="why">Quantity times price has to equal the line amount, allowing
      {e(c["LINE_TOLERANCE_ABS"])} fils or {e(str(float(c["LINE_TOLERANCE_PCT"]) * 100))}% for the
      supplier's own rounding, whichever is larger. A line missing any of the three values cannot
      pass: it goes <span class="flag a">amber</span> rather than being assumed.</div>
  </div>

  <div class="rule">
    <div class="what">
      <h5>The invoice, two ways</h5>
      <div class="formula">A = line sum − discount + rounding<br><br>
      exclusive: | A + tax − total | ≤ {e(c["DOC_TOLERANCE_ABS"])}<br>
      inclusive: | A − total | ≤ {e(c["DOC_TOLERANCE_ABS"])} and tax &gt; 0</div>
    </div>
    <div class="why">GCC invoices come both ways: prices with VAT already inside, or added on
      top. Exactly one identity holds, and that tells us which kind it is. We never take the
      document's word for it, even when it prints one.
      <p><strong>Anchored on the line sum, never the printed subtotal.</strong> An inclusive
      invoice that prints its subtotal as the net figure would otherwise masquerade as exclusive.
      The line sum is the only total we verify independently.</p></div>
  </div>

  <div class="rule">
    <div class="what">
      <h5>Naming the VAT rate</h5>
      {chips([f"{float(r) * 100:g}%" for r in c["GCC_VAT_RATES"]])}
    </div>
    <div class="why">Used to name the rate on an invoice whose arithmetic already worked, as
      confirmation. Never a gate: an invoice at an unlisted rate that still adds up passes, with
      the effective rate derived from its own totals.</div>
  </div>

  <div class="rule">
    <div class="what">
      <h5>Green or amber</h5>
      <p><span class="flag g">Green</span> the arithmetic passed and, where we know the item, the
      price is plausible.</p>
      <p><span class="flag a">Amber</span> everything else, including anything we could not
      check.</p>
    </div>
    <div class="why">Colour never carries the meaning alone: every field also carries an icon or
      a label on the review screen. Amber fields drive one specific question in chat rather than
      a dead end.</div>
  </div>
</section>

<section>
  <h2><span class="n">04</span> Reading the printed form</h2>
  <p class="lede">The model is told to copy exactly as printed, so it does. These rules turn a
  printed value into one we can compute with, without ever changing what it means.</p>

  <h3>Money</h3>
  <div class="rule">
    <div class="what">
      <h5>Accepted and parsed</h5>
      {chips(["AED 332.00", "332.00 AED", "د.إ 45.00", "1,240.50", "(41.70)", "-92.00", "٤٥.٥٠"])}
    </div>
    <div class="why">Currency prefixes, thousands separators, accounting negatives in brackets,
      and Arabic-Indic numerals. A value with no number in it at all is
      <strong>rejected loudly</strong> rather than read as zero, because a silent wrong number is
      the one failure we will not accept.</div>
  </div>

  <h3>A discount is always a magnitude</h3>
  <div class="rule">
    <div class="what">
      <h5>−41.70 is stored as 41.70</h5>
      <div class="formula">A = line sum − discount + rounding</div>
    </div>
    <div class="why">Invoices print a discount as a negative. The identity already subtracts it,
      so a negative would add it back and miss by double, failing a perfectly read invoice into
      amber. Fixed in the schema itself, so no rewording of the prompt can undo it.</div>
  </div>

  <h3>"Nothing here" is an absence</h3>
  <div class="card">{chips(d["placeholders"])}
  <p class="lede">A printed dash in a pack-size column means the row has none. Recorded
  literally, it becomes a pack size of "-" that the catalogue then has to compare against.</p></div>

  <h3>Currency words and signs become ISO codes</h3>
  <table class="grid"><thead><tr><th>stored as</th><th>printed on the invoice as any of</th></tr></thead>
  <tbody>{currency_rows}</tbody></table>
</section>

<section>
  <h2><span class="n">05</span> Cash or credit</h2>
  <p class="lede">This decides which purchases need owner approval, so it is decided by rule.
  The model copies the terms line as printed; the rules below read it.</p>
  <div class="rule">
    <div class="what">
      <h5>Cash, checked first</h5>
      {chips(d["payment"]["cash"])}
    </div>
    <div class="why">Checked before the credit markers on purpose: "cash on delivery" contains a
      word the credit rules also look for, and reading it as a due period would send every COD
      purchase straight past the approval gate.</div>
  </div>
  <div class="rule">
    <div class="what">
      <h5>Credit, a due period in any wording</h5>
      {chips(d["payment"]["credit"])}
    </div>
    <div class="why">"Payment terms: 14 days" is credit even though the page never prints the
      word. That inference used to be forbidden, which is why this field read blank on invoices a
      person reads at a glance.</div>
  </div>
  <div class="callout">
    <strong>Unrecognised stays blank.</strong> Printed terms outrank the model's own reading when
    they disagree. If neither settles it the field stays empty, because guessing "credit" would
    quietly route a cash purchase around the approval gate.
  </div>
</section>

<section>
  <h2><span class="n">06</span> The units dictionary</h2>
  <p class="lede">One dictionary decides what a pack is, for the catalogue and for the accuracy
  exam alike. Read as different packs, the catalogue doubles and a supplier who changed only
  their printing sets off a price alert.</p>
  {"".join(units_rows)}
  <div class="callout">
    <strong>Containers are deliberately not counts.</strong> A carton is not twelve of anything
    until someone says what is in it, so "6 ctn" and "6 pc" never compare equal. Merging them
    would silently combine two real items. A unit we do not recognise is left alone, not guessed.
  </div>
</section>

<section>
  <h2><span class="n">07</span> Matching and price alerts</h2>
  <div class="rule">
    <div class="what">
      <h5>Thresholds</h5>
      <table class="grid"><tbody>
        <tr><td>Supplier name match</td><td class="num">{c["SUPPLIER_MATCH_THRESHOLD"]}</td></tr>
        <tr><td>Item snap</td><td class="num">{c["SNAP_THRESHOLD"]}</td></tr>
        <tr><td>Alert: minimum move</td><td class="num">{e(str(float(c["PRICE_ALERT_MIN_PCT"]) * 100))}%</td></tr>
        <tr><td>Alert: minimum amount</td><td class="num">AED {e(c["PRICE_ALERT_MIN_ABS"])}</td></tr>
      </tbody></table>
    </div>
    <div class="why">Both alert thresholds must be met, so neither a trivial percentage on a big
      number nor a few fils on a cheap one raises a flag. A missed match just means no snapping;
      a wrong match corrupts another supplier's price history, so the bar sits high.
      <p><strong>The baseline only moves on confirmation.</strong> An unconfirmed invoice never
      changes the price we compare against.</p></div>
  </div>
</section>

<section>
  <h2><span class="n">08</span> The exact shape the model must return</h2>
  <p class="lede">Enforced by the API, not by asking nicely. Money crosses as text so nothing
  becomes a floating-point number on the way in.</p>
  <div class="scroll">{pre(d["schema"])}</div>
</section>

<footer>
  Generated from the working tree of <code>apps/api/src/faida_api/extraction/</code> and
  <code>matching.py</code>. Prompt version <code>{e(d["prompt_version"])}</code>,
  model <code>{e(d["model_id"])}</code>. Figures shown are the live constants, not a copy.
</footer>
</div>
"""

out = REPO / "Docs" / "extraction-rules.html"
out.write_text(HTML.replace("#2f6b४6", "#2e6b45"))
print(f"wrote {out} ({len(HTML):,} chars)")
