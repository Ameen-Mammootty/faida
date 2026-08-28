-- 0011: C8 provenance + the audit spine (plan.md §7.2 C8, §8 M5).
--
-- Two questions the schema could not answer before, and needs to answer
-- before M5 turns invoice figures into a cost per base unit:
--
--   1. Where did this number come from? `invoices.confidence` says whether a
--      value survived the arithmetic; nothing said whether a camera saw it.
--      A total read off the page and a total the owner typed into WhatsApp
--      because the paper was out of frame were the same number in the same
--      column. Once that figure is divided twice and sitting inside a plate
--      cost, nothing downstream can tell them apart either.
--
--   2. Who approved this? M5's first feature is a human approval - merging
--      two suppliers' items into one raw material - and a wrong merge
--      quietly corrupts the cost of every menu item above it, with no photo
--      to check it against. audit_events was scheduled for M7, two
--      milestones after the first thing that needs it.
--
-- Division of labour, so neither table becomes a second copy of the other:
-- extraction_runs is the record of what the *model* did (which model, which
-- prompt version, what it cost, whether it needed a repair round);
-- audit_events is the record of what a *person* decided. Together they answer
-- "who did this".

alter table invoices add column provenance jsonb not null default '{}'::jsonb;

comment on column invoices.provenance is
  'C8: field path -> {origin, actor, at}. Flat keys ("total", "lines.3.qty") '
  'because every write is a merge over a subset of fields. See '
  'faida_api/provenance.py for the vocabulary.';

create table audit_events (
  id           bigserial primary key,
  tenant_id    uuid not null references tenants(id),
  actor        text not null,
  action       text not null,
  subject_type text not null,
  subject_id   uuid,
  detail       jsonb not null default '{}'::jsonb,
  created_at   timestamptz not null default now()
);

comment on table audit_events is
  'Human decisions, one row each. actor is free text until M7 brings real '
  'accounts: "whatsapp:+9715...", "console". A string actor is a real answer '
  'to who merged two materials, where the alternative today is silence.';

-- The two reads this table gets: an activity feed per tenant, and the history
-- of one invoice or one raw material.
create index audit_events_tenant_created_idx on audit_events (tenant_id, created_at desc);
create index audit_events_subject_idx on audit_events (subject_type, subject_id, created_at desc);

-- Deny-all, per the 0001 convention: Supabase serves `public` over PostgREST,
-- so a table without this is readable with the anon key. The backend uses the
-- service role and is unaffected; M7 owns real tenant policies.
alter table audit_events enable row level security;
