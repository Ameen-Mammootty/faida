# The three curated demo papers (M4 loop gate)

Three generator prompts in the corpus house format, arithmetic-checked against
`supabase/demo_seed.sql` so the on-stage replies come out exactly as the runbook pins them.
Generate each with the same image tool that produced `eval/fixtures/generated/`, save the
results here as `DEMO-1.png` (or .jpg) etc., and pre-verify through the live upload door
before they touch the demo phone.

| Paper | Supplier | Lines | Total | What the reply shows |
|---|---|---|---|---|
| DEMO-1 (on stage) | Gulf Foods Trading L.L.C., GFT-2026-0834, 20/08/2026 | Milk Powder 2.5kg 12 x 54.50; Karak Tea Dust 3 x 18.75 | 745.76 | "dated 20 Aug 2026", milk **up AED 4.00**, karak **down AED 3.25**, all green |
| DEMO-2 (backup) | Al Madina Trading Co., AMT-26-1187, 22/08/2026 | Evaporated Milk 400ml 2 x 96.00; Chakki Atta Flour 3 x 43.50 | 338.63 | evap milk **up AED 6.00**, flour silent (stable) |
| DEMO-3 (rehearsal) | Gulf Foods Trading L.L.C., GFT-2026-0871, 24/08/2026 | Sugar 2 x 115.00; Cardamom Powder 4 x 24.00 | 342.30 | **no alerts at all** - the quiet path, proving not everything alarms |

Why these exact numbers:

- Every unit price either matches or deliberately moves against the staged `last_price` in
  the seed, so the alert lines are predetermined (threshold: >= AED 0.25 and >= 5%).
- Item names are the seed's canonical names (or the M2 gate test's snapping variant on
  DEMO-1's milk powder), so every line snaps to the staged catalog.
- Distinct invoice numbers per paper: since WP-44, a reused supplier + number + total is
  held as a duplicate - correct in production, a rehearsal-breaker on stage.
- Dates print day-first (`20/08/2026`), which the reply reads out ("dated 20 Aug 2026") -
  a quiet on-stage proof of the date reading, per WP-27.
- All three are credit-terms papers: a cash paper gets the cash-hold closing and OK will
  not confirm it from chat.
- No specimen or QA footer text: these papers are read as invoices on stage, and the
  corpus rule (no watermark text) applies doubly here.

The arithmetic, checked: 654.00 + 56.25 = 710.25, x1.05 = 745.76 (VAT 35.51, printed);
192.00 + 130.50 = 322.50, VAT 16.13, total 338.63; 230.00 + 96.00 = 326.00, VAT 16.30,
total 342.30. All reconcile exclusive at 5% within C4 tolerance.

These images are synthetic demo material and never join the eval corpus; if one is ever
forwarded outside a rehearsal, say so out loud - nothing in the database will.
