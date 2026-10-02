"use client"

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react"

import { api } from "@/lib/api"
import type { Conversation } from "@/types"

interface ConversationsState {
  conversations: Conversation[]
  loading: boolean
  /** Reload after creating or deleting a conversation (or a document). */
  refresh: () => Promise<void>
}

const ConversationsContext = createContext<ConversationsState | null>(null)

/** The signed-in user's conversations, shared by the sidebar and pages. */
export function ConversationsProvider({ children }: { children: ReactNode }) {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      setConversations(await api.conversations.list())
    } catch {
      // The sidebar list is secondary: keep the last known list on errors.
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    api.conversations
      .list(undefined, controller.signal)
      .then(setConversations)
      .catch(() => {})
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [])

  const value = useMemo(() => ({ conversations, loading, refresh }), [conversations, loading, refresh])
  return <ConversationsContext.Provider value={value}>{children}</ConversationsContext.Provider>
}

export function useConversations(): ConversationsState {
  const context = useContext(ConversationsContext)
  if (!context) throw new Error("useConversations must be used inside ConversationsProvider")
  return context
}
