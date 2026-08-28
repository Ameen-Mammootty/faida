"""The one seam where a raw extraction becomes the invoice we work with.

Three things happen between the model's answer and everything downstream, and
all are derivations from printed facts rather than re-readings of the page:
the printed currency word becomes an ISO code, the printed payment terms
become cash or credit, and the printed date becomes a calendar date under the
GCC day-first rule (an ambiguous date staying null, per C3).

They live together here because they have to happen in every path that
produces an invoice - the WhatsApp pipeline, manual entry, and the eval - and
they were already drifting: the eval was copying the pipeline's currency call
by hand, which is how a harness ends up scoring a program nobody ships.
"""

from .currency import normalize_currency
from .dates import derive_invoice_date
from .payment import derive_payment_kind
from .schema import ExtractedInvoice

# A printed table marks "nothing here" with a dash, and a model told to copy
# exactly as printed copies the dash. EDGE-01's delivery-charge row prints "-"
# for its pack size; recorded literally it becomes a pack size of "-", which
# then has to be explained on the review screen and compared against in the
# catalog. An absence is recorded as an absence.
PLACEHOLDERS = frozenset({"-", "--", "---", "\u2013", "\u2014", "n/a", "na", "none", "nil", ""})


def blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    text = " ".join(value.split())
    return None if text.casefold() in PLACEHOLDERS else text


def normalize_extracted(invoice: ExtractedInvoice) -> ExtractedInvoice:
    """Apply every printed-fact derivation to a freshly extracted invoice."""
    lines = [
        line.model_copy(
            update={
                "unit": blank_to_none(line.unit),
                "pack_size": blank_to_none(line.pack_size),
            }
        )
        for line in invoice.lines
    ]
    return invoice.model_copy(
        update={
            "currency": normalize_currency(invoice.currency),
            "payment_kind": derive_payment_kind(invoice.payment_terms_text, invoice.payment_kind),
            "invoice_date": derive_invoice_date(invoice.invoice_date_text, invoice.invoice_date),
            "lines": lines,
        }
    )
