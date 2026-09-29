import { createBrowserClient } from "@supabase/ssr"

/**
 * Browser Supabase client — used for authentication only (sign up, sign in,
 * session). It uses the public anon/publishable key, never the service key.
 * All data access goes through the FastAPI backend via `lib/api.ts`.
 */

// NEXT_PUBLIC_* values must be referenced literally so Next.js can inline them.
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY

export function createClient() {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
    throw new Error(
      "Missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY. Copy frontend/.env.example to .env.local.",
    )
  }
  // createBrowserClient returns a singleton in the browser.
  return createBrowserClient(SUPABASE_URL, SUPABASE_ANON_KEY)
}
