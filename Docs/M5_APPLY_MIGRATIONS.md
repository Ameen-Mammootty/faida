# Applying M5's migrations to the live project

M5 adds three migrations. The live Supabase project was at `0011`, so all three
have to be applied before the API is deployed - the new code reads
`invoice_lines.cost_per_base_unit` on every invoice detail open and will error
without it. **Migrate first, deploy second.**

## Do it this way

Open **[`apply_m5_migrations.sql`](apply_m5_migrations.sql)**, select all, copy,
paste into the Supabase SQL editor, run once.

That file is pure SQL from its first byte to its last - there is no prose in it
and nothing to select wrongly. Do not copy the SQL out of this document; copy
the file.

## 1. Check where the database actually is

Run this on its own first. This project has no migration tracking table -
migrations are applied by hand - so "it is at 0011" is an assumption until you
look.

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
applied and the run will fail on `create table ingredients`. Stop and work out
which.

## 2. Apply all three

Select all of `apply_m5_migrations.sql`, paste, run. It opens with `begin;` and
closes with `commit;` - Postgres has transactional DDL, so either all three land
or none do.

## 3. Check it took

The same query as step 1. All three should now read `false`. Only then deploy.

## What each one does

| Migration | What it adds | Why |
|---|---|---|
| `0012_raw_materials` | `ingredients` table, `supplier_items.ingredient_id`, a composite tenant foreign key, two indexes | One shelf per ingredient: the catalog is scoped to a supplier, so the same material bought from two of them is two rows with two price histories. The composite key makes a cross-tenant mapping fail at the write rather than relying on a code path to remember. |
| `0013_cost_per_base_unit` | `invoice_lines.cost_per_base_unit numeric(18,8)`, `cost_base_unit`, `cost_basis jsonb`, one check constraint | What one gram cost, frozen at confirm. Eight decimal places is a stated rule: flour at AED 43.50 per 25 kg is 0.00174 a gram, which the fils precision the price columns use would store as 0.002 - a 15% error nothing downstream could see. |
| `0014_pack_size_override` | `supplier_items.pack_size_override` | What a person says is inside a container the invoice never described. Deliberately a second column rather than a correction of `pack_size`: one is what a page printed, the other is what somebody asserted, and only the second makes a cost read *estimated*. |

All three are additive - `create table`, `add column`, `add constraint`,
`create index`. Nothing is dropped or rewritten, so they are safe to apply ahead
of the code: the currently deployed API does not know these columns exist and
will not touch them.
