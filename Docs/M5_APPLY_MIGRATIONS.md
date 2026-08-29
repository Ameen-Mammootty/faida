# Applying M5's migrations to the live project

M5 adds three migrations. The live Supabase project was at `0011`, so all three
have to be applied before the API is deployed - the new code reads
`invoice_lines.cost_per_base_unit` on every invoice detail open and will error
without it. Migrate first, deploy second.

Everything below is generated from `supabase/migrations/`, so it cannot drift
from what the repository actually holds. Each block is pure SQL from its first
character to its last: use the copy button on the block rather than selecting
text, and nothing but SQL reaches your clipboard.

## 1. Check where the database actually is

This project has no migration tracking table - migrations are applied by hand -
so "it is at 0011" is an assumption until you look.

```sql
select
  to_regclass('public.ingredients') is null                        as needs_0012,
  not exists (select 1 from information_schema.columns
              where table_name = 'invoice_lines'
                and column_name = 'cost_per_base_unit')            as needs_0013,
  not exists (select 1 from information_schema.columns
              where table_name = 'supplier_items'
                and column_name = 'pack_size_override')            as needs_0014;
```

**All three must come back `true`.** If any is `false`, part of this is already
applied and running the next step will fail on `create table ingredients`. Stop
and work out which.

## 2. Apply all three

One transaction. Postgres has transactional DDL, so either all three land or
none do - there is no half-migrated state to clean up if something objects.

```sql
begin;

-- ==================  0012_raw_materials.sql  ==================
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

-- ==================  0013_cost_per_base_unit.sql  ==================
-- 0013: cost per base unit (plan.md §8 M5, WP-53).
-- Appended per contract C7; the manager squashes periodically (plan.md §4 policy).
--
-- The first number in this product that no photograph shows. Everything up to
-- here sat beside its image; a cost per gram is two divisions away from the
-- page, and by M6 it is folded four sums deep into a plate margin. It is
-- written per confirmed invoice line, inside the confirm transaction, so every
-- cost drills back to the photo it came from.

-- AED per gram / millilitre / piece, ex-VAT and post-discount (C4).
--
-- The precision is a stated rule rather than "as much as possible". Flour at
-- AED 43.50 per 25 kg is 0.00174 AED per gram; numeric(12,3) - the precision
-- the price columns use, because fils is what a price is quoted in - would
-- store that as 0.002, a 15% error on every plate of biryani, invisible
-- everywhere downstream. Eight decimal places holds a fraction of a fils per
-- gram, which is the smallest thing a real menu costing has to add up.
alter table invoice_lines add column cost_per_base_unit numeric(18,8);

-- Which base unit the figure above is per. extraction/units.py measures in
-- exactly these three; a container is not one of them until a human says what
-- is inside it (WP-55).
alter table invoice_lines add column cost_base_unit text
  check (cost_base_unit in ('g', 'ml', 'pc'));

-- A number with no unit beside it is the shape of bug this milestone exists to
-- prevent, so the database refuses it rather than the application remembering
-- to check (plan.md §2 rule 3: Postgres holds the constraints).
alter table invoice_lines add constraint invoice_lines_cost_unit_ck
  check ((cost_per_base_unit is null) = (cost_base_unit is null));

-- C8's record travelling with the number: what the price was divided by, where
-- that pack size was read, the C9 quality label, and which of the cost's inputs
-- a person asserted rather than a camera saw. Flat keys, like invoices.provenance.
--
-- **No quality here is ever 'verified'.** C4's arithmetic proves qty x
-- unit_price = line_total, so the unit price is corroborated by two other
-- numbers on the page - but pack size appears in no identity at all. A supplier
-- prints 25 kg, the model reads 2.5 kg, every check still passes, and the cost
-- is ten times too high. So the vocabulary stops at 'reliable_with_limitations'
-- (PRD §24), and drops to 'estimated' the moment a human supplied an input.
alter table invoice_lines add column cost_basis jsonb not null default '{}';

comment on column invoice_lines.cost_per_base_unit is
  'AED per gram/millilitre/piece, ex-VAT and post-discount (M5 WP-53). Written '
  'at confirm inside the confirm transaction and frozen; a later pack-size '
  'override costs lines that have none and never rewrites one that has.';
comment on column invoice_lines.cost_basis is
  'how that cost was made: pack, pack_source, quality, and the asserted inputs '
  'it leans on (C8/C9). Empty when the line has no cost.';

-- No new index. The read WP-54 makes - the newest costed line among the packs
-- mapped to a material - walks supplier_items.ingredient_id and then
-- invoice_lines.supplier_item_id, and 0012 added both of those with the
-- queries that justified them. Adding a third ahead of a query that needs it
-- would be the speculation the 0009 policy exists to refuse.

-- ==================  0014_pack_size_override.sql  ==================
-- 0014: what a person says is inside the box (plan.md §8 M5, WP-55).
-- Appended per contract C7; the manager squashes periodically (plan.md §4 policy).
--
-- `extraction/units.py` refuses, by design, to guess what a carton holds: "6
-- ctn" and "6 pc" must never compare equal, because guessing there silently
-- merges two real catalog items and corrupts every cost above them. So the
-- answer has to come from a human, once, and this is where it is kept.

-- **Deliberately a second column, not a correction of `pack_size`.** They are
-- different kinds of fact and only one of them is checkable:
--
--   pack_size           what the first invoice this product ever appeared on
--                       printed. Written once and never revised (TODOS.md), so
--                       it goes stale - which is exactly why costing reads the
--                       pack from the invoice line and never from here.
--   pack_size_override  what a person asserted is inside a container that
--                       printed no amount at all. No photograph shows it, so
--                       any cost built on it reads *estimated* by C9,
--                       automatically and with no extra rule to remember.
--
-- Merging the two would lose that distinction, and the distinction is the only
-- thing keeping a human's sentence from being read back later as something the
-- camera saw.
alter table supplier_items add column pack_size_override text;

comment on column supplier_items.pack_size_override is
  'how much is in one of these, said by a person because the invoice never did '
  '(M5 WP-55). Consulted only when nothing printed on the line can be read as a '
  'pack, so the photo always outranks it. audit_events holds the version '
  'history: one supplier_item.pack_size_set row per change, naming who and when.';

-- No `container_conversions` table, and no version columns here. audit_events
-- already records who said what and when, in the transaction that did it (C8),
-- so a second home for the same fact would be the duplication migration 0010
-- was written to delete. Reading the history back is a query against a table
-- that already has its index (0011), not a schema.
--
-- No index either: the override is read by primary key, as part of costing a
-- line whose supplier item is already in hand.

commit;
```

## 3. Check it took

The same query as step 1. All three should now read `false`.

```sql
select
  to_regclass('public.ingredients') is null                        as needs_0012,
  not exists (select 1 from information_schema.columns
              where table_name = 'invoice_lines'
                and column_name = 'cost_per_base_unit')            as needs_0013,
  not exists (select 1 from information_schema.columns
              where table_name = 'supplier_items'
                and column_name = 'pack_size_override')            as needs_0014;
```

## Then deploy

The API can go to the merged commit once the three flags read `false`, and not
before.

## What each one does

| Migration | What it adds | Why |
|---|---|---|
| `0012_raw_materials` | `ingredients` table, `supplier_items.ingredient_id`, a composite tenant foreign key, two indexes | One shelf per ingredient: the catalog is scoped to a supplier, so the same material bought from two of them is two rows with two price histories. The composite key makes a cross-tenant mapping fail at the write rather than relying on a code path to remember. |
| `0013_cost_per_base_unit` | `invoice_lines.cost_per_base_unit numeric(18,8)`, `cost_base_unit`, `cost_basis jsonb`, one check constraint | What one gram cost, frozen at confirm. Eight decimal places is a stated rule: flour at AED 43.50 per 25 kg is 0.00174 a gram, which the fils precision the price columns use would store as 0.002 - a 15% error nothing downstream could see. |
| `0014_pack_size_override` | `supplier_items.pack_size_override` | What a person says is inside a container the invoice never described. Deliberately a second column rather than a correction of `pack_size`: one is what a page printed, the other is what somebody asserted, and only the second makes a cost read *estimated*. |

All three are additive - `create table`, `add column`, `add constraint`,
`create index`. Nothing is dropped or rewritten, so they are safe to apply
ahead of the code: the currently deployed API does not know these columns
exist and will not touch them.
