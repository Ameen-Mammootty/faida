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
--
-- ACT TWO (WP-66, M6): the same stage carries a small menu, so the demo's
-- second half - materials -> menu margins -> "push this, fix that" - can be
-- rehearsed without waiting on the real menu. **The seed rehearses; the real
-- menu gates**: M6's done-when ("one real menu loads in under a day") and the
-- demo gate both close on F7's menu, never on these five items.
--
-- Two confirmed purchase invoices are staged, three weeks and one week back,
-- carrying the same prices the sparkline history shows. They exist because
-- everything above the invoice line is *derived*: a plate cost reads the
-- newest costed invoice line for each material, so with no invoices the menu
-- is honestly incomplete and act two has nothing to show. Two of them, not
-- one, so the money moment (WP-63) has a "previous" to compare against before
-- the on-stage confirm makes a third.
--
--   material            21 days ago   7 days ago   on-stage demo invoice
--   Milk Powder 2.5kg        49.25        50.50    54.50  -> the plates drop
--   Karak Tea Dust           21.00        22.00    18.75  -> the plates rise
--   Sugar 50kg              112.50       115.00    115.00
--   Cardamom Powder 500g     23.25        24.00     24.00
--   Evaporated Milk 400ml    87.00        90.00    (backup invoice 2)
--
-- Chakki Atta Flour is deliberately left **unmapped**, so the materials screen
-- opens with one real row in its queue and the Paratha reads *incomplete*
-- naming exactly what it is waiting for. A menu where everything already works
-- shows none of the machinery that makes the numbers trustworthy.
--
-- Every cost per base unit below is hand-computed and its division is written
-- beside it, the same rule the mock fixtures follow: money is never computed
-- by the thing being demonstrated. `tests/test_demo_seed.py` re-derives each
-- one through `costing.py` and the plates through `plates.py`, so a seed that
-- drifted from the shipped arithmetic fails CI rather than the demo.

begin;

-- ---------------------------------------------------------------------------
-- Reset: delete rehearsal residue for the demo chain, most-dependent first.
-- Every statement is scoped through the fixed tenant UUID or the demo chain's
-- branch phones; no other tenant's rows are reachable from these predicates.
-- ---------------------------------------------------------------------------

-- The menu (M6). Recipe components reference ingredients, which supplier
-- items also reference, so the menu unwinds first and ingredients go last,
-- after the catalog rows that point at them.
delete from recipe_components
 where tenant_id = 'd0000000-0000-0000-0000-000000000001';

delete from recipes
 where tenant_id = 'd0000000-0000-0000-0000-000000000001';

delete from menu_items
 where tenant_id = 'd0000000-0000-0000-0000-000000000001';

-- Every human decision a rehearsal recorded - approvals, menu writes,
-- confirmations. The staged state has no history, so a reset must not leave
-- yesterday's rehearsal in the audit trail.
delete from audit_events
 where tenant_id = 'd0000000-0000-0000-0000-000000000001';

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

-- Last, because supplier_items and recipe_components both point here.
delete from ingredients
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

-- ---------------------------------------------------------------------------
-- ACT TWO (WP-66): the materials, the purchase evidence behind their prices,
-- and a small menu costed off it.
-- ---------------------------------------------------------------------------

-- The shelves. One per material, the unit each is measured in - and Atta Flour
-- exists with no pack pointed at it, which is what makes the Paratha read
-- *incomplete* naming its missing piece rather than reading cheap.
insert into ingredients (id, tenant_id, name, base_unit)
values
  ('d0000000-0000-0000-0000-000000000201', 'd0000000-0000-0000-0000-000000000001',
   'Milk Powder', 'g'),
  ('d0000000-0000-0000-0000-000000000202', 'd0000000-0000-0000-0000-000000000001',
   'Karak Tea Dust', 'g'),
  ('d0000000-0000-0000-0000-000000000203', 'd0000000-0000-0000-0000-000000000001',
   'White Sugar', 'g'),
  ('d0000000-0000-0000-0000-000000000204', 'd0000000-0000-0000-0000-000000000001',
   'Cardamom Powder', 'g'),
  ('d0000000-0000-0000-0000-000000000205', 'd0000000-0000-0000-0000-000000000001',
   'Evaporated Milk', 'ml'),
  ('d0000000-0000-0000-0000-000000000206', 'd0000000-0000-0000-0000-000000000001',
   'Atta Flour', 'g');

-- Five of the six packs are mapped. Chakki Atta Flour is left alone on
-- purpose: it is the one row waiting in the materials queue on stage.
update supplier_items set ingredient_id = 'd0000000-0000-0000-0000-000000000201'
 where id = 'd0000000-0000-0000-0000-000000000101';
update supplier_items set ingredient_id = 'd0000000-0000-0000-0000-000000000202'
 where id = 'd0000000-0000-0000-0000-000000000102';
update supplier_items set ingredient_id = 'd0000000-0000-0000-0000-000000000203'
 where id = 'd0000000-0000-0000-0000-000000000103';
update supplier_items set ingredient_id = 'd0000000-0000-0000-0000-000000000204'
 where id = 'd0000000-0000-0000-0000-000000000104';
update supplier_items set ingredient_id = 'd0000000-0000-0000-0000-000000000205'
 where id = 'd0000000-0000-0000-0000-000000000105';

-- The purchases those prices came from. Every plate cost on the menu screen
-- traces to one of these lines and one click reaches its invoice, which is the
-- property act two demonstrates - there is no stored cost anywhere.
--
-- Tax-exclusive, so the printed unit price is already net and each line's cost
-- per base unit is just that price divided by what is in the pack. Quantities
-- are chosen so 5% VAT lands exactly on the fils.
insert into documents (id, tenant_id, branch_id, source, status, mime, sha256)
values
  ('d0000000-0000-0000-0000-000000000301', 'd0000000-0000-0000-0000-000000000001',
   'd0000000-0000-0000-0000-000000000011', 'manual', 'extracted', null, null),
  ('d0000000-0000-0000-0000-000000000302', 'd0000000-0000-0000-0000-000000000001',
   'd0000000-0000-0000-0000-000000000011', 'manual', 'extracted', null, null),
  ('d0000000-0000-0000-0000-000000000303', 'd0000000-0000-0000-0000-000000000001',
   'd0000000-0000-0000-0000-000000000011', 'manual', 'extracted', null, null),
  ('d0000000-0000-0000-0000-000000000304', 'd0000000-0000-0000-0000-000000000001',
   'd0000000-0000-0000-0000-000000000011', 'manual', 'extracted', null, null);

insert into invoices (id, tenant_id, branch_id, document_id, supplier_id, supplier_name,
                      invoice_no, invoice_date, currency, subtotal, tax, total,
                      tax_treatment, vat_rate, payment_kind, status, confirmed_at)
values
  -- Three weeks ago: the baseline the money moment compares against.
  ('d0000000-0000-0000-0000-000000000311', 'd0000000-0000-0000-0000-000000000001',
   'd0000000-0000-0000-0000-000000000011', 'd0000000-0000-0000-0000-000000000301',
   'd0000000-0000-0000-0000-000000000021', 'Gulf Foods Trading L.L.C.',
   'GF-20418', (now() - interval '21 days')::date, 'AED',
   641.00, 32.05, 673.05, 'exclusive', 0.05, 'credit', 'confirmed',
   now() - interval '21 days'),
  ('d0000000-0000-0000-0000-000000000312', 'd0000000-0000-0000-0000-000000000001',
   'd0000000-0000-0000-0000-000000000011', 'd0000000-0000-0000-0000-000000000302',
   'd0000000-0000-0000-0000-000000000022', 'Al Madina Trading Co.',
   'AM-7731', (now() - interval '21 days')::date, 'AED',
   174.00, 8.70, 182.70, 'exclusive', 0.05, 'credit', 'confirmed',
   now() - interval '21 days'),
  -- One week ago: what the menu screen shows before anyone touches the stage.
  ('d0000000-0000-0000-0000-000000000313', 'd0000000-0000-0000-0000-000000000001',
   'd0000000-0000-0000-0000-000000000011', 'd0000000-0000-0000-0000-000000000303',
   'd0000000-0000-0000-0000-000000000021', 'Gulf Foods Trading L.L.C.',
   'GF-20655', (now() - interval '7 days')::date, 'AED',
   660.00, 33.00, 693.00, 'exclusive', 0.05, 'credit', 'confirmed',
   now() - interval '7 days'),
  ('d0000000-0000-0000-0000-000000000314', 'd0000000-0000-0000-0000-000000000001',
   'd0000000-0000-0000-0000-000000000011', 'd0000000-0000-0000-0000-000000000304',
   'd0000000-0000-0000-0000-000000000022', 'Al Madina Trading Co.',
   'AM-7902', (now() - interval '7 days')::date, 'AED',
   180.00, 9.00, 189.00, 'exclusive', 0.05, 'credit', 'confirmed',
   now() - interval '7 days');

-- cost_per_base_unit = unit_price / what is in the pack, worked out here and
-- re-derived through costing.py by tests/test_demo_seed.py:
--
--   Milk Powder 2.5kg    2500.0 g     49.25/2500 = 0.01970000   50.50/2500 = 0.02020000
--   Karak Tea Dust          400 g     21.00/400  = 0.05250000   22.00/400  = 0.05500000
--   Sugar 50kg            50000 g    112.50/50000= 0.00225000  115.00/50000= 0.00230000
--   Cardamom Powder 500g    500 g     23.25/500  = 0.04650000   24.00/500  = 0.04800000
--   Evaporated Milk       19200 ml    87.00/19200= 0.00453125   90.00/19200= 0.00468750
--                      (48 x 400 ml)
insert into invoice_lines (tenant_id, invoice_id, position, raw_name, supplier_item_id,
                           qty, unit, unit_price, line_total, pack_size,
                           cost_per_base_unit, cost_base_unit, cost_basis)
select 'd0000000-0000-0000-0000-000000000001', l.invoice_id, l.position, l.raw_name,
       l.supplier_item_id, l.qty, l.unit, l.unit_price, l.line_total, l.pack_size,
       l.cost_per_base_unit, l.cost_base_unit,
       jsonb_build_object('quality', 'reliable_with_limitations', 'asserted', '[]'::jsonb,
                          'pack', l.pack_size, 'pack_base_quantity', l.pack_base_quantity,
                          'pack_source', 'pack_size')
from (values
  -- 21 days ago, Gulf Foods
  ('d0000000-0000-0000-0000-000000000311'::uuid, 0, 'MILK PWDR 2.5KG NIDO',
   'd0000000-0000-0000-0000-000000000101'::uuid, 4, 'sack', 49.25, 197.00, '2.5kg',
   0.01970000, 'g', '2500.0'),
  ('d0000000-0000-0000-0000-000000000311', 1, 'KARAK TEA DUST 400G',
   'd0000000-0000-0000-0000-000000000102', 6, 'bag', 21.00, 126.00, '400g',
   0.05250000, 'g', '400'),
  ('d0000000-0000-0000-0000-000000000311', 2, 'SUGAR 50KG',
   'd0000000-0000-0000-0000-000000000103', 2, 'sack', 112.50, 225.00, '50kg',
   0.00225000, 'g', '50000'),
  ('d0000000-0000-0000-0000-000000000311', 3, 'CARDAMOM PWD 500G',
   'd0000000-0000-0000-0000-000000000104', 4, 'tin', 23.25, 93.00, '500g',
   0.04650000, 'g', '500'),
  -- 21 days ago, Al Madina
  ('d0000000-0000-0000-0000-000000000312', 0, 'EVAP MILK 48X400ML',
   'd0000000-0000-0000-0000-000000000105', 2, 'carton', 87.00, 174.00, '48x400ml',
   0.00453125, 'ml', '19200'),
  -- 7 days ago, Gulf Foods
  ('d0000000-0000-0000-0000-000000000313', 0, 'MILK PWDR 2.5KG NIDO',
   'd0000000-0000-0000-0000-000000000101', 4, 'sack', 50.50, 202.00, '2.5kg',
   0.02020000, 'g', '2500.0'),
  ('d0000000-0000-0000-0000-000000000313', 1, 'KARAK TEA DUST 400G',
   'd0000000-0000-0000-0000-000000000102', 6, 'bag', 22.00, 132.00, '400g',
   0.05500000, 'g', '400'),
  ('d0000000-0000-0000-0000-000000000313', 2, 'SUGAR 50KG',
   'd0000000-0000-0000-0000-000000000103', 2, 'sack', 115.00, 230.00, '50kg',
   0.00230000, 'g', '50000'),
  ('d0000000-0000-0000-0000-000000000313', 3, 'CARDAMOM PWD 500G',
   'd0000000-0000-0000-0000-000000000104', 4, 'tin', 24.00, 96.00, '500g',
   0.04800000, 'g', '500'),
  -- 7 days ago, Al Madina
  ('d0000000-0000-0000-0000-000000000314', 0, 'EVAP MILK 48X400ML',
   'd0000000-0000-0000-0000-000000000105', 2, 'carton', 90.00, 180.00, '48x400ml',
   0.00468750, 'ml', '19200')
) as l(invoice_id, position, raw_name, supplier_item_id, qty, unit, unit_price,
       line_total, pack_size, cost_per_base_unit, cost_base_unit, pack_base_quantity);

-- The menu. Prices are what the owner says out loud, VAT inside them; the
-- margin is taken against the price net of 5% (WP-61), and the screen says so.
insert into menu_items (id, tenant_id, name, category, selling_price)
values
  ('d0000000-0000-0000-0000-000000000401', 'd0000000-0000-0000-0000-000000000001',
   'Karak Tea (Cup)', 'Tea Corner', 5.000),
  ('d0000000-0000-0000-0000-000000000402', 'd0000000-0000-0000-0000-000000000001',
   'Karak Tea (Flask 1 L)', 'Tea Corner', 35.000),
  ('d0000000-0000-0000-0000-000000000403', 'd0000000-0000-0000-0000-000000000001',
   'Cardamom Chai (Flask 2 L)', 'Tea Corner', 55.000),
  ('d0000000-0000-0000-0000-000000000404', 'd0000000-0000-0000-0000-000000000001',
   'Nido Milk Tea', 'Tea Corner', 8.000),
  ('d0000000-0000-0000-0000-000000000405', 'd0000000-0000-0000-0000-000000000001',
   'Paratha', 'Bakery', 3.000);

-- One version each. Editing appends a new one and never touches these, so a
-- rehearsal that changes a recipe leaves version 1 exactly as it is here.
insert into recipes (id, tenant_id, menu_item_id, version, yield_portions, yield_label)
values
  ('d0000000-0000-0000-0000-000000000411', 'd0000000-0000-0000-0000-000000000001',
   'd0000000-0000-0000-0000-000000000401', 1, 40, 'cups'),
  ('d0000000-0000-0000-0000-000000000412', 'd0000000-0000-0000-0000-000000000001',
   'd0000000-0000-0000-0000-000000000402', 1, 1, 'flask'),
  ('d0000000-0000-0000-0000-000000000413', 'd0000000-0000-0000-0000-000000000001',
   'd0000000-0000-0000-0000-000000000403', 1, 1, 'flask'),
  ('d0000000-0000-0000-0000-000000000414', 'd0000000-0000-0000-0000-000000000001',
   'd0000000-0000-0000-0000-000000000404', 1, 1, 'glass'),
  ('d0000000-0000-0000-0000-000000000415', 'd0000000-0000-0000-0000-000000000001',
   'd0000000-0000-0000-0000-000000000405', 1, 20, 'pieces');

-- Quantities are AS PURCHASED and per batch: the whole pot, divided once by
-- the yield above. `source_text` keeps the card's own words beside the
-- consultant's converted number - the only audit a typed quantity has.
insert into recipe_components (tenant_id, recipe_id, position, ingredient_id, qty, unit,
                               source_text)
values
  -- Karak Tea (Cup): one 40-cup pot
  ('d0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000411', 0,
   'd0000000-0000-0000-0000-000000000202', 220, 'g', 'one big spoon of dust per litre'),
  ('d0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000411', 1,
   'd0000000-0000-0000-0000-000000000205', 2200, 'ml', 'five tins'),
  ('d0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000411', 2,
   'd0000000-0000-0000-0000-000000000203', 1600, 'g', null),
  ('d0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000411', 3,
   'd0000000-0000-0000-0000-000000000204', 20, 'g', 'a pinch'),
  -- Karak Tea (Flask 1 L)
  ('d0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000412', 0,
   'd0000000-0000-0000-0000-000000000202', 28, 'g', null),
  ('d0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000412', 1,
   'd0000000-0000-0000-0000-000000000205', 390, 'ml', null),
  ('d0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000412', 2,
   'd0000000-0000-0000-0000-000000000201', 70, 'g', null),
  -- Cardamom Chai (Flask 2 L) - the menu's top earner per plate
  ('d0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000413', 0,
   'd0000000-0000-0000-0000-000000000202', 55, 'g', null),
  ('d0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000413', 1,
   'd0000000-0000-0000-0000-000000000205', 780, 'ml', null),
  ('d0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000413', 2,
   'd0000000-0000-0000-0000-000000000201', 140, 'g', null),
  ('d0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000413', 3,
   'd0000000-0000-0000-0000-000000000204', 6, 'g', null),
  -- Nido Milk Tea
  ('d0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000414', 0,
   'd0000000-0000-0000-0000-000000000201', 40, 'g', 'two spoons of Nido'),
  ('d0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000414', 1,
   'd0000000-0000-0000-0000-000000000205', 100, 'ml', null),
  ('d0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000414', 2,
   'd0000000-0000-0000-0000-000000000203', 12, 'g', null),
  -- Paratha: the incomplete one. Atta Flour has no pack mapped to it yet, so
  -- this item shows its menu price and no cost at all - never a cheap plate.
  ('d0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000415', 0,
   'd0000000-0000-0000-0000-000000000206', 2000, 'g', 'one 2 kg batch of dough');

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
