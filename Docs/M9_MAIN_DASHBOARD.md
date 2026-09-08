# The main dashboard - the founder's direction, read against the live `/dashboard` (drafted and reviewed 2026-09-05)

Status: **drafted 2026-09-05, evening, after M9's rows 90 to 95 shipped and before WP-96's live sitting; reviewed the same evening with two outside voices (the report is at the end of this file); APPROVED TO BUILD 2026-09-05 - the founder answered every decision in §7 as recommended ("Go as per your recommendation").**
The founder asked for it in one sentence, showing a screenshot of the previous build's dashboard: *"I would also want a main dashboard something like the above, make a plan for the same"* (2026-09-05).
That sentence is the customer quote `plan.md` §2 rule 8 requires, and it is the founder's own, so the scope is admitted; what this document does is read the reference against what is already live, translate it through the product's display rules, and hand back seven decisions.
The session that wrote it ran unattended, so every choice below was written as **recommended**, in the M9 decomposition's convention; the founder's answer the same evening turned each one into a decision, and §7 records which.
The two reviews corrected three load-bearing claims of the first draft - the tiles were not scope-safe under a branch filter, "every move in the window" was not what the price read returns, and a fall's money came out with the wrong sign - and every correction is folded below and named in the report.

Facts in §2 are from master `fb19bef` (the drill live on both hosts; WP-96 open).

Plan reference: `plan.md` §8 M9 (the checklist and the done-when), §3 (the display rules), §7.2 C12, C13 and the C9 and C6 extensions; `Docs/M9_DECOMPOSITION.md` §3.1 (the wire), §4.1 (the design direction as amended by the 2026-09-05 design review), §5 (the ten decided proposals); the Approved Mockups row for `/dashboard` (Variant A, picked 2026-09-05 11:05); `Docs/brand/faida-brand-guidelines.md` (Date Palm for navigation; "avoid dashboard decoration without informational purpose"); CLAUDE.md's product display rules.

## 1. What the founder asked for, and what the reference is

The screenshot (`Screenshot 2026-09-05 005021.png`, taken at 00:50 on 2026-09-05, before the design review that picked Variant A at 11:05) is the **previous build's** dashboard, run locally at `localhost:3000/dashboard`.
None of its labels exist in this codebase: `git grep` on master finds no "Executive Dashboard", no "Inventory" screen and no "Profitability" screen under `apps/web/src`, and its percentages carry four decimals where every figure this API sends is a one-decimal string.
So the reference is a picture of a shape the founder liked, not a screen to restore, and its numbers are the old build's problems (a cost coverage of 109.0971% beside an "unavailable" chip is exactly the contradiction C9 was written to forbid).
The screenshot lives only on the founder's machine; **copying it to `Docs/reference/` before the design review is a founder step**, so the board has the thing it answers beside it. **Done 2026-09-08:** the file is `Docs/reference/previous-build-dashboard-2026-09-05.jpg` - the photograph the founder pasted into the planning session, of the Windows laptop with the PNG open, recovered from the session transcript because the PNG itself was never on the Mac; `Docs/reference/README.md` says so.

Read element by element, against what is live today:

| Reference element | What it shows | What the live `/dashboard` (Variant A) has | Gap |
|---|---|---|---|
| Heading "Executive Dashboard" and the tagline "Profit visibility, sales cost coverage, and supplier price moves." | a name and a static line | "Dashboard", the freshness line, then **two answer sentences** naming the branch and the dish to look at first | none worth keeping: the sentences say what the tagline promised |
| Branch select "All branches" | one branch or all | the branch filter, writing `?branch=` into the URL; the chain total never follows it (P7) | none |
| From and To date inputs | a free range | the period picker: last 28 days, last 7 days, each calendar month that holds sales; the API takes any `from` and `to` up to 92 days | a control, not a capability - §7 D3 |
| Four tiles: Pre-tax net sales AED 241.00; Attributable material cost AED 44.845; Known contribution AED 196.155, "81.3921% contribution margin"; Cost coverage 109.0971% with a bar | the headline figures | every one of these fields is on the wire already, in `total`, `league`, `freshness` and `unmapped` - shown in the league's total row and the coverage strip, never as tiles | **the tiles are new**; the words and the precision change (§3) |
| Branch performance: Branch, Net sales, Known contribution, Margin %, Cost coverage, Quality; "Detailed Profitability →" | the ranked branches | the league: Branch, Net sales, Purchases ÷ net sales, Contribution (est.), Kept, Status, with the window and the costed share under the name and the status; ranked by Kept lowest first; a branch name opens `/sales#branch-<id>` | a section link, and the costed share as a column if the founder wants one |
| Top menu items: name, "40 sold · AED 200.00 sales", AED 172.947, "86.4735% margin"; "All recipes & margins →" | the best dishes | "Items: what each one contributed": Sold, Net sales, Contribution, Kept, **five best and five worst**, expanding in place to every ingredient's invoice line | a section link; the reference shows only the top |
| Supplier price movements: cards tagged "Price moved" - "Bun is up AED 1.10 each since 4 Sep 2026. Spicy Moon Burger earns AED 2.20 less a portion - check the price or the recipe. was AED 0.10 each · See the invoice"; "All materials →" | the latest move per material, with the plate it hurts | a price **rise** of 5% or more appears in "What to look at" as one of three signal kinds, ranked by money at stake among them and capped at five in total; the full list with both directions lives on `/menu`'s callout, whose card says the reference's own sentence - "earns AED X less a portion - check the price or the recipe" | **the panel is new**; the wording exists almost verbatim in `signals.price_spike` and `/menu`'s `FixCallout` |
| Sidebar: OVERVIEW Dashboard; OPERATIONS Invoices, Sales, Inventory; PERFORMANCE Profitability; SETUP Materials, Menu | grouped navigation on Date Palm | a top bar: the brand mark is the dashboard link (a fifth word does not fit 390 px, measured), then Invoices, Materials, Menu, Sales | **the sidebar is new**; Inventory and Profitability have no screen here (§3) |

The reading is that **the data, the ranking, the drill and the landing already exist**, shipped this morning to the shape the founder picked on the board; what the reference adds is a layout (tiles and a sidebar) and one panel (price moves as a block of their own).
That is the whole plan: a delta on the live screen, never a second screen and never a rebuild.

## 2. What is already live, and what it forbids the plan from doing twice

- **One read serves the whole screen.** `GET /api/dashboard?from&to&branch_id` (`dashboard.py`) returns `period`, `answer`, `freshness`, `latest_day`, `approvals`, `league`, `unassigned`, `scope`, `total`, `items`, `signals`, `unmapped` and `menu`, from an enumerated set of eighteen reads whose count is pinned flat by `test_dashboard.py:45-67`.
  A tile is a projection of that payload; a second read for a tile would breach P9 and the query-count test both.
- **The headline fields exist, and two of them follow the branch filter while `total` never does.** `total` carries `net_sales`, `purchases`, `ratio_pct`, `contribution`, `contribution_pct`, `costed_share_pct` and the two quality words with their notes, always for the chain (`dashboard.py:551-562`).
  `league` is filtered to the branch in view (`dashboard.py:447`) and so is `unmapped` (`dashboard.py:507`, `:572`; the mock proves it - `full.json`'s chain scope has three unmapped names worth AED 8,320, its `br-01` scope one worth AED 3,120, with `total.costed_share_pct` identical in both).
  The shipped coverage strip already resolves this the honest way: under a filter it quotes `league[0].costed_share_pct`, "that branch's row, never the chain's" (`dashboardScreen.ts:500-503`).
  A tile that took its figure from `total` and its sentence from `unmapped` would print a chain share above a branch sentence, which is the reference's 109%-beside-"unavailable" all over again; §4.2 follows the strip's rule instead.
- **The price moves are already computed inside the read and thrown away - and they are each material's latest move, not a history.** `dashboard.py:417-418` builds `pairs` with `as_of=period.end` and calls `menu.price_moves(...)` to feed the spike signal; the resulting `PriceMove` list (`menu.py:765-786`: both lines with their invoice ids and positions, the delta per display unit, and `items` with the per-plate impact and the margin either side) is never serialised.
  What that list holds is bounded by the read behind it: `db.list_price_move_pairs` returns the **two newest** costed lines per material at or before the period's end (`db.py:1451`, `recency <= 2`), with **no lower date bound**, and `menu.price_moves` keeps only materials a current recipe uses, drops a first purchase and a zero delta, and returns at most one move per material (`menu.py:841-850`).
  So the panel can be "each material's latest move", never "every move in the window", and a material last bought twice in March would surface a March move inside an August window unless the block bounds it - §4.3 does.
- **The sales-weighing is one loop and its sign belongs to the cost.** `signals.price_spike` weighs a move by `Σ impact_per_portion × portions sold on or after it` (`signals.py:315-335`), where `plates.margin_impact` is "positive when the price rose" (`plates.py:160-169`); the 5% gate (`signals.py:303-313`) and the wording (`:343-361`) sit outside the loop, so the loop is reusable for a fall, and `rank` sorts by `-money_at_stake` (`signals.py:457-469`), so a fall reused unchanged would rank below a move nothing sold after.
- **The sentences are Python's, and the screen frames them.** C13.5 as practised: the API composes every sentence that carries a conclusion, a ranking or a fact about the business (`answer`, `freshness.sentence`, the signals, the notes), and the screen joins figures the API sent with labels - `freshnessLine` writes "AED 9,856 taken that day across 3 branches" (`dashboardScreen.ts:143-144`), `cardLine` writes "Kept AED 9,483 of AED 17,960 · purchases ÷ net sales 39.3%" (`:260-269`), `coverageStrip` writes "These figures cover 84.2% of what was sold" (`:505-514`) - and never divides, re-words or re-ranks.
  The tiles in §4.2 stay inside that line; the price-moves block in §4.3 carries its sentences from Python because the spike already composes them there.
- **`/menu`'s price-move card is two paragraphs at two sizes**: "{name} earns AED X less a portion - check the price or the recipe" (`MenuMargins.tsx:241-246`) and, in small type, "Also earning less: A (AED …), B (…), and N more items." (`:249-260`, `ALSO_NAMED = 3` at `:166`).
  The reference's card is that first paragraph word for word.
  Its route, `GET /api/price-moves`, is pinned by `tests/test_price_moves.py` (seven tests), and `_move_payload` is documented as "the wire shape the screen has read since WP-63, unchanged" (`menu.py:933`), so anything added there is additive and optional.
- **The screen's decisions live in `dashboardScreen.ts`** (52 exports, pinned by `dashboardScreen.test.ts`), because there is no component-rendering test capability; the tiles and the panel add functions there, and the component renders what they return.
- **The mock computes nothing, and it does not call the route.** `mock/dashboard/generate.py` imports `contribution`, `signals`, `ratio` and `menu`'s dataclasses, hand-builds two `PriceMove` objects (`generate.py:349-382`) and copies `dashboard.py`'s answer and freshness sentences (its own docstring, `:19-21`).
  A new block therefore costs the generator hand-authored inputs and one serialiser call; the serialiser must be a pure function both the route and the generator import, or it is written twice.
- **The shell is measured, and its session control is already mounted twice.** `AppShell.tsx` is a server component with no `<nav>` element (the links sit in `<div>`s inside `<header>`); it renders `SessionMenu` once in the desktop row and once in the phone row (`:96`, `:123`), each mounting its own session read (`SessionMenu.tsx:33-46`); four nav words fill the top row at 390 px, which is why the brand mark became the dashboard link this morning.
- **The grids were measured at 976 px and never narrower** (the `max-w-6xl` column at a 1024 px viewport): the dashboard league is six fixed columns at 23/13/16/16/11/21 (`Dashboard.tsx:846-853`) with a name cell carrying "Al Qusais" and "25-31 Aug, 7 days · 3 deliveries"; `SalesTable` is 30/16/16/18/20; the cards take over below the 640 px viewport breakpoint only, and the table wrappers are `overflow-hidden`, so a grid squeezed below its measured width clips text rather than overflowing the page.
- **The first-run rule stands**: "no tiles, no zeros: one paragraph and the one link that changes the state" (the approved first-run state).
  Tiles appear when there is something to count and never before.
- **Two decisions already wait on the founder in `TODOS.md`** and the tiles make one of them louder: the headline rounding (`roundedAed` truncates while every API sentence rounds half up; "fired, on the dashboard's signal line") becomes four whole-dirham figures beside sentences that round the other way, and the same truncation understates a negative figure.

## 3. The translation the product's rules force

The reference's words and precision are the old build's.
This build has display rules pinned in `plan.md` §3, CLAUDE.md and the 2026-08-30 design review, and contracts C11.6 and C12.7 that name forbidden phrases.
Every label below is the reference's, then what the screen says instead, then why.

| The reference says | The screen says | Why |
|---|---|---|
| Executive Dashboard | Dashboard | the product's voice is an operator's, not an executive summary's; the heading is the nav word |
| Profit visibility, sales cost coverage, and supplier price moves. | the two answer sentences | a tagline is decoration; the sentences are the conclusion (the approved "answer first" rule) |
| Pre-tax net sales · AED 241.00 · "All committed sales" | Net sales · AED 69,707 · "from the till, net of VAT · loaded to Mon 31 Aug" | rounded AED in a headline (§3); "committed" is not a word this product uses - a loaded day is a fact, not a commitment; the branch count already sits in the freshness line above and is not repeated |
| Attributable material cost · AED 44.845 · "Costed from confirmed supplier purchases" | Purchases ÷ net sales (cash basis) · 17.1% · "AED 11,899 of confirmed papers in this window" · status word | M8's own checklist puts "the first analytic on the dashboard: purchases ÷ net sales"; fils in an aggregate are forbidden; the alternative is §7 D2 |
| Known contribution · AED 196.155 · "81.3921% contribution margin" | Contribution before overheads (estimate) · AED 41,804 · "keeps 60.0% of costed sales · after ingredients and packaging" · status word | C12.7: never "net profit", never "profit", and always "which share it covers"; one decimal on a percentage (C11) |
| Cost coverage · 109.0971% · a chip "unavailable" · a progress bar | Costed share of sales · 77% · "3 till names worth AED 8,320 have no dish yet · Map them on Sales" | C12.7a bounds the share 0-100 and derives it from the rows; "costed", never "complete" or "coverage"; a bar without the number beside it carries meaning by colour alone, so the number is the tile and there is no bar |
| Branch performance · Known contribution · Margin % · Cost coverage · Quality | the league's own words: Contribution (est.), Kept, Status, and "covers 78% of sales value" under the status | the league is shipped; the column names are C12's |
| Detailed Profitability → | Days and papers on Sales → | there is no profitability screen; `/sales` holds the days, the papers and the queue |
| Top menu items · "86.4735% margin" | Items: what each one contributed · best five and worst five · Kept 81.4% | the done-when asks "which item is hurting me", which the top five cannot answer; one decimal |
| All recipes & margins → | Every plate on Menu → | `/menu` is where the plate and its ingredients live |
| Supplier price movements · "Price moved" | Supplier price moves · "Price moved" / "Price fell" / "Price basis changed" | the tag pattern is kept; a fall and a basis change are named as what they are, never dressed as a spike |
| "earns AED 2.20 less a portion - check the price or the recipe" | the same sentence | it is `/menu`'s own price-move line (`MenuMargins.tsx:241-246`); the two screens speak one sentence because the API now composes the clause both read |
| All materials → | Every price move on Menu → | the full list with both packs named is `/menu`'s callout and `/materials`; the panel shows five and counts the rest |
| OVERVIEW Dashboard / OPERATIONS Invoices, Sales, Inventory / PERFORMANCE Profitability / SETUP Materials, Menu | OVERVIEW Dashboard / OPERATIONS Invoices, Sales / COSTING Materials, Menu | there is no inventory (deferred beyond MVP, `plan.md` §8, with no customer quote) and no profitability screen (it is this screen and the Menu screen); Materials and Menu are costing screens, not setup |
| From · To | Last 28 days / Last 7 days / the months with sales | the 2026-09-03 design review's rule, "a month offered always has sales"; the API takes a free range already, so this is D3 and one control if the founder wants it |

## 4. The proposed screen

Reader order at 1280 px: the sidebar; the heading with the controls on its right (the reference's placement); the freshness line; the two answer sentences; the four tiles; the league; two columns - what to look at, and the supplier price moves; the items; the coverage strip.
The sentences stay above the tiles because a sentence is a conclusion and a tile is a fact about its size; the reference puts the tiles first, and §7 D1 lets the founder flip that.

```
 ┌ sidebar (Date Palm) ─┐ ┌────────────────────────────────────────────────────────────────────────────┐
 │ ▣ faida              │ │ Dashboard                     [Last 28 days | Last 7 days | Aug 2026]  [All branches ▾] │
 │                      │ │ Sales loaded to Mon 31 Aug, 5 days ago · AED 9,856 taken that day across 3 branches      │
 │ OVERVIEW             │ │ · 3 papers waiting for you                                                               │
 │ ● Dashboard          │ │ Look at Rolla first: it keeps about AED 53 of every 100 it takes, the least of the three. │
 │                      │ │ Chicken 65 Dry sells more than any dish that earns under the menu's average.             │
 │ OPERATIONS           │ │                                                                                          │
 │   Invoices           │ │ ┌ NET SALES ──────┐ ┌ PURCHASES ÷ NET SALES ┐ ┌ CONTRIBUTION (EST.) ┐ ┌ COSTED SHARE ──┐ │
 │   Sales              │ │ │ AED 69,707      │ │ 17.1%                 │ │ AED 41,804          │ │ 77%            │ │
 │                      │ │ │ from the till,  │ │ AED 11,899 of         │ │ keeps 60.0% of      │ │ 3 till names   │ │
 │ COSTING              │ │ │ net of VAT ·    │ │ confirmed papers ·    │ │ costed sales, after │ │ worth AED 8,320│ │
 │   Materials          │ │ │ loaded to       │ │ Incomplete: 2 of 3    │ │ ingredients and     │ │ have no dish   │ │
 │   Menu               │ │ │ Mon 31 Aug      │ │ branches have none    │ │ packaging · Incomplete│ │ Map them →   │ │
 │                      │ │ └─────────────────┘ └───────────────────────┘ └─────────────────────┘ └────────────────┘ │
 │                      │ │                                                                                          │
 │                      │ │ Branch league                                            Days and papers on Sales →    │
 │                      │ │ ┌ Branch ─ Net sales ─ Purchases ÷ net sales ─ Contribution (est.) ─ Kept ─ Status ─┐  │
 │                      │ │ │ ▸ Rolla        AED 17,960  No confirmed purchases  AED 9,483   52.8%  Incomplete  │  │
 │                      │ │ │ ▸ Al Qusais    AED 30,267  39.3%                   AED 18,421  60.9%  Reliable w/l │  │
 │                      │ │ │ ▸ Al Nahda     AED 21,480  No confirmed purchases  AED 13,900  64.7%  Reliable w/l │  │
 │                      │ │ │   All branches AED 69,707  17.1%                   AED 41,804  60.0%  Incomplete   │  │
 │                      │ │ └ Contribution is what is left after ingredients and packaging ... (the shipped footnote) ┘ │
 │                      │ │                                                                                          │
 │                      │ │ ┌ What to look at (3) ───────────────────────┐ ┌ Supplier price moves ─────────────────┐ │
 │                      │ │ │ Rolla keeps 7.2 points less ...  AED 1,293 │ │ 4 materials moved this window,        │ │
 │                      │ │ │ Chicken 65 Dry sold AED 3,120 ...  AED 593 │ │ latest move each · Every move on Menu →│ │
 │                      │ │ │ Milk Powder is up AED 1.60 per kg  AED 210 │ │ PRICE MOVED                            │ │
 │                      │ │ └────────────────────────────────────────────┘ │ Milk Powder is up AED 1.60 per kg      │ │
 │                      │ │                                                │ since 25 Aug. Karak Tea earns AED 0.13 │ │
 │                      │ │                                                │ less a portion; also Karak Tea - Flask │ │
 │                      │ │                                                │ 1 L (-0.07) and 2 more.                │ │
 │                      │ │                                                │ was AED 22.40 per kg · AED 210 at stake│ │
 │                      │ │                                                │ since 25 Aug · See the invoice         │ │
 │                      │ │                                                │ PRICE FELL   Sugar is down AED 0.20 ...│ │
 │                      │ │                                                │ PRICE BASIS CHANGED  Ghee is priced    │ │
 │ owner@koukh.ae       │ │                                                │ from a different pack now ...          │ │
 │ Sign out             │ │                                                └────────────────────────────────────────┘ │
 │ Profit, in plain     │ │ Items: what each one contributed      41 costed of 45 · Every plate on Menu →  Show all │
 │ sight.               │ │ ┌ Best  Karak Tea - Flask 1 L   412   AED 13,733   AED 11,177   81.4% ┐  (the shipped  │
 └──────────────────────┘ │ │ ...   Worst  Chicken 65 Dry    74   AED  3,120   AED  1,279   41.0% │   panel)       │
                          │ └─────────────────────────────────────────────────────────────────────┘                 │
                          │ ┌ mist: These figures cover 77% of what was sold. 3 till names ... Map them on Sales → ┐ │
                          └────────────────────────────────────────────────────────────────────────────────────────┘
```

The board at `~/.gstack/projects/Ameen-Mammootty-faida/designs/dashboard-main-20260905/wireframes.html` draws this at 1160 px with the real tokens and at 390 px, beside the approved Variant A for comparison; `proposed.json` sits next to it and becomes `approved.json` when the founder picks.

### 4.1 The sidebar (WP-97)

- **At 1280 px and above** (Tailwind's `xl`), a 232 px Date Palm column: the mark and the wordmark at the top (the brand guide's horizontal lockup, never below 120 px), three group captions in small caps, five entries, the current one marked with `aria-current="page"` and a Karak Gold bar at its left edge plus bold weight (the word and the weight carry the state; the gold is the third cue, never the only one); at the foot, who is signed in, Sign out, the mock-mode "Sample data" chip when it applies, and the line "Profit, in plain sight." which the footer carries today.
  Text is Warm Cream on Date Palm (11.0:1); the current entry's bar and the focus ring are Karak Gold on the palm ground (5.32:1, AA for text and for a focus indicator), because the palm ring the app uses elsewhere would vanish on itself.
- **Why 1280 and not 1024.** The content column becomes `1280 − 232 − 48 ≈ 1000 px`, wider than the 976 px every fixed grid on the app already survives at a 1024 px viewport, so no colgroup is ever narrower than a width it has already been measured at; nothing is walked, and no card fallback is needed.
  At 1024 px the same sidebar would leave about 744 px, a 24% squeeze on grids tuned at 976, and the `overflow-hidden` wrappers would clip the league's name cell rather than overflow the page - the first draft put the sidebar at 1024 and both reviews caught it.
  The founder's reference is a desktop screenshot; nothing in it argues for 1024.
- **Under 1280 px, nothing changes**: the shipped top bar stays exactly as measured - the mark as the dashboard link, the four words, the quiet second row on a phone.
  The 2026-09-05 decision "the brand mark is the dashboard link" therefore stands where it was measured and is superseded only where there is room for the word.
- **One chrome shows at a time, and it gets a `<nav>`.** `AppShell` stays a server component and cannot pick a chrome by viewport at render time, so both chromes are in the DOM and Tailwind's `hidden` / `xl:flex` (which is `display:none`, never `sr-only` or opacity) removes the other from the accessibility tree and the focus order; each chrome wraps its links in `<nav aria-label="Faida">`, which the shipped header lacks, so a screen reader hears one landmark.
  `aria-current` goes on the Dashboard entry, never on the lockup.
- **One session control, not three.** The shipped header already mounts `SessionMenu` twice, once per row, each running its own session read; the sidebar must not make it three.
  The lane places one instance and moves it between the header row and the sidebar foot with CSS (`order` and positioning inside one grid), or hoists the session read into `AppShell`'s one client island and passes the email down - either way the acceptance is one session read per page load, which also fixes the shipped duplication in passing.
- **The content column** keeps `max-w-6xl` inside the remaining width; every layout's `current` prop and the `Screen` union are unchanged, so no screen file moves.
- **Groups and words**: OVERVIEW - Dashboard; OPERATIONS - Invoices, Sales; COSTING - Materials, Menu.
  The loaders (`/menu/load`, `/sales/load`) stay out of the nav, as decided for `/sales`; they are reached from their screens.

### 4.2 The tiles (WP-98)

Four, on paper, in one row from 1024 px, two by two under it, one column at 390 px.
Each is a `<dl>`: a small-caps `<dt>`, the figure as a Manrope headline with tabular numerals, one sentence, and the status word as the shared `QualityChip` where the figure has one.
No icon, no gauge, no bar, no sparkline, no trend arrow: the brand guide's "dashboard decoration without informational purpose" is exactly the reference's progress bar, and the figure beside it says everything the bar would.

**The tiles are the row in view, and they name the chain beside it.** Unfiltered, every figure comes from `total` (the chain).
Under `?branch=`, every figure comes from `league[0]` - that branch's row, which carries the same fields - and the sentence names the chain's figure for comparison ("the chain keeps 60.0%"), which is what P7 kept `total` chain-wide for.
This is the coverage strip's own rule (`dashboardScreen.ts:500-503`), applied to all four, so a tile can never print a chain share above a branch sentence, and the tiles always agree with the league row and the strip on the same screen.
The first draft took the figures from `total` and the sentences from `unmapped` and `league.length`, which follow the filter; both reviews caught the mismatch.

| Tile | Figure | Sentence beneath | Status | From (unfiltered / filtered) |
|---|---|---|---|---|
| Net sales | `net_sales`, rounded AED | "from the till, net of VAT · loaded to `<weekday date>`", with the word "Estimated" when `freshness.quality` is | the freshness word only | `total` / `league[0]`; `freshness` |
| Purchases ÷ net sales (cash basis) | `ratio_pct` + "%", or the ratio cell's own words (`noRatioWords`) | "AED `<purchases>` of confirmed papers in this window"; filtered, "· the chain reads `<total.ratio_pct>`%" | `ratio_quality` and its first note | `total` / `league[0]` |
| Contribution before overheads (estimate) | `contribution`, rounded AED; the loss figure when negative | "keeps `<contribution_pct>`% of costed sales · after ingredients and packaging"; filtered, "· the chain keeps `<total.contribution_pct>`%" | `contribution_quality` and its first note | `total` / `league[0]` |
| Costed share of sales | `costed_share_pct` + "%" | "`<names>` till names worth AED `<value>` have no dish yet" with the link to the queue, or "Every till name is mapped." | none (a share is a fact about the rows) | `total.costed_share_pct` / `league[0].costed_share_pct`; `unmapped` (already scoped) |

States: **first run** - no tiles (the paragraph stands); **no menu** - the first two tiles show and the third and fourth say "No menu is loaded, so nothing can be costed yet" (`noMenuSentence`); **branch filter** - the branch's row with the chain named beside, and the caption is the branch's name; **stale** - the net sales tile carries the word "Estimated" beside its date; **error** - the strip, no tiles; **a negative contribution** - the loss figure with its words on the same line ("the costed sales lose money"), which means the shared loss component takes its noun as a parameter, since today's two copies hard-code "this item" and "this plate".

No wire change: every figure above is a field on `total`, `league[0]`, `freshness` or `unmapped`, and every sentence is a figure the API sent joined with a label, the shipped screen's own practice (`cardLine`, `coverageStrip`).
`dashboardScreen.ts` gains `tiles(result): Tile[]` and `dashboardScreen.test.ts` pins the four tiles per scenario and per scope.
**`format.ts` is touched only if D7 is taken**: rounding half up in `roundedAed` moves headline figures on `/materials`, `/menu`, `/sales` and `/dashboard` by at most a dirham, so WP-98 owns that change and its regression sweep across the four screens, and nothing else in `format.ts` moves.

### 4.3 The supplier price moves panel (WP-99)

**On the wire**, one block added to `GET /api/dashboard` (C6 extended once more; the query count does not move because the moves are already in hand):

```
"price_moves": {"count": 4, "moves": [       (at most five, ranked; count is the whole number)
  {"ingredient_id": "…", "ingredient_name": "Milk Powder",
   "kind": "moved" | "basis_changed", "direction": "up" | "down" | null,
   "moved_on": "2026-08-25",
   "invoice_id": "…", "line_position": 3,                       (the newest line, for /invoices/<id>#line-<n>)
   "money_at_stake": "210.40" | "-24.10" | null,                (signed: positive costs, negative saved; null for a basis change)
   "sentence": "Milk Powder is up AED 1.60 per kg since 25 Aug.",
   "plates": "Karak Tea earns AED 0.13 less a portion; also Karak Tea - Flask 1 L (-0.07) and 2 more.",
   "evidence": "was AED 22.40 per kg · AED 210 at stake on the 1,240 portions sold since 25 Aug."}
]}
```

- **What the list is, said honestly: each material's latest move, inside this window.** The read holds one move per material on the current menu (§2), so the block is that list filtered to moves whose newest line was purchased **on or after the period's start** - the same `as_of` bound at the top and a lower bound at the bottom, so a March move never surfaces in August - and its caption says so: "4 materials moved this window, latest move each".
  A material that moved twice in the window shows its latest move only, by construction, and the caption's wording is what makes that true rather than hidden.
- **The spike's 5% gate applies both ways.** A rise of 5% or more is news and so is a fall of 5% or more; a 0.3% drift on a spice nobody sells is not, and without the gate a 45-item menu would count twenty "moves" and list five rows of nothing.
  A basis change carries no percentage and is listed regardless, after the moves, because it is evidence and it is rare.
- **Ranked by the money it moved, whichever way.** The spike's weighing loop is extracted into one pure helper that both `price_spike` and this block call: it returns the signed sum (`plates.margin_impact` is positive when the price rose), the block ranks by its absolute value, then by the largest per-plate impact, then by name; `direction` picks "at stake" or "saved" in the evidence sentence; a basis change carries no money and sorts last.
  The first draft reused the signed sum unchanged, which would have ranked a fall below a move nothing sold after; both reviews caught it.
- **The weighing follows the branch filter, exactly as the signals' does** (`signals.py:291-299`): under `?branch=` the portions are that branch's, so the same rise carries the same dirhams in both panels whatever the scope, and the acceptance "the same rise is in both with the same money" holds filtered and unfiltered.
- **Every sentence is composed in Python, once, in a pure function both callers share.** `sentence` is the spike's own wording generalised to "is down" and to the basis-change sentence; `plates` is `/menu`'s named-and-counted clause (`ALSO_NAMED`) without the action verb, so each screen keeps its own action line and its own type sizes; `evidence` is the line the first draft would have assembled in the browser.
  The composer lives beside the spike in `signals.py` (pure, already imported by the mock generator), and the block's serialiser is a function the route and `generate.py` both import - not a second copy, which is what "the mock regenerated" would otherwise cost.
  The raw `items` slice is not carried: nothing on the screen would read it.
- **`/api/price-moves` gains `plates` as an additive, optional field**, composed by the same function, and `FixCallout`'s small "Also earning less" line reads it when present; its first paragraph and "check the price or the recipe" stay the card's own.
  `types.ts`'s `PriceMove.plates` is optional so a stale deploy of either half breaks nothing, `mock/menu.ts` gains the field, and `tests/test_price_moves.py` (the file that owns the route) pins it.
- **On the screen**: the panel beside "What to look at" from 1024 px, under it below; each move a plain list item with its tag ("Price moved" / "Price fell" / "Price basis changed"), the three sentences, and "See the invoice" to the line; the caption in the section head with "Every price move on Menu →"; "No price moves in this window." when there are none.
  A move that is also a signal appears in both panels with the same figure, which is the reference's own shape (its price cards sat beside the branch table) and the honest one: a spike is a move the owner should act on.

## 5. Work packages

Sizes as in `plan.md` §7.3.
Acceptance is demonstrable, never documentary.

| WP | What | Size | Depends | Acceptance |
|---|---|---|---|---|
| 97 | **The console shell with a sidebar.** `AppShell.tsx`: from 1280 px a Date Palm sidebar with the lockup, three groups, five entries, the session control and the mock chip at the foot; under 1280 px the shipped top bar untouched; each chrome's links inside a `<nav aria-label="Faida">`, one chrome displayed at a time; one `SessionMenu` instance (or one hoisted session read) for both chromes; the content column inside the remaining width. No route, no gate change, no screen file moves. Supersedes the "brand mark is the dashboard link" decision at 1280 px and above only | M | D4, D5 | `/browse` at 1440, 1280, 1024 and 390 on all five screens and both loaders: the sidebar at 1440 and 1280, the top bar at 1024 and 390; no horizontal overflow and **no clipped text** (visible-text assertions on the league's name cell and the Sales table, not only document width); one `nav` landmark in the accessibility tree; `aria-current` on the current entry only; keyboard order sidebar then content; Sign out from both chromes; **one session read per page load**; the contrast of gold on palm asserted by calculation (5.32:1) not by eye; `npm test`, `tsc`, lint, build green |
| 98 | **The headline tiles.** Four `<dl>` tiles between the answer sentences and the league (or above the sentences if D1 says so), every figure from `total` unfiltered and from `league[0]` filtered with the chain named beside, the sentences joined from fields the API sent, the status word as the shared chip, the loss component with its noun as a parameter, no icon, bar, gauge or arrow; `dashboardScreen.tiles(result)`; the section links ("Days and papers on Sales →", "Every plate on Menu →"); two by two under 1024, one column at 390; no tile on first run. No wire change. **If D7 is taken, `roundedAed` rounds half up here** and the four screens that use it are swept | S/M | D1, D2, D7 | `dashboardScreen.test.ts` pins the four tiles for full, partial, quiet, nomenu and empty (none), unfiltered and under a branch filter (the branch's figures, the chain named); `/browse` at 1280 and 390 on every scenario, the tiles reading the same figures as the league's total row unfiltered and as the branch's own row and the coverage strip filtered; if D7, `format.test` and the screenshots of `/materials`, `/menu` and `/sales` before and after |
| 99 | **Supplier price moves: the block and the panel.** API: `price_moves {count, moves[≤5]}` on the read, serialised from the moves the read already computes; the window's lower bound; the 5% gate both ways; the weighing extracted into one helper `price_spike` and the block both call, signed, ranked by magnitude; `sentence`, `plates` and `evidence` composed in a pure function in `signals.py` that the route, `/api/price-moves` (`plates`, additive and optional) and `generate.py` all import; `FixCallout`'s "Also earning less" line reads `plates`; `types.ts` and `mock/menu.ts` carry the optional field; six moves hand-authored into the generator's inputs (a rise, a second rise, a fall, a basis change, a move nothing sold after, a sub-5% drift). Web: the panel beside the signals from 1024 px, the tags, the invoice link, the Menu link, the empty sentence | M | 98's grid; D6 | `test_dashboard.py`: a fall of 5% is in the panel with negative money and not in the signals; a 0.4% fall is in neither; a basis change is in the panel with null money and sorts last; the same rise is in both with the same money, unfiltered and under `?branch=`; a move purchased before the period's start is absent; five listed of six with `count` 6; the enumerated query list unchanged. `test_signals.py` byte-identical after the extraction. `test_price_moves.py` pins `plates` and the seven shipped assertions unchanged. `/browse`: the invoice link lands on the line; the panel stacks under the signals at 390 |

Then **WP-96, the live sitting, once, on the final shape**: act four walked from `DEMO_RUNBOOK.md` §H with the tiles and the panel on the real stage, then the boxes and the records.
Recommended over a sitting now and a second one later, because the sitting is the founder's hour and the three rows above are about a day of lane work.

**Waves.** Wave 1, three lanes with no file overlap: WP-97 (`AppShell.tsx`, `SessionMenu.tsx` and its browser walk), WP-98 (`Dashboard.tsx`, `dashboardScreen.ts`, `LossFigure`, its tests, and `format.ts` if D7), WP-99's API half (`dashboard.py`, `signals.py`, `menu.py`, `test_dashboard.py`, `test_signals.py`, `test_price_moves.py`, the mock generator and its fixtures, `types.ts`'s optional field, `mock/menu.ts`).
Wave 2: WP-99's web half (`Dashboard.tsx`, `dashboardScreen.ts`, `MenuMargins.tsx`), after all three.
Wave 3: WP-96 with the founder.
The board is hand-drawn at both widths, so no design session is owed before Wave 1 unless the founder wants variants.

**The cut line, named in advance.** If the budget bites: the price-moves panel first (the spike already reaches the signals, and `/menu` has the whole list), then the sidebar (the mark-as-link shell is measured and live), never the tiles - they are the ask.

## 6. Tests that gate it, and the failure modes

- `apps/web/src/lib/__tests__/dashboardScreen.test.ts`: the four tiles per scenario and per scope, the panel's ordering as received (never re-ranked), the empty sentences.
- `apps/api/tests/test_dashboard.py`: the `price_moves` block's rules above; the enumerated query list unchanged.
- `apps/api/tests/test_signals.py`: the extracted weighing gives the spike the figure it gave before, byte for byte.
- `apps/api/tests/test_price_moves.py`: the route unchanged except for the added optional `plates`.
- Real-browser QA with `/browse` at 1440, 1280, 1024 and 390 on every screen (WP-97) and every dashboard scenario (WP-98, WP-99), asserting visible text, not only overflow.
- Regressions, mandatory: the full API suite green with zero skips, the web suite, `tsc`, lint and build green.

| Path | Realistic failure | Handling | User sees |
|---|---|---|---|
| Tiles | a tenant with sales and no menu | tiles three and four carry the no-menu sentence | "No menu is loaded, so nothing can be costed yet" |
| Tiles | a branch filter | the branch's row, the chain named beside | "AED 17,960 · Rolla" and "keeps 52.8% of costed sales · the chain keeps 60.0%" |
| Tiles | the chain loses money | the loss figure with its words | "-AED 412 · the costed sales lose money" |
| Tiles | a first run | no tiles | the shipped paragraph and its two actions |
| Tiles | sales three weeks old | the word on the net sales tile | "Estimated" beside "loaded to Mon 18 Aug" |
| Sidebar | a 1024 px laptop | the top bar, as today | nothing new, which is the point |
| Sidebar | a screen reader | one `nav` landmark, the other chrome `display:none` | one navigation, never two |
| Sidebar | mock mode | the "Sample data" chip in the sidebar foot | the chip, where the session control is |
| Price moves | a basis change | named, no number, sorts last | "Ghee is priced from a different pack now, so there is no before and after to show." |
| Price moves | a fall of 5% or more | in the panel, not in the signals | "Sugar is down AED 0.20 per kg since 28 Aug" with the dirhams it saved |
| Price moves | a 0.3% drift | in neither | nothing, which is the point |
| Price moves | a material last bought in March, window in August | not in the panel | nothing; `/menu`'s callout still shows it as the price in force |
| Price moves | a move nothing sold after | listed, money null, ranks with the basis changes | "No sales of items using it since it landed." |
| Price moves | more than five | five listed, all counted, the link | "6 materials moved this window · Every price move on Menu →" |

## 7. Decisions for the founder (each with a recommendation) - **decided 2026-09-05, every row as recommended**

**The founder's answer, 2026-09-05 evening: "Go as per your recommendation and commit."** So: D1 (a) the tiles under the answer sentences; D2 (a) the ratio as the second tile; D3 (a) the shipped picker; D4 (a) the sidebar from 1280 px; D5 confirmed; D6 (a) the panel as each material's latest move inside the window, both directions at the 5% gate plus basis changes, ranked by the money it moved; D7 (a) `roundedAed` rounds half up, owned by WP-98 with its four-screen sweep. The table below is the record of what was put to the founder and why.

Three things the first draft listed here are rules now, not decisions, because the code settles them: the tiles are the row in view with the chain named beside (§4.2); the panel is each material's latest move inside the window, gated at 5% both ways (§4.3); the panel's weighing follows the branch filter as the signals' does (§4.3).

| # | Decision | Recommendation and why |
|---|---|---|
| D1 | **Where the tiles sit.** (a) under the answer sentences; (b) above them, as the reference | **(a).** The sentences stay first because "answer first" is the rule every approved screen keeps, and a tile row above the sentence would push the conclusion below the fold on a phone. (b) is one CSS order away if the founder reads the reference's order as the point |
| D2 | **The second tile.** (a) purchases ÷ net sales (cash basis), the ratio M8 built the dashboard's first analytic to be; (b) the ingredients-and-packaging cost of what sold, the reference's "attributable material cost" - **a scope expansion**, not a choice inside the existing payload: two fields on `total` and on every league row (`costed_sales`, `cost`) | **(a).** The ratio is what the plan's own checklist put on the dashboard, it is the figure act three moves on stage, and its tile carries the purchases in dirhams beneath it; the cost of what sold is visible per dish in the item panel. (b) is honest and cheap if the founder wants the reference's tile: it is contribution's other half, and the sentence would be "AED 27,903 of ingredients and packaging in what sold" |
| D3 | **Confirm the period control.** (a) the shipped picker - 28 days, 7 days, the months that hold sales; (b) From and To inputs, which the API already accepts up to 92 days | **(a).** The reference drew (b), which is why this is asked at all; the 2026-09-03 design review pinned "a month offered always has sales", a free range that straddles unloaded days reads incomplete for a reason the owner did not choose, and (b) already has its `TODOS.md` trigger ("a pilot asks for a range the picker lacks"). Nothing is built either way |
| D4 | **The sidebar.** (a) a Date Palm sidebar from 1280 px, the top bar under it; (b) keep the top bar everywhere | **(a).** The founder drew it, the brand guide names Date Palm for navigation, and it retires the fifth-word problem for good at the widths where an owner reads a table. Under 1280 px nothing moves, so the 390 px measurement stands, and no grid is ever narrower than it has already been |
| D5 | **Confirm the entries and the groups.** OVERVIEW Dashboard; OPERATIONS Invoices, Sales; COSTING Materials, Menu | **Confirm.** The reference's Inventory and Profitability are words for screens that do not exist: Inventory is deferred beyond MVP with no customer asking, and Profitability is this screen and the Menu screen. A word can be added the day a screen exists; this is a confirmation, not a choice |
| D6 | **The price-moves panel.** (a) each material's latest move inside the window, both directions at the 5% gate plus basis changes, ranked by the money it moved, beside "What to look at"; (b) rises only, the spike's list a second time; (c) no panel - the signals carry the rise and `/menu` the rest | **(a).** The reference's cards are the PRD §27.1 "major supplier cost changes" block and the demo's money moment one screen up; both directions because a fall is a fact the owner acts on too; ranked by the dirhams it moved so the karak's milk sits above a spice nobody sells. (b) would show the same five lines twice; (c) sends the owner to `/menu` for the one thing the reference put beside the branch table |
| D7 | **The headline rounding**, already in `TODOS.md` with its trigger fired, and now with an owner: (a) `roundedAed` rounds half up, matching every API sentence - WP-98 makes the change and sweeps `/materials`, `/menu`, `/sales` and `/dashboard`; (b) it keeps truncating and the tiles inherit a one-dirham disagreement with the sentences beside them, and a negative headline stays understated | **(a).** Four whole-dirham tiles above sentences that round the other way is the reference's precision problem in miniature. It is a display-rule change (the 2026-08-30 review pinned the rule), so it is the founder's, and this is the screen that makes it worth deciding |

## 8. NOT in scope, and what already exists

**Not in scope** (each with its trigger; `TODOS.md` already carries the first three):

- A free From and To range - D3 (b); trigger: a pilot asks for a range the picker lacks.
- Charts, sparklines, gauges, progress bars, trend arrows - the reference's cost-coverage bar included; trigger: a customer asks to see a direction rather than a level (the "contribution trend over time" entry).
- A branch dashboard as its own route - `?branch=` is the bridge; trigger: WP-78's.
- A price-move **history** inside a window (every move, not the latest per material) - it needs a new read over every costed line in the window with its baseline; trigger: an owner asks why a material's price moved twice in a month and the panel shows one.
- An Inventory screen - deferred beyond MVP in `plan.md` §8 (full inventory ledger, stock counts); trigger: a customer asking, with the quote.
- A Profitability screen - it is `/dashboard` and `/menu`; nothing to build.
- A `tiles` block on the wire with the sentences composed in Python - one of the reviews proposed it; the tiles are joins of fields the API already sends, within the shipped screen's practice, and M10's brief reads `freshness`, `league[0]` and `signals` directly (P8); trigger: a second consumer of the tiles' sentences.
- Extracting `dashboard.py`'s answer and freshness composers so the mock generator stops copying them - a shipped tidy-up the same review proposed; trigger: the third copied sentence.
- Four-decimal percentages, fils in an aggregate, "food cost", "net profit", a coverage above 100 - forbidden by the display rules and C11.6, C12.7, C12.7a; never.
- Editing anything from the dashboard; a second read; a stored tile figure; a mock that computes.

**What already exists and is reused, not rebuilt:** the one read and its eighteen enumerated queries; `total`, `league`, `freshness`, `unmapped`, `menu`; `menu.price_moves` and the `PriceMove` it returns with both invoice lines; `signals.price_spike`'s sentence, gate and weighing loop; `/menu`'s `FixCallout` wording and `ALSO_NAMED`; `dashboardScreen.ts` and its test, including `coverageStrip`'s scope rule; `QualityChip`; the loss component (with one new parameter); `roundedAed`; the period picker and the branch filter; the shipped top bar and its 390 px measurement; `mock/dashboard/generate.py`; the Variant A board and `approved.json`, which stands for everything this document does not change.

## 9. Record

Recorded in `plan.md` on 2026-09-05: rows 97 to 99 in §7.3 under M9 (approved to build), one checklist line in §8 M9, two Decision Log rows (the ask planned as a delta on the live screen, translated by the display rules; then approved with every decision as recommended), one Progress Log line, and an APPROVED row in Approved Mockups pointing at the board; `TODOS.md` carries the picker-range entry's answer, the headline-rounding entry's answer, and three items this plan deferred with triggers.
The board's `approved.json` records the founder's pick of Variant D; `proposed.json` stays as the review's record.
Still a founder step before the lanes start: the screenshot into `Docs/reference/`, so the board has the thing it answers beside it. (Closed 2026-09-08, after the lanes: `Docs/reference/previous-build-dashboard-2026-09-05.jpg`, recovered from the session transcript.)

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | - | not required: the scope is the founder's own sentence, quoted in the header |
| Codex Review | `/codex review` | Independent 2nd opinion | 1 | issues_found (folded) | 14 findings: 11 folded, 2 kept with reasons, 1 deferred to `TODOS.md` with a trigger |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 0 | not run; two outside voices stood in, unattended | 15 findings from a Claude subagent: 13 folded, 1 kept with reason, 1 a founder step |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 (board drawn) | DIRECTION PROPOSED, the founder's own | the board at `designs/dashboard-main-20260905`; the attended review is owed before WP-97 starts, with the screenshot beside it |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | - | - |

Scope: the main dashboard as the founder drew it (WP-97 to WP-99), reviewed 2026-09-05 evening at master `fb19bef`, before any feature code.
Mode: unattended; every question the reviews would have put to the founder was answered with the recommended option and is recorded as **recommended, not decided**; §7 is the founder's list.

**CODEX:** ran at medium reasoning against the file path from a worktree at master and answered with 14 findings. Folded: the tiles mixed the chain's `total` with the branch-scoped `unmapped` and `league.length` under a filter (now the row in view, the coverage strip's rule); "every move in the window" is not what the newest-pair read returns (now each material's latest move, bounded to the window, and the caption says so); a fall's weighted money is negative in the shipped sign convention (now signed on the wire, ranked by magnitude, "saved" in the sentence); the panel's branch scope was undecided (now follows the filter as the signals do); the panel's evidence line would have been assembled in the browser (now `evidence` composed in Python); `test_menu.py` does not own `/api/price-moves` (`test_price_moves.py` does); `plates` on the route needs the optional TypeScript field and the menu mock in the same change; a 1024 px sidebar squeezes grids measured at 976 (now 1280); two CSS-hidden chromes do not double a landmark but a third `SessionMenu` would triple the session read (now one instance and a `<nav>` each); the net sales tile's stale word contradicted the states table (now the freshness word); acceptance criteria that tested document overflow rather than visible text, and eyeballed contrast rather than calculated it. **Kept with reasons:** (1) "no wire change for the tiles breaches C13.5" - the shipped screen already joins figures with labels in `freshnessLine`, `cardLine` and `coverageStrip`, so the tiles stay inside that practice and the `tiles` block is deferred with a trigger (§8); (2) "delete D3 and D7 and round half up without asking" - the founder's reference drew From and To, which is why D3 is asked as a confirmation, and the rounding rule was pinned by the founder's own design review, so it stays the founder's, now with an owner. **Deferred:** extracting `dashboard.py`'s composers so the generator stops copying them (§8, trigger named).

**CROSS-MODEL:** a Claude subagent reviewed the same file against the same tree and agreed with Codex on the four findings that changed the plan's shape - the tile scope under a filter, the newest-pair read, the fall's sign, and the 1024 px squeeze - and added ones Codex did not: the ungated panel would be noise on a real menu (now the 5% gate both ways); `/menu`'s card is two paragraphs and the plan's action line was the losing-money card's, not the price-move card's (now the reference's own "check the price or the recipe", and the API composes only the named-and-counted clause); WP-97's scope line forbade screen changes while its acceptance demanded a card fallback (resolved by 1280); the loss component hard-codes its noun in two copies (now a parameter); the reference screenshot is not in the repository (a founder step); "a cup" versus the shipped "a portion"; and the generator hand-builds its moves, so six must be authored (budgeted in row 99). **Kept with reason:** it read the tiles' TypeScript joins as a C13.5 breach the way Codex did, and the answer is the same. Where the two voices differed - Codex wanted a `tiles` block on the wire, the subagent wanted the C13.5 justification dropped - the plan took the subagent's route: the "one wording, two screens" argument carries the `plates` move on its own, and the tiles need no wire.

**VERDICT:** **APPROVED TO BUILD 2026-09-05.** Reviewed with two outside voices, then every §7 decision answered by the founder as recommended the same evening. No engineering question is left open: the three claims the reviews broke are rewritten against the code, every row's acceptance names the file that proves it, and the query count stays where the test pins it. The founder's pick of the board's Variant D is `approved.json`; the screenshot into `Docs/reference/` is the one founder step left before Wave 1.

NO UNRESOLVED DECISIONS
