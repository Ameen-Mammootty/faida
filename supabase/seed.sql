-- Demo seed: one tenant, one branch.
-- The branch phone is the WhatsApp number a demo phone forwards FROM (E.164 digits only,
-- no '+'), so the webhook resolves sender -> branch.
-- This file keeps the placeholder on purpose: local dev and CI seed from it and the tests
-- pin the same value (tests/conftest.py DEMO_PHONE), and real phone numbers stay out of git.
-- Set the real number per environment instead (the live demo project already has it).

insert into tenants (id, name, currency)
values ('00000000-0000-0000-0000-000000000001', 'Demo Cafeteria Group', 'AED')
on conflict (id) do nothing;

insert into branches (id, tenant_id, name, wa_phone_e164, timezone)
values (
  '00000000-0000-0000-0000-000000000011',
  '00000000-0000-0000-0000-000000000001',
  'Al Barsha Branch',
  '971500000000',  -- CHANGE ME to the demo phone that forwards invoices
  'Asia/Dubai'
)
on conflict (id) do nothing;
