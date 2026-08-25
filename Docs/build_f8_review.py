"""Build Docs/f8-review.html, the ground-truth sign-off screen (F8, WP-15).

The eval's answer key was written by an agent, and plan.md §7.1 is blunt about
what that is worth: "Truth no human checked is not truth." This builds the
screen that lets a human check it - each invoice photo beside the key we score
against, with the values that were *decided* rather than copied called out, so
the review is a few dozen judgements instead of 680 comparisons.

Everything on the page is read from the corpus at build time: the truth files,
the images, and the prompt each image was generated from (which is where the
evidence for a derived value lives, e.g. the printed terms line behind a
cash-or-credit call).

    apps/api/.venv/bin/python Docs/build_f8_review.py

The output is a single self-contained file that opens straight from disk. It
references the corpus images by relative path rather than embedding them (they
total 36 MB), so it must stay in Docs/ next to eval/.
"""

import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "apps" / "api" / "src"))
sys.path.insert(0, str(REPO))

from faida_api.extraction.schema import ExtractionResult
from faida_api.extraction.validate import CheckStatus, validate_invoice

from eval.printed import read as read_printed_page

GENERATED = REPO / "eval" / "fixtures" / "generated"
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png")
HEADER_FIELDS = (
    "supplier_name",
    "invoice_no",
    "invoice_date",
    "currency",
    "payment_kind",
    "subtotal",
    "tax",
    "total",
)
LINE_FIELDS = ("raw_name", "qty", "unit", "pack_size", "unit_price", "line_total")


def find_image(case_dir: pathlib.Path) -> pathlib.Path | None:
    for suffix in IMAGE_SUFFIXES:
        candidate = case_dir / f"{case_dir.name}{suffix}"
        if candidate.exists():
            return candidate
    return None


def render_value(value: object) -> str:
    """What the key asserts, shown the way a reader can compare it to a page."""
    if value is None:
        return "(empty)"
    return str(getattr(value, "value", value))


def build_case(case_dir: pathlib.Path, image: pathlib.Path) -> dict | None:
    """One invoice: the key, plus which values were decided rather than copied.

    A value is marked for review when the page did not simply hand it over.
    Copying a cell out of a printed column is not a judgement; deciding that a
    column does not exist, or joining two scripts into one name, or reading an
    arrangement off a terms line, is.
    """
    truth = ExtractionResult.model_validate_json((case_dir / "truth.json").read_text())
    if truth.invoice is None:
        return None
    invoice = truth.invoice
    page = read_printed_page(case_dir)
    has_pack_column = page.has_table and page._pack is not None
    has_unit_column = page.has_table and page._unit is not None
    validation = validate_invoice(invoice)

    header = []
    for field in HEADER_FIELDS:
        entry = {
            "field": field,
            "value": render_value(getattr(invoice, field)),
            "why": None,
        }
        if field == "payment_kind":
            evidence = (
                f'the page prints "{page.terms}"'
                if page.terms
                else "the page prints no terms line"
            )
            entry["why"] = (
                f"read as {render_value(invoice.payment_kind)} because {evidence}"
            )
        header.append(entry)

    lines = []
    for index, line in enumerate(invoice.lines):
        check = validation.lines[index]
        fields = []
        for field in LINE_FIELDS:
            entry = {
                "field": field,
                "value": render_value(getattr(line, field)),
                "why": None,
            }
            if field == "pack_size":
                if has_pack_column:
                    entry["why"] = "copied from the printed Pack size column"
                elif line.pack_size:
                    entry["why"] = (
                        "no pack-size column on this page; taken from inside the item name"
                    )
                else:
                    entry["why"] = "no pack size printed anywhere on this row"
            elif field == "unit" and not has_unit_column:
                entry["why"] = (
                    "this page prints no unit column at all, so the key records none"
                )
            elif field == "raw_name" and any(ord(ch) > 1500 for ch in line.raw_name):
                entry["why"] = (
                    "the page prints two scripts; both are recorded as one name"
                )
            fields.append(entry)
        arithmetic = None
        if (
            line.qty is not None
            and line.unit_price is not None
            and line.line_total is not None
        ):
            ok = check.arith is CheckStatus.PASSED
            arithmetic = f"{line.qty} x {line.unit_price} = {line.line_total}" + (
                " ok" if ok else " MISMATCH"
            )
        lines.append({"index": index, "fields": fields, "arithmetic": arithmetic})

    document = validation.document
    return {
        "id": case_dir.name,
        "image": f"../{image.relative_to(REPO).as_posix()}",
        "header": header,
        "lines": lines,
        "reconciled": document.arith is CheckStatus.PASSED,
        "treatment": document.tax_treatment.value if document.tax_treatment else None,
        "hasPackColumn": has_pack_column,
        "hasUnitColumn": has_unit_column,
        "terms": page.terms,
    }


def main() -> int:
    cases = []
    for case_dir in sorted(d for d in GENERATED.iterdir() if d.is_dir()):
        if not (case_dir / "truth.json").exists():
            continue
        image = find_image(case_dir)
        if image is None:
            continue  # nothing to check the key against; see the F8 plan page
        built = build_case(case_dir, image)
        if built is not None:
            cases.append(built)

    to_review = sum(
        1
        for c in cases
        for group in ([c["header"]] + [line["fields"] for line in c["lines"]])
        for entry in group
        if entry["why"]
    )
    payload = json.dumps(cases, ensure_ascii=False).replace("</", "<\\/")
    out = REPO / "Docs" / "f8-review.html"
    out.write_text(
        PAGE.replace("__DATA__", payload).replace("__TO_REVIEW__", str(to_review))
    )
    print(f"wrote {out} ({len(cases)} invoices, {to_review} values marked for review)")
    return 0


PAGE = """<title>Ground Truth Sign-off</title>
<style>
:root {
  --bg:#fbf8f3; --panel:#fff; --ink:#1c1a17; --muted:#6b6459; --line:#e5ddd0;
  --accent:#8a6a2f; --accent-soft:#f5edda; --code:#f7f3ec;
  --judge:#c08411; --judge-soft:#faf0d9; --ok:#1d7f57; --ok-soft:#e6f2ec;
  --bad:#a33a2a; --bad-soft:#fbeae7;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg:#16150f; --panel:#1e1c16; --ink:#efe9dd; --muted:#a49b8a; --line:#332f25;
    --accent:#d9b264; --accent-soft:#2a2418; --code:#141210;
    --judge:#b3852f; --judge-soft:#2a2418; --ok:#3f9c70; --ok-soft:#1a2a22;
    --bad:#e08a78; --bad-soft:#2e1c18;
  }
}
:root[data-theme="dark"] {
  --bg:#16150f; --panel:#1e1c16; --ink:#efe9dd; --muted:#a49b8a; --line:#332f25;
  --accent:#d9b264; --accent-soft:#2a2418; --code:#141210;
  --judge:#b3852f; --judge-soft:#2a2418; --ok:#3f9c70; --ok-soft:#1a2a22;
  --bad:#e08a78; --bad-soft:#2e1c18;
}
* { box-sizing:border-box; }
body {
  background:var(--bg); color:var(--ink); margin:0;
  font:15px/1.6 ui-sans-serif,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
}
.topbar {
  position:sticky; top:0; z-index:20; background:var(--panel);
  border-bottom:1px solid var(--line); padding:10px 20px;
  display:flex; align-items:center; gap:16px; flex-wrap:wrap;
}
.topbar h1 { font-size:1rem; margin:0; white-space:nowrap; }
.progress { flex:1; min-width:160px; height:8px; background:var(--code);
  border-radius:99px; overflow:hidden; border:1px solid var(--line); }
.progress i { display:block; height:100%; background:var(--ok); width:0%; transition:width .2s; }
.count { font-size:.82rem; color:var(--muted); font-variant-numeric:tabular-nums;
  white-space:nowrap; }
button {
  font:inherit; font-size:.85rem; padding:6px 13px; border-radius:7px;
  border:1px solid var(--line); background:var(--panel); color:var(--ink); cursor:pointer;
}
button:hover { border-color:var(--accent); }
button:disabled { opacity:.4; cursor:default; }
button.primary { background:var(--accent); border-color:var(--accent); color:#fff; font-weight:600; }
button.ok { background:var(--ok); border-color:var(--ok); color:#fff; font-weight:600; }
input[type=text] {
  font:inherit; font-size:.85rem; padding:5px 9px; border-radius:6px;
  border:1px solid var(--line); background:var(--bg); color:var(--ink);
}
.wrap { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:0; }
.photo {
  position:sticky; top:49px; height:calc(100vh - 49px); overflow:auto;
  background:var(--code); border-right:1px solid var(--line); padding:14px;
}
.photo img { width:100%; display:block; border-radius:6px; cursor:zoom-in;
  box-shadow:0 1px 4px rgba(0,0,0,.12); }
.photo img.zoom { width:auto; max-width:none; cursor:zoom-out; }
.photo .hint { font-size:.75rem; color:var(--muted); margin:0 0 9px; }
.fields { padding:18px 22px 120px; }
.caseid { display:flex; align-items:baseline; gap:10px; margin:0 0 4px; }
.caseid h2 { font-size:1.15rem; margin:0; }
.caseid .of { color:var(--muted); font-size:.82rem; }
.note { color:var(--muted); font-size:.82rem; margin:0 0 16px; }
.group { font-size:.7rem; text-transform:uppercase; letter-spacing:.06em;
  color:var(--muted); font-weight:700; margin:20px 0 5px; }
.row {
  display:flex; align-items:flex-start; gap:12px; padding:6px 9px;
  border-radius:6px; border:1px solid transparent;
}
.row .lbl { font:12px/1.7 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  color:var(--muted); flex:0 0 108px; }
.row .val { flex:1; word-break:break-word; }
.row.copied { color:var(--muted); }
.row.review { background:var(--judge-soft); border-color:var(--judge); cursor:pointer; }
.row.review .lbl { color:var(--judge); }
.row.review .val { font-weight:600; }
.row.flagged { background:var(--bad-soft); border-color:var(--bad); }
.row.flagged .lbl { color:var(--bad); }
.tag { font-size:.66rem; text-transform:uppercase; letter-spacing:.05em;
  font-weight:700; color:var(--judge); white-space:nowrap; padding-top:3px; }
.row.flagged .tag { color:var(--bad); }
.why { font-size:.78rem; color:var(--muted); font-weight:400; margin-top:2px; }
.fix { margin:6px 0 2px 120px; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
.fix input { min-width:220px; }
.fix .lead { font-size:.78rem; color:var(--bad); font-weight:600; }
.arith { font:11px/1.6 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  color:var(--muted); margin:1px 0 8px 120px; }
.linehead { font-size:.72rem; font-weight:700; color:var(--muted);
  margin:14px 0 3px; letter-spacing:.04em; }
.verdict {
  position:fixed; bottom:0; right:0; width:50%; background:var(--panel);
  border-top:1px solid var(--line); padding:12px 22px;
  display:flex; gap:10px; align-items:center; flex-wrap:wrap; z-index:15;
}
.verdict .state { flex:1; font-size:.83rem; color:var(--muted); min-width:130px; }
.verdict .state.done { color:var(--ok); font-weight:600; }
.verdict .state.fixed { color:var(--bad); font-weight:600; }
.done-panel { padding:40px 22px; max-width:760px; margin:0 auto; }
.done-panel h2 { font-size:1.3rem; }
textarea {
  width:100%; height:230px; font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  background:var(--code); color:var(--ink); border:1px solid var(--line);
  border-radius:8px; padding:12px; resize:vertical;
}
.hidden { display:none !important; }
@media (max-width:820px) {
  .wrap { grid-template-columns:1fr; }
  .photo { position:static; height:auto; border-right:0; border-bottom:1px solid var(--line); }
  .verdict { width:100%; }
}
</style>

<div class="topbar">
  <h1>Ground truth sign-off</h1>
  <div class="progress"><i id="bar"></i></div>
  <span class="count" id="count"></span>
  <input type="text" id="reviewer" placeholder="your name" style="width:130px">
  <button id="prev">Prev</button>
  <button id="next">Next</button>
  <button id="finish" class="primary">Finish</button>
</div>

<div class="wrap" id="review">
  <div class="photo">
    <p class="hint">Click the photo to zoom. It scrolls on its own.</p>
    <img id="img" alt="invoice">
  </div>
  <div class="fields">
    <div class="caseid"><h2 id="cid"></h2><span class="of" id="of"></span></div>
    <p class="note" id="cnote"></p>
    <div id="body"></div>
  </div>
</div>

<div class="verdict" id="verdict">
  <span class="state" id="state">Not reviewed yet</span>
  <button class="ok" id="allgood">Key is correct</button>
  <button id="clearflags" class="hidden">Clear the flags</button>
  <button id="skip">Skip for now</button>
</div>

<div class="done-panel hidden" id="donepanel">
  <h2>Sign-off result</h2>
  <p id="summary"></p>
  <p class="note">Paste this back into the session. It records who checked what, which values
  were wrong, and what they should be. Nothing is sent anywhere by this page.</p>
  <textarea id="out" readonly></textarea>
  <p><button class="primary" id="copy">Copy to clipboard</button>
     <button id="back">Back to review</button></p>
</div>

<script>
const CASES = __DATA__;
const TO_REVIEW = __TO_REVIEW__;
const KEY = "faida-f8-signoff";
let state = {};
let at = 0;

try { state = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { state = {}; }
function save() { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} }
const NAME_KEY = KEY + "-reviewer";
const nameBox = document.getElementById("reviewer");
try { nameBox.value = localStorage.getItem(NAME_KEY) || ""; } catch (e) {}
nameBox.addEventListener("input", () => {
  try { localStorage.setItem(NAME_KEY, nameBox.value); } catch (e) {}
});

function caseState(id) {
  if (!state[id]) state[id] = { verdict: null, flags: {} };
  return state[id];
}

function reviewedCount() {
  return CASES.filter(c => state[c.id] && state[c.id].verdict).length;
}

function renderRow(entry, path, cs) {
  const flagged = cs.flags[path];
  const cls = entry.why ? (flagged ? "row review flagged" : "row review") : "row copied";
  const tag = entry.why ? `<span class="tag">${flagged ? "wrong" : "check"}</span>` : "";
  const why = entry.why ? `<div class="why">${entry.why}</div>` : "";
  const fix = flagged
    ? `<div class="fix"><span class="lead">should be</span>
       <input type="text" data-fix="${path}" value="${(flagged.should_be || "").replace(/"/g, "&quot;")}"
        placeholder="what the invoice actually says"></div>`
    : "";
  return `<div class="${cls}" data-path="${entry.why ? path : ""}">
      <span class="lbl">${entry.field}</span>
      <span class="val">${entry.value}${why}</span>${tag}
    </div>${fix}`;
}

function render() {
  const c = CASES[at];
  const cs = caseState(c.id);
  document.getElementById("img").src = c.image;
  document.getElementById("img").classList.remove("zoom");
  document.getElementById("cid").textContent = c.id;
  document.getElementById("of").textContent = `invoice ${at + 1} of ${CASES.length}`;
  const bits = [];
  bits.push(c.reconciled ? "every line and the totals reconcile" : "does NOT reconcile");
  if (c.treatment) bits.push(`VAT ${c.treatment}`);
  bits.push(c.hasPackColumn ? "has a printed pack-size column" : "no pack-size column");
  bits.push(c.hasUnitColumn ? "has a printed unit column" : "no unit column");
  document.getElementById("cnote").textContent =
    bits.join(" \\u00b7 ") + ". Gold rows were decided rather than copied: click one if it is wrong.";

  let out = '<div class="group">Invoice header</div>';
  c.header.forEach((e, i) => { out += renderRow(e, `header.${e.field}`, cs); });
  c.lines.forEach(line => {
    out += `<div class="linehead">Line ${line.index + 1}</div>`;
    line.fields.forEach(e => { out += renderRow(e, `line.${line.index}.${e.field}`, cs); });
    if (line.arithmetic) out += `<div class="arith">${line.arithmetic}</div>`;
  });
  document.getElementById("body").innerHTML = out;

  const flagCount = Object.keys(cs.flags).length;
  const st = document.getElementById("state");
  st.className = "state";
  if (cs.verdict === "ok") { st.textContent = "Marked correct"; st.classList.add("done"); }
  else if (cs.verdict === "corrections") {
    st.textContent = `${flagCount} value${flagCount === 1 ? "" : "s"} flagged as wrong`;
    st.classList.add("fixed");
  } else st.textContent = "Not reviewed yet";

  // The confirm button must never discard a correction that was just typed:
  // once anything is flagged it saves the corrections instead of overwriting
  // them with "all correct".
  const confirm = document.getElementById("allgood");
  confirm.textContent = flagCount ? "Save corrections and continue" : "Key is correct";
  confirm.classList.toggle("ok", !flagCount);
  confirm.classList.toggle("primary", flagCount > 0);
  document.getElementById("clearflags").classList.toggle("hidden", !flagCount);

  document.getElementById("count").textContent =
    `${reviewedCount()}/${CASES.length} reviewed \\u00b7 ${TO_REVIEW} values marked for review`;
  document.getElementById("bar").style.width = (reviewedCount() / CASES.length * 100) + "%";
  document.getElementById("prev").disabled = at === 0;
  document.getElementById("next").disabled = at === CASES.length - 1;
}

document.getElementById("body").addEventListener("click", ev => {
  const row = ev.target.closest(".row.review");
  if (!row || !row.dataset.path) return;
  const cs = caseState(CASES[at].id);
  const path = row.dataset.path;
  if (cs.flags[path]) delete cs.flags[path];
  else {
    const value = row.querySelector(".val").childNodes[0].textContent.trim();
    cs.flags[path] = { was: value, should_be: "" };
    cs.verdict = "corrections";
  }
  if (!Object.keys(cs.flags).length && cs.verdict === "corrections") cs.verdict = null;
  save(); render();
});

document.getElementById("body").addEventListener("input", ev => {
  const path = ev.target.dataset.fix;
  if (!path) return;
  const cs = caseState(CASES[at].id);
  if (cs.flags[path]) { cs.flags[path].should_be = ev.target.value; save(); }
});

document.getElementById("img").addEventListener("click", ev => ev.target.classList.toggle("zoom"));
document.getElementById("prev").onclick = () => { if (at > 0) { at--; render(); window.scrollTo(0, 0); } };
document.getElementById("next").onclick = () => {
  if (at < CASES.length - 1) { at++; render(); window.scrollTo(0, 0); }
};
document.getElementById("allgood").onclick = () => {
  const cs = caseState(CASES[at].id);
  cs.verdict = Object.keys(cs.flags).length ? "corrections" : "ok";
  save();
  if (at < CASES.length - 1) { at++; window.scrollTo(0, 0); }
  render();
};
document.getElementById("clearflags").onclick = () => {
  const cs = caseState(CASES[at].id);
  cs.flags = {}; cs.verdict = null; save(); render();
};
document.getElementById("skip").onclick = () => {
  if (at < CASES.length - 1) { at++; render(); window.scrollTo(0, 0); }
};

document.getElementById("finish").onclick = () => {
  const reviewer = document.getElementById("reviewer").value.trim();
  const result = {
    task: "F8 ground-truth sign-off",
    reviewer: reviewer || "(unnamed)",
    reviewed_at: new Date().toISOString(),
    corpus: "eval/fixtures/generated",
    cases: {}
  };
  CASES.forEach(c => {
    const cs = state[c.id] || { verdict: null, flags: {} };
    result.cases[c.id] = {
      verdict: cs.verdict || "not_reviewed",
      corrections: Object.entries(cs.flags).map(([path, f]) =>
        ({ field: path, key_says: f.was, should_be: f.should_be }))
    };
  });
  const wrong = Object.values(result.cases).reduce((n, c) => n + c.corrections.length, 0);
  const done = Object.values(result.cases).filter(c => c.verdict !== "not_reviewed").length;
  document.getElementById("summary").textContent =
    `${done} of ${CASES.length} invoices reviewed, ${wrong} value${wrong === 1 ? "" : "s"} flagged as wrong.`
    + (done < CASES.length ? " Some invoices have not been looked at yet." : "");
  document.getElementById("out").value = JSON.stringify(result, null, 2);
  document.getElementById("review").classList.add("hidden");
  document.getElementById("verdict").classList.add("hidden");
  document.getElementById("donepanel").classList.remove("hidden");
};
document.getElementById("back").onclick = () => {
  document.getElementById("donepanel").classList.add("hidden");
  document.getElementById("review").classList.remove("hidden");
  document.getElementById("verdict").classList.remove("hidden");
  render();
};
document.getElementById("copy").onclick = () => {
  const box = document.getElementById("out");
  box.select();
  // navigator.clipboard needs a secure context, which file:// is not in every
  // browser; the selection above is the fallback that always works.
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(box.value).then(
      () => { document.getElementById("copy").textContent = "Copied"; },
      () => { document.execCommand("copy"); });
  } else {
    try { document.execCommand("copy"); document.getElementById("copy").textContent = "Copied"; }
    catch (e) { document.getElementById("copy").textContent = "Select all and copy"; }
  }
};

render();
</script>
"""


if __name__ == "__main__":
    raise SystemExit(main())
