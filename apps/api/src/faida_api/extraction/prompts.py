"""Prompts for the Anthropic provider (plan.md §5 layers 1 and 3).

PROMPT_VERSION is recorded on every run next to the model id (C3); bump it on
any wording change so eval results and recorded CI fixtures stay comparable.
"""

from .schema import RepairTarget

PROMPT_VERSION = "v3"

SYSTEM_PROMPT = """\
You read supplier paperwork sent by GCC cafeterias over WhatsApp: supplier invoices and
delivery notes, often crumpled thermal paper photographed at an angle, mixed Arabic and
English, with handwritten quantities, prices, or corrections.

Classify the image first:
- invoice: a supplier invoice or delivery note charging the cafeteria for goods.
- z_report: a POS end-of-day sales summary.
- other: anything else - memes, chat screenshots, selfies, unrelated documents.
Only an invoice gets extracted; for z_report and other, return the classification alone.

Extraction rules:
- Copy every value exactly as printed. Keep amounts in the document's own currency and
  format; never convert currencies or units.
- Never invent or compute a value. A cell that is unreadable, ambiguous, or absent is
  null - do not derive a missing line_total from qty and unit_price.
- raw_name is the item name exactly as written, original language and spelling kept.
- List the lines in the order they appear on the document.
- invoice_date_text: the date exactly as printed ("2026-07-05", "5/7/26", "09.07.2026",
  "9 July 2026", "٥/٧/٢٠٢٦"); null when the document shows none. Copy it exactly - do not
  convert, reorder, or complete it. The calendar date is worked out from this text
  downstream, so a faithful copy of an odd or incomplete date is exactly right.
- currency as printed (AED, SAR, Dhs, ...); null when the document shows none.
- payment_terms_text: the payment or terms line exactly as printed ("Payment terms: 14
  days", "Cash on delivery", "صافي 30 يوم"); null when the document shows none. Copy it,
  do not interpret it - cash or credit is worked out from this text downstream.
- payment_kind: cash for a till or cash-register receipt, or when the document is marked
  paid; credit when it is plainly an on-account supplier invoice. Leave it null if the
  document does not make this clear - a printed terms line will settle it without you.
"""

EXTRACT_PROMPT = (
    "Classify this image. If it is a supplier invoice or delivery note, extract the "
    "supplier block, invoice number, date, currency, payment terms and payment kind, "
    "every line item, and the totals."
)


def build_repair_prompt(targets: list[RepairTarget]) -> str:
    """One scoped re-read (plan.md §5 layer 3): only the targeted cells, never the
    whole document. line_index None targets the document-level totals block."""
    parts = [
        "This document was already extracted; arithmetic checks failed on the cells listed",
        "below. Re-read ONLY those cells from the image - do not re-extract anything else.",
        "",
    ]
    for target in targets:
        cells = ", ".join(target.fields)
        if target.line_index is None:
            parts.append(f"- Totals block, cells: {cells}. Reason: {target.reason}")
        else:
            parts.append(
                f"- Line {target.line_index} (0-based in the extracted line list), "
                f"cells: {cells}. Reason: {target.reason}"
            )
    parts += [
        "",
        "Return one lines entry per targeted line: its line_index, raw_name exactly as",
        "printed (to confirm the row), fresh readings for the targeted cells, and null for",
        "every other field. Fill subtotal/tax/total only when the totals block is targeted",
        "above, else null. A cell you still cannot read stays null; never guess.",
    ]
    return "\n".join(parts)
