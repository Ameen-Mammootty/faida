-- 0016: the menu category (plan.md §7.3 WP-60/62, design review D9 2026-08-30).
-- Appended per contract C7; the manager squashes periodically (plan.md §4 policy).
--
-- The design review asked for this inside 0015, but 0015 was applied to the
-- live project hours before the review landed - so it arrives as its own
-- migration rather than an edit that would leave the live schema and this
-- repo quietly disagreeing about what 0015 means.
--
-- The real menu prints its own sections (Tea Corner, Special Gravy, Fried
-- Chicken) and 45 items in one flat ranking bury the story; the menu screen
-- groups by these, each category ranked by margin in AED. Nullable on
-- purpose: a menu without sections is legal, and the screen renders one
-- unlabelled group rather than inventing a category nobody typed.

alter table menu_items add column category text;

comment on column menu_items.category is
  'the menu''s own section for this item (Tea Corner, Special Gravy...), as '
  'the consultant loads it (WP-64''s CSV carries a category column). Null '
  'means the menu prints no sections; the screen groups by this and never '
  'invents one.';
