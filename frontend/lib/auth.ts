/**
 * Where to send the user after signing in: the `next` path they were going
 * to, if it is a safe same-site path, else the dashboard. Rejects absolute
 * and protocol-relative URLs ("https://evil.com", "//evil.com", "/\evil.com")
 * so the parameter cannot be used as an open redirect.
 */
export function safeNextPath(next: string | null | undefined, fallback = "/dashboard"): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return fallback
  return next
}

/** Friendly messages for Supabase Auth error codes. */
export function authErrorMessage(code: string | undefined, fallback: string): string {
  switch (code) {
    case "invalid_credentials":
      return "Incorrect email or password."
    case "email_not_confirmed":
      return "Please confirm your email first. Check your inbox for the confirmation link."
    case "user_already_exists":
    case "email_exists":
      return "An account with this email already exists. Sign in instead."
    case "weak_password":
      return "Choose a stronger password: at least 8 characters."
    case "over_email_send_rate_limit":
    case "over_request_rate_limit":
      return "Too many attempts. Please wait a minute and try again."
    case "email_address_invalid":
      return "Enter a valid email address."
    case "signup_disabled":
      return "Sign-ups are currently disabled."
    default:
      return fallback
  }
}
