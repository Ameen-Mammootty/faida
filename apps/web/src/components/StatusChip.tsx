import { STATUS_LABEL } from "@/lib/format";
import type { InvoiceStatus } from "@/lib/types";
import { AlertIcon, CheckIcon, PendingIcon } from "./icons";

const STYLE: Record<InvoiceStatus, { classes: string; Icon: typeof CheckIcon }> = {
  confirmed: { classes: "bg-mist text-verified", Icon: CheckIcon },
  awaiting_confirm: { classes: "bg-mist text-palm", Icon: PendingIcon },
  needs_review: { classes: "bg-gold-soft text-caution", Icon: AlertIcon },
  draft: { classes: "bg-mist text-stone", Icon: PendingIcon },
};

export default function StatusChip({ status }: { status: InvoiceStatus }) {
  const { classes, Icon } = STYLE[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-sm px-2 py-1 text-xs font-medium ${classes}`}
    >
      <Icon />
      {STATUS_LABEL[status]}
    </span>
  );
}
