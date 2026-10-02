import type { EmailOtpType } from "@supabase/supabase-js"
import { NextResponse, type NextRequest } from "next/server"

import { safeNextPath } from "@/lib/auth"
import { createClient } from "@/lib/supabase/server"

/**
 * Landing point of the confirmation email link. Supabase redirects here with
 * either `?code=` (PKCE, the default) or `?token_hash=&type=` (custom email
 * templates). Either is exchanged for a session cookie, then the user goes
 * to `next` (the dashboard by default).
 */
export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams
  const next = safeNextPath(params.get("next"))
  const supabase = await createClient()

  const code = params.get("code")
  const tokenHash = params.get("token_hash")
  const type = params.get("type") as EmailOtpType | null

  let failed = true
  if (code) {
    const { error } = await supabase.auth.exchangeCodeForSession(code)
    failed = Boolean(error)
  } else if (tokenHash && type) {
    const { error } = await supabase.auth.verifyOtp({ token_hash: tokenHash, type })
    failed = Boolean(error)
  }

  if (failed) {
    const login = new URL("/login", request.url)
    login.searchParams.set("error", "confirmation")
    return NextResponse.redirect(login)
  }
  return NextResponse.redirect(new URL(next, request.url))
}
