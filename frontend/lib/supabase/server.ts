import "server-only"

import { createServerClient } from "@supabase/ssr"
import { cookies } from "next/headers"

import { supabaseConfig } from "./config"

/**
 * Supabase client for Server Components, Route Handlers and Server Actions.
 * Create one per request; never share it between requests.
 */
export async function createClient() {
  const { url, anonKey } = supabaseConfig()
  const cookieStore = await cookies()

  return createServerClient(url, anonKey, {
    cookies: {
      getAll() {
        return cookieStore.getAll()
      },
      setAll(cookiesToSet) {
        try {
          cookiesToSet.forEach(({ name, value, options }) => cookieStore.set(name, value, options))
        } catch {
          // Called from a Server Component, which cannot set cookies.
          // Safe to ignore: proxy.ts refreshes the session on every request.
        }
      },
    },
  })
}

export interface SessionUser {
  id: string
  email: string | null
}

/**
 * The signed-in user, verified from the session JWT (signature and expiry),
 * or null. Use this — not getSession() — for server-side decisions.
 */
export async function getSessionUser(): Promise<SessionUser | null> {
  const supabase = await createClient()
  const { data, error } = await supabase.auth.getClaims()
  if (error || !data?.claims?.sub) return null
  return { id: data.claims.sub, email: (data.claims.email as string | undefined) ?? null }
}
