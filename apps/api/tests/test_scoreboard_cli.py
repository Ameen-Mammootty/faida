"""M13.7: the print command and the read the morning will use, against real
Postgres (issue #13's last criterion; issue #14 for the job that reads the
same way).

The chain is staged the way the statement tests stage it - the month
created through its door, the lists on the weeks, the sales through the
branch-day door - and then `scoreboard_cli.run` is driven exactly as the
terminal drives it. What is proven is that the printed lines are the
statement the screen shows, that the PNG is written at the card's size,
that a branch or a month with nothing to draw says so and writes nothing,
and that the read serves the final card once a month is approved.
"""

import datetime
from io import BytesIO, StringIO

import pytest
from PIL import Image

from faida_api import scoreboard, scoreboard_card, scoreboard_cli, worker

from .conftest import requires_db
from .test_incentive_api import (
    BRANCH,
    BRANCH_2,
    BRANCH_3,
    JULY,
    TENANT,
    _approve,
    _july,
    _july_with_sales,
    _rest_of_july,
    _statement,
)
from .test_incentive_api import api as _incentive_api

pytestmark = requires_db

#: The incentive tests' own client, with the menu and sales doors wired for
#: staging, under this file's name.
api = _incentive_api

#: The eighth of July 2026, a Wednesday: Al Quoz's newest loaded day is the
#: 7th, so the first line says yesterday, and the second push week (6-12
#: Jul, mandi on its list) is in view.
DAY = datetime.date(2026, 7, 8)


async def _run(db, tmp_path, *, branch=BRANCH, today=DAY, **kw):
    out = StringIO()
    target = tmp_path / "scoreboard.png"
    card = await scoreboard_cli.run(
        db, tenant_id=TENANT, branch_id=branch, today=today, card=str(target), out=out, **kw
    )
    return card, out.getvalue(), target


async def test_the_print_command_writes_the_png_and_prints_the_statements_own_lines(
    api, db, tmp_path
):
    async with api as client:
        await _july_with_sales(client, db)
        read = await _july(client)
        card, printed, target = await _run(db, tmp_path)

    quoz = _statement(read, BRANCH)
    week = quoz["figures"]["weeks"][1]
    assert card is not None
    assert printed.splitlines()[0] == "Al Barsha scoreboard, Wed 8 Jul"
    assert printed.splitlines()[1] == "Sales loaded to Tue 7 Jul, yesterday."
    assert f"July 2026, {quoz['status_words']}" in printed
    assert "This week's push list, 6-12 Jul" in printed
    assert f"  {week['items'][0]['name']}: {week['items'][0]['words']}" in printed
    assert week["items"][0]["words"] == "14 of 10 portions"
    assert "150 of 100 portions" not in printed  # last week's karak is not this week's list
    assert f"Net sales, July so far: {quoz['figures']['net_words']}" in printed
    assert f"Bonus pool so far: {quoz['figures']['pool_words']}" in printed
    assert str(target) in printed

    image = Image.open(BytesIO(target.read_bytes()))
    assert image.size == (scoreboard_card.CANVAS_W, scoreboard_card.CANVAS_H)
    assert target.read_bytes() == scoreboard_card.render_card(card)


async def test_a_branch_loaded_days_ago_is_aged_on_the_first_line(api, db, tmp_path):
    """Karama loaded the 1st and nothing since: on the 7th the line says six
    days and never yesterday (D16)."""
    async with api as client:
        await _july_with_sales(client, db)
        card, printed, _ = await _run(db, tmp_path, branch=BRANCH_2, today=DAY.replace(day=7))
    assert card is not None
    assert printed.splitlines()[1] == "Sales loaded to Wed 1 Jul, 6 days ago."
    assert "yesterday" not in printed


async def test_a_branch_with_nothing_loaded_says_so_and_still_draws(api, db, tmp_path):
    async with api as client:
        await _july_with_sales(client, db)
        card, printed, target = await _run(db, tmp_path, branch=BRANCH_3)
    assert card is not None
    assert printed.splitlines()[1] == "No sales loaded yet for July 2026."
    assert "Bonus pool so far: nothing loaded yet" in printed
    assert target.exists()


async def test_a_month_with_no_scheme_month_has_nothing_to_draw_and_writes_nothing(
    api, db, tmp_path
):
    async with api as client:
        await _july_with_sales(client, db)
        card, printed, target = await _run(db, tmp_path, today=datetime.date(2026, 6, 2))
    assert card is None
    assert printed.strip() == scoreboard_cli.NOTHING_TO_DRAW.format(
        branch_id=BRANCH, tenant_id=TENANT, month="June 2026"
    )
    assert not target.exists()


async def test_a_branch_that_is_not_this_tenants_has_nothing_to_draw(api, db, tmp_path):
    async with api as client:
        await _july_with_sales(client, db)
        card, printed, target = await _run(
            db, tmp_path, branch="00000000-0000-4000-8000-00000000beef"
        )
    assert card is None
    assert "nothing to draw" in printed
    assert not target.exists()


async def test_the_read_serves_the_final_card_once_the_month_is_approved(api, db, tmp_path):
    """The job the approval enqueues reads the same way (issue #15): the
    approved month named, the split by role, and the morning's own variant
    refused on it because the month is closed."""
    async with api as client:
        await _july_with_sales(client, db)
        await _rest_of_july(client)
        before = await _july(client)
        approved = await _approve(client, before)
        assert approved.status_code == 200, approved.text
        quoz = _statement(approved.json(), BRANCH)

        card, printed, _ = await _run(
            db,
            tmp_path,
            today=datetime.date(2026, 8, 3),
            variant=scoreboard.FINAL,
            month=datetime.date(2026, 7, 1),
        )
        with pytest.raises(ValueError, match="closed"):
            await worker.read_scoreboard(db, TENANT, BRANCH, today=datetime.date(2026, 7, 20))

    assert card is not None and card.variant == scoreboard.FINAL
    assert printed.splitlines()[0] == "Al Barsha: July 2026 bonus, final"
    assert f"Bonus pool: {quoz['figures']['pool_words']}" in printed
    split = quoz["figures"]["split"]
    assert f"Manager share, 40%: AED {split['manager']}" in printed
    assert f"Sales team share, 35%: AED {split['sales']}" in printed
    assert JULY == "2026-07"
