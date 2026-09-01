-- One-time live cleanup, 2026-09-01 (founder's call; plan.md Progress Log).
--
-- Removes seed.sql's fixture tenant (Demo Cafeteria Group,
-- 00000000-0000-0000-0000-000000000001) from the live project, so the demo
-- chain is the ONLY tenant - "the demo runs single-tenant seeded" becomes
-- literally true, and db.default_tenant_id's oldest-wins rule has nothing
-- left to mis-pick (the 2026-08-31 demotion in apply_tenant_default_fix.sql
-- becomes moot). M7's real tenancy retires the rule entirely.
--
-- What goes is M0-M2 era test residue, inventoried and backed up before this
-- file was written (fixture-tenant-backup-20260901.txt, session scratchpad):
-- 1 branch (Al Barsha, no phone), 2 suppliers, 10 supplier_items from the
-- first live extraction tests, 1 ingredient, 2 audit rows - one of which
-- references an invoice that no longer exists. Zero documents, invoices,
-- lines, prices, menu rows or extraction runs. wa_messages carry no tenant
-- and stay as inbound/outbound logs.
--
--   psql "$DATABASE_URL" -f Docs/apply_delete_fixture_tenant.sql

begin;

delete from audit_events
 where tenant_id = '00000000-0000-0000-0000-000000000001';

delete from supplier_item_prices
 where tenant_id = '00000000-0000-0000-0000-000000000001';

delete from supplier_items
 where tenant_id = '00000000-0000-0000-0000-000000000001';

delete from ingredients
 where tenant_id = '00000000-0000-0000-0000-000000000001';

delete from suppliers
 where tenant_id = '00000000-0000-0000-0000-000000000001';

delete from branches
 where tenant_id = '00000000-0000-0000-0000-000000000001';

delete from tenants
 where id = '00000000-0000-0000-0000-000000000001'
   and name = 'Demo Cafeteria Group';

commit;

select id, name, created_at from tenants order by created_at;
