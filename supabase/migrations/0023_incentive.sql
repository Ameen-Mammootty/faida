-- 0023: the staff incentive (plan.md §8 M13, D1 to D18; issue #6 the spec, #8 the ticket).
-- Appended per contract C7; the manager squashes periodically (plan.md §4 policy).
--
-- Additive - eight tables and one index, none of which the build before this
-- one reads. So this may be applied ahead of the deploy, and a code rollback
-- with the schema in place is complete; dropping the tables is the reverse
-- paste. Docs/apply_m13_migration.sql is the paste-ready copy with its
-- pre-flight.
--
-- ONLY WHAT THE OWNER TYPED AND WHAT THE OWNER APPROVED ARE ROWS. The scores,
-- the pool and the statement are derived on every read from the sales days
-- (`incentive.py`, C16) and stored nowhere, in the ratio's shape (C11): a
-- screen and a card can then never disagree with the days they were read
-- from. The exception that proves it is `statement_approvals.figures` - the
-- figures *as approved*, kept because an approved statement is a fact with an
-- actor and a time, and a sales day replaced after approval is a second fact
-- beside it, not a rewrite of the first (D12).
--
-- THE 0019 SHAPE, everywhere: every row carries `tenant_id`; every child key
-- is composite `(tenant_id, parent_id)` so a push item under Tenant A can
-- never point at Tenant B's menu item whatever the application forgot; the
-- redundant `unique (tenant_id, id)` on each parent is what those keys need;
-- deny-all row-level security because Supabase serves `public` over
-- PostgREST, and tenancy is enforced in the application layer by decision
-- (Decision Log 2026-09-03).
--
-- The tables, in the order the owner meets them:
--
-- 1. `role_shares`: one row per tenant, the three percentages that split a
--    pool between the manager, the supervisor and the sales team (D2).
--    Editable at any time; a scheme month snapshots them when it is created,
--    which is how "applied from the next month" holds without a version
--    table.
-- 2. `scheme_months`: the calendar month, one per tenant and month, with the
--    shares snapshot on the row (D4: frozen when created).
-- 3. `scheme_month_targets`: each branch's net sales target, the percentage
--    of net sales above target that goes to the pool, and the optional cap
--    (D3, D8). Null cap means no cap.
-- 4. `push_weeks`: Monday to Sunday clipped to the month (D5), laid out by
--    the application when the month is created - one row per week the month
--    spans, so a week is a thing a push list can be set on and a card can
--    name.
-- 5. `push_items`: a menu item on a week's list with its rate per portion
--    above target (D6, D7). One per week and menu item. This one cascades
--    from its week, and `push_item_targets` cascades from it, because setting
--    a list replaces it: the write deletes the week's items and the targets
--    go with them. Nothing above cascades from a scheme month, because a
--    month is never deleted - it is the record of a month.
-- 6. `push_item_targets`: the portion target per branch for that item (D6).
-- 7. `statement_approvals`: the owner's approval of one branch's month - the
--    actor, the reason, the time and the figures approved (D11, D12). One per
--    month and branch, so a second approval is refused by the database.
-- 8. `incentive_branches`: the per-branch pause (D18). A row exists only
--    once a branch has been paused or resumed; `paused_at` null is running.
--
-- The jobs index is 0022's shape for the scoreboard: one `send_scoreboard`
-- job per branch, variant and day, whatever its status, so a second tick, a
-- second instance or a replayed approval inserts against it and gets nothing.

-- 1. role_shares -----------------------------------------------------------------

create table role_shares (
  tenant_id      uuid primary key references tenants(id),
  manager_pct    numeric(5,2) not null check (manager_pct >= 0),
  supervisor_pct numeric(5,2) not null check (supervisor_pct >= 0),
  sales_pct      numeric(5,2) not null check (sales_pct >= 0),
  updated_at     timestamptz not null default now(),
  check (manager_pct + supervisor_pct + sales_pct = 100)
);

comment on table role_shares is
  'how a branch team''s pool splits between the manager, the supervisor and '
  'the sales team (M13 D2): one row per tenant, editable at any time; a '
  'scheme month snapshots it at creation, so a running month keeps the '
  'shares it started with.';

-- 2. scheme_months ---------------------------------------------------------------

create table scheme_months (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null references tenants(id),
  -- The first day of the calendar month: the month's identity.
  month          date not null check (extract(day from month) = 1),
  -- The role shares in force when the month was created (D2, D4).
  manager_pct    numeric(5,2) not null check (manager_pct >= 0),
  supervisor_pct numeric(5,2) not null check (supervisor_pct >= 0),
  sales_pct      numeric(5,2) not null check (sales_pct >= 0),
  created_at     timestamptz not null default now(),
  check (manager_pct + supervisor_pct + sales_pct = 100),
  unique (tenant_id, month)
);

alter table scheme_months add constraint scheme_months_tenant_id_uidx unique (tenant_id, id);

comment on table scheme_months is
  'the calendar month a branch''s incentive is scored and paid on (M13 D4), '
  'frozen when created, carrying the role shares snapshot; one per tenant '
  'and month. Everything scored is derived on read (C16); only this and the '
  'targets are rows.';

-- 3. scheme_month_targets --------------------------------------------------------

create table scheme_month_targets (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references tenants(id),
  scheme_month_id  uuid not null,
  branch_id        uuid not null,
  net_sales_target numeric(12,2) not null check (net_sales_target >= 0),
  above_target_pct numeric(5,2) not null
                   check (above_target_pct >= 0 and above_target_pct <= 100),
  -- Null is no cap (D8), never a cap of zero.
  cap              numeric(12,2) check (cap is null or cap >= 0),
  unique (scheme_month_id, branch_id),
  foreign key (tenant_id, scheme_month_id) references scheme_months (tenant_id, id),
  foreign key (tenant_id, branch_id) references branches (tenant_id, id)
);

comment on table scheme_month_targets is
  'what the owner typed for one branch and one scheme month (M13 D3, D8): the '
  'net sales target, the share of net sales above it that goes to the pool, '
  'and the optional cap. Frozen with the month.';

-- 4. push_weeks ------------------------------------------------------------------

create table push_weeks (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null references tenants(id),
  scheme_month_id uuid not null,
  start_date      date not null,
  end_date        date not null check (end_date >= start_date),
  unique (scheme_month_id, start_date),
  foreign key (tenant_id, scheme_month_id) references scheme_months (tenant_id, id)
);

alter table push_weeks add constraint push_weeks_tenant_id_uidx unique (tenant_id, id);

comment on table push_weeks is
  'Monday to Sunday clipped to the scheme month (M13 D5), laid out when the '
  'month is created; a week not yet started may be re-aimed, a week under '
  'way is frozen - the rule is the application''s, read against the '
  'branches'' own local date.';

-- 5. push_items ------------------------------------------------------------------
--
-- This one cascades from its week, and `push_item_targets` cascades from it,
-- because setting a list replaces it: the write deletes the week's items and
-- the targets go with them. Nothing cascades from a scheme month, because a
-- month is never deleted - it is the record of a month.

create table push_items (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references tenants(id),
  push_week_id     uuid not null,
  menu_item_id     uuid not null,
  rate_per_portion numeric(12,2) not null check (rate_per_portion >= 0),
  unique (push_week_id, menu_item_id),
  foreign key (tenant_id, push_week_id) references push_weeks (tenant_id, id) on delete cascade,
  foreign key (tenant_id, menu_item_id) references menu_items (tenant_id, id)
);

alter table push_items add constraint push_items_tenant_id_uidx unique (tenant_id, id);

comment on table push_items is
  'a menu item on one push week''s list with its rate per portion above '
  'target (M13 D6, D7). The console refuses an item with no till name mapped; '
  'one whose mapping is removed later scores as a named hole, never zero.';

-- 6. push_item_targets -----------------------------------------------------------

create table push_item_targets (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null references tenants(id),
  push_item_id   uuid not null,
  branch_id      uuid not null,
  portion_target numeric(12,3) not null check (portion_target >= 0),
  unique (push_item_id, branch_id),
  foreign key (tenant_id, push_item_id) references push_items (tenant_id, id) on delete cascade,
  foreign key (tenant_id, branch_id) references branches (tenant_id, id)
);

comment on table push_item_targets is
  'the portion target one branch is held to for one push item (M13 D6): a '
  'small branch and a large branch are not held to one number.';

-- 7. statement_approvals ---------------------------------------------------------

create table statement_approvals (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null references tenants(id),
  scheme_month_id uuid not null,
  branch_id       uuid not null,
  approved_at     timestamptz not null default now(),
  actor           text not null,
  reason          text not null check (length(btrim(reason)) > 0),
  -- incentive.figures_json of the statement as approved: what was paid.
  figures         jsonb not null,
  unique (scheme_month_id, branch_id),
  foreign key (tenant_id, scheme_month_id) references scheme_months (tenant_id, id),
  foreign key (tenant_id, branch_id) references branches (tenant_id, id)
);

comment on table statement_approvals is
  'the owner''s approval of one branch''s statement for one scheme month '
  '(M13 D11, D12): the actor, the reason, the time and the figures approved. '
  'The audit row incentive.statement_approved is written in the same '
  'transaction (C8). A day replaced afterwards leaves this untouched and the '
  'read says the till now says otherwise.';

-- 8. incentive_branches ----------------------------------------------------------

create table incentive_branches (
  tenant_id  uuid not null references tenants(id),
  branch_id  uuid not null,
  -- Set to stop this one branch's scoreboard without touching anything
  -- else; the per-branch half of the INCENTIVE_ENABLED kill switch (D18).
  paused_at  timestamptz,
  created_at timestamptz not null default now(),
  primary key (tenant_id, branch_id),
  foreign key (tenant_id, branch_id) references branches (tenant_id, id)
);

comment on table incentive_branches is
  'the per-branch pause of the scoreboard (M13 D18): a row exists once a '
  'branch has been paused or resumed; paused_at null is running. The audit '
  'rows incentive.branch_paused and .resumed carry who and when.';

-- The jobs index: one scoreboard per branch, variant and day ----------------------

create unique index jobs_send_scoreboard_uidx
  on jobs (kind, (payload->>'branch_id'), (payload->>'variant'), (payload->>'day'))
  where kind = 'send_scoreboard';

comment on index jobs_send_scoreboard_uidx is
  'one send_scoreboard job per branch, variant (daily or final) and day, '
  'whatever its status (M13). db.enqueue_scoreboard_once inserts against it '
  'with on conflict do nothing.';

-- Deny-all, per the 0001 convention.
alter table role_shares enable row level security;
alter table scheme_months enable row level security;
alter table scheme_month_targets enable row level security;
alter table push_weeks enable row level security;
alter table push_items enable row level security;
alter table push_item_targets enable row level security;
alter table statement_approvals enable row level security;
alter table incentive_branches enable row level security;
