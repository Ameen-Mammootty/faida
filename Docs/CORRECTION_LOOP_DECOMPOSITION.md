# The correction loop decomposition - the extraction layer learns from what it already collects (drafted 2026-09-04)

Status: **DEFERRED 2026-09-04, at the Step 0 scope gate of `/plan-eng-review`.** Not reviewed, not approved, not scheduled.
The review's complexity check triggered (~19 files, two new modules, a C3 provider-protocol amendment) and the founder's call at the gate was to capture the work in `TODOS.md` and defer it. The four review sections - architecture, code quality, tests, performance - **never ran**, so nothing in this file is eng-cleared.
`TODOS.md` §"The correction loop" is the live record and takes precedence; it carries the three Step 0 findings that amend this draft and should be read before anyone picks this up:

1. **§4 WP-90 is overbuilt.** Use two jsonb columns on `extraction_runs`, not a new `extraction_snapshots` table: `extraction_runs` already carries `tenant_id` (`0009:17`), is already in `TENANT_TABLES` (`tests/test_tenancy.py:68`), and has no reader today, so two of this draft's three arguments for a separate table do not survive contact with the code.
2. **§3's contract C12 is partly redundant.** `eval/fixtures/generated/SIGNOFF.json` and `eval/tests/test_signoff.py` already encode a label ladder - a per-case verdict, a named reviewer, a commit, a truth hash. A promoted correction is a third verdict on that ladder, not a new vocabulary. Note also that `test_signoff.py:29` scans `fixtures/generated/` for `truth.json` and asserts the set matches SIGNOFF exactly, which §4 WP-93 must not trip.
3. **§5 P4 is stronger than it was written.** `TODOS.md` already records the same judgement against prompt rules on the EDGE-01 entry - "a prompt rule is the wrong layer - plan.md §5, accuracy is a pipeline property, not a prompt property". That is the repo's own precedent, so the deterministic-first recommendation is not a preference, it is consistency.

The rest of this file stands as the reasoning behind the TODOS entries; its §5 proposals were never put to the founder as written, and P1's split (capture now, use later) is the shape the TODOS entries take.

Plan reference: `plan.md` §5 (the accuracy engine and the eval harness), §2 rule 6 (test the path the user takes) and rule 9 (new scope needs a customer quote - see §5 P3, which confronts it), §7.2 C3 (extraction schema and provider), C8 (provenance), C9 (derived quality), §7.3 (work packages), PRD §25.1 (AI confined to extraction), §26 (audit).

---

## 1. What this is for, in one paragraph

Every time a person fixes a number Faida misread, they hand us the two things a machine-learning loop is built from: proof the model was wrong, and the right answer.
Today we throw both away.
The model's own reading is never written down, so the moment a correction lands the wrong answer is overwritten in place and gone; the audit row records only *that* `lines.3.qty` was corrected, never that the model said 12 and the owner said 16.
The result is an extraction layer with no memory: the two-hundredth invoice from Al Madeena Trading is read exactly as ignorantly as the first, and our only measurement of accuracy comes from ten invoices a prompt invented.
This plan closes that loop - first by *keeping* the evidence, then, separately and only on measured grounds, by *using* it.

---

## 2. What exists today, and what is missing

Facts from the code at `3d22e5b`, so the review argues about the plan and not about the state.

**The model's answer is never persisted.**
`extraction_runs` (`0002_extraction.sql:6-18`) holds `model_id`, `prompt_version`, `input_tokens`, `output_tokens`, `latency_ms`, `repair_applied` and `outcome` - and no column of any JSON type.
The first-pass reading exists in memory as `extracted` in `_persist_extracted` (`extraction/pipeline.py:182`), is used once to attribute the repair round (`changed_fields(extracted, invoice)`, `pipeline.py:268`) and is then discarded when the function returns.
The post-repair reading becomes the `invoices` and `invoice_lines` rows and is thereafter mutable.
The only jsonb columns in the whole schema are `invoices.confidence` (`0001:74`), `invoices.provenance` (`0011:25`), `invoice_lines.checks`, `invoice_lines.cost_basis` (`0013:42`) and `sales_layouts.columns` (`0019:71`). None of them holds a model output.

**A correction is recorded as a fact about *fields*, never about *values*.**
`apply_invoice_correction` writes `detail = {"fields": corrected_fields, "message_id": message_id}` (`db.py:2841`) and, when a payment-kind edit moves the status, `from_status`/`to_status` (`db.py:2843`), then one `invoice.corrected` audit row (`db.py:2848`).
The `update invoices ... set` at `db.py:2790-2798` and the `update invoice_lines` at `db.py:2816-2822` overwrite in place.
So after a correction, nothing anywhere in the system can answer "what did the model read?"

**The before-value is available at the correction seam and is simply not carried.**
`_apply_correction` (`confirm.py:684`) reads the invoice and its lines (`confirm.py:709-710`), builds the pre-edit invoice with `_to_extracted(invoice_row, line_rows)` and applies the edits to it in one expression (`confirm.py:719`).
The pre-edit `ExtractedInvoice` is therefore in hand, at no extra query, at the exact moment the post-edit one is produced.

**One door means one change.** The review screen's `PATCH` and the WhatsApp grammar both run `_apply_correction` (C8, `confirm.py:694-708`), so capturing from/to once covers both surfaces and no third surface can bypass it.

**`corrected_fields` names the keys the *edit mentioned*, not the keys whose value *moved*.**
`corrected = edited_field_keys(edits)` (`confirm.py:739`, defined `confirm.py:459`) is derived from the parsed edits.
`changed_fields(before, after)` (`provenance.py:132`) - which diffs two invoices and is exactly the "what actually moved" function - exists and is used only by the pipeline's repair attribution (`pipeline.py:268`).
Consequence, and it matters for the metric this plan proposes: a person replying "line 2 qty 16" when line 2 already reads 16 currently produces an `invoice.corrected` row naming `lines.1.qty`. Counted naively, no-op edits inflate the model's apparent error rate.

**Provenance records the origin of the current value, not its history.**
`Origin` (`provenance.py:63-72`) is six labels; `READ_ORIGINS` (`provenance.py:76`) and `ASSERTED_ORIGINS` (`provenance.py:81`) are the split C9 propagates. `mark()` (`provenance.py:117`) re-stamps keys and returns a new dict - it never keeps what it replaced.
Provenance is written in four places and **read in one**: a single `select` that returns it for display (`db.py:128`). Nothing aggregates it, and no analytics query touches it.

**The provider seam has no room for a hint.**
`ExtractionProvider.extract(image, mime)` and `.repair(image, mime, targets)` (`extraction/provider.py:28-33`) are the whole protocol.
Prompts are module constants: `SYSTEM_PROMPT` and `EXTRACT_PROMPT` (`extraction/prompts.py`, `PROMPT_VERSION = "v3"`), with `build_repair_prompt(targets)` the one dynamic string.
Any per-supplier prior is therefore a **C3 amendment**, not a local edit.

**The supplier is known from the first pass, before the repair round could use it.**
`match_supplier(suppliers, invoice.supplier_name)` (`pipeline.py:217`) runs at layer 4, *after* `repair_invoice` (`pipeline.py:205`) - but its only input, `supplier_name`, is present the moment layer 1 returns. The ordering is a sequencing choice, not a data dependency.

**The originals are immutable and addressable.**
The worker stores every inbound document at `{tenant_id}/documents/{document_id}/original` with `x-upsert: false` (CLAUDE.md, `worker.py`), so an eval case can point at a real image rather than copy one.

**The eval corpus is synthetic and hand-grown.**
`eval/fixtures/generated/` carries ten scored cases plus five proposed; `truth.json` per case is a full-document answer key. `score_case` (`eval/score.py:207`) scores every field in `HEADER_FIELDS` and `LINE_FIELDS`. There is no notion of a case that supplies truth for *some* fields only. `F6` (real photos, `plan.md:405`) has been "ongoing, not blocking" since 2026-08-23.

**What already learns, and is not in scope here.** The supplier catalog self-builds on confirm, `supplier_items` accumulate, `name_aliases` exist (`db.py:710`), and `record_confirmed_prices` maintains the price baselines. Layer 4 has a working memory. Layer 1 has none. This plan is about layer 1.

---

## 3. The constraint that shapes everything: a correction is a gold negative, a confirm is not a positive

This has to be pinned before any number is computed, or somebody will quote an accuracy figure that means "nobody complained".

- **A correction is gold, per field.** If a person changed `lines.3.qty` from 12 to 16, the model was definitively wrong on that field and we hold the right answer for it. That is a genuine labelled example, and it is the only kind this system can produce.
- **A confirm with no edits is a weak positive.** The person tapped OK. They may never have looked at line 9. It is evidence of *usability*, not of *correctness*, and it must never be scored as truth.

Two consequences the work packages below obey:

1. **Eval cases built from corrections carry partial truth** - the corrected fields and nothing else. A promoted case must not assert that the other forty fields were right.
2. **The headline number is a floor, not an accuracy.** "Fields we marked green that a human later changed" is a *lower bound* on our error rate, because it counts only the errors somebody noticed. It gets reported as such, in the §3-of-CLAUDE.md house style, or not at all.

**Proposed contract, C12 (new): the label ladder.**
`corrected` is gold and per-field. `confirmed_unedited` is unverified and may never be used as ground truth, in the eval harness or in any figure shown to a customer. `founder_verified` (a human sat with the photo and checked every field, as F8 did for the generated corpus) is the only full-document truth. Every stored case names which rung it is on.

---

## 4. Work packages

Numbers continue from M8's WP-86. Sizes: S ≈ half a day, M ≈ 1-2 days, L ≈ 3+.

| # | Work package | Size | Depends on |
|---|---|---|---|
| 90 | **The model's answer is kept.** Migration 0020 adds `extraction_snapshots`: `id`, `tenant_id`, `document_id` (unique), `invoice_id` nullable, `model_id`, `prompt_version`, `first_pass jsonb not null`, `final jsonb not null`, `created_at`. Written inside the same transaction as the draft invoice, from the `extracted` and `invoice` values already in hand at `pipeline.py:260-270`; the manual path (`Origin.MANUAL`) writes no snapshot, because no model read anything. **A separate table, not two columns on `extraction_runs`**, for three reasons: `extraction_runs` is the operational latency/cost record and every query over it would start dragging a payload; a run row exists for `failed`, `not_invoice` and `z_report` outcomes that have no invoice to snapshot; and a snapshot has a lifecycle a run does not - it is promoted, pruned, or anonymised. Tenant-scoped like every other row: `unique (tenant_id, id)`, child FKs composite, added to `TENANT_TABLES` in `tests/test_tenancy.py:56-70` or CI fails. **No route, no screen** - this is a write-only record until WP-92 reads it. | M | - |
| 91 | **A correction records what it replaced.** `_apply_correction` passes the pre-edit invoice (`confirm.py:719`, already built) alongside the post-edit one; `apply_invoice_correction` writes `detail.changes` as `{field_path: {"from": <old>, "to": <new>}}` beside today's `fields` list, which stays for compatibility with existing readers. Money renders as a string, C4-style, never a float. **`changes` is computed with `changed_fields(before, after)` (`provenance.py:132`), not `edited_field_keys`** - a no-op edit produces no entry, so the metric counts errors and not keystrokes, while the provenance stamp keeps using `edited_field_keys` unchanged (a person asserting a value they read off the page is a real change of origin even when the digits match). C8 amendment: *the audit event carries the value it replaced.* | S/M | 90 |
| 92 | **The two numbers exist and get looked at.** `python -m faida_api.quality --since <date>` prints, per week and per supplier: (a) **the silent-wrong floor** - of fields green at persist time, the share a human later changed, joined `extraction_snapshots` → `audit_events.detail.changes`; (b) **the touch rate** - invoices confirmed with zero changes ÷ invoices confirmed, printed under the fixed label *unverified, not accuracy*; (c) volume, token cost per invoice from `extraction_runs`, and the top five corrected field paths. **A CLI and not an endpoint**, deliberately: §2 rule 1 bans an endpoint without the screen that consumes it, this reader is internal, and the ritual that will actually run it already exists - M11's weekly `failed`-document review (`plan.md:1069`). A screen waits for someone asking for one twice. | M | 90, 91 |
| 93 | **Corrections become eval cases.** `python -m eval.promote` turns a correction into a corpus case: the stored original stays where it is and the case references `{tenant_id}/documents/{document_id}/original`, `truth.partial.json` carries **only the corrected field paths**, and `case.json` names the C12 rung. `eval/score.py` grows partial-truth scoring, where *field absent from truth* is skipped and is a different thing from *field present and null* (which still asserts "this should be null") - one new branch in `score_case` (`eval/score.py:207`) and its own test file, because that distinction is exactly where a scorer bug would hide and silently flatter us. Promoted cases live **outside git** by default, under a gitignored `eval/corpus/live/`; nothing enters the tracked corpus without §5 P5's consent answer. | M/L | 91, P5 |
| 94 | **The pipeline uses what it learned - gated on lift, or it does not ship.** A per-supplier read note derived from that supplier's correction history (the field paths corrected most often, with the direction of the fix), injected into **the repair round only**: `build_repair_prompt` grows a notes section, `ExtractionProvider.repair` grows `notes: str | None`, and `extract` is **left untouched**. Three reasons the repair round and not the first pass: the supplier is already identifiable from layer 1's `supplier_name` (`pipeline.py:217`), so nothing needs reordering; the first pass staying byte-identical for every document keeps the eval corpus comparable and makes it impossible for a prior to contaminate a clean read; and repair only fires when something already failed, so the extra tokens land on the invoices in trouble rather than on all of them. Ships **only** if `eval --live` shows lift on cases the notes did not come from, measured per §5's targets and reported with its token-cost delta. No lift, no merge - the branch is deleted and the finding recorded. C3 amendment, narrow: the repair half of the protocol only. | L | 90-93, real corpus, P4 |
| 95 | **The plan and the docs tell the truth about it.** `plan.md` §5 gains a seventh layer describing the loop; the Decision Log records P1-P6 as decided; `CLAUDE.md` and `AGENTS.md` gain one paragraph each on C12's label ladder, identically (the mirror rule); `TODOS.md` receives whatever §5 defers. | S | 90-94 |

---

## 5. Proposals for the founder (each with a recommendation)

**P1 - Split capture from use, and build capture now.**
Capture (WP-90, WP-91) is a **one-way door**: the model's answer is not recoverable after the fact, so every day without it destroys signal permanently, and every correction made since M1 is already gone. Use (WP-94) is fully reversible and can be decided any time once the data exists.
*Recommendation: yes. Build WP-90 and WP-91 immediately, decide WP-94 later on measured data.* They add no route, no screen and no user-visible behaviour, which is why they can run beside M8 without competing with it.

**P2 - Where does this sit in the sequence?**
Options: (a) capture in parallel with M8 Wave 2, use after M11's first real invoices; (b) the whole thing as a milestone between M8 and M9; (c) all of it after the pilot.
*Recommendation: (a).* WP-90 and WP-91 touch the pipeline's persist seam and the confirm door - neither is where M8's sales lanes (WP-81, WP-82) are working, so the collision risk is low and the data starts accumulating during the pilot instead of after it. WP-94 has nothing real to learn from until the pilot supplies volume, so scheduling it now would be scheduling a guess.

**P3 - This scope has no customer quote, and `plan.md` §2 rule 9 requires one.**
The rule says new scope enters the plan only with a customer naming who asked and what they said. No cafeteria owner has asked for this, and none ever will - it is invisible to them.
The honest reading: the rule exists to stop *feature* bloat, and this is measurement and evidence-retention, not a feature. The counter-argument that carries it is P1's - the data is being destroyed continuously and cannot be recovered later. The counter-argument against is equally real: a pre-revenue product with no paying customer spending days on a flywheel is a classic way to feel productive while not selling anything.
*Recommendation: proceed with WP-90 to WP-92 only (roughly two to three days), record it in the Decision Log as a **named exception** to rule 9 with this reasoning attached, and leave WP-93 and WP-94 genuinely gated on the pilot. If the exception cannot be stated in two sentences the founder would defend to an investor, it should not be taken.*

**P4 - Does the pipeline learn in the prompt, or in deterministic rules?**
Prompt priors (WP-94 as written) are AI-native and open-ended, and they are also unbounded and hard to reason about - a note that helps nine suppliers can quietly hurt the tenth, and `plan.md` §2's whole posture is that accuracy is a pipeline property rather than a prompt property. The deterministic alternative expresses the same learning as rules: this supplier's papers are always VAT-inclusive, so the C4 tie-breaker gets a prior; this supplier's `raw_name` corrections become `name_aliases` rows, which layer 4 already reads.
*Recommendation: deterministic first.* Take the corrections that map onto existing machinery - aliases, tax treatment, pack sizes - and let them feed rules with tests. Reserve prompt priors for what no rule can express (layout quirks: "the qty column on this supplier's paper sits third"), and only after WP-92 shows which those actually are. This keeps AI at extraction, per PRD §25.1, and stops the flywheel becoming a second, untestable implementation of the business logic.

**P5 - Customer invoices in the eval corpus: what consent do we have?**
Promoting a real pilot invoice into an answer key means a customer's supplier prices, in a form we keep and score against, potentially in a git repository. We have no clause covering that.
*Recommendation: pointers, never bytes - the case references the stored original in Supabase Storage and no image enters git; promoted cases stay in a gitignored directory until a pilot agreement covers it; and a founder-track item (**F10**) adds one plain sentence to the pilot agreement granting us the right to use their documents to improve extraction accuracy. Blocking for WP-93 only; WP-90 to WP-92 store nothing that is not already in the database.*

**P6 - Does the silent-wrong number get a screen?**
*Recommendation: no, not yet.* A CLI in the weekly review, per WP-92. A dashboard nobody opens is worse than a number in a ritual somebody already performs. Revisit when a second person needs to see it without asking.

---

## 6. Delegation waves

```
Wave 1  WP-90 (snapshot table + write)  ──┐
        WP-91 (from/to on corrections) ──┤ both touch persist/confirm; sequence 90 then 91
                                          │
Wave 2  WP-92 (the CLI, the two numbers) ─┘ reads what Wave 1 wrote
                                            ↓ founder: F10 (the consent sentence), P4/P5 decided
Wave 3  WP-93 (promoter + partial-truth scoring)
                                            ↓ gate: real corpus volume from the pilot
Wave 4  WP-94 (repair-round notes) ── measured against the eval, or deleted
Wave 5  WP-95 (plan, contracts, docs)
```

Wave 1 is two work packages on one branch: WP-91's `changes` payload is only meaningful next to WP-90's snapshot, and splitting them across branches would land a half-loop on master.

---

## 7. The tests that gate it

Per §2 rule 6, these test the path the data takes, not the shape of the code.

- A document extracted and persisted leaves exactly one `extraction_snapshots` row whose `first_pass` round-trips through the C3 schema unchanged.
- An invoice that went through a repair round has `first_pass` ≠ `final`, and the fields that differ are exactly the ones stamped `repaired` in provenance.
- A manually entered invoice (`Origin.MANUAL`) leaves **no** snapshot row.
- A correction of `lines.1.qty` from 12 to 16 writes `detail.changes = {"lines.1.qty": {"from": "12", "to": "16"}}`, and the same correction arriving over WhatsApp and over the review screen produces byte-identical `changes`.
- **A no-op edit ("line 2 qty 16" when line 2 is already 16) writes no `changes` entry, and still re-stamps provenance** - the two halves of WP-91 disagreeing on purpose, each with its own assertion.
- Tenant B's corrections never appear in tenant A's `quality` output; `extraction_snapshots` joins `TENANT_TABLES` and the tenancy matrix passes untouched.
- The silent-wrong floor computed over a seeded fixture set matches a hand-counted expected value - the metric has its own answer key, or it is just a number.
- A promoted case with partial truth scores only its named fields; a case whose truth says `total: null` still fails an extraction that returns a total. (The distinction that WP-93 exists to get right.)
- The CI smoke stays on recorded responses, under five minutes, with no new API key.

**Failure modes, one per new path.** Snapshot write fails → the invoice still persists (the snapshot is evidence, never a gate; same posture as supplier matching at `pipeline.py:221-228`). Snapshot table grows unboundedly → WP-92 reports its size and a retention decision is taken with data rather than guessed now. `detail.changes` on a very large invoice → capped at the corrected fields, which is bounded by what a person typed. A correction whose before-value is itself a correction → `changes` records the immediately preceding value, and the audit table's ordering carries the chain.

---

## 8. Migration and cutover order

One migration, 0020, additive only: a new table, no column changed, no constraint tightened on an existing row.
It follows the M5-M8 precedent - `Docs/apply_correction_loop_migrations.sql` ships in the same commit, pure SQL first byte to last, applied to the live project **before** the code that writes to it merges, with a backup first (`plan.md` Decision Log, D6).
Rollback is `drop table extraction_snapshots`: nothing reads it until WP-92, and no existing path changes behaviour if it is absent - the write is inside a `try` that logs and continues.

---

## 9. NOT in scope, and what already exists

**Not in scope.** Fine-tuning or training any model on this data (nothing here leaves the database, and the provider swap in C3 exists precisely so we ride model improvements instead of owning a model). Retrieval over past invoices at extraction time. Changing the first-pass prompt for anybody. Auto-confirm or any reduction of the human confirm step - that is a separate proposal with a separate risk profile and it must not ride in on this one. A customer-facing accuracy figure. Retention or anonymisation policy beyond WP-92 reporting the size.

**Already exists, do not rebuild.** Supplier matching and item snapping with aliases (`matching.py`, `db.py:710`). Price baselines on confirm (`record_confirmed_prices`). The provenance spine (`provenance.py`) and the audit spine (`_insert_audit_event`, `db.py:189`). The eval harness, its scorer and its CI smoke (`eval/`). Token, latency and outcome capture per run (`extraction_runs`).

---

## 10. Implementation tasks

- [ ] WP-90 migration 0020 + `Docs/apply_correction_loop_migrations.sql`, applied live before merge
- [ ] WP-90 snapshot write inside the persist transaction; `TENANT_TABLES` and the tenancy matrix updated
- [ ] WP-91 `changes` on `invoice.corrected`, computed with `changed_fields`, both doors covered
- [ ] WP-92 `faida_api.quality` CLI; the two numbers with their fixed labels; its own answer key
- [ ] WP-92 hooked into M11's weekly review in `plan.md`
- [ ] F10 the consent sentence in the pilot agreement (founder), gating WP-93
- [ ] WP-93 `eval.promote` + partial-truth scoring + its test file
- [ ] WP-94 repair notes, measured; merged only on lift
- [ ] WP-95 `plan.md` §5 seventh layer, C8/C3 amendments, C12 pinned, `CLAUDE.md`/`AGENTS.md` mirrored, `TODOS.md` updated
