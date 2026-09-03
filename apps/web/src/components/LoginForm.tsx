"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useState } from "react";
import { isMockMode } from "@/lib/api";
import { safeNextPath } from "@/lib/gate";
import { supabaseBrowser } from "@/lib/supabase/browser";
import { AlertIcon } from "./icons";

/**
 * The sign-in form (M7 WP-71). One job: `signInWithPassword`, then on to
 * the screen the visitor was heading for, or the invoice list.
 *
 * Errors are one plain sentence each. Supabase's own messages ("Invalid
 * login credentials", "Email not confirmed") never reach the screen: a
 * wrong password and an unknown email read the same, on purpose, so the
 * form does not confirm which emails have accounts.
 *
 * In mock mode there is no Supabase and nobody to check a password with:
 * the form still renders for QA and design reviews, and submitting it just
 * walks in as the sample owner.
 *
 * The landing after sign-in is a full navigation rather than the router's:
 * the request interceptor has to see the new session cookies, and it does
 * on the next real request.
 */
export default function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = safeNextPath(searchParams.get("next"));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (isMockMode()) {
      router.replace(next);
      return;
    }
    setBusy(true);
    try {
      const { error: signInError } = await supabaseBrowser().auth.signInWithPassword({
        email: email.trim(),
        password,
      });
      if (signInError) {
        setError(plainSentence(signInError.message));
        setBusy(false);
        return;
      }
      window.location.assign(next);
    } catch {
      setError("Couldn't reach Faida to sign you in. Check your connection and try again.");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
      <label className="flex flex-col gap-1 text-xs font-medium text-ink">
        Email
        <input
          type="email"
          name="email"
          inputMode="email"
          autoComplete="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          className={inputClasses}
        />
      </label>
      <label className="flex flex-col gap-1 text-xs font-medium text-ink">
        Password
        <input
          type="password"
          name="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          className={inputClasses}
        />
      </label>
      {error ? (
        <p
          role="alert"
          className="flex items-center gap-2 rounded-md border border-plum/30 bg-paper px-3 py-2.5 text-sm font-medium text-plum"
        >
          <AlertIcon />
          {error}
        </p>
      ) : null}
      <button
        type="submit"
        disabled={busy}
        className="rounded-sm bg-palm px-4 py-2 text-sm font-semibold text-white hover:bg-palm-deep disabled:opacity-60"
      >
        {busy ? "Signing in" : "Sign in"}
      </button>
    </form>
  );
}

const inputClasses =
  "min-w-0 rounded-sm border border-ink/20 bg-paper px-2.5 py-2 text-base text-ink hover:border-palm/50 sm:text-sm";

/** Supabase's message, translated to the one sentence the owner needs. */
function plainSentence(message: string): string {
  const lower = message.toLowerCase();
  if (lower.includes("invalid login credentials") || lower.includes("invalid_credentials")) {
    return "That email or password didn't match. Try again.";
  }
  if (lower.includes("email not confirmed")) {
    return "This account isn't ready to use yet. Message the Faida team.";
  }
  if (lower.includes("rate limit") || lower.includes("too many")) {
    return "Too many tries in a row. Wait a minute and try again.";
  }
  if (lower.includes("valid email") || lower.includes("validate email")) {
    return "Enter your email address to sign in.";
  }
  return "Couldn't sign you in. Try again.";
}
