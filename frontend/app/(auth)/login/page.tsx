import type { Metadata } from "next"

import { AuthForm } from "@/components/auth/auth-form"
import { safeNextPath } from "@/lib/auth"

export const metadata: Metadata = { title: "Sign in · AI Knowledge Base" }

const ERRORS: Record<string, string> = {
  confirmation: "That confirmation link is invalid or has expired. Sign in, or request a new link.",
}

export default async function LoginPage({ searchParams }: PageProps<"/login">) {
  const { next, error } = await searchParams
  return (
    <AuthForm
      mode="login"
      next={safeNextPath(typeof next === "string" ? next : null)}
      initialError={typeof error === "string" ? ERRORS[error] : undefined}
    />
  )
}
