# M10 decomposition - the daily WhatsApp brief (drafted 2026-09-07)

Status: **redrawn 2026-09-08 to the founder's own KPI direction (§1), and its three questions decided by the founder the same morning: the recipe cost at the latest prices (P16), items by money kept (P17), and the picture card as the way the branch table travels (P15, chosen from the rendered samples after the cost question was answered).** Before that, decomposed and reviewed 2026-09-07 with one outside voice (Codex at medium reasoning against the file path, read-only: thirteen findings, thirteen folded, four of them blockers that changed the queue's story, the migration's number and two founder decisions), awaiting the founder's decisions.**
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

**The founder's direction, 2026-09-08** - the sentence §2 rule 8 asks for, in the founder's own words: "as an owner, what we want to give him is very basic KPIs": what is my yesterday's sale; my month-to-date sales at the total level; my sales with the latest prices of materials; the cost percentage of the input cost of my total sales; then "a table, branch-wise, with the same" - yesterday's sale, the month-to-date sale, raw material cost as a percentage of sales; "top 3 profitable items and worst 3 profitable items"; and "any major price spike alert if any (show only biggest three spikes)".
Asked which cost the two cost figures mean, the founder chose the recipe cost of what was sold at the latest purchase prices - the dashboard's own contribution figures - and not purchases ÷ net sales (cash basis), which stays on the dashboard (P16, decided).
Asked how "profitable" ranks, the founder chose money kept in AED, the dashboard's own item order (P17, decided; `contribution.py:600-616`).
Asked how a branch table can travel inside a WhatsApp template, which cannot hold a line break in a variable, the founder weighed three ways on rendered samples (https://claude.ai/code/artifact/cd930ad7-445d-494a-a3d8-2a891df7cfdc), asked about the cost of each (Meta prices by category and country only, so the three send at the same rate; the card costs about two more days of build and a stored picture a morning), and chose the picture card (P15, decided).
This direction supersedes the checklist's four slots quoted above: the brief carries seven things, every one already on the dashboard read or one additive field away, and the mechanism the plan pinned - fixed sentence shapes, number slots, no generation, filled from the read - is unchanged.

Two of its parts are outside the repository and outside anyone's control here: Meta's review of the template, and the production chain (business verification, a WhatsApp Business Account, a purchased sender) that `plan.md` §3 says "starts early (M5) and runs in the background" (`plan.md:83`).
The founder's answer at the start of this session is that the chain has not started.
That is why §4 makes the deterministic filler and a printed dry run the first vertical slice, the M12 phase-one precedent, and why §5 P8 asks whether the free test number carries the rehearsal.

**Done when** (the checklist's done-when, read against the founder's direction): at 07:00 Dubai time the recipient's phone shows one message carrying the newest loaded day named and aged, that day's net sales, month-to-date net sales, the raw-material cost of what was sold at the latest prices and its share of the sales it covers, a branch table with the same three figures per branch, the three items that earned the most and the three that earned the least, and the three biggest supplier price rises - every number equal to the dashboard's for the same reads, sent through an approved utility template, recorded once, with a button that opens `/dashboard`.
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

### Every one of the founder's seven is on the dashboard read, and two are one field away

`GET /api/dashboard` (`dashboard.py:443-684`) carries everything the founder's direction names, for whatever period it is asked.
What each of the seven is on the wire today, and what the brief must do with it:

| The founder's ask | Field | State on the wire | What the brief must do |
|---|---|---|---|
| the day this is about (P6: the newest loaded day, named and aged) | `freshness.sentence` | a sentence: "Sales loaded to Mon 31 Aug, 5 days ago." (`dashboard.py:166-174`, `:641`); `null` when nothing is loaded | use verbatim, as the header |
| yesterday's sale | `latest_day` | numbers: the chain's `net_sales` on the newest loaded day and one row per branch with sales that day (`dashboard.py:586-601`); present whenever the newest day is inside the period | one fixed shape; the label says "latest day", never "yesterday", because the label is fixed text and the day is not |
| month-to-date sales, total | `total.net_sales` of a read with `from` = the first of the newest loaded day's month and `to` = that day | the route takes any `from` and `to` (`dashboard.py:447-448`; `ratio.resolve_period`, `ratio.py:272-282`); each branch's window is clipped to its loaded days and the chain total sums them (`ratio.period_row`, `chain_total`) | one month-to-date read; the line names the days actually loaded ("25-31 Aug loaded") |
| sales with the latest prices of materials = the raw-material cost of what was sold, at the latest prices (P16) | `Contribution.cost` and `Contribution.net_item_sales` (`contribution.py:315-316`), the plate costed at the prices in force on the period's last day (C12.4), which for a period ending on the newest loaded day is the latest price | **computed and not serialised**: `total` and the league rows carry `contribution`, `contribution_pct` and `costed_share_pct` and neither `cost` nor the costed sales (`dashboard.py:279-304`, `:653-664`) | two additive fields on `total` and on each league row, `cost` and `costed_sales` (C6 extended); one fixed shape |
| the input cost as a share of total sales (P16) | `100 − contribution_pct`, over the costed sales; `costed_share_pct` beside it | numbers | one fixed shape, "32.6% of the AED 56,294 costed (84% of sales)": the share is of costed sales and says so (C12.7, never grossed up); never "food cost %" |
| a branch-wise table: yesterday, month to date, materials share | `latest_day.branches[]`, `league[].net_sales`, `league[].contribution_pct`, `league[].costed_share_pct`, `league[].sales_through` | numbers, one row per branch, the league ordered by kept share lowest first (`dashboard.py:548-549`) | one row per branch in the order the dashboard ranks them, drawn on the card (P15) |
| top 3 and worst 3 profitable items (P17) | `items.top[:3]`, `items.bottom[-3:]` | ordered by money kept, most first, rows with no contribution last (`contribution.py:600-616`); five and five as slices of one list (`dashboard.py:665-672`); `items.count` the costed rows | two lists of three; the number of items that could not be costed named when it is not zero |
| the biggest three price spikes | `price_moves.moves` with `direction = "up"`, ranked by the money at stake | the block lists five of both directions inside the read's own window (`PRICE_MOVES_LISTED`, `dashboard.py:68`; the ranking at `:390-397`), so a month-to-date read on the 3rd holds three days of moves | a second read over the default 28 days (the dashboard's own window) for the spikes, rises only, three; a `limit` keyword on `price_moves_block` so the brief can take three rises past the panel's five |

- The M9 P8 row names the slots as `freshness.sentence`, `latest_day`, `league[0]` and `signals[0..1]` (`plan.md:1248`; `plan.md:1106-1107`); the founder's direction replaces that list, and the signals are no longer read by the brief at all - "what to look at" is the dashboard's, the brief's issue line is the founder's "worst 3 items" and "biggest three spikes".
  The `price_moves` block is exactly "each material's latest move inside the window, both directions, ranked by money" with the sentence composed once for the dashboard, the Menu card and the mock (`dashboard.py:345-361`), so the spikes are its rises.
- Two reads a morning, not one: the month-to-date read for every figure, the table and the items, and the 28-day default read for the spikes.
  P9's one-read rule was about a screen whose blocks must agree with each other; the brief's spikes are a different question from its month, and both reads are the same function with a different window, at 07:00, once.
- The materials share has no sentence anywhere on the wire: the dashboard prints the kept share (`contribution_pct`) and the covered share beside it, and the brief prints their complement.
  C11.6's rule carries over in spirit: the label is "materials share of costed sales", never food cost %, and the fixed template text carries the label, so the words are pinned by Meta's approval as well as by the display rule.
  Purchases ÷ net sales (cash basis) is not in the brief (P16); it stays on the dashboard as the cash view of the same question.
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
  1. *Two reads, one message, no generation.* The brief is composed by a pure `brief.py` from two payloads of the dashboard function for the tenant, read through the function the route calls and never through HTTP: the month-to-date read (`from` the first of the newest loaded day's month, `to` that day) for the figures, the branch table and the items, and the default 28-day read for the price spikes.
     Its lines are the founder's seven (§1): the day (`freshness.sentence` verbatim); the latest day's net sales; month-to-date net sales with the days loaded named; the raw-material cost of what was sold at the latest prices; that cost's share of the sales it covers with the covered share beside it; one row per branch with the same three figures; the three items that earned the most and the three that earned the least, by money kept; the three biggest supplier price rises of the 28 days with the money on the sales since.
     Where the payload carries a sentence the brief uses it verbatim; where it carries only numbers the brief composes one fixed shape in Python, and a test pins every number in the brief to the payload field it came from.
     Nothing is generated, nothing comes from a third read, and no sentence is re-worded.
  2. *The words.* The label is "materials share of costed sales", in the fixed body, with the covered share beside the figure, never food cost; purchases ÷ net sales (cash basis) is not in the brief; contribution is never mentioned as profit; `verified` is never claimed; "yesterday" appears only when `freshness.sentence` says it, which is when the newest loaded day is one day before the brief's date (P6).
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
     Under P15 the picture is part of the record: stored immutably at `{tenant_id}/briefs/{brief_date}/{recipient_id}.png` before the send and named on the row as `card_path`, so what the phone showed can be opened again.
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
  9. *The parameters.* Five text parameters and one image header (P15), the count a constant beside the body and asserted by the filler so a template edited to a different count fails in a test before it fails as Meta's 132000; none contains a newline, a tab or four consecutive spaces (Meta's rule for parameter values), each is at most 160 characters by the filler's own cap, and the rendered body is under 1,024 characters by a test over the widest fixture (a chain of twelve branches).
     Branch names in the net sales line are at most four, then the count; a chain of one branch names no branch.
  10. *C2 amended - a recipient's reply.* `process_wa_message` resolves the sender phone against branches first, then against active brief recipients; a recipient that is not a branch phone gets its inbound row stamped `ignored_brief_recipient` before anything else, one fixed reply a day (`REPLY_BRIEF_RECIPIENT`: "This number receives the morning brief. To forward invoices, use a branch's phone."), and no document, job or model call (P10).
     A phone that is both a branch and a recipient is a branch: C5 applies unchanged.
  11. *The template.* One template, `faida_daily_brief`, category `UTILITY`, language `en`, an image header and the body and samples of shape A in §3.1, the same under the test account and the production account; the name and language are constants in `brief.py`, and the template is edited only through Meta's review.
  12. *What does not change.* No web file; no new route, and **C6 extended by two additive fields**, `cost` and `costed_sales` on `total` and on each league row, which the screen ignores; the signals, the price moves and the dashboard's sentences are read, never re-composed (C13 untouched); `brief_recipients` is tenant-owned, read with `tenant_id` keyword-only and listed in `TENANT_TABLES` (C10); **C7:** one migration, `0022_brief_recipients.sql`, the number fixed now because M12's WP-119 already holds `0021_usable_share.sql` (`plan.md` §7.3 row 119) and the two are independent, so either can land first (the test rig applies the directory in sorted order, `tests/conftest.py:58`); with a paste file and a pre-flight in the 0019 and 0020 shape.

- **C13 untouched.** The brief reads no signal: the spikes are the `price_moves` block's rises, three of them, in the block's own words and for the block's own money, and the items are `items.top` and `items.bottom` in the dashboard's own order; the P8 row's slot list is superseded by the founder's direction (§1).

### 3.1 The template, the wire shapes and the sentence shapes

The three template shapes are rendered on a phone, with the same morning's figures, at https://claude.ai/code/artifact/cd930ad7-445d-494a-a3d8-2a891df7cfdc; the founder chose A, the picture card (P15, 2026-09-08), and B and C stay below for the record of what was weighed.
The figures below are the demo chain's staged week read on 1 Sep (`apps/web/src/lib/mock/dashboard/full.json`): month to date is that week, because only that week is loaded, and the line says so.

**The five lines every shape carries** (the header and the four figures), composed in `brief.py`:

| Line | Shape | Fields |
|---|---|---|
| the day | `freshness.sentence` verbatim; when `freshness.quality` is `estimated`: `<sentence> Figures below are estimated: the sales are older than a week.` | `freshness.sentence`, `freshness.quality` |
| Latest day | `AED <n> on <day>` | `latest_day.net_sales`, `latest_day.date` |
| Month to date | `AED <n> (<from>-<to> loaded)`, the days the chain's clipped windows actually cover; a chain whose branches cover different days names the widest and says "some branches fewer" | `total.net_sales`, `league[].window` |
| Materials used | `AED <n> at the latest prices` | `total.cost` (new) |
| Materials share | `<pct>% of the AED <costed> costed (<share>% of sales)`; withheld: `not available (<first note>)` | `100 − total.contribution_pct`, `total.costed_sales` (new), `total.costed_share_pct`, `total.contribution_notes` |

**The branch row** (one per branch, the league's order): `<Branch> · <latest day> · <month> · <materials share>%`, a branch with no sales on the latest day showing `-` there and its own newest day in the month figure's place when it has one; the covered share per branch is on the dashboard, and the table's header says "of costed sales".

**The lists:** `Earning most: <item> AED <n>; <item> AED <n>; <item> AED <n>` from `items.top[:3]`; `Earning least:` the same from `items.bottom[-3:]`, a loss printed as `AED -107`; when fewer than three items are costed the list is what exists and the line says how many could not be costed.
`Price spikes: <sentence without its full stop>, AED <n> at stake; …` from the 28-day read's rises, three, the panel's own sentence and money (`signals.move_sentence`, `money_at_stake`); a rise nothing was sold after says `nothing sold since`; no rise in 28 days: `none of 5% or more since <from>`.

**Template A - a picture card in the header - the one to submit** (5 body variables and an image header; the sample picture for the submission is `Docs/brief/faida_daily_brief_sample.png`, rendered from the same figures):

```
*Faida morning brief*
{{1}}

*Latest day:* {{2}}
*Month to date:* {{3}}
*Materials used:* {{4}}
*Materials share:* {{5}}

The card above carries every branch, the items and the price spikes. Every figure opens to its source on the dashboard.
```

The header is an image, 1080 by 1350 (4:5, which WhatsApp shows whole), drawn by the API from the same `Brief`: the four figures as tiles, the branch table with its four columns, the two item lists, the spikes, and the sentence "Materials share is of the sales that are costed, never of all sales."
Meta needs a sample picture at submission; the dry run writes one (`--card out.png`).
Rendered: 382 characters of text.

**Template B - text, one row per branch, one template per chain size - not taken** (11 variables for three branches; `faida_daily_brief_3`):

```
*Faida morning brief*
{{1}}

*Latest day:* {{2}}
*Month to date:* {{3}}
*Materials used:* {{4}}
*Materials share:* {{5}}

*By branch* (latest day · month · materials)
{{6}}
{{7}}
{{8}}

*Earning most:* {{9}}
*Earning least:* {{10}}
*Price spikes:* {{11}}

Every figure opens to its source on the dashboard.
```

Rendered: 841 characters for three branches, about 32 more per row; a chain of more than six branches sends its six largest by month-to-date sales and a count.

**Template C - text, every branch on one line - not taken** (9 variables): template B with the three row lines replaced by one `{{6}}` holding `Al Quoz 4,385 · 30,719 · 30.1% | Karama 2,987 · 20,907 · 31.4% | Deira 2,122 · 15,846 · 39.1%`.
Rendered: 839 characters for three branches.

**Sample values** (the same under every shape; Meta shows them to its reviewer):

| Variable | Sample |
|---|---|
| the day | `Sales loaded to Mon 31 Aug, yesterday.` |
| Latest day | `AED 9,493 on Mon 31 Aug` |
| Month to date | `AED 67,471 (25-31 Aug loaded)` |
| Materials used | `AED 18,342 at the latest prices` |
| Materials share | `32.6% of the AED 56,294 costed (84% of sales)` |
| a branch row (B) | `Al Quoz · 4,385 · 30,719 · 30.1%` |
| Earning most | `Karak Tea (Flask 1 L) AED 11,177; Karak Tea (Cup) AED 7,821; Butter Chicken AED 4,862` |
| Earning least | `Mint Lemonade AED -107; Egg Paratha AED 741; Nido Shake AED 1,283` |
| Price spikes | `Milk Powder up AED 3.40 per kg since 21 Aug, AED 109 at stake; White Sugar up AED 0.20 per kg since 28 Aug, AED 8 at stake; Chicken up AED 2.00 per kg since 27 Aug, nothing sold since` |

Every body begins and ends with fixed text, no two variables touch, every variable follows a bold label, and the button is `Open dashboard` to `https://faida-web-nine.vercel.app/dashboard`, static.

**The job payload** (`jobs.payload`, kind `send_brief`):

```json
{"tenant_id": "d0000000-0000-0000-0000-000000000001",
 "recipient_id": "…",
 "brief_date": "2026-09-01"}
```

**The Meta request** (`WhatsAppClient.send_template`, POST `/{phone_number_id}/messages`; the body component's `parameters` in the template's order; under shape A a header component first):

```json
{"messaging_product": "whatsapp",
 "recipient_type": "individual",
 "to": "9715XXXXXXXX",
 "type": "template",
 "template": {
   "name": "faida_daily_brief",
   "language": {"code": "en"},
   "components": [
     {"type": "header",
      "parameters": [{"type": "image", "image": {"id": "<media id from POST /{phone_number_id}/media>"}}]},
     {"type": "body",
      "parameters": [
        {"type": "text", "text": "Sales loaded to Mon 31 Aug, yesterday."},
        {"type": "text", "text": "AED 9,493 on Mon 31 Aug"},
        {"type": "text", "text": "AED 67,471 (25-31 Aug loaded)"},
        {"type": "text", "text": "AED 18,342 at the latest prices"},
        {"type": "text", "text": "32.6% of the AED 56,294 costed (84% of sales)"}
      ]}
   ]}}
```

**The outbound record** (`wa_messages`, `direction = 'out'`, `msg_type = 'template'`, `message_id` Meta's `wamid`):

```json
{"template": "faida_daily_brief", "language": "en",
 "parameters": ["Sales loaded to Mon 31 Aug, yesterday.", "…"],
 "card_path": "<tenant_id>/briefs/2026-09-01/<recipient_id>.png",
 "tenant_id": "…", "recipient_id": "…", "brief_date": "2026-09-01",
 "rehearsal": false,
 "error": null}
```

`card_path` is present under shape A only: the picture is stored immutably in Supabase Storage beside the documents, so the record holds what was sent.
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

**The dry run** (`python -m faida_api.brief --tenant <id> [--today 2026-09-01] [--card out.png]`), printing the lines as the phone will show them, then the parameter list as JSON, and under shape A writing the card; `--send --to 9715XXXXXXXX` sends that brief once through the same handler as a rehearsal (`rehearsal: true`, outside the day's key), which is how the sitting proves the template at any hour.

## 4. Work packages

Sizes as in `plan.md` §7.3: S ≤ half an agent-day, M ≈ one, L = multi-day.
Acceptance is demonstrable, never documentary.
Waves per §6.
The rows are numbered from WP-100 because M9's last row is 99 and M12 holds 119 to 124.

| WP | What | Size | Depends | Acceptance |
|---|---|---|---|---|
| 100 | **The deterministic filler.** A pure `brief.py` in `signals.py`'s shape (C15.1, C15.2, C15.9): `Brief(lines, rows, lists, parameters, quiet)` from the two dashboard payload dicts (month to date and 28 days) and the brief's date, the line shapes, the branch row, the two lists and the spikes of §3.1, `TEMPLATE_NAME`, `TEMPLATE_LANGUAGE` and `TEMPLATE_BODY` as constants, `render(brief)` producing the body as the phone shows it, the parameter rules (no newline, tab or four spaces; the 160-character cap; the four-branch rule), `PRICE_ALERT_MIN_PCT` imported for the no-move sentence, `contribution._money_words` and `signals._short_branch` imported and never copied. No I/O, no clock, no database | M | - | `tests/test_brief.py`: every line, row and list for each of the five committed mock fixtures (`full`, `partial`, `quiet`, `empty`, `nomenu`, chain scope) and for hand-built cases (one branch, twelve branches, fewer than three costed items, a loss in the worst three, fewer than three rises, a rise nothing was sold after, the materials share withheld, a branch with no sales on the latest day, branches whose loaded days differ); every number equal to the payload field it came from, the materials share equal to 100 minus the kept share, the month-to-date figure from the month-to-date read and the spikes from the 28-day read; `empty` produces `quiet` and no lines; the stale fixture never contains "yesterday"; the word "food cost", "net profit" and "verified" absent from every rendering (the module called, never grepped); every parameter clean and under the cap; the twelve-branch rendering under 1,024 characters |
| 101 | **The read as a function, two new fields, and the printed brief.** `dashboard.read_dashboard(db, tenant_id, *, today, date_from=None, date_to=None, branch_id=None) -> dict` extracted from the route with the route as a thin wrapper; `cost` and `costed_sales` added to `total` and to each league row from the `Contribution` the read already holds (C6 extended, additive; the mock's fixtures regenerated); a `limit` keyword on `price_moves_block`; and `python -m faida_api.brief --tenant <id> [--today <date>]` printing the five lines and the parameter JSON for that tenant from the live read, read-only - the milestone's first vertical slice and its consumer until Meta approves anything (the M12 `usage_report` precedent) | M | 100 | `tests/test_dashboard.py` green with the two fields asserted on the seeded stage (the chain's `cost` equal to the sum of its costed rows' `cost`, `costed_sales` to their `net_item_sales`), the enumerated query list unchanged, the route's JSON byte-identical to the function's for the same inputs (one new test); the CLI printing the seeded chain's brief against a test database, its lines equal to `brief.compose` over the route's payload; the founder runs it against the live database and reads the demo chain's brief on the terminal |
| 102 | **The template send and the delivery record.** `WhatsAppClient.send_template(to, name, language, parameters)` with the §3.1 request shape beside `send_text`; `db.record_outbound_template(...)` writing the outbound row of §3.1; the webhook reading `value.statuses` and `db.stamp_outbound_status(message_id, status, error)` on rows it knows; `FakeMeta` recording template sends and answering a configurable template error (132001, 132000) | S | - | `tests/test_wa.py` or the flow suite: the exact JSON on the fake transport; a 500 raising as `send_text` does; `tests/test_webhook_pure.py`: `statuses` no longer dropped - a `delivered`, a `read` and a `failed` with its error stamped on the outbound row; a `delivered` arriving after `read` and a `read` after `failed` ignored; a status for an id with no row yet inserting the stub and the later record upserting into it with the further-along status kept; an inbound `messages` payload unchanged; every existing webhook and flow test green |
| 103 | **The recipient, the morning and the job.** The migration of §3.1 with its paste file and pre-flight (C7); `db.list_active_brief_recipients`, `enqueue_brief_once`, `outbound_brief_exists`, `brief_recipient_for_phone`, all `tenant_id` keyword-only where a tenant is known, the local-time arithmetic in Python with `zoneinfo`; the stale-running reclaim in `claim_job` (P12); `JobKind.SEND_BRIEF` and `worker.send_brief` (the read with the recipient's local date, `brief.compose`, the dedupe check, `send_template`, the record; quiet day logs and returns); the tick in `worker_loop` on every pass, once a minute, behind `BRIEF_ENABLED` and the noon cutoff (C15.5); the resolver amendment and `REPLY_BRIEF_RECIPIENT` (C15.10); `--send --to` on the CLI as the rehearsal door; `brief_recipients` in `TENANT_TABLES` | M | 100, 101, 102 | `tests/test_brief_job.py` against Postgres: the tick enqueues one job per due recipient and a second tick the same day none; a paused recipient none; a recipient at 07:00 Dubai due at 03:00 UTC and not at 02:59; past noon local skipped with the log line; the job sends the exact template JSON and writes the row; a Meta 500 retried three times then `failed` with the error and no row; a 132001 and a 132000 the same; the handler run twice for one payload sending once; a record write that raises after the send followed by a retry sending the brief a second time (C15.3's named limit, pinned); a row left `running` past `STALE_RUNNING_MINUTES` reclaimed once and never twice, an extract job included (P12); the tick enqueuing a due recipient while the queue still holds extract jobs; a recipient whose timezone name does not resolve logged and skipped while the next one is enqueued; two tenants, two recipients, each brief carrying its own tenant's figures and never the other's; the empty tenant sending nothing; a recipient phone texting in getting `REPLY_BRIEF_RECIPIENT` once and its row stamped, a branch-and-recipient phone treated as a branch; `test_tenancy.py` green with the table listed; every existing suite green |
| 104 | **The template, submitted** (founder task, the text ready to paste). In WhatsApp Manager under the test account: the §3.1 name, category, language, body, samples and button, submitted; the approval, the rejection reason if any, and the date recorded in this file's §8; the demo phone confirmed among the test number's recipients. The same submission under the production account when it exists | S (founder) | - | the template shows `APPROVED` in WhatsApp Manager; a `--send --to` rehearsal from the CLI lands on the founder's phone with the sample values replaced by the demo chain's own |
| 106 | **The picture card** (P15, decided). `brief_card.py`: the layout as a pure function over `Brief` returning every drawn line with its box (tested), the drawing a thin Pillow pass over it into a 1080 by 1350 PNG with a bundled OFL font (Manrope and Inter, the brand's), deterministic for the same `Brief`; `WhatsAppClient.upload_media(bytes, mime) -> media id` (POST `/{phone_number_id}/media`, multipart) beside `send_template`, and the header component in the send; the PNG stored at `{tenant_id}/briefs/{brief_date}/{recipient_id}.png` through `storage.put` (immutable, `x-upsert: false`) and named on the outbound row; `--card` on the dry run; `FakeMeta` answering the upload | M | 100, 102 | `tests/test_brief_card.py`: the layout's lines equal to the brief's lines and rows, every figure present once, nothing clipped (every box inside the canvas); the PNG decodes to 1080 by 1350; the same `Brief` twice giving identical bytes; the job under shape A uploading first, sending with the header, storing the file and naming it on the row; an upload refused failing the job before any send |
| 105 | **Live, and the record.** One sitting: the migration applied with its pre-flight, the API deployed by the merge, the recipient row for the founder's phone pasted with its audit row, the next 07:00 brief received and read back against `/dashboard` for the same morning, the outbound row's status read back; then `DEMO_RUNBOOK.md` §J (the morning brief: preconditions, the read-back, the failure lines), `plan.md`'s boxes and logs, `TODOS.md`, `README.md`'s Meta section, `CLAUDE.md` and `AGENTS.md` (an M10 paragraph), and PRD §27.4's wording to what shipped | S | 100-104 | the founder's phone shows the brief at 07:00 with the demo chain's real figures, every number equal to the dashboard's; `wa_messages` carries one `template` row for that morning with `delivered` or `read`; the loop reset leaves the recipient row and the week intact |

**The cut line, named in advance** (`plan.md` §2 rule 9): the card is not on the list - it is the table the founder asked for; if the budget bites, the noon cutoff goes first (one constant and one clause), then the rehearsal flag on the CLI (a recipient row with `send_at_local` two minutes ahead proves the same thing more slowly), then the stub row for a status racing the record (the row reads `sent` in that rare order).
WP-102's status stamping is not on the list: the done-when's read-back needs the row to say `delivered` or `read`, and cutting the stamp would cut the proof.
WP-100, WP-101, WP-103, WP-104, WP-105 and WP-106 are the done-when and cannot be cut.

### 4.1 Design direction: the message is the screen

There is no screen in M10.
The message is read on a phone in a chat list at seven in the morning, by someone who will not open the dashboard unless the message gives a reason to, so it carries the founder's seven things in the founder's order: the day, what came in, what it cost in materials, the branches, the items, the spikes.
The three shapes are rendered on a phone with the same morning's figures at https://claude.ai/code/artifact/cd930ad7-445d-494a-a3d8-2a891df7cfdc, with the trade-offs beside each; the founder chose the picture card (P15).
Under every shape the same five lines lead, so the chat-list preview and a screen reader get the day and the figures without opening anything, and every variant below is the same template with different values.

**A normal morning** (the card carries the table, the lists and the spikes; the text under it is the first five lines below, and shape B's fuller text is shown so the words of every line are on record):

```
*Faida morning brief*
Sales loaded to Mon 31 Aug, yesterday.

*Latest day:* AED 9,493 on Mon 31 Aug
*Month to date:* AED 67,471 (25-31 Aug loaded)
*Materials used:* AED 18,342 at the latest prices
*Materials share:* 32.6% of the AED 56,294 costed (84% of sales)

*By branch* (latest day · month · materials)
Al Quoz · 4,385 · 30,719 · 30.1%
Karama · 2,987 · 20,907 · 31.4%
Deira · 2,122 · 15,846 · 39.1%

*Earning most:* Karak Tea (Flask 1 L) AED 11,177; Karak Tea (Cup) AED 7,821; Butter Chicken AED 4,862
*Earning least:* Mint Lemonade AED -107; Egg Paratha AED 741; Nido Shake AED 1,283
*Price spikes:* Milk Powder up AED 3.40 per kg since 21 Aug, AED 109 at stake; White Sugar up AED 0.20 per kg since 28 Aug, AED 8 at stake; Chicken up AED 2.00 per kg since 27 Aug, nothing sold since

Every figure opens to its source on the dashboard.
[ Open dashboard ]
```

**A stale morning** (the partial fixture, read on 12 Sep; one branch has stopped uploading): the header reads `Sales loaded to Mon 31 Aug, 12 days ago. Figures below are estimated: the sales are older than a week.`; the latest-day figure is Mon 31 Aug's; the month line says `(25-31 Aug loaded; Deira none)`; Deira's row reads `Deira · - · - · -`; the rest as the read gives it.
The header is the nudge: the same figures arrive every morning with the age one day higher, and nothing else in the product asks for the upload.

**A quiet morning** (nothing moved, nothing to rank low): `Price spikes: none of 5% or more since 4 Aug.`; the lists still carry three and three, because the founder asked for the best and the worst, not for exceptions; when fewer than three items are costed the list is what exists and says `2 items cannot be costed yet`.

**A chain of one branch**: the branch table is that one row under shape B and C, and the card's table has one row under A; the chain lines and the branch line say the same numbers, which is honest and is what a one-branch owner expects.

**An empty tenant** (nothing loaded): no message; the job completes and the log says `brief skipped: nothing loaded for tenant <id>`.

**The materials share withheld** (no item costed at all): `Materials used: not available (no item costed yet)` and `Materials share: not available (no item costed yet)`; the lists say the same; the branch rows carry `-` in the materials column.

**The phone's rendering limits, and what the shapes do about them:**

- A template variable cannot hold a line break, a tab or four consecutive spaces, so a table with one row per branch needs a picture (A) or one variable per row (B); C puts the rows in one variable with bars.
  That constraint is the whole of P15.
- Meta caps the body at 1,024 characters after the values are in: A renders at 382, B at 841 for three branches (about 32 per extra row, so ten rows is the ceiling), C at 839 (about 32 per extra branch, eight is where it stops reading as a table).
- Under A the card is a thumbnail in the bubble and readable on tap, full-screen and zoomable; the four figures are in the text so the preview and a screen reader get them without the tap; a 4:5 picture is shown whole, a taller one is cropped in the bubble.
- `*asterisks*` in the fixed body render bold and are used for the labels; the values carry no markup, because a supplier name with an asterisk in it would otherwise toggle bold mid-line.
- On a 390 px phone a chat bubble wraps at roughly 35 to 40 characters, so shape B is about thirty lines and two thumb-scrolls; the chat-list preview shows the first line and a half, which is why the bold title and the day come first.
- The URL button renders full-width under the bubble with the text `Open dashboard` (25 characters is Meta's cap); a static URL shows no preview card.
- No emoji, no icon and no colour in the text; colour never carries meaning alone (`plan.md:92`), and the card uses the brand's own tokens with the figures as words and numbers.
- Arabic and Malayalam are out of scope (the founder's answer; `plan.md:93`); Latin digits and the `÷` sign render in every WhatsApp client, and under A a second language needs a font that carries it.

## 5. Proposals for the founder (each with a recommendation)

**None of these is decided.**
Three questions were answered by the founder at the start of the session (the chain has not started; the founder's demo phone first; English only) and are carried in P2, P7 and P8 as answers to confirm at approval; every other row is open, and the session proceeded on the recommended option so that §3, §4, §6, §7 and §8 describe one consistent plan.
P12, P13 and P14 were added by the outside voice's review (findings 4, 12 and 13 in the report).
P15, P16 and P17 were added on 2026-09-08 from the founder's direction and decided by the founder the same morning.

| # | Proposal | Recommendation and why |
|---|---|---|
| P1 | **The scheduler.** Nothing in the product ticks at a wall-clock time (`worker.py:193-213`). Options: (a) the worker's own tick - once per idle poll, one query for recipients whose local morning has come and who have no job for today, enqueued through a unique index; (b) an external cron (Railway's cron service, a GitHub Actions schedule) hitting one endpoint or running one command at 07:00; (c) an in-process sleeper task computing each recipient's next 07:00 | **(a), the worker's tick.** It is the rule in `plan.md:87`: the `jobs` table is the queue and the worker owns it, no broker. The cost is one cheap query every two seconds when the queue is idle, and the unique index makes the tick idempotent whether it runs once or from two instances. (b) needs a way in: there is no API secret by decision (`CLAUDE.md`, M7), so an endpoint would reintroduce one, and a cron *command* is a second process against the same database with its own deploy and its own cold start at 03:00 UTC; it also fires whether or not the API is up, which is backwards. (c) is a scheduler subsystem with restart semantics for a job the queue already knows how to hold until `run_after` (`db.py:3589`). The one thing (a) cannot do is fire while the API is down, and C15.5's catch-up inside the morning window covers a deploy |
| P2 | **The recipient model.** No table holds an owner's phone (§2). Options: (a) a `brief_recipients` table (§3.1) - tenant, phone, timezone, send time, pause - with the pilot's rows written by the founder's paste file together with their audit row, and the door and screen deferred; (b) two columns on `tenants` (`brief_phone_e164`, `brief_timezone`), no new table; (c) an environment variable listing phones, no schema | **(a), the table, the pilot's row by paste.** The founder's answer names the first recipient - the demo phone - and a chain with two partners is the ordinary case, which (b) cannot hold. Opt-in is a fact Meta's policy and PRD §26's audit model both want recorded, with a time, a way and the evidence, which is the `brief_recipient.added` audit row's job (C8; the review's finding 9 took the duplicate consent columns off the table), and pausing must not be nulling the phone. (c) makes a second tenant a deploy and puts a customer's phone in Railway's variables. The migration is one table and one index; the paste is the branch-phone precedent (`demo_seed.sql:562-570`), and it writes the `brief_recipient.added` audit row the future door will write. A settings screen for one phone field, for one tenant, is the vertical slice rule's letter and not its point; the trigger for the door is in §9 |
| P3 | **Sentence slots or number slots.** *(The content this row weighed - the four checklist slots - is superseded by the founder's direction of 2026-09-08, §1; the mechanism it recommends stands for the seven lines.)* The checklist says "fixed sentence shapes, number slots". Options: (a) one template whose five variables are labelled sentence-slots, each value composed in Python from the read (§3.1); (b) number-only slots inside fixed sentences ("net sales were AED {{1}}"), which needs one template per shape - a normal day, a stale day, a withheld ratio, no move, no signal - each reviewed separately, and no way to send a null | **(a), one template, five labelled slots.** It is what P8 was pinned for: "C13.5 puts every sentence on the wire so the slots are free" (`plan.md:1248`). The fixed labels are the template's honesty to Meta's reviewer (a variable after "Purchases ÷ net sales (cash basis):" cannot be used for anything else), and the values are the product's honesty to the owner - the stale morning and the withheld ratio are the same template saying a different true thing. (b) multiplies templates by variants, each an approval and a rejection risk, and still cannot say "no ratio" in a number slot. The sentence shapes themselves are fixed and tested (WP-100), so the checklist's "no generation" holds either way |
| P4 | **The quiet day.** What is sent when there is nothing new. Options: (a) silence only when nothing was ever loaded; otherwise a brief every morning, the day named and aged in the header, the stale clause after a week; (b) a brief only on a morning when the newest loaded day moved since the last brief; (c) a brief every morning with a separate "nothing new" template | **(a).** A till that exports weekly gives seven mornings of the same sales figures, and the product's answer to that is not silence but the header saying "12 days ago" - the only reminder to upload that exists anywhere. The price moves and the signals still change as papers land. (b) turns the brief into a notification of the upload, which the owner did not do and cannot act on, and breaks the done-when's "each morning"; the first morning it does not arrive is the morning the habit ends. (c) is a second template for a sentence the first already carries. A tenant with nothing loaded ever has nothing to say and a template costs money; that is the one silence |
| P5 | **The tap-through.** Options: (a) a static button to `/dashboard` behind the login gate - one password entry on the phone, then the session cookie (`proxy.ts:14-19`); (b) a signed-in magic link per brief, minted through Supabase's admin link and carried in the button's dynamic suffix | **(a).** A magic link is a session in a chat log: anyone holding the phone, or anyone the message is forwarded to, opens the books, and the link either expires before the owner taps it or lives long enough to be the credential the product refused to hold anywhere (`auth.py:16-20`). The login gate already lands a tap on `/dashboard` (`gate.ts:57-62`) and the dashboard is built for 390 px. If the pilot owner says the password stops them, (b) is one `generate_link` call and a dynamic URL button, and §9 carries it with that trigger. A static URL also means a template that never needs a parameter for its button, one fewer thing to mismatch |
| P6 | **Per-branch briefs for managers.** PRD §27.4's "optionally each branch manager". Options: (a) defer on WP-78's trigger, a pilot chain asking for a branch manager on the screen (`TODOS.md:200-221`); (b) build the row now with a nullable `branch_id` and the read under `branch_id` | **(a), defer.** There is no branch user, no branch phone that is a person, and no one who has asked; a manager's brief without a manager's role sends a branch's money to a phone whose relationship to the branch is a row nobody vouched for. When WP-78 lands it is one nullable column, `?branch=<id>` in the button (a template edit, reviewed again) and the read's existing filter (`dashboard.py:473-476`) |
| P7 | **Language.** Answered at the start of the session: **English only for the pilot**, the demo-scope decision extended (`plan.md:93`, `:1343`). The alternative is one template per language, and every sentence the brief carries is composed in English in five Python modules, so a second language is a second composer for each - the trigger in §9 is a pilot owner who does not read English | **Confirm English only** |
| P8 | **The rehearsal on the test number, and what the done-when means before the production chain.** Answered at the start: only the test number is live, and the first recipient is the founder's demo phone. Options: (a) submit the template under the test account now, rehearse to the founder's phone at 07:00, and call that the done-when's proof, the pilot owner's phone following the production chain; (b) wait for the production chain and send nothing before it | **(a).** The test number sends templates to its registered recipients, a template created under the test account goes through the same review, and the demo phone is registered (`Docs/DEMO_RUNBOOK.md:35`; `README.md:167`). The rehearsal proves everything this repository can prove - the read, the words, the tick, the record, the button - on a real phone at 07:00, weeks before verification clears. What it cannot prove is the production number's category rate and quality rating, which is §8's last step. (b) makes the milestone wait on the one clock nobody here controls |
| P9 | **Which field is the biggest price move.** *(Superseded 2026-09-08: the brief carries the three biggest rises from the `price_moves` block and reads no signal; kept for the record of why the block and not the signals.)* P8 named `signals[0..1]`; WP-99 then added `price_moves` (2026-09-07). Options: (a) `price_moves.moves[0]` - each material's latest move inside the window, both directions, ranked by the dirhams moved, with the money at stake or saved; the issue slot `signals[0]`, or `signals[1]` when the top signal is the spike for the same material; (b) the price spike among the signals, rises only, and nothing on a morning when the biggest move is a fall | **(a).** A fall is a fact an owner acts on too (the panel's own reason, `dashboard.py:355-357`), and the block's sentence is the one the dashboard and the Menu card print, so the phone and the screen quote one move in one set of words. The four slots stay four; the P8 row gains the field name. The money clause is the brief's own ("AED 109 at stake on sales since."), pinned by a test to `money_at_stake` so the amount can never differ from the panel's |
| P10 | **The owner replies to the brief.** Today a phone no branch is registered to gets "This number isn't set up yet, so I can't read invoices from it. Ask the owner to add this number" (`replies.py:53-56`) - to the owner. Options: (a) a recipient that is not a branch phone is stamped and gets one fixed reply a day saying what the number does ("This number receives the morning brief. To forward invoices, use a branch's phone."), the unknown-sender pattern with different words; (b) silence: stamped, no reply; (c) leave it | **(a).** "Thanks" to a brief deserves an answer, and the answer should not tell the owner to ask the owner. It is one lookup after the branch lookup in the one resolver (C2 amended, C15.10), one reply constant, and the existing once-a-day silence. (b) is a phone that talks every morning and never listens. A phone that is both a branch and a recipient - the founder's - stays a branch, so the rehearsal changes nothing about the demo |
| P11 | **The morning window.** The tick catches up after a deploy or an outage. Options: (a) send when due, up to a noon cutoff in the recipient's timezone, then skip the day with a log line; (b) send whenever the tick returns, however late | **(a).** A "morning brief" at ten at night is noise, and by then tomorrow's is nine hours away; five hours of grace covers any deploy and most outages. The cutoff is one constant with its reason beside it and one clause in the due query |
| P12 | **The stranded job** (the review's finding 4). `claim_job` takes `queued` rows only and nothing reclaims a row left `running` by a process that died mid-job (`db.py:3583-3605`); a graceful stop finishes the job first (`main.py:64-67`), a hard kill does not. Every job kind has lived with this; the brief is the first whose stranding shows nowhere (a stranded extract job is a document stuck in `processing` on the invoice list). Options: (a) fold a reclaim into WP-103: `claim_job` also takes a `running` row untouched for `STALE_RUNNING_MINUTES` (10), attempts counted, for every kind; (b) accept it for the pilot, name it in the failure table, defer the reclaim with the trigger "a job found `running` for over an hour" | **(a), the reclaim, in WP-103.** It is one clause and one constant, every handler is already idempotent under retries by C2's rule (`CLAUDE.md`), attempts stay capped at three, and a brief interrupted at 07:00 is sent within the morning instead of never. The cost is that a legitimately slow job over ten minutes runs twice; the extraction target is twenty seconds and the worst observed was 155 s, so the constant has fifty times the headroom. (b) leaves the one morning message the product makes on a queue that can lose it silently |
| P13 | **If Meta approves the template as marketing** (the review's finding 12). `plan.md` §3 fixes a utility template (`plan.md:83`) and PRD §11's cost model assumes it (`Docs/PRD.md:251`). Options: (a) the rehearsal on the free test number proceeds in either category; the production cutover to the pilot owner waits for a utility approval - the wording edited to the rejection reason, or the category appealed; (b) accept marketing for the pilot's one message a day, at the marketing rate and under per-user marketing limits (131049) | **(a).** The brief is an account update the owner asked for, which is what Meta's utility category describes, and the body is labelled facts with nothing offered; if a reviewer still reads it as marketing the honest move is to change the words until it reads as what it is, not to pay the marketing rate for a utility message. The test number costs nothing, so the rehearsal and the done-when on the founder's phone do not wait. The row in §7 says the same |
| P14 | **What authorises the pilot owner's row** (the review's finding 13). The founder can authorise the founder's own phone; nobody here can manufacture the pilot owner's consent to a daily message about their money. Options: (a) the row is pasted only with the owner's own request in hand - a WhatsApp text from the owner's phone to the number, or a signed line on the onboarding sheet (PRD §28 step 2, where branch phones are registered) - and the `brief_recipient.added` audit row's detail names it (`{"evidence": "wa:<message id>"}` or `{"evidence": "onboarding sheet <date>"}`), the paste refusing a row without one; (b) the founder's word alone, recorded as such | **(a).** Meta's policy requires opt-in before a business-initiated template, PRD §26's audit model records the reason on every decision, and the evidence pointer costs one key in a detail that exists anyway. For the founder's demo phone the evidence is this decision, written into the row's detail the same way |
| P15 | **How the branch table travels** (the founder's direction, 2026-09-08; weighed on rendered samples at https://claude.ai/code/artifact/cd930ad7-445d-494a-a3d8-2a891df7cfdc and on the cost of each; **decided by the founder 2026-09-08: (a), the picture card**). A template variable cannot hold a line break, so one row per branch needs a picture or one variable per row. Options: (a) a picture card as the template's image header - the four figures, the branch table, the item lists and the spikes drawn by the API from the same `Brief`, 1080 by 1350, the four figures repeated in the text (5 variables, one template for every chain, WP-106: a renderer with a bundled font, a media upload to Meta, the picture stored for the record; about two more days); (b) text, one variable per branch row, one template per chain size that exists (`faida_daily_brief_3` for the pilot, up to six rows, the six largest and a count beyond that; nothing new to build); (c) text, every branch on one line separated by bars, one template, readable to about eight branches | **(a), the picture card.** It is the table the founder described, at any chain size, and the target chains are multi-branch; one template submitted once; the card is a record and forwardable; the four figures stay in plain text for the preview and a screen reader. The cost is real and bounded: a deterministic renderer, an upload before each send, two more ways a morning can fail, and a font that must carry a second language later. (b) is the honest quick path if the pilot must have the brief before the renderer exists - one three-row template today - with the ceiling of a template per chain size. (c) is the simplest and the least like what was asked |
| P16 | **Which cost the two cost figures mean.** "Sales with the latest prices of materials" and "the cost percentage of the input cost of my total sales": (a) the recipe cost of what was sold at the latest purchase prices and its share of the sales it covers - the dashboard's contribution figures, C12; (b) purchases ÷ net sales (cash basis), the `/sales` ratio; (c) both | **Decided by the founder 2026-09-08: (a), the recipe cost at the latest prices.** The materials share is of costed sales and says the covered share beside it (C12.7, never grossed up), labelled "materials share of costed sales" and never food cost %; purchases ÷ net sales (cash basis) stays on the dashboard as the cash view of the same question. Two additive wire fields carry the cost and the costed sales (row 101) |
| P17 | **How "profitable" ranks the top three and the worst three.** (a) By money kept in AED over the month to date, the dashboard's own item order (`contribution.py:600-616`); (b) by the kept share in percent | **Decided by the founder 2026-09-08: (a), by money kept.** `items.top[:3]` and `items.bottom[-3:]` are slices of the one ordered list the dashboard shows, so the phone and the screen name the same items in the same order; a big seller with a thin margin can rank high, which is the point of ranking by money |

## 6. Delegation waves and parallel lanes

| Step | Modules touched | Depends on |
|---|---|---|
| WP-100 the filler | `apps/api/src/faida_api/brief.py` (new), `apps/api/tests/test_brief.py` (new), the five fixture files read from `apps/web/src/lib/mock/dashboard/` | - |
| WP-101 the read and the dry run | `apps/api/src/faida_api/dashboard.py` (the extraction, additive), `apps/api/src/faida_api/brief.py` (`__main__`), `apps/api/tests/test_dashboard.py` (one test) | 100 |
| WP-102 the send and the record | `apps/api/src/faida_api/{wa,webhook,db}.py` (`send_template`; `statuses`; two message functions), `apps/api/tests/{conftest,test_webhook_pure,test_flow}.py` | - |
| WP-103 the recipient, the morning, the job | `supabase/migrations/0022_brief_recipients.sql` (new), `Docs/apply_m10_migration.sql` (new), `apps/api/src/faida_api/{contracts,worker,replies,config,db,brief}.py`, `apps/api/tests/{test_brief_job,test_tenancy,test_contracts}.py` | 100, 101, 102 |
| WP-106 the picture card | `apps/api/src/faida_api/{brief_card,wa,storage}.py` (`upload_media`, one call), `apps/api/fonts/` (two OFL files), `apps/api/tests/{test_brief_card,conftest}.py` | 100, 102 |
| WP-104 the template | WhatsApp Manager (the founder); this file's §8 for the record | - |
| WP-105 live | `plan.md`, `TODOS.md`, `README.md`, `CLAUDE.md`, `AGENTS.md`, `Docs/DEMO_RUNBOOK.md`, `Docs/PRD.md` §27.4 | all |

- **Wave 0 (manager, no code):** C15 and the C2 amendment pinned in `plan.md` §7.2 as decided; the rows in §7.3; one Decision Log row per §5 decision; the `TODOS.md` entries from §9.
- **Wave 1, two lanes.** Lane A = WP-100 then WP-101 (one lane: `brief.py` and the extraction in `dashboard.py`, whose output is the filler's input). Lane F = WP-104, the founder, from the first day, because Meta's clock is the long one and the text is ready. No file overlap.
- **Wave 2, one lane.** Lane B = WP-102 (`wa.py`, `webhook.py`, two functions in `db.py`'s messages section, the fake and its tests). It could run beside Lane A - the files are disjoint - and does so if a second lane is available; it is listed second only because Lane A is the vertical slice.
- **Wave 2, a second lane.** Lane D = WP-106, `brief_card.py` and the fonts, `upload_media` in `wa.py` beside Lane B's `send_template` (sequenced after B, or the two `wa.py` additions merged by the manager), no other shared file.
- **Wave 3, one lane.** Lane C = WP-103, the only lane that touches `worker.py`, `contracts.py`, `config.py`, the migration and `db.py`'s jobs section, after A, B and D have merged. Sequenced, not parallel, because it edits the resolver every inbound message runs through (C2) and the `db.py` sections both earlier lanes touched.
- **Wave 4: WP-105**, one sitting with the founder, on the morning after the recipient row lands.

The migration is `0022_brief_recipients.sql` whether or not M12's `0021_usable_share.sql` has landed first (C15.12): the two touch different tables, the directory applies in sorted order, and a number claimed now cannot be claimed twice.

## 7. The tests that gate it

- `tests/test_brief.py` (WP-100): every C15 line, row and list as a pure case with no database - the five committed fixtures at chain scope and the hand-built cases named in row 100; every number equal to the payload field it came from, read back by the test from the same dict, the month-to-date figures from the month-to-date payload and the spikes from the 28-day one; the materials share equal to 100 minus the kept share and the covered share beside it; the stale fixture rendering without the word "yesterday" and the fresh one with it; the empty fixture producing `quiet`; the forbidden phrases ("food cost", "net profit", "verified") absent from every rendering by calling the module (never by grepping code); each parameter free of newlines, tabs and four consecutive spaces and at or under 160 characters; the rendering of a twelve-branch chain under 1,024 under each shape; the parameter count asserted per shape; the loss printed with its sign; fewer than three rises or items saying so; a branch with no sales on the latest day carrying `-`.
- `tests/test_dashboard.py` (WP-101): green with the two new fields asserted, the enumerated `READS` list unchanged (`test_dashboard.py:53-75`), the route's JSON equal to `read_dashboard`'s for the same tenant, period and `today`, and a month-to-date period's `total.net_sales` equal to the sum of the league rows' clipped windows.
- `tests/test_brief_card.py` (WP-106): the layout's lines equal to the brief's, every box inside the canvas, the PNG's size, identical bytes for the same `Brief`, the upload-then-send order, an upload refused failing before any send.
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
| the filler | a chain with many branches, or a long item name | under (b) the six-largest rule, under (c) the eight-branch ceiling and under every shape the 160-character cap keep the body under 1,024; a slot over the cap is a filler bug the test catches, never a truncated message | `test_brief.py` |
| the card | the renderer faults, or Meta refuses the upload | the job fails before any send, retries, then `failed` with the error; no half-message | `jobs.last_error`; `test_brief_card.py` |
| the card | the card renders but a figure sits outside the canvas | the layout test pins every box inside the canvas for the twelve-branch case; the row count that fits is a constant with the overflow sentence "and N more on the dashboard" | `test_brief_card.py` |
| the filler | no item is costed, so the materials cost and share are withheld | the lines say so with the read's own note; never 0% and never a grossed-up share (C12.7) | `test_brief.py` |
| the template | Meta rejects the submission | nothing to code: the founder edits the wording to the rejection reason and resubmits; the tick must not be enabled before approval (§8) | WhatsApp Manager |
| the template | Meta approves it as marketing rather than utility | the rehearsal on the free test number proceeds either way; the production cutover waits for a utility approval unless the founder decides otherwise (P13); marketing costs more and carries per-user limits (131049) | WhatsApp Manager; the rate card; P13 |
| the template | the web host changes (a custom domain) | the button's URL is fixed text: a template edit and a review | §9's entry |
| the 24-hour window | the recipient wrote in an hour ago | irrelevant: a template is accepted inside and outside the window, and inside one it is free; the brief never calls `send_text`, and a test pins the request type | `test_brief_job.py` |
| the 24-hour window | someone sends the brief as free text | 131047, asynchronously, and the product would never see it (`webhook.py:33`); the reason the brief is a template and the reason WP-102 reads `statuses` | - |
| the category | the utility template drifts into promotional wording in a later edit | Meta may recategorise on review; the body's fixed text is a constant in `brief.py` with this file as its reason | WP-104's record |

## 8. Migration and cutover order

Two chains, one of code and one of Meta's, that meet at the first 07:00.

**Meta's chain (the founder; external, serial, the long clock):**

1. Now, under the test account: create `faida_daily_brief` in WhatsApp Manager from §3.1 (name, Utility, English, header Image with `Docs/brief/faida_daily_brief_sample.png` as the sample, the body of shape A, its five samples, the button); submit; note the date.
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

### The founder's direction - 2026-09-08 morning

The founder read the decomposition's brief and redrew its content: "as an owner, what we want to give him is very basic KPIs" - yesterday's sale, month-to-date sales, sales with the latest prices of materials, the input cost as a share of sales; a branch-wise table with the same three; the top three and worst three profitable items; the biggest three price spikes.
Three questions were put back and all three answered: the cost figures are the recipe cost of what was sold at the latest prices, not the cash-basis ratio (P16); "profitable" ranks by money kept (P17); and the branch table travels as a picture card in the template's image header (P15), chosen from the three shapes rendered on a phone at https://claude.ai/code/artifact/cd930ad7-445d-494a-a3d8-2a891df7cfdc after the cost of each was set out (Meta prices by category and country only, so the shapes send at one rate; the card is about two more days of build and a stored picture a morning).
What changed in this file: §1 carries the direction in the founder's words; §2's slot table maps the seven things to the wire (two additive fields needed, `cost` and `costed_sales`; two reads a morning, month to date and 28 days); C15.1, C15.9, C15.11 and C15.12 follow; §3.1 carries the three template shapes with the same samples; rows 100 and 101 grew and row 106 (the picture card) exists under P15 (a); §4.1 is rewritten around the seven lines; P3 and P9 are marked superseded; §7's tests and failure modes follow.
Not changed: the scheduler, the recipient, the record, the morning window, the resolver amendment, the migration, the Meta chain and the review's thirteen folded findings, none of which depend on what the message says.
The Codex review above read the four-slot draft; whether a second pass runs on the redrawn content, after P15, is the manager's call, as M9's second voice was.

**UNRESOLVED DECISIONS, added 2026-09-08:**
- P15 decided by the founder: the picture card, after the samples and the cost of each were put side by side
- P16 decided by the founder: the recipe cost at the latest prices and its share of costed sales
- P17 decided by the founder: the top and worst three by money kept
