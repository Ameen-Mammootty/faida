"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { isMockMode } from "@/lib/api";
import { LOGIN_PATH } from "@/lib/gate";
import { getSessionEmail, supabaseBrowser } from "@/lib/supabase/browser";

/** The stand-in owner every gated screen shows in mock mode (WP-71). */
const MOCK_OWNER_EMAIL = "owner@sample.faida";

/**
 * Who is signed in, and the way out (M7 WP-71). Lives in the app shell's
 * header on every console screen.
 *
 * The email comes from the local session, no network; it is a label, not a
 * check - the request interceptor does the checking. Sign out clears the
 * session through Supabase and lands on /login with a full navigation, so a
 * back-button visit to a console screen meets the gate again.
 *
 * In mock mode there is no session to clear and no network to reach: the
 * shell shows the sample owner, and sign out simply goes to /login.
 *
 * One instance serves all three chromes (M9 WP-97), so where the address is
 * shown is now a matter of width alone: the phone's quiet row has the space
 * for it, the header row only from md up, and the sidebar always. The colours
 * follow the ground the shell puts this on - Slate on cream under 1280 px,
 * Warm Cream on Date Palm in the sidebar, where the focus ring has to be gold
 * because the palm ring the app uses elsewhere would vanish on palm. The `!`
 * is deliberate: the global `:focus-visible` rule is unlayered and would
 * otherwise beat a utility.
 */
export default function SessionMenu() {
  const router = useRouter();
  const mock = isMockMode();
  const [email, setEmail] = useState<string | null>(mock ? MOCK_OWNER_EMAIL : null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (mock) return;
    let cancelled = false;
    getSessionEmail()
      .then((value) => {
        if (!cancelled) setEmail(value);
      })
      .catch(() => {
        // Nothing to show; the gate has already decided whether this screen renders.
      });
    return () => {
      cancelled = true;
    };
  }, [mock]);

  async function signOut() {
    if (mock) {
      router.push(LOGIN_PATH);
      return;
    }
    setBusy(true);
    try {
      await supabaseBrowser().auth.signOut();
    } catch {
      // The local session is cleared before the network call; landing on
      // /login is still right.
    }
    window.location.assign(LOGIN_PATH);
  }

  return (
    <div className="flex min-w-0 items-center gap-3 sm:gap-4 xl:w-full xl:flex-col xl:items-start xl:gap-1">
      {email ? (
        <span
          // min-w-0 so a long address truncates rather than pushing the row
          // wide; the cap is the sidebar's own width from 1280 px.
          className="min-w-0 max-w-64 truncate text-xs text-stone sm:hidden md:inline xl:max-w-full xl:text-cream/70"
          title={email}
        >
          {email}
        </span>
      ) : null}
      <button
        type="button"
        onClick={signOut}
        disabled={busy}
        className="text-sm font-medium whitespace-nowrap text-stone hover:text-palm disabled:opacity-60 xl:text-cream/80 xl:hover:text-cream xl:focus-visible:outline-gold!"
      >
        Sign out
      </button>
    </div>
  );
}
