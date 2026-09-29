// Shared frontend types. Domain types (Document, Conversation, Message,
// Source, ...) are added as the corresponding backend phases land.

export interface HealthResponse {
  status: "ok"
}

/** Error body returned by FastAPI (`HTTPException` → `{ detail }`). */
export interface ApiErrorBody {
  detail?: string | { msg: string }[]
}
