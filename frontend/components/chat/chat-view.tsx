"use client"

import { ArrowLeft, FileText, MessageSquarePlus, MoreHorizontal, Trash2 } from "lucide-react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { useCallback, useEffect, useRef, useState } from "react"
import { toast } from "sonner"

import { Composer } from "@/components/chat/composer"
import { AssistantMessage, UserMessage, type ChatTurnMessage } from "@/components/chat/messages"
import { useConversations } from "@/components/layout/conversations-provider"
import { useUserEmail } from "@/components/layout/app-shell"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Skeleton } from "@/components/ui/skeleton"
import { useStartChat } from "@/hooks/use-start-chat"
import { api, ApiError } from "@/lib/api"
import type { ConversationDetail, Document, Message } from "@/types"

/** The backend appends this to answers that were cut off (see services/chat.py). */
const INTERRUPTED_NOTE = "\n\n[Answer interrupted]"
/** Keep following the stream while the reader is within this distance of the bottom. */
const STICK_TO_BOTTOM_PX = 120

type Load =
  | { state: "loading" }
  | { state: "missing" }
  | { state: "error"; message: string }
  | { state: "ready"; conversation: ConversationDetail; document: Document }

let keySeed = 0
const newKey = () => `local-${++keySeed}`

function toTurn(message: Message): ChatTurnMessage {
  const interrupted = message.role === "assistant" && message.content.endsWith(INTERRUPTED_NOTE)
  return {
    key: `m-${message.id}`,
    role: message.role,
    content: interrupted ? message.content.slice(0, -INTERRUPTED_NOTE.length) : message.content,
    sources: message.sources,
    status: interrupted ? "interrupted" : "complete",
  }
}

export function ChatView({ conversationId, initialQuestion }: { conversationId: string; initialQuestion?: string }) {
  const router = useRouter()
  const pathname = usePathname()
  const email = useUserEmail()
  const { refresh } = useConversations()

  const [load, setLoad] = useState<Load>({ state: "loading" })
  const [messages, setMessages] = useState<ChatTurnMessage[]>([])
  const [input, setInput] = useState(initialQuestion ?? "")
  const controllerRef = useRef<AbortController | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const stickRef = useRef(true)

  const streaming = messages.some((m) => m.status === "thinking" || m.status === "streaming")

  // Load the conversation and its document.
  useEffect(() => {
    const controller = new AbortController()
    api.conversations
      .get(conversationId, controller.signal)
      .then(async (conversation) => {
        const document = await api.documents.get(conversation.document_id, controller.signal)
        setMessages(conversation.messages.map(toTurn))
        setLoad({ state: "ready", conversation, document })
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return
        if (error instanceof ApiError && (error.status === 404 || error.status === 422)) return setLoad({ state: "missing" })
        setLoad({ state: "error", message: error instanceof ApiError ? error.message : "Could not load this conversation." })
      })
    return () => controller.abort()
  }, [conversationId])

  // A question passed as ?q= is prefilled once; drop it from the URL so a reload does not repeat it.
  useEffect(() => {
    if (initialQuestion) router.replace(pathname, { scroll: false })
  }, [initialQuestion, pathname, router])

  // Stop a running answer when leaving the page.
  useEffect(() => () => controllerRef.current?.abort(), [])

  // Follow new text while the reader is at the bottom.
  useEffect(() => {
    const el = scrollRef.current
    if (el && stickRef.current) el.scrollTop = el.scrollHeight
  }, [messages])

  const send = useCallback(
    async (text?: string) => {
      const question = (text ?? input).trim()
      if (!question || streaming || load.state !== "ready") return

      const assistantKey = newKey()
      const update = (patch: (m: ChatTurnMessage) => Partial<ChatTurnMessage>) =>
        setMessages((all) => all.map((m) => (m.key === assistantKey ? { ...m, ...patch(m) } : m)))

      setMessages((all) => [
        ...all,
        { key: newKey(), role: "user", content: question, sources: null, status: "complete" },
        { key: assistantKey, role: "assistant", content: "", sources: null, status: "thinking" },
      ])
      setInput("")
      stickRef.current = true

      const controller = new AbortController()
      controllerRef.current = controller
      let received = ""
      let finished = false
      try {
        await api.chat.stream(
          { document_id: load.document.id, conversation_id: conversationId, message: question },
          (event) => {
            if (event.event === "token") {
              received += event.data.text
              update((m) => ({ content: m.content + event.data.text, status: "streaming" }))
            } else if (event.event === "done") {
              finished = true
              update(() => ({ status: "complete", sources: event.data.sources }))
            } else if (event.event === "error") {
              finished = true
              update(() => ({ status: "error", error: event.data.detail }))
            }
          },
          controller.signal,
        )
        if (!finished) update(() => ({ status: "interrupted" })) // stream closed without done/error
        void refresh() // conversation title and order in the sidebar
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          if (received) {
            update(() => ({ status: "interrupted" }))
            void refresh()
          } else {
            // Stopped before the first word: nothing was saved. Give the question back.
            setMessages((all) => all.slice(0, -2))
            setInput(question)
          }
        } else {
          const message = error instanceof ApiError ? error.message : "Could not get an answer. Please try again."
          update(() => ({ status: "error", error: message }))
          if (!received) toast.error("Could not get an answer", { description: message })
        }
      } finally {
        controllerRef.current = null
      }
    },
    [conversationId, input, load, refresh, streaming],
  )

  function retry(assistantKey: string) {
    const index = messages.findIndex((m) => m.key === assistantKey)
    const question = messages[index - 1]?.role === "user" ? messages[index - 1].content : null
    if (!question) return
    setMessages((all) => all.filter((_, i) => i !== index && i !== index - 1))
    void send(question)
  }

  if (load.state !== "ready") {
    return (
      <div className="flex h-[calc(100dvh-3.5rem)] flex-col lg:h-dvh">
        {load.state === "loading" ? (
          <ChatSkeleton />
        ) : (
          <div className="m-auto flex max-w-sm flex-col items-center px-6 text-center">
            <h1 className="text-[15px] font-medium">
              {load.state === "missing" ? "Conversation not found" : "Could not load this conversation"}
            </h1>
            <p className="mt-1.5 text-[14px] text-text-secondary">
              {load.state === "missing" ? "It may have been deleted, or it belongs to another account." : load.message}
            </p>
            <Button asChild variant="outline" className="mt-6">
              <Link href="/dashboard">Back to your documents</Link>
            </Button>
          </div>
        )}
      </div>
    )
  }

  const { document, conversation } = load
  const initial = (email ?? "?").charAt(0).toUpperCase()

  return (
    <div className="flex h-[calc(100dvh-3.5rem)] flex-col lg:h-dvh">
      <ChatHeader
        document={document}
        title={conversation.title ?? messages.find((m) => m.role === "user")?.content ?? "New conversation"}
        conversationId={conversationId}
        disabled={streaming}
        onDeleted={() => {
          void refresh()
          router.replace(`/documents/${document.id}`)
        }}
      />

      <div
        ref={scrollRef}
        onScroll={(e) => {
          const el = e.currentTarget
          stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < STICK_TO_BOTTOM_PX
        }}
        className="flex-1 overflow-y-auto"
      >
        <div className="mx-auto w-full max-w-3xl px-4 pt-8 pb-10 sm:px-6">
          {messages.length === 0 ? (
            <EmptyConversation document={document} onAsk={(q) => void send(q)} />
          ) : (
            <ol className="space-y-9">
              {messages.map((message) => (
                <li key={message.key}>
                  {message.role === "user" ? (
                    <UserMessage content={message.content} initial={initial} />
                  ) : (
                    <AssistantMessage message={message} onRetry={() => retry(message.key)} />
                  )}
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>

      <div className="border-t border-border bg-background/95 backdrop-blur-sm">
        <div className="mx-auto w-full max-w-3xl px-4 pt-3 pb-4 sm:px-6">
          <Composer
            value={input}
            onChange={setInput}
            onSend={() => void send()}
            onStop={() => controllerRef.current?.abort()}
            streaming={streaming}
            disabled={document.status !== "ready"}
          />
          <p className="mt-2 text-center text-[11px] text-text-muted">
            Answers come only from this document. Check important details on the cited pages.
          </p>
        </div>
      </div>
    </div>
  )
}

function ChatHeader({
  document,
  title,
  conversationId,
  disabled,
  onDeleted,
}: {
  document: Document
  title: string
  conversationId: string
  disabled: boolean
  onDeleted: () => void
}) {
  const { startChat } = useStartChat()
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)

  async function remove() {
    setDeleting(true)
    try {
      await api.conversations.delete(conversationId)
      setConfirmOpen(false)
      toast.success("Conversation deleted")
      onDeleted()
    } catch (error) {
      toast.error("Could not delete the conversation", {
        description: error instanceof ApiError ? error.message : "Please try again.",
      })
      setDeleting(false)
    }
  }

  return (
    <header className="flex items-center gap-3 border-b border-border px-4 py-3 sm:px-6">
      <div className="min-w-0 flex-1">
        <Link
          href={`/documents/${document.id}`}
          className="inline-flex max-w-full items-center gap-1.5 rounded-md text-[12px] text-text-secondary transition-colors duration-150 outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/40"
        >
          <ArrowLeft className="size-3.5 shrink-0" aria-hidden />
          <FileText className="size-3.5 shrink-0" strokeWidth={1.75} aria-hidden />
          <span className="truncate">{document.title}</span>
        </Link>
        <h1 className="mt-0.5 truncate text-[15px] font-semibold tracking-[-0.01em]">{title}</h1>
      </div>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon-sm" aria-label="Conversation actions">
            <MoreHorizontal aria-hidden />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={() => void startChat(document.id)}>
            <MessageSquarePlus aria-hidden />
            New chat about this document
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem destructive disabled={disabled} onSelect={() => setConfirmOpen(true)}>
            <Trash2 aria-hidden />
            Delete conversation
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <Dialog open={confirmOpen} onOpenChange={(open) => !deleting && setConfirmOpen(open)}>
        <DialogContent showClose={false}>
          <DialogTitle>Delete this conversation?</DialogTitle>
          <DialogDescription>All its messages will be permanently deleted. The document is kept.</DialogDescription>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmOpen(false)} disabled={deleting}>
              Cancel
            </Button>
            <Button onClick={remove} loading={deleting} className="bg-destructive hover:bg-destructive/90 active:bg-destructive">
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </header>
  )
}

function EmptyConversation({ document, onAsk }: { document: Document; onAsk: (question: string) => void }) {
  const suggestions = (document.questions ?? []).slice(0, 4)
  return (
    <div className="flex flex-col items-center pt-[8vh] text-center">
      <span className="flex size-11 items-center justify-center rounded-xl border border-border bg-canvas text-text-secondary shadow-xs">
        <FileText className="size-5" strokeWidth={1.5} aria-hidden />
      </span>
      <h2 className="mt-4 text-[20px] font-semibold tracking-[-0.015em]">Ask about “{document.title}”</h2>
      <p className="mt-1.5 max-w-md text-[14px] leading-relaxed text-text-secondary">
        Answers are based only on this document and show the pages they come from.
      </p>
      {suggestions.length > 0 && (
        <ul className="mt-8 grid w-full gap-2 text-left sm:grid-cols-2">
          {suggestions.map((question) => (
            <li key={question}>
              <button
                type="button"
                onClick={() => onAsk(question)}
                className="h-full w-full rounded-xl border border-border bg-background px-4 py-3 text-[13px] leading-snug text-text-secondary shadow-xs transition-[border-color,color,box-shadow] duration-200 hover:border-border-strong hover:text-foreground hover:shadow-card-hover focus-visible:ring-3 focus-visible:ring-ring/40 focus-visible:outline-none"
              >
                {question}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function ChatSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading conversation">
      <div className="border-b border-border px-6 py-3.5">
        <Skeleton className="h-3 w-40" />
        <Skeleton className="mt-2 h-4 w-64" />
      </div>
      <div className="mx-auto max-w-3xl space-y-8 px-6 pt-10">
        <Skeleton className="h-4 w-1/2" />
        <div className="space-y-2.5">
          <Skeleton className="h-3.5 w-full" />
          <Skeleton className="h-3.5 w-11/12" />
          <Skeleton className="h-3.5 w-4/5" />
        </div>
      </div>
    </div>
  )
}
