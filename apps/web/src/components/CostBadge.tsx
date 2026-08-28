import { BASIS_LABEL, BLOCKED_LABEL, DISPLAY_UNIT_LABEL, unitCost } from "@/lib/format";
import type { CostBlocked, UnitCost } from "@/lib/types";
import { AlertIcon } from "./icons";

/**
 * A pack's cost per base unit, or the reason it has none. Blocked never
 * relies on colour: it carries an icon and says what to do (plan.md §3).
 */
export default function CostBadge({
  cost,
  blocked,
  showBasis = true,
}: {
  cost: UnitCost | null;
  blocked: CostBlocked | null;
  showBasis?: boolean;
}) {
  if (cost === null) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-sm bg-gold-soft px-2 py-1 text-xs font-medium text-caution">
        <AlertIcon />
        {BLOCKED_LABEL[blocked ?? "unknown_pack"]}
      </span>
    );
  }
  return (
    <span className="inline-flex flex-col">
      <span className="font-display text-lg font-semibold text-ink tabular-nums">
        AED {unitCost(cost.per_display)}{" "}
        <span className="text-sm font-medium text-stone">
          {DISPLAY_UNIT_LABEL[cost.display_unit]}
        </span>
      </span>
      {showBasis ? (
        <span className="text-xs text-stone">
          {cost.pack_display} &middot; {BASIS_LABEL[cost.basis]}
        </span>
      ) : null}
    </span>
  );
}
