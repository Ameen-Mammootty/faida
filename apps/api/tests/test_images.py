"""Vision request-size fitting (extraction/images.py).

Pure functions, no network. The bug these lock in was live on 2026-08-23: a
phone photo over ~7.5 MB was rejected outright by the API, the job retried a
deterministic 400 three times, and the sender got a generic failure message a
minute later with nothing saying the photo was too big.
"""

import io
import random

import pytest
from PIL import Image

from faida_api.extraction.images import (
    BASE64_LIMIT_BYTES,
    base64_length,
    fit_for_vision,
    fits,
)


def _jpeg(width: int, height: int, *, noise: bool = True) -> bytes:
    """A JPEG that resists compression, so size tracks dimensions."""
    picture = Image.new("RGB", (width, height))
    if noise:
        # Flat colour compresses to almost nothing; a per-pixel pattern keeps
        # the encoder honest and the file genuinely large.
        picture.putdata(
            [
                ((x * 7) % 256, (y * 13) % 256, ((x + y) * 3) % 256)
                for y in range(height)
                for x in range(width)
            ]
        )
    buffer = io.BytesIO()
    picture.save(buffer, format="JPEG", quality=98)
    return buffer.getvalue()


def _png_noise(width: int, height: int) -> bytes:
    """PNG of pseudo-random pixels: lossless compression cannot shrink noise,
    so the file really does exceed the limit. A periodic pattern does not -
    it compresses away and the test silently stops testing anything."""
    rng = random.Random(20260823)
    picture = Image.new("RGB", (width, height))
    picture.putdata(
        [
            (rng.randrange(256), rng.randrange(256), rng.randrange(256))
            for _ in range(width * height)
        ]
    )
    buffer = io.BytesIO()
    picture.save(buffer, format="PNG", compress_level=1)
    return buffer.getvalue()


def test_base64_length_matches_real_encoding():
    import base64 as b64

    for size in (0, 1, 2, 3, 4, 100, 3001):
        raw = b"x" * size
        assert base64_length(size) == len(b64.standard_b64encode(raw))


def test_image_within_the_limit_passes_through_untouched():
    small = _jpeg(400, 300)
    out, mime = fit_for_vision(small, "image/jpeg")
    assert out == small  # byte-identical, not merely equivalent
    assert mime == "image/jpeg"


def test_oversized_image_is_resized_until_it_fits():
    big = _jpeg(4200, 4200)
    assert not fits(big), "fixture is not actually over the limit"

    out, mime = fit_for_vision(big, "image/jpeg")

    assert fits(out)
    assert base64_length(len(out)) <= BASE64_LIMIT_BYTES
    assert len(out) < len(big)
    assert mime == "image/jpeg"
    # Still a readable image, not truncated bytes.
    with Image.open(io.BytesIO(out)) as reopened:
        assert reopened.size[0] > 0 and reopened.size[1] > 0


def test_pdf_is_never_rasterized():
    """PDFs travel as a document block under a different limit; rasterizing
    one here would throw away the text layer."""
    payload = b"%PDF-1.7\n" + b"x" * 50
    out, mime = fit_for_vision(payload, "application/pdf")
    assert out == payload
    assert mime == "application/pdf"


def test_undecodable_bytes_are_returned_unchanged_not_raised():
    """This is a safety net around a provider call the caller already handles.
    Raising a new exception from it would turn a handled failure into an
    unhandled one."""
    junk = b"\xff\xd8\xff" + b"not really a jpeg" * 500_000
    assert not fits(junk)
    out, mime = fit_for_vision(junk, "image/jpeg")
    assert out == junk
    assert mime == "image/jpeg"


@pytest.mark.parametrize("mime", ["image/png", "image/webp"])
def test_oversized_non_jpeg_is_converted_to_jpeg(mime):
    """WhatsApp normally sends JPEG, but the upload endpoint accepts PNG. An
    oversized one has to come back as JPEG - PNG cannot shrink far enough on a
    photograph without going lossy anyway."""
    payload = _png_noise(3000, 3000)
    assert not fits(payload), "fixture is not actually over the limit"

    out, out_mime = fit_for_vision(payload, mime)

    assert fits(out)
    assert out_mime == "image/jpeg"
