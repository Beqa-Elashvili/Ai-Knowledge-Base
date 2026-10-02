import { redirect } from "next/navigation"

import { AppShell } from "@/components/layout/app-shell"
import { getSessionUser } from "@/lib/supabase/server"

/**
 * Shell for signed-in pages. proxy.ts already redirects signed-out visitors;
 * this server-side check is the authoritative one for rendering.
 */
export default async function AppLayout({ children }: LayoutProps<"/">) {
  const user = await getSessionUser()
  if (!user) redirect("/login")

  return <AppShell email={user.email}>{children}</AppShell>
}
