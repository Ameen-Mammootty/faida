-- Faida M6: migration 0016 alone, for a live project already at 0015.
--
-- 0015 was applied to the live project on 2026-08-30, hours before the design
-- review added the menu category column - so the catch-up ships as its own
-- paste file rather than an edit to a migration the live database already ran.
--
-- HOW TO USE THIS FILE
--   Open it, select all, copy, paste into the Supabase SQL editor, run once.
--   Every byte of this file is SQL. There is nothing in it to select wrongly.
--
-- BEFORE YOU RUN IT
--   Run the check below on its own first. It must come back true; false means
--   0016 is already applied and the run will fail on `add column category`.
--
--   select not exists (select 1 from information_schema.columns
--                      where table_name = 'menu_items'
--                        and column_name = 'category') as needs_0016;
--
--   (A fresh database with no menu_items table at all needs
--   Docs/apply_m6_migrations.sql instead, which now carries 0015 and 0016.)
--
-- AFTERWARDS
--   Run the check again; it should read false. Then deploy - migrate first,
--   deploy second.

begin;

alter table menu_items add column category text;

comment on column menu_items.category is
  'the menu''s own section for this item (Tea Corner, Special Gravy...), as '
  'the consultant loads it (WP-64''s CSV carries a category column). Null '
  'means the menu prints no sections; the screen groups by this and never '
  'invents one.';

commit;
