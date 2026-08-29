# Faida Demo Runbook (M4 loop gate - act one of the demo)

This is the operating manual for the invoice-loop portion of the demo (plan.md §6) and for the two loop rehearsals before the M4 gate (F7).
Since 2026-08-28 the full demo is two acts and gates at M6 (§1: the loop, then materials and menu margins); this runbook owns act one, and the loop gate stands on its own: the loop runs end to end twice in a row with zero intervention before anything is built on its numbers.
Every reply quoted below is the exact template from `apps/api/src/faida_api/replies.py`, so if the phone shows different words, something is wrong.

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
- [ ] `ANTHROPIC_API_KEY` is set on Railway (with it missing, every invoice gets the failure reply).
- [ ] **The Anthropic account has credit**, checked at console.anthropic.com Plans & Billing, with enough headroom for the whole session (~AED cents per invoice, but a demo day is many rehearsals). Found the hard way in rehearsal 2026-08-29: a drained balance presents as the failure reply after ~70 s - three retries of a 400 - while every other dashboard looks healthy. There is no low-balance warning anywhere in our system.
- [ ] The demo seed is applied: `psql "$DATABASE_URL" -f supabase/demo_seed.sql` (see section C).
- [ ] The founder phone is mapped to the demo chain: the commented UPDATE at the bottom of `supabase/demo_seed.sql` has been run once, so the sender resolves to Al Qusais Branch of Karak Al Khaleej Cafeterias.
- [ ] The review screen loads real data with its API token configured, and the invoice list for the demo chain is empty (no rehearsal leftovers).
- [ ] The 3 curated invoice photos and 1 meme image are saved on the demo phone, in order, first in the gallery.
- [ ] **The extraction grammar is warm.** The first request after a schema or model change pays a one-time server-side compilation measured in minutes (155 s observed 2026-08-28), and the cache is not permanent. Within the hour before going on, run `apps/api/.venv/bin/python -m eval.schema_probe` from the repo root (needs `ANTHROPIC_API_KEY`), or forward one throwaway invoice and delete it. Never let the on-stage forward be the first request.
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
5. Now extraction runs, which takes 15-20 seconds (18.7 s measured on a real forward 2026-08-28); do not stand in silence.
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
16. Close on the plan's line: "no app, no login, no training - the salesman already knows how to do this."

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

## E. The rehearsal log

Plan.md §6 M4 requires the full script rehearsed twice on the demo phones with zero intervention.
Forward-to-reply seconds come from the latency summary the API logs at pipeline completion, one line per document:

```
latency document=<id> webhook_to_reply_ms=<n> stages=ingest:<n>,extract:<n>,repair:<n>,persist:<n>,reply:<n>
```

Grep the Railway logs for `latency document=` and divide `webhook_to_reply_ms` by 1000.
The target is under about 20 seconds from forward to reply; 18.7 s was measured on a real forward at prompt v3 (2026-08-28) with no repair round - a curated invoice that keeps triggering repair should be swapped out.

| Run # | Date | Forward-to-reply (s) | Flakes seen (and the fix shipped) |
|---|---|---|---|
| 1 | | | |
| 2 | | | |

A run with any manual intervention does not count; fix the cause and run it again.
