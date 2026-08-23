-- WP-22: supplier memory (plan.md §5 layer 4).
-- Appended per contract C7; the manager squashes periodically (plan.md §4 policy).

-- The raw extracted supplier name, kept verbatim: supplier matching scores it,
-- the review screen shows it beside the photo, and when no supplier row matched
-- it is the only record of who the invoice came from (WP-13 flagged it as lost).
alter table invoices add column supplier_name text;

-- Price-history appends are idempotent per invoice: confirming the same invoice
-- twice must not duplicate observations (on conflict do nothing). Rows with a
-- null invoice_id (seeded or manual history) stay unrestricted, hence partial.
create unique index supplier_item_prices_item_invoice_uidx
  on supplier_item_prices (supplier_item_id, invoice_id)
  where invoice_id is not null;
