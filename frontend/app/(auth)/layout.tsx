import Link from "next/link"

import { Logo } from "@/components/common/logo"

export default function AuthLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="flex min-h-full flex-1 flex-col bg-canvas">
      <header className="mx-auto flex h-16 w-full max-w-5xl items-center px-4 sm:px-6">
        <Link href="/" className="rounded-md outline-none focus-visible:ring-3 focus-visible:ring-ring/40" aria-label="Home">
          <Logo />
        </Link>
      </header>

      <main className="flex flex-1 items-start justify-center px-4 pt-[8vh] pb-16 sm:items-center sm:pt-0">
        <div className="w-full max-w-[400px] rounded-2xl border border-border bg-background p-6 shadow-card sm:p-8">
          {children}
        </div>
      </main>

      <footer className="pb-6 text-center text-[12px] text-text-muted">
        Your documents are private to your account.
      </footer>
    </div>
  )
}
