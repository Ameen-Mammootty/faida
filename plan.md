# Faida — MVP Build Plan (live file)

> **This is the live build file.** Every working session starts by reading it and ends by updating it:
> tick the boxes you closed, add a dated line to the Progress Log, and record any decision that
> changed in the Decision Log — in the **same commit** as the code. If this file and the code
> disagree, the code is right and this file has a bug: fix the file.

- **Product:** Faida — profit visibility for GCC cafeterias and multi-branch karak/paratha chains, fed through WhatsApp.
- **Reference:** `Docs/PRD.md` (v2). This plan sequences the build; the PRD owns product intent. Where they conflict on *scope timing*, this plan wins.
- **Start date:** 2026-08-22
- **Current milestone:** **M0 proven on real hardware 2026-08-23 (F1-F4 done)** - the live chain carried through M1 extraction and M2 confirm on the first real invoice. The live project's schema is at migration 0011 (applied 2026-08-28), so the C8 code on master is safe to deploy. **The demo bar was raised 2026-08-28 (founder call): the demo is the complete end-to-end MVP chain - exact invoice data → supplier items mapped to raw materials → raw materials as recipe ingredients → menu costed, closing on a menu-wise margin per item - so the demo gate moved from M4 to the end of M6; M4 is now the loop gate.** Founder-gated: a permanent access token (the 24 h token expired 2026-08-23 19:00; replacement in progress), corpus photos (F6) for the accuracy loop (WP-15/16), loop rehearsals (M4 gate), one real menu with recipes and selling prices (F7, for M6's costing and the demo). The review screen is live at `https://faida-web-nine.vercel.app` (deployed 2026-08-24). **M5 (raw materials) is decomposed as of 2026-08-29** into WP-50 to WP-55 (§7.3), and **every M5 prerequisite is closed**: **WP-19** (a short read that silently drops lines) shipped 2026-08-28 with the guard live on both providers, alongside WP-26 (a totals block off-frame confirmed away with a null total) and WP-28 (a USD invoice walking into an AED baseline). Known gaps before the demo: the amber question still dead-ends on a plain-English answer (dates and invoice numbers now have their own grammar and a year question, closed 2026-08-28 with WP-25/WP-27 - free-text answers to *other* questions still clarify). Forward-to-reply measured **19.9 s and 23.0 s** on 2026-08-25 against the ~20 s target, with no repair round on either - the 28.4 s figure is retired. WP-16 rounds 1-2 ran 2026-08-24/25 (`eval --live`): every §5 accuracy target is met *on the ten generated invoices* (phase 1, not pilot accuracy), the rebuilt ground truth signed off by the founder on 2026-08-25 with zero corrections (F8), and five proposed/corpus images still ungenerated (CUT-01 generated 2026-08-29; AMD-01 joined the corpus 2026-08-28). **The post-demo track was resequenced 2026-08-28** (§8, Decision Log): raw materials → menu costing → auth → sales, because costing a plate needs no sales data and the raw-material layer the MVP depends on was in no milestone at all. Nothing in M0-M4 moved

---

## 1. North star and the one demo that matters

The MVP proves one thing (PRD §1): *a cafeteria forwards supplier invoices and daily sales to a
WhatsApp number and understands which items, ingredients, and branches are helping or harming
profit.*

**The demo bar is the complete end-to-end MVP chain** (founder call 2026-08-28 — see the
Decision Log; the earlier bar, the invoice loop alone, is now act one of the demo, not the demo):

1. an extraction layer that captures the **exact invoice data**;
2. extracted supplier nomenclature **mapped to inventory raw materials**;
3. raw materials **tagged as ingredients of menu recipes**;
4. the **menu costed** — so the restaurant sees a menu-wise profit margin per item and knows
   what to push and what to quietly stop pushing.

```
Forward invoice photo on WhatsApp
   → parsed reply in chat, with a price alert   ("Milk powder up AED 4 since last week")
   → reply "OK" → invoice recorded; web screen shows photo beside extracted fields, green per field
   → extracted items mapped to raw materials (proposed by the matcher, approved one keystroke each)
   → raw materials sit inside menu recipes
   → every menu item shows its cost and its margin at its own menu price, ranked
   → the owner sees which items to push — and which popular item quietly loses money
```

Everything in M0–M6 serves that demo: M0–M4 build and harden the invoice loop, M5 maps
materials, M6 costs the menu. **The demo gate is the end of M6.** Everything after it grows the
demo into the full MVP without rewriting it.

---

## 2. Lessons we are carrying in (the anti-over-engineering rules)

These come from the post-mortem of the previous build (132k lines of backend, 182 migrations,
329 RPC contracts, a 13-phase recovery subsystem — and a WhatsApp channel that never sent one
real message). They are standing rules, not suggestions:

1. **De-risk the external dependency first.** The WhatsApp channel is the only part we don't
   control. It goes live before any other code is written, and it is exercised with a real phone
   at every milestone.
2. **Vertical slices only.** No endpoint exists without the screen or chat message that consumes
   it, in the same milestone. No write without a read.
3. **One backend.** Business logic lives in the application layer. Postgres holds data,
   constraints, and (later) RLS — not a second implementation of the business logic in SQL
   functions.
4. **Migrations are squashable until we have a customer.** No freeze ceremony, no immutability
   rules, no migration numbering discourse. When the schema churns pre-launch, squash.
5. **Recovery is a screen, not a subsystem.** Failed extraction → status `failed` + one helpful
   WhatsApp reply + a retry button + manual entry. Nothing more until real usage proves the need.
6. **Test the path the user takes.** The eval harness (real invoices, ground truth, scored) and a
   handful of end-to-end tests over the real flow outrank any volume of unit tests. A test that
   greps code text instead of executing it is banned.
7. **Deterministic money math, AI only at extraction.** (PRD §25 — this rule was always right.)
8. **Scope additions need a customer quote.** Nothing gets built "because the schema supports it."
   New scope enters this plan only with a sentence naming who asked and what they said.
9. **Budget check:** if any single milestone grows past ~2 weeks of work or the codebase past
   ~10k lines before the demo gate, stop and cut scope.

---

## 3. Fixed decisions (stack and architecture)

Settled now so we never relitigate them mid-build. Changes go through the Decision Log.

| Area | Decision | Why |
|---|---|---|
| WhatsApp channel (demo) | **Meta WhatsApp Cloud API, direct, free test number** | No BSP contract, up to 5 registered recipient phones, free-form replies free inside the 24-h window. Closest to production shape. Fallback if setup stalls >1 day: Twilio sandbox to unblock, swap later. |
| WhatsApp channel (production) | Verified WABA + purchased sender + **utility**-category template for the daily brief | PRD §11. The legal-entity → Meta verification → WABA chain is slow and external — it starts early (M5) and runs in the background. |
| Backend | **Python / FastAPI**, one small monolith | One process serves webhook + API + (initially) inline background tasks. Familiar stack, best SDK support for the extraction pipeline. |
| Extraction model | **Gemini 3 Flash** (`gemini-3-flash-preview`) via the google-genai SDK, structured JSON output against the same strict schema, dynamic thinking left on (amended 2026-08-29, Decision Log; was Claude Opus 5, which stays wired as the fallback - `EXTRACTION_PROVIDER=anthropic`, no deploy) | Won the measured bake-off on the phase-1 corpus: accuracy at or above the Opus baseline, ~$0.0065/invoice (a tenth of Opus), 9.5 s average model time with every case inside the ~20 s reply target. Provider call sits behind one thin interface (PRD §25.1) so it swaps in one place. |
| Database + storage + auth | **Supabase** (Postgres, Storage, later Auth + RLS) | Rented foundations. Free tier for the demo. |
| Background work | **A `jobs` table + an async worker loop inside the same process** | Demo volume is one message at a time. A durable queue/broker is banned until job volume proves the need (revisit at M7). |
| Frontend | **Next.js** (single app), deployed on Vercel | One review screen for the demo; grows into the dashboard. |
| Hosting (backend) | Railway or Fly, single always-on service | Webhook needs an always-on public URL; Vercel functions are wrong for the worker loop. |
| Repo layout | Single repo: `apps/api` (FastAPI), `apps/web` (Next.js), `supabase/` (migrations), `eval/` (invoice eval harness), `plan.md` (this file) | |
| CI | GitHub Actions: lint, typecheck, unit tests, eval smoke (3 fixture invoices) on every PR | Keep it under 5 minutes. |
| Money display | Rounded AED headline numbers, exact figures only in invoice detail. No jargon. Colour never carries meaning alone. | Inherited from the old DESIGN.md's four rules — the one part of the old build worth keeping verbatim. |
| Language (demo scope) | **English-only** WhatsApp replies and review-screen UI. Invoices themselves stay mixed Arabic/English; extraction handles both. | Smallest template/parsing surface for the demo; bilingual revisited with pilot feedback. |

**Explicitly out of the MVP** (PRD §2.4, plus this plan's deferrals): POS replacement, payments,
payroll, GL, autonomous actions, conversational AI, khata, delivery-aggregator reconciliation,
multi-region, SSO, **full inventory ledger / theoretical consumption / stock counts** (deferred —
see §8), goods receipts as a separate flow (deferred), moving-average costing (schema leaves the
door open; PRD §19).

---

## 4. Data model (initial — 8 tables)

Every tenant-owned row carries `tenant_id` from day one (columns are cheap; retrofitting isn't).
RLS enforcement is deferred to M7 — the demo runs single-tenant seeded.

```
tenants            id, name, currency, created_at
branches           id, tenant_id, name, wa_phone_e164 (sender → branch mapping), timezone
suppliers          id, tenant_id, name, name_aliases text[]
supplier_items     id, tenant_id, supplier_id, canonical_name, unit, pack_size,
                   last_price, prev_price, last_price_at        -- latest-purchase-price (PRD §19)
supplier_item_prices  id, supplier_item_id, price, invoice_id, observed_at   -- full history for trends
documents          id, tenant_id, branch_id, storage_path, sha256, mime, source ('whatsapp'|'upload'|'manual'),
                   wa_message_id UNIQUE NULL, status ('received'|'processing'|'extracted'|'confirmed'|'failed'),
                   created_at                                    -- immutable original, never overwritten
invoices           id, tenant_id, branch_id, document_id, supplier_id, invoice_no, invoice_date,
                   currency, subtotal, tax, total, payment_kind ('credit'|'cash'), status
                   ('draft'|'awaiting_confirm'|'confirmed'|'needs_review'), confidence jsonb (per field)
invoice_lines      id, invoice_id, raw_name, supplier_item_id NULL, qty, unit, unit_price, line_total,
                   checks jsonb ('arith_ok', 'snapped', ...)
```

Plus three operational tables: `wa_messages` (message_id UNIQUE, direction, from_phone, type,
payload, status — the dedupe + message spine), `jobs` (id, kind, payload, status, attempts,
last_error), and `audit_events` (tenant, actor, action, subject_type, subject_id, detail — every
human decision, C8; `extraction_runs` is its counterpart for model runs). `invoices` also carries
`provenance` jsonb: per field, where that value came from (C8). Raw materials (ingredients + the supplier-item mapping) arrive in M5,
recipes/menu costing in M6, users/roles in M7, sales tables in M8.

Migration policy: plain SQL files in `supabase/migrations/`, squashed freely until first customer.

---

## 5. The accuracy engine (the heart of the build)

"Very accurate" is a pipeline property, not a prompt property. Six layers, in order:

1. **Extraction call.** Image → the extraction model (Gemini 3 Flash since 2026-08-29; Opus 5
   is the configured fallback) with a strict schema: supplier block, invoice no,
   date, currency, lines (raw_name, qty, unit, pack_size, unit_price, line_total), subtotal, tax,
   total. Structured outputs guarantee shape; prompt+model version recorded on the document row.
2. **Arithmetic reconciliation (deterministic).** Per line: `qty × unit_price ≈ line_total`
   (tolerance for rounding). Document: `Σ line_totals + tax ≈ total`. A hallucinated digit almost
   never survives cross-checking against three other numbers on the same page. Results stored per
   line in `checks`.
3. **Targeted repair pass.** Any failed check → one *scoped* second call: "Line 3: qty 12 ×
   4.50 ≠ extracted 58.00 — re-read those three cells." Never re-extract the whole document.
   Max one repair round; still failing → field flagged amber.
4. **Supplier memory.** Match supplier by name/aliases; fuzzy-snap line `raw_name` to that
   supplier's `supplier_items`; on match, compare `unit_price` to `last_price` → **price alert**
   (the demo's money moment). Unknown items are created on confirm, so the catalog self-builds.
5. **Derived confidence, not self-reported.** A field is **green** when it passed arithmetic and
   (for lines) snapped to a known item at a plausible price; **amber** otherwise. Amber fields
   drive one specific WhatsApp question ("Is line 4 quantity 10 or 16?") — never a dead end.
6. **Failure path = one message.** Unclassifiable/unreadable → "Couldn't read this one — try a
   straighter photo, or type the total." Document stays stored with status `failed`; manual entry
   always available.

### The eval harness (`eval/`) — built before polishing anything

- **Corpus, in two phases (amended 2026-08-23, see the Decision Log).** *Phase 1, now:* the
  prompt-generated hazard set in `eval/fixtures/generated/` is the working corpus for M1. It was
  shown to prospective clients who confirmed they receive invoices like these, so it is
  representative rather than merely plausible — enough to run the accuracy loop, and far better
  than stalling the MVP for a fortnight. *Phase 2, when F6 lands:* 20–25 *real* invoices from the
  target segment — crumpled thermal paper, handwritten Arabic/English mixes, karak-supplier
  delivery notes — become the corpus the §5 gate targets are actually scored against, and every
  later pilot failure joins them.
  **The honest limit of phase 1:** generated images carry the hazards someone thought to prompt
  for. They cannot carry the ones nobody did — a stapled second page, a thumb over the total, a
  date written 5/7 with no year, ballpoint that never came through the carbon. So a number from
  phase 1 is always reported as *measured on generated invoices*, never quoted as pilot accuracy,
  and phase 2 is expected to move it down.
- **Ground truth:** one JSON per invoice, hand-verified, same schema as extraction output.
- **Runner:** `python -m eval.run` → scores field-level accuracy (exact for numbers/dates, fuzzy
  ≥0.9 for names), line recall/precision, reconciliation rate, repair-pass lift, cost and latency
  per invoice. Prints a table; writes `eval/results/<date>.json` so runs are comparable.
- **CI policy:** the CI smoke runs 3 fixture invoices against *recorded* provider responses - no
  API key, no spend, no flakiness in CI. The full live eval runs on demand before any pipeline
  change merges; recorded fixtures are regenerated whenever the prompt version bumps.
- **Targets (M4 loop gate):** totals and amounts ≥98% field accuracy; line-item fields ≥95%;
  100% of confirmed invoices arithmetically reconciled; zero silent wrong numbers (a wrong value
  must be amber, never green).
- Every pipeline change runs the eval before merge. Prompt tweaks without the eval are guessing.

---

## 6. Milestones — the invoice loop (M0–M4)

> The demo track is M0–M6: the loop below, then §8's M5 (raw materials) and M6 (menu costing).
> **The demo gate moved from M4 to the end of M6** (founder call 2026-08-28): the demo closes on
> a menu-wise margin screen, not on the loop alone. M4 remains the *loop* gate — the loop must
> run flawlessly before anything is built on top of its numbers.

Sized for focused build days with CC assistance. Each has a **Done when** that is demonstrable,
not documentary. The WP-, F-, and C-identifiers in the checklists are defined in the execution
plan (§7).

### M0 — Channel live (Day 1–2)
- [x] Meta developer app + WhatsApp Cloud API test number (F1, 2026-08-23): app `Faida`
      (28510773781859548), WABA 1472656894879364, test number +1 555-668-2519, 3 demo phones
      registered as recipients. Webhook repointed at the Railway host, `messages` subscribed at
      v26.0. The step nobody had documented: configuring the callback URL is *not* the same as
      subscribing the app to the WABA - until `POST /{waba-id}/subscribed_apps` ran, the only
      subscriber was Meta's own `WA DevX Webhook Events 1P App`, so real forwards were recorded
      in the dashboard and never delivered to us. Publishing the app is *not* required
- [x] Supabase project `Faida MVP` (ap-south-1): schema migrated, private `documents` bucket,
      demo tenant/branch seeded, live branch phone set to the founder's demo handset
- [x] Deployed to Railway (F3, 2026-08-23): `faida-production-3b60.up.railway.app`, Singapore,
      1 replica, Dockerfile builder, root `apps/api`, watch path scoped so `apps/web` pushes do
      not restart the API. Verified from outside: `/health` 200 `db:true`, verify handshake
      echoes, wrong token and unsigned POST both 403. Boot takes 6-10 s (pip install + asyncpg
      pool), so any health check needs a grace period or it restart-loops a healthy service.
- [x] FastAPI service code: webhook GET verification + POST signature check (fails closed
      without app secret), `/health`
- [x] Webhook: verify → dedupe on `message_id` → store raw payload (`wa_messages`) → enqueue →
      return 200 fast; worker downloads media promptly, sha256-hashes, stores immutably
      (`x-upsert: false`), records `documents` row — idempotent under retries
- [x] Canned reply loop (media received / text onboarding / unsupported type), outbound
      messages recorded
- [x] Initial migration `0001_init.sql` (plan §4 tables + `wa_messages` + `jobs`) + demo seed
- [x] Tests: 13 (pure signature/parse + end-to-end flow vs real Postgres with Meta/storage
      mocked at transport: full ingest, duplicate delivery, unknown sender, retry/backoff);
      CI (ruff + pytest + Postgres service) green locally
- **Done when:** a real phone forwards a photo and gets a reply within seconds; the image is in
  storage; sending the same message twice creates one document. ✅ **PROVEN 2026-08-23 (F4)**
  from +971509772702 against the live Railway service: ack in **6.70 s**, document stored with
  sha256 + immutable path, branch resolved from the sender; dedupe proven in production the same
  afternoon (`duplicate wa message skipped`, 200 OK). The run carried straight through M1 and M2
  live - see the Progress Log entry for the extraction, amber-question and confirm results.

### M1 — Extraction pipeline + eval harness (Day 3–6)
- [x] Anthropic API key with billing enabled (F5, 2026-08-23); verified live against
      `claude-opus-5`: a synthetic invoice extracts clean, all checks green, no repair
- [x] Provider interface + Claude Opus 5 structured extraction (layer 1); classification
      (invoice / z_report / other, polite decline for memes) happens inside the same structured
      call - a separate classifier call adds cost and latency for nothing at demo volume (C3, WP-10)
- [x] Arithmetic reconciliation + targeted repair pass (layers 2–3) (C4, WP-11, WP-12)
- [x] Pipeline orchestration + persistence: `extract_document` job, status transitions, draft
      invoices + lines + checks, run metadata, failure + meme decline paths (C1, C2, WP-13)
- [x] Ground truth hand-verified (F8, WP-15) **2026-08-25**: all ten image-backed cases signed
      off against the photos in `Docs/f8-review.html`, **zero corrections** across the 134 values
      that were decided rather than copied. Recorded in
      `eval/fixtures/generated/SIGNOFF.json` with a content hash per truth file, and
      `eval/tests/test_signoff.py` fails if a verified file changes afterwards - a sign-off that
      cannot go stale silently. Runner + scores (WP-14) and the CI smoke (§5 policy) were already
      done. **Still short of the ≥15 target**: the phase-1 corpus is 10, because `DUP-01`,
      `EDGE-02`, `EDGE-03`, `HW-03` and `NEG-01` are ground truth for images nobody generated;
      they are recorded as `unverifiable` and the test flips them back to needing review the
      moment an image appears. F6 (real photos) still owns phase 2
- [x] `--live` mode in `eval/run.py` (2026-08-24): the accuracy loop's missing tool. Runs the
      product's own layers 1-3 through the product's own modules, scores repair lift and cost per
      invoice, records responses so every re-score afterwards is free, and prints the mismatches
      behind each score - `got` versus `truth`, per field
- [ ] Iterate prompt/pipeline until targets in §5 are met on the corpus (WP-16). **Round 1 ran
      2026-08-24 on the ten generated invoices** (phase 1, so: *measured on generated invoices*).
      After the ground-truth rebuild and the discount-sign fix: classification, supplier, invoice
      no, date, currency, subtotal, tax, total, line recall, precision, raw_name, qty, unit,
      unit_price and line_total all **100%**; reconciliation **100%** (10/10). **Round 2 ran
      2026-08-25** and closed both open questions with founder decisions (cash-or-credit by
      rule, a units dictionary): `payment_kind` 60% -> **100%** and `pack_size` 19% -> **99%**,
      the one remaining miss being a bare "30" with no unit. Every §5 target is met on this
      corpus. ~$0.06 and ~10.7 s of provider time per invoice. Two concrete defects were already found live on 2026-08-23, both ahead of any
      eval run: (a) **VAT-inclusive invoices fail C4 reconciliation** - the GCC norm is line
      prices inclusive of VAT, so `subtotal + tax = total` is the wrong identity and every such
      invoice goes spuriously amber even when extraction was perfect (C4 amended 2026-08-23;
      the fix is **WP-17**, which does not wait on the corpus); (b) **the amber question invites
      an answer it cannot parse** - it asks "which is right?", the founder answered "It's
      correct, the lines are inclusive of vat", and got "Sorry, I didn't get that"; (c) **the
      printed currency word reached the reply** - a real cash invoice on 2026-08-24 replied
      "total dirhams 402.00";
      fixed the same day: `extraction/currency.py` derives the ISO code (Dhs, dirhams, د.إ, the
      U+20C3 dirham sign, riyal marks incl. U+20C1) once in the pipeline, the manual path, and
      the eval scorer, while C3 keeps reading the currency as printed
- [x] Line-completeness guard: a short read fails loudly instead of persisting a partial invoice
      whose header still reconciles (WP-19, ported from the old platform's post-mortem 2026-08-24;
      shipped 2026-08-28 - stop_reason='max_tokens' raises even when the cut-off JSON parses,
      through extract and repair alike; the self-reported row count was foreclosed by the
      measured schema ceiling, see the Decision Log)
- **Done when:** eval report hits the accuracy targets, and a forwarded photo produces a stored
  draft invoice with per-field checks.

### M2 — Confirm flow, supplier memory, price alerts (Day 7–9)
- [x] WhatsApp reply composer: supplier, line count, total, amber-field question(s), price alerts,
      "Reply OK to confirm", plus cash-hold, failure, and decline messages - deterministic English
      templates, zero generation (WP-20)
- [x] "OK" / correction parsing (OK, or "line 4 qty 16"-style fix, or numbered options) → status
      `confirmed`; corrections re-run validation; inbound texts resolve to the newest
      awaiting-confirm invoice for that sender per C5 - no pending-confirmations table (WP-21)
- [x] Supplier matching + item snapping + `last_price`/`prev_price` update on confirm (layer 4)
      (WP-22)
- [x] Price alert computed in the *extraction reply* (the demo's money moment) when the extracted
      unit price differs from the snapped item's `last_price` by ≥5% and ≥ AED 0.25;
      `last_price`/`prev_price` update only on confirm, so an unconfirmed invoice never pollutes
      the baseline (WP-23)
- [x] Cash invoices (`payment_kind = 'cash'`) marked and held as `needs_review` — approval UI comes
      later (M7); the distinction is captured now, per PRD §21 (WP-24)
- [x] Required-field ambers: a missing invoice date or number is asked for in the reply, never
      silently stored (WP-25, observed live 2026-08-24; shipped 2026-08-28 together with WP-27's
      date reading - the answer lands via the correction grammar, `date 5/7/26` / `invoice no
      4471`, and a date-shaped answer with no year gets the year question, never a dead end)
- [x] **Totals block off the page: reconstructed by asking, never by computing** (WP-26, done
      2026-08-28): with no total the reply shows the line sum and asks the two facts C4 cannot
      derive without one - is that the whole invoice, and do the prices already include VAT. A
      bare `OK` no longer confirms such an invoice from any door; the answer lands through the
      correction grammar (`total 710.25 inc vat 5%` / `total 710.25 no vat`) and is stamped C8
      origin `reconstructed`, while a total read off the page stays `corrected_chat`
- [x] **Foreign-currency hold** (WP-28, done 2026-08-28, from the live USD forward): an invoice
      whose currency differs from `tenants.currency` is asked about in the reply, confirms
      normally, and never moves price memory - no catalog row, no price observation, no alert -
      with the ack saying so. `currency AED` corrects a misread currency from chat
- **Done when:** two invoices from the same supplier a week apart produce a correct
  "X up AED Y" alert in chat, and "OK" records the invoice. This gate becomes a permanent e2e
  test in CI from the moment it first passes.

### M3 — Review screen (Day 10–12)
- [x] Backend API for the screen (C6): invoice list/detail with signed image URLs, field patch
      (re-validates), confirm, manual upload, price history; demo access via one shared-secret
      bearer token, real auth arrives in M7 (WP-30)
- [x] Next.js app with the one screen: invoice photo left, extracted fields right, green/amber per
      field (with an icon or label, never colour alone), edit-in-place for amber fields, confirm
      button (WP-31)
- [x] Invoice list (by branch, by supplier) with status chips (WP-32)
- [x] Price-trend sparkline per supplier item (from `supplier_item_prices`) (WP-33)
- [x] Manual invoice entry form (`source = 'manual'`) — the vision-outage fallback (WP-34)
- [x] Web CI job: lint + typecheck + build; total CI stays under 5 minutes (WP-35)
- **Done when:** every number on the screen traces to the photo beside it; an amber field can be
  fixed and confirmed in the browser; with the Anthropic key revoked, upload + manual entry +
  all screens still work.

### M4 — Loop hardening + rehearsal (Day 13–15) — **LOOP GATE** (demo gate moved to M6, 2026-08-28)
- [x] Seed demo tenant: 1 chain, 3 branches, 2 suppliers with 3 weeks of price history (so the
      live alert fires on stage) - `supabase/demo_seed.sql`, idempotent, doubles as the
      one-command rehearsal reset (WP-40)
- [x] **Review screen deployed and wired** (2026-08-24): `apps/web` live at
      `https://faida-web-nine.vercel.app` (Vercel project `faida-web`, root `apps/web`),
      `API_TOKEN` + `WEB_ORIGIN` on Railway, `NEXT_PUBLIC_MOCK_API=false` with API base and token
      on the web side. Verified against live data: browser QA of list + detail with the photo
      rendering, token auth 401/200, CORS preflight exact-origin, waitlist browser-to-database.
      Demo script steps 11-12 now have a real screen to open
- [x] Curate the 3 demo invoices; run each through the full loop 5× — flakiness is a bug.
      **Done 2026-08-29:** papers in `Docs/demo-invoices/` (pre-verified via the upload
      door), then **15/15 phone runs clean** - 13.3-17.2 s forward-to-reply, every reply
      byte-identical per paper, zero repair rounds, all checks green. Evidence in
      `Docs/DEMO_RUNBOOK.md` §E0. The one incident was a drained Anthropic credit balance
      (ops, now a runbook precondition), not a pipeline flake. **Re-run owed on Flash** after
      the 2026-08-29 engine swap - the gate closes on the shipped engine
- [x] Latency pass: forward → reply under ~20s (stream nothing; the reply is one message) -
      **18.7 s measured on a real forward at prompt v3, 2026-08-28**, no repair round, model time
      6.9-11 s across the corpus; the 5x curated runs below re-verify it per paper
- [x] Failure demo path: forward a meme, get the polite decline (shows discipline, sells
      trust) - **proven live 2026-08-29**, word-perfect in 11.2 s; a video meme also drew the
      unsupported-media reply, a path never before exercised on a phone. Re-run owed on Flash
      with the rehearsals
- [ ] Full rehearsal of the loop portion of the script, twice, on the demo phones
- [x] Duplicate invoice hold: the same paper sent twice is held with a reply naming the first one,
      `DUP-01` (WP-44; shipped 2026-08-28 - same supplier + normalized number + total holds as
      needs_review naming the earlier record; number alone, or date + total, appends a note
      instead; rehearsal consequence written into `Docs/DEMO_RUNBOOK.md`: reset after every run)
- **Done when:** the loop runs end-to-end twice in a row with zero intervention. This gates M5 —
  nothing gets mapped or costed on top of numbers the loop cannot produce flawlessly.

**Demo script (keep to ~5 minutes; the full run rehearses at the M6 gate):**
Act one, the loop — forward invoice → reply appears with price alert → "OK" → open review
screen: photo beside data, all green → sparkline for the item that moved → forward a meme →
polite decline.
Act two, the money — open the materials screen: today's invoice items already sitting under
their raw materials → open the menu screen: every item with its cost and margin at its own menu
price, ranked → point at the popular item that quietly loses money and the sleeper that earns
the most → "push this, fix that."
Close on: "no app, no login, no training — the salesman already knows how to do this, and the
owner finally knows what every plate earns."

---

## 7. Execution plan (contracts, work packages, delegation)

§6 owns *what* each demo-track milestone delivers; this section owns *how* the work is decomposed
and delegated. The build runs as a manager + sub-agent model: the session manager pins the
contracts, delegates one work package (WP) per sub-agent, integrates the results, and is the only
writer of this file. M5+ gets its own WP decomposition at the M4 retro, not before.

### 7.1 Founder track (human-only)

Agents cannot create Meta apps or collect invoices. Two clocks govern the schedule: this track,
and the accuracy loop (WP-16). Everything else is predictable engineering.

| ID | Task | Time | Unblocks |
|---|---|---|---|
| F1-F4 | ~~Meta app + demo phones, deploy, prove M0 on a real phone~~ **all done 2026-08-23**. F2 2026-08-22, F3 2026-08-23, F1+F4 2026-08-23 (see M0 §6 and the Progress Log) | done | end-to-end reality for everything |
| F5 | ~~Anthropic API key with billing enabled~~ done 2026-08-23, verified live | ~10 min | running extraction (WP-16); building it needs nothing |
| F6 | Corpus growth: photograph the invoices in hand (flat + angled + crumpled variants of each); keep collecting toward 20-25 real ones from pilot contacts. **Deliberately collect both VAT-inclusive and VAT-exclusive invoices** - the first invoice through was inclusive and broke C4 (WP-17), so a corpus of one kind would hide the other. **No longer blocks M1** (2026-08-23): the generated set carries phase 1 while these are collected, ~1-2 weeks out | ongoing, not blocking | phase 2 of the §5 corpus; re-scoring WP-16 |
| F7 | Pilot logistics: pick the target chain; ask the central-purchasing question (§11) before any onboarding talk; schedule the demo only after the **M6** gate passes (amended 2026-08-28: the demo closes on the menu-margin screen). New founder input this creates: one real menu with recipes and selling prices, so M6 has something true to cost | ongoing | M6 |
| F8 | Hand-verify every ground-truth file the labeling agent produces. Truth no human checked is not truth. **Tooling ready 2026-08-25**: `Docs/f8-review.html` (built by `Docs/build_f8_review.py`) puts each invoice photo beside the key and marks the **134 values of 680 that were decided rather than copied** - the other 546 are either proven by arithmetic or copied verbatim from a printed column, so the review is a few dozen judgements, not 680 comparisons. Plain-English brief for the task: `Docs/f8-signoff-plan.html` | ~30 min | eval validity |

### 7.2 Pinned contracts (C1-C7)

Frozen before parallel delegation. A contract change goes through the manager and the Decision
Log; a sub-agent never changes one unilaterally.

- **C1 - Status machines.** `documents.status`: received → processing → extracted | failed
  (worker-owned). `invoices.status`: draft → awaiting_confirm → confirmed | needs_review
  (confirm-flow-owned). `extracted` means a draft invoice with checks exists; `failed` only after
  the repair round also fails or the image is unreadable. Memes: document `failed` with the
  classification recorded, polite decline sent, no invoice row.
- **C2 - Job kinds.** `process_wa_message` (ingest + immediate "Got it" ack) enqueues
  `extract_document` (payload `{document_id}`), which runs the pipeline and sends the parsed
  summary as a second message.
- **C3 - Extraction schema + provider.** One strict Pydantic schema (`Decimal` money) shared by
  provider, validation, persistence, and eval ground truth: supplier block, invoice_no, date,
  currency, payment_kind, lines (raw_name, qty, unit, pack_size, unit_price, line_total),
  subtotal, tax, total, `discount_total`, `rounding_amount`, `tax_treatment`
  (inclusive / exclusive / null) and `vat_rate`, plus a per-line `line_kind`
  (stock_item / charge), plus a
  top-level classification (invoice / z_report / other). `tax_treatment` and `vat_rate` are
  *printed facts* - most GCC invoices state "prices inclusive of VAT" or "VAT 5%" - and are read
  like any other field. They are a **tie-breaker only**: the treatment is derived arithmetically
  per C4, never taken on the document's word (§5 layer 5, derived not self-reported).
  **Dates (amended 2026-08-28, WP-27):** the model copies the printed date verbatim into
  `invoice_date_text` ("5/7/26", "9 July 2026", "٥/٧/٢٠٢٦"); `extraction/dates.py` derives the
  calendar date from it deterministically - GCC dates are day-first (09/07/2026 is 9 July;
  the swapped reading is used only when it is the sole valid one), and **an ambiguous date
  stays null rather than being guessed** ("5/7" with no year is not a date - it becomes a
  WP-25 question). A printing the rules do not recognize falls back to the model's own
  reading; an ambiguous one does not, because the model's answer for "5/7" was a guess too.
  Same split as the currency word and the payment terms. One
  structured vision call classifies and extracts together. Provider protocol:
  `extract(image, mime)` and `repair(image, mime, targets)`; model id + prompt version recorded
  on every run.
- **C4 - Money + tolerances.** `Decimal` in Python, `numeric` in Postgres, never float. Line
  check: |qty × unit_price - line_total| ≤ max(0.05, 0.5% of line_total).
  **Document check - two identities, because GCC invoices come both ways** (amended 2026-08-23,
  see the Decision Log). With L = Σ line_totals, S = printed subtotal, T = tax, G = total:
  with D = discount and R = rounding, and A = L - D + R (the lines once the invoice's own
  adjustments are applied): *exclusive* (lines net) holds when |A + T - G| ≤ 0.10; *inclusive*
  (lines gross) holds when |A - G| ≤ 0.10 **and** T > 0, confirmed against a rate r in the
  GCC table (UAE 5%, KSA 15%, Bahrain 10%, Oman 5%, Qatar 0%, Kuwait 0%). Exactly one holds →
  that is the treatment, and the totals are green. Neither holds → amber and the totals question.
  Both hold → only reachable when T ≈ 0, where the distinction does not matter.
  **Anchor on L, never on S.** An inclusive invoice that prints S as the *net* figure satisfies
  S + T ≈ G and masquerades as exclusive; the line sum is the only total we verify independently
  (qty × unit_price per line), so it is the arbiter.
  **Money is stored exactly as printed.** `subtotal`/`tax`/`total` are what the photo shows, with
  the resolved `tax_treatment` and `vat_rate` recorded beside them; net is derived where
  analytics need it. Storing a normalized figure would break the §3 rule that every number on the
  screen traces to the photo next to it.
  **Price memory is net-canonical.** `supplier_items.last_price`, `prev_price` and
  `supplier_item_prices` store the *ex-VAT* unit price, converted once inside the existing
  confirm transaction; `invoice_lines.unit_price` keeps the as-printed value for display. This is
  not tidiness: `PRICE_ALERT_MIN_PCT` is 5% and UAE VAT is 5%, so mixing bases makes a supplier
  changing invoice format fire a full-threshold price alert when nothing moved - the demo's money
  moment lying in the one moment it asks to be trusted.
  **Discounts and charges (WP-18).** A trade discount is quoted against the goods, so the printed
  subtotal is compared to the *stock* line sum (before or after discount - invoices print it both
  ways) and charge lines sit outside it. Charge lines never become supplier items: the catalog is
  stock, and a catalog full of delivery fees makes price alerts fire on cool-box hire. The
  discount reaches price memory pro rata over the stock lines, because a supplier who holds list
  prices and quietly stops discounting has raised your cost, and storing the list price would
  draw a flat line through exactly that.
  Constants live in one module; the eval scores against the same constants.
- **C5 - Confirmation resolution (no new table).** An inbound text from phone P resolves against
  the newest `awaiting_confirm` invoice whose document traces back to sender P. None pending →
  onboarding reply. Several pending → numbered list; a bare "OK" then asks which. Derived from
  existing tables until real usage demands more.
- **C6 - Web API surface.** `GET /api/invoices` (branch/supplier/status filters),
  `GET /api/invoices/{id}` (fields, checks, confidence, signed image URL),
  `PATCH /api/invoices/{id}/fields`, `POST /api/invoices/{id}/confirm`, `POST /api/documents`
  (manual upload), `GET /api/supplier-items/{id}/prices`. Demo access: one shared-secret bearer
  token from an env var; real auth is M7. Pinned now so web work can start against a mock.
- **C7 - Migrations.** Each WP appends its own numbered SQL file; the manager squashes
  periodically (§4 policy). No two parallel agents touch the same migration file.
- **C8 - Provenance: every stored number says how it got there** (added 2026-08-28, see the
  Decision Log). `invoices.confidence` says whether a value survived the arithmetic; C8 says where
  it came from, which is a different question and the one nothing could answer. Shape:
  `invoices.provenance`, a flat jsonb keyed by field path (`total`, `lines.3.qty`), each carrying
  `origin`, `actor` and `at` (`faida_api/provenance.py`). Origins: `extracted` (the model read it
  off the image), `repaired` (re-read in the scoped round), `corrected_chat`, `corrected_screen`,
  `reconstructed` (never on the page - a person supplied it, WP-26), `manual` (typed wholesale,
  WP-34). Flat keys because every write is a merge over a subset of fields.
  **Derived, not self-reported, exactly like confidence.** The repair round is attributed by
  diffing the invoice before and after the merge - a scoped re-read of three cells routinely hands
  two back unchanged, and only the one that moved was re-read to any effect.
  **The two sets that matter downstream** are `READ_ORIGINS` (a camera saw it, the arithmetic could
  check it) and `ASSERTED_ORIGINS` (a person said so). Neither is worse - `reconstructed` is
  precisely what WP-26 asks for - but only one is checkable against the photo, and that is what C9
  propagates. The vocabulary is partitioned by a test, so an origin added later cannot fall through
  both sets.
  **Actors are free text until M7.** `whatsapp:<phone>` from chat, `console` from the review
  screen. Deliberately *not* taken from a client header: a name anyone holding the shared token can
  choose looks like identity without being it, which is worse than admitting we do not know yet.
  When Supabase Auth lands the string becomes a user id and nothing else changes.
  **The audit trail is the other half.** `audit_events` (tenant, actor, action, subject, detail)
  records *human decisions*; `extraction_runs` records *model runs*. Neither duplicates the other,
  and together they answer "who did this". Confirmations, corrections and hand-entry write their
  event **inside the same transaction as the thing they record**, so a confirmed invoice with no
  note of who confirmed it is unreachable rather than merely unlikely.
  **One honest limit.** A correction has no confirm-style retry guard - re-applying identical edits
  is harmless - so a job that retries after a failed send writes a second `invoice.corrected` row.
  The inbound WhatsApp message id rides on the event, which makes those two rows visibly one
  retried message rather than two decisions. A dedupe guard would be new machinery for a duplicated
  line in a log; the failure that matters (a confirmation with nobody's name on it) is unreachable,
  because those writes share the transaction.
  C8 also settles WP-26's open question: a bare `OK` must not confirm away a missing total, because
  a null total is invisible to everything downstream while a reconstructed one is labelled. The
  totals conversation itself is still WP-26's to build.
- **C9 - A derived number is never greener than its worst input** (added 2026-08-28). From M5 the
  figures a user reads are derived - cost per base unit, plate cost, margin - and no photograph
  shows them. Every derivation therefore carries the quality of its inputs: if a plate's cost leans
  on a pack size that would not parse, or a total assembled from a WhatsApp conversation, the plate
  reads **estimated**, never verified, and names the ingredient that dragged it down.
  This widens M6's existing rule from *missing* to *shaky*: "an item with one uncosted ingredient
  reads incomplete" already covers the absent input; C9 covers the present-but-unverifiable one.
  `provenance.asserted_fields()` is the read a derivation makes. Deliberately written before the
  first derived number exists, because the alternative is discovering it when a margin screen shows
  a confident figure built on a guess - the old platform's dominant failure, in a new place.

### 7.3 Work packages

Sizes: S ≤ half an agent-day, M ≈ one, L = multi-day or iterative. Acceptance must be
demonstrable, not documentary.

**M1 (extraction + eval)**

| WP | What | Size | Depends | Acceptance |
|---|---|---|---|---|
| 10 | Extraction schema + provider interface + Anthropic implementation (`extraction/`): structured outputs, usage (tokens, cost, latency) captured | M | C3 | corpus ground truth round-trips the schema; the SDK is imported nowhere outside `extraction/` |
| 11 | Deterministic validation (`validate.py`): C4 checks, green/amber derivation (snapping hook stubbed until WP-22) | S/M | C3, C4 | pure functions, no I/O; rounding-edge unit tests; a wrong value can never be green |
| 12 | Targeted repair (`repair.py`): scoped targets from failed checks, one round max, merge + re-validate | S | 10, 11 | merge semantics + round cap proven; passing fields untouched |
| 13 | Pipeline + persistence: `extract_document` job, status transitions, draft invoices + lines + checks, run metadata, failure + meme paths | M/L | 10-12 | e2e vs real Postgres with mocked provider; idempotent under job retry |
| 14 | Eval harness (`eval/`): scoring per §5, results JSON, CI smoke on 3 recorded fixtures | M | C3 | `python -m eval.run` green on fixtures; alignment scorer unit-tested (extra / missing / reordered lines) |
| 15 | Ground truth for the current corpus: agent transcribes, founder verifies (F8); 3 become the CI fixtures. **Unblocked 2026-08-23** - `eval/convert_generated.py` already emits C3 `truth.json` for all 15 generated cases; what remains is F8 sign-off and re-running it over the real invoices in phase 2 | S | 14 | founder sign-off on every file |
| 16 | Accuracy loop: live eval → inspect failures → one change per round → re-eval, until §5 targets hold. **Unblocked 2026-08-23** - runs on the generated corpus now, re-runs on the real one in phase 2. Needs `--live` mode in `eval/run.py`, which does not exist yet | L | 13-15, F5 | the eval report, not opinion |
| 17 | ~~**VAT treatment, inclusive + exclusive**~~ **done 2026-08-23** (C3/C4 as amended 2026-08-23): both identities in `validate.py` anchored on the line sum, GCC rate table in `constants.py`, `tax_treatment` + `vat_rate` through schema → persistence → eval ground truth (migration 0006), net-canonical price memory converted inside the confirm transaction, and no totals question when a treatment resolves. **Not blocked on the corpus** - deterministic money math with a real invoice already in hand, so it runs in parallel with F6 | M | C3, C4 | Deira T-0084417 (inclusive, UAE 5%) reconciles green with no question; an exclusive invoice still reconciles green; an inclusive invoice printing a *net* subtotal is not misread as exclusive; a supplier switching format produces **no** price alert |

| 18 | ~~**Discounts and non-stock charges break C4 the same way VAT did.**~~ **done 2026-08-23**. Found by running the generated fixtures through the amended validator: `EDGE-01` reads perfectly and still fails, because the line sum misses the trade discount exactly (834.00 - 41.70 + 25.00 delivery + 40.87 tax = 858.17, but C3 models only subtotal/tax/total). Trade discounts are routine in GCC food supply, so this fails correct invoices into amber. Needs a C3 decision like the VAT one, not a prompt tweak | M | C3, C4 | `EDGE-01` reconciles green; a discounted invoice's price memory records the *post-discount* unit price, since that is what was paid |
| 19 | ~~**Line-completeness guard**~~ **done 2026-08-28** (ported 2026-08-24 from the old platform's post-mortem, whose dominant real failure was a perfect header with 2 of 34 lines from an 8k output ceiling): a short read is a *failure*, not an amber - `stop_reason='max_tokens'` raises in the provider even when the cut-off JSON parses, for extract and repair alike, and the flow persists nothing. The "rows the model reports seeing" comparison is **foreclosed by the schema ceiling** (Decision Log 2026-08-28: the wire budget has room for zero new fields), and the budget proof is measured rather than asserted: `PH-01`, the 34-line corpus worst case, spends 2,638 of the 16,000 output tokens at v3, adaptive thinking included | S | 13 | `PH-01` extracts all 34 lines live; a simulated truncated response fails loudly instead of persisting a partial invoice whose header still reconciles |

**M2 (confirm flow, supplier memory, alerts)**

| WP | What | Size | Depends | Acceptance |
|---|---|---|---|---|
| 20 | Reply composer (`replies.py`): English templates for summary, alerts, amber questions, cash hold, failure, decline | S/M | 13 | pure functions, every message shape unit-tested, zero generation |
| 21 | Confirm/correction flow: C5 routing; "OK", "line 4 qty 16", numbered answers; corrections re-validate and re-reply | M/L | C5, 13, 20 | e2e: confirm; correct-then-confirm; OK with nothing pending; two-pending disambiguation |
| 22 | Supplier memory (`matching.py`): alias match, fuzzy snap (single tunable threshold), on-confirm item create + price update + history append | M | schema | messy real corpus names snap correctly; history append idempotent per invoice |
| 23 | Price alerts per the §6 M2 rule (thresholds as constants in one module) | S | 20, 22 | alert shows in the extraction reply; baseline untouched until confirm |
| 24 | Cash hold: `payment_kind = 'cash'` → `needs_review` + reply notes approval pending | S | 13, 20 | e2e test |
| 25 | ~~**Required-field ambers**~~ **done 2026-08-28** (ported 2026-08-24; observed live the same day when AAF 2214 stored with no date and the reply asked nothing): a null invoice date or invoice number becomes one amber question in the reply, exactly like a failed line, answered through the WP-21 correction path (`date 5/7/26`, `invoice no 4471`). The required-field questions rank above the line questions so they can never overflow to the review screen. Never silently stored | S | 20, 21 | e2e: an invoice with no readable date is asked for it; the answer lands via the correction grammar and the invoice proceeds |
| 26 | ~~**Totals block absent from the page: reconstruct it by asking, not by computing**~~ **done 2026-08-28** (founder call 2026-08-25, from a live forward; the open question below settled by a second founder call 2026-08-28). Artisan Bakehouse ABL-INV-260709-0517 arrived with its totals block outside the frame. Every line read green and summed to 930.00, and the reply said so honestly - "total unreadable, what does it say?" - but it also offered "or OK to confirm the rest", the founder answered `ok`, and the invoice is recorded with a **null total**: nothing for M8's purchases figure, nothing for any cost per gram M5 derives. Shipped as a short conversation, not a calculation: with no total the reply shows the line sum and asks whether that is the whole invoice and whether the prices already carry VAT - the two facts C4 normally derives from the arithmetic and cannot derive with no total to derive them against. **A bare `OK` no longer confirms a null-total invoice** (the settled question: a missing line qty is a small hole, a missing total is the headline number) - it gets the question again, from chat and from the screen alike, and the `total is not null` guard sits in the one confirm write. The answer lands through the correction grammar (`total 710.25 inc vat 5%`, `total 710.25 no vat`; "inc vat" with no rate asks for the rate rather than picking one) and is stamped C8 origin `reconstructed`, never `extracted` - while a total the sender reads off the page stays an ordinary `corrected_chat`. The C4 treatment now travels with every correction, without which a total supplied after the fact would leave a stale `tax_treatment` beside it and store a gross price under a net baseline | M | 20, 21, C4 | a totals-less invoice reaches a stored total through the reply conversation; the stored figure is marked as reconstructed, not as printed; a bare OK does not silently record a null total |
| 27 | ~~**Date formats beyond ISO, and a question when the date is missed**~~ **done 2026-08-28** (founder call 2026-08-25). Al Aweer AAF 2214 came back with `invoice_date` null **while the date was plainly printed on the page** - so this is a reading failure, not an absent field. The cause is almost certainly format: **all ten corpus invoices print `YYYY-MM-DD`** (verified 2026-08-25), which is the one format a GCC supplier is least likely to use, so the eval's 100% date accuracy measures a single shape and proves nothing about `09/07/2026`, `9-7-26`, `09.07.2026` or a written month. Same blind-spot shape as `pack_size` at 19%: the corpus agreed with itself. Shipped as the C3 date amendment (see the contract and the Decision Log): the model copies the printed date into `invoice_date_text`, `extraction/dates.py` derives the calendar date day-first in code, `5/7` with no year stays null and asks (WP-25), and the read date renders in the reply ("dated 5 Jul 2026") so a wrong derivation is challengeable from chat. `AMD-01` (the 5/7/26 carbon bill) is promoted into the corpus awaiting its image; the CI smoke's `01_perfect` now carries its date as printed text only, so the smoke fails if the derivation stops running | M | C3, 25 | the eval carries non-ISO date cases and scores them; an unambiguous `09/07/2026` reads correctly; `5/7` with no year stays null and asks; a null date always produces a question |
| 28 | **Foreign-currency hold** (founder call 2026-08-28, from the live USD forward). Levant Specialty Foods FZCO billed in USD and the confirm recorded 75.00 / 65.00 / 35.00 into `supplier_items.last_price`, a bare number with no currency dimension, on an AED tenant. Harmless while a supplier always bills one currency; poison for M5's cost per gram and any purchases roll-up. Shipped as a hold, not a schema: `extraction/currency.py` compares the derived ISO code with `tenants.currency`, a mismatch adds its own question to the reply (the WP-25 shape) so a misread currency is correctable from chat with `currency AED`, confirming is still allowed because the invoice itself is real, and `record_confirmed_prices` returns before the catalog - no item, no observation, no baseline move - with the ack saying plainly that it did. Price alerts are suppressed on the same test: subtracting an AED baseline from a USD price is the demo's money moment lying. **Deliberately not built:** a currency column on `supplier_item_prices` (plan.md §2 rule 8 - no customer has asked for multi-currency price history, and the hold is reversible without migration pain) | S/M | 20, 21, 22 | a USD invoice on an AED tenant is asked about, confirms, and leaves `supplier_items` and `supplier_item_prices` untouched; an AED invoice replies byte-identically to before; the M2 gate test passes untouched |
| 29 | ~~**Bilingual supplier and item names must match**~~ **done 2026-08-29** (from the live 2026-08-28 eval: HW-04's bilingual letterhead came back as both scripts joined). GCC suppliers print bilingual letterheads, and the model copies both scripts joined on some runs and one script on others - the run-to-run variance the pipeline exists to absorb, not a prompt to tighten. The joined "Dairy House Foodstuff LLC / بيت الألبان..." scored **0.595** against the stored English name, below the 0.85 supplier bar, so the supplier missed, nothing snapped, no alert fired, and confirm created a **duplicate supplier** under the joined name - the catalog splits and the demo's money moment goes silent. The same `_similarity` serves `snap_item`, so bilingual and Arabic-only line items (AR-01 prints them joined, HW-04 Arabic-only) carried the identical risk. Fixed deterministically in `matching.py` alone: scoring is **script-aware** - the English half is compared to the English half and the Arabic to the Arabic, and the best is taken - so a joined name matches a single-script catalog entry on the half they share (0.595 -> 1.00; the Arabic-only and joined item reads -> 1.00). Gated on one side being single-script, so two suppliers cannot cross-match on shared Arabic legal boilerplate ("... للمواد الغذائية ذ.م.م", held at 0.76). **Extraction, the prompt, the schema and the F8 ground truth are untouched** - the answer key still records names exactly as printed, in whichever scripts the page carries. **Deliberately not built:** an English-only extraction rule (a prompt fighting model variance, §5, and it breaks the signed F8 truth) or a reject-if-Arabic gate (turns away a real GCC invoice and reverses the §3 language decision) - both weighed and declined; the pure script-flip with no shared characters stays a `name_aliases` job, as designed | S | 22 | the joined bilingual letterhead matches the stored English supplier; the same item read joined on one invoice and Arabic-only on another snaps to one catalog row; two suppliers sharing only Arabic boilerplate stay apart; the confirm flow creates no duplicate supplier from a joined name |

**M3 (review screen)**

| WP | What | Size | Depends | Acceptance |
|---|---|---|---|---|
| 30 | Backend API per C6 + signed URLs + shared-secret auth + CORS | M | M2 data | e2e: patch an amber field, confirm, status flips; unauthorized rejected |
| 31 | Next.js scaffold (App Router, TypeScript, Tailwind, Vercel) + the review screen | L | C6 (mock until 30 lands) | §3 money-display rules hold; amber/green carry an icon or label, never colour alone |
| 32 | Invoice list + status chips + filters | S/M | 31 | |
| 33 | Price-trend sparkline per supplier item | S | 30 | |
| 34 | Manual entry + upload fallback (`source = 'upload' / 'manual'`) | M | 30 | revoked-key drill: with no Anthropic key, upload + manual entry + every screen still work |
| 35 | Web CI job (lint + typecheck + build) | S | 31 | total CI stays under 5 minutes |

**M4 (loop gate)**

| WP | What | Size |
|---|---|---|
| 40 | Demo seed script: 1 chain, 3 branches, 2 suppliers, 3 weeks of price history; idempotent, targets the real project | S/M |
| 41 | Hardening: per-stage latency logs (webhook, download, extract, repair, reply); forward → reply under ~20 s; each demo invoice through the loop 5×; every flake fixed, never retried around | M |
| 42 | Meme decline path, word-perfect | S |
| 43 | Demo runbook with reset steps between rehearsals; founder rehearses twice (F7) | S |
| 44 | ~~**Duplicate invoice hold**~~ **done 2026-08-28** (ported 2026-08-24): normalize the invoice number (lowercase, strip non-alphanumerics - `matching.normalize_invoice_no`); same supplier + number + total against an existing invoice holds the new one as needs_review with a reply naming the earlier record; number alone, or date + total, appends a note instead of holding (a second same-day delivery is real). Same-supplier means matched ids when both rows have one, else equal normalized names, so an uncataloged supplier can still send the same paper twice. The hold outranks the cash hold; alerts and questions on a copy are noise. No new tables | S |

**M5 (raw materials)** — decomposed 2026-08-29, the breakdown §7.3 deferred to the M4 retro.
Revised the same day after `/plan-eng-review` and a Codex outside voice: 13 findings, all resolved by founder call, three of which changed the shape of the milestone rather than its details (see the Decision Log).

Read the whole block as one rule: **M5 is the first milestone whose output no photograph shows.**
Every earlier number sat beside its image and a human could catch it.
A cost per gram is two divisions away from the page, and by M6 it is folded four sums deep into a plate margin, so a wrong one is not visible anywhere - which is why every row below either refuses to guess or labels what it assumed.

```
  invoice line ──┬─ unit_price ──── ex-VAT ── post-discount ──┐
   (has a photo) │   (arithmetic cross-checks this:            ├─► cost per base unit
                 │    qty × unit_price = line_total)           │    (stored on the line,
                 └─ pack size ───────────────────────────────┘     numeric(18,8), frozen)
                     ▲ NOTHING cross-checks this. It is in no          │
                     │ arithmetic identity. 25kg read as 2.5kg          │
                     │ survives every check we have.                    │
                     └── which is why no cost ever reads "verified"     │
                                                                        │
   supplier_items.ingredient_id  ──────────────────────────────────────┤
    (human-approved, reversible)                                        │
                                                                        ▼
                                          material price per kilo = the newest
                                          costed line among the packs mapped
                                          RIGHT NOW  (derived, never stored)
```

| WP | What | Size | Depends | Acceptance |
|---|---|---|---|---|
| 50 | **Confirming and recording prices must be one transaction.** Found by the outside voice, verified in the code: `db._confirm` commits (db.py:717), then `record_confirmed_prices` opens a *second* transaction (api.py:351, confirm.py:492/535). If the second throws, the invoice is confirmed with no price memory - and retrying from the review screen falls to api.py:344 and raises **409 "invoice is confirmed; cannot confirm"**, permanently. This predates M5 and M5 makes it far likelier, because M5 puts a pile of new arithmetic inside that second step and the thing then lost is a cost with no photo beside it. The fix is a merge, not a repair path (§2 rule 5): status flip, audit row, catalog write, price move and cost in **one** transaction behind one method both doors call. **Deliberately not built:** a heal/retry endpoint, which is the recovery subsystem §2 rule 5 bans | M | - | a forced failure inside price recording leaves the invoice **awaiting_confirm** with no catalog or price rows, and a retry succeeds; the M2 gate test and every existing `record_confirmed_prices` test pass untouched |
| 51 | **A multi-pack pack size must not read as one pack, and a pack of nothing is not a pack.** `units.parse("48x400ml")` returns **400 ml** today, silently dropping the 48 - the carton holds 19,200 ml, so any cost built on it is 48x too high, and that exact pack sits in `supabase/demo_seed.sql` at AED 90.00. The multiplier forms GCC food supply prints (`48x400ml`, `24 x 1L`, `12*500g`) are read deterministically in `extraction/units.py` - the one dictionary the catalog and the eval both ask - because `48 x 400 ml` is arithmetic printed on the page, not a guess about what is inside a box. A zero or negative quantity now returns None: `parse("0kg")` currently yields a real pack of base quantity 0, which divides. Anything nested or unrecognized stays **unparseable** rather than becoming a wrong number. **Deliberately not built:** any inference about a container's contents (that is WP-55's human sentence, and `units.py` refuses it by design) | S | - | `48x400ml` → 19,200 ml, `24x1L` → 24,000 ml, `0kg` → None; `2.5kg` and `6 ctn` unchanged; the whole M0-M4 suite and `python -m eval.run --smoke` stay green - `matching.snap_item`'s pack veto reads this same dictionary, so a token change here can split a catalog item in two |
| 52 | **`ingredients` + the mapping approval, with a reverse gear.** `ingredients` (tenant, name, base unit) as the culinary concept, and `supplier_items.ingredient_id` as the many-packs-to-one-material link (PRD §17-18). `matching.py` **proposes** and never decides. Four actions, each writing **one `audit_events` row inside its own transaction** (C8): approve, reject, **remap** and **unmap**. The last two are not optional polish - a wrong merge is this milestone's stated worst case ("corrupts the cost of every menu item using that material… no photo to check it against"), and an approval gate with no reverse gear leaves a consultant asking an engineer. **Approve creates the material when none exists**, from the pack's cleaned name: the matcher can only propose against materials that exist, and a fresh tenant has none. One Raw Materials screen, two sections - unmapped packs **ranked by money spent**, and mapped materials with their price - cloning the review screen's propose-then-confirm shape. A rejected pair is not re-proposed, derived from `audit_events` with **latest event wins** (so reject-then-approve reads correctly), served by the 0011 subject index. Cross-tenant mapping is refused by **Postgres, not by a code path**: `unique (tenant_id, id)` on ingredients plus a composite FK. An approval whose pack dimension contradicts the material's base unit is refused, never coerced. **Deliberately not built:** auto-merge at any confidence, a WhatsApp mapping grammar, a mapping-state table (it would record approved-ness in two places - the 0010 duplication), and an English/Arabic translation table (WP-29's reasoning holds) | L | 51 | Gulf Foods' and Al Madina's milk powder map to one material; one audit row per approve, reject, remap and unmap, each naming its actor; nothing merges without a keystroke; a wrong merge is undone on the same screen and every price above it corrects itself; a rejected candidate does not reappear, but re-approving it works; a 400 ml pack onto a gram material is refused with a reason; a supplier item cannot be mapped to another tenant's material |
| 53 | **Cost per base unit - derived, traceable, and honest about what nothing checked.** `unit_price ÷ pack size` → AED per gram / millilitre / piece, **ex-VAT and post-discount by reusing the two factors `record_confirmed_prices` already computes per line** (one implementation, not a second), `Decimal` throughout, written per confirmed invoice line inside WP-50's transaction so every cost drills back to a photo. **Precision is a stated rule, not "full":** `numeric(18,8)`, `ROUND_HALF_UP`, quantized once at the division, displayed per kilo at two decimals - flour at AED 43.50 per 25 kg is 0.00174 AED/g, which `numeric(12,3)` would round to 0.002, a 15% error nobody would notice. Pack resolution order: printed `pack_size`, else a pack printed **inside `raw_name`** (`units.first_printed`, which `snap_item` already trusts - TH-01 prints "RICE BASM 5KG" with no pack column), else the line's `unit` when it is itself a measure, else unparseable → WP-55. The stock-line query must **fetch `position`** and key provenance on it: that loop skips charge lines, so its counter is not the line's position on the invoice and C9 would read the wrong line's history. **No cost ever reads "verified".** The arithmetic proves `qty × unit_price = line_total`, so the unit price is corroborated - but **pack size appears in no identity at all**, so a 25kg read as 2.5kg passes every check we have and would carry a green badge on a ten-times-wrong number. Costs read *estimated* when a person supplied an input, and *reliable with limitations* otherwise, naming the pack size as the unchecked one (PRD §24's own vocabulary). C9's asserted-input set mirrors the real data dependency: this line's `unit_price` and `pack_size`, plus `total`/`tax` on a VAT-inclusive invoice, plus `discount_total` **and every stock line's `line_total`** when the invoice discounts - the discount is allocated pro rata from the stock-line sum, so a corrected line taints its neighbours. **Deliberately not built:** moving-average costing (PRD §19 chose latest price), corroborating pack sizes across invoices (the natural upgrade once price history exists - logged), a costing engine or policy table, and any cost on an unconfirmed invoice | M/L | 50, 51 | a 2.5 kg sack at AED 50.50 reads AED 20.20/kg; VAT-inclusive yields ex-VAT and discounted yields post-discount; flour reads 0.00174, not 0.002; a cost resting on a reconstructed total reads *estimated* and names the line; no cost reads *verified*; an invoice with a delivery charge as line 1 labels its stock lines correctly; a zero pack yields no cost and does not throw; `EDGE-01`'s negative return line costs correctly |
| 54 | **One material, one price per kilo - derived, never stored.** The material's price is **the newest costed line among the packs mapped to it right now**, ordered by **printed invoice date** with confirm time only as a tie-breaker (PRD §19 - the most recent *purchase*, so a stack of old invoices handed over during onboarding cannot overwrite this month's real cost). Latest, not cheapest and not averaged. **No `ingredient_costs` table:** the fact lives on the invoice lines, and a stored projection would need refreshing on confirm, approve, reject-reversal, remap, unmap and pack-size override - six triggers to get exhaustively right, and the first draft of this plan already missed the main one (supplier items are created *during* confirm with no material attached, so a cost written only at confirm time had nothing to attach to and approval recomputed nothing). Deriving it deletes the category of bug, makes the mapping undo in WP-52 free, and the answer carries the **invoice line id** it came from - a more precise thing for M6 to name than a row in a summary table. The screen shows the price per kilo with its supplier, its purchase date, its quality label and the photo behind it. **Deliberately not built:** per-branch cost (§2 rule 8 - it waits for a chain that shows different branch prices, and deriving makes that a `where` clause rather than a migration), provisional cost before an invoice (PRD §19, post-MVP), any recipe or menu concept (M6) | M | 52, 53 | **the milestone's Done when:** milk powder bought from two suppliers in three pack sizes reads as one material at one price per kilo, and every figure inside that price drills to the invoice photo behind it; confirming a newer invoice from either supplier moves that price; confirming an *older* one does not; unmapping a wrongly-merged pack corrects the price immediately |
| 55 | **A cost that cannot be computed is an issue on a screen, and a human clears it once.** Any line that cannot be costed appears with **its own reason** - unparseable pack size, a pack printed as a bare container, missing unit price, missing quantity, a zero pack, or the foreign-currency hold - and blocks that material's price rather than guessing (PRD §24). The list is **derived from the data, not a new `issues` table**: PRD §24's first-class-record subsystem is post-MVP and C5's "derived until real usage demands more" is the standing precedent. Clearing it is the same slice, because an issue with no resolution is half a feature: a consultant sets a **pack-size override** on the supplier item ("1 carton = 10 kg chicken"), `audit_events` is its version history, and the rule for old lines is stated rather than implied - **an override costs the lines that have no cost yet and never rewrites a line already costed**, inside the override's own transaction. A cost built on a human's conversion is *estimated* by C9, automatically. **Deliberately not built:** a `container_conversions` table (audit_events already records who said what and when), a severity/impact/status taxonomy, an issue inbox, and yield conversions (10 kg raw → 8.5 kg cooked is a recipe fact, M6) | M | 53, 54 | a carton line with no parseable pack yields no cost, appears with its reason and its invoice line, and blocks its material's price; each other blocker shows its own reason; entering "1 carton = 10 kg" clears it and costs that line but leaves already-costed lines byte-identical; the resulting cost reads *estimated* |

Whole-milestone **out of scope**, restating §2 rule 8 where M5 is most tempted to drift: no recipes or
menu costing (M6), no inventory ledger or theoretical consumption (deferred beyond MVP), no auth or
RLS (M7), no sales (M8), no broker or ORM, no business logic in SQL functions, and no new scope
without a customer quote naming who asked.
Two things the outside voice raised and we deliberately did not adopt: **per-line VAT rates** (real,
but inherited from C4's invoice-level model which already governs price memory - a contract change,
logged in `TODOS.md`, not an M5 decision) and **freezing each line's material mapping** (freezing
would make WP-52's undo preserve errors instead of correcting them; a remap is a correction, and the
audit log records every one).
The Meta production chain in the M5 checklist is founder track (F-track), not agent work.

### 7.4 Delegation waves

```
Wave 0  (manager)  pin C1-C7 in one small change      | founder: F1-F4 sitting
Wave 1  WP-10 + WP-11 + WP-14 in parallel             | founder: F5, F6
Wave 2  WP-12 + WP-15
Wave 3  WP-13, then WP-16 accuracy loop (needs F5+F6)
Wave 4  WP-20 + WP-22, then WP-21 + WP-23 + WP-24     (overlaps WP-16: product code does not wait on prompt tuning)
Wave 5  WP-30 + WP-31, then WP-32-35                  (web starts against the C6 mock)
Wave 6  WP-40-43 → M4 loop gate                       | founder: F7 loop rehearsals
Wave 7  ~~WP-17 VAT treatment~~ done 2026-08-23
Wave 8  WP-50 ∥ WP-51, then WP-52 → WP-53 → WP-54 → WP-55   → M5 raw materials
Wave 9  M6 work packages (decomposed at the M5 close)       → M6 DEMO GATE → demo
```

| Lane | Work package | Modules touched | Depends on |
|---|---|---|---|
| A | WP-50 atomic confirm | `faida_api/db.py`, `api.py`, `confirm.py` | - |
| A | WP-52 ingredients + mapping + screen | `db.py`, `api.py`, `matching.py`, `supabase/migrations/`, `apps/web/` | 51 |
| A | WP-53 cost per base unit + C9 | `costing.py` (new), `db.py`, `api.py`, `apps/web/` | 50, 51 |
| A | WP-54 material price, derived | `db.py`, `api.py`, `apps/web/` | 52, 53 |
| A | WP-55 blocked costs + override | `db.py`, `api.py`, `apps/web/` | 53, 54 |
| B | WP-51 pack-size arithmetic | `faida_api/extraction/units.py` | - |

**Launch A (WP-50) and B (WP-51) in parallel worktrees; merge B before WP-53 starts.**
They are the only pair that can run at once, and only because they share no file: B is the pack
dictionary, A is the confirm transaction.
Everything after is serial on purpose, and all of it lands in `db.py`, `api.py` and `apps/web/` -
lanes that split there would spend more effort merging than they save.
The order is not preference: WP-53 divides by WP-51's answer inside WP-50's transaction, WP-54 reads
WP-53's costs through WP-52's mapping, and WP-55 is the escape hatch for the lines WP-53 refuses to
cost. A wrong number early is inherited by everything above it rather than caught beside a photo.

### 7.5 Delegation protocol

Every sub-agent brief contains: the WP goal and acceptance from §7.3; the contracts it must not
change (a needed change escalates to the manager); the file scope (touching files outside it is a
bug); "run `pytest` and `ruff check . && ruff format --check .` before returning, and report the
real output"; and what NOT to build, quoting §2.

Manager rules: parallel agents with overlapping code run in isolated worktrees and the manager
integrates; schema changes follow C7; only the manager edits this file, in the same commit as the
integrated change; every milestone close re-runs the previous milestone's gate test (a regression
on the demo path is a P0).

---

## 8. Milestones — completing the demo, then the MVP (M5–M11)

Sequenced so each milestone ships something a pilot customer uses that week. Re-estimate at M4.

**M5 and M6 are demo track** (founder call 2026-08-28, second amendment of the day — see the
Decision Log): the demo bar is the complete end-to-end MVP chain, closing on a menu-wise margin
per item, so the demo gate sits at the end of M6, not M4. M7 onward is post-demo.

**Resequenced 2026-08-28** (founder call — see the Decision Log). The track now runs
**raw materials → costing → auth → sales**, where it previously ran sales → auth → costing. The
MVP's stated job is: photograph a receipt, harmonize its items into raw materials, cost a menu
item from them. Costing a plate needs no sales data at all — a menu price is a fact the owner
tells us in a sentence. Sales volume says which items to care about *most*; it is not an input to
the cost. Old → new: **M5 sales → M8**, **M6 auth → M7**, **M7 recipes → split into M5 (raw
materials) + M6 (costing)**, **M8 → M9**, **M9 → M10**, **M10 → M11**. The M0–M4 loop is
untouched. Milestone names are identifiers in code comments too ("real auth is M6"), so every
forward-looking reference in `apps/api`, `apps/web`, the migrations and the READMEs was renumbered
in the same commit; the two logs below keep the numbers they were written with.

**What this ordering costs, plainly.** Purchases ÷ net sales — the first ratio — slips from week
4 to week 10, and the dashboards behind it from week 10 to week 12. Two of those four weeks are
new work, not padding: the old M7 was sized at two weeks on the assumption that the raw-material
layer already existed, and it does not — the catalog built by M2 is scoped to one supplier and
knows nothing about ingredients. The Meta production chain, which is external, serial and slow,
still starts in M5 so the daily brief does not slip with the rest. **And the demo-bar amendment
costs on top:** the demo itself now waits for M5+M6 — roughly weeks 4–7 instead of week 3. That
is the deliberate trade: a demo of the loop alone sells trust in the data; a demo that ends on
"push this item, fix that one" sells the product.

### M5 — Raw materials: one shelf per ingredient (Week 4–5)
Extraction fills a catalog scoped to a single supplier: Al Madina's milk powder and Gulf Foods'
milk powder are two unrelated rows with two separate price histories, and nothing in the schema
represents "milk powder" as a thing you cook with. Costing cannot start until something does.
The mechanical half of this already exists and is tested — `extraction/units.py` reduces any
printed pack to a base quantity ("2kg" and "2000g" are provably one shelf, "6 ctn" and "6 pc"
deliberately are not), and `matching.py` snaps messy printed names — so this is a layer above
them, not a rewrite of them.
- [x] **Provenance and the audit spine first** (C8, done 2026-08-28, migration 0011): every stored
      number records how it got there, and every human decision lands one `audit_events` row inside
      the transaction that made it. Done before the mapping screen rather than after it, because
      the first thing this milestone builds is an approval and there was nowhere to record one —
      `audit_events` had been scheduled for M7, two milestones after its first use
- [x] **Pack arithmetic reads what the page says** (WP-51, done 2026-08-29): a multiplier pack
      ("48x400ml", "24 x 1L", "12*500g", "6×2kg") reduces to the whole carton, a nested chain
      ("2x3x4kg") is refused entirely rather than half-read, and a zero quantity is no longer a
      pack. Fixed in `extraction/units.py`, the one dictionary the catalog, the eval and costing
      all ask, so all three got the same answer at once. Second effect, deliberate and pinned by a
      test: a carton line no longer snaps onto a single-tin catalog row, where it used to compare
      AED 90 against AED 2.10
- [x] **Confirming and recording prices are one transaction** (WP-50, done 2026-08-29, found by the
      eng review's outside voice). They were two, and the gap was unrecoverable: if price recording
      threw, the invoice read confirmed with nothing recorded and the screen's confirm answered 409
      for ever. Merged rather than healed (§2 rule 5): `_confirm` now carries the status flip, the
      audit row and the price baseline on one connection, and `record_confirmed_prices` takes an
      optional `conn` so it can either join a caller's transaction or open its own. The test has
      teeth - reverting the one line makes it fail with `'confirmed' == 'awaiting_confirm'`
- [x] `ingredients` (tenant, name, base unit): the culinary concept, kept separate from the
      purchasable pack, exactly as PRD §17–18 specifies (WP-52, done 2026-08-29, migration 0012).
      `category` dropped until something reads it
- [x] `supplier_items.ingredient_id`: many packs from many suppliers → one raw material. The
      existing fuzzy matcher **proposes**, a human approves, and the approval is recorded with its
      actor — one `audit_events` row per merge and per rejection (C8, in place). **Never
      auto-merged.** A wrong merge quietly corrupts the cost of every menu item
      using that material, and unlike a bad extraction there is no photo to check it against.
      Cross-tenant mapping is refused by Postgres (composite FK), not by a code path — proven by
      driving the raw `update` and watching it raise
- [x] **Unmap and remap, the reverse gear.** An approval gate whose worst case has no undo leaves a
      consultant asking an engineer. Both write their audit row, and because the price is derived,
      unmapping corrects every figure above it instantly
- [x] Mapping screen: unmapped supplier items ranked by money spent, approve or reject one
      keystroke each — the same propose-then-confirm shape as the invoice review screen, so
      nothing new is invented for it. **Approve creates the material when none exists** (the matcher
      can only propose against materials that already exist; a fresh tenant has none). Live at
      `/materials`; proposals are **pack-blind** where snapping is pack-sensitive, so a 2.5 kg sack
      and a 500 g pouch from two suppliers propose as one material
- [x] **Cost per base unit, derived and traceable** (WP-53, done 2026-08-29, migration 0013):
      `unit_price ÷ parsed pack size` → AED per gram / millilitre / piece, ex-VAT per C4's
      net-canonical rule, recorded per confirmed invoice line so every cost drills back to a
      photo. `pack_size` reads 99% *on generated invoices* (phase 1), which is what makes this
      arithmetic rather than guesswork. `numeric(18,8)`, `ROUND_HALF_UP`, displayed per kilo.
      The two C4 factors are reused rather than recomputed, and the rounding happens once at the
      division: quantizing to fils first would put flour at 0.002 instead of 0.00174, which a
      test now pins against the real column
- [x] Container conversions, consultant-entered and versioned ("1 carton = 10 kg chicken")
      (WP-55, done 2026-08-29, migration 0014). `units.py` deliberately refuses to guess what is
      inside a carton, so a human says once. `audit_events` is the version history; an override
      costs the lines that have no cost yet and never rewrites one already costed. Kept in its own
      column, not written over `pack_size`: one is what a page printed and the other is what a
      person asserted, and only the second makes a cost read *estimated*. Saying how much is in
      one also says what it is measured in, so the approval gate stops asking
- [x] An unparseable pack size is an **issue on a screen** (PRD §24), never a guessed number: it
      blocks that material's cost and says which invoice line it came from — **and so does every
      other reason a line cannot be costed** (missing unit price or quantity, a bare container, a
      zero pack, the foreign-currency hold), each with its own reason (WP-55, done 2026-08-29).
      Derived from the invoice lines with no `issues` table, grouped by product so a carton bought
      twelve times is one question, and a box to type in only where a conversion can actually
      answer it
- [x] **C9 applied to the first derived number** (WP-53, done 2026-08-29): a cost per base unit
      inherits the quality of the invoice line under it, so one built on a reconstructed total or a
      corrected quantity reads *estimated* and names the line that made it so —
      `provenance.asserted_fields()` is the read. **No cost reads *verified***: the arithmetic
      corroborates the unit price but **pack size sits in no identity at all**, so a 25kg read as
      2.5kg passes every check we have. Costs read *estimated* or *reliable with limitations*
      (PRD §24's vocabulary), never green. The input set is computed from the arithmetic rather
      than listed, so an exclusive invoice's cost is untouched by a reconstructed total while a
      discounted invoice's costs all taint each other
- [x] **One material, one price per kilo — derived, not stored** (WP-54, done 2026-08-29, no
      migration and none needed). The newest costed line among the packs mapped right now, by
      **printed invoice date** (PRD §19's "most recent purchase", so an onboarding stack of old
      invoices cannot overwrite this month's cost), confirm time only as a tie-breaker, an undated
      invoice falling back to its confirm date read in UTC. No `ingredient_costs` table: a stored
      projection needs six refresh triggers and the first draft of this plan already missed the
      main one. Per-branch cost still waits for a chain that shows different branch prices (§2
      rule 8) — and deriving makes that a `where` clause rather than a migration. One query
      (`db.list_mapped_pack_costs`) returns each pack's own newest cost with the material's winner
      first, so the screen shows the comparison the merge exists to make
- [x] **Prerequisite, not optional: WP-19 closes first** - **all three closed 2026-08-28**
      (WP-19 shipped in commit 4f3ef2c, WP-26 and WP-28 the same day; box ticked 2026-08-29 after
      verifying the guard in the code rather than in this file). A short read that drops a line, a
      null total confirmed away by a bare OK, or a USD price sitting in an AED baseline all make a
      material look cheaper than it is - and once it is a cost per gram, nothing downstream can
      tell. The truncation guard is live on **both** providers, which is what actually matters
      after the 2026-08-29 model swap: Gemini raises on any `finish_reason` but `STOP`, Anthropic
      on `stop_reason='max_tokens'`, each of them even when the cut-off JSON happens to parse
- [ ] **Start the Meta production chain now (external, slow):** legal entity docs → Meta Business
      verification → WABA → purchased verified sender → submit daily-brief template in the
      **utility** category. Track status here: `[ ] entity  [ ] verification  [ ] WABA  [ ] sender  [ ] template`
- **Done when:** milk powder bought from two suppliers in three pack sizes reads as one material
  at one price per kilo, and every figure inside that price drills to the invoice photo behind it.

### M6 — Recipes and menu costing (Week 6–7) — **DEMO GATE**
The layer the landing page already sells: *"when an ingredient's price climbs, every item using it
earns less."* Done-for-you onboarding per PRD §16 — the customer never touches a recipe form.
This milestone ends in the demo: the §6 script's act two runs on a real menu (F7 supplies it),
with margins ranked and one clear "push this, fix that" moment.
- [ ] `menu_items` (tenant, name, selling price + price history). The selling price is something
      the owner says out loud — **no POS and no sales feed is needed to cost a plate**
- [ ] `recipes` / `recipe_components`: ingredient, quantity, unit, with **batch yields as the
      norm** ("one pot → 40 cups"), not the exception (PRD §16)
- [ ] Versioned recipes and conversions; every cost result names the recipe version and cost
      snapshot behind it, so "why did this change?" is answerable (PRD §8, §23)
- [ ] Deterministic cost: plate cost = Σ (component qty converted to base units × ingredient cost
      per base unit) ÷ batch yield, packaging as a component. `Decimal` throughout, never float (C4)
- [ ] **Margin per item at its menu price:** cost, margin in AED, margin %, and what is missing.
      Never labelled "food cost %". An item with one uncosted ingredient reads *incomplete* — it
      must never read as a cheap item
- [ ] **The money screen:** when a raw material's price moves, which menu items just lost margin
      and by how much. This is the M2 price alert finally carried through to the plate
- [ ] Internal batch loader: CSV in + a review grid, the consultant recorded as the actor;
      recipe templates applied across branches with per-branch overrides (PRD §16)
- [ ] Coverage by **item count** here; coverage by **sales value** — the number that tells a
      consultant what to cost first — needs sales and arrives in M8
- **Done when:** one real menu loads in under a day of consultant time; every costed item shows
  its cost, its margin at its own menu price, and the invoice photo behind each ingredient in it;
  and confirming one supplier invoice at a new price visibly moves the items that use it.
  **Demo gate:** the full §6 script — loop, mapping, menu margins, "push this, fix that" — runs
  end-to-end twice in a row with zero intervention, on the demo phones and a real menu.

### M7 — Auth, tenancy enforcement, approvals (Week 8–9)
The demo ran seeded and single-tenant; a pilot cannot.
- [ ] Supabase Auth; three roles: tenant / brand / branch (PRD §4) — memberships + branch access
- [ ] RLS policies on all tenant-owned tables; the API takes tenant scope from the authenticated
      context, never from the client
- [ ] **Worker-side tenant enforcement:** Supabase's service role bypasses RLS, and every invoice
      flows through the worker — so every job carries tenant_id + branch scope and **fails closed**
      without them. Acceptance test: a job built with Tenant A's context against Tenant B's row is
      rejected. This is the one security test that matters most.
- [ ] Cash-purchase approval: branch raises → tenant approves with reason → audit event
      (actor, approver, reason, before/after) — the PRD's one non-negotiable approval gate (§21)
- [ ] `audit_events` **extended**, not created: the table and its confirm/correct/hand-entry and
      M5 mapping-approval writes have existed since 2026-08-28 (C8). M7 adds the events only it can
      have — cash approval, price change, role change — swaps the free-text actor for a real user
      id, and brings the table under the same RLS policies as everything else
- **Done when:** two seeded tenants cannot see each other's data through API, storage URL, or
  worker path; a cash invoice cannot post without an approval record.

### M8 — Sales ingestion + the first ratio (Week 10–11)
Cost is now known per item; sales says which items and which branches it matters on.
- [ ] CSV/Excel sales upload (branch, date, net sales) with a reusable column mapping; layout
      change stops for review, never silently shifts columns (PRD §10)
- [ ] Z-report photo via WhatsApp → same extraction pipeline, `z_report` document type,
      summary-level only — **never turned into fake receipts** (PRD §10)
- [ ] `sales_daily` table (tenant, branch, business_date, net_sales, source, granularity)
- [ ] First analytic on the dashboard: **purchases ÷ net sales (cash basis)** per branch per
      period, ranked, with a completeness/freshness label on every row. Never labelled
      "food cost %" — it isn't one.
- [ ] **Recipe coverage by sales value** ("complete costing covers 78% of sales value"), which
      M6 could not compute: it is the consultant's priority queue for what to cost next
- **Done when:** a week of real sales + real invoices for one branch renders a ranked branch table
  where every purchase number drills down to an invoice photo.

### M9 — Contribution, signals, dashboards (Week 12–13)
Costing exists from M6; this milestone is what sales adds on top of it.
- [ ] Item contribution = net item sales − ingredient cost − packaging (deterministic, versioned
      calculation runs with lineage back to invoices + recipe versions — PRD §23)
- [ ] Branch contribution estimate — **never labelled net profit**
- [ ] Deterministic signals: popular-low-margin items, supplier price spikes, branch gaps (PRD §25.3)
- [ ] Owner dashboard: yesterday's sales, branch league (backed by the real costing from M6),
      top/bottom items, pending approvals, data freshness; branch dashboard: my sales, invoices
      to confirm
- [ ] Every headline carries its §24-style quality status (verified / estimated / incomplete)
- **Done when:** an owner can answer "which item and which branch is hurting me" from one screen,
  and every number traces to source.

### M10 — Daily WhatsApp brief (gated on Meta approval from M5)
- [ ] Deterministic template filler: net sales, est. food-cost %, biggest price move, one flagged
      issue (PRD §27.4) — fixed sentence shapes, number slots, no generation
- [ ] Send via approved utility template outside the 24-h window; tap-through opens the dashboard
- **Done when:** the owner's phone receives a real brief at 7am with yesterday's real numbers.

### M11 — Pilot hardening → first paying chain
- [ ] 2-week live pilot on one real branch: invoices arrive unprompted (≥3 on days we sent nothing)
- [ ] Error budget: every `failed` document reviewed weekly; top failure mode fixed each week
- [ ] Pricing conversation with real value numbers from the pilot
- **MVP is done when:** PRD §31's checklist holds — and one chain pays money, not a letter of intent.

**Deferred beyond MVP** (revisit only with a customer asking): full inventory ledger, theoretical
consumption, stock counts and variance, goods receipts as a separate flow, POS API connector,
multi-brand layer, item-level menu engineering as self-serve, moving-average costing.

---

## 9. Testing strategy

| Layer | What | Gate |
|---|---|---|
| Eval harness | Real-invoice corpus, ground truth, scored per §5 | Accuracy targets before M4; no regression after |
| E2E (few, real) | Webhook→extract→confirm→record; duplicate send; meme decline; provider-outage fallback; (M7+) cross-tenant worker rejection | Green in CI on every PR |
| Unit | Deterministic money math, reconciliation, snapping, template filler | Cheap and thorough — this is where determinism pays |
| Manual, on a phone | The full demo script | Before every demo and every milestone close |

Banned: tests that assert on code text, tests of framework behavior, coverage targets for their
own sake.

## 10. Costs (demo through pilot)

Supabase free tier → $25/mo; Railway/Fly ~$5–10/mo; Vercel free; WhatsApp in-window replies free,
test number free; extraction ≈ $0.05–0.15/invoice (Opus 5, incl. repair pass) → a 75-branch chain
at ~10 invoices/branch/day is ~$40–110/day at scale pricing — fine at AED 99/branch, trivial at
pilot volume. Meta utility template cost applies only from M10 (verify live UAE rate then).

## 11. Risks

| Risk | Mitigation |
|---|---|
| Meta/WABA production chain is slow, external, serial | Start it at M5, track in this file; demo runs on the free test number meanwhile |
| Real invoices are worse than the eval corpus (handwriting, mixed language) | Grow the corpus from every pilot failure; the repair pass + amber-question flow degrades gracefully instead of silently |
| Invoice forwarding doesn't become a habit (the behavioral risk) | Pilot gate in M11 measures *unprompted* forwards; if the habit doesn't form, that's a product finding to face, not to engineer around |
| Central purchasing at target chains (no per-branch invoices) | First question asked of any pilot chain, before onboarding them |
| Scope creep back toward the old build | §2 rules; anything not in a milestone needs a customer quote and a Decision Log entry |
| Founder track stalls (Meta setup, corpus) while agents sprint ahead | F1-F4 scheduled as one sitting now; F6 corpus growth checked at every milestone close |
| Parallel agents drift on interfaces | C-contracts (§7.2) pinned before fan-out; contract changes are manager-only, through the Decision Log |
| Accuracy loop burns days on a too-small corpus | Targets phase in as the corpus grows; every failure joins the corpus; escalate to the founder if it is under 15 invoices when WP-16 starts |
| CI eval fixtures silently diverge from live behaviour | Recorded fixtures regenerated on every prompt-version bump, checked each WP-16 round |

## 12. Decision Log

| Date | Decision | Why |
|---|---|---|
| 2026-08-29 | **A material's price per kilo is derived from the costed invoice lines of the packs mapped to it, never stored; the planned `ingredient_costs` table is dropped** (M5, WP-54) | Founder call on the eng review's outside voice, which found the shape of the plan broken rather than a detail wrong: supplier items are created *during* confirm with no material attached, and mapping happens on the screen afterwards - so a price written only at confirm time had nothing to attach to, and the approval that finally created the material recomputed nothing. WP-53's own "done when" could not happen. The stored form needs refreshing on six separate events (confirm, approve, reject-reversal, remap, unmap, pack-size override) and the first draft of the plan already missed the main one; a derived answer has no refresh rules to get wrong. It also deletes two further findings for free - a remap no longer needs lineage frozen, and a pack-size override no longer needs a projection rebuilt - and makes the mapping undo below almost free, since unmapping a pack corrects every figure above it with nothing left to rebuild. The answer carries the **invoice line id** it came from, which is a more precise thing for M6 to name as its cost snapshot than a row in a summary table. Cost accepted: it contradicts PRD §29's `inventory_cost_snapshots` wording and M6 reads a query rather than a row; at pilot volume, with the two indexes WP-52 adds, that is cheap. Same reasoning as migration 0010, which deleted a duplicated `confirmed` state "kept in sync only by application code" |
| 2026-08-29 | **No cost per base unit ever reads "verified"; costs read *estimated* or *reliable with limitations* (PRD §24's vocabulary)** (C9 amended, M5 WP-53) | Founder call, on the sharpest thing the outside voice said. C4's arithmetic proves `qty × unit_price = line_total`, so the unit price is cross-checked by two other numbers on the page - but **`pack_size` appears in no identity at all**. Nothing corroborates it, ever. A supplier prints 25kg, the model reads 2.5kg, every check still passes, and the cost is ten times too high wearing a green badge. `provenance.asserted_fields()` separates model-read from human-asserted, which is not the same question as right from wrong, and C9's wording had quietly conflated them. The fix costs one word and stops the product claiming something no arithmetic can support - the old platform's dominant failure ("a confidently wrong value was never offered for review") reappearing in the layer C9 was pinned to protect. **Considered and deferred:** earning *verified* by corroborating a pack size across two invoices from the same supplier, which is real evidence and sits in data we already keep - but it reads unverified until a second invoice arrives, so it is the upgrade once there is price history to lean on, not the thing to build first |
| 2026-08-29 | **Confirming an invoice and recording its prices become one transaction** (M5 WP-50) | Found by the outside voice, verified in the code: `db._confirm` commits (db.py:717), then `record_confirmed_prices` opens a second transaction (api.py:351, confirm.py:492/535). A throw in the second leaves the invoice confirmed with no price memory, and a retry from the review screen falls to api.py:344 and raises 409 "invoice is confirmed; cannot confirm" - permanently, with no path back. It predates M5, and M5 makes it materially likelier by putting a pile of new arithmetic inside that second step, where the thing then lost is a cost with no photo beside it. Fixed as a merge rather than a repair endpoint, because a heal path is the recovery subsystem §2 rule 5 bans: status flip, audit row, catalog write, price move and cost commit together behind one method both doors call - the same "one door" shape corrections already use. Accepted cost: it restructures shipped demo-path code during the milestone whose hard constraint is not regressing it, guarded by the ten existing DB tests over that function and the M2 gate test |
| 2026-08-29 | **"Latest purchase price" means the printed invoice date, with confirm time only as a tie-breaker** (M5 WP-54; reverses the same day's earlier call for confirm time) | The eng review first chose confirm time, for consistency with the shipped `supplier_items.last_price_at = now()` and because sorting by printed date looked like it would freeze the price on stage - the corpus invoices are dated 2026-07-02..08 while `demo_seed.sql` stages baselines at `now() - 7 days`. That reasoning was wrong and the outside voice caught it: **neither seed file inserts a single invoice or invoice line**, the price is fed by confirmed lines, and with none staged the first demo invoice sets the price under either rule. There was no demo consequence to protect. With that gone, PRD §19's plain reading wins: an owner handing over a stack of last month's invoices during onboarding must not have them overwrite this month's real cost, silently, in the layer where nothing downstream can notice. A null invoice date falls back to confirm time |
| 2026-08-29 | **Gemini 3 Flash (`gemini-3-flash-preview`) becomes the shipped extraction model; Claude Opus 5 stays wired as the fallback behind `EXTRACTION_PROVIDER`** | Founder call, on the same day's measured bake-off (ten generated invoices, prompt v3 shared verbatim, single runs): Flash scored 100% on every field except the known bilingual-letterhead join (supplier_name 80%, the same run-to-run variance shape all three models show), got right both cells that tripped Gemini 3.1 Pro (the TH-01 subtotal and the pack sizes embedded in item names), reconciled 10/10 with zero repair rounds, at ~$0.0065/invoice (a tenth of Opus, a quarter of 3.1 Pro) and 9.5 s average / 13.9 s worst model time - the first configuration in which every corpus case fits the ~20 s forward-to-reply target (Opus's PH-01 alone reads for 22.9 s). The risk accepted, stated plainly: one run of a generated corpus, phase 2's real photos are precisely where a small model would be expected to fall first, and the repair path has never fired on Gemini because nothing failed - so the swap is built to be reversible in one env var with no deploy, the Opus recordings stay in git history, and the bake-off re-runs on the phase-2 corpus before the pilot leans on the numbers. §5 accuracy targets unchanged and still gate; §10 costs move down |
| 2026-08-29 | **Bilingual invoices are matched by script-aware scoring in `matching.py`, not by constraining extraction to English or rejecting Arabic; the §3 language decision holds** (WP-29) | The 2026-08-28 eval returned HW-04's bilingual letterhead as both scripts joined - legitimate, since a retry read it clean, so it is run variance the pipeline must absorb. The joined "Dairy House Foodstuff LLC / بيت الألبان..." scored 0.595 against the stored English name, under the 0.85 bar: the supplier missed and confirm minted a duplicate supplier row, splitting the catalog and silencing the price alert. Two routes were weighed and declined. Extracting English-only is a prompt instruction set against model variance - exactly what §5's "accuracy is a pipeline property, not a prompt property" forbids - and it would break the founder-signed F8 ground truth, where AR-01's and HW-04's item names are Arabic and joined by design. Rejecting fully-Arabic invoices turns away a real GCC supplier's paper at the trust moment and reverses the §3 decision that invoices stay mixed-language while extraction handles both - a founder-owned call, and one that would not even fix HW-04 (its supplier line is English). The fix instead compares each script to its own and takes the best, so whichever half the model returns carries the match; it is gated on one side being single-script so shared Arabic legal boilerplate ("... للمواد الغذائية ذ.م.م") cannot cross-match two different suppliers (held at 0.76, under the 0.85 bar). Deliberately not built: an English-Arabic translation table (over-engineering; the pure script-flip with no shared characters stays a `name_aliases` job) and an English-preferred display name on the screen (presentation only, deferred until asked). One file, one function, no extraction/schema/ground-truth change |
| 2026-08-28 | **WP-19 is amended: truncation is detected from the provider's stop reason alone; the self-reported row count is foreclosed** | The original brief asked to also compare the extracted line count with a count the model reports seeing - which is one more C3 field, and the ceiling A/B measured this same day found room for exactly zero more. stop_reason='max_tokens' is the transport's own ground truth for truncation and cannot disagree with itself, the guard raises even when the cut-off JSON happens to parse (the old platform's exact failure), and reconciliation still catches any partial read the transport misses. The budget half is proven by measurement: PH-01's 34 lines spend 2,638 of 16,000 output tokens at v3 with adaptive thinking on |
| 2026-08-28 | **A bare "OK" may not confirm an invoice whose total is null** (WP-26, settling the open question the work package carried since 2026-08-25) | Founder call, in their own words: "a missing line qty is a small hole; a missing total is the invoice's headline number, and M5 will divide it into plate costs where no photo can catch it." The reply that caused it was honest and still wrong: it said "total unreadable" and then offered "or OK to confirm the rest", so one word recorded an invoice that contributes nothing to any total-based figure and looks complete from every screen. The rule is about the invoice, not the door: chat re-asks the question instead of confirming, the review screen's confirm returns 409 with the reason, and `total is not null` sits in the single confirm write so a third path written later cannot reopen it. What replaces the OK is a short conversation, never a calculation - the reply shows the line sum (the one figure the per-line arithmetic already proved) and asks the two facts C4 derives from a total and cannot derive without one: is that the whole invoice, and do the printed prices already include VAT. A total assembled from those answers is stamped C8 `reconstructed`; a total the sender reads off the page stays `corrected_chat`. The distinction is the point: from M5 a cost per gram built on the first must read *estimated* (C9), and nothing but the origin can tell them apart four sums downstream |
| 2026-08-28 | **An invoice whose currency differs from the tenant's is held and asked about, and a confirmed foreign-currency invoice never moves price memory** (WP-28) | Founder call, after the live USD forward the same day: Levant Specialty Foods FZCO billed in USD and the confirm wrote 75.00 / 65.00 / 35.00 into `supplier_items.last_price`, which is a bare number with no currency beside it, on an AED tenant. Harmless while that supplier always bills in USD - alerts compare a supplier against its own history - and poison the moment M5 divides those numbers into a cost per gram or M8 adds them into a purchases figure, because nothing downstream can see that three of the numbers are a different kind of money. The hold is deliberately cheap: the reply asks (so a misread currency word is correctable from chat with `currency AED`), the invoice still confirms and still stores exactly as printed, and `record_confirmed_prices` simply returns before the catalog, with the ack saying so rather than promising to watch prices it dropped. Price alerts are suppressed on the same test, because subtracting an AED baseline from a USD price is the demo's money moment lying in the one moment it asks to be trusted. **Recording the currency per price row was considered and deferred** (§2 rule 8): no customer has asked for multi-currency price history, the column would need a backfill decision for every existing row, and a hold is reversible later without migration pain - where a half-built multi-currency baseline is not |
| 2026-08-28 | **The demo bar is the complete end-to-end MVP chain, and the demo gate moves from M4 to the end of M6** | Founder call, in their own words: "we are not ready for the demo until we have the complete end-to-end MVP" - (1) an extraction layer with the exact invoice data, (2) extracted supplier nomenclature mapped to inventory raw materials, (3) raw materials tagged as ingredients of a menu, (4) the menu costed - so "the restaurant will be able to find a menu-wise profit margin, so that he can prioritize what to push and what not to push. That is the main functionality which you want to show in the demo." This completes the morning's resequencing rather than reversing it: M5 (raw materials) and M6 (menu costing) were already first in line; they now sit inside the demo boundary instead of after it. M4 keeps every hardening item and becomes the *loop* gate - the loop must run flawlessly twice before anything is mapped or costed on top of its numbers, because a wrong number that enters a plate cost cannot be seen next to its photo any more. Cost stated plainly: the demo waits for M5+M6, roughly weeks 4-7 instead of week 3. The trade bought: a demo of the loop alone sells trust in the data; a demo that ends on "push this item, fix that one" sells the product. New founder dependency created: one real menu with recipes and selling prices (F7) - without it M6 has nothing true to cost |
| 2026-08-28 | **The invoice date is read from the printed text by rule (`extraction/dates.py`), day-first, and an ambiguous date stays null; C3 gains `invoice_date_text`** (WP-27, with WP-25's required-field asks) | Al Aweer AAF 2214 read null with the date plainly printed, and the corpus could not see it: all ten generated invoices print `YYYY-MM-DD`, so the 100% date score measured one shape. The model now copies the date exactly as printed and the rules live in testable code: GCC dates are day-first (09/07/2026 is 9 July; the swapped reading only when it is the sole valid calendar date), written months in English and Arabic resolve, Arabic-Indic digits translate, and "5/7" with no year stays null and becomes a question - in the reply (WP-25) and in chat ("date 5/7" gets the year question, not the generic clarify). The read date renders in the reply ("dated 5 Jul 2026") so a wrong derivation is challengeable from the phone. Fourth instance of the printed-fact/derivation split: currency, payment terms, units, now dates |
| 2026-08-28 | **The calendar date is absent from the wire schema (`SkipJsonSchema`); `invoice_date_text` is the only date field the model returns** | Adding `invoice_date_text` beside the existing `invoice_date` reproduced the 2026-08-25 failure exactly: `400 Schema is too complex` on every request. An A/B against the live API measured the ceiling precisely - text plus a date field fails *even with the date as a plain string*, text alone compiles, v2 compiles - so the grammar budget fits exactly one date field, and the printed text earns the slot because the calendar date can be derived from it deterministically but not the reverse. `invoice_date` stays on the C3 model for persistence, ground truth and manual entry; it is simply never asked of the model. Consequence accepted: a printing `dates.py` does not recognize resolves to null and is asked for (WP-25), rather than falling back to a model reading that no longer exists on the wire. The schema remains at the ceiling: **the next optional field added to C3 must re-run the schema probe before merge** |
| 2026-08-28 | **C8 (per-field provenance) and C9 (a derived number is never greener than its worst input) are pinned, and the `audit_events` spine moves from M7 to the front of M5** | Founder call, on a design review of the shipped code against the four rules in the agent-native harness pattern (`Docs/harness-design.html`, plain-English version `Docs/harness-explained.html`). Three of the four already held **in code, not in intention**: the review screen's PATCH routes through `confirm._apply_correction`, so a screen edit and a "line 4 qty 16" text are literally the same function; manual entry runs the same `validate_invoice` + `snap_item` and derives the same confidence dump; and the eval's private copy of C4 was deleted on 2026-08-24, leaving one implementation. The fourth did not hold at all, and the half that was missing was the wrong half: `extraction_runs` records the model's every move - model id, prompt version, tokens, latency, repair or not - while nothing recorded a person's, so a total the model read off the page and a total the owner typed into WhatsApp because the paper was out of frame were **the same number in the same column**. Survivable while every figure sits beside its photo; not survivable from M5, where a figure is divided into a cost per base unit and, by M6, folded four sums deep into a plate margin that no photograph shows. The plan was already asking for this in three places with nowhere to put it - WP-26's reconstructed total that "must never look like one read off the page", M5's merge "recorded with its actor", and the audit table itself scheduled two milestones after its first use. Cost of doing it now: one column, one table, ~a day, while the schema is still squashable and the only tenant is seeded. Cost of doing it at M7: a backfill over a real chain's cost history, plus a window in which a bad material merge - which corrupts every cost above it, with no photo to check it against - is untraceable. Deliberately **not** copied from the same picture: a policy engine (our constants module is the shared rule surface), specialised agents per task (C3 keeps classification inside the one extraction call), an audit subsystem (one table, one rule: every write path names its actor), and an approvals workflow (our gate costs one word in a chat, and the customer has no finance team) |
| 2026-08-28 | **C6 extended: the invoice detail payload carries `provenance`** | The screen is where a reconstructed total has to *look* reconstructed (C8's whole point), so the field origins travel with the fields. Same shape as `confidence` beside it; no new endpoint |
| 2026-08-28 | **The post-demo track is resequenced to raw materials (M5) → menu costing (M6) → auth (M7) → sales (M8); the old M7 recipes milestone is split in two and the sales milestone moves from first to fourth** | Founder call, restating the MVP as: photograph a receipt, harmonize the extracted items into raw materials, cost a menu item from them. The plan had sequenced sales first because its post-demo north star was purchases ÷ net sales, and costing sat behind both sales and auth at M7 - about five weeks after the demo gate. Costing a plate needs no sales data: a menu price is a fact the owner tells us, so menu price minus recipe cost is a margin per item that is deliverable with nothing but the invoices already flowing. Sales volume weights which items matter; it is not an input to the number. Two supporting facts: the landing page has led with per-item margin since 2026-08-24 (Decision Log, same date) while the build plan deferred it to M7, and the raw-material layer the founder named **did not exist in the plan at all** - M7 assumed ingredients arriving pre-costed from a consultant spreadsheet, when today's catalog is scoped per supplier (`supplier_items` is unique on supplier + name), so the same material bought from two suppliers is two rows with two price histories and no cost per gram anywhere. The cost of the reorder, stated plainly: purchases ÷ net sales slips from week 4 to week 10 and the dashboards from week 10 to week 12; the Meta production chain still starts in the first post-demo milestone so the daily brief does not slip with them. Milestone names are identifiers in code comments as well as in this file, so the renumbering (M5 sales → M8, M6 auth → M7, M8/M9/M10 → M9/M10/M11) was applied to every forward-looking reference in the same commit; Decision Log and Progress Log entries keep the numbers they were written with |
| 2026-08-25 | **Money crosses the provider boundary as a string, not a JSON number, and the printed form is parsed deterministically (`extraction/money.py`)** | Adding one optional field to C3 made the API reject every request outright: `400 Schema is too complex` / `Grammar compilation timed out`, a hard failure on every invoice rather than a degraded read. Cause found by A/B against the live API: Pydantic renders each `Decimal \| None` as a three-branch union carrying a negative-lookahead regex, and C3 has fourteen of them inside an unbounded array of lines. Declaring one concrete type removed all fourteen lookaheads and 500 characters of grammar. It also closes a real gap - a JSON number is a float on the wire, which C4 bans everywhere else - and the string form invites the printed one, so "AED 332.00", "1,240.50", "(41.70)", the dirham sign's own dot and Arabic-Indic digits are all parsed in one module. Anything with no number in it is rejected loudly rather than read as zero |
| 2026-08-25 | **Cash or credit is derived from the printed terms line by rule (`extraction/payment.py`), not by prompt wording; C3 gains `payment_terms_text`** | Founder call, closing the question escalated 2026-08-24. The field decides which purchases need owner approval (WP-24, PRD §21) and was returning null on invoices a human reads at a glance, because the prompt said "only when the document states cash or credit" and a page printing "Payment terms: 14 days" never prints the word "credit". The model now copies the terms as printed and the rules live in testable code: an explicit cash marker means cash, a due period means credit, printed terms outrank the model's own reading, and anything unrecognized stays null so an unmarked document is never routed around the approval gate. Same split as the printed currency word and its ISO code. `payment_kind` went 60% -> 100% |
| 2026-08-25 | **One units dictionary (`extraction/units.py`) harmonizes pack sizes for the catalog and the eval; a pack size printed inside an item name counts as one** | Founder call. "2 kg", "2000 g", "2.5K" on a receipt too narrow for the second letter and Arabic "كجم" are one pack, and read as several the catalog doubles, price history splits, and the price alert fires on a supplier who changed only their printing - the same failure shape that made price memory net-canonical. The dictionary was private to `matching.py`, so the eval had no way to ask and would have needed a second copy; it now covers mass, volume, count, Arabic units and container words, with containers deliberately their own dimension ("6 ctn" must never equal "6 pc"). `matching.snap_item` already read pack sizes out of item names, so ground truth records them there too, which is what a till receipt printing "RICE BASM 5KG" needs. `pack_size` went 19% -> 99% across this and the printed-page rebuild |
| 2026-08-24 | **The eval's private copy of C4 is deleted; `eval/score.py` scores reconciliation through `faida_api.extraction.validate`** | It was written "so the eval stands alone" and drifted exactly as §2 rule 3 says a second implementation will. Knowing only the exclusive identity, it scored `TH-01` and `EDGE-02` (VAT-inclusive, post-WP-17) and `EDGE-01` (trade discount, post-WP-18) as unreconciled **off hand-verified ground truth** - a ceiling of 11/14 against a §5 gate of 100%, measuring a program we do not ship. Found by running truth through both implementations before trusting either. One implementation of C4, and the eval scores against it |
| 2026-08-24 | **Ground truth for printed fields comes from the printed page (`<CASE>.prompt.txt`), not from the generator's model file** | `expected.json` is the generator's *model* of an invoice - inventory codes, base-unit conversions, unit vocabulary - and `convert_generated.py` had been mapping `pack_quantity` (2000, grams) into C3's `pack_size` (the page prints "2 kg") and `purchase_unit_text` into `unit`, including for `TH-01`, a till receipt with no unit column anywhere on it. Its own docstring had forbidden exactly this from the start. The first live eval scored `pack_size` 19% and `unit` 90% against a >=95% gate with the model having read every one of those cells correctly. `eval/printed.py` now reads the prompt, money and quantities still come from the model file where arithmetic can check them, and every parsed row is cross-checked against the modelled line total so a mis-parse fails the case instead of quietly rewriting truth. Rebuilding truth moved `pack_size` 19% -> 89%, `unit` 90% -> 100%, `raw_name` 92% -> 100%, with no change to the model. **This is agent-written truth and still needs F8 sign-off** |
| 2026-08-24 | **`discount_total` is canonicalized to a magnitude in the C3 schema, not in the prompt** | The first live eval caught the model returning `-41.70` for `EDGE-01`, faithfully copying the sign the invoice prints. C4 states the identity as `line sum - discount + rounding`, so a negative D *adds* the discount, misses by twice it, and fails a perfectly-read invoice into amber - the third instance of the WP-17/WP-18 shape (correct read, wrong convention, spurious amber), and one the repair round cannot reach because the failing check is document-level with no line target. A `field_validator` on the schema fixes it for the pipeline, manual entry and the eval at once, and no prompt rewording can regress it. The prompt never described the field at all, which is the deeper cause and belongs to round 2. Reconciliation went 90% -> 100% |
| 2026-08-24 | **`pack_size` inside an item name, and `payment_kind` inferred from printed terms, are escalated as C3 questions rather than settled in the eval** | Both are the entire remaining gap (`pack_size` 89%, `payment_kind` 60%) and neither is a misread. `TH-01` prints "RICE BASM 5KG" with no pack-size column: the model returns `pack_size` "5KG", truth says none, and the model's reading is arguably the better one - but it changes `matching.py`'s pack-size veto, so it is a product decision. `payment_kind` is the prompt obeying its own instruction ("only when the document states cash or credit"), so "Payment terms: 14 days" and a till receipt both return null; inferring credit and cash from those is what a human reader does and what WP-24's cash hold needs, but it widens a field the approval gate depends on. Per §7.2 a contract question is manager-only, so the eval reports both openly instead of quietly encoding either answer. Neither gates §5, which covers totals, amounts and line-item fields |
| 2026-08-24 | **The old restaurant-profit-platform extraction layer was reviewed read-only and three edge-case ports adopted (WP-19 line-completeness guard, WP-25 required-field ambers, WP-44 duplicate hold); its machinery stays out** | Founder call after a three-explorer survey of the previous build. Its own post-mortem: no run ever completed all 26 stages, extraction failed about one run in three, the dominant failure was a perfect header with 2 of 34 lines from an 8k output ceiling, and a confidently wrong value was never offered for review. The edge-case catalogue is worth keeping; the 7-stage chain, fragment planner, model-reported 0.85 confidence gate, and recovery subsystem are exactly what §2 forbids. Its second synthetic corpus (six Cedar & Spice invoices, one 34 lines over two pages, with 75-line ground truth) is noted as a free phase-1 eval extension; our 15 generated fixtures are the same set it carries |
| 2026-08-24 | **Landing positioning leads with profit margin per item; supplier-price variation demoted to supporting evidence** | Founder call: the main proposition is knowing the margin each item earns, because that is where profit comes from; price moves matter as the thing that eats those margins, not as the headline. Copy uses "item", never "SKU" (no-jargon display rule). The hero's WhatsApp price-alert mock stays as proof of the live loop |
| 2026-08-24 | **C1 amended: `confirmed` leaves the document status vocabulary; the document machine ends at `extracted` (terminal) or `failed`, and the confirm flow touches only the invoice** | A schema review found both tables claiming a `confirmed` state kept in sync only by application code in the two confirm paths - drift waiting for the third path. Since `invoices.document_id` is unique (0008), document confirmation is exactly derivable through its invoice, so the duplicated state carried risk and no information. The C6 detail payload already carries the invoice's `status` and `confirmed_at`; the M3 review screen must read confirmation from those, never from `document.status` |
| 2026-08-24 | **The 1:1 between documents and invoices and the day-one tenancy rule are now DB-enforced** (0008, 0009): unique index on `invoices.document_id`, composite index on `invoice_lines (invoice_id, position)`, and `tenant_id` (not null, FK) on `invoice_lines`, `supplier_item_prices`, `extraction_runs`, derived from the parent row in every insert path | The extraction pipeline's duplicate guard was a check-then-insert read that two of a job's three attempts could both pass, drafting two invoices whose confirms would each move price memory; the code already assumed 1:1 (`get_invoice_by_document` fetches one row). The tenancy rule (§4) had three silent exceptions that would have made M6's RLS policies per-row join subqueries on PostgREST-exposed tables, and adding the column pre-customer is a backfill over seeded data instead of a live migration |
| 2026-08-23 | **The public waitlist is a write-only path through a same-origin Next.js proxy and FastAPI; email addresses are normalized in the backend, deduplicated by Postgres, and new and duplicate signups receive the same response** | The founder explicitly requested a functional public waitlist before the landing page goes live. Browser-held database credentials and a public lookup path would expose signup data or enable address enumeration, while the proxy keeps deployment configuration server-side and RLS with no anonymous policy keeps the table private |
| 2026-08-23 | **The generated hazard set becomes the phase-1 eval corpus; real invoices become phase 2 and stop blocking M1** | Founder call, on evidence this file did not have when the never-synthetic rule was written: the generated images were shown to prospective clients, who said they receive invoices like these. Representative, not merely plausible. Real photos are 1-2 weeks out and the MVP cannot idle that long. The rule it relaxes was right for the reason it gave - generated images only carry hazards someone thought to prompt for - so the mitigation is disclosure, not denial: every phase-1 number is labelled *measured on generated invoices*, the §5 gate is only truly met in phase 2, and the real corpus is expected to move the number down |
| 2026-08-23 | **Gross-canonical price memory considered and rejected; C4 stays net-canonical** | The case for storing the VAT-inclusive price is that a cafeteria owner thinks in what leaves the till, and quoting a figure absent from the receipt in their hand does not get believed. Implemented and reverted on the evidence. Traceability points the other way in practice: 11 of 13 fixture invoices are exclusive or charge no VAT, so their printed price *is* the net one, and grossing them up invents numbers appearing on no document - the M2 gate test caught it immediately, turning `up AED 4.00 (50.50 to 54.50)` into `up AED 4.20 (53.03 to 57.23)`. Net is also the true cost for a VAT-registered business, which any multi-branch chain is, and `up AED 4.00 (50.50 to 54.50)` is written verbatim into `Docs/DEMO_RUNBOOK.md` and staged by `demo_seed.sql`. The cost is that a VAT-inclusive cash-and-carry receipt stores a figure 1/1.05 of its printed price; `tax_treatment` and `vat_rate` are stored per invoice so either basis is derivable |
| 2026-08-23 | **C4 generalized again for trade discounts, rounding and non-stock charges** (WP-18): the identities are stated against `line sum - discount + rounding`; C3 gains `discount_total`, `rounding_amount` and a per-line `line_kind`; charge lines are excluded from the catalog and from the discount base; the discount reaches price memory pro rata | Found by running the generated fixtures through the amended validator rather than by waiting for a real invoice: `EDGE-01` read perfectly and still failed, missing the discount exactly (41.70). Same failure shape as the VAT bug - correct extraction, wrong identity, spurious amber - and trade discounts are routine in GCC food supply. Charges had a second bug hiding behind it: with qty and unit_price present, "Chilled delivery and cool box hire" would have become a supplier item with its own price history |
| 2026-08-23 | **C4 amended to reconcile both VAT-inclusive and VAT-exclusive invoices**, anchored on the line sum; money stored exactly as printed with `tax_treatment` + `vat_rate` beside it; price memory normalized to ex-VAT. C3 gains `tax_treatment` and `vat_rate` as printed facts used only as a tie-breaker | The first real invoice through the live pipeline (Deira Cold Store T-0084417) was VAT-inclusive at UAE 5% and reconciled to the fil - 706.65 / 1.05 = 673.00, and 706.65 - 673.00 = 33.65 exactly matched the printed tax. Extraction was correct; `subtotal + tax = total` was the wrong identity, so correct invoices were going spuriously amber. Storing as printed keeps the §3 photo-traceability rule; net-canonical price memory prevents a 5% VAT basis change from firing the 5% price alert |
| 2026-08-22 | Brand direction selected: Margin Fold mark, Date Palm and Karak Gold palette, and "Profit, in plain sight." positioning line | Connects invoice flow, multi-branch operations, and profit visibility without red, literal currency marks, or generic AI motifs |
| 2026-08-22 | Fresh build; previous restaurant-profit-platform is reference-only, no code carried over | Over-engineering post-mortem; schema *ideas* only |
| 2026-08-22 | Deleted `Docs/DESIGN.md`; this plan is the single sequencing document alongside `Docs/PRD.md` | Founder call |
| 2026-08-22 | Demo-first sequencing (M0–M4) ahead of full MVP phases | WhatsApp accuracy is the wedge and the sale |
| 2026-08-22 | Meta Cloud API direct for the demo; Twilio only as an unblock fallback | Free, production-shaped |
| 2026-08-22 | Inventory ledger / stock counts / goods receipts deferred beyond MVP | Needs recipes + proven data habit first; schema keeps the door open |
| 2026-08-22 | English-only WhatsApp replies + review-screen UI for the demo scope | Smallest surface; invoices stay mixed-language; bilingual revisited with pilot feedback |
| 2026-08-22 | Execution decomposition (founder track, contracts, work packages, delegation protocol) lives in this file as §7; no separate BUILD.md | One live file; this plan stays the single sequencing document |
| 2026-08-22 | Price alerts computed in the extraction reply; `last_price`/`prev_price` update only on confirm | The demo's money moment; unconfirmed invoices must not move the baseline |
| 2026-08-22 | Confirmations resolved by derivation (newest awaiting-confirm per sender), no pending-confirmations table; CI eval smoke = recorded provider responses, live eval on demand | Keep the schema and CI lean until real usage demands more |
| 2026-08-23 | C6 extended: POST /api/invoices/manual - no-AI manual invoice creation running the same deterministic validation + snapping, document source='manual' with classification NULL and status extracted | M3's vision-outage fallback needs a write path; the pipeline invariants (checks, confidence, cash hold) apply identically |
| 2026-08-23 | C6 pinned in implementation: PATCH and confirm return the full updated detail payload; list = {"invoices": [...]}; money serialized as strings, never JSON numbers; confirm also clears needs_review (the review screen is the cash path until M6) | Saves the screen a round trip; float money is banned everywhere |
| 2026-08-22 | C4 document check is line-sum primary (Σ line_totals + tax vs total; extracted subtotal is a cross-check). C3 note: `RepairResult` keeps its dict-keyed patch shape; providers using strict structured outputs translate via private wire models | §5 was always line-sum, and a subtotal must not masquerade as reconciliation. The Anthropic strict-schema transform silently empties open dicts (verified empirically in WP-10) |
| 2026-08-22 | Deny-all RLS (`enable row level security`, zero policies) on all ten public tables, in `0001_init.sql` | Supabase serves the `public` schema over PostgREST, so the anon key would have granted the internet full read/write. Owner role + `service_role` bypass RLS, so the backend is untouched; M6 still owns real tenant policies |

## 13. Progress Log

*(newest first — one line per session: date, what shipped, what's next)*

- 2026-08-29 - **M5 is decomposed into five work packages (WP-50 to WP-54, §7.3) and awaiting founder approval; no feature code written yet.** Baseline in the `m5-raw-materials` worktree is green on the M0-M4 demo path before anything is touched: 393 API tests, 65 eval scorer tests, `eval.run --smoke` OK, ruff clean on both trees.
  **One bug found while reading the ground this milestone stands on, before writing a line of it:** `units.parse("48x400ml")` returns **400 ml**, silently dropping the 48. The carton holds 19,200 ml, so a cost per base unit divided by it would be **48x too high** - and "Evaporated Milk 400ml" with pack_size `48x400ml` is staged in `demo_seed.sql` at AED 90.00, so this is on the demo stage, not hypothetical. Harmless until now (the catalog only ever compared pack strings to each other, and the veto unions the name's token with the pack column's, so nothing mis-snapped) and the first thing that divides by it inherits it. It becomes WP-50, the first slice, ahead of any costing.
  **Two stale boxes corrected against the code, per the "if the plan and the code disagree, the code is right" rule:** WP-19 was recorded as "the last M5 prerequisite open" in the Current-milestone line and left unticked in the M5 checklist, while §7.3, the M1 checklist and the 2026-08-28 log all had it shipped. Verified in the source rather than in this file, and it is live on **both** providers - which is what matters after the model swap: Gemini raises on any `finish_reason` but `STOP`, Anthropic on `stop_reason='max_tokens'`. Every M5 prerequisite is now closed.
  Two judgement calls inside the breakdown that a reader should be able to disagree with: **C9 is folded into the costing slice rather than trailing it**, because a derived number shipped for even one slice without its quality label is the exact failure C9 was pinned to prevent; and the **blocked-cost list is derived from the data rather than given an `issues` table**, following C5's precedent, with PRD §24's first-class-record subsystem left post-MVP.
  **Then `/plan-eng-review` ran with a Codex outside voice, and the breakdown came back materially different: 13 findings, all resolved by founder call, three of which changed the milestone's shape rather than its details.** A scope challenge cut four things first (a duplicate module, a duplicate screen, a `container_conversions` table, and an unread column) on the grounds that each restated a fact already stored. Then eight review findings landed - the ordering key, merge atomicity, the units blast radius, the write-once catalog column, C9's true input set, the stock-loop position bug, the zero-pack division, and two missing indexes. Then Codex found the three that mattered most, and the review had missed all three: **the price per kilo could never be produced at all** (supplier items are created during confirm with no material attached, so mapping later recomputed nothing - the milestone's own done-when was unreachable); **confirm and price-recording are two transactions** with an unrecoverable gap that returns 409 for ever from the screen; and **no cost can honestly read "verified"**, because the arithmetic corroborates the unit price while pack size sits in no identity at all, so a 25kg read as 2.5kg wears a green badge on a ten-times-wrong number.
  **One correction I owe the record:** the review argued for confirm-time ordering partly to protect the demo, and that argument was false - neither seed file inserts any invoice or invoice line, so there was nothing to protect. Codex's phrase, "product behaviour distorted to preserve the demo seed", was fair. Reversed to printed invoice date.
  Net effect: five work packages became six (WP-50 to WP-55), one planned table was deleted rather than added, unmap and remap joined WP-52 as the reverse gear the approval gate lacked, and the quality vocabulary moved to PRD §24's own words. Also written: `TODOS.md` (two deferred findings with their reasoning) and a test plan artifact for `/qa`.
  Founder approved the revised six and building began the same day.
  **WP-51 shipped**: `units.parse("48x400ml")` reads 19,200 ml instead of 400 ml, so the carton staged in `demo_seed.sql` at AED 90.00 can no longer cost out 48x too high. Multiplier forms (`48x400ml`, `24 x 1L`, `12*500g`, `6×2kg`) reduce to the whole pack; a nested chain (`2x3x4kg`) is refused entirely rather than half-read, because "3x4kg" reads 12 kg where the page says 24 and both halves are wrong numbers; a zero quantity is no longer a pack, which matters because the first thing M5 does with a pack size is divide by it inside a transaction that runs after the invoice has already flipped to confirmed.
  Fixed in `extraction/units.py` alone - the one dictionary the catalog, the eval scorer and costing all ask - so all three got the same answer at once, which is the whole reason that module was lifted out of `matching.py` in the first place. The second effect is deliberate and now pinned by a test: a carton line no longer snaps onto a single-tin catalog row, where it used to compare AED 90 against AED 2.10 and fire a nonsense price alert.
  **410 tests green** (was 393; 17 new), eval scorer 65 green, `eval.run --smoke` OK, ruff clean on both trees. No existing test or fixture changed behaviour, so neither predicted regression was real on today's corpus.
  **WP-50 shipped**: confirming an invoice and recording its prices are now one transaction. They were two, and the gap between them was not recoverable - a throw in the second left the invoice reading confirmed with no prices, and the review screen's confirm then answered 409 "invoice is confirmed" for ever, with no way back. `_confirm` now carries the status flip, the audit row and the price baseline on one connection; `record_confirmed_prices` gained an optional `conn` so it either joins a caller's transaction or opens its own, which keeps the retried-ack path and every existing test working unchanged.
  The acceptance test was checked for teeth rather than assumed: reverting the single line that passes the connection makes it fail with `assert 'confirmed' == 'awaiting_confirm'`, which is the bug stated exactly. **411 tests green**, ruff clean.
  **WP-52 shipped**: `ingredients`, `supplier_items.ingredient_id`, the four decisions a person can make (approve, reject, remap, unmap) each writing one audit row inside its own transaction, and the `/materials` screen that consumes them. Migration 0012.
  The matching insight worth recording, because it is the one place M5 must *differ* from what shipped in M2: **proposals are pack-blind where snapping is pack-sensitive.** `snap_item` vetoes across pack sizes, because a 2.5 kg sack and a 500 g pouch are two catalog rows with two price histories; they are one *material*, so pack sizes are stripped from both names before scoring and there is no veto (`units.strip_packs`, new).
  The threshold was measured, not picked: 0.70. Real matches clear it ("MILK PWDR 2.5KG NIDO" 0.72, "EVAP MILK 48x400ML" vs "Evaporated Milk" 0.75), and it does not go lower because **"Chickpeas 1kg" scores 0.696 against "Chicken Breast" - the same as the genuine "Cardamom Powder 500g" vs "Cardamom"**. No threshold keeps one and drops the other, so the tie breaks toward silence: two confusable foods offered as one material is the merge a tired consultant approves and nobody catches.
  Two guards proven rather than assumed. The **cross-tenant refusal** was tested by driving the raw `update supplier_items set ingredient_id` against another tenant's material and watching Postgres raise `supplier_items_ingredient_fk` - the composite key does the work, not a code path that might be forgotten. And the **dimension refusal** was exercised on the real screen: mapping a millilitre carton onto a gram material answers "'Evaporated Milk 48x400ml' is measured by volume, but Milk Powder is measured by weight" - plain English, after a first pass leaked `ml` and `g` into the message and the screenshot caught it.
  Seen working, not just built: the screen was driven end to end in a browser. Naming the first material removes it from the queue, and **the second supplier's 500 g pouch is then proposed as the same material** - the milestone's whole point, on screen.
  **423 API tests green** (was 411; 12 new), ruff clean, web typecheck + eslint + production build clean with the new `/materials` route.
  **WP-53 shipped**: every confirmed invoice line now carries what one gram of it cost, frozen inside the same transaction that confirms the invoice, and the review screen shows it beside the photo. Migration 0013 adds `cost_per_base_unit numeric(18,8)`, `cost_base_unit` and a `cost_basis` jsonb; `costing.py` is the pure module that does the dividing and the labelling.
  **The precision is the whole point of the column, and it was verified by breaking it.** Flour at AED 43.50 per 25 kg is 0.00174 AED a gram. Changing 0013 to `numeric(12,3)` - the precision every price column uses, because fils is what a price is quoted in - makes the test fail with `0.002`: a 15% error, on a number no photograph shows, that nothing downstream could ever notice. The rounding therefore happens **once, at the division**, on the raw unit price rather than on price memory's already-rounded fils figure.
  **The position trap the plan warned about was real, and its test has teeth.** The stock-line query drops charge lines, so the loop counter is not where a line sits on the invoice, and C8 provenance is keyed by that position. Substituting `enumerate` for the fetched `position` makes an invoice whose first line is a delivery charge read every stock line's quality off the row above it - proven by reverting the fix and watching the avocado line come back `estimated` because the *delivery charge* had been corrected. Exactly backwards, on the one number nobody can check against a photo.
  **No cost reads verified, and a test pins the absence of the word** rather than trusting future readers to remember why. Costs read *reliable with limitations*, or *estimated* when a person supplied an input - and the input set is derived from the arithmetic, not listed: an exclusive invoice's cost never touches `total`, so a reconstructed total there changes nothing, while a discounted invoice allocates pro rata over the stock-line sum and one corrected `line_total` taints every other line's cost.
  A line that cannot be costed says which of six things went wrong, in a sentence a consultant can act on, rather than going quiet - the derived half of WP-55, shipped early because "no cost" with no reason beside it is the dead end this product keeps promising not to be.
  Seen on the screen, and two things fixed there that no test would have caught: the quality caption repeated identically on all five rows (now only the exception is labelled, with the standing limitation stated once under the table), and a confirmed invoice showed the word "Confirmed" twice in a stack - the status chip and a disabled button - now the chip plus the date it was confirmed.
  **452 API tests green** (was 423; 29 new), eval scorer 65 green, `eval.run --smoke` OK, ruff clean on both trees, web typecheck + eslint + production build clean.
  **WP-54 shipped, and with it the milestone's done-when: milk powder bought from two suppliers in three pack sizes now reads as one material at one price per kilo, on screen, with the invoice photo one click from the figure.** No migration, because there is nothing new to store: the price is the newest costed line among the packs mapped right now, derived on every read (`db.list_mapped_pack_costs`, `/api/ingredients`).
  **The ordering rule is the one that matters, and its test has teeth.** Ranking by confirm time instead of printed invoice date makes the suite fail with a June price - AED 17.60 a kilo - standing as today's cost, which is exactly the onboarding case the Decision Log reversal was about: someone hands over a pile of paper and it goes through in whatever order it comes out of the envelope. An invoice with no printed date falls back to its confirm date, and the payload keeps the two apart, because "bought on" and "recorded on" are different claims.
  **Unmapping a wrong merge corrects the price with nothing to rebuild**, which is the whole return on not having an `ingredient_costs` table: mapping saffron onto milk powder takes the price to AED 52,250 a kilo, and one unmap puts it back to 20.20 with no refresh anywhere to have remembered.
  One query returns each pack's *own* newest cost as well as the material's, so the screen shows the comparison the merge exists to make: the same material at 20.20 and 23.50 a kilo from two suppliers, with the newer one marked as the one setting the price. That is the number M6 will multiply by a recipe quantity.
  **459 API tests green** (was 452; 7 new), eval 65 + smoke OK, ruff clean, web typecheck + eslint + build clean.
  **WP-55 shipped, and M5 is complete.** Every confirmed line that could not be costed appears on `/materials` with its own reason and the money behind it, grouped by product so a carton bought twelve times is one question; a consultant answers "one holds 10 kg" and every line of that product with no cost is worked out from it. Migration 0014, `supplier_items.pack_size_override`.
  **The override is its own column, deliberately.** `pack_size` is what the first invoice a product ever appeared on printed - write-once and stale by design (`TODOS.md`) - while the override is what a person asserted about a container that printed nothing. Merging them would lose the only distinction that matters: one was seen by a camera and the other was not, and that is exactly what makes a cost built on it read *estimated* with no extra rule to remember.
  **Two guards on "never rewrites a line already costed", and both were checked by breaking them.** Dropping the invoice-level filter makes a corrected conversion pull an old line from AED 14.80 a kilo to 12.33; dropping the line-level one does the same when two unlabelled products share an invoice and are answered on different days. The cost of the rule is stated rather than hidden: a conversion entered wrongly is **not** retro-fixed, so the earlier figure stands and the audit trail shows both answers.
  Two things the screen caught that no test would have. The mock served every cost as read-from-the-invoice, so a price built on a person's conversion claimed on screen to come from the page - the exact false claim C9 exists to prevent, in the demo a founder would be shown. And a bare carton was still being asked what it measures *after* someone had said it holds 10 kg, which is the product not listening; the approval gate now reads the conversion too.
  **473 API tests green** (was 459; 14 new), eval 65 + smoke OK, ruff clean, web typecheck + eslint + build clean.
  Next: M6 decomposition (recipes and menu costing) - the demo gate.

- 2026-08-29 - **All four lanes are one master again: WP-26/28 (landed earlier), the M4 loop-gate lane, WP-29 bilingual matching, and the Gemini 3 Flash swap - merged, tested together, deployed in one push.**
  Integration order was WP-29 then the provider swap, and the combined suite is green: 393 API tests, 65 eval tests, smoke, ruff on both trees.
  Two real cross-lane finds during integration, both fixed where they met: WP-28's own test caught the duplicate hold treating USD 745.76 and AED 745.76 as the same total (totals now compare only within one currency, the number alone still notes), and rehearsal 1 caught the review screen leaking numeric(12,3) storage precision ("54.500", qty "12.000") - trimmed at the one formatting seam, no value ever changed.
  WP-29 lands at the right moment: Flash's only sub-100 field is the bilingual-letterhead join, and the script-aware matcher makes exactly that harmless to the catalog and the alerts.
  The runbook is updated for the Flash era: provider-key and billing preconditions, the warm-up note (grammar compilation is an Opus-fallback concern; the never-cold-open principle stays), reply narration at 10-15 s, and §E0 marked as Opus-era evidence.
  **Owed before the loop gate is called passed: the 5x runs, the meme, and both rehearsals re-run on Flash** - the engine that will actually demo.
  Next: post-deploy upload-door proof that Flash serves live, then the founder's Flash runs, then the M4 retro decomposes M5/M6.

- 2026-08-29 - **Gemini 3 Flash is now the shipped extraction model, on the founder's call after the bake-off below; Opus 5 is one env var away.**
  `EXTRACTION_PROVIDER` selects the provider (default `gemini`), `build_provider` constructs either from explicit keys, and an unknown name fails at boot rather than silently disabling extraction.
  `google-genai` moves from optional extra to hard dependency, the provider's default model becomes `gemini-3-flash-preview`, and prompts, schema, validation, repair and everything downstream are untouched - the swap is exactly the one-place change C3 promised.
  The eval's `--provider` default and the `--record` guard now follow the shipped provider, so recordings can only ever be refreshed with the model we actually ship, and the recorded corpus was refreshed from Flash in the same session so a recorded re-score describes the pipeline we run.
  The refresh doubled as Flash's second accuracy run, and two things moved: the bilingual join switched cases (HW-04 clean this time, AR-01 still joined, supplier_name 90%), and TH-01's embedded pack sizes went from all read to all null (pack_size 100% then 90%), so that read is run-to-run unstable on Flash and is the specific thing the phase-2 corpus should watch.
  Everything else held at 100% both runs, reconciliation 10/10 with zero repair rounds both runs, and the second run was faster and cheaper still (7.5 s, $0.0056 average) - while PH-01's and PR-01's refreshed recordings came back byte-identical to the Opus ones, the same 34-line invoice read to the same values.
  **Deploy order, before this reaches Railway: set `GEMINI_API_KEY` in the service environment first** - without it every forward acks, fails three retries and sends the failure reply (ingest, upload and manual entry keep working); rollback is `EXTRACTION_PROVIDER=anthropic` plus the existing Anthropic key, no deploy.
  The founder set the key on Railway the same day and redeployed - but that deploy predated this branch landing on master, so it shipped Opus unchanged with the key sitting unread; Flash actually goes live with the first deploy after this merge.
  Also owed to the swap, not yet done: the live loop has never run Flash end to end on a real phone forward, and the repair round has never fired on Gemini at all - both belong to the M4 rehearsals before the loop gate is called passed again.
- 2026-08-29 - **The Gemini bake-off ran: on the ten generated invoices, Gemini 3.1 Pro matches the Opus 5 baseline almost everywhere at 2.4x lower cost and ~40% higher latency, and its two real misses are one wrong-cell subtotal that the arithmetic would not have caught and pack sizes left null whenever the pack lives inside the item name.**
  A second reader now sits behind the same provider seam the product already has (C3): same prompt text at v3, word for word, so any accuracy difference in the eval is the model and not the wording - if Gemini turns out to need different wording to keep up, that is a finding for the report and a real cost of switching (two prompts and two baselines to maintain), never a quiet edit.
  The production default is untouched: the pipeline still builds only the Anthropic provider, the Gemini SDK is an optional install (`pip install -e 'apps/api[gemini]'`), and production images do not grow for an experiment.
  The eval runner gained `--provider gemini` (key from `GEMINI_API_KEY`), and `--record` is now refused for any provider but the shipped one - the recorded fixtures are the exam CI marks against, and one careless flag must never replace their answers with another model's.
  Three findings from the wiring and the first live calls: Gemini's *default* structured-output path rejects our schema outright - the live API 400s on the `additionalProperties` our strict models emit - so the provider sends the raw JSON Schema form instead (`response_json_schema`), which the API accepts with every money field crossing as a string (the no-float-money rule holds), proven live end to end on a free-tier model with the answer parsing back through the pinned schema; the repair patch needs the same list-shaped workaround the Anthropic wire needed; and Gemini reports a truncated answer explicitly (`MAX_TOKENS`), so the provider raises on anything but a clean finish - WP-19's rule, a short read fails loudly, never a shorter invoice.
  The founder's key was confirmed against the live model list - `gemini-3.1-pro-preview` is the one plain Gemini 3 Pro id it serves, the provider's default - and the first attempt stopped at quota because the free tier serves `gemini-3.1-pro` at a limit of zero; the founder enabled billing the same day (the same step F5 was for Anthropic) and the run went through.
  One honest stumble on the way: the first billed attempt crashed reading Gemini's token counts because the unit tests had faked the SDK response with a field name the real wire does not have, so ten answers were paid for and thrown away (~$0.26); the fake now builds the SDK's own usage and candidate types so a misnamed field fails in tests, never live.
  Cost table updated with verified list prices: Gemini 3 Pro is $2 in / $12 out per million tokens against Opus 5's $5 / $25, with Google billing thinking tokens as output, and the provider counts them so the cost per invoice cannot under-report.
  One naming caveat found while verifying: the original `gemini-3-pro-preview` id has left Google's pricing page and the current Gemini 3 Pro line is `gemini-3.1-pro-preview`; the exact id the founder's key serves must be confirmed by listing models before the run, and `GEMINI_MODEL_ID` overrides without a code change.
  371 API tests (7 new, faking the Gemini SDK at its own seam), 68 eval tests (4 new, pinning the `--record` refusal), smoke untouched, ruff clean on both trees.
  **The result, measured on the ten generated invoices, single run, prompt v3 shared verbatim, 2026-08-29** (the Opus column is the 2026-08-28 baseline on the same corpus and prompt):

  | metric | Opus 5 | Gemini 3.1 Pro |
  |---|---|---|
  | classification, invoice_no, date, currency, payment_kind, tax, total | 100% | 100% |
  | supplier_name | 100% (known bilingual variance) | 90% (same bilingual shape, on AR-01) |
  | subtotal | 100% | 90% (TH-01 wrong cell) |
  | line recall / precision | 100% / 100% | 100% / 100% |
  | raw_name, qty, unit, unit_price, line_total | 100% | 100% |
  | pack_size | 99% | 89% |
  | reconciliation | 10/10, zero repair rounds | 10/10, zero repair rounds |
  | cost per invoice | ~$0.064 | ~$0.026 |
  | model latency, avg (worst) | ~11 s (22.9 s, PH-01) | 15.0 s (28.3 s, PH-01) |

  The subtotal miss is the finding that matters: TH-01 prints both "Subtotal (VAT inclusive): 706.65" and "Net of VAT: 673.00", and Gemini filled `subtotal` from the net line - a printed value from the wrong labeled cell, not an invention - and `subtotal` is the one header money field the C4 identities do not cross-check (they anchor on the line sum), so in production this would have stored green: a silent wrong number, the exact thing the §5 gate says must never happen.
  The pack_size gap is a single behavior, not scattered noise: all ten TH-01 lines carry the pack inside the item name ("RICE BASM 5KG") and Gemini leaves `pack_size` null where Opus extracts it, plus the same HW-02 "Tray 30" both models arguably miss; a null is honest rather than wrong, but M5's cost-per-unit normalization would inherit the manual work.
  The supplier_name miss is AR-01's letterhead returned with both scripts joined, the same known variance shape Opus shows on HW-04, not a new finding.
  On the other side: Gemini read all 134 line values of a 34-line invoice clean, every date through the WP-27 text path, and reconciled 10/10 with zero repair rounds, at $0.026 an invoice against $0.064 - input tokens are 5x cheaper because Gemini tokenizes the photo into ~1.6k tokens against Opus's ~7.8k.
  Latency is the demo-relevant cost: 15.0 s average model time against Opus's ~11 s, and three of the ten invoices took 18 s or more of model time alone, which does not fit the ~20 s forward-to-reply target that currently carries ~4-9 s of non-model overhead.
  Caveats before anyone quotes these numbers: ten generated invoices, one run each, phase 1 of the corpus - not pilot accuracy - and the prompt was tuned for Opus over two WP-16 rounds, so Gemini-specific wording might close the pack_size and subtotal gaps, at the standing cost of maintaining two prompts and two baselines.
  The trade for the founder: Gemini saves ~$0.04 per invoice and gives back one silent-wrong-number shape, the embedded pack sizes, and ~4 s of average latency; at demo volume the money is irrelevant by §3's own table, so nothing here argues for switching before the demo, and the numbers to revisit at pilot volume are a Gemini-tuned prompt scored on the phase-2 real corpus.
  **Round two, founder-requested the same day: Gemini 3 Flash (`gemini-3-flash-preview`, $0.50 in / $3 out verified), same corpus, same shared prompt, single run - and it beat both Pro models on this corpus.**
  Every field scored 100% except supplier_name at 80%, where both misses are the same known bilingual-join shape (AR-01 and HW-04, the same Dairy House letterhead both scripts joined); subtotal, the embedded pack sizes, even HW-02's arguable "Tray 30" all came back right, line capture 100/100, reconciliation 10/10 with zero repair rounds.
  Cost per invoice ~$0.0065, a tenth of Opus and a quarter of 3.1 Pro, and the whole ten-invoice run cost $0.065 - the price of one Opus invoice.
  Latency 9.5 s average with the worst case 13.9 s, faster than Opus's ~11 s average - and PH-01's 34 lines read perfectly in 9.2 s against 22.9 s on Opus and 28.3 s on 3.1 Pro, so every one of the ten fits inside the ~20 s reply target with room to spare.
  The honest frame before anyone re-platforms on a ten-invoice exam: one run of a generated corpus, the bilingual-join variance hits all three models run to run, and phase 2's real photos - crumpled thermal, handwriting, carbon - are precisely where a small model would be expected to fall first; but on today's evidence Flash, not 3.1 Pro, is the alternative worth taking to the phase-2 corpus.
  Choosing the provider is the founder's call; this lane's deliverable is the table, and the production default stays Anthropic.
- 2026-08-29 - **The bilingual supplier gap is closed: a GCC letterhead that comes back in two scripts now finds its supplier and its items, instead of quietly splitting the catalog in two.**
  Found on the 2026-08-28 eval - HW-04's supplier line came back as English and Arabic joined ("Dairy House Foodstuff LLC / بيت الألبان..."), and a retry read it clean, so both readings are legitimate and will keep happening.
  The joined name scored 0.595 against the stored English name, below the 0.85 match bar, so the supplier missed: no item snapping, no price alert, and on confirm a **second "Dairy House" supplier** would be created under the joined name - the catalog splits and that supplier's money moment goes quiet.
  The same scoring serves the line items, so an item printed joined on one invoice (AR-01, "Halloumi Cheese جبنة حلوم") and Arabic-only on the next (HW-04, "جبنة حلوم") would have become two catalog rows too.
  Fixed where the fault is, in `matching.py` and nowhere else: the score now compares the English half to the English half and the Arabic to the Arabic and takes the best, so whichever script the model happens to copy, the shared half carries the match - the joined supplier and both item variants all score 1.00.
  It is gated so the boost only applies when one side is a single script; two different suppliers that share the same Arabic legal boilerplate ("... للمواد الغذائية ذ.م.م") stay apart at 0.76, well under the bar.
  Extraction, the prompt, the schema and the founder-signed ground truth are all untouched - names are still stored exactly as printed, in whatever scripts the page carries.
  Two routes were considered and declined for the record: telling the model to extract English only (a prompt set against the very run-variance the pipeline exists to absorb, and it breaks the F8 answer key), and rejecting Arabic invoices (turning away a real supplier's paper, and it would not even fix this case since the supplier line here is English).
  4 new tests (the joined and Arabic-only matches, plus the adversarial-boilerplate and different-item guards), 368 green, ruff clean; the matching change is pure and the downstream confirm and pipeline flow tests pass unchanged.
  Next: WP-19 (the line-completeness guard) remains the last M5 prerequisite open, then the M4 loop-gate items - curate the three demo invoices, the meme decline, and the two rehearsals.
- 2026-08-29 - **The three demo papers exist and are pre-verified on the live pipeline; only phone work remains on the loop gate.**
  Generator prompts written to the demo seed's exact numbers (`Docs/demo-invoices/`), images generated by the founder, and each uploaded once through the production C6 door: every field exact against spec, all lines green, exclusive at 5%, no repair round, 4.7-5.2 s model time, and all three day-first printed dates (20/08, 22/08, 24/08) derived correctly.
  Test rows and storage were removed after each check; the live project is untouched.
  Remaining on the loop gate, all runbook phone work: save the papers plus the meme to the demo phone, section A preconditions, 5x runs per paper, the meme decline, two act-one rehearsals.

- 2026-08-29 - **The three curated M4 demo papers are generated from their exact-content prompts.**
  Added `Docs/demo-invoices/DEMO-1.png`, `DEMO-2.png`, and `DEMO-3.png` beside the committed prompts.
  Each saved image was visually checked for the required supplier, invoice number, date, two line items, VAT, total, unobstructed page corners, and readable digits.
  This closes image generation only; live upload verification and five full-loop runs per paper remain before the M4 curation checklist can move.

- 2026-08-28 - **M4 loop gate: WP-19 and WP-44 shipped and the latency box closes; what remains is phone work.**
  Built in an isolated worktree (`m4-loop-gate`) with its own venv and test database while WP-26/WP-28 ran in a parallel session on the main tree, per §7.5.
  **WP-19:** a truncated read now fails loudly at the provider - `stop_reason='max_tokens'` raises even when the cut-off JSON parses, for extract and repair alike - so the old platform's worst failure (a perfect header with 2 of 34 lines) cannot persist here. The model-reported row count half of the brief is foreclosed by the schema ceiling and logged as an amendment; the budget half is measured, not asserted (PH-01: 2,638 of 16,000 output tokens).
  **WP-44:** the same paper sent twice is held as needs_review with a reply naming the earlier record ("This one is already recorded: ..."); a number-only or date+total match appends a note instead, because a second same-day delivery is real. Pure rule in `pipeline.find_duplicate` (testable without a database), number normalization in `matching.normalize_invoice_no`, headers fetched once per tenant.
  **Latency** ticks on evidence: 18.7 s on a real forward at v3, no repair round; the 5x curated runs re-verify per paper.
  `Docs/DEMO_RUNBOOK.md` is caught up with the week: the exact reply now carries the "dated" line, the wait narration says 15-20 s not 30, the grammar warm-up is a precondition, curated papers must print distinct invoice numbers and a date (the duplicate hold makes a reused number a rehearsal-breaker - reset after every run now), and the failure playbook gains the duplicate-hold pivot line.
  13 new tests; 346 API tests, ruff clean.
  Still open on the loop gate, all founder phone work: curate the three papers to the runbook's spec, run each through the loop 5x, the meme decline word-perfect, two rehearsals.

- 2026-08-29 - **CUT-01 generated and put through the real model: the pipeline returned no total rather than inventing one, which is the whole bet WP-26 rests on.**
  The new fixture (`eval/fixtures/generated/proposed/CUT-01.prompt.txt` and its image) is an export invoice billed in USD with no totals block on the page: five lines that read green and sum to 710.50, and a true total of 710.50 that appears nowhere in the picture.
  It carries both of yesterday's hazards on purpose, because they arrived together in real life.
  Layer 1 at prompt v3 read it in **8.0 s** with no repair round: supplier, invoice number, `09/07/2026` derived day-first to 9 Jul 2026, currency USD, all five lines green, and `total`, `subtotal` and `tax` all **null**.
  That is the finding that matters - a vision model asked to read a page with no total is perfectly capable of adding the lines up and reporting the answer as though it had read it, and this one did not.
  The reply then carried both new questions in one message, a bare `OK` was refused, `total 710.50 no vat` resolved the invoice green against the paper's real total, and the ack said the prices were kept out of price history.
  `pack_size` came back null on all five lines, which is right rather than a miss: this invoice has no pack-size column and the pack is inside the description, exactly the `HW-02` ruling the founder signed off on 2026-08-25.
  **Then proven on the phone the same night, which is what actually settles it.**
  The founder forwarded CUT-01 from the demo handset at 02:39:01: ack at +6 s, full reading at **+19 s**, inside the ~20 s target, no repair round, 8.5 s of model time at prompt v3.
  WhatsApp compressed the 2 MB PNG to a JPEG on the way and every figure still read correctly, which is the closest thing yet to what a salesman's forward actually looks like.
  Every reply came back **byte-identical to the local rehearsal**, including the ack, and the stored invoice carries `total` and `tax` as C8 `reconstructed` by `whatsapp:971509772702` with every other field `extracted` by `model:claude-opus-5` - the first reconstructed values in production.
  The confirm then proved the half that caused the original incident: the invoice went `confirmed`, a supplier row was created for identity, and **price memory did not move at all** - zero catalog items, zero price observations, zero lines linked - with the ack saying so in the sender's own chat.
  `audit_events` holds the pair: `invoice.corrected` naming fields `total` and `tax` with the inbound message id, then `invoice.confirmed`.
  The one step not exercised on hardware is the bare `OK` refusal, because the founder answered the question directly rather than testing the refusal first; it stands on the e2e tests and the local rehearsal.
  All CUT-01 rows were then wiped from live on the founder's instruction - invoice, lines, audit events, supplier, document, extraction run, four jobs, seven messages and the stored photo - leaving zero null-total invoices and a clean referential state.
  Unrelated and worth knowing: `demo_seed.sql` (WP-40) was run against live at 02:43:25 with its documented manual phone step, so the demo handset now resolves to the **Karak Al Khaleej Cafeterias** chain with its staged three weeks of price history, and the older `Demo Cafeteria Group` rows are no longer reachable from that phone.
  CUT-01 is not in the corpus yet - promoting it needs ground truth and an F8 verdict, which is a founder call, not mine.
- 2026-08-29 - **CUT-01 now has its generated invoice photograph.**
  The image preserves the complete header and all five USD line items while the paper continues beyond the bottom of the frame before any totals content appears.
  The visible values were checked against `CUT-01.prompt.txt`; `710.50`, subtotal, tax, freight, and every totals-area character are absent as required.
  The case remains proposed until ground truth and readback verification are written and it is added to the manifest.

- 2026-08-28 - **The two live findings are closed: an invoice with no total can no longer be confirmed away, and an invoice billed in someone else's money can no longer walk into the price baseline.**
  Both were found on real forwards rather than in tests, and both are the same shape - a number that looks complete and means nothing, which is survivable while every figure sits beside its photo and is not survivable from M5.
  **WP-26.** With the totals block off the page, the reply now shows the line sum and asks the two facts the arithmetic cannot supply on its own: is that the whole invoice, and do the prices already include VAT.
  A bare `OK` no longer confirms such an invoice from chat or from the review screen, and the guard sits in the single confirm write as well as in both callers, so the message can say why while the rule cannot be walked around.
  The answer arrives through the existing correction grammar - `total 710.25 inc vat 5%` or `total 710.25 no vat` - and is stored as C8 `reconstructed`, while a total the sender reads off the page stays `corrected_chat`.
  "inc vat" with no rate gets its own question rather than a guessed rate, the same shape as WP-27's missing year.
  One bug surfaced on the way: the C4 treatment was not being re-derived when a correction changed the arithmetic, so a total supplied after the fact would have left a stale `tax_treatment` beside it and recorded a gross price under a net baseline.
  It travels with every correction now.
  **WP-28.** A currency that differs from `tenants.currency` produces its own question in the reply, the invoice still confirms and still stores exactly as printed, and `record_confirmed_prices` returns before the catalog - no item created, no observation appended, no baseline moved - with the ack saying plainly that it was held back.
  Price alerts are suppressed on the same test: subtracting an AED baseline from a USD price is the demo's money moment lying in the one moment it asks to be trusted.
  Recording currency per price row was deliberately not built (§2 rule 8): no customer has asked for multi-currency history, and a hold is reversible later without a migration.
  31 new tests, 364 green, eval smoke unchanged; an AED invoice's reply is byte-identical to yesterday's, which is the regression the whole thing had to avoid.
  **Deployed and the live data cleaned, same session, on founder decisions.**
  Five scenes were rehearsed locally through the real webhook-to-reply path first so the exact WhatsApp wording was seen before it could reach a phone; CI green in 1m24s, pushed, Railway health steady at `ok:true db:true` across the redeploy window.
  Two sets of live rows were then deleted, both scoped by hand and executed with per-statement row counts asserted against what was expected:
  the three Levant `supplier_items` carrying USD baselines (75.000 / 65.000 / 35.000) went entirely - three price observations deleted, three `invoice_lines` unlinked - while the Levant supplier and its USD invoice stay, correctly stored as printed;
  and the Artisan Bakehouse invoice, confirmed on 2026-08-25 with a null total and unreachable by the new conversation because confirmed invoices are not editable, was wiped completely - invoice, 6 lines, 6 price observations, 6 catalog items, the supplier row, the extraction run, the document, its three jobs, the five WhatsApp messages of that exchange, and the stored original in Supabase Storage.
  The live project now holds zero null-total invoices, no cross-currency price rows, and passes every referential check.
  The one thing not yet proven on hardware: the deploy carries no version marker and the API token is not held locally, so **one real forward is still owed as the live proof** - the same standard M0 was held to.
  Next: WP-19 (the line-completeness guard) is the last M5 prerequisite still open, then the remaining M4 gate items - curate the three demo invoices and the two rehearsals.
- 2026-08-28 - **The demo bar is raised to the complete end-to-end MVP: extraction → raw-material mapping → recipe ingredients → menu costing, closing on a menu-wise margin per item. The demo gate moves from M4 to the end of M6.**
  Founder call, quoted in the Decision Log: the demo must show a restaurant finding its menu-wise profit margin "so that he can prioritize what to push and what not to push" - the loop alone is act one, not the show.
  The plan is amended throughout: §1 states the four-layer chain as the north star, §6 is the invoice loop with M4 as its *loop* gate (every hardening item kept - the loop must run flawlessly twice before anything is costed on top of it), §8's M5+M6 join the demo track with the **DEMO GATE** at M6's end, the demo script gains act two (materials screen → ranked menu margins → "push this, fix that"), and F7 gains the founder input M6 cannot run without: one real menu with recipes and selling prices.
  `CLAUDE.md`/`AGENTS.md` now carry the MVP chain definition so every future session builds toward it.
  Cost stated in §8: the demo waits for M5+M6, roughly weeks 4-7 instead of week 3.
  Next, unchanged in content but re-motivated: close WP-26 and the currency question (both now feed M5's cost integrity), finish the M4 loop-gate items, then decompose M5/M6 into work packages at the M4 retro.
- 2026-08-28 - **First real forward through the v3 pipeline: 18.7 s photo-to-reply, confirmed from chat in 5 s, and the first real C8 audit row - plus one finding: a USD invoice walked into AED price memory unlabeled.**
  The founder forwarded Levant Specialty Foods FZCO LSF-EXP-260716-0098 (a PNG sent as a WhatsApp *document*, which the ingest handled): ack at +8 s, full reading at **+18.7 s** - under the ~20 s target, at prompt v3 with no repair round, 6.9 s model time, warm grammar.
  The reply carried WP-27's "dated 16 Jul 2026" line live for the first time; all three lines green, 150+65+35 = 250.00 exclusive, every provenance field `extracted` by `model:claude-opus-5`.
  "ok" confirmed it 2 s after arriving, the ack followed 3 s later, and `audit_events` now holds its first real row: `whatsapp:971509772702 | invoice.confirmed` - who confirmed, written in the same transaction as the confirm.
  **The finding:** the invoice bills in **USD** and the confirm recorded 75.00 / 65.00 / 35.00 into `supplier_items.last_price`, which is a bare number with no currency dimension, on an AED tenant.
  Harmless while a supplier always bills one currency (alerts compare that supplier's own history), but a supplier switching currency would fire nonsense alerts, and any M5 purchases roll-up would add these as if they were dirhams.
  This is exactly the "tenant-currency mismatch amber" the old-platform review listed as a cheap fourth port (2026-08-24) and we declined; it now has a live occurrence. Founder call wanted: hold-and-ask on a currency that differs from the tenant's, or record the currency beside the price - before M5 makes these numbers load-bearing.
  Next: unchanged - WP-26's bare-OK question, demo invoice curation, rehearsals, the six corpus images, the bilingual supplier gap, and now the currency question.

- 2026-08-28 - **Migration 0011 applied to the live project; the C8 deploy-order debt is cleared.**
  Pre-flight confirmed the live schema at exactly 0010 (no `provenance` column, no `audit_events`, 4 invoice rows); 0011 then ran in one transaction and verified clean: `invoices.provenance` defaulting `{}` on all 4 existing rows, `audit_events` with both indexes, RLS enabled with zero policies per the 0001 convention.
  The risk window between the code push and this migration was never exercised - the last live job ran 2026-08-25 18:10 (the channel has been quiet), so nothing on master ever wrote against the old schema.
  Same day, both closed: Railway auto-deployed 099fb1f on push (GitHub deployment status success 14:32 UTC, `/health` 200 `db:true` against the migrated schema), and the v3 grammar was warmed with `python -m eval.schema_probe` - 3.7 s round-trip against the ~155 s cold compile measured that morning, so the cache is hot and the next live forward reads at normal speed.
  **The live loop was then verified end to end through the upload door** (the one leg a phone is not needed for): PR-01 uploaded via the production C6 API extracted on attempt 1 in 7.0 s of model time at prompt v3 with no repair round, every field matching truth, all checks green, reconciled exclusive at 5%, and the first C8 provenance ever written in production - 34 field paths stamped `extracted` by `model:claude-opus-5`. The test rows and the stored image were then deleted (production is back to its 4 real invoices), per the fixtures README rule that a generated invoice in the pipeline is indistinguishable from a real one. The WhatsApp plumbing checks out too - the long-lived token authenticates and the Faida app is still subscribed to the WABA - so the only unverified link is Meta delivering a real forward to the webhook, which takes one photo from a demo phone and also opens the 24 h window so the reply delivers.
- 2026-08-28 - **WP-25 and WP-27 shipped: a missing date or invoice number is now asked for instead of silently stored, dates are read day-first from the printed text by rule, and the calendar date had to leave the wire schema to fit.**
  The model now copies the date exactly as printed into C3's new `invoice_date_text` and `extraction/dates.py` derives the calendar date in code: GCC day-first (09/07/2026 is 9 July, the swapped reading only when it is the sole valid one), written months in English and Arabic, Arabic-Indic digits, and "5/7" with no year stays null and asks - the fourth printed-fact/derivation split after currency, payment terms and units.
  The reply asks one question per missing required field ("I couldn't read the invoice date - what does it say?"), ranks those questions above the line ambers so they can never overflow, and shows a read date as "dated 5 Jul 2026" so a wrong derivation can be challenged from the phone; the correction grammar gained `date 5/7/26` and `invoice no 4471`, and a date-shaped answer with no year gets a specific "send it with the year" reply, not the generic clarify.
  **The 2026-08-25 schema ceiling struck again, and this time it was measured:** adding the one text field made the API 400 on every request, an A/B against the live API showed the grammar budget fits exactly one date field (text plus even a plain-string date fails; text alone compiles), so `invoice_date` is now absent from the wire (`SkipJsonSchema`) while remaining on the model for persistence, truth and manual entry.
  `eval/schema_probe.py` makes that check a command; run it after any C3 change and note that the first request against a changed schema pays server-side grammar compilation (three cases took ~155 s before the cache warmed, the other seven ran at v2 speed), so warm the grammar after a deploy before anyone forwards a real invoice.
  **v3 numbers, measured on generated invoices:** every §5 target still holds - `invoice_date` 100% through the new path, `pack_size` 99% (the same signed-off arguable miss), reconciliation 100%, ~$0.064 per invoice.
  `supplier_name` scored 90% because HW-04's bilingual letterhead came back as both scripts joined; a retry read it clean, so it is run variance, but it exposed a real gap: `match_supplier` scores the joined form 0.595 against the 0.85 threshold, so a bilingual header can miss the supplier entirely - no snap, no alert, and a duplicate supplier row on confirm. Booked for a session of its own, same shape as the units dictionary.
  Also fixed along the way: the chat-correction path rebuilt invoices without `line_kind`, `discount_total` and `rounding_amount`, so a correction on a discounted invoice re-validated against the wrong C4 identity and would have failed a correct invoice into amber; now carried and covered by an e2e test.
  `AMD-01` (the 5/7/26 carbon bill) is promoted into the corpus awaiting its image, and the CI smoke's `01_perfect` now stores its date as printed text only, so the smoke fails the moment the derivation stops running.
  315 API tests, 60 eval tests, smoke green, ruff clean, recordings regenerated at prompt v3.
  Next: WP-26 needs the founder's call on whether a bare OK may confirm away a missing total; then the M4 gate items (curate the three demo invoices, meme decline, two rehearsals), the six missing corpus images, and the bilingual supplier-name gap.
- 2026-08-28 - **Provenance shipped: every stored number now records how it got there, and every human decision lands on the record.** Founder said yes to the harness review's three changes; all three are in, in front of M5 rather than delaying it.
  **What was wrong.** `extraction_runs` recorded the model's every move while nothing recorded a person's, so a total read off the page and a total the owner typed into WhatsApp because the paper was out of frame were the same number in the same column. Fine while every figure sits beside its photo; useless from M5, where it becomes a cost per gram three divisions away from anything you can look at.
  **What shipped** (migration 0011, 18 new tests, 282 green): `invoices.provenance` - flat jsonb keyed by field path, each field carrying origin, actor and time (`provenance.py`, C8). The repair round is attributed by **diffing** the invoice before and after the merge, not by asking the repair what it touched - a scoped re-read of three cells routinely hands two back unchanged. Chat corrections stamp `corrected_chat` with the sender's phone, the screen stamps `corrected_screen` with `console`, manual entry stamps the whole document `manual`, and every field the edit did not touch keeps the model's reading. `audit_events` records human decisions (confirm, correct, hand-entry, and M5's merges when they land) while `extraction_runs` keeps recording model runs - neither duplicates the other. The audit row is written **inside the same transaction** as the thing it records, so a confirmed invoice with no note of who confirmed it is unreachable, and a retried job that re-sends its ack still leaves exactly one confirmation in the trail (tested).
  **C9 is a written rule, not code yet**, because no derived number exists to carry it: a plate cost leaning on a reconstructed total reads *estimated*, never verified. `asserted_fields()` is the read it will make. Written now because the alternative is discovering it when a margin screen shows a confident figure built on a guess.
  **What was deliberately not built:** a policy engine, an agent per task, an audit subsystem, an approvals workflow. Three of the four harness rules already held in shipped code - the job was to name the missing one, not to rewrite anything.
  **Next:** M5 proper - `ingredients`, the supplier-item mapping and its approval screen, which now has somewhere to record what it approves.

- 2026-08-28 - **The post-demo track is resequenced: raw materials and menu costing now come first, sales moves to fourth.**
  Read the whole codebase against the founder's restatement of the MVP - extract a receipt, harmonize the items into raw materials, cost a menu item - and the three layers are in very different states.
  **Layer 1 is built and is the strongest part of the codebase**: per line we already extract name, qty, unit, pack size, unit price, line total and stock-vs-charge, with arithmetic reconciliation, one scoped repair round and derived green/amber, at ~20 s on real forwards.
  **Layer 2 is half-built at the wrong altitude**: `extraction/units.py` and `matching.py` already harmonize pack sizes and messy names - the mechanically hard part - but the catalog they fill is scoped to one supplier, nothing represents a tenant-level raw material, and nothing anywhere computes a cost per gram. That last step is one division away from data we already store (`unit_price ÷ parsed pack size`), and it is written down nowhere.
  **Layer 3 did not exist**: no recipes, no menu items, no costing, in code or in schema - and it sat at M7, behind sales and auth, roughly five weeks past the demo gate, while the landing page has been selling per-item margin since 2026-08-24.
  §8 now runs M5 raw materials → M6 recipes and costing → M7 auth → M8 sales → M9 contribution → M10 brief → M11 pilot, with the Meta production chain still starting in the first post-demo milestone. The reorder's cost is stated in §8 rather than buried: the first ratio slips from week 4 to week 10.
  Two existing work packages are promoted to prerequisites of M5 rather than backlog: **WP-19** (a short read that drops a line) and **WP-26** (a null total confirmed away by a bare OK). Both make a material look cheaper than it is, and once the number is a cost per gram there is nothing downstream that can notice.
  Milestone identifiers appear in code comments, so the renumbering was applied to 24 references across `apps/api`, `apps/web`, the migrations and the READMEs in this commit; the two logs keep the numbers they were written with.
  Next: the M4 gate items still stand (curate the three demo invoices, two rehearsals, WP-26 and WP-27 with the founder). M5/M6 get their WP decomposition at the M4 retro per §7, not before - the schema sketch in §8 is deliberately not a work-package list yet.
- 2026-08-25 - **Latency measured on real forwards and the target is essentially met; two real invoices exposed two gaps, both now written up as WP-26 and WP-27.**
  The Meta token had expired again (a 2-hour USER token, the fourth in three days); exchanged it for a long-lived one valid **59 days, to 2026-10-24**, written to `apps/api/.env` and handed over for Railway. The permanent system-user token is still the real fix and still founder-gated.
  **Two live forwards, prompt v2 in production:** Artisan Bakehouse **23.0 s** (ingest 5.0 s, model 11.23 s) and Al Aweer **19.9 s** (ingest 2.9 s, model 11.19 s). The ~20 s target is met on one and missed by 3 s on the other, and the whole difference is how long Meta took to hand over the photo, not anything we control.
  **The repair round is confirmed dead in production** (`repair_applied=False` on both): the 7 s that WP-17 and WP-18 bought back is now proven on a phone rather than inferred from the harness, and the 28.4 s figure is retired. Model time is strikingly stable at 11.2 s on both, and barely moved between 5,009 and 5,026 input tokens - which weakens the "send a smaller photo" lever the latency plan ranked first.
  Today's payment work ran live on its first real invoices: Bakehouse read `credit`, Al Aweer read `cash` and was correctly held for owner approval.
  **WP-26** (totals block outside the frame: the reply asked honestly, `OK` confirmed it away, and the invoice is stored with a null total that contributes nothing to M5's purchases figure - the fix is a short conversation about subtotal and VAT treatment, never a silent computation) and **WP-27** (the date was *on the page* and still read null; all ten corpus invoices print `YYYY-MM-DD`, so the eval's 100% date score measures one format and proves nothing about `09/07/2026`) are the two gaps, both booked for the next session.
  WP-27 is the same blind-spot shape as `pack_size` at 19%: a number that looked perfect because the corpus only ever tested itself.
  Next session: review WP-26 and WP-27 with the founder, then the remaining M4 gate items (curate the three demo invoices, two rehearsals).
- 2026-08-25 - **Latency pass planned, and the headline number turns out to be stale in our favour.**
  `Docs/latency-plan.html` lays out the whole thing in plain English with the stage breakdown.
  The 28.4 s on record was measured 2026-08-23, when reading took 18 s *because the model was asked twice*: that invoice was VAT-inclusive, C4 said it did not add up, and a repair round fired on a perfectly-read page.
  WP-17 and WP-18 fixed those identities, and across all ten corpus invoices at prompt v2 **not one now needs a repair round**; reading averages 10.7 s (7.3 s on a small delivery note, 22.4 s on the 34-line `PH-01`).
  Holding the other stages constant that projects to **~21 s**, so step zero is to forward one photo and read the `webhook_to_reply_ms` line WP-41 already prints, rather than optimise something that may already be fixed.
  Ranked levers if it is still over: a lower image ceiling (up to ~4 s, and the accuracy cost is now measurable with `--live`), starting the read before the photo finishes filing (~1-2 s), fast mode (a few seconds, doubles cost to ~$0.12, needs checking against structured outputs), and the queue poll (~1 s).
  **Correction carried into three places in this file:** the "~4 s idle across two job hops" figure was wrong and had been quoted as an easy win repeatedly, including by me. `worker.py` sleeps only when the queue is empty, so the second job starts immediately; the exposure is one wait of up to 2 s.
  Noted for the demo: at 22.4 s to read, `PH-01` alone cannot clear a 20 s target, so curating the three demo invoices and the latency pass are the same job.
  Next: the founder forwards one invoice to re-measure; then the levers, in order, only as far as the target needs.
- 2026-08-25 - **F8 done: the ten image-backed cases are human-verified, zero corrections, and the sign-off is now something that can go stale loudly rather than quietly.**
  The founder reviewed all ten invoices against their photos and confirmed every one of the 134 values that had been decided rather than copied: pack sizes under the changed rule, the bilingual names joined from two scripts, TH-01's asserted absence of a unit column, and all ten cash-or-credit calls read off printed terms.
  That also settles the one question left deliberately open: `HW-02`'s "Eggs Free Range Large Tray 30" has **no** pack size, so the model returning "30" is a genuine miss and the 99% `pack_size` figure is real rather than an artifact of my own key.
  `eval/fixtures/generated/SIGNOFF.json` records the verdict, the reviewer, the commit and a sha256 per truth file; `eval/tests/test_signoff.py` fails if a verified file changes afterwards, if a new case joins the corpus without a verdict, or if one of the five image-less cases ever gets an image - which turns "truth no human checked is not truth" from a slogan into something CI enforces.
  Two honest marks against the result: the review tool's name field was left blank, so the reviewer is attributed from git config and the record says so; and zero corrections out of 134 is a strong claim resting on one pass by one person.
  The phase-1 numbers now carry a human behind them: every extraction field 100% except `pack_size` at 99%, reconciliation 100%, ~$0.06 and ~10.7 s per invoice, **measured on generated invoices** and still not pilot accuracy.
  59 eval tests, 264 API tests, smoke green.
  Next: generate the five missing images (`EDGE-02` and `EDGE-03` cover reconciliation paths nothing else reaches, and the old platform's six Cedar & Spice invoices are a free extension); the latency pass; the amber question that still dead-ends; and the deferred currency guard.
- 2026-08-25 - **F8 sign-off tooling built; the ground-truth review is now a half-hour job instead of a day.**
  `Docs/f8-review.html` shows each invoice photo beside the key we score against, one invoice per screen, and marks only the values that were *decided* rather than copied: pack sizes (the field whose meaning changed), bilingual item names joined from two scripts, the units TH-01 asserts do not exist, and each cash-or-credit call with the printed terms line quoted as its evidence.
  That is 134 of the 680 asserted values; the other 546 are either proven by arithmetic (every line multiplies out, every invoice reconciles) or copied verbatim from a printed column, so they are shown dimmed rather than queued for a decision.
  Flagging a value captures what the key says and what it should be, work survives a reload, and Finish emits a JSON sign-off record naming the reviewer and every correction.
  Built by `Docs/build_f8_review.py` from the truth files, the images and the prompts, so it cannot drift from the corpus; the five image-less cases are excluded because there is nothing to check their key against.
  Driving it in a browser found and fixed one real defect before handover: flagging a value and then pressing the confirm button silently discarded the correction. The button now saves corrections rather than overwriting them, and clearing flags is a separate explicit action.
  Also `Docs/f8-signoff-plan.html`, the plain-English brief for what the task is and why it cannot be skipped, with the 19%-that-was-really-100% incident as the worked example.
  Next: the founder runs the review; corrections get applied, the eval re-runs against the saved answers at no API cost, and the sign-off record lands in the repo against a commit.
- 2026-08-25 - **WP-16 round 2: every extraction field is at 100% on the phase-1 corpus except one genuinely ambiguous pack size, and the round found a latent way to take the whole pipeline down.**
  Three founder decisions implemented: cash-or-credit conventions in code, a units dictionary with harmonizing, and plain-English reporting as a standing rule in `CLAUDE.md`/`AGENTS.md`.
  `extraction/payment.py` derives the arrangement from the printed terms line, which C3 now carries as `payment_terms_text`: a due period is credit, an explicit cash marker is cash, printed terms outrank the model's own reading, and anything unrecognized stays null so no unmarked document slips past the cash approval gate. `payment_kind` 60% -> 100%.
  `extraction/units.py` lifts the pack-size dictionary out of `matching.py` and widens it to mass, volume, count, container words and Arabic, so "2 kg", "2000 g" and the receipt-truncated "2.5K" are one pack in the catalog and in the eval alike. `pack_size` 19% -> 99% across this and the printed-page truth rebuild; the one remaining miss is "Eggs Free Range Large Tray 30", where a bare 30 with no unit is genuinely arguable.
  **The scare, and it is worth reading twice:** adding one optional string field to C3 made the API reject every single request with `400 Schema is too complex` / `Grammar compilation timed out`. Not a worse read - no read at all, on every invoice, with the customer getting the generic failure reply. An A/B against the live API found the cause: Pydantic renders each `Decimal | None` as a three-branch union carrying a negative-lookahead regex, and C3 has fourteen of them inside an unbounded array of lines, so the schema had been sitting one field away from the grammar-compilation ceiling the whole time. Money now crosses as a string with one concrete type: fourteen lookaheads gone, 500 characters of grammar gone, headroom restored, and float money removed from the wire where C4 already banned it everywhere else. The string form invites the printed form, so `extraction/money.py` parses "AED 332.00", "1,240.50", "(41.70)", the dirham sign's own dot and Arabic-Indic digits, and rejects anything with no number in it rather than reading it as zero.
  Two smaller harness fixes: a printed "-" now means absence in the pipeline as well as in ground truth (one shared definition), and recorded replays run through the same derivation seam live runs use, so a recording cannot score differently depending on how it is read.
  **Round 2, measured on generated invoices** (phase 1, never quotable as pilot accuracy): classification, supplier, invoice no, date, currency, payment kind, subtotal, tax, total, line recall and precision, `raw_name`, `qty`, `unit`, `unit_price`, `line_total` all 100%; `pack_size` 99%; reconciliation 100% with no repair round needed on any case; ~$0.06 and ~10.7 s of provider time per invoice.
  264 API tests, 32 eval tests, smoke green, ruff clean. Prompt is at v2 and the corpus recordings were regenerated with it.
  Next: F8 sign-off on the rebuilt ground truth; generate the five missing images (`EDGE-02` and `EDGE-03` cover reconciliation paths nothing else reaches); the latency pass (see the correction in the 2026-08-25 entry: the worker poll costs ~1 s, not ~4 s); and the amber question that still dead-ends on a plain-English answer.
- 2026-08-24 - **`eval --live` shipped and WP-16 round 1 ran; the first real accuracy numbers exist, and most of what they first showed was the harness, not the model.**
  `--live` runs the product's own layers 1-3 through the product's own modules (extract, the pipeline's currency normalization, `validate_invoice`, one scoped `repair_invoice` round), scores repair lift and cost per invoice, records responses so every later re-score is free, runs cases concurrently, and isolates a failing case instead of losing the round.
  Three harness defects came out ahead of any model finding, each one capable of sending the accuracy loop after a phantom.
  The eval had its own copy of C4 that predated WP-17/WP-18, so three of fourteen invoices scored as unreconciled off perfect ground truth; it now delegates to the shipped validator.
  Ground truth for printed fields was the generator's *model* of the invoice rather than the page: `pack_size` held "2000" where the page prints "2 kg", and `TH-01`, a till receipt, carried `unit: 'bag'` with no unit column anywhere on it.
  Rebuilding truth from the prompt the image was generated from moved `pack_size` 19% -> 89%, `unit` 90% -> 100% and `raw_name` 92% -> 100% without touching the model, and every run now prints the mismatches behind the scores, because a boolean cannot tell a model error from a ground-truth error.
  The one genuine model defect the round found is worth the whole exercise: `discount_total` came back as `-41.70`, copying the sign the invoice prints, which makes C4 add the discount instead of subtracting it and fails a perfectly-read invoice into amber - the WP-17/WP-18 shape a third time, and out of the repair round's reach. Canonicalized in the schema so no rewording can regress it.
  **Round 1, measured on generated invoices** (phase 1, never quotable as pilot accuracy): classification, supplier, invoice no, date, currency, subtotal, tax, total, line recall and precision, `raw_name`, `qty`, `unit`, `unit_price`, `line_total` all 100%; reconciliation 100% (10/10); ~$0.06 and ~10.6 s of provider time per invoice over 100 line items.
  `pack_size` 89% and `payment_kind` 60% are the only gaps and both are open C3 questions, escalated rather than settled here (see the Decision Log).
  Also found by running it: **the phase-1 corpus is 10 images, not 15** - `DUP-01`, `EDGE-02`, `EDGE-03`, `HW-03` and `NEG-01` are ground truth for images nobody generated, and two of them cover reconciliation paths nothing else in the set reaches. `eval/` was never linted by CI either, which is how a wrong-line-length reformat slipped in mid-session; it now has its own ruff config and a CI step.
  211 API tests, 32 eval tests, smoke green, ruff clean.
  Next, in order: F8 sign-off on the rebuilt ground truth (agent-written truth is exactly what F8 exists to check); round 2 on the prompt, which describes neither `discount_total` nor `line_kind` nor `tax_treatment` and tells the model to skip `payment_kind` unless the page says the word; generate the five missing images (and the old platform's six Cedar & Spice invoices noted 2026-08-24 are a free extension); then the latency pass (the ~4 s worker-poll figure quoted here was wrong; see the 2026-08-25 correction).
- 2026-08-24 - **Old-platform extraction layer reviewed (read-only); three ports entered the plan.**
  Three explorers catalogued restaurant-profit-platform's pipeline mechanics, its design docs and corpus, and its SQL normalization layer against ours; the comparison is a reference artifact (Extraction Inheritance Review).
  Adopted as WP-19 (line-completeness guard, M1), WP-25 (required-field ambers, M2) and WP-44 (duplicate invoice hold, M4), each with a checklist box; a tenant-currency mismatch amber is noted as a cheap fourth.
  Deliberately not inherited: the 7-stage job chain, fragment planning, model-reported confidence with a flat 0.85 SQL gate, the recovery subsystem, and the no-persisted-model-output rule its own assessment called fatal for learning.
  Where the explorers assumed we lacked totals reconciliation or a negative control, they were wrong: `validate.py` carries both VAT identities and `NEG-01` is in the fixtures.
  Next: eval `--live` mode, then WP-16 with WP-19 folded in.
- 2026-08-24 - **First real photo through the hardened schema in production; currency normalization shipped.**
  The founder sent a real cash invoice (Al Aweer Fresh Vegetable Trading, 6 lines, 402.00) to the test number.
  The webhook received and enqueued it even with the dead token; media download 401'd three times; after a fresh 24 h token went into Railway the failed job was requeued by hand and ran clean on attempt 1: photo stored (sha256 matches Meta's), branch resolved, ack at +3 s, extraction with no repair round, all six lines reconciled, cash hold to `needs_review` with the owner-approval reply.
  Every schema change from this morning held in production: `tenant_id` on the run and all six lines, one invoice per document, document at `extracted` with the invoice owning the review state.
  Found and fixed the same day: the currency was read as the printed word ("dirhams") and reached the reply verbatim; `extraction/currency.py` now derives the ISO code once in the pipeline seam, the manual-entry builder, and the eval scorer (211 API tests, 13 eval tests), and the live row was corrected to AED.
  Open from the same run: the invoice date came back null (check the photo); extraction took 135 s (5,332 in / 914 out tokens) against the ~18-27 s seen before, most likely Anthropic overload that day (529s seen on other calls), so it is not the new baseline until a second forward measures it; the token in Railway is a 24 h temporary one and expires 2026-08-25 ~18:00 Dubai - the permanent system-user token is still F-track.
- 2026-08-24 - **Landing repositioned around per-item profit margin (founder call, see Decision Log).**
  New hero: "Know the profit margin on every item you sell."; the primary capability card is now Item margins with a per-item margin visual (the low-margin item highlighted as the quiet loser), supplier prices demoted to a supporting card tied to margins, and the closing banner reads "Every item. Every branch. Real margins."
  The Source proof card folded into the Built for trust section it duplicated; the grid stays three cards, no CSS changes.
  Lint, tsc and a non-mock production build pass; verified visually on a local dev server before deploying to the live Vercel production URL.
- 2026-08-24 - **Review screen deployed and wired; the M4 deploy checkbox is closed.**
  `apps/web` is live at `https://faida-web-nine.vercel.app` (Vercel project `faida-web`, root `apps/web`), built non-mock for the first time anywhere; the four web env vars are set for Production, and `API_TOKEN` + `WEB_ORIGIN` are on Railway (the first attempt failed CORS preflight on an inexact `WEB_ORIGIN`; the byte-exact origin fixed it).
  Verified live: token auth flips 401 to 200, the preflight echoes the exact origin, the list renders the real confirmed T-0084417 with no mock data and no sample badge, the detail shows the photo (signed URL, loaded at 714x1280) beside ten green-checked lines with per-item price history, the console is clean, and a waitlist signup landed exactly one normalized row browser to database before the test row was deleted.
  Known stored-data artifact, not a bug: T-0084417's totals block still shows the pre-WP-17 amber ("lines plus VAT come to 740.30") because its checks were stored before the VAT amendment; re-extraction would clear it.
  Token posture per C6: the bearer token is baked into the public JS bundle, demo data only, closed in M6; rotating it requires a Vercel redeploy, and Vercel preview deployments fail CORS by design (single-origin policy, demo from production only).
  Deploy docs added in the same commit: `API_TOKEN`/`WEB_ORIGIN` rows in the README's Railway table, a Vercel deploy section, and `apps/web/.env.example` now tracked and documenting all four web vars.
  Next: eval `--live` mode and the WP-16 accuracy loop; the latency pass; then curate the 3 demo invoices and rehearse.
- 2026-08-24 - **Live project migrated to 0010; the deploy-order debt is cleared.**
  A schema check against the live Supabase project found it at 0007 (0006/0007 had been applied since the WP-18 warning) while the code pushed this morning already writes the 0009 `tenant_id` columns.
  Applied 0008-0010 in order, each atomically, and verified: both indexes present, zero null or parent-mismatched `tenant_id`s after backfill, the one `confirmed` document remapped to `extracted`, four-state status constraint in place.
  No live damage occurred: the last job ran 2026-08-23 14:00, before the pushes, because the expired Meta token has kept the channel silent since.
  The plan header was also stale (it still listed WP-17 VAT reconciliation and WP-40 `demo_seed.sql` as gaps; both shipped 2026-08-23) and is fixed in this commit per the plan-vs-code rule.
  Next: permanent Meta system-user token into Railway + `.env` and redeploy (founder, in progress), then one test forward; then the review-screen deploy and the eval `--live` mode.
- 2026-08-24 - **Schema hardening: findings 1-4 of a full schema review fixed, migrations 0008-0010.**
  A visual schema review produced eight findings; the four that get expensive after the first paying customer are closed while migrations are still squashable.
  0008 turns the assumed one-invoice-per-document into a unique index (the pipeline's check-then-insert guard was raceable across a job's three attempts) and indexes `invoice_lines (invoice_id, position)`, which also serves the review screen's `order by position`.
  0009 adds `tenant_id` to `invoice_lines`, `supplier_item_prices` and `extraction_runs`, backfilled from and always derived from the parent row, closing the three silent exceptions to the §4 day-one tenancy rule before M6 RLS needs it.
  0010 removes `confirmed` from `documents.status` (C1 amended, see Decision Log): the document machine is ingest-only and terminal at `extracted`, the invoice owns review, and the confirm paths in `db.py` collapse to a single-statement update each.
  All 186 tests pass against a re-migrated database after each step; the backfill and status-mapping paths, dead in the empty-schema test run, were proven separately on scratch databases.
  Findings 5-8 (no FK on the `wa_message_id` text match, no sign checks on money columns, no per-invoice `position` uniqueness, remaining unindexed FKs) stay open as recorded low-severity notes.
- 2026-08-23 - **Public waitlist landing page completed and proven browser to database.**
  The root route now carries the approved supplier-price headline, full traceable-margin promise, Margin Fold identity, invoice-to-alert proof, three-step workflow, product capability breakdown, trust model, and final brand line in the Date Palm, Karak Gold and Warm Cream system.
  The email form posts to a same-origin Next.js route, which forwards to a size-limited, validated, honeypot-protected FastAPI endpoint and inserts into the RLS-protected `waitlist_signups` table with database-owned deduplication.
  Browser QA found and fixed one high-severity false-error bug caused by reading React's event target after the asynchronous request.
  A desktop browser submitted `codex.waitlist+e2e@example.com` twice and showed the success state; direct Postgres verification returned exactly one normalized `landing_page` row.
  Invalid email produced browser `typeMismatch=true` with no request, the 390 px layout had no horizontal overflow, final browser console and network checks were clean, the isolated Postgres integration suite passed 4/4, the API suite passed 104 tests, and web lint, TypeScript and production build passed.
  Evidence is in `.gstack/qa-reports/qa-report-localhost-2026-08-23.md`.
- 2026-08-23 - **Oversized invoice photos were failing extraction outright; fixed.** Found by
  measuring token cost on the fixture images rather than by any test: the Messages API rejects a
  base64 image over 10 MB (`400 ... 13588412 bytes > 10485760 bytes`), nothing in the pipeline
  resized, and a phone at full resolution clears that ceiling routinely. `PH-01` (9.7 MB) sits in
  our own fixture set and would have failed every live eval run. The failure was the quiet kind:
  document stored, deterministic 400 retried three times to no purpose, generic failure reply a
  minute later, nothing anywhere saying the photo was too big.
  `extraction/images.py` now fits an image to the limit before the vision call, and deliberately
  **only when it would otherwise be rejected** - anything already inside passes through
  byte-identical, so there is no accuracy trade to argue about (the status quo for these was not
  a worse read, it was no read). `PH-01` goes 10.2 MB -> 2.6 MB and is accepted at 4,730 input
  tokens. Whether a *lower* ceiling also helps latency and cost trades against reading small
  print on faded thermal paper, so it belongs to WP-16 with the eval to measure it. Pillow is now
  a dependency. 186 API tests, 12 eval tests.
  Next, in order: `--live` mode in `eval/run.py` (does not exist, and WP-16 needs it), then the
  accuracy loop on the phase-1 corpus, then the amber question that dead-ends on a plain-English
  answer, then the worker's 2-second poll (two job hops, so up to ~4s of the 28.43s is idle). **Corrected 2026-08-25:** that ~4s was never there. `worker.py` only sleeps when the queue is empty, so the second job starts the instant the first finishes; there is one wait, at the start, of up to 2s. The real lever was the repair round, which the WP-17 and WP-18 fixes have since stopped firing entirely.
- 2026-08-23 - **WP-18 shipped: discounts, rounding and non-stock charges.** The C4 identities
  are now stated against `line sum - discount + rounding`, so a trade discount no longer fails a
  correct invoice; C3 gains `discount_total`, `rounding_amount` and a per-line `line_kind`
  (migration 0007). Charge lines are excluded from the printed-subtotal comparison, from the
  discount base, and from the catalog entirely - the second bug found here, since a delivery line
  carrying qty and unit_price would otherwise have become a supplier item with its own price
  history and its own alerts. The discount reaches price memory pro rata over the stock lines:
  92.00 with a 5% trade discount records 87.40, because a supplier who holds list prices and
  quietly stops discounting has raised the cost, and storing the list price would draw a flat
  line straight through it.
  All 14 generated invoices now reconcile green (`EDGE-03`, a delivery note with no prices, stays
  correctly indeterminate and asks; `NEG-01` is correctly not an invoice). 179 API tests against
  real Postgres, 12 eval tests, ruff clean. One test asserts the fix itself by removing the
  discount and checking the invoice breaks by exactly 41.70.
  **Deploy order matters:** the live project is still at migration 0005, and this code inserts
  `tax_treatment`, `vat_rate`, `discount_total`, `rounding_amount` and `line_kind`. Applying 0006
  and 0007 has to come *before* the next Railway deploy, or every extraction fails on insert.
- 2026-08-23 - **WP-17 shipped: C4 now reconciles both VAT treatments.** `check_document` tries
  the exclusive identity (L + T = G) then the inclusive one (L = G with T inside), anchored on
  the line sum so an inclusive invoice printing a *net* subtotal cannot masquerade as exclusive;
  the subtotal cross-check accepts either the gross or the net figure, since both are legitimate
  printings; a GCC rate table names the rate but never gates the result, so an invoice at an
  unlisted rate that adds up still passes with a note. Migration 0006 carries `tax_treatment` +
  `vat_rate`; price memory is net-canonical, converted inside the confirm transaction from the
  invoice's own totals rather than the stored rate, so no rounding can move a recorded price.
  The today's-invoice shape now reconciles green with no question asked. 172 tests green against
  real Postgres, including one that proves a supplier switching VAT format fires **no** price
  alert - the 5%-VAT-versus-5%-threshold collision that made this net-canonical.
  Two tests had encoded the old contract and were rewritten rather than deleted: the one named
  `test_tax_inclusive_mismatch_fails_document_check` asserted precisely the behaviour that was
  the bug.
  The generated receipt set moved to `eval/fixtures/generated/` with a README stating plainly
  that it is synthetic, excluded from the §5 targets, and no substitute for F6, plus
  `eval/convert_generated.py` translating its ground truth into C3 `truth.json`. All 15 convert;
  running them through the validator puts 13 of 14 invoices green.
  The two that do not are both informative: `EDGE-03` (a delivery note with no prices) is
  correctly indeterminate and should ask, and `EDGE-01` exposed **WP-18** - discounts and
  non-stock charges break C4 exactly the way VAT did, on a perfectly-read invoice.
  Next: F6 real photos (still zero); WP-18; the permanent access token; `demo_seed.sql` + branch
  mapping; `API_TOKEN` + `WEB_ORIGIN` and a deployed review screen for the M4 gate.
- 2026-08-23 - **M0 PROVEN ON A REAL PHONE (F1-F4 closed)**, and the same forward carried
  through M1 and M2 live. Root cause of the earlier silence found by querying
  `GET /{waba-id}/subscribed_apps`: the WABA's only subscriber was Meta's own `WA DevX Webhook
  Events 1P App`, so Meta recorded each real forward in the dashboard's test-webhook panel and
  delivered nothing to us. Configuring the callback URL in the app dashboard does *not* subscribe
  the app to the WABA - that needs `POST /{waba-id}/subscribed_apps`. Publishing the app was
  **not** required, which spared the business-verification chain the plan defers to M5.
  Also fixed on the way: an expired 24-hour token (regenerated), and the token never having been
  applied to Railway (a variable change without a redeploy). Migrations 0004 + 0005 applied to
  the live project; the deployed `/api/waitlist` was exercised end to end (202, row written, row
  deleted).
  The run, from +971509772702 at 13:58:01 UTC: ack **6.70 s**; document stored with sha256 and an
  immutable path, branch resolved from the sender; `claude-opus-5` prompt v1 extracted 10 lines
  in **17.97 s** with a repair round, 7045/843 tokens; every line arithmetically green and summing
  exactly to the stated subtotal; the document-level check correctly went amber because the total
  (706.65) did not equal subtotal + tax (740.30); parsed reply at **28.43 s**; `OK` confirmed,
  `confirmed_at` written, catalog self-built to 1 supplier + 10 items + 10 price-history rows.
  Three findings, none of them infrastructure:
  (1) **VAT-inclusive invoices break C4.** The founder's answer - "the lines are inclusive of
  vat" - means extraction was *correct* and our identity is wrong. `subtotal + tax = total` does
  not hold for the GCC norm, so correct invoices go spuriously amber. This needs a C4 decision,
  not a prompt tweak, and it will hit the curated demo invoices.
  (2) **The amber question invites an answer it cannot parse.** It asks "which is right?"; the
  founder answered in plain English and got "Sorry, I didn't get that." The clarify path did its
  job of not dead-ending, but on stage that is a bad beat.
  (3) **Latency 28.43 s against the ~20 s M4 target** (WP-41's flagged risk, confirmed). Better
  than F5's ~27 s for extraction alone, and this run included a repair round.
  **Correction (same day):** that invoice was *not* real. It was `TH-01` from a set of
  prompt-generated receipts, byte-identical in supplier, invoice number, date, totals and all ten
  lines, and its ground truth carries `"synthetic": true`. It was briefly written up here as
  "corpus item #1"; **F6 is still at zero real invoices.** Two things survive the correction:
  M0's proof stands, since the channel, storage, dedupe, worker, reply and confirm all ran for
  real and only the document was generated; and extraction scored *perfectly* against that ground
  truth (all ten lines, supplier, invoice_no, date, totals exact), which is a real measurement on
  a synthetic document. A generated receipt arriving through the same door as a real one is
  indistinguishable downstream - nothing in the database says which it was.
  Next: permanent access token; F6 corpus; the C4 VAT decision; `demo_seed.sql` + branch mapping;
  `API_TOKEN` + `WEB_ORIGIN` on Railway for the review screen.
- 2026-08-23 - Webhook repointed to the Railway host (founder): callback URL set, handshake
  verified, `messages` subscribed at v26.0, which matches the `config.py` default. Meta's
  dashboard Test returned success, and since a signature mismatch is a 403 at `webhook.py:71`
  and Meta reports success only on a 200, that is production proof of signature verification.
  Three blockers found before F4 can run, none of them code:
  (1) The Meta access token is an expired 24-hour temporary token, not the system-user token the
  founder-session entry below claimed. Graph returns OAuthException 190/463 "Session has expired
  on 23-Aug-26 01:00:00 PDT" on both v21.0 and v26.0, so it is the token and not the version.
  A forwarded photo fails at media download and at the reply, and the phone shows total silence;
  `jobs` id 3 already burned its 3 attempts exactly this way. Needs a real system-user token in
  Railway Variables *and* `apps/api/.env`.
  (2) The live project is still at migration 0003: `invoices.confirmed_at` (0004) and
  `waitlist_signups` (0005) are both absent, so the demo script's "Reply OK" step and the landing
  waitlist form would both fail on stage. Apply 0004 + 0005.
  (3) That failed job called Graph v21.0 though the code has defaulted to v26.0 since 264e1bb.
  The deployed build is current - its `openapi.json` carries every Wave 7b route - so either
  `GRAPH_API_BASE` is pinned to v21.0 in Railway Variables from an early `.env` paste, or it
  self-healed on a later redeploy. One look at the Variables tab settles it.
  Unplanned win: Meta's sample payload carries a fixed message id, so the Test press deduped
  against the 11:57 UTC row through `on conflict (message_id) do nothing` (`db.py:51`) - a real
  production proof of the dedupe clause in M0's done-when. It also means the Test button cannot
  prove anything new again, since every future press dedupes against that same row.
  Next: system-user token -> apply 0004 + 0005 -> check `GRAPH_API_BASE` -> `demo_seed.sql` plus
  its branch UPDATE -> F4 phone proof.
- 2026-08-23 - M4 agent side integrated (WP-40/41/43, WP-42 verified): demo_seed.sql (closed
  demo-chain world, staged prices produce the exact alert lines, deletes rehearsal residue on
  re-run, cross-tenant safety asserted in tests), per-stage latency logs + the
  webhook_to_reply_ms summary line, Docs/DEMO_RUNBOOK.md (preconditions, 4-minute script with
  verbatim expected replies, one-command reset, failure playbook, rehearsal log). 165 API tests.
  RISK FLAGGED: extract alone measured ~27 s (F5), so the ~20 s reply target likely misses -
  rehearsal 1's latency line decides; tuning lives in WP-16 once the corpus exists. Remaining
  work is all founder-gated: webhook repoint + F4 phone proof, F6 corpus -> WP-15/16, curated
  demo invoices + two rehearsals.
- 2026-08-23 - Wave 7b integrated (WP-34 + WP-35): manual endpoint (deterministic validation +
  snapping, cash hold, 422 parity with PATCH), upload page with 3 s polling and an honest
  60 s timeout state that offers manual entry (never a dead end), manual entry form with
  per-row validation, mock demonstrating both upload outcomes; web CI job (npm ci, lint, tsc,
  build, ~1 min). The revoked-key drill is now a permanent test - M3's done-when is executable.
  162 API tests, web build clean. M3 checklist fully ticked. Next: M4 agent side (WP-40 seed,
  WP-41 latency instrumentation, WP-43 runbook); WP-42 meme path already word-perfect in
  replies.py; founder: webhook repoint + F4 phone proof + F6 corpus.
- 2026-08-23 - Wave 7a integrated: web client aligned to the implemented C6 (corrections PATCH
  body, prices envelope, mock now byte-identical to the real API incl. status codes and
  timestamps, signed-URL expiry refetch on image error); WP-32 list refinement (branch/supplier
  filters on query params, branch_name joined into list + detail, URL-preserved status tabs,
  date sort, empty states); WP-33 price sparkline (inline SVG, last point emphasized in Karak
  Gold, exact-string delta labels, sr-only value table; dataviz-skill guided). 156 API tests,
  web lint/tsc/build clean, browser-QA'd. Next: Wave 7b (WP-34 manual entry + upload, WP-35
  web CI) closes M3's checklist; revoked-key drill lands there.
- 2026-08-23 - Wave 6 integrated (WP-30 + WP-31): C6 API live (six routes, fail-closed bearer
  token, signed image URLs degrading to null, upload with type/size caps, confirm doubles as
  the cash-review path; 16 tests) and the Next.js review screen (photo + zoom left, green/amber
  fields with icons, edit-in-place, totals reconciliation strip, cash approve; brand system
  applied; mock mode default until wired). Landing stream's waitlist (web form + FastAPI
  endpoint + migration 0005) rode along cleanly. 156 API tests green, web lint/tsc/build clean.
  Known follow-up: web real-mode client shapes (PATCH body, prices envelope, branch_name)
  drifted from the implemented C6 - alignment is Wave 7a with WP-32/33.
- 2026-08-23 - Founder session: Meta credentials complete (app secret, access token, phone
  number ID) by reusing the restaurant-profit-platform app. The token was recorded here as a
  system-user token; it was in fact the 24-hour temporary one, which expired the next morning
  and blocked F4 - corrected in the webhook-repoint entry above. Graph base bumped v21 -> v26
  after probing which versions are live. Webhook proven locally against the live DB with the
  real secret: verify handshake, fail-closed on bad/absent signature, dedupe on redelivery,
  job enqueued, test rows cleaned up. Live project brought up to migrations 0002-0003 (it was
  three behind); 0004 held until the confirm-flow session commits it. Docker image built and
  booted against live config: /health 200, `PYTHONUNBUFFERED=1` added so host log panes are not
  empty. Next: F3 deploy, repoint the Meta webhook (this takes the old tool off the wire),
  F4 prove M0, and F6 corpus, which now gates M1 alone.
- 2026-08-23 - Wave 5b integrated (WP-21): confirm/correction flow live - "OK"/"okay" with
  punctuation tolerance, "line N field value" and totals corrections (all-or-nothing multi-edit),
  stateless disambiguation with leading-integer selection, clarify message that never dead-ends,
  line-out-of-range guard. Confirm = invoice + document CONFIRMED + record_confirmed_prices in
  one transaction; migration 0004 adds invoices.confirmed_at so worker retries re-ack instead of
  double-confirming. M2 gate test is a permanent e2e (alert "up AED 4.00" -> OK -> history
  [50.50, 54.50]). 136 API tests green. M2 chat side is code-complete; demo-phone proof still
  founder-gated. Next: M3 (WP-30 backend API + WP-31 review screen vs the C6 mock, in parallel).
- 2026-08-23 - Wave 5a integrated (WP-23 + WP-24 + composer wiring): price alerts computed in
  the extraction reply (both thresholds, multiplication form so zero baselines are safe, sorted
  by delta, falling prices included), baseline provably untouched until confirm; cash invoices
  persist needs_review with the cash-hold reply; non-cash persist awaiting_confirm; pipeline and
  worker fully on replies.py, local constants deleted; amber questions render from real
  post-repair state. 104 API tests green. The demo reply now reads: summary + "Karak Tea Dust
  down AED 3.25..." + "Reply OK to confirm." Next: WP-21 confirm/correction flow closes M2 chat.
- 2026-08-23 - Wave 4 integrated: WP-20 reply composer (every message shape as pure
  deterministic functions, 3-question amber cap with overflow, PriceAlert rendering, 21 tests)
  and WP-22 supplier memory (matching.py fuzzy match + snap with pack-size veto, thresholds
  0.85/0.80, migration 0003 supplier_name + idempotent price-history index, snapping wired into
  the pipeline, record_confirmed_prices ready for WP-21). 100 API tests green vs real Postgres.
  Composer wiring + M2 checkbox ticks land with Wave 5 (WP-23+24 pipeline side, then WP-21
  confirm flow, run sequentially - they share files).
- 2026-08-23 - F5 done: Anthropic key live, verified against `claude-opus-5` (auth, model
  access, billing). Ran layers 1-3 on a synthetic invoice PDF: clean extraction, document and
  all 5 lines green, repair correctly not applied. Measured 4.3k in / 421 out and ~27 s per
  document, so the demo's second WhatsApp reply lands roughly half a minute after "Got it",
  and cost is ~$0.03/invoice at Opus 5 rates. Next: F1/F3/F4 (Meta app, deploy, prove M0) and
  F6 corpus photos, which now gate WP-15/WP-16 alone.
- 2026-08-22 - Wave 3: WP-13 integrated - the full M1 loop is code-complete. extract_document
  job chained after ingest (ack stays immediate), pipeline extract -> validate -> one-round
  repair -> draft invoice + lines + checks + confidence in one transaction, extraction_runs
  telemetry (migration 0002, RLS kept), plain M1 replies incl. meme/z-report declines and the
  layer-6 failure message on final retry. 58 API tests + 12 eval tests green, smoke OK. Noted
  for WP-22: persist extracted supplier_name (0003) for matching and the review screen. Next:
  Wave 4 (WP-20 reply composer + WP-22 supplier memory in parallel).
- 2026-08-22 - Brand handover shipped under `Docs/brand/`: five geometric logo concepts,
  recommended Margin Fold system, professional color and typography guidance, positioning copy,
  SVG masters, rendered application mockups, and an image-generation exploration record. Next:
  founder approval, similarity search, and custom outlined wordmark refinement before launch.
- 2026-08-22 - Wave 2: WP-12 targeted repair integrated (targets from FAILED checks only,
  indeterminate stays amber for the question flow; one-round cap owned by MAX_REPAIR_ROUNDS;
  RepairOutcome shape ready for WP-13). 52 tests green vs real Postgres including the founder
  session's RLS migration, which this commit also carries. Next: Wave 3 (WP-13 pipeline +
  persistence).
- 2026-08-22 - Supabase live (F2): project `Faida MVP` (`wiirrenkpgyrghmclayf`, ap-south-1)
  migrated from `0001_init.sql`, private `documents` bucket created, demo tenant/branch seeded.
  Added deny-all RLS to `0001_init.sql` and applied it: 10 advisor ERRORs cleared, verified
  `anon` sees 0 rows while the owner role still reads. Live branch phone set to the founder's
  demo handset (kept out of `seed.sql`, which stays on the placeholder that CI and the tests
  pin). Next: F1/F3/F4 (Meta app, deploy, prove M0 on a real phone).
- 2026-08-22 - Wave 1 integrated: WP-10 Anthropic provider (`claude-opus-5` structured outputs
  behind the seam, adaptive thinking, PDF + image blocks, mocked-SDK tests), WP-11 deterministic
  validation (`validate.py`, checks shape ready for WP-13, wrong-never-green invariant), WP-14
  eval harness (scorer, recorded provider, 3 fixtures, CI smoke steps). 41 API tests green vs
  real Postgres + 12 eval tests + smoke OK. Next: Wave 2 (WP-12 repair); WP-15/WP-16 wait on
  founder F5 (API key) + F6 (corpus photos).
- 2026-08-22 - Wave 0 shipped: contracts pinned in code (`contracts.py`: C1 status machines +
  C2 job kinds; `extraction/schema.py` + `provider.py`: C3; `extraction/constants.py`: C4
  tolerances + alert thresholds); webhook/worker wired to them; 17 tests green (13 existing +
  4 new contract tests) against real Postgres. Next: Wave 1 fan-out (WP-10 + WP-11 + WP-14 in
  parallel) on the agent side; F1-F4 founder sitting + F5 API key on the founder side.
- 2026-08-22 - Execution plan added as §7 (founder track F1-F8, contracts C1-C7, work packages
  WP-10 through WP-43, delegation waves + protocol); M1-M3 checklists tied to WPs; M3 backend
  gap closed; price-alert timing, confirmation rule, CI eval policy, and English-only demo
  language pinned; later sections renumbered §8-13. Next: Wave 0 contract pinning (agents) +
  F1-F4 founder sitting (~2.5 h).
- 2026-08-22 — M0 code complete: repo scaffold (`apps/api`, `apps/web` stub, `supabase/`,
  `eval/` stub), migration 0001 + seed, FastAPI webhook + Postgres-job worker + canned replies,
  13 tests green (incl. e2e flow vs real Postgres), CI + Dockerfile + README setup guide.
  Next: founder does README §M0 (Meta app, Supabase project, deploy), then prove M0 on a real
  phone and tick the last boxes.
- 2026-08-22 — Plan created. Next: M0 — Meta app + webhook service live.

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR (PLAN) | 23 issues, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |
| Outside Voice | `/plan-eng-review` (codex) | Cross-model plan challenge | 1 | ISSUES_FOUND | 15 findings, all resolved |

Scope: M5 raw materials (WP-50 to WP-55), reviewed 2026-08-29 at commit `c50daf3` against the code it
builds on. Mode: SCOPE_REDUCED — a Step 0 complexity challenge cut four items (a duplicate module, a
duplicate screen, a `container_conversions` table, and an unread column) before any review section ran.

**CODEX:** 15 findings from an independent read of the repository. Three changed the shape of the
milestone rather than its details, and the eng review had missed all three: a stored `ingredient_costs`
row written at confirm time can never be populated (supplier items are created during confirm with no
material attached, and mapping happens afterwards), confirm and price-recording are two transactions
with an unrecoverable gap that 409s for ever from the review screen, and no cost can honestly read
*verified* because pack size appears in no arithmetic identity. All 15 resolved by founder call.

**CROSS-MODEL:** Five tension points, all put to the founder individually. Codex overturned one eng-review
decision outright — ordering the price per kilo by confirm time, which the review had defended partly on a
demo consequence that does not exist, since neither seed file inserts any invoice or invoice line. Reversed
to printed invoice date. On two others the models agreed on the problem and differed on the cure, and the
simpler cure won both times: deriving the material price rather than adding refresh triggers to a stored one,
and unmap/remap rather than a mapping-state table. Half of Codex's finding 10 (audit events as operational
state) was judged overstated and declined with reasons; its other half (no undo path) was accepted.

**VERDICT:** ENG CLEARED — ready to implement, pending founder go-ahead on the revised six work packages.

NO UNRESOLVED DECISIONS
