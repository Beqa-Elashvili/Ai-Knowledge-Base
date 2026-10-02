import type { Metadata } from "next"

import { AuthForm } from "@/components/auth/auth-form"
import { safeNextPath } from "@/lib/auth"

export const metadata: Metadata = { title: "Create account · AI Knowledge Base" }

export default async function RegisterPage({ searchParams }: PageProps<"/register">) {
  const { next } = await searchParams
  return <AuthForm mode="register" next={safeNextPath(typeof next === "string" ? next : null)} />
}
