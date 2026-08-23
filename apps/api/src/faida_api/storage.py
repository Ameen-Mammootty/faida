"""Supabase Storage client (service key, private bucket). Originals are immutable:
uploads never upsert, and nothing in the codebase overwrites a stored object."""

import httpx

from .config import Settings

# Signed URLs are short-lived on purpose: the bucket is private and the review
# screen (C6) re-fetches the detail payload whenever it needs a fresh link.
SIGNED_URL_TTL_SECONDS = 600


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

    async def put(self, path: str, data: bytes, mime: str) -> str:
        resp = await self._http.post(
            f"/object/{self._bucket}/{path}",
            content=data,
            headers={"Content-Type": mime, "x-upsert": "false"},
        )
        resp.raise_for_status()
        return path

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
