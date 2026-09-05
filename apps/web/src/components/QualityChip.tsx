import { QUALITY_WORD } from "@/lib/salesScreen";
import type { PeriodQuality } from "@/lib/types";
import { AlertIcon, CheckIcon, PendingIcon } from "./icons";

/**
 * The period-quality word with its icon, one lookup for both screens that
 * show it (`/sales` and `/dashboard`; M9 WP-93, the design review's fourth
 * tone). Four words, four tones: mist and palm for reliable with limitations,
 * gold-soft and caution for estimated, mist and plum for incomplete, and
 * mist and stone for unavailable - the quietest pair in the palette, because
 * unavailable is the absence of a figure and not a warning about one. PRD
 * §24's words; never a colour alone.
 */
const STYLE: Record<PeriodQuality, { classes: string; Icon: typeof CheckIcon }> = {
  reliable_with_limitations: { classes: "bg-mist text-palm", Icon: CheckIcon },
  estimated: { classes: "bg-gold-soft text-caution", Icon: AlertIcon },
  incomplete: { classes: "bg-mist text-plum", Icon: PendingIcon },
  unavailable: { classes: "bg-mist text-stone", Icon: PendingIcon },
};

export default function QualityChip({ quality }: { quality: PeriodQuality }) {
  const { classes, Icon } = STYLE[quality];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-[11px] font-medium whitespace-nowrap ${classes}`}
    >
      <Icon className="h-3 w-3" />
      {QUALITY_WORD[quality]}
    </span>
  );
}
