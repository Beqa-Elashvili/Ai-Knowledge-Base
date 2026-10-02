"use client"

import { ChevronsUpDown, Files, LayoutGrid, LogOut, MessageSquare, SquarePen } from "lucide-react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { useState, type ComponentType, type SVGProps } from "react"

import { NewChatDialog } from "@/components/chat/new-chat-dialog"
import { Logo } from "@/components/common/logo"
import { useConversations } from "@/components/layout/conversations-provider"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Skeleton } from "@/components/ui/skeleton"
import { createClient } from "@/lib/supabase/client"
import { cn } from "@/lib/utils"

const NAV: { href: string; label: string; icon: ComponentType<SVGProps<SVGSVGElement>> }[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutGrid },
  { href: "/documents", label: "Documents", icon: Files },
]

const RECENT_LIMIT = 12

interface SidebarProps {
  email: string | null
  /** Called after navigating (closes the mobile drawer). */
  onNavigate?: () => void
}

export function Sidebar({ email, onNavigate }: SidebarProps) {
  const pathname = usePathname()

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-14 shrink-0 items-center px-4">
        <Link
          href="/dashboard"
          onClick={onNavigate}
          className="rounded-md outline-none focus-visible:ring-3 focus-visible:ring-ring/40"
        >
          <Logo />
        </Link>
      </div>

      <div className="px-3">
        <NewChatDialog onStarted={onNavigate}>
          <button
            type="button"
            className="flex h-9 w-full items-center gap-2 rounded-lg border border-border bg-background px-3 text-[13px] font-medium shadow-xs transition-colors duration-150 hover:border-border-strong hover:bg-canvas focus-visible:ring-3 focus-visible:ring-ring/40 focus-visible:outline-none"
          >
            <SquarePen className="size-4 text-text-secondary" strokeWidth={1.75} aria-hidden />
            New chat
          </button>
        </NewChatDialog>
      </div>

      <nav aria-label="Main" className="mt-4 space-y-0.5 px-3">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(`${href}/`)
          return (
            <Link
              key={href}
              href={href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex h-8 items-center gap-2.5 rounded-md px-2.5 text-[13px] transition-colors duration-150 outline-none focus-visible:ring-3 focus-visible:ring-ring/40",
                active ? "bg-surface font-medium text-foreground" : "text-text-secondary hover:bg-surface hover:text-foreground",
              )}
            >
              <Icon className="size-4" strokeWidth={1.75} aria-hidden />
              {label}
            </Link>
          )
        })}
      </nav>

      <RecentConversations pathname={pathname} onNavigate={onNavigate} />

      <div className="shrink-0 border-t border-border p-3">
        <UserMenu email={email} />
      </div>
    </div>
  )
}

function RecentConversations({ pathname, onNavigate }: { pathname: string; onNavigate?: () => void }) {
  const { conversations, loading } = useConversations()

  return (
    <div className="mt-6 flex min-h-0 flex-1 flex-col">
      <h2 className="px-5 pb-1.5 text-[11px] font-medium tracking-[0.04em] text-text-muted uppercase">Recent chats</h2>
      <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-3">
        {loading ? (
          <div className="space-y-2 px-2.5 pt-1.5">
            {[72, 56, 64].map((w) => (
              <Skeleton key={w} className="h-3.5" style={{ width: `${w}%` }} />
            ))}
          </div>
        ) : conversations.length === 0 ? (
          <p className="px-2.5 pt-1 text-[12px] leading-relaxed text-text-muted">
            Your conversations will appear here.
          </p>
        ) : (
          <ul className="space-y-0.5">
            {conversations.slice(0, RECENT_LIMIT).map((conversation) => {
              const href = `/chat/${conversation.id}`
              const active = pathname === href
              return (
                <li key={conversation.id}>
                  <Link
                    href={href}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    title={conversation.title ?? "New conversation"}
                    className={cn(
                      "flex h-8 items-center gap-2.5 rounded-md px-2.5 text-[13px] transition-colors duration-150 outline-none focus-visible:ring-3 focus-visible:ring-ring/40",
                      active ? "bg-surface text-foreground" : "text-text-secondary hover:bg-surface hover:text-foreground",
                    )}
                  >
                    <MessageSquare className="size-3.5 shrink-0" strokeWidth={1.75} aria-hidden />
                    <span className="truncate">{conversation.title ?? "New conversation"}</span>
                  </Link>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}

function UserMenu({ email }: { email: string | null }) {
  const router = useRouter()
  const [signingOut, setSigningOut] = useState(false)
  const initial = (email ?? "?").charAt(0).toUpperCase()

  async function signOut() {
    setSigningOut(true)
    await createClient().auth.signOut()
    router.replace("/login")
    router.refresh()
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left transition-colors duration-150 hover:bg-surface focus-visible:ring-3 focus-visible:ring-ring/40 focus-visible:outline-none aria-expanded:bg-surface"
        >
          <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-surface text-[12px] font-medium text-foreground ring-1 ring-border">
            {initial}
          </span>
          <span className="min-w-0 flex-1 truncate text-[13px]">{email}</span>
          <ChevronsUpDown className="size-3.5 shrink-0 text-text-muted" aria-hidden />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent side="top" align="start" className="w-[var(--radix-dropdown-menu-trigger-width)]">
        <DropdownMenuLabel className="truncate">{email}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={signOut} disabled={signingOut}>
          <LogOut aria-hidden />
          {signingOut ? "Signing out…" : "Sign out"}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
