"""Supabase Storage client (service key, private bucket). Originals are immutable:
uploads never upsert, and nothing in the codebase overwrites a stored object."""

import datetime
from typing import Literal

import httpx

from .config import Settings

StoreOutcome = Literal["stored", "already_there"]

# Signed URLs are short-lived on purpose: the bucket is private and the review
# screen (C6) re-fetches the detail payload whenever it needs a fresh link.
SIGNED_URL_TTL_SECONDS = 600


# The keys, built in one place so a writer and a reader can never disagree on
# where an object lives. Each names the one thing it holds, which is what makes
# "already there" safe to call success.


def document_original_key(tenant_id: str, document_id: str) -> str:
    """A paper's original, as the phone or the screen sent it."""
    return f"{tenant_id}/documents/{document_id}/original"


def brief_card_key(tenant_id: str, brief_date: datetime.date | str, recipient: str) -> str:
    """One morning's card for one recipient (C15.4). `recipient` is the
    recipient row's id, or `rehearsal-<phone>` for a founder's rehearsal."""
    return f"{tenant_id}/briefs/{brief_date}/{recipient}.png"


def sales_file_key(tenant_id: str, sha256: str) -> str:
    """A till export, under the hash the server computed of its bytes."""
    return f"{tenant_id}/sales/{sha256}.csv"


def _already_there(response: httpx.Response) -> bool:
    """Storage's refusal to overwrite (`x-upsert: false`): a 409, or the 400
    with a Duplicate body that Supabase's own API answers."""
    if response.status_code == 409:
        return True
    text = response.text.lower()
    return response.status_code == 400 and ("duplicate" in text or "already exists" in text)


class Storage:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self._bucket = settings.storage_bucket
        self._base_url = f"{settings.supabase_url}/storage/v1"
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {settings.supabase_service_key}",
                "apikey": settings.supabase_service_key,
            },
            timeout=60.0,
            transport=transport,
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def put_immutable(self, path: str, data: bytes, mime: str) -> StoreOutcome:
        """Keep `data` at `path`, never overwriting what is there.

        "already_there" is success, not an error: every key above names one
        thing, so the object a retry meets is its own first attempt's - an
        upload that landed before the step after it failed, or one that timed
        out after the bytes were written. Treating that as a failure strands
        the job at its own evidence for every retry it has. Any other refusal
        raises."""
        resp = await self._http.post(
            f"/object/{self._bucket}/{path}",
            content=data,
            headers={"Content-Type": mime, "x-upsert": "false"},
        )
        if _already_there(resp):
            return "already_there"
        resp.raise_for_status()
        return "stored"

    async def get(self, path: str) -> bytes:
        """Fetch a stored original (the extraction pipeline re-reads it)."""
        resp = await self._http.get(f"/object/{self._bucket}/{path}")
        resp.raise_for_status()
        return resp.content

    async def sign_url(self, path: str, expires_in: int = SIGNED_URL_TTL_SECONDS) -> str:
        """A short-lived signed URL for a stored object (C6: the review screen
        shows the photo without the bucket ever going public)."""
        resp = await self._http.post(
            f"/object/sign/{self._bucket}/{path}", json={"expiresIn": expires_in}
        )
        resp.raise_for_status()
        # Supabase returns a path like "/object/sign/{bucket}/{path}?token=...".
        return f"{self._base_url}{resp.json()['signedURL']}"
