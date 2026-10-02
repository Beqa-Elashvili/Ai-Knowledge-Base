"use client"

import { useRouter } from "next/navigation"
import { useCallback } from "react"

/** URL of a new, not yet saved chat about a document (optionally with a prefilled question). */
export function newChatHref(documentId: string, question?: string): string {
  const params = new URLSearchParams({ document: documentId })
  if (question) params.set("q", question)
  return `/chat/new?${params}`
}

/**
 * Open a new chat about a document. Nothing is created until the first
 * question is sent (POST /chat creates the conversation then), so opening
 * and leaving a chat leaves no empty conversations behind.
 */
export function useStartChat() {
  const router = useRouter()
  const startChat = useCallback(
    (documentId: string, question?: string) => router.push(newChatHref(documentId, question)),
    [router],
  )
  return { startChat }
}
