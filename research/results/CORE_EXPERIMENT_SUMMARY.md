# Core RAG Experiment Summary

**Run:** `core_experiment_audit_2026-10-29`  
**Code revision:** `2788f3ef56f5bc261d4081dbc859c831c6ff4646`  
**Status:** No paper experiment was executed. This is a verified blocker and evaluation-readiness record, not an IEEE result table.

## Verified evidence

| Item | Result |
| --- | --- |
| Configured generation / embedding models | `llama3:8b` / `bge-m3`; not live-verified in this session |
| Approved PDF files discoverable in repository | 0 |
| Versioned review/benchmark datasets discoverable in repository | 0 |
| Human-reviewed ground-truth labels | 0 |
| RAG evaluation engineering smoke suite | 22 passed in 1.14 s |
| Docker live access from this session | Blocked by named-pipe and `.docker` access denial |

The smoke suite covered hybrid ranking, retrieval report traces and split-aware calibration safeguards, citation provenance, claim-faithfulness audit behavior, and human-review dataset integrity. It used test fixtures only and must not be cited as retrieval, answer-quality, or citation-accuracy performance.

## IEEE-ready results table

| Experiment | Dataset (n) | P@5 | R@5 | MRR | nDCG@10 | Latency | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| E1 dense / lexical / hybrid RRF | 0 | — | — | — | — | — | Blocked |
| E2 Top-K / threshold / chunk ablations | 0 | — | — | — | — | — | Blocked |
| E3 answer quality / hallucination | 0 | — | — | — | — | — | Blocked |
| E4 citation accuracy | 0 | — | — | — | — | — | Blocked |
| E5 RAG vs base LLM | 0 | — | — | — | — | — | Blocked |

No confidence intervals are calculable at `n=0`.

## Exact host-user validation and E1/E2 commands

Run from the verified Docker user's standard PowerShell, not the Codex sandbox identity. These commands do not download models or modify data except the explicitly gated migration and report writes.

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
```

Only after a reviewer confirms the returned database identity belongs to LearnMateAI and migration status is below the static head, run:

```powershell
docker compose exec api python -m alembic upgrade 0010_hybrid_retrieval_fts
```

After approved source documents are ingested and independent human reviewers produce a split-separated JSONL dataset, run development E1 and feasible E2 sweeps. Do not calibrate with the test split.

```powershell
Set-Location backend
$dataset = 'evaluation/datasets/exp01/retrieval.jsonl'
New-Item -ItemType Directory -Force research/results | Out-Null
Get-FileHash $dataset -Algorithm SHA256 | ConvertTo-Json | Set-Content research/results/exp01_dataset_sha256.json
python -m scripts.review_dataset validate $dataset
python -m scripts.run_retrieval_benchmark $dataset research/results/E1_retrieval.dev.json --split dev --mode all --top-k 10 --calibrate
foreach ($k in 3,5,10) { python -m scripts.run_retrieval_benchmark $dataset "research/results/E2_topk_$k.dev.json" --split dev --mode all --top-k $k }
python -m scripts.review_dataset export-csv research/results/E1_retrieval.dev.json research/results/E1_retrieval.dev.csv
```

Use a separate, frozen test JSONL only once configurations are selected on development data. E3/E4 require human adjudications in the existing review schema; E5 additionally requires the same frozen questions, generation configuration, and prompt template with retrieval explicitly disabled and source access documented. Their result files should be created only after those executions complete.
