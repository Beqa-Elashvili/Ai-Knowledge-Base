"use client"

import { ArrowUp, Square } from "lucide-react"
import { useEffect, useRef, type KeyboardEvent } from "react"

import { cn } from "@/lib/utils"

export const MAX_QUESTION_CHARS = 2000

interface ComposerProps {
  value: string
  onChange: (value: string) => void
  onSend: () => void
  onStop: () => void
  streaming: boolean
  disabled?: boolean
  placeholder?: string
}

/** Question input: Enter sends, Shift+Enter adds a line; Stop while answering. */
export function Composer({ value, onChange, onSend, onStop, streaming, disabled, placeholder }: ComposerProps) {
  const ref = useRef<HTMLTextAreaElement>(null)
  const trimmed = value.trim()
  const tooLong = value.length > MAX_QUESTION_CHARS
  const canSend = Boolean(trimmed) && !tooLong && !streaming && !disabled

  // Grow with the text up to a limit, then scroll.
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }, [value])

  useEffect(() => {
    if (!streaming) ref.current?.focus()
  }, [streaming])

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      if (canSend) onSend()
    }
  }

  return (
    <div
      className={cn(
        "rounded-2xl border border-border bg-background shadow-card transition-[border-color,box-shadow] duration-150",
        "focus-within:border-[#c9c9c6] focus-within:shadow-card-hover",
        tooLong && "border-destructive/40",
      )}
    >
      <label htmlFor="question" className="sr-only">
        Ask a question about this document
      </label>
      <textarea
        id="question"
        ref={ref}
        rows={1}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder={placeholder ?? "Ask a question about this document…"}
        disabled={disabled}
        className="block max-h-[200px] w-full resize-none bg-transparent px-4 pt-3.5 pb-1 text-[15px] leading-relaxed outline-none placeholder:text-text-muted disabled:opacity-60"
      />
      <div className="flex items-center justify-between gap-3 px-3 pt-1 pb-2.5">
        <span className={cn("pl-1 text-[12px] text-text-muted", tooLong && "text-destructive")}>
          {value.length > MAX_QUESTION_CHARS * 0.8 ? `${value.length} / ${MAX_QUESTION_CHARS}` : "Shift + Enter for a new line"}
        </span>
        {streaming ? (
          <button
            type="button"
            onClick={onStop}
            aria-label="Stop generating"
            className="flex size-8 items-center justify-center rounded-lg border border-border bg-background text-foreground shadow-xs transition-colors duration-150 hover:bg-surface focus-visible:ring-3 focus-visible:ring-ring/40 focus-visible:outline-none"
          >
            <Square className="size-3 fill-current" aria-hidden />
          </button>
        ) : (
          <button
            type="button"
            onClick={onSend}
            disabled={!canSend}
            aria-label="Send question"
            className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-button transition-[background-color,opacity] duration-150 hover:bg-primary-hover focus-visible:ring-3 focus-visible:ring-ring/40 focus-visible:outline-none disabled:opacity-30"
          >
            <ArrowUp className="size-4" strokeWidth={2} aria-hidden />
          </button>
        )}
      </div>
    </div>
  )
}
