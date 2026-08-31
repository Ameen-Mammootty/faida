# Five papers to put Koukh Al Shay's real menu on its feet (M6 demo gate)

The five papers themselves (`KAS-1.png` … `KAS-5.png`), the generator prompts that describe
them, the renderer that produced them and the script that verifies them. Sized against the real
45-recipe menu in `~/Downloads/Menu engineer/koukh-al-shay/faida-loader-preview.csv`.

**These are rendered, not image-generated, and that is the point.** Every total, every VAT line
and every per-base-unit delta here is load-bearing - the on-stage alert thresholds are computed
off them to the fils. An image model rewrites digits, which is why the corpus prompts have to
shout "reproduce every character exactly" and why every generated paper needs proofreading. A
render cannot get a digit wrong, so the paper on the phone is the paper the arithmetic was
checked against. `KAS-*.prompt.txt` are kept anyway: they are the corpus-format description of
each paper, and the route to take if a photographed-on-a-desk variant is ever wanted.

    apps/api/.venv/bin/python Docs/demo-invoices/koukh-al-shay/render_papers.py   # HTML
    # then, per paper, with the browse skill:
    #   $B viewport 1055x1491
    #   $B goto file://$PWD/Docs/demo-invoices/koukh-al-shay/KAS-1.html
    #   $B screenshot Docs/demo-invoices/koukh-al-shay/KAS-1.png --selector .page

`build_prompts.py` holds the numbers; the prompts and the rendered papers both import them, so
they cannot drift apart.

These do **not** replace `Docs/demo-invoices/DEMO-1..3` — those are act one's papers, tuned to
`demo_seed.sql`'s staged catalog. These are act two's: they exist so the real menu can be costed.

| Paper | Supplier | Date | Lines | Total AED | Why it exists |
|---|---|---|---|---|---|
| KAS-1 | Al Aweer Fresh Produce LLC, AAF-2026-3318 | 24/08/2026 | 16 | 753.90 | every vegetable on the menu |
| KAS-2 | Deira Spice & Dry Foods Trading LLC, DSF-26-08-441 | 24/08/2026 | 24 | 2,732.10 | sugar, salt, every spice, the dals and nuts |
| KAS-3 | Al Madina Trading Co., AMT-26-1203 | 25/08/2026 | 14 | 2,977.28 | dairy, eggs, paneer, the frozen proteins |
| KAS-4 | Gulf Foods Trading L.L.C., GFT-2026-0908 | 25/08/2026 | 28 | 3,833.55 | tea and beverage powders, bakery, sauces, water, all disposables |
| **KAS-5** | **Al Madina Trading Co., AMT-26-1274** | **31/08/2026** | **4** | **1,527.75** | **the on-stage paper: the same packs a week later, prices moved** |

Confirm KAS-1 to KAS-4 during preparation. **KAS-5 is the one you forward live** - it is a
repeat purchase, which is the only way the money moment can exist at all.

## Verified by reading them back, on the shipped engine

`verify_papers.py` extracts all five with Gemini 3 Flash and compares every line against the
source table. Last run 2026-08-31:

| Paper | Lines | Read | Totals | Reconciles | Latency |
|---|---|---|---|---|---|
| KAS-1 | 16 | 16 | 718.00 / 35.90 / 753.90 | green, exclusive 5% | 5.7 s |
| KAS-2 | 24 | 24 | 2,602.00 / 130.10 / 2,732.10 | green, exclusive 5% | 11.0 s |
| KAS-3 | 14 | 14 | 2,835.50 / 141.78 / 2,977.28 | green, exclusive 5% | 5.3 s |
| KAS-4 | 28 | 28 | 3,651.00 / 182.55 / 3,833.55 | green, exclusive 5% | 7.8 s |
| KAS-5 | 4 | 4 | 1,455.00 / 72.75 / 1,527.75 | green, exclusive 5% | 3.5 s |

**86 of 86 lines, zero mismatches** on name, quantity, unit, pack size and unit price. Supplier,
invoice number, day-first date, currency and credit terms all read correctly on every paper, and
the VAT treatment is *derived* from the arithmetic rather than taken from the document's claim.
Every latency is inside the ~20 s forward-to-reply target with room for the rest of the loop.

Re-run it after any edit:

    apps/api/.venv/bin/python Docs/demo-invoices/koukh-al-shay/verify_papers.py

It needs `GEMINI_API_KEY` and costs about a fils a paper.

## What was checked before these were written

Run against the shipped code, not asserted:

- **All 86 lines cost.** Every pack size parses in `units.py` and `costing.cost_line` returns a
  number for every line - no blocked costs, so no WP-55 queue to clear before the menu lights up.
- **All 82 materials the menu names have a line behind them.** 80 of them will be *proposed* by
  the matcher on the `/materials` queue; exactly two (`Garlic`, `Oil`) need the name typed,
  because the invoice prints "GARLIC PEELED" and "OIL SUNFLOWER" and a one-word material cannot
  clear the 0.70 proposal threshold once a description adds words. That is the matcher choosing
  silence over a guess, and it is worth showing rather than hiding.
- **Descriptions are printed the way a GCC wholesaler prints them** - bare commodity word in
  caps, pack size in its own column. That is both authentic and what makes the proposals land.

## Why the coverage has to be this complete

A plate is *incomplete* if **any** one component is missing, so coverage is close to
all-or-nothing. Measured on this menu:

| materials costed | items that can be costed (of 45) |
|---|---|
| 20 | 11 |
| 40 | 24 |
| 60 | 28 |
| 80 | 43 |
| 82 | 45 |

M6's done-when is 90% of items by count, so it needs roughly 80 of the 82. Four invoices is not
a shortcut - it is the smallest number of real papers that covers a cafeteria's actual buying.

## Two things in the menu that these papers had to solve

**Water is in 23 of the 45 items**, and nobody invoices the tap. Left alone, those 23 items stay
*incomplete* for ever and the 90% gate is unreachable. KAS-4 therefore buys **bottled water in
18.9 L bottles**, which is what a UAE cafeteria running a tea counter actually does.
**Founder call needed:** if Koukh Al Shay uses filtered mains water, the honest fix is to take
Water out of the recipes instead - it is not a purchase, so it is not a cost.

**Egg is measured in grams** in the recipes (4.167 g per portion), so its pack has to be a mass.
A 30-egg tray is a *count*, and the mapping door correctly refuses a piece pack onto a gram
material. KAS-3 prints eggs as a 1.8 kg tray, which is legitimate and maps cleanly.

## The money moment, and the WhatsApp alert it rides on

KAS-5 repeats four of KAS-3's exact packs, so "previous" is same-pack and the comparison is
honest (D3 - a delta across pack sizes is a pack artifact wearing a percent sign).

| Line | KAS-3 | KAS-5 | Per base unit | WhatsApp alert | On the menu |
|---|---|---|---|---|---|
| EVAP MILK 48X400ML | 90.00 | 99.00 | 4.69 → 5.16 per litre | up AED 9.00 (+10%) | every karak and coffee-milk item earns less |
| MILK POWDER 25 kg | 395.00 | 432.00 | 15.80 → 17.28 per kg | up AED 37.00 (+9.4%) | the milk-powder drinks follow |
| FRESH MILK 12X1L | 42.00 | 42.00 | unchanged | **silent** | nothing moves - not everything alarms |
| CHICKEN BONELESS 10 kg | 34.50 | 31.00 | 3.45 → 3.10 per kg | down AED 3.50 (-10.1%) | the chicken curries earn **more** |

The alert threshold is >= AED 0.25 and >= 5% of the last price, so three of the four fire and
the fresh milk deliberately does not. The chicken going *down* is worth pointing at on stage:
the callout is not a bad-news feed, it is what changed.

The menu screen's second callout ranks same-day moves by **what they cost a plate**, so it will
lead with whichever of these hits the biggest per-portion figure - the 2 L flask's 780 ml of
evaporated milk, on these numbers. Confirm KAS-5, **reload `/menu`**, and it is there.

## House rules these papers keep

- Distinct invoice number on every paper (since WP-44 a reused supplier + number + total is held
  as a duplicate - correct in production, a rehearsal-breaker on stage). KAS-3 and KAS-5 share a
  supplier on purpose and differ in number, date and total.
- Dates print day-first (`24/08/2026`), which the reply reads back as "dated 24 Aug 2026".
- **Credit terms on all five.** A cash paper gets the cash-hold closing and OK will not confirm
  it from chat.
- Prices are exclusive of VAT and each paper says so, so C4 derives the treatment from the
  arithmetic rather than guessing.
- No specimen or QA footer text: these are read as invoices on stage, and the corpus rule
  against watermarks applies doubly here.
- Every pack size is in its own column and parses - no bare cartons, which would land in the
  blocked-cost queue instead of on a plate.

## Regenerating or editing

The numbers came from a script, so change them there rather than by hand - the totals, the VAT
and the per-base-unit deltas all have to stay consistent with each other and with the alert
thresholds. If you change a description, re-check it against `propose_ingredients` before
printing; if you change a pack size, re-check it against `costing.cost_line`.
If you change an **invoice number**, update the prop list in `supabase/demo_reset_loop.sql` in
the same commit - the between-rehearsals reset identifies rehearsal residue by those numbers,
and a renumbered KAS-5 it does not know about would survive the reset and hold the next
rehearsal as a duplicate.
KAS-5's **printed date** must also stay newer than KAS-1..4's - costing ranks purchases by the
printed date (runbook §A's freshness rule), so a stale on-stage paper slots behind the
preparation purchases and the money moment never fires.
