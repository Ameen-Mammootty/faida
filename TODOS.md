# TODOS

Deferred work with its reasoning intact. Anything here was considered and consciously
not built; nothing enters this file without a reason someone can argue with later.

## Backend (apps/api)

### Catalog pack size and unit are written once and never corrected

**What:** Update `supplier_items.unit` and `supplier_items.pack_size` when a later invoice
prints a value and the stored one is blank.

**Why:** The columns are filled the first time a product is ever seen and never touched again.
`db.py:569` re-sets only the name on conflict - `on conflict (supplier_id, canonical_name) do
update set canonical_name = excluded.canonical_name` - and the insert does not run at all for a
line that snapped to an existing product. So if the first invoice a product appeared on had a
blank or misread pack-size column, the catalog carries that blank forever, however clearly every
later invoice prints it. The price-history screen reads those columns, so it shows the stale value.

**Context:** Found during the M5 plan review on 2026-08-29 (`/plan-eng-review`, Issue 4). M5
deliberately routes around it rather than depending on it: costing, the pack-dimension check and
the unreadable-pack queue all read `invoice_lines.pack_size` from the newest confirmed line, which
has a photo behind it. That is why this is deferred rather than fixed - the fix is about two lines
of SQL (`coalesce` the stored value with the incoming one on the conflict clause), but it adds a
write to the confirm transaction, which is the shipped M0-M4 demo path, for a column M5 no longer
reads. Not worth the regression risk during the milestone whose one hard constraint is not
regressing that path.

It gets more interesting later in two places: M8's purchases roll-up may want a catalog-level pack
size, and at pilot scale the first invoice a product ever appears on is often the worst photo
anyone ever sends - exactly the one whose reading gets frozen.

**Effort:** S
**Priority:** P3
**Depends on:** None. Independent of every M5 work package.

### VAT is applied at invoice level, so a mixed-rate invoice produces wrong ex-VAT unit costs

**What:** Decide whether C4 should capture a per-line tax basis, or whether an invoice with mixed or
zero-rated lines should refuse to produce a cost at all.

**Why:** `db._net_price_factor` derives one factor from the invoice's own `tax` and `total` and
applies it to every line. That is correct when every stock line carries the same rate, which is the
normal GCC case. It is wrong when an invoice mixes rates or carries zero-rated lines: each line's
ex-VAT unit price comes out plausible and slightly false, and from M5 that flows into a cost per kilo
and from M6 into a plate margin, with nothing downstream able to see it.

**Context:** Raised by the Codex outside voice during the M5 plan review on 2026-08-29 (finding 13).
Deliberately not fixed in M5 for one reason: this is not a new M5 defect. The same invoice-level
factor already governs `supplier_items.last_price` and has since WP-17 shipped on 2026-08-23, so
changing it is an amendment to contract C4 - manager-only, through the Decision Log - and not a
work-package decision. It also needs a real example before it is worth designing against: no invoice
in the phase-1 corpus mixes rates, and the phase-2 real corpus (F6) is the place such an invoice
would first appear. The cheap interim answer, if one is wanted before then, is C9-shaped rather than
arithmetic: refuse to call a cost anything better than *estimated* when the invoice's lines do not
all share one basis.

**Effort:** M
**Priority:** P3
**Depends on:** A real mixed-rate invoice in the corpus (F6, phase 2). A C4 amendment decision.

### Pack sizes are corroborated by nothing; corroborate them across invoices

**What:** Let a cost earn a *verified* label by checking the pack size against the same supplier's
previous invoices for the same product, rather than never claiming verification at all.

**Why:** C4's arithmetic cross-checks the unit price (`qty × unit_price = line_total`) but pack size
appears in no identity, so nothing anywhere corroborates it. A 25kg misread as 2.5kg passes every
check the pipeline has. M5 handles this honestly by never labelling a cost *verified* - but "honest
about knowing nothing" is weaker than actually checking, and the evidence needed is already sitting
in `supplier_item_prices` and the invoice lines behind it.

**Context:** Raised as the stronger option during the M5 plan review on 2026-08-29 (eng review
tension 5, option B) and consciously deferred. It only starts working once a supplier has billed the
same pack twice, so on a new tenant it would read unverified for weeks regardless - which makes it an
upgrade for when price history exists, not a thing to build alongside the first cost. Start at
`matching._pack_tokens` and the price-history query; the comparison is the one `units.same_pack_size`
already implements.

**Effort:** M
**Priority:** P3
**Depends on:** M5 shipped, plus enough repeat-purchase history to compare against.
