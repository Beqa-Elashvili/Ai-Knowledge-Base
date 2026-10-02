# AI Knowledge Base — My Personal ChatGPT

Upload your own PDFs and chat with them. Answers come only from your document, through a real Retrieval-Augmented Generation (RAG) pipeline, and every answer cites the pages it is based on.

## Contents

- [Project overview](#project-overview)
- [Features](#features)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [RAG pipeline](#rag-pipeline)
- [Database schema](#database-schema)
- [Environment variables](#environment-variables)
- [Local setup](#local-setup)
- [Supabase setup](#supabase-setup)
- [Running the backend](#running-the-backend)
- [Running the frontend](#running-the-frontend)
- [Testing](#testing)
- [API endpoints](#api-endpoints)
- [Example RAG flow](#example-rag-flow)
- [Security](#security)
- [Deployment](#deployment)
- [Future improvements](#future-improvements)

## Project overview

A personal knowledge base for books, lecture notes and reports:

1. You upload a PDF. The backend extracts its text page by page, splits it into page-aware chunks, embeds every chunk and stores the vectors in PostgreSQL (pgvector).
2. You ask a question. The question is embedded, the most similar chunks **of that document** are retrieved, and an LLM answers **only** from those excerpts.
3. The answer streams in token by token, with sources such as `p. 14`. If the document does not contain the answer, the assistant says so instead of guessing.

Conversations are saved per document, and each document can get an AI summary and suggested questions.

## Features

- **Accounts:** email + password with email confirmation (Supabase Auth). Every user sees only their own data.
- **PDF upload:** drag and drop with progress. Validation of type, size (≤ 20 MB), page count (≤ 2000) and text layer (scanned PDFs are rejected with a clear message).
- **Semantic search:** 1536-dimensional embeddings, cosine similarity on an HNSW index, always scoped to one document.
- **Chat with your PDF:**
  - Answers stream over Server-Sent Events.
  - Answers cite exact pages, even when an excerpt spans two pages.
  - Conversation memory handles follow-up questions ("and who built it?").
  - Stop button: a stopped answer is kept as "[Answer interrupted]".
- **Conversation history:** listed per document and in the sidebar. A chat is only created when its first question is sent.
- **Summaries:** overview, key points and conclusion. Long documents are map-reduced, so the summary covers the whole document.
- **Suggested questions:** six questions specific to the document, one click to ask.
- **Interface:** neutral, minimal UI (Next.js + Tailwind + shadcn/ui). Responsive, keyboard accessible, with skeleton loading states and toasts.

## Architecture

```
 Browser (Next.js, React)
   │  Supabase Auth session (cookies) ── anon key only
   │  Authorization: Bearer <access token>
   ▼
 FastAPI backend ───────────────► Gemini API
   │  verifies the token             embeddings (gemini-embedding-2, 1536-d)
   │  scopes every query to the user chat (gemini-3.5-flash-lite)
   ▼
 Supabase
   ├─ PostgreSQL + pgvector   documents, document_chunks, conversations, messages
   ├─ Storage (private)       original PDFs: <user_id>/<document_id>.pdf
   └─ Auth                    users, JWTs
```

- **The frontend never talks to the database or the AI provider.** It uses Supabase only for sign-in. All data goes through the FastAPI backend via `frontend/lib/api.ts`.
- **The backend holds every secret:** service key, database URL and API keys. It verifies the user's JWT on each request and filters every query by `user_id`. Row Level Security on all tables is a second line of defence.

```
backend/
  app/
    api/           HTTP routes (thin): documents, chat, conversations, auth, health
    services/      business logic: pdf, chunking, embeddings, vector_search,
                   rag, chat, conversations, summaries, questions, storage, …
    config.py      settings from environment variables
    main.py        app, middleware, routers
  scripts/         migrate, verify_*, dev_token, reembed, e2e_helper
  tests/           pytest (no real services needed)
frontend/
  app/             routes: / (landing), /login, /register, /auth/callback,
                   /dashboard, /documents, /documents/[id], /chat/new, /chat/[id]
  components/      ui/ (shadcn), layout/, documents/, chat/, auth/, common/
  lib/             api.ts (backend client), sse.ts, supabase/, format.ts
  proxy.ts         session refresh + redirects for signed-out visitors
  e2e/             full end-to-end browser test
supabase/
  migrations/      SQL: schema, pgvector, RPC, RLS, storage bucket
```

## Tech stack

| Layer | Technology |
| --- | --- |
| Frontend | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS v4, shadcn/ui (Radix), Lucide, Sonner, react-markdown |
| Backend | Python 3.12, FastAPI, Pydantic, SQLAlchemy 2, psycopg 3, PyMuPDF, httpx |
| Data | Supabase PostgreSQL + pgvector (HNSW), Supabase Storage, Supabase Auth |
| AI | Google Gemini (free tier works): `gemini-embedding-2` at 1536 dimensions, `gemini-3.5-flash-lite` for answers. OpenAI `text-embedding-3-small` is supported as an alternative embedding provider. |
| Tests | pytest, Vitest, Playwright (E2E) |

## RAG pipeline

### Ingestion (on upload)

```
PDF ─► validate (type, size, pages, text layer)
    ─► extract text per page (PyMuPDF), clean whitespace
    ─► chunk: ~1600 characters, 200 overlap, split on paragraph/sentence
       boundaries; each chunk keeps page_number, page_end and page_breaks
       (where each later page begins inside the chunk)
    ─► embed all chunks (batches of 100, retries on 429/5xx, L2-normalized)
    ─► store PDF in Storage, document + chunks in Postgres → status "ready"
```

Embedding happens **before** anything is stored, so a failed upload leaves nothing behind.

### Answering (per question)

```
question ─► (follow-up?) rewrite into a standalone search query using the
            last 6 messages
         ─► embed query ─► match_document_chunks(document_id, top 5)
         ─► context: excerpts in reading order, labelled [Excerpt 2 | p. 14],
            with [Page 15 begins here] markers, ≤ 12,000 characters
         ─► Gemini: system prompt = answer only from the excerpts, cite pages
            as [p. N], say so if the answer is not there
         ─► stream tokens to the browser (SSE)
         ─► sources = pages the answer cites AND a retrieved excerpt covers
         ─► save question, answer and sources to the conversation
```

The sources are never taken from the model alone, so a hallucinated page number cannot appear as a source.

### Summaries and suggested questions

- **Summaries** never send a whole PDF to the model. Chunks are grouped into sections of up to 60,000 characters. A short document is summarized in one call; a long one is map-reduced (section notes → condensed notes → final summary).
- **Suggested questions** use the summary plus excerpts sampled evenly from the first to the last page. They come from Gemini in JSON mode, in the document's language.

## Database schema

All tables live in `public`. Migrations are in `supabase/migrations/`.

```
documents
  id uuid PK, user_id uuid → auth.users (cascade), title, filename,
  storage_path, summary, page_count, status ('processing'|'ready'|'failed'),
  questions jsonb, created_at

document_chunks
  id uuid PK, document_id uuid → documents (cascade), content,
  page_number, page_end, page_breaks jsonb, chunk_index,
  embedding vector(1536), created_at
  unique (document_id, chunk_index); HNSW index (vector_cosine_ops)

conversations
  id uuid PK, user_id uuid → auth.users (cascade),
  document_id uuid → documents (cascade), title, created_at,
  updated_at (bumped by a trigger on every new message)

messages
  id bigint PK, conversation_id uuid → conversations (cascade),
  role ('user'|'assistant'), content, sources jsonb, created_at
```

- `match_document_chunks(query_embedding, match_document_id, match_count, min_similarity)` returns the most similar chunks of one document, using HNSW with `iterative_scan`, so the document filter never starves the results.
- Row Level Security on every table limits users to their own rows. The `documents` Storage bucket is private and limited to 20 MB PDFs, and each user can only access their own folder.
- Deleting a document removes its chunks, conversations, messages and stored file.

## Environment variables

### `backend/.env` (copy from `backend/.env.example`)

| Variable | Required | Description |
| --- | --- | --- |
| `SUPABASE_URL` | yes | `https://<ref>.supabase.co` |
| `SUPABASE_SERVICE_KEY` | yes | service_role / secret key. **Backend only.** |
| `DATABASE_URL` | yes | Session pooler connection string with the `postgresql+psycopg://` prefix |
| `GEMINI_API_KEY` | yes (default provider) | https://aistudio.google.com/apikey |
| `OPENAI_API_KEY` | only with `EMBEDDING_PROVIDER=openai` | |
| `ENVIRONMENT` | no | `development` (default) or `production` (hides `/docs`) |
| `CORS_ORIGINS` | no | JSON list of frontend URLs, default `["http://localhost:3000"]` |
| `EMBEDDING_PROVIDER` / `EMBEDDING_MODEL` | no | `gemini` (default) or `openai`. An empty model means the provider default. |
| `LLM_MODEL`, `LLM_TEMPERATURE`, `LLM_MAX_OUTPUT_TOKENS`, `LLM_THINKING_LEVEL` | no | Chat model settings |
| `SEARCH_TOP_K`, `SEARCH_MIN_SIMILARITY` | no | Retrieval: 5 chunks, no similarity floor |
| `CHUNK_SIZE`, `CHUNK_OVERLAP` | no | 1600 / 200 characters |
| `RAG_MAX_CONTEXT_CHARS` | no | Excerpt budget per question (12,000) |
| `CHAT_HISTORY_MESSAGES`, `CHAT_HISTORY_MESSAGE_CHARS` | no | Conversation memory (6 messages, 2,000 characters each) |
| `SUMMARY_SECTION_CHARS`, `QUESTIONS_COUNT`, `QUESTIONS_SOURCE_CHARS` | no | Summary and suggested-question settings |
| `STORAGE_BUCKET`, `MAX_UPLOAD_SIZE_MB`, `MAX_PDF_PAGES`, `SIGNED_URL_EXPIRES_SECONDS` | no | Upload limits |

### `frontend/.env.local` (copy from `frontend/.env.example`)

| Variable | Description |
| --- | --- |
| `NEXT_PUBLIC_API_URL` | Backend URL, e.g. `http://127.0.0.1:8000` |
| `NEXT_PUBLIC_SUPABASE_URL` | Same project URL as the backend |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Publishable / anon key, which is safe in the browser |
| `NEXT_PUBLIC_MAX_UPLOAD_MB` | Must match the backend's `MAX_UPLOAD_SIZE_MB` |

Only `NEXT_PUBLIC_*` values reach the browser. Never put the service key or AI keys in the frontend. Neither `.env` file is committed.

## Local setup

Requirements: Python 3.12, Node.js ≥ 20.9, a Supabase project (free plan is fine) and a Gemini API key.

```powershell
git clone https://github.com/Beqa-Elashvili/Ai-Knowledge-Base.git
cd Ai-Knowledge-Base
```

1. [Supabase setup](#supabase-setup): create the project and apply the migrations.
2. [Running the backend](#running-the-backend).
3. [Running the frontend](#running-the-frontend).
4. Open http://localhost:3000, create an account, confirm the email and upload a PDF.

Commands are shown for Windows PowerShell. On macOS/Linux, use `source venv/bin/activate` and `cp` instead of `copy`.

## Supabase setup

1. Create a project at https://supabase.com/dashboard.
2. Collect these values:

| Value | Where | Goes into |
| --- | --- | --- |
| Project URL | Project Settings → Data API | `SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_URL` |
| Publishable / anon key | Project Settings → API Keys | `NEXT_PUBLIC_SUPABASE_ANON_KEY` |
| Secret / service_role key | Project Settings → API Keys | `SUPABASE_SERVICE_KEY` (backend only) |
| Connection string | **Connect** → **Session pooler** | `DATABASE_URL` (backend only) |

   Use the **Session pooler** string, because the direct connection is IPv6-only and fails on many networks. Replace `postgresql://` with `postgresql+psycopg://`.

3. Apply the schema (pgvector, tables, vector search function, RLS, storage bucket). Run this from `backend/` with the venv active, after [installing the backend](#running-the-backend):

   ```powershell
   python -m scripts.migrate            # applies pending supabase/migrations/*.sql
   python -m scripts.migrate --status   # shows applied / pending
   python -m scripts.verify_schema      # DB checks inside a transaction that is rolled back
   python -m scripts.verify_storage     # bucket upload/download/RLS checks, cleans up
   ```

   Alternatively, run the files in `supabase/migrations/` in order in the Supabase SQL Editor.

4. **Authentication → URL Configuration:** set **Site URL** to `http://localhost:3000` and add `http://localhost:3000/auth/callback` to **Redirect URLs**, because the confirmation email links there. On the free plan, Supabase sends only a few auth emails per hour.

## Running the backend

```powershell
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements-dev.txt     # runtime + pytest; production uses requirements.txt
copy .env.example .env                  # then fill in the values
uvicorn app.main:app --reload
```

- API: http://127.0.0.1:8000
- Liveness: http://127.0.0.1:8000/health
- Readiness (database, pgvector, Storage): http://127.0.0.1:8000/health/ready
- Swagger (development only): http://127.0.0.1:8000/docs

To call authenticated endpoints from Swagger, create a local test account (pre-confirmed) and paste the printed token under **Authorize**:

```powershell
python -m scripts.dev_token --email you+dev@example.com --password "a-long-dev-password"
```

Switching the embedding provider or model? Re-embed stored chunks, because vectors from different models are not comparable:

```powershell
python -m scripts.reembed --all
```

## Running the frontend

```powershell
cd frontend
npm install
copy .env.example .env.local            # then fill in the values
npm run dev
```

- App: http://localhost:3000
- Production build: `npm run build` then `npm start`.

## Testing

| What | Command | Needs |
| --- | --- | --- |
| Backend unit tests | `cd backend; python -m pytest` | nothing (credentials are faked, services mocked) |
| Frontend unit tests | `cd frontend; npm test` | nothing |
| Lint | `cd frontend; npm run lint` | nothing |
| Database checks | `python -m scripts.verify_schema` | real Supabase (rolled back) |
| API checks | `python -m scripts.verify_documents_api` | real Supabase + Gemini (throwaway users, removed) |
| End-to-end | `cd frontend; npm run test:e2e` | backend + frontend running, Microsoft Edge or Chrome |

- **Backend unit tests** cover:
  - health endpoints
  - PDF validation and extraction
  - chunking and page tracking
  - embeddings
  - vector search
  - document and conversation ownership
  - RAG context and citations
  - streaming, disconnects and memory
  - summaries and questions
  - error handling
- **Frontend unit tests** cover:
  - the API client (auth header, errors, 401 sign-out)
  - SSE parsing (events split across network chunks, multi-byte characters)
  - safe login redirects
  - formatting
- **End-to-end** runs the spec's manual checklist in a real browser against the running app. It covers register (with the real confirmation link), login, upload, storage, chunks and embeddings, chat, correct source pages, persistence, summary, questions and logout. It creates a throwaway user and always deletes it with all its data. Options: `E2E_BASE_URL` (default `http://localhost:3000`), `E2E_BROWSER` (`msedge`/`chrome`) and `E2E_HEADED=1`.

GitHub Actions (`.github/workflows/ci.yml`) runs the backend tests, frontend lint, tests and production build on every push and pull request. CI needs no secrets.

## API endpoints

All endpoints except health require `Authorization: Bearer <Supabase access token>`. Every request is scoped to that user, so someone else's document or conversation returns 404.

| Method | Path | Description |
| --- | --- | --- |
| GET | `/health` | Liveness |
| GET | `/health/ready` | Database, pgvector and Storage connectivity (503 if one fails) |
| GET | `/auth/me` | Current user |
| POST | `/documents/upload` | Multipart `file` (PDF), optional `title` → 201 document (`ready`) |
| GET | `/documents` | Your documents, newest first |
| GET | `/documents/{id}` | One document |
| DELETE | `/documents/{id}` | Document, chunks, conversations and file → 204 |
| POST | `/documents/{id}/summary` | Optional `{"language"}` → generates and stores the summary |
| POST | `/documents/{id}/questions` | Optional `{"language"}` → generates and stores 6 suggested questions |
| POST | `/documents/{id}/search` | `{"question", "top_k"?}` → most similar chunks (retrieval only) |
| POST | `/documents/{id}/ask` | `{"question"}` → full answer with sources (not streamed, not saved) |
| POST | `/chat` | `{"document_id", "conversation_id"?, "message"}` → streamed answer (SSE), saved |
| GET | `/conversations?document_id=` | Your conversations, most recently active first |
| POST | `/conversations` | `{"document_id", "title"?}` → empty conversation |
| GET | `/conversations/{id}` | Conversation with all messages and sources |
| DELETE | `/conversations/{id}` | → 204 |

`POST /chat` streams these events:

```
event: meta    data: {"conversation_id": "…", "user_message_id": 41}
event: token   data: {"text": "The Enguri Dam is "}          (many)
event: done    data: {"message_id": 42, "sources": [{"page": 4, "similarity": 0.81}]}
event: error   data: {"detail": "…", "message_id": 42}        (instead of done)
```

- Without `conversation_id`, a new conversation is created and titled from the question.
- Failures before the first token (not found, not ready, model unavailable) are normal HTTP errors and save nothing.
- If the client disconnects mid-answer, generation stops and the partial answer is saved.

Errors are returned as `{"detail": "…"}` with status 400, 401, 404, 409 (document not ready), 413, 415, 422 (also for damaged, encrypted or scanned PDFs), 502 (AI provider) or 500. Internal details are never exposed.

## Example RAG flow

A 12-page travel guide is uploaded; page 4 says *"The Enguri Dam is 271 metres high"*.

1. **Upload:** 12 pages → 14 chunks → 14 embeddings → status `ready`.
2. **Question:** "How high is the Enguri Dam?"
3. **Retrieval:** the page-4 chunk is the closest match, followed by weaker ones.
4. **Prompt:** the excerpts are labelled `[Excerpt 1 | p. 4]` …, followed by the question.
5. **Answer (streamed):** "The Enguri Dam is 271 metres high, one of the tallest arch dams in the world [p. 4]."
6. **Sources:** `p. 4`, because it is cited and was retrieved. The UI shows it as a chip.
7. **Follow-up:** "When was it built?" is rewritten for search as "When was the Enguri Dam built?". The guide does not say, so the prompt requires the answer to state that this is not in the document, and an answer that cites no page has no sources.

## Security

- **Secrets are backend only:** the service key, database URL and AI keys are `SecretStr` and never logged. The browser only gets the anon key. `.env` files are git-ignored.
- **Authentication:** the backend verifies the Supabase JWT on every request, and the user id always comes from the token, never from the request body. The frontend re-checks the session server-side (`getClaims()`), and `proxy.ts` redirects signed-out visitors.
- **Authorization:** every query filters by `user_id`, and vector search reads only the chunks of a document the user owns. RLS on all tables and on Storage adds defence in depth.
- **Uploads:** extension, MIME type and `%PDF` signature are all checked. Size and page limits apply, and encrypted or damaged files are rejected. Stored files sit in a private bucket that no endpoint serves publicly, and storage paths never reach the client. If you add PDF viewing, use the short-lived signed-URL helper (`services/storage.create_signed_url`).
- **Prompt grounding:** the model may only use the retrieved excerpts, and sources are verified against what was retrieved.
- **Errors:** unexpected errors return a generic 500 (with CORS headers) and are logged server-side. Provider error messages are not forwarded.
- **No open redirects:** the login `next` parameter accepts same-site paths only.
- **Production mode:** `ENVIRONMENT=production` disables `/docs`, `/redoc` and `/openapi.json`.

## Deployment

The two halves deploy separately: the frontend to a Node host such as **Vercel**, and the backend to any container or Python host such as **Render**, **Railway**, **Fly.io** or **Cloud Run**. The database, storage and auth stay on Supabase.

### Current deployment (Vercel)

Both halves run on Vercel as two projects (database, storage and auth stay on Supabase):

| Project | Root directory | URL |
| --- | --- | --- |
| `ai-knowledge-base` (Next.js) | `frontend` | https://ai-knowledge-base-gamma-wine.vercel.app |
| `ai-knowledge-base-api` (FastAPI) | `backend` | https://ai-knowledge-base-api-kappa.vercel.app |

- The backend runs as one Python function: `backend/api/index.py` imports the app, and `backend/vercel.json` routes every path to it with `maxDuration: 300`. Vercel uses Python 3.12 (`.python-version`).
- Vercel limits a request body to 4.5 MB, so production uses `MAX_UPLOAD_SIZE_MB=4` and `NEXT_PUBLIC_MAX_UPLOAD_MB=4`. An upload must also finish embedding within 300 s (about 200 pages on the Gemini free tier). For larger PDFs, deploy the backend with the Dockerfile instead.
- `.vercelignore` files keep `.env*`, `venv/`, tests and scripts out of every upload. Environment variables are set in each Vercel project (`vercel env add NAME production`).
- To redeploy, run `npx vercel deploy --prod` in `backend/` or `frontend/`. After changing a `NEXT_PUBLIC_*` value, redeploy the frontend, because those values are built in.

The rest of this section applies to any host.

### Backend

`backend/Dockerfile` builds a slim production image (runtime dependencies only, non-root user). It listens on `$PORT` (default 8000) and trusts the platform's proxy headers.

```powershell
cd backend
docker build -t ai-knowledge-base-api .
docker run --env-file .env -e ENVIRONMENT=production -p 8000:8000 ai-knowledge-base-api
```

Without Docker, use build command `pip install -r requirements.txt` (Python 3.12, see `.python-version`) and start command:

```
uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'
```

Set these on the host:
- every variable from `backend/.env`
- `ENVIRONMENT=production`
- `CORS_ORIGINS=["https://your-frontend.example.com"]`

Point the platform's health check at `/health`.

### Frontend

On Vercel, import the repository with **Root Directory** `frontend`. Set:
- `NEXT_PUBLIC_API_URL`: the backend's public `https://` URL
- `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `NEXT_PUBLIC_MAX_UPLOAD_MB`

### Supabase

Under Authentication → URL Configuration, set **Site URL** to the frontend's production URL and add `https://your-frontend.example.com/auth/callback` to **Redirect URLs** (keep the localhost entries for development). For real users, configure custom SMTP, because the built-in mailer is rate-limited.

### Checklist

- [ ] Migrations applied to the production database (`python -m scripts.migrate --status` shows nothing pending).
- [ ] `GET /health/ready` on the deployed backend returns `"status": "ok"`.
- [ ] `CORS_ORIGINS` contains the exact frontend origin (scheme + host, no trailing slash).
- [ ] Supabase Site URL and Redirect URLs point at the production frontend.
- [ ] The host allows requests of a few minutes and does not buffer `text/event-stream`. Uploads embed synchronously: about 2 minutes for a 100-page PDF on the Gemini free tier.
- [ ] The Gemini key has suitable quota. On the free tier, Google may use the content you send to improve its products, so use a paid key for private documents.
- [ ] `npm run test:e2e` passes against the deployed URLs (`E2E_BASE_URL=https://…`; the backend must allow that origin).

## Future improvements

- Background ingestion (task queue) with live progress, so large uploads don't hold a request open.
- OCR for scanned PDFs.
- Chat across several documents or a whole collection.
- Hybrid search (pgvector + full-text) and re-ranking.
- Clickable sources that open the PDF at the cited page with the passage highlighted.
- Streaming summaries; regeneration of individual answers.
- More formats: DOCX, EPUB, web pages.
- Per-user rate limits and usage quotas; observability (tracing, token usage).
- Sharing conversations and team workspaces.
