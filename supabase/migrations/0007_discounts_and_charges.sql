-- WP-18: discounts and non-stock charges (plan.md C3/C4).
-- Appended per contract C7; the manager squashes periodically (plan.md §4 policy).

-- The C4 identities generalize to:
--   exclusive  sum(lines) - discount + rounding + tax = total
--   inclusive  sum(lines) - discount + rounding       = total   (tax inside)
-- Without these two columns a trade discount makes a perfectly-read invoice
-- fail both identities and go amber, which is routine in GCC food supply.
-- Discount is stored POSITIVE and subtracted, the way invoices print it.
alter table invoices add column discount_total  numeric(12,2);
alter table invoices add column rounding_amount numeric(12,2);

-- Delivery, cool-box hire, pallet fees. They belong in the invoice total and in
-- cost, but they are not stock: they must never become supplier_items, or the
-- price catalog fills with charges and price alerts start firing on delivery
-- fees. Defaulting to 'stock_item' keeps every existing row correct.
alter table invoice_lines add column line_kind text not null default 'stock_item'
  check (line_kind in ('stock_item', 'charge'));

comment on column invoices.discount_total is
  'positive amount subtracted from the line sum (C4); null when the invoice shows none';
comment on column invoice_lines.line_kind is
  'stock_item feeds the catalog and price memory; charge is cost-only (C4, WP-18)';
