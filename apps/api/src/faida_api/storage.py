"""Supabase Storage client (service key, private bucket). Originals are immutable:
uploads never upsert, and nothing in the codebase overwrites a stored object."""

import httpx

from .config import Settings


class Storage:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self._bucket = settings.storage_bucket
        self._http = httpx.AsyncClient(
            base_url=f"{settings.supabase_url}/storage/v1",
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
