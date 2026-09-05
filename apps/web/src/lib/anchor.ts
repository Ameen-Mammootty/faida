/**
 * M9 WP-94: the app's one anchor idiom, in one place.
 *
 * A URL fragment of the shape `#<thing>-<id>` means "the row this names is
 * open, on screen, and holds the focus ring". It shipped first on
 * `/materials#material-<id>` (M6 design review: a menu drill lands on the
 * material itself, so "fix on the materials screen" means arriving at the
 * fix), and `/invoices/<id>#line-<position>` has kept it company since. This
 * module is what the third and fourth screens learn rather than each
 * inventing a query-parameter convention of their own.
 *
 * The parsing is here; the *deciding* is here too - which row a hash names on
 * a screen, and whether that row is one that opens - because a component
 * cannot be unit tested in this project (`vitest.config.ts` runs `.test.ts` in
 * node, with no rendering library), so every decision that can leave a
 * component does.
 *
 * What is deliberately **not** here: taking focus. That is three lines inside
 * each screen, next to its own drill ref, because the element focus lands on
 * is the drill the screen already renders. Each screen guards it with an
 * `arrived` ref so the hash is honoured once per mount and no later reload of
 * its list ever yanks the reader's focus back.
 */

import type { BranchRow, MenuItemSummary } from "./types";

/**
 * The id inside a `#<prefix>-<id>` fragment, or null when the fragment is
 * absent, empty, or names something else.
 *
 * Ids are percent-decoded, because the screens that write these links encode
 * what they put in them. A fragment that is not valid encoding is returned
 * as it stands: it names no row we know, which is the same answer, and it is
 * not a reason to throw inside an effect.
 */
export function anchorId(hash: string, prefix: string): string | null {
  const head = `#${prefix}-`;
  if (!hash.startsWith(head)) return null;
  const raw = hash.slice(head.length);
  if (raw === "") return null;
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

/** `/materials#material-<id>` - the first of these, shipped in M6. */
export function anchorMaterialId(hash: string): string | null {
  return anchorId(hash, "material");
}

/** `/menu#item-<id>` - the dashboard's "See today's plate" (WP-94). */
export function anchorItemId(hash: string): string | null {
  return anchorId(hash, "item");
}

/** `/sales#branch-<id>` - a dashboard league row's days and papers (WP-94). */
export function anchorBranchId(hash: string): string | null {
  return anchorId(hash, "branch");
}

/**
 * The key `/menu` groups a category under. A menu that prints no sections
 * renders as one unlabelled group, so the null category needs a key of its
 * own; it lives here so the anchor and the ranking cannot drift apart about
 * which group a row is in.
 */
export function menuGroupKey(category: string | null): string {
  return category ?? "(none)";
}

/**
 * Which row on `/menu` a hash names.
 *
 * `ranked` is an item with a plate: it has a row in the ranking, so it opens
 * to its recipe, and its category group is expanded first because a collapsed
 * group renders only its first five rows and the named one may not be among
 * them. `uncosted` is a live item the ranking cannot carry - it sits in the
 * can't-be-costed-yet section with its missing pieces, and there is nothing
 * to open, only somewhere to arrive.
 *
 * Null for a hash that names nothing, an item that does not exist, or an item
 * that is archived: archived items appear nowhere on this screen, so the
 * honest answer is to expand nothing and say nothing.
 */
export type MenuAnchor =
  | { kind: "ranked"; id: string; groupKey: string }
  | { kind: "uncosted"; id: string };

export function menuAnchor(hash: string, items: MenuItemSummary[]): MenuAnchor | null {
  const id = anchorItemId(hash);
  if (id === null) return null;
  const item = items.find((row) => row.id === id && row.archived_at === null);
  if (item === undefined) return null;
  if (item.plate.quality === "incomplete") return { kind: "uncosted", id };
  return { kind: "ranked", id, groupKey: menuGroupKey(item.category) };
}

/**
 * Which branch row on `/sales` a hash names: its id when the table carries
 * it, null otherwise. Every branch of the tenant gets a row there whether or
 * not a day was ever loaded for it, so a league row's link always lands
 * somewhere - on a branch with nothing loaded it lands on the row that says
 * so, which is the answer to the question that was asked.
 */
export function salesAnchorBranchId(hash: string, rows: BranchRow[]): string | null {
  const id = anchorBranchId(hash);
  if (id === null) return null;
  return rows.some((row) => row.branch_id === id) ? id : null;
}
