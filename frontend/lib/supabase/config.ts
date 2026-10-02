// NEXT_PUBLIC_* values must be referenced literally so Next.js can inline them.
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY

/** Public Supabase settings (URL + anon key). The service key never reaches the frontend. */
export function supabaseConfig(): { url: string; anonKey: string } {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
    throw new Error(
      "Missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY. Copy frontend/.env.example to .env.local.",
    )
  }
  return { url: SUPABASE_URL, anonKey: SUPABASE_ANON_KEY }
}
