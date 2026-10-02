import type { Metadata } from "next"

import { Dashboard } from "@/components/documents/dashboard"

export const metadata: Metadata = { title: "Dashboard · AI Knowledge Base" }

export default function DashboardPage() {
  return <Dashboard />
}
