# M10 decomposition - the daily WhatsApp brief (drafted 2026-09-07)

Status: **decomposed and reviewed 2026-09-07 with one outside voice (Codex at medium reasoning against the file path, read-only: thirteen findings, thirteen folded, four of them blockers that changed the queue's story, the migration's number and two founder decisions), awaiting the founder's decisions.**
The session ran as a planning lane beside WP-96's live sitting, on a branch cut from `origin/master` at `64f9793`; no feature code was written and nothing was merged.
Three questions were put to the founder at the start of the session and answered: only the free test number is live (no business verification, no WhatsApp Business Account of our own, no purchased sender); the brief's first recipient is the founder's demo phone; the brief is English-only for the pilot.
Every other question this document raises is answered with the recommended option and recorded as **recommended, not decided**; §5 is the founder's decision list, and the report at the end lists every one of its proposals as open.
M8, M9 and M12 were each decomposed, reviewed with an outside voice, and only then approved to build; M10 follows the same path.
To be recorded in `plan.md` on the founder's word: the contract in §7.2 (proposed here as C15), the rows in §7.3, the M10 header in §8, one Decision Log row per decision, and the deferred items in `TODOS.md`.

Facts in §2 are from master `64f9793` (Wave 2 and three lanes merged, WP-87's API half live, WP-96's sitting still open), so the review argues about the plan and not about the state.

Plan reference: `plan.md` §8 M10 (the checklist and the done-when, as corrected 2026-09-05), §3 (the two WhatsApp channel rows and the language row), §2 (the standing rules), §7.2 C2 (job kinds, as amended), C8 (provenance and audit), C9 (quality words), C10 (auth context), C11 (the ratio's label), C12, C13 and its C13.5, C14; the Decision Log rows for M9 P6, P8 and P10, WP-74's best-effort notice and the C2 rewording; PRD §11 (the WhatsApp production chain), §25.4, §27.4 and §31.

## 1. What M10 is for

`plan.md` §8 says it in four lines, quoted whole because every row below answers one of them (dashes normalised to the plain hyphen this repo writes in; `plan.md:1104-1110`):

> ### M10 - Daily WhatsApp brief (gated on Meta approval from M5)
> - [ ] Deterministic template filler: net sales, purchases ÷ net sales (cash basis), biggest price move, one flagged issue (PRD §27.4, its "est. food-cost %" corrected 2026-09-05 per §3's display rule and C11.6; the four slots are `GET /api/dashboard`'s `freshness.sentence`, `latest_day`, `league[0]` and `signals[0..1]`, M9 P8) - fixed sentence shapes, number slots, no generation
> - [ ] Send via approved utility template outside the 24-h window; tap-through opens the dashboard
> - **Done when:** the owner's phone receives a real brief at 7am with yesterday's real numbers.

M9 built the screen an owner reads.
M10 is for the owner who will not open it.
PRD §27.4 says it plainly: the brief is "the primary consumption surface for a non-tech owner who will never open a BI dashboard unprompted" (`Docs/PRD.md:464`), and PRD §31's MVP definition lists it as item 10 of thirteen (`Docs/PRD.md:578`).

The milestone adds no figure and no sentence about a figure that the dashboard does not already carry.
M9 P8 pinned the four slots on `GET /api/dashboard` precisely so that this milestone would fill them and word nothing itself (`plan.md:1248`; C6 extended, `plan.md:556`), and C13.5 puts every sentence that states a fact or a number on the wire for the same reason (`plan.md:554`; `signals.py:42-45`).
What M10 adds is the message shape, the one Meta template that carries it, the recipient, the morning, and the record.

Two of its parts are outside the repository and outside anyone's control here: Meta's review of the template, and the production chain (business verification, a WhatsApp Business Account, a purchased sender) that `plan.md` §3 says "starts early (M5) and runs in the background" (`plan.md:83`).
The founder's answer at the start of this session is that the chain has not started.
That is why §4 makes the deterministic filler and a printed dry run the first vertical slice, the M12 phase-one precedent, and why §5 P8 asks whether the free test number carries the rehearsal.

**Done when** (as the checklist says, read against this decomposition): at 07:00 Dubai time the recipient's phone shows one message with five lines - the newest loaded day named and aged, that day's net sales, purchases ÷ net sales (cash basis) for the window with the branch to look at first, the biggest supplier price move with the money on the sales since, and the top flagged issue - every number equal to the dashboard's for the same read, sent through an approved utility template, recorded once, with a button that opens `/dashboard`.
On the founder's answer, the first phone is the founder's, on the test number; the pilot owner's phone follows the production chain.

## 2. What exists today, and what is missing

### The client sends free text and nothing else

- `wa.WhatsAppClient` has three methods: `close`, `get_media` and `send_text` (`wa.py:18-45`).
  `send_text` posts `{"type": "text", "text": {"preview_url": false, "body": ...}}` to `/{phone_number_id}/messages` and returns Meta's message id (`wa.py:32-45`); its own docstring says "valid inside the 24h service window" (`wa.py:33`).
  **There is no template send**: no `type: "template"`, no template name, no language, no components anywhere in `apps/api`.
- The client takes an injected `httpx` transport (`wa.py:9`, `:15`), which is how every test mocks Meta: `tests/conftest.py`'s `FakeMeta` answers any POST ending in `/messages` with a fabricated `wamid.out<n>` and records the JSON it was sent (`conftest.py:147-168`), and flips to a 500 on `fail_sends` (`conftest.py:155`, `:163-164`).
  A template send is one more JSON shape through the same transport, and the fake already records whatever it is given.
- Meta's own rule is the one the product has lived with since M0: outside 24 hours of the recipient's last inbound message a free-form text is refused with error 131047, "More than 24 hours have passed since the recipient last replied to the sender number", whose documented solution is "Send the recipient a template message instead" (Meta Cloud API error codes, fetched 2026-09-07).
  The WP-74 Decision Log row records the consequence for the cash-approval notice: "outside Meta's 24 h window the branch learns nothing until M10's utility template" (`plan.md:1276`; `replies.py:74-80`; `api.py:712-718`).
  A brief sent at 07:00 to a phone that wrote nothing yesterday is exactly that case, every day.

### Nothing ticks at a wall-clock time

- The worker is one asyncio task started in the API's lifespan (`main.py:48-60`), and its loop does one thing: claim a queued job, run it, and when the queue is empty wait `worker_poll_seconds` (2 s, `config.py:43`) before looking again (`worker.py:193-213`).
  There is no scheduler, no cron, no timer and no clock anywhere in `apps/api` beyond the retry backoff.
- The queue already knows about the future: `claim_job` takes only rows whose `run_after <= now()` (`db.py:3583-3605`, the predicate at `:3589`), and `finish_job` pushes a failed job 30 s ahead through the same column (`db.py:3607-3626`; `RETRY_LIMIT = 3`, `RETRY_BACKOFF_SECONDS = 30`, `db.py:28-29`).
  So a job enqueued at midnight with `run_after` at 07:00 would run at 07:00 with no new machinery.
  What does not exist is the thing that would enqueue it: nothing looks at the calendar.
- Two job kinds exist, `process_wa_message` and `extract_document` (`contracts.py:43-52`; `HANDLERS`, `worker.py:161-164`), and C2 as amended says every job but the resolver carries `tenant_id` and a handler refuses one that does not (`contracts.py:22-33`, `:68-78`).
  A brief job is a third kind and inherits the rule.
- "Once, ever" already has one implementation: `enqueue_once` inserts against `jobs_extract_document_uidx`, a partial unique index on `(kind, payload->>'document_id') where kind = 'extract_document'`, and tolerates the conflict (`db.py:3562-3581`; `0018_auth_and_tenancy.sql:97-103`).
  It refuses any other kind by design (`db.py:3570-3571`), so "one brief per recipient per day" is a second index in the same shape and a second conflict target, not a status flag in Python - the reason the first one was built that way (`db.py:3565-3570`).

### Nobody has an owner's phone

- The only phone the schema knows is `branches.wa_phone_e164`, unique across every tenant, the *sender* a branch forwards invoices from (`0001_init.sql:15`; resolved by `db.branch_for_phone`, `db.py:466-469`; digits only with no `+`, `supabase/demo_seed.sql:562-570`).
- `tenants` has `id, name, currency, created_at` and nothing else (`0001_init.sql:4-9`).
  `memberships` has a bare Supabase `user_id` and a role whose only value is `tenant` (`0018_auth_and_tenancy.sql:57-64`), with no phone, and the comment says why there is no foreign key to `auth.users`: CI has no auth schema (`0018:66-71`).
  So an owner's WhatsApp number is modelled nowhere, and the sign-in identity cannot reach one either.
- The worker's rule for a phone it does not know is settled and tested: the inbound row is stamped `ignored_unknown_sender` first, then one polite reply inside a 24-hour window, then silence (`worker.py:86-113`; `UNKNOWN_SENDER_SILENCE`, `worker.py:31`; `db.inbound_status_seen_from_phone`, `db.py:435-464`; the words at `replies.py:51-56`).
  **That reply is wrong for an owner who answers the brief.**
  A recipient phone that is not a branch phone gets "This number isn't set up yet, so I can't read invoices from it. Ask the owner to add this number" - addressed to the owner.
  §3 C15.10 amends C2 for it.
- For the demo chain the two phones coincide: the founder's handset is mapped to Al Qusais by the runbook's founder step (`Docs/DEMO_RUNBOOK.md:35`; `demo_seed.sql:562-570`), so the first recipient is also a branch phone and the rehearsal never hits that path.
  The pilot owner's phone will.
- `branches.timezone` exists, defaults to `Asia/Dubai`, and is read by nothing (`0001_init.sql:16`; `TODOS.md:323-342` says so and defers the business-day arithmetic).
  `db.list_branches` returns it (`db.py:2019-2027`).
  There is no tenant-level timezone: a tenant's morning has to be a fact about the recipient, or derived from its branches.

### Three of the four slots are sentences on the wire; the ratio and the net sales are numbers

`GET /api/dashboard` (`dashboard.py:443-684`) carries, for the default period, everything the checklist names.
What each slot is on the wire today, and whether the brief can use it verbatim:

| Slot (checklist) | Field | State on the wire | What the brief must do |
|---|---|---|---|
| the day, named and aged (P6) | `freshness.sentence` | a sentence: "Sales loaded to Mon 31 Aug, 5 days ago." (`dashboard.py:166-174`, `:641`); `null` when nothing is loaded | use verbatim |
| net sales | `latest_day` | numbers: the chain's `net_sales` and one row per branch with sales that day (`dashboard.py:586-601`); `null` when nothing is loaded or the newest day is outside the period | compose one fixed shape |
| purchases ÷ net sales (cash basis) | `total.ratio_pct`, `total.ratio_quality`, `total.ratio_notes`, `period`; `league[0]` | numbers and notes: the chain's ratio to a tenth with its quality word and the sentences that made it (`dashboard.py:653-664`); `league[0]` is the branch keeping the least, by `contribution.rank` (`dashboard.py:548-549`; C12.9), with its own `ratio_pct`, `window` and `ratio_notes` (`dashboard.py:279-304`) | compose one fixed shape |
| the biggest supplier price move | `price_moves.moves[0]` | a sentence and its evidence: "Milk Powder is up AED 3.40 per kg since 21 Aug, against its last purchase on 12 Mar." with `money_at_stake`, `direction` and `kind` (`dashboard.py:336-417`; words from `signals.move_sentence`, `signals.py:476-497`, and `move_evidence`, `:500-528`); ranked by the dirhams moved, both directions, basis changes last (`dashboard.py:390-397`) | use the sentence verbatim; the money in one fixed clause |
| one flagged issue | `signals[0]` | a sentence and a detail, ranked by money and capped at five (`dashboard.py:673`; `signals.py:705-717`; the three sentences at `signals.py:251-254`, `:614`, `:684-687`); the detail carries "(estimated)" when the signal fired on an estimated input (`signals.py:194-198`) | use the sentence verbatim, the word carried |

- The M9 P8 row names the slots as `freshness.sentence`, `latest_day`, `league[0]` and `signals[0..1]` (`plan.md:1248`; `plan.md:1106-1107`).
  The `price_moves` block did not exist when that was pinned: WP-99 added it on 2026-09-07, and it is exactly "each material's latest move inside the window, both directions, ranked by money" with the sentence composed once for the dashboard, the Menu card and the mock (`dashboard.py:345-361`; `CLAUDE.md`'s M9 paragraph).
  A price spike among the signals is a rise only (C13.2), so on a morning when the biggest move is a fall the signals carry no move at all.
  §5 P9 asks the founder to let the move slot read `price_moves.moves[0]`.
- The ratio has no sentence anywhere on the wire: `/sales` and the dashboard print the number under its label and the notes beside it.
  C11.6 fixes the label: "purchases ÷ net sales (cash basis)" on every surface and never food cost % (`plan.md:550`).
  The brief's fixed template text carries the label, so the words are pinned by Meta's approval as well as by the display rule.
- The net sales slot has no sentence either.
  `contribution._money_words` is the one headline-money formatter, rounded half up to whole dirhams with thousands separated (`contribution.py:334-337`), and `signals._short_branch` is the one branch-name shortener ("Rolla" from "Rolla Branch", `signals.py:172-178`), imported by `dashboard.py:46` the way the brief will import it.
- `latest_day` is `null` when the newest loaded day is outside the period (`dashboard.py:587`).
  With no `from` and `to`, `ratio.resolve_period` ends the period on the newest loaded day (`ratio.py:256-282`, the default at `:268-271`), so for the default period the block is present whenever anything is loaded, and absent exactly when nothing is.
  The brief always reads the default period.

### "Yesterday" is already the newest loaded day, named and aged

- M9 P6 decided that "yesterday's sales" means the newest loaded day, named and aged, because sales arrive by CSV days later and a block headed Yesterday would usually be blank (`plan.md:1246`).
  `freshness_sentence` says "today" at age 0, "yesterday" at age 1 and "N days ago" after that (`dashboard.py:173`), and the dashboard's quality word turns `estimated` past `FRESHNESS_STALE_DAYS = 7` (`dashboard.py:56`, `:636-640`).
  A brief that uses the sentence verbatim never says "yesterday" when it is not, by construction; the test in §7 pins it on the stale fixture.
- The read's `today` is the UTC date (`dashboard.py:459`).
  At 07:00 in Dubai it is 03:00 UTC on the same calendar date, so a Dubai brief ages the day correctly; a recipient west of UTC, or a send before 04:00 Dubai, would age it wrong.
  The route keeps UTC (the deferred timezone work at `TODOS.md:323-342`); the brief passes the recipient's local date in, which is one keyword on the extracted read (§3 C15.6).

### The one send pattern the product has for a message nobody asked for

- Every message the product sends today is a reply to an inbound message, inside the window, on the same job that read it (`worker.py:82-83`), except two: the cash-approval notice, sent after the approval has committed and never inside it, best-effort, logged on failure and never retried (`api.py:712-737`; the test at `tests/test_api.py:533-565`), and the unknown-sender reply, stamped before it is sent so a retry finds the decision already made (`worker.py:86-113`).
  The brief is the first message the product sends because a clock said so, and it must survive three retries without sending three briefs; the stamp-first shape is the precedent.
- `db.record_outbound_message` hard-codes `msg_type = 'text'`, `status = 'sent'` and `payload = {"text": body}` (`db.py:408-418`).
  `wa_messages` has no `tenant_id` and no `direction`-specific columns beyond `from_phone` and `to_phone` (`0001_init.sql:103-113`); it is not a tenant-owned table on purpose, because a phone's messages exist before a tenant is resolved, and the demo seed deletes its rows by phone (`demo_seed.sql:185-198`).
  A template send is an outbound row whose `msg_type` is `template` and whose payload carries the template name, the parameters and the brief's key.

### What the record can and cannot say about an outbound message

- The webhook flattens `value.messages` and skips everything else; its docstring says "Status updates (delivered/read receipts) are not messages and are skipped" (`webhook.py:31-52`, the rule at `:33` and `:38`), and `tests/test_webhook_pure.py:52` pins that a `statuses` payload yields nothing.
  So after `send_text` returns a message id the product knows nothing further: not delivered, not read, not failed.
  For a reply the sender sees, that is fine.
  For a 07:00 message the founder cannot watch, "the owner says nothing arrived" has no record to check.
  Meta says its errors come "either synchronously as a Graph API response, asynchronously via Webhook, or sometimes through both" (error codes page, fetched 2026-09-07); a template that is not approved (132001), paused (132015) or disabled (132016) fails synchronously, an undeliverable number (131026) asynchronously.
- `audit_events` records human decisions, one row each, written inside the transaction they describe (`0011_provenance_and_audit.sql:32-46`; `db._insert_audit_event`, `db.py:327-345`; C8, `plan.md:486`).
  A scheduled send is not a human decision.
  Who asked for the brief, when, and who paused it are; §3 C15.4 puts the audit rows there and the send itself on `wa_messages`.

### The test number, and what a template submission needs

- The demo runs on Meta's free test number, direct, with "up to 5 registered recipient phones" (`plan.md:82`; `README.md:127-167`, the five recipients at `:167`).
  The runbook's preconditions already carry the two facts that bite an unattended morning send: the dashboard's Step 1 token expires on a 24-hour boundary and must be replaced by one whose `expires_at` is 0 (`Docs/DEMO_RUNBOOK.md:24-34`; `README.md:134-141`), and the app must be subscribed to the WhatsApp Business Account or Meta delivers nothing (`Docs/DEMO_RUNBOOK.md:16-22`; `README.md:147`).
- What Meta needs for a template, from its Business Management API documentation fetched 2026-09-07 (the numbers are Meta's; the founder verifies them in WhatsApp Manager on the day): a **name** of lowercase letters, digits and underscores; a **category** of `UTILITY`, `MARKETING` or `AUTHENTICATION`; a **language** code; a **body** of at most 1,024 characters with positional placeholders `{{1}}`, `{{2}}`, each with an **example value** ("you must include an example value for each parameter"); an optional text **header** of at most 60 characters and **footer** of at most 60; **buttons** of at most 25 characters of text, at most two URL buttons and ten buttons in all, a URL button carrying at most one variable appended to the end of its URL; review "can take up to 24 hours"; only an `APPROVED` template can be sent.
  Sending is `type: "template"` with the name, the language and a `components` array whose body component lists the parameter values in order; a value count that does not match the template is error 132000.
  Since 2025-07-01 Meta charges per message; a utility template inside an open customer-service window is free and outside one is charged at the country's rate, published in a rate card that includes AED (Meta pricing page, fetched 2026-09-07; PRD §11's own "verify the live UAE utility rate" stands, `Docs/PRD.md:251`; `plan.md:1181`).
- The category is the risk PRD §11 names ("get it approved in the *utility* category, not marketing", `Docs/PRD.md:249`).
  A daily account update the recipient asked for is what Meta's utility examples describe; a reviewer who reads it as promotional makes it marketing, which costs more and is subject to per-user marketing limits (error 131049).
  The body in §3.1 is factual and labelled, with nothing offered or advertised, which is the only lever this side of the review.
- Meta's own get-started flow for the test number sends the pre-approved `hello_world` template to a registered recipient (the Cloud API get-started page, fetched 2026-09-07), and a template created under the test account goes through the same review as any other.
  Whether the rehearsal runs there is §5 P8.

### The tap-through already exists

- `/dashboard` is where a sign-in lands (`DEFAULT_AFTER_LOGIN`, `apps/web/src/lib/gate.ts:30`; M9 P10, `plan.md:1250`), it is gated (`gate.ts:23`), and a signed-out visit to it redirects to a bare `/login` because the target is the default (`gate.ts:57-62`, `:107-108`), with `?next=` reserved for any other path and refused for anything off-site (`gate.ts:70-79`).
  The proxy refreshes the Supabase session cookie on every gated request (`apps/web/src/proxy.ts:14-19`, `:44`), so a phone that signed in once stays signed in.
  The login form is email and password only (`apps/web/src/components/LoginForm.tsx:45`); there is no magic link, no OTP and no deep-link token anywhere in `apps/web`.
- The public host is `https://faida-web-nine.vercel.app` (the M9 deploy record, `plan.md` Progress Log 2026-09-07); it is written in no repository file, so a template that names it is the first place the host becomes a fact Meta holds.
- The dashboard was measured at 390 px (WP-93, WP-97, WP-99 in `plan.md` §7.3), so the tap lands on a screen built for the phone it is tapped on.
  **No web file changes in M10.**

### The dashboard read is a route handler, and M12 already needs it as a function

- `dashboard()` takes `Request` and the auth `Context` and does everything inline: the enumerated reads, the pure modules, the serialisation (`dashboard.py:443-684`).
  Nothing outside an HTTP request can call it.
  A worker job cannot present a token, and must not: the worker's tenant comes from the job payload (C2 as amended; `contracts.py:68-78`).
- `test_dashboard.py` asserts the read makes exactly the enumerated queries, the membership read first (`tests/test_dashboard.py:53-75`, the test at `:711`).
  Extracting the body into `read_dashboard(db, tenant_id, *, today, date_from, date_to, branch_id)` with the route as a wrapper leaves that test and every other one green byte for byte, and gives the brief job and M12's `usage_report` (`plan.md` §7.3 row 120, not yet built) the same function.
  `ratio.resolve_period` was extracted from `sales._period` for the same reason one milestone ago (`ratio.py:249-282`; C6 extended, `plan.md:556`).

### The tests and the fixtures the brief inherits

- The web mock's dashboard fixtures are produced by the shipped Python modules through `apps/web/src/lib/mock/dashboard/generate.py` (686 lines) and committed as `full.json`, `partial.json`, `quiet.json`, `empty.json` and `nomenu.json`, each keyed by scope with `""` the chain.
  They carry real outputs of `freshness_sentence`, `latest_day`, the league, the signals and the price moves: the full chain reads "Sales loaded to Mon 31 Aug, 5 days ago.", net sales 9492.86 on the newest day across Al Quoz, Karama and Deira, a chain ratio of 23.7 labelled `incomplete` with "1 of 3 branches incomplete", Deira first in the league at 26.0 over 25-31 Aug, "Mint Lemonade sold AED 2,027 and kept -5.3%; the menu keeps 67.4%." as the top signal, and "Milk Powder is up AED 3.40 per kg since 21 Aug, against its last purchase on 12 Mar." with AED 108.58 at stake as the top move.
  The stale fixture ages the same day to 12 days and drops Deira's sales; the quiet one fires no signal and no move; the empty one has nothing loaded and `freshness.sentence` null.
  A pure `brief.py` tested over exactly these files agrees with the mock by construction, and the mock's screen and the phone's message can never disagree about a number.
- The tenancy rig builds its matrix from the router table and fails on any route without an entry (`tests/test_tenancy.py`), and lists every tenant-owned table in `TENANT_TABLES` (`test_tenancy.py:61`).
  M10 adds no route and one table.

### `TODOS.md` entries M10 fires

| Entry | Line | Why M10 touches it |
|---|---|---|
| A branch role on the screen (WP-78) | `:200-221` | PRD §27.4's "optionally each branch manager" has no user, no phone and no scope until the branch role exists; §5 P6 defers the manager's brief on WP-78's own trigger |
| The business-day cutoff and timezone arithmetic | `:323-342` | `branches.timezone` is read by nothing; the brief's morning is the first thing in the product that needs a local clock |
| A branch dashboard as its own route | `:537-546` | the tap-through for a manager's brief would be `/dashboard?branch=`, which the login gate already round-trips |
| A fifth slot in the daily brief | `:826-834` | written before M12's D9 removed the usage panel's answer sentence; the entry names `usage.answer`, which will not exist; §9 rewrites it |

## 3. Contracts to pin before fan-out (C15 new; C2 amended; C7 one migration; C8 extended; C6, C10 and C13 untouched)

- **C15 - The daily brief.**
  1. *One read, five lines, no generation.* The brief is composed by a pure `brief.py` from one `GET /api/dashboard` payload for the tenant's default period (28 days ending on the newest loaded day, `ratio.resolve_period`), read through the same function the route calls and never through HTTP.
     It is five labelled lines in a fixed template body (§3.1): the day, net sales, purchases ÷ net sales (cash basis), the biggest supplier price move, and the flagged issue.
     Where the payload carries a sentence the brief uses it verbatim (`freshness.sentence`, `price_moves.moves[0].sentence`, `signals[0].sentence`); where it carries only numbers (`latest_day`, `total`, `league[0]`, `price_moves.moves[0].money_at_stake`) the brief composes one fixed shape in Python, and a test pins every number in the brief to the payload field it came from.
     Nothing is generated, nothing comes from a second read, and no sentence is re-worded.
  2. *The words.* The label is "purchases ÷ net sales (cash basis)", in the fixed body, never food cost; contribution is never mentioned as profit; `verified` is never claimed; "yesterday" appears only when `freshness.sentence` says it, which is when the newest loaded day is one day before the brief's date (P6).
     Money is whole dirhams rounded half up with thousands separated (`contribution._money_words`, the §3 display rule), percentages to a tenth as the wire carries them, dates as `_short_date` and `_weekday_date` print them.
     A quality word rides on the line it qualifies, in the brief's own fixed clause, with the first note the payload gives: "(incomplete: 1 of 3 branches incomplete)", "(estimated: 1 invoice awaiting confirm)"; a signal carries "(estimated)" after its sentence exactly as its detail does on the wire.
     A figure the read withholds (`null`) is a sentence saying so with the read's own note, never a zero and never a blank slot.
  3. *One brief per recipient per local day.* The unit is (recipient, brief date).
     The job kind is `send_brief`, payload `{"tenant_id", "recipient_id", "brief_date"}`, enqueued only through `db.enqueue_brief_once` against a partial unique index on `jobs (kind, payload->>'recipient_id', payload->>'brief_date') where kind = 'send_brief'`, the 0018 shape, so a second tick, a second worker or a restart mid-tick enqueues nothing.
     The handler reads `wa_messages` for an outbound brief with the same key before it sends, so a job run twice for one payload sends once.
     A retry happens when the handler raises (Meta answering 500, the record write raising after the send), through `finish_job`'s three attempts at 30 s (`db.py:3607-3626`); the one honest limit is a record write that raises after Meta has accepted the message, where the retry finds no row and sends the same brief once more, and a test pins that case so the limit is known rather than discovered.
     A process that dies mid-job leaves the row `running` for ever today, because `claim_job` takes `queued` rows only and nothing reclaims an abandoned one (`db.py:3583-3605`); a graceful stop finishes the running job first (`main.py:64-67`), so a deploy does not strand, and a hard kill does.
     P12 puts the reclaim to the founder: `claim_job` also taking a `running` row untouched for `STALE_RUNNING_MINUTES` (10), attempts counted, every handler already idempotent under retries by C2's rule, so a brief interrupted by a kill is sent within the morning rather than never.
     The job carries `tenant_id` and refuses to run without it (C2).
  4. *The record.* Every send writes one outbound `wa_messages` row: `direction = 'out'`, `msg_type = 'template'`, `status = 'sent'`, payload `{"template", "language", "parameters", "tenant_id", "recipient_id", "brief_date", "rehearsal"}`.
     Meta's status updates for that message id stamp `status` through the webhook, which starts reading `value.statuses`: the order is `sent`, `delivered`, `read`, with `failed` terminal, a stamp only ever moves forward, and a late or duplicate event is ignored; a status for an id with no row yet (Meta's receipt racing the record write by a few hundred milliseconds) inserts a stub outbound row carrying the status, and the record write upserts into it, keeping the further-along status, so neither order loses a fact.
     No audit row for a send (C8: `audit_events` is human decisions).
     **C8 extended** by three human decisions about the recipient: `brief_recipient.added`, `brief_recipient.paused`, `brief_recipient.resumed`, subject `brief_recipient`, written in the same transaction as the row by whatever door writes it; the `added` row's detail carries the evidence of the owner's request (P14), and the row itself carries state and nothing about consent, so who decided, when and on what evidence lives in one place.
  5. *The morning.* The brief is due at `send_at_local` (default 07:00) in the recipient's `timezone` (default `Asia/Dubai`), one morning per recipient; a tenant with two recipients in two timezones has two mornings.
     The worker's tick runs on every pass of the loop before it claims a job, at most once a minute by a monotonic clock and whatever the queue holds, so an extraction backlog cannot starve the morning; it lists the active recipients, computes each one's local date and time in Python with `zoneinfo`, logs and skips a row whose timezone name does not resolve so one typo cannot silence every other recipient, and enqueues those whose morning has come and who have no job for (recipient, today).
     After `BRIEF_SEND_UNTIL_LOCAL` (12:00) the day's brief is skipped with a log line and never sent late: a morning brief at ten at night is noise, and tomorrow's is nine hours away (P11).
     `BRIEF_ENABLED` (default true) is the kill switch beside `WORKER_ENABLED`; a paused recipient row is the per-recipient switch.
  6. *Today is the recipient's date.* The brief job passes the recipient's local date as `today` to the extracted read; the route keeps the UTC date it has (a stated limit, `TODOS.md:323`).
  7. *The quiet day.* When the read has nothing loaded (`freshness.sentence` null, `latest_day` null) no message is sent, the job completes, and one log line says so with the tenant; there is nothing to say and a template costs money.
     When sales exist the brief is sent every morning whatever their age, the header naming the day and its age; past `FRESHNESS_STALE_DAYS` the header's fixed clause says the figures are estimated because the sales are older than a week (P4).
     A day with no move and no signal says so in those two lines and is still sent.
  8. *The tap-through.* One static URL button to `https://faida-web-nine.vercel.app/dashboard`; the login gate's round trip is untouched and the message carries no credential (P5).
  9. *The parameters.* Exactly five text parameters, positional, the count a constant beside the body and asserted by the filler so a template edited to a different count fails in a test before it fails as Meta's 132000; none contains a newline, a tab or four consecutive spaces (Meta's rule for parameter values), each is at most 160 characters by the filler's own cap, and the rendered body is under 1,024 characters by a test over the widest fixture (a chain of twelve branches).
     Branch names in the net sales line are at most four, then the count; a chain of one branch names no branch.
  10. *C2 amended - a recipient's reply.* `process_wa_message` resolves the sender phone against branches first, then against active brief recipients; a recipient that is not a branch phone gets its inbound row stamped `ignored_brief_recipient` before anything else, one fixed reply a day (`REPLY_BRIEF_RECIPIENT`: "This number receives the morning brief. To forward invoices, use a branch's phone."), and no document, job or model call (P10).
     A phone that is both a branch and a recipient is a branch: C5 applies unchanged.
  11. *The template.* One template, `faida_daily_brief`, category `UTILITY`, language `en`, the body and samples in §3.1, the same text under the test account and the production account; the name and language are constants in `brief.py`, and the template is edited only through Meta's review.
  12. *What does not change.* No web file; no new route (C6 untouched); the signals, the price moves and the dashboard's sentences are read, never re-composed (C13 untouched); `brief_recipients` is tenant-owned, read with `tenant_id` keyword-only and listed in `TENANT_TABLES` (C10); **C7:** one migration, `0022_brief_recipients.sql`, the number fixed now because M12's WP-119 already holds `0021_usable_share.sql` (`plan.md` §7.3 row 119) and the two are independent, so either can land first (the test rig applies the directory in sorted order, `tests/conftest.py:58`); with a paste file and a pre-flight in the 0019 and 0020 shape.

- **C13 untouched, one reading pinned.** The brief's move slot reads `price_moves.moves[0]`, which is the block WP-99 added after P8 was pinned, and its issue slot reads `signals[0]`; when `signals[0]` is the price spike for the same material as `moves[0]`, the issue slot reads `signals[1]`, so one move is never quoted twice (P9).
  Amends the P8 row's `signals[0..1]` to `price_moves.moves[0]` and `signals[0..1]`; the four slots stay four.

### 3.1 The template, the wire shapes and the sentence shapes

**The template to submit** (WhatsApp Manager, Message templates, Create template; the founder pastes it as it stands):

| Field | Value |
|---|---|
| Name | `faida_daily_brief` |
| Category | Utility |
| Language | English (`en`) |
| Header | none |
| Body | below, 152 characters of fixed text plus five variables (177 with the placeholders written out) |
| Footer | none |
| Button | Visit website, text `Open dashboard`, URL type static, `https://faida-web-nine.vercel.app/dashboard` |

Body, exactly:

```
*Faida morning brief*
{{1}}

Net sales: {{2}}
Purchases ÷ net sales (cash basis): {{3}}
Supplier prices: {{4}}
Flagged: {{5}}

Every figure opens to its source on the dashboard.
```

Sample values, one per variable, which Meta shows its reviewer; they are the full fixture's own figures, aged to the morning after its newest day:

| Variable | Sample |
|---|---|
| `{{1}}` | `Sales loaded to Mon 31 Aug, yesterday.` |
| `{{2}}` | `AED 9,493 on Mon 31 Aug: Al Quoz 4,385, Karama 2,987, Deira 2,122.` |
| `{{3}}` | `23.7% for the chain over 4-31 Aug (incomplete: 1 of 3 branches incomplete); Deira, the branch to look at first, 26.0% over 25-31 Aug.` |
| `{{4}}` | `Milk Powder is up AED 3.40 per kg since 21 Aug, against its last purchase on 12 Mar. AED 109 at stake on sales since.` |
| `{{5}}` | `Mint Lemonade sold AED 2,027 and kept -5.3%; the menu keeps 67.4%. (estimated)` |

The body begins and ends with fixed text, no two variables touch, and every variable follows a label, which is the shape Meta's review accepts most readily; the bold header is WhatsApp's own `*asterisk*` markup and renders bold on the phone.

**The sentence shapes** (composed in `brief.py`; `<>` marks a slot filled from the payload field named beside it; the fixed clauses are the brief's own and the quoted sentences are the wire's):

| Line | Shape | Fields |
|---|---|---|
| 1 the day | `freshness.sentence` verbatim; when `freshness.quality` is `estimated`: `<sentence> Figures below are estimated: the sales are older than a week.` | `freshness.sentence`, `freshness.quality` |
| 2 net sales | `AED <chain> on <day>: <Branch> <n>, <Branch> <n>, <Branch> <n>.` with at most four branches, then `across <count> branches`; a branch in the league whose `sales_through` is older than the day is appended as `; <Branch> loaded to <its day>`, and one with none as `; <Branch> has no sales loaded`; a chain of one branch: `AED <n> on <day>.` | `latest_day.net_sales`, `latest_day.branches[]`, `league[].sales_through` |
| 3 the ratio | `<pct>% for the chain over <window>` + optional ` (<word>: <first note>)`; then `; <Branch>, the branch to look at first, <pct>% over <its window>` when the league has two or more rows and `league[0].ratio_pct` is present, or `; <Branch>, the branch to look at first, has no ratio (<its first note>)` when it is withheld; a chain of one branch: `<pct>% over <window>` with its word; the chain's ratio withheld: `not available for <window> (<first note>)` | `total.ratio_pct`, `total.ratio_quality`, `total.ratio_notes`, `period`, `league[0]` |
| 4 the move | `moves[0].sentence` verbatim, then ` AED <n> at stake on sales since.` on a rise, ` AED <n> saved on sales since.` on a fall, ` Nothing sold since.` when the money is zero, and nothing after a basis change; no move: `no move of 5% or more since <period.from>.` | `price_moves.moves[0]` (`sentence`, `direction`, `money_at_stake`, `kind`), `period.from`, `PRICE_ALERT_MIN_PCT` |
| 5 the issue | `signals[0].sentence` verbatim, ` (estimated)` appended when `signals[0].quality` is `estimated` (the detail's own convention), `signals[1]` when `signals[0]` is the spike for line 4's material; none: `nothing flagged on the figures loaded.` | `signals[]` |

**The job payload** (`jobs.payload`, kind `send_brief`):

```json
{"tenant_id": "d0000000-0000-0000-0000-000000000001",
 "recipient_id": "…",
 "brief_date": "2026-09-01"}
```

**The Meta request** (`WhatsAppClient.send_template`, POST `/{phone_number_id}/messages`):

```json
{"messaging_product": "whatsapp",
 "recipient_type": "individual",
 "to": "9715XXXXXXXX",
 "type": "template",
 "template": {
   "name": "faida_daily_brief",
   "language": {"code": "en"},
   "components": [
     {"type": "body",
      "parameters": [
        {"type": "text", "text": "Sales loaded to Mon 31 Aug, yesterday."},
        {"type": "text", "text": "AED 9,493 on Mon 31 Aug: Al Quoz 4,385, Karama 2,987, Deira 2,122."},
        {"type": "text", "text": "23.7% for the chain over 4-31 Aug (incomplete: 1 of 3 branches incomplete); Deira, the branch to look at first, 26.0% over 25-31 Aug."},
        {"type": "text", "text": "Milk Powder is up AED 3.40 per kg since 21 Aug, against its last purchase on 12 Mar. AED 109 at stake on sales since."},
        {"type": "text", "text": "Mint Lemonade sold AED 2,027 and kept -5.3%; the menu keeps 67.4%. (estimated)"}
      ]}
   ]}}
```

A static URL button needs no component in the request.

**The outbound record** (`wa_messages`, `direction = 'out'`, `msg_type = 'template'`, `message_id` Meta's `wamid`):

```json
{"template": "faida_daily_brief", "language": "en",
 "parameters": ["Sales loaded to Mon 31 Aug, yesterday.", "…", "…", "…", "…"],
 "tenant_id": "…", "recipient_id": "…", "brief_date": "2026-09-01",
 "rehearsal": false,
 "error": null}
```

`status` moves `sent` to `delivered` to `read`, or to `failed` with Meta's error object copied into `error`, as the webhook's `statuses` entries arrive.

**The recipient row** (`0022_brief_recipients.sql`, applied in §8):

```sql
create table brief_recipients (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references tenants(id),
  phone_e164    text not null,                       -- digits only, no '+', as branches.wa_phone_e164
  timezone      text not null default 'Asia/Dubai',  -- an IANA name; the branches' default (0001:16)
  send_at_local time not null default '07:00',
  paused_at     timestamptz,
  created_at    timestamptz not null default now(),
  unique (tenant_id, phone_e164)
);
-- State only. Who asked for the brief, when, and on what evidence is the
-- `brief_recipient.added` audit row written in the same transaction (C8).
alter table brief_recipients enable row level security;

create unique index jobs_send_brief_uidx
  on jobs (kind, (payload->>'recipient_id'), (payload->>'brief_date'))
  where kind = 'send_brief';
```

**The dry run** (`python -m faida_api.brief --tenant <id> [--today 2026-09-01]`), printing the five lines as the phone will show them, then the parameter list as JSON; `--send --to 9715XXXXXXXX` sends that brief once through the same handler as a rehearsal (`rehearsal: true`, outside the day's key), which is how the sitting proves the template at any hour.

## 4. Work packages

Sizes as in `plan.md` §7.3: S ≤ half an agent-day, M ≈ one, L = multi-day.
Acceptance is demonstrable, never documentary.
Waves per §6.
The rows are numbered from WP-100 because M9's last row is 99 and M12 holds 119 to 124.

| WP | What | Size | Depends | Acceptance |
|---|---|---|---|---|
| 100 | **The deterministic filler.** A pure `brief.py` in `signals.py`'s shape (C15.1, C15.2, C15.9): `Brief(lines, parameters, quiet)` from one dashboard payload dict and the brief's date, the five sentence shapes of §3.1, `TEMPLATE_NAME`, `TEMPLATE_LANGUAGE` and `TEMPLATE_BODY` as constants, `render(brief)` producing the body as the phone shows it, the parameter rules (no newline, tab or four spaces; the 160-character cap; the four-branch rule), `PRICE_ALERT_MIN_PCT` imported for the no-move sentence, `contribution._money_words` and `signals._short_branch` imported and never copied. No I/O, no clock, no database | M | - | `tests/test_brief.py`: the five lines for each of the five committed mock fixtures (`full`, `partial`, `quiet`, `empty`, `nomenu`, chain scope) and for hand-built cases (one branch, twelve branches, a fall as the top move, a basis change, the spike duplicating the move, no signal, the chain ratio withheld, `league[0]` withheld); every number in every line equal to the payload field it came from; `empty` produces `quiet` and no lines; the stale fixture never contains "yesterday"; the word "food cost", "net profit" and "verified" absent from every rendering (the module called, never grepped); every parameter clean and under the cap; the twelve-branch rendering under 1,024 characters |
| 101 | **The read as a function, and the printed brief.** `dashboard.read_dashboard(db, tenant_id, *, today, date_from=None, date_to=None, branch_id=None) -> dict` extracted from the route with the route as a thin wrapper, and `python -m faida_api.brief --tenant <id> [--today <date>]` printing the five lines and the parameter JSON for that tenant from the live read, read-only - the milestone's first vertical slice and its consumer until Meta approves anything (the M12 `usage_report` precedent) | M | 100 | `tests/test_dashboard.py` green unchanged, the enumerated query list unchanged, the route's JSON byte-identical to the function's for the same inputs (one new test); the CLI printing the seeded chain's brief against a test database, its lines equal to `brief.compose` over the route's payload; the founder runs it against the live database and reads the demo chain's brief on the terminal |
| 102 | **The template send and the delivery record.** `WhatsAppClient.send_template(to, name, language, parameters)` with the §3.1 request shape beside `send_text`; `db.record_outbound_template(...)` writing the outbound row of §3.1; the webhook reading `value.statuses` and `db.stamp_outbound_status(message_id, status, error)` on rows it knows; `FakeMeta` recording template sends and answering a configurable template error (132001, 132000) | S | - | `tests/test_wa.py` or the flow suite: the exact JSON on the fake transport; a 500 raising as `send_text` does; `tests/test_webhook_pure.py`: `statuses` no longer dropped - a `delivered`, a `read` and a `failed` with its error stamped on the outbound row; a `delivered` arriving after `read` and a `read` after `failed` ignored; a status for an id with no row yet inserting the stub and the later record upserting into it with the further-along status kept; an inbound `messages` payload unchanged; every existing webhook and flow test green |
| 103 | **The recipient, the morning and the job.** The migration of §3.1 with its paste file and pre-flight (C7); `db.list_active_brief_recipients`, `enqueue_brief_once`, `outbound_brief_exists`, `brief_recipient_for_phone`, all `tenant_id` keyword-only where a tenant is known, the local-time arithmetic in Python with `zoneinfo`; the stale-running reclaim in `claim_job` (P12); `JobKind.SEND_BRIEF` and `worker.send_brief` (the read with the recipient's local date, `brief.compose`, the dedupe check, `send_template`, the record; quiet day logs and returns); the tick in `worker_loop` on every pass, once a minute, behind `BRIEF_ENABLED` and the noon cutoff (C15.5); the resolver amendment and `REPLY_BRIEF_RECIPIENT` (C15.10); `--send --to` on the CLI as the rehearsal door; `brief_recipients` in `TENANT_TABLES` | M | 100, 101, 102 | `tests/test_brief_job.py` against Postgres: the tick enqueues one job per due recipient and a second tick the same day none; a paused recipient none; a recipient at 07:00 Dubai due at 03:00 UTC and not at 02:59; past noon local skipped with the log line; the job sends the exact template JSON and writes the row; a Meta 500 retried three times then `failed` with the error and no row; a 132001 and a 132000 the same; the handler run twice for one payload sending once; a record write that raises after the send followed by a retry sending the brief a second time (C15.3's named limit, pinned); a row left `running` past `STALE_RUNNING_MINUTES` reclaimed once and never twice, an extract job included (P12); the tick enqueuing a due recipient while the queue still holds extract jobs; a recipient whose timezone name does not resolve logged and skipped while the next one is enqueued; two tenants, two recipients, each brief carrying its own tenant's figures and never the other's; the empty tenant sending nothing; a recipient phone texting in getting `REPLY_BRIEF_RECIPIENT` once and its row stamped, a branch-and-recipient phone treated as a branch; `test_tenancy.py` green with the table listed; every existing suite green |
| 104 | **The template, submitted** (founder task, the text ready to paste). In WhatsApp Manager under the test account: the §3.1 name, category, language, body, samples and button, submitted; the approval, the rejection reason if any, and the date recorded in this file's §8; the demo phone confirmed among the test number's recipients. The same submission under the production account when it exists | S (founder) | - | the template shows `APPROVED` in WhatsApp Manager; a `--send --to` rehearsal from the CLI lands on the founder's phone with the sample values replaced by the demo chain's own |
| 105 | **Live, and the record.** One sitting: the migration applied with its pre-flight, the API deployed by the merge, the recipient row for the founder's phone pasted with its audit row, the next 07:00 brief received and read back against `/dashboard` for the same morning, the outbound row's status read back; then `DEMO_RUNBOOK.md` §J (the morning brief: preconditions, the read-back, the failure lines), `plan.md`'s boxes and logs, `TODOS.md`, `README.md`'s Meta section, `CLAUDE.md` and `AGENTS.md` (an M10 paragraph), and PRD §27.4's wording to what shipped | S | 100-104 | the founder's phone shows the brief at 07:00 with the demo chain's real figures, every number equal to the dashboard's; `wa_messages` carries one `template` row for that morning with `delivered` or `read`; the loop reset leaves the recipient row and the week intact |

**The cut line, named in advance** (`plan.md` §2 rule 9): if the budget bites, the noon cutoff goes first (one constant and one clause), then the rehearsal flag on the CLI (a recipient row with `send_at_local` two minutes ahead proves the same thing more slowly), then the stub row for a status racing the record (the row reads `sent` in that rare order).
WP-102's status stamping is not on the list: the done-when's read-back needs the row to say `delivered` or `read`, and cutting the stamp would cut the proof.
WP-100, WP-101, WP-103, WP-104 and WP-105 are the done-when and cannot be cut.

### 4.1 Design direction: the message is the screen

There is no screen in M10.
The message is read on a phone in a chat list at seven in the morning, by someone who will not open the dashboard unless the message gives a reason to, so the message has to carry the answer and the reason in the order the dashboard carries them: what day this is about, what came in, what went out against it, what a supplier did, and what to look at.
Every variant below is the same template; only the five values change, because a Meta template is fixed text and the brief's honesty lives in the values.

**A normal morning** (the full fixture, read on 1 Sep):

```
*Faida morning brief*
Sales loaded to Mon 31 Aug, yesterday.

Net sales: AED 9,493 on Mon 31 Aug: Al Quoz 4,385, Karama 2,987, Deira 2,122.
Purchases ÷ net sales (cash basis): 23.7% for the chain over 4-31 Aug (incomplete: 1 of 3 branches incomplete); Deira, the branch to look at first, 26.0% over 25-31 Aug.
Supplier prices: Milk Powder is up AED 3.40 per kg since 21 Aug, against its last purchase on 12 Mar. AED 109 at stake on sales since.
Flagged: Mint Lemonade sold AED 2,027 and kept -5.3%; the menu keeps 67.4%. (estimated)

Every figure opens to its source on the dashboard.
[ Open dashboard ]
```

**An estimated morning** (hand-built from the full fixture: one pending paper inside the window moves the chain's ratio and its word, and the fixture's own branch-gap signal is the top one; a row in `test_brief.py`):

```
Sales loaded to Mon 31 Aug, yesterday.

Net sales: AED 9,493 on Mon 31 Aug: Al Quoz 4,385, Karama 2,987, Deira 2,122.
Purchases ÷ net sales (cash basis): 24.1% for the chain over 4-31 Aug (estimated: 1 invoice awaiting confirm); Deira, the branch to look at first, 26.0% over 25-31 Aug.
Supplier prices: Milk Powder is up AED 3.40 per kg since 21 Aug, against its last purchase on 12 Mar. AED 109 at stake on sales since.
Flagged: Deira keeps 6.5 points less of every dirham than the chain. (estimated)
```

**A stale morning** (the partial fixture, read on 12 Sep; one branch has stopped uploading):

```
Sales loaded to Mon 31 Aug, 12 days ago. Figures below are estimated: the sales are older than a week.

Net sales: AED 7,726 on Mon 31 Aug: Al Quoz 4,385, Karama 3,342; Deira has no sales loaded.
Purchases ÷ net sales (cash basis): 31.0% for the chain over 4-31 Aug (incomplete: 2 of 3 branches incomplete); Karama, the branch to look at first, has no ratio (no confirmed purchases 25-31 Aug).
Supplier prices: Milk Powder is up AED 3.40 per kg since 21 Aug, against its last purchase on 12 Mar. AED 91 at stake on sales since.
Flagged: Chicken 65 Dry sold AED 2,168 and kept 38.1%; the menu keeps 69.4%. (estimated)
```

The header is the nudge: the same figures arrive every morning with the age one day higher, and nothing else in the product asks for the upload.

**A quiet morning** (the quiet fixture: sales loaded, nothing moved, nothing flagged):

```
Sales loaded to Mon 31 Aug, yesterday.

Net sales: AED 4,135 on Mon 31 Aug: Al Quoz 2,116, Karama 1,230, Deira 790.
Purchases ÷ net sales (cash basis): 54.0% for the chain over 4-31 Aug; Deira, the branch to look at first, 74.3% over 25-31 Aug.
Supplier prices: no move of 5% or more since 4 Aug.
Flagged: nothing flagged on the figures loaded.
```

**A chain of one branch** (the same shapes with the chain clauses dropped):

```
Sales loaded to Mon 31 Aug, yesterday.

Net sales: AED 4,385 on Mon 31 Aug.
Purchases ÷ net sales (cash basis): 38.7% over 25-31 Aug.
Supplier prices: Cream is down AED 1.50 per litre since 26 Aug. AED 44 saved on sales since.
Flagged: nothing flagged on the figures loaded.
```

**An empty tenant** (the empty fixture): no message.
The job completes, the log says `brief skipped: nothing loaded for tenant <id>`, and the recipient hears nothing until the first sales day is loaded.

**A fall as the biggest move**, and **a basis change**, and **the spike duplicating the move**, and **the chain ratio withheld** are single-line variants: `Cream is down AED 1.50 per litre since 26 Aug. AED 44 saved on sales since.`; `Karak Tea Dust is priced from a different pack now, so there is no before and after to show.` with nothing after it; the issue line moving to `signals[1]`; `not available for 4-31 Aug (3 of 3 branches with nothing loaded)`.
Each is a row in `test_brief.py`.

**The phone's rendering limits, and what the shapes do about them:**

- Meta caps the body at 1,024 characters after the values are in; the fixed text is 152, the five values are capped at 160 each by the filler, and the widest committed rendering (the normal morning above) is 584.
  A twelve-branch chain names four branches and the count, so the net sales line cannot grow with the chain.
- A parameter value may not contain a newline, a tab or four consecutive spaces, so each value is one paragraph and the line breaks belong to the fixed body; every value ends with a full stop so a label and its value read as one sentence.
- `*asterisks*` in the fixed body render bold; the values carry no markup, because a supplier name with an asterisk in it would otherwise toggle bold mid-line.
- On a 390 px phone a chat bubble wraps at roughly 35 to 40 characters, so the normal morning is about twenty lines and one thumb-scroll; the chat list preview shows the first line and a half, which is why the bold title and the day come first and the figures after.
- The URL button renders full-width under the bubble with the text `Open dashboard` (25 characters is Meta's cap); a static URL shows no preview card.
- No emoji, no icon and no colour: the brand's rule that colour never carries meaning alone (`plan.md:92`) holds trivially in a medium that has none, and the quality words are words.
- Arabic and Malayalam are out of scope (the founder's answer; `plan.md:93`); Latin digits and the `÷` sign render in every WhatsApp client.

## 5. Proposals for the founder (each with a recommendation)

**None of these is decided.**
Three questions were answered by the founder at the start of the session (the chain has not started; the founder's demo phone first; English only) and are carried in P2, P7 and P8 as answers to confirm at approval; every other row is open, and the session proceeded on the recommended option so that §3, §4, §6, §7 and §8 describe one consistent plan.
P12, P13 and P14 were added by the outside voice's review (findings 4, 12 and 13 in the report).

| # | Proposal | Recommendation and why |
|---|---|---|
| P1 | **The scheduler.** Nothing in the product ticks at a wall-clock time (`worker.py:193-213`). Options: (a) the worker's own tick - once per idle poll, one query for recipients whose local morning has come and who have no job for today, enqueued through a unique index; (b) an external cron (Railway's cron service, a GitHub Actions schedule) hitting one endpoint or running one command at 07:00; (c) an in-process sleeper task computing each recipient's next 07:00 | **(a), the worker's tick.** It is the rule in `plan.md:87`: the `jobs` table is the queue and the worker owns it, no broker. The cost is one cheap query every two seconds when the queue is idle, and the unique index makes the tick idempotent whether it runs once or from two instances. (b) needs a way in: there is no API secret by decision (`CLAUDE.md`, M7), so an endpoint would reintroduce one, and a cron *command* is a second process against the same database with its own deploy and its own cold start at 03:00 UTC; it also fires whether or not the API is up, which is backwards. (c) is a scheduler subsystem with restart semantics for a job the queue already knows how to hold until `run_after` (`db.py:3589`). The one thing (a) cannot do is fire while the API is down, and C15.5's catch-up inside the morning window covers a deploy |
| P2 | **The recipient model.** No table holds an owner's phone (§2). Options: (a) a `brief_recipients` table (§3.1) - tenant, phone, timezone, send time, pause - with the pilot's rows written by the founder's paste file together with their audit row, and the door and screen deferred; (b) two columns on `tenants` (`brief_phone_e164`, `brief_timezone`), no new table; (c) an environment variable listing phones, no schema | **(a), the table, the pilot's row by paste.** The founder's answer names the first recipient - the demo phone - and a chain with two partners is the ordinary case, which (b) cannot hold. Opt-in is a fact Meta's policy and PRD §26's audit model both want recorded, with a time, a way and the evidence, which is the `brief_recipient.added` audit row's job (C8; the review's finding 9 took the duplicate consent columns off the table), and pausing must not be nulling the phone. (c) makes a second tenant a deploy and puts a customer's phone in Railway's variables. The migration is one table and one index; the paste is the branch-phone precedent (`demo_seed.sql:562-570`), and it writes the `brief_recipient.added` audit row the future door will write. A settings screen for one phone field, for one tenant, is the vertical slice rule's letter and not its point; the trigger for the door is in §9 |
| P3 | **Sentence slots or number slots.** The checklist says "fixed sentence shapes, number slots". Options: (a) one template whose five variables are labelled sentence-slots, each value composed in Python from the read (§3.1); (b) number-only slots inside fixed sentences ("net sales were AED {{1}}"), which needs one template per shape - a normal day, a stale day, a withheld ratio, no move, no signal - each reviewed separately, and no way to send a null | **(a), one template, five labelled slots.** It is what P8 was pinned for: "C13.5 puts every sentence on the wire so the slots are free" (`plan.md:1248`). The fixed labels are the template's honesty to Meta's reviewer (a variable after "Purchases ÷ net sales (cash basis):" cannot be used for anything else), and the values are the product's honesty to the owner - the stale morning and the withheld ratio are the same template saying a different true thing. (b) multiplies templates by variants, each an approval and a rejection risk, and still cannot say "no ratio" in a number slot. The sentence shapes themselves are fixed and tested (WP-100), so the checklist's "no generation" holds either way |
| P4 | **The quiet day.** What is sent when there is nothing new. Options: (a) silence only when nothing was ever loaded; otherwise a brief every morning, the day named and aged in the header, the stale clause after a week; (b) a brief only on a morning when the newest loaded day moved since the last brief; (c) a brief every morning with a separate "nothing new" template | **(a).** A till that exports weekly gives seven mornings of the same sales figures, and the product's answer to that is not silence but the header saying "12 days ago" - the only reminder to upload that exists anywhere. The price moves and the signals still change as papers land. (b) turns the brief into a notification of the upload, which the owner did not do and cannot act on, and breaks the done-when's "each morning"; the first morning it does not arrive is the morning the habit ends. (c) is a second template for a sentence the first already carries. A tenant with nothing loaded ever has nothing to say and a template costs money; that is the one silence |
| P5 | **The tap-through.** Options: (a) a static button to `/dashboard` behind the login gate - one password entry on the phone, then the session cookie (`proxy.ts:14-19`); (b) a signed-in magic link per brief, minted through Supabase's admin link and carried in the button's dynamic suffix | **(a).** A magic link is a session in a chat log: anyone holding the phone, or anyone the message is forwarded to, opens the books, and the link either expires before the owner taps it or lives long enough to be the credential the product refused to hold anywhere (`auth.py:16-20`). The login gate already lands a tap on `/dashboard` (`gate.ts:57-62`) and the dashboard is built for 390 px. If the pilot owner says the password stops them, (b) is one `generate_link` call and a dynamic URL button, and §9 carries it with that trigger. A static URL also means a template that never needs a parameter for its button, one fewer thing to mismatch |
| P6 | **Per-branch briefs for managers.** PRD §27.4's "optionally each branch manager". Options: (a) defer on WP-78's trigger, a pilot chain asking for a branch manager on the screen (`TODOS.md:200-221`); (b) build the row now with a nullable `branch_id` and the read under `branch_id` | **(a), defer.** There is no branch user, no branch phone that is a person, and no one who has asked; a manager's brief without a manager's role sends a branch's money to a phone whose relationship to the branch is a row nobody vouched for. When WP-78 lands it is one nullable column, `?branch=<id>` in the button (a template edit, reviewed again) and the read's existing filter (`dashboard.py:473-476`) |
| P7 | **Language.** Answered at the start of the session: **English only for the pilot**, the demo-scope decision extended (`plan.md:93`, `:1343`). The alternative is one template per language, and every sentence the brief carries is composed in English in five Python modules, so a second language is a second composer for each - the trigger in §9 is a pilot owner who does not read English | **Confirm English only** |
| P8 | **The rehearsal on the test number, and what the done-when means before the production chain.** Answered at the start: only the test number is live, and the first recipient is the founder's demo phone. Options: (a) submit the template under the test account now, rehearse to the founder's phone at 07:00, and call that the done-when's proof, the pilot owner's phone following the production chain; (b) wait for the production chain and send nothing before it | **(a).** The test number sends templates to its registered recipients, a template created under the test account goes through the same review, and the demo phone is registered (`Docs/DEMO_RUNBOOK.md:35`; `README.md:167`). The rehearsal proves everything this repository can prove - the read, the words, the tick, the record, the button - on a real phone at 07:00, weeks before verification clears. What it cannot prove is the production number's category rate and quality rating, which is §8's last step. (b) makes the milestone wait on the one clock nobody here controls |
| P9 | **Which field is the biggest price move.** P8 named `signals[0..1]`; WP-99 then added `price_moves` (2026-09-07). Options: (a) `price_moves.moves[0]` - each material's latest move inside the window, both directions, ranked by the dirhams moved, with the money at stake or saved; the issue slot `signals[0]`, or `signals[1]` when the top signal is the spike for the same material; (b) the price spike among the signals, rises only, and nothing on a morning when the biggest move is a fall | **(a).** A fall is a fact an owner acts on too (the panel's own reason, `dashboard.py:355-357`), and the block's sentence is the one the dashboard and the Menu card print, so the phone and the screen quote one move in one set of words. The four slots stay four; the P8 row gains the field name. The money clause is the brief's own ("AED 109 at stake on sales since."), pinned by a test to `money_at_stake` so the amount can never differ from the panel's |
| P10 | **The owner replies to the brief.** Today a phone no branch is registered to gets "This number isn't set up yet, so I can't read invoices from it. Ask the owner to add this number" (`replies.py:53-56`) - to the owner. Options: (a) a recipient that is not a branch phone is stamped and gets one fixed reply a day saying what the number does ("This number receives the morning brief. To forward invoices, use a branch's phone."), the unknown-sender pattern with different words; (b) silence: stamped, no reply; (c) leave it | **(a).** "Thanks" to a brief deserves an answer, and the answer should not tell the owner to ask the owner. It is one lookup after the branch lookup in the one resolver (C2 amended, C15.10), one reply constant, and the existing once-a-day silence. (b) is a phone that talks every morning and never listens. A phone that is both a branch and a recipient - the founder's - stays a branch, so the rehearsal changes nothing about the demo |
| P11 | **The morning window.** The tick catches up after a deploy or an outage. Options: (a) send when due, up to a noon cutoff in the recipient's timezone, then skip the day with a log line; (b) send whenever the tick returns, however late | **(a).** A "morning brief" at ten at night is noise, and by then tomorrow's is nine hours away; five hours of grace covers any deploy and most outages. The cutoff is one constant with its reason beside it and one clause in the due query |
| P12 | **The stranded job** (the review's finding 4). `claim_job` takes `queued` rows only and nothing reclaims a row left `running` by a process that died mid-job (`db.py:3583-3605`); a graceful stop finishes the job first (`main.py:64-67`), a hard kill does not. Every job kind has lived with this; the brief is the first whose stranding shows nowhere (a stranded extract job is a document stuck in `processing` on the invoice list). Options: (a) fold a reclaim into WP-103: `claim_job` also takes a `running` row untouched for `STALE_RUNNING_MINUTES` (10), attempts counted, for every kind; (b) accept it for the pilot, name it in the failure table, defer the reclaim with the trigger "a job found `running` for over an hour" | **(a), the reclaim, in WP-103.** It is one clause and one constant, every handler is already idempotent under retries by C2's rule (`CLAUDE.md`), attempts stay capped at three, and a brief interrupted at 07:00 is sent within the morning instead of never. The cost is that a legitimately slow job over ten minutes runs twice; the extraction target is twenty seconds and the worst observed was 155 s, so the constant has fifty times the headroom. (b) leaves the one morning message the product makes on a queue that can lose it silently |
| P13 | **If Meta approves the template as marketing** (the review's finding 12). `plan.md` §3 fixes a utility template (`plan.md:83`) and PRD §11's cost model assumes it (`Docs/PRD.md:251`). Options: (a) the rehearsal on the free test number proceeds in either category; the production cutover to the pilot owner waits for a utility approval - the wording edited to the rejection reason, or the category appealed; (b) accept marketing for the pilot's one message a day, at the marketing rate and under per-user marketing limits (131049) | **(a).** The brief is an account update the owner asked for, which is what Meta's utility category describes, and the body is labelled facts with nothing offered; if a reviewer still reads it as marketing the honest move is to change the words until it reads as what it is, not to pay the marketing rate for a utility message. The test number costs nothing, so the rehearsal and the done-when on the founder's phone do not wait. The row in §7 says the same |
| P14 | **What authorises the pilot owner's row** (the review's finding 13). The founder can authorise the founder's own phone; nobody here can manufacture the pilot owner's consent to a daily message about their money. Options: (a) the row is pasted only with the owner's own request in hand - a WhatsApp text from the owner's phone to the number, or a signed line on the onboarding sheet (PRD §28 step 2, where branch phones are registered) - and the `brief_recipient.added` audit row's detail names it (`{"evidence": "wa:<message id>"}` or `{"evidence": "onboarding sheet <date>"}`), the paste refusing a row without one; (b) the founder's word alone, recorded as such | **(a).** Meta's policy requires opt-in before a business-initiated template, PRD §26's audit model records the reason on every decision, and the evidence pointer costs one key in a detail that exists anyway. For the founder's demo phone the evidence is this decision, written into the row's detail the same way |

## 6. Delegation waves and parallel lanes

| Step | Modules touched | Depends on |
|---|---|---|
| WP-100 the filler | `apps/api/src/faida_api/brief.py` (new), `apps/api/tests/test_brief.py` (new), the five fixture files read from `apps/web/src/lib/mock/dashboard/` | - |
| WP-101 the read and the dry run | `apps/api/src/faida_api/dashboard.py` (the extraction, additive), `apps/api/src/faida_api/brief.py` (`__main__`), `apps/api/tests/test_dashboard.py` (one test) | 100 |
| WP-102 the send and the record | `apps/api/src/faida_api/{wa,webhook,db}.py` (`send_template`; `statuses`; two message functions), `apps/api/tests/{conftest,test_webhook_pure,test_flow}.py` | - |
| WP-103 the recipient, the morning, the job | `supabase/migrations/0022_brief_recipients.sql` (new), `Docs/apply_m10_migration.sql` (new), `apps/api/src/faida_api/{contracts,worker,replies,config,db,brief}.py`, `apps/api/tests/{test_brief_job,test_tenancy,test_contracts}.py` | 100, 101, 102 |
| WP-104 the template | WhatsApp Manager (the founder); this file's §8 for the record | - |
| WP-105 live | `plan.md`, `TODOS.md`, `README.md`, `CLAUDE.md`, `AGENTS.md`, `Docs/DEMO_RUNBOOK.md`, `Docs/PRD.md` §27.4 | all |

- **Wave 0 (manager, no code):** C15 and the C2 amendment pinned in `plan.md` §7.2 as decided; the rows in §7.3; one Decision Log row per §5 decision; the `TODOS.md` entries from §9.
- **Wave 1, two lanes.** Lane A = WP-100 then WP-101 (one lane: `brief.py` and the extraction in `dashboard.py`, whose output is the filler's input). Lane F = WP-104, the founder, from the first day, because Meta's clock is the long one and the text is ready. No file overlap.
- **Wave 2, one lane.** Lane B = WP-102 (`wa.py`, `webhook.py`, two functions in `db.py`'s messages section, the fake and its tests). It could run beside Lane A - the files are disjoint - and does so if a second lane is available; it is listed second only because Lane A is the vertical slice.
- **Wave 3, one lane.** Lane C = WP-103, the only lane that touches `worker.py`, `contracts.py`, `config.py`, the migration and `db.py`'s jobs section, after A and B have merged. Sequenced, not parallel, because it edits the resolver every inbound message runs through (C2) and the `db.py` sections both earlier lanes touched.
- **Wave 4: WP-105**, one sitting with the founder, on the morning after the recipient row lands.

The migration is `0022_brief_recipients.sql` whether or not M12's `0021_usable_share.sql` has landed first (C15.12): the two touch different tables, the directory applies in sorted order, and a number claimed now cannot be claimed twice.

## 7. The tests that gate it

- `tests/test_brief.py` (WP-100): every C15 sentence shape as a pure case with no database - the five committed fixtures at chain scope and the hand-built cases named in row 100; every number in a line equal to the payload field it came from, read back by the test from the same dict; the stale fixture rendering without the word "yesterday" and the fresh one with it; the empty fixture producing `quiet`; the forbidden phrases absent from every rendering by calling the module (never by grepping code); each parameter free of newlines, tabs and four consecutive spaces and at or under 160 characters; the twelve-branch rendering under 1,024; exactly five parameters, asserted; the fall, the basis change, the duplicate spike and the withheld ratio each one line; a chain of one branch dropping the chain clauses; the money clause equal to `money_at_stake` rounded half up.
- `tests/test_dashboard.py` (WP-101): green unchanged, the enumerated `READS` list unchanged (`test_dashboard.py:53-75`), and one new case: the route's JSON equal to `read_dashboard`'s for the same tenant, period and `today`.
- `tests/test_webhook_pure.py` and the flow suite (WP-102): the template request's exact JSON on the fake transport; a 500 raising; `statuses` stamping `delivered`, `read` and `failed` with the error on an outbound row, a stamp never moving backwards, a status before the record inserting the stub the record then upserts into, inbound `messages` payloads unchanged.
- `tests/test_brief_job.py` (WP-103), against Postgres: the tick's idempotence (one job per due recipient, a second tick none), the tick firing while the queue holds extract jobs, the timezone boundary (03:00 UTC due, 02:59 not), a timezone name that does not resolve skipped with the next recipient enqueued, the noon cutoff, the paused row, the send with the exact JSON and the row written, the three retries then `failed` on a 500, a 132001 and a 132000, the handler run twice sending once, the record write raising after the send and the retry sending a second copy (the named limit), a `running` row reclaimed once after `STALE_RUNNING_MINUTES` (P12), two tenants' briefs carrying their own figures, the empty tenant sending nothing, the recipient reply and its stamp, the branch-and-recipient phone treated as a branch.
- `tests/test_tenancy.py`: `brief_recipients` in `TENANT_TABLES`; no new route, so the matrix is unchanged and the route-coverage test proves it.
- `tests/test_contracts.py`: green with the third job kind; the status vocabularies it checks against the migrations are untouched.
- **Regressions, mandatory:** the full API suite green with zero skips; the eval smoke green because no extraction code changes; the web suite, `tsc`, lint and build green because no web file changes.
- **The live proof** (WP-105): the founder's phone at 07:00, the message read back line by line against `/dashboard` for the same morning, and the outbound row's status read back from `wa_messages`.
- Banned as before: tests that grep code text, framework tests, coverage targets for their own sake.

### Failure modes, one per new path

| Path | Failure | What happens | Where it is seen |
|---|---|---|---|
| the send | Meta answers 500, or the token has expired (401) | the job fails, retries twice at 30 s (`db.py:28-29`), then `failed` with the error in `last_error`; no `wa_messages` row; tomorrow is a new job | `jobs`; the runbook's failure playbook line for the morning brief (WP-105) |
| the send | the template is not approved yet, paused for quality or disabled (132001, 132015, 132016, synchronous) | the same path; the error names the template state | `jobs.last_error`; WhatsApp Manager |
| the send | the number is unreachable (131026, asynchronous) | the row is written as `sent`, then stamped `failed` with the error when the status arrives | `wa_messages.status` |
| the send | Meta accepted the message, then the record write raised | the retry finds no row and sends the brief once more, 30 s later - C15.3's named limit, pinned by a test | two rows for one morning |
| the send | the process is killed between the send and the record (a hard kill, not a deploy: the lifespan stop finishes the running job, `main.py:64-67`) | today the job stays `running` for ever and the day's brief is silently one of sent-and-unrecorded or never sent (`db.py:3583-3605`); with P12's reclaim it is retried within ten minutes and the row above applies | `jobs.status = 'running'` with an old `updated_at` |
| the send | the template was edited to a different variable count (132000) | the filler asserts five before the send, so the mismatch fails in a test; a template edited behind the code fails the job with Meta's error | `test_brief.py`; `jobs.last_error` |
| the tick | two API instances, or a restart mid-tick | the unique index makes the second enqueue a no-op | nothing to see, which is the point |
| the tick | a morning-long extraction backlog | the tick runs on every pass of the loop, once a minute, before a job is claimed, so a busy queue does not starve it | `test_brief_job.py` |
| the tick | a recipient's timezone name does not resolve | that row is logged and skipped; every other recipient is enqueued; the paste's pre-flight checks the name before the row exists | Railway logs; the pre-flight |
| the tick | the API was down at 07:00 | the tick catches up on return inside the morning window; past noon the day is skipped with a log line | Railway logs |
| the tick | a tenant has no recipient row | nothing is enqueued and nothing is logged per day, because that is the normal state of every tenant but the pilot's | the sitting's read-back |
| the recipient | the owner replies "thanks" | stamped `ignored_brief_recipient`, one fixed reply a day, nothing created (C15.10); today it would be told to ask the owner | `wa_messages.status` |
| the recipient | the phone is also a branch phone (the founder's) | a branch: C5 applies, the brief is unaffected | - |
| the read | the read raises (the database is down) | the job fails and retries; nothing is sent partially, because the message is composed before the send and sent once | `jobs` |
| the filler | a chain with many branches, or a long supplier name | the four-branch rule and the 160-character cap keep the body under 1,024; a slot over the cap is a filler bug the test catches, never a truncated message | `test_brief.py` |
| the filler | the chain ratio or `league[0]`'s ratio is withheld | the line says so with the read's own note; never 0% (C11.6) | `test_brief.py` |
| the template | Meta rejects the submission | nothing to code: the founder edits the wording to the rejection reason and resubmits; the tick must not be enabled before approval (§8) | WhatsApp Manager |
| the template | Meta approves it as marketing rather than utility | the rehearsal on the free test number proceeds either way; the production cutover waits for a utility approval unless the founder decides otherwise (P13); marketing costs more and carries per-user limits (131049) | WhatsApp Manager; the rate card; P13 |
| the template | the web host changes (a custom domain) | the button's URL is fixed text: a template edit and a review | §9's entry |
| the 24-hour window | the recipient wrote in an hour ago | irrelevant: a template is accepted inside and outside the window, and inside one it is free; the brief never calls `send_text`, and a test pins the request type | `test_brief_job.py` |
| the 24-hour window | someone sends the brief as free text | 131047, asynchronously, and the product would never see it (`webhook.py:33`); the reason the brief is a template and the reason WP-102 reads `statuses` | - |
| the category | the utility template drifts into promotional wording in a later edit | Meta may recategorise on review; the body's fixed text is a constant in `brief.py` with this file as its reason | WP-104's record |

## 8. Migration and cutover order

Two chains, one of code and one of Meta's, that meet at the first 07:00.

**Meta's chain (the founder; external, serial, the long clock):**

1. Now, under the test account: create `faida_daily_brief` in WhatsApp Manager from §3.1 (name, Utility, English, body, the five samples, the button); submit; note the date.
   Review is "up to 24 hours".
   Confirm the demo phone is among the test number's registered recipients (`README.md:167`) and the access token's `expires_at` is 0 (`Docs/DEMO_RUNBOOK.md:24-34`).
2. On approval: the rehearsal send from the CLI (`--send --to`) at any hour, then the 07:00 brief after the recipient row lands (step 6 below).
   This is the done-when on the founder's phone.
3. In the background, the production chain `plan.md:83` has described since M5: Meta Business verification of the legal entity; a WhatsApp Business Account on the verified business; a sender number bought or migrated, with its display name reviewed; a payment method on the account, because a utility template outside an open window is charged; the same template submitted under that account and approved.
4. Cutover to production is three environment variables on Railway (`META_PHONE_NUMBER_ID`, `META_ACCESS_TOKEN` as a System User token that never expires, and the app secret if the app changes), the webhook re-pointed and the app re-subscribed to the new account (`Docs/DEMO_RUNBOOK.md:16-22`), and the pilot owner's recipient row.
   The template name and the code do not change.

**The code's chain:**

1. **Wave 1 merges** (WP-100, WP-101): no schema, no behaviour change, the route byte-identical; Railway deploys; the founder runs `python -m faida_api.brief --tenant <demo chain>` against the live database and reads the demo chain's brief.
   The first vertical slice is done before Meta has answered anything.
2. **Wave 2 merges** (WP-102): the client can send a template and the webhook stamps statuses; nothing sends, because nothing enqueues.
3. **The migration**, `0022_brief_recipients.sql`, applied by the founder from `Docs/apply_m10_migration.sql` after a `pg_dump` and the read-only pre-flight checks (0020 present, 0021 present or absent - the two are independent - no `brief_recipients` table, and `select now() at time zone 'Asia/Dubai'` answering, the check the recipient's timezone name gets again before its row is pasted), in the 0019 and 0020 shape; read-back: the table present with RLS on, the index present, zero rows.
4. **Wave 3 merges** (WP-103); Railway deploys; the tick runs and finds no recipient, so the queue stays empty.
   `BRIEF_ENABLED` is unset (true) because an empty table is the safe state; it exists for the day a brief must stop without SQL.
5. **The template is approved** (Meta's step 2); the rehearsal from the CLI proves the request shape against the real number.
6. **The recipient row** for the founder's demo phone, pasted with its `brief_recipient.added` audit row whose detail names the evidence (for the founder's own phone, this decision; for the pilot owner's, the owner's request, P14); the next 07:00 Dubai is the live proof; the sitting reads it back (WP-105).
7. **Production** (Meta's step 4): the template approved as utility (P13), the same code, the pilot owner's row on the owner's own request (P14), and the first morning the pilot owner reads.

Rollback: `BRIEF_ENABLED=false` on Railway stops every send in one variable; `paused_at` on the row stops one recipient in one SQL statement; Railway redeploys the previous build in one click.
The migration is additive (one table, one index) and old code ignores both, so a code rollback with the schema in place is complete; dropping the table is the reverse paste.

## 9. NOT in scope, and what already exists

**NOT in scope** (each with its trigger; every entry goes into `TODOS.md` under an M10 heading in the M9 and M12 shape):

- **A door and a screen for the recipient** (add, pause, resume, change the phone, the send time): trigger: the second tenant, or the pilot owner asks to change the number.
  It is one `POST`/`DELETE /api/briefs/recipients` pair with the three audit actions and a settings section the console does not have yet; the paste file is the pilot's door, and a row's label is the door's to add when it exists.
- **"brief off" and "brief on" from the recipient's own phone**: trigger: the pilot owner replies asking to stop, or Meta's quality rating for the template dips.
  C15.10 gives the recipient phone a stamp and a reply; a pause by chat is one parser in `confirm.py`'s shape writing `paused_at` with the `whatsapp:<phone>` actor.
- **Per-branch briefs for the branch manager** (P6): trigger: WP-78's own, a pilot chain asks for a branch manager on the screen (`TODOS.md:200`).
  One nullable `branch_id` on the recipient row, the read under the branch filter, `?branch=` in the button, a template edit.
- **A second language** (P7): trigger: a pilot owner who does not read English.
  One template per language, and a composer per language for the five modules whose sentences the brief carries (`dashboard.py`, `signals.py`, `ratio.py`, `contribution.py`, `brief.py`).
- **A magic-link tap-through** (P5): trigger: the pilot owner says signing in on the phone stops them.
  One `generate_link` call at send time and a dynamic URL button; the expiry and the forwarding risk decided then.
- **The cash-approval notice as a utility template**: trigger: a branch phone misses an approval notice because the window had closed (the WP-74 row's own gap, `plan.md:1276`).
  Once M10's template machinery exists it is a second template and one call in `api.py:712-737`.
- **Delivery and read status on a screen**: trigger: an owner disputes receiving a brief.
  WP-102 stamps the row; the read is SQL at the sitting until someone needs it on a screen.
- **A weekly digest, or a cadence per recipient**: trigger: a customer quote.
  `send_at_local` is a time; a weekday set is a column and a clause.
- **Meta's template status webhooks** (`message_template_status_update`: paused, disabled, category changed): trigger: a template paused once in production.
  The app subscribes to the `messages` field only (`Docs/DEMO_RUNBOOK.md:16`); the day a template pauses, the send fails synchronously anyway (132015).
- **A dynamic URL button**: trigger: the manager's brief, or a custom domain that changes per tenant.
  Meta's URL variable is appended to the end of the URL and percent-encoded, which is why the pilot's button is static.
- **The fifth slot from M12**: the existing entry at `TODOS.md:826-834` names `usage.answer`, which M12's D9 removed; rewritten to the top material row's own words (`usage.quantity_words` and the direction sentence) with the same trigger: the template is drafted and the founder wants the shelf in it.
  It is a sixth variable and a template edit.
- **A timezone on the tenant**, or the business-day arithmetic (`TODOS.md:323`): the recipient row carries its own timezone, which is the fact the brief needs; the route's UTC `today` stays a stated limit.
- The production Meta chain itself (business verification, the sender, the rate) is the founder's track and not a work package; PRD §11's "verify the live UAE utility rate" is done when the rate card is read at step 3 of Meta's chain.
- Anything conversational: a reply that asks a question gets the fixed recipient reply; PRD §25.4 removed the conversational agent and nothing here reopens it.

**What already exists and is reused, not rebuilt:** the dashboard read and every sentence on it (extracted into a function, never copied); `freshness_sentence`, `signals.move_sentence`, the three signal sentences, `_short_branch`, `contribution._money_words`, `ratio._short_date` and `window_words`; `ratio.resolve_period`'s default period; the mock's five fixtures as the filler's inputs; `WhatsAppClient` and its injected transport, `FakeMeta`; the `jobs` table, `claim_job`'s `run_after`, `finish_job`'s three attempts, and the 0018 partial-unique-index pattern behind `enqueue_once`; the unknown-sender stamp-then-reply pattern and its once-a-day silence; `record_outbound_message`'s row shape; `audit_events` and `_insert_audit_event`; `branches.timezone`'s default; the login gate's `?next=` round trip and the 390 px dashboard; the runbook's token and subscription checks; `test_tenancy.py`'s table list and the enumerated `READS` guard.

## 10. Implementation Tasks

Synthesized from this decomposition and its review.
Each task derives from a specific row above.
Run with Claude Code; checkbox as you ship.

- [ ] **T1 (P1, human: ~1 day / CC: ~2h)** - `apps/api` - WP-100: `brief.py`, the five sentence shapes, the constants, the parameter rules, `render`, and `test_brief.py` over the five fixtures and the hand-built cases
  - Surfaced by: §2 "three of the four slots"; §3 C15.1, C15.2, C15.9; §5 P3, P9
  - Files: `apps/api/src/faida_api/brief.py`, `apps/api/tests/test_brief.py`
  - Verify: `pytest tests/test_brief.py`; every number traced to its field; the stale fixture without "yesterday"
- [ ] **T2 (P1, human: ~4h / CC: ~1h)** - `apps/api` - WP-101: `read_dashboard` extracted, the route a wrapper, the CLI printing the brief
  - Surfaced by: §2 "the dashboard read is a route handler"; §3 C15.1, C15.6
  - Files: `apps/api/src/faida_api/dashboard.py`, `apps/api/src/faida_api/brief.py`, `apps/api/tests/test_dashboard.py`
  - Verify: `pytest tests/test_dashboard.py` green unchanged plus the equality case; the CLI against a test database
- [ ] **T3 (P1, human: ~4h / CC: ~1h)** - `apps/api` - WP-102: `send_template`, the outbound template row, the `statuses` stamp, the fake
  - Surfaced by: §2 "the client sends free text", "what the record can and cannot say"; §3 C15.4
  - Files: `apps/api/src/faida_api/{wa,webhook,db}.py`, `apps/api/tests/{conftest,test_webhook_pure,test_flow}.py`
  - Verify: the exact JSON; `statuses` stamped; every existing flow test green
- [ ] **T4 (P1, human: ~1.5 days / CC: ~3h)** - `apps/api` + `supabase` - WP-103: the migration and paste, the recipient reads, the tick, the job, the resolver amendment, the rehearsal flag
  - Surfaced by: §3 C15.3, C15.5, C15.7, C15.10, C15.12; §5 P1, P2, P4, P10, P11
  - Files: `supabase/migrations/0022_brief_recipients.sql`, `Docs/apply_m10_migration.sql`, `apps/api/src/faida_api/{contracts,worker,replies,config,db,brief}.py`, `apps/api/tests/{test_brief_job,test_tenancy,test_contracts}.py`
  - Verify: `pytest` green with zero skips; the tick's idempotence and the timezone boundary; two tenants isolated
- [ ] **T5 (P1, founder: ~30 min plus Meta's review)** - WhatsApp Manager - WP-104: the template submitted from §3.1, the approval recorded
  - Surfaced by: §2 "the test number"; §5 P8
  - Verify: `APPROVED` in WhatsApp Manager; the CLI rehearsal on the founder's phone
- [ ] **T6 (P1, human: ~2h / CC: ~30 min)** - live - WP-105: the migration applied, the recipient row pasted, the 07:00 brief read back, the records
  - Files: `plan.md`, `TODOS.md`, `README.md`, `CLAUDE.md`, `AGENTS.md`, `Docs/DEMO_RUNBOOK.md`, `Docs/PRD.md`
  - Verify: the phone at 07:00 against `/dashboard`; `wa_messages` with one `template` row for the morning

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | - | not required: the milestone is the plan's own checklist item, PRD §27.4 names it the primary surface and PRD §31 lists it as item 10 of the MVP |
| Codex Review | `/codex` consult | Independent 2nd opinion | 1 | issues_found (folded) | 13 findings - 4 blockers, 7 should-fix, 2 nits - 13 folded, 0 kept, 0 dismissed; three proposals added to §5 (P12, P13, P14), one contract paragraph rewritten (C15.3), the migration's number fixed |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 0 | **RECOMMENDED, NOT APPROVED** | the session ran unattended beside WP-96's sitting; its substance is §2 to §9 with the outside voice; a review with the founder present, as M9 and M12 had, is the next step and the §5 decisions are its agenda |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | - | there is no screen: the message is the screen, and §4.1 writes every variant out; no board |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | - | - |

### Review - unattended, 2026-09-07 evening (Codex as the outside voice)

Scope: M10 the daily WhatsApp brief (WP-100 to WP-105, C15, the C2 amendment), reviewed 2026-09-07 at master `64f9793` on the lane branch `m10-decomposition`, before any feature code.
Mode: consult, medium reasoning, read-only, the file path and the twelve source files it cites, with a four-minute budget in the prompt; the reviewer read the document, the code it cites line by line, `plan.md` §2, §3, §7.2 and the M10 entry, and `CLAUDE.md`'s rules, and answered in about six minutes.
The reviewer's verdict on the draft: **not ready to hand to the founder**, with one change insisted on first - "fix the abandoned-`running` job problem and write the crash behavior and test around the queue semantics that will actually ship".
That change is folded below (finding 4, P12, C15.3 rewritten, row 103's tests) and the verdict is answered; §5 stays the founder's.
Every finding was verified against the code before its disposition; the dispositions are the manager's.

**Step 0.** Existing code reused rather than rebuilt: the dashboard read and every sentence it composes (extracted, never copied); `freshness_sentence`, `signals.move_sentence`, the three signal sentences, `_short_branch`, `contribution._money_words`, `ratio._short_date`; `ratio.resolve_period`; the mock's five fixtures; `WhatsAppClient` and `FakeMeta`; the `jobs` table with `run_after`, `claim_job`, `finish_job` and the 0018 partial-unique-index pattern; the unknown-sender stamp-then-reply pattern; `record_outbound_message`'s row; `audit_events`; `branches.timezone`; the login gate's round trip; the runbook's token and subscription checks; `test_tenancy.py`'s table list and the enumerated `READS` guard.
The complexity check triggered on one migration, one new job kind, a change to the one resolver and a change to the queue's claim, and was answered by what is *not* built: no route, no web file, no settings screen, no scheduler subsystem, no broker, no second composer for any sentence.

**Corrections of record made before the outside voice ran** (the self-check):
1. The estimated-morning variant in §4.1 quoted a chain ratio no fixture produces; it is now labelled hand-built, with the row it becomes in `test_brief.py`.
2. §2 said "except one" and listed two exceptions; corrected.
3. §2 cited `README.md:170` for the `hello_world` template, which that line does not describe; Meta's get-started page is cited instead.

**Verified before folding:** `claim_job` selects `status = 'queued'` only and sets `running` with no reclaim (`db.py:3583-3605`); the lifespan stop awaits the running job (`main.py:64-67`); the worker waits only when `run_one_job` returns `False` (`worker.py:202-212`); the test rig applies migrations in sorted order with no contiguity rule (`tests/conftest.py:58`); row 119 names `0021_usable_share.sql` (`plan.md:773`); `record_outbound_message` inserts with `on conflict do nothing` (`db.py:408-418`), which is why a stub row from a racing status needs an upsert on the record side.

**Codex findings, each with its disposition:**
1. [BLOCKER] The crash-recovery test in row 103 was impossible as written: a record write that fails leaves no row, so "leaving one row and a retry sending nothing" could not be staged. **Folded:** two tests replace it - the handler run twice for one payload sends once (the dedupe), and a record write that raises after the send is followed by a retry that sends a second copy (the named limit, pinned so it is known).
2. [SHOULD FIX] Status stamping was first on the cut line while the done-when's read-back requires `delivered` or `read`. **Folded:** the stamping is off the cut list and the cut line says why.
3. [SHOULD FIX] No monotonic rule for the outbound status: a late `delivered` could overwrite `read`, a late receipt could overwrite `failed`. **Folded:** C15.4 pins the order `sent`, `delivered`, `read`, `failed` terminal, a stamp only ever forward, late and duplicate events ignored; two tests in row 102.
4. [BLOCKER] "The process dies, the retry sends again" was wrong about the queue: `claim_job` takes `queued` rows only, a job whose process died stays `running` for ever, and the daily index would refuse a replacement. **Folded, and made a decision:** C15.3 now tells the two cases apart (an exception after the send retries and can duplicate once; a hard kill strands, a deploy does not), the failure table carries both, and P12 puts the reclaim - `claim_job` also taking a `running` row untouched for ten minutes, every kind, attempts counted - to the founder, recommended into WP-103.
5. [BLOCKER] The tick ran only when the queue was empty, so an extraction backlog could starve the morning past the noon cutoff. **Folded:** the tick runs on every pass of the loop before a job is claimed, at most once a minute by a monotonic clock; a failure-table row and a test.
6. [SHOULD FIX] A status can arrive before the record write commits, and "an unknown id is ignored" would lose it for good. **Folded:** an unknown id inserts a stub outbound row carrying the status and the record write upserts into it, the further-along status kept; the stub is the last item on the cut line.
7. [SHOULD FIX] `timezone` is free text, and one typo would make a SQL conversion fail for every recipient. **Folded:** the local-time arithmetic moves to Python with `zoneinfo`, a row whose name does not resolve is logged and skipped, the paste's pre-flight checks the name, and a test covers it.
8. [SHOULD FIX] 132000 (parameter count mismatch) was named in §2 and absent from §7. **Folded:** the filler asserts exactly five parameters (a test), `FakeMeta` answers 132000, the failure table has the row.
9. [SHOULD FIX] Consent was stored twice - `opted_in_at` and `opted_in_via` on the row plus the audit event. **Folded:** the columns are gone; the row is state, the `brief_recipient.added` audit row is who, when and on what evidence (C8's own split).
10. [NIT] `label` had no consumer. **Folded:** dropped; the door that needs it adds it.
11. [BLOCKER] The migration's number was left to the lane ("0021 or 0022") with a wrong claim that row 119 said the reverse, while row 119 names `0021_usable_share.sql` outright. **Folded:** M10 is `0022_brief_recipients.sql`, fixed now; the two migrations are independent and the directory applies in sorted order, so either lands first.
12. [BLOCKER] The failure table silently accepted a marketing classification against `plan.md` §3's fixed utility decision. **Folded as P13:** the rehearsal on the free test number proceeds in either category; the production cutover waits for a utility approval unless the founder decides otherwise.
13. [BLOCKER] The plan treated pasting a row as proof of the pilot owner's opt-in. **Folded as P14:** a row is pasted only with the owner's own request in hand, named in the audit row's detail; the founder's own phone carries this decision as its evidence.

**Disposition count:** 13 folded, 0 kept, 0 dismissed. Three proposals added (P12, P13, P14); one contract paragraph rewritten (C15.3); two columns removed from the migration; the migration numbered; five failure-table rows added; nine tests added to rows 100, 102 and 103.

**Test coverage delta (the paths this review added, every one named to a row):**

```
[+] handler run twice, one send (WP-103)            test_brief_job     the dedupe on the outbound key
[+] record raises after the send (WP-103)           test_brief_job     the named duplicate, pinned
[+] stale running row reclaimed once (WP-103)       test_brief_job     P12, every kind, attempts counted
[+] tick fires under an extract backlog (WP-103)    test_brief_job     once a minute, before a claim
[+] bad timezone name skipped (WP-103)              test_brief_job     the next recipient still enqueued
[+] 132000 on send (WP-103)                         test_brief_job     three attempts then failed
[+] five parameters asserted (WP-100)               test_brief         before Meta can say 132000
[+] status never moves backwards (WP-102)           test_webhook_pure  delivered after read ignored
[+] status before the record: stub then upsert (WP-102) test_webhook_pure the further-along status kept
COVERAGE: every path the review opened has a named test; 0 critical gaps.
```

**Failure modes:** the table in §7 gained five rows (the exception after the send; the hard kill; the edited template; the backlog; the bad timezone) and one row was rewritten to point at P13.

**Parallelization:** unchanged in shape - Lane A (WP-100, WP-101) and the founder's Lane F run first, Lane B (WP-102) beside or after A with no shared file, Lane C (WP-103) last because it edits the resolver and the queue's claim; WP-103 grew by the reclaim and stays one lane.

**Lake score:** 13 of 13 dispositions took the complete option; none took a shortcut.

**CODEX:** the file path at medium reasoning, read-only, thirteen findings in about six minutes on a 603-line draft; every citation it made held against the code, including the one this document had got wrong about the queue.

**DESIGN:** no `/plan-design-review` ran; there is no screen, and §4.1 writes the message out in every variant, with the phone's limits stated beside the shapes.

**VERDICT:** **RECOMMENDED TO THE FOUNDER, NOT APPROVED.** Every outside-voice finding is folded or turned into a decision; the contracts in §3 are proposed, not pinned; the rows in §4 are not approved to build; no code exists.
The one thing between here and Wave 1 is the founder's answer to §5, and the one thing between Wave 1 and the first 07:00 is Meta's review of the template, which the founder can start today from §3.1.

**UNRESOLVED DECISIONS (the founder's, every §5 proposal):**
- P1 the scheduler: the worker's own tick, once a minute, no broker, no external cron (recommended)
- P2 the recipient model: a `brief_recipients` table, the pilot's row by the founder's paste with its audit row, the door and screen deferred (recommended; the first recipient is the founder's demo phone, as answered)
- P3 sentence slots or number slots: one template, five labelled sentence slots (recommended)
- P4 the quiet day: silence only when nothing was ever loaded; otherwise every morning with the day named and aged (recommended)
- P5 the tap-through: a static button behind the login gate, no magic link (recommended)
- P6 per-branch briefs for managers: deferred on WP-78's trigger (recommended)
- P7 language: English only for the pilot (answered by the founder at the start of the session; to confirm)
- P8 the rehearsal on the test number as the done-when's proof on the founder's phone, the pilot owner's phone following the production chain (answered in substance at the start of the session; to confirm)
- P9 the move slot reads `price_moves.moves[0]`, the issue slot `signals[0]` or `[1]`; the P8 row amended (recommended)
- P10 a recipient's reply gets one fixed reply a day, never the unknown-sender words (recommended)
- P11 the morning window: due at 07:00 local, skipped after noon, never sent late (recommended)
- P12 the stranded job: the stale-running reclaim in `claim_job`, every kind, in WP-103 (recommended; added by the review)
- P13 a marketing classification: the rehearsal proceeds, the production cutover waits for utility (recommended; added by the review)
- P14 the pilot owner's row only with the owner's own request in hand, named in the audit row (recommended; added by the review)
