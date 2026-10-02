import { NextResponse, type NextRequest } from "next/server"

import { updateSession } from "@/lib/supabase/proxy"

/** App pages that require a signed-in user. */
const PROTECTED_PREFIXES = ["/dashboard", "/documents", "/chat"]
/** Pages only for signed-out visitors. */
const AUTH_PAGES = ["/login", "/register"]

function matches(pathname: string, prefixes: string[]): boolean {
  return prefixes.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`))
}

function redirectKeepingCookies(url: URL, from: NextResponse): NextResponse {
  const redirect = NextResponse.redirect(url)
  from.cookies.getAll().forEach((cookie) => redirect.cookies.set(cookie))
  from.headers.forEach((value, key) => {
    if (key.toLowerCase() === "cache-control") redirect.headers.set(key, value)
  })
  return redirect
}

/**
 * Keeps the Supabase session fresh on every page request and performs the
 * optimistic redirects: signed-out users away from app pages (to /login,
 * remembering where they were going), signed-in users away from the auth
 * pages. Layouts re-check the user server-side; the backend verifies the
 * token on every API call.
 */
export async function proxy(request: NextRequest) {
  const { response, signedIn } = await updateSession(request)
  const { pathname, search } = request.nextUrl

  if (!signedIn && matches(pathname, PROTECTED_PREFIXES)) {
    const url = new URL("/login", request.url)
    url.searchParams.set("next", `${pathname}${search}`)
    return redirectKeepingCookies(url, response)
  }
  if (signedIn && matches(pathname, AUTH_PAGES)) {
    return redirectKeepingCookies(new URL("/dashboard", request.url), response)
  }
  return response
}

export const config = {
  matcher: [
    // Every page except Next internals and static files.
    "/((?!_next/static|_next/image|favicon.ico|.*\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)",
  ],
}
