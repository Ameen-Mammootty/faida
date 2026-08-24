-- Invoice integrity: enforce one invoice per document, index the lines FK.
-- Appended per contract C7; the manager squashes periodically (plan.md §4 policy).

-- C1/C2 treat a document and its invoice as 1:1 - `extracted` means one draft
-- invoice with checks exists for that document - and the code already assumes
-- it: extraction/pipeline.py returns early when an invoice exists, and
-- Database.get_invoice_by_document fetches a single row. That guard is a read
-- before a write, so two `extract_document` attempts (3 per job, 30 s backoff)
-- can both pass it and draft two invoices for one photo. The review screen
-- would then show whichever came back first, and confirming each would move
-- price memory twice. The 1:1 is an invariant, so Postgres enforces it.
create unique index invoices_document_uidx on invoices (document_id);

-- invoice_lines.invoice_id had no index: Postgres does not create one for a
-- foreign key. Every invoice render, the confirm flow's line-sum check, and the
-- on-delete cascade scanned the whole table, which grows with every line of
-- every invoice. `position` rides along so the review screen's
-- `order by position` is served by the same index.
create index invoice_lines_invoice_idx on invoice_lines (invoice_id, position);
