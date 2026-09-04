-- Faida: migration 0019 alone, for a live project already at 0018.
--
-- Adds M8's sales tables (WP-80): sales_layouts, till_items, sales_daily,
-- sales_lines and branch_aliases. Tables and nothing else - no column on any
-- existing table changes, nothing is deleted, nothing is backfilled.
--
-- HOW TO USE THIS FILE
--   Open it, select all, copy, paste into the Supabase SQL editor, run once.
--   Every byte of this file is SQL. There is nothing in it to select wrongly.
--
-- RUN THIS BEFORE WP-80 MERGES TO MASTER.
--   Nothing on master reads these tables until WP-80's router, and that
--   router has no screen until WP-84, so either order is safe today. The
--   written order stays migration-first because it is the strictly safe
--   direction (Decision Log 2026-09-01), and a rule with exceptions that
--   need remembering is not a rule. Old code against the new schema is
--   unaffected in both directions, so rollback is Railway redeploying the
--   previous build; the tables can stay.
--
-- BEFORE YOU RUN IT
--   Run the check below on its own first. Both columns must come back as
--   shown; anything else means stop and read the note beside it.
--
--   select not exists (select 1 from information_schema.tables
--                      where table_name = 'sales_daily') as needs_0019,
--          exists (select 1 from information_schema.tables
--                  where table_name = 'memberships') as has_0018;
--
--   needs_0019    true    (false: already applied; the run would fail on
--                          `create table`)
--   has_0018      true    (false: the project is behind 0018 - run
--                          Docs/apply_m7_migrations.sql first; the composite
--                          key on branches this file references is created
--                          there)
--
--   (A fresh database with no tenants table at all needs the full migration
--   set in supabase/migrations/, not this file.)
--
-- WHAT IT DELETES
--   Nothing.

begin;

create table sales_layouts (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references tenants(id),
  name         text not null,
  header_key   text not null,
  columns      jsonb not null,
  amount_basis text not null check (amount_basis in ('inclusive', 'exclusive')),
  date_order   text not null check (date_order in ('dmy', 'ymd')),
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  unique (tenant_id, name)
);

alter table sales_layouts add constraint sales_layouts_tenant_id_uidx unique (tenant_id, id);

comment on table sales_layouts is
  'which column of a till''s CSV export is which (M8 WP-80, C11.1): saved once '
  'per till by name, applied by header name, never by position.';

create table till_items (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references tenants(id),
  name         text not null,
  name_key     text not null,
  code         text,
  menu_item_id uuid,
  excluded_at  timestamptz,
  created_at   timestamptz not null default now(),
  foreign key (tenant_id, menu_item_id) references menu_items (tenant_id, id)
);

create unique index till_items_tenant_code_uidx
  on till_items (tenant_id, code) where code is not null;
create unique index till_items_tenant_name_key_uidx
  on till_items (tenant_id, name_key) where code is null;

alter table till_items add constraint till_items_tenant_id_uidx unique (tenant_id, id);

comment on table till_items is
  'every distinct item name a till has printed (M8 WP-80), minted on first '
  'sight and mapped to a menu item by a person one keystroke at a time (WP-82). '
  'Identity is the till''s code when there is one, the normalised name otherwise.';

create table sales_daily (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null references tenants(id),
  branch_id       uuid not null,
  business_date   date not null,
  granularity     text not null check (granularity in ('item', 'summary')),
  source          text not null default 'csv' check (source in ('csv')),
  amount_basis    text not null check (amount_basis in ('inclusive', 'exclusive')),
  vat_rate        numeric(6,4),
  takings         numeric(12,2) not null,
  net_sales       numeric(12,2) not null,
  line_count      integer not null check (line_count >= 0),
  layout_id       uuid,
  source_sha256   text,
  source_filename text,
  loaded_by       text not null,
  loaded_at       timestamptz not null default now(),
  unique (tenant_id, branch_id, business_date),
  foreign key (tenant_id, branch_id) references branches (tenant_id, id),
  foreign key (tenant_id, layout_id) references sales_layouts (tenant_id, id)
);

alter table sales_daily add constraint sales_daily_tenant_id_uidx unique (tenant_id, id);

comment on table sales_daily is
  'what a branch took on one business day (M8 WP-80, C11): takings as the '
  'till printed them, net sales derived beside them with the basis and rate '
  'frozen, unique per branch-day so a re-upload replaces and never doubles.';
comment on column sales_daily.source_sha256 is
  'the exact bytes this day came from, by hash; the file lives in Storage at '
  '{tenant_id}/sales/{sha256}.csv, immutable. Computed by the server, never '
  'the client''s word.';

create table sales_lines (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null,
  sales_day_id uuid not null,
  position     integer not null,
  till_item_id uuid not null,
  name         text not null,
  code         text,
  qty          numeric(12,3),
  amount       numeric(12,2) not null,
  net_amount   numeric(12,2) not null,
  unique (sales_day_id, position),
  foreign key (tenant_id, sales_day_id) references sales_daily (tenant_id, id) on delete cascade,
  foreign key (tenant_id, till_item_id) references till_items (tenant_id, id)
);

comment on table sales_lines is
  'the item-wise rows of an item day (M8 WP-80): printed name and code as '
  'evidence, the till item as identity, amount as printed and net beside it.';

create table branch_aliases (
  id         uuid primary key default gen_random_uuid(),
  tenant_id  uuid not null references tenants(id),
  branch_id  uuid not null,
  alias_key  text not null,
  alias      text not null,
  created_at timestamptz not null default now(),
  unique (tenant_id, alias_key),
  foreign key (tenant_id, branch_id) references branches (tenant_id, id)
);

alter table branch_aliases add constraint branch_aliases_tenant_id_uidx unique (tenant_id, id);

comment on table branch_aliases is
  'the till''s own label for a branch (M8 WP-80, C11.1), taught once in the '
  'loader''s mapping step and reused by every layout.';

alter table sales_layouts enable row level security;
alter table till_items enable row level security;
alter table sales_daily enable row level security;
alter table sales_lines enable row level security;
alter table branch_aliases enable row level security;

commit;

-- Verify: five tables, all with row security on, all empty (WP-83's loader
-- fills them; WP-85 stages the demo week).
select relname, relrowsecurity
  from pg_class
 where relname in ('sales_layouts', 'till_items', 'sales_daily', 'sales_lines',
                   'branch_aliases')
 order by relname;

select (select count(*) from sales_layouts) as layouts,
       (select count(*) from till_items) as till_items,
       (select count(*) from sales_daily) as days,
       (select count(*) from sales_lines) as lines,
       (select count(*) from branch_aliases) as aliases;
