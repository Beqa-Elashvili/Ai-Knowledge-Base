import * as React from "react"

import { cn } from "@/lib/utils"

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "h-10 w-full min-w-0 rounded-lg border border-border bg-background px-3 text-[14px] text-foreground shadow-xs outline-none",
        "transition-[border-color,box-shadow] duration-150 ease-out placeholder:text-text-muted",
        "hover:border-border-strong focus-visible:border-[#bdbdba] focus-visible:ring-3 focus-visible:ring-ring/25",
        "disabled:cursor-not-allowed disabled:bg-canvas disabled:opacity-60",
        "aria-invalid:border-destructive/60 aria-invalid:ring-3 aria-invalid:ring-destructive/10",
        className,
      )}
      {...props}
    />
  )
}

export { Input }
