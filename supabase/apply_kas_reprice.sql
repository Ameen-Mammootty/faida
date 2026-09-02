-- Adopt the repriced KAS papers on a REAL stage (founder's call 2026-09-01).
--
-- The four preparation papers confirmed on the live project carry the FIRST
-- draft's prices - boneless chicken at AED 3.45/kg - and the menu screen
-- answers with chicken curries at 89% margin. `build_prompts.py` now holds
-- researched UAE wholesale prices (`price-research-2026-09.md`), so the
-- preparation has to be redone against the new papers. This file clears the
-- old preparation purchases so they can be re-forwarded. One run:
--
--   psql "$DATABASE_URL" -f supabase/demo_reset_loop.sql      -- first: rehearsal residue
--   psql "$DATABASE_URL" -f supabase/apply_kas_reprice.sql    -- then: this
--
-- then re-forward and confirm KAS-1..4 from the phone. Running it twice, or
-- on a stage that never held the old papers, is a no-op.
--
-- RUN THE LOOP RESET FIRST. Baselines here are recomputed from the price
-- observations that survive, so KAS-5 (or a prop) still sitting confirmed
-- would be re-armed as though it were preparation evidence. `demo_reset_loop`
-- is scoped to the props' numbers and is idempotent, so running it first
-- always costs nothing and removes exactly that risk.
--
-- THE SCOPE IS THE FOUR PREPARATION PAPERS, by their printed invoice numbers:
--
--   KAS-1  AAF-2026-3318   Al Aweer Fresh Produce LLC
--   KAS-2  DSF-26-08-441   Deira Spice & Dry Foods Trading LLC
--   KAS-3  AMT-26-1203     Al Madina Trading Co.
--   KAS-4  GFT-2026-0908   Gulf Foods Trading L.L.C.
--
-- WHAT THIS FILE MUST NOT DESTROY, and does not touch: `menu_items`,
-- `recipes`, `recipe_components`, `ingredients`, and above all
-- `supplier_items` - whose `ingredient_id` holds the 79 mappings a human
-- approved one keystroke at a time. Deleting the catalog rows would be the
-- easy way to write this file and would throw that work away; the packs are
-- kept and only their price history is cleared, so the re-forwarded papers
-- snap straight back onto the same mapped rows.
--
-- WHY THE RE-FORWARD RE-SNAPS CLEANLY, since the papers changed. Five packs
-- were corrected to shapes UAE suppliers actually sell (garlic 5 kg box ->
-- 1 kg tub, curry leaves 500 g -> 100 g, toor dal 25 kg -> 15 kg, soy 5 l ->
-- 4 l, instant coffee 1 kg tin -> 200 g jar). `snap_item`'s pack veto only
-- fires when BOTH sides name a pack size, and these papers print the bare
-- commodity word with the pack in its own column - so the line's raw_name
-- carries no pack token and the veto never applies. Verified against
-- `snap_item` before this file was written: 81 of 81 lines re-snap to their
-- existing mapped row. The two updates below are the tidy-up that snapping
-- itself does not do, because a snapped line never rewrites its catalog row.

begin;

create temporary table _kas_invoices on commit drop as
  select id, document_id
    from invoices
   where tenant_id = 'd0000000-0000-0000-0000-000000000001'
     and invoice_no in ('AAF-2026-3318', 'DSF-26-08-441', 'AMT-26-1203', 'GFT-2026-0908');

create temporary table _kas_docs on commit drop as
  select distinct document_id as id from _kas_invoices where document_id is not null;

-- Human decisions recorded against these invoices and their documents. The
-- mapping approvals on `/materials` have supplier_item subject ids and stay,
-- which is the point - the audit trail of who mapped what survives the
-- repricing, because those decisions are still true.
delete from audit_events
 where tenant_id = 'd0000000-0000-0000-0000-000000000001'
   and (subject_id in (select id from _kas_invoices)
        or subject_id in (select id from _kas_docs));

delete from jobs
 where payload->>'document_id' in (select id::text from _kas_docs)
    or payload->>'message_id' in (
      select wa_message_id from documents
       where id in (select id from _kas_docs) and wa_message_id is not null);

delete from wa_messages
 where message_id in (
   select wa_message_id from documents
    where id in (select id from _kas_docs) and wa_message_id is not null);

delete from extraction_runs
 where document_id in (select id from _kas_docs);

-- Exactly the price observations these four confirms appended.
delete from supplier_item_prices
 where invoice_id in (select id from _kas_invoices);

delete from invoices where id in (select id from _kas_invoices);  -- lines cascade

delete from documents where id in (select id from _kas_docs);

-- ---------------------------------------------------------------------------
-- Two corrections a re-forward cannot make for itself. `record_confirmed_prices`
-- writes `pack_size` and `canonical_name` only when it CREATES a catalog row;
-- a line that snaps to an existing row leaves both alone (db.py, the insert is
-- guarded by `if item_id is None`). So without these the catalog would keep
-- describing packs the new papers no longer print, and a consultant on
-- `/materials` would read a pack size that disagrees with the invoice photo
-- one click away. Cosmetic for the arithmetic - costs come from the invoice
-- line's own pack - and exactly the kind of small lie this product exists not
-- to tell.
-- ---------------------------------------------------------------------------

update supplier_items s
   set pack_size = v.pack
  from (values
          ('GARLIC PEELED',   '1 kg'),
          ('CURRY LEAVES',    '100 g'),
          ('TOOR DAL',        '15 kg'),
          ('LIGHT SOY SAUCE', '4 l'),
          ('INSTANT COFFEE',  '200 g')
       ) as v(name, pack)
 where s.tenant_id = 'd0000000-0000-0000-0000-000000000001'
   and upper(s.canonical_name) = v.name;

-- The identity fix, not a price fix: every UAE source that sells "Habbat Al
-- Hamra" sells a seed (garden cress / aliv / asario), not a tea blend, so the
-- paper now names the seed. The line still snaps to this row - "SEEDS" against
-- "BLEND" clears SNAP_THRESHOLD comfortably - so the mapping survives either
-- way; this only stops the catalog from keeping a name the paper contradicts.
update supplier_items
   set canonical_name = 'HABBAT AL HAMRA SEEDS'
 where tenant_id = 'd0000000-0000-0000-0000-000000000001'
   and upper(canonical_name) = 'HABBAT AL HAMRA BLEND';

-- ---------------------------------------------------------------------------
-- Re-arm, identical in shape to `demo_reset_loop.sql`: last_price/prev_price
-- mirror the newest two surviving history rows, and a pack with no
-- observations left holds no baseline. After this the KAS packs have no price
-- at all, which is correct and temporary - the re-forwarded papers put the
-- researched ones back, and until they do `/menu` honestly reads incomplete
-- rather than showing a stale margin.
-- ---------------------------------------------------------------------------

update supplier_items s
   set last_price = h.newest_price,
       prev_price = h.second_price,
       last_price_at = h.newest_at
  from (
    select p.supplier_item_id,
           (array_agg(p.price order by p.observed_at desc))[1] as newest_price,
           (array_agg(p.price order by p.observed_at desc))[2] as second_price,
           max(p.observed_at) as newest_at
      from supplier_item_prices p
      join supplier_items si on si.id = p.supplier_item_id
     where si.tenant_id = 'd0000000-0000-0000-0000-000000000001'
     group by p.supplier_item_id
  ) h
 where h.supplier_item_id = s.id;

update supplier_items s
   set last_price = null, prev_price = null, last_price_at = null
 where s.tenant_id = 'd0000000-0000-0000-0000-000000000001'
   and not exists (select 1 from supplier_item_prices p where p.supplier_item_id = s.id);

commit;
