-- One-time live fix, 2026-08-31 (demo-gate session; plan.md Progress Log).
--
-- KAS-3 (AMT-26-1203) was forwarded twice during preparation. WP-44 correctly
-- held the second copy as a duplicate ("This one is already recorded..."),
-- but a held copy has no resolution door on the review screen - it sits in
-- needs_review forever. The founder hit this on 2026-08-31: "the duplicate
-- invoice of al madina is in my invoice list, and there is no option to mark
-- duplicate and delete it." The product door is recorded as new scope
-- (TODOS.md); this file clears the one accidental copy so the §A checklist
-- ("no rehearsal leftovers in the invoice list") passes for the gate.
--
-- Targeted by the duplicate's own row ids, verified before writing:
--   duplicate invoice  e1308b09-9516-46b6-8536-43a0bff6007f  (14:16:32, needs_review)
--   its document       4aa5c89d-45b9-4d10-9ec8-f265cf7c1bb9
-- The CONFIRMED original (2b023fc9..., 14:14:31) is not touched, and the
-- duplicate had no price rows and no audit rows (never confirmed). Its photo
-- stays in the storage bucket - originals are immutable evidence.
--
--   psql "$DATABASE_URL" -f Docs/apply_remove_duplicate_kas3.sql

begin;

delete from jobs
 where payload->>'document_id' = '4aa5c89d-45b9-4d10-9ec8-f265cf7c1bb9'
    or payload->>'message_id' = (
      select wa_message_id from documents
       where id = '4aa5c89d-45b9-4d10-9ec8-f265cf7c1bb9');

delete from wa_messages
 where message_id = (
   select wa_message_id from documents
    where id = '4aa5c89d-45b9-4d10-9ec8-f265cf7c1bb9');

delete from extraction_runs
 where document_id = '4aa5c89d-45b9-4d10-9ec8-f265cf7c1bb9';

delete from invoices
 where id = 'e1308b09-9516-46b6-8536-43a0bff6007f'
   and status = 'needs_review';  -- lines cascade; refuses if it was somehow confirmed

delete from documents
 where id = '4aa5c89d-45b9-4d10-9ec8-f265cf7c1bb9';

commit;

select invoice_no, status, created_at
  from invoices
 where tenant_id = 'd0000000-0000-0000-0000-000000000001'
 order by created_at;
