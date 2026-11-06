# RAG comparison experiment — Part 1

This protocol uses frozen run `nine_science_03`, corpus SHA-256 `d9c6dd16c44bf402f26e922449c988a4e19d8bf4edd285addb1999d6f8f06bb8`, and only Class 10 Science chapters 1, 2, 3, 7, 9, 10, 11, 12, and 13 (643 frozen chunks, 1024-dimensional vectors). Chapters 4, 5, 6, and 8 are excluded. No query can widen the approved document/chunk ID allowlist.

The original 50-question source and split assignments are unchanged. The separate 40-question set contains all 18 dev questions plus 22 round-robin selected test questions; the original 32 test questions remain authoritative. The selected test questions are evaluation-only. Do not tune thresholds, prompts, or other parameters using either selected test items or the authoritative test split.

## Verified implementation configuration

See `system_configuration.json` and `frozen_corpus_report.json` for the evidence and per-setting source paths. The frozen snapshot records database `learnmate_db`, user `tutor`, revision `0010_hybrid_retrieval_fts`, pgvector `0.8.6`, and a `simple`-dictionary FTS GIN expression index. Retrieval code computes cosine distance/similarity, FTS via `websearch_to_tsquery('simple', ...)` ranked by `ts_rank_cd(..., 32)`, and hybrid fusion by RRF (`k=60`). For requested top 10, dense/FTS candidate depth is 40 using multiplier 4. Frozen Ollama tags record BGE-M3 digest `7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab` (1024 dimensions) and Llama 3 8B digest `365c0bd3c000a25d28ddbf732fe1c6add414de7275464c4e4d1c3b5fcb5d8ad1` (Q4_0). Runtime overrides and current live model tags must be checked on the host; these are values recorded at freeze time. No HNSW/IVFFlat index appears in the frozen `pg_indexes` evidence; the live query plan was not captured. The measured passage lengths are character lengths: 243 minimum, 999 maximum, mean 820.36, median 912, p90 986.

## Exact Windows PowerShell workflow

Run the local read-only frozen artifact check, config extraction, and 40-question selection:

```powershell
Set-Location 'C:\Users\Aayush Pulkundwar\OneDrive\Desktop\LearnMateAI\backend'
python -m scripts.rag_comparison inspect --run-dir ..\research\results\nine_science_03 --output ..\research\experiments\rag_comparison\system_configuration.json
python -m scripts.rag_comparison select-dataset --run-dir ..\research\results\nine_science_03 --source-dataset ..\research\results\nine_science_03\questions.candidates.jsonl --output-dir ..\research\experiments\rag_comparison\datasets
```

Run actual dense, PostgreSQL FTS, and hybrid retrieval from the authorized Windows Docker account. This runner uses the existing `api` container and mounted application, verifies the live DB snapshot fingerprint before and after, and performs read-only retrieval only. It does not migrate, ingest, or download models. Use a unique run ID because outputs are immutable:

```powershell
Set-Location 'C:\Users\Aayush Pulkundwar\OneDrive\Desktop\LearnMateAI'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\research\scripts\RUN_RAG_COMPARISON.ps1 -RunId rag_cmp_20261030_a
```

The runner captures per-query pre-gate rankings, scores, source page/document/chapter, status, monotonic retrieval latency, and post-gate accepted evidence in `runs\dense.json`, `runs\fts.json`, and `runs\hybrid.json`. It records a deterministic randomized condition order, seed, and un-controlled warm/cold cache state. Any failures remain in the files; pooling refuses to proceed unless every question succeeded under every condition. Check the manifest and all per-query status values before continuing.

Create the deduplicated, shuffled pool and two identical blinded worksheets after the three real result files exist:

```powershell
Set-Location 'C:\Users\Aayush Pulkundwar\OneDrive\Desktop\LearnMateAI\backend'
python -m scripts.rag_comparison pool --run-dir ..\research\results\nine_science_03 --dataset ..\research\experiments\rag_comparison\datasets\questions.jsonl --runs-dir ..\research\experiments\rag_comparison\runs --output-dir ..\research\experiments\rag_comparison --seed 20261030
```

The reviewer workbooks are `annotations\reviewer_1.csv` and `annotations\reviewer_2.csv`. The source retriever/rank/score mapping is stored separately in `annotations\pool_origin_mapping.json`; keep it from reviewers until annotation is complete. In each workbook, review every row and fill relevance (`1` sufficient evidence, `0` insufficient, no blanks), distinct reviewer ID, rationale, and a positive duration if recorded. For every question, fill the same explicit answerability (`true`/`false`), reference answer and evidence spans on each repeated row; leave evidence spans as `[]` only for unanswerable questions. Use JSON span objects like `[{"passage_id":"<candidate chunk UUID>","start_char":10,"end_char":40}]`, with zero-based offsets in the exact displayed passage. Question comments are optional. Reviewers must verify answerability and evidence against the included textbook corpus, not infer irrelevance from absence in the retrieval pool.

Import both independent files, calculate agreement, and write a disagreement worksheet:

```powershell
python -m scripts.rag_comparison import-reviews --run-dir ..\research\results\nine_science_03 --pool-mapping ..\research\experiments\rag_comparison\annotations\pool_origin_mapping.json --reviewer-1 ..\research\experiments\rag_comparison\annotations\reviewer_1.csv --reviewer-2 ..\research\experiments\rag_comparison\annotations\reviewer_2.csv --disagreements ..\research\experiments\rag_comparison\annotations\disagreements.csv --summary ..\research\experiments\rag_comparison\annotations\agreement.json
```

The import validates candidate completeness, frozen chunk/document/page metadata, question IDs/text, distinct reviewer identities, labels, rationale, question-level fields, evidence spans, and provided durations/timestamps. `agreement.json` reports labelled pairs, positive/negative totals, raw agreement, Cohen's kappa, disagreements, and median recorded duration. Copy `disagreements.csv` to `adjudications.csv`; fill `final_relevance` (0/1) for relevance rows, or `final_answerability`, `final_reference_answer`, and `final_evidence_spans_json` for question-level rows. Every disagreement row also requires adjudicator ID, rationale, and date in `YYYY-MM-DD` format. No majority vote is substituted.

After all disagreement rows are explicitly adjudicated, produce Part 2-compatible `gold.json` (a JSON list accepted by `load_benchmark_dataset`):

```powershell
python -m scripts.rag_comparison export-gold --run-dir ..\research\results\nine_science_03 --dataset ..\research\experiments\rag_comparison\datasets\questions.jsonl --pool-mapping ..\research\experiments\rag_comparison\annotations\pool_origin_mapping.json --reviewer-1 ..\research\experiments\rag_comparison\annotations\reviewer_1.csv --reviewer-2 ..\research\experiments\rag_comparison\annotations\reviewer_2.csv --adjudications ..\research\experiments\rag_comparison\annotations\adjudications.csv --output ..\research\experiments\rag_comparison\gold.json
```

The gold contains only pooled judged passages, with per-passage binary judgments, answerability, reference answers, evidence spans, split, and corpus fingerprint. Unjudged passages are explicitly unknown, not negative. All commands refuse to overwrite existing result, worksheet, or gold files. To refresh the manifest after live outputs exist, run:

```powershell
python -m scripts.rag_comparison manifest --run-dir ..\research\results\nine_science_03 --experiment-dir ..\research\experiments\rag_comparison --source-dataset ..\research\results\nine_science_03\questions.candidates.jsonl --subset-dataset ..\research\experiments\rag_comparison\datasets\questions.jsonl --refresh
```

## Focused software tests

```powershell
Set-Location 'C:\Users\Aayush Pulkundwar\OneDrive\Desktop\LearnMateAI\backend'
python -m pytest -q tests\test_rag_comparison.py tests\test_nine_chapter_corpus.py
```

The tests use synthetic data only for software behavior. They are not retrieval or quality measurements. No human annotation, gold labels, or research accuracy claims exist until the two reviewers complete the worksheets and adjudicate differences.

## Part 2: metrics, generation, and human scoring

Part 1 artifacts must be checked before use. The current frozen inputs are `datasets/questions.jsonl`, `system_configuration.json`, `experiment_manifest.json`, and `frozen_corpus_report.json`. In this checkout, all three run files are present and validate as 40 successful queries each; the Part 1 reviewer CSVs exist but have no labels or reviewer IDs, and `gold.json` is absent. Retrieval scoring stops with an explicit error until adjudicated `gold.json` from two reviewers exists.

The generation comparison uses the first ten development records in the immutable selected-dataset order (fixed IDs are saved in each output); it never selects from held-out results. Retrieval-free generation calls the already installed local `llama3:8b` tag only and refuses to download or use a different digest. RAG generation calls the existing authenticated FastAPI `/api/v1/query/` endpoint and requires a human-operated test-account login. Credentials and the session cookie remain in process memory. The API does not expose its exact rendered internal prompt or generation options; outputs disclose this limitation. Confirm the API is connected to the verified staging database before running it. The RAG runner filters each question to its approved frozen document ID and rejects citations outside the nine-document allowlist.

From the repository root in Windows PowerShell:

```powershell
Set-Location 'C:\Users\Aayush Pulkundwar\OneDrive\Desktop\LearnMateAI'
python .\research\experiments\rag_comparison\generate_no_retrieval.py
python .\research\experiments\rag_comparison\record_generation_manifest.py
python .\research\experiments\rag_comparison\generate_rag.py --api http://127.0.0.1:8000
```

`generate_rag.py` first requires a healthy API, then asks the operator to confirm the live database identity is `learnmate_db|tutor` and the current Ollama model digest matches the frozen `llama3:8b` digest, then prompts interactively for the existing account. These confirmations are operator assertions, not API queries; verify using the authorized host session before proceeding. For example, from the repository root in PowerShell: `docker compose exec -T postgres psql -U tutor -d learnmate_db -c "SELECT current_database(), current_user; SELECT version_num FROM alembic_version;"` and `docker compose exec -T ollama ollama list`. It does not save the password, bearer token, or cookie. Do not run this against production or an unidentified database. The current Part 2 execution ran the retrieval-free condition (10/10); RAG generation was not run because a test-account credential and live database/model confirmation were not available to this process.

After human-adjudicated `gold.json` is exported, run:

```powershell
Set-Location 'C:\Users\Aayush Pulkundwar\OneDrive\Desktop\LearnMateAI\research\experiments\rag_comparison'
python eval_retrieval.py
```

The evaluator enforces the frozen run/fingerprint, common query IDs, frozen passage membership, explicit answerability, complete top-10 judgments for scored queries, and the rule that unjudged passages are unknown (never negative). Incomplete pooled queries are excluded and counted; unanswerable queries are reported separately. Failed and empty retrievals remain in per-query output and score zero where a query is otherwise scorable. Latency comes from the stored monotonic retrieval-call measurements; embedding latency is separate in the raw run files.

After both answer files exist, generate blinded worksheets; these are not produced until both conditions have real outputs:

```powershell
python .\research\experiments\rag_comparison\answer_review.py worksheets --seed 20261030
```

Two independent reviewers fill all score columns (0–2), their own reviewer ID, rationale, unsupported-claims comments, and measured duration. Do not alter question text, references, evidence, answer text, or row IDs. The hidden `annotations\answer_blinding_key.json` contains the randomized A/B condition mapping and immutable-content hashes; keep it from reviewers. Import both completed files, explicitly resolve every disagreement in `answer_disagreements.csv`, then export:

```powershell
python .\research\experiments\rag_comparison\answer_review.py import
# Manually complete final_score (0/1/2), adjudicator_id, rationale, and ISO date for every disagreement row.
python .\research\experiments\rag_comparison\answer_review.py export
```

Final answer metrics are emitted only after complete scores and explicit disagreement adjudication. Citation support is interpreted separately because the retrieval-free condition has no source evidence.

Generate the IEEE results prose after any stage; it reports unavailable measurements as unavailable. LaTeX tables and figures are generated only when their corresponding validated metrics JSON exists. If refreshing after human review, use `--refresh`; each replaced output is preserved as a `.pre_refresh` backup, and an existing backup causes refusal:

```powershell
python .\research\experiments\rag_comparison\generate_ieee_report.py --refresh
```

Do not rerun an export over an existing artifact. All writers use exclusive creation and require a new run/output location or explicit archival by the researcher. Focused tests and their actual log are run with:

```powershell
python .\research\experiments\rag_comparison\run_focused_tests.py
python .\research\experiments\rag_comparison\record_part2_status.py
```
