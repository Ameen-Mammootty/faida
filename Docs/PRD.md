# Cafeteria Profit-Intelligence Platform — MVP PRD (v2)

*Revised from the original "Restaurant Profit-Intelligence Platform" blueprint. This version is scoped for GCC cafeterias and multi-branch karak/paratha chains, priced for an AED 99/branch tier, and built so a non-technical owner and a branch salesman never have to learn software to feed it data.*

**What changed from v1 (summary):**
1. **Users collapsed** to three roles — Tenant, Brand, Branch — instead of five.
2. **Approvals stripped back** to near-zero, with a hard rule: **anything involving cash requires approval.**
3. **Onboarding simplified.** Recipe and menu-engineering setup is a **done-for-you consultant service**, loaded in batches — not a task the customer performs.
4. **WhatsApp is a core ingestion channel**, not an excluded "future assistant."
5. **AI harness simplified** to **one extraction pipeline**. All financial logic is **deterministic algorithms**. Tenants consume results through **dashboards** (and a daily WhatsApp brief), not a conversational agent.
6. **Costing uses latest purchase price**, not moving weighted-average.
7. **Tenancy isolation, row-level security, audit, and secure storage stay in the MVP.** These are non-negotiable foundations.

Everything not explicitly changed below is inherited from v1 and still applies: the append-only inventory ledger, invoice-≠-goods-receipt separation, versioned recipes/costs/calculations, data quality as first-class records, and immutable source evidence.

---

## 1. MVP purpose

The MVP is an intelligence and profit-visibility layer for cafeterias that already use a POS (or none at all).

It ingests sales, menu, recipe, invoice, purchasing, and stock information from **imperfect, real-world, WhatsApp-first sources** and converts it into:

- branch-level sales visibility;
- menu-item contribution analysis;
- ingredient-cost and supplier-price tracking;
- stock visibility and theoretical-vs-physical comparison;
- waste analysis;
- data-quality warnings;
- deterministic, evidence-backed operational signals.

The MVP proves **one** business value:

> A cafeteria can feed its existing operational data — mostly by forwarding supplier invoices and daily sales to a WhatsApp number — and understand which items, ingredients, and branches are helping or harming contribution profit.

The system must stay **honest when data is incomplete**. It must never present an estimate as verified net profit.

---

## 2. Product boundary

### 2.1 What the MVP owns
Tenant/brand/branch configuration; source configuration (incl. WhatsApp senders); imported source documents and records; normalized sales; menu records and mappings; recipe and ingredient records; supplier and supplier-item records; invoice extraction and confirmation; goods receipts; inventory movements; stock counts; waste and transfers; **latest-purchase-price cost snapshots**; recipe-cost and contribution calculations; data-quality status; deterministic analytical signals; dashboards; the daily brief; human confirmation/approval records; audit history.

### 2.2 What remains owned by the POS
The POS stays authoritative for completed sales, receipt identity, timestamps, item sold, quantity, discounts, refunds, voids, tax, payment info, and the POS branch identifier. The MVP imports but never modifies the POS.

### 2.3 What remains human-controlled — **cash-gated, otherwise minimal**

**The rule:** reduce friction everywhere, **except where cash moves**. Cash purchases and cash payments are where money leaks and fraud hides, and they often have no supplier invoice trail — so they require explicit approval with an actor and reason. Everything else is either a light **confirm** (a WhatsApp "OK") or fully automatic with an audit trail.

**Requires formal approval (actor + approver + reason + audit):**
- cash purchases / cash-out to suppliers;
- petty-cash spend;
- manual cost overrides that change a money value;
- unusual stock adjustments that write off cash value (e.g. large write-offs);
- selling-price changes.

**Light confirm only (single WhatsApp "OK" or one dashboard tap):**
- extracted invoice from a known supplier (card/credit/known-account);
- goods-receipt quantity when it matches the invoice.

**Automatic, no human step (audit only):**
- recipe versions and menu mappings **loaded by our consultants** (the consultant is the approving actor by role — the customer does nothing);
- routine stock counts and inter-branch transfers;
- theoretical sales consumption;
- all deterministic calculations.

This removes ~12 of the 14 approval gates in v1 while keeping a hard control on cash.

### 2.4 What the MVP does **not** include
POS replacement; payment processing; live kitchen order management; payroll; tax filing; general ledger; autonomous ordering, pricing, or stock correction; loyalty; full net-profit reporting; complex central-kitchen production; lot-level FIFO; expiry optimization; multi-region infra; enterprise SSO; **unrestricted conversational AI**.

**Moved OUT of the exclusion list (now in scope):**
- **WhatsApp ingestion** — promoted to a core channel (§11).
- **Daily WhatsApp brief** — the primary way owners consume results (§27).

**Deliberately still deferred:** Khata (customer credit ledger) and delivery-aggregator reconciliation remain post-MVP, but are acknowledged as the top two roadmap moats.

---

## 3. Core MVP principles

1. Sales, source documents, confirmed invoices, stock events, and audit records are never silently overwritten.
2. Raw source evidence is preserved (including every WhatsApp image).
3. External data is normalized into provider-neutral records.
4. Transaction-level and summary-level sales are kept separate.
5. Inventory is an **append-only movement ledger**; balances are a projection.
6. Physical stock and theoretical stock are different concepts.
7. Supplier invoice and physical goods receipt are separate records.
8. Recipes, mappings, conversions, costs, and calculations are **versioned**.
9. Tenant and branch isolation is enforced in **every** layer (§26).
10. **All financial calculations are deterministic algorithms.**
11. **AI is confined to the extraction pipeline.** It produces document candidates only — never financial facts, mappings, or postings.
12. Weak data produces weak-confidence results, clearly labelled.
13. **Any cash-related action requires an actor, approver, reason, and audit event.**
14. Imports and jobs are idempotent.
15. The system is a **modular monolith** with background workers.
16. **Cost basis is the latest approved purchase price** (§19).

---

## 4. Users and responsibilities — **three roles**

Collapsed from five roles to three. A cafeteria has an owner and staff, not a finance department.

### 4.1 Tenant user (owner / head office)
The security boundary and top authority. Can: access all authorized branches and brands; view tenant-wide and branch dashboards; review contribution and supplier trends; **approve cash-related items**; approve selling-price changes; manage users; export permitted reports.

### 4.2 Brand user (optional — for groups with multiple brands)
Same as branch scope but across all branches of one brand inside the tenant. Can: view brand-level dashboards; approve cash items for the brand's branches; review brand recommendations. Optional — many tenants will have no brand layer.

### 4.3 Branch user (manager / salesman)
The person on the ground. Can: **forward invoices and sales via WhatsApp** (no login needed for this); review/confirm invoice extractions; confirm goods receipts; perform stock counts; record waste and transfers; **raise cash-purchase entries for approval**; view their branch dashboard.

> Note: the highest-frequency action — feeding an invoice — needs **no role and no login**. It is a WhatsApp forward (§11). Roles only govern the app and approvals.

**Removed from v1:** dedicated Finance/Analyst and Auditor roles. Their read-only and lineage needs are met by the Tenant role's dashboards and the always-on audit trail (§26), which any authorized user can inspect.

---

## 5. Organizational hierarchy

```
Tenant
├── Brand (optional)
├── Branch
└── Inventory Location
```

- **Tenant** — the customer security boundary (one cafeteria, or a 76-branch chain).
- **Brand** — optional grouping; the entity exists to avoid future restructuring even if unused.
- **Branch** — a physical outlet. Has timezone, business-day cutoff, currency, tax config, active status, default inventory location.
- **Inventory location** — stock lives here. MVP starts each branch with one default location; the schema supports more later.

---

## 6. Capability map

- **Identity & tenancy** — tenant, brand, branch, user, memberships, role assignments, branch access, row-level authorization.
- **Source ingestion** — **WhatsApp channel**, POS API (one provider), CSV/Excel, Z-report, PDF/image, manual fallback, import batches, raw-source storage, duplicate detection.
- **Menu & catalog** — canonical menu items, branch menu items, variants, modifiers, selling-price history, external mappings. *(Loaded by consultants — §16.)*
- **Recipes & ingredients** — ingredients, inventory items, recipe versions, components, packaging, unit conversions, completeness. *(Loaded by consultants in batches — §16.)*
- **Suppliers & invoices** — supplier records, supplier-item mappings, invoice upload/extraction, review/confirm, duplicate detection, **latest price history**.
- **Goods receiving** — goods receipts, received quantities, partial receipts, invoice-to-receipt matching, inventory posting.
- **Inventory** — opening stock, purchase receipts, theoretical consumption, waste, spoilage, stock counts, transfers, adjustments, reconciliation.
- **Costing & profitability** — **latest-purchase-price cost**, recipe cost, packaging cost, item contribution, branch contribution estimate, data-quality status.
- **Analytical signals (deterministic)** — menu engineering, supplier price variance, waste impact, stock variance, branch comparison.
- **Extraction pipeline (the only AI)** — document classification + invoice/Z-report extraction + confidence.
- **Dashboards & brief** — tenant/brand/branch dashboards; daily WhatsApp brief.
- **Audit & operations** — audit events, background jobs, outbox, import diagnostics, extraction runs.

---

## 7. High-level architecture

```
Users (Tenant / Brand / Branch)
   │
   ├── WhatsApp (BSP)  ──────────────┐   ← primary ingestion for invoices & sales
   │                                 │
   ▼                                 ▼
Web / Mobile-friendly App        Webhook Receiver
   │                                 │  (verify, dedupe, store raw, enqueue, 200-fast)
   └────────────► Modular Backend API ◄──────────────┐
                     │                                │
     ┌───────────────┼───────────────┬───────────────┤
     ▼               ▼               ▼               ▼
  Ingestion   Menu & Recipe   Documents &      Inventory
   Module        Module     Extraction Pipeline   Module
     │               │               │               │
     ▼               ▼               ▼               ▼
  Costing (latest price) → Deterministic Signals → Dashboards & Brief
     │
     ▼
  Data Quality Module
                     │
   Durable Job Queue ─► Background Workers ─► Vision Provider (extraction only)
                                          ─► POS APIs
   PostgreSQL   Private Object Storage   Cache/Locks   Observability
```

The **only** call to an AI/vision provider is inside the extraction pipeline. Everything downstream — cost, contribution, signals, brief — is deterministic code.

---

## 8. Architecture style

One frontend; one modular backend; one PostgreSQL database; private object storage; one durable job queue; separate background workers; **one extraction pipeline (not a multi-agent harness)**; one observability system. No microservices at start; keep clean module boundaries for later extraction.

---

## 9. End-to-end MVP workflow

```
1  Create tenant, branch(es), default inventory location, business-day config
2  Register branch WhatsApp sender numbers  ← maps phone → branch
3  Connect POS or set up sales upload / Z-report forwarding
4  CONSULTANT loads menu + recipes + costs in batch  ← done-for-you, §16
        │
        ▼
5  Branch forwards supplier invoice to WhatsApp number
6  Extraction pipeline: classify → extract → validate → confidence
7  Reply in-chat: summary + price alerts → "reply OK"  (light confirm)
        │  (cash purchase? → route to approval instead, §21)
        ▼
8  Confirmed invoice → goods receipt → inventory ledger → latest-price cost snapshot
9  Sales import → theoretical recipe consumption
10 Stock counts / waste / transfers recorded
11 Deterministic calculations: recipe cost, item & branch contribution
12 Deterministic signals: menu engineering, price spikes, variance, branch comparison
13 Dashboards update; daily WhatsApp brief sent (template)
14 Human acts on what the dashboard/brief surfaces
```

The customer's only recurring actions are **forward invoices** and **occasionally confirm/approve**. Setup (step 4) is done for them.

---

## 10. Sales ingestion

Four tiers, unchanged in spirit from v1, now with WhatsApp as a delivery method for the photo tiers:

1. **POS API** — one selected provider at MVP; connector framework provider-neutral.
2. **CSV / Excel** — reusable column-mapping templates; layout change stops for review, never silently shifts columns.
3. **Z-report** — classified by granularity (transaction-level / item-summary / branch-summary). **Summary reports must never be turned into fake receipts.** Can arrive as a **WhatsApp photo**.
4. **Manual fallback** — clearly marked `Source: Manual`, with optional attachment and entered-by.

Granularity governs available analytics: only item-level sales support recipe depletion and menu engineering; branch-summary supports revenue only.

---

## 11. WhatsApp ingestion — **core channel**

*Full detail in the companion "WhatsApp Invoice Ingestion" spec. Summarized here as it is now central.*

**Why it's core:** cafeteria↔supplier transactions already happen on WhatsApp. The lowest-friction capture is a **forward to one number** — no app, no login, no navigation.

**Mechanism:** WhatsApp Business Platform (Cloud API) via a **BSP** (prototype on Twilio; scale on 360dialog). Inbound messages hit a webhook.

**The receiver is dumb and fast:** verify BSP signature → dedupe on `message_id` → store raw payload → enqueue job → return `200`. All heavy work happens in a worker.

**Worker flow:** download media promptly (URLs expire) → hash + store original → classify (invoice / Z-report / noise) → resolve branch from **sender phone number** (never guessed from invoice text) → run extraction pipeline → reply in-chat with summary + price alerts → on "OK", post.

**Branch resolution:** known sender → silent; unknown sender → ask once, remember; multi-branch sender (area manager) → ask per invoice.

**The 24-hour window (critical cost & delivery rule):**
- Reactive replies (confirmations, corrections) are **inside** the window → free-form and **free** at Meta's layer.
- The **daily brief** is sent **outside** the window → must be a **pre-approved utility template** (get it approved in the *utility* category, not marketing — far cheaper).

**Cost:** invoice confirmations are free (service messages in-window). The only recurring Meta cost is the daily brief (~1 utility template/day/branch). Net WhatsApp cost lands well under AED 3–4/branch/month — comfortable inside AED 99. *(Verify the live UAE utility rate and whether the BSP per-channel fee is per-platform or per-branch before finalizing.)*

**Security:** every forwarded file is untrusted — size/MIME/malware checks before the vision model; document text is data only, never instructions (§26).

---

## 12–14. Source lineage, idempotency, business day

Inherited unchanged from v1:
- **Source lineage** — every source preserved as `source_document` + `raw_source_record`; normalized records link back. WhatsApp images are `source_document.channel = 'whatsapp'`.
- **Idempotency** — file identity (tenant + type + branch + file hash + period) and message identity (`message_id`) prevent duplicates; exact duplicate skips, corrected version creates a new version, conflict creates a review issue.
- **Business day** — each branch defines timezone, currency, and cutoff; every transaction stores source/UTC/local timestamps + business date. Changing the cutoff never rewrites history.

---

## 15. Menu & catalog

Canonical menu item (e.g. Karak Tea) → branch menu item (availability, branch price, external POS ID) → variants (small/large/family) → modifiers (extra cheese, less sugar; add/remove/replace ingredients, may change price).

**Difference from v1:** menu records are **loaded and maintained by our consultants** during onboarding and updates (§16), not extracted-and-approved by the customer. Menu extraction tooling still exists — but it is a **consultant-facing** tool, not a customer task.

---

## 16. Recipe & menu-engineering onboarding — **done-for-you, batch-friendly**

**This is the biggest onboarding change.** In v1 the customer built recipes through a 7-stage self-service flow — the exact step where non-technical owners drop out. In v2, **our consultants do it for them, in batches.**

**How it works:**
1. During sales onboarding, the customer hands over whatever they have — recipe cards, a spreadsheet, photos, or just "here's how we make karak." Often this is a single conversation.
2. **Our consultants** convert these into structured recipes, ingredients, packaging, and unit conversions using an internal **batch-loading tool** (bulk import + a review grid), applying sensible cafeteria defaults (batch-yield recipes — "one pot → 40 cups" — as the norm, not the exception).
3. Consultants set initial costs from the first supplier invoices.
4. The customer sees finished dashboards. They never touch a recipe form.

**Batch-friendly requirements for the internal tool:**
- Bulk import recipes across many branches/brands at once.
- Templated recipes reused across similar branches (a chain's karak recipe is one template applied to 76 branches, with per-branch overrides only where needed).
- A consultant review grid showing recipe **coverage by sales value** (e.g. "Complete cost coverage: 78% of sales value") so consultants prioritize the highest-impact items first.
- Everything versioned; consultant is the recorded actor.

**Recipe maturity states** (unchanged): Uncosted → Estimated → Partially mapped → Complete → Verified. Reports always show coverage **by sales value**, and clearly label uncosted revenue.

> Menu *engineering* (deciding which items to promote, rework, or drop) is delivered as a **consultant-led insight**, powered by the deterministic signals (§25), not a self-serve analysis the customer runs.

---

## 17–18. Ingredients, inventory items, units

Inherited unchanged:
- **Ingredient** (culinary concept: milk, tea dust) is kept separate from **inventory item** (purchasable, stock-controlled: "Milk powder 2.5kg sack"). One ingredient → many inventory items (multiple suppliers, pack sizes).
- **Units & conversions** — standard units, generic conversions (1kg=1000g), item-specific (1 carton = 10kg chicken), and yield (10kg raw → 8.5kg cooked). Every non-trivial conversion is versioned with source and exact/estimated status. Consultants approve conversions during batch loading.

---

## 19. Costing method — **latest purchase price**

**Changed from v1's moving weighted-average.**

**The rule:** an ingredient's cost = the **price on its most recent approved purchase** (per inventory item, per branch). When a newer approved invoice arrives with a new price, that becomes the cost going forward.

**Why:** it's simple, transparent, and easy to explain to an owner — "your milk costs what you last paid for it." Moving-average requires tracking on-hand quantity and value through every movement, which is heavier to build and harder to explain. For cafeterias buying frequently in small lots, latest price tracks reality closely enough and reacts fast to the price spikes we most want to surface.

**Store per inventory item:**
- latest approved purchase price (the active cost);
- previous purchase price (for the "milk up 40 fils" alert);
- full price history (for trend charts);
- optional manual/estimated cost where no invoice exists yet.

**Trade-off, stated honestly:** latest price is more volatile than a moving average and doesn't value existing stock at blended cost. That's an acceptable simplification for the MVP. **The schema still records quantities and values on the ledger**, so moving-average can be added later as an alternative cost policy **without** replacing any data (§30 evolution).

**Provisional cost** (goods received before an approved invoice): use previous approved price → recalculate when the real invoice arrives, creating a controlled recalculation (versioned).

---

## 20. Invoice ingestion & processing

Sources: WhatsApp photo (primary), uploaded image, scanned/digital PDF, Excel/CSV, manual entry.

Pipeline (single, deterministic-validated — see §25):
```
Capture/forward → validate (type/size/malware) → store immutable original
→ preprocess (rotate/deskew) → extract (vision) → header + line fields
→ suggest supplier & inventory mappings → deterministic arithmetic checks
→ field-level confidence → [human review if low-confidence or cash] → confirmed
→ goods receipt → post to ledger + latest-price cost snapshot
```

**Field-level confidence** is recorded per field (supplier, number, date, qty, unit, pack size, unit price, line/invoice total, tax, mappings). **Material low-confidence fields block posting.** For this audience, "blocked" means **one WhatsApp message with the flagged field to fix** — never a dead end.

**Invoice ≠ goods receipt** (unchanged and important): billed 20 cartons, received 18 → inventory rises by 18. For simple cash purchases one action may confirm both, but they stay separate internally — **and cash purchases require approval (§21).**

**Duplicate detection:** file hash + perceptual image hash + invoice number + line similarity. Potential duplicates go to review; never auto-post.

---

## 21. Approvals — cash-gated model

```
Invoice from known supplier (card/credit/account)
    → light confirm ("OK" in WhatsApp)  → post

Cash purchase / cash payment / petty cash
    → branch user raises entry
    → Tenant (or Brand) approves with reason
    → audit event recorded
    → then post

Selling-price change / manual money override / large write-off
    → requires Tenant approval + reason + audit
```

Rationale: cash is the one place with no external paper trail and the highest fraud/error risk, so it keeps a human gate. Documented supplier invoices carry their own evidence and need only a light confirm. This is the whole of the approval model — there is nothing else to approve.

---

## 22. Inventory ledger

Inherited unchanged — this is core durable architecture:
- **Append-only** inventory events + event lines; balances are a **projection** rebuilt from the ledger.
- Event types: opening balance, purchase receipt, theoretical sale consumption, transfer out/in, waste, spoilage, staff meal, complimentary, count adjustment, manual correction, reversal.
- **Theoretical closing stock** = opening + receipts + transfers-in − theoretical consumption − waste − spoilage − staff meals − complimentary − transfers-out ± approved corrections.
- Theoretical ≠ physical. Stock-count sessions produce variance = physical − theoretical. **Variance is never auto-labelled theft**; it may create an approved adjustment.
- **Double-counting protection:** sales-driven theoretical consumption and manual events must never post the same consumption twice.

---

## 23. Profitability engine — deterministic

All formulas are fixed algorithms, versioned via calculation runs. Cost inputs use **latest purchase price** (§19).

- **Net sales before tax** = gross − discounts − refunds − voids.
- **Ingredient cost** = Σ (recipe component qty × latest-price ingredient cost).
- **Packaging cost** = packaging qty × latest packaging cost.
- **Item contribution** = net item sales − ingredient cost − packaging cost − directly attributable variable fees.
- **Contribution margin %** = item contribution ÷ net item sales.
- **Branch operating contribution estimate** = net branch sales − theoretical ingredient cost − packaging − recorded waste − direct variable fees. **This is not net profit** and must never be labelled as such (labour, rent, utilities, overhead are absent).

Every result belongs to a **calculation run** (formula version, cost-policy version, recipe-resolution version, source watermark) and is **immutable** — recalculation creates a new version. Each result links to its source batches, recipe version, cost snapshot, invoices, and receipts, so "why did this change?" is always answerable.

---

## 24. Data-quality subsystem

Inherited unchanged — this is what keeps the product honest. Issues are first-class records (menu item unmapped, recipe missing/incomplete, invoice total mismatch, supplier item unmapped, pack size unknown, stale stock count, negative theoretical stock, summary-only sales source, etc.), each with severity, business impact, affected result, suggested resolution, and status.

**Report quality statuses:** verified / reliable-with-limitations / estimated / incomplete / unavailable — always shown to the user, e.g. *"Menu contribution: reliable with limitations — 82% of sales value has complete recipe costing; latest stock count is 8 days old."*

---

## 25. The extraction pipeline & deterministic layer — **the only AI**

**Changed from v1's three-agent harness.** v2 has **one** AI pipeline and **everything else is deterministic**.

### 25.1 Extraction pipeline (AI)
A single, bounded pipeline that:
- classifies an uploaded/forwarded document (invoice / Z-report / menu / noise);
- extracts structured field candidates from invoices and Z-reports (vision);
- flags uncertain values with field-level confidence.

It **cannot**: approve anything, post to the ledger, create cost or sales facts, choose a tenant, or execute any financial action. It outputs **candidates**; deterministic code and humans decide.

**Provider abstraction:** the vision call sits behind a thin interface so the model can be swapped in one place. Prompt and model versions are recorded on each extraction run.

### 25.2 Deterministic validation
Fixed algorithms check every extraction: quantity × price = line total; subtotal/tax/total reconciliation; unit-dimension sanity; allowed-currency; known supplier-item consistency; duplicate detection. Failures route to human review.

### 25.3 Deterministic calculation & signals
All costing, contribution, variance, and analytical signals are **defined algorithms** — no model in the loop. Signals include: high-sales/low-contribution items, contribution decline, branch contribution gaps, supplier price spikes, negative/slow-moving stock, high post-count variance, waste concentration.

### 25.4 Dashboards & brief (how tenants consume it)
- **Dashboards** (§27) render deterministic results per tenant/brand/branch.
- **Daily WhatsApp brief** is a **template populated from deterministic numbers** — not a generative agent. Fixed sentence shapes with number slots (e.g. "Yesterday: net sales AED {x}; est. food cost {y}%; {supplier} {ingredient} up {z}").

**Removed from v1:** the Data-Preparation agent (mappings/recipes are now consultant work) and the conversational Profit-Analyst agent (replaced by deterministic signals + dashboards). No agent harness, token budgets, tool allow-lists, or multi-step agent loops in the MVP.

**Fallback:** if the vision provider is down, uploads are still stored, manual entry still works, and all deterministic reports/dashboards remain available. No financial workflow depends on AI being up.

---

## 26. Tenancy isolation, RLS, audit, storage, security — **kept in MVP**

Explicitly retained. These are foundations, not features to defer.

**Multi-tenant isolation:** every tenant-owned row carries `tenant_id`; every branch-owned row carries `(tenant_id, branch_id)`; inventory rows also reference an authorized inventory location. Composite foreign keys prevent cross-tenant references even if application code has a bug.

**Enforcement by layer:**
- **API** — tenant/branch scope comes from the authenticated server context; the client can't choose an arbitrary tenant.
- **Database** — row-level security, composite FKs, tenant-scoped uniqueness, separate DB roles.
- **Background jobs** — every job carries tenant id, branch scope, actor/service principal, correlation id, idempotency key; workers fail if tenant context is missing.
- **Object storage** — private paths (`tenant/{uuid}/documents/{uuid}/original`); authorization checked before signed URLs are issued.
- **Cache** — keys include tenant and branch.
- **Extraction** — deterministic code selects authorized data before any prompt is built; document text can never change system rules or select tenants (prompt-injection protection).
- **Exports** — every export records requester, scope, filters, data classes, expiry, and download history.

**Security requirements:** managed auth; secure password handling; short-lived sessions; MFA for the Tenant role where feasible; role-based access; RLS; secret manager; encrypted transport and storage; malware scanning on every uploaded/forwarded file; signed download URLs; audit events; session revocation; invitation expiry.

**Audit model:** audit events record actor, tenant, branch, action, resource, previous/new value, reason, timestamp, source, approval state, correlation id. **Audited actions:** invoice confirmation, invoice correction, **every cash approval**, recipe load/change (consultant), mapping change, stock-count approval, stock adjustment, transfer confirmation, selling-price change, role change, export request, support access.

---

## 27. Dashboards & the daily brief

### 27.1 Tenant / owner dashboard
Yesterday's net sales (tenant-wide and per branch); contribution estimate + completeness; **branch league table** (which branch has the best/worst food-cost % this week — the hero view for chains); top-performing and popular-low-margin items; major supplier cost changes; inventory warnings; pending cash approvals; data freshness.

### 27.2 Brand dashboard
Same, scoped to one brand's branches.

### 27.3 Branch dashboard
This branch's sales, contribution, invoices needing confirm, stock counts due, high variance, waste concentration.

### 27.4 Daily WhatsApp brief
A templated utility message each morning to the owner (and optionally each branch manager): net sales, estimated food-cost %, biggest supplier price move, and one flagged issue. Tapping through opens the dashboard. This is the primary consumption surface for a non-tech owner who will never open a BI dashboard unprompted.

---

## 28. Onboarding — simplified

**Customer-facing onboarding is minimal.** Most setup is done for them.

**Customer does (minutes, guided):**
1. Confirm tenant, branches, timezone/business-day, currency.
2. Register branch WhatsApp sender numbers (phone → branch).
3. Point us at sales: connect POS, or start forwarding Z-reports.
4. Hand over recipe/menu info in whatever form they have.

**We do (consultant-led, batch):**
5. Batch-load menu, recipes, ingredients, packaging, conversions (§16).
6. Set initial costs from first invoices.
7. Prioritize recipe coverage by sales value.
8. Turn on dashboards + daily brief.

The customer's steady state after onboarding is: **forward invoices, confirm the occasional item, approve cash purchases, read the brief.**

---

## 29. Minimum database blueprint (delta from v1)

Keep v1's schema for identity, sales, menu, recipes, suppliers/invoices, inventory, costing, data quality, and audit. **Changes:**

**Add (WhatsApp channel):**
```
whatsapp_senders            (tenant_id, branch_id?, phone_number, default_branch_id,
                             is_multi_branch, verified_at)
whatsapp_messages           (tenant_id, message_id UNIQUE, from_phone, direction,
                             message_type, media_id, source_document_id,
                             classification, window_expires_at, status)
whatsapp_pending_confirmations (tenant_id, branch_id, source_document_id,
                             extracted_summary, awaiting_since, resolved_by_message_id)
whatsapp_templates          (name, category, meta_status, body, variables)
```

**Add (consultant batch loading):**
```
recipe_import_batches       (tenant_id, consultant_actor, template_ref, status, coverage_pct)
```

**Change (costing):**
```
cost_policies               → default = 'latest_purchase_price'
inventory_cost_snapshots    → store latest_price, previous_price (+ history)
                             (quantity/value columns retained on the ledger for
                              a future moving-average policy, unused for now)
```

**Simplify (AI):**
```
Keep:   extraction_runs, prompt_versions, model_policies
Remove: agent_runs, agent_tool_calls  (no multi-agent harness in MVP)
```

**Keep entirely:** `audit_events`, all tenancy/RLS structures, `source_documents`, `raw_source_records`, `outbox_events`, `job_runs`, `processed_event_keys`.

**Roles:** collapse role tables/enums to `tenant` / `brand` / `branch`.

---

## 30. Delivery phases (re-sequenced)

The goal: **something demoable to a chain in weeks, not quarters.** Foundations stay, but we cut vertically so value appears early.

**Phase A — Foundation (kept, lean)**
Tenancy, three roles, RLS, audit, object storage, queue, workers, observability.
*Done when:* Tenant A can't touch Tenant B's data/files/jobs; audit fires on privileged actions; files are private.

**Phase B — WhatsApp + invoice extraction (the wedge)**
BSP integration; webhook receiver (dedupe, 200-fast); media storage; classifier; branch resolution; extraction pipeline + deterministic validation; in-chat confirm; **cash-purchase approval path**.
*Done when:* a forwarded supplier photo comes back parsed with a price alert, and "OK" records it; a meme gets a polite reply and costs nothing; cash purchases route to approval.

**Phase C — Sales ingestion**
One POS connector; CSV/Excel; Z-report photo; manual fallback; transaction/item/branch-summary handling; dedup; business-day.
*Done when:* duplicate imports don't duplicate sales; summaries aren't turned into fake receipts; granularity governs analytics.

**Phase D — Consultant menu/recipe loading**
Internal batch-loading tool; templated recipes with per-branch overrides; conversions; coverage-by-sales-value grid; latest-price costs from first invoices.
*Done when:* a chain's menu+recipes load across all branches from one template set; coverage is visible; customer touched no recipe form.

**Phase E — Inventory ledger**
Opening stock, receipts, theoretical consumption, waste, transfers, stock counts, variance, adjustments, reversals, balance projection.
*Done when:* balances reproduce from the ledger; consumption isn't double-counted; variance is auditable.

**Phase F — Profitability (deterministic)**
Latest-price cost snapshots; recipe cost; item & branch contribution; calculation runs + lineage; quality status; recalculation.
*Done when:* every result is versioned and reproducible; incomplete data lowers confidence; contribution is never labelled net profit.

**Phase G — Dashboards, signals & daily brief**
Deterministic signals; tenant/brand/branch dashboards incl. branch league table; daily WhatsApp brief template (submitted for Meta utility approval early).
*Done when:* dashboards render deterministic results; the brief sends as an approved utility template outside the 24h window; model downtime doesn't disable reports.

*Phases B–C are demoable to a customer on their own — that's the meeting asset.*

---

## 31. Final MVP definition

The MVP is complete when a cafeteria (single shop or multi-branch chain) can:

1. Have a tenant, brands, and branches created with secure isolation.
2. Register branch WhatsApp numbers (phone → branch).
3. **Forward supplier invoices to one WhatsApp number** and have them parsed, price-checked, and confirmed with a single "OK."
4. Route **cash purchases** through a lightweight approval.
5. Connect a POS or forward Z-reports for sales.
6. Have **menu, recipes, and costs loaded for them by consultants** in batch — touching no recipe form.
7. Get ingredient and recipe costs on **latest purchase price**.
8. See item and branch **contribution**, with completeness clearly labelled.
9. See **deterministic signals** and a **branch league table** on a dashboard.
10. Receive a **daily WhatsApp brief** of the numbers that matter.
11. Trace any value back to its source evidence (image, invoice, recipe version, cost snapshot).
12. Operate with enforced tenant/branch isolation, RLS, audit, and private storage.
13. Reprocess and recalculate without duplicating or corrupting data.

---

## 32. Final architecture statement

The durable core is unchanged from v1:

```
External sales → canonical menu items → versioned recipes
→ ingredients & inventory items → supplier invoices (WhatsApp-first)
→ goods receipts → inventory movements → latest-price cost snapshots
→ deterministic contribution → deterministic signals → dashboards + daily brief
→ human action (cash-gated)
```

The most valuable part is not the AI model. It is the **trusted operational graph** connecting sales, recipes, inventory, purchasing, costs, and branches — fed frictionlessly through WhatsApp, set up for the customer by consultants, and read back deterministically. AI sits at exactly one point — reading documents — and never replaces the ledger or the deterministic financial engine.