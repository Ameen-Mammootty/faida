-- Demo seed: one tenant, one branch.
-- Set the branch phone to the WhatsApp number a demo phone will forward FROM
-- (E.164 digits only, no '+'), so the webhook resolves sender -> branch.

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
