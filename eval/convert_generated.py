"""Convert generated-fixture ground truth into the C3 schema.

`eval/fixtures/generated/<CASE>/<CASE>.expected.json` is written in the
generator's own shape (line_kind, expected_inventory_code, purchase_quantity,
net_before_tax and so on). A corpus/fixture `truth.json` is exactly a
serialized `ExtractionResult` (eval/README.md), so the two cannot be swapped
without a translation - this is it.

The mapping is deliberately lossy in one direction only: fields the C3 schema
does not model (inventory codes, base-unit conversions, hazard metadata) are
dropped rather than smuggled in, because truth.json must describe what is *on
the page*, not what we hope to derive from it.

That rule was stated here from the start and broken in the same file: until
WP-16 this mapped `pack_quantity` (a base-unit conversion, "2000") into C3's
`pack_size` (a printed fact, "2 kg") and `purchase_unit_text` into `unit`,
including for TH-01, a till receipt that prints no unit column at all. The
first live eval run scored pack_size 19% and unit 90% on those two lines of
code alone, with the model having read every cell correctly. Printed facts now
come from `eval.printed`, which reads the prompt the image was generated from;
money and quantities still come from this file, where they can be checked
arithmetically. Every parsed row is cross-checked against the modelled line
total, so a mis-parse fails the case instead of quietly rewriting truth.

    python -m eval.convert_generated           # write truth.json per case
    python -m eval.convert_generated --check    # report only, write nothing
"""

import argparse
import json
import pathlib
import sys
from decimal import Decimal

from faida_api.extraction import units
from faida_api.extraction.schema import (
    Classification,
    ExtractedInvoice,
    ExtractedLine,
    ExtractionResult,
    LineKind,
    TaxTreatment,
)

from eval.printed import PrintedPage, PrintedPageError
from eval.printed import read as read_printed_page

GENERATED = pathlib.Path(__file__).parent / "fixtures" / "generated"


def _dec(value: str | None) -> Decimal | None:
    return None if value in (None, "") else Decimal(str(value))


def _tax_treatment(header: dict) -> TaxTreatment | None:
    """Derived from the header the same way C4 derives it from an extraction:
    if the line-level total already equals the invoice total, the tax is
    inside the prices. Never read off a claim in the document."""
    total = _dec(header.get("invoice_total"))
    net = _dec(header.get("net_before_tax"))
    tax = _dec(header.get("tax_total"))
    if total is None or tax is None or tax <= 0:
        return None
    if net is not None and abs(net + tax - total) <= Decimal("0.10"):
        # The printed subtotal is the net and the total is the gross: whether
        # the *lines* are gross is what decides, and that is checked below.
        subtotal = _dec(header.get("subtotal_before_discount"))
        if subtotal is not None and abs(subtotal - total) <= Decimal("0.10"):
            return TaxTreatment.INCLUSIVE
        return TaxTreatment.EXCLUSIVE
    return None


def _check_alignment(case_id: str, page: PrintedPage, modelled: list[dict]) -> None:
    """The printed table and the modelled lines must describe the same
    invoice. Row count and every amount are compared before a single printed
    cell is trusted; a mismatch means the parse slipped and the case fails."""
    if len(page.rows) != len(modelled):
        raise PrintedPageError(
            f"{case_id}: prompt shows {len(page.rows)} printed rows, "
            f"expected.json models {len(modelled)}"
        )
    for index, line in enumerate(modelled):
        printed = page.amount(index)
        expected_total = _dec(line.get("line_total"))
        if printed is None or expected_total is None:
            continue
        if printed != expected_total:
            raise PrintedPageError(
                f"{case_id}: printed row {index + 1} amount {printed} does not match "
                f"the modelled line total {expected_total}"
            )


def convert(case_dir: pathlib.Path) -> ExtractionResult:
    case_id = case_dir.name
    expected = json.loads((case_dir / f"{case_id}.expected.json").read_text())

    if expected.get("expected_document_type") != "invoice":
        kind = expected.get("expected_document_type")
        classification = Classification.Z_REPORT if kind == "z_report" else Classification.OTHER
        return ExtractionResult(classification=classification, invoice=None)

    header = expected.get("header", {})
    modelled = expected.get("lines", [])
    page = read_printed_page(case_dir)
    if page.has_table:
        _check_alignment(case_id, page, modelled)

    lines = [
        ExtractedLine(
            # Printed text comes from the page; money and quantities from the
            # model file, where arithmetic can check them.
            raw_name=(page.description(index) if page.has_table else None)
            or line["description_raw"],
            line_kind=(
                LineKind.CHARGE
                if line.get("line_kind") == "non_stock_charge"
                else LineKind.STOCK_ITEM
            ),
            qty=_dec(line.get("purchase_quantity")),
            unit=page.unit(index) if page.has_table else None,
            # A page with no pack-size column can still print the pack inside
            # the item name ("RICE BASM 5KG"), and the catalog already reads it
            # there, so truth records it there too.
            pack_size=(
                page.pack_size(index)
                if page.has_table
                else units.first_printed(line["description_raw"])
            ),
            unit_price=_dec(line.get("unit_price")),
            line_total=_dec(line.get("line_total")),
        )
        for index, line in enumerate(modelled)
    ]
    treatment = _tax_treatment(header)
    invoice = ExtractedInvoice(
        supplier_name=header.get("supplier_name"),
        invoice_no=header.get("invoice_number"),
        invoice_date=header.get("invoice_date"),
        currency=header.get("currency"),
        # Printed terms decide; the generator's own kind is the fallback for a
        # receipt that states no terms (a till receipt is a cash purchase).
        payment_kind=page.payment_kind()
        or ("cash" if expected.get("expected_invoice_kind") == "cash_purchase" else None),
        lines=lines,
        subtotal=_dec(header.get("subtotal_before_discount")),
        tax=_dec(header.get("tax_total")),
        total=_dec(header.get("invoice_total")),
        discount_total=_dec(header.get("discount_total")),
        rounding_amount=_dec(header.get("rounding_amount")),
        tax_treatment=treatment,
    )
    return ExtractionResult(classification=Classification.INVOICE, invoice=invoice)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report only, write nothing")
    parser.add_argument(
        "--only",
        action="append",
        metavar="CASE",
        help="convert just this case (repeatable). Signed-off truth files must "
        "not be rewritten wholesale - a serialization-order or schema-field "
        "change would trip every SIGNOFF.json hash at once (test_signoff)",
    )
    args = parser.parse_args()

    # A directory without ground truth is not a case: `proposed/` holds
    # prompts for images nobody has generated yet (see its README).
    cases = sorted(
        d for d in GENERATED.iterdir() if d.is_dir() and (d / f"{d.name}.expected.json").exists()
    )
    if args.only:
        wanted = set(args.only)
        cases = [d for d in cases if d.name in wanted]
        missing = wanted - {d.name for d in cases}
        if missing:
            print(f"no such case: {', '.join(sorted(missing))}")
            return 1
    failures = 0
    for case_dir in cases:
        case_id = case_dir.name
        try:
            result = convert(case_dir)
        except Exception as exc:  # noqa: BLE001 - report every case, fail at the end
            print(f"{case_id:9} FAILED  {type(exc).__name__}: {exc}")
            failures += 1
            continue
        invoice = result.invoice
        detail = (
            f"{len(invoice.lines):2d} lines  total={invoice.total}  "
            f"treatment={invoice.tax_treatment or '-'}"
            if invoice is not None
            else f"classification={result.classification}"
        )
        has_image = (case_dir / f"{case_id}.jpg").exists()
        print(f"{case_id:9} ok  {'img' if has_image else '   '}  {detail}")
        if not args.check:
            (case_dir / "truth.json").write_text(
                result.model_dump_json(indent=2, exclude_none=False) + "\n"
            )
    print(
        f"\n{len(cases) - failures}/{len(cases)} converted" + ("" if args.check else " (written)")
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
