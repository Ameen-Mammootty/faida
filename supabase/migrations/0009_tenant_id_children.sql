-- Tenant ownership on the three child tables that reached it only by join.
-- Appended per contract C7; the manager squashes periodically (plan.md §4 policy).

-- Every tenant-owned row carries tenant_id from day one (plan.md §4), but
-- invoice_lines, supplier_item_prices and extraction_runs each found their
-- tenant only through a parent: invoice_id -> invoices, supplier_item_id ->
-- supplier_items, document_id -> documents. M7 puts real RLS policies on a
-- schema PostgREST already serves, and a policy that has to reach the tenant
-- through a parent is a subquery per row plus one more predicate to get wrong
-- on exactly the tables that must not leak. The column makes each policy a
-- direct comparison.
--
-- Done now, this is one column and a backfill over a single-tenant seeded
-- schema. After the first paying customer it is a migration against live rows.
alter table invoice_lines        add column tenant_id uuid references tenants(id);
alter table supplier_item_prices add column tenant_id uuid references tenants(id);
alter table extraction_runs      add column tenant_id uuid references tenants(id);

-- The parent is the authority for the value: a child row must never claim a
-- different tenant than the row it hangs off. Every insert path derives the
-- column the same way, so the two can never drift.
update invoice_lines l
  set tenant_id = i.tenant_id from invoices i where i.id = l.invoice_id;
update supplier_item_prices p
  set tenant_id = s.tenant_id from supplier_items s where s.id = p.supplier_item_id;
update extraction_runs r
  set tenant_id = d.tenant_id from documents d where d.id = r.document_id;

alter table invoice_lines        alter column tenant_id set not null;
alter table supplier_item_prices alter column tenant_id set not null;
alter table extraction_runs      alter column tenant_id set not null;

-- No index on these columns yet: nothing queries by tenant_id alone today, and
-- the indexes that RLS wants depend on the policy predicates M7 writes. They
-- arrive with those policies, not ahead of them.
