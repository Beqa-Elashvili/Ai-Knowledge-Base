import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { formatBytes, formatDate, formatRelative, pluralize, summaryPreview } from "@/lib/format"

describe("formatDate", () => {
  beforeEach(() => vi.useFakeTimers({ now: new Date("2026-06-15T12:00:00") }))
  afterEach(() => vi.useRealTimers())

  it("omits the year for dates in the current year", () => {
    expect(formatDate("2026-09-29T10:00:00")).toBe("Sep 29")
  })

  it("shows the year for other years", () => {
    expect(formatDate("2025-09-29T10:00:00")).toBe("Sep 29, 2025")
  })
})

describe("formatRelative", () => {
  const now = new Date("2026-06-15T12:00:00")
  beforeEach(() => vi.useFakeTimers({ now }))
  afterEach(() => vi.useRealTimers())
  const ago = (seconds: number) => new Date(now.getTime() - seconds * 1000).toISOString()

  it.each([
    [10, "Just now"],
    [5 * 60, "5 min ago"],
    [3 * 3600, "3 h ago"],
    [30 * 3600, "Yesterday"],
  ])("%i seconds ago -> %s", (seconds, expected) => {
    expect(formatRelative(ago(seconds))).toBe(expected)
  })

  it("falls back to a date after two days", () => {
    expect(formatRelative(ago(3 * 86400))).toBe("Jun 12")
  })
})

describe("formatBytes", () => {
  it.each([
    [512, "512 B"],
    [2048, "2 KB"],
    [5.5 * 1024 * 1024, "5.5 MB"],
  ])("%i -> %s", (bytes, expected) => {
    expect(formatBytes(bytes)).toBe(expected)
  })
})

describe("summaryPreview", () => {
  it("strips Markdown so the preview reads as plain text", () => {
    const markdown = "## Overview\n\nThe guide covers **Georgia**.\n\n**Key points:**\n- Enguri Dam\n- Rikoti tunnel"
    expect(summaryPreview(markdown)).toBe("Overview The guide covers Georgia. Enguri Dam Rikoti tunnel")
  })

  it("drops the section labels with or without a colon", () => {
    expect(summaryPreview("**Key points**\n- A\n\n**Conclusion**: B")).toBe("A B")
  })
})

describe("pluralize", () => {
  it("uses the singular only for one", () => {
    expect(pluralize(1, "page")).toBe("1 page")
    expect(pluralize(0, "page")).toBe("0 pages")
    expect(pluralize(3, "query", "queries")).toBe("3 queries")
  })
})
