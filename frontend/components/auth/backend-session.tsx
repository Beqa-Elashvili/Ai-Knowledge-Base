"use client"

import { ShieldCheck } from "lucide-react"
import { useEffect, useState } from "react"

import { api, ApiError } from "@/lib/api"
import type { User } from "@/types"

/** Confirms the backend accepts this session (GET /auth/me). */
export function BackendSession() {
  const [user, setUser] = useState<User | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    api
      .me(controller.signal)
      .then(setUser)
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") return
        setError(err instanceof ApiError ? err.message : "Could not reach the server.")
      })
    return () => controller.abort()
  }, [])

  if (error) return <p className="text-[13px] text-destructive">{error}</p>
  if (!user) return <div className="h-5 w-64 animate-pulse rounded-md bg-surface" aria-label="Checking session" />
  return (
    <p className="inline-flex items-center gap-2 text-[13px] text-text-secondary" data-testid="backend-user">
      <ShieldCheck className="size-4 text-success" strokeWidth={1.75} aria-hidden />
      Backend verified your session as <span className="font-medium text-foreground">{user.email}</span>
    </p>
  )
}
