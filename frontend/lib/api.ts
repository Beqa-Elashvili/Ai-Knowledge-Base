import type {
  ApiErrorBody,
  ChatEvent,
  Conversation,
  ConversationDetail,
  Document,
  HealthResponse,
  User,
} from "@/types"

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

export interface UploadOptions {
  title?: string
  signal?: AbortSignal
  /** Upload progress of the file bytes, 0–1. */
  onProgress?: (fraction: number) => void
  /** Called once the file is sent; the server is now extracting and embedding. */
  onProcessing?: () => void
}

/**
 * Upload a PDF. Uses XMLHttpRequest because fetch cannot report upload
 * progress. Resolves with the created document once the server has
 * extracted, chunked and embedded it.
 */
async function uploadDocument(file: File, options: UploadOptions = {}): Promise<Document> {
  const token = await accessToken()
  const form = new FormData()
  form.append("file", file)
  if (options.title) form.append("title", options.title)

  return new Promise<Document>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open("POST", `${API_URL}/documents/upload`)
    xhr.setRequestHeader("Authorization", `Bearer ${token}`)
    xhr.setRequestHeader("Accept", "application/json")
    xhr.responseType = "json"

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) options.onProgress?.(event.loaded / event.total)
    }
    xhr.upload.onload = () => {
      options.onProgress?.(1)
      options.onProcessing?.()
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) return resolve(xhr.response as Document)
      if (xhr.status === 401) onUnauthorized()
      reject(new ApiError(errorMessage(xhr.response as ApiErrorBody | null, "Upload failed."), xhr.status))
    }
    xhr.onerror = () => reject(new ApiError("Unable to reach the server.", 0))
    xhr.onabort = () => reject(new DOMException("Upload cancelled", "AbortError"))

    options.signal?.addEventListener("abort", () => xhr.abort(), { once: true })
    xhr.send(form)
  })
}

export interface ChatRequest {
  document_id: string
  conversation_id?: string
  message: string
}

/**
 * Ask a question and receive the answer as Server-Sent Events
 * (`meta`, `token`…, `done` | `error`). Errors before the stream starts
 * (404, 409, 502, …) reject with ApiError; abort the signal to stop the
 * answer (the backend saves what was generated so far).
 */
async function streamChat(body: ChatRequest, onEvent: (event: ChatEvent) => void, signal?: AbortSignal): Promise<void> {
  const token = await accessToken()
  let response: Response
  try {
    response = await fetch(`${API_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream", Authorization: `Bearer ${token}` },
      body: JSON.stringify(body),
      signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error
    throw new ApiError("Unable to reach the server.", 0)
  }
  if (!response.ok || !response.body) {
    const errorBody = (await response.json().catch(() => null)) as ApiErrorBody | null
    if (response.status === 401) onUnauthorized()
    throw new ApiError(errorMessage(errorBody, "Could not get an answer."), response.status)
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ""
  try {
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += value
      let boundary: number
      while ((boundary = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        const event = parseEvent(block)
        if (event) onEvent(event)
      }
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error
    throw new ApiError("The connection was interrupted.", 0)
  } finally {
    reader.releaseLock()
  }
}

function parseEvent(block: string): ChatEvent | null {
  let name = ""
  const data: string[] = []
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) name = line.slice(6).trim()
    else if (line.startsWith("data:")) data.push(line.slice(5).trimStart())
  }
  if (!name || data.length === 0) return null
  try {
    return { event: name, data: JSON.parse(data.join("\n")) } as ChatEvent
  } catch {
    return null
  }
}

const json = (body: unknown): RequestOptions => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
})

export const api = {
  health: (signal?: AbortSignal) => request<HealthResponse>("/health", { signal, auth: false }),
  me: (signal?: AbortSignal) => request<User>("/auth/me", { signal }),

  documents: {
    list: (signal?: AbortSignal) => request<Document[]>("/documents", { signal }),
    get: (id: string, signal?: AbortSignal) => request<Document>(`/documents/${id}`, { signal }),
    upload: uploadDocument,
    delete: (id: string) => request<void>(`/documents/${id}`, { method: "DELETE" }),
    /** Generate (or regenerate) and store the summary; can take a while for long PDFs. */
    summarize: (id: string, language?: string) =>
      request<Document>(`/documents/${id}/summary`, json(language ? { language } : {})),
    /** Generate (or regenerate) and store suggested questions. */
    generateQuestions: (id: string, language?: string) =>
      request<Document>(`/documents/${id}/questions`, json(language ? { language } : {})),
  },

  conversations: {
    list: (documentId?: string, signal?: AbortSignal) =>
      request<Conversation[]>(
        documentId ? `/conversations?document_id=${encodeURIComponent(documentId)}` : "/conversations",
        { signal },
      ),
    get: (id: string, signal?: AbortSignal) => request<ConversationDetail>(`/conversations/${id}`, { signal }),
    create: (documentId: string, title?: string) =>
      request<Conversation>("/conversations", json({ document_id: documentId, title })),
    delete: (id: string) => request<void>(`/conversations/${id}`, { method: "DELETE" }),
  },

  chat: { stream: streamChat },
}
