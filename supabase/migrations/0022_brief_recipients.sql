-- 0022: who gets the morning brief (plan.md §8 M10, WP-103).
-- Appended per contract C7; the manager squashes periodically (plan.md §4 policy).
--
-- Additive - one table and one index, both of which the build before this one
-- ignores. So this may be applied ahead of the deploy and a code rollback with
-- the schema in place is complete; dropping the table is the reverse paste.
-- Docs/apply_m10_migration.sql is the paste-ready copy with its pre-flight.
-- The number is fixed against M12's 0021_usable_share.sql, which is
-- independent of this one: either may land first (plan.md §7.3).
--
-- WHY A TABLE. The only phone the schema knew until now is
-- branches.wa_phone_e164 - the *sender* a branch forwards invoices from
-- (0001:15). An owner's phone is the other direction, and nothing held it:
-- `tenants` has four columns and `memberships` a bare Supabase user id with
-- no phone (0018:57-64). Two columns on `tenants` would hold one owner; a
-- chain with two partners, which is the ordinary case, needs rows (P2).
--
-- STATE ONLY. The row says where a brief goes, in which timezone, at what
-- hour, and whether it is paused. It says nothing about consent, because a
-- decision belongs in audit_events with its actor, its time and the evidence
-- behind it: `brief_recipient.added` is written in the same transaction as
-- the row and its detail names what the owner's request was (C8 extended,
-- P14). Pausing is `paused_at`, never nulling the phone - a phone nulled to
-- stop a message loses which number the owner had asked for.
--
-- THE TIMEZONE IS THE RECIPIENT'S, not the branch's and not the server's. A
-- tenant with two recipients in two timezones has two mornings (C15.5), and
-- the local date this row implies is the `today` the brief's read is made
-- for (C15.6). Python resolves the name with zoneinfo and logs and skips a
-- row whose name does not resolve, so one typo cannot silence the others -
-- the paste file checks the name against the database before the row exists.

create table brief_recipients (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references tenants(id),
  -- Digits only, no '+', exactly as branches.wa_phone_e164 is written and as
  -- Meta reports a sender (demo_seed.sql:562-570), because the resolver
  -- compares this column with that one against the same inbound phone.
  phone_e164    text not null,
  -- An IANA name, the branches' own default (0001:16).
  timezone      text not null default 'Asia/Dubai',
  send_at_local time not null default '07:00',
  -- Set to stop this one recipient without touching anything else; the
  -- per-recipient half of the BRIEF_ENABLED kill switch (C15.5).
  paused_at     timestamptz,
  created_at    timestamptz not null default now(),
  -- One row per phone per tenant: adding a number twice is the same
  -- recipient, not a second morning.
  unique (tenant_id, phone_e164)
);

comment on table brief_recipients is
  'who receives the daily WhatsApp brief (M10 WP-103): the phone, its '
  'timezone and the local hour the morning is. State only - who asked for '
  'it, when and on what evidence is the brief_recipient.added audit row '
  'written in the same transaction (C8).';

alter table brief_recipients enable row level security;

-- One brief per recipient per local day, whatever its status - the 0018
-- shape (jobs_extract_document_uidx), and for the same reason: "once, ever"
-- is a constraint the database holds, not a flag Python remembers. A second
-- tick, a second API instance or a restart mid-tick inserts against this and
-- gets nothing. db.enqueue_brief_once is the one door that writes it.
create unique index jobs_send_brief_uidx
  on jobs (kind, (payload->>'recipient_id'), (payload->>'brief_date'))
  where kind = 'send_brief';

comment on index jobs_send_brief_uidx is
  'one send_brief job per recipient per local day (C15.3). WP-103''s '
  'enqueue_brief_once inserts against it with on conflict do nothing.';
