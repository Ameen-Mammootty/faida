-- 0020: supplier aliases get a table of their own (plan.md §8 M9, WP-87).
-- Appended per contract C7; the manager squashes periodically (plan.md §4 policy).
--
-- APPLY THIS BEFORE WP-87 MERGES TO MASTER. It drops a column master reads
-- today (suppliers.name_aliases), so this is the one direction that is not
-- reversible by redeploying the previous build: run it, then deploy.
-- Docs/apply_wp87_migration.sql is the paste-ready copy with a pre-flight
-- check, and it starts by telling the founder to take a backup.
--
-- WHY A TABLE. An alias is the answer to "this printed name is that supplier",
-- and until now it lived in a text[] on the supplier. Three things the array
-- could not do, and WP-87 needs all three:
--
-- 1. Refuse a collision. Two suppliers could both hold "Al Madina" and the
--    matcher would book a paper under whichever sorted first - silently, and
--    for ever. `unique (tenant_id, normalized)` makes that state unreachable:
--    an alias belongs to one supplier in a tenant, and the confirm that would
--    have created the second one fails instead, naming the holder.
--
-- 2. Carry the comparable form. Matching compares normalized names
--    (matching.normalize), and an array of printed strings has nowhere to put
--    the normalized one, so the uniqueness above had nothing to key on.
--
-- 3. Say when it was learnt. From this row on, aliases are taught by people
--    confirming papers, so `created_at` is the difference between a seeded
--    alias and one the product learnt on a Tuesday.
--
-- `normalized` is written by Python (matching.normalize) on every insert from
-- here on. The one place SQL computes it is the copy below, which mirrors
-- that function for the aliases already in the array - lowercase, dots that
-- are not decimal points to spaces, punctuation to spaces, whitespace
-- collapsed. It runs once, over names like "GULF FOODS TRADING", and Python
-- owns the value afterwards.

create table supplier_aliases (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references tenants(id),
  supplier_id uuid not null references suppliers(id) on delete cascade,
  -- The name as it was printed on the paper that taught it, kept for the
  -- screen and the audit trail; `normalized` is what matching compares.
  alias       text not null,
  normalized  text not null,
  created_at  timestamptz not null default now(),
  -- One supplier per printed name, per tenant. The whole point of the table.
  unique (tenant_id, normalized)
);

-- The redundant unique the composite foreign key needs (the 0012 shape), so a
-- supplier's alias can never be another tenant's alias.
alter table suppliers add constraint suppliers_tenant_id_uidx unique (tenant_id, id);
alter table supplier_aliases add constraint supplier_aliases_tenant_fk
  foreign key (tenant_id, supplier_id) references suppliers (tenant_id, id) on delete cascade;

create index supplier_aliases_supplier_idx on supplier_aliases (supplier_id);

comment on table supplier_aliases is
  'the printed names that mean one supplier (M9 WP-87): seeded, or learnt on '
  'confirm when a person books a paper under a supplier whose catalog name is '
  'not what the paper printed. Unique per tenant on the normalized form.';

-- The copy. Every alias in the array becomes a row; duplicates within one
-- tenant (two suppliers holding the same normalized name, which the array
-- allowed) keep the first by supplier name and drop the rest, because the new
-- constraint is exactly the rule that says the second one was never safe.
-- Blank aliases are dropped: an empty alias matched nothing anyway.
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
