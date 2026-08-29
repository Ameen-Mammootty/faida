/**
 * The extraction seam's placeholder vocabulary, mirrored value for value from
 * apps/api extraction/normalize.py (PLACEHOLDERS / blank_to_none). A printed
 * table marks "nothing here" with a dash, so a dash, "n/a" or an empty string
 * is an absence, not a value. The server runs every pack-size correction
 * through this vocabulary (api.py _to_edit); the mock and the edit form share
 * this one mirror so neither invents its own idea of blank.
 */
export const PLACEHOLDERS = new Set([
  "-",
  "--",
  "---",
  "–",
  "—",
  "n/a",
  "na",
  "none",
  "nil",
  "",
]);

/** normalize.py blank_to_none: collapse whitespace; a placeholder is null. */
export function blankToNone(value: string): string | null {
  const text = value.split(/\s+/).filter(Boolean).join(" ");
  return PLACEHOLDERS.has(text.toLowerCase()) ? null : text;
}
