import Link from "next/link"
import { redirect } from "next/navigation"

import { SignOutButton } from "@/components/auth/sign-out-button"
import { Logo } from "@/components/common/logo"
import { getSessionUser } from "@/lib/supabase/server"

/**
 * Shell for signed-in pages. proxy.ts already redirects signed-out visitors;
 * this server-side check is the authoritative one for rendering.
 */
export default async function AppLayout({ children }: LayoutProps<"/">) {
  const user = await getSessionUser()
  if (!user) redirect("/login")

  return (
    <div className="flex min-h-full flex-1 flex-col bg-background">
      <header className="border-b border-border">
        <div className="mx-auto flex h-14 w-full max-w-5xl items-center justify-between gap-4 px-4 sm:px-6">
          <Link href="/dashboard" className="rounded-md outline-none focus-visible:ring-3 focus-visible:ring-ring/40">
            <Logo />
          </Link>
          <div className="flex min-w-0 items-center gap-2">
            <span className="hidden truncate text-[13px] text-text-secondary sm:block">{user.email}</span>
            <SignOutButton />
          </div>
        </div>
      </header>
      <div className="flex flex-1 flex-col">{children}</div>
    </div>
  )
}
