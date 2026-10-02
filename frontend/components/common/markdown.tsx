import ReactMarkdown, { type Components } from "react-markdown"

import { cn } from "@/lib/utils"

/**
 * Markdown from the AI model (summaries, answers), styled for reading.
 * react-markdown does not render raw HTML, so model output cannot inject
 * markup or scripts.
 */

const CITATION_HREF = "#cite"
// [p. 14] [pp. 14-15] [p. 3, 7] — the format the RAG prompt asks for.
const CITATION = /\[(pp?\.\s*\d+(?:\s*[-–,;]\s*(?:p\.\s*)?\d+)*)\]/g

/** Turn page citations into links the renderer shows as small chips. */
function markCitations(text: string): string {
  return text.replace(CITATION, (_match, label: string) => `[${label.replace(/\s+/g, " ")}](${CITATION_HREF})`)
}

const components: Components = {
  p: ({ children }) => <p className="my-3 first:mt-0 last:mb-0">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  ul: ({ children }) => <ul className="my-3 list-disc space-y-1.5 pl-5 marker:text-text-muted">{children}</ul>,
  ol: ({ children }) => <ol className="my-3 list-decimal space-y-1.5 pl-5 marker:text-text-muted">{children}</ol>,
  li: ({ children }) => <li className="pl-1">{children}</li>,
  h1: ({ children }) => <h3 className="mt-5 mb-2 text-[16px] font-semibold first:mt-0">{children}</h3>,
  h2: ({ children }) => <h3 className="mt-5 mb-2 text-[15px] font-semibold first:mt-0">{children}</h3>,
  h3: ({ children }) => <h4 className="mt-4 mb-1.5 text-[14px] font-semibold first:mt-0">{children}</h4>,
  pre: ({ children }) => (
    <pre className="my-3 overflow-x-auto rounded-lg border border-border bg-canvas p-3.5 font-mono text-[12.5px] leading-relaxed [&>code]:bg-transparent [&>code]:p-0">
      {children}
    </pre>
  ),
  code: ({ children }) => <code className="rounded bg-surface px-1 py-0.5 font-mono text-[0.88em]">{children}</code>,
  blockquote: ({ children }) => <blockquote className="my-3 border-l-2 border-border pl-3 text-text-secondary">{children}</blockquote>,
  a: ({ children, href }) =>
    href === CITATION_HREF ? (
      <span className="mx-0.5 inline-flex h-[18px] items-center rounded-[5px] border border-border bg-canvas px-1.5 align-[1px] text-[11px] font-medium whitespace-nowrap text-text-secondary">
        {children}
      </span>
    ) : (
      <a href={href} target="_blank" rel="noreferrer noopener" className="underline underline-offset-4">
        {children}
      </a>
    ),
}

export function Markdown({
  children,
  className,
  citations = false,
}: {
  children: string
  className?: string
  /** Show [p. N] page citations as chips (chat answers). */
  citations?: boolean
}) {
  return (
    <div className={cn("text-[14px] leading-[1.7] text-foreground/90 break-words", className)}>
      <ReactMarkdown components={components}>{citations ? markCitations(children) : children}</ReactMarkdown>
    </div>
  )
}
