import { LibraryBig } from "lucide-react"

import { cn } from "@/lib/utils"

export function Logo({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <span className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground shadow-button">
        <LibraryBig className="size-4" strokeWidth={1.75} aria-hidden />
      </span>
      <span className="text-[14px] font-semibold tracking-[-0.01em]">AI Knowledge Base</span>
    </div>
  )
}
