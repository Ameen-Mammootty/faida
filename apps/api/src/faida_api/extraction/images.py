"""Fit an invoice photo inside the vision API's request limit.

A phone at full resolution routinely produces a 5-12 MB JPEG, and the Messages
API rejects any base64 image over 10 MB outright:

    400 invalid_request_error - image exceeds 10 MB maximum:
    13588412 bytes > 10485760 bytes

Measured 2026-08-23 against `claude-opus-5` with `PH-01.jpg` (9.7 MB), which
lives in our own fixture set. Nothing in the pipeline resized, so that photo -
and every real invoice shot at full resolution - failed extraction outright:
the document stored fine, the job threw a deterministic 400, retried three
times to no purpose, and the sender got the generic failure reply a minute
later. Nothing told them the photo was simply too big.

The policy here is deliberately conservative: **resize only when the image
would otherwise be rejected.** Anything already inside the limit passes through
byte-identical. Whether a lower ceiling would also help latency and cost is a
real question, but it trades against reading the small print on a faded thermal
receipt - so it belongs to the accuracy loop (WP-16) with the eval to measure
it, not to a bug fix.
"""

import io
import logging
import math

logger = logging.getLogger(__name__)

# The API's hard ceiling on the base64 payload, from the error above.
BASE64_LIMIT_BYTES = 10_485_760
# Base64 inflates by 4/3. Leave headroom so a re-encode that lands slightly
# over its estimate still clears the limit.
RAW_LIMIT_BYTES = int(BASE64_LIMIT_BYTES * 3 / 4 * 0.92)  # ~7.2 MB

# Re-encode quality when a resize is forced. High enough that printed digits
# survive; the alternative for these images is not a cleaner read, it is no
# read at all.
JPEG_QUALITY = 88
MIN_SCALE = 0.15  # never shrink past this; give up and let the caller proceed


def base64_length(raw_len: int) -> int:
    """Exact encoded length for a payload of `raw_len` bytes."""
    return math.ceil(raw_len / 3) * 4


def fits(image: bytes) -> bool:
    return base64_length(len(image)) <= BASE64_LIMIT_BYTES


def fit_for_vision(image: bytes, mime: str) -> tuple[bytes, str]:
    """Return (image, mime) small enough to send, resizing only if needed.

    PDFs are passed through: they travel as a `document` block under a
    different limit, and rasterizing one here would lose the text layer.

    If the image cannot be decoded or shrunk, the original is returned rather
    than raising. A provider error the caller already handles beats a new
    exception thrown from what is meant to be a safety net.
    """
    if mime == "application/pdf" or fits(image):
        return image, mime

    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow is a hard dependency
        logger.warning("Pillow unavailable; sending oversized image unchanged")
        return image, mime

    original_len = len(image)
    try:
        with Image.open(io.BytesIO(image)) as opened:
            # JPEG cannot carry alpha, and these are photographs regardless.
            picture = opened.convert("RGB")
            width, height = picture.size

            scale = 1.0
            while scale >= MIN_SCALE:
                candidate = picture
                if scale < 1.0:
                    candidate = picture.resize(
                        (max(1, int(width * scale)), max(1, int(height * scale))),
                        Image.LANCZOS,
                    )
                buffer = io.BytesIO()
                candidate.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
                encoded = buffer.getvalue()
                if fits(encoded):
                    logger.info(
                        "resized image for vision: %d -> %d bytes (%dx%d -> %dx%d)",
                        original_len,
                        len(encoded),
                        width,
                        height,
                        *candidate.size,
                    )
                    return encoded, "image/jpeg"
                # Area scales with the square of the linear factor, so step
                # down on the square root of how far over we still are.
                overshoot = len(encoded) / RAW_LIMIT_BYTES
                scale *= min(0.9, 1 / math.sqrt(overshoot))
    except Exception:
        logger.exception("could not resize image; sending unchanged")
        return image, mime

    logger.warning("image still oversized at minimum scale; sending unchanged")
    return image, mime
