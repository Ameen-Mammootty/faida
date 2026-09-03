import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";
import { supabaseEnv } from "./env";

/**
 * The browser-side Supabase client (M7 WP-71): the login form signs in
 * through it, the shell signs out through it, and `api.ts` asks it for the
 * access token before every request. `@supabase/ssr` keeps the session in
 * cookies, which is what lets `src/proxy.ts` see the same session on the
 * server without a second sign-in.
 *
 * Created on first use and then shared, never at module scope: importing
 * this file must not touch the env, so a mock-mode build with no Supabase
 * values still compiles and runs.
 */
let client: SupabaseClient | null = null;

export function supabaseBrowser(): SupabaseClient {
  if (!client) {
    const { url, key } = supabaseEnv();
    client = createBrowserClient(url, key);
  }
  return client;
}

/**
 * The current access token, or null when nobody is signed in. Read per
 * request rather than once: `getSession` hands back a refreshed token when
 * the old one has expired, so a long run of calls - the 45-recipe loader at
 * /menu/load - survives a refresh in the middle of it.
 */
export async function getAccessToken(): Promise<string | null> {
  const {
    data: { session },
  } = await supabaseBrowser().auth.getSession();
  return session?.access_token ?? null;
}

/** The signed-in user's email for the shell, from the local session only:
 * no network, and null when nobody is signed in. */
export async function getSessionEmail(): Promise<string | null> {
  const {
    data: { session },
  } = await supabaseBrowser().auth.getSession();
  return session?.user.email ?? null;
}
