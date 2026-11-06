# PDF extraction recovery

## 2026-10-30 recovery correction

The owner reports Chapter 8 page 3 and Chapter 6 page 8 failures inside Docker, plus extraction timeouts for Chapters 4 and 5. The earlier implementation attempted MuPDF only after pypdf had consumed resources in the same 1 GiB/120-second process. It discarded the underlying exception at the subprocess boundary. Consequently the historical Docker failure cannot be attributed specifically to memory, import/dependency failure, or a native parser error from the available messages. No retained Docker logs or concurrency measurements were supplied.

The retry CLI previously queued all four tasks immediately; Compose left Celery concurrency at its CPU-dependent default. Concurrent heavy parsers were therefore possible, but actual resource contention in that run is unproven. The per-document advisory lock only prevents simultaneous retries of the same document.

The isolated text worker now opens MuPDF first, once per document, excluding image payloads from text extraction. This avoids expensive pypdf layout construction and retained decompression allocations before fallback. The pypdf helper and all decompression protections remain intact. Limits remain 25 MiB input, 500 pages, 1 GiB address space, 110/115 seconds CPU, 120 seconds wall time, and the same output text/file caps. Page exceptions retain their physical page number and exception type; the subprocess report now includes exception cause types.

Compose uses `--concurrency=1 --prefetch-multiplier=1`. The retry CLI also waits for each terminal result before dispatching the next selected failed document. A wait timeout stops further dispatches because the preceding task may still be running. Database chunk replacement and completed status remain atomic; failures never persist a partial extraction.

Measured Windows parser checks against the archived PDFs (not Docker ingestion):

| Chapter | Pages returned | Text characters | Empty pages | Seconds |
| --- | ---: | ---: | ---: | ---: |
| 4 | 21 | 61,250 | 0 | 1.093 |
| 5 | 21 | 69,215 | 0 | 0.838 |
| 6 | 13 | 37,552 | 0 | 0.341 |
| 8 | 6 | 22,311 | 0 | 1.297 |

### Read-only verification of all chapter uploads

Run in authorized host PowerShell at the repository root. This shows all matching uploads, including duplicates, and counts missing embeddings or invalid page references. Expect 13 intended uploads; do not hide discrepancies with aggregation across documents.

```powershell
@'
SELECT current_database(), current_user;
SELECT ch.chapter_number, d.id AS document_id, d.title, d.chapter,
       d.processing_status, count(c.id) AS chunks,
       count(c.embedding) AS embedded_chunks,
       min(vector_dims(c.embedding)) AS min_embedding_dim,
       max(vector_dims(c.embedding)) AS max_embedding_dim,
       min(c.page_number) AS first_pdf_page, max(c.page_number) AS last_pdf_page,
       count(c.id) FILTER (WHERE c.page_number IS NULL OR c.page_number < 1) AS invalid_page_refs
FROM documents d
LEFT JOIN chapters ch ON ch.id = d.chapter_id
LEFT JOIN chunks c ON c.document_id = d.id
WHERE lower(trim(d.subject)) = 'science'
  AND lower(trim(d.grade)) IN ('10','class 10','grade 10')
GROUP BY d.id, ch.chapter_number
ORDER BY ch.chapter_number NULLS LAST, d.title, d.id;
'@ | docker compose exec -T postgres sh -lc 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

### Rebuild and sequential retry

The rebuild uses the existing volumes and document IDs. The retry CLI displays database identity and requires `RETRY_FAILED` confirmation. Only selected documents currently marked `failed` are queued.

```powershell
docker compose build api worker
docker compose up -d --no-deps api worker
docker compose exec worker python -c "import pymupdf; print('MuPDF', pymupdf.VersionBind)"
docker compose exec api python -m scripts.retry_failed_documents 342c7865-7f32-43cf-ad44-23870b66625a a4fc3f78-1df2-43e6-ab25-9bc7ccce6dc9 01a8f57c-144b-4a07-accf-5cf180a164b0 c8432cec-6b58-41ff-a228-a2dbce40b648
docker compose logs --tail 200 worker
```

Run the read-only verification again after retries. Linux sandbox execution and successful stored ingestion are pending host validation. The older investigation below is retained as historical evidence and is superseded by this correction.

Local source inspection, 2026-10-29. No database or Docker commands were executed.

## Provenance and measured evidence

`research/results/sciencecs10_ingestion_manifest.json` records these failures:

| Chapter | Document ID | Locally reproduced pypdf limit pages |
| --- | --- | --- |
| 4 — Carbon and its Compounds | c8432cec-6b58-41ff-a228-a2dbce40b648 | None |
| 5 — Life Processes | 01a8f57c-144b-4a07-accf-5cf180a164b0 | None |
| 6 — Control and Coordination | a4fc3f78-1df2-43e6-ab25-9bc7ccce6dc9 | None |
| 8 — Heredity and Evolution | 342c7865-7f32-43cf-ad44-23870b66625a | Physical PDF page 3 |

Each of the four archived PDFs was inspected page by page with pypdf layout extraction. Chapter 8 page 3 triggers `LimitReachedError`; MuPDF extracted 4,206 characters from that page. These are local parser observations, not completed database ingestion results. The provenance CSV is empty. The previously reported page-8 failure cannot be assigned to a document from the supplied records; inspect worker logs before attributing it.

## Limits and failure semantics

The Linux Celery worker now calls an isolated interpreter for the entire extraction phase, including the MuPDF fallback. Only `LimitReachedError` activates MuPDF for the same physical page. No pypdf limit is altered.

- Input: 25 MiB; pages: 500.
- Address space: 1 GiB (`RLIMIT_AS`); CPU: 110 seconds soft / 115 seconds hard; wall time: 120 seconds.
- Text: 100,000 characters per page / 2,000,000 per document; serialized output file: 16,000,000 bytes.
- Native parser crashes, timeouts, resource exhaustion, oversized output, or fallback failure fail the document. No partial page list is persisted.
- Optional OCR is explicitly rejected by this bounded text worker when `OCR_ENABLED=true`; separate constrained OCR execution is required before enabling it. This prevents unbounded Tesseract child processes. Text fallback does not require OCR.
- Local Windows can test parser helpers; production ingestion fails closed outside the Linux worker because `RLIMIT_AS` is unavailable.
- `fontTools` warnings are separate from decompression failures. No global warning suppression or speculative font dependency was added.

Retries retain the document ID, chapter and physical page metadata. A dedicated session-level advisory lock serializes work per document across heartbeat commits. Completed documents are skipped before download/embedding. Failed attempts do not write prepared chunks; successful replacement and completed status commit together. Repeated failed attempts can recompute embeddings, but do not append duplicate stored chunks.

## Host Docker commands

From the authorized PowerShell account at the repository root, inspect identity and existing statuses first:

```powershell
docker compose ps
docker compose exec postgres sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT current_database(),current_user; SELECT id,chapter,processing_status FROM documents WHERE processing_status = ''failed'';"'
docker compose logs --tail 200 worker
```

After confirming the intended LearnMateAI database, rebuild only the Python services and queue the selected documents. The CLI displays the database identity and requires `RETRY_FAILED`. It skips any selected document no longer failed.

```powershell
docker compose build api worker
docker compose up -d --no-deps api worker
docker compose exec api python -m pytest tests/test_pdf_extraction.py tests/test_ingestion_embeddings.py
docker compose exec api python -m scripts.retry_failed_documents c8432cec-6b58-41ff-a228-a2dbce40b648 01a8f57c-144b-4a07-accf-5cf180a164b0 a4fc3f78-1df2-43e6-ab25-9bc7ccce6dc9 342c7865-7f32-43cf-ad44-23870b66625a
docker compose logs --follow --tail 100 worker
```

Final read-only verification:

```powershell
docker compose exec postgres sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT d.id,d.chapter,d.processing_status,count(c.id) AS chunks,min(c.page_number) AS first_pdf_page,max(c.page_number) AS last_pdf_page,min(vector_dims(c.embedding)) AS min_dim,max(vector_dims(c.embedding)) AS max_dim FROM documents d LEFT JOIN chunks c ON c.document_id=d.id WHERE d.id IN (''c8432cec-6b58-41ff-a228-a2dbce40b648'',''01a8f57c-144b-4a07-accf-5cf180a164b0'',''a4fc3f78-1df2-43e6-ab25-9bc7ccce6dc9'',''342c7865-7f32-43cf-ad44-23870b66625a'') GROUP BY d.id ORDER BY d.chapter;"'
```

Regression evidence on Windows: 117 tests passed in 4.01 seconds. Actual Linux resource-limit execution and database retry results remain host-session checks.
