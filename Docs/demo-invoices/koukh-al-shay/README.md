# Five papers to put Koukh Al Shay's real menu on its feet (M6 demo gate)

Generator prompts in the corpus house format, arithmetic-checked, sized against the real
45-recipe menu in `~/Downloads/Menu engineer/koukh-al-shay/faida-loader-preview.csv`.
Generate each with the same image tool that produced `eval/fixtures/generated/`, save the
results here as `KAS-1.png` … `KAS-5.png`, and pre-verify every one through the live upload
door before any of them touches the demo phone.

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
