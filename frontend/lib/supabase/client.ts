import { createBrowserClient } from "@supabase/ssr"

import { supabaseConfig } from "./config"

/**
 * Browser Supabase client — used for authentication only (sign up, sign in,
 * sign out, the current session's access token). Data access goes through
 * the FastAPI backend via `lib/api.ts`. The session lives in cookies, so the
 * server (proxy, layouts) sees the same session.
 */
export function createClient() {
  const { url, anonKey } = supabaseConfig()
  // createBrowserClient returns a singleton in the browser.
  return createBrowserClient(url, anonKey)
}
