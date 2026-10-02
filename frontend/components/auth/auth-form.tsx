"use client"

import { Eye, EyeOff, MailCheck } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState, type FormEvent } from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { authErrorMessage } from "@/lib/auth"
import { createClient } from "@/lib/supabase/client"

const MIN_PASSWORD_LENGTH = 8

type Mode = "login" | "register"

interface AuthFormProps {
  mode: Mode
  /** Safe, same-site path to continue to after signing in. */
  next: string
  /** Message to show on load, e.g. after a failed confirmation link. */
  initialError?: string
}

export function AuthForm({ mode, next, initialError }: AuthFormProps) {
  const router = useRouter()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(initialError ?? null)
  const [unconfirmed, setUnconfirmed] = useState(false)
  const [sentTo, setSentTo] = useState<string | null>(null)

  const isRegister = mode === "register"

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setUnconfirmed(false)

    const cleanEmail = email.trim()
    if (isRegister && password.length < MIN_PASSWORD_LENGTH) {
      setError(`Use at least ${MIN_PASSWORD_LENGTH} characters for your password.`)
      return
    }

    setPending(true)
    const supabase = createClient()
    try {
      if (isRegister) {
        const { data, error } = await supabase.auth.signUp({
          email: cleanEmail,
          password,
          options: { emailRedirectTo: callbackUrl(next) },
        })
        if (error) throw error
        if (data.session) {
          // Email confirmation is off for this project: already signed in.
          router.replace(next)
          router.refresh()
          return
        }
        setSentTo(cleanEmail)
      } else {
        const { error } = await supabase.auth.signInWithPassword({ email: cleanEmail, password })
        if (error) throw error
        router.replace(next)
        router.refresh()
        return
      }
    } catch (err) {
      const code = (err as { code?: string }).code
      setUnconfirmed(code === "email_not_confirmed")
      setError(authErrorMessage(code, isRegister ? "Could not create your account. Please try again." : "Could not sign you in. Please try again."))
    }
    setPending(false)
  }

  if (sentTo) {
    return <CheckYourEmail email={sentTo} next={next} onBack={() => setSentTo(null)} />
  }

  return (
    <div className="w-full">
      <h1 className="text-[22px] leading-tight font-semibold tracking-[-0.02em]">
        {isRegister ? "Create your account" : "Welcome back"}
      </h1>
      <p className="mt-1.5 text-[14px] text-text-secondary">
        {isRegister ? "Upload PDFs and chat with them, with page-level sources." : "Sign in to your knowledge base."}
      </p>

      <form onSubmit={onSubmit} noValidate className="mt-7 space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            inputMode="email"
            placeholder="you@example.com"
            required
            autoFocus
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            aria-invalid={Boolean(error) || undefined}
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="password">Password</Label>
          <div className="relative">
            <Input
              id="password"
              type={showPassword ? "text" : "password"}
              autoComplete={isRegister ? "new-password" : "current-password"}
              required
              minLength={isRegister ? MIN_PASSWORD_LENGTH : undefined}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-invalid={Boolean(error) || undefined}
              aria-describedby={isRegister ? "password-hint" : undefined}
              className="pr-10"
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? "Hide password" : "Show password"}
              className="absolute inset-y-0 right-0 flex w-10 items-center justify-center rounded-r-lg text-text-muted transition-colors duration-150 hover:text-foreground focus-visible:text-foreground focus-visible:outline-none"
            >
              {showPassword ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
            </button>
          </div>
          {isRegister && (
            <p id="password-hint" className="text-[12px] text-text-muted">
              At least {MIN_PASSWORD_LENGTH} characters.
            </p>
          )}
        </div>

        {error && (
          <div role="alert" className="rounded-lg border border-destructive/20 bg-destructive/[0.04] px-3 py-2.5 text-[13px] text-destructive">
            {error}
            {unconfirmed && <ResendLink email={email.trim()} next={next} />}
          </div>
        )}

        <Button type="submit" className="w-full" loading={pending} disabled={!email.trim() || !password}>
          {isRegister ? "Create account" : "Sign in"}
        </Button>
      </form>

      <p className="mt-6 text-center text-[13px] text-text-secondary">
        {isRegister ? "Already have an account? " : "New here? "}
        <Link
          href={`${isRegister ? "/login" : "/register"}${next !== "/dashboard" ? `?next=${encodeURIComponent(next)}` : ""}`}
          className="font-medium text-foreground underline-offset-4 hover:underline"
        >
          {isRegister ? "Sign in" : "Create an account"}
        </Link>
      </p>
    </div>
  )
}

function callbackUrl(next: string): string {
  const url = new URL("/auth/callback", window.location.origin)
  url.searchParams.set("next", next)
  return url.toString()
}

function CheckYourEmail({ email, next, onBack }: { email: string; next: string; onBack: () => void }) {
  return (
    <div className="w-full">
      <span className="flex size-10 items-center justify-center rounded-xl border border-border bg-canvas text-foreground shadow-xs">
        <MailCheck className="size-[18px]" strokeWidth={1.6} aria-hidden />
      </span>
      <h1 className="mt-5 text-[22px] leading-tight font-semibold tracking-[-0.02em]">Check your email</h1>
      <p className="mt-2 text-[14px] leading-relaxed text-text-secondary">
        We sent a confirmation link to <span className="font-medium text-foreground">{email}</span>. Open it on this
        device to activate your account and sign in.
      </p>
      <div className="mt-6 flex flex-wrap items-center gap-x-4 gap-y-2 text-[13px]">
        <ResendLink email={email} next={next} />
        <button type="button" onClick={onBack} className="text-text-secondary underline-offset-4 hover:text-foreground hover:underline">
          Use a different email
        </button>
      </div>
    </div>
  )
}

function ResendLink({ email, next }: { email: string; next: string }) {
  const [state, setState] = useState<"idle" | "sending" | "sent" | "failed">("idle")

  async function resend() {
    setState("sending")
    const { error } = await createClient().auth.resend({
      type: "signup",
      email,
      options: { emailRedirectTo: callbackUrl(next) },
    })
    setState(error ? "failed" : "sent")
  }

  if (state === "sent") return <span className="text-success"> Confirmation email sent again.</span>
  return (
    <>
      {" "}
      <button
        type="button"
        onClick={resend}
        disabled={state === "sending" || !email}
        className="font-medium text-foreground underline underline-offset-4 disabled:opacity-50"
      >
        {state === "sending" ? "Sending…" : "Resend confirmation email"}
      </button>
      {state === "failed" && <span className="text-destructive"> Could not send. Try again in a minute.</span>}
    </>
  )
}
