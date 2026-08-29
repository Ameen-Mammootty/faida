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

### TH-01's subtotal comes off the wrong labelled cell about one run in ten

**What:** On TH-01 the model sometimes returns `subtotal` as `673.00` (the "Net of VAT" line)
instead of `706.65` (the "Subtotal (VAT inclusive)" line). Observed once in ten live Gemini 3
Flash runs on 2026-08-29 (run 3 of the second set of five).

**Why:** This is the failure the Decision Log already named as "the finding that matters" when it
appeared on Gemini 3.1 Pro, and it is now confirmed on the shipped Flash model too, just rarer.
It is a **silent wrong number**: `subtotal` is the one header money field C4's identities do not
cross-check - they anchor on the line sum - so the invoice still reconciles 10/10 and the value
stores green. plan.md §5's gate says a wrong value must be amber, never green.

**Context:** The page genuinely prints both numbers, clearly labelled, so this is a wrong-cell
read rather than an invention, and no amount of prompt wording reliably fixes a cell-selection
slip (§5: accuracy is a pipeline property, not a prompt property).
The candidate fix is a deterministic cross-check rather than a prompt: when `subtotal`, `tax` and
`total` are all present, `subtotal + tax == total` for an exclusive invoice and
`subtotal == total` for an inclusive one, so a subtotal that satisfies neither is amber.
That is a C4 validator change and needs care - it must not fail correct invoices with discounts
or rounding lines, which is exactly what the existing identities already handle.
Not fixed here because it is a validator change in front of the M4 loop gate, and it is unrelated
to the pack_size work this branch carries.

**Effort:** M
**Priority:** P2
**Depends on:** None, but it belongs with whoever owns `extraction/validate.py` and the M4 gate.

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
