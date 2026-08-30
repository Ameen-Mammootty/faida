-- Faida M6: migrations 0015 and 0016, applied by hand, for a database at 0014.
--
-- A live project that already ran the original 0015 (applied 2026-08-30,
-- before the design review added the category column) needs
-- Docs/apply_m6_category.sql instead - a paste of this file would fail on
-- `create table menu_items`.
--
-- HOW TO USE THIS FILE
--   Open it, select all, copy, paste into the Supabase SQL editor, run once.
--   Every byte of this file is SQL. There is nothing in it to select wrongly.
--
-- BEFORE YOU RUN IT
--   This project has no migration tracking table - migrations are applied by
--   hand - so "the database is at 0014" is an assumption until you look. Run
--   the query below on its own first. It must come back true. If it is false,
--   0015 is already applied: use Docs/apply_m6_category.sql for the 0016
--   catch-up instead.
--
--   select to_regclass('public.menu_items') is null as needs_0015;
--
-- AFTERWARDS
--   Run that same query again; it should now read false. Only then deploy the
--   API - the menu endpoints write these tables and error without them.
--   Migrate first, deploy second.
--
-- One transaction: Postgres has transactional DDL, so either everything lands
-- or nothing does. There is no half-migrated state to clean up.

begin;

-- ---------------------------------------------------------------------------
-- 0015_menu_and_recipes.sql
-- ---------------------------------------------------------------------------

create table menu_items (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references tenants(id),
  name          text not null,
  selling_price numeric(12,3) not null check (selling_price > 0),
  archived_at   timestamptz,
  created_at    timestamptz not null default now()
);

create unique index menu_items_tenant_name_uidx
  on menu_items (tenant_id, name) where archived_at is null;

alter table menu_items add constraint menu_items_tenant_id_uidx unique (tenant_id, id);

create table recipes (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null,
  menu_item_id   uuid not null,
  version        integer not null check (version >= 1),
  yield_portions numeric(10,3) not null check (yield_portions > 0),
  yield_label    text,
  created_at     timestamptz not null default now(),
  unique (menu_item_id, version),
  foreign key (tenant_id, menu_item_id) references menu_items (tenant_id, id)
);

alter table recipes add constraint recipes_tenant_id_uidx unique (tenant_id, id);

create table recipe_components (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null,
  recipe_id     uuid not null,
  position      integer not null,
  ingredient_id uuid not null,
  qty           numeric(14,4) not null check (qty > 0),
  unit          text not null,
  source_text   text,
  unique (recipe_id, position),
  foreign key (tenant_id, recipe_id) references recipes (tenant_id, id),
  foreign key (tenant_id, ingredient_id) references ingredients (tenant_id, id)
);

comment on table recipes is
  'append-only recipe versions (M6 WP-60): the current recipe is the newest '
  'version, the history is the table. Every write lands one audit_events row '
  'naming its actor.';
comment on column recipes.yield_portions is
  'the batch divisor: one pot of this recipe makes this many portions. WP-61 '
  'divides the summed component cost by it, once.';
comment on column recipe_components.source_text is
  'the recipe card''s own words for this line, kept beside the consultant''s '
  'converted number - the only audit a typed quantity will ever have.';

alter table menu_items enable row level security;
alter table recipes enable row level security;
alter table recipe_components enable row level security;

-- ---------------------------------------------------------------------------
-- 0016_menu_category.sql
-- ---------------------------------------------------------------------------

alter table menu_items add column category text;

comment on column menu_items.category is
  'the menu''s own section for this item (Tea Corner, Special Gravy...), as '
  'the consultant loads it (WP-64''s CSV carries a category column). Null '
  'means the menu prints no sections; the screen groups by this and never '
  'invents one.';

commit;
