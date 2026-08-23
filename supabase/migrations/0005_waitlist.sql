-- Public landing-page waitlist.
-- The browser never writes to Postgres directly. The FastAPI service validates
-- and normalizes the address, then inserts through its owner connection.

create table waitlist_signups (
  id         bigserial primary key,
  email      text not null unique,
  source     text not null default 'landing_page'
             check (source in ('landing_page')),
  created_at timestamptz not null default now(),
  check (email = lower(btrim(email))),
  check (char_length(email) between 3 and 254)
);

create index waitlist_signups_created_idx on waitlist_signups (created_at desc);

-- Supabase exposes public-schema tables through PostgREST. No policy is
-- intentional: anonymous clients cannot read or write the waitlist table.
alter table waitlist_signups enable row level security;
