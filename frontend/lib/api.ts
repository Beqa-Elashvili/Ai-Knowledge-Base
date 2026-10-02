import type { ApiErrorBody, HealthResponse, User } from "@/types"

import { createClient } from "@/lib/supabase/client"

/**
 * Single entry point for all backend (FastAPI) communication.
 * Components must call `api.*` instead of using fetch directly.
 *
 * Authenticated requests carry the Supabase access token as a Bearer token;
 * the backend verifies it and scopes every query to that user.
 */

const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "")

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message)
    this.name = "ApiError"
  }
}

function errorMessage(body: ApiErrorBody | null, fallback: string): string {
  if (!body?.detail) return fallback
  if (typeof body.detail === "string") return body.detail
  return body.detail.map((d) => d.msg).join(", ")
}

async function accessToken(): Promise<string> {
  const { data } = await createClient().auth.getSession()
  const token = data.session?.access_token
  if (!token) {
    onUnauthorized()
    throw new ApiError("Your session has ended. Please sign in again.", 401)
  }
  return token
}

/** Session missing or rejected by the backend: sign out and go to /login. */
function onUnauthorized() {
  if (typeof window === "undefined") return
  void createClient().auth.signOut({ scope: "local" })
  const next = `${window.location.pathname}${window.location.search}`
  // A full navigation on purpose: it drops all client state of the ended
  // session. (This module is not a component, so useRouter is unavailable.)
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination
  window.location.assign(`/login?next=${encodeURIComponent(next)}`)
}

interface RequestOptions extends RequestInit {
  /** Send the user's access token (default true). */
  auth?: boolean
}

async function request<T>(path: string, { auth = true, ...init }: RequestOptions = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set("Accept", "application/json")
  if (auth) headers.set("Authorization", `Bearer ${await accessToken()}`)

  let response: Response
  try {
    response = await fetch(`${API_URL}${path}`, { ...init, headers })
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error
    throw new ApiError("Unable to reach the server.", 0)
  }

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as ApiErrorBody | null
    if (response.status === 401 && auth) onUnauthorized()
    throw new ApiError(errorMessage(body, response.statusText || "Request failed"), response.status)
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  health: (signal?: AbortSignal) => request<HealthResponse>("/health", { signal, auth: false }),
  me: (signal?: AbortSignal) => request<User>("/auth/me", { signal }),
}
