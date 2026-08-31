# Faida Demo Runbook (both acts; M4 loop gate, M6 demo gate)

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
- [ ] The demo seed is applied: `psql "$DATABASE_URL" -f supabase/demo_seed.sql` (see section C).
- [ ] The founder phone is mapped to the demo chain: the commented UPDATE at the bottom of `supabase/demo_seed.sql` has been run once, so the sender resolves to Al Qusais Branch of Karak Al Khaleej Cafeterias.
- [ ] The review screen loads real data with its API token configured, and the invoice list for the demo chain is empty (no rehearsal leftovers).
- [ ] The 3 curated invoice photos and 1 meme image are saved on the demo phone, in order, first in the gallery.
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
Curate credit invoices only: an invoice marked cash gets the cash-hold closing instead of "Reply OK to confirm", and OK will not confirm it from chat.

## B. The 4-minute script

The script from plan.md §6 M4, verbatim: forward invoice, reply appears with price alert, "OK", open review screen with photo beside data all green, show the sparkline for the item that moved, forward a meme, polite decline, close on the no-app line.

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

One command restores the exact staged state, however messy the last run was:

```bash
psql "$DATABASE_URL" -f supabase/demo_seed.sql
```

`$DATABASE_URL` is the same session-pooler URI Railway uses (README §M0 step 2).
The reset deletes every rehearsal trace for the demo chain (documents, invoices, lines, messages, jobs, runs, confirm-created catalog rows, appended price history) and re-stages the baselines; it cannot touch any other tenant, and it preserves the branch phone mapping.
Run it after EVERY rehearsal run, confirmed or not (this got stricter 2026-08-28): confirming moves `last_price` to 54.50 so the alert will not fire again, and even without confirming, re-forwarding the same paper now trips the duplicate hold (WP-44) - the second copy is held with "This one is already recorded..." instead of being read out. Both are correct product behavior and both ruin a rehearsal that expected the full reply.
Rehearsal images stay in the storage bucket; that is intended, since originals are immutable and nothing references them after the reset.

Re-check after the reset:

1. `select last_price, prev_price from supplier_items where id = 'd0000000-0000-0000-0000-000000000101';` returns `50.500 | 49.750`.
2. `select name, wa_phone_e164 from branches where tenant_id = 'd0000000-0000-0000-0000-000000000001';` still shows the founder phone on Al Qusais Branch.
3. `curl https://<host>/health` returns `{"ok":true,"db":true}`.
4. The review screen's invoice list for the demo chain is empty again.
5. `select count(*) from menu_items where tenant_id = 'd0000000-0000-0000-0000-000000000001';` returns `5`, and `/menu` shows four costed items with Paratha in the "can't be costed yet" section (act two's staged state, section F).

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
> Still owed on Flash: **the two full rehearsals**, which are the gate itself and not this
> table.

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

Plan.md §6 M4 requires the full script rehearsed twice on the demo phones with zero intervention.
Forward-to-reply seconds come from the latency summary the API logs at pipeline completion, one line per document:

```
latency document=<id> webhook_to_reply_ms=<n> stages=ingest:<n>,extract:<n>,repair:<n>,persist:<n>,reply:<n>
```

Grep the Railway logs for `latency document=` and divide `webhook_to_reply_ms` by 1000.
The target is under about 20 seconds from forward to reply; 18.7 s was measured on a real forward at prompt v3 (2026-08-28) with no repair round - a curated invoice that keeps triggering repair should be swapped out.

Both acts count as one run: the gate is the **full** §6 script - loop, mapping, menu margins, "push this, fix that" - twice in a row with zero intervention, on the demo phones and on **F7's real menu**, not the staged one.

| Run # | Date | Act one: forward-to-reply (s) | Act two: clean? | Flakes seen (and the fix shipped) |
|---|---|---|---|---|
| 1 | | | | |
| 2 | | | | |

A run with any manual intervention does not count; fix the cause and run it again.

Still owed before this gate can be called passed (neither is this runbook's to close):
**these two rehearsals themselves**, on Flash, and F7's real menu loaded into the demo project through `/menu/load`.
M4's Flash re-run of the papers and the meme closed 2026-08-30 (section E0).

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

If the price-move callout is absent, the invoice was never confirmed (act one step 9) or the page was not reloaded.
If it names white sugar instead of milk powder, the seed was re-applied after the confirm - re-run act one, or run section C and start again.

**The loader is not in this script.** `/menu/load` is a consultant tool, reachable from the quiet link at the foot of `/menu` and never from the owner's nav. Show it only if asked how a menu gets in, and then show the CSV template first: "the whole menu, one morning, in a spreadsheet the owner watches you fill in."

### Act two preconditions

- [ ] The demo seed is applied and includes act two's menu (section C check 5).
- [ ] `/materials` and `/menu` both load against the demo chain's data with the API token set.
- [ ] The browser has `/materials` and `/menu` in two tabs, already loaded, before going on.
- [ ] Zoom the browser to about 125% so the back row can read the margin column.
- [ ] Run act two once immediately after act one in every rehearsal - the price-move callout only exists once an invoice has been confirmed in that same reset cycle.
