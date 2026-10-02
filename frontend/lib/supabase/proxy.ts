import { createServerClient } from "@supabase/ssr"
import { NextResponse, type NextRequest } from "next/server"

import { supabaseConfig } from "./config"

/**
 * Refresh the Supabase session for this request and report whether a user
 * is signed in. Refreshed auth cookies are written to both the request (so
 * Server Components see them) and the returned response.
 */
export async function updateSession(request: NextRequest): Promise<{ response: NextResponse; signedIn: boolean }> {
  const { url, anonKey } = supabaseConfig()
  let response = NextResponse.next({ request })

  const supabase = createServerClient(url, anonKey, {
    cookies: {
      getAll() {
        return request.cookies.getAll()
      },
      setAll(cookiesToSet, headers) {
        cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value))
        response = NextResponse.next({ request })
        cookiesToSet.forEach(({ name, value, options }) => response.cookies.set(name, value, options))
        Object.entries(headers ?? {}).forEach(([key, value]) => response.headers.set(key, value))
      },
    },
  })

  // Must run before anything else reads the session: it refreshes expired
  // tokens and verifies the JWT.
  const { data } = await supabase.auth.getClaims()
  return { response, signedIn: Boolean(data?.claims?.sub) }
}
