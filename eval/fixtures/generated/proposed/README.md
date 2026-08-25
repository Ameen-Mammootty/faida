# Proposed cases - prompts only, not yet in the corpus

Five new prompts in the house format of `eval/fixtures/generated/`.
They are deliberately **not** listed in `../manifest.json` and have no `expected.json`, so
`eval.convert_generated` and the CI smoke set are unaffected until someone generates the images
and writes ground truth.

To promote one: generate `<CASE-ID>.jpg` from the prompt, write `<CASE-ID>.expected.json` in the
generator's shape (copy `../EDGE-01/EDGE-01.expected.json` as the template, `"synthetic": true`),
read the image back into `<CASE-ID>.verify.json`, move the folder up one level, and add the case
to `manifest.json`.

Every arithmetic figure in these prompts was checked before writing.
The buyer is Cedar & Spice Hospitality LLC throughout, matching the existing set, and four of the
five suppliers already appear in it.

## The five, and the hazard each one adds

| Case | Document | Hazards not covered by the existing 15 |
|---|---|---|
| `MP-01` | Page 1 of a stapled 2-page invoice, 12 lines, Gulf Pantry Supply | `page_1_of_2`, `carried_forward_subtotal`, `no_totals_block`, `staple_shadow` |
| `KSA-01` | Saudi ZATCA tax invoice, 6 lines, SAR, Arabic-dominant | `non_aed_currency`, `vat_rate_15`, `arabic_dominant_headings`, `zatca_qr_block` |
| `AMD-01` | Handwritten carbon cash bill with struck-through corrections | `struck_through_correction`, `ambiguous_date_format`, `amount_in_words`, `no_trn` |
| `STMT-01` | Monthly statement of account, 7 ledger rows, Dairy House | `not_a_purchase_invoice`, `looks_like_invoice`, `opening_balance`, `double_count_risk` |
| `OCC-01` | Phone photo, thumb covering the totals block, 6 lines | `occluded_totals`, `must_ask_not_guess`, `hand_holding_page` |

### Why each is worth generating

**`MP-01`** is the "stapled second page" this folder's own README names as a real-world failure
nobody prompts for.
The page carries `Carried forward to page 2: AED 1,908.90` and no total, no VAT line and no
subtotal.
Recording 1,908.90 as an invoice total, or reconciling green on a page whose VAT is on the sheet
that never arrived, is the failure to catch.
The correct behaviour is to notice the invoice is incomplete and ask, not to record a number that
is not the total.

**`KSA-01`** is the first non-UAE, non-AED document in the set: 15% VAT, SAR, and every heading
Arabic-first.
It exercises the GCC rate table in `constants.py` and the currency path end to end.
A pipeline that has only ever seen 5% and AED will assume both.

**`AMD-01`** carries two hazards that arrive together on real market chits.
The date reads `5/7/26`, which is 2026-07-05 in GCC day-first convention and 2026-05-07 if read
American-style, and nothing else on the page disambiguates it.
Two cells are struck through and rewritten: quantity 12 corrected to 15, and rate 8.00 corrected
to 9.00 with the amount corrected from 64.00 to 72.00.
The final figures reconcile to 402.00.
The struck figures do not, so reading the wrong one shows up immediately in reconciliation.

**`STMT-01`** is the expensive misclassification.
It is a genuine financial document from a supplier already in the master, with a total-looking
`CLOSING BALANCE DUE: AED 4,518.30` and four invoice references, two of which (`DHF-INV-260705-0688`)
correspond to invoices already in the system.
Recording it as a purchase invoice double-counts a month of buying and quietly destroys the profit
number.
`EDGE-03` covers a delivery note and `NEG-01` covers a non-document; neither covers a real
financial document that must not be recorded as a purchase.
The prompt deliberately omits the "this is not a tax invoice" line that some suppliers print.

**`OCC-01`** is the "thumb over the total" case, and it is the one prompt here that suspends the
folder's standing `degrade the paper, not the data` rule, on purpose and for exactly one region.
Every header field and all 6 line rows are readable; the totals block is completely covered.
Hidden ground truth, present on the page but invisible in the photograph:

```
Subtotal / net before VAT   AED   930.00
VAT 5%                      AED    46.50
TOTAL                       AED   976.50
```

The line sum is 930.00, so a pipeline that reconciles from lines can derive all three.
The failure to catch is fabricating a printed total it never saw, or claiming high confidence on a
header it could not read.
The right outcome is the amber question path.
