-- 0019: sales, one branch-day at a time (plan.md §8 M8, WP-80; Docs/M8_DECOMPOSITION.md §3 C11).
-- Appended per contract C7; the manager squashes periodically (plan.md §4 policy).
--
-- APPLY THIS BEFORE WP-80 MERGES. Nothing on master reads these tables until
-- WP-80's router, and that router has no screen until WP-84, so either order
-- is safe today; the written order stays migration-first because it is the
-- strictly safe direction (Decision Log 2026-09-01). Docs/apply_m8_migrations.sql
-- is the paste-ready copy with a pre-flight check.
--
-- What M8 adds is one fact per branch per day - what the till took - and the
-- five tables here are that fact, its evidence, and the two bits of memory
-- that make the second upload cheaper than the first:
--
-- 1. `sales_layouts`: which column of a till's export is which, saved once per
--    till under the name the consultant calls it. `columns` maps logical
--    names to header *names*, never positions, so a reordered export applies
--    unchanged and a renamed column stops the file (PRD §10). The header key
--    beside it is compatibility evidence, not identity: two tills with the
--    same column names but a different date order or VAT basis are two
--    layouts (Codex 6).
--
-- 2. `till_items`: every distinct item name the till has ever printed, minted
--    on first sight and mapped to a menu item by a person, one keystroke
--    each, in WP-82 (never automatically - M5's rule). Identity is the till's
--    own code when the file has one and the normalised name otherwise, so a
--    code survives a rename and two products never share one (Codex 7).
--    `excluded_at` marks a name that is not a menu item (a delivery charge,
--    a discount line): it stays in net sales and leaves the mapping queue.
--
-- 3. `sales_daily`: the unit of identity (PRD §13) - unique per tenant,
--    branch and business date. `takings` is the till's figure as printed and
--    `net_sales` the ex-VAT figure derived beside it (C4's shape: stored as
--    printed, derived beside it), with the basis and rate that derived it
--    frozen on the row so a rate change later cannot silently restate
--    history. `granularity` says whether the day carries lines (`item`) or
--    is a summary export's total (`summary`, no coverage). `source_sha256`
--    is the hash of the exact bytes the day came from, computed by the
--    server and stored immutably in Storage under that hash, so a figure on
--    the screen traces to the file for ever; the filename beside it is a
--    label, never identity.
--
-- 4. `sales_lines`: the item-wise rows of an `item` day. The printed name
--    and code on the line are the evidence; the till item is the identity.
--    Nothing stores a menu item per line: the mapping is read through
--    `till_items`, so a remap corrects every day at once. Cascade on the day
--    so a replaced day's lines go with it in one statement and the demo
--    reset stays a delete by tenant.
--
-- 5. `branch_aliases`: the till's own label for a branch ("QUSAIS 1"),
--    taught once and reused by every layout - the chain's fact, not the
--    layout's (outside voice 10).
--
-- Every table is `tenant_id not null` with the redundant `unique (tenant_id,
-- id)` the composite foreign keys need (the 0012 shape), every child key is
-- `(tenant_id, parent_id)`, and RLS is deny-all like every table since 0001:
-- the backend uses the service role; the anon key must never read a till.

-- 1. sales_layouts --------------------------------------------------------------

create table sales_layouts (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references tenants(id),
  -- The till, as the consultant calls it ("Main till"). The layout's identity.
  name         text not null,
  -- The mapped header names, normalised and sorted, joined with "|": the
  -- evidence a file matches this layout. Derived by the server, never sent.
  header_key   text not null,
  -- {"branch": "Outlet", "date": "Date", "item": "Item", "code": "PLU",
  --  "qty": "Qty", "amount": "Amount"} - logical name to header name. A
  --  summary export maps no item column.
  columns      jsonb not null,
  -- Whether the file's amounts carry VAT. Asked once, on the first upload of
  -- this layout, and shown on every preview after.
  amount_basis text not null check (amount_basis in ('inclusive', 'exclusive')),
  -- How a numeric date in this file reads: day-first (25/08/2026) or
  -- year-first (2026-08-25). A date that reads two ways stops its row.
  date_order   text not null check (date_order in ('dmy', 'ymd')),
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  unique (tenant_id, name)
);

alter table sales_layouts add constraint sales_layouts_tenant_id_uidx unique (tenant_id, id);

comment on table sales_layouts is
  'which column of a till''s CSV export is which (M8 WP-80, C11.1): saved once '
  'per till by name, applied by header name, never by position.';

-- 2. till_items -------------------------------------------------------------------

create table till_items (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references tenants(id),
  -- As the till printed it, most recently. A rename under a known code
  -- updates this and keeps the mapping (till_item.renamed).
  name         text not null,
  -- matching.normalize(name): the identity when the till prints no code.
  name_key     text not null,
  -- The till's own item code (PLU), when the export has one. Identity first.
  code         text,
  -- Set by a person in WP-82, never by the loader. Null is "not yet mapped".
  menu_item_id uuid,
  -- "Not a menu item": stays in net sales, leaves the queue. Mapping it
  -- later clears this.
  excluded_at  timestamptz,
  created_at   timestamptz not null default now(),
  -- A till item on another tenant's menu item fails at the write, in
  -- Postgres, whatever the application forgot (the 0012 shape).
  foreign key (tenant_id, menu_item_id) references menu_items (tenant_id, id)
);

-- Identity: code first, name second (C11.7). Partial, so a coded till and
-- an uncoded till each get one row per item and never collide with the
-- other's rule.
create unique index till_items_tenant_code_uidx
  on till_items (tenant_id, code) where code is not null;
create unique index till_items_tenant_name_key_uidx
  on till_items (tenant_id, name_key) where code is null;

alter table till_items add constraint till_items_tenant_id_uidx unique (tenant_id, id);

comment on table till_items is
  'every distinct item name a till has printed (M8 WP-80), minted on first '
  'sight and mapped to a menu item by a person one keystroke at a time (WP-82). '
  'Identity is the till''s code when there is one, the normalised name otherwise.';

-- 3. sales_daily -------------------------------------------------------------------

create table sales_daily (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null references tenants(id),
  branch_id       uuid not null,
  -- The till's own date on the row, as a calendar date. Faida applies no
  -- cutoff arithmetic to a daily export (C11.3); branches.timezone stays unread.
  business_date   date not null,
  -- 'item': the day carries lines. 'summary': a summary export's total, no
  -- lines, no coverage.
  granularity     text not null check (granularity in ('item', 'summary')),
  -- CSV is the only source until a Z-report photo path exists (TODOS.md).
  source          text not null default 'csv' check (source in ('csv')),
  -- How the file's amounts were read, frozen with the rate that derived
  -- net_sales from them: a later rate change restates nothing.
  amount_basis    text not null check (amount_basis in ('inclusive', 'exclusive')),
  vat_rate        numeric(6,4),
  -- The till's figure, as printed: the sum of the lines' amounts, or the
  -- summary row's amount. Signed: refunds and voids are rows that reduce it.
  takings         numeric(12,2) not null,
  -- Ex-VAT, derived per line and summed (an item day equals the exact sum of
  -- its stored lines, to the fil - Codex 10), or derived once for a summary.
  net_sales       numeric(12,2) not null,
  line_count      integer not null check (line_count >= 0),
  layout_id       uuid,
  -- sha256 of the exact bytes the day was loaded from, computed by the
  -- server on POST /api/sales/files and stored under that hash in Storage.
  source_sha256   text,
  -- A label for people. Never identity.
  source_filename text,
  loaded_by       text not null,
  loaded_at       timestamptz not null default now(),
  -- The unit of identity (PRD §13): one consolidated report per branch-day.
  unique (tenant_id, branch_id, business_date),
  -- Branch is resolved from the phone or picked in the loader, never read
  -- from a document; a day on another tenant's branch is refused here.
  foreign key (tenant_id, branch_id) references branches (tenant_id, id),
  foreign key (tenant_id, layout_id) references sales_layouts (tenant_id, id)
);

alter table sales_daily add constraint sales_daily_tenant_id_uidx unique (tenant_id, id);

comment on table sales_daily is
  'what a branch took on one business day (M8 WP-80, C11): takings as the '
  'till printed them, net sales derived beside them with the basis and rate '
  'frozen, unique per branch-day so a re-upload replaces and never doubles.';
comment on column sales_daily.source_sha256 is
  'the exact bytes this day came from, by hash; the file lives in Storage at '
  '{tenant_id}/sales/{sha256}.csv, immutable. Computed by the server, never '
  'the client''s word.';

-- 4. sales_lines -------------------------------------------------------------------

create table sales_lines (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null,
  sales_day_id uuid not null,
  -- The row's order in the file. Data, not decoration: re-upload equality
  -- ignores it (C11.4), the drill shows it.
  position     integer not null,
  till_item_id uuid not null,
  -- The printed name and code on this line: the evidence. The till item is
  -- the identity, and the menu item is read through it, never stored here.
  name         text not null,
  code         text,
  qty          numeric(12,3),
  -- As printed, signed. net_amount is amount / (1 + rate) to the fil when
  -- the day's basis is inclusive, and the amount itself when exclusive.
  amount       numeric(12,2) not null,
  net_amount   numeric(12,2) not null,
  unique (sales_day_id, position),
  -- Cascade: a replaced day's lines go with the day in one statement, and
  -- the demo reset stays a delete by tenant.
  foreign key (tenant_id, sales_day_id) references sales_daily (tenant_id, id) on delete cascade,
  foreign key (tenant_id, till_item_id) references till_items (tenant_id, id)
);

comment on table sales_lines is
  'the item-wise rows of an item day (M8 WP-80): printed name and code as '
  'evidence, the till item as identity, amount as printed and net beside it.';

-- 5. branch_aliases ------------------------------------------------------------------

create table branch_aliases (
  id         uuid primary key default gen_random_uuid(),
  tenant_id  uuid not null references tenants(id),
  branch_id  uuid not null,
  -- matching.normalize(alias): what a file's branch cell is matched on.
  alias_key  text not null,
  -- As the till prints it ("QUSAIS 1"), for the screen.
  alias      text not null,
  created_at timestamptz not null default now(),
  -- One label names one branch, chain-wide: an alias is the chain's fact,
  -- not a layout's.
  unique (tenant_id, alias_key),
  foreign key (tenant_id, branch_id) references branches (tenant_id, id)
);

alter table branch_aliases add constraint branch_aliases_tenant_id_uidx unique (tenant_id, id);

comment on table branch_aliases is
  'the till''s own label for a branch (M8 WP-80, C11.1), taught once in the '
  'loader''s mapping step and reused by every layout.';

-- No further indexes. The reads M8 makes - a tenant's days in a date range
-- with their lines, a tenant's layouts, a tenant's till items - are served
-- by the unique constraints above; a third index ahead of a query that
-- needs it would be the speculation the 0009 policy refuses.

-- Deny-all, per the 0001 convention: Supabase serves `public` over PostgREST,
-- so a table without this is readable with the anon key. The backend uses the
-- service role and is unaffected; tenancy is enforced in the application
-- layer by decision (Decision Log 2026-09-03).
alter table sales_layouts enable row level security;
alter table till_items enable row level security;
alter table sales_daily enable row level security;
alter table sales_lines enable row level security;
alter table branch_aliases enable row level security;
