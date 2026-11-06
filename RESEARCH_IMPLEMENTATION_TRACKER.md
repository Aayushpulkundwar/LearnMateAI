# Research-to-Implementation Tracker

Status legend: **Implemented** is covered by code and automated tests; **Partially implemented** has a bounded implementation but known functional gap; **Missing** has no implementation; **Unverified** requires the current research manuscript, approved data, or a live staging stack.

> The latest LearnMateAI research manuscript was not present in this repository during this audit. This tracker maps the documented platform claims in `README.md` and the stated research scope to code evidence. Manuscript-only claims remain **Unverified** until the manuscript and its experiment assets are supplied.

| Claimed capability | Status | Evidence / gap |
| --- | --- | --- |
| FastAPI, React, PostgreSQL/pgvector, Redis/Celery, MinIO, Ollama architecture | Partially implemented | Compose and service modules exist. Request correlation IDs, safe liveness/readiness responses, upload guards, and secure production config checks are regression-tested. `STAGING_VALIDATION_REPORT.md` records a valid static Compose configuration, but Docker Desktop remains unavailable for live verification. |
| Text PDF extraction with page provenance | Implemented | `pdf_extraction.py`, chunking and ingestion tests preserve physical page numbers. |
| Layout-aware PDF extraction | Implemented | Extractor now prefers pypdf `extraction_mode="layout"` with compatibility fallback. |
| OCR for scanned PDFs | Partially implemented | Opt-in `LocalTesseractOCREngine` renders with PyMuPDF and OCRs with local Tesseract; page provenance and failure handling are tested. The optional Python bridge (`pytesseract 0.3.13`) is installed, but native Tesseract is absent, so live OCR is unverified. |
| Chapter/topic curriculum metadata | Partially implemented | Normalized grade/subject/chapter/topic models and upload validation exist; automatic chapter/topic extraction is absent. |
| BGE-M3 embeddings through Ollama | Partially implemented | Validated embedding client and ingestion path exist; `ollama list` reports `bge-m3:latest`, and a local `/api/embed` smoke test returned one 1024-dimensional vector. Database-backed ingestion remains unverified. |
| Llama 3 8B generation through Ollama | Partially implemented | Default configuration targets the locally verified `llama3:8b` tag; a host-local generation request succeeds. LangGraph, grounded-generation/citation, and quiz tests remain model-agnostic and pass without a live database-backed workflow. |
| Dense + PostgreSQL FTS retrieval with RRF | Implemented | `retrieval_service.py`, migration `0010`, and hybrid tests cover ranking/filter logic. |
| Optional reranking | Missing | No cross-encoder or deterministic secondary reranker is implemented. |
| Relevance gate and unsupported-question refusal | Implemented | LangGraph relevance node, shared evaluator, and regression tests. |
| Grounded answers with textbook citations | Partially implemented | Context-limited generation and page/chunk/source-index citations exist. `evaluation/faithfulness.py` verifies inline source mapping and reports claim/citation audit metrics; `tests/test_faithfulness.py` covers valid, missing, contradictory, and empty-context cases. Factual entailment still needs human labels or an explicitly evaluated optional judge. |
| Student authentication and curriculum/document authorization | Implemented | Auth, session, student scope, assessment ownership, and curriculum/document authorization tests are present. |
| Subject-wide diagnostics and deterministic grading | Implemented | Assessment models/services and tests cover diagnostic selection, snapshots, and scoring. |
| Performance analytics and mastery uncertainty | Partially implemented | Topic/chapter aggregates, sample counts, confidence levels, and evidence-interval indicators are implemented and tested. Mastery remains an explicitly smoothed performance proxy, not calibrated BKT/IRT uncertainty. |
| Personalized dashboard and weak-topic reassessment | Partially implemented | Backend recommendation/progress paths and frontend components exist; live browser integration is unverified. |
| AI-generated questions validated against sources | Partially implemented | Structural, duplicate, page, source-document, and answer-option source checks exist; ambiguous options are routed to review. Human reviewer workflow and semantic validation remain required. |
| Retrieval benchmark and development-only calibration | Implemented | JSON/JSONL runner emits traces/configuration/metrics, records embedding and generation model identifiers for reproducibility, and blocks test-split calibration. |
| Faithfulness, citation accuracy, quiz validity, diagnostic reliability experiments | Partially implemented | Versioned JSONL review schema, reviewer provenance, disagreement/adjudication, CSV export, and faithfulness/citation benchmark hooks are implemented (`review_dataset.py`, `tests/test_review_dataset.py`). Approved labels and live experiment reports remain absent. |
| Reproducible live staging experiments | Unverified | `STAGING_SETUP.md`, `BENCHMARK_DATASET_GUIDE.md`, and `STAGING_VALIDATION_REPORT.md` document the procedure and observed blockers. Migration `0010` is the static Alembic head; it was not applied because no identified isolated database is available. |

## Audit priorities

1. Bring up an isolated non-production Compose stack, then run migration `0010` and ingestion/retrieval smoke tests with approved source material.
2. Version human-reviewed development/test retrieval and answer/citation datasets; run the existing benchmark runner without mixing splits.
3. Install and verify the optional local OCR dependencies plus native Tesseract on a dedicated ingestion worker before accepting scanned textbooks.
4. Add approved human claim labels and a separately evaluated optional entailment judge before reporting paper-quality faithfulness or validity results.

## 2026-10-29 live-validation handoff

Docker Desktop is reported running by the owner, but this Codex session cannot access its named pipe or the configured user's Docker CLI directory. Live status remains unverified from this execution identity. `RESEARCH_EXPERIMENT_01.md` now supplies a host-user-only sequence that verifies database identity before migration, confirms `0010`, pgvector, GIN FTS, Ollama tags, service health, and produces versioned E1 development reports only from approved human-reviewed labels. The latest local regression evidence remains 109 passing tests in 3.66 seconds; no live RAG or retrieval result is claimed.
