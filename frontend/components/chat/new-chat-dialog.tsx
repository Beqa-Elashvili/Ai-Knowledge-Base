"use client"

import { ChevronRight, FileText } from "lucide-react"
import Link from "next/link"
import { useEffect, useState, type ReactNode } from "react"

import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Skeleton } from "@/components/ui/skeleton"
import { useStartChat } from "@/hooks/use-start-chat"
import { api, ApiError } from "@/lib/api"
import { formatDate, pluralize } from "@/lib/format"
import type { Document } from "@/types"

/** "New chat": pick one of your ready documents, then open a conversation about it. */
export function NewChatDialog({ children, onStarted }: { children: ReactNode; onStarted?: () => void }) {
  const [open, setOpen] = useState(false)

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{children}</DialogTrigger>
      <DialogContent className="max-w-lg p-0">
        <div className="px-6 pt-6">
          <DialogTitle>New chat</DialogTitle>
          <DialogDescription>Choose the document you want to ask about.</DialogDescription>
        </div>
        {open && (
          <DocumentPicker
            onStarted={() => {
              setOpen(false)
              onStarted?.()
            }}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

function DocumentPicker({ onStarted }: { onStarted: () => void }) {
  const [documents, setDocuments] = useState<Document[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { startChat } = useStartChat()

  useEffect(() => {
    const controller = new AbortController()
    api.documents
      .list(controller.signal)
      .then((all) => setDocuments(all.filter((d) => d.status === "ready")))
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") return
        setError(err instanceof ApiError ? err.message : "Could not load your documents.")
      })
    return () => controller.abort()
  }, [])

  if (error) return <p className="px-6 pt-4 pb-6 text-[13px] text-destructive">{error}</p>

  if (!documents) {
    return (
      <div className="space-y-1 px-3 pt-4 pb-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="flex items-center gap-3 px-3 py-2.5">
            <Skeleton className="size-8 rounded-lg" />
            <div className="flex-1 space-y-1.5">
              <Skeleton className="h-3.5 w-2/3" />
              <Skeleton className="h-3 w-1/3" />
            </div>
          </div>
        ))}
      </div>
    )
  }

  if (documents.length === 0) {
    return (
      <div className="px-6 pt-4 pb-6">
        <p className="text-[14px] text-text-secondary">Upload a PDF first, then you can chat with it.</p>
        <Button asChild variant="outline" className="mt-4" onClick={onStarted}>
          <Link href="/dashboard">Go to documents</Link>
        </Button>
      </div>
    )
  }

  return (
    <ul className="max-h-[50vh] overflow-y-auto px-3 pt-4 pb-3">
      {documents.map((doc) => (
        <li key={doc.id}>
          <button
            type="button"
            onClick={() => {
              startChat(doc.id)
              onStarted()
            }}
            className="group flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors duration-150 hover:bg-surface focus-visible:bg-surface focus-visible:outline-none disabled:opacity-60"
          >
            <span className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-border bg-canvas text-text-secondary">
              <FileText className="size-4" strokeWidth={1.6} aria-hidden />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[14px] font-medium">{doc.title}</span>
              <span className="block text-[12px] text-text-muted">
                {doc.page_count ? `${pluralize(doc.page_count, "page")} · ` : ""}Added {formatDate(doc.created_at)}
              </span>
            </span>
            <ChevronRight
              className="size-4 text-text-muted transition-transform duration-150 group-hover:translate-x-0.5"
              aria-hidden
            />
          </button>
        </li>
      ))}
    </ul>
  )
}
