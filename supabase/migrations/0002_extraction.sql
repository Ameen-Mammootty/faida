-- WP-13: extraction pipeline persistence (plan.md §6 M1).
-- Appended per contract C7; the manager squashes periodically (plan.md §4 policy).

-- One row per completed pipeline run (plan.md §5 layer 1): which model and
-- prompt read the document, what it cost, and how the run ended.
create table extraction_runs (
  id             bigserial primary key,
  document_id    uuid not null references documents(id),
  model_id       text not null,
  prompt_version text not null,
  input_tokens   int,
  output_tokens  int,
  latency_ms     int,
  repair_applied boolean not null default false,
  outcome        text not null
                 check (outcome in ('extracted', 'failed', 'not_invoice', 'z_report')),
  created_at     timestamptz not null default now()
);
create index extraction_runs_document_idx on extraction_runs (document_id);

-- The structured call classifies and extracts together (C3); non-invoice
-- documents keep their classification next to status 'failed' (C1).
alter table documents add column classification text
  check (classification in ('invoice', 'z_report', 'other'));

-- C3 line schema carries pack_size; persist it with the other line fields.
alter table invoice_lines add column pack_size text;

-- Deny-all RLS, keeping the 0001 invariant: PostgREST serves the public
-- schema, the backend connects as owner/service_role and bypasses it.
alter table extraction_runs enable row level security;
