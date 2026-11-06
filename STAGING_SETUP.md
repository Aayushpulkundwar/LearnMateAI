# Isolated Staging Setup

These steps create or use only the repository's local Compose volumes. Do not point `.env` at a shared, production, or otherwise unidentified database.

## Docker Desktop administrator step

The local `com.docker.service` is manual/stopped and could not be started without administrator control. An administrator must:

1. Open **Docker Desktop** using **Run as administrator**.
2. Wait until Docker Desktop reports that the engine is running.
3. In a non-administrator terminal, run `docker version` and confirm both Client and Server sections appear.
4. Do not delete existing containers, volumes, or databases while diagnosing startup.

## Start and verify the isolated stack

```powershell
cd <LearnMateAI repository root>
docker compose up -d postgres redis minio ollama
docker compose ps
```

Verify that only the Compose-managed `postgres` service is used before any migration:

```powershell
docker compose exec postgres sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT current_database();"'
docker compose exec postgres sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT extname FROM pg_extension WHERE extname = ''vector'';"'
```

The returned database name must match the local Compose configuration. If it does not, stop; do not migrate it.

## Models, migration, and checks

```powershell
ollama list  # verify bge-m3 and llama3:8b are installed
cd backend
cd ..
docker compose run --rm api python -m alembic upgrade 0010_hybrid_retrieval_fts
docker compose exec postgres sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT indexname FROM pg_indexes WHERE tablename = ''chunks'' AND indexname = ''ix_chunks_content_fts'';"'
docker compose run --rm api python -m pytest
```

Only run PDF ingestion and retrieval benchmarks after approved textbooks and the human-reviewed dataset described in `BENCHMARK_DATASET_GUIDE.md` are available.

## Optional scanned-PDF OCR worker

Install a native Tesseract package from the operating system's trusted package source, ensure `tesseract` is on `PATH`, then:

```powershell
cd backend
python -m pip install -r requirements-ocr.txt
```

Set `OCR_ENABLED=true` only for the dedicated ingestion worker. The fallback keeps original PDF page numbers and does not send document pages to external services.
