"""Meta WhatsApp Cloud API client. The only place Graph API shapes live."""

from collections.abc import Sequence

import httpx

from .config import Settings


def _raise_meta_refusal(response: httpx.Response) -> None:
    """Raise Meta's own words about a refusal, not just its status code.

    `httpx.raise_for_status` prints the status and the URL, and the fact that
    decides what to do at seven in the morning is in the body: the template is
    not approved (132001), it is paused or disabled (132015, 132016), or it
    was edited to a different variable count (132000). The exception type is
    unchanged - the worker's retry path treats it exactly as it treats the 500
    a free-text send raises (M10 WP-102, decomposition §7's failure table).
    """
    try:
        error = response.json().get("error") or {}
    except ValueError:
        error = {}
    said = error.get("message") or response.text or "no reason given"
    code = error.get("code")
    details = (error.get("error_data") or {}).get("details")
    message = f"Meta answered {response.status_code}: {said}"
    if code is not None:
        message += f" (code {code})"
    if details:
        message += f" - {details}"
    raise httpx.HTTPStatusError(message, request=response.request, response=response)


class WhatsAppClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self._phone_number_id = settings.meta_phone_number_id
        self._http = httpx.AsyncClient(
            base_url=settings.graph_api_base,
            headers={"Authorization": f"Bearer {settings.meta_access_token}"},
            timeout=30.0,
            transport=transport,
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def get_media(self, media_id: str) -> tuple[bytes, str]:
        """Resolve a media id to (bytes, mime). Media URLs expire — download promptly."""
        meta_resp = await self._http.get(f"/{media_id}")
        meta_resp.raise_for_status()
        meta = meta_resp.json()
        mime = meta.get("mime_type", "application/octet-stream")
        # Absolute URL overrides base_url; auth header is required on the CDN fetch too.
        media_resp = await self._http.get(meta["url"])
        media_resp.raise_for_status()
        return media_resp.content, mime

    async def send_text(self, to_phone: str, body: str, *, reply_to: str | None = None) -> str:
        """Send a free-form text (valid inside the 24h service window). Returns message id.

        `reply_to` is the WhatsApp id of an earlier message in the chat - the
        invoice photo a reply is about (WP-125) - and makes this a contextual
        reply, quoted above that message. Meta drops the quote bubble after
        about 30 days but still delivers the text."""
        message: dict = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
        }
        if reply_to is not None:
            message["context"] = {"message_id": reply_to}
        message["type"] = "text"
        message["text"] = {"preview_url": False, "body": body}
        resp = await self._http.post(f"/{self._phone_number_id}/messages", json=message)
        resp.raise_for_status()
        return resp.json()["messages"][0]["id"]

    async def send_template(
        self,
        to_phone: str,
        name: str,
        language: str,
        parameters: Sequence[str],
        *,
        header_image_id: str | None = None,
    ) -> str:
        """Send an approved template. Returns Meta's message id (M10 WP-102, C15).

        The one thing a free-form text cannot do: a template is accepted
        outside the 24-hour service window, which every 07:00 brief is
        (`send_text`'s own window note, and Meta's 131047). The values fill
        the template's `{{1}}`..`{{n}}` in the order given, so the caller's
        order is the template's order and a count that does not match is
        Meta's 132000 - which is why the filler asserts the count before we
        ever get here (C15.9).

        `header_image_id` is a media id from `upload_media`: under the picture
        card (P15) the header component carries it and must come first in
        `components`. A non-2xx raises, carrying Meta's reason, and the caller
        decides whether that is a retry or a dead morning."""
        components: list[dict] = []
        if header_image_id is not None:
            components.append(
                {
                    "type": "header",
                    "parameters": [{"type": "image", "image": {"id": header_image_id}}],
                }
            )
        components.append(
            {
                "type": "body",
                "parameters": [{"type": "text", "text": value} for value in parameters],
            }
        )
        message = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": "template",
            "template": {
                "name": name,
                "language": {"code": language},
                "components": components,
            },
        }
        resp = await self._http.post(f"/{self._phone_number_id}/messages", json=message)
        if resp.is_error:
            _raise_meta_refusal(resp)
        return resp.json()["messages"][0]["id"]

    async def upload_media(self, data: bytes, mime: str) -> str:
        """Upload bytes to Meta and return the media id (M10 WP-102, for WP-106).

        The brief's picture card is drawn fresh each morning, so there is
        nothing to link to: Meta wants the file itself, multipart, and hands
        back an id that a template's header component may name for the next
        thirty days. The upload is a separate request from the send, so a
        refusal here fails the job before any message leaves - a half-sent
        brief is not a thing that can happen."""
        filename = f"upload.{mime.rsplit('/', 1)[-1] or 'bin'}"
        resp = await self._http.post(
            f"/{self._phone_number_id}/media",
            data={"messaging_product": "whatsapp", "type": mime},
            files={"file": (filename, data, mime)},
        )
        if resp.is_error:
            _raise_meta_refusal(resp)
        return resp.json()["id"]
