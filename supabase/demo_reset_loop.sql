-- The between-rehearsals reset for a REAL stage (M6 demo gate).
--
-- Once F7's real menu is loaded through /menu/load, `demo_seed.sql` must never
-- run against that database again: its reset deletes every menu, ingredient
-- and mapping row for the demo chain and re-stages the five practice items.
-- This file is the reset the runbook's §C points at instead. One run:
--
--   psql "$DATABASE_URL" -f supabase/demo_reset_loop.sql
--
-- clears what a rehearsal created and re-arms the price alerts; running it
-- twice, or on a clean stage, is a no-op.
--
-- THE SCOPE IS THE PROPS. A rehearsal is defined by the papers it forwards,
-- and every prop prints a fixed invoice number, so rehearsal residue is any
-- demo-chain invoice carrying one of those numbers - however many times it
-- was forwarded, confirmed or held:
--
--   act one's papers      DEMO-1  GFT-2026-0834   (Docs/demo-invoices/)
--                         DEMO-2  AMT-26-1187
--                         DEMO-3  GFT-2026-0871
--   the real stage's      KAS-5   AMT-26-1274     (Docs/demo-invoices/koukh-al-shay/)
--   on-stage paper
--
-- KAS-1..4 print different numbers ON PURPOSE: they are preparation evidence
-- - the purchases the real menu is costed from - and this file can never
-- touch them, even though KAS-3/KAS-4 name the same suppliers the props do.
-- If a prop is ever regenerated with a new number, update the list below in
-- the same commit (the papers' README says the same).
--
-- What this file never touches: menu_items, recipes, recipe_components,
-- ingredients, supplier_items.ingredient_id (mappings), branches (the founder
-- phone), tenants, suppliers, any invoice that is not one of the props.
-- What it deliberately leaves behind: text messages and outbound replies
-- (inert log rows); documents with no invoice (a meme decline blocks nothing,
-- and a failed real paper must keep its retry path); any supplier_item a
-- botched rehearsal minted (the props snap to existing packs, so a stray
-- mint is an accident - remove it by hand, or run demo_seed.sql if this is
-- the practice stage).

begin;

create temporary table _reset_invoices on commit drop as
  select id, document_id
    from invoices
   where tenant_id = 'd0000000-0000-0000-0000-000000000001'
     and invoice_no in ('GFT-2026-0834', 'AMT-26-1187', 'GFT-2026-0871', 'AMT-26-1274');

create temporary table _reset_docs on commit drop as
  select distinct document_id as id from _reset_invoices where document_id is not null;

-- Human decisions recorded against the props' rows; audit rows for real
-- invoices and menu work have other subject ids and stay.
delete from audit_events
 where tenant_id = 'd0000000-0000-0000-0000-000000000001'
   and (subject_id in (select id from _reset_invoices)
        or subject_id in (select id from _reset_docs));

delete from jobs
 where payload->>'document_id' in (select id::text from _reset_docs)
    or payload->>'message_id' in (
      select wa_message_id from documents
       where id in (select id from _reset_docs) and wa_message_id is not null);

-- The forwarded photos' inbound messages (texts and outbound replies stay).
delete from wa_messages
 where message_id in (
   select wa_message_id from documents
    where id in (select id from _reset_docs) and wa_message_id is not null);

delete from extraction_runs
 where document_id in (select id from _reset_docs);

-- Exactly the price observations the props' confirms appended - each carries
-- its invoice id. Staged history and the KAS-1..4 observations have other
-- (or no) invoice ids and survive.
delete from supplier_item_prices
 where invoice_id in (select id from _reset_invoices);

delete from invoices where id in (select id from _reset_invoices);  -- lines cascade

delete from documents where id in (select id from _reset_docs);

-- ---------------------------------------------------------------------------
-- Re-arm: last_price / prev_price mirror the newest two history rows (the
-- invariant demo_seed.sql pins and record_confirmed_prices maintains), so
-- with the props' observations gone the baselines are recomputed from what
-- survives - staged packs return to their staged numbers, the real packs to
-- their newest preparation purchase, and the next rehearsal's alerts fire.
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

-- A pack with no observations left never had a real purchase recorded (the
-- confirm always appends history when it moves a baseline), so it holds no
-- baseline either.
update supplier_items s
   set last_price = null, prev_price = null, last_price_at = null
 where s.tenant_id = 'd0000000-0000-0000-0000-000000000001'
   and not exists (select 1 from supplier_item_prices p where p.supplier_item_id = s.id);

commit;
