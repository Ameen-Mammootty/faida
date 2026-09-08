-- Faida: migration 0021 alone, for a live project already at 0020.
--
-- Adds one optional column to `recipe_components`: `usable_share`, the share
-- of what is bought that reaches the pot. Chicken at 0.85 means the 500 g the
-- recipe puts in the curry cost 588 g off the shelf. The plate cost and M12's
-- theoretical-usage figure divide by the same number, so what a dish costs and
-- what it draws from the storeroom always describe the purchased amount.
--
-- HOW TO USE THIS FILE
--   Open it, select all, copy, paste into the Supabase SQL editor, run once.
--   Every byte of this file is SQL. There is nothing in it to select wrongly.
--
-- EITHER ORDER IS SAFE - BEFORE OR AFTER THE DEPLOY.
--   This migration only adds a column, and it is nullable with no default.
--   The build running today never names it, so nothing on the live site
--   changes the moment you run this: no recipe moves, no plate cost moves, no
--   menu margin moves. WP-119's build reads it and treats null exactly as it
--   treats a recipe with no share today. So run it whenever suits - before the
--   deploy, or after - and nothing is in a broken half-state in between.
--
--   A backup never hurts and Supabase's dashboard has the button, but unlike
--   0020 this migration removes nothing and rewrites no row, so rolling back
--   is `alter table recipe_components drop column usable_share;` and not a
--   restore.
--
-- BEFORE YOU RUN IT
--   Run the check below on its own first. All three columns must come back as
--   shown; anything else means stop and read the note beside it.
--
--   select not exists (select 1 from information_schema.columns
--                      where table_name = 'recipe_components'
--                        and column_name = 'usable_share')      as needs_0021,
--          exists (select 1 from information_schema.tables
--                  where table_name = 'supplier_aliases')       as has_0020,
--          (select count(*) from recipe_components)             as components_now;
--
--   needs_0021      true    (false: already applied; there is nothing to do
--                            and the run below would fail on `add column`)
--   has_0020        true    (false: the project is behind 0020 - run
--                            Docs/apply_wp87_migration.sql first)
--   components_now  a small number, the recipe lines on file. Write it down:
--                   the verify block at the bottom prints it again, and it
--                   must be the same number - this migration writes no rows.
--
--   (A fresh database with no recipe_components table at all needs the full
--   migration set in supabase/migrations/, not this file.)
--
-- WHAT IT CHANGES
--   One new column, empty on every existing row. No row is written, no row is
--   deleted, no column is dropped. Every recipe on file keeps costing exactly
--   what it costs today, because an empty share means "the quantity is already
--   as-purchased" - the convention every one of those recipes was typed under.
--
--   There is deliberately no backfill to 1.0000. A share is a fact about a
--   kitchen that only a person can state, and a guessed 1.0000 written across
--   every row would afterwards be indistinguishable from one somebody meant.

begin;

alter table recipe_components
  add column usable_share numeric(5,4) null
    check (usable_share > 0 and usable_share <= 1);

comment on column recipe_components.usable_share is
  'the share of what is bought that reaches the pot (M12 WP-119, D13): 0.85 '
  'means 500 g in the curry cost 588 g off the shelf. Null means the quantity '
  'is already as-purchased - the M6 convention, and what every recipe written '
  'before this column says. The plate and M12''s usage divide by it alike.';

commit;

-- Verify: the column is there, it is nullable, it holds four decimals, every
-- existing row has it empty, and the component count is the one you wrote
-- down - this migration writes no rows.
select column_name, data_type, numeric_precision, numeric_scale, is_nullable
  from information_schema.columns
 where table_name = 'recipe_components' and column_name = 'usable_share';

select count(*) as components_now,
       count(usable_share) as components_with_a_share
  from recipe_components;

-- Expected, on the demo project and on a pilot's:
--   usable_share | numeric | 5 | 4 | YES
--   components_now = the number you wrote down, components_with_a_share = 0.
--
-- The check constraint is proved by the test suite, not by a query you have to
-- run here: `\d recipe_components` in psql lists it as
-- recipe_components_usable_share_check, and any write outside (0, 1] is
-- refused by Postgres whatever the API forgot.
