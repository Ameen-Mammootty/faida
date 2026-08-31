-- One-time live fix, 2026-08-31 (demo-gate session; plan.md Progress Log).
--
-- The console resolves its tenant as "oldest created_at" (db.default_tenant_id),
-- and on the live project seed.sql's fixture tenant (Demo Cafeteria Group,
-- created 2026-08-22) predates the demo chain (2026-08-29) - so every /api/*
-- read and the menu loader would hit the fixture tenant while the WhatsApp
-- invoices land in the demo chain. Verified live before this fix:
-- /api/menu-items would have written Koukh Al Shay's menu into the wrong tenant.
--
-- The fix demotes the fixture tenant rather than deleting it (reversible; the
-- founder can decide to drop it later). Its rows are fixture residue only:
-- 1 branch, 2 suppliers, 10 supplier_items, 1 ingredient, 2 audit events,
-- 0 documents, 0 invoices (inventoried 2026-08-31).
--
-- To reverse: its original created_at was 2026-08-22 15:52:01.404796+00.
--
--   psql "$DATABASE_URL" -f Docs/apply_tenant_default_fix.sql

update tenants
   set created_at = now()
 where id = '00000000-0000-0000-0000-000000000001'
   and name = 'Demo Cafeteria Group';

select id, name, created_at from tenants order by created_at;
