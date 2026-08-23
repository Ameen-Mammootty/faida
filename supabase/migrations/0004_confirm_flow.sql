-- WP-21: confirm flow (plan.md §6 M2, C5).
-- Appended per contract C7; the manager squashes periodically (plan.md §4 policy).

-- When the invoice confirmed (the chat "OK" today; review-screen confirm from M3).
-- The confirm flow's retry guard compares it against the inbound message's arrival
-- time, so a re-run text job re-sends the ack instead of confirming a second invoice.
alter table invoices add column confirmed_at timestamptz;
