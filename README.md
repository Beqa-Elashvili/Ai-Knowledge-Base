# AI Knowledge Base — My Personal ChatGPT

Upload your own PDFs and chat with them through a real Retrieval-Augmented Generation (RAG) pipeline, with page-level source citations.

> Work in progress. This project is being built in phases; the full README (architecture, RAG pipeline, schema, API reference) arrives in the final phase.

## Stack

| Layer    | Technology                                              |
| -------- | ------------------------------------------------------- |
| Frontend | Next.js (App Router), TypeScript, Tailwind CSS, shadcn/ui, Lucide |
| Backend  | Python 3.11, FastAPI, Pydantic, SQLAlchemy, PyMuPDF      |
| Data     | Supabase PostgreSQL + pgvector, Supabase Storage, Supabase Auth |
| AI       | Embeddings (1536-d): Google Gemini `gemini-embedding-2` (default, free tier) or OpenAI `text-embedding-3-small`; streaming chat model |

## Supabase setup

1. Create a project at https://supabase.com/dashboard.
2. Collect these values:

| Value | Where | Goes into |
| ----- | ----- | --------- |
| Project URL | Project Settings → Data API | `backend/.env` (`SUPABASE_URL`), `frontend/.env.local` (`NEXT_PUBLIC_SUPABASE_URL`) |
| Publishable / anon key | Project Settings → API Keys | `frontend/.env.local` (`NEXT_PUBLIC_SUPABASE_ANON_KEY`) |
| Secret / service_role key | Project Settings → API Keys | `backend/.env` only (`SUPABASE_SERVICE_KEY`) |
| Connection string | **Connect** → **Session pooler** | `backend/.env` only (`DATABASE_URL`) |

Use the **Session pooler** string: the direct connection is IPv6-only and fails on many networks. Replace the `postgresql://` prefix with `postgresql+psycopg://`. The backend tolerates special characters in the password, but a letters-and-digits password avoids URL escaping issues entirely.

3. Apply the database schema (pgvector, tables, vector search RPC, RLS) from `backend/` with the venv active:

```powershell
python -m scripts.migrate            # applies pending supabase/migrations/*.sql
python -m scripts.migrate --status   # shows applied / pending
python -m scripts.verify_schema      # end-to-end DB checks, always rolled back
python -m scripts.verify_storage     # upload/download/RLS checks on the documents bucket, cleans up after itself
```

   Alternatively, paste `supabase/migrations/0001_initial_schema.sql` into the Supabase SQL Editor.

4. Verify connectivity with the backend running: `GET http://127.0.0.1:8000/health/ready` should return `"status": "ok"` for both `database` and `supabase`.

## Local setup (Windows / PowerShell)

### Backend

```powershell
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

- API: http://127.0.0.1:8000
- Health: http://127.0.0.1:8000/health
- Readiness (DB + Supabase): http://127.0.0.1:8000/health/ready
- Swagger: http://127.0.0.1:8000/docs

Try authenticated endpoints in Swagger with a local test account (created with a pre-confirmed email):

```powershell
python -m scripts.dev_token --email you+dev@example.com --password "a-long-dev-password"
```

Open `/docs`, click **Authorize**, paste the printed token.

End-to-end check against real Supabase (creates and removes throwaway users):

```powershell
python -m scripts.verify_documents_api
```

Run tests:

```powershell
pytest
```

### Frontend

```powershell
cd frontend
npm install
copy .env.example .env.local
npm run dev
```

- App: http://localhost:3000

## Embeddings

Every chunk is embedded during upload, before anything is stored, so a failed embedding leaves no file or record behind; a successful upload is saved with status `ready`.

- Provider: `EMBEDDING_PROVIDER=gemini` (key from https://aistudio.google.com/apikey → `GEMINI_API_KEY`) or `openai` (`OPENAI_API_KEY`). `EMBEDDING_MODEL` overrides the provider's default model.
- Vectors are requested at 1536 dimensions and L2-normalized, matching `vector(1536)` and cosine search.
- Rate limits (429) and 5xx errors are retried with backoff, honouring the provider's retry delay. On the Gemini free tier, roughly 100 chunks per minute are embedded, so a 100-page PDF (~200 chunks) takes about 2 minutes to upload.
- Vectors from different providers/models are not comparable. After switching, re-embed stored chunks (from `backend/`):

```powershell
python -m scripts.reembed          # only chunks without an embedding
python -m scripts.reembed --all    # every chunk
```

## Vector search

`services/vector_search.py` embeds the question and calls the `match_document_chunks` SQL function (pgvector cosine distance on an HNSW index). Ownership is checked first and the function only reads rows of that one `document_id`, so a search never returns chunks from another document or another user. `SEARCH_TOP_K` (default 5, max 50) and `SEARCH_MIN_SIMILARITY` (default 0) are configurable.

## API (so far)

All endpoints except health require `Authorization: Bearer <Supabase access token>`.

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/health` | Liveness |
| GET | `/health/ready` | Database, pgvector and Storage connectivity |
| GET | `/auth/me` | Current user from the access token |
| POST | `/documents/upload` | Multipart `file` (PDF ≤ 20 MB, ≤ 2000 pages, with a text layer), optional `title` → 201 |
| GET | `/documents` | Current user's documents, newest first |
| GET | `/documents/{id}` | One document (404 if missing or not yours) |
| DELETE | `/documents/{id}` | Deletes record, chunks, conversations and the stored file → 204 |
| POST | `/documents/{id}/search` | `{"question": "...", "top_k": 5}` → chunks of that document most similar to the question, best first, with pages and similarity (retrieval only, no LLM) |

Errors are returned as `{"detail": "..."}` with 400 / 401 / 404 / 409 (document not ready for search) / 413 / 415 / 422 (also damaged, password-protected or scanned PDFs) / 502 / 500; internal details are never exposed.

## Project structure

```
backend/    FastAPI app (api/ routes, services/ business logic)
frontend/   Next.js app (app/ routes, components/, lib/api.ts client)
```
