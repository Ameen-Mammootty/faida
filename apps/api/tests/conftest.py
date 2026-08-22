import os
import pathlib

import asyncpg
import httpx
import pytest

from faida_api.config import Settings
from faida_api.db import Database
from faida_api.extraction.provider import ProviderUsage
from faida_api.extraction.schema import ExtractionResult, RepairResult, RepairTarget

MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parents[3] / "supabase" / "migrations"
SEED_FILE = pathlib.Path(__file__).resolve().parents[3] / "supabase" / "seed.sql"

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

requires_db = pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL not set")

TEST_APP_SECRET = "test-app-secret"
DEMO_PHONE = "971500000000"  # matches seed.sql


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url=TEST_DATABASE_URL or "",
        meta_verify_token="verify-me",
        meta_app_secret=TEST_APP_SECRET,
        meta_access_token="test-token",
        meta_phone_number_id="1234567890",
        supabase_url="http://supabase.test",
        supabase_service_key="service-key",
        worker_enabled=False,
    )


@pytest.fixture
async def db(settings):
    """Fresh schema per test: drop, migrate, seed."""
    conn = await asyncpg.connect(TEST_DATABASE_URL)
    await conn.execute("drop schema public cascade; create schema public;")
    for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
        await conn.execute(migration.read_text())
    await conn.execute(SEED_FILE.read_text())
    await conn.close()

    database = Database(TEST_DATABASE_URL)
    await database.connect()
    yield database
    await database.close()


class FakeMeta:
    """Mock transport for the Graph API: media metadata, media bytes, message send."""

    def __init__(self):
        self.sent: list[dict] = []
        self.media_bytes = b"\xff\xd8fake-jpeg-bytes"

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/messages"):
                import json

                self.sent.append(json.loads(request.content))
                return httpx.Response(
                    200, json={"messages": [{"id": f"wamid.out{len(self.sent)}"}]}
                )
            if request.url.host == "cdn.test":
                return httpx.Response(200, content=self.media_bytes)
            # media id lookup
            return httpx.Response(
                200, json={"url": "https://cdn.test/media/abc", "mime_type": "image/jpeg"}
            )

        return httpx.MockTransport(handle)


class FakeStorage:
    """Mock transport for Supabase Storage."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            # Path shape: /storage/v1/object/{bucket}/{path...} -> key is {path...}
            key = request.url.path.removeprefix("/storage/v1/object/").split("/", 1)[1]
            if request.method == "GET":
                if key in self.objects:
                    return httpx.Response(200, content=self.objects[key])
                return httpx.Response(404, json={"error": "Object not found"})
            if key in self.objects:
                return httpx.Response(409, json={"error": "Duplicate"})
            self.objects[key] = request.content
            return httpx.Response(200, json={"Key": key})

        return httpx.MockTransport(handle)


class FakeExtraction:
    """Scriptable ExtractionProvider: canned results, recorded calls. Tests
    always inject one; the real provider never runs in the suite."""

    def __init__(
        self,
        result: ExtractionResult | None = None,
        repair_patch: RepairResult | None = None,
        extract_error: Exception | None = None,
    ):
        self.result = result
        self.repair_patch = repair_patch if repair_patch is not None else RepairResult()
        self.extract_error = extract_error
        self.extract_calls: list[tuple[bytes, str]] = []
        self.repair_calls: list[list[RepairTarget]] = []

    @staticmethod
    def usage() -> ProviderUsage:
        return ProviderUsage(
            model_id="fake-model",
            prompt_version="v0",
            input_tokens=100,
            output_tokens=50,
            latency_ms=7,
        )

    async def extract(self, image: bytes, mime: str) -> tuple[ExtractionResult, ProviderUsage]:
        self.extract_calls.append((image, mime))
        if self.extract_error is not None:
            raise self.extract_error
        assert self.result is not None, "FakeExtraction needs a canned result"
        return self.result, self.usage()

    async def repair(
        self, image: bytes, mime: str, targets: list[RepairTarget]
    ) -> tuple[RepairResult, ProviderUsage]:
        self.repair_calls.append(targets)
        return self.repair_patch, self.usage()


def wa_image_payload(message_id: str = "wamid.in1", from_phone: str = DEMO_PHONE) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "waba-id",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "messages": [
                                {
                                    "id": message_id,
                                    "from": from_phone,
                                    "timestamp": "1755850000",
                                    "type": "image",
                                    "image": {"id": "media-1", "mime_type": "image/jpeg"},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
