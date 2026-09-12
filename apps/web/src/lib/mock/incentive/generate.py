"""Regenerate the incentive mock's fixtures (M13, the /incentive screen): the
JSON files beside this script, one per scenario, each the exact payload of
`GET /api/incentive?month=` for the three sample branches and the sample
menu.

Every figure the mock serves is produced here by the *shipped* pure module
(`faida_api.incentive`): the push weeks, the portions net of refunds, the
pool, the cap, the split, the provisional and final words, the recomputed
figures beside an approved statement, and the screen's blocks through the
module's own serialisers. The TypeScript mock computes nothing: it picks a
scenario and returns the literal, and its own doors (create a month, set a
list, approve, pause) only move rows the way the API's would. That is the
dashboard mock's rule in its strongest form, and it is why these files must
be regenerated whenever the wording or the arithmetic in the module moves.

Run from apps/api with its venv (the module is imported from src):

    .venv/bin/python ../web/src/lib/mock/incentive/generate.py \
        ../web/src/lib/mock/incentive src

Scenarios (reachable on the screen by `?scenario=`):

    full       September 2026 under way on 16 Sep: the week of 14-20 Sep in
               view with its list, two branches loaded to the 15th, Deira
               loaded to the 10th and paused, a hole (Honey Cake lost its
               till name), a cap binding at Karama
    final      August 2026 approved for every branch, one branch (Karama)
               with a day replaced after approval, so the till now says
               otherwise
    complete   August 2026 with every day loaded and nothing approved yet:
               the approval control shows on every branch
    empty      the shares are set and no scheme month exists yet
    noshares   nothing is set at all
"""

import datetime
import json
import sys
from decimal import Decimal as D

sys.path.insert(0, sys.argv[2] if len(sys.argv) > 2 else "src")
from faida_api import incentive as I  # noqa: E402

OUT = sys.argv[1]
CURRENCY = "AED"
TODAY = datetime.date(2026, 9, 16)
NOW = datetime.datetime(2026, 9, 16, 5, 30, tzinfo=datetime.UTC)
BRANCHES = [("br-01", "Al Quoz"), ("br-02", "Karama"), ("br-03", "Deira")]
NAMES = dict(BRANCHES)

# --- the menu: the dashboard mock's fourteen items, what each plate keeps ---------
# (id, name, category, kept per plate or None when not costed, mapped)
MENU = [
    ("menu-1", "Karak Tea (Cup)", "Tea Corner", "3.950", True),
    ("menu-2", "Karak Tea (Flask 1 L)", "Tea Corner", "27.129", True),
    ("menu-3", "Nido Shake", "Shakes", "7.329", True),
    ("menu-4", "Chicken Mandi", "Rice", None, True),
    ("menu-5", "Honey Cake", None, None, False),
    ("menu-6", "Sulaimani", "Tea Corner", "2.637", True),
    ("menu-7", "Butter Chicken", "Special Gravy", "15.290", True),
    ("menu-8", "Paneer Butter Masala", "Special Gravy", "14.139", True),
    ("menu-9", "Chicken 65 Dry", "Starters", "18.024", True),
    ("menu-10", "Mutter Mushroom", "Special Gravy", "13.141", True),
    ("menu-11", "Egg Paratha", "Breads", "2.429", True),
    ("menu-12", "Veg Biryani", "Rice", "10.098", True),
    ("menu-13", "Mint Lemonade", "Drinks", "-0.401", True),
    ("menu-14", "Masala Chai", "Tea Corner", "3.170", True),
]
KEPT = {mid: (None if kept is None else D(kept)) for mid, _, _, kept, _ in MENU}
MAPPED = {mid: mapped for mid, _, _, _, mapped in MENU}
MENU_NAME = {mid: name for mid, name, _, _, _ in MENU}
MENU_CATEGORY = {mid: cat for mid, _, cat, _, _ in MENU}

SHARES = I.Shares(D("50"), D("20"), D("30"))
SHARES_JSON = {**I.shares_json(SHARES), "updated_at": "2026-08-28T09:12:00+00:00"}


def menu_block():
    return I.group_by_category(
        [
            I.menu_item_json(
                menu_item_id=mid, name=name, category=cat, kept_per_plate=KEPT[mid],
                mapped=MAPPED[mid], currency=CURRENCY,
            )
            for mid, name, cat, _, _ in MENU
        ]
    )


def push_item(pid, mid, rate, targets, *, mapped=None, archived=False):
    return I.PushItem(
        push_item_id=pid,
        menu_item_id=mid,
        name=MENU_NAME[mid],
        category=MENU_CATEGORY[mid],
        rate_per_portion=D(rate),
        archived=archived,
        mapped=MAPPED[mid] if mapped is None else mapped,
        targets={bid: D(t) for bid, t in targets.items()},
    )


def scheme(month, targets, lists, *, scheme_id):
    windows = I.push_weeks(month)
    weeks = tuple(
        I.PushWeek(f"pw-{scheme_id}-{i + 1}", window, tuple(lists.get(i, ())))
        for i, window in enumerate(windows)
    )
    return I.SchemeMonth(
        scheme_month_id=scheme_id,
        month=month,
        shares=SHARES,
        targets={
            bid: I.BranchTargets(bid, D(net), D(pct), None if cap is None else D(cap))
            for bid, (net, pct, cap) in targets.items()
        },
        weeks=weeks,
    )


def loaded(bid, month, days, net_per_day):
    return [I.LoadedDay(bid, month.replace(day=d), D(net_per_day)) for d in days]


def sold(bid, month, mid, per_day, days, *, refund_on=None, refund_qty="0"):
    rows = []
    for d in days:
        qty = D(per_day)
        if refund_on == d:
            qty -= D(refund_qty)
        rows.append(I.ItemDay(bid, month.replace(day=d), mid, qty, 0))
    return rows


def branch_block(bid, paused_at, previous):
    return I.branch_json(
        branch_id=bid, name=NAMES[bid], timezone="Asia/Dubai", paused_at=paused_at,
        previous_month_net_sales=previous, currency=CURRENCY,
    )


def statement(sch, bid, days, items, *, approval=None):
    mine = [d for d in days if d.branch_id == bid]
    newest = max((d.business_date for d in mine), default=None)
    st = I.compose_statement(
        sch, bid, days=days, items=items, newest_loaded=newest, approval=approval, currency=CURRENCY
    )
    return I.statement_json(st, branch_name=NAMES[bid])


def payload(*, month, months, shares, branches, sch=None, created_at=None, statements=()):
    return {
        "month": I.month_key(month),
        "month_words": I.month_words(month),
        "today": TODAY.isoformat(),
        "months": months,
        "shares": shares,
        "branches": branches,
        "menu": menu_block(),
        "scheme_month": None
        if sch is None
        else I.scheme_month_json(
            sch, created_at=created_at, today=TODAY, kept=KEPT, statements=list(statements),
            currency=CURRENCY,
        ),
    }


def write(name, out):
    with open(f"{OUT}/{name}.json", "w") as f:
        json.dump(out, f, separators=(",", ":"), ensure_ascii=False)


# --- full: September under way -----------------------------------------------------

SEPT = datetime.date(2026, 9, 1)
AUG = datetime.date(2026, 8, 1)

FULL = scheme(
    SEPT,
    {"br-01": ("60000", "10", None), "br-02": ("40000", "10", "1500"), "br-03": ("30000", "8", None)},
    {
        0: (
            push_item("pi-1", "menu-1", "0.25", {"br-01": "900", "br-02": "700", "br-03": "300"}),
            push_item("pi-2", "menu-7", "2.00", {"br-01": "120", "br-02": "100", "br-03": "70"}),
        ),
        1: (
            push_item("pi-3", "menu-1", "0.25", {"br-01": "900", "br-02": "700", "br-03": "300"}),
            push_item("pi-4", "menu-13", "0.50", {"br-01": "90", "br-02": "70", "br-03": "90"}),
            push_item("pi-5", "menu-5", "1.00", {"br-01": "30", "br-02": "15", "br-03": "10"}),
        ),
        2: (
            push_item("pi-6", "menu-1", "0.25", {"br-01": "1000", "br-02": "750", "br-03": "300"}),
            push_item("pi-7", "menu-6", "0.20", {"br-01": "400", "br-02": "350", "br-03": "250"}),
            push_item("pi-8", "menu-7", "2.00", {"br-01": "140", "br-02": "105", "br-03": "70"}),
            push_item("pi-9", "menu-9", "3.00", {"br-01": "35", "br-02": "21", "br-03": "40"}),
            push_item("pi-10", "menu-13", "0.50", {"br-01": "100", "br-02": "70", "br-03": "100"}),
        ),
        3: (
            push_item("pi-11", "menu-2", "1.50", {"br-01": "240", "br-02": "110", "br-03": "60"}),
            push_item("pi-12", "menu-12", "2.00", {"br-01": "60", "br-02": "45", "br-03": "60"}),
        ),
    },
    scheme_id="sm-2026-09",
)

FULL_DAYS = (
    loaded("br-01", SEPT, range(1, 16), "2450.00")
    + loaded("br-02", SEPT, range(1, 16), "4000.00")
    + loaded("br-03", SEPT, range(1, 11), "1050.00")
)
FULL_ITEMS = (
    # Week 0 (1-6 Sep) and week 1 (7-13 Sep): karak above target everywhere.
    sold("br-01", SEPT, "menu-1", "170", range(1, 16), refund_on=9, refund_qty="4")
    + sold("br-02", SEPT, "menu-1", "110", range(1, 16))
    + sold("br-03", SEPT, "menu-1", "48", range(1, 11))
    + sold("br-01", SEPT, "menu-7", "22", range(1, 16))
    + sold("br-02", SEPT, "menu-7", "13", range(1, 16))
    + sold("br-03", SEPT, "menu-7", "9", range(1, 11))
    + sold("br-01", SEPT, "menu-13", "16", range(1, 16))
    + sold("br-02", SEPT, "menu-13", "9", range(1, 16))
    + sold("br-03", SEPT, "menu-13", "12", range(1, 11))
    + sold("br-01", SEPT, "menu-6", "70", range(1, 16))
    + sold("br-02", SEPT, "menu-6", "44", range(1, 16))
    + sold("br-01", SEPT, "menu-9", "6", range(1, 16))
    + sold("br-02", SEPT, "menu-9", "2", range(1, 16))
    # Honey cake sold, but its till name is unmapped: a hole, never a nought.
    + sold("br-01", SEPT, None, "5", range(1, 16))
)
FULL_BRANCHES = [
    branch_block("br-01", None, D("58210.40")),
    branch_block("br-02", None, D("38975.10")),
    branch_block("br-03", datetime.datetime(2026, 9, 11, 6, 2, tzinfo=datetime.UTC), None),
]
FULL_MONTHS = [{"id": "sm-2026-09", "month": "2026-09", "words": "September 2026"}]

write(
    "full",
    payload(
        month=SEPT,
        months=FULL_MONTHS,
        shares=SHARES_JSON,
        branches=FULL_BRANCHES,
        sch=FULL,
        created_at=datetime.datetime(2026, 8, 30, 8, 15, tzinfo=datetime.UTC),
        statements=[statement(FULL, bid, FULL_DAYS, FULL_ITEMS) for bid, _ in BRANCHES],
    ),
)

# --- final: August approved -----------------------------------------------------------

FINAL = scheme(
    AUG,
    {"br-01": ("55000", "10", None), "br-02": ("38000", "10", "1500"), "br-03": ("28000", "8", None)},
    {
        i: (
            push_item(f"pa-{i}-1", "menu-1", "0.25", {"br-01": "900", "br-02": "700", "br-03": "300"}),
            push_item(f"pa-{i}-2", "menu-7", "2.00", {"br-01": "120", "br-02": "100", "br-03": "70"}),
        )
        for i in range(6)
    },
    scheme_id="sm-2026-08",
)
FINAL_DAYS = (
    loaded("br-01", AUG, range(1, 32), "1950.00")
    + loaded("br-02", AUG, range(1, 32), "1380.00")
    + loaded("br-03", AUG, range(1, 32), "880.00")
)
FINAL_ITEMS = (
    sold("br-01", AUG, "menu-1", "150", range(1, 32))
    + sold("br-02", AUG, "menu-1", "108", range(1, 32))
    + sold("br-03", AUG, "menu-1", "45", range(1, 32))
    + sold("br-01", AUG, "menu-7", "21", range(1, 32))
    + sold("br-02", AUG, "menu-7", "16", range(1, 32))
    + sold("br-03", AUG, "menu-7", "11", range(1, 32))
)
# Karama's 20 Aug was re-uploaded on 3 Sep: 90 karak that day, not 108.
FINAL_ITEMS_LATER = [
    I.ItemDay(r.branch_id, r.business_date, r.menu_item_id, D("90"), 0)
    if r.branch_id == "br-02" and r.menu_item_id == "menu-1" and r.business_date.day == 20
    else r
    for r in FINAL_ITEMS
]


def approval_for(bid):
    figures = I.compute_figures(FINAL, bid, days=FINAL_DAYS, items=FINAL_ITEMS, currency=CURRENCY)
    return I.Approval(
        approved_at=datetime.datetime(2026, 9, 2, 10, 40, tzinfo=datetime.UTC),
        actor="user:00000000-0000-4000-8000-0000000000aa",
        reason="August paid with the 5 September salaries",
        figures=I.figures_json(figures),
    )


FINAL_BRANCHES = [
    branch_block("br-01", None, D("54120.00")),
    branch_block("br-02", None, D("36240.55")),
    branch_block("br-03", None, D("27110.00")),
]
FINAL_MONTHS = [
    {"id": "sm-2026-09", "month": "2026-09", "words": "September 2026"},
    {"id": "sm-2026-08", "month": "2026-08", "words": "August 2026"},
]

write(
    "final",
    payload(
        month=AUG,
        months=FINAL_MONTHS,
        shares=SHARES_JSON,
        branches=FINAL_BRANCHES,
        sch=FINAL,
        created_at=datetime.datetime(2026, 7, 29, 8, 0, tzinfo=datetime.UTC),
        statements=[
            statement(FINAL, bid, FINAL_DAYS, FINAL_ITEMS_LATER, approval=approval_for(bid))
            for bid, _ in BRANCHES
        ],
    ),
)

write(
    "complete",
    payload(
        month=AUG,
        months=FINAL_MONTHS,
        shares=SHARES_JSON,
        branches=FINAL_BRANCHES,
        sch=FINAL,
        created_at=datetime.datetime(2026, 7, 29, 8, 0, tzinfo=datetime.UTC),
        statements=[statement(FINAL, bid, FINAL_DAYS, FINAL_ITEMS) for bid, _ in BRANCHES],
    ),
)

# --- empty and noshares -------------------------------------------------------------------

EMPTY_BRANCHES = [
    branch_block("br-01", None, D("58210.40")),
    branch_block("br-02", None, D("38975.10")),
    branch_block("br-03", None, None),
]

write("empty", payload(month=SEPT, months=[], shares=SHARES_JSON, branches=EMPTY_BRANCHES))
write("noshares", payload(month=SEPT, months=[], shares=None, branches=EMPTY_BRANCHES))
