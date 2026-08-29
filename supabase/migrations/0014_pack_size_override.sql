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
