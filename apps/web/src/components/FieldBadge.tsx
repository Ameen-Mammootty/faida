import type { FieldStatus } from "@/lib/types";
import { AlertIcon, CheckIcon } from "./icons";

/**
 * Per-field status: colour plus icon plus label, always together
 * (plan.md section 3: colour never carries meaning alone).
 */
export default function FieldBadge({
  status,
  label,
}: {
  status: FieldStatus;
  label?: string;
}) {
  if (status === "green") {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium whitespace-nowrap text-verified">
        <CheckIcon />
        {label ?? "Checked"}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs font-medium whitespace-nowrap text-caution">
      <AlertIcon />
      {label ?? "Needs review"}
    </span>
  );
}
