"""Pinned contracts C1 (status machines) and C2 (job kinds) - plan.md §7.2.

Frozen for parallel delegation: a change here goes through the manager and the
Decision Log, never a sub-agent working alone. Values must stay in lockstep with
the check constraints in supabase/migrations/0001_init.sql.
"""

from enum import StrEnum

# Inbound message types the webhook treats as documents (C2 ingest path).
MEDIA_TYPES = {"image", "document"}


class JobKind(StrEnum):
    # Ingest + immediate "Got it" ack; enqueues EXTRACT_DOCUMENT for media.
    PROCESS_WA_MESSAGE = "process_wa_message"
    # Runs the extraction pipeline, sends the parsed summary as a second
    # message. Payload: {"document_id": str}.
    EXTRACT_DOCUMENT = "extract_document"


class DocumentStatus(StrEnum):
    RECEIVED = "received"
    PROCESSING = "processing"
    EXTRACTED = "extracted"  # a draft invoice with checks exists
    CONFIRMED = "confirmed"  # its invoice was confirmed
    FAILED = "failed"  # repair also failed, unreadable, or not an invoice


class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    AWAITING_CONFIRM = "awaiting_confirm"
    CONFIRMED = "confirmed"
    NEEDS_REVIEW = "needs_review"  # e.g. cash invoices held for approval


# The worker owns document transitions up to EXTRACTED/FAILED; the confirm flow
# owns EXTRACTED -> CONFIRMED. FAILED -> PROCESSING is the retry path
# (recovery is a screen, not a subsystem - plan.md §2 rule 5).
DOCUMENT_TRANSITIONS: dict[DocumentStatus, set[DocumentStatus]] = {
    DocumentStatus.RECEIVED: {DocumentStatus.PROCESSING},
    DocumentStatus.PROCESSING: {DocumentStatus.EXTRACTED, DocumentStatus.FAILED},
    DocumentStatus.EXTRACTED: {DocumentStatus.CONFIRMED},
    DocumentStatus.CONFIRMED: set(),
    DocumentStatus.FAILED: {DocumentStatus.PROCESSING},
}

# Corrections keep an invoice in AWAITING_CONFIRM (no transition); NEEDS_REVIEW
# clears through the review screen (M3) or cash approval (M6).
INVOICE_TRANSITIONS: dict[InvoiceStatus, set[InvoiceStatus]] = {
    InvoiceStatus.DRAFT: {InvoiceStatus.AWAITING_CONFIRM, InvoiceStatus.NEEDS_REVIEW},
    InvoiceStatus.AWAITING_CONFIRM: {InvoiceStatus.CONFIRMED, InvoiceStatus.NEEDS_REVIEW},
    InvoiceStatus.NEEDS_REVIEW: {InvoiceStatus.CONFIRMED},
    InvoiceStatus.CONFIRMED: set(),
}
