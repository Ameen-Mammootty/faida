import { formatDate, money } from "@/lib/format";
import type { PricePoint } from "@/lib/types";

/**
 * The WP-33 price-trend sparkline: one supplier item's confirmed prices as a
 * small inline SVG - no chart library.
 *
 * Dataviz spec: a 2px round-joined line in the quiet slate hue (the trend is
 * context), with the last point emphasized as an 8px Karak Gold marker
 * carrying a 2px surface ring so it stays legible on the line. No gridlines
 * or axes at this size - the exact decimal price strings ride beside the
 * chart as direct labels (money stays a string end to end; floats appear
 * only here, for y-scaling geometry). Each point carries an invisible
 * full-height hit column with a native tooltip, and the caller renders a
 * visually-hidden table so every value is reachable without hovering.
 */

const WIDTH = 120;
const HEIGHT = 36;
const PAD_X = 6; // room for the end marker (r4 + 2px ring)
const PAD_Y = 7;

export default function Sparkline({
  label,
  prices,
}: {
  /** Accessible name: the item and its range, e.g. "Milk powder, 48.00 to 50.50 AED". */
  label: string;
  prices: PricePoint[];
}) {
  if (prices.length === 0) return null;
  // Defensive: the API serves the series ascending by observed_at already.
  const series = [...prices].sort((a, b) => (a.observed_at < b.observed_at ? -1 : 1));

  // Geometry only - never for display: x from the observation time, y from
  // the price parsed as a float.
  const times = series.map((point) => Date.parse(point.observed_at));
  const values = series.map((point) => Number.parseFloat(point.price));
  const tMin = Math.min(...times);
  const tMax = Math.max(...times);
  const vMin = Math.min(...values);
  const vMax = Math.max(...values);
  const tSpan = tMax - tMin || 1;
  const vSpan = vMax - vMin || 1;

  const x = (t: number) =>
    series.length === 1 ? WIDTH / 2 : PAD_X + ((t - tMin) / tSpan) * (WIDTH - 2 * PAD_X);
  const y = (v: number) =>
    vMax === vMin
      ? HEIGHT / 2
      : PAD_Y + ((vMax - v) / vSpan) * (HEIGHT - 2 * PAD_Y);

  const points = series.map((point, index) => ({
    ...point,
    cx: x(times[index]),
    cy: y(values[index]),
  }));
  const last = points[points.length - 1];

  // Hover hit columns: each point owns the span to the midpoints of its
  // neighbours, full height - a target far bigger than the mark.
  const bounds = points.map((point, index) => {
    const left = index === 0 ? 0 : (points[index - 1].cx + point.cx) / 2;
    const right = index === points.length - 1 ? WIDTH : (point.cx + points[index + 1].cx) / 2;
    return { left, right };
  });

  return (
    <svg
      role="img"
      aria-label={label}
      width={WIDTH}
      height={HEIGHT}
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      className="shrink-0"
    >
      {points.length > 1 ? (
        <polyline
          points={points.map((point) => `${point.cx},${point.cy}`).join(" ")}
          fill="none"
          stroke="var(--color-stone)"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      ) : null}
      <circle
        cx={last.cx}
        cy={last.cy}
        r="4"
        fill="var(--color-gold)"
        stroke="var(--color-paper)"
        strokeWidth="2"
      />
      {points.map((point, index) => (
        <rect
          key={point.observed_at + point.cx}
          x={bounds[index].left}
          y={0}
          width={bounds[index].right - bounds[index].left}
          height={HEIGHT}
          fill="transparent"
        >
          <title>{`${formatDate(point.observed_at)}: ${money(point.price)}`}</title>
        </rect>
      ))}
    </svg>
  );
}
