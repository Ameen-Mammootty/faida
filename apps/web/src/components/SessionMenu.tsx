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
 * `showEmail` forces the address on: the shell's narrow-screen row has the
 * room for it, the desktop header only from md up.
 */
export default function SessionMenu({ showEmail = false }: { showEmail?: boolean } = {}) {
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
    <div className="flex items-center gap-3 sm:gap-4">
      {email ? (
        <span
          className={`max-w-[16rem] truncate text-xs text-stone ${showEmail ? "" : "hidden md:inline"}`}
          title={email}
        >
          {email}
        </span>
      ) : null}
      <button
        type="button"
        onClick={signOut}
        disabled={busy}
        className="text-sm font-medium whitespace-nowrap text-stone hover:text-palm disabled:opacity-60"
      >
        Sign out
      </button>
    </div>
  );
}
