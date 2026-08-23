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
  fixtures/generated/        15 prompt-generated receipts across a hazard matrix, with
                             ground truth and provenance. SYNTHETIC: development and CI
                             material, never scored against the §5 targets, and no
                             substitute for F6. See its README.
  fixtures/expected_aggregate.json   expected corpus-level score for the fixtures
  score.py                   scoring + aggregation, pure functions
  recorded.py                provider replaying recorded.json/usage.json (the CI provider)
  run.py                     python -m eval.run
  results/<date>.json        run outputs, gitignored
  tests/                     scorer unit tests
```

A `truth.json` is exactly a serialized `ExtractionResult` from the pinned schema (`faida_api.extraction.schema`): `classification` plus an `invoice` object with supplier block, invoice_no, invoice_date, currency, payment_kind, lines, subtotal, tax, total.
Money values are strings ("18.50") so they parse as exact Decimals; dates are ISO ("2026-08-10").

## Commands

```bash
apps/api/.venv/bin/python -m eval.run             # score eval/corpus against recorded responses
apps/api/.venv/bin/python -m eval.run --smoke     # CI smoke: fixtures vs their expected scores
apps/api/.venv/bin/python -m pytest eval/tests -q # scorer unit tests
apps/api/.venv/bin/python -m eval.convert_generated  # generated fixtures -> C3 truth.json
```

`--live` (real provider calls) arrives with WP-16.
Recorded responses are regenerated whenever the prompt version bumps (plan.md §5 CI policy).
The smoke exits nonzero if any fixture score drifts from its `expected.json`, so the scorer itself is regression-tested in CI - no key, no network, no spend.

## Scoring

- Header fields: exact for numbers and dates (Decimal-numeric, so "54.5" == "54.50"), fuzzy >= 0.9 for the supplier name (difflib on casefolded, whitespace-collapsed text).
- Lines: greedy alignment on raw_name similarity plus qty/unit_price agreement, then recall, precision, and per-field accuracy over aligned pairs.
- Reconciliation rate: fraction of extracted invoices whose arithmetic reconciles under the C4 tolerances in `faida_api.extraction.constants`.
- Cost and latency per invoice come from `ProviderUsage`; repair-lift fields stay null until live runs supply them (WP-16).

Gate targets (plan.md §5): totals/amounts >= 98% field accuracy, line fields >= 95%, 100% of confirmed invoices arithmetically reconciled, zero silent wrong numbers.
Corpus images contain real supplier data - treat as sensitive; `results/` is gitignored.
