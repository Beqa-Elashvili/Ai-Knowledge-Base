// Shared frontend types. They mirror the FastAPI response schemas
// (backend/app/schemas.py); keep the two in sync.

export interface HealthResponse {
  status: "ok"
}

/** The signed-in user, as verified by the backend (`GET /auth/me`). */
export interface User {
  id: string
  email: string | null
}

export type DocumentStatus = "processing" | "ready" | "failed"

/** An uploaded PDF. `storage_path` is internal and never sent to the browser. */
export interface Document {
  id: string
  title: string
  filename: string
  status: DocumentStatus
  page_count: number | null
  summary: string | null
  questions: string[] | null
  created_at: string
}

/** A retrieved excerpt of a document (vector search result). */
export interface DocumentChunk {
  chunk_index: number
  page_number: number
  page_end: number
  similarity: number
  content: string
}

export interface SearchResponse {
  document_id: string
  question: string
  results: DocumentChunk[]
}

/** A page an answer was taken from. Only pages that were actually retrieved. */
export interface Source {
  page: number
  similarity: number
}

export interface Conversation {
  id: string
  document_id: string
  title: string | null
  created_at: string
  updated_at: string
}

export type MessageRole = "user" | "assistant"

export interface Message {
  id: number
  role: MessageRole
  content: string
  sources: Source[] | null
  created_at: string
}

export interface ConversationDetail extends Conversation {
  messages: Message[]
}

/** Non-streaming answer (`POST /documents/{id}/ask`). */
export interface AskResponse {
  answer: string
  sources: Source[]
  model: string
}

/** Server-Sent Events of `POST /chat`. */
export type ChatEvent =
  | { event: "meta"; data: { conversation_id: string; user_message_id: number } }
  | { event: "token"; data: { text: string } }
  | { event: "done"; data: { message_id: number | null; sources: Source[] } }
  | { event: "error"; data: { detail: string; message_id: number | null } }

/** Error body returned by FastAPI (`{ detail }`; a list for validation errors). */
export interface ApiErrorBody {
  detail?: string | { msg: string }[]
}
