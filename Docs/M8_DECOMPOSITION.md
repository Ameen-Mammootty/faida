# M8 decomposition - sales ingestion and the first ratio (drafted 2026-09-03)

Status: **eng-reviewed 2026-09-03** (`/plan-eng-review` with two outside voices, Codex and a Claude subagent; the report is at the end of this file), before any feature code; **decided by the founder 2026-09-04** (§5: seven recommendations taken, P6 overridden - the real till export moves to M11 with the pilot), so the rows in `plan.md` §7.3 are approved to build; **Wave 1 (rows 80 and 83) shipped 2026-09-04**, its integration notes in `plan.md`'s Decision Log; Waves 2 and 2b (rows 81, 82 and 85) the same day; **Wave 3 (row 84, the screen) shipped 2026-09-05**; row 86, the live sitting, is what remains.
The session that wrote this ran unattended, so every review question was answered with the recommended option and recorded here as recommended, not as decided; the founder's reply to §5 is the approval.
M6 and M7 were decomposed, reviewed with an outside voice, and only then approved to build; M8 follows the same path.
The founder's inputs for this decomposition, given 2026-09-03: sales arrive as a CSV export from the till; there is no real sales data yet, so the build runs on a seeded week of demo sales for the demo chain, generated from the real menu and its selling prices; the Z-report photo path is not assumed available.

Plan reference: `plan.md` §8 M8 (the checklist and the done-when), §7.2 C4 (money), C8 (provenance), C9 (derived quality), C10 (auth context), §3 (display rules), PRD §10 (sales ingestion), §12-14 (lineage, idempotency, business day), §19 (costing), §23 (profitability), §24 (data quality), §25.3 (signals), §27 (dashboards).

## 1. What M8 is for

M6 costs every plate and M7 makes the product safe for a second chain; neither knows what the chain sells.
Cost per plate says what a karak earns when it is sold; sales say how many were sold, on which branch, and therefore which items and which branches the money actually moves through.
M8 puts the first sales figures in the product and reads the first ratio off them: purchases divided by net sales, per branch per period, ranked, with every purchase figure one click from the invoice photo it came from.

It is deliberately the *first* ratio and not the last.
Item contribution, branch contribution and the signals are M9's (PRD §23, §25.3); the daily brief is M10's.
M8 is the data they all need, one honest ratio on top of it, and the consultant's priority queue for what to cost next: recipe coverage by sales value, which M6 could not compute because it had no sales to weigh the menu by.

**Done when** (from `plan.md` §8, read against the founder's 2026-09-03 decision): a week of sales for the demo chain's branches, loaded from a CSV through the same loader a pilot would use, renders a ranked branch table of purchases divided by net sales where every purchase number drills to an invoice photo, and every row carries its completeness and freshness label.
The checklist's "a week of *real* sales" clause is met at the first pilot upload (M11); until then the seeded week is the gate, because there is no real sales data to gate on and the founder chose to build rather than wait (§5, P4).

## 2. What exists today, and what is missing

Facts from the code as of master `35697f5`, so the review argues about the plan and not about the state.

**Nothing about sales exists.**
No table, column, route, job kind or module mentions sales; the only forward reference is `TODOS.md:36` ("M8's purchases roll-up may want a catalog-level pack").
Z-reports are recognised and discarded: `extraction/schema.py:37` (`Z_REPORT = "z_report"  # stored and politely declined until M8`), `extraction/pipeline.py:135-140` marks the document failed with that classification and replies `REPLY_Z_REPORT` ("I read supplier invoices for now - sales reports are coming soon.", `replies.py:47`).

**The schema carries what the ratio needs on the purchases side.**

- `tenants.currency text not null default 'AED'` (`0001_init.sql:7`); there is no country or VAT column, and the VAT rate is derived from currency by `VAT_RATE_BY_CURRENCY` (`extraction/constants.py:37-44`: AED and OMR 5%, BHD 10%, SAR 15%, QAR and KWD 0%).
- `branches.timezone text not null default 'Asia/Dubai'` (`0001_init.sql:16`) exists and **nothing reads it**; there is no business-day cutoff column anywhere.
- `invoices` carries `branch_id` (nullable, `0001:62`, composite `(tenant_id, branch_id)` FK since `0018:85-86`), `invoice_date date` (nullable, `0001:66`), `confirmed_at` (`0004:7`), `currency` (`0001:67`), `subtotal`, `tax`, `total` as printed (`0001:68-70`), `tax_treatment` and `vat_rate` (`0006:8-10`), `discount_total` and `rounding_amount` (`0007:10-11`), `provenance` (`0011:25`) and `status` in `('draft','awaiting_confirm','confirmed','needs_review','dismissed')` (`0017:28-30`).
- `invoice_lines.line_kind` splits stock lines from charges (`0007:17-18`); `line_total numeric(12,2)` (`0001:88`).
- **No method sums invoices by branch or date.** The only `sum(...)` calls in `db.py` are the per-invoice stock-line sum (`db.py:135`, `db.py:1876`) and the per-supplier-item spend in `list_unmapped_supplier_items` (`db.py:838`); there is no `group by branch_id` and no `date_trunc` anywhere.

**The purchase-date rule is already pinned, three times identically.**
`purchased_on = coalesce(inv.invoice_date, (inv.confirmed_at at time zone 'UTC')::date)` at `db.py:798-799`, `db.py:1337-1338` and `db.py:1381-1382`, filtered to `inv.status = 'confirmed'`, with the rationale at `db.py:763-769`: the printed date first, confirm time only as a tie-breaker, so a stack of last month's invoices cannot overwrite this month's cost.
The ratio's purchases must rank by the same rule or the materials screen and the sales screen will disagree about which week a paper belongs to.

**The net-of-VAT arithmetic exists in two shapes, and neither is the one the ratio needs.**
`_net_price_factor` (`db.py:31-50`) derives a multiplier from the invoice's own `total` and `tax`, never from the stored rate, and `record_confirmed_prices` returns before the catalog when the invoice's currency differs from the tenant's (`db.py:1861-1862`).
`plates.net_of_vat(price, vat_rate)` (`plates.py:172-178`) divides a menu price by `1 + rate` with the rate from `VAT_RATE_BY_CURRENCY` keyed on `db.tenant_currency` (`menu.py:246-247`, `db.py:344-348`).
A whole-invoice net figure is `invoice.total - tax`, computed inline once in `validate.py:222` and stored nowhere.

**Quality labels exist for costs and plates, not for periods.**
`plates.PlateQuality` is `reliable_with_limitations | estimated | incomplete` (`plates.py:51-58`); `verified` is deliberately absent (`plates.py:15-19`, Decision Log 2026-08-29).
`plates.plate()` rolls a plate up to its worst component (`plates.py:200-238`): any missing piece is `incomplete` with no numbers at all (`:217-219`), any estimated component makes the plate estimated (`:226-230`).
`provenance.asserted_fields()` (`provenance.py:160-172`) is the read C9 says a derivation makes; `READ_ORIGINS` and `ASSERTED_ORIGINS` are at `provenance.py:76` and `:81`.
Nothing yet says what *incomplete* or *estimated* means for a figure summed over days, which is what C9's amendment in §3 pins.

**There is no branches endpoint, and a paper can have no branch.**
C6 lists none; the upload screen derives its branch choices from the invoice list and says so (`UploadInvoice.tsx:51-52`: "Branch choices come from the invoice list (C6 has no branches endpoint); with no invoices yet the select simply stays hidden - branch is optional").
`POST /api/documents` takes `branch_id` as an optional form field (`api.py:913`) and manual entry as an optional body field (`api.py:729`, `:808-812`); both refuse a foreign branch and both accept none.
So a confirmed invoice with `branch_id` null is a real state on the console path, and a ratio grouped by branch would count it nowhere.

**The audit spine is one function with sixteen actions.**
`_insert_audit_event(conn, *, tenant_id, actor, action, subject_type, subject_id, detail)` (`db.py:189-198`) takes the connection so it commits with what it records.
Actions today: `invoice.created_by_hand`, `invoice.confirmed`, `invoice.cash_approved`, `invoice.dismissed`, `invoice.corrected`, `ingredient.created`, `supplier_item.mapped`, `supplier_item.unmapped`, `supplier_item.pack_size_set`, `supplier_item.mapping_rejected`, `menu_item.created`, `menu_item.price_changed`, `menu_item.category_changed`, `menu_item.archived`, `menu_item.unarchived`, `recipe.version_created` (`db.py:600-1647`).
Subject types: `invoice`, `ingredient`, `supplier_item`, `menu_item`, `recipe`.

**The tenancy discipline a new table and route must join.**

- `AuthContext(user_id, tenant_id, actor)` (`auth.py:65-75`); `require_context` (`auth.py:227`); both routers declare it at router level and per handler (`api.py:119-120`, `menu.py:66-67`).
- The composite pattern: `branches unique (tenant_id, id)` (`0018:80`), `menu_items unique (tenant_id, id)` (`0015:33`), `invoices unique (tenant_id, id)` (`0017:52`), and every child FK is `(tenant_id, parent_id)` (`0015:57`, `0017:56-58`, `0018:82-86`).
- `tests/test_tenancy.py` generates its matrix from the production router table (`routes_of`, `:77-91`); `PUBLIC_ROUTES` (`:45-53`) is the deliberate public list; `test_the_matrix_covers_every_non_public_route` (`:121-128`) fails on any route with no `MATRIX` entry; `TENANT_TABLES` (`:56-70`, 13 tables) is what `counts_for` (`:291-297`) proves tenant B never wrote into; the `rig` fixture mounts every router by name (`:142-145`).
  A new router must be added to the rig, a new tenant-owned table to `TENANT_TABLES`, and every new route to `MATRIX`, or CI fails.
- 647 API tests collected (`pytest --collect-only -q`), zero skips with `TEST_DATABASE_URL`.

**The CSV loader precedent (WP-64) is three files with a clean split.**

- `apps/web/src/lib/csv.ts` is generic and domain-free: `parseCsv(text): CsvResult` (`:97`), BOM stripped (`:41`), RFC 4180 quoting (`:56-68`), comma only by design (`:11-12`), CRLF handled (`:74-76`), three file-level refusals - empty (`:98-100`), a spreadsheet binary sniffed and told to Save As CSV (`:102-109`), a header with under two columns (`:115-122`).
  It has no row cap, does not refuse an unterminated quote, and pads a ragged row to blank cells (the consumer at `menuLoad.ts:338` reads a missing cell as `""`).
  **Reused, hardened in place (row 83).**
- `apps/web/src/lib/menuLoad.ts` owns the menu's columns: an alias map per logical column (`COLUMNS`, `:39-49`), `normalizeHeader` (`:75-81`), `REQUIRED` (`:54-61`), the parsed shapes `LoadLine` (`:181-192`) and `LoadItem` (`:261-276`), and `planLoad` (`:428-518`) which predicts `new | unchanged | new_version | blocked` before commit by the same semantic-equality rule the door applies (`sameRecipe`, `:538-552`; the door's copy is `recipes.recipes_match`, `recipes.py:68-71`).
  Money stays a string cell to wire (`:22-23`); no float anywhere.
  **Column recognition is by fixed aliases and is not saved per tenant**; a till's headers will not match any alias list, which is why M8 needs a saved layout (C11).
- `apps/web/src/components/MenuLoader.tsx`: phases `idle | reading | ready | loading | done` (`:67`); one request per recipe, sequential, in file order (`:268-288`); rows restamped from the door's answer (`:292-301`); the grid stays after commit (it is keyed on the items, `:526-566`, not on the phase) under a summary bar with a primary link onward (`:439-468`); desktop-only, stated (`:364-367`); the file input clears its value so re-picking the same filename fires again - the fix loop (`:388-392`).
  New materials are offered once each, ranked by how many items each unblocks (`newMaterials`, `menuLoad.ts:213-230`), one click per material, never bulk (`api.py:1215-1218`).

**The propose-then-approve door (WP-52) is the mapping precedent.**
`matching.propose_ingredients(ingredients, canonical_name, *, rejected_ids=())` (`matching.py:261-297`) proposes and never decides, pack-blind, threshold `INGREDIENT_PROPOSAL_THRESHOLD = 0.70` (`:74`) with the measured reason it goes no lower (`:59-73`), at most three (`:75`).
The routes: `GET /api/supplier-items/unmapped` (`api.py:1247`), `POST .../ingredient` (approve and remap, `:1286`), `DELETE .../ingredient` (unmap, `:1357`), `POST .../ingredient/reject` (`:1507`), each one audit row in its own transaction (`db.py:959-1051`, `:1179`); a cross-tenant material raises before any write (`db.py:1006-1007`) and Postgres refuses it anyway through the composite FK.
The screen (`RawMaterials.tsx`): one row per unmapped pack ranked by money spent, numbered proposal buttons, keyboard 1-3 / R / N (`:202-226`), one write door `decide()` (`:173-192`), and an Unmap on every mapped pack (`:672-685`).

**The demo stage, both halves.**

- The practice stage (`supabase/demo_seed.sql`) stages tenant `d0000000-0000-0000-0000-000000000001` ("Karak Al Khaleej Cafeterias", AED, `:213-215`) with three branches, all `Asia/Dubai` (`:217-226`): Al Qusais (`...0011`; the seed leaves every `wa_phone_e164` null and the founder's one manual step at `:509-519` points their phone here), Al Nahda (`...0012`), Rolla (`...0013`).
  **It stages four confirmed invoices** on Al Qusais - Gulf Foods and Al Madina, at `now() - 35 days` and `now() - 28 days`, all exclusive 5% VAT (`:345-376`) - with ten costed lines (`:387-432`) and a five-item menu (`:436-447`).
  Its reset deletes by tenant (`:120-205`) and refuses to run over more than 20 menu items (`:96-109`).
- The real stage's reset is `supabase/demo_reset_loop.sql`, scoped to the props' printed invoice numbers (`:46`) and listing what it never touches (`:30-38`); the loaded 45-item menu and its 81 materials survive it by construction.
- The papers: KAS-1 and KAS-2 print 24/08/2026, KAS-3 and KAS-4 print 25/08/2026, KAS-5 (the on-stage paper) prints 31/08/2026 (`Docs/demo-invoices/koukh-al-shay/KAS-*.prompt.txt:19`); totals 776.00, 3,001.95, 5,335.79, 4,285.00 and 2,873.33, all exclusive 5% (`README.md:32-38`).
  Costing ranks by the printed date, so **a week of sales ending 31 August contains KAS-3, KAS-4 and, once confirmed on stage, KAS-5**: the ratio can move live in the same forward that moves the plates.
- The real 45-item menu CSV is **not in the repo**: `~/Downloads/Menu engineer/koukh-al-shay/faida-loader-preview.csv` (45 items, item codes `52a`-`64c` and `126`-`146`, two categories, prices VAT-inclusive), referenced from `plate_costs.py:49` as `DEFAULT_CSV` with a `--csv` override.
  `plate_costs.py:35-45` is the precedent for a demo script that imports the shipped code (`sys.path` to `apps/api/src`, then `from faida_api import costing, plates`), and it needs no database and no key.
- `Docs/DEMO_RUNBOOK.md` is §A-F: preconditions, the script, two resets (§C), the failure playbook, the logs and act two (§F, `:291`).
  Act three does not exist.

**The web app's seams a new screen must join.**
`GATED_PREFIXES = ["/invoices", "/materials", "/menu"]` (`gate.ts:22`) and its test's `GATED` and `OPEN` arrays (`gate.test.ts:11-37`, plus the list inside the `needsSession` test at `:149`); `AppShell`'s `current` union (`AppShell.tsx:18`, `:21`) and its three nav entries (`:48-68`); a `layout.tsx` per route (`app/menu/layout.tsx:9-11`).
`api.ts` is the single chokepoint with the mock switch (`:91`) and one short wrapper per endpoint (23 today, four to nine lines each), and every endpoint also needs a mock implementation in `mock/*.ts` and its request and response types in `types.ts`; mocks compute no money (`mock/menu.ts:1-20`) and carry a bigint `Dec` for the one place arithmetic is unavoidable (`mock/decimal.ts`).
`format.ts`: `roundedAed` takes the integer part and groups thousands (`:57-61`); `money` pads to two decimals by string operations (`:17-26`); `formatDate` is string-only (`:113-118`); **there is no percent formatter** - percentages arrive from the API as one-decimal strings and render with a literal `%` (`MenuMargins.tsx:372`).
vitest runs `src/**/__tests__/**/*.test.ts` in a node environment (`vitest.config.ts:9-10`); CI's web job runs lint, `npm test`, `tsc` and build.

## 3. Contracts to pin before fan-out (C11 new; C9 amended; C6 and C8 extended; C10 and C2 untouched)

- **C11 - The sales row and the ratio.**
  1. *The canonical row is item-wise:* one row per (branch, business date, till item name, quantity, amount), from the till's item-wise report.
     Daily totals are a sum.
     ~~A summary-only export (branch, business date, amount) is accepted by the same loader with no item column mapped and stored as a `summary` day with no lines; a summary day carries net sales and no coverage.~~ **Amended by the founder 2026-09-04, after Wave 1: item-wise only for the MVP. A `summary` day is a closed day (amount 0) and nothing else; a day-totals export moves to M11 with the pilot (`plan.md` Decision Log, `TODOS.md`).**
     ~~A file is one shape throughout; two rows for one branch-day in a summary file stop the day with a sentence.~~ (Retired with the summary shape, 2026-09-04; two entries for one branch-day in one body are still refused.)
     *A layout maps logical columns to header names, never to positions* (`columns` is `{logical: header_name}`), so a reordered export applies the saved layout unchanged and a renamed mapped column stops it (outside voice 9).
     *A till's branch label is the chain's fact, not the layout's*: `branch_aliases` is its own tenant-owned table keyed on the normalised alias, taught once and reused by every layout (outside voice 10).
     *The raw file is kept* (PRD §12): the browser posts it once to `POST /api/sales/files`, the API computes the sha256 and stores the bytes immutably at `{tenant_id}/sales/{sha256}.csv` through `storage.py` (`x-upsert: false`, the documents precedent), and every day loaded from it carries that hash - so a figure on the screen traces to the bytes it came from, and the hash is never the client's word (outside voice, Codex 4).
  2. *Net sales* is the till's own net figure per row, converted to ex-VAT once, in the tenant's currency, summed per branch per business day.
     The file's amounts are read as VAT-inclusive or VAT-exclusive per saved layout (chosen once, on the first upload of that layout, and shown on every preview after), the rate is `VAT_RATE_BY_CURRENCY[tenant.currency]` - the C4 table, the same lookup WP-61's margin uses - and `net_amount = amount / (1 + rate)` quantized `ROUND_HALF_UP` to a fil per line, with the day's `net_sales` the exact sum of its lines.
     The printed amount, the basis and the rate are stored beside the net figure (C4: stored as printed, derived beside it), and so are the printed item name and code on every line - the resolved `till_items` row is the identity, the printed text is the evidence (outside voice 5).
     Discounts, refunds and voids are whatever the till exported as rows; negative amounts are legal and reduce the day.
     There is no currency column: a till exporting in a currency other than the tenant's is nobody's ask (§2 rule 8).
  3. *Business day* is the till's own date on the row, taken as a calendar date; Faida applies no cutoff arithmetic to a daily export, and `branches.timezone` stays unread.
     A purchase's business day is its printed invoice date, falling back to the confirm date exactly as costing does (`purchased_on`).
     A cutoff column enters with the first transaction-level source (PRD §14; `TODOS.md`).
  4. *Identity and idempotency* (PRD §13): the unit is the branch-day, unique on `(tenant_id, branch_id, business_date)`.
     A day is **unchanged** when the incoming day has the same granularity, the same basis and the same multiset of (normalised name, code, qty, amount) as the stored one, in any order; nothing is written and no audit row appears.
     Otherwise the day is **replaced** inside one transaction - lines deleted and re-inserted, the day row updated - with one `sales_day.replaced` audit row carrying the previous and new net sales, line counts and file hashes.
     A first load writes `sales_day.loaded`.
     Re-uploading the same file is therefore a no-op, a corrected file replaces exactly the days it carries, and nothing is ever double-counted.
     A partial-day export replaces the whole day, by design and visibly: the preview shows every replaced day as before and after ("25 Aug: AED 4,310 to AED 1,120, 41 rows to 12"), and **a day whose net or line count would fall is blocked until the consultant confirms that day by name** - the drift stop's shape, one tick per shrinking day, never a bulk "replace all" (Codex 2 and outside voice 6, in agreement).
     A day inside a file's own date range for a branch that has no rows is loaded as a takings-0 day and shown in the preview as such ("29 Aug: no rows in the file, loaded as a zero day"), because the till's export range is the till's own statement of the days it covers; a day outside every file's range is a gap (Codex 8).
     The identity is one consolidated report per branch-day; a second sales stream on the same branch-day (a second till, a delivery aggregator's report) is nobody's ask yet and is a `TODOS.md` entry with its trigger, and the day row keeps the layout it came from so the backfill is one update when it comes (Codex 5, deferred).
     A retry of a request that already landed is unchanged, so the loader is safe under a refresh mid-run (WP-71's rule).
     The door takes a list of branch-days (at most 31 per request, one branch-month) and runs **one transaction per day**, answering an outcome per day, so a year of history at onboarding is a few dozen requests rather than a thousand (review finding 14).
     A closed day is recorded as a summary day with takings 0, never inferred from a gap; the template shows one.
     A business date after tomorrow or before 2020 is refused with a sentence, because a swapped day and month lands in the future (review finding 9).
  5. *Purchases* for a branch and period are the invoices with `status = 'confirmed'` (not awaiting, not held, not dismissed), `branch_id` the branch (resolved from the phone, never from paper), `purchased_on` inside the period, and `currency` the tenant's.
     The figure per invoice is **`total - coalesce(tax, 0)`**: two printed numbers, the whole paper ex-VAT, charges and discounts as the supplier billed them, on a cash basis (PRD §10 - counted when invoiced, never when consumed).
     A confirmed invoice always has a total (`_confirm`'s `total is not null`, `db.py:2185-2187`); an inclusive invoice always has a tax (C4); an exclusive one with no tax is net already.
     The figure is immune to the per-line VAT question in `TODOS.md`, because the printed tax is the printed tax whatever the lines' rates were.
     **A confirmed invoice with no branch is counted in no row and is never dropped:** the read returns it in an unranked "No branch" group with its figure and its invoices, so the owner sees purchases the ranking could not place (review finding 1).
  6. *The ratio* is `purchases / net_sales`, `Decimal`, quantized to a tenth of a percent, per branch per period, and is **labelled "purchases ÷ net sales (cash basis)"** on every surface - the M8 checklist's own words and the July design doc's non-negotiable naming rule.
     It is never labelled food cost %, because it is not one: purchases are what arrived, not what was consumed, and no stock count corrects the difference (PRD §22 is post-MVP).
     A branch with net sales and no confirmed purchases shows no ratio at all, never 0%; a branch whose net sales for the period are not positive (a refund-heavy or empty till) shows no ratio either, reads incomplete, and says so (Codex 11 and outside voice 3, in agreement).
     The default period is **28 days**, with 7 as the option: on a cash basis a week mostly ranks who took a delivery, and four weeks averages the lumpiness (outside voice 15); every row says how many deliveries its window holds.
     The screen states the direction in words - "higher means more of every dirham taken went to suppliers" - because the menu screen's identical grammar puts the winner on top and this table puts the branch to look at first on top.
  7. *Mapping never decides.* A till item is a `till_items` row minted on first sight, identified by the till's own **code when the file has one** and by the normalised name otherwise (a code survives a rename and two products never share one; a rename under the same code updates the display name, keeps the mapping and writes `till_item.renamed` - Codex 7); `menu_item_id` is set by a person, one keystroke each, from proposals the matcher ranks with the WP-52 scorer and threshold.
     An exact name still needs its keystroke (M5's rule; a 45-name till is 45 keystrokes once).
     A name that is not a menu item (a delivery charge, a discount line) is marked so, stays in net sales, and leaves the queue; mapping it later un-marks it.
     Every line with that name follows the mapping, derived at read time - a remap corrects every day at once, and nothing stores a menu item per line.
  8. *Coverage by sales value* over a period is the positive net value of lines whose till item maps to a menu item whose plate is not `incomplete`, over the positive net value of item-granularity lines that are not marked "not a menu item" - refund lines count in net sales and not in coverage, and a delivery charge is takings but not menu sales, so the figure is bounded 0-100% and can reach it (Codex 11, outside voice 8); refunds and non-menu value are reported beside the figure, never inside it (summary days too, until the 2026-09-04 amendment retired them).
     The word is **costed, never complete**: "Costed: 78% of sales value, 12 points of it on estimated plates" - an estimated plate counts as costed and is named as estimated, because "complete costing" over plates `plates.py` refuses to call verified would be the C9 sin one layer up (outside voice 7).
     Uncosted revenue is named in two buckets: mapped but the plate cannot be costed, and not yet mapped.
- **C9 amended - completeness and freshness for period figures.**
  A figure summed over days carries the quality of its inputs and of its *gaps*, in PRD §24's vocabulary, never `verified`.
  A row's window is the period clipped to the branch's own loaded sales range - it ends on that branch's newest loaded day and starts on its oldest inside the period - and the row says so ("25-31 Aug, 7 days"); purchases are counted over the same clipped window, so two days of sales are never set against seven days of deliveries, and a branch that uploads later than its siblings reads fresh-to-a-date rather than permanently incomplete (outside voice 11).
  For a branch-period row: **unavailable** when the branch has neither a sales day nor a counted purchase in the period (the row still carries the branch's newest sales day ever, so "last sales 25 Aug" is visible); **incomplete** when a day strictly inside the branch's window has no sales row (a closed day is a loaded zero, never a gap), when the branch has purchases and no sales in the period (purchases shown, net sales absent, ratio withheld - a branch's papers are never hidden by a missing upload, outside voice 4), or when the branch has sales and no *counted* purchase in the window (net sales shown, ratio withheld, and any exclusion sentence rides along); **estimated** when an invoice for the branch is still `awaiting_confirm` or `needs_review` and is placed inside the period by its printed date or, when it has none yet, by the day it arrived (`created_at`; a pending paper has no confirm time, so the costing rule alone would drop it from every period - Codex 9), with "undated" in the sentence, when a confirmed invoice inside the period was excluded for a foreign currency, or when a counted invoice's `total` or `tax` has an asserted origin (`ASSERTED_ORIGINS`, exactly C9's read); otherwise **reliable with limitations**, because a till's figures are its own word and nothing cross-checks them.
  Precedence is unavailable over incomplete over estimated.
  Every row carries the sentences that made its label ("2 of 7 days have no sales", "1 invoice awaiting confirm", "1 invoice in USD not counted", "3 deliveries in this window"), and its freshness as facts: the newest sales day and the newest purchase date, so a screen can say "sales to Mon 31 Aug".
  **A chain total row reconciles the table**: net sales, purchases and the ratio over every branch row plus the "No branch" group, and a test pins that the total equals the sum of the rows, so purchases cannot vanish between the papers and the screen (outside voice 4).
  The coverage figure carries the same rule: it is estimated when any counted plate is, and named the summary-only days beside it until the 2026-09-04 amendment retired them - no summary day carries money now, so there is nothing to name.
- **C6 extended.** The response shapes are pinned in §3.1 so the web lanes build against them, not against prose (outside voice 2). `GET /api/branches` (the tenant's branches: id, name, timezone - the console has needed this since the upload screen and worked around it), `GET /api/sales/days?from&to`, `POST /api/sales/days` (a list of branch-days, one transaction each, an outcome each), `GET /api/sales/layouts`, `POST /api/sales/layouts` (upsert by header key), `GET /api/sales/branches?from&to` (the ratio table with its drill), `GET /api/sales/coverage?from&to` (coverage and the queue), `POST /api/till-items/{id}/menu-item` (approve and remap), `DELETE /api/till-items/{id}/menu-item` (unmap), `POST /api/till-items/{id}/exclude` (not a menu item).
  Money as strings, one-decimal percentages as strings, dates ISO.
  The JSON shapes are pinned in §4's rows so the web lanes mock against them.
- **C8 extended.** New actions: `sales_day.loaded`, `sales_day.replaced`, `sales_layout.saved`, `till_item.mapped` (remap carries `previous_menu_item_id`), `till_item.unmapped`, `till_item.excluded`.
  Subject types `sales_day`, `sales_layout`, `till_item`.
  Actors are `ctx.actor` from the context, never from a form.
- **C7.** Migration 0019, one file, the four tables in §4 row 80, applied live from `Docs/apply_m8_migrations.sql` before the code that reads them merges (§8).
- **C10 untouched.** Every new route takes `Context`; every new `db.py` method takes `tenant_id` keyword-only and puts it in the `WHERE`; a foreign row is 404.
- **C2 untouched.** Sales upload is a synchronous door like the menu loader, not a job; the jobs table stays the WhatsApp queue.
  The one place M8 touches the queue is nowhere.

### 3.1 Wire shapes (pinned for the web lanes; money and percentages as strings, dates ISO)

```
GET /api/branches
  {"branches": [{"id": "d0…0011", "name": "Al Qusais Branch", "timezone": "Asia/Dubai",
                 "aliases": ["AL QUSAIS", "QUSAIS 1"]}]}
POST /api/branches/{id}/aliases   {"alias": "QUSAIS 1"}
  201 {"alias": {"id": "…", "branch_id": "…", "alias": "QUSAIS 1", "alias_key": "qusais 1"}}
  409 when the alias already names another branch

POST /api/sales/files   (multipart: file)
  201 {"sha256": "…64 hex…", "filename": "sales-week.csv", "bytes": 18342}   (a second post of the same bytes: 200, same hash)

GET /api/sales/layouts
  {"layouts": [{"id": "…", "name": "Main till", "header_key": "amount|date|item|outlet|plu|qty",
                "columns": {"branch": "Outlet", "date": "Date", "item": "Item", "code": "PLU",
                            "qty": "Qty", "amount": "Amount"},
                "amount_basis": "inclusive", "date_order": "dmy", "updated_at": "2026-09-03T18:00:00Z"}]}
POST /api/sales/layouts   {"name", "columns", "amount_basis", "date_order"}   -> 201 or 200, {"layout": {…}}
  (header_key is derived server-side from the mapped header names, sorted; the client never sends it)

GET /api/sales/days?from=2026-08-25&to=2026-08-31
  {"days": [{"id": "…", "branch_id": "…", "business_date": "2026-08-25", "granularity": "item",
             "amount_basis": "inclusive", "vat_rate": "0.05", "takings": "4525.50", "net_sales": "4310.00",
             "line_count": 41, "layout_id": "…", "source_sha256": "…", "source_filename": "sales-week.csv",
             "loaded_by": "user:…", "loaded_at": "…",
             "lines": [{"position": 0, "name": "KARAK TEA FLASK 1L", "code": "52a", "qty": "14",
                        "amount": "490.00", "net_amount": "466.67", "till_item_id": "…"}]}]}
POST /api/sales/days
  {"days": [{"branch_id": "…", "business_date": "2026-08-25", "granularity": "item", "amount_basis": "inclusive",
             "layout_id": "…", "source": {"sha256": "…", "filename": "sales-week.csv"},
             "lines": [{"position": 0, "name": "KARAK TEA FLASK 1L", "code": "52a", "qty": "14", "amount": "490.00"}]},
            {"branch_id": "…", "business_date": "2026-08-29", "granularity": "summary", "amount_basis": "inclusive",
             "layout_id": "…", "source": {…}, "amount": "0.00"}]}
  200 {"days": [{"branch_id": "…", "business_date": "2026-08-25", "outcome": "loaded" | "unchanged" | "replaced",
                 "previous": {"net_sales": "4310.00", "line_count": 41} | null, "day": {…the day without lines…}}]}
  422 for more than 31 days, or a bad row (the day and the position named); 404 for a foreign branch

GET /api/sales/branches?from=2026-08-04&to=2026-08-31
  {"period": {"from": "2026-08-04", "to": "2026-08-31", "days": 28, "default": true, "sales_through": "2026-08-31"},
   "rows": [{"branch_id": "…", "branch_name": "Al Qusais Branch",
             "window": {"from": "2026-08-25", "to": "2026-08-31", "days": 7},
             "net_sales": "30120.00", "takings": "31626.00", "purchases": "9162.65", "ratio_pct": "30.4" | null,
             "quality": "reliable_with_limitations" | "estimated" | "incomplete" | "unavailable",
             "notes": ["3 deliveries in this window"], "days_loaded": 7, "days_missing": 0, "deliveries": 3,
             "sales_through": "2026-08-31", "last_purchase_on": "2026-08-25",
             "days": [{"business_date": "2026-08-25", "net_sales": "4310.00", "granularity": "item", "purchases": "9162.65",
                       "invoices": [{"invoice_id": "…", "supplier_name": "…", "invoice_no": "AAF-2026-3318",
                                     "purchased_on": "2026-08-25", "net_purchase": "5081.70", "total": "5335.79",
                                     "tax": "254.09", "quality": "reliable_with_limitations" | "estimated"}]}],
             "pending": [{"invoice_id": "…", "supplier_name": "…", "invoice_no": "…", "status": "awaiting_confirm",
                          "placed_on": "2026-08-30", "undated": false}],
             "excluded": [{"invoice_id": "…", "supplier_name": "…", "invoice_no": "…", "currency": "USD", "total": "120.00"}]}],
   "unassigned": {"count": 0, "purchases": "0.00", "invoices": []},
   "total": {"net_sales": "…", "purchases": "…", "ratio_pct": "…" | null, "quality": "…", "notes": […]}}

GET /api/sales/coverage?from&to
  {"period": {…}, "sales_value": "52000.00", "costed_value": "40560.00", "costed_pct": "78.0", "estimated_points": "12.0",
   "uncosted": {"incomplete_plate": "3120.00", "unmapped": "8320.00"},
   "beside": {"refunds": "-210.00", "not_menu_items": "640.00"},
   "queue": [{"till_item_id": "…", "name": "CHKN 65 DRY", "code": "131", "value": "3120.00",
              "proposals": [{"menu_item_id": "…", "name": "Chicken 65 Dry", "score": "0.91"}]}],
   "mapped": [{"till_item_id": "…", "name": "…", "code": "…", "value": "…", "menu_item_id": "…",
               "menu_item_name": "…", "plate_quality": "reliable_with_limitations" | "estimated" | "incomplete"}],
   "excluded": [{"till_item_id": "…", "name": "DELIVERY CHARGE", "value": "640.00"}]}

POST /api/till-items/{id}/menu-item   {"menu_item_id": "…"}   -> {"till_item": {…}}
DELETE /api/till-items/{id}/menu-item                          -> {"till_item": {…}}
POST /api/till-items/{id}/exclude                              -> {"till_item": {…}}
```

The demo till export's header, pinned so rows 83 and 85 agree without meeting: `Outlet,Date,PLU,Item,Qty,Amount`, dates `dd/mm/yyyy`, amounts VAT-inclusive as a till prints them, one file for the three branches.

## 4. Work packages

Sizes as in §7.3: S ≤ half an agent-day, M ≈ one, L = multi-day.
Acceptance is demonstrable, never documentary.
Waves per §6.

| WP | What | Size | Depends | Acceptance |
|---|---|---|---|---|
| 80 | **The sales tables and the one write door.** Migration 0019, in the 0012/0018 shape, all five tables `tenant_id` not null with deny-all RLS: `sales_daily (id, tenant_id, branch_id not null, business_date date not null, granularity check in ('item','summary'), source check in ('csv'), amount_basis check in ('inclusive','exclusive'), vat_rate numeric(6,4), takings numeric(12,2) not null, net_sales numeric(12,2) not null, line_count int not null, source_sha256 text, source_filename text, loaded_by text not null, loaded_at timestamptz not null, unique (tenant_id, branch_id, business_date), unique (tenant_id, id), foreign key (tenant_id, branch_id) references branches (tenant_id, id))`; `sales_lines (id, tenant_id, sales_day_id, position, till_item_id, name text not null, code text, qty numeric(12,3), amount numeric(12,2) not null, net_amount numeric(12,2) not null, unique (sales_day_id, position), composite FKs to sales_daily (on delete cascade, for the resets) and till_items)` - the printed name and code on the line are the evidence, the till item is the identity; `till_items (id, tenant_id, name text not null, name_key text not null, code text, menu_item_id uuid, excluded_at timestamptz, created_at, unique (tenant_id, code) where code is not null, unique (tenant_id, name_key) where code is null, unique (tenant_id, id), foreign key (tenant_id, menu_item_id) references menu_items (tenant_id, id))`; `sales_layouts (id, tenant_id, name text not null, header_key text not null, columns jsonb not null, amount_basis, date_order check in ('dmy','ymd'), created_at, updated_at, unique (tenant_id, name))`; `branch_aliases (id, tenant_id, branch_id, alias_key text not null, alias text not null, created_at, unique (tenant_id, alias_key), unique (tenant_id, id), foreign key (tenant_id, branch_id) references branches (tenant_id, id))` with `POST /api/branches/{id}/aliases` writing `branch_alias.saved` - the layout's identity is its name (the till, as the consultant calls it) and the header is compatibility evidence, so two tills with the same column names but a different date order or VAT basis are two layouts (Codex 6). `sales_daily` carries `layout_id` and `source_sha256`, and `POST /api/sales/files` (multipart) stores the raw CSV immutably and returns the server-computed sha256 (C11.1). A new router `sales.py` (prefix `/api`, the router-level auth dependency, `Context` per handler, mounted in `main.py` and in the tenancy rig) with `GET /api/branches` (id, name, timezone, scoped) and `POST /api/sales/days` taking `{days: [{branch_id, business_date, granularity, amount_basis, source: {filename, sha256}, lines: [{position, name, code, qty?, amount}]}]}` (an item day) or `{..., amount}` with no lines (a summary day; amount 0 is a closed day), at most 31 days per request, one transaction and one outcome per day, `extra="forbid"`, money as signed decimal strings validated with the by-hand door's helpers, `qty` optional, a business date after tomorrow or before 2020 refused with a sentence, `source_filename` stored as a label and never as identity; the pure rules in a new `takings.py` (`name_key`, `till_item_key` (code first, name second), `day_key`, `net_amount` - its own three lines quantizing to a fil, because `plates.net_of_vat` quantizes to a tenth of a fil and the day must equal the sum of its stored lines exactly (Codex 10) - the one-shape-per-file check, the interior-gap rule) so the mock and the tests read them from one place; `db.load_sales_day(*, tenant_id, ...)` as one transaction: `for update` on the day row, `till_items` minted by code or name key with `on conflict do nothing` and renamed under a known code with `till_item.renamed`, C11.4's unchanged / replaced / loaded outcomes with their audit rows, the branch checked against the tenant before any write (`db.get_branch`). `GET /api/sales/days?from&to` returns the stored days with their lines so the loader can predict. `GET /api/sales/layouts` and `POST /api/sales/layouts` upsert by name with `sales_layout.saved`. `Docs/apply_m8_migrations.sql` with a `needs_0019` pre-flight | M/L | C11 | `tests/test_sales_load.py` against real Postgres: a first load answers `loaded` with one `sales_day.loaded` row; the same day again answers `unchanged` and writes nothing (audit count unchanged); the same rows reordered are unchanged; a changed qty answers `replaced` with one `sales_day.replaced` row carrying both net figures and both hashes, and the day's lines are exactly the new file's; inclusive 105.00 stores net 100.00 and exclusive 100.00 stores 100.00, to the fil, summed per day; a negative refund row reduces the day; a summary day stores net sales and zero lines (from 2026-09-04 only as a closed day with amount 0; money on a summary day is refused); two entries for one branch-day in one body are refused with the sentence; a till name seen on three days is one `till_items` row; a foreign `branch_id` is 404 from the API and refused by Postgres; a foreign `menu_item_id` on a till item is refused by Postgres; a date after tomorrow is refused with the sentence; a takings-0 summary day loads as a day; a 31-day body answers 31 outcomes and a 32-day body is 422; two clients posting the same day at once both succeed and the second reads `unchanged` (the `for update` row lock); the layout upsert saves once and updates on the second call, and a layout saved by one member is read by another member of the same tenant; `GET /api/branches` lists the tenant's branches and none of tenant B's; a posted file is stored once under its server-computed hash and a second post of the same bytes answers the same hash without a second object; a renamed item under a known code keeps its mapping and writes `till_item.renamed`; a pending invoice with no printed date is placed by its arrival day; a period whose net sales are not positive answers no ratio and the sentence; the day's `net_sales` equals the sum of its stored `net_amount`s over a hundred lines of non-exact divisions; every new route is in the tenancy matrix and the four tables in `TENANT_TABLES`; the 647 existing tests stay green |
| 81 | **The ratio, derived on every read, labelled by its gaps.** A pure `ratio.py` (no I/O, `Decimal` only): `period_row(branch, days, invoices, period)` returning net sales, takings, purchases, `ratio_pct` (quantized `0.1`, `ROUND_HALF_UP`), `quality` per the C9 amendment with precedence, `notes` (the sentences), `days_loaded`, `days_missing`, `sales_through`, `last_purchase_on`, the per-day breakdown and the per-invoice figures (`net_purchase = total - coalesce(tax, 0)`), plus `pending` and `excluded` invoice lists, and an `unassigned` group for confirmed invoices with no branch (count, purchases, invoices; never ranked); and `coverage(lines, mappings, plates, period)` per C11.8 with its uncosted buckets (the summary-only day count retired by the 2026-09-04 amendment), its sums done in SQL (`sum(net_amount) group by till_item_id`) and never over lines in Python. `db.py` reads, each `tenant_id` keyword-only: `list_sales_days(*, tenant_id, from, to)`, `list_period_invoices(*, tenant_id, from, to)` selecting confirmed, awaiting and held invoices by `purchased_on` (the same `coalesce` as `db.py:798`) with `provenance`, `currency`, `total`, `tax`, supplier and number, and `list_period_sales_lines(*, tenant_id, from, to)` joined to `till_items`; the ratio route reuses `menu._menu_context` and `plates.plate` for coverage so a plate's quality is computed by exactly one function. Routes `GET /api/sales/branches?from&to` and `GET /api/sales/coverage?from&to`; `from`/`to` default to the 28 days ending on the tenant's newest sales business date, 7 as the option (C11.6 and the §3.1 `period` shape; this row said seven days until 2026-09-04, a leftover from before outside voice 15 was folded - so the default is never empty when any sales exist, and the freshness sentence says how old that is), 422 on a reversed or over-long range (cap 92 days). Ranked by `ratio_pct` descending with the unrated rows last, ties by branch name. Serialization in `sales.py` through `api._dec` | M | 80 | `tests/test_ratio.py`, pure: a full week with confirmed purchases reads reliable with limitations and the arithmetic to the tenth; two missing days read incomplete with the sentence; an awaiting invoice reads estimated and is not counted, and an undated one is placed by its arrival day with "undated" in the sentence; a period with negative net sales answers no ratio and reads incomplete; coverage ignores refund lines and stays within 0-100%; a `needs_review` and a dismissed invoice are not counted; a USD invoice is excluded and the row reads estimated naming it; a total with origin `reconstructed` reads estimated; sales with no purchases reads incomplete with no ratio; sales with only an excluded USD purchase reads incomplete and names the exclusion; purchases with no sales reads incomplete with the purchases shown; neither reads unavailable and still carries the branch's last sales day; a confirmed invoice with no branch appears in the unassigned group and in no row; the chain total equals the sum of the rows plus the group; a lagging branch's window ends on its own newest day and its purchases are counted to that day only; each row counts its deliveries; three invoices confirmed today with printed dates last month land on last month's days, not today; precedence unavailable over incomplete over estimated; the ranking puts the highest ratio first and unrated rows last. `tests/test_sales_api.py` against Postgres: three branches, one with purchases, answer the right rows; each day's invoice list carries ids that resolve on `GET /api/invoices/{id}`; coverage on the staged five-item menu reports the costed share to the tenth and the incomplete Paratha's value in the right bucket; the default period ends on the newest sales day; tenant B sees nothing |
| 82 | **The till-name mapping door - propose, one keystroke, reverse gear.** `matching.propose_menu_items(menu_items, till_name)` beside `propose_ingredients`, the same `_similarity` over `normalize()` but **never over `strip_packs()`** - pack-blindness is right for supplier packs and wrong for a menu, where "Karak Tea (Flask 1 L)" and "(Flask 2 L)" are two items and score 1.00 stripped (outside voice 1, measured) - with its own threshold re-derived on the staged five and the real 45 against till-style spellings, at most three, excluding archived items; proposals are computed on the coverage read for every unmapped, unexcluded till item. Routes: `POST /api/till-items/{id}/menu-item` `{menu_item_id}` (approve or remap, clearing `excluded_at`), `DELETE .../menu-item` (unmap, 409 when nothing is mapped), `POST .../exclude` (not a menu item, 409 when mapped); each one audit row inside its own transaction (`till_item.mapped` with `previous_menu_item_id`, `till_item.unmapped`, `till_item.excluded`); a foreign till item is 404, a foreign menu item is 404 from the API and refused by Postgres; an archived menu item is 409 with a sentence | S/M | 80 | `tests/test_till_items.py`: an exact-name till item is proposed at the top and is **not** mapped until the keystroke; "KARAK FLASK 1L" proposes the 1 L flask above the 2 L one and the two never tie; a size word alone does not clear the threshold; approve writes the row and every line in every day follows on the next coverage read; remap carries the previous id and moves the value between menu items in one read; unmap returns the name to the queue with its value; exclude drops it from the queue and keeps it in net sales; mapping an excluded name un-excludes it; the two 409s; cross-tenant refusals; the queue is ranked by net value in the period, most first |
| 83 | **The sales loader at `/sales/load`: a till's export, mapped once, loaded in a minute.** `apps/web` only, against the mock first. Reuses `csv.ts` unchanged. A new `salesLoad.ts` owns: `headerKey(header)` (normalised names, sorted, joined - the layout's identity); applying a saved layout to a file whose key matches; `csv.ts` hardened in place (an unterminated quote refuses the file; a row whose cell count differs from the header's is blocked with its line number; duplicate column names refuse the header) with the menu loader's own tests re-run as the regression (Codex 12); a **layout-drift stop**: a saved layout applies when every column it maps is present by name (several candidates ask which layout this is; a new till gets a name in the mapping step), extra unmapped columns are noted and ignored, and a missing or renamed mapped column stops the file - the screen names what appeared and what disappeared and offers the mapping step again, and never reads a column by position (PRD §10); the mapping step itself (which column is branch, date, item, code, qty, amount, by header name; a layout name with a default; branch by column with unknown labels taught once into `branch_aliases` through `GET /api/branches` and `POST /api/branches/{id}/aliases`, or one branch picked for the whole file when no column is; the VAT basis question, asked once); date reading for ISO and day-first numeric forms with the layout's `date_order`, a date that reads two ways stopping the row (the `dates.py` rule, not a port of it); a row with an empty date cell (a till's totals footer) skipped and counted ("1 row with no date ignored"), never dated by guess; grouping rows into branch-days, the one-shape-per-file check, `dayKey` mirroring `takings.day_key`, and `planDays` predicting `new | unchanged | replaced | blocked` against `GET /api/sales/days` before commit, a replaced day showing before and after and a shrinking one flagged, an interior gap shown as the zero day it will load. The file-choose and read phase (input, re-pick, `parseCsv`, the file-level sentences) is lifted out of `MenuLoader` into a `useCsvFile` hook both loaders use; the grids stay separate. `SalesLoader.tsx` in `MenuLoader`'s phases: choose file, map (or apply the saved layout with one line saying which and the basis), preview grid of branch-days (branch, date, rows, takings as an exact string sum through `mock/decimal.ts`'s `Dec`, what will change, the fix - **no net figure before commit**, because net is a division the browser must not own; the door's answer restamps each day with its net, outside voice 14), commit one branch-month per request (the door's list body) in file order with the layout saved on the first successful request, rows restamped from the door's answer, a summary line ("21 days loaded, 0 replaced, 0 unchanged"), a primary link to `/sales`, the grid staying; a template CSV in the item-wise shape with a worked day and a closed-day zero row; desktop-only, stated. `api.ts` gains the day, layout and read functions; `mock/sales.ts` reproduces the door's decisions and computes no money beyond `Dec` sums. `/sales` and `/sales/load` join `GATED_PREFIXES`, the gate test's arrays, `AppShell.current`, and a `layout.tsx` | M/L | C11 (shapes in row 80), mock | vitest `salesLoad.test.ts`: the header key is order-insensitive and case-insensitive; a saved layout applies to a matching file and not to a drifted one, and the drift message names the added and missing columns; `25/08/2026`, `2026-08-25` and `25-08-2026` read as one date, `5/7/26` stops the row, `2026-25-08` stops it; a file with no item column is stopped with the sentence (2026-09-04; the summary file it once accepted moved to M11); a footer row with no date is skipped and counted; an extra unmapped column does not stop a saved layout and a renamed mapped one does; a branch alias resolves and an unknown branch name blocks its rows; `planDays` predicts unchanged for the same rows reordered and replaced for a changed amount, shows before and after on a replaced day, and fills an interior gap as a zero day; an unterminated quote and a ragged row are refused with the line named, and the menu loader's tests still pass; the gate tests pass with the two new paths. Real browser at 1280 and 390: a first upload walks the mapping, saves the layout and loads 21 days; the same file again previews 21 unchanged and writes nothing; a file with a renamed column stops with the diff; a corrected file previews 1 replaced and 20 unchanged; no horizontal overflow at 390; the grid stays after commit with the link to `/sales` |
| 84 | **The sales screen at `/sales` - the ranked branch table, and the consultant's queue beside it.** Direction from the design review (§10 report; `plan.md` Approved Mockups). Nav label "Sales", fourth entry, the owner's; the loader linked from this screen's footer and its empty state, never the nav (WP-62's rule). Reader order: a period line (28 days by default, 7 as the option, and "sales to Mon 31 Aug, 3 days ago" as the freshness sentence) and the direction in words ("higher means more of every dirham taken went to suppliers"); the ranked table - Branch, Net sales (rounded AED, §3), Purchases (rounded AED), **Purchases ÷ net sales (cash basis)** (one-decimal %, the column header exactly those words), Status (the label word and its first sentence) - highest ratio first, rows with no ratio last with their sentence in the figure's place, an unranked "No branch" row under them when confirmed papers carry no branch, linking to those invoices, and a chain total row that reconciles the table; each row shows its own window ("25-31 Aug, 7 days") and its delivery count; each row a real button opening its days (date, net sales, purchases) and each day's invoices (supplier, number, the ex-VAT figure exact, a link to `/invoices/{id}` - the photo), with pending and excluded invoices named under the day they are dated; then the coverage panel: "Costed: 78% of sales value, 12 points of it on estimated plates" with the two uncosted buckets, the refunds and the non-menu takings in words beside it, and the queue in `RawMaterials`' row shape (name and code, net value, numbered proposal buttons, "Not a menu item", a "pick from the menu" select of live items, keyboard 1-3 / X / P, one write door, Unmap on every mapped name); an empty state pointing at the loader when no sales exist. Mobile mirrors the table as cards (MenuMargins' `MenuCard` pattern). Money by `roundedAed` in the table and `money` in the drill; never "food cost", never "profit". Mock fixtures hand-written for the three-branch week including one incomplete row and one estimated row | M/L | 81, 82, 83 (85 for the real-data gate, run at 86) | real browser at 1280 and 390 on the mock: three branches ranked, the incomplete branch shows sales and no ratio with its sentence, the estimated row names its pending invoice, a row expands to days and a day to invoices, the invoice link lands on the review screen, the coverage panel's percentage matches the API's and names its estimated points, approving a proposal moves its value into the costed share on reload, Unmap returns it, the chain total equals the rows, the empty state links to the loader, no horizontal overflow at 390 - that is the Wave 3 gate on the mock; the walk against the real API with the seeded week, and a dated invoice's confirm moving the branch's ratio on reload, is row 86's gate |
| 85 | **The demo week, generated from the shipped code, loaded through the loader.** `Docs/demo-invoices/koukh-al-shay/build_sales_week.py` in `plate_costs.py`'s shape (`sys.path` to `apps/api/src`; imports `ratio`, `takings` and `VAT_RATE_BY_CURRENCY`, never re-implementing them): reads the menu's items and selling prices from the loader CSV (`--csv`, defaulting to `plate_costs.DEFAULT_CSV`) or the five staged items (`--practice`), writes an item-wise till export for the three branches - till names printed the way a till prints them (upper case, the item code beside, a few abbreviated enough to need the pick-from-menu path, one "DELIVERY CHARGE" line to exercise "not a menu item"), a fixed seed so the file is reproducible, weekend uplift, Al Qusais the largest, amounts VAT-inclusive as a till prints them - for the seven days ending on **KAS-5's printed date, read from `build_prompts.SUPPLIERS` and never typed** (31/08/2026 today, so the week holds KAS-3, KAS-4 and the on-stage KAS-5; a reprinted prop moves the week with it) and, in `--practice` mode, the seven days ending on the demo tenant's newest staged purchase day **read from the database** (`TEST_DATABASE_URL` or `DATABASE_URL`, the `prove_reprice.py` precedent) - the seed stages its purchases relative to the moment it runs, so a date computed from "today" drifts off them within days (outside voice 12, verified) - and prints the per-branch net sales, purchases and ratio the screen will show. The volume constant is chosen so the demo's ratio sits in a plausible 30-40% band, and the README and the runbook say so in those words: the demo's sales are invented, its purchases are not, and the screen's honesty claim is about the second. Output `Docs/demo-invoices/koukh-al-shay/sales-week.csv` (the real week, committed) and `sales-week-practice.csv` (regenerated before a practice rehearsal). `demo_seed.sql`'s reset deletes the tenant's sales rows (a complete practice reset); `demo_reset_loop.sql` **never touches** the four sales tables and says so in its list (`:29-38`). `DEMO_RUNBOOK.md` gains act three (§G): upload the week at `/sales/load`, the ranked table, the drill to KAS-3's photo, the coverage panel, then the on-stage forward moving Al Qusais's ratio; and a §A precondition (the week loaded, the layout saved) | S/M | 80, 81, 83 (the loader's header shape, pinned in §3.1) | `tests/test_demo_seed.py` gains: the practice week is generated in-process after the seed runs and loads through the door (21 days, `loaded`), a second load is 21 `unchanged`, the ratio for Al Qusais equals the generator's printed figure to the tenth, the two other branches read incomplete with "no confirmed purchases", `demo_seed.sql` clears the week and `demo_reset_loop.sql` spares it; a test loads the committed real-week CSV rows through the door on the fixture tenant (21 days, idempotent, net total equal to the file's own footer line); the generator runs with no database and no key |
| 86 | **Live: the week on the real stage, and the record.** One sitting with the founder, outside demo hours, after rows 80-85 merge: confirm 0019 is live (applied before row 80 merged, §8); deploy web (`vercel --prod`); sign in; upload `sales-week.csv` at `/sales/load` - the first upload walks the mapping and saves the layout; map the till names (one keystroke each, the queue ranked by value); walk act three on the real menu; run `demo_reset_loop.sql` and confirm the week and the layout survive; then `plan.md` boxes, Decision Log, Progress Log, `DEMO_RUNBOOK.md` §E row, README's route list, CLAUDE.md and AGENTS.md (the architecture paragraph gains one sentence on the sales door and the ratio) in the same commit | S | 80-85 | the live screen shows the three branches with Al Qusais rated and the other two incomplete; KAS-3's figure drills to its photo on the live host; the loop reset leaves the week intact; the two-act script still runs clean once as a smoke |

Deferred with a named trigger, not built (§9): the Z-report photo path, the business-day cutoff, Excel parsing, a bulk "map all exact names", a reject for till-name proposals.

Budget check (§2 rule 9): M/L + M + S/M + M/L + M/L + S/M + S is roughly eight agent-days, inside the plan's two weeks.
If it runs over, the summary-only shape (P1's second half) and the coverage panel's pick-from-menu select can trail; nothing else is cuttable without breaking the done-when.

### 4.1 Design direction for `/sales` and `/sales/load` (from `/plan-design-review`, 2026-09-03)

Wireframes: `~/.gstack/projects/Ameen-Mammootty-faida/designs/sales-branches-20260903/wireframes.html` (three variants plus the under-640 cards); the recommended direction is in `proposed.json` beside it, and **the founder picked variant B on 2026-09-04** (`approved.json` beside it, in the menu screen's shape; `proposed.json` stays as the review's record), so row 84 builds from B.
Calibrated against `DESIGN.md` (the brand guidelines, the `globals.css` tokens, and CLAUDE.md's display rules) and the M6 menu screen's approved decisions.

**Reader order (variant B, "Answer first"):**

```
  Sales                                  [Last 28 days | Last 7 days | Aug 2026]
  Sales loaded to Mon 31 Aug, 3 days ago.
  Look at Al Qusais first: AED 40 of every 100 it took went to suppliers this window.   <- 1st: the conclusion, one sentence, not a card
  ┌ Branch ─────── Net sales ── Purchases ── Purchases ÷ net sales (cash basis) ── Status ┐
  │ ▸ Al Qusais      AED 30,120  AED 11,899   39.5%      Reliable with limitations         │  <- 2nd: the evidence, ranked
  │   25-31 Aug, 7 days · 3 deliveries                   Every day loaded, every paper confirmed
  │ ▸ Al Nahda       AED 21,480  -            No confirmed purchases   Incomplete           │
  │ ▸ Rolla          AED 17,960  -            No confirmed purchases   Estimated · 1 awaiting
  │   No branch      -           AED 0        -                        (only when papers have none)
  │   All branches   AED 69,560  AED 11,899   17.1%      Incomplete · 2 of 3 branches have no papers
  └ Purchases are confirmed papers dated in the window, less printed VAT, counted when invoiced.
    Higher means more of every dirham taken went to suppliers. This is not a food cost. ┘
  ▾ a row opens its days: date · net sales · purchases · each paper "AED 5,081.70 = 5,335.79 less VAT 254.09 · See the invoice"
  ┌ mist panel: Costed: 78% of sales value · 12 points on estimated plates · buckets in words ┐   <- 3rd: the consultant's queue
  │ CHKN 65 DRY  code 131 · AED 3,120      [1 Chicken 65 Dry] [P Pick from the menu] [X Not a menu item]
  └ Keys: 1-3 approve, P pick, X not a menu item. Load or update sales from the till's export ┘
```

- **Constraint worship:** three things - the sentence, the table, the drill. No callout cards (the menu screen earns its two by having a loss and a price move to narrate; here the top row is the narrative and the sentence restates it). The coverage panel is a different person's work and sits below in the menu screen's mist-panel shape, never beside the table (variant C rejected for stealing a third of the owner's width).
- **The ratio reads two ways on purpose:** the cell carries the percentage with tabular numerals (the rule the menu's margin column set), the sentence carries "AED 40 of every 100", because an owner says the second out loud and reads the first across rows.
- **Status is a word and a sentence, never a colour alone:** the chip tones are the menu screen's (`mist` for reliable and incomplete, `gold-soft` for estimated), the word is PRD §24's, and the first sentence of the row's notes sits under it.
- **Period picker:** a segmented control - Last 28 days (default), Last 7 days, and each calendar month that has sales - no free date inputs (a custom range is a TODO with the trigger "a pilot asks for a range the picker lacks").

**Interaction states:**

| Feature | Loading | Empty | Error | Success | Partial |
|---|---|---|---|---|---|
| Branch table | the menu screen's `role="status"` "Loading" line, no skeletons | "No sales loaded yet. Upload the till's export and every branch's purchases will be set against what it took." with the primary "Load sales from a CSV" link | the app's error strip with the API's sentence | the sentence, the ranked table, the total | rows labelled incomplete, estimated or unavailable with their sentences; the "No branch" row only when it has papers |
| Row drill | nothing loads (the payload carries the days) | "No papers dated these days" on a day; pending and excluded papers named under their day | - | days and papers with the ex-VAT arithmetic and the link | a day with a pending paper shows it in the estimated tone under the confirmed ones |
| Coverage panel | fetched in the same `Promise.all` as the table | "No item-wise sales in this window" when every day is a summary day | the strip | the costed sentence, the buckets, the queue | the estimated points named in the sentence |
| Queue actions | the pressed button busy, the row inert (`busyId`) | "Every till name is mapped." | "Not done: <sentence>" banner | "Done. CHKN 65 DRY is now Chicken 65 Dry." banner, the row leaves the queue | - |
| Loader | "Reading the file" status | "Choose a CSV" with the template link | one file-level sentence (`csv.ts`'s three, plus the drift stop naming columns) | the grid restamped, "21 days loaded, 0 replaced, 0 unchanged", the link to `/sales` | rows blocked with their fix; shrinking days waiting on their tick |

**Journey (owner, five seconds / five minutes / five months):** lands, reads one sentence naming a branch (visceral: "I know where to look"); scans the table and opens the top row (behavioural: "I can see which papers"); clicks a paper and sees the photo (trust: "this number is real"); five months on the same screen with a month picked and the total row reads as a habit. The consultant's arc is the loader's: upload, watch 21 rows go green, map names with one key each, watch the costed share rise.

**Responsive and accessibility:** the table at 640 px and above with one fixed `colgroup` (30/16/16/18/20) so every row lines up; cards under 640 with the ratio as the large figure and the status sentence beneath (the menu screen's `MenuCard` pattern, both renders in the DOM with `onScreen()` refs); row toggles are real buttons with `aria-expanded`; the queue's keys mirror `RawMaterials` (`1-3`, `P`, `X`) with the hint line visible; every button 44 px tall on touch; contrast per the brand palette (ink on cream, palm on paper); the loader is desktop-only and says so.

**Design decisions taken (recommended; the founder may reverse any):** no callout cards; the sentence uses the "of every 100" lens; highest ratio first with the direction footnote; the "No branch" row is muted and appears only when needed; the total row is bold in the table body's last row; the picker has months but no free range; the coverage panel says "costed" and names its estimated points; the loader's shrinking-day confirmation is a tick per day next to the before-and-after figures.

## 5. Proposals for the founder (each with a recommendation)

**Decided by the founder 2026-09-04:** P1, P2, P3, P4, P5, P7 and P8 as recommended (P1 amended the same afternoon: item-wise only, the summary export to M11); **P6 overridden** - no founder-track F9 is created, and the real till export moves to M11 with the pilot, where the first real upload proves the layout step (`plan.md` Decision Log 2026-09-04 and the M11 checklist).

| # | Proposal | Recommendation and why |
|---|---|---|
| P1 | **The CSV's canonical shape.** The checklist says (branch, date, net sales); "recipe coverage by sales value" needs sales per item. Options: item-wise only (a summary export is refused), or item-wise canonical with the summary shape accepted by the same loader | **Item-wise canonical, summary accepted.** Most tills export an item-wise report and it is the only shape that feeds coverage; the summary shape is the checklist's own words, costs one optional column mapping and one branch in the door, and is what a till that gives only day totals would send. It stores as a `summary` day with net sales and no coverage, so the ratio still works and the coverage figure says plainly which days are outside it. Cut it if the budget bites (§4). **Amended by the founder 2026-09-04, after Wave 1: item-wise only for the MVP; the summary export moves to M11 with the pilot (`plan.md` Decision Log)** |
| P2 | **Which purchase figure.** (a) the invoice's printed total less printed VAT - the whole paper, charges and discounts as billed, two numbers the photo shows; (b) the stock lines ex-VAT after the pro-rata discount - the basis price memory uses, which excludes delivery and other charge lines | **(a), total less VAT.** The ratio asks what the branch paid its suppliers against what it took, and delivery charges are paid. It is two printed figures, so the drill reads "AED 5,081.70 = 5,335.79 less VAT 254.09" beside the photo; (b) would make the sales screen's number disagree with the invoice's own total on the review screen, and the difference (a cool-box fee) is exactly the kind of thing an owner asks about. The materials screen keeps (b) for prices per kilo, where charges have no place; the two figures answer different questions and are labelled as such |
| P3 | **Sales for all three branches, when only Al Qusais has purchases.** The demo phone feeds one branch; the other two would read *incomplete: no confirmed purchases*. Alternative: seed Al Qusais only | **All three.** Two honest incomplete rows are the label doing its job on stage, and they set up the sentence "register the other branches' phones and their papers flow the same way" (PRD §28 step 2). A one-row table is not a ranking |
| P4 | **What gates M8 with no real sales.** The checklist's done-when says "a week of real sales + real invoices for one branch". There is none | **The seeded week, loaded through the loader on the real stage, is the build gate; the "real sales" clause moves to M11's pilot** (the first pilot upload is the proof). Recorded as a Decision Log row so the done-when is not quietly rewritten |
| P6 | **One real till export before the layout step is finalised** (Codex 1: "the contract is designed against synthetic sales generated to fit it"). | **Proceed, and add founder-track F9: ask any target chain for one anonymised till export, any month, before WP-83 merges.** The build does not wait for it - the founder decided that - but the mapping step is the hedge, and one real file would prove the hedge before the layout UI is finished rather than at the first pilot upload. Non-blocking. **Overridden by the founder 2026-09-04:** no F9, and nothing is sought before row 83 merges; the real till export moves to M11 with the pilot. The mapping step and the drift stop stay the hedge, and the pilot's first upload is where they are proven |
| P7 | **Item-wise now, or summary-only M8 with the item spine in M9** (the outside voice's structural challenge: the done-when needs one table, and every other table plus WP-82, the menu-item proposer and the coverage panel exist for one number in a side panel - the consultant's homework list, an item-count version of which already ships on `/menu`; §2 rule 2 argues the item spine belongs with M9's item contribution, the screen that consumes per-item sales) | **Item-wise, sequenced so the ratio ships first.** The checklist names coverage by sales value as M8's own item, the founder's question 1 asked for it, PRD §16 makes it the consultant's priority queue, and M9 is two weeks away and would rebuild the loader's mapping step and `till_items` if they were cut now. But the voice is right about order: Waves 1-2 deliver the summary-capable ratio end to end (rows 80, 81, 83, 84 without the coverage panel), the item spine and the panel land last (row 82 and the panel), so the cut line is clean if the budget bites and the done-when is met before a keystroke of mapping. If the founder prefers the smaller milestone, rows 82 and the panel move to M9 and nothing else changes |
| P5 | **Z-report photos.** The checklist has "Z-report photo via WhatsApp → same extraction pipeline, `z_report` document type, summary-level only" | **Defer to `TODOS.md` with the trigger "a pilot branch whose till cannot export".** With CSV as the source, a half-built photo path would sit unused; the classification, the decline reply and the `extraction_runs.outcome` value already exist, so the door is open when the trigger fires. Never turned into fake receipts stands in the TODO's wording |

## 6. Delegation waves and parallel lanes

| Step | Modules touched | Depends on |
|---|---|---|
| WP-80 tables + door | `supabase/migrations/0019_sales.sql`, `Docs/apply_m8_migrations.sql`, `apps/api/src/faida_api/` (`sales.py` new, `takings.py` new, `db.py` additions, `main.py` one include, `contracts.py` if the audit action names are listed there), `apps/api/tests/` (`test_sales_load.py`, `test_tenancy.py`) | - |
| WP-83 loader (mock) | `apps/web/src/lib/` (`salesLoad.ts`, `api.ts`, `gate.ts`, `types.ts`, `mock/sales.ts`), `apps/web/src/components/SalesLoader.tsx`, `apps/web/src/app/sales/`, `apps/web/public/faida-sales-template.csv`, `apps/web/src/lib/__tests__/` | C11 shapes; the real API only for its browser QA |
| WP-81 ratio reads | `apps/api/src/faida_api/` (`ratio.py` new, `sales.py` routes, `db.py` reads), `apps/api/tests/` (`test_ratio.py`, `test_sales_api.py`, `test_tenancy.py`) | WP-80 |
| WP-82 mapping door | `apps/api/src/faida_api/` (`matching.py` one function, `sales.py` routes, `db.py` three writes), `apps/api/tests/` (`test_till_items.py`, `test_tenancy.py`) | WP-80 |
| WP-84 screen | `apps/web/src/components/SalesTable.tsx` (or the design review's name), `apps/web/src/lib/` (`api.ts`, `types.ts`, `mock/sales.ts`), `apps/web/src/app/sales/` | WP-81, WP-82, WP-83 (mock gate); WP-85 for the real-data gate at WP-86 |
| WP-85 demo week | `Docs/demo-invoices/koukh-al-shay/` (`build_sales_week.py`, two CSVs, README), `supabase/demo_seed.sql`, `supabase/demo_reset_loop.sql`, `Docs/DEMO_RUNBOOK.md`, `apps/api/tests/test_demo_seed.py` | WP-80, WP-81, the §3.1 header shape |
| WP-86 live | `Docs/`, `README.md`, `CLAUDE.md`, `AGENTS.md`, `plan.md`, `TODOS.md` | all |

- **Wave 0 (manager, no code):** pin C11 and the amendments in `plan.md` §7.2; move the rows into §7.3; Decision Log rows from §5 and the reviews; TODOS entries from §9.
- **Wave 1, two lanes:** Lane A = WP-80 (owns 0019, `sales.py`, `takings.py`, the `db.py` additions); Lane B = WP-83 against the mock, `apps/web` only.
  No file overlap.
  **0019 is applied to the live project from `Docs/apply_m8_migrations.sql` before Lane A merges** (§8).
- **Wave 2, two lanes:** Lane C = WP-81 (`ratio.py`, reads); Lane D = WP-82 (`matching.py`, the three writes).
  Conflict flag: both add routes to `sales.py` and methods to `db.py`, new functions only, and both add `MATRIX` entries to `test_tenancy.py`; merge sequentially, C then D, and D rebases once.
- **Wave 2b, one lane, after C merges:** Lane F = WP-85 (the generator and the stage; it needs the door and the ratio, and the loader's header shape from §3.1, not the loader itself).
  It edits `demo_seed.sql` and `test_demo_seed.py`, which no other lane touches.
- **Wave 3, one lane:** Lane E = WP-84 (the screen, after B, C, D), gated on the mock; its real-data gate runs at WP-86 against the week F loaded (outside voice 13 - the draft had E and F side by side with E's acceptance depending on F).
- **Wave 4: WP-86**, one sitting with the founder, live.

## 7. The tests that gate it

- `tests/test_sales_load.py` (WP-80): the door's three outcomes and their audit rows, the VAT arithmetic to the fil, the summary shape and the zero day, the one-shape refusal, the future-date refusal, the 31-day body and the 32-day refusal, the concurrent-post lock, the till-item mint, the layout's tenant-wide visibility, the branches list, the cross-tenant refusals from the API and from Postgres.
- `tests/test_ratio.py` and `tests/test_sales_api.py` (WP-81): every label and its sentence as pure cases, the clipped window, the purchase figure and date rule, the undated pending placement, the exclusions, the non-positive period, the purchases-without-sales row, the "No branch" group, the chain total equal to the rows, the ranking, the 28-day default; then the three-branch e2e through the API with the drill's ids resolving on the invoice route.
- `tests/test_till_items.py` (WP-82): never-automatic on an exact name, approve / remap / unmap / exclude with their audit rows, the value moving between buckets on the next read, the two 409s.
- `tests/test_tenancy.py`: the new router in the rig, four tables in `TENANT_TABLES`, nine `MATRIX` entries; the existing route-coverage test makes a missing entry a CI failure.
- `tests/test_demo_seed.py` (WP-85): the practice week through the door, the ratio to the tenth, the two resets' behaviour, the committed real week loading idempotently.
- `apps/web/src/lib/__tests__/salesLoad.test.ts` (WP-83): the header key, the saved-layout apply and the drift stop, date reading, grouping and the one-shape rule, `planDays`; `gate.test.ts` gains the two paths.
- Real-browser QA with `/browse` at 1280 and 390 for WP-83 and WP-84, on the mock and then against the seeded week.
- **Regressions, mandatory:** the 647 API tests green with zero skips; the eval smoke green because no extraction code changes; `demo_reset_loop.sql`'s existing spare-the-menu test still green with the sales tables added to its never-touch list.
- Banned as before: tests that grep code text, framework tests, coverage targets.

### Failure modes, one per new path

| Path | Realistic failure | Test | Handling | User sees |
|---|---|---|---|---|
| Header read | the till renames or reorders a column | yes (WP-83) | no layout matches; the drift stop | the added and missing columns named; map again, never a shifted column |
| Header read | a spreadsheet uploaded as `.xlsx` | yes (csv.ts, existing) | the binary sniff | "Save As CSV" in one sentence |
| Date read | `5/7/26`, or a month-first export | yes (WP-83) | the row stops; the layout's `date_order` | "this date reads two ways" on the row; the layout asks which order once |
| Branch read | the till's branch name is not a Faida branch | yes (WP-83) | rows blocked until an alias is saved | the branch named on the rows and one alias prompt |
| VAT basis | a layout saved as inclusive on a file that is exclusive | browser QA | shown on every preview | "amounts read as VAT-inclusive; net = ÷ 1.05" on the preview line; the fix is the layout |
| Load | a refresh mid-run | yes (WP-80, unchanged on retry) | the day is unchanged on the second post | the run resumes; nothing double-counted |
| Load | a corrected file for two days | yes (WP-80) | replaced, one audit row per day | "1 replaced, 20 unchanged" |
| Load | a partial day (the till exported half a day) | none possible | the latest file is the truth for that day | the day's net moves; the audit row keeps the previous figure |
| Ratio | an invoice still awaiting confirm | yes (WP-81) | not counted; estimated | "1 invoice awaiting confirm" under the day it is dated |
| Ratio | a USD paper confirmed on the branch | yes (WP-81) | excluded; estimated | "1 invoice in USD not counted" |
| Ratio | a branch with sales and no papers | yes (WP-81) | incomplete; no ratio | net sales shown, "no confirmed purchases 25-31 Aug" in the ratio's place |
| Ratio | the newest sales day is two weeks old | yes (WP-81) | the default period still ends there | "sales to Mon 18 Aug, 16 days ago" on the period line |
| Mapping | two till names for one menu item (a rename) | yes (WP-82) | both map; both follow | the value sums on the menu item; the old name stays mapped |
| Mapping | a fee line sits in the queue | yes (WP-82) | exclude | "Not a menu item"; net sales unchanged |
| Ratio | a confirmed paper with no branch | yes (WP-81) | the unassigned group | a "No branch" row with the figure and the papers |
| Header read | a totals footer with no date | yes (WP-83) | skipped and counted | "1 row with no date ignored" |
| Date read | day and month swapped into the future | yes (WP-80) | 422 with a sentence | the row named; the layout's date order is the fix |
| Load | a year of history at onboarding | yes (WP-80, the 31-day body) | one request per branch-month | minutes, not an hour |
| Load | two tabs posting the same day | yes (WP-80) | the row lock; the second is unchanged | nothing double-counted |
| Ratio | a branch closed on Friday | yes (WP-80, takings 0; WP-83 interior gap) | a loaded zero day | no "missing day" sentence |
| Load | a half-day export re-uploaded over a full day | yes (WP-83 preview) | before and after shown, shrink flagged | "25 Aug: AED 4,310 to AED 1,120" before pressing anything |
| Ratio | a pending paper with no date | yes (WP-81) | placed by arrival day | "1 undated invoice awaiting confirm" |
| Ratio | a refund-heavy period, net sales below zero | yes (WP-81) | no ratio; incomplete | "net sales are not positive this period" |
| Header read | an unterminated quote swallows the file | yes (WP-83) | refused | one sentence naming the line |
| Load | file bytes lost after the numbers landed | none possible | the stored file under its hash | the source is one click away for ever |
| Tenancy | a new route forgets the context | matrix | CI fails | nothing shipped |
| Live | 0019 not yet applied when row 80 merges | the paste order | the new routes 500; ingest untouched | nothing, because no screen calls them yet; the order is still written down |

## 8. Migration and cutover order

1. Row 80's branch carries `supabase/migrations/0019_sales.sql` and `Docs/apply_m8_migrations.sql` (pre-flight `needs_0019`, the 0017 shape).
2. **Apply 0019 to the live project before row 80 merges**, a pg_dump backup first.
   Nothing on master reads the new tables until row 80, and row 80's routes have no screen until row 84, so either order is safe today; the written order stays migration-first because it is strictly the safe direction (Decision Log 2026-09-01) and the rule should not have exceptions that need remembering.
3. Merge row 80; Railway deploys; `/health` ok; the new routes answer 401 to no token and an empty `{"days": []}` to a real one.
4. Rows 81 and 82 merge in Wave 2; rows 83, 84 and 85 in Wave 3; web deploys after row 84 merges (`vercel --prod --yes`, manual).
5. Row 86: the founder's sitting, above.

Rollback: Railway redeploys the previous build and Vercel promotes the previous deployment, both one click, both independent.
0019 adds tables and nothing else, so old code against the new schema is unaffected in both directions.

## 9. NOT in scope, and what already exists

**NOT in scope** (each with its trigger; the first eight go into `TODOS.md`):

- **Z-report photos through WhatsApp** (P5): trigger: a pilot branch whose till cannot export. The classification, `REPLY_Z_REPORT` and the `extraction_runs.outcome` value exist; what is missing is an extraction schema for a summary, the `summary` day write through the same door, and the rule that a summary is never turned into fake receipts.
- **The business-day cutoff and timezone arithmetic** (PRD §14): trigger: the first transaction-level source (a POS API). A daily export already carries its business date.
- **Excel parsing**: trigger: a till that exports only `.xlsx`. The loader tells such a file to Save As CSV today.
- **A bulk "map every exact name"**: trigger: a chain with more than a hundred till names. Until then one keystroke per name is M5's rule and two minutes of work.
- **Reject-a-proposal for till names**: trigger: a consultant asks. Approve, pick-from-menu and exclude cover the queue; a wrong top proposal is one keystroke further down.
- **A branch correction door on an invoice** (set or change `branch_id` from the review screen, one audit row): trigger: the first confirmed paper with no branch on a pilot. Until then the "No branch" row names them and the upload form's branch picker (fed by `GET /api/branches` from WP-80, no longer derived from the invoice list) is the prevention.
- **Branch calendars** (closure days, so a missing day is not always a gap): trigger: a pilot branch that closes a day a week. Until then a closed day is a loaded zero, and a file's interior gaps load as zero days.
- **A second sales stream per branch-day** (a second till, a delivery aggregator's report; the day identity gains the stream): trigger: a branch with two sales sources. The day row already carries its layout, so the backfill is one update.
- Item contribution, branch contribution, signals, the calculation-run subsystem and versioned results (M9, PRD §23); the daily brief (M10); the POS API connector and multi-brand (deferred beyond MVP, `plan.md` §8).
- A sales `issues` table: the labels are derived from the data, C5's "derived until real usage demands more" and WP-55's precedent.
- Editing a day on the screen: the CSV is the single source and the fix loop is fix-in-spreadsheet, re-upload (WP-64's rule).
- A job for the upload: the door is synchronous like the menu loader's; a 21-day file is 21 requests of a few rows each.
- Multi-currency sales, per-line VAT rates (the existing TODO), a branch role on the screen (WP-78 stands).
- Any change to extraction, matching's snap rules, costing or plates.

**What already exists and is reused, not rebuilt:** `csv.ts` unchanged; `MenuLoader`'s phases, grid, restamping and fix loop; D8's semantic-equality shape (`recipes.py`) as the model for `takings.day_key`; the WP-52 propose-then-approve door and `RawMaterials`' row and keyboard shape; `matching.py`'s scorer and threshold; `VAT_RATE_BY_CURRENCY` with `db.tenant_currency` and `plates.net_of_vat`; the `purchased_on` rule; `_insert_audit_event`; the composite tenancy FK pattern; `menu._menu_context` and `plates.plate` for coverage; `require_context`, `Context` and the tenancy matrix; the mock layer and `Dec`; `roundedAed`, `money`, `formatDate`; the invoice review screen as the drill's landing; `plate_costs.py` as the generator's shape; `demo_reset_loop.sql`'s scoping discipline; `db.get_branch` for the branch check.

## 10. Implementation Tasks

Synthesized from this decomposition and its reviews. Each task derives from a specific row above. Run with Claude Code; checkbox as you ship.

- [ ] **T1 (P1, human: ~1.5 days / CC: ~3h)** - `supabase/migrations` + `apps/api` - WP-80: 0019 with the five tables, the paste file, `takings.py`, `sales.py`, the batch `db.load_sales_day`, the file store under a server-computed hash, the layout upsert by name, the branches and aliases routes, the days read, the rig and `TENANT_TABLES`
  - Surfaced by: Architecture 1, 7, 9, 14; Codex 4, 6, 7, 10; outside voice 5
  - Files: `supabase/migrations/0019_sales.sql`, `Docs/apply_m8_migrations.sql`, `apps/api/src/faida_api/{sales,takings,db,main}.py`, `apps/api/tests/{test_sales_load,test_tenancy}.py`
  - Verify: `pytest -q`; the matrix green; 647 existing green
- [ ] **T2 (P1, human: ~1 day / CC: ~2h)** - `apps/web` - WP-83: `salesLoad.ts`, `SalesLoader.tsx`, the layout step (by header name, tenant aliases) and the drift stop, `csv.ts` hardened, the `useCsvFile` hook, no net in the preview, the mock, the template, the gate
  - Surfaced by: Architecture 2, 8; Code quality 10; Codex 12; outside voice 9, 10, 14
  - Files: `apps/web/src/lib/{salesLoad,api,gate,types}.ts`, `apps/web/src/lib/mock/sales.ts`, `apps/web/src/components/SalesLoader.tsx`, `apps/web/src/app/sales/`, `apps/web/public/faida-sales-template.csv`, `apps/web/src/lib/__tests__/`
  - Verify: `npm test`, `tsc`, lint, build; `/browse` at 1280 and 390
- [ ] **T3 (P1, human: ~1 day / CC: ~2h)** - `apps/api` - WP-81: `ratio.py` with the C9 labels, the clipped window, the unassigned group and the chain total, undated pending placement, the non-positive rule, coverage in SQL, the 28-day default
  - Surfaced by: Architecture 3, 4; Performance 15; Codex 9, 11; outside voice 4, 7, 8, 11, 15
  - Files: `apps/api/src/faida_api/{ratio,sales,db}.py`, `apps/api/tests/{test_ratio,test_sales_api,test_tenancy}.py`
  - Verify: the pure cases and the three-branch e2e
- [ ] **T4 (P1, human: ~4h / CC: ~1h)** - `apps/api` - WP-82: `propose_menu_items` over `normalize()` without `strip_packs()`, its own threshold, the three doors, their audit rows
  - Surfaced by: outside voice 1
  - Files: `apps/api/src/faida_api/{matching,sales,db}.py`, `apps/api/tests/{test_till_items,test_tenancy}.py`
  - Verify: never-automatic; the value moves on the next read
- [ ] **T5 (P1, human: ~1.5 days / CC: ~3h)** - `apps/web` - WP-84: the screen to the design review's direction, the direction sentence, the total and "No branch" rows, the drill, the coverage panel ("costed", estimated points) and queue, the cards at 390
  - Surfaced by: Architecture 5; outside voice 4, 7, 15
  - Files: `apps/web/src/components/SalesTable.tsx`, `apps/web/src/lib/{api,types}.ts`, `apps/web/src/lib/mock/sales.ts`, `apps/web/src/app/sales/page.tsx`
  - Verify: `/browse` on the mock, then against the seeded week
- [ ] **T6 (P1, human: ~4h / CC: ~1h)** - `Docs` + `supabase` - WP-85: the generator (end date from the props and, in practice mode, from the database), the two CSVs, the candour line, the reset changes, act three
  - Surfaced by: Architecture 6; outside voice 12, 13
  - Files: `Docs/demo-invoices/koukh-al-shay/{build_sales_week.py,sales-week.csv,sales-week-practice.csv,README.md}`, `supabase/{demo_seed,demo_reset_loop}.sql`, `Docs/DEMO_RUNBOOK.md`, `apps/api/tests/test_demo_seed.py`
  - Verify: the generator runs with no database; the seed tests
- [ ] **T7 (P1, human: ~2h / CC: ~30 min)** - live - WP-86: 0019 confirmed live, web deployed, the week loaded and mapped, act three walked, the records
  - Files: `Docs/DEMO_RUNBOOK.md`, `README.md`, `CLAUDE.md`, `AGENTS.md`, `plan.md`, `TODOS.md`
  - Verify: the live walk; the loop reset spares the week

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | - | - |
| Codex Review | `/codex review` | Independent 2nd opinion | 1 | issues_found (folded) | 12 findings, 9 accepted, 1 deferred to TODOS, 2 kept |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR (PLAN), approved by the founder 2026-09-04 | 15 review findings, 27 outside-voice findings, 0 critical gaps open |
| Design Review | `/plan-design-review` | UI/UX gaps | 1 | APPROVED (FULL), the founder's pick 2026-09-04 | score 4/10 to 9/10; 8 decisions taken as recommended; variant B picked, wireframes written, `approved.json` beside them |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | - | - |

Scope: M8 sales ingestion and the first ratio (WP-80 to WP-86), reviewed 2026-09-03 at commit `35697f5`, before any feature code.
Mode: FULL_REVIEW - the Step 0 complexity check triggered (five tables, three new API modules, about twenty files) and was answered rather than reduced: each table is the smallest honest home for one concept (a day, a line, a till name, a layout, a branch alias), the cut line is named (the summary shape and the pick-from-menu select can trail; rows 82 and the coverage panel can move to M9 as a whole - §5 P7), and the ratio ships before the item spine so the done-when is met before any mapping exists.
This session ran unattended: every question the review would have put to the founder was answered with the recommended option and is recorded below as recommended; §5 is the founder's decision list.

**Step 0.** Existing code reused rather than rebuilt: `csv.ts`, the loader's phases, D8's equality rule, the WP-52 door and `RawMaterials`' row, the matcher's scorer, the VAT table, the `purchased_on` rule, the audit spine, the composite FK pattern, `_menu_context` and `plates.plate`, the tenancy matrix, the mock layer. No new infrastructure, no new dependency, no job kind: Layer 1 throughout. `TODOS.md` cross-reference: the invoice-level VAT entry does not touch the ratio (the printed tax is the printed tax); the catalog-pack entry is moot for a figure built from invoice totals.

**Review findings (own), each decided with the recommended option:**
1. [P1] (9/10) No branches endpoint; branch optional on upload (`api.py:913`) and manual entry (`api.py:729`, `:808-812`); `UploadInvoice.tsx:51-52` derives branch options from the invoice list. Decided: `GET /api/branches` in row 80; a "No branch" group and row; a branch-correction door in TODOS.
2. [P2] (8/10) A layout keyed on the whole header stops on any extra column. Decided: apply when every mapped column is present by name; extras noted; a missing mapped column stops.
3. [P2] (8/10) A closed day and an un-uploaded day were the same gap. Decided: a takings-0 day; interior gaps in a file's range load as zero days; branch calendars in TODOS.
4. [P2] (8/10) Sales with only excluded purchases fell through the label rules. Decided: incomplete keys on *counted* purchases; the exclusion sentence rides along; unavailable rows keep the branch's last sales day.
5. [P2] (9/10) The label lacked "(cash basis)". Decided: the M8 checklist's and the July design doc's exact words on every surface.
6. [P2] (7/10) The generator typed 31/08/2026. Decided: the end date is read from `build_prompts.SUPPLIERS`.
7. [P3] (8/10) `sales_lines` needed `on delete cascade` for the resets; `qty` must be optional. Decided: both.
8. [P2] (8/10) Till footers ("TOTAL,,,,30120.00") would block or mis-date. Decided: a row with no date is skipped and counted, never dated.
9. [P2] (8/10) A swapped day and month lands in the future silently. Decided: the door refuses a business date after tomorrow or before 2020.
10. [P3] (7/10) Two loaders would duplicate the file-choose and read phase. Decided: a `useCsvFile` hook shared by both; grids separate.
11. [P3] (8/10) `plates.net_of_vat` quantizes to a tenth of a fil. Decided: `takings.net_amount` is its own three lines at a fil, the day equal to the sum of its stored lines.
12. [P3] (7/10) `source_filename` is client-asserted. Decided: a label, never identity; the hash is server-computed (Codex 4).
13. Test gaps named into acceptance: footer row, future date, zero day, "No branch" row, per-day batch outcomes, two tabs on one day, a layout visible tenant-wide, the `expect_b` rows, the 92-day cap, the loader's 401 mid-run (existing `api.ts` test).
14. [P2] (8/10) One request per branch-day is 21 for the week and about 1,100 for a year of history at 1-2 s each on the live host. Decided: a list body of up to 31 branch-days, one transaction and one outcome per day.
15. [P3] (8/10) Coverage summed over lines in Python would not scale. Decided: SQL aggregation; the ratio read is four fixed queries.

**Test coverage (planned, every gap named into a row's acceptance):**

```
CODE PATHS                                                   USER FLOWS
[+] takings.py / db.load_sales_day (WP-80)                   [+] /sales/load first upload
  ├── loaded / unchanged / replaced + audit    test_sales_load  ├── map columns, name the till, basis   browser QA
  ├── VAT inclusive/exclusive to the fil       test_sales_load  ├── unknown branch label -> alias        browser QA + vitest
  ├── summary day, zero day, one-shape refusal test_sales_load  ├── drift stop (renamed column)          vitest + browser
  ├── future date, >31 days, ragged body       test_sales_load  ├── footer row skipped                   vitest
  ├── row lock under two posters               test_sales_load  ├── shrinking day confirm per day        browser QA
  ├── till item by code / by name, rename      test_sales_load  └── refresh mid-run resumes              api.test.ts (401) + unchanged
  └── file stored once under its hash          test_sales_load [+] /sales
[+] ratio.py (WP-81)                                             ├── ranked, direction sentence, total   browser QA
  ├── every label + sentence, precedence       test_ratio       ├── incomplete / estimated / No branch  browser QA
  ├── clipped window, deliveries count         test_ratio       ├── drill day -> invoice -> photo        browser QA [->E2E]
  ├── total - tax, printed date, exclusions    test_ratio       ├── coverage %, approve 1-3, X, Unmap    browser QA
  ├── undated pending by arrival               test_ratio       └── on-stage confirm moves the ratio     WP-86 [->E2E]
  ├── non-positive net sales                   test_ratio     [+] Tenancy
  ├── unassigned + chain total reconciles      test_sales_api   └── 9 routes x {A, B, none}             test_tenancy matrix
  └── three-branch e2e, drill ids resolve      test_sales_api [+] Demo stage
[+] matching.propose_menu_items (WP-82)                          ├── practice week generated after seed   test_demo_seed
  ├── not pack-blind; 1 L vs 2 L never tie     test_till_items  ├── loop reset spares the week          test_demo_seed
  └── approve / remap / unmap / exclude audit  test_till_items  └── committed real week loads idempotent test_demo_seed
[+] salesLoad.ts (WP-83): header key, layout apply, drift, dates, grouping, planDays   salesLoad.test.ts
[+] csv.ts hardening: unterminated quote, ragged row, duplicate header               csv/menuLoad tests (regression)
COVERAGE: every planned path has a named test; 2 flows marked [->E2E] run in the real browser against the seeded week.
```

**Failure modes:** the table in §7; 0 critical gaps (every new path has a test, handling, and a sentence the user sees).

**Parallelization:** six lanes; Wave 1 runs A (row 80) and B (row 83) in parallel; Wave 2 runs C (81) and D (82) in parallel with a sequential merge on `sales.py` and `db.py`; Wave 2b F (85) after C; Wave 3 E (84); Wave 4 the live sitting.

**Lake score:** 15/15 review decisions took the complete option.

**CODEX:** ran at medium reasoning against the file path (the inline-prompt form times out on this repo) and answered in under four minutes with twelve findings. Accepted and folded: the raw file stored under a server-computed hash (4), layouts identified by name with the header as evidence (6), till items identified by code when present (7), interior gaps as zero days (8), undated pending papers placed by arrival (9), a fil-precise sales quantizer with the day equal to its lines (10), no ratio on non-positive net sales and a positive-only coverage denominator (11), `csv.ts` hardened (12), a real till export as founder-track F9 (1, as §5 P6 - overridden by the founder 2026-09-04: no F9, the file moves to M11 with the pilot). Kept with reasons: file atomicity (3) - one transaction per day with idempotent retry is the completion, and the label tells the truth in between; partial-day overwrite (2) - taken as a per-day confirmation in the preview, not a server-side rejection. Deferred to TODOS with its trigger: a second sales stream per branch-day (5).

**CROSS-MODEL:** the Claude subagent filed fifteen findings and one structural challenge. Folded: the pack-blind scorer collapsing size variants (1, measured at 1.00), the response shapes pinned as literal JSON in §3.1 (2), purchases hidden behind a missing upload and the chain total row (4), the printed name and code stored on the line (5), a per-day confirm on a shrinking replace (6, agreeing with Codex 2), "costed" never "complete" with the estimated points named (7), the coverage denominator excluding non-menu value (8), columns mapped by header name (9), branch aliases as a tenant table (10), the row window clipped to the branch's own loaded range (11), the practice week's end date read from the database (12, verified against `demo_seed.sql:353-376`), row 85 moved to Wave 2b and row 84's real-data gate moved to row 86 (13), no net figure computed in the browser (14), a 28-day default with the direction stated in words and the delivery count on every row (15). Kept: withholding the ratio below a delivery-count threshold (15) - the count is shown instead. Both voices agree on non-positive net sales (Codex 11, Claude 3) and on the shrinking-day guard (Codex 2, Claude 6). **The structural challenge - ship M8 summary-only and move the item spine to M9 - is put to the founder as §5 P7 with the recommendation to keep item-wise but sequence the ratio first.** Three factual corrections applied to §2 (the seed leaves every phone null; the grid stays because it is keyed on items; the never-touch list is `:30-38`).

**DESIGN:** `/plan-design-review` ran after the eng review, unattended: the plan rated 4/10 on design completeness before §4.1 (the row named columns and an order but no states, no journey, no responsive rule, no picker) and 9/10 after it; the remaining point is the founder's pick on the board. Seven passes: information architecture (the sentence-table-drill order, constraint worship, variant C rejected), interaction states (the table above), journey (the three horizons), AI-slop risk (no card grids, no dashboard tiles, one table and one panel in the app's existing vocabulary), design-system alignment (`DESIGN.md` found; tokens, chips, colgroup and `MenuCard` reused), responsive and accessibility (the specs above), unresolved decisions (eight, taken as recommended and listed). Wireframes at `~/.gstack/projects/Ameen-Mammootty-faida/designs/sales-branches-20260903/wireframes.html`; the founder picks a variant on it and the pick becomes `approved.json` and the Approved Mockups row in `plan.md`.

**VERDICT:** ENG CLEARED on the engineering questions and DESIGN APPROVED - the founder answered §5 and picked variant B on 2026-09-04, so the rows in `plan.md` §7.3 are approved to build. The CEO review is not required (the milestone is the plan's own checklist item with the founder's quote).

**DECISIONS (the founder, 2026-09-04):**
- P1 the CSV's canonical shape - item-wise canonical, summary accepted (as recommended)
- P2 the purchase figure - total less printed VAT (as recommended)
- P3 sales for all three branches in the demo week (as recommended)
- P4 the seeded week as M8's gate, "real sales" moving to M11 (as recommended)
- P5 Z-report photos deferred to TODOS with the trigger (as recommended)
- P6 **overridden**: no founder-track F9 and nothing sought before row 83 merges; the real till export moves to M11 with the pilot
- P7 item-wise now with the ratio sequenced first, not summary-only (as recommended)
- P8 the `/sales` wireframe variant B "Answer first" (as recommended; `approved.json` written, A and C not picked)

**UNRESOLVED DECISIONS:** none.
