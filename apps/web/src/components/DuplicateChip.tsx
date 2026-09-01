import { AlertIcon } from "./icons";

/**
 * WP-44: this paper is already recorded.
 *
 * Not a StatusChip variant, because "Duplicate" is not a status - the row is
 * `needs_review` like a cash hold, and the two mean entirely different things
 * to a reviewer. It stands in for the status chip wherever a held duplicate is
 * shown, so the list and the detail page say the same word about the same row.
 * Icon plus the word, so it reads with colour removed.
 */
export default function DuplicateChip() {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-sm bg-gold-soft px-2 py-1 text-xs font-medium text-caution">
      <AlertIcon />
      Duplicate
    </span>
  );
}
