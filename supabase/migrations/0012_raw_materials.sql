-- 0012: raw materials - one shelf per ingredient (plan.md §8 M5, WP-52).
-- Appended per contract C7; the manager squashes periodically (plan.md §4 policy).
--
-- The catalog `supplier_items` fills itself from invoices, but it is scoped to
-- one supplier: Al Madina's milk powder and Gulf Foods' milk powder are two
-- rows with two price histories, and nothing represents "milk powder" as a
-- thing you cook with. This adds that, and the link between the two.
--
-- The distinction is PRD §17-18's and it is not cosmetic. An *ingredient* is
-- the culinary concept (milk powder). A *supplier item* is the purchasable
-- pack (Gulf Foods' 2.5 kg sack). One ingredient has many packs, across many
-- suppliers and many sizes, and the whole point of M5 is that they end up
-- costing one number per kilo.

create table ingredients (
  id         uuid primary key default gen_random_uuid(),
  tenant_id  uuid not null references tenants(id),
  name       text not null,
  -- The dimension every pack of this material reduces to. Grams, millilitres
  -- or pieces: the base units extraction/units.py measures in. A material has
  -- exactly one, so a millilitre pack can never be mapped onto a gram
  -- material - that is a wrong merge, and a wrong merge corrupts the cost of
  -- every menu item above it with no photo to check against.
  base_unit  text not null check (base_unit in ('g', 'ml', 'pc')),
  created_at timestamptz not null default now(),
  unique (tenant_id, name)
);

-- Redundant for uniqueness (id is already the primary key) and required as the
-- target of the composite foreign key below: Postgres will only reference a
-- unique constraint over exactly the referenced columns.
alter table ingredients add constraint ingredients_tenant_id_uidx unique (tenant_id, id);

-- Many packs from many suppliers -> one raw material. Null until a human
-- approves the merge; the fuzzy matcher only ever proposes (plan.md §8 M5).
alter table supplier_items add column ingredient_id uuid;

-- Tenancy enforced by the database, not by a code path remembering to check.
-- A plain reference to ingredients(id) would happily let Tenant A's pack point
-- at Tenant B's material: RLS is deferred to M7 and the demo API holds one
-- shared token, so nothing else would have caught it. Matching on
-- (tenant_id, ingredient_id) makes the cross-tenant write fail at the write.
-- Null ingredient_id satisfies it (MATCH SIMPLE), which is the unmapped state.
alter table supplier_items add constraint supplier_items_ingredient_fk
  foreign key (tenant_id, ingredient_id) references ingredients (tenant_id, id);

comment on column supplier_items.ingredient_id is
  'the raw material this pack is, once a human approved it (M5 WP-52). Null '
  'means unmapped; the matcher proposes, it never decides.';

-- The two reads M5 adds, each shipping with the query that justifies it
-- (the 0009 policy: indexes arrive with their policies, not ahead of them).
-- "Which packs belong to this material" walks the new column:
create index supplier_items_ingredient_idx on supplier_items (ingredient_id);
-- "Unmapped packs, most money first" groups invoice lines by their pack, and
-- invoice_lines had no index on that foreign key at all:
create index invoice_lines_supplier_item_idx on invoice_lines (supplier_item_id);

-- Deny-all, per the 0001 convention: Supabase serves `public` over PostgREST,
-- so a table without this is readable with the anon key. The backend uses the
-- service role and is unaffected; M7 owns real tenant policies.
alter table ingredients enable row level security;
