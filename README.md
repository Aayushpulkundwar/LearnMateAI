# 🎓 LearnMateAI

> **An AI-powered textbook tutor that answers student questions using course material, semantic retrieval, grounded generation, and source citations.**

LearnMateAI is an intelligent learning assistant designed to help students understand academic concepts using their own textbooks and learning material.

## Platform update: adaptive learning

LearnMateAI now combines its textbook-grounded tutor with authenticated student profiles, validated MCQ banks, diagnostic and targeted reassessments, deterministic evaluation, performance analytics, evidence-based topic mastery, and adaptive recommendations. The original RAG ingestion, retrieval, Ollama, and citation flow remains the source of truth for tutor answers.

### Architecture

```text
React/Vite dashboard and tutor
        | cookie-authenticated API
FastAPI -> PostgreSQL + pgvector <- Alembic migrations
   |          |             |
Celery/Redis  MinIO      Ollama (embeddings + grounded generation)
```

- Documents are extracted, chunked with page metadata, embedded through Ollama, stored in pgvector, and retrieved with existing similarity and metadata filters.
- The assessment domain is relational: students, curriculum (grades/subjects/chapters/topics), questions/options, assessments/attempts, answers/evaluations, mastery history, and recommendations.
- Assessment grading is deterministic on the backend. Correct options are not present in pre-submission assessment responses.
- Topic mastery is a performance proxy, not a validated probability of knowledge: weighted accuracy (easy 1.0, medium 1.5, hard 2.0) is Bayesian-smoothed with configurable prior settings. Confidence is evidence-based.

### Assessment and adaptive-learning workflow

1. A student registers, signs in, selects a grade-appropriate subject, and begins a randomized diagnostic.
2. The server snapshots question and option order, grades on submission, stores evaluation aggregates, and recalculates affected topic masteries atomically.
3. Analytics, the dashboard, and recommendations read persisted student-scoped evidence only.
4. Recommendations prioritize low mastery when evidence is sufficient; insufficient evidence results in a request for more assessment evidence instead of a weakness claim.
5. Targeted reassessments use validated, previously unseen questions where available. If sufficient fresh questions do not exist, the API returns a clear warning rather than pretending the attempt is independent.
6. A dashboard topic can open the tutor with server-derived subject/chapter filters and evidence-sensitive explanation depth. Retrieval grounding and citations remain mandatory.

### API guide

All student data endpoints use the authenticated session and never accept a client-authoritative student ID.

| Area | Endpoints |
| --- | --- |
| Auth/profile | `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `POST /api/v1/auth/logout`, `GET/PATCH /api/v1/students/me` |
| Assessments | `POST /api/v1/assessments/diagnostic/start`, `GET /api/v1/assessments/attempts/{id}`, `POST /api/v1/assessments/attempts/{id}/submit`, `GET /api/v1/assessments/attempts/{id}/results` |
| Analytics/mastery | `/api/v1/analytics/*`, `/api/v1/mastery/*` |
| Adaptive learning | `GET /api/v1/learning/recommendations`, `PATCH /api/v1/learning/recommendations/{id}`, `POST /api/v1/learning/reassessments/start`, `GET /api/v1/learning/progress` |
| Tutor | `POST /api/v1/query/`; optional `study_topic_id` is validated against the authenticated student's curriculum before personalization is applied |

### Installation and configuration

Copy `.env.example` to `.env` and configure PostgreSQL, Redis, MinIO, `OLLAMA_BASE_URL`, embedding/generation model names, JWT secret, and CORS origins. Start dependencies with Docker Compose, then apply the schema:

```powershell
cd backend
python -m alembic upgrade head
python -m scripts.seed_grades

cd ..\frontend
npm install
npm run dev
```

Run the backend/Celery services using the existing Compose configuration after Ollama has the configured models available.

For an existing Docker installation, run `docker compose exec api python -m scripts.seed_grades`.
This inserts missing Class 7 through Class 12 records and preserves existing grade IDs and relationships; it is safe to repeat.
The registration dropdown reads `GET /api/v1/auth/grades` and submits the selected API-provided UUID.
Frontend requests use the same-origin `/api` proxy by default. Docker routes that proxy to `http://api:8000`; native Vite uses `http://127.0.0.1:8000`.
Set `VITE_API_BASE_URL` explicitly only when deploying the frontend with a separate API origin (and configure backend CORS for that origin).

To verify registration for every supported grade against the local Docker stack:

```powershell
docker compose exec -e RUN_REGISTRATION_INTEGRATION=1 api python -m unittest tests.test_registration_grades -v
```

These integration checks create temporary student accounts and remove them after the run.

### Testing

```powershell
cd backend
python -m unittest discover -s tests -v
python -m alembic upgrade head --sql

cd ..\frontend
npx tsc --noEmit
npm run build
```

The unit suite covers authentication/session behavior, ownership checks, deterministic grading, diagnostics, mastery math, analytics aggregation, question validation, ingestion/extraction, embeddings, relevance, grounded generation, and citation preservation. A live integration run additionally requires PostgreSQL/pgvector, Redis/Celery, MinIO, and Ollama.

### Known limitations and future work

- The current mastery score is an explainable performance proxy rather than calibrated Bayesian Knowledge Tracing or Item Response Theory.
- Live browser/device testing and service integration require the local dependency stack.
- Add production rate limits, observability/metrics, admin curriculum management UI, generated-question reviewer UI, and richer chart/accessibility test automation before production rollout.

Instead of relying only on the general knowledge of a Large Language Model, LearnMateAI retrieves relevant passages from indexed educational content and uses those passages as context for generating answers.

Every grounded response can include citations pointing back to the relevant textbook passages, together with a semantic relevance score.

---

## 📌 Table of Contents

- [Overview](#-overview)
- [Problem Statement](#-problem-statement)
- [Key Features](#-key-features)
- [System Architecture](#-system-architecture)
- [How LearnMateAI Works](#-how-learnmateai-works)
- [RAG Pipeline](#-rag-pipeline)
- [Technology Stack](#-technology-stack)
- [Project Structure](#-project-structure)
- [Citation System](#-citation-system)
- [Ollama Integration](#-ollama-integration)
- [Health Monitoring](#-health-monitoring)
- [Getting Started](#-getting-started)
- [Environment Configuration](#-environment-configuration)
- [Running with Docker](#-running-with-docker)
- [Development Setup](#-development-setup)
- [Testing](#-testing)
- [API Flow](#-api-flow)
- [Example Query Flow](#-example-query-flow)
- [Error Handling](#-error-handling)
- [Performance Considerations](#-performance-considerations)
- [Troubleshooting](#-troubleshooting)
- [Future Improvements](#-future-improvements)
- [Security Considerations](#-security-considerations)
- [Contributing](#-contributing)
- [Author](#-author)
- [License](#-license)

---

# 🌟 Overview

LearnMateAI is a **Retrieval-Augmented Generation (RAG) based educational assistant**.

A student can ask a question such as:

> **What is a balanced chemical equation?**

Instead of directly forwarding the question to an LLM, LearnMateAI:

1. Receives the student's question.
2. Generates/searches its semantic representation.
3. Searches indexed textbook passages.
4. Retrieves the most relevant content.
5. Passes the retrieved context into a LangGraph workflow.
6. Sends the grounded prompt to a locally hosted Llama model through Ollama.
7. Generates a student-friendly explanation.
8. Returns the answer with textbook citations.
9. Displays semantic relevance scores for individual citations.

The result is an AI tutor that is significantly more useful for curriculum-specific learning than a generic chatbot.

---

# 🎯 Problem Statement

General-purpose AI assistants can provide useful explanations, but their answers are not always aligned with:

- a student's prescribed textbook,
- a specific syllabus,
- classroom terminology,
- uploaded learning material,
- or the exact source from which the answer originated.

They may also provide answers without indicating where the information came from.

LearnMateAI addresses this by combining:

- **semantic search**
- **vector retrieval**
- **textbook grounding**
- **LangGraph orchestration**
- **local LLM inference**
- **source citations**

to create a more transparent and curriculum-focused learning experience.

---

# ✨ Key Features

### 📚 Textbook-Grounded Answers

Responses are generated using relevant passages retrieved from indexed educational content.

### 🔍 Semantic Search

Questions are matched with textbook content based on semantic similarity rather than simple keyword matching.

### 🧠 Retrieval-Augmented Generation

Relevant textbook passages are supplied to the LLM before generation.

### 🔗 Source Citations

Generated answers include references to the textbook passages used to construct the response.

### 📊 Citation Relevance Scores

Each citation can display its own semantic relevance percentage.

Example:

```text
Relevance: 65.5%
```

### 🧩 LangGraph Orchestration

The question-answering workflow is managed using LangGraph, allowing the RAG pipeline to remain modular and extensible.

### 🦙 Local LLM with Ollama

LearnMateAI uses Ollama to run Llama locally rather than depending entirely on an external LLM provider.

Current model:

```text
llama3:8b
```

Ollama resolves the installed model to:

```text
llama3:8b
```

### 🐳 Dockerized Architecture

The application is designed to run as multiple services using Docker Compose.

### ❤️ Health Monitoring

The backend verifies:

- Ollama availability
- configured model availability
- service health

without exposing unnecessary infrastructure details to users.

### 🛡️ Safe Error Handling

Detailed technical failures are logged server-side while the frontend receives a safe error message.

### 📱 Responsive Interface

Citation cards and chat elements adapt to smaller screens without overlapping metadata or relevance information.

---

# 🏗 System Architecture

## High-Level Architecture

```mermaid
flowchart TB

    Student["👨‍🎓 Student"]

    subgraph Frontend["Frontend Layer"]
        UI["React + TypeScript\nChat Interface"]
        CitationUI["Citation Cards\nRelevance Display"]
    end

    subgraph Backend["Backend Layer — FastAPI"]
        API["REST API"]
        QueryService["Query / Tutor Service"]
        Health["Health API"]
    end

    subgraph AI["AI Orchestration Layer"]
        Graph["LangGraph Workflow"]
        Retriever["Semantic Retriever"]
        Prompt["Grounded Prompt Builder"]
        LLMService["LLM Service"]
    end

    subgraph Knowledge["Knowledge Layer"]
        Embeddings["Embedding Model"]
        VectorDB["Vector Store\nTextbook Chunks + Embeddings"]
        Textbook["Indexed Textbook Content"]
    end

    subgraph LLM["Local LLM Infrastructure"]
        Ollama["Ollama Server"]
        Llama["Llama 3 8B"]
    end

    Student --> UI

    UI -->|Question| API
    API --> QueryService

    QueryService --> Graph

    Graph --> Retriever

    Retriever -->|Semantic query| Embeddings
    Embeddings --> VectorDB

    Textbook --> VectorDB

    VectorDB -->|Top relevant chunks| Retriever

    Retriever --> Prompt

    Prompt --> LLMService

    LLMService -->|HTTP request| Ollama
    Ollama --> Llama

    Llama -->|Generated answer| Ollama
    Ollama --> LLMService

    LLMService --> Graph

    Graph -->|Answer + citations| QueryService

    QueryService --> API

    API --> UI

    UI --> CitationUI

    Health -->|/api/tags| Ollama
```

---

# 🔄 How LearnMateAI Works

The complete runtime pipeline is:

```text
Student Question
      ↓
Frontend
      ↓
FastAPI
      ↓
LangGraph
      ↓
Semantic Retrieval
      ↓
Relevant Textbook Chunks
      ↓
Grounded Prompt Construction
      ↓
Ollama
      ↓
Llama 3 8B
      ↓
Generated Answer
      ↓
Citation Mapping
      ↓
Similarity Scores
      ↓
Frontend Response
```

---

# 🧠 RAG Pipeline

LearnMateAI uses **Retrieval-Augmented Generation** to ensure answers remain grounded in educational content.

## 1. Student Question

Example:

```text
What is a balanced chemical equation?
```

---

## 2. Semantic Retrieval

The question is compared against the embeddings of indexed textbook passages.

Instead of searching only for exact words, semantic retrieval attempts to understand the meaning of the question.

For example:

```text
Student Question
       ↓
Question Embedding
       ↓
Vector Similarity Search
       ↓
Top Relevant Textbook Chunks
```

---

## 3. Context Selection

The most relevant textbook passages are selected.

Each retrieved passage contains information such as:

```text
document
chapter
page
text
similarity_score
```

---

## 4. Grounded Prompt Construction

Relevant textbook passages are inserted into the prompt supplied to the LLM.

Conceptually:

```text
SYSTEM:
You are a textbook tutor.

CONTEXT:
[Retrieved textbook passages]

QUESTION:
What is a balanced chemical equation?

INSTRUCTION:
Answer using the provided educational context.
```

---

## 5. LangGraph Execution

LangGraph manages the sequence between retrieval, prompt construction and response generation.

This makes it possible to extend LearnMateAI later with additional nodes such as:

```text
Question Classification
        ↓
Retrieval
        ↓
Context Validation
        ↓
Generation
        ↓
Citation Verification
        ↓
Answer Evaluation
```

---

## 6. LLM Generation

The completed grounded prompt is sent to the local Ollama server.

Current configuration:

```text
Model: llama3:8b
Ollama service: http://ollama:11434
```

The LLM generates an explanation using the retrieved context.

---

## 7. Citation Mapping

Retrieved passages are returned together with the answer.

The frontend displays citation information so students can identify the educational source behind the explanation.

---

# 🧱 Technology Stack

| Layer | Technology |
|---|---|
| Frontend | React |
| Language | TypeScript |
| Styling | CSS |
| Backend | FastAPI |
| Backend Language | Python |
| AI Orchestration | LangGraph |
| LLM Runtime | Ollama |
| LLM | Llama 3 8B (`llama3:8b`) |
| Retrieval | Semantic / Vector Search |
| Architecture | Retrieval-Augmented Generation |
| API Communication | REST / HTTP |
| Containerization | Docker |
| Orchestration | Docker Compose |
| Backend Testing | Python `unittest` |
| Health Monitoring | FastAPI Health Endpoints |

---

# 📁 Project Structure

A simplified representation of the repository:

```text
LearnMateAI/
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   └── CitationBadge.tsx
│   │   │
│   │   ├── index.css
│   │   └── ...
│   │
│   ├── package.json
│   └── ...
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── routes/
│   │   │       ├── health.py
│   │   │       └── ...
│   │   │
│   │   ├── core/
│   │   │   └── config.py
│   │   │
│   │   ├── services/
│   │   │   ├── llm_service.py
│   │   │   └── ...
│   │   │
│   │   └── ...
│   │
│   ├── tests/
│   │   ├── test_llm_service.py
│   │   └── ...
│   │
│   └── ...
│
├── docker-compose.yml
├── .env
├── .env.example
├── .gitignore
└── README.md
```

The exact internal layout may evolve as LearnMateAI develops.

---

# 🔗 Citation System

Citations are an important component of LearnMateAI's transparency.

Instead of returning only:

```text
A balanced chemical equation has an equal number of atoms of each
element on both sides of the equation.
```

LearnMateAI can also provide the textbook passages used for the answer.

Each citation can contain:

```json
{
  "document": "Chemistry Textbook",
  "chapter": "Chemical Reactions",
  "text": "...",
  "similarity_score": 0.655
}
```

---

## Citation Relevance

The frontend uses:

```text
similarity_score
```

to show the semantic similarity between the student's question and the retrieved textbook passage.

The calculation is:

```text
similarity_score × 100
```

For:

```json
{
  "similarity_score": 0.655
}
```

the interface displays:

```text
Relevance: 65.5%
```

### Formatting Rules

- Percentage uses **1 decimal place**
- Different citations retain their individual scores
- Citation ordering is preserved
- Citation count is preserved
- Missing values are not displayed
- A valid zero remains visible

Example:

```text
similarity_score = 0
```

displays:

```text
Relevance: 0.0%
```

Missing similarity score:

```text
similarity_score = null
```

results in no relevance text being rendered.

---

## Relevance Tooltip

The citation relevance indicator explains:

> **Semantic similarity between your question and this textbook passage.**

This is intentionally described as **semantic similarity**, not as answer correctness or confidence.

---

# 🦙 Ollama Integration

LearnMateAI runs its LLM using Ollama.

The backend communicates with the Ollama HTTP API.

Docker service URL:

```text
http://ollama:11434
```

Current model:

```text
llama3:8b
```

Installed model:

```text
llama3:8b
```

---

## Ollama Generation Flow

```mermaid
sequenceDiagram

    participant API as FastAPI
    participant LG as LangGraph
    participant LLM as LLM Service
    participant O as Ollama
    participant M as Llama 3 8B

    API->>LG: Student question + retrieved context

    LG->>LLM: Generate grounded response

    LLM->>O: POST /api/generate

    O->>M: Run inference

    M-->>O: Generated tokens

    O-->>LLM: Generated response

    LLM-->>LG: Answer

    LG-->>API: Answer + citations
```

---

# ❤️ Health Monitoring

LearnMateAI performs Ollama availability validation.

The backend can check:

1. Whether the Ollama server is reachable.
2. Whether `/api/tags` responds successfully.
3. Whether the configured model exists.

Conceptually:

```text
FastAPI Health Check
        ↓
GET /api/tags
        ↓
Ollama
        ↓
Available Models
        ↓
Verify llama3:8b
```

Infrastructure details are logged internally but should not be unnecessarily exposed to end users.

---

# 🚀 Getting Started

## Prerequisites

Install:

- Git
- Docker Desktop
- Docker Compose
- Node.js
- Python
- Ollama, if running Ollama outside Docker

For the recommended setup, Docker Desktop should be running before starting the application.

---

## 1. Clone the Repository

```bash
git clone <your-repository-url>
cd LearnMateAI
```

---

## 2. Configure Environment Variables

Create the environment file from the provided template:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

---

# ⚙️ Environment Configuration

Example configuration:

```env
OLLAMA_BASE_URL=http://ollama:11434

LLM_MODEL=llama3:8b

OLLAMA_GENERATION_TIMEOUT_SECONDS=300
```

Additional environment variables may exist depending on the project's storage, database, embedding and frontend configuration.

---

## Ollama Base URL

Because the backend and Ollama run as Docker Compose services, the backend uses the Compose service hostname:

```env
OLLAMA_BASE_URL=http://ollama:11434
```

Do **not** replace this with:

```text
http://localhost:11434
```

from inside the backend container.

Inside Docker, `localhost` refers to the container itself.

---

## Generation Timeout

LLM generation can take longer than normal HTTP requests.

LearnMateAI therefore supports a configurable timeout:

```env
OLLAMA_GENERATION_TIMEOUT_SECONDS=300
```

The timeout is intentionally finite.

---

# 🐳 Running with Docker

Build and start the project:

```bash
docker compose up --build
```

Or run in detached mode:

```bash
docker compose up --build -d
```

---

## View Running Containers

```bash
docker compose ps
```

---

## Backend Logs

```bash
docker compose logs -f
```

Or, for the API container:

```bash
docker logs tutor_api
```

---

## Stop the Application

```bash
docker compose down
```

---

## Rebuild After Code Changes

```bash
docker compose down
docker compose up --build -d
```

---

# 💻 Development Setup

If running components independently rather than through Docker:

## Backend

Navigate to:

```bash
cd backend
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it.

### Windows

```powershell
.venv\Scripts\activate
```

### Linux/macOS

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the API using the project's configured FastAPI entry point.

---

## Frontend

Navigate to:

```bash
cd frontend
```

Install packages:

```bash
npm install
```

Run the development server:

```bash
npm run dev
```

---

# 🧪 Testing

The backend currently includes automated tests for the LLM integration and related application logic.

Run the test suite inside the API container:

```bash
docker exec tutor_api python -m unittest discover -s tests -v
```

Current verified result:

```text
45 passed
0 failed
```

---

## LLM Test Coverage

Tests include scenarios such as:

### Ollama Available

```text
Ollama reachable
+
configured model available
→ generation proceeds
```

### Missing Model

```text
Ollama reachable
+
configured model unavailable
→ diagnostic failure
```

### Connection Failure

```text
Ollama unavailable
→ safe application failure
→ detailed server-side logging
```

### Timeout

```text
generation exceeds configured timeout
→ timeout handled safely
```

---

# 🌐 API Flow

A normal tutoring request follows this path:

```text
POST Student Question
        ↓
FastAPI Route
        ↓
Tutor / Query Service
        ↓
LangGraph
        ↓
Retriever
        ↓
Vector Search
        ↓
Relevant Textbook Chunks
        ↓
Prompt Builder
        ↓
Ollama
        ↓
Llama 3 8B
        ↓
Generated Answer
        ↓
Citation Metadata
        ↓
API Response
```

---

# 📖 Example Query Flow

### Student

```text
What is a balanced chemical equation?
```

### Retrieval

The semantic retriever searches indexed chemistry material.

Possible passages:

```text
Chemical equations must contain the same number of atoms of each
element on both sides of the equation.
```

### Generated Answer

Example:

```text
A balanced chemical equation is an equation in which the number of
atoms of each element is equal on both the reactant and product sides.

For example:

2H₂ + O₂ → 2H₂O

There are four hydrogen atoms and two oxygen atoms on both sides of
the equation, so the equation is balanced.
```

### Citation

```text
Chemistry Textbook
Chapter: Chemical Reactions
Relevance: 65.5%
```

---

# ⚠️ Error Handling

LearnMateAI separates developer diagnostics from user-facing errors.

The backend records detailed causes such as:

- Ollama connection failure
- request timeout
- HTTP errors
- malformed responses
- empty responses
- unavailable model

Example internal issue:

```text
Ollama generation request timed out
```

The frontend receives a controlled error instead of sensitive server information.

---

# ⏱ Performance Considerations

Local LLM inference depends heavily on:

- CPU
- GPU
- system RAM
- VRAM
- model size
- prompt size
- number of retrieved chunks
- output length

During verified end-to-end testing, one larger grounded query required approximately:

```text
2 minutes 34 seconds
```

to complete using local Llama inference.

The current timeout is therefore:

```env
OLLAMA_GENERATION_TIMEOUT_SECONDS=300
```

---

## Potential Latency Optimizations

Future optimization can focus on:

### Context Reduction

Retrieve only the passages that materially contribute to the answer.

### Prompt Compression

Reduce repetitive system instructions and unnecessary metadata.

### Retrieval Tuning

Improve top-K retrieval selection.

### GPU Acceleration

Ensure Ollama is using available GPU resources.

### Smaller / Faster Models

Alternative local models can be evaluated for latency versus educational answer quality.

### Streaming

Stream generated tokens to the frontend as they are produced.

---

# 🔧 Troubleshooting

## `Failed to generate text from Ollama model "llama3:8b"`

Check whether Ollama is running:

```bash
docker compose ps
```

Check available models:

```bash
curl http://localhost:11434/api/tags
```

From within Docker, use the Ollama service hostname:

```text
http://ollama:11434
```

---

## Check Installed Ollama Models

```bash
ollama list
```

Expected:

```text
llama3:8b
```

---

## Generation Times Out

Increase:

```env
OLLAMA_GENERATION_TIMEOUT_SECONDS=300
```

Only increase this when necessary.

A timeout increase fixes request cancellation but does not improve inference speed.

---

## Inspect Backend Logs

```bash
docker logs tutor_api
```

or:

```bash
docker compose logs -f
```

---

## Test Ollama API

```bash
curl http://localhost:11434/api/tags
```

---

# 🔮 Future Improvements

LearnMateAI has significant room for expansion.

### 🚀 Streaming Responses

Display LLM output token-by-token rather than waiting for the complete response.

### ⚡ Faster Local Inference

Profile:

- prompt evaluation
- retrieval latency
- token generation speed
- GPU utilization

### 📚 Multi-Textbook Support

Allow students to choose between multiple courses and textbooks.

### 🧠 Query Classification

Automatically identify:

```text
Definition
Explanation
Numerical
Comparison
Derivation
Short Answer
Long Answer
```

and adjust the response style.

### 📝 Exam Mode

Generate answers specifically formatted for:

```text
2 marks
5 marks
7 marks
10 marks
```

### ❓ Quiz Generation

Automatically generate MCQs and short-answer questions from textbook chapters.

### 🧪 Practice Mode

Allow students to answer questions and receive feedback.

### 📊 Learning Analytics

Track:

- studied chapters
- common doubts
- weak topics
- quiz performance
- revision frequency

### 💾 Conversation Memory

Allow sessions to maintain learning context across multiple questions.

### 🔍 Citation Verification

Automatically verify that generated statements are supported by retrieved textbook passages.

### 📈 Retrieval Evaluation

Measure metrics such as:

```text
Precision@K
Recall@K
MRR
Hit Rate
```

### 🧮 Reranking

Introduce a reranking stage after initial vector retrieval.

```text
Question
   ↓
Vector Search
   ↓
Top 10 Chunks
   ↓
Reranker
   ↓
Top 3–5 Chunks
   ↓
LLM
```

### 🎓 Personalized Tutor

Adapt explanations based on:

- difficulty level
- previous questions
- student's course
- preferred explanation style

---

# 🔐 Security Considerations

LearnMateAI should avoid exposing:

- internal Docker hostnames
- environment variables
- API credentials
- internal exception traces
- sensitive configuration
- infrastructure details

Detailed debugging information should remain in backend logs.

Never commit `.env` files containing secrets.

Ensure `.gitignore` contains:

```gitignore
.env
.env.*
!.env.example

__pycache__/
*.pyc

node_modules/

.venv/
venv/
```

---

# 🧪 Current Verified Status

The following complete workflow has been tested successfully:

```text
Student Question
        ↓
Retrieval
        ↓
LangGraph
        ↓
Ollama
        ↓
Llama 3 8B
        ↓
Grounded Answer
        ↓
Citations
        ↓
Similarity Scores
        ↓
Frontend
```

Test question:

```text
What is a balanced chemical equation?
```

Result:

```text
HTTP 200
```

with a grounded response and:

```text
5 citations
```

where each citation retained its individual:

```text
similarity_score
```

---

# 🗺 Complete System Architecture

```mermaid
flowchart LR

    subgraph Client["👨‍🎓 Client"]
        Student["Student"]
    end

    subgraph Web["🖥 Frontend"]
        Chat["Chat Interface"]
        Messages["Conversation UI"]
        Citations["Citation Cards"]
        Scores["Relevance Scores"]
    end

    subgraph API["⚙️ FastAPI Backend"]
        Endpoint["Tutor API"]
        Service["Query Service"]
        Health["Health Service"]
    end

    subgraph Graph["🧠 LangGraph"]
        Start["Question Input"]
        Retrieve["Retrieval Node"]
        Context["Context Builder"]
        Generate["Generation Node"]
        Output["Response Builder"]
    end

    subgraph RAG["📚 Retrieval Layer"]
        Embed["Query Embedding"]
        Search["Vector Similarity Search"]
        Chunks["Textbook Chunks"]
    end

    subgraph Inference["🦙 LLM Layer"]
        LLMService["LLM Service"]
        Ollama["Ollama API"]
        Llama["Llama 3 8B"]
    end

    Student --> Chat

    Chat --> Endpoint

    Endpoint --> Service

    Service --> Start

    Start --> Retrieve

    Retrieve --> Embed

    Embed --> Search

    Search <--> Chunks

    Search --> Retrieve

    Retrieve --> Context

    Context --> Generate

    Generate --> LLMService

    LLMService --> Ollama

    Ollama --> Llama

    Llama --> Ollama

    Ollama --> LLMService

    LLMService --> Generate

    Generate --> Output

    Output --> Service

    Service --> Endpoint

    Endpoint --> Messages

    Messages --> Citations

    Citations --> Scores

    Health -.-> Ollama
```

---

# 🔁 Request Sequence

```mermaid
sequenceDiagram

    actor Student

    participant Frontend
    participant API as FastAPI
    participant LG as LangGraph
    participant Retriever
    participant VectorDB as Vector Store
    participant Ollama
    participant Llama as Llama 3 8B

    Student->>Frontend: Ask question

    Frontend->>API: Submit question

    API->>LG: Execute tutor workflow

    LG->>Retriever: Retrieve context

    Retriever->>VectorDB: Semantic similarity search

    VectorDB-->>Retriever: Relevant textbook chunks + scores

    Retriever-->>LG: Context + citations

    LG->>Ollama: Grounded prompt

    Ollama->>Llama: Run local inference

    Llama-->>Ollama: Generated answer

    Ollama-->>LG: Response

    LG-->>API: Answer + citations

    API-->>Frontend: JSON response

    Frontend-->>Student: Answer + source relevance
```

---

# 👨‍💻 Author

## Aayush Pulkundwar

Information Technology  
Don Bosco Institute of Technology, Mumbai

LearnMateAI was developed as an AI-powered education platform focused on combining modern LLM technology with textbook-grounded learning.

---

# 🤝 Contributing

Contributions, suggestions and improvements are welcome.

To contribute:

1. Fork the repository.
2. Create a feature branch.

```bash
git checkout -b feature/your-feature
```

3. Commit your changes.

```bash
git commit -m "Add your feature"
```

4. Push the branch.

```bash
git push origin feature/your-feature
```

5. Open a Pull Request.

---

# 📄 License

Add your chosen license here.

For example:

```text
MIT License
```

---

# ⭐ LearnMateAI

**Learn from your material. Ask naturally. Get grounded answers. Verify the source.**

```text
Textbook
   +
Semantic Retrieval
   +
LangGraph
   +
Local LLM
   +
Citations
   =
LearnMateAI
```
