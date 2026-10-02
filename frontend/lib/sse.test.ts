import { describe, expect, it } from "vitest"

import { parseEvent, readEvents } from "@/lib/sse"
import type { ChatEvent } from "@/types"

/** A response body that delivers `chunks` one network read at a time. */
function body(chunks: (string | Uint8Array<ArrayBuffer>)[]): ReadableStream<Uint8Array<ArrayBuffer>> {
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(typeof chunk === "string" ? encoder.encode(chunk) : chunk)
      controller.close()
    },
  })
}

async function collect(chunks: (string | Uint8Array<ArrayBuffer>)[]): Promise<ChatEvent[]> {
  const events: ChatEvent[] = []
  await readEvents(body(chunks), (event) => events.push(event))
  return events
}

const sse = (event: string, data: unknown) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`

describe("readEvents", () => {
  it("emits a full answer stream in order", async () => {
    const events = await collect([
      sse("meta", { conversation_id: "c1", user_message_id: 1 }) +
        sse("token", { text: "The dam is " }) +
        sse("token", { text: "271 m [p. 4]." }) +
        sse("done", { message_id: 2, sources: [{ page: 4 }] }),
    ])
    expect(events.map((e) => e.event)).toEqual(["meta", "token", "token", "done"])
    expect(events[2]).toEqual({ event: "token", data: { text: "271 m [p. 4]." } })
  })

  it("waits for events split across network chunks", async () => {
    const text = sse("token", { text: "split" })
    const events = await collect([text.slice(0, 9), text.slice(9, 20), text.slice(20, -1), text.slice(-1)])
    expect(events).toEqual([{ event: "token", data: { text: "split" } }])
  })

  it("keeps multi-byte characters intact when a chunk ends mid-character", async () => {
    const bytes = new TextEncoder().encode(sse("token", { text: "გამარჯობა" }))
    const cut = bytes.indexOf(0xe1) + 1 // inside the first Georgian letter
    const events = await collect([bytes.slice(0, cut), bytes.slice(cut)])
    expect(events).toEqual([{ event: "token", data: { text: "გამარჯობა" } }])
  })

  it("drops an incomplete trailing event", async () => {
    const events = await collect([sse("token", { text: "a" }) + 'event: token\ndata: {"text": "b"}'])
    expect(events).toHaveLength(1)
  })
})

describe("parseEvent", () => {
  it("joins multi-line data", () => {
    expect(parseEvent('event: error\ndata: {"detail":\ndata: "x", "message_id": null}')).toEqual({
      event: "error",
      data: { detail: "x", message_id: null },
    })
  })

  it.each([": keep-alive comment", "data: {}", "event: token", "event: token\ndata: not json"])("ignores %j", (block) => {
    expect(parseEvent(block)).toBeNull()
  })
})
