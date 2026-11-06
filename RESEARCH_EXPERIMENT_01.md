# Research Experiment 01 — RAG Baseline

**Date:** 2026-10-29  
**Status:** Blocked before any infrastructure mutation. No experimental result is claimed.

## Environment status

| Item | Status | Measured evidence |
| --- | --- | --- |
| Docker daemon | **Blocked** | `docker version --format '{{.Server.Version}}'` failed: `permission denied while trying to connect to the docker API at npipe:////./pipe/docker_engine`. Docker also reported that `C:\Users\Aayush Pulkundwar\.docker\config.json` could not be opened because access was denied. |
| Staging Compose stack | Not started | Per the experiment constraint, no `docker compose` command was run after the daemon failure. Existing databases and volumes were not inspected or touched. |
| PostgreSQL identity / migrations / pgvector / GIN | Not run | Requires the identified isolated Compose PostgreSQL instance. |
| Alembic chain (static) | Pass | `python -m alembic heads` returned `0010_hybrid_retrieval_fts (head)`. The `0010` migration defines `ix_chunks_content_fts` as a GIN index. This does not establish that it exists in a database. |
| Host Ollama (`llama3:8b`, `bge-m3`) | Not run | Stopped with other infrastructure-dependent checks after Docker access failed; no model pull was attempted. |
| PDF ingestion / chunks / embeddings / metadata | Not run | No approved textbook PDF and no identified isolated database were available. |
| Human-reviewed development data | 0 examples | No approved ingested passages or human adjudications were available; no labels were created. |
| Retrieval benchmark | Not run | No labeled dataset or staging retrieval service was available. |
| Regression suite | Pass | `python -m pytest`: **109 passed** in **3.66 s** (Python 3.14.4, pytest 9.1.1). |

## Metrics and artifacts

No corpus was ingested and no benchmark query was executed. Therefore Precision@5, Recall@5, MRR, nDCG@10, retrieval latency, query traces, model identifiers, and dataset hashes are **not available**. Reporting them as zero would be misleading, so they are deliberately absent.

Generated report: `RESEARCH_EXPERIMENT_01.md` (this file). No benchmark report or dataset artifact was generated.

## Required administrator action

An administrator must start Docker Desktop and ensure its engine is running, add the intended Windows account to the local `docker-users` group (then have that account sign out and sign in), and restore that account's read/write permission to `C:\Users\Aayush Pulkundwar\.docker\config.json`. Do not delete Docker configuration, containers, volumes, or databases while fixing access.

The experiment may resume only after this standard-user verification succeeds:

```powershell
docker version
```

Both Client and Server sections must appear. This run did not retry Docker after the failure.

## Reproducible continuation commands

Run these only after the daemon verification above succeeds. The Compose project name isolates new named resources from any existing Compose project.

```powershell
$project = 'learnmate-rag-exp01'
docker compose --project-name $project up -d postgres redis minio ollama
docker compose --project-name $project ps
docker compose --project-name $project exec postgres sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT current_database(), current_user;"'
docker compose --project-name $project exec postgres sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT extname FROM pg_extension WHERE extname = ''vector'';"'
docker compose --project-name $project run --rm api python -m alembic upgrade 0010_hybrid_retrieval_fts
docker compose --project-name $project exec postgres sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT indexname FROM pg_indexes WHERE tablename = ''chunks'' AND indexname = ''ix_chunks_content_fts'';"'
```

Before ingestion, verify the models already exist via the approved host Ollama endpoint; do not pull models:

```powershell
Invoke-RestMethod http://127.0.0.1:11434/api/tags
```

Confirm tags for `llama3:8b` and `bge-m3`, then ingest only an approved textbook PDF. Build the development dataset from its persisted chunk IDs and human-reviewed source passages according to `BENCHMARK_DATASET_GUIDE.md`. Validate it and benchmark development data only:

```powershell
cd backend
python -m scripts.review_dataset validate evaluation/datasets/exp01-dev/retrieval.jsonl
python -m scripts.run_retrieval_benchmark evaluation/datasets/exp01-dev/retrieval.jsonl reports/exp01-dev.json --split dev --calibrate
python -m scripts.review_dataset export-csv reports/exp01-dev.json reports/exp01-dev.csv
$env:PYTHONDONTWRITEBYTECODE='1'; python -m pytest
```

The JSON benchmark report records dense, lexical, and hybrid query traces, Precision@5, Recall@5, MRR, nDCG@10, latency, model configuration, and the source dataset path. Record a SHA-256 hash of the finalized JSONL alongside it before reporting results. Do not tune against a held-out test split.

## 2026-10-29 host-session execution block

The project owner reports that Docker Engine and seven project containers are running. This Codex session could not independently validate that state: its Windows identity is `LAPTOP-OCU9CMRI\codexsandboxoffline`, which is denied the Docker named pipe and the configured user's `.docker` directory. No Docker command below was run from this session.

Execute the following from a fresh standard PowerShell owned by the verified Docker user. It is read-only through the identity gate; inspect the returned database name and owner before manually proceeding to the migration command.

```powershell
Set-Location '<LearnMateAI repository root>'
docker version
docker compose ps
docker compose exec postgres sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT current_database() || ''|'' || current_user;"'
docker compose exec api python -m alembic current
docker compose exec api python -m alembic heads
docker compose exec postgres sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT extname FROM pg_extension WHERE extname = ''vector''; SELECT indexname FROM pg_indexes WHERE tablename = ''chunks'' AND indexname = ''ix_chunks_content_fts'';"'
docker compose exec ollama ollama list
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-RestMethod http://127.0.0.1:8000/health/ready
docker compose exec redis redis-cli ping
docker compose exec minio sh -lc 'curl -fsS http://localhost:9000/minio/health/live'
docker compose exec worker celery -A app.core.celery_app inspect ping
```

If and only if the database identity is the intended LearnMateAI database and `alembic current` is below `0010_hybrid_retrieval_fts`, run:

```powershell
docker compose exec api python -m alembic upgrade 0010_hybrid_retrieval_fts
```

After an approved PDF is ingested and human-reviewed development labels exist, generate E1 artifacts without touching the held-out split:

```powershell
Set-Location backend
$dataset = 'evaluation/datasets/exp01-dev/retrieval.jsonl'
New-Item -ItemType Directory -Force reports/exp01 | Out-Null
Get-FileHash $dataset -Algorithm SHA256 | ConvertTo-Json | Set-Content reports/exp01/dataset-sha256.json
python -m scripts.review_dataset validate $dataset
python -m scripts.run_retrieval_benchmark $dataset reports/exp01/e1-dev.json --split dev --mode all
python -m scripts.review_dataset export-csv reports/exp01/e1-dev.json reports/exp01/e1-dev.csv
$env:PYTHONDONTWRITEBYTECODE='1'; python -m pytest
```

`e1-dev.json` contains model identifiers, dense/lexical/hybrid configurations, aggregate Precision@5, Recall@5, MRR, nDCG@10, mean retrieval latency, and per-query traces. No E1 metric is reported until that file is produced from verified labels.
