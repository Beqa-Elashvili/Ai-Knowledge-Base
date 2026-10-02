"use client"

import { FileText, MessageSquare, MoreHorizontal, RotateCcw, Search, Trash2, Upload } from "lucide-react"
import Link from "next/link"
import { useEffect, useMemo, useState } from "react"

import { DeleteDocumentDialog } from "@/components/documents/document-card"
import { UploadZone } from "@/components/documents/upload-zone"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { useStartChat } from "@/hooks/use-start-chat"
import { api, ApiError } from "@/lib/api"
import { formatDate, pluralize } from "@/lib/format"
import type { Document } from "@/types"

type Load = { state: "loading" } | { state: "error"; message: string } | { state: "ready"; documents: Document[] }

/** All documents as a compact, searchable list. */
export function DocumentsList() {
  const [load, setLoad] = useState<Load>({ state: "loading" })
  const [attempt, setAttempt] = useState(0)
  const [query, setQuery] = useState("")
  const [uploadOpen, setUploadOpen] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    api.documents
      .list(controller.signal)
      .then((documents) => setLoad({ state: "ready", documents }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return
        setLoad({ state: "error", message: error instanceof ApiError ? error.message : "Could not load your documents." })
      })
    return () => controller.abort()
  }, [attempt])

  const documents = useMemo(() => (load.state === "ready" ? load.documents : []), [load])
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return documents
    return documents.filter((d) => d.title.toLowerCase().includes(q) || d.filename.toLowerCase().includes(q))
  }, [documents, query])

  function added(document: Document) {
    setUploadOpen(false)
    setLoad((current) => ({
      state: "ready",
      documents: [document, ...(current.state === "ready" ? current.documents : [])],
    }))
  }

  function removed(id: string) {
    setLoad((current) => (current.state === "ready" ? { ...current, documents: current.documents.filter((d) => d.id !== id) } : current))
  }

  return (
    <main className="mx-auto w-full max-w-5xl px-4 pt-8 pb-20 sm:px-6 lg:px-10 lg:pt-12">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[28px] leading-tight font-semibold tracking-[-0.02em]">Documents</h1>
          <p className="mt-1.5 text-[14px] text-text-secondary">
            {load.state === "ready" ? pluralize(documents.length, "document") : "All your uploaded PDFs"}
          </p>
        </div>
        <Dialog open={uploadOpen} onOpenChange={setUploadOpen}>
          <DialogTrigger asChild>
            <Button>
              <Upload aria-hidden />
              Upload
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-lg">
            <DialogTitle>Upload a document</DialogTitle>
            <DialogDescription>It is processed right away so you can chat with it.</DialogDescription>
            <div className="mt-5">
              <UploadZone onUploaded={added} compact />
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {documents.length > 0 && (
        <div className="relative mt-8 max-w-sm">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-text-muted" aria-hidden />
          <Input
            type="search"
            placeholder="Search by title or file name"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="pl-9"
            aria-label="Search documents"
          />
        </div>
      )}

      <div className="mt-6">
        {load.state === "loading" && (
          <div className="overflow-hidden rounded-[14px] border border-border" aria-busy="true" aria-label="Loading documents">
            {[0, 1, 2].map((i) => (
              <div key={i} className="flex items-center gap-3 border-b border-border px-4 py-3.5 last:border-b-0">
                <Skeleton className="size-8 rounded-lg" />
                <div className="flex-1 space-y-1.5">
                  <Skeleton className="h-3.5 w-1/3" />
                  <Skeleton className="h-3 w-1/4" />
                </div>
              </div>
            ))}
          </div>
        )}

        {load.state === "error" && (
          <div role="alert" className="flex flex-col items-center rounded-2xl border border-border px-6 py-12 text-center">
            <p className="text-[14px] font-medium">Could not load your documents</p>
            <p className="mt-1 text-[13px] text-text-secondary">{load.message}</p>
            <Button
              variant="outline"
              className="mt-5"
              onClick={() => {
                setLoad({ state: "loading" })
                setAttempt((n) => n + 1)
              }}
            >
              <RotateCcw aria-hidden />
              Try again
            </Button>
          </div>
        )}

        {load.state === "ready" && documents.length === 0 && (
          <div className="flex flex-col items-center rounded-2xl border border-dashed border-border-strong bg-canvas px-6 py-14 text-center">
            <span className="flex size-11 items-center justify-center rounded-xl border border-border bg-background text-text-secondary shadow-xs">
              <FileText className="size-5" strokeWidth={1.5} aria-hidden />
            </span>
            <h2 className="mt-4 text-[15px] font-medium">No documents yet</h2>
            <p className="mt-1.5 max-w-sm text-[14px] text-text-secondary">
              Upload your first PDF and start chatting with your knowledge base.
            </p>
            <Button variant="outline" className="mt-6" onClick={() => setUploadOpen(true)}>
              <Upload aria-hidden />
              Upload document
            </Button>
          </div>
        )}

        {load.state === "ready" && documents.length > 0 && filtered.length === 0 && (
          <p className="rounded-[14px] border border-border px-4 py-8 text-center text-[14px] text-text-secondary">
            No documents match “{query.trim()}”.
          </p>
        )}

        {filtered.length > 0 && (
          <ul className="overflow-hidden rounded-[14px] border border-border bg-background shadow-card">
            {filtered.map((document) => (
              <DocumentRow key={document.id} document={document} onDeleted={removed} />
            ))}
          </ul>
        )}
      </div>
    </main>
  )
}

function DocumentRow({ document, onDeleted }: { document: Document; onDeleted: (id: string) => void }) {
  const { startChat, startingId } = useStartChat()
  const [confirmOpen, setConfirmOpen] = useState(false)
  const ready = document.status === "ready"

  return (
    <li className="group relative flex items-center gap-3 border-b border-border px-4 py-3 transition-colors duration-150 last:border-b-0 hover:bg-canvas">
      <span className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-border bg-background text-text-secondary">
        <FileText className="size-4" strokeWidth={1.6} aria-hidden />
      </span>
      <div className="min-w-0 flex-1">
        <Link
          href={`/documents/${document.id}`}
          className="block truncate text-[14px] font-medium outline-none after:absolute after:inset-0 focus-visible:after:ring-3 focus-visible:after:ring-ring/40 focus-visible:after:ring-inset"
        >
          {document.title}
        </Link>
        <p className="truncate text-[12px] text-text-muted">
          {document.filename}
          <span className="sm:hidden">{document.page_count ? ` · ${pluralize(document.page_count, "page")}` : ""}</span>
        </p>
      </div>
      <span className="hidden w-20 shrink-0 text-right text-[13px] text-text-secondary sm:block">
        {document.page_count ? pluralize(document.page_count, "page") : "—"}
      </span>
      <span className="hidden w-24 shrink-0 text-right text-[13px] text-text-secondary md:block">
        {ready ? formatDate(document.created_at) : <span className="capitalize">{document.status}</span>}
      </span>
      <div className="relative z-10 flex shrink-0 items-center gap-0.5">
        <Button
          variant="ghost"
          size="sm"
          disabled={!ready}
          loading={startingId === document.id}
          onClick={() => void startChat(document.id)}
          aria-label={`Chat with ${document.title}`}
        >
          {startingId !== document.id && <MessageSquare aria-hidden />}
          <span className="hidden sm:inline">Chat</span>
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon-sm" className="text-text-muted" aria-label="Document actions">
              <MoreHorizontal aria-hidden />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem destructive onSelect={() => setConfirmOpen(true)}>
              <Trash2 aria-hidden />
              Delete document
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <DeleteDocumentDialog document={document} open={confirmOpen} onOpenChange={setConfirmOpen} onDeleted={onDeleted} />
    </li>
  )
}
