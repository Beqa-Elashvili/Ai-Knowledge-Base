import { describe, expect, it } from "vitest"

import { newChatHref } from "@/hooks/use-start-chat"

describe("newChatHref", () => {
  it("links to a new chat about the document", () => {
    expect(newChatHref("doc-1")).toBe("/chat/new?document=doc-1")
  })

  it("encodes a prefilled question", () => {
    const href = newChatHref("doc-1", "What is 5 & 6?")
    expect(href).toBe("/chat/new?document=doc-1&q=What+is+5+%26+6%3F")
    expect(new URL(href, "http://x").searchParams.get("q")).toBe("What is 5 & 6?")
  })
})
