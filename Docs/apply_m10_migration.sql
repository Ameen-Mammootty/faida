-- Faida: migration 0022 alone, for a live project already at 0020.
--
-- Adds the table that holds who receives the morning WhatsApp brief
-- (`brief_recipients`) and the unique index that makes one brief per
-- recipient per day a rule the database keeps rather than a flag the worker
-- remembers (`jobs_send_brief_uidx`).
--
-- HOW TO USE THIS FILE
--   Open it, select all, copy, paste into the Supabase SQL editor, run once.
--   Every byte of this file is SQL. There is nothing in it to select wrongly.
--
-- THIS ONE ADDS AND DELETES NOTHING. No column is dropped, no row is
--   rewritten, and the build running today ignores both the table and the
--   index. So the order does not matter here the way it did for 0020: this
--   can be run before the deploy or after it, and redeploying the previous
--   build with the table in place is a complete rollback. A backup is still
--   a minute well spent, and Supabase's dashboard has the button.
--
-- WHEN TO RUN IT
--   Any time before the WP-103 deploy. After the deploy the worker's tick
--   runs, finds an empty table, and enqueues nothing - which is the safe
--   state, and why BRIEF_ENABLED is left unset (true). The first brief is
--   sent only once a recipient row exists, which is the commented insert at
--   the bottom of this file, and only after Meta has approved the template.
--
-- BEFORE YOU RUN IT
--   Run the check below on its own first. All four columns must come back as
--   shown; anything else means stop and read the note beside it.
--
--   select exists (select 1 from information_schema.tables
--                  where table_name = 'supplier_aliases')     as has_0020,
--          exists (select 1 from information_schema.columns
--                  where table_name = 'recipe_components'
--                    and column_name = 'usable_share')        as has_0021,
--          exists (select 1 from information_schema.tables
--                  where table_name = 'brief_recipients')     as has_0022,
--          now() at time zone 'Asia/Dubai'                    as dubai_now;
--
--   has_0020    true   (false: the project is behind 0020 - run
--                       Docs/apply_wp87_migration.sql first)
--   has_0021    either  is fine. 0021 is M12's yields column and has nothing
--                       to do with the brief; the two migrations are
--                       independent and either may land first.
--   has_0022    false  (true: already applied; the run below would fail on
--                       `create table`)
--   dubai_now   a timestamp that reads like the time in Dubai right now.
--               This is the same lookup the recipient's timezone name gets:
--               if this errors, the database does not know the name, and the
--               row at the bottom must not be pasted with it. (A fresh
--               database with no tenants table at all needs the full
--               migration set in supabase/migrations/, not this file.)

begin;

create table brief_recipients (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references tenants(id),
  phone_e164    text not null,
  timezone      text not null default 'Asia/Dubai',
  send_at_local time not null default '07:00',
  paused_at     timestamptz,
  created_at    timestamptz not null default now(),
  unique (tenant_id, phone_e164)
);

comment on table brief_recipients is
  'who receives the daily WhatsApp brief (M10 WP-103): the phone, its '
  'timezone and the local hour the morning is. State only - who asked for '
  'it, when and on what evidence is the brief_recipient.added audit row '
  'written in the same transaction (C8).';

alter table brief_recipients enable row level security;

create unique index jobs_send_brief_uidx
  on jobs (kind, (payload->>'recipient_id'), (payload->>'brief_date'))
  where kind = 'send_brief';

comment on index jobs_send_brief_uidx is
  'one send_brief job per recipient per local day (C15.3). WP-103''s '
  'enqueue_brief_once inserts against it with on conflict do nothing.';

commit;

-- Verify: the table exists with row security on, it is empty, and the index
-- is there. Expected: one row reading `brief_recipients | t`, a count of 0,
-- and one row naming `jobs_send_brief_uidx`.
select relname, relrowsecurity
  from pg_class
 where relname = 'brief_recipients';

select count(*) as recipients_now from brief_recipients;

select indexname from pg_indexes where indexname = 'jobs_send_brief_uidx';

-- ---------------------------------------------------------------------------
-- THE RECIPIENT ROW - not part of the migration, and not to be run yet.
--
-- Run this only after Meta has approved the template (§8 step 5), and only
-- with the owner's own request in hand: a WhatsApp message from that phone
-- asking for the brief, or a signed line on the onboarding sheet. The
-- evidence goes into the audit row's detail, because nobody here can
-- manufacture an owner's consent to a daily message about their money
-- (P14). For the founder's own phone the evidence is the founder's own
-- decision, and the line below says so.
--
-- The insert and its audit row are one statement on purpose: the row and the
-- record of who added it, on what evidence, commit together or not at all -
-- which is what `db.add_brief_recipient` does from the code side (C8).
--
-- Fill in three things: the tenant, the phone (digits only, no '+', the way
-- branches.wa_phone_e164 is written), and the actor. Then uncomment and run.
--
--   with added as (
--     insert into brief_recipients (tenant_id, phone_e164, timezone, send_at_local)
--     values ('00000000-0000-0000-0000-000000000001',  -- the tenant
--             '971500000000',                          -- the phone, digits only
--             'Asia/Dubai',
--             '07:00')
--     returning id, tenant_id, phone_e164, timezone, send_at_local
--   )
--   insert into audit_events (tenant_id, actor, action, subject_type, subject_id, detail)
--   select tenant_id,
--          'whatsapp:971500000000',                    -- who decided
--          'brief_recipient.added',
--          'brief_recipient',
--          id,
--          jsonb_build_object(
--            'phone_e164', phone_e164,
--            'timezone', timezone,
--            'send_at_local', to_char(send_at_local, 'HH24:MI'),
--            'evidence', 'the founder''s decision of 2026-09-08, M10 P14')
--     from added;
--
-- Read it back, and check the morning it implies:
--
--   select r.phone_e164, r.timezone, r.send_at_local, r.paused_at,
--          (now() at time zone r.timezone)::date as its_local_date,
--          (now() at time zone r.timezone)::time as its_local_time,
--          a.actor, a.detail->>'evidence' as evidence
--     from brief_recipients r
--     left join audit_events a
--       on a.subject_type = 'brief_recipient' and a.subject_id = r.id
--      and a.action = 'brief_recipient.added';
--
-- To stop that recipient without deleting anything:
--
--   update brief_recipients set paused_at = now() where phone_e164 = '971500000000';
--
-- To stop every send at once, without SQL: BRIEF_ENABLED=false on Railway.
