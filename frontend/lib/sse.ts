import type { ChatEvent } from "@/types"

/**
 * Read a Server-Sent Events body and call `onEvent` for each complete event.
 * Network chunks may split an event (or a multi-byte character) anywhere;
 * events are only emitted once their terminating blank line has arrived.
 */
export async function readEvents(body: ReadableStream<BufferSource>, onEvent: (event: ChatEvent) => void): Promise<void> {
  const reader = body.pipeThrough(new TextDecoderStream()).getReader()
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
  } finally {
    reader.releaseLock()
  }
}

/** One `event:` / `data:` block, or null if it is incomplete or not JSON. */
export function parseEvent(block: string): ChatEvent | null {
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
