"use client";

import { useEffect, useState } from "react";
import { getIncentive, setRoleShares } from "@/lib/api";
import {
  SHARES_APPLIES_NOTE,
  SHARES_CAPTION,
  SHARE_LABEL,
  SHARE_ROLES,
  canSaveShares,
  shareBody,
  shareDraft,
  sharesStanding,
  sharesUpdatedWords,
  sumWords,
  type ShareDraft,
} from "@/lib/incentiveScreen";
import type { RoleSharesRow } from "@/lib/types";

/**
 * M13.2 (issue #8): the staff incentive screen, sixth in the shell - its
 * first block, the three role shares that split a month's pool between the
 * manager, the supervisor and the sales team (D2).
 *
 * Every choice this renders is decided in `lib/incentiveScreen.ts` and pinned
 * by vitest there - the dashboard's rule, because a choice left inside a
 * component would be untested by construction. Nothing here words a refusal:
 * Save is offered only for three percentages adding to a hundred, and a
 * refusal that gets past that is the API's own sentence, shown as it came.
 *
 * The scheme month, the push weeks and each branch's statement land below
 * this block in the tickets that follow, out of the same one read.
 */
export default function Incentive() {
  const [shares, setShares] = useState<RoleSharesRow | null>(null);
  const [draft, setDraft] = useState<ShareDraft>(shareDraft(null));
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  // Try again is a bump of this, so the one effect above is the only place
  // that reads - the shipped Dashboard's pattern, and what keeps the
  // cancelled guard on every read rather than on the first one.
  const [reloadKey, setReloadKey] = useState(0);
  const [feedback, setFeedback] = useState<{
    kind: "error" | "done";
    text: string;
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const result = await getIncentive();
        if (cancelled) return;
        setShares(result.shares);
        setDraft(shareDraft(result.shares));
        setLoadError(null);
      } catch (error) {
        if (cancelled) return;
        setLoadError(error instanceof Error ? error.message : "Could not load the incentive.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  async function save() {
    setSaving(true);
    setFeedback(null);
    try {
      const result = await setRoleShares(shareBody(draft));
      setShares(result.shares);
      setDraft(shareDraft(result.shares));
      setFeedback({ kind: "done", text: "The shares are saved." });
    } catch (error) {
      setFeedback({
        kind: "error",
        text: error instanceof Error ? error.message : "That did not work.",
      });
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <p role="status" aria-live="polite" className="text-sm text-stone">
        Loading the incentive
      </p>
    );
  }

  if (loadError !== null) {
    return (
      <div className="space-y-3">
        <p className="max-w-3xl text-base leading-relaxed text-ink">{loadError}</p>
        <button
          type="button"
          onClick={() => {
            setLoading(true);
            setLoadError(null);
            setReloadKey((key) => key + 1);
          }}
          className="min-h-11 rounded-sm border border-palm/30 px-3 py-2 text-sm font-medium text-palm hover:border-palm"
        >
          Try again
        </button>
      </div>
    );
  }

  const saveable = canSaveShares(draft, shares);

  return (
    <div className="space-y-6">
      <p className="max-w-3xl text-base leading-relaxed text-ink">{sharesStanding(shares)}</p>

      <section aria-labelledby="shares-heading" className="space-y-4">
        <div className="space-y-1">
          <h2 id="shares-heading" className="text-sm font-semibold text-ink">
            Role shares
          </h2>
          <p className="max-w-2xl text-sm text-stone">{SHARES_CAPTION}</p>
        </div>

        <div className="max-w-2xl space-y-4 rounded-md border border-ink/10 bg-paper p-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {SHARE_ROLES.map((role) => (
              <label key={role} className="flex flex-col gap-1 text-xs font-medium text-ink">
                {SHARE_LABEL[role]}
                <span className="flex items-center gap-1">
                  <input
                    type="text"
                    inputMode="decimal"
                    value={draft[role]}
                    onChange={(event) => {
                      setFeedback(null);
                      setDraft({ ...draft, [role]: event.target.value });
                    }}
                    aria-label={`${SHARE_LABEL[role]} share, percent`}
                    className="min-h-11 w-full rounded-sm border border-ink/20 bg-paper px-3 text-sm text-ink"
                  />
                  <span aria-hidden="true" className="text-sm text-stone">
                    %
                  </span>
                </span>
              </label>
            ))}
          </div>

          <p role="status" aria-live="polite" className="text-sm text-stone">
            {sumWords(draft)}
          </p>

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              disabled={!saveable || saving}
              onClick={() => void save()}
              className="min-h-11 rounded-sm bg-palm px-4 py-2 text-sm font-medium text-cream disabled:opacity-60"
            >
              {saving ? "Saving" : "Save shares"}
            </button>
            <p className="text-xs text-stone">{sharesUpdatedWords(shares)}</p>
          </div>

          <p className="max-w-xl text-xs leading-relaxed text-stone">{SHARES_APPLIES_NOTE}</p>

          {feedback !== null ? (
            <p
              role="status"
              aria-live="polite"
              className={`rounded-sm border px-3 py-2 text-sm ${
                feedback.kind === "error"
                  ? "border-plum/40 bg-paper text-ink"
                  : "border-palm/30 bg-paper text-ink"
              }`}
            >
              <span className="font-medium">
                {feedback.kind === "error" ? "Not done: " : "Done. "}
              </span>
              {feedback.text}
            </p>
          ) : null}
        </div>
      </section>
    </div>
  );
}
