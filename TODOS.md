# TODOS

Deferred work with its reasoning intact, and enough context to pick up cold. Anything here was
considered and consciously not built; nothing enters this file without a reason someone can argue
with later.

Two lanes wrote into this file independently and it was unioned when they merged on 2026-08-29:
the M5 raw-materials lane owns **Backend**, and the eval-phase2 lane (`/plan-eng-review`) owns
**Extraction & matching**. No entry appears twice. (The **Plan corrections** section the
eval-phase2 lane also owned was applied to plan.md on 2026-08-29 - the TH-01 false-alarm
correction, in the M6-decomposition commit - and retired from this file.)

## Backend (apps/api)

### Catalog pack size and unit are written once and never corrected

**What:** Update `supplier_items.unit` and `supplier_items.pack_size` when a later invoice
prints a value and the stored one is blank.

**Why:** The columns are filled the first time a product is ever seen and never touched again.
`db.py:569` re-sets only the name on conflict - `on conflict (supplier_id, canonical_name) do
update set canonical_name = excluded.canonical_name` - and the insert does not run at all for a
line that snapped to an existing product. So if the first invoice a product appeared on had a
blank or misread pack-size column, the catalog carries that blank forever, however clearly every
later invoice prints it. The price-history screen reads those columns, so it shows the stale value.

**Context:** Found during the M5 plan review on 2026-08-29 (`/plan-eng-review`, Issue 4). M5
deliberately routes around it rather than depending on it: costing, the pack-dimension check and
the unreadable-pack queue all read `invoice_lines.pack_size` from the newest confirmed line, which
has a photo behind it. That is why this is deferred rather than fixed - the fix is about two lines
of SQL (`coalesce` the stored value with the incoming one on the conflict clause), but it adds a
write to the confirm transaction, which is the shipped M0-M4 demo path, for a column M5 no longer
reads. Not worth the regression risk during the milestone whose one hard constraint is not
regressing that path.

It gets more interesting later in two places: M8's purchases roll-up may want a catalog-level pack
size, and at pilot scale the first invoice a product ever appears on is often the worst photo
anyone ever sends - exactly the one whose reading gets frozen.

**Effort:** S
**Priority:** P3
**Depends on:** None. Independent of every M5 work package.

### VAT is applied at invoice level, so a mixed-rate invoice produces wrong ex-VAT unit costs

**What:** Decide whether C4 should capture a per-line tax basis, or whether an invoice with mixed or
zero-rated lines should refuse to produce a cost at all.

**Why:** `db._net_price_factor` derives one factor from the invoice's own `tax` and `total` and
applies it to every line. That is correct when every stock line carries the same rate, which is the
normal GCC case. It is wrong when an invoice mixes rates or carries zero-rated lines: each line's
ex-VAT unit price comes out plausible and slightly false, and from M5 that flows into a cost per kilo
and from M6 into a plate margin, with nothing downstream able to see it.

**Context:** Raised by the Codex outside voice during the M5 plan review on 2026-08-29 (finding 13).
Deliberately not fixed in M5 for one reason: this is not a new M5 defect. The same invoice-level
factor already governs `supplier_items.last_price` and has since WP-17 shipped on 2026-08-23, so
changing it is an amendment to contract C4 - manager-only, through the Decision Log - and not a
work-package decision. It also needs a real example before it is worth designing against: no invoice
in the phase-1 corpus mixes rates, and the phase-2 real corpus (F6) is the place such an invoice
would first appear. The cheap interim answer, if one is wanted before then, is C9-shaped rather than
arithmetic: refuse to call a cost anything better than *estimated* when the invoice's lines do not
all share one basis.

**Effort:** M
**Priority:** P3
**Depends on:** A real mixed-rate invoice in the corpus (F6, phase 2). A C4 amendment decision.

### Pack sizes are corroborated by nothing; corroborate them across invoices

**What:** Let a cost earn a *verified* label by checking the pack size against the same supplier's
previous invoices for the same product, rather than never claiming verification at all.

**Why:** C4's arithmetic cross-checks the unit price (`qty × unit_price = line_total`) but pack size
appears in no identity, so nothing anywhere corroborates it. A 25kg misread as 2.5kg passes every
check the pipeline has. M5 handles this honestly by never labelling a cost *verified* - but "honest
about knowing nothing" is weaker than actually checking, and the evidence needed is already sitting
in `supplier_item_prices` and the invoice lines behind it.

**Context:** Raised as the stronger option during the M5 plan review on 2026-08-29 (eng review
tension 5, option B) and consciously deferred. It only starts working once a supplier has billed the
same pack twice, so on a new tenant it would read unverified for weeks regardless - which makes it an
upgrade for when price history exists, not a thing to build alongside the first cost. Start at
`matching._pack_tokens` and the price-history query; the comparison is the one `units.same_pack_size`
already implements.

**Effort:** M
**Priority:** P3
**Depends on:** M5 shipped, plus enough repeat-purchase history to compare against.

### ~~A held duplicate invoice has no resolution door - it sits in needs_review forever~~ done 2026-09-01

Closed by the dismiss door (migration 0017, `POST /api/invoices/{id}/dismiss`). WP-44 now
*records* its hold instead of spending it on the reply and forgetting it -
`invoices.duplicate_of_invoice_id`, written by the pipeline in the same branch that sets
`needs_review` - so the review screen can name the paper a copy duplicates, and the door can key on
it. `invoices.status` gained a terminal `dismissed`: the single confirm write already guards on
status equality, so a dismissed invoice is refused by both confirm doors with no new code, and
`_EDITABLE_STATUSES` refuses a PATCH for free.

**Only a held duplicate can be dismissed** - `duplicate_of_invoice_id is not null` sits in the
write, not just the endpoint. The original carries no pointer, so the two-click path to erasing a
real paper (dismiss the original, then the copy) is unreachable rather than merely discouraged.
Dismissal is not deletion: the row, its lines, its document and its photo all stay, and
`?status=dismissed` still returns it.

The screen gained a `Duplicate` chip on list and detail alike, the WhatsApp sentence as an amber
banner linking to the original, `Dismiss this copy` as the primary action with `Confirm` demoted to
the outline treatment, and a row-level Dismiss whose success *and* failure both speak through one
`role="status"` strip. The action condition was inverted while there: written as a bare `else`,
`dismissed` would have been offered a Confirm button the API is guaranteed to refuse.

Tested end to end in
`tests/test_api.py::test_dismissing_a_copy_clears_the_list_and_leaves_the_original_alone`, with
eleven beside it (the original refused, an ordinary invoice refused, a confirmed copy refused,
double-dismiss, the confirm/dismiss race naming the real status, a third send held against the live
original), plus the enum-to-CHECK lockstep in
`tests/test_contracts.py::test_the_database_accepts_every_invoice_status_the_enum_declares`.

### A dismissal cannot be undone from any screen

**What:** An un-dismiss action, and a way to reach dismissed rows so one can be found at all.

**Why:** The dismiss door is one-way. The row survives and `/invoices?status=dismissed` reaches it,
but there is no tab, no button and no path a reviewer can walk - a misclick is recoverable only
within that page view, through the status strip. The blast radius is small, because the guard
refuses anything without a duplicate pointer: the worst case is losing a real invoice that WP-44
held by mistake. That is exactly the fallible case that argued against auto-hiding duplicates in the
first place, so it should not stay unaddressed for ever.

**Context:** Deliberately not built 2026-09-01 - nobody has asked (§2 rule 8), and designing a
dismissed-rows screen for a list that is empty on every tenant is speculation. It pairs with M7,
which has to answer "who may dismiss" anyway; the same answer covers "who may un-dismiss". Start at
`db.dismiss_invoice` (the guarded update inverts cleanly) and `InvoiceList.tsx`, where the tab list
and the typed status set both live.

**Effort:** S
**Priority:** P3
**Depends on:** M7's roles, which decide who is allowed. *Answered by the 2026-09-03 M7 review (D2): one
role for the pilot, so any member of the tenant may dismiss; un-dismiss itself stays unbuilt until asked.*

### ~~The runbook's leftover check got weaker when the invoice list started hiding rows~~ done 2026-09-03

Closed in the M7 cutover prep: DEMO_RUNBOOK §A's check now names the hidden dismissed rows and the `?status=dismissed` view.

**What:** One sentence in `Docs/DEMO_RUNBOOK.md` §A, so its "no rehearsal leftovers in the invoice
list" check accounts for the rows the list now hides.

**Why:** The runbook has the operator verify by eye, before a demo, that the demo chain's invoice
list carries no leftovers (`DEMO_RUNBOOK.md:139`, checklist at `:46`). Dismissed rows are out of
that list by default, so a dismissed leftover would pass a check written to catch it. Nothing
actually breaks - `demo_reset_loop.sql` deletes by the props' printed invoice numbers regardless of
status - but the human step no longer verifies quite what its sentence claims, and it is the step
standing between a rehearsal and a live audience.

**Context:** Not fixed alongside the dismiss door because that file was fenced off while the M6 gate
was pending. The gate passed 2026-09-01, so it is editable again; it was kept out of that change to
keep the diff on the door.

**Effort:** S
**Priority:** P3
**Depends on:** None.

### The invoice list is not usable at 390 px without a sideways swipe

**What:** Card rows under 640 px on `/invoices`, the shape `/menu` already uses.

**Why:** The list is a six-column table inside an `overflow-x-auto` wrapper. At 390 px the table is
549 px wide before the dismiss work and 674 px after, so Total, Status and the row action all sit
off-screen behind a horizontal swipe *inside* the table. The page itself does not overflow and the
content is reachable, so nothing is broken - it is a table pretending to be responsive. Measured
2026-09-01 during the dismiss-door QA: `/menu`, `/materials` and `/invoices/new` all report 390 vs
390 at that width, and only `/invoices` does not.

**Context:** Pre-existing - Status was already off-screen before the dismiss work, which made an
existing weakness one column worse rather than creating it. Deliberately not fixed there: the answer
is M6 design decision D11's card-row treatment (`MenuMargins.tsx:538,578` - a real table above
640 px, cards below, the headline figure first), and applying that to the invoice list is a redesign
of a shipped screen that deserves its own design pass rather than riding along on a bug fix.

**Effort:** M
**Priority:** P3
**Depends on:** None. Worth a `/plan-design-review` first, as the menu screen's version had.

### ~~A material with a blocked newer purchase silently shows its older price as current~~ done 2026-08-30

Closed by WP-61 (derivation amendment 3, D11): `db.list_newest_purchases` asks what the newest
confirmed purchase was, costed or not, with the same ordering and qty >= 0 rule as the price
query; a `costed = false` winner caps its material and every plate above it at *estimated*, keeps
the older price visible with its date, and names the blocked line with its WP-55 reason - on the
materials screen and in every plate answer. Tested end to end in
`tests/test_plates.py::test_a_newer_uncosted_purchase_caps_the_material_and_its_plates`.

## Auth & tenancy (deferred by the M7 eng review, 2026-09-03)

M7 was decomposed in `Docs/M7_DECOMPOSITION.md` and reduced to one app role (`tenant`) on
2026-09-03 (`/plan-eng-review`, D2). The four entries below are what that reduction and the
review's other decisions consciously left out, each with the trigger that brings it back.

### A branch role on the screen (WP-78)

**What:** A `branch` membership role, a `membership_branches` table under the 0012 composite-FK
pattern, branch-level scoping on the invoice routes (list, detail, correct, confirm, dismiss,
approve refused), read-only materials and menu for branch users, and the matching rows in
`tests/test_tenancy.py`'s matrix.

**Why:** PRD §4.3 gives branch managers a login for reviewing their own branch's invoices, and
PRD §21's cash gate is "branch raises, owner approves". M7 ships one role, so on the screen the two
parties are the branch's WhatsApp phone (which never logs in) and the owner's login - a real
separation for a pilot chain, but not a role-enforced one. `Docs/M7_DECOMPOSITION.md` §9 says so
rather than ticking §21 closed.

**Context:** Cut in the review's Step 0 (D2): no chain has asked for branch managers on the screen,
and the done-when (two tenants isolated, cash needs an approval record, the shared token gone) is
met with one role. `memberships.role` already exists with `check (role in ('tenant'))`, so widening
it is one migration. Start at `auth.py`'s `AuthContext` (add `branch_ids`), the matrix test, and the
invoice routes in `api.py`.

**Effort:** M (about a day and a half)
**Priority:** P2
**Depends on:** M7 shipped. Trigger: a pilot chain asks for a branch manager on the screen.

### A users screen with invites (WP-75)

**What:** `/settings/users` for the owner: the tenant's members, invite by email (backend calls
Supabase's admin invite with the service key, then writes the membership; a failed membership
write deletes the just-created account so the two never drift), remove a member, `member.invited`
and `member.removed` audit rows.

**Why:** PRD §4.1 lists "manage users" for the tenant role. For a one-chain pilot the founder
creates accounts in the Supabase dashboard and adds the membership row by script, so the screen
buys nothing until a second owner-side user exists.

**Context:** Deferred by D2. Public sign-ups are disabled (D8), so the invite path is the only way a
non-founder account can come to exist; re-enabling sign-ups is not the answer. Supabase's default
mailer is rate-limited to a handful of messages per hour, which also argues for dashboard
provisioning at pilot scale.

**Effort:** M
**Priority:** P3
**Depends on:** M7 shipped. Trigger: a second owner-side user on any tenant.

### Row-level security as the second lock (WP-77)

**What:** A dedicated `faida_api` database role without `bypassrls`; every request's transaction
does `set local app.tenant_id`; policies `using (tenant_id = current_setting('app.tenant_id')::uuid)`
on every tenant-owned table; the worker sets it from the job payload. Acceptance: with the
application-layer filter deliberately removed from one query in a test, Postgres still returns
nothing foreign.

**Why:** Defence in depth. M7 enforces tenancy in the application layer - a required keyword-only
`tenant_id` on every tenant-owned `db.py` method (D10) plus the route matrix - because the API is
the only thing that reads the database and it connects as the table owner, which RLS exempts.
Policies written today would guard nothing reachable (D16).

**Context:** `plan.md` §8 M7's checkbox says "RLS policies on all tenant-owned tables"; the review
amended it to this entry. Roughly 120 call sites in `db.py` need wrapping in a transaction that sets
the tenant, and the live pooler needs a second role - a multi-day change on the shipped path, owed
the day something other than the API reads the database.

**Effort:** L
**Priority:** P2
**Depends on:** M7 shipped. Trigger: the first second door to the database - a direct Supabase read
from a browser, a second service, or a data export.

### MFA for the owner role

**What:** A second factor (authenticator-app TOTP, which Supabase Auth ships) on the owner's login,
with enrolment and recovery codes on the web app.

**Why:** The owner account can approve cash, load menus and remap materials, so a phished password
is the whole tenant. PRD §26 lists MFA "where feasible".

**Context:** Deferred by the 2026-09-03 review (D18): one owner account exists for the pilot and it is
hand-provisioned. The risk to weigh when building it is a lockout on the demo laptop, so recovery
codes are part of the first version, not a follow-up.

**Effort:** M
**Priority:** P3
**Depends on:** M7 shipped. Trigger: a second real tenant, or an owner asking.

## Sales (deferred by the M8 decomposition, 2026-09-03)

M8 was decomposed in `Docs/M8_DECOMPOSITION.md` and reviewed with two outside voices on 2026-09-03
(`/plan-eng-review`, `/plan-design-review`); the founder decided its §5 on 2026-09-04 and M8 is approved
to build. The entries below are what the decomposition and its reviews consciously left out, each with the trigger
that brings it back.

### A day-totals (summary) sales export

**What:** A till that exports only day totals (branch, date, amount): the loader's item column becomes
optional again, a file with no item column groups into `summary` days with money, the door accepts a
summary day with a non-zero amount, a summary day carries net sales and no coverage, and the coverage
figure names such days beside it.

**Why:** The founder amended P1 on 2026-09-04, after Wave 1: item-wise only for the MVP, because the
summary shape doubled the loader's cases and the door's refusal set for a till nobody has met yet, and
the one integration conflict Wave 1 produced came from carrying both shapes in one body. Wave 1 shipped
both; the summary half was retired the same day and lives in history at `f1c76a4` (web) and `6ec6375`
(API), so this is an adaptation, not a build.

**Depends on:** M8 shipped. Trigger: M11's pilot chain, or any target chain, whose till exports day
totals only.

### Z-report photos through WhatsApp

**What:** A summary extraction schema for a till's end-of-day report (branch-summary or item-summary),
the `summary` day written through `POST /api/sales/days`'s door with `source = 'z_report'`, the reply
that reads the day back, and the rule that a summary is never turned into fake receipts (PRD §10).

**Why:** PRD §10's third tier and the M8 checklist's second item. With CSV as the source the photo path
would sit half-built and untested; a branch that cannot export needs it and nobody else does.

**Context:** The classification (`extraction/schema.py:37`), the polite decline (`REPLY_Z_REPORT`,
`replies.py:47`) and the `extraction_runs.outcome` value already exist, so the door is open. Start at
`extraction/pipeline.py:135-140` (today the document is marked failed) and the C3 schema probe (the
grammar budget is at its ceiling - a second schema, not fields on the invoice's).

**Effort:** M
**Priority:** P3
**Depends on:** M8 shipped. Trigger: a pilot branch whose till cannot export.

### The business-day cutoff and timezone arithmetic

**What:** A per-branch cutoff (PRD §14) and the arithmetic that turns a timestamped transaction into a
business date in the branch's timezone; `branches.timezone` finally read.

**Why:** A daily export already carries its business date as the till defines it, so M8 stores calendar
dates and applies no cutoff. The first transaction-level source (a POS API) needs the rule.

**Context:** `branches.timezone` exists (`0001_init.sql:16`) and nothing reads it. C11 says a purchase's
business day is its printed date and a sale's is the till's; changing the cutoff must never rewrite
history (PRD §14).

**Effort:** M
**Priority:** P3
**Depends on:** M8 shipped. Trigger: the first transaction-level sales source.

### Excel parsing in the loaders

**What:** Read `.xlsx` in the browser (one library, the first sheet, the same header rules) so a till
that exports only Excel loads without a Save As.

**Why:** `csv.ts` sniffs a spreadsheet binary and answers "Save As CSV" in one sentence (`csv.ts:102-109`);
that is enough until a till gives nothing else.

**Context:** The loaders parse in the browser by decision (2026-08-31); an Excel reader would join
`useCsvFile` behind the same `parseCsv` result shape.

**Effort:** S
**Priority:** P3
**Depends on:** WP-83. Trigger: a till that exports only `.xlsx`.

### A bulk "map every exact name" on the till queue

**What:** One action that maps every unmapped till name whose normalised name equals a live menu item's,
with one audit row per mapping.

**Why:** M5's rule - nothing merges without a keystroke - holds for till names too, and a 45-name till is
two minutes of keystrokes once. A chain with hundreds of names is where the rule starts to cost.

**Context:** The proposer never auto-maps even an exact name (C11.7). Start at the coverage read's queue
and `db.map_till_item`; the action must still refuse size variants that only differ by a pack word.

**Effort:** S
**Priority:** P3
**Depends on:** WP-82. Trigger: a chain with more than a hundred till names.

### A reject for till-name proposals

**What:** `POST /api/till-items/{id}/menu-item/reject`, the WP-52 shape, so a wrong top proposal stops
being offered.

**Why:** Approve, pick-from-menu and exclude cover the queue; a wrong top proposal is one keystroke
further down. The reject door exists for supplier items because a material can be created from a
proposal; a menu item cannot.

**Context:** The M5 reject is derived from `audit_events` with latest-event-wins (`db.py:913`); the same
read would serve.

**Effort:** S
**Priority:** P3
**Depends on:** WP-82. Trigger: a consultant asks.

### A branch correction door on an invoice

**What:** Set or change `invoices.branch_id` from the review screen with one `invoice.branch_set` audit
row, refusing a foreign branch the way upload does.

**Why:** Upload and manual entry accept no branch (`api.py:913`, `:729`), so a confirmed paper with no
branch is a real state; M8 shows it in a "No branch" row rather than losing it, but nothing moves it.

**Context:** `GET /api/branches` (WP-80) lets the upload form offer every branch instead of deriving
choices from the invoice list (`UploadInvoice.tsx:51-52`), which is the prevention. The correction is
one field on the correction door with the composite FK doing the refusing.

**Effort:** S
**Priority:** P2
**Depends on:** WP-80. Trigger: the first confirmed paper with no branch on a pilot.

### Branch calendars

**What:** Closure days per branch, so a missing sales day inside a window is not always a gap.

**Why:** C9's amendment reads a gap strictly inside a branch's loaded range as incomplete; a branch closed
every Friday would read incomplete every week. M8's answer is a loaded zero day (a takings-0 row, or a
file's interior gap loaded as one).

**Context:** Start at `ratio.py`'s missing-day rule and a `branch_closures` table under the composite-FK
pattern.

**Effort:** S
**Priority:** P3
**Depends on:** WP-81. Trigger: a pilot branch that closes a day a week.

### A second sales stream per branch-day

**What:** The day identity gains the stream (a second till, a delivery aggregator's report), and net sales
per branch-day becomes the sum over streams.

**Why:** C11 identifies a day by (tenant, branch, business date): one consolidated report per branch-day.
Two sources for one day would overwrite each other. Raised by the Codex outside voice (finding 5).

**Context:** `sales_daily` already carries its `layout_id`, so the backfill is one update naming the
existing days' stream; the loader's layout step already names the till.

**Effort:** M
**Priority:** P3
**Depends on:** WP-80. Trigger: a branch with two sales sources.

### A custom date range on the sales screen

**What:** Free `from` and `to` inputs beside the picker.

**Why:** The API takes any range up to 92 days; the picker exposes 28 days, 7 days and the months that
have sales, because a free range is two inputs nobody asked for.

**Context:** `GET /api/sales/branches?from&to` needs nothing; the change is the picker.

**Effort:** S
**Priority:** P3
**Depends on:** WP-84. Trigger: a pilot asks for a range the picker lacks.

### Correcting a wrongly taught branch alias

**What:** A way back for an alias taught to the wrong branch: a delete on `POST /api/branches/{id}/aliases`'s
row (one audit row), and the loader offering to re-teach a label it already knows when the consultant asks.

**Why:** It happened on the first live upload (2026-09-05, the M8 go-live sitting): `AL NAHDA` was answered
with Al Qusais Branch, both outlets' rows landed in one branch's days, and nothing on the screen could undo it.
The fix was one row deleted in SQL and a re-upload - acceptable once, with an engineer at the keyboard, and
not for a pilot chain's consultant.

**Depends on:** WP-80, WP-83. Trigger: already fired once; build it before the first pilot upload (M11) or the
moment a consultant asks.

## Contribution, signals, dashboards (deferred by the M9 decomposition, 2026-09-05)

M9 was decomposed in `Docs/M9_DECOMPOSITION.md`, reviewed twice on 2026-09-05 (once unattended, once
with the founder present, three outside voices between them) and approved to build; the founder decided
every §5 proposal that day. The entries below are what the decomposition and its reviews consciously
left out, each with the trigger that brings it back and the decision it hangs on where there is one.

### Versioned calculation runs and stored results

**What:** A run table, an invalidation rule, a recompute path, the answer to "what does a user see between
runs", and PRD §14's rule that changing a rule never rewrites history (PRD §23; M9 §5 P1 option (c)).

**Why:** Everything shipped derives on every read and stores nothing, by four recorded decisions; the
recommendation is to keep that and cost a period at the prices in force on its last day, which buys a
closed period that stops moving for one `where` clause. A run is a subsystem, and nothing has asked for
one.

**Depends on:** M9 shipped. Trigger: a customer keeps a monthly report and asks why last month's figure
changed, or an auditor asks for a figure as it stood.

### A menu price history table

**What:** Selling price changes as rows, so a past margin can be reproduced at the price then in force.

**Why:** A price change lives only in `audit_events` today, enough to answer "who changed it" and not
enough to reproduce a past margin.

**Depends on:** M9 shipped. Trigger: the same as the calculation runs.

### A packaging flag on `ingredients`

**What:** One boolean, one migration, one sentence: the coverage panel says how many costed items list
no packaging (M9 §5 P2 option (b)).

**Why:** Packaging is already costed as a recipe component, and 14 of the real menu's 20 checked items
carry a cup or a container; what nothing can do is tell a recipe with no cup from a dish that needs none.
The recommendation is one standing sentence, and this is the flag the founder may prefer.

**Depends on:** M9's P2, decided (a) on 2026-09-05. Trigger: the founder or a consultant wants the count on
the screen.

### Waste and directly attributable variable fees in branch contribution

**What:** Recorded waste and a delivery aggregator's commission subtracted from branch contribution
(PRD §23).

**Why:** Neither has a schema home and neither is anyone's ask; the sentence beneath the figure says
they are absent.

**Depends on:** M9 shipped. Trigger: a chain that records waste, or a commission statement.

### Per-tenant signal thresholds and a settings screen

**What:** The three signal thresholds as a per-tenant setting rather than constants in one module
(M9 §5 P5). The price spike has no absolute money floor by the second review's decision: the ranking by
money and the cap at five do the floor's job, and a measured per-display-unit floor is the first thing to
add here if a real panel shows the cap is not enough.

**Why:** There is no settings table anywhere in the schema, and the first customer who says a threshold
is wrong for their menu is also the first evidence about what the right one is.

**Depends on:** WP-91. Trigger: a customer says a threshold is wrong for their menu.

### A signals table, dismissal, snooze, a lifecycle

**What:** Signals as rows an owner can hide once acted on.

**Why:** Until asked, a signal is a sentence derived from the data - C5's rule and WP-55's precedent.

**Depends on:** WP-91. Trigger: an owner asks to hide a signal they have already acted on.

### A branch dashboard as its own route

**What:** A second route for a branch manager, with the branch role (WP-78 above).

**Why:** There is no user who can only see one branch; `/dashboard?branch=<id>` is the bridge, and the
day the branch role lands that link becomes the manager's landing page with no new screen written
(M9 §5 P7).

**Depends on:** WP-78. Trigger: WP-78's own - a pilot chain asks for a branch manager on the screen.

### Contribution trend over time

**What:** A direction rather than a level: two windows side by side, sparklines, charts.

**Why:** The period picker answers "which window"; a trend is a different screen nobody has asked for.

**Depends on:** WP-93. Trigger: a customer asks to see a direction.

### A day-by-day view of one dish

**What:** Which Tuesdays the karak sells: a per-day array on an item row.

**Why:** The branch drill on `/sales` already shows the days a branch's money came from, and an item's
day array would make the dashboard payload thirty times its size for a question nobody has asked. Since
the second review the database read carries the days (grouped by branch, till item and day); the wire
does not, so the day this is asked the answer is a payload field, not a query.

**Depends on:** WP-92. Trigger: a customer asks.

### A download route for the stored source CSV

**What:** A signed-URL read in `storage.py`'s shape, scoped by tenant, serving the file a sales day came
from.

**Why:** M8 stores every uploaded file immutably under its hash and puts the hash on every day, but no
route serves it back, so "traces to source" on the sales side reaches the day and its file's name and
hash, not the bytes. The gap is M8's; M9 neither widens nor closes it.

**Depends on:** WP-80. Trigger: a customer or an auditor asks to see the file a figure came from.

### An as-of menu-item detail read

**What:** The plate drill at a past date's prices, so a historical contribution figure can show the
invoice lines it was costed from.

**Why:** The only place a component's invoice line is visible is today's plate; the contribution row
carries today's cost beside its own whenever they differ and the link says which is which. An as-of
detail payload is a variant of the whole screen for a question nobody has asked.

**Depends on:** WP-90. Trigger: a consultant asks why a past figure differs from today's plate and the
row's two costs do not answer it.

### An audit read of menu price changes behind the discount sentence

**What:** One query over `audit_events` (`menu_item.price_changed`, by subject and date, fixed count) so
the item drill can withhold "sold at an average AED X against today's menu price of AED Y" when the
menu price changed after the period's end, instead of relying on the word *today's*.

**Why:** There is no price history table (M9 §5 P1, P4); the drill compares against today's price and
says so, which is honest and can still be misread as a discount on a closed month with a price rise
since.

**Depends on:** WP-94. Trigger: a consultant reads a price rise as a discount despite the word *today's*.

### Costing each day at the price in force that day

**What:** A price series per material over the window (a new read) and a plate per day, so a delivery
late in the window reprices only the days after it; PRD §19's latest-purchase-price policy changes
with it (M9 second review, D19; both outside voices).

**Why:** The period is costed at one price per material, the latest in force on its last day - PRD §19's
policy and `/menu`'s - and the lineage says so; the spike's money at stake is a since-landed figure and
the two are never added. Exact per-day economics is a different policy nobody has asked for.

**Depends on:** WP-90. Trigger: a customer asks why a late delivery moved the whole month.

### A per-branch material price

**What:** A branch key on `list_mapped_pack_costs` and a plate per branch, so the league compares branches
at what each actually paid (M9 second review; Codex 3).

**Why:** The plate is a tenant-level fact (M6): the tenant's latest purchase prices a material whichever
branch bought it, which is right for central buying and a stated limit otherwise.

**Depends on:** WP-90. Trigger: a chain whose branches buy the same material at different prices asks why
the league does not show it.

### An index on the sales tables

**What:** The first index beyond the uniques on `sales_lines` and `sales_daily`, in a 0020.

**Why:** 0019 refuses indexes until a read needs one, and the dashboard read is the read that will.

**Depends on:** WP-92. Trigger: a tenant's `sales_lines` passes a million rows or the dashboard read
passes 500 ms.

### The real menu CSV lives outside the repository, so act four's exact figures cannot fail CI

**What:** Commit a copy of the founder's 45-item menu in the loader's shape (or a fixture derived
from it) under `Docs/demo-invoices/koukh-al-shay/`, and drop the skip in
`tests/test_demo_seed.py::test_act_four_speaks_the_figures_the_runbook_quotes`.

**Why:** `DEMO_RUNBOOK.md` §H quotes exact figures (the branch the league puts first, the chain's
kept percentage before and after KAS-5, the dish at the bottom of the five, the two milk moves)
that `act_four.py` prints from the real stage, and the test that pins them runs only where
`~/Downloads/Menu engineer/koukh-al-shay/faida-loader-preview.csv` exists - the founder's
machine, not CI. Until the CSV is in the repository a change that quietly breaks act four fails
on stage rather than in CI, which is the failure the row's acceptance was written to prevent.

**Context:** WP-95, 2026-09-05. The practice stage (the seed's five items and the rehearsal week)
is pinned everywhere, but it fires no signal and speaks none of §H's figures. The runbook already
publishes the derived plate costs, so the prices are not a new disclosure; the recipes are the
client's, which is why this is a data call and not an engineering one.

**Depends on:** the founder's say-so on committing the client's menu. Trigger: fired - the day
act four became the demo bar.

### The screen's headline rounding truncates while every API sentence rounds half up

**What:** Decide one rounding for a whole-dirham headline and apply it to `format.roundedAed`
(string operations only, per the house rule), with its tests; or keep truncation and say so
beside every Python sentence that sits next to a table figure.

**Why:** `roundedAed` truncates by design since M5 ("can only ever understate a ranking figure by
under a dirham"), and every sentence composed in Python - the signals, the answer, the
contribution notes, the runbook's script - rounds half up (`ROUND_HALF_UP`). The dashboard is the
first screen to put both on one line: a signal's detail says "AED 1,106 more" while the money
column beside it reads "AED 1,105", and the runbook had to quote fils (135.58 rather than 136) to
avoid naming a figure the table would not show. One dirham, but on the one screen whose job is to
be believed at a glance.

**Context:** Found at WP-93's browser walk and again at WP-95's runbook, 2026-09-05. The
recommended fix is to round half up in `roundedAed` - it moves other screens' headline figures
by at most one dirham, towards the figure the API's own words use - and it is a display-rule
change, so it is the founder's call (the 2026-08-30 design review pinned the rounding rule).

**Depends on:** nothing. Trigger: fired, on the dashboard's signal line.

## Extraction & matching

### A handwritten margin note gets folded into an item name and splits the catalog

**What:** On EDGE-01 the model returns line 6's `raw_name` as
`"Avocado Credit: one box returned, soft fruit"` instead of `"Avocado"`.
The page prints `Avocado` in the description cell; the rest is a separate handwritten margin
note on a credit row.

**Why:** Measured in 3 of 5 live Gemini 3 Flash runs on 2026-08-29, and the consequence is verified:

```
snap_item('Avocado')                                      -> item 1 (Avocado)
snap_item('Avocado Credit: one box returned, soft fruit')  -> None      (SNAP_THRESHOLD = 0.8)
```

A snap miss means `confirm` mints a **second** "Avocado" catalog row.
That is the same catalog-splitting, price-alert-silencing failure WP-29 closed for bilingual
names on 2026-08-29, arriving through a different door: an annotation rather than a second script.
It matters more once M5 starts mapping catalog rows to raw materials, because a split catalog
corrupts the cost of every menu item built on it.

**Context:** `raw_name` scored 99-100% across the five runs, so the eval barely registers this -
the damage is downstream in `matching.py`, not in the score.
Credit and return lines are where it shows up, because that is where people write in the margin.
Start from WP-29's shape: a deterministic fix in `matching.py` alone, with extraction, the prompt,
the schema and the F8 ground truth untouched.
The hard part is deciding when trailing prose is an annotation rather than part of a real name,
without truncating legitimately long supplier item names.
A prompt rule is the wrong layer - plan.md §5, "accuracy is a pipeline property, not a prompt property".
Proposed for M6 as WP-65 in the 2026-08-29 decomposition (plan.md §7.3); founder decision pending.

**Effort:** M
**Priority:** P2
**Depends on:** None. Coordinate with whoever owns `matching.py` (the M5 terminal is adjacent).

### Supplier matching re-parses the whole catalog on every invoice line

**What:** `snap_item` (`matching.py:172-190`) computes `_pack_tokens` twice for every catalog item,
and `pipeline.py:205` calls `snap_item` once per invoice line, so supplier matching is
O(lines x catalog) regex evaluations per invoice against a pattern built from ~120 unit spellings.

**Why:** PH-01 has 34 lines.
At a 200-item catalog that is roughly 13,600 regex passes per invoice; at 2,000 items, 136,000.
Today it is milliseconds and invisible inside a ~9.5 s model call, so this is a characterisation,
not a complaint.

**Context:** The catalog self-builds on confirm, so item count grows with every new supplier item
forever, per tenant.
This becomes noticeable at multi-branch chain scale (the 75-branch chain in the design doc), not at
demo scale.
The fix is obvious when it is needed: hoist the per-item pack tokens out of the per-line loop and
compute them once per invoice, roughly a 34x reduction on the corpus's largest invoice.
**Measure before fixing** - plan.md §2 warns against optimising ahead of proven need, and the point
of recording it is so a future slow-confirm investigation starts here instead of blaming model latency.

**Effort:** S
**Priority:** P4
**Depends on:** None. Should be measured before it is fixed.

### The eval marks TH-01's subtotal wrong when the model reads the other legitimate row

**Corrected 2026-08-29.** An earlier version of this entry called this a silent wrong number that
poisons price memory, and recommended a stricter C4 cross-check. **That was wrong on both counts,
disproven by the trace below.** It is an eval-strictness artifact with no product consequence.

**What:** On TH-01 the model sometimes returns `subtotal` as `673.00` (the printed "Net of VAT"
row) instead of `706.65` (the printed "Subtotal (VAT inclusive)" row). Observed once in ten live
Gemini 3 Flash runs on 2026-08-29. Ground truth records 706.65, so the eval scores it wrong and
`header subtotal` reads 90% on that run.

**Why it does not matter to the product.** Traced through the shipped validator and the shipped
net-price maths, both readings side by side:

```
CORRECT (truth)  subtotal=706.65        RUN 3 (misread)  subtotal=673.00
   tax_treatment  = inclusive              tax_treatment  = inclusive
   arith          = passed                 arith          = passed
   subtotal_check = passed                 subtotal_check = passed
   doc status     = green                  doc status     = green
   net factor     = 0.95238095...          net factor     = 0.95238095...
   line 1 net unit price stored            line 1 net unit price stored
                  = 32.000                                = 32.000
```

Nothing downstream reads the subtotal. `validate.py:174` derives the tax treatment anchored on the
line sum, "never on the printed subtotal", and `db.py:533` builds the net-price factor from
`tax_treatment, tax, total` alone. The price baseline `confirm` writes is byte-identical either
way, so this cannot poison price history.

**And it is not silent.** `_check_subtotal` does cross-check the subtotal and does feed the
document status. It passes 673.00 deliberately, not accidentally:

```
subtotal                                       subtotal_check   doc status
706.65  the printed 'Subtotal (VAT inclusive)'        passed        green
673.00  the printed 'Net of VAT'                      passed        green
670.00  a genuinely wrong number                      failed        amber
707.00  wrong by 0.35                                 failed        amber
500.00  a badly wrong number                          failed        amber
```

A VAT-inclusive invoice may legitimately print its subtotal as either the gross (equal to the
total) or the net (total - tax), and 673.00 is exactly 706.65 - 33.65. The function's own
docstring says why it accepts both: *"Accepting a legitimate printing matters as much as catching
a wrong one: manufacturing an amber on a correct document spends the sender's attention and
teaches them the ambers are noise."* A genuinely wrong subtotal goes amber, so the §5 gate holds.

**What is actually left, and it is small.** Two options, neither urgent:

1. Teach the eval the same tolerance the validator already has, so `header subtotal` stops
   flickering to 90% for a reading the product treats as correct. This matches the WP-16
   principle that there is one implementation of C4 and the eval scores against it. The argument
   against: an answer key exists to be exact, and loosening it to accept two values sets a
   precedent worth thinking about before applying it more widely.
2. Display fidelity: the review screen would show 673.00 beside a paper whose "Subtotal" row reads
   706.65. Nothing is wrong, but a cafeteria owner comparing screen to paper sees a number that
   is not on the line it is labelled with. Cosmetic, and only if someone complains.

**Do not** build the stricter validator cross-check the earlier version of this entry proposed.
It already exists in more permissive form, on purpose, and tightening it would manufacture ambers
on correct invoices.

**Effort:** S
**Priority:** P4
**Depends on:** None. Option 1 belongs with whoever owns `eval/score.py`.

### Regenerating ground truth would rewrite 14 signed files for serialization reasons alone

**What:** Running `python -m eval.convert_generated` today rewrites 14 of 16 `truth.json` files and
would trip their `SIGNOFF.json` hashes - but the only difference is two schema fields
(`invoice_date_text`, `payment_terms_text`) that were added after the founder signed off, and which
`exclude_none=False` now serializes.

**Why:** Verified on 2026-08-29 by regenerating in memory and diffing: **no printed fact moves.**
All 130 lines across all 15 invoice cases keep their exact `raw_name`, `unit` and `pack_size`.
The risk is that the next person to touch the converter sees 14 changed files, cannot tell a
serialization diff from a truth diff, and either re-signs blindly or abandons a correct change.

**Context:** `convert_generated.py`'s own `--only` docstring already anticipates this
("a serialization-order or schema-field change would trip every SIGNOFF.json hash at once").
The clean resolution is a deliberate one-time regeneration plus a founder re-sign through
`Docs/f8-review.html`, done as its own commit that changes nothing but serialization, so the diff
is reviewable as exactly that. Do not bundle it with a content change.

**Effort:** S
**Priority:** P3
**Depends on:** Founder availability for the F8 re-sign.
