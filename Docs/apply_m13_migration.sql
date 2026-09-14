-- Faida: migration 0023 alone, for a live project already at 0022.
--
-- Adds the staff incentive's tables (M13, plan.md §8): the role shares, the
-- scheme months with their per-branch targets, the push weeks with their
-- push items and per-branch portion targets, the statement approvals, the
-- per-branch pause, and the unique index that makes one scoreboard job per
-- branch, variant and day a rule the database keeps.
--
-- HOW TO USE THIS FILE
--   Open it, select all, copy, paste into the Supabase SQL editor, run once.
--   Every byte of this file is SQL. There is nothing in it to select wrongly.
--
-- THIS ONE ADDS AND DELETES NOTHING. No column is dropped, no row is
--   rewritten, and the build running today ignores every table here. So the
--   order does not matter the way it did for 0020: this can be run before the
--   deploy or after it, and redeploying the previous build with the tables in
--   place is a complete rollback. A backup is still a minute well spent
--   (pg_dump, as before 0022), and Supabase's dashboard has the button.
--
-- WHEN TO RUN IT
--   Any time before the M13 deploy. After the deploy the worker's tick runs,
--   finds no scheme month, and enqueues nothing - which is the safe state,
--   and why INCENTIVE_ENABLED is left unset (true). The first scoreboard is
--   sent only once the owner has created a scheme month on /incentive and a
--   branch's morning has come, and only after Meta has approved the template.
--
-- BEFORE YOU RUN IT
--   Run the check below on its own first. Both columns must come back as
--   shown; anything else means stop and read the note beside it.
--
--   select exists (select 1 from information_schema.tables
--                  where table_name = 'brief_recipients')     as has_0022,
--          exists (select 1 from information_schema.tables
--                  where table_name = 'scheme_months')        as has_0023;
--
--   has_0022    true   (false: the project is behind 0022 - run
--                       Docs/apply_m10_migration.sql first)
--   has_0023    false  (true: already applied; the run below would fail on
--                       `create table`)

begin;

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

commit;

-- Verify: the eight tables exist with row security on, all empty, and the
-- index is there. Expected: eight rows each reading `<name> | t`, eight
-- counts of 0, and one row naming `jobs_send_scoreboard_uidx`.
select relname, relrowsecurity
  from pg_class
 where relname in ('role_shares', 'scheme_months', 'scheme_month_targets', 'push_weeks',
                   'push_items', 'push_item_targets', 'statement_approvals',
                   'incentive_branches')
 order by relname;

select (select count(*) from role_shares)         as role_shares,
       (select count(*) from scheme_months)       as scheme_months,
       (select count(*) from scheme_month_targets) as scheme_month_targets,
       (select count(*) from push_weeks)          as push_weeks,
       (select count(*) from push_items)          as push_items,
       (select count(*) from push_item_targets)   as push_item_targets,
       (select count(*) from statement_approvals) as statement_approvals,
       (select count(*) from incentive_branches)  as incentive_branches;

select indexname from pg_indexes where indexname = 'jobs_send_scoreboard_uidx';

-- ---------------------------------------------------------------------------
-- NOTHING ELSE TO PASTE. The role shares, the scheme month, the push lists
-- and the approval are all typed by the owner on /incentive, each through its
-- own door with its own audit row; there is no row to add by hand here.
--
-- To stop one branch's scoreboard without deleting anything (the console's
-- pause control does this with an audit row; this is the SQL of last resort):
--
--   insert into incentive_branches (tenant_id, branch_id, paused_at)
--   values ('<tenant id>', '<branch id>', now())
--   on conflict (tenant_id, branch_id) do update set paused_at = now();
--
-- To stop every scoreboard at once, without SQL: INCENTIVE_ENABLED=false on
-- Railway.
