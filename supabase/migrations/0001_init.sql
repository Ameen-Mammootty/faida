-- Faida initial schema (plan.md §4).
-- Squashable until first customer: edit this file freely pre-launch instead of adding new ones.

create table tenants (
  id         uuid primary key default gen_random_uuid(),
  name       text not null,
  currency   text not null default 'AED',
  created_at timestamptz not null default now()
);

create table branches (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references tenants(id),
  name          text not null,
  wa_phone_e164 text unique,
  timezone      text not null default 'Asia/Dubai',
  created_at    timestamptz not null default now()
);

create table suppliers (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references tenants(id),
  name         text not null,
  name_aliases text[] not null default '{}',
  created_at   timestamptz not null default now(),
  unique (tenant_id, name)
);

create table supplier_items (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null references tenants(id),
  supplier_id    uuid not null references suppliers(id),
  canonical_name text not null,
  unit           text,
  pack_size      text,
  last_price     numeric(12,3),
  prev_price     numeric(12,3),
  last_price_at  timestamptz,
  created_at     timestamptz not null default now(),
  unique (supplier_id, canonical_name)
);

-- Immutable source evidence: the stored original is never overwritten.
create table documents (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references tenants(id),
  branch_id     uuid references branches(id),
  storage_path  text,
  sha256        text,
  mime          text,
  source        text not null check (source in ('whatsapp', 'upload', 'manual')),
  wa_message_id text unique,
  status        text not null default 'received'
                check (status in ('received', 'processing', 'extracted', 'confirmed', 'failed')),
  created_at    timestamptz not null default now()
);
create index documents_sha256_idx on documents (sha256);

create table invoices (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references tenants(id),
  branch_id    uuid references branches(id),
  document_id  uuid not null references documents(id),
  supplier_id  uuid references suppliers(id),
  invoice_no   text,
  invoice_date date,
  currency     text not null default 'AED',
  subtotal     numeric(12,2),
  tax          numeric(12,2),
  total        numeric(12,2),
  payment_kind text check (payment_kind in ('credit', 'cash')),
  status       text not null default 'draft'
               check (status in ('draft', 'awaiting_confirm', 'confirmed', 'needs_review')),
  confidence   jsonb not null default '{}',
  created_at   timestamptz not null default now()
);
create index invoices_tenant_idx on invoices (tenant_id, created_at desc);

create table invoice_lines (
  id               uuid primary key default gen_random_uuid(),
  invoice_id       uuid not null references invoices(id) on delete cascade,
  position         int not null default 0,
  raw_name         text not null,
  supplier_item_id uuid references supplier_items(id),
  qty              numeric(12,3),
  unit             text,
  unit_price       numeric(12,3),
  line_total       numeric(12,2),
  checks           jsonb not null default '{}'
);

create table supplier_item_prices (
  id               bigserial primary key,
  supplier_item_id uuid not null references supplier_items(id),
  price            numeric(12,3) not null,
  invoice_id       uuid references invoices(id),
  observed_at      timestamptz not null default now()
);
create index supplier_item_prices_item_idx
  on supplier_item_prices (supplier_item_id, observed_at desc);

-- The dedupe + audit spine of the WhatsApp channel.
create table wa_messages (
  id         bigserial primary key,
  message_id text unique not null,
  direction  text not null check (direction in ('in', 'out')),
  from_phone text,
  to_phone   text,
  msg_type   text,
  payload    jsonb,
  status     text not null default 'received',
  created_at timestamptz not null default now()
);

-- Simple Postgres-backed job queue. A broker is banned until volume proves the need (plan §3).
create table jobs (
  id         bigserial primary key,
  kind       text not null,
  payload    jsonb not null default '{}',
  status     text not null default 'queued'
             check (status in ('queued', 'running', 'done', 'failed')),
  attempts   int not null default 0,
  last_error text,
  run_after  timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index jobs_claim_idx on jobs (status, run_after);

-- Deny-all RLS. Supabase exposes the `public` schema through PostgREST, so the anon key
-- (public by design, and embedded in apps/web from M3) would otherwise read and write every
-- table here. No policies yet: the backend connects as the table owner and storage.py uses
-- service_role, both of which bypass RLS. Real tenant policies arrive in M7 (plan §"M7").
alter table tenants              enable row level security;
alter table branches             enable row level security;
alter table suppliers            enable row level security;
alter table supplier_items       enable row level security;
alter table documents            enable row level security;
alter table invoices             enable row level security;
alter table invoice_lines        enable row level security;
alter table supplier_item_prices enable row level security;
alter table wa_messages          enable row level security;
alter table jobs                 enable row level security;
