// Shared frontend types. Domain types (Document, Conversation, Message,
// Source, ...) are added as the corresponding backend phases land.

export interface HealthResponse {
  status: "ok"
}

/** The signed-in user, as verified by the backend (`GET /auth/me`). */
export interface User {
  id: string
  email: string | null
}

/** Error body returned by FastAPI (`HTTPException` → `{ detail }`). */
export interface ApiErrorBody {
  detail?: string | { msg: string }[]
}
