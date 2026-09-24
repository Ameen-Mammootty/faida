# Architecture specs - the first four candidates of the 2026-09-24 review (drafted 2026-09-24)

Status: **drafted 2026-09-24 against master `e90a68a`; the founder accepted every recommendation the same day (D1 to D10 as written in §0.2) and asked for Wave 0, the four bug fixes, to start; nothing else built.**
Each spec was drafted by a read-only design pass over the code, and the load-bearing claims (the four bugs, the two price derivations, the plate-money split) were re-read by hand before this file was written.
The bugs are confirmed by reading the code, not yet reproduced; each spec's first step is the failing test that reproduces it.
The review that ranked these is `$TMPDIR/architecture-review-20260924-122317.html` (temp, may be gone); the earlier review's candidates 1 to 3 (filing, the quality word, the period read) are merged and are not re-argued here.

Vocabulary is the `codebase-design` skill's: module, interface, implementation, depth, seam, adapter, leverage, locality.
Domain words are `CONTEXT.md`'s.
Line numbers are master `e90a68a` and will drift.

## 0. What this means, in one screen

Four changes, three of them carrying a real bug an owner or a phone can see today.

| # | Change | What an owner sees today | Size | Behaviour change |
|---|---|---|---|---|
| 1 | One answer for what a recipe line draws and costs | A price rise on a dish with a usable share reads about 15% too small, on the Menu card, the dashboard's supplier prices, the price-spike signal and the morning brief | Small, one module | Yes, the fix, only for dishes with a usable share |
| 2 | Each refusal inside the transaction that writes | A WhatsApp "OK" can be told "recorded" when nothing was; a millilitre pack can be filed under a gram material; an archived dish can still be edited | Big, door by door | Three bug fixes first, then none |
| 3 | A material's price in force as one value | The Menu screen says "from 6 Jul" and drops the reason; Materials says "on 6 Jul" and gives it; "per kg" and "/kg" on different screens | Medium, API then web | Wording made one |
| 4 | The house wording as public modules | One plate cost can read AED 6.41 on `/menu` and AED 6.42 in a dashboard note | Medium, mechanical | Only the plate-money rule, by decision |

## 0.1 The order, and why

The four drafts disagreed on order: 4 said "me first", 3 said "4, then 3, then 1", and 1 said "any time".
The order below resolves that. It puts the bugs first, the mechanical refactor second, and the one needing a founder sitting last.

1. **Wave 0: the bugs, as ordinary fixes, each test-first.**
   Candidate 1 whole (it is small, and its interface takes no price, so it cannot collide with 3), and candidate 2's Part A (bugs A, B, C).
   Four independent lanes; none waits on a decision below except §2 decision 1 (the wording of a lost-race reply).
2. **Wave 1: candidate 4** (words, wire, typed).
   No behaviour change except the plate-money decision, which is its last step and can be held.
3. **Wave 2: candidate 3** (the price in force), built on 4's public words.
   API first and deployed, web second.
4. **Wave 3: candidate 2's Part B** (the doors), after a planning sitting with the founder, confirm door first.

Shared seams, so the lanes do not collide:
- `plates.line_draw` (1) takes a quantity and a unit, never a price; `plates.cost_component` keeps its signature through 1, and 3 later swaps its price argument from `Priced` to `PriceInForce`.
- `words` (4) is the only place English for money, dates, units and counts is written; 3 calls `words.per_unit`, `words.long_date`, `words.price` and never defines its own.
- 4 leaves `_apply_correction` for 2's correction door and `_material_price` for 3's price in force; it does not move them.

## 0.2 The decisions, in one table

| # | Decision | Recommendation |
|---|---|---|
| D1 | Accept that price-move figures for dishes with a usable share rise to the correct amount (spec 1) | Yes - a fix; the old "before" margin disagreed with the Menu screen |
| D2 | Tell the pilot? (spec 1) | Only if a live recipe has a usable share (`select count(*) from recipe_components where usable_share is not null`); then one line in the next conversation, not a message |
| D3 | What the phone says when its "OK" lost a race with the screen (spec 2) | The fresh ack if it did get confirmed, the cash-hold reply if it is now held, otherwise "This one was changed on the review screen, so this OK didn't record it." |
| D4 | M13's `approve_statement` in scope of the doors? (spec 2) | No - convert it after M13 merges, as door 5 |
| D5 | Delete the two dead database methods (spec 2) | Yes, in the cleanup step; keep the brief-recipient methods |
| D6 | Keep the SQL guard on confirm as defence in depth (spec 2) | Yes; a disagreement between it and the Python rule is a 500, not a 409 |
| D7 | "per kg" everywhere, or "/kg" in tight cells? (spec 3) | "per kg" everywhere |
| D8 | The Menu screen's estimated note always carries its reason (spec 3) | Yes |
| D9 | Plate money: cut to the fils or rounded half up? (spec 4) | Cut, everywhere - it is what `/menu` shows and what is documented |
| D10 | The dashboard's dish row prints "AED 6.410 a plate" raw (spec 4) | Send it through the same cut, as a small web follow-up |

Two findings are recorded as follow-ups, not decided here: `/menu` and `/materials` let an invoice printed with a future date win the price, which the period figures do not (spec 3 D-follow-up); `/sales/coverage` costs the menu at today's prices instead of the period's (review candidate 5).

---

## 1. One answer for what a recipe line draws and costs

### 1.1 What it means

A recipe line such as "500 g chicken, 85% usable" has to become "this much left the shelf, at this price" before anything else can happen.
Four places in the code each work that out themselves, and the price-move card forgets the "85% usable" part.
After this change one function answers the question, every screen asks it, and the price-move numbers for trimmed dishes become correct.

### 1.2 Current state

| Site | Share applied? | Dimension check? | Yield | Rounding |
|---|---|---|---|---|
| `plates.py:128-174` `cost_component` | yes, via `bought_base_qty` (`:173`) | yes (`:162`) | no, `plate()` divides later (`:279`) | none; `plate()` rounds once to 0.001 |
| `period_read.py:286-290` `_menu_items` | yes, via `bought_base_qty` | yes, against `cost_base_unit` | no, `contribution._components` divides (`contribution.py:451`) | none; contribution rounds once per component |
| `usage.py:810-824` `_used_by_material` | yes, inline (`:820-822`) | yes | yes (`:824`) | once per dish to 0.001 base units (`:850`) |
| `menu.py:969-982` in `price_moves` | **no** | **no** | inside `margin_impact` | `margin_impact` to 0.001 half up (`plates.py:224`) |

`signals.py` has no copy of its own; it multiplies the wrong impact from `menu.price_moves` by the portions sold (`signals.py:409`).
`usage.py:733-765` builds a fake `cost_component` call at a price of 1 only to borrow its "does not convert" sentence, another sign the interface is too shallow.
The web mocks do not copy the arithmetic, and no mocked move touches a dish with a share.

### 1.3 The bug

`price_moves` sums `to_base_qty` over the dish's components and hands the sum to `margin_impact` without dividing by `usable_share`, although the component rows carry it (`db.py:1645`).
A dish with a share of 0.8 shows 80% of its true impact, and `margin_before = plate.margin + impact` (`menu.py:985`) is wrong with it.

Reproduction, in `apps/api/tests/test_price_moves.py` with the `test_plates.py` builders it already imports:
1. `scenario = await _karak(db, api)`.
2. `special = await _menu_item(api, "Karak Special", "10.00")` with tea 4 g, milk 60 ml at `"usable_share": "0.8"`, cup 1 pc.
3. `before = await _detail(api, special)`.
4. Deliver milk at 9.00 per 1 L on 2026-08-15, as `test_milk_up_names_each_plate_and_its_exact_aed_drop` does.
5. `GET /api/price-moves`, take the Karak Special item.

| Field | Expected | Today |
|---|---|---|
| `impact_per_portion` | 0.075 | 0.060 |
| `margin_before` | 8.652, equal to `before["margin"]` | 8.637 |
| `margin_pct_before` | 90.8 | 90.7 |

The pin is `item["margin_before"] == before["margin"]`: the "before" figure is the margin the owner actually saw.
A second test in `test_dashboard.py` sells 100 Karak Special after the move and asserts `money_at_stake` is 7.500, not 6.000.

Wrong today: the Menu screen's price-move card, the dashboard's supplier prices panel (money at stake and row order, `dashboard.py:299`), the price-spike signal's money, rank and sentence (`signals.py:574`), and the brief's three rises (`brief.py:369`).

### 1.4 The deepened module

Two shapes were weighed: one pure function returning a value, or a `RecipeLine` object with `.draw()` and `.cost()`.
The object needs an adapter at every call site (callers hold asyncpg records, `contribution.RecipeComponent` and dicts), so it adds interface for no depth.
Chosen: one pure function in `plates.py`, beside the sentences and the quality rules it already owns.

```python
@dataclass(frozen=True)
class LineDraw:
    bought: Decimal | None   # base units off the shelf, full precision
    missing: str | None      # plain-words reason; exactly one of the two is set
    def cost(self, cost_per_base_unit: Decimal) -> Decimal: ...  # bought x price, unrounded

def line_draw(*, qty: Decimal, unit: str, usable_share: Decimal | None,
              measured_in: str, ingredient_name: str) -> LineDraw
```

Invariants:
- `bought` is `qty` converted to base units, divided by the share only when a share is set, so a recipe from before 0021 is byte for byte unchanged.
- `bought` is never rounded, and the yield is never applied: each caller rounds and divides where it does today, because each of those rules is load-bearing (plate once per plate, impact once per plate and move, usage once per dish, contribution once per component).
- The Decimal operations run in the same order as each current copy.

Error modes:
- A unit that is not a measure, or whose dimension differs from `measured_in`: `missing` is the existing sentence "'{unit}' does not convert to how {name} is measured".
- A missing price is not this function's concern; it stays in `cost_component`.
- `cost()` on a line with a hole raises, so a hole is never multiplied by accident.

`to_base_qty` becomes private and `bought_base_qty` is folded in; `margin_impact` stays public with its parameter renamed `bought_base_qty`.
`usable_words` (`plates.py:213`) stays as it is: it is display arithmetic on the typed quantity, not a draw.

### 1.5 Callers after

- `plates.cost_component`: `line_draw(measured_in=price.base_unit)`, then `draw.missing` or `draw.cost(...)`; signature unchanged.
- `period_read._menu_items`: `draw.cost(...)` when `draw.bought` is set.
- `usage._used_by_material`: `draw.bought / item.yield_portions`, holes from `draw.missing`; `_no_convert_sentence` deleted.
- `menu.price_moves`: sums `draw.bought` with `measured_in=current["base_unit"]`, then `margin_impact` - the fix.

### 1.6 Tests and steps

1. Add `LineDraw` and `line_draw` with pure tests (kg to g, a vessel gives `missing`, a dimension mismatch gives `missing` and never a number); nothing calls it yet.
2. Move `cost_component` onto it; everything stays green.
3. Add the failing price-move test from §1.3, watch it fail on 0.060 and 8.637, move `price_moves` onto `line_draw`, watch it pass. The only step that changes behaviour.
4. Add the dashboard money-at-stake test; it should already pass.
5. Move `period_read._menu_items`.
6. Move `usage._used_by_material`; `test_usage.py`'s exact-equality tests guard the accumulation order, the one place a 0.001 drift could creep in.
7. Make `to_base_qty` private, delete `bought_base_qty`, move their tests behind `line_draw` (`test_plates.py:41, 132, 155`).
8. Regenerate the dashboard mock (`generate.py`) and confirm an empty diff; `plan.md` Progress and Decision Log; one line in `CLAUDE.md`/`AGENTS.md` naming `plates.line_draw`.

Must pass unchanged: `test_plates.py`, `test_price_moves.py`, `test_usage*.py`, `test_period_read.py`, `test_contribution*.py`, `test_signals.py`, `test_dashboard.py`, `test_brief*.py`, `test_menu*.py`, and the query-count tests.
No eval run is needed; nothing near extraction moves.

### 1.7 Out of scope

Money on usage's bought side, `_no_pack_sentence`'s probe of `cost_component`, which pack a line was bought in, where `margin_impact` rounds, and whether `margin_before` should be read from the plate at the previous price (with the fix the two agree).

---

## 2. Put each refusal inside the transaction that writes

### 2.1 What it means

When someone confirms an invoice, maps a pack to a material or edits a dish, the product checks whether the action is allowed and then writes.
Today the check and the write often happen at two different moments, so a change made in between by someone else is missed, and the user can be told something that is no longer true.
The fix is one rule everywhere: read the row, decide, write and record who did it, in one sealed step nobody else can interleave with.
That sealed step is a **door**.
Three real bugs come from the gap today; they are fixed first as ordinary small fixes (Part A), and the pattern follows door by door (Part B).

### 2.2 Evidence (checked)

- `db.py` is 4,100 lines with about 110 methods; 75 `tenant_id = $` clauses and 28 `_insert_audit_event(` calls.
- `live_menu_item_by_name` (`db.py:1568`) and `record_audit_event` (`db.py:3721`) have no callers anywhere; `add/pause/resume_brief_recipient` are called only from `tests/test_brief_job.py`.
- The confirm rule is stated in `db._confirm`'s WHERE clause (`db.py:3494-3496`), the screen route (`api.py:632-688`) and the chat door (`confirm.py:762-786`).
- "Cash is held" is decided in four places: `extraction/pipeline.py:279-310`, `api.py:970-974`, `confirm.py:629-650` and `confirm.py:653-675`.
- Two more findings: `approve_cash_invoice`'s audit detail is built from a pre-read row (`api.py:726-734`), and `_resolve_supplier` (`confirm.py:962`) mints a supplier outside the correction's transaction, so a refused correction leaves the supplier behind.
- Precedent for the refusal shape already exists: `SupplierAliasCollision` is a typed, worded exception every adapter maps.

### 2.3 Part A - three fixes, first

**Bug A - the phone told "recorded" when it was not.**
`confirm.py:776` discards the bool `db.confirm_invoice` returns, and `:786` acks from the row read before the write, so a total corrected in between is quoted stale too.
The harmful interleaving: the screen marks the paper cash between the chat's pending read and its write, and the phone says "Confirmed ... recorded" about a paper held for approval.
Reproduce in `tests/test_api.py` with the `api` fixture and `handle_inbound_text`, as `apply_chat_correction` (`test_api.py:1306`) does: wrap `db.pending_invoices_for_phone` with `monkeypatch` so it awaits the real read and then PATCHes `payment_kind=cash` through the client - a real screen action against real Postgres, not a fake database.
Fix: keep the bool; on False, re-read and choose the reply from the fresh row (D3); on success, ack from the fresh row as well.
Pin the new `REPLY_CONFIRM_REFUSED` in `tests/test_replies.py` beside `REPLY_CORRECTION_REFUSED` (`:808`).

**Bug B - a volume pack mapped onto a weight material.**
Deterministic, not only a race: `db.map_supplier_item` upserts `on conflict (tenant_id, name) do update set name` (`db.py:1335-1339`) and returns the existing material whatever its `base_unit`, while the route checked the request's unit (`api.py:1427-1495`).
Reproduce in `tests/test_raw_materials.py` beside `test_a_millilitre_pack_cannot_be_mapped_onto_a_gram_material` (`:287`): map "Milk Powder 2.5kg" with `{"name": "Milk"}`, then "Evaporated Milk 400ml" with `{"name": "Milk"}`; assert a 422 naming both measures and no audit row.
Fix inside the transaction: lock the pack row, take `previous_ingredient_id` from it (the parameter goes), resolve the name with `on conflict do nothing returning` plus a fallback select, and raise a new `MaterialMeasuredOtherwise` carrying the `MEASURE_WORDS` sentence when the existing material is measured otherwise.

**Bug C - writes to a dish archived a moment ago.**
`menu._live_item` (`menu.py:551-564`) checks before `set_menu_item_price` (`db.py:1823`) and `create_recipe_version` (`db.py:1954`); `sales.py:899-904` checks before `map_till_item` (`db.py:2936`); only `load_menu_recipe` checks under lock (`db.py:2075-2087`).
Reproduce in `tests/test_menu.py` and `tests/test_till_items.py` with the same interleave (the read, then POST `/archive`).
Fix: each of the three writes reads `archived_at` under `select ... for update` and raises `MenuItemArchived`, which the adapters map to the 409 sentences already in use (`menu.py:562`, `sales.py:902`).
The pack-size override (`db.py:1393`) gets the same treatment for its measure check (`api.py:1628-1636`).

### 2.4 Part B - the door

A door is a module whose interface is one async function per human decision.
It reads the row under lock, refuses in the product's words, writes and writes its audit row in one transaction, and returns an outcome.
Adapters - the FastAPI routes, the chat flow, the pipeline - translate input into a door call and the outcome into an HTTP code or a reply.

Two shapes were weighed: a returned outcome, `Done | Refused(kind, words, status)`, or a raised `Refusal`.
Chosen: the returned outcome.
A refusal is an expected result, not an exception; with two adapters speaking in two voices, a `match` with `assert_never` makes a forgotten kind fail at the adapter, where a forgotten `except` would be a 500 on the screen and a silent phone on chat.
`Done` carries the fresh locked row the adapter needs to say anything, so it cannot be dropped the way bug A dropped a bool.
Inside the implementation exceptions still roll back (`SupplierAliasCollision`); the door catches them at its edge.
The shared types (`Done`, `Refused`) live in a small `doors.py`.

Where the transaction lives: `db.py` keeps every line of SQL.
`Database._txn` (`db.py:386`) becomes a public `transaction()`, the confirm-family methods take a `conn=` keyword (the pattern `set_menu_item_price` and `create_recipe_version` already use), and `db.lock_invoice` is `get_invoice`'s select with `for update of i`.
The door opens the transaction, locks, decides in Python, and calls the db writes on that connection.
Tenant scope is the lock read's `where id = $1 and tenant_id = $2`, so a row outside the tenant is `Refused(NOT_FOUND)` and the screen's 404.
The actor stays an input built at the adapter, never from a client header.
`_confirm`'s WHERE guard stays as defence in depth (D6): a constraint, not a SQL function, so `plan.md` §2 allows it.

### 2.5 The first door in full - `invoice_doors.py`

- `confirm(db, id, *, tenant_id, actor, duplicate_hold_ok)` - the screen passes True, chat False.
- `approve_cash(db, id, *, tenant_id, actor, reason)` - the audit detail built from the locked row.
- `dismiss(db, id, *, tenant_id, actor)`.
- `correct(db, id, edits, *, tenant_id, actor, origin, message_id)` - returns the filed result (invoice, checks, alerts, status, booked-under, item names); the chat adapter composes the reply from it instead of `_apply_correction` returning WhatsApp text, and the line-range check, the supplier resolution, the duplicate re-check and the write all run under the lock.

Refusal kinds: `NOT_FOUND`, `CASH_NEEDS_APPROVAL`, `NO_TOTAL`, `NOT_CASH`, `ALREADY_CONFIRMED`, `DISMISSED`, `NOT_EDITABLE`, `LINE_OUT_OF_RANGE`, `SUPPLIER_NOT_FOUND`, `ALIAS_COLLISION`.
The screen adapter maps each to today's code and words, word for word (the constants at `api.py:135-139`), because `apps/web/src/lib/mock/store.ts` mirrors them; its pre-checks and re-reads go (`api.py:643-681`, `505-524`, `_fresh_status` at `788`).
The chat adapter keeps the retry guard and the pending resolution and maps each kind to the existing reply constants.

"Cash is held" folds into one pure `held_status(status, *, payment_kind, duplicate_of_invoice_id)`: only awaiting_confirm or needs_review move; a duplicate pointer or cash means needs_review, otherwise awaiting_confirm.
It matches both existing functions on every reachable state; the one difference, awaiting_confirm with a duplicate pointer, nothing produces.

Order of the doors after confirm, by risk: the supplier item door (map, unmap, pack size - a wrong merge corrupts every cost with no photo to check it against); the menu item door; the till item map; M13's `approve_statement` after its merge (D4); branch alias wording; the sales day loader stays as it is (already one door under an advisory lock).

### 2.6 Tests and steps

Must stay green, unedited except imports: `test_api.py`, `test_confirm_flow.py`, `test_flow.py`, `test_tenancy.py` (its route matrix proves every door still 404s across tenants), `test_extraction_flow.py`, `test_raw_materials.py`, `test_menu*.py`, `test_till_items.py`, `test_contracts.py`, `test_replies.py`.
New `tests/test_invoice_doors.py` against real Postgres: every refusal kind once, and `Done` carrying the fresh row.
One real-concurrency test: `asyncio.gather` a chat confirm and a screen `payment_kind=cash`; whatever the order, never "confirmed" with a hold reply and never "held" with an ack.
Never thin a Postgres suite in the commit that moves code.

1. Bug A with its test and reply constant.
2. Bug B with `MaterialMeasuredOtherwise`.
3. Bug C with `MenuItemArchived`, plus the pack-size recheck.
4. Public `transaction()`, `lock_invoice`, `conn=` on the confirm family - no behaviour change.
5. The `held_status` fold.
6. `doors.py` and `invoice_doors.confirm / approve_cash / dismiss`; the screen routes and the chat OK switch over.
7. `invoice_doors.correct`; the PATCH and chat corrections switch, reply composition moves to the chat adapter.
8. The supplier item door.
9. The menu item door and the till item door.
10. Cleanup on the founder's word: the dead methods (D5), test setup moved onto the doors later.

Steps 1 to 3 are Wave 0; steps 4 onward wait for the planning sitting.

### 2.7 Risks and out of scope

Row locks now last through filing in `correct` (pure Python, milliseconds); each door locks one invoice row first, so deadlock risk is low; `for update` over joins must name `of i`.
A 409 sentence drifting from `store.ts` would break the mock; adapters reuse the existing constants.
Out of scope: the read paths, manual entry's missing duplicate check (`TODOS.md`), RLS, one module for the actor builders, splitting `db.py` by table, the sales day loader, the brief recipients.

---

## 3. A material's price in force as one value

### 3.1 What it means

Every material has one price at any moment: the newest delivery we could cost.
If a newer delivery arrived that we could not cost, the old price still shows but reads estimated, and the screen says why.
Today the back end works that rule out twice and hands raw database rows to four more places, and the web writes the "estimated because" sentence three times, three ways.
After this change one module works out the price and writes its sentences, and every screen prints them as they are.

### 3.2 Current state

Where the rule is decided:
- `menu.pricing` (`menu.py:296-320`) and `api.list_ingredients` (`api.py:1300-1322`) each rebuild "newest costed line per material" and the stale set from the same two reads; only `pricing` takes `as_of`.
- `plates.py:59-65, 171-172` caps the quality and forces estimated when stale; `usage.py:1057` restates the rule a third time with a separate stale set (`usage_report.py:218-248`).

Where the raw `cost_basis` row is unpacked: `menu.py:345-357`, `api.py:302-322` (wrapped by `_material_price`, `api.py:1233-1269`), `usage_report.py:156-172`, and `period_read.py:284-293`.
`menu.py:60-61` imports `_material_price` and `blocked_line_reason` from `api.py`, so a domain module depends on a route module.

Where the web words it:

| Site | "Estimated because" | Per-unit |
|---|---|---|
| `MenuMargins.tsx:77-88` | "a newer delivery **from** 6 Jul 2026 has no cost yet", no reason | "per kg" (`:62, :93, :247`) |
| `RawMaterials.tsx:79-92` | "a newer delivery **on** 6 Jul 2026 has no cost yet - {reason}" | "per kg" (`:46, :51`) |
| `LinesTable.tsx:74-81` | override and asserted, a third wording | "/kg" (`:100`) |
| `dashboardScreen.ts:1021-1023` | - | "/kg" |

What an owner could see differ: the Menu screen drops the reason Materials gives; "per kg" on two screens and "/kg" on two; the web always writes "AED" where Python uses the tenant's currency.
A hidden edge: `/menu`, `/materials` and today's dashboard plates pass no date limit, so an invoice misread with a future date wins there while the period figures ignore it (a follow-up, not this change).

### 3.3 The deepened module

Two shapes were weighed: a pure value with a pure constructor from rows, or a module that also owns the read.
Chosen: the read too - `await price_in_force.read(db, tenant_id, *, as_of=None)` makes the two `db` calls and calls the public pure `from_rows`, which is the test seam.
The SQL stays in `db.py`; the rule "two reads, one date limit, joined this way" lives once.
`list_ingredients` calls `from_rows` directly because it also needs the per-pack rows from the same query.

New module `apps/api/src/faida_api/price_in_force.py`, pure apart from `read`.
`PriceInForce` (frozen): the material id, `cost_per_base_unit`, `base_unit`, `per_display_unit`, `display_unit`, `unit_words`, `quality` (already capped, estimated when stale), `stale`, `newer_uncosted` (the blocked line and its WP-55 reason), the pack and its source, `asserted`, the supplier, product, invoice and line it came from, and `why_estimated`.
`PricesInForce` gives `.get(material_id)` and `.blocked_reason(material_id)` for a material with no price but a known blocked purchase.

Invariants: stale implies estimated; `why_estimated` is present exactly when the quality is estimated; the quality is only ever reliable with limitations or estimated; a return line never wins; `read(as_of=None) == read()`.

The sentences live only here, `why_estimated` checked in order:
- Stale: "Estimated: a newer delivery on 6 Jul 2026 has no cost yet - nothing on the invoice says how much one of these holds."
- Pack override: "Estimated: divided by 1 ctn, which someone entered for this product."
- Asserted fields: "Estimated: leans on the quantity, supplied by a person." - which ports the web's `describeField` (`apps/web/src/lib/format.ts:127`) to Python.

`blocked_line_reason` and `newer_uncosted_summary` move here from `api.py:1201-1230`, which removes `menu.py`'s import of the route module.

API payloads change **additively**: `why_estimated` and `unit_words` on every material price, `unit_words` on invoice-line costs and price-move lines; the existing fields stay, because a browser tab opened before the deploy still reads them.

### 3.4 Callers after

- `plates.Priced` (`plates.py:82-94`) is deleted; `cost_component` takes a `PriceInForce` - its four fields are a subset.
- `menu.pricing` returns `(PricesInForce, vat_rate)`; `CostedMenu.prices` and `.stale` become one `prices`.
- `api._material_price` only serializes; `list_ingredients` loses its stale dict; `usage_report._material_prices` and every `stale_ingredient_ids` are deleted.
- The web prints `why_estimated` and `unit_words` in `MenuMargins.tsx`, `RawMaterials.tsx`, `LinesTable.tsx` and `dashboardScreen.ts`, and its local sentence builders go.

### 3.5 Tests and steps

New pure `tests/test_price_in_force.py`, built by hand from rows like `test_filing.py`: the newest line wins and a tie breaks on confirm time, a stale purchase makes estimated and names itself, a priceless stale purchase gives `blocked_reason`, a stored "verified" is capped, each `why_estimated` sentence, the unit words for g, ml and pc.
The key pin: `test_plates.py:572` extended to assert that `/api/ingredients`' `why_estimated` equals the menu component's byte for byte - the two screens agree by test.
`test_contribution_db.py`'s `as_of` tests, `test_dashboard.py`'s read count and `test_usage_report.py`'s printout must come out unchanged.
Web: a mock parity test in `apps/web/src/lib/__tests__/` that every mock price carries `unit_words` matching its `display_unit` and `why_estimated` exactly when estimated.

1. Candidate 4's words promotion, if not already landed.
2. `price_in_force.py` with its pure tests; the two blocked-line helpers move in.
3. Switch `menu.pricing`, `CostedMenu`, `plates.cost_component` (delete `Priced`), `dashboard.py:475`, `period_read.py:284`; payloads byte-identical.
4. Switch `list_ingredients` and `_material_price`; byte-identical.
5. Switch usage; the printout byte-identical.
6. Add the payload fields, extend the pin, regenerate the mock if the moves block changed; deploy the API.
7. Web: render the API's strings, delete the local builders, update the mocks and the parity test - merged only after step 6 is live, or the reason line goes blank.
8. `plan.md`, `CLAUDE.md`/`AGENTS.md`, and a "Price in force" entry in `CONTEXT.md`.

### 3.6 Out of scope

The price-move pairs query beyond `unit_words`, the draw arithmetic (candidate 1), the web's money and date formatters, any change to which lines count as costed, their order or the `as_of` defaults, and storing prices.

---

## 4. The house wording as public modules

### 4.1 What it means

Faida writes the same kinds of figure in many places: "AED 1,240", "AED 0.06 a plate", "31 Aug", "3 invoices", "per kg".
Each rule lives in whichever file needed it first, and the others borrow it through a name starting with `_`, which means "private, don't touch".
Two rules have already split: one plate cost can read AED 6.41 on one screen and AED 6.42 on another.
This moves every wording rule into one public module, `words.py`, and the two JSON helpers into `wire.py`.
Apart from the plate-money decision (D9), no one sees a different character.

### 4.2 Inventory

Counted with a read-only `ast` walk over `src/faida_api/**/*.py` and `tests/*.py`, printing every `ImportFrom` of a single-underscore name and every `<module>._name` attribute on a `faida_api` module: 36 imports of 18 private names across 9 source modules.

| Name | Defined at | Imported by |
|---|---|---|
| `_dec`, `_iso` | `api.py:207, 211` | dashboard, menu, sales, usage_report |
| `_clean` | `api.py:887` | menu, sales |
| `_material_price` | `api.py:1233` | menu (goes to candidate 3) |
| `_parse_number` | `confirm.py:504` | api, menu, sales |
| `_apply_correction` | `confirm.py:801` | api (goes to candidate 2) |
| `_money_words` | `contribution.py:318` | brief, signals, usage |
| `_price_words` | `contribution.py:324` | signals, usage, usage_report |
| `_pct_words` | `contribution.py:331` | brief |
| `_qty_words`, `_long_date`, `_names_words` | `contribution.py:335, 344, 350` | usage |
| `_plural` | `ratio.py:275` | contribution, usage, usage_report |
| `_short_date` | `ratio.py:280` | contribution, brief, signals |
| `_pending_sentences` | `ratio.py:325` | usage (renamed public, stays in ratio) |
| `_short_branch` | `signals.py:180` | brief, dashboard |
| `_per_unit_words` | `signals.py:419` | usage |
| `_weekday_date` | `dashboard.py:114` | brief |

Tests reaching private names: `test_brief.py:32` (`_money_words`, `_pct_words`); `test_matching.py:15`, `test_delivery_notes.py:26` and `test_signals.py:835, 879` (`menu._move_payload`) belong to other work.

Duplicated or divergent rules:

| Rule | Copies | Same output? |
|---|---|---|
| Headline money, whole AED, half up | `contribution.py:318`; web `roundedAed` | Yes, decided 2026-09-05 |
| Plate money | half up in `contribution.py:324` (the notes at `:544-550`); cut in `signals.py:425, 434` and the web's `summaryMoney` (`MenuMargins.tsx:54`); raw three decimals in `Dashboard.tsx:408` | **No** |
| Whole percent | `contribution.py:331`; inline at `dashboard.py:142, 178, 179`, `usage.py:1678` | Yes |
| Quantity | `contribution.py:335` (no commas); `signals.py:193` (commas, deliberate); `usage.py:454`; `replies.py:615` | Differs at 1,000 and above |
| "31 Aug 2026" | `contribution.py:344` (`strftime`, locale-dependent); `replies.py:610` (own month table) | Same on an English host |
| "Mon 31 Aug" | `dashboard.py:114`; the mock's `generate.py:442`, a deliberate copy | Yes |
| Plurals | `ratio.py:275`; `brief_card.py:138`; `usage.py:477` | Yes |

Only the plate-money rule changes a visible string when unified, provided the dates move to a fixed month tuple instead of `strftime('%b')`.

### 4.3 The deepened modules

One `words.py` rather than one file each for money, dates and lists: each function is two to six lines, so three files would be three shallow modules, and one module answers "how does Faida write X" in one place.
Public: `money`, `plate_money`, `price` (per-unit, fils half up), `pct`, `qty`, `portions`, `count`, `names`, `short_date`, `long_date`, `weekday_date`, `short_branch`, `per_unit`.
Private inside it: the month and weekday tables and the quanta.
Deletion test: without `words.py`, 15 call sites in 9 modules each need their copy back.

`wire.py` holds `dec` and `iso`: a two-line interface with more than 170 call sites, and one rule it fixes - money goes out as a string, never a float.

`typed.py` holds the input side - `parse_number` (from `confirm.py:504`) and `clean` (from `api.py:887`) - because reading what a person typed is not wording.

`words` and `wire` import nothing from `faida_api`, so no import cycle can form.

### 4.4 The plate-money decision (D9)

Rule A, cut to the fils: the dashboard's price-move "plates" clause and every plate margin and cost on `/menu`, documented in `signals._plate_words`' docstring as matching `/menu`.
Rule B, half up to the fils: the dashboard item notes "sold at an average X against today's menu price of Y" and "today's plate is X" (`contribution.py:544-550`).
`CLAUDE.md`'s display rules say plate figures are fils-precise and that half up applies to totals and aggregates; they do not say which way a plate figure rounds.
The stored plate carries three decimals (`plates.PLATE_QUANTUM`), so the rules disagree whenever the third decimal is 5 or more: 6.415 reads AED 6.41 on `/menu` and AED 6.42 in the note.
Recommendation: A, cut, for plate money everywhere - it is what the owner sees most and the one documented; the largest understatement is under one fil.
Per-unit prices keep half up, through `words.price`.

### 4.5 Tests and steps

A new `tests/test_words.py` drives the public functions: a negative headline rounds half up, a plate figure is cut at the third decimal, the dates spell the same months under any locale, `count` handles one and many.
The byte-for-byte guard, run before the first step and after every step: regenerate the dashboard mock with `generate.py` and require `git diff --exit-code apps/web/src/lib/mock/dashboard`, then the brief, brief card, dashboard, signals, price moves, contribution, usage, usage report, replies, sales and menu suites, then the full suite.
No test asserts on code text or import lines.

1. Baseline: full suite, mock regenerated, empty diff.
2. `wire.py`: `perl -pi -e 's/\b_dec\(/wire.dec(/g; s/\b_iso\(/wire.iso(/g'` over the five source files only (`test_sales_api.py` has its own `_iso`), imports by hand.
3. `typed.py`: `parse_number` and `clean`, imports fixed in confirm, api, sales and menu.
4. `words.py`: the twelve formatters moved with bodies unchanged, one at a time, `perl -pi -e 's/\b_money_words\b/words.money/g'` and so on over src and tests; each original deleted.
5. Locale-free dates: a fixed month tuple; `replies.py:610` and `:719` pointed at `words`; `replies._MONTHS` deleted.
6. Fold the inline copies (percent at `dashboard.py:142, 178, 179` and `usage.py:1678`); `ratio._pending_sentences` renamed public; optionally point `generate.py` at `words` and `wire`.
7. The plate-money decision - the only step that changes a string: `contribution.py:544-550` onto `words.plate_money`, `test_contribution.py:583` updated if its value moves, the mock regenerated with a diff touching only those notes.

### 4.6 Out of scope

The web's own formatters (except D10's follow-up), the half-to-even rounding of invoice detail in `replies.py:599`, `usage.quantity_words` (C14.6's unit scaling), `matching.py`'s private names, test helpers borrowed between test files, and `_apply_correction` and `_material_price`, which move with candidates 2 and 3.

---

## 5. How each lane runs

The lane pattern is unchanged from the 2026-09-14 candidates: one candidate (or one Wave 0 bug) per worktree off `origin/master`, its own venv and its own `faida_test_<lane>` database, baseline suite first, the failing test before the fix, `code-review` against the base before asking for a merge, and `plan.md` Progress and Decision Log in the same commit as the code.
No lane touches extraction, so the eval is not in the gate; the dashboard mock's empty diff is, for candidates 1, 3 and 4.
