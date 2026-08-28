-- 0012: M5 raw materials - one shelf per ingredient (plan.md §8 M5).
-- Appended per contract C7; the manager squashes periodically (plan.md §4 policy).

-- The culinary concept, kept separate from the purchasable pack (PRD §17-18).
-- `supplier_items` is unique on (supplier_id, canonical_name), so the same
-- material bought from two suppliers is two rows with two price histories and
-- no shared identity. Nothing in the schema said "milk powder" until now, and
-- a menu item cannot be costed against a row that only one supplier can see.
--
-- base_unit is the DIMENSION's base from extraction/units.py, not a printed
-- unit: gram for mass, millilitre for volume, piece for count. Costs are
-- stored and compared per base unit, so 2 kg and 2000 g land on one shelf and
-- a supplier who only changed their printing never moves a cost.
create table ingredients (
  id         uuid primary key default gen_random_uuid(),
  tenant_id  uuid not null references tenants(id),
  name       text not null,
  base_unit  text not null check (base_unit in ('g', 'ml', 'pc')),
  category   text,
  created_at timestamptz not null default now(),
  unique (tenant_id, name)
);

-- Many purchasable packs -> one raw material. Nullable on purpose: an unmapped
-- item is the normal state of a catalog that self-builds from invoices, and it
-- is exactly what the mapping queue ranks by spend.
--
-- The mapping is a HUMAN decision, so it records who made it and when. A wrong
-- merge silently corrupts the cost of every menu item above it, and unlike a
-- misread invoice there is no photo to check it against - which is why the
-- fuzzy matcher only ever proposes (matching.propose_ingredient) and this
-- column is only ever written by an approval.
alter table supplier_items add column ingredient_id uuid references ingredients(id);
alter table supplier_items add column mapped_at     timestamptz;
alter table supplier_items add column mapped_by     text;
create index supplier_items_ingredient_idx on supplier_items (ingredient_id);

-- Container conversions, stated by a human because nothing else can know them.
-- units.py deliberately refuses to guess what is inside a carton ("6 ctn" and
-- "6 pc" must never compare equal), so an item priced per carton has no cost
-- per kilo until someone says "1 carton = 10 kg chicken".
--
-- Append-only: a correction inserts a new row and the newest wins, so the cost
-- a calculation used stays reconstructible after somebody fixes a conversion
-- (PRD §8 - conversions are versioned).
create table supplier_item_conversions (
  id               bigserial primary key,
  tenant_id        uuid not null references tenants(id),
  supplier_item_id uuid not null references supplier_items(id),
  base_quantity    numeric(14,4) not null check (base_quantity > 0),
  base_unit        text not null check (base_unit in ('g', 'ml', 'pc')),
  note             text,
  actor            text not null,
  created_at       timestamptz not null default now()
);
create index supplier_item_conversions_item_idx
  on supplier_item_conversions (supplier_item_id, created_at desc);

comment on column ingredients.base_unit is
  'dimension base from extraction/units.py: g (mass), ml (volume), pc (count)';
comment on column supplier_item_conversions.base_quantity is
  'how much base_unit one purchase unit of this item contains (1 ctn = 10000 g)';

-- Deny-all RLS, keeping the 0001 invariant: PostgREST serves the public
-- schema, the backend connects as owner/service_role and bypasses it.
alter table ingredients               enable row level security;
alter table supplier_item_conversions enable row level security;
