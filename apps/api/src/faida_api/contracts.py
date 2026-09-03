"""Pinned contracts C1 (status machines) and C2 (job kinds) - plan.md §7.2.

Frozen for parallel delegation: a change here goes through the manager and the
Decision Log, never a sub-agent working alone. Values must stay in lockstep with
the check constraints in supabase/migrations/ - 0001_init.sql defines both, and
0010 (documents) and 0017 (invoices) have since replaced them, so the newest
migration naming a table is the one that owns its vocabulary. The lockstep is
enforced behaviourally in tests/test_contracts.py, not by this sentence.

C2 as amended 2026-09-03 (M7, Decision Log; WP-72 built it): jobs carry their
scope. `process_wa_message` is the one named resolver - it maps the sender
phone to a branch and tenant and carries the phone - and every job it enqueues
carries `tenant_id` and `branch_id`. Every handler that loads a tenant-owned
row reads it scoped by the payload's tenant and refuses a mismatch by raising,
so the job fails loudly and is never guessed; a job without a tenant is a
failed job. The documented exception is `process_wa_message` itself: its
payload is the inbound message id alone, because resolving the tenant is its
job and the webhook that enqueues it stays dumb and fast. A phone no branch is
registered to resolves to nothing: the inbound row is stamped
`ignored_unknown_sender` before anything else, the phone is answered once a
day, and no document, job or model call exists for it.
"""

from enum import StrEnum
from typing import Any

# Inbound message types the webhook treats as documents (C2 ingest path).
MEDIA_TYPES = {"image", "document"}


class JobKind(StrEnum):
    # The resolver: ingest + immediate "Got it" ack; enqueues EXTRACT_DOCUMENT
    # for media. Payload: {"message_id": str} - the one job without a tenant,
    # because finding the tenant is what it does.
    PROCESS_WA_MESSAGE = "process_wa_message"
    # Runs the extraction pipeline, sends the parsed summary as a second
    # message. Payload: {"document_id": str, "tenant_id": str,
    # "branch_id": str | None}. One per document, ever (jobs_extract_document_uidx,
    # 0018): enqueued through Database.enqueue_once.
    EXTRACT_DOCUMENT = "extract_document"


# wa_messages.status for an inbound message from a phone no branch is
# registered to (C2 as amended). Stamped before any reply, so the decision to
# ignore the phone is recorded whether or not Meta ever delivered the reply,
# and the 24 h silence is derived from rows carrying it.
WA_STATUS_IGNORED_UNKNOWN_SENDER = "ignored_unknown_sender"


class JobRefused(RuntimeError):
    """A job the worker will not run: it carries no tenant, or the row it
    names does not exist in that tenant. Raised, never logged-and-skipped, so
    the job lands in the queue's failure path with the reason on it."""


def job_tenant_id(kind: str, payload: dict[str, Any]) -> str:
    """The tenant a job carries, or JobRefused. Every handler that loads a
    tenant-owned row starts here: the tenant comes from the payload the
    resolver wrote, never from the row, so a job that names no tenant cannot
    find one by reading the thing it was about to touch."""
    tenant_id = payload.get("tenant_id")
    if not tenant_id:
        raise JobRefused(
            f"{kind} job carries no tenant_id (C2): a job without a tenant is a failed job"
        )
    return str(tenant_id)


class DocumentStatus(StrEnum):
    RECEIVED = "received"
    PROCESSING = "processing"
    EXTRACTED = "extracted"  # a draft invoice with checks exists
    FAILED = "failed"  # repair also failed, unreadable, or not an invoice


class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    AWAITING_CONFIRM = "awaiting_confirm"
    CONFIRMED = "confirmed"
    NEEDS_REVIEW = "needs_review"  # e.g. cash invoices held for approval
    DISMISSED = "dismissed"  # a WP-44 duplicate hold, resolved from the screen


# Ingest states only: the worker owns every document transition, and EXTRACTED
# is terminal because the invoice owns the review lifecycle from there (a
# document is confirmed only in the sense that its invoice is - read it through
# invoices.document_id). FAILED -> PROCESSING is the retry path (recovery is a
# screen, not a subsystem - plan.md §2 rule 5).
DOCUMENT_TRANSITIONS: dict[DocumentStatus, set[DocumentStatus]] = {
    DocumentStatus.RECEIVED: {DocumentStatus.PROCESSING},
    DocumentStatus.PROCESSING: {DocumentStatus.EXTRACTED, DocumentStatus.FAILED},
    DocumentStatus.EXTRACTED: set(),
    DocumentStatus.FAILED: {DocumentStatus.PROCESSING},
}

# Corrections keep an invoice in AWAITING_CONFIRM (no transition); NEEDS_REVIEW
# clears through the review screen (M3) or cash approval (M7), or - when it is a
# WP-44 duplicate hold - through DISMISSED. Only NEEDS_REVIEW reaches DISMISSED
# because only a held duplicate carries duplicate_of_invoice_id, and the
# pipeline sets that in the same branch that sets NEEDS_REVIEW. Both terminal
# states are terminal: a dismissed invoice is refused by the single confirm
# write, and a confirmed one is a financial record.
INVOICE_TRANSITIONS: dict[InvoiceStatus, set[InvoiceStatus]] = {
    InvoiceStatus.DRAFT: {InvoiceStatus.AWAITING_CONFIRM, InvoiceStatus.NEEDS_REVIEW},
    InvoiceStatus.AWAITING_CONFIRM: {InvoiceStatus.CONFIRMED, InvoiceStatus.NEEDS_REVIEW},
    InvoiceStatus.NEEDS_REVIEW: {InvoiceStatus.CONFIRMED, InvoiceStatus.DISMISSED},
    InvoiceStatus.CONFIRMED: set(),
    InvoiceStatus.DISMISSED: set(),
}
