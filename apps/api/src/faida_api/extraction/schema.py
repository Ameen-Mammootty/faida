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


class ExtractedLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_name: str
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
