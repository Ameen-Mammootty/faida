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
