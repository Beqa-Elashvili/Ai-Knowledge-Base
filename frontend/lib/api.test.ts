import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { api, ApiError } from "@/lib/api"
import type { ChatEvent } from "@/types"

const auth = vi.hoisted(() => ({ getSession: vi.fn(), signOut: vi.fn() }))
vi.mock("@/lib/supabase/client", () => ({ createClient: () => ({ auth }) }))

const fetchMock = vi.fn<typeof fetch>()
const assign = vi.fn()

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock)
  vi.stubGlobal("window", { location: { pathname: "/documents/1", search: "?tab=chat", assign } })
  auth.getSession.mockResolvedValue({ data: { session: { access_token: "token-123" } } })
  auth.signOut.mockResolvedValue({})
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

describe("request", () => {
  it("sends the access token and returns the JSON body", async () => {
    fetchMock.mockResolvedValue(json(200, [{ id: "d1" }]))
    await expect(api.documents.list()).resolves.toEqual([{ id: "d1" }])
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/documents$/)
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer token-123")
  })

  it("does not send a token to public endpoints", async () => {
    fetchMock.mockResolvedValue(json(200, { status: "ok" }))
    await api.health()
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).has("Authorization")).toBe(false)
    expect(auth.getSession).not.toHaveBeenCalled()
  })

  it("turns the FastAPI detail into an ApiError", async () => {
    fetchMock.mockResolvedValue(json(404, { detail: "Document not found." }))
    const error = await api.documents.get("x").catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ message: "Document not found.", status: 404 })
  })

  it("joins validation error messages", async () => {
    fetchMock.mockResolvedValue(json(422, { detail: [{ msg: "too long" }, { msg: "bad id" }] }))
    await expect(api.documents.get("x")).rejects.toMatchObject({ message: "too long, bad id", status: 422 })
  })

  it("resolves 204 responses with nothing", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }))
    await expect(api.documents.delete("d1")).resolves.toBeUndefined()
  })

  it("reports an unreachable server", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"))
    await expect(api.documents.list()).rejects.toMatchObject({ message: "Unable to reach the server.", status: 0 })
  })

  it("passes aborts through unchanged", async () => {
    fetchMock.mockRejectedValue(new DOMException("aborted", "AbortError"))
    await expect(api.documents.list()).rejects.toMatchObject({ name: "AbortError" })
  })

  it("signs out and returns to the current page after login on 401", async () => {
    fetchMock.mockResolvedValue(json(401, { detail: "Invalid or expired token" }))
    await expect(api.documents.list()).rejects.toMatchObject({ status: 401 })
    expect(auth.signOut).toHaveBeenCalledWith({ scope: "local" })
    expect(assign).toHaveBeenCalledWith("/login?next=%2Fdocuments%2F1%3Ftab%3Dchat")
  })

  it("redirects to login without calling the API when there is no session", async () => {
    auth.getSession.mockResolvedValue({ data: { session: null } })
    await expect(api.documents.list()).rejects.toMatchObject({ status: 401 })
    expect(fetchMock).not.toHaveBeenCalled()
    expect(assign).toHaveBeenCalled()
  })
})

describe("chat.stream", () => {
  const body = { document_id: "d1", message: "How high is the Enguri Dam?" }

  it("posts the question and emits the streamed events", async () => {
    fetchMock.mockResolvedValue(
      new Response('event: token\ndata: {"text": "271 m"}\n\nevent: done\ndata: {"message_id": 2, "sources": []}\n\n', {
        headers: { "Content-Type": "text/event-stream" },
      }),
    )
    const events: ChatEvent[] = []
    await api.chat.stream(body, (event) => events.push(event))
    expect(events.map((e) => e.event)).toEqual(["token", "done"])
    const init = fetchMock.mock.calls[0][1]
    expect(init?.method).toBe("POST")
    expect(JSON.parse(init?.body as string)).toEqual(body)
  })

  it("rejects errors returned before the stream starts", async () => {
    fetchMock.mockResolvedValue(json(409, { detail: "This document is still being processed." }))
    await expect(api.chat.stream(body, () => {})).rejects.toMatchObject({ status: 409 })
  })

  it("reports a connection dropped mid-answer", async () => {
    let reads = 0
    const broken = new ReadableStream<Uint8Array<ArrayBuffer>>({
      pull(controller) {
        if (reads++ === 0) controller.enqueue(new TextEncoder().encode('event: token\ndata: {"text": "partial"}\n\n'))
        else controller.error(new TypeError("network error"))
      },
    })
    fetchMock.mockResolvedValue(new Response(broken))
    const events: ChatEvent[] = []
    await expect(api.chat.stream(body, (e) => events.push(e))).rejects.toMatchObject({
      message: "The connection was interrupted.",
    })
    expect(events).toHaveLength(1)
  })
})
