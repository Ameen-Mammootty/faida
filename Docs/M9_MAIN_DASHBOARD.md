# The main dashboard - the founder's direction, read against the live `/dashboard` (drafted 2026-09-05)

Status: **drafted 2026-09-05, evening, after M9's rows 90 to 95 shipped and before WP-96's live sitting; proposed, not decided.**
The founder asked for it in one sentence, showing a screenshot of the previous build's dashboard: *"I would also want a main dashboard something like the above, make a plan for the same"* (2026-09-05).
That sentence is the customer quote `plan.md` §2 rule 8 requires, and it is the founder's own, so the scope is admitted; what this document does is read the reference against what is already live, translate it through the product's display rules, and hand back seven decisions.
Nothing below is approved to build until the founder answers §7.
The session that wrote it ran unattended, so every choice is **recommended, never decided**, in the M9 decomposition's own convention.

Facts in §2 are from master `fb19bef` (the drill live on both hosts; WP-96 open).

Plan reference: `plan.md` §8 M9 (the checklist and the done-when), §3 (the display rules), §7.2 C12, C13 and the C9 and C6 extensions; `Docs/M9_DECOMPOSITION.md` §3.1 (the wire), §4.1 (the design direction as amended by the 2026-09-05 design review), §5 (the ten decided proposals); the Approved Mockups row for `/dashboard` (Variant A, picked 2026-09-05 11:05); `Docs/brand/faida-brand-guidelines.md` (Date Palm for navigation; "avoid dashboard decoration without informational purpose"); CLAUDE.md's product display rules.

## 1. What the founder asked for, and what the reference is

The screenshot (`Screenshot 2026-09-05 005021.png`, taken at 00:50 on 2026-09-05, before the design review that picked Variant A at 11:05) is the **previous build's** dashboard, run locally at `localhost:3000/dashboard`.
None of its labels exist in this codebase: `git grep` on master finds no "Executive Dashboard", no "Inventory" screen and no "Profitability" screen under `apps/web/src`, and its percentages carry four decimals where every figure this API sends is a one-decimal string.
So the reference is a picture of a shape the founder liked, not a screen to restore, and its numbers are the old build's problems (a cost coverage of 109.0971% beside an "unavailable" chip is exactly the contradiction C9 was written to forbid).

Read element by element, against what is live today:

| Reference element | What it shows | What the live `/dashboard` (Variant A) has | Gap |
|---|---|---|---|
| Heading "Executive Dashboard" and the tagline "Profit visibility, sales cost coverage, and supplier price moves." | a name and a static line | "Dashboard", the freshness line, then **two answer sentences** naming the branch and the dish to look at first | none worth keeping: the sentences say what the tagline promised |
| Branch select "All branches" | one branch or all | the branch filter, writing `?branch=` into the URL; the chain total never follows it (P7) | none |
| From and To date inputs | a free range | the period picker: last 28 days, last 7 days, each calendar month that holds sales; the API takes any `from` and `to` up to 92 days | a control, not a capability - §7 D3 |
| Four tiles: Pre-tax net sales AED 241.00; Attributable material cost AED 44.845; Known contribution AED 196.155, "81.3921% contribution margin"; Cost coverage 109.0971% with a bar | the headline figures | every one of these figures is on the wire already, in `total`, `freshness` and `unmapped` - shown in the league's total row and the coverage strip, never as tiles | **the tiles are new**; the words and the precision change (§3) |
| Branch performance: Branch, Net sales, Known contribution, Margin %, Cost coverage, Quality; "Detailed Profitability →" | the ranked branches | the league: Branch, Net sales, Purchases ÷ net sales, Contribution (est.), Kept, Status, with the window and the costed share under the name and the status; ranked by Kept lowest first; a branch name opens `/sales#branch-<id>` | a section link, and the costed share as a column if the founder wants one |
| Top menu items: name, "40 sold · AED 200.00 sales", AED 172.947, "86.4735% margin"; "All recipes & margins →" | the best dishes | "Items: what each one contributed": Sold, Net sales, Contribution, Kept, **five best and five worst**, expanding in place to every ingredient's invoice line | a section link; the reference shows only the top |
| Supplier price movements: cards tagged "Price moved" - "Bun is up AED 1.10 each since 4 Sep 2026. Spicy Moon Burger earns AED 2.20 less a portion - check the price or the recipe. was AED 0.10 each · See the invoice"; "All materials →" | every recent move, with the plate it hurts | a price **rise** of 5% or more appears in "What to look at" as one of three signal kinds, ranked by money at stake among them and capped at five in total; the full list with both directions lives on `/menu`'s callout and `/materials` | **the panel is new**; the wording exists almost verbatim in `signals.price_spike` and `/menu`'s `FixCallout` |
| Sidebar: OVERVIEW Dashboard; OPERATIONS Invoices, Sales, Inventory; PERFORMANCE Profitability; SETUP Materials, Menu | grouped navigation on Date Palm | a top bar: the brand mark is the dashboard link (a fifth word does not fit 390 px, measured), then Invoices, Materials, Menu, Sales | **the sidebar is new**; Inventory and Profitability have no screen here (§3) |

The reading is that **the data, the ranking, the drill and the landing already exist**, shipped this morning to the shape the founder picked on the board; what the reference adds is a layout (tiles and a sidebar) and one panel (price moves as a block of their own).
That is the whole plan: a delta on the live screen, never a second screen and never a rebuild.

## 2. What is already live, and what it forbids the plan from doing twice

- **One read serves the whole screen.** `GET /api/dashboard?from&to&branch_id` (`dashboard.py`) returns `period`, `answer`, `freshness`, `latest_day`, `approvals`, `league`, `unassigned`, `scope`, `total`, `items`, `signals`, `unmapped` and `menu`, from an enumerated set of eighteen reads whose count is pinned flat by `test_dashboard.py`.
  A tile is a projection of `total`; a second read for a tile would breach P9 and the query-count test both.
- **`total` already carries every headline figure the tiles need**: `net_sales`, `purchases`, `ratio_pct`, `contribution`, `contribution_pct`, `costed_share_pct`, and the two quality words with their notes (`types.ts:1219-1230`).
  `freshness.sentence` is the freshness line; `unmapped {names, value}` is the costed-share tile's second line; `menu {items, costed}` says whether anything can be costed at all.
- **The price moves are already computed inside the read and thrown away.** `dashboard.py:417-418` builds `pairs` bounded by `as_of=period.end` and calls `menu.price_moves(...)` to feed the spike signal; the resulting `PriceMove` list (`menu.py:765-786`: both lines with their invoice ids and positions, the delta per display unit, and `items` with the per-plate impact and the margin either side) is never serialised.
  The panel is a serialisation of a value the read holds, not a computation.
- **The sentences are Python's.** C13.5: every sentence that states a fact or a number is composed on the API and carried on the wire; the screen frames, joins and links.
  `signals.price_spike` already composes "Milk Powder is up AED 1.60 per kg since 25 Aug" and "AED 210 off contribution on the 1,240 portions sold since it landed, across 4 items" (`signals.py:344-361`); `/menu`'s callout composes the plate line in TypeScript today ("earns AED 0.13 less a portion", three named, the rest counted - `ALSO_NAMED`, `MenuMargins.tsx:147-160`), which is the one sentence about a number the web still owns and which the panel must not copy a second time.
- **The screen's decisions live in `dashboardScreen.ts`** (52 exports, pinned by `dashboardScreen.test.ts`), because there is no component-rendering test capability; the tiles and the panel add functions there, and the component renders what they return.
- **The mock computes nothing**: `mock/dashboard/*.json` are produced by `generate.py` running the shipped Python over a hand-built week (Decision Log 2026-09-05); a `price_moves` block is added by regenerating, never by typing.
- **The shell is measured.** `AppShell.tsx` records that four nav words fill the top row at 390 px, which is why the brand mark became the dashboard link this morning; the sidebar the founder drew changes the premise at desktop widths only.
- **The first-run rule stands**: "no tiles, no zeros: one paragraph and the one link that changes the state" (the approved first-run state).
  Tiles appear when there is something to count and never before.
- **Two decisions already wait on the founder in `TODOS.md`** and the tiles make one of them louder: the headline rounding (`roundedAed` truncates while every API sentence rounds half up; "fired, on the dashboard's signal line") becomes four whole-dirham figures beside sentences that round the other way.

## 3. The translation the product's rules force

The reference's words and precision are the old build's.
This build has display rules pinned in `plan.md` §3, CLAUDE.md and the 2026-08-30 design review, and contracts C11.6 and C12.7 that name forbidden phrases.
Every label below is the reference's, then what the screen says instead, then why.

| The reference says | The screen says | Why |
|---|---|---|
| Executive Dashboard | Dashboard | the product's voice is an operator's, not an executive summary's; the heading is the nav word |
| Profit visibility, sales cost coverage, and supplier price moves. | the two answer sentences | a tagline is decoration; the sentences are the conclusion (the approved "answer first" rule) |
| Pre-tax net sales · AED 241.00 · "All committed sales" | Net sales · AED 69,707 · "from the till, net of VAT · 3 branches · loaded to Mon 31 Aug" | rounded AED in a headline (§3); "committed" is not a word this product uses - a loaded day is a fact, not a commitment |
| Attributable material cost · AED 44.845 · "Costed from confirmed supplier purchases" | Purchases ÷ net sales (cash basis) · 17.1% · "AED 11,899 of confirmed papers in this window" · status word | M8's own checklist puts "the first analytic on the dashboard: purchases ÷ net sales"; fils in an aggregate are forbidden; the alternative is §7 D2 |
| Known contribution · AED 196.155 · "81.3921% contribution margin" | Contribution before overheads (estimate) · AED 41,804 · "keeps 60.0% of costed sales · after ingredients and packaging" · status word | C12.7: never "net profit", never "profit", and always "which share it covers"; one decimal on a percentage (C11) |
| Cost coverage · 109.0971% · a chip "unavailable" · a progress bar | Costed share of sales · 77% · "3 till names worth AED 8,320 have no dish yet · Map them on Sales" | C12.7a bounds the share 0-100 and derives it from the rows; "costed", never "complete" or "coverage"; a bar without the number beside it carries meaning by colour alone, so the number is the tile and there is no bar |
| Branch performance · Known contribution · Margin % · Cost coverage · Quality | the league's own words: Contribution (est.), Kept, Status, and "covers 78% of sales value" under the status | the league is shipped; the column names are C12's |
| Detailed Profitability → | Days and papers on Sales → | there is no profitability screen; `/sales` holds the days, the papers and the queue |
| Top menu items · "86.4735% margin" | Items: what each one contributed · best five and worst five · Kept 81.4% | the done-when asks "which item is hurting me", which the top five cannot answer; one decimal |
| All recipes & margins → | Every plate on Menu → | `/menu` is where the plate and its ingredients live |
| Supplier price movements · "Price moved" | Supplier price moves · "Price moved" / "Price fell" / "Price basis changed" | the tag pattern is kept; a fall and a basis change are named as what they are, never dressed as a spike |
| "check the price or the recipe" | "Reprice it or trim the recipe" | `/menu`'s own action line, so the two screens speak one sentence |
| All materials → | Every price move on Menu → | the full list with both packs named is `/menu`'s callout and `/materials`; the panel shows five and counts the rest |
| OVERVIEW Dashboard / OPERATIONS Invoices, Sales, Inventory / PERFORMANCE Profitability / SETUP Materials, Menu | OVERVIEW Dashboard / OPERATIONS Invoices, Sales / COSTING Materials, Menu | there is no inventory (deferred beyond MVP, `plan.md` §8, with no customer quote) and no profitability screen (it is this screen and the Menu screen); Materials and Menu are costing screens, not setup |
| From · To | Last 28 days / Last 7 days / the months with sales | the 2026-09-03 design review's rule, "a month offered always has sales"; the API takes a free range already, so this is D3 and one control if the founder wants it |

## 4. The proposed screen

Reader order at 1280 px: the sidebar; the heading with the controls on its right (the reference's placement); the freshness line; the two answer sentences; the four tiles; the league; two columns - what to look at, and the supplier price moves; the items; the coverage strip.
The sentences stay above the tiles because a sentence is a conclusion and a tile is a fact about its size; the reference puts the tiles first, and §7 D1 lets the founder flip that.

```
 ┌ sidebar (Date Palm) ─┐ ┌────────────────────────────────────────────────────────────────────────────┐
 │ ▣ faida              │ │ Dashboard                     [Last 28 days | Last 7 days | Aug 2026]  [All branches ▾] │
 │                      │ │ Sales loaded to Mon 31 Aug, 5 days ago · AED 9,856 taken that day · 3 papers waiting     │
 │ OVERVIEW             │ │                                                                                          │
 │ ● Dashboard          │ │ Look at Rolla first: it keeps about AED 53 of every 100 it takes, the least of the three. │
 │                      │ │ Chicken 65 Dry sells more than any dish that earns under the menu's average.             │
 │ OPERATIONS           │ │                                                                                          │
 │   Invoices           │ │ ┌ NET SALES ──────┐ ┌ PURCHASES ÷ NET SALES ┐ ┌ CONTRIBUTION (EST.) ┐ ┌ COSTED SHARE ──┐ │
 │   Sales              │ │ │ AED 69,707      │ │ 17.1%                 │ │ AED 41,804          │ │ 77%            │ │
 │                      │ │ │ from the till,  │ │ AED 11,899 of         │ │ keeps 60.0% of      │ │ 3 till names   │ │
 │ COSTING              │ │ │ net of VAT ·    │ │ confirmed papers ·    │ │ costed sales, after │ │ worth AED 8,320│ │
 │   Materials          │ │ │ 3 branches      │ │ Incomplete: 1 of 3    │ │ ingredients and     │ │ have no dish   │ │
 │   Menu               │ │ │                 │ │ branches has no papers│ │ packaging · Incomplete│ │ Map them →   │ │
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
 │                      │ │ ┌ What to look at (3) ───────────────────────┐ ┌ Supplier price moves (6) ─────────────┐ │
 │                      │ │ │ Rolla keeps 7.2 points less ...  AED 1,293 │ │ PRICE MOVED                            │ │
 │                      │ │ │ Chicken 65 Dry sold AED 3,120 ...  AED 593 │ │ Milk Powder is up AED 1.60 per kg      │ │
 │                      │ │ │ Milk Powder is up AED 1.60 per kg  AED 210 │ │ since 25 Aug. Karak Tea earns AED 0.13 │ │
 │                      │ │ └────────────────────────────────────────────┘ │ less a cup; also Karak Tea - Flask 1 L │ │
 │                      │ │                                                │ (-0.07) and 2 more.                    │ │
 │                      │ │                                                │ was AED 22.40 per kg · AED 210 at stake│ │
 │                      │ │                                                │ · See the invoice                      │ │
 │                      │ │                                                │ PRICE FELL   Sugar is down AED 0.20 ...│ │
 │                      │ │                                                │ PRICE BASIS CHANGED  Ghee is priced    │ │
 │                      │ │                                                │ from a different pack now ...          │ │
 │ owner@koukh.ae       │ │                                                └ Every price move on Menu →            ┘ │
 │ Sign out             │ │                                                                                          │
 │ Profit, in plain     │ │ Items: what each one contributed      41 costed of 45 · Every plate on Menu →  Show all │
 │ sight.               │ │ ┌ Best  Karak Tea - Flask 1 L   412   AED 13,733   AED 11,177   81.4% ┐  (the shipped  │
 └──────────────────────┘ │ │ ...   Worst  Chicken 65 Dry    74   AED  3,120   AED  1,279   41.0% │   panel)       │
                          │ └─────────────────────────────────────────────────────────────────────┘                 │
                          │ ┌ mist: These figures cover 77% of what was sold. 3 till names ... Map them on Sales → ┐ │
                          └────────────────────────────────────────────────────────────────────────────────────────┘
```

The board at `~/.gstack/projects/Ameen-Mammootty-faida/designs/dashboard-main-20260905/wireframes.html` draws this at 1160 px with the real tokens and at 390 px, beside the approved Variant A for comparison; `proposed.json` sits next to it and becomes `approved.json` when the founder picks.

### 4.1 The sidebar (WP-97)

- **At 1024 px and above**, a 232 px Date Palm column: the mark and the wordmark at the top (the brand guide's horizontal lockup, never below 120 px), three group captions in small caps, five entries, the current one marked with `aria-current="page"` and a Karak Gold bar at its left edge plus bold weight (the word and the weight carry the state; the gold is the third cue, never the only one); at the foot, who is signed in, Sign out, and the line "Profit, in plain sight." which the footer carries today.
  Text is Warm Cream on Date Palm; the focus ring is Karak Gold on the palm ground because the palm ring the app uses elsewhere would vanish on itself.
- **Under 1024 px, nothing changes**: the shipped top bar stays exactly as measured - the mark as the dashboard link, the four words, the quiet second row on a phone.
  The 2026-09-05 decision "the brand mark is the dashboard link" therefore stands where it was measured and is superseded only where there is room for the word.
- **The content column** keeps `max-w-6xl` inside the remaining width; at 1280 px that is about 1000 px of content, at 1024 px about 760, and every fixed `colgroup` the tables use (`SalesTable` at 30/16/16/18/20, `MenuMargins`' shared category grid, the dashboard's league and items) has to be walked at 1024 px because that width did not exist for them before.
- **Groups and words**: OVERVIEW - Dashboard; OPERATIONS - Invoices, Sales; COSTING - Materials, Menu.
  The loaders (`/menu/load`, `/sales/load`) stay out of the nav, as decided for `/sales`; they are reached from their screens.
- **One layout answer for every screen**: `AppShell` renders both chromes and CSS picks; the `Screen` union and every layout's `current` prop are unchanged, so no screen file moves.

### 4.2 The tiles (WP-98)

Four, on paper, in one row from 1024 px, two by two under it, one column at 390 px.
Each is a `<dl>`: a small-caps `<dt>`, the figure as a Manrope headline with tabular numerals, one sentence, and the status word as the shared `QualityChip` where the figure has one.
No icon, no gauge, no bar, no sparkline, no trend arrow: the brand guide's "dashboard decoration without informational purpose" is exactly the reference's progress bar, and the figure beside it says everything the bar would.

| Tile | Figure | Sentence beneath | Status | From |
|---|---|---|---|---|
| Net sales | `total.net_sales`, rounded AED | "from the till, net of VAT · N branches · loaded to `<weekday date>`" | none (a loaded day is a fact) | `total`, `league.length`, `freshness` |
| Purchases ÷ net sales (cash basis) | `total.ratio_pct` + "%", or "No confirmed purchases" | "AED `<purchases>` of confirmed papers in this window" | `total.ratio_quality` and its first note | `total` |
| Contribution before overheads (estimate) | `total.contribution`, rounded AED; `/menu`'s `LossFigure` when negative | "keeps `<contribution_pct>`% of costed sales · after ingredients and packaging" | `total.contribution_quality` and its first note | `total` |
| Costed share of sales | `total.costed_share_pct` + "%" | "`<names>` till names worth AED `<value>` have no dish yet" with the link to the queue, or "Every till name is mapped." | none (a share is a fact about the rows) | `total.costed_share_pct`, `unmapped` |

States: **first run** - no tiles (the paragraph stands); **no menu** - the first two tiles show and the third and fourth say "No menu is loaded, so nothing can be costed yet" (`noMenuSentence`); **branch filter** - the tiles stay the chain's, captioned "All branches", because `total` never follows the filter and a tile that silently switched scope would be the reference's 109% all over again; **stale** - the net sales tile carries the word "Estimated" beside its date when `freshness.quality` is; **error** - the strip, no tiles.

No wire change.
`dashboardScreen.ts` gains `tiles(result): Tile[]` and `dashboardScreen.test.ts` pins the four tiles per scenario.
`format.ts` is untouched: `roundedAed` for the money and the API's one-decimal strings for the percentages.

### 4.3 The supplier price moves panel (WP-99)

**On the wire**, one block added to `GET /api/dashboard` (C6 extended once more; the query count does not move because the moves are already in hand):

```
"price_moves": {"count": 6, "moves": [       (at most five, ranked; count is the whole number)
  {"ingredient_id": "…", "ingredient_name": "Milk Powder",
   "kind": "moved" | "basis_changed", "direction": "up" | "down" | null,
   "display_unit": "kg", "was": "22.40", "now": "24.00", "delta_per_display_unit": "1.60",
   "moved_on": "2026-08-25", "previous_on": "2026-03-12",
   "invoice_id": "…", "line_position": 3,                       (the newest line, for /invoices/<id>#line-<n>)
   "money_at_stake": "210.40" | null, "portions_since": "1240" | null,
   "sentence": "Milk Powder is up AED 1.60 per kg since 25 Aug.",
   "plates": "Karak Tea earns AED 0.13 less a cup; also Karak Tea - Flask 1 L (-0.07) and 2 more.",
   "items": [{"menu_item_id": "…", "name": "Karak Tea", "impact_per_portion": "-0.130"}]   (three at most)}
]}
```

- **Both directions and basis changes**, because the panel answers "what moved" and the signals panel answers "what to look at"; a fall is good news the owner should see, and C13's "a fall stays on `/menu`" was a rule about the *signals* list, which is unchanged.
- **Ranked by money at stake, then by the largest per-plate impact, then by name** - the spike's own weighing (the per-plate impact times the portions sold on or after the move, inside the window) extracted from `signals.price_spike` into one pure helper both callers use, so a rise carries the same dirhams in both panels and a fall carries the dirhams it saved; a basis change carries no number and sorts last among its day.
- **The sentences are Python's**: `sentence` is the spike's own wording generalised to "is down" and to the basis-change sentence `/menu` composes today; `plates` is the callout's three-named-then-counted rule (`ALSO_NAMED`) moved to the API, and `/menu`'s `FixCallout` reads it from the price-moves route in the same commit so the app composes it once.
- **On the screen**: the panel beside "What to look at" from 1024 px, under it below; each move a plain list item with its tag, the sentence, the plates line, "was AED 22.40 per kg · AED 210 at stake since 25 Aug", and "See the invoice"; "Every price move on Menu →" in the section head; "No price moves in this window." when there are none.
  A move that is also a signal appears in both panels with the same figure, which is the reference's own shape (its price cards sat beside the branch table) and the honest one: a spike is a move the owner should act on.

## 5. Work packages

Sizes as in `plan.md` §7.3.
Acceptance is demonstrable, never documentary.

| WP | What | Size | Depends | Acceptance |
|---|---|---|---|---|
| 97 | **The console shell with a sidebar.** `AppShell.tsx`: from 1024 px a Date Palm sidebar with the lockup, three groups, five entries, the session at the foot; under 1024 px the shipped top bar untouched; the content column inside the remaining width; `SessionMenu` rendered in whichever chrome is showing. No route, no gate change, no screen file moves. Supersedes the "brand mark is the dashboard link" decision at 1024 px and above only | M | D4, D5 | `/browse` at 1280, 1024 and 390 on all five screens and both loaders: no horizontal overflow anywhere, every fixed `colgroup` still fits at 1024, the current entry carries `aria-current` and reads as current without colour, keyboard order runs sidebar then content, Sign out works from both chromes, the gold focus ring meets contrast on palm; `npm test`, `tsc`, lint, build green |
| 98 | **The headline tiles.** Four tiles between the answer sentences and the league (or above the sentences if D1 says so), every figure from `total`, `freshness`, `unmapped` and the league's length; `dashboardScreen.tiles(result)` returning label, figure, sentence and quality word; the shared chip; `LossFigure` for a negative contribution; the section links in the league and item heads ("Days and papers on Sales →", "Every plate on Menu →"); two by two under 1024, one column at 390; no tile on first run. No wire change | S/M | D1, D2 | `dashboardScreen.test.ts` pins the four tiles for full, partial, quiet, nomenu and empty (none) and the chain caption under a branch filter; `/browse` at 1280 and 390 on every scenario, the tiles reading the same figures as the league's total row |
| 99 | **Supplier price moves: the block and the panel.** API: `price_moves` on the read, serialised from the moves the read already computes; the weighing extracted from `price_spike` into one helper; `sentence` and `plates` composed in Python; `/menu`'s route carries `plates` too and `FixCallout` stops composing it; the mock regenerated. Web: the panel beside the signals from 1024 px, the tags, the invoice link, the Menu link, the empty sentence | M | 98's grid; D6 | `test_dashboard.py`: a fall is in the panel and not in the signals; a basis change is in the panel with no number; the same rise is in both with the same money; a move with no sales after it ranks last; five listed of six with `count` 6; the query list unchanged; `test_menu.py` green with the callout's line now on the wire; `/browse`: the invoice link lands on the line, the panel stacks under the signals at 390 |

Then **WP-96, the live sitting, once, on the final shape**: act four walked from `DEMO_RUNBOOK.md` §H with the tiles and the panel on the real stage, then the boxes and the records.
Recommended over a sitting now and a second one later, because the sitting is the founder's hour and the three rows above are about a day of lane work.

**Waves.** Wave 1, three lanes with no file overlap: WP-97 (`AppShell.tsx` and its browser walk), WP-98 (`Dashboard.tsx`, `dashboardScreen.ts`, its tests), WP-99's API half (`dashboard.py`, `signals.py`, `menu.py`, `test_dashboard.py`, the mock generator).
Wave 2: WP-99's web half, after all three.
Wave 3: WP-96 with the founder.
The board is hand-drawn at both widths, so no design session is owed before Wave 1 unless the founder wants variants.

**The cut line, named in advance.** If the budget bites: the price-moves panel first (the spike already reaches the signals, and `/menu` has the whole list), then the sidebar (the mark-as-link shell is measured and live), never the tiles - they are the ask.

## 6. Tests that gate it, and the failure modes

- `apps/web/src/lib/__tests__/dashboardScreen.test.ts`: the four tiles per scenario, the chain caption under a filter, the panel's ordering as received (never re-ranked), the empty sentences.
- `apps/api/tests/test_dashboard.py`: the `price_moves` block's rules above; the enumerated query list unchanged.
- `apps/api/tests/test_signals.py`: the extracted weighing gives the spike the figure it gave before, byte for byte.
- `apps/api/tests/test_menu.py`: the price-moves route unchanged except for the added `plates` sentence.
- Real-browser QA with `/browse` at 1280, 1024 and 390 on every screen (WP-97) and every dashboard scenario (WP-98, WP-99).
- Regressions, mandatory: the full API suite green with zero skips, the web suite, `tsc`, lint and build green.

| Path | Realistic failure | Handling | User sees |
|---|---|---|---|
| Tiles | a tenant with sales and no menu | tiles three and four carry the no-menu sentence | "No menu is loaded, so nothing can be costed yet" |
| Tiles | a branch filter | the tiles stay the chain's and say so | "All branches" under each figure |
| Tiles | the chain loses money | `LossFigure` | "-AED 412 · this chain's costed sales lose money" |
| Tiles | a first run | no tiles | the shipped paragraph and its two actions |
| Sidebar | a 1024 px laptop with the Sales table | the colgroup walked at that width | a table that fits, or a card layout at that width if it cannot |
| Sidebar | a screen reader | `<nav aria-label="Faida">` once, in whichever chrome shows | one navigation landmark, never two |
| Price moves | a basis change | named, no number, sorts last | "Ghee is priced from a different pack now, so there is no before and after to show." |
| Price moves | a fall | in the panel, not in the signals | "Sugar is down AED 0.20 per kg since 28 Aug" with the dirhams it saved |
| Price moves | a move nothing sold after | ranks last | "No sales of items using it since it landed." |
| Price moves | more than five | five listed, all counted, the link | "6 this window · Every price move on Menu →" |

## 7. Decisions for the founder (each with a recommendation)

| # | Decision | Recommendation and why |
|---|---|---|
| D1 | **Tiles, and where.** (a) four tiles under the answer sentences; (b) four tiles above them, as the reference; (c) none, the approved Variant A as is | **(a).** The tiles are the ask and they cost no wire; the sentences stay first because "answer first" is the rule every approved screen keeps, and a tile row above the sentence would push the conclusion below the fold on a phone. (b) is one CSS order away if the founder reads the reference's order as the point |
| D2 | **The second tile.** (a) purchases ÷ net sales (cash basis), the ratio M8 built the dashboard's first analytic to be; (b) the ingredients-and-packaging cost of what sold, the reference's "attributable material cost", which needs two fields on `total` (`costed_sales`, `cost`) | **(a).** The ratio is what the plan's own checklist put on the dashboard, it is the figure act three moves on stage, and its tile carries the purchases in dirhams beneath it; the cost of what sold is visible per dish in the item panel. (b) is honest and cheap if the founder wants the reference's tile: it is contribution's other half, and the sentence would be "AED 27,903 of ingredients and packaging in what sold" |
| D3 | **The period control.** (a) the shipped picker - 28 days, 7 days, the months that hold sales; (b) From and To inputs, which the API already accepts up to 92 days | **(a).** The 2026-09-03 design review pinned "a month offered always has sales"; a free range that straddles unloaded days reads incomplete for a reason the owner did not choose. (b) is one control and its `TODOS.md` trigger ("a pilot asks for a range the picker lacks") is the honest moment for it |
| D4 | **The sidebar.** (a) a Date Palm sidebar from 1024 px, the top bar under it; (b) keep the top bar everywhere | **(a).** The founder drew it, the brand guide names Date Palm for navigation, and it retires the fifth-word problem for good at the widths where an owner reads a table. Under 1024 px nothing moves, so the 390 px measurement stands |
| D5 | **The entries and the groups.** (a) OVERVIEW Dashboard; OPERATIONS Invoices, Sales; COSTING Materials, Menu; (b) the reference's seven, with Inventory and Profitability | **(a).** Inventory has no screen and is deferred beyond MVP with no customer asking; Profitability is this screen and the Menu screen, and a nav word for a page that does not exist is the reference's problem, not its shape. A word can be added the day a screen exists |
| D6 | **The price-moves panel.** (a) every move in the window, both directions and basis changes, ranked by money at stake, beside "What to look at"; (b) rises only, the spike's list a second time; (c) no panel - the signals carry the rise and `/menu` the rest | **(a).** The reference's cards are the PRD §27.1 "major supplier cost changes" block and the demo's money moment one screen up; both directions because a fall is a fact the owner acts on too; ranked by the dirhams it moved so the karak's milk sits above a spice nobody sells. (b) would show the same five lines twice; (c) sends the owner to `/menu` for the one thing the reference put beside the branch table |
| D7 | **The headline rounding**, already in `TODOS.md` with its trigger fired: (a) `roundedAed` rounds half up, matching every API sentence; (b) it keeps truncating and the tiles inherit a one-dirham disagreement with the sentences beside them | **(a).** Four whole-dirham tiles above sentences that round the other way is the reference's precision problem in miniature. It is a display-rule change (the 2026-08-30 review pinned the rule), so it is the founder's, and this is the screen that makes it worth deciding |

## 8. NOT in scope, and what already exists

**Not in scope** (each with its trigger; `TODOS.md` already carries the first three):

- A free From and To range - D3 (b); trigger: a pilot asks for a range the picker lacks.
- Charts, sparklines, gauges, progress bars, trend arrows - the reference's cost-coverage bar included; trigger: a customer asks to see a direction rather than a level (the "contribution trend over time" entry).
- A branch dashboard as its own route - `?branch=` is the bridge; trigger: WP-78's.
- An Inventory screen - deferred beyond MVP in `plan.md` §8 (full inventory ledger, stock counts); trigger: a customer asking, with the quote.
- A Profitability screen - it is `/dashboard` and `/menu`; nothing to build.
- Four-decimal percentages, fils in an aggregate, "food cost", "net profit", a coverage above 100 - forbidden by the display rules and C11.6, C12.7, C12.7a; never.
- Editing anything from the dashboard; a second read; a stored tile figure; a mock that computes.

**What already exists and is reused, not rebuilt:** the one read and its eighteen enumerated queries; `total`, `freshness`, `unmapped`, `menu`; `menu.price_moves` and the `PriceMove` it returns with both invoice lines; `signals.price_spike`'s sentence and weighing; `/menu`'s `FixCallout` wording and `ALSO_NAMED`; `dashboardScreen.ts` and its test; `QualityChip`; `LossFigure`; `roundedAed`; the period picker and the branch filter; the shipped top bar and its 390 px measurement; `mock/dashboard/generate.py`; the Variant A board and `approved.json`, which stands for everything this document does not change.

## 9. Record

Recorded in `plan.md` on 2026-09-05 as proposed: rows 97 to 99 in §7.3 under M9, one checklist line in §8 M9, one Decision Log row (the ask is planned as a delta on the live screen, translated by the display rules), one Progress Log line, and a PROPOSED row in Approved Mockups pointing at the board; `TODOS.md`'s picker-range entry notes that the founder's reference drew one.
The founder's answers to §7 turn "proposed" into "approved to build" and `proposed.json` into `approved.json`.

## Review

None yet.
This is a direction document written unattended in one session, not a decomposition: it adds no table, no route and one block to an existing read, so the engineering questions are small and named in §5's acceptance.
The reviews the repo's precedent owes before a line is coded are `/plan-design-review` on the board with the founder present (the three earlier screens each had one) and, if the founder wants it, a Codex pass on this file at medium reasoning against the path, which is the form that has worked here.
