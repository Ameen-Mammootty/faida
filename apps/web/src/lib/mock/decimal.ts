/**
 * Exact decimal arithmetic on money strings, mock-side only.
 *
 * The mock has to replay the server's deterministic checks (apps/api
 * extraction/validate.py runs Python Decimal), so it needs real arithmetic.
 * BigInt-scaled integers keep that exact - no floats anywhere. UI code never
 * imports this: rendering stays verbatim strings.
 */

export interface Dec {
  units: bigint;
  scale: number;
}

const DEC_RE = /^([+-]?)(\d+)(?:\.(\d+))?$/;

export function dec(value: string): Dec | null {
  const match = DEC_RE.exec(value.trim());
  if (!match) return null;
  const [, sign, whole, frac = ""] = match;
  const units = BigInt(whole + frac) * (sign === "-" ? -1n : 1n);
  return { units, scale: frac.length };
}

function rescale(d: Dec, scale: number): Dec {
  if (scale < d.scale) throw new Error("cannot reduce scale");
  return { units: d.units * 10n ** BigInt(scale - d.scale), scale };
}

function aligned(a: Dec, b: Dec): [Dec, Dec] {
  const scale = Math.max(a.scale, b.scale);
  return [rescale(a, scale), rescale(b, scale)];
}

export function add(a: Dec, b: Dec): Dec {
  const [x, y] = aligned(a, b);
  return { units: x.units + y.units, scale: x.scale };
}

export function sub(a: Dec, b: Dec): Dec {
  const [x, y] = aligned(a, b);
  return { units: x.units - y.units, scale: x.scale };
}

export function mul(a: Dec, b: Dec): Dec {
  return { units: a.units * b.units, scale: a.scale + b.scale };
}

export function abs(d: Dec): Dec {
  return { units: d.units < 0n ? -d.units : d.units, scale: d.scale };
}

/** -1, 0, or 1 for a <=> b. */
export function cmp(a: Dec, b: Dec): number {
  const [x, y] = aligned(a, b);
  if (x.units === y.units) return 0;
  return x.units < y.units ? -1 : 1;
}

export function lte(a: Dec, b: Dec): boolean {
  return cmp(a, b) <= 0;
}

export function maxDec(a: Dec, b: Dec): Dec {
  return cmp(a, b) >= 0 ? a : b;
}

export const ZERO: Dec = { units: 0n, scale: 0 };

/**
 * a / b to a fixed scale, rounded half up - Python's ROUND_HALF_UP, which is
 * what the sales door quantizes a net amount with (M8 C11.2: `amount /
 * (1 + rate)` to a fil per line). Mock-side only, like everything here: the
 * browser never divides money before the door answers.
 */
export function divTo(a: Dec, b: Dec, scale: number): Dec {
  if (b.units === 0n) throw new Error("division by zero");
  // Scale the numerator so the integer quotient carries `scale` decimals
  // plus one guard digit for the rounding.
  const shift = BigInt(scale + 1 + b.scale - a.scale);
  const numerator = shift >= 0n ? a.units * 10n ** shift : a.units / 10n ** -shift;
  const quotient = numerator / b.units;
  const negative = quotient < 0n;
  const magnitude = negative ? -quotient : quotient;
  const guard = magnitude % 10n;
  const rounded = magnitude / 10n + (guard >= 5n ? 1n : 0n);
  return { units: negative ? -rounded : rounded, scale };
}

/** Sum a list of money strings exactly, rendered at the widest scale seen
 * (at least two decimals) - the preview's "takings" column. */
export function sumStrings(values: string[]): string {
  let total: Dec = { units: 0n, scale: 2 };
  for (const value of values) {
    const parsed = dec(value);
    if (parsed) total = add(total, parsed);
  }
  return fmt(total);
}

/**
 * Render with the scale the arithmetic produced, matching how Python Decimal
 * serializes: 12 x 4.50 renders "54.00", 2.5 x 4.50 renders "11.250".
 */
export function fmt(d: Dec): string {
  const negative = d.units < 0n;
  const digits = (negative ? -d.units : d.units).toString().padStart(d.scale + 1, "0");
  const cut = digits.length - d.scale;
  const whole = digits.slice(0, cut);
  const frac = digits.slice(cut);
  return `${negative ? "-" : ""}${whole}${frac ? `.${frac}` : ""}`;
}
