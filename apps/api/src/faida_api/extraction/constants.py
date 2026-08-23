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
# Document: two identities, because GCC invoices come both ways (C4, amended
# 2026-08-23). With L = sum(line_totals), T = tax, G = total:
#   exclusive (lines net)   |L + T - G| <= DOC_TOLERANCE_ABS
#   inclusive (lines gross) |L - G|     <= DOC_TOLERANCE_ABS  and T > 0
# They cannot both hold while T is material, so there is no ambiguity to break.
DOC_TOLERANCE_ABS = Decimal("0.10")

# GCC VAT rates, used to name the rate on an invoice whose arithmetic already
# reconciled - confirmation, never a gate. An inclusive invoice at an unlisted
# rate still reconciles; we derive the effective rate from the totals instead.
GCC_VAT_RATES = (
    Decimal("0.05"),  # UAE, Oman
    Decimal("0.10"),  # Bahrain
    Decimal("0.15"),  # Saudi Arabia
)

# Repair pass (plan.md §5 layer 3): one scoped round, never more.
MAX_REPAIR_ROUNDS = 1

# Price alerts (plan.md §6 M2, WP-23): both thresholds must be met, compared
# against the snapped item's last_price at extraction-reply time.
PRICE_ALERT_MIN_PCT = Decimal("0.05")
PRICE_ALERT_MIN_ABS = Decimal("0.25")  # AED
