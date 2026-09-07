# Faida Demo Runbook (four acts; M4 loop gate, M6 demo gate, M8 act three, M9 act four)

This is the operating manual for the demo (plan.md §6) and for the rehearsals before its two gates.
Since 2026-08-28 the full demo is two acts and gates at M6 (§1: the loop, then materials and menu margins).
**Act one** (sections A-E) is the invoice loop on WhatsApp and stands on its own as the M4 loop gate: it runs end to end twice in a row with zero intervention before anything is built on its numbers.
**Act two** (section F, added 2026-08-31 by WP-66) is the screens - materials, then menu margins, closing on "push this, fix that".
**Act three** (section G) is the branches, and **act four** (section H, added 2026-09-05 by WP-95) is the dashboard: what the chain kept, the dish that sells and does not earn, and what one delivery did to both.
Every reply quoted below is the exact template from `apps/api/src/faida_api/replies.py`, so if the phone shows different words, something is wrong.
Since WP-125 (2026-09-07) every reply about a paper arrives as a WhatsApp quoted reply above that invoice's photo, with the supplier and total in bold and the closing line last; the blank lines in the blocks below are part of the message.

> **What gates and what only rehearses.** The staged menu in `supabase/demo_seed.sql` exists so act two can be practised today, on a laptop, without waiting on anything. It is **not** what the milestone closes on: M6's done-when ("one real menu loads in under a day of consultant time") and the demo gate both close on F7's real menu, loaded through `/menu/load`. Rehearse on the seed; gate on the real one.

## A. Preconditions checklist

Run through this list the day before, and again 30 minutes before going on.

- [ ] The API is deployed and healthy: `curl https://<host>/health` returns `{"ok":true,"db":true}` (README §M0 has the troubleshooting table).
- [ ] The worker is on: Railway variable `WORKER_ENABLED=true` (without it the ack and extraction never run).
- [ ] The Meta webhook points at the Railway host: WhatsApp → Configuration → Webhook shows `https://<host>/webhook`, verified, subscribed to the `messages` field.
- [ ] **The app is subscribed to the WABA.** This is separate from the webhook config above and the dashboard never mentions it; without it Meta records forwards and delivers nothing.

      ```bash
      curl -s "https://graph.facebook.com/v26.0/<WABA_ID>/subscribed_apps" \
        -H "Authorization: Bearer $META_ACCESS_TOKEN"
      ```

      Your app must appear in the list, not only Meta's `WA DevX Webhook Events 1P App`. Re-subscribe with the same URL and `-X POST`.
- [ ] **The access token does not expire**, verified rather than assumed. A mid-demo expiry looks like total silence on the phone, with no error visible anywhere on stage.

      ```bash
      curl -s "https://graph.facebook.com/v26.0/debug_token?input_token=$TOKEN&access_token=$TOKEN" \
        | python3 -m json.tool     # expires_at: 0
      ```

      Anything other than `0` is a clock running against the demo. The dashboard's Step 1 button issues 24-hour tokens that expire on a fixed boundary, so a token generated in the afternoon can die the same evening.
- [ ] The demo phone(s) are registered as recipients on the Meta test number and have confirmed the code.
- [ ] `GEMINI_API_KEY` is set on Railway (the shipped model is Gemini 3 Flash since
      2026-08-29; with the key missing, every invoice gets the failure reply). If falling back
      to Opus (`EXTRACTION_PROVIDER=anthropic`), `ANTHROPIC_API_KEY` must be set instead.
- [ ] **The provider account has credit/billing enabled**, checked at the provider's console
      (Google AI billing for Flash; console.anthropic.com Plans & Billing when on the Opus
      fallback), with headroom for the whole session. Found the hard way in rehearsal
      2026-08-29: a drained balance presents as the failure reply after ~70 s - three retries
      of a 400 - while every other dashboard looks healthy. There is no low-balance warning
      anywhere in our system.
- [ ] The stage is reset (see section C for which file): `supabase/demo_seed.sql` on a practice database, `supabase/demo_reset_loop.sql` on the real stage. Never `demo_seed.sql` on the real stage - it deletes the loaded menu, and it now refuses to run when it sees one.
- [ ] The founder phone is mapped to the demo chain: the commented UPDATE at the bottom of `supabase/demo_seed.sql` has been run once, so the sender resolves to Al Qusais Branch of Karak Al Khaleej Cafeterias.
- [ ] Signed in on the demo laptop as the founder's account (Supabase Auth, email and password; sign-ups are off, accounts are created in the dashboard and given a `memberships` row). **A sign-in now lands on `/dashboard`, not on the invoice list** (WP-93), so click **Invoices** in the nav to run the rest of this check. The invoice list for the demo chain carries no rehearsal leftovers - on the practice stage that means empty; on the real stage it means only the KAS-1..4 preparation purchases and the chain's own real invoices, nothing from a previous run of the props (DEMO-1..3, KAS-5). The list hides dismissed rows by default, so open `/invoices?status=dismissed` as well: a dismissed leftover passes the eye test and still needs the reset.
- [ ] **Every till name is on its own dish** (§H's preconditions have the read-back): the §C5 sitting found one on a lookalike, and the screen cannot see it.
- [ ] The right papers are on the demo phone, first in the gallery: on the practice stage, the 3 curated invoice photos and the meme; on the real stage, **KAS-5** and the meme (KAS-1..4 were confirmed once during preparation and are not forwarded again - a re-forward trips the duplicate hold).
- [x] **Act three's week is loaded and its layout saved** (added 2026-09-04, WP-85; the screen
      built 2026-09-05, WP-84; loaded once at the §C4 sitting, 2026-09-05 - done). On the real stage, `Docs/demo-invoices/koukh-al-shay/sales-week.csv`
      was uploaded once at `/sales/load`: the mapping walked, the three till labels
      (`AL QUSAIS`, `AL NAHDA`, `ROLLA`) taught as aliases, the layout saved as "Main till" -
      and `/sales` shows Al Qusais at **30.3%** against KAS-3 and KAS-4 with the other two
      branches reading *incomplete - no confirmed purchases 25-31 Aug*. On the practice stage,
      regenerate `sales-week-practice.csv` (`build_sales_week.py --practice`; it reads the
      seed's own purchase dates) and upload it after every `demo_seed.sql` run, because that
      reset clears the week; the loop reset spares it. **The demo's sales are invented; its
      purchases are not; the screen's honesty claim is about the second.**
- [ ] **One warm-up forward before going on.** On the Opus fallback this is load-bearing: the
      first request after a schema change pays a server-side grammar compilation measured in
      minutes (155 s observed 2026-08-28) - run `apps/api/.venv/bin/python -m eval.schema_probe`
      (needs `ANTHROPIC_API_KEY`). Gemini's raw-JSON-schema path has shown no such compile
      penalty, but the principle stands on any engine: never let the on-stage forward be the
      day's first request - forward one throwaway invoice, verify the reply, delete it.
- [ ] Phone details: full battery, full signal or stage wifi, notifications from every other app silenced.

Staged catalog quick reference (from `supabase/demo_seed.sql`):

| Item | Staged last price | Demo invoice price | Expected alert |
|---|---|---|---|
| Milk Powder 2.5kg | 50.50 | 54.50 | up AED 4.00 |
| Karak Tea Dust | 22.00 | 18.75 | down AED 3.25 |
| Evaporated Milk 400ml | 90.00 | 96.00 | up AED 6.00 (backup invoice 2) |
| Sugar 50kg, Cardamom Powder 500g, Chakki Atta Flour 25kg | stable | unchanged | none |

Curated invoice 1 (Gulf Foods Trading LLC, 2 lines, total AED 745.76) is the on-stage invoice.
Invoices 2 (Al Madina Trading) and 3 are rehearsal and backup material.
What every curated paper must print (the reply echoes these, so they are part of the script):
a distinct invoice number per paper (the same supplier + number + total sent twice is HELD as a duplicate since 2026-08-28 - correct in production, wrong on stage);
a printed date (the reply now reads it out as "dated 20 Aug 2026" - printing it day-first, like 20/08/2026, quietly demos the date reading);
AED amounts; credit terms or no terms line at all.
**The printed date must be fresh - within the last three weeks, and newer than the chain's newest confirmed purchase of the same materials (ideally the demo week itself).**
Costing and the money moment rank purchases by the printed date, not by when the confirm happened, so a prop that has aged past the purchase evidence slots in as history: the plates never move after the on-stage confirm, or the callout reads "down" while the phone just said "up".
The staged purchase evidence sits 35 and 28 days back to give the props four weeks of headroom, but a curated paper is a prop with a shelf life - re-print it when it goes stale.
Curate credit invoices only: an invoice marked cash gets the cash-hold closing ("⏸️ Marked cash, so it needs the owner's approval before it's recorded...") instead of "Reply *OK* to confirm.", and OK will not confirm it from chat.

## B. The 4-minute script

The script from plan.md §6 M4, verbatim: forward invoice, reply appears with price alert, "OK", open review screen with photo beside data all green, show the sparkline for the item that moved, forward a meme, polite decline, close on the no-app line.

> **Which paper, which stage.** On the practice stage the forward is curated invoice 1 (DEMO-1) and the replies below are its exact words. On the real stage the forward is **KAS-5** (`Docs/demo-invoices/koukh-al-shay/README.md` has its read-out): the same beats with its own numbers - three alerts fire (evaporated milk and milk powder up, chicken **down**, worth pointing at) and fresh milk stays deliberately silent. DEMO-1..3 are tuned to the staged catalog and are dead props on the real stage: DEMO-1's printed date (20/08/2026) is older than KAS-3's preparation purchase (25/08/2026), and costing ranks by the printed date, so its confirm would not move a single plate there (§A's freshness rule).

1. Open WhatsApp on the demo phone with the chat to the Faida number already on screen.
2. Say: "This is a supplier invoice from this morning's delivery. Watch what the salesman does with it."
3. Forward curated invoice 1.
4. Within a couple of seconds the ack arrives, quoted above the photo: `Got it - invoice received and saved. I'll reply with the details here soon.`
5. Now extraction runs, which takes roughly 10-15 seconds on Gemini 3 Flash (9.5 s average
   model time on the corpus; the Opus-era measurement was 13.3-17.2 s end to end); do not
   stand in silence.
6. While waiting, say: "It is reading the photo now: every line item, every price, and checking that the math on the page actually adds up. No typing, no app, and it compares every price against what this cafeteria paid last week."
7. The parsed reply arrives, exactly, quoted above the photo (the invoice number and date are whatever invoice 1 prints, the date read out in words; the supplier and total render bold; the blank lines are part of the message):
   ```
   ✅ Read it
   *Gulf Foods Trading LLC*
   Invoice INV-1041 · 20 Aug 2026 · 2 lines
   Total *AED 745.76*

   *Price moves since your last purchase*
   📈 Milk Powder 2.5kg up AED 4.00 (50.50 to 54.50, +7.9%)
   📉 Karak Tea Dust down AED 3.25 (22.00 to 18.75, -14.8%)

   Reply *OK* to confirm.
   ```
8. Point at the price-moves lines and say: "That is the money moment: milk powder went up four dirhams, nearly eight percent, and the owner knows before the invoice is even filed."
9. Reply `OK`.
10. The confirmation arrives, quoted above the photo, in three lines: `✅ Confirmed` / `*Gulf Foods Trading LLC*, AED 745.76 recorded.` / `I'll watch these prices for you.`
11. Open the review screen: the invoice photo sits on the left, the extracted fields on the right, every field green with its check icon.
12. Open the Milk Powder 2.5kg sparkline: three weeks of gentle drift, then today's jump to 54.50.
13. Back in WhatsApp, forward the meme and say: "And when someone sends it nonsense?"
14. First the same ack arrives (`Got it - invoice received and saved. I'll reply with the details here soon.`), then after the read, the decline, exactly and quoted above the meme: `That doesn't look like a supplier invoice, so I'll leave it - forward an invoice photo and I'll read it.`
15. Say: "It refuses politely instead of inventing numbers. That discipline is why you can trust the numbers it does record."
16. Close on the plan's line: "no app, no login, no training - the salesman already knows how to do this." Then go straight into **act two (section F)** without changing rooms: the screens are already open in the same browser.

## C. Reset between rehearsals

Two stages, two reset files - and running the wrong one on the real stage destroys the real menu, which is why `demo_seed.sql` refuses to run when it sees one (added 2026-08-31).

**Practice stage** (a laptop database the seed staged entirely, including the five-item menu):

```bash
psql "$DATABASE_URL" -f supabase/demo_seed.sql
```

This restores the complete staged state, however messy the last run was: it deletes every rehearsal trace for the demo chain (documents, invoices, lines, messages, jobs, runs, confirm-created catalog rows, appended price history, menu edits, **and the loaded sales week with its layout, aliases and till-name mappings**) and re-stages everything; it cannot touch any other tenant, and it preserves the branch phone mapping. The week goes back in through `/sales/load` from a regenerated `sales-week-practice.csv` (§A).

**Real stage** (F7's menu loaded through `/menu/load` - the live demo project):

```bash
psql "$DATABASE_URL" -f supabase/demo_reset_loop.sql
```

This removes only what a rehearsal creates - the props' documents, invoices, lines, runs, messages and jobs, and the price observations their confirms appended - then recomputes every pack's baseline from the purchases that survive, so the alerts re-arm.
It works by scope: rehearsal residue is any demo-chain invoice printing one of the props' fixed numbers (DEMO-1 `GFT-2026-0834`, DEMO-2 `AMT-26-1187`, DEMO-3 `GFT-2026-0871`, KAS-5 `AMT-26-1274`), so the loaded menu, its materials, every mapping, and the KAS-1..4 preparation purchases - which share suppliers with the props on purpose - are out of reach by construction.
It never touches the five sales tables: the loaded week, its layout, its aliases and its till-name mappings are consultant work, and removing KAS-5's invoice is exactly what puts Al Qusais's ratio back to its before-the-stage figure (act three step 4 in reverse).
Regenerating a prop with a new number means updating the list in that file in the same commit.
`demo_seed.sql` must NEVER run against the live project once the real menu is loaded - its reset would delete the menu, its 82 materials and every mapping.

`$DATABASE_URL` is the same session-pooler URI Railway uses (README §M0 step 2).
Run the reset after EVERY rehearsal run, confirmed or not (this got stricter 2026-08-28): confirming moves `last_price` to 54.50 so the alert will not fire again, and even without confirming, re-forwarding the same paper now trips the duplicate hold (WP-44) - the second copy is held with "⏸️ Already recorded" and the earlier paper's name instead of being read out. Both are correct product behavior and both ruin a rehearsal that expected the full reply.
Rehearsal images stay in the storage bucket; that is intended, since originals are immutable and nothing references them after the reset.

Re-check after the reset:

1. `select last_price, prev_price from supplier_items where id = 'd0000000-0000-0000-0000-000000000101';` returns `50.500 | 49.750`.
2. `select name, wa_phone_e164 from branches where tenant_id = 'd0000000-0000-0000-0000-000000000001';` still shows the founder phone on Al Qusais Branch.
3. `curl https://<host>/health` returns `{"ok":true,"db":true}`.
4. The review screen's invoice list for the demo chain carries no rehearsal leftovers (§A's wording: empty on the practice stage; only preparation purchases and real invoices on the real one).
5. Practice stage only: `select count(*) from menu_items where tenant_id = 'd0000000-0000-0000-0000-000000000001';` returns `5`, and `/menu` shows four costed items with Paratha in the "can't be costed yet" section (act two's staged state, section F). On the real stage, `/menu` shows the loaded menu unchanged - a loop reset that altered any menu number is a bug.
6. `select count(*) from sales_daily where tenant_id = 'd0000000-0000-0000-0000-000000000001';` returns `21` on the real stage after the loop reset (it never touches the week) and `0` on the practice stage after `demo_seed.sql` (re-upload the practice week, §A). `/sales` shows Al Qusais back at its before-the-stage ratio once KAS-5's invoice is gone.

## C2. One-off: adopting the repriced papers (founder's call 2026-09-01)

Run this ONCE, before the performance, and never again. It is not part of the rehearsal loop.

**Why.** The KAS papers confirmed on the live project carry the first draft's prices - boneless chicken at AED 3.45/kg - and `/menu` answers with chicken curries at 89% margin. `build_prompts.py` now holds researched UAE wholesale prices with a source and a date per line (`Docs/demo-invoices/koukh-al-shay/price-research-2026-09.md`). Adopting means redoing the preparation against the new papers: the old purchases have to go, because costing ranks by printed invoice date and the old and new KAS-1..4 print the *same* dates.

**What survives, by construction:** the 45-item menu, its recipes, the 81 materials, and every one of the 79 mappings a human approved. Only the four preparation purchases and their price history go. Verified on a local replica before this was written, including the part that matters - re-forwarding the new papers re-snaps all 81 lines onto their **original** mapped catalog rows and mints nothing new.

```bash
# 0. Take a backup first. This deletes confirmed invoices.
pg_dump "$DATABASE_URL" > ~/faida-before-reprice-$(date +%F).sql

# 1. Clear rehearsal residue first (idempotent; scoped to the props' numbers).
#    Order matters: baselines below are recomputed from surviving history, so a
#    KAS-5 left confirmed would be re-armed as though it were preparation evidence.
psql "$DATABASE_URL" -f supabase/demo_reset_loop.sql

# 2. Clear the old preparation purchases.
psql "$DATABASE_URL" -f supabase/apply_kas_reprice.sql
```

Between step 2 and step 3, `/menu` will honestly read every item as *incomplete* - the materials have no costed purchase behind them yet. That is the correct intermediate state, not a fault.

```
# 3. From the demo phone, forward and confirm the four NEW papers, in order:
#      KAS-1.png  KAS-2.png  KAS-3.png  KAS-4.png
#    Each reads back and each needs an "OK". KAS-5 stays for the stage.
```

Re-check before you call it done:

1. `select count(*) from menu_items where tenant_id = 'd0000000-0000-0000-0000-000000000001';` still returns the loaded menu's count - a repricing that changed it is a bug.
2. `select count(*) from supplier_items where tenant_id = 'd0000000-0000-0000-0000-000000000001' and ingredient_id is null;` returns the same number it did before you started. A jump means a line minted a new catalog row instead of snapping, and that material is now unmapped.
3. `/menu` shows every item costed again, and the ranking is the researched one: the karak delivery cups sit at the bottom around 17-26%, not 49-58%.
4. `select last_price from supplier_items where tenant_id = 'd0000000-0000-0000-0000-000000000001' and upper(canonical_name) = 'CHICKEN BONELESS';` returns `180.000`.
5. Then rehearse the two-act script twice, clean, exactly as the M6 gate required - the gate was passed on the old numbers, and its evidence is stale until it runs on these.

If step 3 shows unmapped materials, the fastest repair is `/materials`: the proposals are still there and each is one keystroke. Nothing is lost.

## C3. One-off: the M7 cutover (2026-09-03)

Run this ONCE, outside demo hours. It is the sitting where the old shared token dies: Railway deploys every merge to master, so merging WP-70's branch is the moment the API stops accepting it, and the screen is dark until the web deploy that follows. Everything below it was prepared in advance (plan.md Progress Log, 2026-09-03).

Before the sitting, all already true: migration 0018 live; the project on JWT signing keys with the ES256 key Current and the legacy secret untouched; sign-ups off; the founder's and a QA account created and confirmed, each with a `memberships` row on the demo chain; the two Supabase values set on Vercel Production; a real access token from the live project verified against the local API on the branch.

```bash
# 1. Backup.
pg_dump "$DATABASE_URL" --no-owner --no-privileges -f ~/faida-before-cutover-$(date +%F).sql
# 2. Merge WP-70's branch into master and push. Railway deploys; from this moment the old token is refused.
#    The WhatsApp path is unaffected throughout.
# 3. Deploy web from master.
cd apps/web && vercel --prod --yes
# 4. On the deployed screen: sign in, forward one paper from the demo phone, walk both acts.
# 5. Remove NEXT_PUBLIC_API_TOKEN from Vercel and API_TOKEN from Railway; they are dead variables now.
```

Rollback, independent on each host and one click each: Railway redeploys the previous build; Vercel promotes the previous deployment. Neither touches the database, and 0018 is harmless to the previous code.

**Ran 2026-09-03, 19:20 to 21:30 local, no rollback needed.** Backup `~/faida-before-cutover-2026-09-03-1920.sql`; merge `304eeec`; Railway up at 19:24 (old token 401, a fresh token 200); web deployed, sign-in page live; the founder signed in, forwarded KAS-5 and confirmed it in 18 s; the money moment on the reloaded screen; both dead variables removed. §E row 5 is that run.

## C4. One-off: the M8 go-live (WP-86)

Run this ONCE, outside demo hours, with the founder: it is the sitting that puts the sales screen and the demo week on the real stage. Nothing in it migrates the database (0019 has been live since 2026-09-04) and nothing touches the API (every M8 route has been on Railway since the Wave 1 and Wave 2 merges of 2026-09-04), so the only deploy is the web.

Pre-flight, run 2026-09-05 (plan.md Progress Log), all true: the five sales tables exist on the live project and are empty for the demo chain (0 days, 0 layouts, 0 aliases, 0 till names); Al Qusais carries KAS-1..4 confirmed (newest printed 25 Aug) and nothing pending, the other two branches nothing; Vercel Production carries every variable the screen needs (the two Supabase values, the API base, mock off) and its newest deployment is the M7 cutover of 2026-09-03; master builds clean (`next build`; 184 web tests, 738 API tests); the live API answers `/health` ok with the database reachable and every sales route 401 without a token (probed 2026-09-05 from the host recorded in the session memory, not in the repo). The committed week has 46 till names, one of them DELIVERY CHARGE.

```bash
# 1. Backup - cheap, and the 0017 lesson.
pg_dump "$DATABASE_URL" --no-owner --no-privileges -f ~/faida-before-m8-live-$(date +%F).sql
# 2. Deploy the web from master. The API needs nothing.
cd apps/web && vercel --prod --yes
# 3. Sign in on the deployed screen. /sales reads "No sales loaded yet." with the one link to the loader.
# 4. Load the week at /sales/load from Docs/demo-invoices/koukh-al-shay/sales-week.csv. First upload, so the
#    mapping step: Outlet / Date / PLU / Item / Qty / Amount, VAT-inclusive, day first, till name "Main till";
#    the three labels AL QUSAIS, AL NAHDA, ROLLA taught as aliases; "Load 21 days" -> 21 loaded, 0 replaced,
#    0 unchanged; "See the branches".
# 5. /sales: Al Qusais 30.3%, reliable with limitations, 2 deliveries; Al Nahda and Rolla incomplete, "no
#    confirmed purchases 25-31 Aug"; the total incomplete. Open Al Qusais; KAS-3 drills to its photo.
# 6. The queue: one keystroke per till name (CHKN 65 DRY proposes; B/CHKN needs P); DELIVERY CHARGE -> X.
# 7. Act three in full (section G) with KAS-5 forwarded from the demo phone: reload, 39.3%, 3 deliveries.
# 8. The loop reset (supabase/demo_reset_loop.sql), then the read-backs below: the week survives, KAS-5 is
#    gone, Al Qusais is back at 30.3%.
```

Read-backs, against the live project, after step 8:

```sql
select count(*) from sales_daily    where tenant_id = 'd0000000-0000-0000-0000-000000000001';  -- 21
select count(*) from sales_layouts  where tenant_id = 'd0000000-0000-0000-0000-000000000001';  -- 1
select count(*) from branch_aliases where tenant_id = 'd0000000-0000-0000-0000-000000000001';  -- 3
select count(*) as names, count(menu_item_id) as mapped, count(excluded_at) as not_menu
  from till_items where tenant_id = 'd0000000-0000-0000-0000-000000000001';                   -- 46, the mapped, 1
```

Then the record, in one commit: this file's §A week box ticked and §G's **[WP-84]** markers dropped, plan.md's four M8 boxes, its §1 line and Progress Log, and the M8 line in README, CLAUDE.md and AGENTS.md if the sitting changed anything they say.

Rollback: Vercel promotes the previous deployment, one click. The week's rows are data on tables nothing older reads, so they can stay either way.

**Ran 2026-09-05, afternoon, no rollback needed.** Backup `~/faida-before-m8-live-2026-09-05.sql`; CI green on `8a557f2`; web deployed at 16:0x local, `/sales` answering with a redirect to sign-in where it had answered 404. The founder signed in and loaded the week; the first pass loaded 14 days because the alias question for `AL NAHDA` was answered with Al Qusais Branch, so both outlets' rows landed in Al Qusais's days (92 lines a day instead of 46) - caught by the read-back, fixed by deleting the one alias row in SQL (there is no screen door for a wrongly taught alias) and re-uploading the same file: the loader asked the branch question again, offered the seven Al Qusais days as a shrinking replace with a tick each, and answered "7 loaded, 7 replaced, 7 unchanged". Read-backs: 21 days, 322 lines a branch, takings 75,540.00 equal to the file's footer, Al Qusais net 30,267.43. The screen: Al Qusais 30.3% reliable with limitations, two deliveries, the other two incomplete; the 46 till names mapped one keystroke each (45 mapped, DELIVERY CHARGE not a menu item, one audit row each), costed 100.0%. KAS-5 forwarded from the demo phone and confirmed; the reloaded screen read **39.3%** with three deliveries and AED 11,899 of purchases, the other rows untouched. The loop reset ran; the read-backs after it: 21 days and 75,540.00 intact, the layout, the three aliases and the 46 mappings intact, KAS-5 gone, Al Qusais back at 30.3% with two deliveries. §E row 6 is that run. One finding for `TODOS.md`: a wrongly taught alias has no way back on the screen.

## C5. One-off: the M9 go-live (WP-96)

Run this ONCE, outside demo hours, with the founder: the sitting that closes M9 on the real stage. Nothing in it migrates the database (the dashboard adds no table; 0020 had been live since the morning of 2026-09-07) and nothing deploys (both hosts served master at `64f9793` before the sitting), so it is a read-back sitting: the live screen against the figures `act_four.py` prints, one paper forwarded, one reset.

Pre-flight, run 2026-09-07 (plan.md Progress Log), all true: `/health` ok with the database up; `GET /api/dashboard` answers 401 to no token; the three branches carry 7 loaded days each, 25-31 Aug (Al Qusais 30,267.43, Al Nahda 23,066.47, Rolla 18,608.45; 71,942.35 net over 966 lines); KAS-1..4 confirmed on Al Qusais and no KAS-5, which is what the loop reset leaves; the menu 45 live items, 82 ingredients, 68 recipes; 1 layout, 3 branch aliases, 46 till names (45 mapped, DELIVERY CHARGE not a menu item). `act_four.py --stage real` ran against a throwaway local database first, so every figure below was printed before anyone looked at the screen.

```bash
# 1. Read-only pre-flight: /health, the 401, the counts above (psql on the pooler URL, read-only).
# 2. The figures: act_four.py --migrate --database-url postgresql://localhost:5432/faida_act_four --stage real
# 3. GET /api/dashboard on the live host with a real token, diffed against the script's first read - BEFORE the screen
#    is looked at. A disagreement here is the stage, not the code (§H's preconditions list the three causes).
# 4. The founder signs in on a laptop wider than 1280 px and lands on /dashboard: read back the two sentences, the
#    four tiles and the whole league without scrolling.
# 5. Act four (§H) on the live screen: the filter (?branch=), the drill to a photograph, the price-moves panel
#    (empty before the paper).
# 6. KAS-5 from the demo phone, OK from the chat, reload: the after figures; the seconds from wa_messages.
# 7. The loop reset (supabase/demo_reset_loop.sql), then the read-backs below: the week and the dashboard intact.
```

Read-backs, against the live project, after step 7:

```sql
select count(*), sum(net_sales) from sales_daily where tenant_id = 'd0000000-0000-0000-0000-000000000001'; -- 21, 71942.35
select invoice_no, status from invoices where tenant_id = 'd0000000-0000-0000-0000-000000000001'
  order by invoice_date, invoice_no;                                                             -- KAS-1..4 only, confirmed
select count(*) from menu_items where tenant_id = 'd0000000-0000-0000-0000-000000000001'
  and archived_at is null;                                                                       -- 45
select count(*) from sales_layouts  where tenant_id = 'd0000000-0000-0000-0000-000000000001';  -- 1
select count(*) from branch_aliases where tenant_id = 'd0000000-0000-0000-0000-000000000001';  -- 3
select count(*) as names, count(menu_item_id) as mapped, count(excluded_at) as not_menu
  from till_items where tenant_id = 'd0000000-0000-0000-0000-000000000001';                   -- 46, 45, 1
```

and `GET /api/dashboard` byte-identical to the read taken in step 3.

Then the record, in one commit: this file's §H in the compact screen's words with the panel added, §E's row, plan.md's M9 boxes, its §1 line, row 96 and both logs, `TODOS.md`, and the M9 line in README, CLAUDE.md and AGENTS.md if the sitting changed anything they say.

**Ran 2026-09-07, evening, no rollback needed.** Step 3 caught one thing before the screen was looked at: the live read listed **44 costed** items where the script has 45, the chain kept **AED 47,240.78 at 66.1%** where the script says 47,020.76 at 65.8%, and *Coffee Milk - Flask 1 L* sat in the best five on 51 flasks and AED 2,676 of sales. The till name `COFFEE MILK FLASK 2L` had been mapped to the 1 L flask at the §C4 sitting - a keystroke, not the matcher, which proposes the 2 L flask first for that name (0.976 against 0.927) - so 51 two-litre flasks were costed at the 1 L plate. The founder fixed it on the live `/sales` screen through the shipped door: *Mapped names*, **Unmap**, then the queue's top proposal; two audit rows in the founder's name at 18:11:12 and 18:11:27 local. The live read then matched the script **to the fil**: the sentence, the league (15,028.97 / 12,148.63 / 19,843.16; the chain 47,020.76 at 65.8%), the best and worst five, both signals (406.29 and 245.64), 45 costed. The screen at 1366x768, signed in: the two sentences, the four tiles (AED 71,942; 12.7% Incomplete on AED 9,163; AED 47,021 keeping 65.8%; 100.0%), the league at 65.7 / 65.8 / 66.0 / 65.8 with its total row ending at 608 of 768, both signals, the panel reading "No price moves in this window.", no console errors, no sideways scroll. The filter: `?branch=` in the URL, Al Nahda's tiles with the chain named beside ("chain 12.7%", "chain 65.8%"), the sentence "Al Nahda keeps about AED 66 of every 100 it takes". The drill: the small delivery karak opened in place to its eight lines, "Invoice line 1, 25 Aug 2026" on the evaporated milk landing on AMT-26-1203 with the photograph beside the figures and line 1 highlighted - two clicks from the dashboard to the paper. KAS-5 from the demo phone: received 18:13:08.9, the ack 18:13:16.6, the read-out 18:13:24.7 (**15.8 s** from forward to reply, zero repair), OK 18:13:47.9, the confirmation 18:13:53.5 (5.5 s). The reload: **AED 46,909 keeping 65.7%**, Al Qusais 19,797 at 65.8% and 39.3%, the chain's ratio 16.5% on AED 11,899, four signals with three shown and "Show all 4" (403, 244, 26, 1), the panel with three moves (evaporated milk up AED 0.83 per litre, AED 26 at stake; chicken, boneless down AED 1.25 per kg, AED 11 saved; milk powder up AED 1.06 per kg, AED 1), 45 costed, the small karak at AED 116 and 16.6% with its milk line now "AED 0.580 a plate · Invoice line 1, 31 Aug 2026" - KAS-5's own line; every figure the script printed for the after-read. The reset ran (one paper with its lines, document, messages, jobs, runs and price observations; 87 pack baselines recomputed, the Al Madina packs back to their 25 Aug prices); the read-backs above all as listed, the live read byte-identical to step 3's, the screen back to AED 47,021 and two signals, `/sales` at 30.3% with two deliveries. Written down, not fixed: the dashboard read is 162 to 165 KB and took 3.2 to 4.8 s on the live host (open the tab before going on); the hero sentence wraps after the dash inside "Hot Chocolate - Large 250 ml" at 1366 px (cosmetic); the reference screenshot is still owed to `Docs/reference/` (a founder step). Decided on the day: the real menu CSV is committed beside the papers, so the test that pins act four's figures runs in CI. §E row 7 is that run.

## D. Failure playbook

Rule one, from plan.md §7.3 WP-41: every flake found in rehearsal gets fixed, never retried around.

**Extraction is slow or fails on stage.**
If the second reply has not arrived after about 60 seconds, or the failure reply arrives (`⚠️ Couldn't read this one - try a straighter photo, or enter it on the review screen.`), do not fumble.
The pivot line: "And that is the honest path: when it cannot read something, it says so and asks, instead of quietly guessing a number into your books."
Then show the review screen's manual entry as the fallback, which is a feature, not an apology.

**The alert did not fire.**
The reply arrived but without the price alert line.
Almost always this means a rehearsal confirm moved the baseline: check `last_price` on the milk powder item (query in section C) and re-run the reset.
If `last_price` is already 54.50, the previous run was confirmed and not reset.

**The duplicate hold fired instead of the read-out.**
The reply opens `⏸️ Already recorded` and names the earlier paper - a previous rehearsal of the same paper was not reset.
Run the section C reset and forward again; if it happens on stage, the pivot line writes itself: "and if a salesman sends the same invoice twice, it refuses to count it twice" - then forward the backup invoice.

**WhatsApp is silent (no ack at all).**
No ack within 10 seconds means the message never reached the worker.
Check in this order, per the README §M0 troubleshooting table: `/health` returns `db:true`; the Railway logs show a `POST /webhook` at all; `META_APP_SECRET` matches (a logged POST returning 403 means the signature is being rejected); the access token has not expired; `WORKER_ENABLED` is true.
If the Railway logs show **no POST whatsoever** while Meta's dashboard shows the event, the app has come unsubscribed from the WABA - re-run the POST in section A.
That failure mode presents as a completely dead system while every dashboard screen looks correctly configured, so check it early rather than late.
On stage, switch to the backup demo phone first and debug later.

**The review screen shows no image.**
Signed image URLs expire; refresh the page and the screen re-fetches a fresh signed URL.
If it still fails, show the fields and the sparkline, which carry the story without the photo.

## E0. The 5x-run log (2026-08-29 on Opus; re-run clean on Flash 2026-08-30)

> **Engine swap 2026-08-29, and the re-run that settled it.** Gemini 3 Flash became the
> shipped extraction model after the table below was earned on Opus 5. The papers, the 5x
> runs and the meme were **re-run on Flash on 2026-08-30 and came back clean** (founder), so
> the shipped engine now carries the evidence and the Opus table stands as history.
>
> **The seconds in the table are still the Opus measurement** - per-run timings were not
> captured on the Flash pass, and no number here is a Flash number. That is a gap in the
> record rather than in the loop: the next rehearsal logs its own timings from the `latency
> document=` lines (section E), and those become the shipped engine's figures.
>
> The two full rehearsals followed the same day and were also clean - see section E. M4's
> loop gate is passed.

Every paper through the full loop five times, verified run-by-run against the live
database; the meme once (plus an accidental video, which proved the unsupported-media
reply too). Zero pipeline flakes; the only incident was a drained Anthropic credit
balance mid-session, now a section A precondition.

| Paper | Runs | Forward-to-reply (s) - **Opus** | Replies | Repair rounds |
|---|---|---|---|---|
| DEMO-1 (alert pair) | 5/5 | 14.3, 17.2, 14.3, 14.9, 15.4 | byte-identical, both alerts exact | 0 |
| DEMO-2 (single alert) | 5/5 | 15.0, 15.5, 17.1, 13.6, 14.0 | byte-identical, flour silent | 0 |
| DEMO-3 (quiet path) | 5/5 | 15.3, 13.3, 15.2, 16.3, 14.9 | byte-identical, no alerts | 0 |
| Meme (image) | 1/1 | 11.2 to the decline | word-perfect | - |

Every run under the ~20 s target; range 13.3-17.2 s. A duplicate "OK" during one run
re-acked without double-recording (the WP-21 guard, live). One run was forwarded out of
order (DEMO-3 before DEMO-1) and counted for the paper actually sent - the database, not
the gallery order, is the referee.

## E. The rehearsal log

Plan.md §6 M4 required the loop portion rehearsed twice on the demo phones with zero intervention - **passed 2026-08-30**. The M6 demo gate requires the same of the full two-act script on the real menu, and that is still open.
Forward-to-reply seconds come from the latency summary the API logs at pipeline completion, one line per document:

```
latency document=<id> webhook_to_reply_ms=<n> stages=ingest:<n>,extract:<n>,repair:<n>,persist:<n>,reply:<n>
```

Grep the Railway logs for `latency document=` and divide `webhook_to_reply_ms` by 1000.
The target is under about 20 seconds from forward to reply; 18.7 s was measured on a real forward at prompt v3 (2026-08-28) with no repair round - a curated invoice that keeps triggering repair should be swapped out.

**M4's loop gate: passed 2026-08-30.** Act one rehearsed twice on the demo phones, both runs clean with zero intervention, on Gemini 3 Flash.

| Run # | Date | Act one: forward-to-reply (s) | Act two: clean? | Flakes seen (and the fix shipped) |
|---|---|---|---|---|
| 1 | 2026-08-30 | not captured | n/a - act two did not exist yet | none |
| 2 | 2026-08-30 | not captured | n/a - act two did not exist yet | none |
| 3 | 2026-09-01 | 17.7 (message timestamps; extraction 4.1 s, zero repair) | yes - both callouts, the drill, "push this, fix that" | none; the ack ran 8.5 s because no warm-up preceded the day's first forward - the §A warm-up rule, not a pipeline flake |
| 4 | 2026-09-01 | 17.9 (message timestamps; extraction 5.7 s, zero repair) | yes - both callouts live on the reloaded screen | none; an "OK" typed before the read-out arrived confirmed correctly once persisted, and the second "OK" hit the WP-21 duplicate guard and re-acked without double-recording - the guard proving itself live, exactly as in the §E0 runs |
| 5 | 2026-09-03 | 18 (message timestamps: photo 17:24:56, read-back 17:25:14 UTC; zero repair) | yes - the money moment on the reloaded screen, signed in through the new front door | none; the M7 cutover's walk-through (§C3), on the repriced papers - the first of the two clean runs §C2 asks for |
| 6 | 2026-09-05 | not captured in the record (the forward and confirm ran clean inside act three's step 4) | act three on the reloaded `/sales`: 30.3% to 39.3%, three deliveries, the drill to KAS-3's photo; act two not separately walked | none in the pipeline; the M8 go-live sitting (§C4) - the loader's alias question was answered wrong once and corrected before the walk |
| 7 | 2026-09-07 | 15.8 (message timestamps: photo 18:13:08.9, read-out 18:13:24.7 local; zero repair; OK to confirmation 5.5 s) | act four on the reloaded `/dashboard`: the chain from AED 47,021 keeping 65.8% to AED 46,909 keeping 65.7%, four signals and three price moves, the drill to KAS-5's line; act two and three not separately walked | none in the pipeline; the M9 go-live sitting (§C5) - a till name mapped to a lookalike dish at the §C4 sitting, found by the API read-back and fixed on the screen before the walk |

Rows 1-2's seconds were not logged. That is a gap in the record, not in the loop; row 3's seconds are derived from the `wa_messages` timestamps (photo in → reply out) - grep the Railway `latency document=` lines for the official per-stage split when convenient.

**The M6 demo gate: PASSED 2026-09-01.** The two-act script ran twice in a row on the demo phone against the real menu with zero intervention - rows 3 and 4 above. **Founder's amendment, 2026-09-01: the meme beat (§B steps 13-15) is waived from the gate rehearsals** - the decline path was separately signed off on Flash on 2026-08-30 (§E0, word-perfect) and does not need re-proving; it stays in the on-stage script. Both runs: KAS-5 through the loop on the real menu, all three alerts with exact numbers and fresh milk silent, the confirm, and act two's callouts, drill and closing line on the reloaded screens.

One thing to arrange first, not this runbook's to close: loading the real menu leaves every item reading *incomplete* until invoices exist for its materials, so put a few of that chain's own supplier invoices through the loop before rehearsing act two on it - otherwise the closing screen is a list of homework instead of a margin ranking. The staged seed carries two purchase invoices for exactly this reason.

## F. Act two: the screens (added 2026-08-31, WP-66)

Act one ends with the owner's phone. Act two answers the question it leaves hanging: *so what did that price change actually cost me?*
Three screens, one browser, no navigation gymnastics - and one manual page reload, which is the whole point and is called out below rather than hidden.

Run it straight after step 16 of section B, in the same browser, starting on the Materials tab.

**1. Materials - "every price you pay, on one shelf each" (about 40 seconds).**

Open `/materials`.
Say: "The invoice just went in. This is what it did to the shelf."
Point at Milk Powder: one price per kilo, the supplier and the date under it, and the packs it came from.
Then point at the one row waiting in the queue - Chakki Atta Flour has no material yet - and say: "It never guesses. When it doesn't know which shelf something belongs on, it asks, and a person answers once."

Say what the figure is *not*: no figure here is marked verified, because nothing outside the invoice corroborates a printed pack size. The screen says so itself in its footnote.

**2. Menu - "what each plate actually earns" (about 60 seconds).**

Open `/menu`. Read the first callout out loud, whatever it says today:

```
Earns the most per plate: Cardamom Chai (Flask 2 L), AED 42.58 of 55.00.
Push it - nothing else on the menu banks more per sale.
```

Then the table: every item ranked by what it earns in dirhams, with the percentage beside it, grouped by the menu's own sections.
Say: "This is margin, not profit - rent and wages are not in it. And it is per plate, to the fils, because at karak prices a rounded dirham tells you nothing."

Click an item name. The drill opens **in the row** - the ranking never leaves the screen - and shows the recipe version, every ingredient, what each one cost in this plate, which supplier it came from and when, and a link straight to the invoice line it was priced from.
Say: "Every number on this screen goes back to a photograph of a piece of paper. Three clicks."

Then scroll to the quiet section at the bottom: **Paratha, sells at AED 3.00, no cost and no margin at all**, with the sentence "no supplier product is mapped to Atta Flour yet" and a link to fix it.
This is the beat that sells the whole product, so do not skip it: "It would be easy to show a number here. A half-costed dish shows up as the best thing on your menu, and you'd push it. So it shows nothing, and tells you exactly what it is waiting for."

**3. The money moment - "push this, fix that" (about 40 seconds).**

Still on `/menu`, read the second callout:

```
Milk Powder is up AED 1.60 per kg since 31 Aug 2026.
Cardamom Chai (Flask 2 L) earns AED 0.22 less a portion - check the price or the recipe.
Also Karak Tea (Flask 1 L) -0.11, Nido Milk Tea -0.06 · was AED 20.20 per kg · See the invoice
```

Say: "The WhatsApp alert said milk powder is up four dirhams a sack. This says what that costs you per cup, on every item that uses it. That is the difference between a number and a decision."

Close on the founder's line: **"push this, fix that."**

> **The reload is a real step, not a workaround.** Everything above the invoice line is derived on read, so confirming an invoice moves these numbers the next time the page loads - there is no cache, no recompute job and nothing to invalidate. If `/menu` was already open when you replied OK in act one, **reload it** before step 3. Nobody built polling and nobody should: the reload is the demo's own gesture and takes half a second.

If the price-move callout is absent, the invoice was never confirmed (act one step 9), the page was not reloaded, or the paper's printed date is older than the newest purchase already recorded for that material - §A's freshness rule; check `invoice_date` on the confirmed invoice against the staged purchases.
If it names white sugar instead of milk powder, the seed was re-applied after the confirm - re-run act one, or run section C and start again.

**The loader is not in this script.** `/menu/load` is a consultant tool, reachable from the quiet link at the foot of `/menu` and never from the owner's nav. Show it only if asked how a menu gets in, and then show the CSV template first: "the whole menu, one morning, in a spreadsheet the owner watches you fill in."

### Act two preconditions

- [ ] The demo seed is applied and includes act two's menu (section C check 5).
- [ ] `/materials` and `/menu` both load against the demo chain's data with the API token set.
- [ ] The browser has `/materials` and `/menu` in two tabs, already loaded, before going on.
- [ ] Zoom the browser to about 125% so the back row can read the margin column.
- [ ] Run act two once immediately after act one in every rehearsal - the price-move callout only exists once an invoice has been confirmed in that same reset cycle.

## G. Act three: the branches (added 2026-09-04, WP-85; the screen built 2026-09-05, WP-84; live since 2026-09-05, WP-86)

Act two ends on a plate. Act three answers the owner's next question: *which branch is this happening in?*
One screen, `/sales`, and one number per branch: **purchases ÷ net sales (cash basis)** - what the branch's suppliers billed it, against what its till took net of VAT, over the same days.
Never "food cost": purchases are what arrived, not what was consumed, and nothing here pretends otherwise.

Run it straight after act two, in the same browser. The screen is variant B, "answer first", live since 2026-09-05 (§C4); the same figures are on `GET /api/sales/branches`.

**1. The ranked table (about 40 seconds).** Open `/sales`. The sentence above the table names the row to look at first:

```
Al Qusais: of every AED 100 taken this week, about 30 went to suppliers.
```

(The tab was opened before act one, so it still shows the week before KAS-5 - that is what step 4 moves.)
Then the table: Al Qusais on top with its ratio, and Al Nahda and Rolla below it with their net sales, no ratio, and the words *incomplete - no confirmed purchases 25-31 Aug*.
Say: "Two branches have sales and no papers yet. It does not guess a number for them. Register their phones and their invoices flow in exactly the way you just saw."
Every row says how many deliveries its window holds ("3 deliveries in this window"), and the period line says how fresh the sales are ("sales to Mon 31 Aug").

**2. The drill (about 30 seconds).** Click Al Qusais. The row opens in place: seven days, each with its net sales and the papers dated that day.
Click KAS-3 (Al Madina Trading Co., AMT-26-1203, 25 Aug): the invoice opens with the photo beside the figures, "AED 5,081.70 = 5,335.79 less VAT 254.09".
Say: "Every purchase number on this screen is a photograph of a piece of paper, two clicks away."

**3. The coverage panel (about 30 seconds).** Below the table: "Costed: N% of sales value" - the share of what was sold that the menu can already cost - and the queue of till names not yet mapped, ranked by money.
Map one with a keystroke: `CHKN 65 DRY` proposes Chicken 65 Dry at the top; `B/CHKN` proposes nothing and needs the pick-from-menu path - show it needing you.
Mark `DELIVERY CHARGE` as "not a menu item": it stays in net sales and leaves the queue (and a pick from the menu would bring it back).
Say: "It never maps a name on its own. One keystroke each, once, and every day that name was ever sold follows."

**4. The move (about 20 seconds).** KAS-5 was confirmed in act one. **Reload `/sales`.** Al Qusais moves from **30.3% to 39.3%**: AED 2,736.50 of net purchases landing on 31 Aug, the week's last day, and the row's deliveries going from 2 to 3.
Say: "That is one delivery, confirmed from a phone, changing the branch's week. The number is not a report someone typed. It is the papers."

> **The reload is a real step** (act two's rule, one layer up): the ratio derives on every read from the papers and the loaded days; nothing is stored, nothing recomputes in the background, and nothing needs invalidating.

The figures the generator prints are the figures the screen shows - `build_sales_week.py` computes them through the shipped `ratio.period_row`, not a copy of it - so for the committed week they are 30.3% before the stage and 39.3% after, to the tenth.
If the screen disagrees: the week on the stage is not the committed file (re-upload it - the same file changes nothing, a different file replaces exactly the days it carries), or KAS-5 is not confirmed on Al Qusais, or the page was not reloaded.

**If asked where the sales came from, say it plainly: the demo's sales are invented; its purchases are not; the screen's honesty claim is about the second.** The week is a till export in the shape a pilot's till prints, generated from the real menu so the ratio sits where a cafeteria's does.

Then go straight into **act four (section H)** in the same browser: the ratio says what went out, and the dashboard says what stayed.

### Act three preconditions

- [ ] §A's week check: loaded, the layout saved, the three aliases taught, `/sales` at 30.3% for Al Qusais before act one.
- [ ] `/sales` open in a third tab before going on, signed in.
- [ ] Act one's KAS-5 confirm has happened in this reset cycle, or step 4 has nothing to move.
- [ ] Run act three once immediately after act two in every rehearsal: the loop reset takes KAS-5 with it and the ratio goes back to 30.3% by itself.

## H. Act four: the dashboard (added 2026-09-05, WP-95; live on the real stage 2026-09-07, WP-96)

Act three ends on a ratio - what went out to suppliers against what came in. Act four answers the question underneath it: *of what the chain took, how much did it keep, and which dish is eating it?*
One screen, `/dashboard`, read straight after act three, in the same browser. It is one read: the two sentences, the four tiles, the league, what to look at, the supplier price moves, the items. Nothing on it is stored and nothing recomputes in the background.
The screen is the founder's compact redesign of 2026-09-07: the answer, the four figures and the whole league on one laptop screen (the league's total row ends at 608 of 768 at 1366x768), whole-dirham headlines rounded half up so they agree with the sentences beside them, and every sentence that qualifies a figure behind the info icon next to it - the caveat on the answer, the window on a status, "After ingredients and packaging." on the contribution tile. Hover or tap an icon when a figure needs its sentence; do not read the icons out.

**Every figure quoted below is printed, not typed.** `Docs/demo-invoices/koukh-al-shay/act_four.py` stages the chain through the same doors a person uses - the menu through the loader, the four preparation papers through the typed-invoice door and the confirm, each pack mapped to its material, the committed week through `POST /api/sales/days`, one keystroke per till name - and then reads `GET /api/dashboard` and prints exactly what comes back:

```bash
apps/api/.venv/bin/python Docs/demo-invoices/koukh-al-shay/act_four.py --migrate \
    --database-url postgresql://localhost:5432/faida_act_four --stage real
```

Two things about that script are worth knowing before you quote it on stage. It types the four preparation papers instead of photographing them, and a typed price is *asserted* (C8), which caps every plate at **estimated** - so the script's quality words are one notch below the real stage's, where the same papers were read from photographs and read *reliable with limitations*. **The money is identical**; only the word moves. And it stages a throwaway database, never the live one. On 2026-09-07 the live read and the script's read agreed to the fil in every figure (§C5); the one difference is that the live drill says *Recipe version 2*, because the real menu was loaded twice, where the script's throwaway says version 1.

**1. The one sentence and the four figures (about 30 seconds).** Open `/dashboard`. (The tab was opened before act one, so it still shows the week before KAS-5 - that is what step 4 moves, exactly as it did on `/sales`.) Under the heading, the freshness line - `Sales loaded to Mon 31 Aug, 7 days ago · AED 9,625 taken that day across 3 branches` - then the two sentences, which read out loud:

```
Look at Al Nahda first: it keeps about AED 66 of every 100 it takes, the least of the three.
Hot Chocolate - Large 250 ml sells more than any item that earns under the menu's average.
```

Say: "Act three told you where the money went out. This tells you what stayed - and it names the branch and the dish before you have read a single number."
Then the four tiles under them:

```
NET SALES                                   AED 71,942    to Mon 31 Aug
PURCHASES ÷ NET SALES (CASH BASIS)          12.7%         Incomplete · AED 9,163 of confirmed papers
CONTRIBUTION BEFORE OVERHEADS (ESTIMATE)    AED 47,021    Reliable with limitations · keeps 65.8% of costed sales
COSTED SHARE OF SALES                       100.0%        Every till name is mapped.
```

Say: "Four figures, and the second one is honest about itself: two branches have no papers yet, so the chain's ratio says *incomplete* rather than pretending." Point at **45 costed** beside the items heading further down - the screen says what it is built on (it reads "N costed of M" the moment a row carries no numbers).

**2. The league, with contribution beside the ratio (about 40 seconds).** The table, ordered by what each branch keeps, least first - **not** by the ratio, which is `/sales`' key:

```
BRANCH             NET SALES    PURCHASES ÷ NET SALES    CONTRIBUTION (EST.)   KEPT     STATUS
Al Nahda Branch    AED 23,066   No confirmed purchases   AED 15,029            65.7%    Reliable with limitations
Rolla Branch       AED 18,608   No confirmed purchases   AED 12,149            65.8%    Reliable with limitations
Al Qusais Branch   AED 30,267   30.3%                    AED 19,843            66.0%    Reliable with limitations
All branches       AED 71,942   12.7%                    AED 47,021            65.8%    Reliable with limitations
```

(The exact figures behind the rows are 15,028.97, 12,148.63, 19,843.16 and 47,020.76; the screen rounds half up, so 15,028.97 reads **AED 15,029**, and the bar beside each percentage is drawn to its own number.)

Say: "This is contribution before overheads - ingredients and packaging out of what the till took. It is **not** net profit: rent, wages and electricity are not in it, and neither is waste, because nobody records waste yet and this screen does not invent it."
Then point at Al Nahda and Rolla: "Those two have no invoices yet, so act three could not give them a ratio. They still have a contribution, because contribution needs sales and a costed menu, not papers. That is the same discipline in the other direction: it says what it knows."
And be straight about the spread: the three branches sit within a third of a point of each other, because the demo's sales are invented from one distribution. On a real chain that column is where the differences show up.
If asked for one branch, pick it in the picker at the top right: the URL gains `?branch=`, the tiles become that branch's row with the chain named beside each figure (`Al Nahda · to Mon 31 Aug`; `AED 0 of confirmed papers · chain 12.7%`; `keeps 65.7% of costed sales · chain 65.8%`), the sentence becomes "Al Nahda keeps about AED 66 of every 100 it takes. Hot Chocolate - Large 250 ml sells more than any item at Al Nahda that earns under the menu's average.", and the league keeps that branch and the chain's row. It is the same screen, never a second one.

**3. The item that sells and does not earn (about 40 seconds).** The item panel - **Items: what each one contributed** - best five and worst five, "Show all 45 items" beneath. Read the bottom of it:

```
WORST
Karak Delivery - Large 400 ml    388   AED 1,848   AED 522   28.2%
Lotus Cake - slice               104   AED 1,090   AED 510   46.8%
Honey Cake - slice               111   AED 1,163   AED 484   41.6%
Karak Delivery - Medium 250 ml   542   AED 1,549   AED 353   22.8%
Karak Delivery - Small 120 ml    492   AED 703     AED 136   19.3%
```

Say: "The small delivery karak sold 492 cups this week and kept AED 135.58 of the AED 702.86 it took." (The fils are the API's; the row reads AED 136 of AED 703.)
Then open the row - the drill opens in place, the ranking never leaves the screen - and read the reason off it:

```
PORTIONS 492 sold        COSTED AED 1.153 a plate        TILL NAMES KARAK DELIVERY S
Costed at the prices in force on 31 Aug 2026. Recipe version 2.
CTC black tea · 3.3 g            AED 0.056 a plate · Invoice line 1, 25 Aug 2026
Green cardamom · 0.27 g          AED 0.051 a plate · Invoice line 15, 24 Aug 2026
Cinnamon stick · 0.09 g          AED 0.008 a plate · Invoice line 14, 24 Aug 2026
Saffron · 0.006 g                AED 0.056 a plate · Invoice line 24, 24 Aug 2026
Evaporated milk · 47 ml          AED 0.541 a plate · Invoice line 1, 25 Aug 2026
Condensed milk · 10 g            AED 0.199 a plate · Invoice line 2, 25 Aug 2026
White sugar · 5 g                AED 0.013 a plate · Invoice line 1, 24 Aug 2026
Delivery cup S + lid · 1 ea      AED 0.230 a plate · Invoice line 20, 25 Aug 2026
Cost covers what the recipe lists.   See today's plate
```

Say: "A 47 ml pour of evaporated milk and a 23-fils cup and lid, against a sale of AED 1.429 net of VAT. Nobody had that number before: the till knows what sold, the invoice knows what a lid costs, and nothing joined them."
Every one of those lines is a link to the invoice line its price came from. Click the evaporated milk's: AMT-26-1203 opens with the photograph beside the figures and line 1 highlighted - **two clicks from the dashboard to a piece of paper**. Go back; the dashboard is where you left it.

**4. The reload, one layer up (about 25 seconds).** KAS-5 was confirmed in act one, and act three reloaded `/sales` to watch Al Qusais move from 30.3% to 39.3%. Act four is the same gesture one layer up. **Reload `/dashboard`.**

```
Contribution tile   AED 47,021 · keeps 65.8%          ->   AED 46,909 · keeps 65.7%
Ratio tile          12.7% · AED 9,163 of papers       ->   16.5% · AED 11,899 of confirmed papers
Al Qusais           AED 19,843   66.0%   30.3%        ->   AED 19,797   65.8%   39.3%
Al Nahda            AED 15,029   65.7%                ->   AED 14,994   65.5%
Rolla               AED 12,149   65.8%                ->   AED 12,118   65.6%
Karak Delivery - Small 120 ml   AED 136   19.3%       ->   AED 116   16.6%
```

(Exactly: 47,020.76 to 46,908.73; 19,843.16 to 19,796.71; 135.58 to 116.40. The worst five reorder too: the large delivery karak drops below both cakes.)

Say: "One delivery, confirmed from a phone, moved what the whole chain kept by AED 112, moved every branch, and reordered the bottom of the item table. Nothing was stored and nothing recomputed in the background - the page was read again, and it derived the lot."
Open the small delivery karak again to show where the AED 19 went: its evaporated milk line reads **AED 0.541 a plate · Invoice line 1, 25 Aug 2026** before the reload and **AED 0.580 a plate · Invoice line 1, 31 Aug 2026** after it, and that link now lands on KAS-5. One line on one paper, on one plate, on 492 cups.

**5. What to look at, and the price moves in money (about 40 seconds).** The reload also changed the two panels under the league. **What to look at** now reads "4 this window, largest first" - ranked by the money at stake, capped at five, three shown and "Show all 4" beneath:

```
Hot Chocolate - Large 250 ml sold AED 3,010 and kept 52.3%; the menu keeps 65.7%.    AED 403
Hot Chocolate - Small 150 ml sold AED 1,981 and kept 53.4%; the menu keeps 65.7%.    AED 244
Evaporated milk is up AED 0.83 per litre since 31 Aug.                               AED 26
Show all 4  ->  Milk powder is up AED 1.06 per kg since 31 Aug.                      AED 1
```

Behind each icon, the sentence that made the figure: "At the menu's average it would have contributed AED 403 more."; "AED 26 off contribution on the 211 portions sold since it landed, across 9 items."; "AED 1 off contribution on the 105 portions sold since it landed, across 2 items." (Before the reload the panel held the two dishes only, "2 this window", at AED 406 and AED 246 - there was no move to compare.)

Say: "The phone said milk powder is up. The menu screen said what that costs a cup. This says what it has cost the business since the delivery landed - and it ranks both milk moves **below** two dishes that quietly keep twelve and thirteen points less than the rest of the menu. A price alert is not the biggest thing happening to you."
**The AED 26 and the AED 1 are small on purpose, and say why if asked:** KAS-5 is printed on 31 August, the last day of the week, so only that one day's cups were sold at the new price. The signal answers "what has this move cost since it landed", not "what would a week of it cost".

Beside it, **Supplier price moves** - "3 moved this window · latest move each" - is the other half of the same reload. It lists every material's latest move inside the window, both directions, at the 5% gate, with the invoice behind each:

```
Price moved   Evaporated milk is up AED 0.83 per litre since 31 Aug.     See the invoice    AED 26  at stake
Price fell    Chicken, boneless is down AED 1.25 per kg since 31 Aug.    See the invoice    AED 11  saved
Price moved   Milk powder is up AED 1.06 per kg since 31 Aug.            See the invoice    AED 1   at stake
Every price move on Menu ->
```

Behind each icon: the plates ("Karak Tea - Flask 2 L earns AED 0.65 less a portion; also Coffee Milk - Flask 2 L (-0.63), Habbat Al Hamra - Flask 2 L (-0.58), Karak Tea - Flask 1 L (-0.32) and 5 more."; "Butter Chicken earns AED 0.16 more a portion; also Chicken Kadai (0.16), Pepper Chicken (0.16), Chicken 65 Dry (0.15) and 3 more.") and the evidence ("was AED 11.51 per litre · AED 26 at stake on the 211 portions sold since 31 Aug."; "was AED 18.00 per kg · AED 11 saved on the 73 portions sold since 31 Aug."). Before the reload it reads "No price moves in this window."
Say: "The panel is what moved; the list on the left is what it is costing you. Chicken went down, so it is here and not there - and *See the invoice* is the same paper again, the one the phone read twenty minutes ago." The chicken line is worth pointing at: the phone's read-out said it, the panel weighs it, nothing else on the screen fires on a fall.

> **Why the chain moved by AED 112 and the signals name AED 27.** They are answers to two different questions. The signals price the cups sold *after* the delivery landed; the column reprices the whole week, because a period is costed at one price per material - the latest in force on its last day (C12.4, PRD §19's policy, the same one `/menu` applies) - so a delivery on the last day reprices all seven days. **The two are never added.**

**6. The founder's line, and it is not optional.** Close act four with it:

> "The volumes here are invented - the till never exported a week for this chain, so we generated one. **The prices and the recipes are real**, and the papers are real. So read the shape and the discipline, not the headline: a real chain's contribution figure is its own."

`build_sales_week.py` generates the week at `VOLUME = 0.49`, which is what makes Al Qusais's ratio land in a plausible band - and it is the one constant that would move every figure on this screen.

> **The plate on this screen equals `/menu`'s only while no confirmed paper is dated after 31 Aug.** The dashboard costs the week at the prices in force on the week's last day; `/menu` always costs at today's. They agree today because KAS-5 is printed **on** 31 August and nothing is printed after it. Confirm a paper dated 1 September and they part company: the item row then carries today's cost beside its own and says which is which, with a "See today's plate" link. Never promise on stage that the two screens agree - say that they agree *today, and the row will tell you the day they stop*.

### Act four preconditions

- [ ] Act three has just run, in the same browser, with KAS-5 confirmed in this reset cycle - or step 4 has nothing to move and step 5's panels never gain their milk moves.
- [ ] `/dashboard` open in a fourth tab **before act one**, signed in, and not reloaded since - the reload in step 4 is the whole beat. A sign-in lands there now (§A). The read takes 3 to 5 s on the live host (162 to 165 KB, measured 2026-09-07), so open the tab before going on, never on stage.
- [ ] The whole week's till names are mapped and `DELIVERY CHARGE` is marked "not a menu item" (§C4 step 6), or the coverage tile reads under 100% and the league's `costed` column says so.
- [ ] **Every till name is mapped to its own dish, not a lookalike.** The §C5 sitting found `COFFEE MILK FLASK 2L` on the 1 L flask - a keystroke at the §C4 sitting that lifted the chain's contribution by AED 220 and put a flask in the best five. The screen cannot see it (the queue is empty, the coverage is 100%); the figures can: "44 costed" where the menu has 45 items, or a size name in the best five. Read the mapping back before a rehearsal week, and fix a wrong one on `/sales` under *Mapped names* (Unmap, then the queue's top proposal):

      ```sql
      select t.name, m.name from till_items t join menu_items m on m.id = t.menu_item_id
       where t.tenant_id = 'd0000000-0000-0000-0000-000000000001' order by t.name;   -- 45 rows, each name its own dish
      ```
- [ ] Run `act_four.py --stage real` once before a rehearsal week and read its figures against the screen (CI runs the same read on every push since the menu CSV was committed, 2026-09-07). If they disagree, one of three things: the stage is not the committed week, the papers are not KAS-1..5, or a till name is mapped to the wrong dish (the box above).
- [ ] **On the practice stage act four is a walk-through, not the script.** `demo_seed.sql`'s five items are all tea, every one keeps between 81% and 86%, and the seed's own price history moves nothing by 5% - so no dish is ten points below the average, no branch is five points below the chain, and **the signals panel is empty**, correctly. `act_four.py --stage practice` prints exactly that, and `tests/test_demo_seed.py` pins it. Rehearse the sentence, the league and the item panel there; gate act four on the real stage.
