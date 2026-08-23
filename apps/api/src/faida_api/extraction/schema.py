"""C3: the one extraction schema (plan.md §7.2).

Shared by the provider, deterministic validation, persistence, and eval ground
truth - a corpus truth.json is exactly a serialized ExtractionResult.
"""

import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Classification(StrEnum):
    INVOICE = "invoice"
    Z_REPORT = "z_report"  # stored and politely declined until M5
    OTHER = "other"  # memes, chat screenshots, anything else


class TaxTreatment(StrEnum):
    """Whether the line prices already contain VAT. Both shapes are normal in
    the GCC (C4): a UAE cash-and-carry receipt usually prints tax-inclusive
    prices, a trade delivery note usually does not."""

    EXCLUSIVE = "exclusive"  # lines are net; total = subtotal + tax
    INCLUSIVE = "inclusive"  # lines are gross; total = sum(lines), tax inside


class LineKind(StrEnum):
    """Delivery, cool-box hire and pallet fees belong in the invoice total and
    in cost, but they are not stock. Keeping them out of the catalog is what
    stops price alerts firing on a delivery fee (C4, WP-18)."""

    STOCK_ITEM = "stock_item"
    CHARGE = "charge"


class ExtractedLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_name: str
    line_kind: LineKind = LineKind.STOCK_ITEM
    qty: Decimal | None = None
    unit: str | None = None
    pack_size: str | None = None
    unit_price: Decimal | None = None
    line_total: Decimal | None = None


class ExtractedInvoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_name: str | None = None
    invoice_no: str | None = None
    invoice_date: datetime.date | None = None
    currency: str | None = None
    payment_kind: Literal["credit", "cash"] | None = None
    lines: list[ExtractedLine] = Field(default_factory=list)
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal | None = None
    # Stored POSITIVE and subtracted, the way an invoice prints it. Without
    # these the C4 identities miss a trade discount exactly, failing correct
    # invoices into amber (WP-18).
    discount_total: Decimal | None = None
    rounding_amount: Decimal | None = None
    # Printed facts, read like any other field: many GCC invoices state
    # "prices inclusive of VAT" or "VAT 5%". C4 makes these a TIE-BREAKER
    # ONLY - the treatment is derived from the arithmetic, never taken on the
    # document's word (plan.md §5 layer 5: derived, not self-reported).
    tax_treatment: TaxTreatment | None = None
    vat_rate: Decimal | None = None


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classification: Classification
    invoice: ExtractedInvoice | None = None  # present iff classification is INVOICE


class RepairTarget(BaseModel):
    """One scoped re-read request (plan.md §5 layer 3), e.g. 'Line 3: qty 12 x
    4.50 != extracted 58.00 - re-read those cells.' line_index None targets the
    document-level totals block."""

    model_config = ConfigDict(extra="forbid")

    line_index: int | None = None
    fields: list[str]
    reason: str


class RepairResult(BaseModel):
    """A partial patch: only the re-read values. Merge semantics live in
    WP-12; repair never touches fields that passed."""

    model_config = ConfigDict(extra="forbid")

    lines: dict[int, ExtractedLine] = Field(default_factory=dict)
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal | None = None
