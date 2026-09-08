"""M10 WP-103: the morning brief on a terminal, and the rehearsal send
(Docs/M10_DECOMPOSITION.md §3.1 "The dry run", §4 rows 101 and 103, §8).

    python -m faida_api.brief_cli --tenant <id>
    python -m faida_api.brief_cli --tenant <id> --today 2026-09-01
    python -m faida_api.brief_cli --tenant <id> --card out.png
    python -m faida_api.brief_cli --tenant <id> --send --to 9715XXXXXXXX

Three things, all of which the product needs before Meta has approved
anything. The first is the printed brief: exactly what a phone would show for
that tenant on that morning, read from the live database, read-only, so the
founder can look at the words and the figures a milestone before the first
07:00 (the M12 `usage_report` precedent - a printed answer is the first
vertical slice). The second is `--card`, which writes the morning's picture to
a file: the sample image Meta asks for at submission, and the way to look at
the card without sending anything (WP-106, §3.1). The third is the rehearsal:
one real template send to one phone at any hour, which is how the sitting
proves the template against the real number without waiting for a morning
(§8 step 5).

It composes nothing of its own. `worker.read_brief` is the one function that
makes the two dashboard reads and calls the filler, and `worker.send_brief_card`
is the one that stores, uploads and sends - so what is printed here is what the
job sends there, and a rehearsal takes the same three steps in the same order
as a morning, by construction and not by agreement. A rehearsal is recorded
like any other send, with `rehearsal: true` on the row, which keeps it outside
the day's key: a rehearsal at four in the afternoon must not silence the next
morning's brief (`db.outbound_brief_exists`).

Nothing else is written. There is no recipient row to add here and no job to
enqueue: adding a number is a decision with evidence behind it and belongs to
the paste file's insert with its audit row (P14, `db.add_brief_recipient`).
"""

import argparse
import asyncio
import datetime
import json
import sys
from pathlib import Path
from typing import TextIO

from . import brief, brief_card
from .config import get_settings
from .db import Database
from .storage import Storage
from .wa import WhatsAppClient
from .worker import read_brief, send_brief_card

#: What a quiet brief prints instead of a message (C15.7). The sentence says
#: which tenant, because the usual cause is the wrong id on the command line.
NOTHING_TO_SEND = "nothing to send: no sales are loaded for tenant {tenant_id}"


def rehearsal_card_path(tenant_id: str, today: datetime.date, phone: str) -> str:
    """Where a rehearsal's card is stored: beside the mornings, under the day
    it was read for, named as the rehearsal it is.

    Not the morning's own key (`.../{recipient_id}.png`), because a rehearsal
    to the founder's phone at four in the afternoon must not sit where that
    recipient's 07:00 card will go - the objects never overwrite, and the
    morning would then find its own key taken by a different day's figures."""
    return f"{tenant_id}/briefs/{today.isoformat()}/rehearsal-{phone}.png"


async def run(
    db: Database,
    wa: WhatsAppClient | None,
    storage: Storage | None = None,
    *,
    tenant_id: str,
    today: datetime.date,
    send_to: str | None = None,
    card: str | None = None,
    out: TextIO = sys.stdout,
) -> str | None:
    """Print one morning's brief, write its card if asked, and send it if
    asked. Returns the message id of a rehearsal send, or None.

    Takes its database, its Graph client and its storage client rather than
    building them, so the test drives the same function the terminal does
    against the test database and a mocked Meta."""
    morning = await read_brief(db, tenant_id, today=today)
    if morning.quiet:
        print(NOTHING_TO_SEND.format(tenant_id=tenant_id), file=out)
        return None

    print(brief.render(morning), file=out)
    print(file=out)
    print(json.dumps(list(morning.parameters), indent=2, ensure_ascii=False), file=out)

    if card is not None:
        # The picture on its own: Meta's sample at submission, and the way to
        # look at the card before any morning has one (WP-106). The write goes
        # to a thread because everything else on this path is async.
        await asyncio.to_thread(Path(card).write_bytes, brief_card.render_card(morning))
        print(
            f"\ncard written to {card} ({brief_card.CANVAS_W} by {brief_card.CANVAS_H})",
            file=out,
        )

    if send_to is None:
        return None
    if wa is None or storage is None:
        raise ValueError("a rehearsal send needs a WhatsApp client and a storage client")
    # The same three steps in the same order as a morning, through the same
    # function: store the card, upload it, send with it as the header.
    card_path = rehearsal_card_path(tenant_id, today, send_to)
    message_id = await send_brief_card(wa, storage, morning, phone=send_to, card_path=card_path)
    # A phone that is already a recipient keeps its own id on the row, so the
    # rehearsal reads back beside that recipient's mornings; any other phone
    # is named as what it is, a send from this command line.
    recipient = await db.brief_recipient_for_phone(send_to)
    recipient_id = recipient["id"] if recipient is not None else f"cli:{send_to}"
    await db.record_outbound_template(
        message_id,
        send_to,
        template=brief.TEMPLATE_NAME,
        language=brief.TEMPLATE_LANGUAGE,
        parameters=list(morning.parameters),
        tenant_id=tenant_id,
        recipient_id=recipient_id,
        brief_date=today,
        rehearsal=True,
        card_path=card_path,
    )
    print(f"\nsent to {send_to} as {message_id} (rehearsal)", file=out)
    return message_id


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m faida_api.brief_cli",
        description="Print one tenant's morning brief, and optionally send it as a rehearsal.",
    )
    parser.add_argument("--tenant", required=True, help="the tenant id to read")
    parser.add_argument(
        "--today",
        help="the brief's date, YYYY-MM-DD (default: today, UTC). The day the "
        "read is aged against, as a recipient's local date is for the job.",
    )
    parser.add_argument(
        "--card",
        help="write the morning's picture card to this path as a PNG "
        "(the sample image Meta asks for at submission)",
    )
    parser.add_argument(
        "--send", action="store_true", help="really send it, as a rehearsal, to --to"
    )
    parser.add_argument("--to", help="the phone to send the rehearsal to, digits only, no '+'")
    args = parser.parse_args(argv)
    if args.send and not args.to:
        parser.error("--send needs --to <phone>")
    if args.to and not args.send:
        parser.error("--to only means something with --send")
    return args


async def _run_from_settings(args: argparse.Namespace) -> None:
    settings = get_settings()
    today = (
        datetime.date.fromisoformat(args.today)
        if args.today
        else datetime.datetime.now(datetime.UTC).date()
    )
    db = Database(settings.database_url)
    await db.connect()
    # Only a rehearsal talks to Meta or to storage; a printed brief and a card
    # written to a file need neither, so neither is built.
    wa = WhatsAppClient(settings) if args.send else None
    storage = Storage(settings) if args.send else None
    try:
        await run(
            db,
            wa,
            storage,
            tenant_id=args.tenant,
            today=today,
            send_to=args.to if args.send else None,
            card=args.card,
        )
    finally:
        if wa is not None:
            await wa.close()
        if storage is not None:
            await storage.close()
        await db.close()


def main(argv: list[str] | None = None) -> None:
    asyncio.run(_run_from_settings(parse_args(argv)))


if __name__ == "__main__":
    main()
