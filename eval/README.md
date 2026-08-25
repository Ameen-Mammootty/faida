# eval - invoice extraction harness

Scores extraction output against hand-verified ground truth (plan.md §5).
It imports the pinned contracts from `faida_api` (C3 schema, C4 tolerances), so run everything with `apps/api/.venv/bin/python` from the repo root.

## Layout

```
eval/
  corpus/<id>/image.jpg      one real invoice photo per case dir (never synthetic; WP-15/F6)
  corpus/<id>/truth.json     hand-verified ground truth: exactly a serialized ExtractionResult
  corpus/<id>/recorded.json  recorded provider response for that image (ExtractionResult dump)
  corpus/<id>/usage.json     matching ProviderUsage dump (tokens, latency)
  fixtures/<id>/             3 synthetic CI smoke cases: truth.json, recorded.json,
                             usage.json, expected.json (the case's expected score)
  fixtures/generated/        15 prompt-generated cases across a hazard matrix, of which
                             10 have images and can be scored; the other 5 are ground
                             truth for images nobody has generated yet. SYNTHETIC:
                             development material, no substitute for F6. See its README.
  fixtures/expected_aggregate.json   expected corpus-level score for the fixtures
  score.py                   scoring + aggregation, pure functions
  recorded.py                provider replaying recorded.json/usage.json (the CI provider)
  live.py                    real provider runs: the pipeline's own layers 1-3 (WP-16)
  printed.py                 what a generated case actually prints, read from its prompt
  run.py                     python -m eval.run
  results/<date>.json        run outputs, gitignored
  tests/                     scorer, live-runner and printed-page unit tests
```

A `truth.json` is exactly a serialized `ExtractionResult` from the pinned schema (`faida_api.extraction.schema`): `classification` plus an `invoice` object with supplier block, invoice_no, invoice_date, currency, payment_kind, lines, subtotal, tax, total.
Money values are strings ("18.50") so they parse as exact Decimals; dates are ISO ("2026-08-10").

## Commands

```bash
apps/api/.venv/bin/python -m eval.run             # score eval/corpus against recorded responses
apps/api/.venv/bin/python -m eval.run --smoke     # CI smoke: fixtures vs their expected scores
apps/api/.venv/bin/python -m pytest eval/tests -q # scorer, live-runner, printed-page tests
apps/api/.venv/bin/python -m eval.convert_generated  # generated fixtures -> C3 truth.json

# WP-16 accuracy loop, on the phase-1 (generated) corpus. Spends money.
export ANTHROPIC_API_KEY=...
apps/api/.venv/bin/python -m eval.run --live --corpus eval/fixtures/generated --record
apps/api/.venv/bin/python -m eval.run --corpus eval/fixtures/generated   # re-score, free
apps/api/.venv/bin/python -m eval.run --live --only EDGE-01 --corpus eval/fixtures/generated
```

`--live` calls the real provider and runs the layers the product runs, in the product's order,
through the product's modules: extract, the pipeline's currency normalization, `validate_invoice`,
one scoped `repair_invoice` round.
Re-implementing any of them in the eval would score a program we do not ship.
`--record` refreshes each case's `recorded.json`/`usage.json`, which is both the §5 CI policy
(regenerate whenever the prompt version bumps) and what makes every later re-score free.
A failing case is reported and skipped, never fatal: an accuracy round that dies on case 3 of 14
wastes the calls already spent on the rest.

Every run prints the mismatches behind the scores - `got` versus `truth`, per field - because a
boolean cannot tell a model error from a ground-truth error.
The first live run scored `pack_size` at 19% and that turned out to be entirely the latter.

The smoke exits nonzero if any fixture score drifts from its `expected.json`, so the scorer itself is regression-tested in CI - no key, no network, no spend.

## Scoring

- Header fields: exact for numbers and dates (Decimal-numeric, so "54.5" == "54.50"), fuzzy >= 0.9 for the supplier name (difflib on casefolded, whitespace-collapsed text).
- Lines: greedy alignment on raw_name similarity plus qty/unit_price agreement, then recall, precision, and per-field accuracy over aligned pairs.
- Reconciliation rate: fraction of extracted invoices whose arithmetic reconciles under C4, decided by `faida_api.extraction.validate` - the validator the product ships.
  The eval carried its own copy of C4 until WP-16 and it had drifted: knowing only the exclusive identity, it scored VAT-inclusive and discounted invoices as unreconciled off hand-verified ground truth, a ceiling of 11/14 against a gate of 100%.
  There is one implementation of C4 and the eval scores against it.
- Line units and pack sizes are compared through the units dictionary (`faida_api.extraction.units`), so a supplier writing "2 kg" where the catalog says "2000 g" is not scored as a miss.
- Both the live and recorded paths run the pipeline's derivation seam (`normalize_extracted`) before scoring, so a recording cannot score differently depending on how it is read.
- Cost per invoice comes from token counts at the model's list price; an unpriced model scores a null cost rather than a guessed one.
- Repair lift (reconciliation before versus after the scoped round) needs both calls, so it is reported on live runs and left null on recorded replays.

### Ground truth for the generated corpus

`<CASE>.expected.json` is the generator's *model* of an invoice - inventory codes, base-unit conversions, unit vocabulary - and `<CASE>.prompt.txt` is the human-authored specification of what the image actually prints.
For every C3 field defined as a printed fact (`raw_name`, `unit`, `pack_size`), truth comes from the prompt via `printed.py`; money and quantities come from `expected.json`, where arithmetic can check them.
Every parsed row is cross-checked against the modelled line total, so a mis-parse fails the case instead of quietly rewriting truth.

This is not a distinction on paper.
Until WP-16 the converter mapped `pack_quantity` (2000, grams) into `pack_size` (the page prints "2 kg") and `purchase_unit_text` into `unit`, including for TH-01, a till receipt with no unit column anywhere on it.
Regenerating truth from the printed page moved `pack_size` from 19% to 89%, `unit` from 90% to 100% and `raw_name` from 92% to 100% without touching the model.

A page with no pack-size column can still print the pack inside the item name ("RICE BASM 5KG"), and `matching.snap_item` already reads it there, so truth records it there too.
Pack sizes are compared through `faida_api.extraction.units`, the same dictionary the catalog uses, so "2 kg" and "2000 g" agree in the eval exactly when they would agree when snapping.

Gate targets (plan.md §5): totals/amounts >= 98% field accuracy, line fields >= 95%, 100% of confirmed invoices arithmetically reconciled, zero silent wrong numbers.
Phase-1 numbers are always reported as *measured on generated invoices* and never quoted as pilot accuracy.
Corpus images contain real supplier data - treat as sensitive; `results/` is gitignored.
