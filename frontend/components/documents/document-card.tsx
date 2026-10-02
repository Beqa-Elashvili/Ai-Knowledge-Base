"use client"

import { ArrowRight, FileText, MessageSquare, MoreHorizontal, Trash2 } from "lucide-react"
import Link from "next/link"
import { useState } from "react"
import { toast } from "sonner"

import { useConversations } from "@/components/layout/conversations-provider"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Skeleton } from "@/components/ui/skeleton"
import { useStartChat } from "@/hooks/use-start-chat"
import { api, ApiError } from "@/lib/api"
import { formatDate, pluralize, summaryPreview } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { Document } from "@/types"

const STATUS_LABEL = { processing: "Processing", failed: "Failed" } as const

export function DocumentCard({ document, onDeleted }: { document: Document; onDeleted: (id: string) => void }) {
  const [confirmOpen, setConfirmOpen] = useState(false)
  const { startChat, startingId } = useStartChat()
  const ready = document.status === "ready"
  const href = `/documents/${document.id}`

  return (
    <article className="group relative flex flex-col rounded-[14px] border border-border bg-background p-5 shadow-card transition-[border-color,box-shadow] duration-200 ease-out hover:border-border-strong hover:shadow-card-hover">
      <div className="flex items-start gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg border border-border bg-canvas text-text-secondary">
          <FileText className="size-[18px]" strokeWidth={1.6} aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="line-clamp-2 text-[15px] leading-snug font-medium break-words">
            {/* Whole-card link; the action buttons sit above it (z-10). */}
            <Link href={href} className="outline-none after:absolute after:inset-0 after:rounded-[14px] focus-visible:after:ring-3 focus-visible:after:ring-ring/40">
              {document.title}
            </Link>
          </h3>
          <p className="truncate text-[12px] text-text-muted">{document.filename}</p>
        </div>
        <DocumentMenu onDelete={() => setConfirmOpen(true)} />
      </div>

      <p
        className={cn(
          "mt-4 line-clamp-2 min-h-[2lh] text-[13px] leading-relaxed",
          document.summary ? "text-text-secondary" : "text-text-muted",
        )}
      >
        {document.summary ? summaryPreview(document.summary) : "No summary yet. Open the document to generate one."}
      </p>

      <div className="mt-4 flex items-center justify-between gap-3 border-t border-border pt-3.5">
        <p className="flex min-w-0 items-center gap-2 text-[12px] text-text-muted">
          {!ready && (
            <span
              className={cn(
                "rounded-md border px-1.5 py-px text-[11px] font-medium",
                document.status === "failed" ? "border-destructive/20 text-destructive" : "border-border text-text-secondary",
              )}
            >
              {STATUS_LABEL[document.status as keyof typeof STATUS_LABEL]}
            </span>
          )}
          <span className="truncate">
            {document.page_count ? `${pluralize(document.page_count, "page")} · ` : ""}Added {formatDate(document.created_at)}
          </span>
        </p>
        <div className="relative z-10 flex shrink-0 items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            disabled={!ready}
            loading={startingId === document.id}
            onClick={() => void startChat(document.id)}
          >
            {startingId !== document.id && <MessageSquare aria-hidden />}
            Chat
          </Button>
          <Button asChild variant="ghost" size="sm" className="text-foreground">
            <Link href={href}>
              Open
              <ArrowRight className="transition-transform duration-150 group-hover:translate-x-0.5" aria-hidden />
            </Link>
          </Button>
        </div>
      </div>

      <DeleteDocumentDialog document={document} open={confirmOpen} onOpenChange={setConfirmOpen} onDeleted={onDeleted} />
    </article>
  )
}

function DocumentMenu({ onDelete }: { onDelete: () => void }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" className="relative z-10 -mt-1 -mr-2 text-text-muted" aria-label="Document actions">
          <MoreHorizontal aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem destructive onSelect={onDelete}>
          <Trash2 aria-hidden />
          Delete document
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export function DeleteDocumentDialog({
  document,
  open,
  onOpenChange,
  onDeleted,
}: {
  document: Document
  open: boolean
  onOpenChange: (open: boolean) => void
  onDeleted: (id: string) => void
}) {
  const [deleting, setDeleting] = useState(false)
  const { refresh } = useConversations()

  async function remove() {
    setDeleting(true)
    try {
      await api.documents.delete(document.id)
      onOpenChange(false)
      onDeleted(document.id)
      void refresh() // its conversations were deleted with it
      toast.success("Document deleted", { description: document.title })
    } catch (error) {
      toast.error("Could not delete the document", {
        description: error instanceof ApiError ? error.message : "Please try again.",
      })
    } finally {
      setDeleting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !deleting && onOpenChange(next)}>
      <DialogContent showClose={false}>
        <DialogTitle>Delete this document?</DialogTitle>
        <DialogDescription>
          <span className="font-medium text-foreground">{document.title}</span>, its summary and all conversations about it
          will be permanently deleted.
        </DialogDescription>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={deleting}>
            Cancel
          </Button>
          <Button
            onClick={remove}
            loading={deleting}
            className="bg-destructive hover:bg-destructive/90 active:bg-destructive"
          >
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function DocumentCardSkeleton() {
  return (
    <div className="rounded-[14px] border border-border bg-background p-5 shadow-card">
      <div className="flex items-start gap-3">
        <Skeleton className="size-9 rounded-lg" />
        <div className="flex-1 space-y-2 pt-0.5">
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-3 w-1/2" />
        </div>
      </div>
      <div className="mt-5 space-y-2">
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-3 w-5/6" />
      </div>
      <div className="mt-5 flex items-center justify-between border-t border-border pt-3.5">
        <Skeleton className="h-3 w-28" />
        <Skeleton className="h-6 w-24" />
      </div>
    </div>
  )
}
