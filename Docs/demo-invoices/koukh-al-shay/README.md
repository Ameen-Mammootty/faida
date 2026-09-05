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
    #   $B viewport 1055x1491 --scale 2
    #   $B goto file://$PWD/Docs/demo-invoices/koukh-al-shay/KAS-1.html
    #   $B screenshot Docs/demo-invoices/koukh-al-shay/KAS-1.png --selector .page

`--scale 2` is the setting `render_papers.py` documents and the one the 2026-09-01 papers were
rasterised at: A4 at 2110x2982, which is what a 300 dpi scan of the same page looks like. The
snippet here used to omit it and produced half-resolution papers - harmless for extraction, but
the two instructions disagreed, and the renderer's is the right one.

`build_prompts.py` holds the numbers; the prompts and the rendered papers both import them, so
they cannot drift apart.

These do **not** replace `Docs/demo-invoices/DEMO-1..3` — those are act one's papers, tuned to
`demo_seed.sql`'s staged catalog. These are act two's: they exist so the real menu can be costed.

| Paper | Supplier | Date | Lines | Total AED | Why it exists |
|---|---|---|---|---|---|
| KAS-1 | Al Aweer Fresh Produce LLC, AAF-2026-3318 | 24/08/2026 | 16 | 776.00 | every vegetable on the menu |
| KAS-2 | Deira Spice & Dry Foods Trading LLC, DSF-26-08-441 | 24/08/2026 | 24 | 3,001.95 | sugar, salt, every spice, the dals and nuts |
| KAS-3 | Al Madina Trading Co., AMT-26-1203 | 25/08/2026 | 14 | 5,335.79 | dairy, eggs, paneer, the frozen proteins |
| KAS-4 | Gulf Foods Trading L.L.C., GFT-2026-0908 | 25/08/2026 | 27 | 4,285.00 | tea and beverage powders, bakery, sauces, all disposables |
| **KAS-5** | **Al Madina Trading Co., AMT-26-1274** | **31/08/2026** | **4** | **2,873.33** | **the on-stage paper: the same packs a week later, prices moved** |

**The prices on these papers are real** - researched against UAE foodservice and wholesale
sources on 2026-09-01, one row per line with its source and date in
[`price-research-2026-09.md`](price-research-2026-09.md). The first draft's numbers were built
to make the arithmetic work (boneless chicken at AED 3.45/kg), which made the closing margin
screen read as a toy. Change a number in `build_prompts.py` and update that file in the same
commit.

Confirm KAS-1 to KAS-4 during preparation. **KAS-5 is the one you forward live** - it is a
repeat purchase, which is the only way the money moment can exist at all.

## Verified by reading them back, on the shipped engine

`verify_papers.py` extracts all five with Gemini 3 Flash and compares every line against the
source table. Last run 2026-09-01, after the repricing:

| Paper | Lines | Read | Totals | Reconciles | Latency |
|---|---|---|---|---|---|
| KAS-1 | 16 | 16 | 739.05 / 36.95 / 776.00 | green, exclusive 5% | 5.3 s |
| KAS-2 | 24 | 24 | 2,859.00 / 142.95 / 3,001.95 | green, exclusive 5% | 10.2 s |
| KAS-3 | 14 | 14 | 5,081.70 / 254.09 / 5,335.79 | green, exclusive 5% | 5.1 s |
| KAS-4 | 27 | 27 | 4,080.95 / 204.05 / 4,285.00 | green, exclusive 5% | 7.3 s |
| KAS-5 | 4 | 4 | 2,736.50 / 136.83 / 2,873.33 | green, exclusive 5% | 3.5 s |

**85 of 85 lines, zero mismatches** on name, quantity, unit, pack size and unit price. Supplier,
invoice number, day-first date, currency and credit terms all read correctly on every paper, and
the VAT treatment is *derived* from the arithmetic rather than taken from the document's claim.
Every latency is inside the ~20 s forward-to-reply target with room for the rest of the loop.

Re-run it after any edit:

    apps/api/.venv/bin/python Docs/demo-invoices/koukh-al-shay/verify_papers.py

It needs `GEMINI_API_KEY` and costs about a fils a paper.

## What was checked before these were written

Run against the shipped code, not asserted:

- **All 85 lines cost.** Every pack size parses in `units.py` and `costing.cost_line` returns a
  number for every line - no blocked costs, so no WP-55 queue to clear before the menu lights up.
- **All 81 materials the menu names have a line behind them.** 79 of them will be *proposed* by
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
| 20 | 3 |
| 60 | 20 |
| 75 | 37 |
| 80 | 40 |
| 81 | 45 |

M6's done-when is 90% of items by count, and that needs **80 of the 81**. Dropping Water barely
moved it, which is the point: the constraint is the long tail, not any one ingredient. Four
invoices is not a shortcut - it is the smallest number of real papers that covers a cafeteria's
actual buying, and all four are needed.

## Two things in the menu that these papers had to solve

**Water was in 23 of the 45 items, and it has been taken out of the recipes** - founder's call,
2026-08-31. The cafeteria runs mains water, so it is not a purchase, and a cost line for
something nobody buys would be an invented number in the layer this whole product exists to keep
honest. Two things followed: the menu CSV dropped its 23 Water rows (45 items intact, 81
materials now), and KAS-4 lost the bottled-water line it had been carrying to make those items
costable. The alternative - invoicing 18.9 L bottles - was the wrong shape: it would have made
the numbers *work* rather than making them *true*.

Consequence to expect on a menu already loaded: re-uploading the corrected CSV writes a new
recipe version for each of those 23 items, which is D8 doing its job. The Water material stays
in the catalog as an orphan with no pack and no price - there is deliberately no delete door for
a material (M5 gives mapping an undo, not ingredients a delete), and an unused shelf costs
nothing and lies about nothing.

**Egg is measured in grams** in the recipes (4.167 g per portion), so its pack has to be a mass.
A 30-egg tray is a *count*, and the mapping door correctly refuses a piece pack onto a gram
material. KAS-3 prints eggs as a 1.8 kg tray, which is legitimate and maps cleanly.

## The money moment, and the WhatsApp alert it rides on

KAS-5 repeats four of KAS-3's exact packs, so "previous" is same-pack and the comparison is
honest (D3 - a delta across pack sizes is a pack artifact wearing a percent sign).

| Line | KAS-3 | KAS-5 | Per base unit | WhatsApp alert | Worst plate |
|---|---|---|---|---|---|
| EVAP MILK 48X400ML | 221.00 | 237.00 | 11.51 → 12.34 per litre | up AED 16.00 (+7.2%) | Karak Flask 2 L, **-0.650** |
| MILK POWDER 25 kg | 333.50 | 360.00 | 13.34 → 14.40 per kg | up AED 26.50 (+7.9%) | Cappuccino Large, -0.013 |
| FRESH MILK 12X1L | 56.50 | 56.50 | unchanged | **silent** | nothing moves - not everything alarms |
| CHICKEN BONELESS 10 kg | 180.00 | 167.50 | 18.00 → 16.75 per kg | down AED 12.50 (-6.9%) | Butter Chicken, **+0.163** |

The alert threshold is >= AED 0.25 and >= 5% of the last price, so three of the four fire and
the fresh milk deliberately does not. The chicken going *down* is worth pointing at on stage:
the callout is not a bad-news feed, it is what changed.

**The two callouts deliberately disagree about what matters, and that is the point.** The
WhatsApp alert ranks by what the *supplier* changed, so milk powder's +7.9% reads as the joint
headline. The menu screen's second callout ranks by **what the move costs a plate** (WP-63), and
on the real menu that is not close: evaporated milk takes the top six places, because a 2 L karak
flask carries 780 ml of it, while milk powder appears in two drinks at about 12 g each and costs
them just over a fil. A price alert is not a margin alert - showing both, ranked differently and
each honest about its own question, is the argument for the layer. Confirm KAS-5, **reload
`/menu`**, and it is there.

| What it costs a plate | Item |
|---|---|
| -0.650 | 52b Karak Tea - Flask 2 L |
| -0.633 | 53b Coffee Milk - Flask 2 L |
| -0.583 | 54b Habbat Al Hamra - Flask 2 L |
| -0.325 | 52a Karak Tea - Flask 1 L |

## The sales week (act three, WP-85, added 2026-09-04)

Act three closes on a ranked branch table - **purchases ÷ net sales (cash basis)** per branch,
every purchase one click from its invoice photo. The purchases are these papers. No till has ever
exported a week for this chain, so `build_sales_week.py` invents one, and it says so wherever it
can: **the demo's sales are invented; its purchases are not; and the screen's honesty claim is
about the second.**

    apps/api/.venv/bin/python Docs/demo-invoices/koukh-al-shay/build_sales_week.py
    apps/api/.venv/bin/python Docs/demo-invoices/koukh-al-shay/build_sales_week.py --practice

`sales-week.csv` is the committed real week: the seven days ending on **KAS-5's printed date,
read from `build_prompts.SUPPLIERS` and never typed** (25/08 to 31/08/2026 today - a reprinted
prop moves the week with it), for the three demo branches, in the header the loader pins
(`Outlet,Date,PLU,Item,Qty,Amount`, day-first dates, amounts with the VAT inside them), 966 rows
and a totals footer with no date that the loader skips and counts. Item names are the till's own
shorthand with the code beside - most clear the proposer's bar (`CHKN 65 DRY`, `GOBI MSL`), three
are abbreviated enough to need the pick-from-menu path on purpose (`B/CHKN`, `MTR MSHRM`,
`PNR BTR MSL`), and one `DELIVERY CHARGE` line a day gives the coverage panel a "not a menu item".
A fixed seed makes it reproducible, and a test pins that the committed bytes are what the script
prints. The outlets print as `AL QUSAIS`, `AL NAHDA` and `ROLLA`, not as Faida's branch names, so
the first upload teaches three aliases once and every upload after that needs nothing.

`sales-week-practice.csv` is the rehearsal week for the practice stage: the five staged items, the
seven days ending on the demo tenant's newest staged purchase day **read from the database**
(`TEST_DATABASE_URL` or `DATABASE_URL`), because `demo_seed.sql` stages its purchases relative to
the moment it runs and a week computed from "today" drifts off them within days. **Regenerate it
before a practice rehearsal**; the committed copy exists so the path is real, not so its dates are.

The script does not re-implement anything: `takings.net_amount` divides the VAT out per line the
way the door does, and `ratio.period_row` computes the row the screen will show. It prints those
rows, and the volume constant is chosen so Al Qusais sits in a plausible band:

| | net sales | purchases | ratio |
|---|---|---|---|
| before the stage (KAS-3 and KAS-4 printed 25/08; KAS-1 and KAS-2 print the day before the week) | 30,267.43 | 9,162.65 | **30.3%** |
| after the on-stage forward (KAS-5, printed 31/08) | 30,267.43 | 11,899.15 | **39.3%** |

Al Nahda and Rolla have sales and no papers, so they read *incomplete - no confirmed purchases*:
two honest rows are the label doing its job on stage (the founder's call, P3). The practice week
reads 30.5% for Al Qusais against the seed's two four-week-old papers.

Two resets, two behaviours: `demo_seed.sql` deletes the week with everything else (re-upload the
regenerated practice file afterwards); `demo_reset_loop.sql` never touches the five sales tables,
and removing KAS-5 is what puts the ratio back to 30.3% by itself. Act three's script is
`Docs/DEMO_RUNBOOK.md` §G.

## Act four, and the figures the runbook quotes (WP-95, added 2026-09-05)

Act three ends on a ratio; act four (`Docs/DEMO_RUNBOOK.md` §H) answers what is underneath it -
what the chain **kept**, which dish sells and does not earn, and what one delivery did to both.
`act_four.py` prints every figure §H quotes, so none of them is typed:

    apps/api/.venv/bin/python Docs/demo-invoices/koukh-al-shay/act_four.py --migrate \
        --database-url postgresql://localhost:5432/faida_act_four --stage real
    ... --stage practice          # the seeded five-item menu and the rehearsal week
    ... --menu-csv <path>         # the real menu, if it is not at the default location

`--migrate` drops and rebuilds `public` from `supabase/migrations/`, so point it at a throwaway
database and never at a live one. The script stages the chain through the doors a person uses -
the menu through the loader, the four preparation papers through the typed-invoice door and the
confirm, each pack mapped to its material on the `/materials` queue, the week through
`POST /api/sales/days`, one keystroke per till name and `DELIVERY CHARGE` marked not a menu item -
and then reads `GET /api/dashboard` twice, before and after the on-stage paper. It imports the
shipped modules and computes nothing of its own; the only two things it simulates are the browser
and the sign-in.

**The real stage, after KAS-5 is confirmed** - the state act four reloads into at §H step 4, with
45 items costed and every till name mapped:

| | net sales | contribution | kept | ratio |
|---|---|---|---|---|
| Al Nahda | 23,066.47 | 14,994.39 | **65.5%** | - |
| Rolla | 18,608.45 | 12,117.63 | 65.6% | - |
| Al Qusais | 30,267.43 | 19,796.71 | 65.8% | 39.3% |
| the chain | 71,942.35 | **46,908.73** | **65.7%** | 16.5% |

Before that confirm the chain kept 47,020.76 at 65.8% and the signals panel held no milk move at
all; the confirm moves the whole week, because it is costed at the price in force on its last day
and KAS-5 is printed **on** that day (C12.4). The dish that sells and does not earn is
Hot Chocolate - Large 250 ml (AED 403 at stake); the bottom of the item panel is
Karak Delivery - Small 120 ml, 492 cups and AED 702.86 of sales, which kept AED 135.58 before the
on-stage paper and AED 116.40 after it. Both milk moves fire as spikes, dated 31 Aug: evaporated
milk AED 25.93 across 9 items, milk powder AED 1.11 across 2 - small because the delivery landed
on the week's last day, so only that day's cups carry it.

Two honesty notes the runbook repeats. The script **types** the four preparation papers, and a
typed price is asserted (C8), so every plate it prints is capped at *estimated*; on the real stage
those papers were read from photographs and the same figures read *reliable with limitations*. The
money is identical and only the word moves. And on the **practice** stage - the seeded five-item
menu - every dish keeps between 81% and 86%, so nothing is ten points below the average, no branch
is five points below the chain, and the seed's own price history moves nothing by 5%: **no signal
can fire there**, which is C13.3a's warning about a relative rule on a very short menu rather than
a fault. `tests/test_demo_seed.py` pins both stages - the practice one everywhere, the real one
where the menu CSV is - so a change that quietly breaks the script fails a test instead of the
demo.

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
**And check what it does to the menu before you print it:**

    apps/api/.venv/bin/python Docs/demo-invoices/koukh-al-shay/plate_costs.py --materials --moves

`plate_costs.py` runs the whole chain locally - invoice line to cost per base unit to material
price to plate cost to margin - by importing the shipped `costing.cost_line` and `plates.plate`
rather than reimplementing them, so what it prints is what `/menu` will show. It costs the real
45-recipe menu off these papers, ranks it, names any item that turns thin or negative, and prints
the money moment with the per-plate impact of each move. It needs no database and no API key.
A price that reads fine on the paper and quietly puts a plate under water is the failure this
catches; it also fails loudly if a pack stops parsing or a line stops costing.
If you change an **invoice number**, update the prop list in `supabase/demo_reset_loop.sql` in
the same commit - the between-rehearsals reset identifies rehearsal residue by those numbers,
and a renumbered KAS-5 it does not know about would survive the reset and hold the next
rehearsal as a duplicate.
KAS-5's **printed date** must also stay newer than KAS-1..4's - costing ranks purchases by the
printed date (runbook §A's freshness rule), so a stale on-stage paper slots behind the
preparation purchases and the money moment never fires.
