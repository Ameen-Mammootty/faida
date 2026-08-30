-- 0015: the menu and its recipes, every version of them kept (plan.md §7.3 M6, WP-60).
-- Appended per contract C7; the manager squashes periodically (plan.md §4 policy).
--
-- M6 invents no new numbers: every price inside a plate cost is M5's derivation
-- read as-is, and every quantity here is typed by a named consultant. So this
-- schema's whole job is to keep what the consultant typed, keep every version
-- of it, and refuse the shapes that would later divide by zero or cost an empty
-- set as a perfect margin.

create table menu_items (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references tenants(id),
  name          text not null,
  -- What the owner says out loud, VAT inside it (GCC menu prices are displayed
  -- inclusive; WP-61 margins against the net and says so in words). numeric,
  -- never float (C4); fils precision, like every price column.
  selling_price numeric(12,3) not null check (selling_price > 0),
  -- Archive is the reverse gear, never deletion: recipes hang off this row and
  -- audit rows name it, so removal has readers. An archived item leaves the
  -- ranking and the coverage count and one click brings it back.
  archived_at   timestamptz,
  created_at    timestamptz not null default now()
);

-- One live "Karak" per tenant. Partial, so archiving an item frees its name
-- for a successor while the archived row keeps its history.
create unique index menu_items_tenant_name_uidx
  on menu_items (tenant_id, name) where archived_at is null;

-- Redundant for uniqueness (id is the primary key) and required as the target
-- of the composite foreign keys below - the 0012 shape: Postgres will only
-- reference a unique constraint over exactly the referenced columns.
alter table menu_items add constraint menu_items_tenant_id_uidx unique (tenant_id, id);

-- Recipes are append-only version rows. "Versioned" is a property of the
-- schema, not a subsystem: the current recipe is the newest version, the
-- history is the table itself, and editing writes a whole new version without
-- touching an old one. No immutability trigger - the first SQL-resident logic
-- in the codebase would be against §2; the unique constraint plus the
-- byte-identical test carry the promise.
create table recipes (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null,
  menu_item_id   uuid not null,
  version        integer not null check (version >= 1),
  -- The batch yield, as the norm ("one pot -> 40 portions", PRD §16): a bare
  -- positive divisor plus display text. "cups" would be illegal one column
  -- over, and nothing may ever convert against the label (eng review D18).
  yield_portions numeric(10,3) not null check (yield_portions > 0),
  yield_label    text,
  created_at     timestamptz not null default now(),
  -- Two concurrent saves compute the same max+1 and the second fails loudly
  -- here instead of minting the same version twice (eng review D17).
  unique (menu_item_id, version),
  -- Tenancy enforced by the database, not by a code path remembering to check
  -- (the 0012 shape). Null-free on both sides, so there is no unmapped state.
  foreign key (tenant_id, menu_item_id) references menu_items (tenant_id, id)
);

alter table recipes add constraint recipes_tenant_id_uidx unique (tenant_id, id);

create table recipe_components (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null,
  recipe_id     uuid not null,
  -- Order on the card. Also what re-upload equality compares against
  -- order-insensitively (WP-64), so it is data, not decoration.
  position      integer not null,
  ingredient_id uuid not null,
  -- The consultant's converted number. Positive by constraint: a negative
  -- quantity would silently subtract cost from a plate (the door refuses it
  -- with a sentence; this is the backstop). Four decimals because per-portion
  -- draws of spice are real: 0.006 g of saffron in one cup of karak.
  qty           numeric(14,4) not null check (qty > 0),
  -- As typed ("kg", "g", "ml"). The door refuses a unit units.py cannot
  -- convert to the ingredient's base unit; kitchen measures ("cup", "tbsp")
  -- are deliberately absent from that dictionary because a karak cup is a
  -- serving vessel, not a measure (PRD §16).
  unit          text not null,
  -- The card's own words ("1 cup"), kept beside the converted number. A recipe
  -- quantity has no photo and no arithmetic behind it; the source words are
  -- the only audit anyone will ever have (PRD §17-18).
  source_text   text,
  unique (recipe_id, position),
  foreign key (tenant_id, recipe_id) references recipes (tenant_id, id),
  -- A component on another tenant's ingredient fails at the write, in
  -- Postgres, whatever the application forgot (the 0012 shape).
  foreign key (tenant_id, ingredient_id) references ingredients (tenant_id, id)
);

comment on table recipes is
  'append-only recipe versions (M6 WP-60): the current recipe is the newest '
  'version, the history is the table. Every write lands one audit_events row '
  'naming its actor.';
comment on column recipes.yield_portions is
  'the batch divisor: one pot of this recipe makes this many portions. WP-61 '
  'divides the summed component cost by it, once.';
comment on column recipe_components.source_text is
  'the recipe card''s own words for this line, kept beside the consultant''s '
  'converted number - the only audit a typed quantity will ever have.';

-- No further indexes. The reads M6 makes - all current versions with their
-- components in one query, per tenant - are served by the unique constraints
-- above ((menu_item_id, version) and (recipe_id, position)); a third index
-- ahead of a query that needs it would be the speculation the 0009 policy
-- refuses.

-- Deny-all, per the 0001 convention: Supabase serves `public` over PostgREST,
-- so a table without this is readable with the anon key. The backend uses the
-- service role and is unaffected; M7 owns real tenant policies.
alter table menu_items enable row level security;
alter table recipes enable row level security;
alter table recipe_components enable row level security;
