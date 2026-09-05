import { AlertIcon } from "./icons";

/**
 * A figure that is below zero - a plate, an item, a whole window's costed
 * sales - in Critical Plum with its icon and its words on the same line,
 * never colour alone (the display rules).
 *
 * One component since M9 WP-98. `/menu` and `/dashboard` each carried their
 * own copy with its own noun ("this plate", "this item"), the tiles needed a
 * third ("the costed sales"), and three copies of a rule about honesty is
 * two copies too many. The noun is the caller's, so is the figure: the menu
 * prints per-plate money to the fil and the dashboard rounds a headline to
 * the dirham, and neither should be decided here.
 */
export default function LossFigure({
  figure,
  noun,
  plural = false,
  align = "start",
  figureClass = "tabular-nums",
}: {
  /** The figure exactly as the screen prints it: "-AED 0.40", "-AED 412". */
  figure: string;
  /** What loses the money: "this plate", "this item", "the costed sales". */
  noun: string;
  /** True when the noun takes "lose" rather than "loses". */
  plural?: boolean;
  align?: "start" | "end";
  /** The figure's own type, so a headline reads as a headline. */
  figureClass?: string;
}) {
  return (
    // The figure and its icon never split: in a fixed-width column the label
    // is what wraps to the next line, not "-AED 0.40" away from the symbol
    // that says it is bad news.
    <span
      className={`inline-flex flex-wrap items-center gap-x-1.5 font-medium text-plum ${
        align === "end" ? "justify-end" : ""
      }`}
    >
      <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
        <AlertIcon className="h-3.5 w-3.5" />
        <span className={figureClass}>{figure}</span>
      </span>
      <span className="text-xs font-normal">
        {noun} {plural ? "lose" : "loses"} money
      </span>
    </span>
  );
}
