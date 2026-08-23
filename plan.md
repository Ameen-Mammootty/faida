# Faida — MVP Build Plan (live file)

> **This is the live build file.** Every working session starts by reading it and ends by updating it:
> tick the boxes you closed, add a dated line to the Progress Log, and record any decision that
> changed in the Decision Log — in the **same commit** as the code. If this file and the code
> disagree, the code is right and this file has a bug: fix the file.

- **Product:** Faida — profit visibility for GCC cafeterias and multi-branch karak/paratha chains, fed through WhatsApp.
- **Reference:** `Docs/PRD.md` (v2). This plan sequences the build; the PRD owns product intent. Where they conflict on *scope timing*, this plan wins.
- **Start date:** 2026-08-22
- **Current milestone:** M0-M4 agent-side code complete; webhook repointed 2026-08-23. Founder-gated: a fresh system-user token + migrations 0004/0005 on the live project, then the M0 phone proof (F4); corpus photos (F6) for the accuracy loop (WP-15/16); demo rehearsals (M4 gate)

---

## 1. North star and the one demo that matters

The MVP proves one thing (PRD §1): *a cafeteria forwards supplier invoices and daily sales to a
WhatsApp number and understands which items, ingredients, and branches are helping or harming
profit.*

The **near-term goal is a demo** whose entire job is to make one loop look effortless and
provably accurate:

```
Forward invoice photo on WhatsApp
   → parsed reply in chat, with a price alert   ("Milk powder up AED 4 since last week")
   → reply "OK"
   → invoice recorded; web screen shows photo beside extracted fields, green per field
```

Everything in M0–M4 serves that loop. Everything after it grows the loop into the MVP without
rewriting it.

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
| Extraction model | **Claude Opus 5** (`claude-opus-5`) via the Anthropic Python SDK, structured outputs (`client.messages.parse()` with a strict Pydantic schema), adaptive thinking left on | Accuracy is the demo. Cost ≈ $0.05–0.15/invoice incl. repair pass — irrelevant at demo volume. Provider call sits behind one thin interface (PRD §25.1) so it swaps in one place. |
| Database + storage + auth | **Supabase** (Postgres, Storage, later Auth + RLS) | Rented foundations. Free tier for the demo. |
| Background work | **A `jobs` table + an async worker loop inside the same process** | Demo volume is one message at a time. A durable queue/broker is banned until job volume proves the need (revisit at M6). |
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
RLS enforcement is deferred to M6 — the demo runs single-tenant seeded.

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

Plus two operational tables: `wa_messages` (message_id UNIQUE, direction, from_phone, type,
payload, status — the dedupe + audit spine) and `jobs` (id, kind, payload, status, attempts,
last_error). Sales tables arrive in M5, users/roles in M6, recipes/costing in M7.

Migration policy: plain SQL files in `supabase/migrations/`, squashed freely until first customer.

---

## 5. The accuracy engine (the heart of the build)

"Very accurate" is a pipeline property, not a prompt property. Six layers, in order:

1. **Extraction call.** Image → Claude Opus 5 with a strict schema: supplier block, invoice no,
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

- **Corpus:** 20–25 *real* invoices from the target segment — crumpled thermal paper, handwritten
  Arabic/English mixes, karak-supplier delivery notes. Currently in hand: a handful (<10).
  Founder task F6 (§7.1): photograph these properly (flat + angled + crumpled variants of each)
  and keep collecting from pilot contacts; every later pilot failure joins the corpus.
- **Ground truth:** one JSON per invoice, hand-verified, same schema as extraction output.
- **Runner:** `python -m eval.run` → scores field-level accuracy (exact for numbers/dates, fuzzy
  ≥0.9 for names), line recall/precision, reconciliation rate, repair-pass lift, cost and latency
  per invoice. Prints a table; writes `eval/results/<date>.json` so runs are comparable.
- **CI policy:** the CI smoke runs 3 fixture invoices against *recorded* provider responses - no
  API key, no spend, no flakiness in CI. The full live eval runs on demand before any pipeline
  change merges; recorded fixtures are regenerated whenever the prompt version bumps.
- **Targets (demo gate):** totals and amounts ≥98% field accuracy; line-item fields ≥95%;
  100% of confirmed invoices arithmetically reconciled; zero silent wrong numbers (a wrong value
  must be amber, never green).
- Every pipeline change runs the eval before merge. Prompt tweaks without the eval are guessing.

---

## 6. Milestones — demo track (M0–M4)

Sized for focused build days with CC assistance. Each has a **Done when** that is demonstrable,
not documentary. The WP-, F-, and C-identifiers in the checklists are defined in the execution
plan (§7).

### M0 — Channel live (Day 1–2)
- [ ] Meta developer app + WhatsApp Cloud API test number; register 2 demo phones
      *(founder, ~1 h — step-by-step in README §M0)*
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
  storage; sending the same message twice creates one document. ← *needs the two founder
  steps above, then the README §M0 "Prove M0" checklist.*

### M1 — Extraction pipeline + eval harness (Day 3–6)
- [x] Anthropic API key with billing enabled (F5, 2026-08-23); verified live against
      `claude-opus-5`: a synthetic invoice extracts clean, all checks green, no repair
- [x] Provider interface + Claude Opus 5 structured extraction (layer 1); classification
      (invoice / z_report / other, polite decline for memes) happens inside the same structured
      call - a separate classifier call adds cost and latency for nothing at demo volume (C3, WP-10)
- [x] Arithmetic reconciliation + targeted repair pass (layers 2–3) (C4, WP-11, WP-12)
- [x] Pipeline orchestration + persistence: `extract_document` job, status transitions, draft
      invoices + lines + checks, run metadata, failure + meme decline paths (C1, C2, WP-13)
- [ ] Eval corpus ≥15 invoices with hand-verified ground truth (currently <10 - F6, F8, WP-15);
      runner + scores (WP-14); CI smoke = 3 recorded fixtures (§5 CI policy)
- [ ] Iterate prompt/pipeline until targets in §5 are met on the corpus (WP-16)
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
      later (M6); the distinction is captured now, per PRD §21 (WP-24)
- **Done when:** two invoices from the same supplier a week apart produce a correct
  "X up AED Y" alert in chat, and "OK" records the invoice. This gate becomes a permanent e2e
  test in CI from the moment it first passes.

### M3 — Review screen (Day 10–12)
- [x] Backend API for the screen (C6): invoice list/detail with signed image URLs, field patch
      (re-validates), confirm, manual upload, price history; demo access via one shared-secret
      bearer token, real auth arrives in M6 (WP-30)
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

### M4 — Demo hardening + rehearsal (Day 13–15) — **DEMO GATE**
- [x] Seed demo tenant: 1 chain, 3 branches, 2 suppliers with 3 weeks of price history (so the
      live alert fires on stage) - `supabase/demo_seed.sql`, idempotent, doubles as the
      one-command rehearsal reset (WP-40)
- [ ] Curate the 3 demo invoices; run each through the full loop 5× — flakiness is a bug
- [ ] Latency pass: forward → reply under ~20s (stream nothing; the reply is one message)
- [ ] Failure demo path: forward a meme, get the polite decline (shows discipline, sells trust)
- [ ] Full rehearsal of the exact script, twice, on the demo phones
- **Done when:** the demo runs end-to-end twice in a row with zero intervention.

**Demo script (keep to 4 minutes):** forward invoice → reply appears with price alert → "OK" →
open review screen: photo beside data, all green → show the sparkline for the item that moved →
forward a meme → polite decline. Close on: "no app, no login, no training — the salesman already
knows how to do this."

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
| F1-F4 | The unticked M0 founder boxes in §6, in order (Meta app + demo phones, deploy, prove M0 on a real phone). F2 (Supabase project + bucket) done 2026-08-22 | one ~2 h sitting | end-to-end reality for everything |
| F5 | ~~Anthropic API key with billing enabled~~ done 2026-08-23, verified live | ~10 min | running extraction (WP-16); building it needs nothing |
| F6 | Corpus growth: photograph the invoices in hand (flat + angled + crumpled variants of each); keep collecting toward 20-25 real ones from pilot contacts | ongoing | WP-15, WP-16 |
| F7 | Pilot logistics: pick the target chain; ask the central-purchasing question (§11) before any onboarding talk; schedule the demo only after the M4 gate passes | ongoing | M4 |
| F8 | Hand-verify every ground-truth file the labeling agent produces. Truth no human checked is not truth | per batch | eval validity |

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
  subtotal, tax, total, plus a top-level classification (invoice / z_report / other). One
  structured vision call classifies and extracts together. Provider protocol:
  `extract(image, mime)` and `repair(image, mime, targets)`; model id + prompt version recorded
  on every run.
- **C4 - Money + tolerances.** `Decimal` in Python, `numeric` in Postgres, never float. Line
  check: |qty × unit_price - line_total| ≤ max(0.05, 0.5% of line_total). Document check:
  |Σ line_totals + tax - total| ≤ 0.10, with the extracted subtotal cross-checked against the
  line sum when present (§5 layer 2). Constants live in one module; the eval scores against the
  same constants.
- **C5 - Confirmation resolution (no new table).** An inbound text from phone P resolves against
  the newest `awaiting_confirm` invoice whose document traces back to sender P. None pending →
  onboarding reply. Several pending → numbered list; a bare "OK" then asks which. Derived from
  existing tables until real usage demands more.
- **C6 - Web API surface.** `GET /api/invoices` (branch/supplier/status filters),
  `GET /api/invoices/{id}` (fields, checks, confidence, signed image URL),
  `PATCH /api/invoices/{id}/fields`, `POST /api/invoices/{id}/confirm`, `POST /api/documents`
  (manual upload), `GET /api/supplier-items/{id}/prices`. Demo access: one shared-secret bearer
  token from an env var; real auth is M6. Pinned now so web work can start against a mock.
- **C7 - Migrations.** Each WP appends its own numbered SQL file; the manager squashes
  periodically (§4 policy). No two parallel agents touch the same migration file.

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
| 15 | Ground truth for the current corpus: agent transcribes, founder verifies (F8); 3 become the CI fixtures | S | 14, F6 | founder sign-off on every file |
| 16 | Accuracy loop: live eval → inspect failures → one change per round → re-eval, until §5 targets hold | L | 13-15, F5, F6 | the eval report, not opinion |

**M2 (confirm flow, supplier memory, alerts)**

| WP | What | Size | Depends | Acceptance |
|---|---|---|---|---|
| 20 | Reply composer (`replies.py`): English templates for summary, alerts, amber questions, cash hold, failure, decline | S/M | 13 | pure functions, every message shape unit-tested, zero generation |
| 21 | Confirm/correction flow: C5 routing; "OK", "line 4 qty 16", numbered answers; corrections re-validate and re-reply | M/L | C5, 13, 20 | e2e: confirm; correct-then-confirm; OK with nothing pending; two-pending disambiguation |
| 22 | Supplier memory (`matching.py`): alias match, fuzzy snap (single tunable threshold), on-confirm item create + price update + history append | M | schema | messy real corpus names snap correctly; history append idempotent per invoice |
| 23 | Price alerts per the §6 M2 rule (thresholds as constants in one module) | S | 20, 22 | alert shows in the extraction reply; baseline untouched until confirm |
| 24 | Cash hold: `payment_kind = 'cash'` → `needs_review` + reply notes approval pending | S | 13, 20 | e2e test |

**M3 (review screen)**

| WP | What | Size | Depends | Acceptance |
|---|---|---|---|---|
| 30 | Backend API per C6 + signed URLs + shared-secret auth + CORS | M | M2 data | e2e: patch an amber field, confirm, status flips; unauthorized rejected |
| 31 | Next.js scaffold (App Router, TypeScript, Tailwind, Vercel) + the review screen | L | C6 (mock until 30 lands) | §3 money-display rules hold; amber/green carry an icon or label, never colour alone |
| 32 | Invoice list + status chips + filters | S/M | 31 | |
| 33 | Price-trend sparkline per supplier item | S | 30 | |
| 34 | Manual entry + upload fallback (`source = 'upload' / 'manual'`) | M | 30 | revoked-key drill: with no Anthropic key, upload + manual entry + every screen still work |
| 35 | Web CI job (lint + typecheck + build) | S | 31 | total CI stays under 5 minutes |

**M4 (demo gate)**

| WP | What | Size |
|---|---|---|
| 40 | Demo seed script: 1 chain, 3 branches, 2 suppliers, 3 weeks of price history; idempotent, targets the real project | S/M |
| 41 | Hardening: per-stage latency logs (webhook, download, extract, repair, reply); forward → reply under ~20 s; each demo invoice through the loop 5×; every flake fixed, never retried around | M |
| 42 | Meme decline path, word-perfect | S |
| 43 | Demo runbook with reset steps between rehearsals; founder rehearses twice (F7) | S |

### 7.4 Delegation waves

```
Wave 0  (manager)  pin C1-C7 in one small change      | founder: F1-F4 sitting
Wave 1  WP-10 + WP-11 + WP-14 in parallel             | founder: F5, F6
Wave 2  WP-12 + WP-15
Wave 3  WP-13, then WP-16 accuracy loop (needs F5+F6)
Wave 4  WP-20 + WP-22, then WP-21 + WP-23 + WP-24     (overlaps WP-16: product code does not wait on prompt tuning)
Wave 5  WP-30 + WP-31, then WP-32-35                  (web starts against the C6 mock)
Wave 6  WP-40-43 → M4 gate → demo                     | founder: F7 rehearsals
```

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

## 8. Milestones — from demo to MVP (M5–M9)

Sequenced so each milestone ships something a pilot customer uses that week. Re-estimate at M4.

### M5 — Sales ingestion + the first ratio (Week 4–5)
The demo captures cost; profit visibility needs sales against it.
- [ ] CSV/Excel sales upload (branch, date, net sales) with a reusable column mapping; layout
      change stops for review, never silently shifts columns (PRD §10)
- [ ] Z-report photo via WhatsApp → same extraction pipeline, `z_report` document type,
      summary-level only — **never turned into fake receipts** (PRD §10)
- [ ] `sales_daily` table (tenant, branch, business_date, net_sales, source, granularity)
- [ ] First analytic on the dashboard: **purchases ÷ net sales (cash basis)** per branch per
      period, ranked, with a completeness/freshness label on every row. Never labelled
      "food cost %" — it isn't one.
- [ ] **Start the Meta production chain now (external, slow):** legal entity docs → Meta Business
      verification → WABA → purchased verified sender → submit daily-brief template in the
      **utility** category. Track status here: `[ ] entity  [ ] verification  [ ] WABA  [ ] sender  [ ] template`
- **Done when:** a week of real sales + real invoices for one branch renders a ranked branch table
  where every purchase number drills down to an invoice photo.

### M6 — Auth, tenancy enforcement, approvals (Week 6–7)
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
- [ ] `audit_events` table wired to: invoice confirm/correct, cash approval, price change, role change
- **Done when:** two seeded tenants cannot see each other's data through API, storage URL, or
  worker path; a cash invoice cannot post without an approval record.

### M7 — Recipes + costing, consultant-loaded (Week 8–9)
Done-for-you onboarding (PRD §16) — the customer never touches a recipe form.
- [ ] Internal-only batch loader: ingredients, recipes (batch-yield as the norm: "one pot → 40
      cups"), packaging, unit conversions — CSV in + a review grid, consultant is the recorded actor
- [ ] Recipe templates applied across branches with per-branch overrides
- [ ] Latest-purchase-price cost per ingredient (PRD §19) — already accumulating since M2
- [ ] Recipe cost + **coverage-by-sales-value** ("complete costing covers 78% of sales value") so
      consultants prioritise high-impact items
- **Done when:** one real menu loads from a spreadsheet in under a day of consultant time and every
  costed item shows its cost basis and coverage.

### M8 — Contribution, signals, dashboards (Week 10–11)
- [ ] Item contribution = net item sales − ingredient cost − packaging (deterministic, versioned
      calculation runs with lineage back to invoices + recipe versions — PRD §23)
- [ ] Branch contribution estimate — **never labelled net profit**
- [ ] Deterministic signals: popular-low-margin items, supplier price spikes, branch gaps (PRD §25.3)
- [ ] Owner dashboard: yesterday's sales, branch league (now backed by real costing), top/bottom
      items, pending approvals, data freshness; branch dashboard: my sales, invoices to confirm
- [ ] Every headline carries its §24-style quality status (verified / estimated / incomplete)
- **Done when:** an owner can answer "which item and which branch is hurting me" from one screen,
  and every number traces to source.

### M9 — Daily WhatsApp brief (gated on Meta approval from M5)
- [ ] Deterministic template filler: net sales, est. food-cost %, biggest price move, one flagged
      issue (PRD §27.4) — fixed sentence shapes, number slots, no generation
- [ ] Send via approved utility template outside the 24-h window; tap-through opens the dashboard
- **Done when:** the owner's phone receives a real brief at 7am with yesterday's real numbers.

### M10 — Pilot hardening → first paying chain
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
| E2E (few, real) | Webhook→extract→confirm→record; duplicate send; meme decline; provider-outage fallback; (M6+) cross-tenant worker rejection | Green in CI on every PR |
| Unit | Deterministic money math, reconciliation, snapping, template filler | Cheap and thorough — this is where determinism pays |
| Manual, on a phone | The full demo script | Before every demo and every milestone close |

Banned: tests that assert on code text, tests of framework behavior, coverage targets for their
own sake.

## 10. Costs (demo through pilot)

Supabase free tier → $25/mo; Railway/Fly ~$5–10/mo; Vercel free; WhatsApp in-window replies free,
test number free; extraction ≈ $0.05–0.15/invoice (Opus 5, incl. repair pass) → a 75-branch chain
at ~10 invoices/branch/day is ~$40–110/day at scale pricing — fine at AED 99/branch, trivial at
pilot volume. Meta utility template cost applies only from M9 (verify live UAE rate then).

## 11. Risks

| Risk | Mitigation |
|---|---|
| Meta/WABA production chain is slow, external, serial | Start it at M5, track in this file; demo runs on the free test number meanwhile |
| Real invoices are worse than the eval corpus (handwriting, mixed language) | Grow the corpus from every pilot failure; the repair pass + amber-question flow degrades gracefully instead of silently |
| Invoice forwarding doesn't become a habit (the behavioral risk) | Pilot gate in M10 measures *unprompted* forwards; if the habit doesn't form, that's a product finding to face, not to engineer around |
| Central purchasing at target chains (no per-branch invoices) | First question asked of any pilot chain, before onboarding them |
| Scope creep back toward the old build | §2 rules; anything not in a milestone needs a customer quote and a Decision Log entry |
| Founder track stalls (Meta setup, corpus) while agents sprint ahead | F1-F4 scheduled as one sitting now; F6 corpus growth checked at every milestone close |
| Parallel agents drift on interfaces | C-contracts (§7.2) pinned before fan-out; contract changes are manager-only, through the Decision Log |
| Accuracy loop burns days on a too-small corpus | Targets phase in as the corpus grows; every failure joins the corpus; escalate to the founder if it is under 15 invoices when WP-16 starts |
| CI eval fixtures silently diverge from live behaviour | Recorded fixtures regenerated on every prompt-version bump, checked each WP-16 round |

## 12. Decision Log

| Date | Decision | Why |
|---|---|---|
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
