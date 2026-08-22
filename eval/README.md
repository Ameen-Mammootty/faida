# eval — invoice extraction harness

Arrives in **M1** (see `/plan.md` §5). Layout when it lands:

```
eval/
  corpus/<name>.jpg|pdf     real invoices (never synthetic)
  truth/<name>.json         hand-verified ground truth, extraction schema
  run.py                    python -m eval.run -> scores + eval/results/<date>.json
```

Gate targets: totals/amounts >= 98% field accuracy, line fields >= 95%,
100% of confirmed invoices arithmetically reconciled, zero silent wrong numbers.
Corpus images contain real supplier data — treat as sensitive; results/ is gitignored.
