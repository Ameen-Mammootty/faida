"""Public, write-only waitlist endpoint for the Faida landing page.

The endpoint returns the same result for a new address and an existing one so
callers cannot use it to discover whether somebody has already signed up.
Postgres owns deduplication; the browser never receives database credentials.
"""

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .db import Database

WAITLIST_BODY_MAX_BYTES = 1_024
EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)

router = APIRouter(prefix="/api")


class WaitlistRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: str = Field(min_length=3, max_length=254)
    # A real person never sees or fills this field. Bots often do.
    website: str = Field(default="", max_length=200)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.casefold()
        if not EMAIL_PATTERN.fullmatch(normalized):
            raise ValueError("enter a valid email address")
        return normalized


async def parse_waitlist_request(request: Request) -> WaitlistRequest:
    content_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if content_type != "application/json":
        raise HTTPException(status_code=415, detail="content type must be application/json")

    length = request.headers.get("content-length")
    if length is not None:
        try:
            if int(length) > WAITLIST_BODY_MAX_BYTES:
                raise HTTPException(status_code=413, detail="request body too large")
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid content-length header") from None

    raw = await request.body()
    if len(raw) > WAITLIST_BODY_MAX_BYTES:
        raise HTTPException(status_code=413, detail="request body too large")
    try:
        return WaitlistRequest.model_validate_json(raw)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


@router.post("/waitlist", status_code=status.HTTP_202_ACCEPTED)
async def join_waitlist(
    body: Annotated[WaitlistRequest, Depends(parse_waitlist_request)],
    request: Request,
    response: Response,
) -> dict[str, bool]:
    response.headers["Cache-Control"] = "no-store"

    # Quietly absorb honeypot submissions. Returning the normal response keeps
    # the field useful without teaching bots how to bypass it.
    if body.website:
        return {"ok": True}

    db: Database = request.app.state.db
    await db.insert_waitlist_signup(body.email)
    return {"ok": True}
