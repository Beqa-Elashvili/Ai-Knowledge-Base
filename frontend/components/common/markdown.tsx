import ReactMarkdown, { type Components } from "react-markdown"

import { cn } from "@/lib/utils"

/**
 * Markdown from the AI model (summaries, answers), styled for reading.
 * react-markdown does not render raw HTML, so model output cannot inject
 * markup or scripts.
 */
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
  code: ({ children }) => <code className="rounded bg-surface px-1 py-0.5 font-mono text-[0.9em]">{children}</code>,
  blockquote: ({ children }) => <blockquote className="my-3 border-l-2 border-border pl-3 text-text-secondary">{children}</blockquote>,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer noopener" className="underline underline-offset-4">
      {children}
    </a>
  ),
}

export function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div className={cn("text-[14px] leading-[1.7] text-foreground/90 break-words", className)}>
      <ReactMarkdown components={components}>{children}</ReactMarkdown>
    </div>
  )
}
