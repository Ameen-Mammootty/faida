# AGENTS.md

This file provides guidance to AI coding agents (OpenAI Codex and others) when working with code in this repository.

CLAUDE.md and AGENTS.md are identical mirrors (only this header line differs).
When you change one, apply the same change to the other in the same commit.

## The live build plan

`plan.md` is the live build file and the single source of sequencing truth.
Read it at the start of every working session.
End every session by updating it in the same commit as the code: tick the boxes you closed, add a dated line to the Progress Log, and record any changed decision in the Decision Log.
If `plan.md` and the code disagree, the code is right and the plan has a bug: fix the plan.
`Docs/PRD.md` owns product intent; where they conflict on scope timing, `plan.md` wins.

## What this is

Faida: profit visibility for GCC cafeterias and multi-branch chains, fed through WhatsApp.
Cafeterias forward supplier invoice photos to a WhatsApp number; the pipeline extracts, validates, and records them, then surfaces price alerts and profit analytics.

The complete end-to-end MVP - and the demo bar (founder call 2026-08-28, plan.md §1) - is a four-layer chain, and every session builds toward it:
(1) an extraction layer that captures the exact invoice data;
(2) extracted supplier nomenclature mapped to inventory raw materials;
(3) raw materials tagged as ingredients of menu recipes;
(4) the menu costed - so the restaurant sees a menu-wise profit margin per item and knows what to push and what not to push.
The invoice loop (M0-M4) is act one of that demo, gated on its own flawlessness; the demo gate is the end of M6 (menu costing).

```
apps/api    FastAPI backend: WhatsApp webhook, Postgres job queue + worker, (M1+) extraction pipeline
apps/web    Next.js review screen + dashboard (arrives M3)
supabase/   plain SQL migrations + demo seed
eval/       invoice extraction eval harness (arrives M1)
```

## Commands

All backend work happens in `apps/api` (Python >= 3.11):

```bash
cd apps/api
pip install -e '.[dev]'                  # install
cp ../../.env.example .env               # then fill in values
uvicorn faida_api.main:app --reload      # run locally

pytest                                   # all tests
pytest tests/test_webhook_pure.py        # pure tests only, no DB needed
pytest tests/test_flow.py::test_duplicate_delivery_creates_one_document   # single test
ruff check . && ruff format --check .    # lint + format check (line length 100)
```

Flow tests need `TEST_DATABASE_URL` pointing at a real Postgres and are skipped without it:

```bash
export TEST_DATABASE_URL=postgresql://localhost:5432/faida_test
```

That database is wiped on every test (`drop schema public cascade`), then re-migrated from `supabase/migrations/` and re-seeded from `supabase/seed.sql`.
Never point it at a database you care about.

CI (`.github/workflows/ci.yml`) runs ruff + pytest against a Postgres 16 service on every push/PR.
Keep CI under 5 minutes.

## Architecture

One small FastAPI monolith in `apps/api/src/faida_api/`.
A single process serves the webhook, the API, and the background worker (started in `main.py`'s lifespan; disable with `WORKER_ENABLED=false`).

The ingest flow, which everything else builds on:

1. `webhook.py` is a dumb, fast receiver: verify the Meta HMAC signature (fails closed when the app secret is missing), dedupe on `message_id` against `wa_messages`, store the raw payload, enqueue a job, return 200 immediately. No heavy work here.
2. `worker.py` is an asyncio loop in the same process polling the `jobs` table (`FOR UPDATE SKIP LOCKED` claim, 3 attempts, 30 s backoff). It downloads media promptly (Meta URLs expire), sha256-hashes it, stores the immutable original in Supabase Storage at `{tenant_id}/documents/{document_id}/original` (never overwritten, `x-upsert: false`), records the `documents` row, and sends the canned reply. Job handlers must be idempotent under retries. The worker fails closed (M7 WP-72, C2 as amended): `process_wa_message` is the one resolver from sender phone to branch and tenant, every job it enqueues carries `tenant_id` and `branch_id`, `extract_document` reads its document scoped by the payload's tenant and refuses a mismatch or a missing tenant by raising (the job fails, never guesses), and there is one extract job per document ever (`db.enqueue_once` against the 0018 index). A phone no branch is registered to gets its inbound `wa_messages` row stamped `ignored_unknown_sender` before anything else, one polite reply a day at most (best-effort), and nothing created.
3. `db.py` is a thin asyncpg layer: plain SQL, no ORM. Postgres holds data and constraints; business logic lives in Python, never in SQL functions.
4. `wa.py` and `storage.py` are thin httpx clients for the Meta Graph API and Supabase Storage. Both accept an injected transport, so tests mock Meta and storage at the transport layer (see `tests/conftest.py`), never at the client layer. Every reply about a paper is a WhatsApp quoted reply to that invoice's photo (`context.message_id`, carried as `replies.Reply.reply_to`, WP-125): the text is composed in `replies.py` in the card look - WhatsApp markup through its helpers and never inline, a fixed five-icon vocabulary where an icon never stands without a word, user-supplied names through `replies.plain`, the items listed under the total (the catalog name each line was filed under or the printed one, quantity times unit price, a question mark for an unreadable value, eight lines at most and the rest counted for the screen - WP-126, so "line 4" in a question points at something the sender can see), and the closing line always last, so the filing note, the duplicate note and the filed names are the composer's inputs. An inbound reaction is stamped `ignored_reaction` and answered with nothing.
5. `provenance.py` records where every stored number came from (C8): a flat jsonb on `invoices.provenance` keyed by field path, each carrying `origin` (`extracted` / `repaired` / `corrected_chat` / `corrected_screen` / `reconstructed` / `manual`), actor and time. Derived, never self-reported - the repair round is attributed by diffing the invoice before and after the merge. `audit_events` is the matching record of *human* decisions and is written inside the transaction it describes; `extraction_runs` stays the record of *model* runs. Actors are `user:<auth user id>` from the console (the verified Supabase token, M7) and `whatsapp:<phone>` from chat, and are never taken from a client header.

One door for everyone: a correction from the review screen and a "line 4 qty 16" text run the same function (`confirm._apply_correction`), manual entry runs the same validation and snapping as a photo, and the cash approval (M7 WP-74, PRD §21) is the confirm write (`db._confirm`) with a different audit row - `invoice.cash_approved`, reason required - never a second confirm. `payment_kind` is a correctable field (`payment cash` / `payment credit`, or "Paid by" on the screen) so a misread cash is corrected, never approved; it is the one correction that moves a status (C1 as amended, `confirm.status_after_payment_kind`). A new write path - human or model - goes through that door too, and names its actor.

Tenancy: every tenant-owned row carries `tenant_id` from day one.
Branch is resolved from the sender phone (`branches.wa_phone_e164`), never from document text.
Every API read and write is scoped by `auth.py`'s `AuthContext` (M7 WP-73): handlers take it as a dependency, every console-reachable `db.py` method takes `tenant_id` as a required keyword-only argument, and a row outside the tenant is None, so the API answers 404, never 403.
Its source is the user's Supabase access token, verified against the project's JWT signing keys (asymmetric only, fetched with async httpx and cached by key id) plus the `memberships` row read on every request (WP-70); the worker path takes its tenant from the job payload (WP-72) and never from a default. There is no API secret: the project must be on JWT signing keys, and the legacy JWT secret stays because it signs the storage service key. RLS stays deny-all: tenancy is enforced in the application layer by decision (2026-09-03 Decision Log), and policy-based RLS is owed at the first second door to the database (`TODOS.md`).

Sales (M8): a branch-day of till sales has one door - `POST /api/sales/days`, `db.load_sales_day`, one transaction per day under an advisory lock, `loaded` / `unchanged` / `replaced` with an audit row each - fed by the loader at `/sales/load` from the till's own item-wise CSV export: columns mapped once by header name and saved per till (`sales_layouts`), a renamed column stopping the file, branches resolved through `branch_aliases`, the raw file kept under its server-computed hash. Nothing derived is stored. `ratio.py` computes purchases ÷ net sales (cash basis) per branch on every read: purchases are `total - printed VAT` of confirmed papers by printed date (C11), the window is clipped to the branch's loaded range, and every row is labelled reliable with limitations / estimated / incomplete / unavailable with the sentences that made the label (the C9 amendment); recipe coverage by sales value is *costed*, never *complete*. A till name is proposed against the menu (`matching.propose_menu_items`, 0.72, a size-word-only name proposes nothing) and mapped only with a keystroke through the three till-item doors, one audit row each. The `/sales` screen (WP-84, variant B) is one sentence naming the branch to look at first, the ranked table with the "No branch" row and the chain total, the drill to each paper's photo, and the queue. A till label taught to the wrong branch is put right from the loader (2026-09-07): every label the file reads through an alias is listed with the branch it reads as and one control, "Not this branch?", which un-teaches through `DELETE /api/branches/{id}/aliases/{alias_id}` and teaches again through the POST, one audit row each, then re-reads the file so the days move before anything is written; a second step that fails leaves the label unteached and says so, never re-taught to the old branch; "Forget this label" is the first door alone.

Dashboard (M9): one read serves the whole owner screen - `GET /api/dashboard?from&to&branch_id` in `dashboard.py` - and every figure on it is derived on that request and never stored, out of one period, one set of clipped windows and one costed menu, so nothing on the screen can disagree with anything else on it; the reads it makes are an enumerated list with the count asserted by a test, flat whatever the menu's length or the branch count.
Contribution is derived the same way (`contribution.py`, C12): net item sales minus portions times the plate, the plate costed at the prices in force on the period's last day, called "contribution before overheads (estimate)" and never net profit, with the share of sales it covers said beside it - a row whose plate is incomplete or whose till line carried no quantity is listed, leaves every aggregate, lowers that costed share and never downgrades the quality word (C9 extended, which is also why a league row carries two words, one for the ratio and one for the contribution).
The three signals are rules and sentences, not a model (`signals.py`, C13): an item that sells well and keeps at least ten points less than the chain, a supplier price rise weighed by the portions sold since it landed, and a branch keeping at least five points less than the chain over that branch's own window; ranked by the money at stake, capped at five, silent on an input the read does not trust, and carrying the estimated word when it fires on an estimated one; since 2026-09-08 a signal also carries the numbers its sentence is written from as fields (`kept_pct` and `benchmark_pct` for a dish or a branch; `price_before`, `price_after`, `unit` and `change_pct` for a spike, the last through `signals.move_change_pct`), and the price-moves block carries the same four on every real move, so the screen can draw them without re-reading the sentence.
The `price_moves` block beside them is each material's latest move inside the window - both directions at the spike's own 5% gate, basis changes listed after it and carrying no number - and its sentences are composed once in Python (`signals.weigh_move`, `menu.price_moves`, `dashboard.price_moves_block`) for the dashboard, the Menu screen's card and the mock alike, so one move can never be quoted in two sets of words or for two amounts.
The screen is `/dashboard`, where a fresh sign-in lands (`gate.ts`'s `DEFAULT_AFTER_LOGIN`, P10), in its simple form since 2026-09-08 (the founder's brief: owners who are "not at all sophisticated", a screen that was "too much verbose", "information overload"): the freshness sentence with the to-dos beside it as a strip of links (papers waiting, till names with no dish, dishes that cannot be costed - present only when there is something behind them); the answer as two bullets the API writes crisp ("Look at Deira: keeps 61%, the least of the three branches.", "Chicken 65 Dry: sells well but keeps only 38% against the menu's 67%." - `dashboard.py`'s `branch_answer` and `item_answer`, copied in the mock's `generate.py`); three tiles in plain words - Sold, Kept after ingredients, Paid to suppliers - that are the row in view with the chain's figure named beside it, each one figure, one line in the answer's own idiom ("AED 67 of every 100 sold") and a chip only where the word is a caveat, with the formal names the contracts pin ("purchases ÷ net sales (cash basis)", "contribution before overheads (estimate)") as the first line behind the tile's info icon and the covered share as the kept tile's bar; the branch league as name, sold, kept and the share kept drawn beside a whole-number percentage, ranked lowest first, the quality word said once for the block when every row agrees; worth a look and supplier prices side by side and held to one height, each row a track (the panels board's Variant C, the founder's pick of 2026-09-08): a dish or a branch is its kept share filled against a gold tick at its benchmark, a price move is the price now filled against a tick where it was with the change as a chip, the money on the right and the API's sentences behind the row's icon (`shareTrack`, `priceTrack`, `TrackRow`); the dishes as best and weakest earners side by side; every sentence that qualifies a figure behind an info icon (`InfoTip.tsx`, the founder's redesign of 2026-09-07), so the answer, the three figures and the whole league sit on one laptop screen; the branch view is that same screen filtered by `?branch=`, never a second route (P7).
`dashboardScreen.ts` holds every decision the component renders, because there is no component-rendering test capability and a choice left inside React would be untested by construction; the mock's fixtures are produced by the shipped Python modules through `apps/web/src/lib/mock/dashboard/generate.py`, and are regenerated whenever the wording or the arithmetic moves.
The shell around all five screens is `AppShell.tsx` (WP-97): from 1280 px a Date Palm sidebar in three groups - 1280 and not 1024, so the content column stays about 1000 px, wider than the 976 px every fixed grid was measured at - and under that width the shipped top bar with the brand mark as the dashboard link, one chrome displayed at a time and one session read per page load.
Whole-dirham headlines round half up from M9 (`roundedAed`, decided 2026-09-05), so a headline agrees with the sentence printed beside it instead of reading a dirham under it - the display rule below.

Usage (M12 phase one, 2026-09-08): what the period's sales needed of each raw material against what was bought of it, per branch, derived on every read and stored nowhere - `usage.py` is pure (`material_rows`, `chain_material_rows`, `unassigned_rows`, `unused_materials`, `recipe_coverage`, `unmapped_packs`, `orphans`, `left_out`, `quantity_words`, `STANDING_SENTENCE`) and composes every sentence, so the printout today and the panel later can never quote a figure in two sets of words (C14).
Used is the recipes on file times the portions the till printed (refunds counted as made and named, P9), each component converted by `plates.to_base_qty`, divided by its optional usable share (`recipe_components.usable_share`, migration 0021, D13 - the plate divides by the same share, so cost and quantity always describe the purchased amount) and by the yield, rounded once per dish to 0.001 base units; bought is every confirmed stock line in the branch's clipped window (`db.list_period_material_purchases`, line grain, price and currency never filters) times the frozen `cost_basis.pack_base_quantity` where the line was costed and `costing.resolve_pack` only where it was not (D2), rounded once per line, so every sum above is exact.
The difference is a *recorded difference*, never variance, waste, theft, shrinkage, loss or negative stock (a test calls the module and pins the absence of each word); a hole is named and never zeroed (a till line with no quantity blanks every material that dish names, an unreadable or quantity-less pack line blanks bought, no pack mapped means no bought figure, a paper with no branch is listed apart and never summed, a material no sold recipe names is listed out of the ranking); there is no headline sentence (D9) and a row with one purchase date says a single delivery is not a rate (D15).
Phase one's consumer is `python -m faida_api.usage_report --tenant <id> --from --to [--branch]`, read-only, in three layers - `usage_inputs` (the dashboard's own reads through `dashboard._branch_ratio_rows`, `_item_sales`, `_menu_items` and the sixth value of `_menu_context`, plus the one new read), `usage_blocks` (pure, §3.1's block) and `render` - with `usage_payload` ready to become the dashboard's `usage` block in phase two, which waits on the pilot's owner acting on the printout (D22) and a design review drawn from it (D23).

Extraction (M1+): Gemini 3 Flash (`gemini-3-flash-preview`) via the google-genai SDK with structured JSON output - the shipped default since 2026-08-29 (measured bake-off, Decision Log) - behind one thin provider interface so the provider swaps in one place; Claude Opus 5 stays wired as the fallback (`EXTRACTION_PROVIDER=anthropic`, no deploy needed).
Accuracy is a pipeline property, not a prompt property: deterministic arithmetic reconciliation, one scoped repair pass, supplier-memory snapping, and derived (never self-reported) confidence.
Supplier matching (`matching.match_supplier`) is that character score with a word check on top (2026-09-05): a candidate over the 0.85 bar is refused when a meaningful word on either side has no counterpart on the other (single-letter runs joined, a prefix only for a dotted abbreviation, per script, legal boilerplate ignored), so a new vendor "Al Madina ABC" never books under "Al Madina"; the check can only remove a match, and confirm matches a supplier-less paper again before creating a supplier. The evidence is `tests/fixtures/supplier_name_pairs.json` and the corpus guard in `tests/test_matching.py`; a wrong booking is silent and permanent, a miss is one alias keystroke (WP-87).
The full six-layer design is `plan.md` §5.
Once the eval harness exists, every pipeline change runs the eval before merge.

## Standing rules (plan.md §2, distilled from the previous build's post-mortem)

- Vertical slices only: no endpoint without the screen or chat message that consumes it, in the same milestone.
- One backend: Postgres is data + constraints, not a second implementation of the business logic.
- Migrations are plain SQL files in `supabase/migrations/`, squashable freely until there is a paying customer.
- Deterministic money math; AI only at extraction.
- The `jobs` table + in-process worker is the queue. A broker/durable queue is banned until job volume proves the need.
- Recovery is a screen, not a subsystem: failed extraction means status `failed`, one helpful WhatsApp reply, a retry button, and manual entry. Nothing more.
- Test the path the user takes: the eval harness and a few end-to-end tests over the real flow outrank any volume of unit tests. Banned: tests that assert on code text, tests of framework behavior, coverage targets for their own sake.
- New scope enters the plan only with a customer quote naming who asked and what they said.

## How to report back

Answer in plain English, the way you would explain it to the founder rather than to another
engineer. Assume the reader is smart, knows the business cold, and does not know what a schema
validator or a reconciliation identity is. The point of a report is to make a decision easy.

- Lead with what it means, not what you did. "The scorecard was marking correct answers wrong"
  before "`invoice_reconciles` delegated to the shipped validator".
- Translate every internal term on first use, or drop it. Ground truth is the answer key.
  Reconciliation is whether the invoice adds up. An eval is an exam.
- Name the decision the reader has to make, and say which way you would go and why.
- Say plainly when a number is not what it looks like: which corpus it came from, what it does
  not cover, and what would change it.
- Keep the code identifiers for the diff and for follow-up questions. They belong at the end of a
  point, not at the front of it.

## Product display rules

Rounded AED headline numbers, rounded half up (`roundedAed`, decided 2026-09-05); exact figures only in invoice detail.
Half up rather than truncated because the dashboard was the first screen to put a rounded headline beside a sentence that rounds half up, and a truncated headline read a dirham under it and made a loss look smaller than it is.
Exception, pinned by the 2026-08-30 design review: per-plate costs and margins are fils-precise
everywhere (a plate margin rounded to whole dirhams carries no information at karak prices);
the rounding rule applies to totals and aggregates.
No jargon; colour never carries meaning alone.
Purchases ÷ net sales is never labelled "food cost %", and branch contribution is never labelled net profit.
