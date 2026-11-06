# Staging Validation Report

**Date:** 2026-10-29  
**Scope:** local, non-production verification only. No database, Docker volume, model, or external environment was modified during this validation. The authorized `.env` model override was changed from `llama3.1` to `llama3:8b`; all other configuration was preserved.

## Result summary

| Check | Result | Evidence |
| --- | --- | --- |
| Compose definition | Passed (static) | `docker compose config --quiet` exited 0. |
| Docker engine | Blocked | Docker CLI 29.5.3 is installed, but `com.docker.service` is `Stopped`/`Manual`; the current user receives named-pipe permission denial and cannot inspect volumes. |
| Migration chain | Passed (static) | `python -m alembic heads` reports `0010_hybrid_retrieval_fts (head)`. |
| Database identity / ownership | Blocked | No Compose PostgreSQL instance could be started. A pre-existing local listener was not treated as staging and was not migrated. |
| GIN index / migration application | Not run | Requires the identified Compose PostgreSQL database. |
| BGE-M3 | Verified locally | `ollama list` reports `bge-m3:latest`; a prior native embedding smoke test returned one 1024-dimensional vector. Database-backed ingestion was not run. |
| Llama 3 8B | Verified locally | `ollama list` reports the standard generation tag `llama3:8b`; no model download was performed for this configuration change. |
| Optional OCR Python dependencies | Partially verified | `pytesseract 0.3.13`, PyMuPDF, and Pillow are installed. Native `tesseract` is absent, so live OCR remains unavailable; fallback/failure tests pass. |
| Ollama connectivity | Passed (host-local) | `http://127.0.0.1:11434/api/tags` responded and reported six models from the current Windows user profile. |
| Llama 3 8B inference | Passed (host-local) | A non-streaming `/api/generate` request to `llama3:8b` returned a non-empty response; Ollama reports it running through `llamacpp` on CPU/GPU. |
| BGE-M3 embedding | Passed (host-local) | `/api/embed` with `bge-m3` returned one vector of dimension 1024. |
| Backend/Ollama routing | Unverified live | No host FastAPI health endpoint responds and Docker is unavailable. `.env` retains Compose service routing (`http://ollama:11434`) and now explicitly selects `llama3:8b`. |
| Backend suite | Passed | `python -m pytest`: 109 passed in 5.48 seconds after the `.env` model update. |
| Frontend build | Passed | `npm run build`: TypeScript and Vite production build completed in 2.88 seconds after the `.env` model update. |
| Authenticated E2E / recovery / concurrency | Not run | Requires the unavailable isolated stack plus approved textbook and test-user fixtures. |

## Docker Desktop administrator action

An administrator must:

1. Open **Docker Desktop** using **Run as administrator** and wait for its engine to be ready.
2. Confirm the intended Windows account is a member of the local `docker-users` group. If it is added, that account must sign out and sign in before retrying Docker.
3. Restore that account's read/write access to its own `C:\Users\<user>\.docker\config.json` through the file's Security properties; do not delete or print the file.
4. Return to a standard terminal and confirm:

```powershell
docker version
docker compose config --quiet
```

Both Client and Server sections must be present. Do not delete existing containers, volumes, databases, or Docker configuration while resolving the service. The observed Docker configuration-file access warning and unavailable named pipe must be resolved by the account or administrator that owns Docker Desktop; this validation did not bypass either permission boundary.

## Safe staging runbook

Use only a fresh local Compose project and values in a non-committed staging environment file. Set `ENVIRONMENT=staging`, a unique `JWT_SECRET_KEY`, `AUTH_COOKIE_SECURE=true`, explicit HTTPS frontend origins in `CORS_ORIGINS`, `MINIO_SECURE=true` behind TLS, and non-default PostgreSQL/MinIO credentials. Do not use a production hostname, database URL, bucket, or credentials.

```powershell
docker compose config --quiet
docker volume ls
docker compose up -d postgres redis minio ollama
docker compose ps
docker compose exec postgres sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT current_database(), current_user;"'
docker compose exec postgres sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT extname FROM pg_extension WHERE extname = ''vector'';"'
docker compose run --rm api python -m alembic upgrade 0010_hybrid_retrieval_fts
docker compose exec postgres sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT indexname FROM pg_indexes WHERE tablename = ''chunks'' AND indexname = ''ix_chunks_content_fts'';"'
```

Stop if the returned database name or owner is not the new Compose database. Apply migrations using a dedicated migration role; run the API and Celery worker with a separate non-superuser role limited to the application schema. Restrict PostgreSQL, Redis, MinIO, and Ollama host ports to the private staging network or localhost; terminate TLS and enforce rate limits at the staging reverse proxy before exposing the API.

After this identity check, run `ollama list` and verify `bge-m3` and `llama3:8b`. Then start `api`, `worker`, and `frontend`, execute authenticated fixtures against `/health/live` and `/health/ready`, and run upload, OCR, ingestion retry, retrieval/citation, assessment, authorization, recovery, and concurrency scenarios. Use only approved textbook material and reviewed labels.

## Findings requiring follow-up

- `docker-compose.yml` is developer-oriented: API hot reload, bind mounts, and public service ports should not be exposed directly in staging.
- Compose currently uses one PostgreSQL bootstrap account. Separate migration and runtime roles require a reviewed staging secret/role-provisioning plan before deployment.
- Native Tesseract is not installed or on `PATH`. Install it from an approved operating-system package source, then enable OCR only on the dedicated ingestion worker.
- The active Ollama executable is under the current Windows user profile and exposes the standardized `llama3:8b` tag. Benchmark reports now record both generation and embedding model identifiers for reproducibility.
- The Compose `ollama` service uses its own `ollama_data` volume, so it will not automatically reuse host-user models. Do not pull duplicates; use an explicitly reviewed staging endpoint override only if Docker Desktop supports reaching the host Ollama service.
- No approved textbook corpus, authenticated staging users, or human-reviewed benchmark labels were available; no live RAG, citation, diagnostic, quiz, or reassessment result is claimed.

## 2026-10-29 execution-session limitation

The owner reports that the Engine and all seven Compose containers are now running. The Codex execution identity remains `LAPTOP-OCU9CMRI\codexsandboxoffline`; it received `Access is denied` for the Docker named pipe and the configured user's `.docker` directory. Consequently, this report has no independent live container, database, Ollama, or API observation for that claim. The host-user commands in `RESEARCH_EXPERIMENT_01.md` are the required identity-gated validation sequence. No Docker resources were changed by this session.
