"""C3: the one extraction schema (plan.md §7.2).

Shared by the provider, deterministic validation, persistence, and eval ground
truth - a corpus truth.json is exactly a serialized ExtractionResult.
"""

import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, WithJsonSchema, field_validator

from .money import parse_money

# Money and quantities cross the provider boundary as plain decimal strings.
#
# Pydantic's default JSON schema for `Decimal | None` is a three-branch union
# carrying a negative-lookahead regex, and the schema has fourteen of them
# inside an unbounded array of lines. That compiled fine until one more
# optional field was added and the API began rejecting every request outright
# with "Schema is too complex" / "Grammar compilation timed out" - a hard 400
# on every invoice, not a degraded read. Declaring one concrete type drops the
# regex and a branch per field.
#
# It also removes a real ambiguity: a JSON number is a float on the wire, and
# C4 bans float money everywhere else in this codebase.
# The string form invites the printed one - the model returns "AED 332.00"
# when told to copy exactly as printed, which is correct of it - so the printed
# form is parsed here rather than argued with in the prompt.
Money = Annotated[Decimal, BeforeValidator(parse_money), WithJsonSchema({"type": "string"})]


class Classification(StrEnum):
    INVOICE = "invoice"
    Z_REPORT = "z_report"  # stored and politely declined until M8
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
    qty: Money | None = None
    unit: str | None = None
    pack_size: str | None = None
    unit_price: Money | None = None
    line_total: Money | None = None


class ExtractedInvoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_name: str | None = None
    invoice_no: str | None = None
    invoice_date: datetime.date | None = None
    currency: str | None = None
    payment_kind: Literal["credit", "cash"] | None = None
    # The terms line as printed ("Payment terms: 14 days", "Cash on delivery").
    # A printed fact, copied not interpreted: extraction.payment turns it into
    # payment_kind, the same split as the printed currency word and its ISO
    # code. Not persisted - it is an input to that derivation, not a column.
    payment_terms_text: str | None = None
    lines: list[ExtractedLine] = Field(default_factory=list)
    subtotal: Money | None = None
    tax: Money | None = None
    total: Money | None = None
    # Stored POSITIVE and subtracted, the way an invoice prints it. Without
    # these the C4 identities miss a trade discount exactly, failing correct
    # invoices into amber (WP-18).
    discount_total: Money | None = None
    rounding_amount: Money | None = None
    # Printed facts, read like any other field: many GCC invoices state
    # "prices inclusive of VAT" or "VAT 5%". C4 makes these a TIE-BREAKER
    # ONLY - the treatment is derived from the arithmetic, never taken on the
    # document's word (plan.md §5 layer 5: derived, not self-reported).
    tax_treatment: TaxTreatment | None = None
    vat_rate: Money | None = None

    @field_validator("discount_total")
    @classmethod
    def _discount_is_a_magnitude(cls, value: Decimal | None) -> Decimal | None:
        """A discount is a reduction, so C4 states its identity as
        `line sum - discount + rounding` and this field carries the magnitude.

        Invoices print the same fact as "-41.70", and the first live eval run
        caught the model copying that sign faithfully: with D negative the
        identity *adds* the discount, misses by twice it, and fails a
        perfectly-read invoice into amber (EDGE-01, 2026-08-24). Canonicalizing
        here rather than in the prompt means no rewording can regress it, and
        every path - pipeline, manual entry, eval - gets the same convention
        from the one place the schema is defined. This normalizes a
        representation, like the ISO currency code; it never invents a value.
        """
        return None if value is None else abs(value)


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
    subtotal: Money | None = None
    tax: Money | None = None
    total: Money | None = None
