-- Faida: migration 0017 alone, for a live project already at 0016.
--
-- Adds the dismiss door for WP-44 duplicate holds: a fifth invoices.status
-- ('dismissed') and the duplicate_of_invoice_id pointer the review screen
-- needs to name what a held copy duplicates.
--
-- HOW TO USE THIS FILE
--   Open it, select all, copy, paste into the Supabase SQL editor, run once.
--   Every byte of this file is SQL. There is nothing in it to select wrongly.
--
-- RUN THIS BEFORE DEPLOYING THE API THAT NEEDS IT.
--   The invoice insert names duplicate_of_invoice_id explicitly, so an API
--   deploy that lands first does not degrade - it raises UndefinedColumn on
--   EVERY forwarded invoice, retries three times, then goes quiet. The order
--   is: run this file, then deploy the API, then deploy web (Vercel is manual;
--   web last, or the Dismiss button calls an endpoint that is not there yet).
--   Doing all three in one sitting keeps the live schema from running ahead of
--   master for days.
--
-- BEFORE YOU RUN IT
--   Run the check below on its own first. It must come back true; false means
--   0017 is already applied and the run will fail on `add column`.
--
--   select not exists (select 1 from information_schema.columns
--                      where table_name = 'invoices'
--                        and column_name = 'duplicate_of_invoice_id') as needs_0017;
--
--   (A fresh database with no invoices table at all needs the full migration
--   set in supabase/migrations/, not this file.)

begin;

alter table invoices drop constraint invoices_status_check;
alter table invoices add constraint invoices_status_check
  check (status in ('draft', 'awaiting_confirm', 'confirmed', 'needs_review', 'dismissed'));

comment on column invoices.status is
  'draft -> awaiting_confirm -> confirmed | needs_review | dismissed (C1). '
  '**dismissed** is terminal and screen-only: a reviewer resolving a WP-44 '
  'duplicate hold. Only a row carrying duplicate_of_invoice_id can reach it, '
  'and only from a never-confirmed state - a recorded invoice is a financial '
  'record. audit_events holds who dismissed it and when.';

alter table invoices add constraint invoices_tenant_id_uidx unique (tenant_id, id);

alter table invoices add column duplicate_of_invoice_id uuid;

alter table invoices add constraint invoices_duplicate_of_fk
  foreign key (tenant_id, duplicate_of_invoice_id)
  references invoices (tenant_id, id) on delete set null;

comment on column invoices.duplicate_of_invoice_id is
  'the earlier invoice this one duplicates, written by the pipeline when WP-44 '
  'holds it (same supplier + normalized number + total). Null on every ordinary '
  'invoice, which is what makes it the dismiss guard: the original carries no '
  'pointer, so it can never be dismissed. on delete set null so a future '
  'id-targeted cleanup of an original is not blocked by a copy pointing at it.';

commit;

-- Verify: all three should come back, and every existing invoice reads null.
select conname from pg_constraint
 where conname in ('invoices_status_check', 'invoices_tenant_id_uidx',
                   'invoices_duplicate_of_fk')
 order by conname;

select count(*) as invoices, count(duplicate_of_invoice_id) as with_pointer
  from invoices;
