import type { Metadata } from "next"

import { ChatView } from "@/components/chat/chat-view"

export const metadata: Metadata = { title: "Chat · AI Knowledge Base" }

export default async function ChatPage({ params, searchParams }: PageProps<"/chat/[conversationId]">) {
  const { conversationId } = await params
  const { q } = await searchParams
  // key: a fresh view (and data load) when switching conversations
  return <ChatView key={conversationId} conversationId={conversationId} initialQuestion={typeof q === "string" ? q : undefined} />
}
