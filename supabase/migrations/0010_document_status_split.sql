-- Document status owns ingest only; the invoice owns review (plan.md C1).
-- Appended per contract C7; the manager squashes periodically (plan.md §4 policy).

-- Both tables claimed a 'confirmed' state, and nothing but application code
-- kept the pair in step: the two confirm paths updated invoices and then
-- documents back to back, so any future path that updated one and forgot the
-- other would drift with no constraint to notice. The document's job ends when
-- a draft invoice with checks exists for it ('extracted'); everything after
-- that is the invoice's lifecycle. Confirmation is read through
-- invoices.document_id, unique since 0008, so the derived answer is exact.
update documents set status = 'extracted' where status = 'confirmed';

alter table documents drop constraint documents_status_check;
alter table documents add constraint documents_status_check
  check (status in ('received', 'processing', 'extracted', 'failed'));

comment on column documents.status is
  'ingest only: received -> processing -> extracted | failed. Whether the '
  'invoice was confirmed lives on invoices.status (C1)';
