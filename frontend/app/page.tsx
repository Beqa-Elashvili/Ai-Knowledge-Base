import { ArrowUpRight, FileText, FileUp, Quote, ScanSearch, Upload } from "lucide-react"

import { ApiStatus } from "@/components/common/api-status"
import { Logo } from "@/components/common/logo"
import { Button } from "@/components/ui/button"

const STEPS = [
  {
    icon: FileUp,
    title: "Upload your PDFs",
    body: "Books, lectures and notes are stored securely and split into page-aware chunks.",
  },
  {
    icon: ScanSearch,
    title: "Semantic retrieval",
    body: "Each question is embedded and matched against your document with pgvector.",
  },
  {
    icon: Quote,
    title: "Answers with sources",
    body: "Responses stream in, grounded only in your document, with the pages they came from.",
  },
] as const

export default function Home() {
  return (
    <div className="flex min-h-full flex-1 flex-col bg-background">
      <header className="border-b border-border">
        <div className="mx-auto flex h-14 w-full max-w-5xl items-center justify-between px-4 sm:px-6">
          <Logo />
          <ApiStatus />
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl flex-1 px-4 pt-14 pb-20 sm:px-6 sm:pt-20">
        <section className="max-w-2xl">
          <p className="text-[13px] font-medium text-text-secondary">Document intelligence</p>
          <h1 className="mt-3 text-[32px] leading-[1.15] font-semibold tracking-[-0.025em] sm:text-[36px]">
            AI Knowledge Base
          </h1>
          <p className="mt-3 text-[16px] leading-relaxed text-text-secondary">
            Chat with your documents using AI-powered retrieval.
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Button size="lg" type="button">
              <Upload aria-hidden />
              Upload document
            </Button>
            <span className="text-[13px] text-text-muted">PDF up to 20 MB</span>
          </div>
        </section>

        {/* Workspace preview — the real empty state of the dashboard */}
        <section aria-labelledby="workspace-title" className="mt-14 rounded-[18px] border border-border bg-canvas p-1.5 sm:mt-16">
          <div className="rounded-[14px] border border-border bg-background shadow-card">
            <div className="flex items-center justify-between border-b border-border px-5 py-3.5">
              <h2 id="workspace-title" className="text-[14px] font-medium">
                Your documents
              </h2>
              <span className="text-[12px] text-text-muted">0 documents</span>
            </div>

            <div className="flex flex-col items-center px-6 py-16 text-center sm:py-20">
              <span className="flex size-11 items-center justify-center rounded-xl border border-border bg-canvas text-text-secondary shadow-xs">
                <FileText className="size-5" strokeWidth={1.5} aria-hidden />
              </span>
              <h3 className="mt-4 text-[15px] font-medium">No documents yet</h3>
              <p className="mt-1.5 max-w-sm text-[14px] leading-relaxed text-text-secondary">
                Upload your first PDF and start chatting with your knowledge base.
              </p>
              <Button variant="outline" className="mt-6" type="button">
                <Upload aria-hidden />
                Upload document
              </Button>
            </div>
          </div>
        </section>

        <section aria-labelledby="how-title" className="mt-16">
          <h2 id="how-title" className="text-[13px] font-medium text-text-secondary">
            How it works
          </h2>
          <ol className="mt-4 grid gap-px overflow-hidden rounded-[14px] border border-border bg-border sm:grid-cols-3">
            {STEPS.map(({ icon: Icon, title, body }, i) => (
              <li key={title} className="bg-background p-5">
                <div className="flex items-center justify-between">
                  <Icon className="size-[18px] text-foreground" strokeWidth={1.6} aria-hidden />
                  <span className="font-mono text-[11px] text-text-muted">0{i + 1}</span>
                </div>
                <h3 className="mt-4 text-[14px] font-medium">{title}</h3>
                <p className="mt-1.5 text-[13px] leading-relaxed text-text-secondary">{body}</p>
              </li>
            ))}
          </ol>
        </section>
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto flex h-14 w-full max-w-5xl items-center justify-between px-4 text-[12px] text-text-muted sm:px-6">
          <span>Next.js · FastAPI · Supabase pgvector</span>
          <a
            href={`${process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"}/docs`}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 transition-colors duration-150 hover:text-foreground"
          >
            API docs
            <ArrowUpRight className="size-3.5" aria-hidden />
          </a>
        </div>
      </footer>
    </div>
  )
}
