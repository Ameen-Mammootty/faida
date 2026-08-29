"""Does the C3 wire schema still compile inside the API's grammar budget?

    export ANTHROPIC_API_KEY=...
    apps/api/.venv/bin/python -m eval.schema_probe

C3 sits AT the structured-outputs complexity ceiling, and the failure mode is
total: a schema one field over does not read worse, it 400s on every invoice
("Schema is too complex" / "Grammar compilation timed out") while the sender
gets the generic failure reply. It has happened twice - the optional field
that forced money-as-strings (2026-08-25), and `invoice_date_text`, which
forced the calendar date off the wire entirely (2026-08-28, see the Decision
Log). Run this after ANY change to the extraction schema, before merging.

The probe sends one tiny non-invoice image, so a compiling schema costs a
classification-only call (a fraction of a cent). A grammar failure surfaces
as the 400 this exists to catch; the model's answer is irrelevant.
"""

import base64
import io
import sys

import anthropic
from faida_api.extraction.anthropic_provider import MODEL_ID
from faida_api.extraction.schema import ExtractionResult


def main() -> int:
    try:
        from PIL import Image
    except ImportError:  # Pillow is an apps/api dependency; be explicit anyway
        print("Pillow is required (it ships with apps/api)", file=sys.stderr)
        return 1

    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(buffer, format="PNG")
    client = anthropic.Anthropic()
    try:
        response = client.messages.parse(
            model=MODEL_ID,
            max_tokens=2000,
            output_format=ExtractionResult,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": base64.standard_b64encode(buffer.getvalue()).decode(),
                            },
                        },
                        {"type": "text", "text": "Classify this image."},
                    ],
                }
            ],
        )
    except anthropic.BadRequestError as exc:
        message = exc.body.get("error", {}).get("message", str(exc))
        # Not every 400 is the grammar ceiling: a drained credit balance
        # arrives as a BadRequestError too (found in rehearsal 2026-08-29),
        # and telling someone to slim the schema over a billing problem
        # would send them at entirely the wrong fix.
        if "credit balance" in message.casefold() or "billing" in message.casefold():
            print(f"FAIL: billing, not the schema - {message}")
            print("Top up at console.anthropic.com Plans & Billing, on the org that")
            print("owns this API key, then re-run.")
            return 1
        print(f"FAIL: the wire schema no longer compiles - {message}")
        print("Every extraction would 400. Slim the schema before merging (see the")
        print("2026-08-25 and 2026-08-28 Decision Log entries for what worked).")
        return 1
    print(
        f"OK: the wire schema compiles against {MODEL_ID} "
        f"({response.usage.output_tokens} output tokens spent)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
