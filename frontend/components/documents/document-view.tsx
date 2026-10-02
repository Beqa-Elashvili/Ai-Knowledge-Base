"use client"

import {
  ArrowLeft,
  ArrowUpRight,
  FileText,
  Languages,
  Loader2,
  MessageSquare,
  MessagesSquare,
  MoreHorizontal,
  RefreshCw,
  Sparkles,
  Trash2,
} from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useEffect, useState, type ReactNode } from "react"
import { toast } from "sonner"

import { Markdown } from "@/components/common/markdown"
import { DeleteDocumentDialog } from "@/components/documents/document-card"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Skeleton } from "@/components/ui/skeleton"
import { useStartChat } from "@/hooks/use-start-chat"
import { api, ApiError } from "@/lib/api"
import { formatDate, formatRelative, pluralize } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { Conversation, Document } from "@/types"

const LANGUAGES = [
  { value: "", label: "Document's language" },
  { value: "English", label: "English" },
  { value: "Georgian", label: "Georgian" },
] as const

type Load = { state: "loading" } | { state: "missing" } | { state: "error"; message: string } | { state: "ready"; document: Document }

export function DocumentView({ id }: { id: string }) {
  const [load, setLoad] = useState<Load>({ state: "loading" })

  useEffect(() => {
    const controller = new AbortController()
    api.documents
      .get(id, controller.signal)
      .then((document) => setLoad({ state: "ready", document }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return
        if (error instanceof ApiError && (error.status === 404 || error.status === 422)) return setLoad({ state: "missing" })
        setLoad({ state: "error", message: error instanceof ApiError ? error.message : "Could not load this document." })
      })
    return () => controller.abort()
  }, [id])

  return (
    <main className="mx-auto w-full max-w-5xl px-4 pt-6 pb-20 sm:px-6 lg:px-10 lg:pt-10">
      <Link
        href="/documents"
        className="inline-flex items-center gap-1.5 rounded-md text-[13px] text-text-secondary transition-colors duration-150 outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/40"
      >
        <ArrowLeft className="size-3.5" aria-hidden />
        Documents
      </Link>

      {load.state === "loading" && <DocumentSkeleton />}
      {load.state === "missing" && (
        <Notice title="Document not found" body="It may have been deleted, or it belongs to another account." />
      )}
      {load.state === "error" && <Notice title="Could not load this document" body={load.message} />}
      {load.state === "ready" && (
        <DocumentDetails document={load.document} onChange={(document) => setLoad({ state: "ready", document })} />
      )}
    </main>
  )
}

function DocumentDetails({ document, onChange }: { document: Document; onChange: (document: Document) => void }) {
  const router = useRouter()
  const { startChat, startingId } = useStartChat()
  const [language, setLanguage] = useState("")
  const [summarizing, setSummarizing] = useState(false)
  const [generatingQuestions, setGeneratingQuestions] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const ready = document.status === "ready"

  async function generateSummary() {
    setSummarizing(true)
    try {
      onChange(await api.documents.summarize(document.id, language || undefined))
      toast.success("Summary generated")
    } catch (error) {
      toast.error("Could not generate the summary", { description: errorText(error) })
    } finally {
      setSummarizing(false)
    }
  }

  async function generateQuestions() {
    setGeneratingQuestions(true)
    try {
      onChange(await api.documents.generateQuestions(document.id, language || undefined))
      toast.success("Questions generated")
    } catch (error) {
      toast.error("Could not generate questions", { description: errorText(error) })
    } finally {
      setGeneratingQuestions(false)
    }
  }

  return (
    <>
      <header className="mt-6 flex flex-col gap-5 border-b border-border pb-7 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-start gap-4">
          <span className="flex size-12 shrink-0 items-center justify-center rounded-xl border border-border bg-canvas text-text-secondary shadow-xs">
            <FileText className="size-[22px]" strokeWidth={1.5} aria-hidden />
          </span>
          <div className="min-w-0">
            <h1 className="text-[26px] leading-tight font-semibold tracking-[-0.02em] break-words sm:text-[28px]">
              {document.title}
            </h1>
            <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] text-text-secondary">
              <span className="truncate">{document.filename}</span>
              {document.page_count != null && (
                <>
                  <Dot />
                  {pluralize(document.page_count, "page")}
                </>
              )}
              <Dot />
              Added {formatDate(document.created_at)}
              {!ready && (
                <span className="rounded-md border border-border px-1.5 py-px text-[11px] font-medium capitalize">
                  {document.status}
                </span>
              )}
            </p>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <Button
            onClick={() => void startChat(document.id)}
            disabled={!ready}
            loading={startingId === document.id}
          >
            {startingId !== document.id && <MessageSquare aria-hidden />}
            Chat
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="icon" aria-label="More actions">
                <MoreHorizontal aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem destructive onSelect={() => setConfirmDelete(true)}>
                <Trash2 aria-hidden />
                Delete document
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>

      <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="min-w-0 space-y-10">
          <Section
            title="Summary"
            action={
              ready && (
                <GenerateButton
                  busy={summarizing}
                  hasResult={Boolean(document.summary)}
                  onGenerate={generateSummary}
                  language={language}
                  onLanguage={setLanguage}
                  label="summary"
                />
              )
            }
          >
            {summarizing ? (
              <GeneratingPlaceholder lines={6} note="Reading the whole document. Long PDFs are summarized part by part and can take a minute." />
            ) : document.summary ? (
              <div className="rounded-[14px] border border-border bg-background p-5 shadow-card sm:p-6">
                <Markdown>{document.summary}</Markdown>
              </div>
            ) : (
              <EmptyPanel
                icon={<Sparkles className="size-4" strokeWidth={1.6} aria-hidden />}
                text="Get an overview of the whole document: what it is about, its key points and conclusion."
                action={
                  ready && (
                    <Button variant="outline" size="sm" onClick={generateSummary}>
                      Generate summary
                    </Button>
                  )
                }
              />
            )}
          </Section>

          <Section
            title="Suggested questions"
            action={
              ready && (
                <GenerateButton
                  busy={generatingQuestions}
                  hasResult={Boolean(document.questions?.length)}
                  onGenerate={generateQuestions}
                  language={language}
                  onLanguage={setLanguage}
                  label="questions"
                />
              )
            }
          >
            {generatingQuestions ? (
              <div className="grid gap-2.5 sm:grid-cols-2">
                {[0, 1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-[62px] rounded-xl" />
                ))}
              </div>
            ) : document.questions?.length ? (
              <ul className="grid gap-2.5 sm:grid-cols-2">
                {document.questions.map((question) => (
                  <li key={question}>
                    <button
                      type="button"
                      disabled={startingId !== null}
                      onClick={() => void startChat(document.id, question)}
                      className="group flex h-full w-full items-start justify-between gap-3 rounded-xl border border-border bg-background px-4 py-3.5 text-left text-[14px] leading-snug shadow-xs transition-[border-color,box-shadow,background-color] duration-200 hover:border-border-strong hover:shadow-card-hover focus-visible:ring-3 focus-visible:ring-ring/40 focus-visible:outline-none disabled:opacity-60"
                    >
                      <span>{question}</span>
                      <ArrowUpRight
                        className="mt-0.5 size-4 shrink-0 text-text-muted transition-[color,transform] duration-150 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-foreground"
                        aria-hidden
                      />
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyPanel
                icon={<MessagesSquare className="size-4" strokeWidth={1.6} aria-hidden />}
                text="Questions this document can answer. Click one to start a chat with it."
                action={
                  ready && (
                    <Button variant="outline" size="sm" onClick={generateQuestions}>
                      Generate questions
                    </Button>
                  )
                }
              />
            )}
          </Section>
        </div>

        <aside className="space-y-6">
          <DocumentConversations documentId={document.id} />
          <InfoCard document={document} />
        </aside>
      </div>

      <DeleteDocumentDialog
        document={document}
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        onDeleted={() => router.replace("/dashboard")}
      />
    </>
  )
}

function GenerateButton({
  busy,
  hasResult,
  onGenerate,
  language,
  onLanguage,
  label,
}: {
  busy: boolean
  hasResult: boolean
  onGenerate: () => void
  language: string
  onLanguage: (language: string) => void
  label: string
}) {
  const current = LANGUAGES.find((l) => l.value === language)?.label
  return (
    <div className="flex items-center">
      <Button variant="ghost" size="sm" onClick={onGenerate} disabled={busy} className="rounded-r-none">
        {busy ? <Loader2 className="animate-spin" aria-hidden /> : hasResult ? <RefreshCw aria-hidden /> : <Sparkles aria-hidden />}
        {busy ? "Generating…" : hasResult ? "Regenerate" : `Generate ${label}`}
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon-sm" disabled={busy} className="rounded-l-none" aria-label={`Language: ${current}`}>
            <Languages aria-hidden />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuLabel>Write the {label} in</DropdownMenuLabel>
          <DropdownMenuSeparator />
          {LANGUAGES.map((option) => (
            <DropdownMenuItem key={option.value} onSelect={() => onLanguage(option.value)}>
              <span className={cn("size-1.5 rounded-full", option.value === language ? "bg-foreground" : "bg-transparent")} aria-hidden />
              {option.label}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}

function DocumentConversations({ documentId }: { documentId: string }) {
  const [conversations, setConversations] = useState<Conversation[] | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    api.conversations
      .list(documentId, controller.signal)
      .then(setConversations)
      .catch(() => setConversations([]))
    return () => controller.abort()
  }, [documentId])

  return (
    <div className="rounded-[14px] border border-border bg-background p-4 shadow-card">
      <h2 className="px-1 text-[13px] font-medium">Conversations</h2>
      {conversations === null ? (
        <div className="mt-3 space-y-2.5 px-1">
          <Skeleton className="h-3.5 w-4/5" />
          <Skeleton className="h-3.5 w-3/5" />
        </div>
      ) : conversations.length === 0 ? (
        <p className="mt-2 px-1 text-[13px] leading-relaxed text-text-muted">No chats about this document yet.</p>
      ) : (
        <ul className="mt-2 space-y-0.5">
          {conversations.map((c) => (
            <li key={c.id}>
              <Link
                href={`/chat/${c.id}`}
                className="flex flex-col rounded-md px-1 py-1.5 transition-colors duration-150 outline-none hover:bg-surface focus-visible:ring-3 focus-visible:ring-ring/40"
              >
                <span className="truncate text-[13px]">{c.title ?? "New conversation"}</span>
                <span className="text-[12px] text-text-muted">{formatRelative(c.updated_at)}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function InfoCard({ document }: { document: Document }) {
  const rows: [string, ReactNode][] = [
    ["File", <span key="f" className="block truncate" title={document.filename}>{document.filename}</span>],
    ["Pages", document.page_count ?? "—"],
    ["Added", formatDate(document.created_at)],
    ["Status", <span key="s" className="capitalize">{document.status}</span>],
  ]
  return (
    <div className="rounded-[14px] border border-border bg-background p-4 shadow-card">
      <h2 className="px-1 text-[13px] font-medium">Document information</h2>
      <dl className="mt-2 divide-y divide-border">
        {rows.map(([label, value]) => (
          <div key={label} className="flex justify-between gap-4 px-1 py-2 text-[13px]">
            <dt className="text-text-muted">{label}</dt>
            <dd className="min-w-0 text-right text-text-secondary">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

function Section({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section aria-label={title}>
      <div className="mb-3 flex min-h-8 items-center justify-between gap-3">
        <h2 className="text-[18px] font-semibold tracking-[-0.01em]">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  )
}

function EmptyPanel({ icon, text, action }: { icon: ReactNode; text: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-3 rounded-[14px] border border-dashed border-border-strong bg-canvas p-5 sm:flex-row sm:items-center">
      <span className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-border bg-background text-text-secondary">
        {icon}
      </span>
      <p className="flex-1 text-[13px] leading-relaxed text-text-secondary">{text}</p>
      {action}
    </div>
  )
}

function GeneratingPlaceholder({ lines, note }: { lines: number; note: string }) {
  return (
    <div className="rounded-[14px] border border-border bg-background p-5 shadow-card sm:p-6" aria-busy="true">
      <div className="space-y-2.5">
        {Array.from({ length: lines }, (_, i) => (
          <Skeleton key={i} className="h-3.5" style={{ width: `${[96, 88, 92, 70, 84, 60][i % 6]}%` }} />
        ))}
      </div>
      <p className="mt-5 text-[12px] text-text-muted">{note}</p>
    </div>
  )
}

function DocumentSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading document">
      <div className="mt-6 flex items-start gap-4 border-b border-border pb-7">
        <Skeleton className="size-12 rounded-xl" />
        <div className="flex-1 space-y-2.5 pt-1">
          <Skeleton className="h-7 w-2/3" />
          <Skeleton className="h-3.5 w-1/3" />
        </div>
      </div>
      <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="space-y-3">
          <Skeleton className="h-5 w-28" />
          <Skeleton className="h-40 rounded-[14px]" />
        </div>
        <Skeleton className="h-36 rounded-[14px]" />
      </div>
    </div>
  )
}

function Notice({ title, body }: { title: string; body: string }) {
  return (
    <div className="mt-10 flex flex-col items-center rounded-2xl border border-border px-6 py-14 text-center">
      <span className="flex size-11 items-center justify-center rounded-xl border border-border bg-canvas text-text-secondary">
        <FileText className="size-5" strokeWidth={1.5} aria-hidden />
      </span>
      <h1 className="mt-4 text-[15px] font-medium">{title}</h1>
      <p className="mt-1.5 max-w-sm text-[14px] text-text-secondary">{body}</p>
      <Button asChild variant="outline" className="mt-6">
        <Link href="/dashboard">Back to your documents</Link>
      </Button>
    </div>
  )
}

function Dot() {
  return <span aria-hidden className="size-0.5 rounded-full bg-text-muted" />
}

function errorText(error: unknown): string {
  return error instanceof ApiError ? error.message : "Please try again."
}
