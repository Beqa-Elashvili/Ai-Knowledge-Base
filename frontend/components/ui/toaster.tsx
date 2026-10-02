"use client"

import { CircleAlert, CircleCheck } from "lucide-react"
import { Toaster as Sonner } from "sonner"

/** Quiet, monochrome toasts at the bottom right. Use `toast` from "sonner". */
export function Toaster() {
  return (
    <Sonner
      position="bottom-right"
      gap={8}
      icons={{
        success: <CircleCheck className="size-4 text-success" strokeWidth={1.75} />,
        error: <CircleAlert className="size-4 text-destructive" strokeWidth={1.75} />,
      }}
      toastOptions={{
        unstyled: true,
        classNames: {
          toast:
            "flex w-full items-start gap-2.5 rounded-xl border border-border bg-background px-4 py-3 text-[13px] shadow-[0_4px_16px_rgba(0,0,0,0.06)] sm:w-[356px]",
          title: "font-medium text-foreground",
          description: "mt-0.5 text-text-secondary",
          icon: "mt-px",
          actionButton: "ml-auto shrink-0 rounded-md bg-primary px-2 py-1 text-[12px] font-medium text-primary-foreground",
        },
      }}
    />
  )
}
