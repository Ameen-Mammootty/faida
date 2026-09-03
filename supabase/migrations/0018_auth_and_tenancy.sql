-- 0018: auth and tenancy keys (plan.md §8 M7, WP-73).
-- Appended per contract C7; the manager squashes periodically (plan.md §4 policy).
--
-- APPLY THIS AFTER WP-73 MERGES AND BEFORE ANY WAVE 2 LANE MERGES. WP-73's
-- code runs against 0017 - nothing in it reads memberships or inserts against
-- the new index - but WP-72's enqueue_once needs the jobs index to exist, and
-- WP-70 needs memberships. Docs/apply_m7_migrations.sql is the paste-ready copy
-- with a pre-flight check.
--
-- Three things, none of which the code reads yet:
--
-- 1. `memberships`: which people belong to which tenant, and as what. WP-70
--    swaps the shared console token for a verified Supabase token and reads
--    this table to turn a user id into a tenant id. One role for now -
--    'tenant', the owner-level role - because it is the only one the product
--    has a screen for; brand and branch (PRD §4) join the check constraint
--    when their screens exist, not before.
--
--    `user_id` is a bare uuid with NO foreign key to auth.users, on purpose.
--    CI applies these migrations to a plain Postgres with no auth schema, and
--    a reference to it would fail there on `create table`. The same choice
--    was made for audit_events.subject_id (0011): an id column whose
--    referent lives outside this schema stays a plain uuid, and the
--    application is what keeps it honest. Deny-all RLS like every table since
--    0001 - the anon key must never read who belongs where.
--
-- 2. `(tenant_id, branch_id)` composite foreign keys on documents and
--    invoices, the 0012/0017 shape. Branch is resolved from the sender's
--    phone and lands on both rows; a plain reference to branches(id) lets a
--    document under Tenant A point at Tenant B's branch, and until now only
--    the worker's care prevented it. Postgres refuses it at the write now,
--    whatever a code path forgot (plan.md §2 rule 3). `branches` gains the
--    redundant unique (tenant_id, id) the composite key has to reference.
--    Null branch_id still satisfies it (MATCH SIMPLE): an unknown sender's
--    document has no branch, and that stays legal.
--
-- 3. One extract job per document: a unique index on jobs (kind, document_id)
--    for kind = 'extract_document', with NO status filter. The worker's
--    process_wa_message enqueues the extract job and then sends the ack; if
--    the send fails, the 30 s retry re-runs the whole handler and enqueues a
--    second extract job for the same paper. Today that second job is harmless
--    only because the pipeline notices the invoice already exists. The index
--    makes the duplicate impossible instead of merely harmless, and WP-72's
--    enqueue_once (insert ... on conflict do nothing) is what the worker will
--    call against it. No status filter, on purpose (D22): the retry always
--    lands after extraction is done, so "queued or running only" would let
--    the retry mint a fresh job the moment the first one finished - exactly
--    the duplicate this exists to refuse.
--
--    Live data may already hold such duplicates from past retries. The
--    delete below keeps the first job for each document and drops the later
--    copies, so the index can be created; a copy still queued would only have
--    re-run a pipeline that no-ops on an invoice that already exists.

-- 1. memberships ---------------------------------------------------------------

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

-- WP-70 turns a user id into a tenant id on every request.
create index memberships_user_idx on memberships (user_id);

alter table memberships enable row level security;

-- 2. branch tenancy keys ------------------------------------------------------

alter table branches add constraint branches_tenant_id_uidx unique (tenant_id, id);

alter table documents add constraint documents_branch_fk
  foreign key (tenant_id, branch_id) references branches (tenant_id, id);

alter table invoices add constraint invoices_branch_fk
  foreign key (tenant_id, branch_id) references branches (tenant_id, id);

-- 3. one extract job per document ---------------------------------------------

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
