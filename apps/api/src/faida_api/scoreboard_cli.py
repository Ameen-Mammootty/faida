"""M13.7: the scoreboard on a terminal, and its picture written to a file
(plan.md §8 M13 D13; issue #13's print command).

    python -m faida_api.scoreboard_cli --tenant <id> --branch <id>
    python -m faida_api.scoreboard_cli --tenant <id> --branch <id> --day 2026-09-16
    python -m faida_api.scoreboard_cli --tenant <id> --branch <id> --card out.png
    python -m faida_api.scoreboard_cli --tenant <id> --branch <id> --final --month 2026-08

Exactly what the branch's phone would show for that day, read from the live
database, read-only, so the founder can look at the words and the picture
before the first 07:00 (the brief's `brief_cli` precedent, and M12's printed
answer as the first vertical slice). It composes nothing of its own:
`worker.read_scoreboard` is the one function that reads the statement and
composes the card, so what is printed here is what the morning's job will
send (issue #14), by construction and not by agreement. Nothing is sent and
nothing is written but the PNG asked for.
"""

import argparse
import asyncio
import datetime
import json
import sys
from pathlib import Path
from typing import TextIO

from . import incentive, scoreboard, scoreboard_card
from .config import get_settings
from .db import Database
from .worker import read_scoreboard

#: What is printed when there is no card to draw. The sentence names the
#: tenant and the branch, because the usual cause is a wrong id or a month
#: with no scheme month.
NOTHING_TO_DRAW = (
    "nothing to draw: branch {branch_id} of tenant {tenant_id} has no statement for {month}"
)


async def run(
    db: Database,
    *,
    tenant_id: str,
    branch_id: str,
    today: datetime.date,
    variant: str = scoreboard.DAILY,
    month: datetime.date | None = None,
    card: str | None = None,
    out: TextIO = sys.stdout,
) -> scoreboard.Scoreboard | None:
    """Print one branch's card for one day, and write its picture if asked.
    Returns the composed card, or None when there is nothing to draw.

    Takes its database rather than building one, so the test drives the
    same function the terminal does against the test database."""
    composed = await read_scoreboard(
        db, tenant_id, branch_id, today=today, variant=variant, month=month
    )
    if composed is None:
        month_words = incentive.month_words(incentive.month_start(month or today))
        print(
            NOTHING_TO_DRAW.format(branch_id=branch_id, tenant_id=tenant_id, month=month_words),
            file=out,
        )
        return None

    print(scoreboard.render(composed), file=out)
    print(file=out)
    print(json.dumps(list(composed.parameters), indent=2, ensure_ascii=False), file=out)

    if card is not None:
        # The picture on its own: the way to look at the card before any
        # morning has one, and Meta's sample at submission (issue #16).
        await asyncio.to_thread(Path(card).write_bytes, scoreboard_card.render_card(composed))
        print(
            f"\ncard written to {card} ({scoreboard_card.CANVAS_W} by {scoreboard_card.CANVAS_H})",
            file=out,
        )
    return composed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m faida_api.scoreboard_cli",
        description="Print one branch's scoreboard for one day, and optionally write its picture.",
    )
    parser.add_argument("--tenant", required=True, help="the tenant id to read")
    parser.add_argument("--branch", required=True, help="the branch id to draw the card for")
    parser.add_argument(
        "--day",
        help="the card's date, YYYY-MM-DD (default: today, UTC). The branch's own local "
        "date for the job: the day the newest loaded day is aged against, and the day "
        "whose push week is in view.",
    )
    parser.add_argument(
        "--month",
        help="the scheme month to read, YYYY-MM (default: the month of --day); "
        "with --final, the month that was approved",
    )
    parser.add_argument(
        "--final",
        action="store_true",
        help="draw the final card of an approved month instead of the morning's",
    )
    parser.add_argument("--card", help="write the card to this path as a PNG")
    args = parser.parse_args(argv)
    if args.month is not None and incentive.parse_month_key(args.month) is None:
        parser.error(f"--month {args.month!r} is not a month: YYYY-MM")
    return args


async def _run_from_settings(args: argparse.Namespace) -> None:
    settings = get_settings()
    today = (
        datetime.date.fromisoformat(args.day)
        if args.day
        else datetime.datetime.now(datetime.UTC).date()
    )
    db = Database(settings.database_url)
    await db.connect()
    try:
        await run(
            db,
            tenant_id=args.tenant,
            branch_id=args.branch,
            today=today,
            variant=scoreboard.FINAL if args.final else scoreboard.DAILY,
            month=incentive.parse_month_key(args.month) if args.month else None,
            card=args.card,
        )
    finally:
        await db.close()


def main(argv: list[str] | None = None) -> None:
    asyncio.run(_run_from_settings(parse_args(argv)))


if __name__ == "__main__":
    main()
