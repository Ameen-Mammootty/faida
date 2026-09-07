-- Faida: migration 0020 alone, for a live project already at 0019.
--
-- Moves supplier aliases out of the `suppliers.name_aliases` array into a
-- table of their own (`supplier_aliases`), copies every alias across, and
-- drops the column. From here on an alias belongs to exactly one supplier per
-- tenant, so no two suppliers can answer to the same printed name.
--
-- HOW TO USE THIS FILE
--   Open it, select all, copy, paste into the Supabase SQL editor, run once.
--   Every byte of this file is SQL. There is nothing in it to select wrongly.
--
-- TAKE A BACKUP FIRST. This is the first migration since 0017 that removes
--   something: `suppliers.name_aliases` is dropped at the end. Supabase's
--   dashboard has a database backup button; take one, note the time, and only
--   then run this. The 0017 lesson was that a migration nobody had rehearsed
--   met a database nobody had backed up.
--
-- RUN THIS BEFORE WP-87 MERGES TO MASTER, AND DEPLOY RIGHT AFTER.
--   Master today reads `suppliers.name_aliases`, so between this run and the
--   deploy the old build cannot match a supplier by alias: an invoice that
--   arrives in that window books under nobody and waits, which is a delay and
--   not a wrong number. WP-87's build reads the new table and cannot run
--   against the old column, so the order is: backup, run this, deploy.
--   Rolling back to the previous build means restoring the backup, which is
--   why the backup line is above and not below.
--
-- BEFORE YOU RUN IT
--   Run the check below on its own first. All three columns must come back as
--   shown; anything else means stop and read the note beside it.
--
--   select exists (select 1 from information_schema.columns
--                  where table_name = 'suppliers' and column_name = 'name_aliases')
--            as needs_0020,
--          exists (select 1 from information_schema.tables
--                  where table_name = 'sales_daily') as has_0019,
--          (select count(*) from suppliers) as suppliers_now;
--
--   needs_0020     true    (false: already applied; the run would fail on
--                           `create table`)
--   has_0019       true    (false: the project is behind 0019 - run
--                           Docs/apply_m8_migrations.sql first)
--   suppliers_now  a small number, and the same number you see on the
--                  supplier list. Write it down: the verify block at the
--                  bottom prints it again.
--
--   Then run this second check, which lists the aliases that would be dropped
--   because two suppliers in one tenant hold the same one. Expected: no rows.
--   Any row it prints is an alias to re-add to the right supplier afterwards,
--   so copy the answer somewhere before you run the migration.
--
--   select tenant_id, normalized, count(*) as suppliers_holding_it,
--          array_agg(supplier_name order by supplier_name) as held_by
--     from (select s.tenant_id, s.name as supplier_name,
--                  trim(regexp_replace(
--                    regexp_replace(
--                      regexp_replace(lower(alias), '(?<!\d)\.|\.(?!\d)', ' ', 'g'),
--                      '[^[:alnum:][:space:].]', ' ', 'g'),
--                    '\s+', ' ', 'g')) as normalized
--             from suppliers s, unnest(s.name_aliases) as alias) named
--    where normalized <> ''
--    group by tenant_id, normalized
--   having count(distinct supplier_name) > 1;
--
--   (A fresh database with no tenants table at all needs the full migration
--   set in supabase/migrations/, not this file.)
--
-- WHAT IT DELETES
--   The column `suppliers.name_aliases`, after copying every alias in it into
--   the new table. No supplier row, no invoice, no price is touched.
--
--   One case loses an alias on purpose, and it is the reason the table exists:
--   if two suppliers in one tenant both hold the same alias (spelt the same
--   way once normalized), only the first by supplier name keeps it. The array
--   allowed that state and the matcher would have booked papers under
--   whichever sorted first, silently. The second query in BEFORE YOU RUN IT
--   lists any alias this would drop - run it first, because once the column
--   is gone the answer is gone with it. On the demo project it returns
--   nothing.

begin;

create table supplier_aliases (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references tenants(id),
  supplier_id uuid not null references suppliers(id) on delete cascade,
  alias       text not null,
  normalized  text not null,
  created_at  timestamptz not null default now(),
  unique (tenant_id, normalized)
);

alter table suppliers add constraint suppliers_tenant_id_uidx unique (tenant_id, id);
alter table supplier_aliases add constraint supplier_aliases_tenant_fk
  foreign key (tenant_id, supplier_id) references suppliers (tenant_id, id) on delete cascade;

create index supplier_aliases_supplier_idx on supplier_aliases (supplier_id);

comment on table supplier_aliases is
  'the printed names that mean one supplier (M9 WP-87): seeded, or learnt on '
  'confirm when a person books a paper under a supplier whose catalog name is '
  'not what the paper printed. Unique per tenant on the normalized form.';

insert into supplier_aliases (tenant_id, supplier_id, alias, normalized)
select distinct on (tenant_id, normalized) tenant_id, supplier_id, alias, normalized
from (
  select s.tenant_id,
         s.id as supplier_id,
         s.name as supplier_name,
         alias,
         trim(regexp_replace(
           regexp_replace(
             regexp_replace(lower(alias), '(?<!\d)\.|\.(?!\d)', ' ', 'g'),
             '[^[:alnum:][:space:].]', ' ', 'g'),
           '\s+', ' ', 'g')) as normalized
  from suppliers s, unnest(s.name_aliases) as alias
) named
where normalized <> ''
order by tenant_id, normalized, supplier_name;

alter table suppliers drop column name_aliases;

alter table supplier_aliases enable row level security;

commit;

-- Verify: the table exists with row security on, the supplier count is the
-- one you wrote down, and every supplier's aliases read back beside its name.
select relname, relrowsecurity
  from pg_class
 where relname = 'supplier_aliases';

select (select count(*) from suppliers) as suppliers_now,
       (select count(*) from supplier_aliases) as aliases_now;

select s.name,
       coalesce(array_agg(a.alias order by a.alias) filter (where a.alias is not null),
                array[]::text[]) as aliases
  from suppliers s
  left join supplier_aliases a on a.supplier_id = s.id
 group by s.id, s.name
 order by s.name;
