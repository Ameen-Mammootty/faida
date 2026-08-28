import {
  BASIS_LABEL,
  BLOCKED_LABEL,
  DISPLAY_UNIT_LABEL,
  estimatedReason,
  unitCost,
} from "@/lib/format";
import type { CostBlocked, CostQuality, EstimatedBecause, UnitCost } from "@/lib/types";
import { AlertIcon } from "./icons";

/**
 * A pack's cost per base unit, or the reason it has none. Blocked never
 * relies on colour: it carries an icon and says what to do (plan.md §3).
 */
export default function CostBadge({
  cost,
  blocked,
  quality = null,
  reasons = [],
  showBasis = true,
}: {
  cost: UnitCost | null;
  blocked: CostBlocked | null;
  quality?: CostQuality | null;
  reasons?: EstimatedBecause[];
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
      {/* C9: a cost resting on something a person asserted is honest and not
          checkable against a photo, and must not read like one that is. */}
      {quality === "estimated" ? (
        <span className="mt-1 inline-flex items-center gap-1.5 self-end rounded-sm bg-gold-soft px-2 py-0.5 text-xs font-medium text-caution">
          <AlertIcon />
          Estimated
        </span>
      ) : null}
      {quality === "estimated" && reasons.length > 0 ? (
        <span className="mt-1 max-w-xs text-right text-xs text-stone">
          {reasons.map((reason) => estimatedReason(reason)).join(" ")}
        </span>
      ) : null}
    </span>
  );
}
