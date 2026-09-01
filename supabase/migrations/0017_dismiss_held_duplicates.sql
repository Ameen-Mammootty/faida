-- 0017: a held duplicate gets a way out (plan.md TODOS pull-forward, 2026-09-01).
-- Appended per contract C7; the manager squashes periodically (plan.md §4 policy).
--
-- APPLY THIS BEFORE THE CODE THAT NEEDS IT. The invoice insert (db.py, the
-- fixed column list in insert_draft_invoice) names duplicate_of_invoice_id
-- explicitly, so a deploy that lands ahead of this file does not degrade - it
-- raises UndefinedColumn on EVERY forwarded invoice, three job retries, then
-- silence. The order is: apply this, then deploy the API, then deploy web.
-- Docs/apply_dismiss_door.sql is the paste-ready copy with a pre-flight check.
--
-- WP-44 holds the second copy of a re-sent paper as needs_review and replies
-- "This one is already recorded...". Correct, and until now a dead end: chat
-- OK resolves only awaiting_confirm, the screen offered correct/confirm paths
-- that make no sense for a copy, and there was no way out at all. The founder
-- hit it the day before the M6 gate: "the duplicate invoice of al madina is in
-- my invoice list, and there is no option to mark duplicate and delete it."

-- **A terminal status, not a flag on the row.** The single confirm write
-- (db._confirm) is `where id = $1 and status = $2 and total is not null`, and
-- both doors pass the status they expect. So a dismissed invoice is refused by
-- both with no new code, and a third door written later cannot reopen it -
-- exactly the argument WP-26 made for putting `total is not null` in that same
-- clause. A dismissed_at flag would leave the row reading needs_review, and
-- confirm_reviewed_invoice would go right on confirming it.
--
-- Everything downstream keys on 'confirmed' (costing, price memory, plates), so
-- a fifth value is inert everywhere it should be.
alter table invoices drop constraint invoices_status_check;
alter table invoices add constraint invoices_status_check
  check (status in ('draft', 'awaiting_confirm', 'confirmed', 'needs_review', 'dismissed'));

comment on column invoices.status is
  'draft -> awaiting_confirm -> confirmed | needs_review | dismissed (C1). '
  '**dismissed** is terminal and screen-only: a reviewer resolving a WP-44 '
  'duplicate hold. Only a row carrying duplicate_of_invoice_id can reach it, '
  'and only from a never-confirmed state - a recorded invoice is a financial '
  'record. audit_events holds who dismissed it and when.';

-- **What the hold was held against.** Until now the pipeline computed the
-- duplicate, spent it on the WhatsApp sentence, and threw it away - so a
-- duplicate hold and a WP-24 cash hold were the same row, and the review screen
-- could say nothing about either. Recorded at the moment of the decision, never
-- re-derived: find_duplicate answers against every earlier header, so a later
-- invoice changes the answer, and a screen re-deriving it months on could
-- contradict the sentence the sender already received.
--
-- The unique constraint below is redundant for uniqueness (id is already the
-- primary key) and is required as the target of the composite foreign key -
-- the 0012 shape. Cross-tenant is refused by Postgres rather than by the scope
-- of whichever query happens to feed the insert (plan.md §2 rule 3), which
-- matters more the moment M7 turns tenancy enforcement on.
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

-- Deliberately NOT added.
--
-- No dismissed_at column. Nothing would read it: audit_events already records
-- who dismissed the row and when, in the transaction that did it (C8), and a
-- second home for the same fact is the duplication migration 0010 deleted.
-- confirmed_at exists only because the detail screen prints it.
--
-- No index on duplicate_of_invoice_id. The self-referencing foreign key makes
-- every invoice delete scan invoices, and both demo reset files delete
-- invoices - but at demo and pilot volume that is a scan of a few hundred rows,
-- and 0013's policy refuses an index ahead of a query that needs one. Revisit
-- with a measurement, not with a guess.
