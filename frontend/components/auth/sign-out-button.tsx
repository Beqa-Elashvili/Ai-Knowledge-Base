"use client"

import { LogOut } from "lucide-react"
import { useRouter } from "next/navigation"
import { useState } from "react"

import { Button } from "@/components/ui/button"
import { createClient } from "@/lib/supabase/client"

export function SignOutButton() {
  const router = useRouter()
  const [pending, setPending] = useState(false)

  async function signOut() {
    setPending(true)
    await createClient().auth.signOut()
    router.replace("/login")
    router.refresh()
  }

  return (
    <Button variant="ghost" size="sm" onClick={signOut} loading={pending}>
      {!pending && <LogOut aria-hidden />}
      Sign out
    </Button>
  )
}
