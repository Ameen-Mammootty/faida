# Faida Demo Runbook (three acts; M4 loop gate, M6 demo gate, M8 act three)

This is the operating manual for the demo (plan.md §6) and for the rehearsals before its two gates.
Since 2026-08-28 the full demo is two acts and gates at M6 (§1: the loop, then materials and menu margins).
**Act one** (sections A-E) is the invoice loop on WhatsApp and stands on its own as the M4 loop gate: it runs end to end twice in a row with zero intervention before anything is built on its numbers.
**Act two** (section F, added 2026-08-31 by WP-66) is the screens - materials, then menu margins, closing on "push this, fix that".
Every reply quoted below is the exact template from `apps/api/src/faida_api/replies.py`, so if the phone shows different words, something is wrong.

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
- [ ] Signed in on the demo laptop as the founder's account (Supabase Auth, email and password; sign-ups are off, accounts are created in the dashboard and given a `memberships` row), and the invoice list for the demo chain carries no rehearsal leftovers - on the practice stage that means empty; on the real stage it means only the KAS-1..4 preparation purchases and the chain's own real invoices, nothing from a previous run of the props (DEMO-1..3, KAS-5). The list hides dismissed rows by default, so open `/invoices?status=dismissed` as well: a dismissed leftover passes the eye test and still needs the reset.
- [ ] The right papers are on the demo phone, first in the gallery: on the practice stage, the 3 curated invoice photos and the meme; on the real stage, **KAS-5** and the meme (KAS-1..4 were confirmed once during preparation and are not forwarded again - a re-forward trips the duplicate hold).
- [ ] **Act three's week is loaded and its layout saved** (added 2026-09-04, WP-85; the screen
      lands with WP-84). On the real stage, `Docs/demo-invoices/koukh-al-shay/sales-week.csv`
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
Curate credit invoices only: an invoice marked cash gets the cash-hold closing instead of "Reply OK to confirm", and OK will not confirm it from chat.

## B. The 4-minute script

The script from plan.md §6 M4, verbatim: forward invoice, reply appears with price alert, "OK", open review screen with photo beside data all green, show the sparkline for the item that moved, forward a meme, polite decline, close on the no-app line.

> **Which paper, which stage.** On the practice stage the forward is curated invoice 1 (DEMO-1) and the replies below are its exact words. On the real stage the forward is **KAS-5** (`Docs/demo-invoices/koukh-al-shay/README.md` has its read-out): the same beats with its own numbers - three alerts fire (evaporated milk and milk powder up, chicken **down**, worth pointing at) and fresh milk stays deliberately silent. DEMO-1..3 are tuned to the staged catalog and are dead props on the real stage: DEMO-1's printed date (20/08/2026) is older than KAS-3's preparation purchase (25/08/2026), and costing ranks by the printed date, so its confirm would not move a single plate there (§A's freshness rule).

1. Open WhatsApp on the demo phone with the chat to the Faida number already on screen.
2. Say: "This is a supplier invoice from this morning's delivery. Watch what the salesman does with it."
3. Forward curated invoice 1.
4. Within a couple of seconds the ack arrives: `Got it - invoice received and saved. I'll reply with the details here soon.`
5. Now extraction runs, which takes roughly 10-15 seconds on Gemini 3 Flash (9.5 s average
   model time on the corpus; the Opus-era measurement was 13.3-17.2 s end to end); do not
   stand in silence.
6. While waiting, say: "It is reading the photo now: every line item, every price, and checking that the math on the page actually adds up. No typing, no app, and it compares every price against what this cafeteria paid last week."
7. The parsed reply arrives, exactly (the date is whatever invoice 1 prints, read out in words):
   ```
   Read it: Gulf Foods Trading LLC, 2 lines, total AED 745.76, dated 20 Aug 2026.
   Milk Powder 2.5kg up AED 4.00 (50.50 to 54.50) since your last purchase.
   Karak Tea Dust down AED 3.25 (22.00 to 18.75) since your last purchase.
   Reply OK to confirm.
   ```
8. Point at the alert line and say: "That is the money moment: milk powder went up four dirhams and the owner knows before the invoice is even filed."
9. Reply `OK`.
10. The confirmation arrives: `Confirmed - Gulf Foods Trading LLC, AED 745.76 recorded. I'll watch these prices for you.`
11. Open the review screen: the invoice photo sits on the left, the extracted fields on the right, every field green with its check icon.
12. Open the Milk Powder 2.5kg sparkline: three weeks of gentle drift, then today's jump to 54.50.
13. Back in WhatsApp, forward the meme and say: "And when someone sends it nonsense?"
14. First the same ack arrives (`Got it - invoice received and saved. I'll reply with the details here soon.`), then after the read, the decline, exactly: `That doesn't look like a supplier invoice, so I'll leave it - forward an invoice photo and I'll read it.`
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
Run the reset after EVERY rehearsal run, confirmed or not (this got stricter 2026-08-28): confirming moves `last_price` to 54.50 so the alert will not fire again, and even without confirming, re-forwarding the same paper now trips the duplicate hold (WP-44) - the second copy is held with "This one is already recorded..." instead of being read out. Both are correct product behavior and both ruin a rehearsal that expected the full reply.
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

## D. Failure playbook

Rule one, from plan.md §7.3 WP-41: every flake found in rehearsal gets fixed, never retried around.

**Extraction is slow or fails on stage.**
If the second reply has not arrived after about 60 seconds, or the failure reply arrives (`Couldn't read this one - try a straighter photo, or type the total.`), do not fumble.
The pivot line: "And that is the honest path: when it cannot read something, it says so and asks, instead of quietly guessing a number into your books."
Then show the review screen's manual entry as the fallback, which is a feature, not an apology.

**The alert did not fire.**
The reply arrived but without the price alert line.
Almost always this means a rehearsal confirm moved the baseline: check `last_price` on the milk powder item (query in section C) and re-run the reset.
If `last_price` is already 54.50, the previous run was confirmed and not reset.

**The duplicate hold fired instead of the read-out.**
The reply says `This one is already recorded: ...` - a previous rehearsal of the same paper was not reset.
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

## G. Act three: the branches (added 2026-09-04, WP-85; the screen built 2026-09-05, WP-84; live at WP-86)

Act two ends on a plate. Act three answers the owner's next question: *which branch is this happening in?*
One screen, `/sales`, and one number per branch: **purchases ÷ net sales (cash basis)** - what the branch's suppliers billed it, against what its till took net of VAT, over the same days.
Never "food cost": purchases are what arrived, not what was consumed, and nothing here pretends otherwise.

Run it straight after act two, in the same browser. Steps marked **[WP-84]** describe the screen as built (variant B, "answer first", on master since 2026-09-05); until WP-86 deploys the web, the same figures are on `GET /api/sales/branches`.

**1. The ranked table (about 40 seconds).** Open `/sales`. **[WP-84]** The sentence above the table names the row to look at first:

```
Al Qusais: of every AED 100 taken this week, about 30 went to suppliers.
```

(The tab was opened before act one, so it still shows the week before KAS-5 - that is what step 4 moves.)
Then the table: Al Qusais on top with its ratio, and Al Nahda and Rolla below it with their net sales, no ratio, and the words *incomplete - no confirmed purchases 25-31 Aug*.
Say: "Two branches have sales and no papers yet. It does not guess a number for them. Register their phones and their invoices flow in exactly the way you just saw."
Every row says how many deliveries its window holds ("3 deliveries in this window"), and the period line says how fresh the sales are ("sales to Mon 31 Aug").

**2. The drill (about 30 seconds).** Click Al Qusais. **[WP-84]** The row opens in place: seven days, each with its net sales and the papers dated that day.
Click KAS-3 (Al Madina Trading Co., AMT-26-1203, 25 Aug): the invoice opens with the photo beside the figures, "AED 5,081.70 = 5,335.79 less VAT 254.09".
Say: "Every purchase number on this screen is a photograph of a piece of paper, two clicks away."

**3. The coverage panel (about 30 seconds).** Below the table **[WP-84]**: "Costed: N% of sales value" - the share of what was sold that the menu can already cost - and the queue of till names not yet mapped, ranked by money.
Map one with a keystroke: `CHKN 65 DRY` proposes Chicken 65 Dry at the top; `B/CHKN` proposes nothing and needs the pick-from-menu path - show it needing you.
Mark `DELIVERY CHARGE` as "not a menu item": it stays in takings and leaves the queue.
Say: "It never maps a name on its own. One keystroke each, once, and every day that name was ever sold follows."

**4. The move (about 20 seconds).** KAS-5 was confirmed in act one. **Reload `/sales`.** Al Qusais moves from **30.3% to 39.3%**: AED 2,736.50 of net purchases landing on 31 Aug, the week's last day, and the row's deliveries going from 2 to 3.
Say: "That is one delivery, confirmed from a phone, changing the branch's week. The number is not a report someone typed. It is the papers."

> **The reload is a real step** (act two's rule, one layer up): the ratio derives on every read from the papers and the loaded days; nothing is stored, nothing recomputes in the background, and nothing needs invalidating.

The figures the generator prints are the figures the screen shows - `build_sales_week.py` computes them through the shipped `ratio.period_row`, not a copy of it - so for the committed week they are 30.3% before the stage and 39.3% after, to the tenth.
If the screen disagrees: the week on the stage is not the committed file (re-upload it - the same file changes nothing, a different file replaces exactly the days it carries), or KAS-5 is not confirmed on Al Qusais, or the page was not reloaded.

**If asked where the sales came from, say it plainly: the demo's sales are invented; its purchases are not; the screen's honesty claim is about the second.** The week is a till export in the shape a pilot's till prints, generated from the real menu so the ratio sits where a cafeteria's does.

### Act three preconditions

- [ ] §A's week check: loaded, the layout saved, the three aliases taught, `/sales` at 30.3% for Al Qusais before act one.
- [ ] `/sales` open in a third tab before going on, signed in.
- [ ] Act one's KAS-5 confirm has happened in this reset cycle, or step 4 has nothing to move.
- [ ] Run act three once immediately after act two in every rehearsal: the loop reset takes KAS-5 with it and the ratio goes back to 30.3% by itself.
