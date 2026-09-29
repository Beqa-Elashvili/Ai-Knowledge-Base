import type { ApiErrorBody, HealthResponse } from "@/types"

/**
 * Single entry point for all backend (FastAPI) communication.
 * Components must call `api.*` instead of using fetch directly.
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...init?.headers },
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error
    throw new ApiError("Unable to reach the server.", 0)
  }

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as ApiErrorBody | null
    throw new ApiError(errorMessage(body, response.statusText || "Request failed"), response.status)
  }

  return (await response.json()) as T
}

export const api = {
  health: (signal?: AbortSignal) => request<HealthResponse>("/health", { signal }),
}
