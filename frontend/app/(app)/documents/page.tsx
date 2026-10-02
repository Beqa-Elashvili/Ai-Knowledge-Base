import type { Metadata } from "next"

import { DocumentsList } from "@/components/documents/documents-list"

export const metadata: Metadata = { title: "Documents · AI Knowledge Base" }

export default function DocumentsPage() {
  return <DocumentsList />
}
