"use client"

import { Menu } from "lucide-react"
import Link from "next/link"
import { useState, type ReactNode } from "react"

import { Logo } from "@/components/common/logo"
import { ConversationsProvider } from "@/components/layout/conversations-provider"
import { Sidebar } from "@/components/layout/sidebar"
import { Dialog, DialogDescription, DialogTitle, SheetContent } from "@/components/ui/dialog"

/**
 * Signed-in layout: a fixed sidebar on desktop; on smaller screens a top bar
 * whose menu button opens the same sidebar as a drawer.
 */
export function AppShell({ email, children }: { email: string | null; children: ReactNode }) {
  const [drawerOpen, setDrawerOpen] = useState(false)

  return (
    <ConversationsProvider>
      <div className="flex min-h-full flex-1 bg-background">
        <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 border-r border-border bg-background lg:block">
          <Sidebar email={email} />
        </aside>

        <Dialog open={drawerOpen} onOpenChange={setDrawerOpen}>
          <SheetContent aria-describedby={undefined}>
            <DialogTitle className="sr-only">Navigation</DialogTitle>
            <DialogDescription className="sr-only">Pages, recent chats and your account</DialogDescription>
            <Sidebar email={email} onNavigate={() => setDrawerOpen(false)} />
          </SheetContent>
        </Dialog>

        <div className="flex min-w-0 flex-1 flex-col lg:pl-60">
          <header className="sticky top-0 z-20 flex h-14 items-center gap-2 border-b border-border bg-background/95 px-3 backdrop-blur-sm lg:hidden">
            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              aria-label="Open navigation"
              className="flex size-9 items-center justify-center rounded-lg text-text-secondary transition-colors duration-150 hover:bg-surface hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/40 focus-visible:outline-none"
            >
              <Menu className="size-5" strokeWidth={1.75} aria-hidden />
            </button>
            <Link href="/dashboard" className="rounded-md outline-none focus-visible:ring-3 focus-visible:ring-ring/40">
              <Logo />
            </Link>
          </header>
          <div className="flex flex-1 flex-col">{children}</div>
        </div>
      </div>
    </ConversationsProvider>
  )
}
