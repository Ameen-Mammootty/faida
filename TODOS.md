# TODOS

Deferred work with enough context to pick up cold.
Added by `/plan-eng-review` on 2026-08-29 (branch `worktree-eval-phase2`).

## Extraction & matching

### A handwritten margin note gets folded into an item name and splits the catalog

**What:** On EDGE-01 the model returns line 6's `raw_name` as
`"Avocado Credit: one box returned, soft fruit"` instead of `"Avocado"`.
The page prints `Avocado` in the description cell; the rest is a separate handwritten margin
note on a credit row.

**Why:** Measured in 3 of 5 live Gemini 3 Flash runs on 2026-08-29, and the consequence is verified:

```
snap_item('Avocado')                                      -> item 1 (Avocado)
snap_item('Avocado Credit: one box returned, soft fruit')  -> None      (SNAP_THRESHOLD = 0.8)
```

A snap miss means `confirm` mints a **second** "Avocado" catalog row.
That is the same catalog-splitting, price-alert-silencing failure WP-29 closed for bilingual
names on 2026-08-29, arriving through a different door: an annotation rather than a second script.
It matters more once M5 starts mapping catalog rows to raw materials, because a split catalog
corrupts the cost of every menu item built on it.

**Context:** `raw_name` scored 99-100% across the five runs, so the eval barely registers this -
the damage is downstream in `matching.py`, not in the score.
Credit and return lines are where it shows up, because that is where people write in the margin.
Start from WP-29's shape: a deterministic fix in `matching.py` alone, with extraction, the prompt,
the schema and the F8 ground truth untouched.
The hard part is deciding when trailing prose is an annotation rather than part of a real name,
without truncating legitimately long supplier item names.
A prompt rule is the wrong layer - plan.md §5, "accuracy is a pipeline property, not a prompt property".

**Effort:** M
**Priority:** P2
**Depends on:** None. Coordinate with whoever owns `matching.py` (the M5 terminal is adjacent).

### Supplier matching re-parses the whole catalog on every invoice line

**What:** `snap_item` (`matching.py:172-190`) computes `_pack_tokens` twice for every catalog item,
and `pipeline.py:205` calls `snap_item` once per invoice line, so supplier matching is
O(lines x catalog) regex evaluations per invoice against a pattern built from ~120 unit spellings.

**Why:** PH-01 has 34 lines.
At a 200-item catalog that is roughly 13,600 regex passes per invoice; at 2,000 items, 136,000.
Today it is milliseconds and invisible inside a ~9.5 s model call, so this is a characterisation,
not a complaint.

**Context:** The catalog self-builds on confirm, so item count grows with every new supplier item
forever, per tenant.
This becomes noticeable at multi-branch chain scale (the 75-branch chain in the design doc), not at
demo scale.
The fix is obvious when it is needed: hoist the per-item pack tokens out of the per-line loop and
compute them once per invoice, roughly a 34x reduction on the corpus's largest invoice.
**Measure before fixing** - plan.md §2 warns against optimising ahead of proven need, and the point
of recording it is so a future slow-confirm investigation starts here instead of blaming model latency.

**Effort:** S
**Priority:** P4
**Depends on:** None. Should be measured before it is fixed.

### The eval marks TH-01's subtotal wrong when the model reads the other legitimate row

**Corrected 2026-08-29.** An earlier version of this entry called this a silent wrong number that
poisons price memory, and recommended a stricter C4 cross-check. **That was wrong on both counts,
disproven by the trace below.** It is an eval-strictness artifact with no product consequence.

**What:** On TH-01 the model sometimes returns `subtotal` as `673.00` (the printed "Net of VAT"
row) instead of `706.65` (the printed "Subtotal (VAT inclusive)" row). Observed once in ten live
Gemini 3 Flash runs on 2026-08-29. Ground truth records 706.65, so the eval scores it wrong and
`header subtotal` reads 90% on that run.

**Why it does not matter to the product.** Traced through the shipped validator and the shipped
net-price maths, both readings side by side:

```
CORRECT (truth)  subtotal=706.65        RUN 3 (misread)  subtotal=673.00
   tax_treatment  = inclusive              tax_treatment  = inclusive
   arith          = passed                 arith          = passed
   subtotal_check = passed                 subtotal_check = passed
   doc status     = green                  doc status     = green
   net factor     = 0.95238095...          net factor     = 0.95238095...
   line 1 net unit price stored            line 1 net unit price stored
                  = 32.000                                = 32.000
```

Nothing downstream reads the subtotal. `validate.py:174` derives the tax treatment anchored on the
line sum, "never on the printed subtotal", and `db.py:533` builds the net-price factor from
`tax_treatment, tax, total` alone. The price baseline `confirm` writes is byte-identical either
way, so this cannot poison price history.

**And it is not silent.** `_check_subtotal` does cross-check the subtotal and does feed the
document status. It passes 673.00 deliberately, not accidentally:

```
subtotal                                       subtotal_check   doc status
706.65  the printed 'Subtotal (VAT inclusive)'        passed        green
673.00  the printed 'Net of VAT'                      passed        green
670.00  a genuinely wrong number                      failed        amber
707.00  wrong by 0.35                                 failed        amber
500.00  a badly wrong number                          failed        amber
```

A VAT-inclusive invoice may legitimately print its subtotal as either the gross (equal to the
total) or the net (total - tax), and 673.00 is exactly 706.65 - 33.65. The function's own
docstring says why it accepts both: *"Accepting a legitimate printing matters as much as catching
a wrong one: manufacturing an amber on a correct document spends the sender's attention and
teaches them the ambers are noise."* A genuinely wrong subtotal goes amber, so the §5 gate holds.

**What is actually left, and it is small.** Two options, neither urgent:

1. Teach the eval the same tolerance the validator already has, so `header subtotal` stops
   flickering to 90% for a reading the product treats as correct. This matches the WP-16
   principle that there is one implementation of C4 and the eval scores against it. The argument
   against: an answer key exists to be exact, and loosening it to accept two values sets a
   precedent worth thinking about before applying it more widely.
2. Display fidelity: the review screen would show 673.00 beside a paper whose "Subtotal" row reads
   706.65. Nothing is wrong, but a cafeteria owner comparing screen to paper sees a number that
   is not on the line it is labelled with. Cosmetic, and only if someone complains.

**Do not** build the stricter validator cross-check the earlier version of this entry proposed.
It already exists in more permissive form, on purpose, and tightening it would manufacture ambers
on correct invoices.

**Effort:** S
**Priority:** P4
**Depends on:** None. Option 1 belongs with whoever owns `eval/score.py`.

### Regenerating ground truth would rewrite 14 signed files for serialization reasons alone

**What:** Running `python -m eval.convert_generated` today rewrites 14 of 16 `truth.json` files and
would trip their `SIGNOFF.json` hashes - but the only difference is two schema fields
(`invoice_date_text`, `payment_terms_text`) that were added after the founder signed off, and which
`exclude_none=False` now serializes.

**Why:** Verified on 2026-08-29 by regenerating in memory and diffing: **no printed fact moves.**
All 130 lines across all 15 invoice cases keep their exact `raw_name`, `unit` and `pack_size`.
The risk is that the next person to touch the converter sees 14 changed files, cannot tell a
serialization diff from a truth diff, and either re-signs blindly or abandons a correct change.

**Context:** `convert_generated.py`'s own `--only` docstring already anticipates this
("a serialization-order or schema-field change would trip every SIGNOFF.json hash at once").
The clean resolution is a deliberate one-time regeneration plus a founder re-sign through
`Docs/f8-review.html`, done as its own commit that changes nothing but serialization, so the diff
is reviewable as exactly that. Do not bundle it with a content change.

**Effort:** S
**Priority:** P3
**Depends on:** Founder availability for the F8 re-sign.

## Plan corrections (for the loop-gate lane, which owns plan.md)

### The 2026-08-29 bake-off entry records a false alarm about TH-01's subtotal

**What:** Both the Decision Log row and the Progress Log entry dated 2026-08-29 describe Gemini
3.1 Pro's TH-01 subtotal read as a silent wrong number that would store green. The trace above
disproves it: the value is a legitimate alternative printing, `_check_subtotal` passes it by
design, a genuinely wrong subtotal goes amber, and nothing downstream reads the field.

**Why it matters enough to correct:** it was written up as "the subtotal miss is the finding that
matters" and weighed in the Pro-versus-Flash comparison that preceded a model swap. A false alarm
carrying weight in a shipped-model decision is worth un-recording, and CLAUDE.md is explicit that
when plan.md and the code disagree, the code is right and the plan has the bug.

**The sentence to replace** is `plan.md:894`, in the Progress Log entry beginning
"The Gemini bake-off ran":

> The subtotal miss is the finding that matters: TH-01 prints both "Subtotal (VAT inclusive):
> 706.65" and "Net of VAT: 673.00", and Gemini filled `subtotal` from the net line - a printed
> value from the wrong labeled cell, not an invention - and `subtotal` is the one header money
> field the C4 identities do not cross-check (they anchor on the line sum), so in production this
> would have stored green: a silent wrong number, the exact thing the §5 gate says must never
> happen.

**Suggested replacement:**

> The subtotal miss turned out to be a false alarm, traced 2026-08-29 in the eval-phase2 lane:
> TH-01 prints both "Subtotal (VAT inclusive): 706.65" and "Net of VAT: 673.00", and Gemini filled
> `subtotal` from the net line. Both are legitimate printings of an inclusive invoice's subtotal,
> and `validate._check_subtotal` accepts either on purpose - a genuinely wrong subtotal (670.00,
> 707.00, 500.00 all tested) still goes amber, so the §5 gate holds. Nothing downstream reads the
> field either: the tax treatment is derived from the line sum, never the printed subtotal, and the
> net-price factor is built from `tax_treatment, tax, total`, so the price baseline stored on
> confirm is identical under both readings. The eval scores it wrong only because ground truth
> records one of the two legitimate rows. **The real finding from that bake-off was the pack sizes,
> not the subtotal.**

One knock-on edit in the same pass: the Decision Log row (`plan.md:807`) for the Flash swap says Flash "got right
both cells that tripped Gemini 3.1 Pro (the TH-01 subtotal and the pack sizes embedded in item
names)" - only the pack half was ever a real defect, and Flash was later measured missing the same
subtotal row once in ten runs, so that clause overstates the gap between the two models.

**Effort:** S
**Priority:** P2 (it is a correctness claim in the sequencing document, not code)
**Depends on:** Nothing. Belongs in the same commit as the loop-gate lane's next plan.md update.
