import { AlertCircle, FileText, LibraryBig, RotateCcw } from "lucide-react"

import { Markdown } from "@/components/common/markdown"
import { Button } from "@/components/ui/button"
import type { Source } from "@/types"

/** Shown at the end of an answer while it streams in. */
const STREAMING_CARET = " ▍"

export type TurnStatus = "thinking" | "streaming" | "complete" | "interrupted" | "error"

export interface ChatTurnMessage {
  key: string
  role: "user" | "assistant"
  content: string
  sources: Source[] | null
  status: TurnStatus
  error?: string
}

export function UserMessage({ content, initial }: { content: string; initial: string }) {
  return (
    <div className="animate-in fade-in-0 duration-200">
      <Indicator label="You">
        <span className="flex size-6 items-center justify-center rounded-full bg-surface text-[11px] font-medium text-foreground ring-1 ring-border">
          {initial}
        </span>
      </Indicator>
      <p className="mt-2 pl-8 text-[15px] leading-relaxed font-medium whitespace-pre-wrap text-foreground">{content}</p>
    </div>
  )
}

export function AssistantMessage({ message, onRetry }: { message: ChatTurnMessage; onRetry?: () => void }) {
  const { status, content, sources } = message

  return (
    <div aria-live={status === "streaming" ? "polite" : undefined} aria-busy={status === "streaming" || status === "thinking"}>
      <Indicator label="Assistant">
        <span className="flex size-6 items-center justify-center rounded-md bg-primary text-primary-foreground shadow-button">
          <LibraryBig className="size-3.5" strokeWidth={1.75} aria-hidden />
        </span>
      </Indicator>

      <div className="mt-2 pl-8">
        {status === "thinking" ? (
          <Thinking />
        ) : (
          content && (
            <Markdown citations className="text-[15px] leading-[1.75]">
              {status === "streaming" ? `${content}${STREAMING_CARET}` : content}
            </Markdown>
          )
        )}

        {status === "interrupted" && (
          <p className="mt-3 text-[12px] text-text-muted">Answer interrupted. The text above is what was generated before it stopped.</p>
        )}

        {status === "error" && (
          <div role="alert" className="mt-3 flex flex-wrap items-center gap-3 rounded-lg border border-destructive/20 bg-destructive/3 px-3 py-2.5 text-[13px]">
            <AlertCircle className="size-4 shrink-0 text-destructive" strokeWidth={1.75} aria-hidden />
            <span className="min-w-0 flex-1 text-destructive">{message.error ?? "Something went wrong."}</span>
            {onRetry && (
              <Button variant="outline" size="sm" onClick={onRetry}>
                <RotateCcw aria-hidden />
                Retry
              </Button>
            )}
          </div>
        )}

        {status === "complete" && <Sources sources={sources ?? []} />}
      </div>
    </div>
  )
}

/** Pages the answer was taken from. Only pages that were actually retrieved. */
function Sources({ sources }: { sources: Source[] }) {
  if (sources.length === 0) return null
  return (
    <div className="mt-4 flex flex-wrap items-center gap-1.5 animate-in fade-in-0 duration-200">
      <span className="mr-1 text-[12px] font-medium text-text-muted">Sources</span>
      {sources.map((source) => (
        <span
          key={source.page}
          title={`Page ${source.page} · relevance ${Math.round(source.similarity * 100)}%`}
          className="inline-flex h-7 items-center gap-1.5 rounded-lg border border-border bg-background px-2.5 text-[12px] font-medium text-text-secondary shadow-xs transition-[border-color,color] duration-150 hover:border-border-strong hover:text-foreground"
        >
          <FileText className="size-3.5" strokeWidth={1.75} aria-hidden />
          Page {source.page}
        </span>
      ))}
    </div>
  )
}

function Thinking() {
  return (
    <p className="flex items-center gap-2 text-[14px] text-text-secondary" role="status">
      Thinking
      <span className="flex gap-1" aria-hidden>
        {[0, 150, 300].map((delay) => (
          <span key={delay} className="size-1 animate-pulse rounded-full bg-text-muted" style={{ animationDelay: `${delay}ms` }} />
        ))}
      </span>
    </p>
  )
}

function Indicator({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      {children}
      <span className="text-[12px] font-medium text-text-secondary">{label}</span>
    </div>
  )
}
