import type { Metadata } from "next"

import { ChatView } from "@/components/chat/chat-view"

export const metadata: Metadata = { title: "New chat · AI Knowledge Base" }

/** A chat that is not saved yet: the first question creates the conversation. */
export default async function NewChatPage({ searchParams }: PageProps<"/chat/new">) {
  const { document, q } = await searchParams
  const documentId = typeof document === "string" ? document : undefined
  return (
    <ChatView
      key={documentId ?? "none"}
      conversationId={null}
      documentId={documentId}
      initialQuestion={typeof q === "string" ? q : undefined}
    />
  )
}
