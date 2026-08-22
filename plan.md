# Faida — MVP Build Plan (live file)

> **This is the live build file.** Every working session starts by reading it and ends by updating it:
> tick the boxes you closed, add a dated line to the Progress Log, and record any decision that
> changed in the Decision Log — in the **same commit** as the code. If this file and the code
> disagree, the code is right and this file has a bug: fix the file.

- **Product:** Faida — profit visibility for GCC cafeterias and multi-branch karak/paratha chains, fed through WhatsApp.
- **Reference:** `Docs/PRD.md` (v2). This plan sequences the build; the PRD owns product intent. Where they conflict on *scope timing*, this plan wins.
- **Start date:** 2026-08-22
- **Current milestone:** M0 (not started)

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
  Arabic/English mixes, karak-supplier delivery notes. Owner: collect from the pilot contacts.
  (Blocker if we can't get real ones: start with 10 photographed from local suppliers, keep growing.)
- **Ground truth:** one JSON per invoice, hand-verified, same schema as extraction output.
- **Runner:** `python -m eval.run` → scores field-level accuracy (exact for numbers/dates, fuzzy
  ≥0.9 for names), line recall/precision, reconciliation rate, repair-pass lift, cost and latency
  per invoice. Prints a table; writes `eval/results/<date>.json` so runs are comparable.
- **Targets (demo gate):** totals and amounts ≥98% field accuracy; line-item fields ≥95%;
  100% of confirmed invoices arithmetically reconciled; zero silent wrong numbers (a wrong value
  must be amber, never green).
- Every pipeline change runs the eval before merge. Prompt tweaks without the eval are guessing.

---

## 6. Milestones — demo track (M0–M4)

Sized for focused build days with CC assistance. Each has a **Done when** that is demonstrable,
not documentary.

### M0 — Channel live (Day 1–2)
- [ ] Meta developer app + WhatsApp Cloud API test number; register 2 demo phones
- [ ] FastAPI service deployed (Railway/Fly) with public webhook URL; signature verification
- [ ] Webhook: verify → dedupe on `message_id` → store raw payload (`wa_messages`) → download +
      store media in Supabase Storage (`documents`, sha256, immutable) → enqueue job → return 200 fast
- [ ] Canned reply loop working ("Got it — reading your invoice…")
- [ ] Supabase project + initial migration (the 8 tables + `wa_messages` + `jobs`)
- **Done when:** a real phone forwards a photo and gets a reply within seconds; the image is in
  storage; sending the same message twice creates one document.

### M1 — Extraction pipeline + eval harness (Day 3–6)
- [ ] Provider interface + Claude Opus 5 structured extraction (layer 1)
- [ ] Classifier step: invoice / not-an-invoice (polite decline for memes)
- [ ] Arithmetic reconciliation + targeted repair pass (layers 2–3)
- [ ] Eval corpus ≥15 invoices with ground truth; runner + scores wired into CI (3-invoice smoke)
- [ ] Iterate prompt/pipeline until targets in §5 are met on the corpus
- **Done when:** eval report hits the accuracy targets, and a forwarded photo produces a stored
  draft invoice with per-field checks.

### M2 — Confirm flow, supplier memory, price alerts (Day 7–9)
- [ ] WhatsApp reply template: supplier, line count, total, amber-field question(s), price alerts,
      "Reply OK to confirm"
- [ ] "OK" / correction parsing (OK, or "line 4 qty 16"-style fix, or numbered options) → status
      `confirmed`; corrections re-run validation
- [ ] Supplier matching + item snapping + `last_price`/`prev_price` update on confirm (layer 4)
- [ ] Price alert fires when confirmed price differs from `last_price` beyond threshold
- [ ] Cash invoices (`payment_kind = 'cash'`) marked and held as `needs_review` — approval UI comes
      later (M6); the distinction is captured now, per PRD §21
- **Done when:** two invoices from the same supplier a week apart produce a correct
  "X up AED Y" alert in chat, and "OK" records the invoice.

### M3 — Review screen (Day 10–12)
- [ ] Next.js app with the one screen: invoice photo left, extracted fields right, green/amber per
      field, edit-in-place for amber fields, confirm button
- [ ] Invoice list (by branch, by supplier) with status chips
- [ ] Price-trend sparkline per supplier item (from `supplier_item_prices`)
- [ ] Manual invoice entry form (`source = 'manual'`) — the vision-outage fallback
- **Done when:** every number on the screen traces to the photo beside it; an amber field can be
  fixed and confirmed in the browser; with the Anthropic key revoked, upload + manual entry +
  all screens still work.

### M4 — Demo hardening + rehearsal (Day 13–15) — **DEMO GATE**
- [ ] Seed demo tenant: 1 chain, 3 branches, 2 suppliers with 3 weeks of price history (so the
      live alert fires on stage)
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

## 7. Milestones — from demo to MVP (M5–M9)

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

## 8. Testing strategy

| Layer | What | Gate |
|---|---|---|
| Eval harness | Real-invoice corpus, ground truth, scored per §5 | Accuracy targets before M4; no regression after |
| E2E (few, real) | Webhook→extract→confirm→record; duplicate send; meme decline; provider-outage fallback; (M6+) cross-tenant worker rejection | Green in CI on every PR |
| Unit | Deterministic money math, reconciliation, snapping, template filler | Cheap and thorough — this is where determinism pays |
| Manual, on a phone | The full demo script | Before every demo and every milestone close |

Banned: tests that assert on code text, tests of framework behavior, coverage targets for their
own sake.

## 9. Costs (demo through pilot)

Supabase free tier → $25/mo; Railway/Fly ~$5–10/mo; Vercel free; WhatsApp in-window replies free,
test number free; extraction ≈ $0.05–0.15/invoice (Opus 5, incl. repair pass) → a 75-branch chain
at ~10 invoices/branch/day is ~$40–110/day at scale pricing — fine at AED 99/branch, trivial at
pilot volume. Meta utility template cost applies only from M9 (verify live UAE rate then).

## 10. Risks

| Risk | Mitigation |
|---|---|
| Meta/WABA production chain is slow, external, serial | Start it at M5, track in this file; demo runs on the free test number meanwhile |
| Real invoices are worse than the eval corpus (handwriting, mixed language) | Grow the corpus from every pilot failure; the repair pass + amber-question flow degrades gracefully instead of silently |
| Invoice forwarding doesn't become a habit (the behavioral risk) | Pilot gate in M10 measures *unprompted* forwards; if the habit doesn't form, that's a product finding to face, not to engineer around |
| Central purchasing at target chains (no per-branch invoices) | First question asked of any pilot chain, before onboarding them |
| Scope creep back toward the old build | §2 rules; anything not in a milestone needs a customer quote and a Decision Log entry |

## 11. Decision Log

| Date | Decision | Why |
|---|---|---|
| 2026-08-22 | Fresh build; previous restaurant-profit-platform is reference-only, no code carried over | Over-engineering post-mortem; schema *ideas* only |
| 2026-08-22 | Deleted `Docs/DESIGN.md`; this plan is the single sequencing document alongside `Docs/PRD.md` | Founder call |
| 2026-08-22 | Demo-first sequencing (M0–M4) ahead of full MVP phases | WhatsApp accuracy is the wedge and the sale |
| 2026-08-22 | Meta Cloud API direct for the demo; Twilio only as an unblock fallback | Free, production-shaped |
| 2026-08-22 | Inventory ledger / stock counts / goods receipts deferred beyond MVP | Needs recipes + proven data habit first; schema keeps the door open |

## 12. Progress Log

*(newest first — one line per session: date, what shipped, what's next)*

- 2026-08-22 — Plan created. Next: M0 — Meta app + webhook service live.
