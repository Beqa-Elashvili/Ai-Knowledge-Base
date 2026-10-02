import type { Metadata } from "next"

import { BackendSession } from "@/components/auth/backend-session"

export const metadata: Metadata = { title: "Dashboard · AI Knowledge Base" }

// Placeholder until the dashboard phase: proves the signed-in session works
// end to end (browser → Next.js → FastAPI → Supabase Auth).
export default function DashboardPage() {
  return (
    <main className="mx-auto w-full max-w-5xl px-4 pt-12 pb-20 sm:px-6">
      <h1 className="text-[28px] leading-tight font-semibold tracking-[-0.02em]">Dashboard</h1>
      <p className="mt-2 text-[15px] text-text-secondary">Your documents will appear here.</p>
      <div className="mt-6">
        <BackendSession />
      </div>
    </main>
  )
}
