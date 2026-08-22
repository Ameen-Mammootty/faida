"""Invoice extraction eval harness (plan.md §5).

Scores extraction output against hand-verified ground truth (a corpus
truth.json is exactly a serialized ExtractionResult, C3) and runs a
recorded-fixture smoke in CI: no key, no network, no spend. Imports the pinned
contracts from faida_api; run with apps/api/.venv/bin/python from the repo
root.
"""
