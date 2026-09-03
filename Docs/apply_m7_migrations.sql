-- Faida: migration 0018 alone, for a live project already at 0017.
--
-- Adds M7's tenancy keys: the memberships table WP-70 will read, the
-- (tenant_id, branch_id) composite foreign keys on documents and invoices,
-- and the one-extract-job-per-document index WP-72's enqueue_once needs.
--
-- HOW TO USE THIS FILE
--   Open it, select all, copy, paste into the Supabase SQL editor, run once.
--   Every byte of this file is SQL. There is nothing in it to select wrongly.
--
-- RUN THIS AFTER WP-73 IS ON MASTER AND BEFORE ANY WAVE 2 LANE MERGES.
--   WP-73's code runs against 0017 as well as 0018 - it reads none of this.
--   The Wave 2 lanes do: WP-72 inserts extract jobs against the index below,
--   and WP-70 reads memberships. Railway deploys every merge to master, so
--   the order is: merge WP-73, run this file, then merge the Wave 2 lanes.
--
-- BEFORE YOU RUN IT
--   Run the check below on its own first. All three columns must come back
--   as shown; anything else means stop and read the note beside it.
--
--   select not exists (select 1 from information_schema.tables
--                      where table_name = 'memberships') as needs_0018,
--          (select count(*) from documents d
--            where d.branch_id is not null
--              and not exists (select 1 from branches b
--                               where b.id = d.branch_id
--                                 and b.tenant_id = d.tenant_id))
--            as documents_on_a_foreign_branch,
--          (select count(*) from invoices i
--            where i.branch_id is not null
--              and not exists (select 1 from branches b
--                               where b.id = i.branch_id
--                                 and b.tenant_id = i.tenant_id))
--            as invoices_on_a_foreign_branch;
--
--   needs_0018                       true   (false: already applied; the run
--                                            would fail on `create table`)
--   documents_on_a_foreign_branch    0      (anything else: a document claims
--                                            another tenant's branch and the
--                                            composite key will refuse to be
--                                            created - find it with the
--                                            subquery above and fix the row
--                                            before running this file)
--   invoices_on_a_foreign_branch     0      (same)
--
--   (A fresh database with no tenants table at all needs the full migration
--   set in supabase/migrations/, not this file.)
--
-- WHAT IT DELETES
--   Duplicate extract jobs: where a document has more than one
--   'extract_document' job (a past retry after a failed WhatsApp send), the
--   first is kept and the later copies are deleted so the unique index can be
--   created. A later copy only ever re-ran a pipeline that stops when the
--   invoice already exists. The verify block at the end reports how many
--   went.

begin;

create table memberships (
  id         uuid primary key default gen_random_uuid(),
  tenant_id  uuid not null references tenants(id),
  user_id    uuid not null,
  role       text not null default 'tenant' check (role in ('tenant')),
  created_at timestamptz not null default now(),
  unique (tenant_id, user_id)
);

comment on table memberships is
  'who belongs to which tenant (M7 WP-70 reads it; WP-73 created it). '
  'user_id is a Supabase auth user id kept as a bare uuid: no foreign key to '
  'auth.users, because CI has no auth schema (the audit_events.subject_id '
  'precedent). One role for now; brand and branch join the check when their '
  'screens exist.';

create index memberships_user_idx on memberships (user_id);

alter table memberships enable row level security;

alter table branches add constraint branches_tenant_id_uidx unique (tenant_id, id);

alter table documents add constraint documents_branch_fk
  foreign key (tenant_id, branch_id) references branches (tenant_id, id);

alter table invoices add constraint invoices_branch_fk
  foreign key (tenant_id, branch_id) references branches (tenant_id, id);

delete from jobs later
 using jobs first
 where later.kind = 'extract_document'
   and first.kind = 'extract_document'
   and later.payload->>'document_id' = first.payload->>'document_id'
   and later.id > first.id;

create unique index jobs_extract_document_uidx
  on jobs (kind, (payload->>'document_id'))
  where kind = 'extract_document';

comment on index jobs_extract_document_uidx is
  'one extract job per document, whatever its status (D22). WP-72''s '
  'enqueue_once inserts against it with on conflict do nothing.';

commit;

-- Verify: the four constraints and the index should all come back, memberships
-- should be empty (WP-70 fills it), and every document still has its job.
select conname from pg_constraint
 where conname in ('branches_tenant_id_uidx', 'documents_branch_fk',
                   'invoices_branch_fk', 'memberships_tenant_id_user_id_key')
 order by conname;

select indexname from pg_indexes where indexname = 'jobs_extract_document_uidx';

select (select count(*) from memberships) as memberships,
       (select count(*) from jobs where kind = 'extract_document') as extract_jobs,
       (select count(distinct payload->>'document_id') from jobs
         where kind = 'extract_document') as documents_with_a_job;
