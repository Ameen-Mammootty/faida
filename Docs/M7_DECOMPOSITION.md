# M7 decomposition - auth, tenancy enforcement, approvals (reviewed 2026-09-03)

Status: **eng-reviewed 2026-09-03** (`/plan-eng-review`, scope reduced, outside voice absorbed - see the report at the end).
Approved to build by the founder the same day: the rows in §4 are in `plan.md` §7.3 as WP-70 to WP-76, C10 and the amendments in §7.2, the decisions in §5 in the Decision Log, and the TODOS in §9 in `TODOS.md`.
This file stays as the milestone's record: contracts, failure modes, the cutover order and the review report.
WP-73 and WP-71 shipped on 2026-09-03 from their briefs, before this record reached master; both match their rows, and WP-73's one boundary (the worker's by-id reads wait for WP-72) is in the Decision Log.
WP-72 shipped the same day and closed that boundary: the worker's reads are scoped by the tenant the job carries, and an unknown phone creates nothing.
M6 was decomposed, reviewed with an outside voice, and only then approved to build; M7 follows the same path.

Plan reference: `plan.md` §8 M7 (the checklist and the done-when), §7.2 C2, C6 and C8 (the contracts M7 amends), PRD §4 (roles), §21 (cash approval), §26 (tenancy isolation).

## 1. What M7 is for

The demo ran seeded and single-tenant behind one shared secret; a pilot cannot.
M7 makes the product safe to put a second cafeteria on: every request knows who is asking, every row is read and written inside that person's tenant, the worker refuses work it cannot place, and the one approval PRD §21 makes non-negotiable exists.

**Done when** (from `plan.md` §8, plus one clause): two seeded tenants cannot see each other's data through the API, a storage URL, or the worker path; a cash invoice cannot post without an approval record; and the shared bearer token is gone from every environment.

**Scope, decided in review (D2):** one app role, `tenant`.
The branch side of PRD §21's "branch raises, owner approves" is the WhatsApp phone, which never logs in; the screen only needs an owner.
The branch role, branch-level scoping and the users screen are recorded in `TODOS.md` with their triggers (§9).

## 2. What exists today, and what is wrong with it

Facts from the code as of master `25d81d3`, so the review argued about the plan and not about the state.

- Access is one shared bearer token (`require_api_token`, `apps/api/src/faida_api/api.py`), compared in constant time, fail-closed when unset.
  The same token is baked into the public web bundle as `NEXT_PUBLIC_API_TOKEN`, so it is public by construction (README calls this the accepted C6 posture until M7).
- Tenant scope is not taken from the request at all.
  `db.default_tenant_id()` returns the oldest tenant, and every `/api/*` read and write resolves through it (`_tenant(db)` in `api.py` and `menu.py`, and three direct callers).
  `db.list_invoices` (`db.py:535`) has no tenant filter; every by-id read (`get_invoice`, `get_supplier_item`, `get_menu_item`, `get_document`, `get_ingredient`) is keyed on the UUID alone.
- `documents.branch_id` and `invoices.branch_id` are plain `references branches(id)` (`0001_init.sql:47`, `:62`), no composite tenancy key.
  The API already refuses a foreign branch on upload and manual entry (`api.py:643`, `:770`); the database does not.
- The worker maps a sender phone to a branch and, when there is none, **falls back to the default tenant** (`worker.process_wa_message`), pinned by `test_unknown_sender_still_ingests_with_default_tenant`.
  An unknown phone can therefore create an invoice in the live tenant and confirm it with "OK".
- `process_wa_message` is not idempotent under retry: a failed ack re-runs the handler, and each run enqueues another `extract_document` for the same document.
  `RETRY_BACKOFF_SECONDS = 30` (`db.py:21`) and extraction finishes in about 18 s, so the retry always arrives after the first extraction is `done`.
  The invoice path is guarded (`invoices_document_uidx`); a not-an-invoice photo is re-read and declined once per retry.
- Cash invoices are held as `needs_review` (WP-24), and `confirm_reviewed_invoice` lets anyone holding the token confirm one from the screen with no reason recorded.
  `payment_kind` is not a correctable field (`api.py` `Correction.field`, `confirm.py`), so a misread "cash" has no correction door.
- `audit_events` exists (0011) with fifteen actions already written inside their transactions; actors are `console` and `whatsapp:<phone>`.
  `CONSOLE_ACTOR` has twelve uses in `api.py` and seven in `menu.py`, including the provenance actor and `created_by` on manual entry, plus 35 test assertions on the literal.
- RLS is enabled deny-all on every public table with zero policies.
  The API connects to Postgres as the table owner through asyncpg, so RLS does not apply to it; policies would today guard only PostgREST, which nothing uses.
- Composite tenancy foreign keys exist where a cross-tenant pointer was possible (0012 `supplier_items.ingredient_id`, 0015 recipes, 0017 `duplicate_of_invoice_id`).
- The web app is Next.js 16 App Router with three gated screens (`/invoices`, `/materials`, `/menu` plus `/menu/load`) and one public landing page whose waitlist form already posts through a same-origin server route (`apps/web/src/app/api/waitlist/route.ts`, server-only `FAIDA_API_URL`).
  Mock mode is the default and serves byte-identical shapes, which is how offline QA works.
  There is no unit test runner in `apps/web`; CI runs lint, typecheck and build.
- CI seeds two tenants for the API tests (`seed.sql`'s fixture tenant and `demo_seed.sql`'s chain); `test_demo_seed.py` uses the fixture tenant as a cross-tenant canary.
- The API and the WhatsApp worker share one process and one event loop (`main.py`), so any blocking I/O in a request path stalls the worker's ack.

## 3. Contracts to pin before fan-out (C10 new; C2, C6, C8 amended)

- **C10 - Auth context.** Every `/api/*` handler receives `AuthContext(user_id, tenant_id, actor)`, derived server-side, never from any client-supplied value.
  Its source is swapped once (D20): in Wave 1 the legacy token resolves to the existing tenant helper; from WP-70 it is a verified Supabase access token plus the `memberships` row.
  Every tenant-owned `db.py` method takes `tenant_id` as a **required keyword-only argument** and puts it in the `WHERE`, by-id reads included (D10); `default_tenant_id()` is deleted at WP-70.
- **C2 amended - jobs carry their scope, with one named resolver (D6).** `process_wa_message` is the resolver: it maps the sender phone to a branch and tenant and carries the phone.
  Every job it enqueues carries `tenant_id` and `branch_id`; every handler that loads a tenant-owned row refuses a payload/row tenant mismatch.
  A job without a tenant is a failed job, never a guess.
  One extract job per document, ever (D22): a future retry re-queues the existing row.
- **C6 amended - the bearer is a Supabase access token (D5).** The browser calls the Railway host directly with `Authorization: Bearer <access token>`; CORS is unchanged; `api.ts` stays the single chokepoint and attaches a fresh token per request.
  `API_TOKEN` and `NEXT_PUBLIC_API_TOKEN` cease to exist at WP-76.
- **C8 amended - actors.** The review screen's actor is `user:<auth user id>`; `console` is retired in WP-73, where the nineteen call sites are.
  WhatsApp actors stay `whatsapp:<phone>`: feeding an invoice needs no login (PRD §4, §11), and the phone now belongs to a registered branch by construction.
- **C5 amended - `payment_kind` is correctable (D23).** `payment cash` / `payment credit` in chat and the same field on the screen, origin `corrected_chat` / `corrected_screen`; cash to credit returns a held invoice to `awaiting_confirm`, the first correction that moves a status.
- **C1 unchanged.** No new invoice status: a cash approval is a `needs_review -> confirmed` transition through `_confirm`, distinguished by its audit row.

## 4. Work packages

Sizes as in §7.3: S ≤ half an agent-day, M ≈ one, L = multi-day.
Acceptance is demonstrable, never documentary.
Waves per §6 (D20): scoping first, auth swap after.

| WP | What | Size | Depends | Acceptance |
|---|---|---|---|---|
| 73 | **Every read and write is scoped by the context, and the schema gets its tenancy keys.** Wave 1, alone. Introduce `AuthContext` and `require_context` in a new `auth.py`; in this wave its only source is the legacy token resolving to the existing tenant helper (the strangler step - the type is real, the source is temporary). Every `default_tenant_id()` and `_tenant(db)` caller takes `ctx.tenant_id`; every tenant-owned `db.py` method gains a required keyword-only `tenant_id` in its `WHERE` (D10), `list_invoices` included, by-id reads included; the storage URL is signed only after the tenant check passes; a row outside the tenant answers 404, never 403. The nineteen `CONSOLE_ACTOR` sites take `ctx.actor` (still `console` in this wave). Migration 0018 lands here in full: `memberships (id, tenant_id, user_id uuid, role check (role in ('tenant')), created_at, unique (tenant_id, user_id))` with the tenancy FK and **no** FK to `auth.users` (D7 - CI runs on plain Postgres); `branches` gains `unique (tenant_id, id)` and `documents` / `invoices` gain composite `(tenant_id, branch_id)` FKs; a unique index on `jobs (kind, (payload->>'document_id'))` for extract jobs with no status filter (D22); RLS deny-all on the new table | M/L | C10 | `tests/test_tenancy.py`: a matrix generated from the router's route table over every `/api/*` route x {tenant A, tenant B, no token} asserting 200 / 404 / 401, with a deliberate public list (`/webhook`, `/health`, `/api/waitlist`) that a new public route must join on purpose or CI fails; beside it, a test that every non-public router declares the auth dependency (D24); the storage transport mock proves no sign call is made for a foreign document; the 592 existing tests stay green; a cross-tenant `branch_id` is refused by Postgres |
| 70 | **The API knows who is asking, and never asks the client.** `require_context`'s real source: verify the Supabase access token against the project's JWKS with PyJWT, **asymmetric algorithms only** (D4; the founder migrates the project to JWT signing keys first, and the legacy JWT secret is never revoked because `storage.py:20`'s service_role key is signed by it - WP-70 verifies both before it starts), issuer and `authenticated` audience checked, then the membership row, then the context; no membership is 403, no token or a bad one is 401. Keys are fetched with **async httpx through an injected transport** (D15), cached in-process by key id; a miss triggers one refetch rate-limited to once a minute; on fetch failure cached keys are served; 503 "sign-in service unreachable" only when nothing is cached (D11). `default_tenant_id()` and `API_TOKEN` are deleted. New dependency `PyJWT` (`cryptography` is already present) | M | 73, C6 | `tests/test_auth.py` with a local key pair and a mocked JWKS transport: no header, malformed, expired, wrong issuer, wrong audience and HS256 are 401; unknown kid refetches once then 401; fetch failure with a warm cache verifies; fetch failure with an empty cache is 503; valid token with no membership is 403; valid plus membership yields the right tenant and actor `user:<id>`; the refetch rate limit holds under a burst |
| 71 | **Login on the web app, and a session that rides on every API call.** `@supabase/ssr`: a `/login` page (email + password, D17; accounts are created by the founder, sign-ups disabled, D8), `src/proxy.ts` (Next 16's request interceptor; a leftover `middleware.ts` is silently ignored, so none may exist) refreshing the session and sending unauthenticated visitors to `/login` for `/invoices`, `/materials`, `/menu` and `/menu/load` while `/` and the waitlist stay public, a sign-out control, and `api.ts` attaching the session's access token **per request** so the 45-post loader survives a refresh mid-run, with a 401 sending the visitor to `/login` and back. The Supabase client is never constructed at module scope, so `next build` succeeds with no env (CI). Mock mode fakes a signed-in owner and constructs no client. `NEXT_PUBLIC_SUPABASE_URL` and the anon key are public by design; `NEXT_PUBLIC_API_TOKEN` is deleted. vitest is added (D14) with `npm test` wired into CI's web job | M | C6 | vitest: `isGatedPath` for every path in the list and the public ones, the mock bypass, the token attach and the 401 path; real browser at 1280 and 390: signed out lands on `/login`, a wrong password is refused with a plain sentence, a right one lands on `/invoices` with real rows, an expired session re-logs in and returns to the page it left, the landing page and waitlist need no login, no horizontal overflow at 390; the built bundle contains no bearer token |
| 72 | **The worker fails closed.** C2 as amended: an unknown sender's inbound `wa_messages` row is stamped `status = 'ignored_unknown_sender'` **before** any reply (D9); the 24 h silence is derived from inbound rows with that status from the same phone, **excluding the current message id**; the reply is best-effort and a send failure is logged, never raised; no document, no job, no model spend. Every enqueue carries `tenant_id` and `branch_id`; `extract_document` refuses a document whose tenant differs from its payload; manual upload and manual entry take the tenant from the context. `enqueue_once` inserts with `ON CONFLICT DO NOTHING` against the 0018 index, so a retried ack enqueues nothing (D13, D22) | S/M | 73 | `tests/test_worker_tenancy.py`: a job built with tenant A's context against tenant B's row is rejected; an unknown phone gets exactly one reply and creates nothing; a second message inside 24 h gets nothing; a send failure leaves the stamp and a successful job; a retried ack after the extraction is `done` inserts no job; the registered demo phone still lands in its branch. `test_flow.py::test_unknown_sender_still_ingests_with_default_tenant` is **inverted** (regression) |
| 74 | **Cash approval - the one gate PRD §21 makes non-negotiable.** `POST /api/invoices/{id}/approve` with a required non-empty `reason`, running the same `_confirm` write (same transaction, same price write) with an `invoice.cash_approved` audit row carrying actor, reason, `from_status` and the invoice's headline figures. Keyed on `payment_kind = 'cash'` alone (D12): a cash paper that is also a held duplicate approves with a reason and the screen shows both banners; `POST .../confirm` refuses cash with a 409 naming the approve door; chat already refuses. `payment_kind` becomes correctable (D23) so a misread cash is corrected, never laundered through an approval. Screen: the cash banner offers "Approve" with a reason field | M | 70, 71, 73 | e2e: a cash invoice cannot reach `confirmed` without an `invoice.cash_approved` row; an empty reason is 422; a non-cash invoice is refused by approve; confirm on cash is 409; cash-plus-duplicate approves; `payment cash` / `payment credit` correct the field from chat and screen, and cash to credit returns the invoice to `awaiting_confirm`; the price baseline moves only on approval. `test_api.py::test_confirm_from_needs_review_is_the_cash_approval_path` and `::test_manual_cash_invoice_is_held_and_approved_from_the_screen` move to the approve door (regression) |
| 76 | **Cutover: the shared token dies and the stage keeps working.** A hard swap with its rollback written down (D3, D21), one sitting outside demo hours: back up; migrate the project to JWT signing keys and confirm the legacy secret is untouched; disable sign-ups; create the founder's account and run the membership script; **rehearse** by minting a real token from the live project and verifying it against the local API; deploy API (the old token is refused from this moment); deploy web; log in; forward one paper from the demo phone and walk both acts; delete `NEXT_PUBLIC_API_TOKEN` from Vercel and `API_TOKEN` from Railway. Rollback pair named in the runbook: Railway redeploys the previous build, Vercel promotes the previous deployment, both one click. Docs: README env tables, `apps/web/README.md`, both `.env.example`s, DEMO_RUNBOOK §A (login precondition, and the leftover-check sentence from TODOS - D19), CLAUDE.md and AGENTS.md in the same commit (the C8 actor paragraph, the C6 line), TODOS entries closed, plan.md rows, Decision Log and Progress Log | S/M | 70-74 | curl with the old token gets 401 on the live host; sign-up with the anon key is refused; the two-act script runs once clean end to end after cutover as a smoke; the served bundle carries no bearer token |

Deferred with a named trigger, not built (§9): WP-75 users screen, WP-77 RLS as a second lock, WP-78 branch role.

## 5. Decisions taken in the review (for the Decision Log)

| # | Decision | Why |
|---|---|---|
| D2 | One role, `tenant`; no branch role, no users screen, no branch scoping in M7 | The done-when is met with one role; the branch side of the cash gate is the WhatsApp phone; §2 rule 8 |
| D3, D21 | No dual-accept path; a hard-swap cutover with the rollback pair written and a real-token rehearsal | A second front door for one afternoon, mapped to "the oldest tenant", is the rule that bit on 2026-08-31 |
| D4 | Verifier accepts asymmetric algorithms only; the project migrates to signing keys first; the legacy secret is never revoked | Railway holds nothing that can forge a session; the service_role key still depends on the legacy secret |
| D5 | The browser calls Railway directly with the user's token; CORS unchanged | A per-user, short-lived token in the browser is the normal posture; no hop added to a 1-2 s API |
| D6 | C2 reworded: `process_wa_message` is the named resolver; everything it enqueues carries the scope | The webhook stays dumb; the contract describes reality instead of bending it |
| D7 | `memberships.user_id` is a bare uuid, no FK to `auth.users` | CI runs migrations on plain Postgres; the `audit_events.subject_id` precedent |
| D8 | Public sign-ups disabled; accounts are dashboard-provisioned | One chain, one owner; an open sign-up is an account factory against a rate-limited mailer |
| D9 | Unknown sender: stamp the inbound row first, silence derived from inbound rows excluding self, reply best-effort | The decision is ours and is recorded before anything leaves; nothing to retry for a phone we do not know |
| D10 | Required keyword-only `tenant_id` on every tenant-owned `db.py` method | A forgotten scope is a TypeError at the call site, not a silent cross-tenant read |
| D11 | JWKS cache by kid; refetch on miss, rate-limited; stale on failure; 503 only when empty | A Supabase blip must not read as "wrong password" to every user |
| D12 | Approve keys on cash alone; a cash duplicate approves with a reason | Otherwise a cash false duplicate has no door at all |
| D13, D22 | One extract job per document, ever: unique index with no status filter, `ON CONFLICT DO NOTHING` | The 30 s retry always arrives after the first extraction is done, so a live-only filter never fires |
| D14 | vitest in `apps/web` for the gate's pure decisions and `api.ts` | The gate is auth; the repo bans framework tests, not tests of our own decisions |
| D15 | JWKS fetched with async httpx and an injected transport | One process, one loop: blocking urllib in a request would stall the worker's ack |
| D16 | RLS stays deny-all; WP-77 owed at the first second door to the database | The API is the only door and connects as the owner; policies would guard nothing reachable |
| D17 | Email and password; Supabase's reset email for the forgotten case | Login depends on nothing external at the moment it happens |
| D20 | Scoping (WP-73) lands first under the legacy token; the auth swap changes only the context's source | The widest diff soaks alone before the cutover changes one function's source |
| D23 | `payment_kind` joins the correctable field set | A misread cash must be correctable, or every misread becomes a fabricated approval |
| D24 | Route-table matrix with an explicit public list, plus a router-dependency assertion | A public route missing from the list fails CI loudly; the router check guards an empty new router |

## 6. Delegation waves and parallel lanes

| Step | Modules touched | Depends on |
|---|---|---|
| WP-73 scoping + 0018 | `apps/api/src/faida_api/` (db, api, menu, confirm, auth), `supabase/migrations/`, `apps/api/tests/` | - |
| WP-70 auth source | `apps/api/src/faida_api/` (auth, config, main), `apps/api/pyproject.toml`, `apps/api/tests/` | WP-73 |
| WP-71 web login | `apps/web/`, `.github/workflows/` | - (mock); cutover needs WP-70 |
| WP-72 worker | `apps/api/src/faida_api/` (worker, pipeline, contracts, db.enqueue_once), `apps/api/tests/` | WP-73 |
| WP-74 approve + payment_kind | `apps/api/src/faida_api/` (api, confirm, db, replies), `apps/web/src/components/`, `apps/api/tests/` | WP-70, WP-71, WP-73 |
| WP-76 cutover | `Docs/`, `README.md`, `apps/web/README.md`, `.env.example`s, `CLAUDE.md`, `AGENTS.md`, `plan.md`, `TODOS.md` | all |

- **Wave 0 (manager, no code):** pin C10 and the amendments in `plan.md` §7.2; move the rows into §7.3; Decision Log rows from §5.
- **Wave 1: Lane A = WP-73 alone.** It touches `db.py`, `api.py`, `menu.py` and `confirm.py` throughout and owns migration 0018, so nothing runs beside it.
  0018 is applied to the live project from `Docs/apply_m7_migrations.sql` (pre-flight included) after WP-73 merges and **before any Wave 2 lane merges**: WP-73's code needs nothing from it, but WP-72's `enqueue_once` and WP-70's membership read do, and Railway deploys every merge.
- **Wave 2, three parallel worktrees:** Lane B = WP-70 (`auth.py`, `config.py`, `main.py`); Lane C = WP-71 (`apps/web`, against the mock); Lane D = WP-72 (`worker.py`, `pipeline.py`, `contracts.py`).
  Conflict flags: B and D both add to `apps/api/tests/`, new files only; D's `enqueue_once` is a small addition to `db.py` after A has merged.
- **Wave 3: WP-74** after B, C and D merge; it touches `api.py` (after B) and `apps/web` (after C).
- **Wave 4: WP-76**, one sitting with the founder, live.

Budget check (§2 rule 9): M/L + M + M + S/M + M + S/M is roughly seven agent-days, inside the plan's two weeks.
If it runs over, WP-74's screen half can trail by a day; nothing else is cuttable without breaking the done-when.

## 7. The tests that gate it

Coverage as reviewed: 6 of 41 planned paths had a test before this plan; every gap below is now a named test in a WP's acceptance.

- `tests/test_tenancy.py` (WP-73): the route-table matrix with the deliberate public list, the router-dependency assertion, the no-sign-call proof for a foreign document, the composite `branch_id` refusal.
- `tests/test_auth.py` (WP-70): the eleven token cases with a local key pair and a mocked JWKS transport, including the cache, the rate limit and the 503 path.
- `tests/test_worker_tenancy.py` (WP-72): cross-tenant rejection, the unknown-sender path including send failure and the self-exclusion, the exactly-one-job retry proof measured after the first extraction is `done`.
- The WP-74 approve cases beside the confirm tests, plus the `payment_kind` correction from chat and screen.
- **Regressions, mandatory:** `test_flow.py::test_unknown_sender_still_ingests_with_default_tenant` inverted; the two cash-confirm-from-screen tests in `test_api.py` moved to approve plus a 409-on-cash test; the three shared-token tests at `test_api.py:65-97` replaced by JWT equivalents; the 35 `console` assertions become `user:<id>` (chat actors unchanged).
- `apps/web/src/lib/__tests__/` (WP-71): the gate's path decisions, the mock bypass, the token attach and the 401 path, run by `npm test` in CI.
- Real-browser QA with `/browse` at 1280 and 390 for WP-71 and WP-74; the QA sheet is `~/.gstack/projects/Ameen-Mammootty-faida/mohammedameen-master-eng-review-test-plan-20260903-070005.md`.
- The existing 592 tests stay green with zero skips; the eval smoke stays green because no extraction code changes.
- Banned as before: tests that grep code text, framework tests, coverage targets.

### Failure modes, one per new path

| Path | Realistic failure | Test | Handling | User sees |
|---|---|---|---|---|
| JWKS fetch | Supabase unreachable | yes (WP-70) | cached keys, else 503 | a clear "sign-in service unreachable", not a logout |
| Token verify | rotated key id | yes | one refetch | nothing, verified on the new key |
| Membership read | row deleted after login | yes | 403 per request | "no access" on the next click |
| Tenant scope | new endpoint forgets `tenant_id` | signature TypeError + matrix | crash at call site | a 500 in CI, never a leak |
| Storage URL | foreign document id | yes | 404 before signing | a not-found page |
| Unknown sender | reply send fails | yes (WP-72) | stamp stands, logged | nothing; the stamp prevents retries |
| Ack retry | extraction already done | yes | index refuses the insert | one reply, no second read |
| Cash approve | double-click | yes | guarded update, `_fresh_status` | the real current status |
| Cash approve | misread cash | yes (D23) | `payment credit` correction | the invoice returns to awaiting confirm |
| Login | expired session mid-loader | browser QA | fresh token per request | the loader completes |
| Gate | leftover `middleware.ts` | review checklist | none possible | every route public - the checklist item exists for this |
| Cutover | login fails on the day | rehearsal step | rollback pair | the previous build in two clicks |

Two of these were critical gaps in the draft as written (a self-silencing unknown-sender lookup, and a retry guard that expired before the retry) and both are closed above.

## 8. Live cutover order (WP-76)

1. Back up the live database.
2. In the Supabase dashboard: migrate the project to JWT signing keys; **do not revoke the legacy JWT secret** (the service_role key in `storage.py:20` is signed by it); disable email sign-ups.
3. Confirm 0018 is already live (it is applied from its paste file **before Wave 2 merges**, because Railway deploys every merge and WP-72's `enqueue_once` and WP-70's membership read both need it; the 0017 lesson).
4. Create the founder's account in the dashboard; run the membership script for the demo chain.
5. Rehearse: mint a real access token from the live project and verify it against the local API's `require_context`; walk `/login` on the local rig.
6. Merge and let Railway deploy the API. The old token is refused from this moment; the WhatsApp path is unaffected.
7. Deploy web; log in; forward one paper from the demo phone; walk both acts.
8. Delete `NEXT_PUBLIC_API_TOKEN` from Vercel and `API_TOKEN` from Railway.
9. Record it in the Progress Log and DEMO_RUNBOOK §A.

Rollback, written into the runbook: Railway redeploys the previous build and Vercel promotes the previous deployment, both one click, both independent of each other.
The screen is dark only between steps 6 and 7, minutes, outside demo hours.

## 9. NOT in scope, and what already exists

**NOT in scope** (each with its trigger; the first four are in `TODOS.md` as of 2026-09-03):

- **Branch role on the screen** (WP-78): `membership_branches`, branch-level scoping rules, and their matrix rows. Trigger: a chain asks for branch managers on the screen. Until then, one role does not give PRD §21's two-party gate by role; the two parties are the branch phone and the owner's login, and §9 of the plan says so rather than ticking §21 closed.
- **Users screen with invites** (WP-75): trigger: a second owner-side user on any tenant. Until then, accounts are dashboard-created and memberships scripted.
- **RLS as a second lock** (WP-77): trigger: the first second door to the database - a direct Supabase read from a browser, a second service, or an export.
- **MFA for the owner role** (PRD §26): trigger: a second real tenant, or an owner asking; Supabase TOTP is the path.
- Un-dismiss: still nobody has asked; "who may dismiss" is now any member of the tenant.
- Session revocation lists and invitation expiry: the per-request membership read gives immediate revocation on removal, which covers the pilot.
- A retry button for failed extractions: when it is built it re-queues the existing job row, because there is one extract job per document (D22).
- Any change to extraction, matching, costing or plates; a broker or a second process.

**What already exists and is reused, not rebuilt:** the router-level auth dependency shape; `_confirm` as the single confirm write; `_insert_audit_event` and its fifteen actions; the composite tenancy FK pattern from 0012 and 0015; `branch_for_phone`; the `_get_branch` tenant check at `api.py:643` and `:770`; the two-tenant test seed and the `test_demo_seed.py` canary; the route loop in `test_wrong_or_missing_token_is_rejected_on_every_route` as the matrix's seed; the mock layer in `api.ts`; the injected-transport convention of `wa.py` and `storage.py`; the same-origin server route in `app/api/waitlist/route.ts` as the precedent if hiding the host ever matters.

## 10. Implementation Tasks

Synthesized from this review's findings. Each task derives from a specific finding above. Run with Claude Code or Codex; checkbox as you ship.

- [ ] **T1 (P1, human: ~1.5 days / CC: ~3h)** - `apps/api` - WP-73: `AuthContext` with the legacy source, required keyword-only `tenant_id` on every tenant-owned `db.py` method, `list_invoices` filter, by-id scoping, 404 for foreign ids, sign-after-check, `ctx.actor` at the nineteen `CONSOLE_ACTOR` sites
  - Surfaced by: Architecture (D10), outside voice 7 and 12
  - Files: `db.py`, `api.py`, `menu.py`, `confirm.py`, `auth.py` (new), `tests/test_tenancy.py`
  - Verify: `pytest -q`; the matrix and router assertion green; 592 existing green
- [ ] **T2 (P1, human: ~3h / CC: ~30 min)** - `supabase/migrations` - 0018: memberships (bare uuid, role check), `branches unique (tenant_id, id)`, composite `(tenant_id, branch_id)` FKs on documents and invoices, unscoped unique index on extract jobs, deny-all RLS, paste file with pre-flight
  - Surfaced by: Architecture (D7), outside voice 3, Code quality (D13, D22)
  - Files: `supabase/migrations/0018_auth_and_tenancy.sql`, `Docs/apply_m7_migrations.sql`
  - Verify: conftest applies it on plain Postgres; a cross-tenant `branch_id` insert is refused
- [ ] **T3 (P1, human: ~1 day / CC: ~2h)** - `apps/api` - WP-70: async JWKS fetch with injected transport, kid cache, rate-limited refetch, stale-on-failure, 503 when empty, asymmetric only, issuer and audience, membership lookup, `PyJWT` dependency; pre-check of the project's signing-key state
  - Surfaced by: Architecture (D4), Code quality (D11), Performance (D15), outside voice 6
  - Files: `auth.py`, `config.py`, `main.py`, `pyproject.toml`, `tests/test_auth.py`
  - Verify: the eleven token cases in `tests/test_auth.py`
- [ ] **T4 (P1, human: ~1 day / CC: ~2h)** - `apps/web` - WP-71: `@supabase/ssr`, `/login`, `src/proxy.ts`, per-request token in `api.ts`, 401 to login and back, sign-out, no client at module scope, mock session, vitest and `npm test` in CI
  - Surfaced by: Architecture (D5), Test review (D14), outside voice 5 and 9
  - Files: `apps/web/src/proxy.ts`, `apps/web/src/app/login/`, `apps/web/src/lib/api.ts`, `apps/web/src/lib/supabase/`, `apps/web/package.json`, `.github/workflows/ci.yml`
  - Verify: `npm test`, `tsc`, lint, build with no env; `/browse` at 1280 and 390
- [ ] **T5 (P1, human: ~4h / CC: ~1h)** - `apps/api` - WP-72: stamp-first unknown sender with self-excluded lookup and best-effort reply, scoped job payloads, mismatch refusal, `enqueue_once`; invert the pinned test
  - Surfaced by: Code quality (D9), outside voice 4, Architecture (D6)
  - Files: `worker.py`, `extraction/pipeline.py`, `contracts.py`, `db.py`, `tests/test_worker_tenancy.py`, `tests/test_flow.py`
  - Verify: the six cases in `tests/test_worker_tenancy.py`; the retry proof runs after extraction is `done`
- [ ] **T6 (P1, human: ~1 day / CC: ~2h)** - `apps/api` + `apps/web` - WP-74: approve endpoint keyed on cash, reason required, audit row, confirm refuses cash, `payment_kind` correctable from chat and screen with the status move, screen banner
  - Surfaced by: Code quality (D12), outside voice 8 (D23)
  - Files: `api.py`, `confirm.py`, `db.py`, `replies.py`, `apps/web/src/components/InvoiceReview.tsx`, `tests/test_api.py`, `tests/test_confirm_flow.py`
  - Verify: the approve e2e cases; the two moved tests; `/browse` at 390 with the reason field open
- [ ] **T7 (P1, human: ~3h / CC: ~30 min)** - `Docs` + root - WP-76: hard-swap cutover with rollback pair and rehearsal, signing-key migration and never-revoke note, sign-ups off, README and env tables, runbook §A with the leftover-check sentence, CLAUDE.md and AGENTS.md, plan.md rows and logs
  - Surfaced by: Architecture (D3, D8), outside voice 1 and 6 (D21), TODO (D19)
  - Files: `Docs/DEMO_RUNBOOK.md`, `README.md`, `apps/web/README.md`, `.env.example`, `apps/web/.env.example`, `CLAUDE.md`, `AGENTS.md`, `plan.md`, `TODOS.md`
  - Verify: old token gets 401 live; sign-up refused; one clean two-act run

_No new tasks from Performance beyond T3._

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | - | - |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | - | - |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR (PLAN) | 13 issues, 35 test gaps named into acceptance, 0 critical gaps open |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | - | - |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | - | - |

Scope: M7 auth, tenancy enforcement and cash approval, reviewed 2026-09-03 at commit `25d81d3`, before any feature code.
Mode: SCOPE_REDUCED - the Step 0 complexity challenge cut the branch role, branch scoping and the users screen (D2), leaving five work packages plus the cutover.
Findings: six architecture (dual-accept cut, asymmetric-only verifier, direct browser calls, C2 reworded, no FK to `auth.users`, sign-ups disabled), five code quality (stamp-first unknown sender, keyword-only tenant scope, JWKS cache and outage rule, approve keyed on cash alone, one extract job per document), one test (vitest for the gate), one performance (async JWKS fetch); two scope proposals decided (RLS deferred to a named trigger, email and password).

**CROSS-MODEL:** Codex timed out at five minutes with no output; the outside voice ran as a Claude subagent and filed twelve findings.
Five were tensions with the review and were put to the user individually: the sequencing (accepted - scoping lands before the auth swap), the cutover story (kept D3, with the rollback pair and a real-token rehearsal written in), the enqueue guard (accepted - the live-status filter provably expired before the 30 s retry), `payment_kind` as a correctable field (accepted), and the matrix design (kept, with the router-dependency assertion added beside it).
Seven were corrections and additions applied as amendments: composite `branch_id` keys in 0018, the self-excluded silence lookup, the impossible "no host in the bundle" clause dropped, the legacy JWT secret never revoked because the service_role key depends on it, actor threading priced into WP-73, `npm test` in CI and no module-scope Supabase client, and §9 saying plainly that one role does not give PRD §21's two-party gate.
One outside-voice claim was corrected against the code: the API already refuses a foreign `branch_id` at `api.py:643` and `:770`; the composite FK is the database-level belt, not the first guard.

**VERDICT:** ENG CLEARED - ready to implement, pending the founder's go-ahead on the reduced scope and the Wave 0 move of these rows into `plan.md`.

NO UNRESOLVED DECISIONS
