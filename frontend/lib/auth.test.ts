import { describe, expect, it } from "vitest"

import { authErrorMessage, safeNextPath } from "@/lib/auth"

describe("safeNextPath", () => {
  it("keeps same-site paths with their query", () => {
    expect(safeNextPath("/chat/new?document=1&q=hi")).toBe("/chat/new?document=1&q=hi")
  })

  it.each([null, undefined, "", "dashboard", "https://evil.com", "//evil.com", "/\\evil.com"])(
    "rejects %j (open redirect) and falls back",
    (next) => {
      expect(safeNextPath(next)).toBe("/dashboard")
      expect(safeNextPath(next, "/documents")).toBe("/documents")
    },
  )
})

describe("authErrorMessage", () => {
  it("maps known Supabase codes to friendly messages", () => {
    expect(authErrorMessage("invalid_credentials", "x")).toBe("Incorrect email or password.")
    expect(authErrorMessage("email_exists", "x")).toMatch(/already exists/)
    expect(authErrorMessage("weak_password", "x")).toMatch(/at least 8/)
  })

  it("falls back for unknown or missing codes", () => {
    expect(authErrorMessage("something_new", "Sign-in failed.")).toBe("Sign-in failed.")
    expect(authErrorMessage(undefined, "Sign-in failed.")).toBe("Sign-in failed.")
  })
})
