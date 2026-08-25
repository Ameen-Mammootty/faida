# Generated receipt fixtures - synthetic, never scored against the §5 targets

> **10 of the 15 cases have images.** `DUP-01`, `EDGE-02`, `EDGE-03`, `HW-03` and `NEG-01` are
> ground truth and prompts for images that were never generated, so `--live` skips them and the
> corpus that actually scores is ten. Generating those five images is the cheapest way to grow
> phase 1, and two of them (`EDGE-02` VAT-inclusive, `EDGE-03` a delivery note with no prices)
> cover reconciliation paths nothing else in the set reaches.

Every image in this directory was produced from a text prompt (`<case>.prompt.txt`), and
every `expected.json` carries `"synthetic": true`.
They are development and CI material.
They are **not** the eval corpus.

`plan.md` §5 requires the corpus to be 20-25 **real** invoices, and `eval/README.md` says "never
synthetic" for `eval/corpus/`.
That rule is not bureaucracy.
Tuning against generated images measures how well the pipeline reads a model's idea of crumpled
thermal paper.
Real invoices fail in ways nobody thinks to prompt for: a stapled second page, a thumb over the
total, a date written 5/7 with no year, ballpoint that did not transfer through the carbon.
Hitting the §5 accuracy targets on this set would tell you nothing about Tuesday's delivery note,
so **F6 stays open until real photos exist**.

## What they are good for

- **Edge cases the real corpus will not cover for months.** `EDGE-01` has a negative line and a
  percentage discount, `AR-01` and `HW-04` cover RTL and bilingual rows, `NEG-01` is a
  non-document for the decline path, `DUP-01` is a duplicate submission.
- **Regression fixtures for specific defects.** `TH-01` and `EDGE-02` are VAT-inclusive; `TH-01`
  is WP-17's reference case (see below).
- **CI smoke**, which is explicitly synthetic by design (§5 CI policy).

## TH-01, and a caution worth keeping

On 2026-08-23 `TH-01.jpg` was forwarded through the live WhatsApp channel during the F4 phone
proof.
It extracted perfectly - all ten lines, supplier, invoice number, date and totals exact - and it
exposed the VAT-inclusive reconciliation bug that became WP-17.
Its own `what_this_tests` had predicted exactly that: *"VAT already inside the printed prices.
This is the shape that made extracted headers disagree with net line sums."*

It was also briefly mistaken for a real invoice and written into `plan.md` as "corpus item #1"
before the ground truth here gave it away.
A generated receipt that reaches the pipeline through the same door a real one does is
indistinguishable downstream.
If you forward one of these for a demo or a test, say so out loud, because nothing in the
database will.

## Layout

```
<CASE-ID>/<CASE-ID>.jpg            the generated image (10 of 15 cases; 5 are still dry-run)
<CASE-ID>/<CASE-ID>.prompt.txt     the prompt that produced it - proof of provenance
<CASE-ID>/<CASE-ID>.expected.json  ground truth in the generator's own shape, not C3
<CASE-ID>/<CASE-ID>.verify.json    a read-back check that the image matches the ground truth
manifest.json                      case index: hazards, medium, line counts, status
```

`expected.json` is **not** a serialized `ExtractionResult`, so it cannot be dropped in as a
`truth.json`. Convert it:

```bash
apps/api/.venv/bin/python -m eval.convert_generated          # writes <CASE-ID>/truth.json
apps/api/.venv/bin/python -m eval.convert_generated --check  # verify without writing
```

Cases still marked `dry-run` in `manifest.json` have no image yet: `HW-03`, `EDGE-02`, `EDGE-03`,
`NEG-01`, `DUP-01`. `EDGE-02` is one of the two VAT-inclusive cases, so it is worth generating.
