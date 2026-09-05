# M12 decomposition - theoretical usage vs purchases (drafted 2026-09-05)

Status: **drafted 2026-09-05, not yet reviewed, awaiting the founder's answers to §5.**
No outside voice has read it yet: M8 and M9 each had a Codex review at medium reasoning against the file path before the founder decided, and the same path is recommended here (`/plan-eng-review` on this file, then the founder's sitting).
Nothing in §4 is approved to build.
M12 entered the plan on 2026-09-05 by the founder's call after a question about how inventory is handled; the customer sentence §2 rule 8 asks for is owed on its Decision Log row, and `plan.md` §8 names the trigger to build as the pilot's till file showing a quantity column.

Facts in §2 are from master `fb19bef` (the drill live, WP-96 still open), so the review argues about the plan and not about the state.

Plan reference: `plan.md` §8 M12 (the checklist and the done-when), §1 (the north star), §2 (the standing rules), §3 (the fixed decisions and the display rules), §7.2 C4 (money), C8 (provenance), C9 and its amendment and extension (derived quality), C11 (the sales row and the ratio), C12 (contribution), C13 (signals), C6 extended (the dashboard read); PRD §17-18 (ingredients and units), §19 (costing), §22 (the inventory ledger, whose theoretical sale consumption this computes and posts nowhere), §24 (data quality), §25.3 (signals), §27.1 (the owner dashboard's "inventory warnings").

## 1. What M12 is for

`plan.md` §8 says it in its own words, quoted whole because every row below answers one of them:

> ### M12 - Theoretical usage vs purchases
> What the period's sales needed of each raw material, against what was bought of it, per branch - with no count, no ledger and no new habit asked of the cafeteria.
> - [ ] Used, per (material, branch, period): portions sold of each mapped menu item × the current recipe version's component quantity ÷ its yield, converted to the material's base unit the way `plates.py` converts a component; packaging counts (a cup is a `pc` material). A line with no quantity, a dish with no recipe and an unmapped till name each leave the figure and lower a stated share ...
> - [ ] Bought, per (material, branch, period): the confirmed stock lines of papers dated in the window whose pack maps to the material, line qty × the pack's base quantity from the line's stored cost basis. A return line nets out; a blocked line (no pack size) makes the row incomplete and names the count; a paper with no branch counts in the chain row only ...
> - [ ] The gap, both ways: bought − used in the material's display unit (kg, L, pieces) and in money at the period's price per base unit ..., ranked by money per branch with the chain total. Used above bought over a whole window is the useful direction - a recipe quantity or a pack size is wrong - and the sentence says that, never "stock is negative".
> - [ ] Quality in the C9 vocabulary, never verified ... the period defaults to the ratio's 28 days (C11.6) and the row names how many purchases sit in the window, because one sack bought on the window's last day is not a rate.
> - [ ] One screen and one sentence, the home decided at decomposition ...; at most one signal added to C13 ... and at most one brief slot, both decided there too.
> - **Done when:** an owner can answer "which material and which branch is buying more than its sales needed, and what that costs" from one screen, every number reaches an invoice line or a sales day, and no word on the screen claims a count that was never made.
> - **Not in M12, by decision:** stock on hand, counts, waste and transfer entries, the append-only ledger, goods receipts, and the word variance.

M6 costs a plate: a karak needs 5.5 g of tea dust and 55 ml of evaporated milk.
M8 says how many karaks each branch sold.
M9 multiplied the two into money and asked "what did the branch keep".
M12 multiplies the same two into **quantities** and asks the question one shelf down: the branch sold 1,400 karaks, so its recipes needed 7.7 kg of tea dust; the confirmed papers say it bought 12 kg; where is the difference, and what did it cost.

It is the second milestone in a row that adds **no new data**.
The used side is the till's quantity column times the recipe's quantities, both held since M6 and M8.
The bought side is each confirmed stock line's quantity times the pack size WP-53 already divided its price by, frozen on the line at confirm.
There is no new source, no new upload, no new channel, no new table, and - as with M9 - no migration.
What M12 adds is the multiplication, one new read over invoice lines, one block on the dashboard read, one panel on the dashboard, and the honesty rules that keep a gap from being called something it is not.

**What it is not, said first because every reviewer will ask.** Bought minus used is not stock lost.
The difference is on the shelf, in the bin, or unrecorded, and no count says which.
So the figure is never labelled variance, waste, theft, shrinkage or loss, on any surface, in any sentence; the standing sentence beneath the panel says what the difference can be; and the milestone ships nothing that asks a cafeteria to count, log or transfer anything.
PRD §22's theoretical sale consumption is computed here as a read and posted to no ledger.

**Done when** (as the checklist says, read against this decomposition): an owner opens the dashboard, scrolls past the items to a panel headed by one sentence naming a material and a branch and a sum of money, sees each material's bought and used figures side by side with the gap in kilos and in dirhams, opens a row to the papers that bought it and the dishes that used it, and reaches an invoice line or a sales day from every number.
The demo runs it as act five, on the same committed week, straight after act four on the same screen.

## 2. What exists today, and what is missing

### The used side's inputs all exist, and nobody multiplies them into quantities

- `db.list_period_item_sales` (`db.py:2113`, query `:2147-2163`) returns one row per (branch, till item, business day) with `qty_sold`, `qty_refunded` and `no_qty_lines`, summed in SQL (C12.1). `contribution.ItemSales` (`contribution.py:128-150`) carries it; `contribution.item_rows` (`:618`) groups it per (branch, menu item) and produces `ItemRow.qty_sold` and `qty_refunded` net of refunds (C12.6a). **The portions sold per dish per branch per period already exist on every dashboard read.**
- `db.list_current_recipe_components` (`db.py:1308-1331`) returns every item's current recipe with `qty`, `unit`, `ingredient_id`, `ingredient_name` and the ingredient's `base_unit`, one query for the whole menu; `db.list_menu_items` (`:1217-1236`) carries `yield_portions`. `menu._menu_context` (`menu.py:333-363`) already fetches both on every dashboard read and hands them to `dashboard._menu_items` (`dashboard.py:98-150`), which builds `contribution.RecipeComponent(ingredient_id, ingredient_name, qty, unit, batch_cost, ...)` per component (`contribution.py:166-183`).
- The conversion is one function: `plates.to_base_qty(qty, unit)` (`plates.py:79-92`) turns `(2, "kg")` into `(2000, "g")` through `extraction/units.py`, and `plates.cost_component` (`:119-157`) already refuses a unit that does not convert to the material's base unit with the sentence "'cup' does not convert to how X is measured". `dashboard._menu_items` calls the same converter to make `batch_cost` (`dashboard.py:114-116`).
- So the used quantity of one material in one branch is `sum over dishes of (portions net of refunds x component base quantity / yield_portions)`, and every term is in memory on the dashboard read. **Nobody sums it.** `contribution._components` (`contribution.py:459-482`) divides a component's *cost* by the yield; no function divides its *quantity*.
- Packaging is already a material: a paper cup is an ingredient with `base_unit = 'pc'` (`0012:24`), loaded as a recipe component like a spoon of tea (`plan.md` §7.3 row 61; 14 of the real menu's 20 checked items carry one). It multiplies like everything else and needs no special case.
- `sales_lines.qty` is nullable (`0019:193`); C12.6 pins that a line with no quantity makes its (branch, item) pair uncountable and that a quantity is never invented from money. The rule carries straight into usage: a pair that cannot be counted contributes nothing to any material's used figure, and the material row says so.

### The bought side's factor is frozen on every costed line, and no read sums it

- `invoice_lines.cost_basis` (`0013:42`) is the jsonb C8 record written at confirm: `quality`, `asserted`, `pack`, `pack_base_quantity`, `pack_source` (`costing.LineCost.basis`, `costing.py:134-148`). **`pack_base_quantity` is the amount one unit price bought, in base units** - `2500.0` grams for a 2.5 kg sack, `19200` millilitres for `48x400ml` (`demo_seed.sql:422`, `:460`). It is the exact factor `cost_line` divided the price by (`costing.py:300`), so line `qty x pack_base_quantity` is what the line delivered, in the material's base unit, by the same arithmetic that costed it.
- It is frozen: "written at confirm inside the confirm transaction and frozen; a later pack-size override costs lines that have none and never rewrites one that has" (`0013:44-47`). A line confirmed before its pack had an override is costed by the override afterwards, so every line that *can* carry a basis does.
- A line with no basis is a line with no cost. `db.list_blocked_costs` (`db.py:1154`, query `:1169-1186`) lists them - confirmed, `line_kind = 'stock_item'`, `cost_per_base_unit is null` - and `costing.blocked_reason_for` (`costing.py:328-357`) names why: a missing unit price, a missing quantity, a foreign currency, or one of three pack problems. For usage the first two and the pack problems all mean the same thing, **the line's quantity in base units is unknown**, and a foreign-currency paper's goods were delivered whatever its currency, but its lines carry no basis either. So the bought side has exactly one kind of hole, "this line could not be measured", and the blocked-costs queue is already where a person fixes it.
- `line_kind` (`0007:17`) splits stock lines from charges; a delivery fee delivers nothing and is excluded. `invoice_lines.qty` (`0001:85`) is signed; a return prints a negative quantity and `cost_line` costs it anyway (`costing.py:284-286`), so a return line carries a basis and nets out by its own sign.
- `invoices.branch_id` is nullable (`0001:62`); `ratio.unassigned_group` (`ratio.py:551-571`) is the shipped rule for confirmed papers with no branch: counted in no row, never dropped. Their lines have quantities and materials and belong to no branch's shelf; they belong in the chain's figure and nowhere else.
- **No read sums quantities by material, by branch, by date.** `db.list_mapped_pack_costs` (`db.py:759`, query `:808-838`) picks the *newest* costed line per pack, `distinct on (s.id)`; `db.list_newest_purchases` (`:1334`) the newest purchase per material; `db.list_price_move_pairs` (`:1398`) the top two per material; `db.list_unmapped_supplier_items` sums spend on packs with no material. Every one collapses to a price. There is no `sum(l.qty * ...)` anywhere in `db.py`, and no query on `invoice_lines` groups by `inv.branch_id`.
- The date a line belongs to is settled: `purchased_on = coalesce(inv.invoice_date, (inv.confirmed_at at time zone 'UTC')::date)` is the costing rule (`db.py:823-824`) and the ratio's (`db.list_period_invoices`, `:2065-2066`), so a paper sits in the same week on the materials screen, the sales screen and here.

### The window discipline exists, and `BranchRow` carries the sales half of its label but not the purchase half

- `ratio.period_row` (`ratio.py:358-548`) clips a branch's window to its own loaded sales range (C9 amended, `:380-384`), filters the branch's papers to confirmed, tenant-currency, `purchased_on` inside that window (`:386-395`), and derives the row's word and sentences (`:426-476`). M9 made it carry the **sales half** separately - `BranchRow.sales_quality` and `sales_notes` (`:226-227`), derived on the way to the merged word - so `contribution.py` could read a gap sentence without re-wording it (C9 extended).
- The **purchase half** is not carried. "No confirmed purchases 25-31 Aug" (`:449`), the pending-paper sentences (`:460`), the foreign-currency sentences (`:461`), the asserted-total sentence (`:463-464`) and the "3 deliveries in this window" count (`:466`) all land in the merged `notes` and nowhere else. C9 extended kept the purchase side out of contribution on purpose ("a pending paper is a fact about the ratio, not about a contribution"). **For usage the purchase side is the bought figure itself**, so a pending paper in the window is exactly the estimate a bought quantity should admit, and "no confirmed purchases" is exactly why a bought figure is zero. Reusing those sentences needs the symmetric pair of fields, additive, derived where the merged word already is.
- `BranchRow.deliveries` (`:212`) is the count of counted papers in the window, and `window` (`:203`) is the clipped range. Both are what a material row needs to say "3 deliveries in this window" and to sum lines over the right days; both are on every dashboard read.

### The dashboard read holds everything but one query

- `dashboard.py` (579 lines) makes the eighteen reads `test_dashboard.py` enumerates (`test_dashboard.py:45-66`, `MAX_QUERIES` derived at `:67`) and asserts the count flat from two items to forty-five (`:493-510`). It already holds, on every request: `ratio_rows` per branch with their windows (`dashboard.py:396-407`), `_menu_context` as of the period's end with the components and the prices (`:412-414`), the item sales by branch and day (`:418-423`), and the contribution rows with their portions (`:421-433`).
- Of the six terms in §3's C14, five are in that memory. The sixth - the confirmed stock lines mapped to a material inside the period, with their branch, their date and their frozen basis - is **one new read**, and it is the only query M12 adds. The enumerated list becomes nineteen.
- The payload is a dict composed at `:510-579`; a new block is a new key. `ITEMS_SLICE = 5` (`:63`) and the `items.top` / `items.bottom` / `items.all` slicing (`:562-569`) are the panel shape a materials block inherits.
- `_dec` and `_iso` (`api.py:176-181`) serialise money and dates; quantities are `Decimal` too and serialise the same way (C4).

### The screen pattern the panel inherits

- `Dashboard.tsx` is 1,189 lines with five blocks: freshness, the two sentences, the league, the signals, the items panel (`:1031-1110`) and the coverage strip. The items panel is the shape a materials panel copies: a fixed `colgroup` (`:1048-1054`), `ItemTableRow` at 640 px and up (`:363`) and `ItemCard` under it (`:436`), five and five with "Show all N items" (`dashboardScreen.itemPanel`, `dashboardScreen.ts:389-400`, `SPLIT_AT = 10` at `:376`), incomplete rows listed beneath with no numbers (`incompleteItems`, `:403-405`), the heading count (`itemsHeading`, `:424-429`), and the in-row drill (`ItemDrill`, `:267`) with the component links to `/invoices/<id>#line-<n>` (`componentLink`, `dashboardScreen.ts:471`) and `/menu#item-<id>` (`todaysPlateLink`, `:482`).
- **Every decision the component renders lives in `dashboardScreen.ts`** (527 lines, 40 exports, pinned by `dashboardScreen.test.ts`'s 37 cases), because `vitest.config.ts` runs `.test.ts` in a node environment with no rendering library; whatever the component decides for itself is untested by construction. A materials panel's decisions go there too.
- **The mock computes nothing.** `mock/dashboard.ts` returns one of five JSON literals per scenario and scope (`?scenario=full|partial|quiet|empty|nomenu|error`), and those literals are produced by `mock/dashboard/generate.py`, which imports the *shipped* modules (`contribution`, `signals`, `ratio`, `plates`, `menu.price_moves`) over a hand-built week and writes the payloads out (Decision Log 2026-09-05). A `usage` block joins the fixtures the same way: `generate.py` imports `usage.py` and regenerates. Until `usage.py` exists the web lane writes the block's literals by hand and checks them by hand, the `mock/menu.ts` rule, and Wave 3 replaces them with the generated ones.
- `format.ts` (141 lines) has money, grouped money, rounded AED, dates, `points`, and **no quantity formatter**: nothing turns `"94.292"` into "94.3 kg". The house rule is string operations only, no arithmetic (`format.ts:1-5`), so the API must carry the figure already in the display unit; the screen trims and labels.
- `types.ts` (1,340 lines) carries `DashboardResult` (`:1326-1340`) with thirteen keys; a fourteenth, `usage`, joins it. `MaterialPrice` (`:389-420`) already knows `per_display_unit` and `display_unit`, the vocabulary a quantity in kilos reuses.

### `/materials` is the consultant's screen, and it has no period

- `RawMaterials.tsx` (709 lines) fetches three lists in one `Promise.all` (`:123-146`) - the mapping queue, the materials, the blocked costs - and re-fetches all three after every decision. It has no period picker, no branch filter, and no window: its one number per material is *today's* price (`/api/ingredients`, `api.py:1153-1202`, derived from `list_mapped_pack_costs` with no `as_of`). Its arc is the consultant's: map a pack, watch a price appear, watch a dish become costable.
- `plan.md` §8 M12 named "the material's row on `/materials` in `/sales`' period shape" as the recommended direction before this decomposition. Read against the code, that means giving the consultant's screen a period, a branch filter, a second read and a third list, and putting an owner's question on the screen where a consultant works. §5 P1 argues the other way and recommends the dashboard.

### The quality vocabulary agrees, and has no word for stock

- `ratio.Quality` (`ratio.py:69-76`), `contribution._QUALITY_RANK` (`contribution.py:102-107`) and `plates.PlateQuality` (`plates.py:51-58`) agree on four words and their precedence and none contains `verified`. Usage rows speak the same four words.
- PRD §24 lists "stale stock count" and "negative theoretical stock" among its issue kinds. Neither can exist here: there is no count to be stale and no stock to be negative. A used figure above a bought figure is not negative stock; it is a window that started with stock on the shelf, or a recipe or pack size that is wrong, and C14.5 words it as exactly those two possibilities.

### The demo stage, and what act five inherits

- The practice stage: `demo_seed.sql` stages six materials (`:311-322`), five with a pack mapped and Atta Flour with none (`:325-334`), two confirmed papers 35 days ago and two 28 days ago on Al Qusais (`:373-404`), ten costed lines with `pack_base_quantity` in every basis (`:415-460`), and five recipes (`:478-533`). `build_sales_week.py --practice` generates the rehearsal week as **the seven days ending on the tenant's newest staged purchase day** (`README.md:181-184`), so the 28-day-old papers land on the last day of the week. Worked by hand from the committed `sales-week-practice.csv` (127 rows, three branches, the `DELIVERY CHARGE` name and a trailing `TOTAL` row) and the seeded recipes, Al Qusais reads, in the window's last-day paper against the week's sales:

  | material | used | bought | bought - used | at the period's price |
  |---|---|---|---|---|
  | White Sugar | 5.7 kg | 100 kg | 94.3 kg | AED 216.87 |
  | Cardamom Powder | 97 g | 2 kg | 1.9 kg | AED 91.34 |
  | Milk Powder | 6.25 kg | 10 kg | 3.75 kg | AED 75.75 |
  | Karak Tea Dust | 1.35 kg | 2.4 kg | 1.05 kg | AED 57.53 |
  | Evaporated Milk | 27.5 L | 38.4 L | 10.9 L | AED 51.19 |
  | Atta Flour | 13.9 kg | no pack mapped | - | - |

  Every row is the honest failure mode the checklist warns about: one paper on the last day of a seven-day window, so sugar tops the ranking with two sacks against a week's use, and the row says "1 purchase in this window; a single delivery is not a rate". Al Nahda and Rolla have sales and no papers, so every material reads "no confirmed purchases 1-7 Aug" with a used figure and nothing bought. Atta Flour names the mapping queue. That is a walk-through of every sentence, on a stage that exists, before any real figure is spoken. (The committed CSV's dates are stale by design and the file is regenerated before a rehearsal, `README.md:184`.)
- The real stage: the 45-item menu, KAS-1 to KAS-5, the committed `sales-week.csv`, and the founder's menu CSV outside the repository, exactly as act four (`act_four.py:36-44`). Act four's script stages the chain through the shipped doors and reads the shipped route; act five reads one more block of the same payload, so it is the same script printing one more section, not a second script.
- `test_demo_seed.py` pins act four's named facts (`:1413`, `:1458`) and skips the real stage where the CSV is absent; act five's assertions join the same two tests.

### `TODOS.md` entries M12 touches

| Entry | Line | Why M12 touches it |
|---|---|---|
| Catalog pack size and unit are written once and never corrected | `:15` | a wrong pack size is a wrong bought quantity, exactly as it is a wrong cost; the "used above bought" sentence is the first place a wrong pack becomes visible in quantities |
| Pack sizes are corroborated by nothing | `:69` | same: usage is the second number a pack size feeds, and a used-above-bought row on a fast-moving material is weak corroboration in the other direction |
| A branch correction door on an invoice | `:385` | a confirmed paper with no branch delivers goods to no branch's shelf; the chain row holds them and nothing moves them |
| A day-totals (summary) sales export | `:289` | a summary day has no lines and no quantities, so a branch on such a till has no used figure at all (`unavailable`) |
| Costing each day at the price in force that day | `:592` | the money on a usage row is the gap at one price, the period's; a per-day price would reprice it |
| A per-branch material price | `:604` | the same: one tenant-level price values every branch's gap |

### Signals: the panel has three kinds and a cap, and a fourth kind is a contract change

`signals.py` pins three kinds (`:98-100`), `MAX_SIGNALS = 5` (`:95`), and C13.2 says "three kinds, and only three". A "sales needed more than was bought" signal would be a fourth kind with a threshold, and §5 P3 recommends against one in M12: used above bought is ambiguous by construction (stock carried in from before the window, or a wrong recipe or pack), so any threshold is a guess dressed as a rule, and the ranked panel with its own sentence already says "look here first" without one.

## 3. Contracts to pin before fan-out (C14 new; C9 extended by the purchase half; C6 extended by one block; C13, C8, C7 untouched)

- **C14 - Theoretical usage and what was bought.**
  1. *The unit is (material, branch, period).* A material is an `ingredients` row; a row exists for every material with a pack mapped **or** a component in a current recipe (a material with neither has nothing to say). Every figure is `Decimal` in base units (`g`, `ml`, `pc`) at full precision, quantized once where it is displayed (C4's rule one shelf down).
  2. *Used is the recipes times the portions, over the pairs that produced a count.* For each (branch, menu item) pair that `contribution.item_rows` counted - `qty_sold` and `qty_refunded` present, so no line without a quantity (C12.6) - and for each component of that item's **current** recipe (C12.4's rule, unchanged: recipes are loaded after the sales they cost), used += `(portions sold - portions refunded) x plates.to_base_qty(component.qty, component.unit) / yield_portions`. The converter is `plates.to_base_qty` and nothing else; a component whose unit does not convert to its material's base unit is skipped and the row carries `plates.cost_component`'s own sentence for it. Packaging counts: a cup is a `pc` material and multiplies like a spoon of tea. A dish with no recipe, an unmapped till name and an excluded one contribute nothing, and the shortfall is a **share**, not a label (C9 extended's rule): *recipe coverage* is the positive net value of lines on menu items whose current recipe has at least one component, over the positive net value of lines on names not marked "not a menu item", per branch and for the chain, worded "recipes cover N% of this branch's sales value". It is a third share on purpose and it differs from both shipped ones: `ratio.coverage` asks what the menu can cost today and `contribution.costed_share_pct` asks what could be costed at the period's prices, while usage needs a recipe's quantities and not its price - the seeded Paratha's flour is real usage of a material nobody has bought yet. The three are never shown on one row and each is worded with its own noun (P4).
  3. *Bought is the confirmed stock lines, measured by the factor that costed them.* A line counts when its invoice is `confirmed`, its `line_kind` is `stock_item`, its pack maps to the material (`supplier_items.ingredient_id`), and its `purchased_on` - the printed date, confirm time as the tie-breaker, the same `coalesce` as `db.py:823-824` - lies inside the branch's clipped window (`ratio.BranchRow.window`, C9 amended). Its quantity is `qty x (cost_basis->>'pack_base_quantity')`, the frozen factor of `0013:42`, and **nothing else**: a line with no basis is *unmeasured*, counted on the row ("2 lines could not be measured"), linked to the blocked-costs queue that owns it, and never re-resolved at read time (P2). A negative quantity is a return and nets out by its own sign, named ("1 return"). Currency is not a filter - goods arrived whatever the paper's currency - and a foreign paper's lines carry no basis, so they are unmeasured lines like any other. A paper with no branch counts in the chain row only, the `ratio.unassigned_group` rule, and the chain row names how many. The row carries the count of papers it summed ("3 deliveries in this window", `BranchRow.deliveries`' own words).
  4. *The read is one query at line grain, bounded by the period, and the roll-up is in Python.* `db.list_period_material_purchases(*, tenant_id, date_from, date_to)` returns every confirmed stock line mapped to a material whose `purchased_on` is inside the period, with its branch, its date, its quantity, its basis factor (null when unmeasured), its pack and supplier names, and its invoice id and position for the drill; `usage.py` sums per (branch, material) over each branch's clipped window, counts papers and returns and unmeasured lines, and keeps the lines for the drill. Line grain, because the drill must reach the line (`/invoices/<id>#line-<n>`, the M9 anchor) and a chain-month of confirmed stock lines mapped to materials is a few hundred rows; C11.8's "sum in SQL, never over lines in Python" is a rule about till lines, which arrive by the thousand a week. The trigger to split it into a summed read beside a drill read: a tenant's confirmed stock lines in one period pass 5,000.
  5. *The gap is bought minus used, said both ways and named for what it can be.* `gap = bought - used` in base units. A positive gap is worded "bought 94.3 kg more than its sales needed"; a negative one "its sales needed 3.2 kg more than was bought", **followed by the two things it can mean**: "either stock from before this window was used, or a recipe quantity or a pack size is wrong". A gap is never worded as variance, waste, theft, shrinkage, loss, or negative stock, and a test pins the absence of each word from every sentence the module composes. The standing sentence beneath the panel is composed once, in Python, and carried on the wire: "The difference between bought and used is on the shelf, in the bin or unrecorded; no count says which." When a row's window holds exactly one purchase the row adds "1 purchase in this window; a single delivery is not a rate" - the sugar sack on the last day.
  6. *Display units are the API's, and the screen does no arithmetic.* Every quantity travels twice: exact in base units (`used_base`, `bought_base`, `gap_base`) and in the material's display unit (`costing.DISPLAY_UNITS`: kg, litre, each) to three decimals (`used`, `bought`, `gap`), produced by a quantity twin of `costing.per_display_unit`. The screen trims and labels; it never divides (C13.5's rule).
  7. *Money is the gap at the period's price, and only when there is one.* `money = gap_base x price.cost_per_base_unit`, the as-of price `_menu_context(as_of=period.end)` already holds for the material (C12.4), quantized to a fil, signed like the gap; `price_per_display_unit` beside it in the row's words ("at AED 2.30 per kg on 31 Aug"). A material with no as-of price carries the quantity gap and `money: null` with "no price to value it at"; it is listed, ranked after the rows with money, and never valued at today's price or at a guess. The money's own label is the price's (`cost_basis.quality`, the stale flag): an estimated price makes the money estimated, and the row says which ingredient's price it is.
  8. *Quality is the worse of three halves, in the C9 vocabulary, never verified; holes lower a share and never the word.* The **sales half** is `BranchRow.sales_quality` and `sales_notes`, read and never re-worded (C9 extended). The **purchase half** is the new `BranchRow.purchase_quality` and `purchase_notes` (C9 extended below): `incomplete` when the window holds no confirmed purchase, `estimated` when a pending paper is placed in it, a confirmed paper was excluded for its currency, or a counted paper's total or VAT was typed. The **material half** is the row's own: `incomplete` when no pack is mapped to the material (no bought figure at all; `plates.cost_component`'s sentence, "no supplier product is mapped to X yet") or when any summed line is unmeasured; `estimated` when any measured line's `pack_source` is `override` ("a pack size you entered measures N lines"). Precedence is `ratio._QUALITY_RANK`'s. A (branch, item) pair left out for a missing quantity, and a dish with no recipe, **lower the recipe coverage share and are named** ("1 dish left out: lines with no quantity"; "recipes cover 94% of this branch's sales value") and never downgrade the word - PRD §24's own example, C9 extended's rule. `unavailable` is the branch's: nothing loaded and nothing bought in the window, the ratio's own word, and such a branch has no rows.
  9. *The chain reconciles, and the invariant is stated precisely enough to hold.* A chain row per material: `bought` is the sum of the branch rows' bought plus the unassigned papers' lines; `used` is the sum of the branch rows' used; both sums are over the branches that carry a figure for that material, and the row names the branches it left out. Pinned: **chain bought equals the sum of branch bought plus unassigned bought, and chain used equals the sum of branch used**, per material, to the base unit; and **a branch's used of a material equals the sum over its item rows of `qty_sold - qty_refunded` times that recipe's component quantity per portion**, so the panel and the items panel above it can never disagree about how many karaks were sold.
  10. *Ranked by money, largest either way first; the sentence names the top row.* Rows are ordered by the absolute money in the gap, largest first, rows with no money next by absolute gap in base units, rows with no numbers last, ties by material name. The answer sentence names the top row in the scope with its direction and its money: "Al Qusais bought 94.3 kg more sugar than its sales needed, AED 217 at the period's price." Under `?branch_id` the rows and the sentence are that branch's; unfiltered they are the chain's. The screen frames and never re-ranks (C13.5).
  11. *One implementation.* `usage.py` **calls** `plates.to_base_qty`, reads `_menu_context`'s components and prices, reads `contribution.item_rows`' portions, reads `ratio.period_row`'s windows and both halves of its label, and uses `costing.DISPLAY_UNITS`; a second unit table, a second window rule, a second price read or a second portion count is a contract breach, not a refactor (§2 rule 3, C12.9's precedent).

- **C9 extended by the purchase half.** `ratio.BranchRow` gains `purchase_quality: Quality` and `purchase_notes: tuple[str, ...]`, additive with defaults, derived inside `period_row` on the way to the merged word exactly as `sales_quality` and `sales_notes` were (`ratio.py:426-476`): the "no confirmed purchases" sentence, the pending-paper sentences, the foreign-currency sentences and the asserted-total sentence go into `purchase_notes` as they go into `notes`, and `purchase_quality` is `incomplete` for the first, `estimated` for the rest, `reliable_with_limitations` otherwise. The merged `quality` and `notes` are unchanged byte for byte; `test_ratio.py` green proves the `/sales` wire did not move, and one new case pins that the merged word is the worse of the two halves. `contribution.py` keeps reading the sales half only (C9 extended, unchanged); `usage.py` reads both.

- **C6 extended by one block, and no route.** `GET /api/dashboard` gains `usage` (§3.1): the scope's material rows, the answer sentence, the recipe coverage, the counts of what was left out, and the standing sentence. One more read in the enumerated set (nineteen). `branch_id` filters the rows and the sentence; the chain rows appear unfiltered. There is no `/api/usage` route: the panel's period, branch filter, windows and costed menu are the dashboard's, computed once (P9's reasoning, one milestone on), and a second route would resolve the period a second time and be the second reader of `_menu_context` on one screen. `/sales`, `/menu` and `/materials` are untouched.

- **C13 untouched.** Three kinds, a cap of five, no fourth kind (P3). The usage panel's answer sentence is a sentence, not a signal: it names the top row of a ranking and has no threshold.

- **C8 untouched.** M12 adds no write path, no action, no subject type, no audit row and no provenance origin. Every code path it adds is a read.

- **C7 untouched.** M12 ships no migration. The live project stays at 0019.

- **C11, C12, C10, C4, C2 untouched.** The ratio, the item rows and their labels are read exactly as pinned; the new `db.py` method takes `tenant_id` keyword-only; money and quantities are `Decimal` in Python and `numeric` in Postgres; nothing is enqueued.

### 3.1 Wire shape (pinned for the web lane; money, quantities and percentages as strings, dates ISO)

```
GET /api/dashboard?from=2026-08-04&to=2026-08-31&branch_id=<optional>
{ ...every block §3.1 of M9 pinned, unchanged...,
  "usage": {
    "answer": "Al Qusais bought 94.3 kg more sugar than its sales needed, AED 217 at the period's price.",
    "standing": "The difference between bought and used is on the shelf, in the bin or unrecorded; no count says which.",
    "rows": [ ...MaterialRow... ],                    (the scope's rows, ranked - C14.10; the chain's when unfiltered)
    "count": 5,                                       (rows carrying both figures)
    "coverage": {"recipes_pct": "94.0",
                 "sentence": "recipes cover 94% of this branch's sales value"},
    "left_out": {"items_without_quantity": 0, "items_without_recipe": 1, "unmeasured_lines": 0},
    "unassigned": {"papers": 0, "lines": 0}           (purchases with no branch, in the chain rows only)
  }
}

MaterialRow =
{"ingredient_id": "…", "ingredient_name": "White Sugar", "base_unit": "g", "display_unit": "kg",
 "branch_id": "…" | null,                             (null = the chain row)
 "used": "5.708", "bought": "100.000", "gap": "94.292",          (display units, three decimals; null when unknown)
 "used_base": "5708", "bought_base": "100000", "gap_base": "94292",   (base units, exact)
 "direction": "over" | "under" | "even" | null,
 "money": "216.87" | null, "price_per_display_unit": "2.30" | null, "priced_on": "2026-08-07" | null,
 "price_quality": "reliable_with_limitations" | "estimated" | null,
 "purchases": 1, "returns": 0, "unmeasured_lines": 0, "items": 3,
 "quality": "reliable_with_limitations" | "estimated" | "incomplete",
 "notes": ["bought 94.3 kg more than its sales needed",
           "1 purchase in this window; a single delivery is not a rate",
           "at AED 2.30 per kg on 7 Aug 2026", "recipe version 1"],
 "lines": [{"invoice_id": "…", "line_position": 2, "purchased_on": "2026-08-07",
            "supplier_name": "Gulf Foods Trading L.L.C.", "product_name": "SUGAR 50KG",
            "qty": "2.000", "pack": "50kg", "base_qty": "100000", "measured": true}],
 "dishes": [{"menu_item_id": "…", "menu_item_name": "Karak Tea (Cup)",
             "portions": "110.000", "per_portion_base": "40", "base_qty": "4400"}]}
```

A chain `MaterialRow` carries `"left_out": ["Rolla"]` in its notes when a branch produced no figure for it. An `incomplete` row with no pack mapped carries `bought`, `gap`, `money` and `direction` as `null`, its `used` figure, and the plates sentence; a hole never renders as a shelf that is exactly right.

## 4. Work packages

Sizes as in `plan.md` §7.3: S ≤ half an agent-day, M ≈ one, L = multi-day.
Acceptance is demonstrable, never documentary. Waves per §6.

| WP | What | Size | Depends | Acceptance |
|---|---|---|---|---|
| 120 | **Theoretical usage and what was bought, derived on read.** A pure `usage.py` in `contribution.py`'s shape (C14): `PurchaseLine` and `MaterialRow` dataclasses, `material_rows(item_rows, menu, lines, windows, prices, ...)`, `chain_material_rows`, `recipe_coverage`, `rank`, `answer`, the standing sentence, the direction words, the two-cause sentence; `Decimal` throughout, base units exact, display units via a quantity twin of `costing.per_display_unit`; every sentence composed here. A new `db.list_period_material_purchases(*, tenant_id, date_from, date_to)` returning confirmed stock lines mapped to a material inside the period at line grain, with the branch, `purchased_on`, `qty`, the basis factor, `pack_source`, pack and supplier names, and the invoice id and position. `ratio.period_row` gains `purchase_quality` and `purchase_notes` on `BranchRow`, additive. No route. | L | - | `tests/test_usage.py` (pure): the hand-checked karak week to the gram - 110 cups at 220 g per 40-cup pot is 605 g of tea dust; a pair with no quantity leaving the used figure and named, the word unchanged; a dish with no recipe lowering recipe coverage and named; a component in cups skipped with the plates sentence; a return line netting out and named; an unmeasured line making the row incomplete with its count; an override making it estimated; no pack mapped giving a row with no bought figure and the plates sentence; a paper with no branch in the chain row only; one purchase in the window adding its sentence; used above bought giving "under" with the two-cause sentence; a material with no price carrying the quantity and `money` null; the chain invariants (C14.9) to the base unit; the ranking by absolute money then absolute gap then name; the answer naming the top row, under a branch scope and unfiltered; **the absence of every forbidden word** (variance, waste, theft, shrinkage, loss, negative stock) from every sentence the module composes. `tests/test_usage_db.py` (Postgres): the read returning one row per confirmed stock line mapped to a material inside the period and nothing else - a charge line, a draft, a dismissed paper, an unmapped pack and a paper dated outside the period all absent; the basis factor null on a blocked line and present after an override; a return with its sign; a no-branch paper with `branch_id` null; the window roll-up agreeing with a hand sum. `tests/test_ratio.py`: green unchanged plus the one new case (C9 extended); `test_sales_api.py` unchanged |
| 121 | **The usage block on the dashboard read.** `dashboard.py`: the one new read, `usage.material_rows` over the item rows, the menu context and the windows the read already holds, `chain_material_rows`, the block to §3.1, the answer scoped by `branch_id`, the enumerated list gaining one read. No new route, no matrix change. | M | 120 | `tests/test_dashboard.py`: the three-branch end-to-end on the seeded stage with the karak week - Al Qusais's sugar row, its lines reaching `/api/invoices/{id}`, its dishes reaching `/api/menu-items/{id}`; **chain bought = Σ branch bought + unassigned and chain used = Σ branch used** per material; **a branch's used of tea dust equals Σ over `items.all` of portions × the recipe's per-portion quantity**, so the two panels agree; `branch_id` narrowing the rows and the sentence while the chain rows appear only unfiltered; a paper dated after the period absent from every row; a pending paper making the purchase half estimated; a branch with nothing loaded carrying no rows; the query count asserted against the enumerated list of **nineteen**, flat from two items to forty-five and from three materials to sixty; `test_sales_api.py` and `test_tenancy.py` unchanged and green |
| 122 | **The materials panel on `/dashboard`.** `Dashboard.tsx`: a fourth panel below the items, "Materials: bought against what the sales needed", one sentence above it, five rows and "Show all N materials" in `itemPanel`'s shape, a fixed `colgroup` at 640 px and cards under it, the row drill in place listing the papers (each `/invoices/<id>#line-<n>`) and the dishes that used it (each `/menu#item-<id>`), rows with no numbers listed beneath with their sentence, the standing sentence always visible, the recipe-coverage line. `dashboardScreen.ts` gains **every decision the panel renders** (`usagePanel`, the heading count, the empty and partial cases, the direction words' framing, the drill's link builders); `types.ts` the block and the row; `format.ts` a `quantity(value, unit)` formatter, string operations only; `mock/dashboard/generate.py` imports `usage.py` and regenerates the five fixtures (the block hand-written in the JSONs until WP-120 lands); `dashboardScreen.test.ts` the panel's cases. | M | §3.1's shape; WP-121 for browser QA | `npm test`, `tsc`, lint, build green; `/browse` at 1280 and 390: the full scenario shows five rows and the sentence, "Show all" expands in place, a row opens to its papers and dishes and each link lands on the anchor, an `under` row shows the two-cause sentence, an incomplete row shows no numbers and the plates sentence, the standing sentence is visible without scrolling the panel, the quiet scenario shows every row `even` or near it, the empty scenario shows no panel; nothing in the panel is divided or re-ranked in TypeScript |
| 123 | **Act five on the demo stage.** `DEMO_RUNBOOK.md` §I straight after §H on the same screen: scroll to the panel, read the sentence, open sugar's row to the paper, open Atta Flour's row to the mapping queue, and say the one line about a single delivery not being a rate; `act_four.py` prints act five's figures as one more section of the same run (both stages); `test_demo_seed.py` asserts the named facts: on the practice stage sugar first by money with "1 purchase in this window" on its row, Atta Flour incomplete with the plates sentence, Al Nahda and Rolla every row `under` with "no confirmed purchases" from the purchase half; on the real stage the top material and its money before and after KAS-5, skipping where the founder's CSV is absent (the existing `TODOS.md` entry) | S | 121, the committed week | `pytest tests/test_demo_seed.py` green on the named facts; every figure §I quotes printed by the script, none typed |
| 124 | **Live, and the record.** One sitting: API deployed by the merge, web deployed, the panel read against the real menu and the loaded week, act five walked, then `plan.md`'s boxes and logs, `TODOS.md`, `README.md`, `CLAUDE.md`, `AGENTS.md` (the M12 paragraph), and PRD §27.1's "inventory warnings" reworded to what shipped | S | 120-123 | the live panel answers "which material and which branch is buying more than its sales needed, and what that costs" in one sentence, and the number drills to an invoice line; the loop reset leaves the week and the panel intact |

**The cut line, named in advance** (§2 rule 9): if the budget bites, WP-122's in-row drill goes first (the rows stay, and the papers are one click away on `/sales`' branch drill), then act five's real-stage assertions (the practice stage carries every sentence). WP-120, 121 and 122's rows are the done-when and cannot be cut; WP-123 is the demo bar.

### 4.1 Design direction for the materials panel

No wireframe board yet; this is one recommended direction, calibrated against the four approved screens and Variant A of the dashboard (Approved Mockups, 2026-09-05). A `/plan-design-review` before WP-122 is the founder's call, as it was for M9.

**Reader order (the sentence, then the table, then the caveat):**

```
  ┌ Materials: bought against what the sales needed              6 materials · recipes cover 94% of sales value
  │ Al Qusais bought 94.3 kg more sugar than its sales needed, AED 217 at the period's price.
  │
  │ Material          Sales needed    Bought      Difference           At the period's price    Status
  │ ▸ White Sugar        5.7 kg     100.0 kg    94.3 kg more bought      AED 217    Reliable w/ limits
  │     1 purchase in this window; a single delivery is not a rate
  │ ▸ Cardamom Powder    97 g         2.0 kg     1.9 kg more bought      AED  91    Reliable w/ limits
  │ ▸ Milk Powder        6.3 kg      10.0 kg     3.8 kg more bought      AED  76    Reliable w/ limits
  │ ▸ Karak Tea Dust     1.4 kg       2.4 kg     1.0 kg more bought      AED  58    Reliable w/ limits
  │ ▸ Evaporated Milk   27.5 L       38.4 L     10.9 L more bought       AED  51    Reliable w/ limits
  │                                                                       [Show all 6 materials]
  │ ▸ Atta Flour        13.9 kg          -       no supplier product is mapped to Atta Flour yet
  │
  │ ▾ a row opens in place:  Bought - 2 x SUGAR 50KG, Gulf Foods, 7 Aug (invoice GF-20655, line 3)
  │                          Used by - Karak Tea (Cup) 110 sold, 40 g each · Nido Milk Tea 109 sold, 12 g each
  └ The difference between bought and used is on the shelf, in the bin or unrecorded; no count says which.
```

- **Constraint worship, again.** One sentence, one table, one caveat. No gauge, no stock-level bar, no traffic light: a bar would draw a level nobody measured. The panel sits below the items panel because the reader order is branch, dish, then shelf, and the standing sentence is the panel's last line, always visible, never a tooltip.
- **The difference column is words and a number, never a bare sign.** "94.3 kg more bought" and "3.2 kg more needed than bought" are the API's own sentences; a signed number alone would read as a loss to half the room and a gain to the other half. An `under` row's two-cause sentence sits beneath it in the row's own tone, and never the word variance.
- **Money is the ranking and it says whose price.** "At the period's price" in the header; the drill names the price and its date. Rounded AED in the column, fils in the drill (§3, the 2026-08-30 exception for per-plate figures does not apply: these are period totals).
- **Quantities are the API's display unit trimmed by the screen**: `quantity("94.292", "kg")` gives "94.3 kg", `quantity("0.097", "kg")` gives "97 g" only if the API sent grams - it does not; the screen shows "0.1 kg" and the drill the exact figure. String operations only, the `format.ts` house rule. (A per-material choice of display unit is the API's, not the screen's, and stays with `costing.DISPLAY_UNITS`.)
- **Status is the shared four-word chip** (`QualityChip`, the `Record` lookup shape) with the first note beneath it; "1 purchase in this window; a single delivery is not a rate" is the note that matters most and it is the sugar row's first.
- **The drill is two lists, not a table**: the papers with their line links, the dishes with their per-portion quantity and their `/menu#item-<id>` link. Under 640 px a stacked list beneath the card, the item drill's rule.
- **Rows with no numbers are listed beneath**, the `/menu` and items-panel pattern: Atta Flour shows its used figure, no bought figure, and the plates sentence that names the next action.

**Interaction states:**

| Feature | Loading | Empty | Error | Success | Partial |
|---|---|---|---|---|---|
| Sentence | with the payload | "Load a week of sales and map its names, and this will name the material to look at." | the strip | one sentence naming the material, the branch and the money | "its sales needed more than was bought" with the two-cause sentence when the top row is `under`; the word *incomplete* inside the sentence when the top row is |
| Table | with the payload | "No recipe uses a material that has been bought yet." | the strip | five rows ranked by money, expand to all | rows with no money after the ranked ones by quantity; rows with no numbers beneath with their sentence |
| Row drill | nothing loads | - | - | the papers and the dishes | an unmeasured line listed with "could not be measured" and a link to the blocked-costs queue |
| Branch filter | the panel dims | "This branch has no sales in this window." | the strip | the branch's rows and sentence | a branch with sales and no papers: every row `under` with "no confirmed purchases", the purchase half's own words |
| Coverage line | with the payload | "Every dish sold has a recipe." | the strip | "recipes cover 94% of sales value" | "1 dish sold has no recipe" beside it, a link to `/menu` |

**Journey.** Five seconds: the owner reads "Al Qusais bought 94 kg more sugar than its sales needed" and knows which shelf to look at. Five minutes: opens the row, sees two sacks on one paper on the last day of the week, reads "a single delivery is not a rate", and picks last month from the period picker; the row now says 3 purchases and a gap that means something. Five months: a material that reads `under` every month is a recipe that says 40 g when the kitchen uses 60, and the sentence has said so all along. The consultant's arc: an unmeasured line sends them to the blocked-costs queue, and a material with no pack to the mapping queue, both links already shipped.

**Responsive and accessibility.** The table at 640 px and up with one fixed `colgroup` sized off 640 px so no quantity wraps; cards under it with the difference sentence as the large line; row toggles are real buttons with `aria-expanded`; every touch target 44 px; the sentence is the panel's first content so a screen reader hears the conclusion first; no meaning by colour anywhere, and no colour at all on the direction.

## 5. Proposals for the founder (each with a recommendation)

| # | Proposal | Recommendation and why |
|---|---|---|
| P1 | **Where it lives.** (a) A `usage` block on `GET /api/dashboard` and a fourth panel on `/dashboard`; (b) the material's row on `/materials` gaining a period picker, a branch filter and a second read - the direction `plan.md` §8 named before this decomposition; (c) a new `/usage` route and screen | **(a), the dashboard.** Five of C14's six inputs are already in the dashboard read's memory - the windows, the costed menu with its components and as-of prices, the item sales with their portions - and the sixth is one query; the period, the branch filter and the picker are already on the screen; and the question is the owner's ("where is my money sitting"), which is the dashboard's reader. (b) would put an owner's period question on the consultant's screen, give that screen a period it has never had, and resolve the period and build `_menu_context` a second time for figures that must agree with the panel above them. (c) is a sixth nav word at 390 px, which the shell already cannot fit (`AppShell.tsx:44-47`), for a screen whose every input is the dashboard's. The cost of (a) is a longer dashboard - six blocks - and §4.1 puts the panel last with its own heading so the five-second read is unchanged |
| P2 | **How a line is measured.** (a) The frozen `cost_basis.pack_base_quantity` only, so an uncosted line is unmeasured; (b) re-resolve the pack at read time (`costing.resolve_pack`) for lines with no basis, so a line blocked for a missing unit price with a perfectly readable "25 kg" still counts | **(a).** One door: the factor that measured a line is the factor that costed it, frozen at confirm, so a bought quantity and a bought price can never disagree about what a sack holds, and an override that lands later measures the lines it costs (`0013:44-47`) through the shipped path. (b) is a second resolution with its own rules for which lines it applies to, and the case it rescues - a readable pack on a line with no price - is already on the blocked-costs queue with a person's name on it. The row says "2 lines could not be measured" and links there |
| P3 | **A fourth signal.** (a) No signal in M12: the ranked panel and its answer sentence say "look here first" with no threshold; (b) a "sales needed more than was bought" signal in C13, with a threshold; (c) a "bought far more than needed" signal | **(a).** Both candidate signals are ambiguous by construction: used above bought is a window that started with stock on the shelf **or** a wrong recipe or pack, and bought far above used is a sack on the last day **or** waste, and no threshold tells them apart without a count. A signal that fires on either would be a guess dressed as a rule - the thing C13.2 refused for the price floor - and C13.2 says three kinds. The panel's sentence names the top row without claiming a threshold; the trigger for (b) is in §9 |
| P4 | **Recipe coverage as a third share.** (a) A share of its own - sales value on dishes with a recipe - worded "recipes cover N%"; (b) reuse `costed_share_pct`, so only dishes whose plate produced a cost feed the used figure | **(a).** Usage needs a recipe's quantities and not its price: the seeded Paratha's 2 kg of flour per batch is real usage of a material nobody has bought yet, and (b) would throw it away and hide exactly the row - "13.9 kg used, nothing bought, no pack mapped" - that sends the consultant to the queue. The M9 review's warning about two numbers meaning different things holds and is met by never putting the shares on one row and giving each its own noun: *costed* (contribution), *recipes cover* (usage), *can be costed today* (`/sales`' coverage) |
| P5 | **The ranking key.** (a) Absolute money in the gap, largest first, either direction; (b) over-bought rows only, by money; (c) quantity in display units | **(a).** The owner wants both directions first: where money is sitting (over) and where the data is wrong (under), and the sentence carries the direction word so the ranking need not. (b) hides the recipe-is-wrong row, which is the most valuable thing the panel finds. (c) ranks a kilo of saffron with a kilo of sugar |
| P6 | **Where the purchase half of a branch's label is derived.** (a) Two additive fields on `ratio.BranchRow`, derived in `period_row` beside the sales half; (b) `usage.py` re-derives it from the invoices | **(a).** It is where the sentences already are (`ratio.py:449-466`), it is the exact shape M9 used for the sales half, `test_ratio.py` green proves the `/sales` wire unchanged, and (b) would word "no confirmed purchases" a second time - the thing C9 extended forbade |
| P7 | **When to build.** (a) The plan's trigger: decompose now, build when the pilot's till file shows a quantity column, during M11's pilot fortnight; (b) build now, before M10 and M11, on the committed week | **(a), and it costs nothing to hold.** Nothing in M12 needs a real file to be *built* - the committed week carries quantities and every test stages its own - but the first real file is the first evidence that a real till prints a quantity column at all, and a till that prints values only makes the whole panel `unavailable` for that chain. M10 and M11 are the road to a paying chain; M12 is the first thing that chain asks for after it pays, or the reason it does not, and the pilot's fortnight is when we find out which. If the founder wants it visible for a sales conversation before then, (b) is one wave of two lanes and nothing in this document changes |
| P8 | **"Days of use" beside the gap.** Bought ÷ (used per day) = "bought 34 days of use in a 7-day window", which reads the sack-on-the-last-day case as what it is | **Defer, with the trigger in §9.** It is one more derived number on a row that already carries four, it divides by a rate the window may not have earned (a two-day window has no rate), and the "1 purchase in this window" sentence says the same thing in words. The first owner who asks "how long will that sack last" is the trigger |

## 6. Delegation waves and parallel lanes

| Step | Modules touched | Depends on |
|---|---|---|
| WP-120 usage | `apps/api/src/faida_api/usage.py` (new), `db.py` (one new read), `ratio.py` (two additive fields on `BranchRow`), `apps/api/tests/{test_usage,test_usage_db,test_ratio}.py` | - |
| WP-121 the block | `apps/api/src/faida_api/dashboard.py`, `apps/api/tests/test_dashboard.py` | 120 |
| WP-122 the panel | `apps/web/src/components/Dashboard.tsx`, `apps/web/src/lib/{types,format,dashboardScreen}.ts`, `apps/web/src/lib/mock/dashboard/{*.json,generate.py}`, `apps/web/src/lib/__tests__/dashboardScreen.test.ts` | §3.1's shape; 121 for browser QA and the regenerated fixtures |
| WP-123 act five | `Docs/DEMO_RUNBOOK.md`, `Docs/demo-invoices/koukh-al-shay/{act_four.py,README.md}`, `apps/api/tests/test_demo_seed.py` | 121 |
| WP-124 live | `plan.md`, `TODOS.md`, `README.md`, `CLAUDE.md`, `AGENTS.md`, `Docs/PRD.md` §27.1 | all |

- **Wave 0 (manager, no code):** pin C14, the purchase half and the one block in `plan.md` §7.2 as decided; the rows in §7.3; Decision Log rows from §5 and the review; the `TODOS.md` entries from §9. **No migration and no live schema step.**
- **Wave 1, two lanes.** Lane A = WP-120 (owns `usage.py`, the read, the two fields). Lane B = WP-122 against the mock, `apps/web` only, the block's literals hand-written and hand-checked in the five JSONs. No file overlap; B never waits for A.
- **Wave 2, one lane.** Lane C = WP-121 (`dashboard.py` and its test). It is the only lane that edits a shipped route.
- **Wave 3, two lanes.** Lane D = WP-123 (act five, after C). Lane B again: `generate.py` imports `usage.py`, the fixtures regenerated, the browser QA against the real read.
- **Wave 4: WP-124**, one sitting with the founder, live.

## 7. The tests that gate it

- `tests/test_usage.py` (WP-120): every C14 rule as a pure case with no database - the karak week to the gram; the pair with no quantity; the dish with no recipe and the recipe-coverage share; the unconvertible component; the return; the unmeasured line; the override; no pack mapped; the no-branch paper; the single purchase's sentence; `under` and its two-cause sentence; no price and `money` null; the estimated price making the money estimated; the three halves of the label and their precedence; the chain invariants; the ranking; the answer under both scopes; the standing sentence; and the forbidden-word test over every sentence the module can compose.
- `tests/test_usage_db.py` (WP-120): the new SQL through Postgres, papers confirmed through the real confirm path and an override applied through the real door - what the read returns and what it must not, the basis factor before and after an override, a return's sign, a no-branch paper, and the window roll-up against a hand sum.
- `tests/test_ratio.py`: green unchanged, plus one case that the merged word is the worse of the sales half and the purchase half and that `purchase_notes` is a subset of `notes`.
- `tests/test_dashboard.py` (WP-121): the end-to-end on the seeded stage, the two reconciliations (C14.9), the agreement between the items panel's portions and the materials panel's used figure, the branch scope, the after-period paper, the pending paper, the branch with nothing loaded, and the query count against the enumerated **nineteen**, flat as items, branches and materials grow.
- `tests/test_tenancy.py`: unchanged - no new route and no new table. The new read takes `tenant_id` keyword-only, which the existing convention test covers.
- `tests/test_contribution.py`, `test_signals.py`, `test_menu.py`, `test_plates.py`, `test_costing.py`, `test_sales_api.py`: green unchanged, proving the two `BranchRow` fields are additive and nothing else moved.
- `apps/web/src/lib/__tests__/dashboardScreen.test.ts` (WP-122): the panel's decisions - the five-and-all slicing, the rows-with-no-numbers list, the direction framing, the empty and partial cases, the link builders, the `quantity` formatter's trimming - **and never a sum, a division or a re-ranking**, C13.5's rule.
- Real-browser QA with `/browse` at 1280 and 390 for WP-122, on the mock and then against the seeded week.
- `tests/test_demo_seed.py` (WP-123): act five's named facts on the practice stage; the real stage's top material and money, skipping without the CSV.
- **Regressions, mandatory:** the full API suite green with zero skips on a database; the eval smoke green because no extraction code changes; the web suite, `tsc`, lint and build green.
- Banned as before: tests that grep code text, framework tests, coverage targets for their own sake. The forbidden-word test is not a grep of code: it calls the module and reads its sentences.

### Failure modes, one per new path

| Path | Realistic failure | Test | Handling | User sees |
|---|---|---|---|---|
| Used | a till line on the karak has no quantity | yes (WP-120) | the (branch, karak) pair leaves every material's used figure; the share is lowered and the pair named; the word unchanged | "1 dish left out: lines with no quantity" on the coverage line |
| Used | a dish sold has no recipe | yes (WP-120) | contributes nothing; recipe coverage lowered and named | "recipes cover 94% of this branch's sales value; 1 dish sold has no recipe" |
| Used | a component typed in cups | yes (WP-120) | skipped, the plates sentence on the row | "'cup' does not convert to how Evaporated Milk is measured" |
| Used | the recipe was edited mid-period | yes (WP-120) | the current version, C12.4's rule; the row says which | "recipe version 2" |
| Used | a till that exports day totals only | yes (WP-121) | no lines, no portions, no used figure; the branch's rows are `unavailable` | "This branch's till exports day totals, so what its sales needed cannot be computed." |
| Bought | a bare carton with no pack size | yes (WP-120) | unmeasured; the row incomplete and the count named; the blocked-costs link | "1 line could not be measured - see Can't be costed yet" |
| Bought | a pack size a person entered | yes (WP-120) | measured, estimated, named | "a pack size you entered measures 3 lines" |
| Bought | a return line | yes (WP-120) | nets out by its sign, named | "1 return" |
| Bought | a confirmed paper with no branch | yes (WP-120, 121) | the chain row only, named | "2 papers with no branch, in the chain's figure only" |
| Bought | a pending paper placed in the window | yes (WP-120) | the purchase half `estimated`, the ratio's own sentence | "1 invoice awaiting confirm" beside the row's word |
| Bought | a paper printed in the window and confirmed a week later | yes (WP-121) | `purchased_on` counts it; the figure moves and the drill shows the paper | the paper in the row's list |
| Bought | a paper dated after the period | yes (WP-121) | absent from every row | nothing, which is the point |
| Bought | no pack mapped to the material | yes (WP-120) | a row with used and no bought, incomplete, the plates sentence | "no supplier product is mapped to Atta Flour yet" |
| Bought | one sack on the window's last day | yes (WP-120, 123) | counted; the single-purchase sentence | "1 purchase in this window; a single delivery is not a rate" |
| Gap | sales needed more than was bought | yes (WP-120) | `under`, the two-cause sentence, never negative stock | "its sales needed 3.2 kg more than was bought - either stock from before this window was used, or a recipe quantity or a pack size is wrong" |
| Money | a material with no as-of price | yes (WP-120) | the quantity gap, `money` null, ranked after the rows with money | "no price to value it at" |
| Money | an estimated price | yes (WP-120) | the money estimated, the ingredient named | "at an estimated AED 2.30 per kg" |
| Branch | sales loaded and no papers | yes (WP-121) | every row `under`, the purchase half `incomplete` | "no confirmed purchases 25-31 Aug" |
| Branch | nothing loaded | yes (WP-121) | no rows; the ratio's `unavailable` | the league's row already says it |
| Chain | one branch missing a material's figure | yes (WP-120) | summed over the branches that carry it; the branch named | "Rolla not included in this row" |
| Dashboard read | the read grows with materials | yes (WP-121, query count) | one read whatever the count | nothing; the test is the guard |
| Screen | sixty materials | browser QA | five and "Show all 60 materials" | the panel stays one screen tall |
| Screen | the mock's usage disagrees with the API's | none possible by construction | `generate.py` runs `usage.py` | the mock is a fixture, never a second implementation |
| Words | a sentence says variance | yes (WP-120) | the forbidden-word test fails | nothing shipped |
| Performance | a chain-month of stock lines at line grain | named, not tested | a few hundred rows at pilot scale | nothing today. **Trigger for a summed read beside a drill read: a tenant's confirmed stock lines in one period pass 5,000** |

## 8. Migration and cutover order

1. **There is no migration.** The live project stays at 0019 and there is no paste file. The second milestone in a row with no schema.
2. Rows 120 and 121 merge in Waves 1 and 2; Railway deploys; `/health` ok; `GET /api/dashboard` carries a well-formed `usage` block on a tenant with nothing loaded (no rows, the empty sentence). A block live for a few hours before its panel is the M8 and M9 precedent, and API-before-web is the safe direction.
3. Row 122 merges after row 121 is live; **web deploys after** (`vercel --prod --yes`, manual), because the panel is the first reader of the block.
4. Row 123 is documentation and a test; it merges any time after row 121.
5. Row 124: the founder's sitting.

Rollback: Railway redeploys the previous build and Vercel promotes the previous deployment, both one click, both independent. With no schema change, old code and new code read the same database in both directions. A web rollback alone leaves a block on the wire that nothing reads, which is harmless; an API rollback alone leaves a panel reading an absent block, which the screen must render as its empty state - a `dashboardScreen.test.ts` case.

## 9. NOT in scope, and what already exists

**NOT in scope** (each with its trigger; ten of them go into `TODOS.md` at Wave 0, and the rest already have an entry under M8 or M9 or are a decision already recorded):

- **Stock on hand, opening balances, stock counts, a count sheet through WhatsApp** (PRD §22): trigger: a pilot owner asks for a count by name, or says the ratio is useless because deliveries are lumpy. A count is the first thing that asks the cafeteria to change how it works, and it waits for the customer who asks.
- **Waste, spoilage, staff-meal and transfer entries** (PRD §22): trigger: a chain that records waste, or asks why two branches' gaps differ by a transfer. The standing sentence says these are unrecorded.
- **The append-only inventory ledger, balances as a projection, goods receipts as a separate flow** (PRD §22): trigger: a customer whose received quantities differ from billed ones and says so with a paper. Invoice ≠ goods receipt is a real rule and this milestone measures what was billed.
- **The word variance, and theoretical vs physical**: trigger: a count exists. Until then there is no physical figure and the word has no referent.
- **A fourth signal, "sales needed more than was bought"** (§5 P3): trigger: a material reads `under` for the same branch over two consecutive periods that each hold at least two purchases; that pattern is what makes the reading a recipe rather than a shelf, and the threshold is then measured, not guessed.
- **"Days of use" beside the gap** (§5 P8): trigger: an owner asks how long a delivery lasts.
- **A per-day usage series, a chart, a trend**: trigger: a customer asks for a direction rather than a level; the period picker answers "which window".
- **A per-branch material price valuing each branch's gap at what it paid** (`TODOS.md:604`): the trigger is unchanged; the money on a usage row is at the tenant's as-of price and the row says so.
- **A usage row on `/materials`** (§5 P1 option (b)): trigger: a consultant asks to see the gap while mapping. The dashboard's row links to the material's anchor already.
- **A fifth slot in the daily brief**: M10's four slots are pinned (M9 P8) and a fifth is M10's decision when the template is drafted; C13.5 makes it free when wanted - `usage.answer` is a sentence on the wire.
- **Re-resolving packs for uncosted lines** (§5 P2 option (b)): trigger: a chain where lines blocked for a missing price are a material share of purchases.
- **Theoretical usage for a summary-only till** (M11's day-totals export): a summary day has no quantities and the block says so; nothing derives a quantity from money (C12.6).
- **An as-of recipe read**: C12.4's decision, unchanged, for the same reason.
- **An index on `invoice_lines` for the period read**: trigger: the read passes 500 ms or a tenant's confirmed stock lines pass 100,000. The read walks `supplier_items.ingredient_id` and `invoice_lines.supplier_item_id`, both indexed by 0012, and filters by invoice date.
- Any change to extraction, matching, costing, plates, contribution, signals or the ratio's wire. Two additive fields on `BranchRow` and one keyword nowhere; the tests that prove it are named in §7.

**What already exists and is reused, not rebuilt:** `ratio.period_row` with its clipped window, its `deliveries` and both halves of its label; `ratio.unassigned_group`'s no-branch rule; `ratio.Quality` and `_QUALITY_RANK`; `contribution.item_rows` and `chain_item_rows` with their portions and `no_qty_lines`; `plates.to_base_qty`, `plates.cost_component`'s sentences and `no_recipe_plate`; `costing.DISPLAY_UNITS`, `per_display_unit`'s shape, `LineCost.basis`'s keys and `BLOCKED_REASONS`; `menu._menu_context` with its components and as-of prices; `db.list_period_item_sales`, `list_current_recipe_components`, `list_menu_items`, `list_mapped_pack_costs` (the `purchased_on` expression, copied verbatim into the new read), `list_blocked_costs` (the queue the unmeasured line links to); `dashboard.py`'s reads, adapters, scope and payload; `test_dashboard.py`'s enumerated set and `_CountingPool`; `dashboardScreen.itemPanel`, `incompleteItems`, `itemsHeading` and the link builders; `Dashboard.tsx`'s `ItemTableRow`, `ItemCard`, `ItemDrill` and `colgroup` shapes; `QualityChip`; `format.ts`'s house rule; `mock/dashboard/generate.py` and the scenario switch; the `/invoices/<id>#line-<n>` and `/menu#item-<id>` anchors; `act_four.py`'s staging and `test_demo_seed.py`'s two act-four tests; `build_sales_week.py --practice` and the seeded papers as act five's data.

## 10. Implementation Tasks

Synthesized from this decomposition. Each task derives from a specific row above. Run with Claude Code; checkbox as you ship.

- [ ] **T1 (P1, human: ~1.5 days / CC: ~3h)** - `apps/api` - WP-120: `usage.py` with `PurchaseLine`, `MaterialRow`, `material_rows`, `chain_material_rows`, `recipe_coverage`, `rank`, `answer`, the standing sentence and the display-unit twin of `per_display_unit`; `db.list_period_material_purchases` at line grain; `BranchRow.purchase_quality` and `purchase_notes` derived in `period_row`
  - Surfaced by: §2 (the used side, the bought side, the purchase half); C14.1-11; §5 P2, P4, P5, P6
  - Files: `apps/api/src/faida_api/{usage,db,ratio}.py`, `apps/api/tests/{test_usage,test_usage_db,test_ratio}.py`
  - Verify: `pytest -q`; the forbidden-word test; `test_ratio.py` and `test_sales_api.py` green unchanged
- [ ] **T2 (P1, human: ~4h / CC: ~1h)** - `apps/api` - WP-121: the one new read in `dashboard.py`, the `usage` block to §3.1, the scoped answer, the enumerated list at nineteen
  - Surfaced by: §2 (the dashboard read); C6 extended; §5 P1
  - Files: `apps/api/src/faida_api/dashboard.py`, `apps/api/tests/test_dashboard.py`
  - Verify: the two reconciliations; the portions agreement with `items.all`; the query count flat
- [ ] **T3 (P1, human: ~1 day / CC: ~2h)** - `apps/web` - WP-122: the panel to §4.1, `dashboardScreen.ts`'s decisions, the `quantity` formatter, the types, the fixtures regenerated by `generate.py` importing `usage.py`
  - Surfaced by: §2 (the screen pattern); §4.1; §5 P1, P5
  - Files: `apps/web/src/components/Dashboard.tsx`, `apps/web/src/lib/{types,format,dashboardScreen}.ts`, `apps/web/src/lib/mock/dashboard/`, `apps/web/src/lib/__tests__/dashboardScreen.test.ts`
  - Verify: `npm test`, `tsc`, lint, build; `/browse` at 1280 and 390 walking every state in §4.1's table
- [ ] **T4 (P1, human: ~2h / CC: ~30 min)** - `Docs` + `apps/api` - WP-123: act five in the runbook with figures printed by `act_four.py`, and the seed test's named facts on both stages
  - Files: `Docs/DEMO_RUNBOOK.md`, `Docs/demo-invoices/koukh-al-shay/{act_four.py,README.md}`, `apps/api/tests/test_demo_seed.py`
  - Verify: `pytest tests/test_demo_seed.py`; no figure in §I typed by hand
- [ ] **T5 (P1, human: ~2h / CC: ~30 min)** - live - WP-124: the panel on the real stage, act five walked, the records
  - Files: `plan.md`, `TODOS.md`, `README.md`, `CLAUDE.md`, `AGENTS.md`, `Docs/PRD.md`
  - Verify: the live walk; the loop reset spares the week and the panel
