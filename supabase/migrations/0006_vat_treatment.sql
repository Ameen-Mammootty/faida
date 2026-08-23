-- WP-17: VAT treatment (plan.md C3/C4 as amended 2026-08-23).
-- Appended per contract C7; the manager squashes periodically (plan.md §4 policy).

-- Which C4 identity reconciled this invoice's totals, and at what rate. Both
-- are DERIVED from the arithmetic, never taken from the document's own claim.
-- Money stays exactly as printed (subtotal/tax/total); these columns say how to
-- read it, so the review screen can keep tracing every number to the photo.
alter table invoices add column tax_treatment text
  check (tax_treatment in ('inclusive', 'exclusive'));
alter table invoices add column vat_rate numeric(6,4);

-- Price memory is net-canonical (C4): supplier_items.last_price/prev_price and
-- supplier_item_prices.price hold the EX-VAT unit price, while
-- invoice_lines.unit_price keeps the as-printed value for display. Mixing the
-- two bases would make a supplier switching invoice format fire a
-- full-threshold price alert (PRICE_ALERT_MIN_PCT is 5%, UAE VAT is 5%).
comment on column supplier_items.last_price is
  'ex-VAT unit price (C4 net-canonical); display price lives on invoice_lines';
comment on column supplier_items.prev_price is
  'ex-VAT unit price (C4 net-canonical); display price lives on invoice_lines';
comment on column supplier_item_prices.price is
  'ex-VAT unit price (C4 net-canonical); display price lives on invoice_lines';
