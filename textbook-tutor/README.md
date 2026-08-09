# AI Textbook Tutor 📚🤖

Curriculum-based RAG assistant that answers student questions strictly from prescribed class textbooks (NCERT / State Board).

## Core Architectural Guarantees
- **Strict Grounding**: Answers are generated ONLY from retrieved textbook chunks. If retrieved content similarity is below `RELEVANCE_THRESHOLD` (default `0.6`), the system hard-refuses rather than hallucinating from general LLM training data.
- **Granular Citations**: Every generated response attaches chapter and page number metadata.
- **Local & Offline First**: Zero cloud API dependencies (no OpenRouter or OpenAI keys needed). Uses **Ollama** for embeddings (`bge-m3`, dimension 1024) and generation (`llama3.1`).

---

## Tech Stack
- **Backend**: Python 3.11+, FastAPI, Pydantic V2
- **Orchestration**: LangGraph for stateful query/RAG graph logic
- **Ingestion Pipeline**: Celery + Redis (broker & result backend)
- **Database**: PostgreSQL 16 + pgvector (`pgvector/pgvector:pg16`)
- **Object Storage**: MinIO (Raw PDF storage)
- **AI Models**: Ollama (`bge-m3` embeddings, `llama3.1` LLM)
- **Frontend**: React 18 + TypeScript + Vite
- **Infra**: Docker Compose

---

## Quick Start & Setup Instructions

### 1. Environment Setup
Copy the environment template:
```bash
cp .env.example .env
```

### 2. Launch Services with Docker Compose
Start all background containers (Postgres+pgvector, Redis, MinIO, Ollama, API, Worker, Frontend):
```bash
docker compose up -d --build
```

### 3. Run Database Migrations
Apply Alembic migrations to initialize the `documents` and `chunks` tables with pgvector extension:
```bash
docker compose exec api alembic upgrade head
```

### 4. Pull Ollama Models
Inside the running Ollama container, pull the embedding and LLM models:
```bash
docker compose exec ollama ollama pull bge-m3
docker compose exec ollama ollama pull llama3.1
```

---

## Usage Workflow

### 1. Ingest a Textbook PDF
Upload a PDF document via the API or Frontend UI:
```bash
curl -X POST "http://localhost:8000/api/v1/documents/upload" \
  -F "file=@sample_ncert_class10_science.pdf" \
  -F "title=NCERT Class 10 Science" \
  -F "subject=Science" \
  -F "grade=10" \
  -F "chapter=Chemical Reactions and Equations"
```
Check processing status:
```bash
curl "http://localhost:8000/api/v1/documents/<DOCUMENT_ID>"
```

### 2. Query the Assistant
Ask a question grounded in the textbook context:
```bash
curl -X POST "http://localhost:8000/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What is a balanced chemical equation?",
    "subject": "Science",
    "grade": "10"
  }'
```

### 3. Secondary Features (Summarization & Quiz)
- **Summarize Chapter**: `POST /api/v1/query/summarize`
- **Generate Quiz**: `POST /api/v1/query/quiz`

---

## Directory Structure Overview

```
textbook-tutor/
├── docker-compose.yml
├── .env.example
├── README.md
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/routes/ (documents.py, query.py, health.py)
│   │   ├── core/ (config.py, celery_app.py, db.py)
│   │   ├── models/ (document.py, chunk.py)
│   │   ├── schemas/ (document.py, query.py)
│   │   ├── services/ (embedding_service.py, llm_service.py, minio_service.py)
│   │   ├── graph/ (state.py, nodes.py, workflow.py)
│   │   └── tasks/ (ingestion.py)
│   ├── alembic/ (migrations)
│   ├── requirements.txt
│   └── Dockerfile
└── frontend/
    ├── src/
    │   ├── components/ (BookSelector, MessageThread, CitationBadge, DocumentUpload)
    │   ├── api/ (client.ts)
    │   └── App.tsx
    └── Dockerfile
```
