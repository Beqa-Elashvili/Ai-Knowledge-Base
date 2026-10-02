"use client"

import { FileText, RotateCcw, Upload } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { DocumentCard, DocumentCardSkeleton } from "@/components/documents/document-card"
import { UploadZone } from "@/components/documents/upload-zone"
import { Button } from "@/components/ui/button"
import { api, ApiError } from "@/lib/api"
import { pluralize } from "@/lib/format"
import type { Document } from "@/types"

type Load = { state: "loading" } | { state: "error"; message: string } | { state: "ready"; documents: Document[] }

export function Dashboard() {
  const [load, setLoad] = useState<Load>({ state: "loading" })
  const [attempt, setAttempt] = useState(0)
  const uploadRef = useRef<HTMLDivElement>(null)

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

  const documents = load.state === "ready" ? load.documents : []

  function added(document: Document) {
    setLoad((current) => ({
      state: "ready",
      documents: [document, ...(current.state === "ready" ? current.documents.filter((d) => d.id !== document.id) : [])],
    }))
  }

  function removed(id: string) {
    setLoad((current) => (current.state === "ready" ? { ...current, documents: current.documents.filter((d) => d.id !== id) } : current))
  }

  function focusUpload() {
    uploadRef.current?.scrollIntoView({ behavior: "smooth", block: "center" })
    uploadRef.current?.querySelector<HTMLButtonElement>("button[data-browse]")?.click() // absent while uploading
  }

  return (
    <main className="mx-auto w-full max-w-6xl px-4 pt-8 pb-20 sm:px-6 lg:px-10 lg:pt-12">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[28px] leading-tight font-semibold tracking-[-0.02em]">Your documents</h1>
          <p className="mt-1.5 text-[14px] text-text-secondary">
            {load.state === "ready" && documents.length > 0
              ? `${pluralize(documents.length, "document")} in your knowledge base`
              : "Upload PDFs and ask questions about them, with page-level sources."}
          </p>
        </div>
        {documents.length > 0 && (
          <Button onClick={focusUpload}>
            <Upload aria-hidden />
            Upload
          </Button>
        )}
      </div>

      <div ref={uploadRef} className="mt-8">
        <UploadZone onUploaded={added} compact={documents.length > 0} />
      </div>

      <section aria-labelledby="documents-heading" className="mt-10">
        <h2 id="documents-heading" className="sr-only">
          Documents
        </h2>

        {load.state === "loading" && (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" aria-busy="true" aria-label="Loading documents">
            {[0, 1, 2].map((i) => (
              <DocumentCardSkeleton key={i} />
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
          <div className="flex flex-col items-center px-6 py-10 text-center">
            <span className="flex size-11 items-center justify-center rounded-xl border border-border bg-canvas text-text-secondary shadow-xs">
              <FileText className="size-5" strokeWidth={1.5} aria-hidden />
            </span>
            <h3 className="mt-4 text-[15px] font-medium">No documents yet</h3>
            <p className="mt-1.5 max-w-sm text-[14px] leading-relaxed text-text-secondary">
              Upload your first PDF and start chatting with your knowledge base.
            </p>
          </div>
        )}

        {load.state === "ready" && documents.length > 0 && (
          <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {documents.map((document) => (
              <li key={document.id} className="animate-in fade-in-0 duration-200">
                <DocumentCard document={document} onDeleted={removed} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  )
}
