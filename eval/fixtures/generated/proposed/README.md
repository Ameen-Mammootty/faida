# Proposed cases - not yet in the corpus

Five prompts in the house format of `eval/fixtures/generated/`.
`CUT-01.png` was generated on 2026-08-29; the other four cases still have prompts only.
`AMD-01` was promoted into the corpus on 2026-08-28 for WP-27 (its prompt reworked into the
machine-readable table shape `eval/printed.py` parses); it awaits an image like the other
dry-run cases.
These proposed cases are deliberately **not** listed in `../manifest.json` and have no `expected.json`, so
`eval.convert_generated` and the CI smoke set are unaffected until someone generates the images
and writes ground truth.

To promote one: generate `<CASE-ID>.jpg` from the prompt, write `<CASE-ID>.expected.json` in the
generator's shape (copy `../EDGE-01/EDGE-01.expected.json` as the template, `"synthetic": true`),
read the image back into `<CASE-ID>.verify.json`, move the folder up one level, and add the case
to `manifest.json`.

Every arithmetic figure in these prompts was checked before writing.
The buyer is Cedar & Spice Hospitality LLC throughout, matching the existing set, and most of
the suppliers already appear in it.

## The five, and the hazard each one adds

| Case | Document | Hazards not covered by the existing 15 |
|---|---|---|
| `MP-01` | Page 1 of a stapled 2-page invoice, 12 lines, Gulf Pantry Supply | `page_1_of_2`, `carried_forward_subtotal`, `no_totals_block`, `staple_shadow` |
| `KSA-01` | Saudi ZATCA tax invoice, 6 lines, SAR, Arabic-dominant | `non_aed_currency`, `vat_rate_15`, `arabic_dominant_headings`, `zatca_qr_block` |
| `STMT-01` | Monthly statement of account, 7 ledger rows, Dairy House | `not_a_purchase_invoice`, `looks_like_invoice`, `opening_balance`, `double_count_risk` |
| `OCC-01` | Phone photo, thumb covering the totals block, 6 lines | `occluded_totals`, `must_ask_not_guess`, `hand_holding_page` |
| `CUT-01` | Export invoice in USD, photographed with the foot of the page outside the frame, 5 lines | `off_frame_totals`, `must_reconstruct_not_compute`, `non_aed_currency`, `zero_rated_export` |

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

**`STMT-01`** is the expensive misclassification.
It is a genuine financial document from a supplier already in the master, with a total-looking
`CLOSING BALANCE DUE: AED 4,518.30` and four invoice references, two of which (`DHF-INV-260705-0688`)
correspond to invoices already in the system.
Recording it as a purchase invoice double-counts a month of buying and quietly destroys the profit
number.
`EDGE-03` covers a delivery note and `NEG-01` covers a non-document; neither covers a real
financial document that must not be recorded as a purchase.
The prompt deliberately omits the "this is not a tax invoice" line that some suppliers print.

**`CUT-01`** is the live 2026-08-25 failure, as a fixture: an invoice whose totals block was
never in the picture at all.
It is the one case in this folder where the missing total cannot be recovered by looking harder
at the image, which is what separates it from `OCC-01` - a thumb can be lifted, a frame cannot be
widened after the shutter.
The right outcome is the WP-26 conversation: `total` null, the reply showing the line sum
(710.50) and asking whether that is the whole invoice and whether the prices carry VAT, a bare
`OK` refused, and the answer stored with C8 origin `reconstructed`.
It carries a second hazard deliberately, because the two arrived together in real life: the
document is billed in **USD** against an AED tenant, so it also exercises the WP-28 hold - the
currency question in the same reply, the invoice confirming normally, and price memory left
completely alone.
The arithmetic is built so the reconstruction is checkable: zero-rated, delivery included, so the
true total is exactly the line sum and `total 710.50 no vat` is the correct answer.
Read it against `OCC-01`, where the line sum is 930.00 and the true total is 976.50 - the pair is
the whole argument for asking instead of computing, in two images.

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
