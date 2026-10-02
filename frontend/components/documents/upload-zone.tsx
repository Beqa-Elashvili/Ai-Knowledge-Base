"use client"

import { FileText, FileUp, RotateCcw, X } from "lucide-react"
import { useRef, useState, type DragEvent } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { api, ApiError } from "@/lib/api"
import { formatBytes, pluralize } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { Document } from "@/types"

const MAX_MB = Number(process.env.NEXT_PUBLIC_MAX_UPLOAD_MB ?? 20)
const MAX_BYTES = MAX_MB * 1024 * 1024

type UploadState =
  | { phase: "idle" }
  | { phase: "uploading"; file: File; progress: number }
  | { phase: "processing"; file: File }
  | { phase: "error"; file: File; message: string }

/** Client-side checks mirroring the backend's, for instant feedback. */
function validate(file: File): string | null {
  const isPdf = file.name.toLowerCase().endsWith(".pdf") && (file.type === "" || file.type === "application/pdf")
  if (!isPdf) return "Only PDF files are supported."
  if (file.size === 0) return "This file is empty."
  if (file.size > MAX_BYTES) return `This file is ${formatBytes(file.size)}. The maximum is ${MAX_MB} MB.`
  return null
}

export function UploadZone({ onUploaded, compact = false }: { onUploaded: (document: Document) => void; compact?: boolean }) {
  const inputRef = useRef<HTMLInputElement>(null)
  const controllerRef = useRef<AbortController | null>(null)
  const dragDepth = useRef(0)
  const [dragging, setDragging] = useState(false)
  const [state, setState] = useState<UploadState>({ phase: "idle" })

  const busy = state.phase === "uploading" || state.phase === "processing"

  async function upload(file: File) {
    const problem = validate(file)
    if (problem) {
      setState({ phase: "error", file, message: problem })
      return
    }

    const controller = new AbortController()
    controllerRef.current = controller
    setState({ phase: "uploading", file, progress: 0 })
    try {
      const document = await api.documents.upload(file, {
        signal: controller.signal,
        onProgress: (progress) => setState((s) => (s.phase === "uploading" ? { ...s, progress } : s)),
        onProcessing: () => setState({ phase: "processing", file }),
      })
      setState({ phase: "idle" })
      onUploaded(document)
      toast.success("Document ready", {
        description: `${document.title}${document.page_count ? ` · ${pluralize(document.page_count, "page")}` : ""}`,
      })
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        setState({ phase: "idle" })
        return
      }
      const message = error instanceof ApiError ? error.message : "Upload failed. Please try again."
      setState({ phase: "error", file, message })
      toast.error("Upload failed", { description: message })
    } finally {
      controllerRef.current = null
    }
  }

  function pick(files: FileList | null) {
    const file = files?.[0]
    if (!file || busy) return
    if (files.length > 1) toast("One file at a time", { description: `Uploading ${file.name} only.` })
    void upload(file)
  }

  function onDragEnter(event: DragEvent) {
    event.preventDefault()
    if (busy) return
    dragDepth.current += 1
    setDragging(true)
  }

  function onDragLeave(event: DragEvent) {
    event.preventDefault()
    dragDepth.current = Math.max(0, dragDepth.current - 1)
    if (dragDepth.current === 0) setDragging(false)
  }

  function onDrop(event: DragEvent) {
    event.preventDefault()
    dragDepth.current = 0
    setDragging(false)
    pick(event.dataTransfer.files)
  }

  return (
    <div
      onDragEnter={onDragEnter}
      onDragOver={(e) => e.preventDefault()}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      className={cn(
        "rounded-2xl border border-dashed transition-colors duration-200",
        dragging ? "border-[#b9b9b6] bg-surface" : "border-border-strong bg-canvas",
        busy && "border-solid border-border bg-background",
      )}
    >
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        className="sr-only"
        tabIndex={-1}
        onChange={(e) => {
          pick(e.target.files)
          e.target.value = "" // allow choosing the same file again
        }}
      />

      {state.phase === "uploading" || state.phase === "processing" ? (
        <UploadProgress state={state} onCancel={() => controllerRef.current?.abort()} />
      ) : (
        <div className={cn("flex flex-col items-center px-6 text-center", compact ? "py-7" : "py-10 sm:py-12")}>
          <span className="flex size-10 items-center justify-center rounded-xl border border-border bg-background text-text-secondary shadow-xs">
            <FileUp className="size-[18px]" strokeWidth={1.6} aria-hidden />
          </span>
          <p className="mt-3.5 text-[14px] font-medium">{dragging ? "Release to upload" : "Drop your PDF here"}</p>
          <p className="mt-1 text-[13px] text-text-secondary">
            or{" "}
            <button
              type="button"
              data-browse
              onClick={() => inputRef.current?.click()}
              className="font-medium text-foreground underline underline-offset-4 decoration-border-strong transition-colors duration-150 hover:decoration-foreground focus-visible:rounded-sm focus-visible:ring-3 focus-visible:ring-ring/40 focus-visible:outline-none"
            >
              browse files
            </button>
          </p>
          <p className="mt-3 text-[12px] text-text-muted">PDF with selectable text, up to {MAX_MB} MB</p>

          {state.phase === "error" && (
            <div
              role="alert"
              className="mt-5 flex max-w-md items-center gap-3 rounded-lg border border-destructive/20 bg-background px-3 py-2 text-left text-[13px]"
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{state.file.name}</span>
                <span className="text-destructive">{state.message}</span>
              </span>
              {validate(state.file) === null && (
                <Button variant="outline" size="sm" onClick={() => void upload(state.file)}>
                  <RotateCcw aria-hidden />
                  Retry
                </Button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function UploadProgress({
  state,
  onCancel,
}: {
  state: Extract<UploadState, { phase: "uploading" | "processing" }>
  onCancel: () => void
}) {
  const uploading = state.phase === "uploading"
  const percent = uploading ? Math.round(state.progress * 100) : 100

  return (
    <div className="px-5 py-6 sm:px-6" aria-live="polite">
      <div className="flex items-center gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-xl border border-border bg-canvas text-text-secondary">
          <FileText className="size-[18px]" strokeWidth={1.6} aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[14px] font-medium">{state.file.name}</p>
          <p className="text-[12px] text-text-muted">{formatBytes(state.file.size)}</p>
        </div>
        {uploading && (
          <Button variant="ghost" size="icon-sm" onClick={onCancel} aria-label="Cancel upload">
            <X aria-hidden />
          </Button>
        )}
      </div>

      <div
        className="mt-4 h-1 overflow-hidden rounded-full bg-surface"
        role="progressbar"
        aria-label={uploading ? "Uploading" : "Processing"}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={uploading ? percent : undefined}
      >
        {uploading ? (
          <div className="h-full rounded-full bg-foreground transition-[width] duration-200 ease-out" style={{ width: `${percent}%` }} />
        ) : (
          <div className="h-full w-1/3 animate-[indeterminate_1.4s_ease-in-out_infinite] rounded-full bg-foreground" />
        )}
      </div>

      <ol className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[12px]">
        <Step done={!uploading} active={uploading}>
          {uploading ? `Uploading… ${percent}%` : "Uploaded"}
        </Step>
        <Step done={false} active={!uploading}>
          Extracting text and generating embeddings
        </Step>
      </ol>
      {!uploading && (
        <p className="mt-2 text-[12px] text-text-muted">Large PDFs can take a minute or two. You can keep this page open.</p>
      )}
    </div>
  )
}

function Step({ done, active, children }: { done: boolean; active: boolean; children: React.ReactNode }) {
  return (
    <li className={cn("flex items-center gap-1.5", active ? "text-foreground" : done ? "text-text-secondary" : "text-text-muted")}>
      <span
        aria-hidden
        className={cn(
          "size-1.5 rounded-full",
          done ? "bg-success" : active ? "animate-pulse bg-foreground" : "bg-border-strong",
        )}
      />
      {children}
    </li>
  )
}
