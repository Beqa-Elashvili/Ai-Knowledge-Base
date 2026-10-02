import type { Metadata } from "next"

import { DocumentView } from "@/components/documents/document-view"

export const metadata: Metadata = { title: "Document · AI Knowledge Base" }

export default async function DocumentPage({ params }: PageProps<"/documents/[id]">) {
  const { id } = await params
  // key: a fresh view (and data load) when navigating between documents
  return <DocumentView key={id} id={id} />
}
