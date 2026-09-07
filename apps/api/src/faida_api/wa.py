"""Meta WhatsApp Cloud API client. The only place Graph API shapes live."""

import httpx

from .config import Settings


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
