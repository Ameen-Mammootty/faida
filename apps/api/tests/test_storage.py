"""Storage's one write door (`put_immutable`), with Supabase mocked at the
transport. The refusal shapes are the two the service answers when a key is
taken: our fake's 409, and Supabase's own 400 with a Duplicate body."""

import httpx
import pytest

from faida_api.storage import Storage


def storage_answering(settings, status: int, body: dict) -> Storage:
    return Storage(
        settings, transport=httpx.MockTransport(lambda _: httpx.Response(status, json=body))
    )


@pytest.mark.parametrize(
    ("status", "body", "outcome"),
    [
        (200, {"Key": "k"}, "stored"),
        (409, {"error": "Duplicate"}, "already_there"),
        (
            400,
            {"statusCode": "409", "error": "Duplicate", "message": "The resource already exists"},
            "already_there",
        ),
    ],
)
async def test_a_taken_key_is_already_there(settings, status, body, outcome):
    storage = storage_answering(settings, status, body)
    assert await storage.put_immutable("t/documents/d/original", b"x", "image/jpeg") == outcome


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (400, {"error": "InvalidKey", "message": "Invalid key"}),
        (500, {"error": "internal"}),
        (403, {"error": "Unauthorized"}),
    ],
)
async def test_any_other_refusal_raises(settings, status, body):
    storage = storage_answering(settings, status, body)
    with pytest.raises(httpx.HTTPStatusError):
        await storage.put_immutable("t/documents/d/original", b"x", "image/jpeg")
