"""Pinned money constants: C4 tolerances and M2 alert thresholds (plan.md §7.2).

Money is Decimal in Python and numeric in Postgres, never float. The eval
harness scores against these same constants.
"""

from decimal import Decimal

# C4 - arithmetic reconciliation tolerances (plan.md §5 layer 2).
# Line: |qty * unit_price - line_total| <= max(LINE_TOLERANCE_ABS,
#                                              LINE_TOLERANCE_PCT * line_total)
LINE_TOLERANCE_ABS = Decimal("0.05")
LINE_TOLERANCE_PCT = Decimal("0.005")
# Document: |subtotal + tax - total| <= DOC_TOLERANCE_ABS
DOC_TOLERANCE_ABS = Decimal("0.10")

# Repair pass (plan.md §5 layer 3): one scoped round, never more.
MAX_REPAIR_ROUNDS = 1

# Price alerts (plan.md §6 M2, WP-23): both thresholds must be met, compared
# against the snapped item's last_price at extraction-reply time.
PRICE_ALERT_MIN_PCT = Decimal("0.05")
PRICE_ALERT_MIN_ABS = Decimal("0.25")  # AED
