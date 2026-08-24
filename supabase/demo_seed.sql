-- WP-40: the M4 demo seed (plan.md §6 M4).
--
-- One chain tenant, 3 branches, 2 suppliers, 6 catalog items, 3 weeks of price
-- history staged so the curated demo invoices fire price alerts on stage.
--
-- The demo chain is DISTINCT from seed.sql's demo tenant on purpose: every
-- delete below is scoped to this file's fixed tenant UUID (or to phones owned
-- by its branches), so a reset can never touch another tenant's rows - and
-- seed.sql's tenant doubles as the canary proving that (tests/test_demo_seed.py).
--
-- IDEMPOTENT RESET: this file is also the between-rehearsals reset. It first
-- deletes everything a rehearsal created for the demo chain (documents,
-- invoices, lines, runs, messages, jobs, confirm-created suppliers/items, and
-- all price history), then re-inserts the exact staged state. One run:
--
--   psql "$DATABASE_URL" -f supabase/demo_seed.sql
--
-- restores the stage completely; running it twice is a no-op. The only rows it
-- deliberately preserves across runs are the branch wa_phone_e164 values (the
-- founder's one manual UPDATE, documented at the bottom). Storage objects from
-- rehearsals stay in the bucket - originals are immutable evidence and nothing
-- references them once their documents rows are gone.
--
-- STAGED PRICES vs THE CURATED DEMO INVOICES (plan.md §6 M4 script):
-- the alert fires when |invoice price - last_price| >= AED 0.25 AND >= 5% of
-- last_price (extraction/constants.py). Intended on-stage numbers:
--
--   item (canonical_name)      staged last  demo invoice  expected alert line
--   Milk Powder 2.5kg          50.50        54.50         "Milk Powder 2.5kg up AED 4.00 (50.50 to 54.50) since your last purchase."
--   Karak Tea Dust             22.00        18.75         "Karak Tea Dust down AED 3.25 (22.00 to 18.75) since your last purchase."
--   Sugar 50kg                 115.00       115.00        none (stable line - proves not everything alerts)
--   Cardamom Powder 500g       24.00        24.00         none
--   Evaporated Milk 400ml      90.00        96.00         "Evaporated Milk 400ml up AED 6.00 (90.00 to 96.00) since your last purchase."  (backup invoice 2)
--   Chakki Atta Flour 25kg     43.50        43.50         none
--
-- Demo invoice 1 (Gulf Foods Trading LLC, the on-stage one) carries the milk
-- powder and karak tea dust lines at those prices, totalling AED 745.76 - the
-- same shape the M2 gate test pins. If a curated photo's real price differs,
-- adjust the staged last_price here so the delta stays >= both thresholds.
--
-- IMPORTANT: confirming an invoice moves last_price to the invoice price, so
-- after any rehearsal in which you replied OK the alert will NOT fire again
-- until this file is re-run.

begin;

-- ---------------------------------------------------------------------------
-- Reset: delete rehearsal residue for the demo chain, most-dependent first.
-- Every statement is scoped through the fixed tenant UUID or the demo chain's
-- branch phones; no other tenant's rows are reachable from these predicates.
-- ---------------------------------------------------------------------------

-- Jobs referencing demo-chain documents (extract_document payloads).
delete from jobs
 where payload->>'document_id' in (
   select id::text from documents
    where tenant_id = 'd0000000-0000-0000-0000-000000000001');

-- Jobs referencing demo-chain inbound messages (process_wa_message payloads):
-- media messages trace through documents, texts (OK / corrections) through the
-- demo branches' phones.
delete from jobs
 where payload->>'message_id' in (
   select wa_message_id from documents
    where tenant_id = 'd0000000-0000-0000-0000-000000000001'
      and wa_message_id is not null
   union
   select message_id from wa_messages
    where from_phone in (
      select wa_phone_e164 from branches
       where tenant_id = 'd0000000-0000-0000-0000-000000000001'
         and wa_phone_e164 is not null));

-- WhatsApp messages: inbound media traced through demo documents, plus every
-- message from or to a demo-branch phone (inbound texts, outbound replies).
delete from wa_messages
 where message_id in (
   select wa_message_id from documents
    where tenant_id = 'd0000000-0000-0000-0000-000000000001'
      and wa_message_id is not null)
    or from_phone in (
      select wa_phone_e164 from branches
       where tenant_id = 'd0000000-0000-0000-0000-000000000001'
         and wa_phone_e164 is not null)
    or to_phone in (
      select wa_phone_e164 from branches
       where tenant_id = 'd0000000-0000-0000-0000-000000000001'
         and wa_phone_e164 is not null);

delete from extraction_runs
 where document_id in (
   select id from documents
    where tenant_id = 'd0000000-0000-0000-0000-000000000001');

delete from invoice_lines
 where invoice_id in (
   select id from invoices
    where tenant_id = 'd0000000-0000-0000-0000-000000000001');

-- All price history for demo-chain items (staged rows are re-inserted below,
-- confirm-appended rows must go).
delete from supplier_item_prices
 where supplier_item_id in (
   select id from supplier_items
    where tenant_id = 'd0000000-0000-0000-0000-000000000001');

delete from invoices
 where tenant_id = 'd0000000-0000-0000-0000-000000000001';

delete from documents
 where tenant_id = 'd0000000-0000-0000-0000-000000000001';

-- Catalog rows, including any supplier_items / suppliers that confirms
-- self-built during rehearsals; the staged six come back below.
delete from supplier_items
 where tenant_id = 'd0000000-0000-0000-0000-000000000001';

delete from suppliers
 where tenant_id = 'd0000000-0000-0000-0000-000000000001';

-- ---------------------------------------------------------------------------
-- Staged state: the chain, its branches, suppliers, catalog, and history.
-- Tenant and branches are UPSERTED (never deleted) so branch wa_phone_e164 -
-- the founder's one manual step - survives every reset.
-- ---------------------------------------------------------------------------

insert into tenants (id, name, currency)
values ('d0000000-0000-0000-0000-000000000001', 'Karak Al Khaleej Cafeterias', 'AED')
on conflict (id) do update set name = excluded.name, currency = excluded.currency;

insert into branches (id, tenant_id, name, wa_phone_e164, timezone)
values
  ('d0000000-0000-0000-0000-000000000011', 'd0000000-0000-0000-0000-000000000001',
   'Al Qusais Branch', null, 'Asia/Dubai'),
  ('d0000000-0000-0000-0000-000000000012', 'd0000000-0000-0000-0000-000000000001',
   'Al Nahda Branch', null, 'Asia/Dubai'),
  ('d0000000-0000-0000-0000-000000000013', 'd0000000-0000-0000-0000-000000000001',
   'Rolla Branch', null, 'Asia/Dubai')
on conflict (id) do update set name = excluded.name, timezone = excluded.timezone;
-- wa_phone_e164 intentionally not updated on conflict: see the founder step below.

insert into suppliers (id, tenant_id, name, name_aliases)
values
  ('d0000000-0000-0000-0000-000000000021', 'd0000000-0000-0000-0000-000000000001',
   'Gulf Foods Trading L.L.C.',
   array['Gulf Foods', 'Gulf Foods Trading LLC', 'GULF FOODS TRADING']),
  ('d0000000-0000-0000-0000-000000000022', 'd0000000-0000-0000-0000-000000000001',
   'Al Madina Trading Co.',
   array['Al Madeena Trading', 'AL MADINA TRADING CO LLC', 'Al Madina Trading']);

-- last_price / prev_price mirror the last two history rows below;
-- last_price_at matches the newest observation (a week ago).
insert into supplier_items
  (id, tenant_id, supplier_id, canonical_name, unit, pack_size,
   last_price, prev_price, last_price_at)
values
  ('d0000000-0000-0000-0000-000000000101', 'd0000000-0000-0000-0000-000000000001',
   'd0000000-0000-0000-0000-000000000021',
   'Milk Powder 2.5kg', 'sack', '2.5kg', 50.50, 49.75, now() - interval '7 days'),
  ('d0000000-0000-0000-0000-000000000102', 'd0000000-0000-0000-0000-000000000001',
   'd0000000-0000-0000-0000-000000000021',
   'Karak Tea Dust', 'bag', null, 22.00, 21.50, now() - interval '7 days'),
  ('d0000000-0000-0000-0000-000000000103', 'd0000000-0000-0000-0000-000000000001',
   'd0000000-0000-0000-0000-000000000021',
   'Sugar 50kg', 'sack', '50kg', 115.00, 113.75, now() - interval '7 days'),
  ('d0000000-0000-0000-0000-000000000104', 'd0000000-0000-0000-0000-000000000001',
   'd0000000-0000-0000-0000-000000000021',
   'Cardamom Powder 500g', 'tin', '500g', 24.00, 23.50, now() - interval '7 days'),
  ('d0000000-0000-0000-0000-000000000105', 'd0000000-0000-0000-0000-000000000001',
   'd0000000-0000-0000-0000-000000000022',
   'Evaporated Milk 400ml', 'carton', '48x400ml', 90.00, 88.00, now() - interval '7 days'),
  ('d0000000-0000-0000-0000-000000000106', 'd0000000-0000-0000-0000-000000000001',
   'd0000000-0000-0000-0000-000000000022',
   'Chakki Atta Flour 25kg', 'sack', '25kg', 43.50, 42.75, now() - interval '7 days');

-- Three weeks of history per item (the review screen's sparkline), oldest
-- first: gentle weekly drift ending at last_price, so the on-stage confirm
-- appends a visible jump.
-- tenant_id is read from the catalog item, the same way every insert path in
-- the API derives it: the observation belongs to the row it prices.
insert into supplier_item_prices (tenant_id, supplier_item_id, price, observed_at)
select i.tenant_id, h.item_id, h.price, h.observed_at
from (values
  ('d0000000-0000-0000-0000-000000000101'::uuid,  49.25, now() - interval '21 days'),
  ('d0000000-0000-0000-0000-000000000101',  49.75, now() - interval '14 days'),
  ('d0000000-0000-0000-0000-000000000101',  50.50, now() - interval '7 days'),
  ('d0000000-0000-0000-0000-000000000102',  21.00, now() - interval '21 days'),
  ('d0000000-0000-0000-0000-000000000102',  21.50, now() - interval '14 days'),
  ('d0000000-0000-0000-0000-000000000102',  22.00, now() - interval '7 days'),
  ('d0000000-0000-0000-0000-000000000103', 112.50, now() - interval '21 days'),
  ('d0000000-0000-0000-0000-000000000103', 113.75, now() - interval '14 days'),
  ('d0000000-0000-0000-0000-000000000103', 115.00, now() - interval '7 days'),
  ('d0000000-0000-0000-0000-000000000104',  23.25, now() - interval '21 days'),
  ('d0000000-0000-0000-0000-000000000104',  23.50, now() - interval '14 days'),
  ('d0000000-0000-0000-0000-000000000104',  24.00, now() - interval '7 days'),
  ('d0000000-0000-0000-0000-000000000105',  87.00, now() - interval '21 days'),
  ('d0000000-0000-0000-0000-000000000105',  88.00, now() - interval '14 days'),
  ('d0000000-0000-0000-0000-000000000105',  90.00, now() - interval '7 days'),
  ('d0000000-0000-0000-0000-000000000106',  42.00, now() - interval '21 days'),
  ('d0000000-0000-0000-0000-000000000106',  42.75, now() - interval '14 days'),
  ('d0000000-0000-0000-0000-000000000106',  43.50, now() - interval '7 days')
) as h(item_id, price, observed_at)
join supplier_items i on i.id = h.item_id;

commit;

-- ---------------------------------------------------------------------------
-- Founder step: point the demo handset at the chain's flagship branch, once
-- per environment, AFTER applying this file. The webhook resolves sender ->
-- branch through wa_phone_e164 (digits only, no '+'), the column is UNIQUE,
-- and the reset above never touches it - so this survives every re-run.
-- Replace 9715XXXXXXXX with the founder's demo phone:
--
--   update branches set wa_phone_e164 = null  where wa_phone_e164 = '9715XXXXXXXX';
--   update branches set wa_phone_e164 = '9715XXXXXXXX'
--    where id = 'd0000000-0000-0000-0000-000000000011';
-- ---------------------------------------------------------------------------
