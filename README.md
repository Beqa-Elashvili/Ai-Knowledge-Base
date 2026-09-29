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
