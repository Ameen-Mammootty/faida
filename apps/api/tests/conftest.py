import os
import pathlib
import time

import asyncpg
import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from jwt.algorithms import ECAlgorithm

from faida_api.auth import TokenVerifier
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
DEMO_TENANT_ID = "00000000-0000-0000-0000-000000000001"  # matches seed.sql

#: The signed-in owner every API test acts as (M7 WP-70): a fixed auth user
#: id whose membership row in the seeded tenant the `db` fixture plants right
#: after the seed. So every module's API fixture is one person signed in to
#: the demo tenant - the same single identity the shared token used to
#: stand for, now with a name on it.
TEST_USER_ID = "00000000-0000-4000-8000-0000000000aa"
TEST_ACTOR = f"user:{TEST_USER_ID}"


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
    await conn.execute(
        "insert into memberships (tenant_id, user_id) values ($1, $2)", DEMO_TENANT_ID, TEST_USER_ID
    )
    await conn.close()

    database = Database(TEST_DATABASE_URL)
    await database.connect()
    yield database
    await database.close()


class FakeJwks:
    """A local signing key pair and the JWKS endpoint that publishes its
    public half, mocked at the transport layer like Meta and storage: the
    verifier never learns it is talking to a fake. `mint` signs access tokens
    the way Supabase Auth does (ES256 with a key id; issuer, audience, expiry
    and subject claims), and every keyword is overridable so a test can forge
    exactly one thing wrong. `fetches` counts JWKS reads and `down` makes the
    endpoint unreachable, for the cache and outage cases."""

    def __init__(self, issuer: str = "http://supabase.test/auth/v1", kid: str = "faida-test-key"):
        self.issuer = issuer
        self.kid = kid
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        self.keys: list[dict] = [self.public_jwk(self.private_key, kid)]
        self.fetches = 0
        self.down = False

    @staticmethod
    def public_jwk(private_key, kid: str) -> dict:
        jwk = ECAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
        return {**jwk, "kid": kid, "alg": "ES256", "use": "sig"}

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            assert request.url.path.endswith("/auth/v1/.well-known/jwks.json"), request.url
            self.fetches += 1
            if self.down:
                raise httpx.ConnectError("sign-in service down", request=request)
            return httpx.Response(200, json={"keys": self.keys})

        return httpx.MockTransport(handle)

    def mint(
        self,
        sub: str = TEST_USER_ID,
        *,
        kid: str | None = None,
        alg: str = "ES256",
        key=None,
        issuer: str | None = None,
        audience: str | None = "authenticated",
        expires_in: int = 3600,
        **claims,
    ) -> str:
        now = int(time.time())
        payload = {
            "iss": issuer or self.issuer,
            "sub": sub,
            "iat": now,
            "exp": now + expires_in,
            "role": "authenticated",
            **claims,
        }
        if audience is not None:
            payload["aud"] = audience
        return jwt.encode(
            payload, key or self.private_key, algorithm=alg, headers={"kid": kid or self.kid}
        )


#: One key pair for the whole suite, and the headers every API test sends:
#: an access token for TEST_USER_ID signed by it. Fixture apps are wired to
#: the same fake JWKS by `wire_auth`, so the token verifies there and nowhere
#: else.
JWKS = FakeJwks()
AUTH = {"Authorization": f"Bearer {JWKS.mint()}"}


def wire_auth(app: FastAPI) -> None:
    """The one door for a test app: the real verifier over the fake JWKS.
    Call it after `app.state.settings` is set; the issuer and key URL derive
    from that settings' `supabase_url`."""
    app.state.auth = TokenVerifier(app.state.settings, transport=JWKS.transport())


class FakeMeta:
    """Mock transport for the Graph API: media metadata, media bytes, message send."""

    def __init__(self):
        self.sent: list[dict] = []
        self.media_bytes = b"\xff\xd8fake-jpeg-bytes"
        # Meta answering 500 to every send: what a best-effort reply has to
        # survive. Nothing is recorded in `sent` while it is on.
        self.fail_sends = False

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/messages"):
                import json

                if self.fail_sends:
                    return httpx.Response(500, json={"error": {"message": "meta down"}})
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
        # Every key a sign call was made for, in order - the tenancy tests
        # prove no URL is ever signed for a paper the caller cannot see.
        self.signed: list[str] = []

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            # Sign endpoint: POST /storage/v1/object/sign/{bucket}/{path...}
            # answers with a relative signed path, like the real Supabase API.
            if request.url.path.startswith("/storage/v1/object/sign/"):
                bucket, _, key = request.url.path.removeprefix(
                    "/storage/v1/object/sign/"
                ).partition("/")
                self.signed.append(key)
                if key not in self.objects:
                    return httpx.Response(404, json={"error": "Object not found"})
                return httpx.Response(
                    200, json={"signedURL": f"/object/sign/{bucket}/{key}?token=fake-signed-token"}
                )
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
