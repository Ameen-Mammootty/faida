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
2. `worker.py` is an asyncio loop in the same process polling the `jobs` table (`FOR UPDATE SKIP LOCKED` claim, 3 attempts, 30 s backoff). It downloads media promptly (Meta URLs expire), sha256-hashes it, stores the immutable original in Supabase Storage at `{tenant_id}/documents/{document_id}/original` (never overwritten, `x-upsert: false`), records the `documents` row, and sends the canned reply. Job handlers must be idempotent under retries.
3. `db.py` is a thin asyncpg layer: plain SQL, no ORM. Postgres holds data and constraints; business logic lives in Python, never in SQL functions.
4. `wa.py` and `storage.py` are thin httpx clients for the Meta Graph API and Supabase Storage. Both accept an injected transport, so tests mock Meta and storage at the transport layer (see `tests/conftest.py`), never at the client layer.
5. `provenance.py` records where every stored number came from (C8): a flat jsonb on `invoices.provenance` keyed by field path, each carrying `origin` (`extracted` / `repaired` / `corrected_chat` / `corrected_screen` / `reconstructed` / `manual`), actor and time. Derived, never self-reported - the repair round is attributed by diffing the invoice before and after the merge. `audit_events` is the matching record of *human* decisions and is written inside the transaction it describes; `extraction_runs` stays the record of *model* runs. Actors are free text (`whatsapp:<phone>`, `console`) until M7 brings real accounts, and are never taken from a client header.

One door for everyone: a correction from the review screen and a "line 4 qty 16" text run the same function (`confirm._apply_correction`), and manual entry runs the same validation and snapping as a photo. A new write path - human or model - goes through that door too, and names its actor.

Tenancy: every tenant-owned row carries `tenant_id` from day one.
Branch is resolved from the sender phone (`branches.wa_phone_e164`), never from document text.
RLS enforcement is deferred to M7; the demo runs single-tenant seeded.

Extraction (M1+): Claude Opus 5 (`claude-opus-5`) via the Anthropic SDK with structured outputs, behind one thin provider interface so the provider swaps in one place.
Accuracy is a pipeline property, not a prompt property: deterministic arithmetic reconciliation, one scoped repair pass, supplier-memory snapping, and derived (never self-reported) confidence.
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

Rounded AED headline numbers; exact figures only in invoice detail.
No jargon; colour never carries meaning alone.
Purchases ÷ net sales is never labelled "food cost %", and branch contribution is never labelled net profit.
