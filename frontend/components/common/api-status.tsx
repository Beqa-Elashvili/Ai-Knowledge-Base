"use client"

import { useEffect, useState } from "react"

import { api } from "@/lib/api"
import { cn } from "@/lib/utils"

type Status = "checking" | "online" | "offline"

const LABELS: Record<Status, string> = {
  checking: "Checking API",
  online: "API online",
  offline: "API offline",
}

/** Small live indicator backed by the FastAPI `/health` endpoint. */
export function ApiStatus({ className }: { className?: string }) {
  const [status, setStatus] = useState<Status>("checking")

  useEffect(() => {
    const controller = new AbortController()
    api
      .health(controller.signal)
      .then(() => setStatus("online"))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return
        setStatus("offline")
      })
    return () => controller.abort()
  }, [])

  return (
    <div
      role="status"
      className={cn(
        "inline-flex h-7 items-center gap-2 rounded-md border border-border bg-background px-2.5 text-[12px] text-text-secondary",
        className,
      )}
    >
      <span
        aria-hidden
        className={cn(
          "size-1.5 rounded-full transition-colors duration-200",
          status === "checking" && "animate-pulse bg-text-muted",
          status === "online" && "bg-success",
          status === "offline" && "bg-destructive",
        )}
      />
      {LABELS[status]}
    </div>
  )
}
