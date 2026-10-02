"use client"

import { useRouter } from "next/navigation"
import { useCallback, useState } from "react"
import { toast } from "sonner"

import { useConversations } from "@/components/layout/conversations-provider"
import { api, ApiError } from "@/lib/api"

/** Create a conversation about a document and open it. */
export function useStartChat() {
  const router = useRouter()
  const { refresh } = useConversations()
  const [startingId, setStartingId] = useState<string | null>(null)

  const startChat = useCallback(
    async (documentId: string, question?: string) => {
      setStartingId(documentId)
      try {
        const conversation = await api.conversations.create(documentId)
        void refresh()
        const query = question ? `?q=${encodeURIComponent(question)}` : ""
        router.push(`/chat/${conversation.id}${query}`)
        return true
      } catch (error) {
        toast.error("Could not start a chat", {
          description: error instanceof ApiError ? error.message : "Please try again.",
        })
        return false
      } finally {
        setStartingId(null)
      }
    },
    [refresh, router],
  )

  return { startChat, startingId }
}
