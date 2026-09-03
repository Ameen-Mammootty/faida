import { createServerClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";
import { NextResponse, type NextRequest } from "next/server";
import { supabaseEnv } from "./env";

/**
 * The server-side Supabase client for the request interceptor (M7 WP-71).
 *
 * One client per request, bound to that request's cookies. When Supabase
 * refreshes an expired session mid-request, `setAll` writes the new cookies
 * onto both the request (so anything rendered after the interceptor sees
 * them) and the response (so the browser keeps them). Skipping either half
 * is the documented road to random sign-outs, which is why this lives in
 * one place.
 *
 * The response is created here and handed back with the client, because a
 * refreshed cookie must ride on whatever response the interceptor finally
 * returns - a pass-through or a redirect.
 */
export function supabaseForRequest(request: NextRequest): {
  supabase: SupabaseClient;
  response: NextResponse;
} {
  const { url, key } = supabaseEnv();
  let response = NextResponse.next({ request });
  const supabase = createServerClient(url, key, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet) {
        for (const { name, value } of cookiesToSet) {
          request.cookies.set(name, value);
        }
        response = NextResponse.next({ request });
        for (const { name, value, options } of cookiesToSet) {
          response.cookies.set(name, value, options);
        }
      },
    },
  });
  return {
    supabase,
    get response() {
      return response;
    },
  };
}
