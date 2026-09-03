/**
 * The two public Supabase values (M7 WP-71). Both are NEXT_PUBLIC_ and
 * inlined into the bundle at build time; both are public by design - the
 * project URL and the anon (publishable) key grant nothing on their own, and
 * every table already sits behind deny-all row-level security.
 *
 * Read lazily, at call time: CI runs `next build` with neither value set,
 * and mock mode must be able to construct no client at all. A missing value
 * in live mode is a plain error the moment something needs it, never at
 * import.
 */
export function supabaseEnv(): { url: string; key: string } {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) {
    throw new Error(
      "NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY must both be set to sign in. " +
        "Set them (see .env.example) or run in mock mode.",
    );
  }
  return { url, key };
}
