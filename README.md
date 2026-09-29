# AI Knowledge Base — My Personal ChatGPT

Upload your own PDFs and chat with them through a real Retrieval-Augmented Generation (RAG) pipeline, with page-level source citations.

> Work in progress. This project is being built in phases; the full README (architecture, RAG pipeline, schema, API reference) arrives in the final phase.

## Stack

| Layer    | Technology                                              |
| -------- | ------------------------------------------------------- |
| Frontend | Next.js (App Router), TypeScript, Tailwind CSS, shadcn/ui, Lucide |
| Backend  | Python 3.11, FastAPI, Pydantic, SQLAlchemy, PyMuPDF      |
| Data     | Supabase PostgreSQL + pgvector, Supabase Storage, Supabase Auth |
| AI       | OpenAI `text-embedding-3-small` (1536-d) + streaming chat model |

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

## Project structure

```
backend/    FastAPI app (api/ routes, services/ business logic)
frontend/   Next.js app (app/ routes, components/, lib/api.ts client)
```
