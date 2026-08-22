"""Meta webhook endpoints. The receiver is dumb and fast: verify signature,
dedupe on message_id, store raw, enqueue, return 200. All heavy work is in the worker."""

import hashlib
import hmac
import json
import logging
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import PlainTextResponse

from .contracts import MEDIA_TYPES, JobKind

logger = logging.getLogger(__name__)
router = APIRouter()


def verify_signature(raw_body: bytes, signature_header: str | None, app_secret: str) -> bool:
    """Meta signs the raw body: X-Hub-Signature-256 = 'sha256=' + HMAC-SHA256(app_secret, body)."""
    if not app_secret:
        # Refuse to run unsigned in any environment: misconfiguration must fail loudly.
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature_header.removeprefix("sha256="), expected)


def extract_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten a Cloud API webhook payload into inbound message dicts.
    Status updates (delivered/read receipts) are not messages and are skipped."""
    out: list[dict[str, Any]] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []):
                msg_type = msg.get("type")
                media_id = None
                if msg_type in MEDIA_TYPES:
                    media_id = msg.get(msg_type, {}).get("id")
                out.append(
                    {
                        "id": msg.get("id"),
                        "from": msg.get("from"),
                        "type": msg_type,
                        "media_id": media_id,
                        "raw": msg,
                    }
                )
    return out


@router.get("/webhook")
async def verify_webhook(request: Request) -> Response:
    params = request.query_params
    if (
        params.get("hub.mode") == "subscribe"
        and params.get("hub.verify_token") == request.app.state.settings.meta_verify_token
        and params.get("hub.challenge")
    ):
        return PlainTextResponse(params["hub.challenge"])
    return Response(status_code=403)


@router.post("/webhook")
async def receive_webhook(request: Request) -> Response:
    raw = await request.body()
    settings = request.app.state.settings
    signature = request.headers.get("X-Hub-Signature-256")
    if not verify_signature(raw, signature, settings.meta_app_secret):
        return Response(status_code=403)

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return Response(status_code=400)

    db = request.app.state.db
    for msg in extract_messages(payload):
        if not msg["id"]:
            continue
        fresh = await db.record_inbound_message(msg["id"], msg["from"], msg["type"], msg["raw"])
        if fresh:
            await db.enqueue(JobKind.PROCESS_WA_MESSAGE, {"message_id": msg["id"]})
        else:
            logger.info("duplicate wa message skipped: %s", msg["id"])
    return Response(status_code=200)
