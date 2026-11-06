# Nine-chapter research protocol

Only chapters **1, 2, 3, 7, 9, 10, 11, 12, 13** are approved. Chapters **4, 5, 6, 8** are excluded because ingestion failed. Their records must not be retried or modified by this workflow. The earlier import/recovery runners are not part of this protocol.

## Scope and evidence status

The fixed document IDs are in `backend/app/evaluation/nine_chapter_corpus.py`. They come from the existing ingestion manifest. The owner reports nine completed documents, **643 chunks**, and **1024-dimensional** vectors. These totals are not independently asserted as a new database observation by Codex. The host freeze checks every included document/chunk and stops if any count, dimension, status, page provenance, extension, or index fails verification. It exports exact per-chapter counts and a SHA-256 fingerprint covering document metadata, chunk IDs/content/page metadata, and every vector's fingerprint.

Both candidate SQL queries filter approved document IDs AND frozen chunk IDs before ranking. An empty allowlist matches nothing. A result outside the snapshot aborts evaluation. Later indexing of excluded chapters cannot expand the corpus. Changes to included chunks or vectors invalidate the fingerprint. Snapshot transactions are read-only and repeatable-read; no migration or ingestion is performed.

## Dataset and human review

`research/datasets/nine_chapters/questions.candidates.jsonl` contains **50 machine-authored candidate questions**, distributed across all nine included chapters, with 18 dev / 32 test records. Their topical/source coverage is pending human verification. They have no accepted answerability or gold labels. The host freeze adds up to three candidate passages from the corresponding approved document using deterministic word overlap, explicitly as suggestions. Those passages must not automatically become gold evidence.

Reviewers should search the entire included corpus for all relevant passages, not only the suggestions; otherwise Recall@5 is recall against incomplete judgments. Review/rewrite questions for source support before any experiments, keeping 50 unique questions and the original split allocation. Include source-grounded unanswerable cases if abstention is to be evaluated; do not source them from excluded chapters. The current draft makes no promise of unanswerable coverage.

For every record, a human must set `answerable` (boolean), `gold_passage_ids`, a grounded `reference_answer` for answerable questions, and exact `evidence_spans` (`passage_id`, `start_char`, `end_char`). Preserve `document_id`, `split`, and `corpus_sha256`. Set:

```json
{"relevance_review":{"status":"approved","provenance":"human","reviewer_id":"actual-reviewer-id","rationale":"Reviewer-authored evidence rationale"}}
```

Never copy this example as proof of review. The runner checks all 50 judgments and rejects pending labels, excluded/unknown passages, invalid spans, arbitrary question filters, or corpus drift. Reviewers are responsible for the truth of the attestations; structural validation cannot establish independent human review.

### CSV review workflow

The current `research/datasets/nine_chapters/questions.reviewed.jsonl` is still the original 50-row draft: all 50 have pending relevance review, null answerability, no gold passage IDs, and no evidence spans. This is why `validate_judgments()` refuses it. Its splits remain 18 dev / 32 test.

Export a review worksheet from the immutable `nine_science_03` snapshot. Each row displays the question, chapter title, proposed chunk IDs, page numbers, and full passage excerpts. The expected answer column explicitly says when no answer was supplied. Candidate passages are suggestions only. The reviewer must author the answer and manually enter the confirmed gold IDs and span offsets.

```powershell
Set-Location 'C:\Users\Aayush Pulkundwar\OneDrive\Desktop\LearnMateAI\backend'
python -m scripts.review_nine_chapter_dataset export-csv --run-dir ..\research\results\nine_science_03 --output ..\research\datasets\nine_chapters\review\nine_science_03_review.csv
```

Edit that CSV in Excel or another spreadsheet editor. For each of the 50 rows, set `decision` to `approve` or `correct`; `reject` and blank decisions intentionally prevent export. Fill `reviewer_id`, a record-specific rationale, `answerable` (`true`/`false`), `gold_passage_ids` (semicolon-separated IDs; review the entire included corpus, not just suggestions), `reference_answer`, and `evidence_spans_json`, for example `[ {"passage_id":"<approved-chunk-id>","start_char":12,"end_char":48} ]`. Offsets are zero-based character positions in that frozen chunk's `content`. If a question is corrected, edit its `question` cell. Do not change `id`, `split`, `chapter_number`, `document_id`, or `corpus_sha256`. The importer checks every ID against the frozen snapshot and rejects excluded/unknown chunks, missing decisions, missing reviewer attestations, invalid spans, and split/fingerprint changes. It refuses to overwrite an existing output.

Only after a human has reviewed all rows, import to a new final dataset path:

```powershell
python -m scripts.review_nine_chapter_dataset import-csv --run-dir ..\research\results\nine_science_03 --review-csv ..\research\datasets\nine_chapters\review\nine_science_03_review.csv --output ..\research\datasets\nine_chapters\reviewed\nine_science_03\questions.reviewed.jsonl
```

Then run the evaluator using that output file. The importer revalidates all 50 records against `nine_science_03/corpus.json` and preserves the fingerprint in every question. No judgment is accepted automatically.

## Exact Windows PowerShell commands

Run local software tests independently of research evaluation:

```powershell
Set-Location 'C:\Users\Aayush Pulkundwar\OneDrive\Desktop\LearnMateAI'
New-Item -ItemType Directory -Force research/results/software-host | Out-Null
Push-Location backend
python -m pytest -ra --junitxml=../research/results/software-host/backend.junit.xml 2>&1 | Tee-Object ../research/results/software-host/backend-tests.log
Pop-Location
Push-Location frontend
npm test 2>&1 | Tee-Object ../research/results/software-host/frontend-tests.log
npm run build 2>&1 | Tee-Object ../research/results/software-host/frontend-build.log
Pop-Location
```

From the authorized Docker host account, prepare the frozen corpus, read-only database/retrieval checks, and API smoke checks. Use a unique run ID. No rebuild/start/retry command is required if current code is already mounted and dependencies installed.

```powershell
.\research\scripts\RUN_NINE_CHAPTER_RESEARCH.ps1 -Phase Prepare -RunId nine_science_01
```

This probes all nine included chapters in dense/lexical/hybrid modes, verifies `/health/live` and `/health/ready`, and checks anonymous document listing returns 401. It saves actual traces as **engineering smoke evidence**, without accuracy metrics. Software unit tests use fixtures/mocks; these host checks provide the separate live API/database/retrieval evidence.

Copy `research/results/nine_science_01/questions.candidates.jsonl` to a separate reviewed dataset, complete human review, then run:

```powershell
.\research\scripts\RUN_NINE_CHAPTER_RESEARCH.ps1 -Phase Evaluate -RunId nine_science_01 -ReviewedDataset '.\research\datasets\nine_chapters\questions.reviewed.jsonl' -Split dev -GenerateAnswers
# Freeze all settings using development evidence before touching test outcomes.
.\research\scripts\RUN_NINE_CHAPTER_RESEARCH.ps1 -Phase Evaluate -RunId nine_science_01 -ReviewedDataset '.\research\datasets\nine_chapters\questions.reviewed.jsonl' -Split test -GenerateAnswers
.\research\scripts\RUN_NINE_CHAPTER_RESEARCH.ps1 -Phase Report -RunId nine_science_01
```

Retrieval outputs: per-query JSON/CSV, P@5, R@5, **MRR@10**, nDCG@10, p50/p95 SQL-retrieval latency, separate embedding/total-query latency. Precision/recall/nDCG averages use answerable records; answerability errors include negative cases. Lexical retrieval does not embed or execute vector SQL; dense retrieval does not execute FTS SQL; hybrid executes both and uses RRF. Fixed conditions: top-k 10, RRF k=60, candidate multiplier=4, configured relevance thresholds, identical reviewed questions and snapshot. This script does not calibrate thresholds. Sequential single-pass timings are descriptive; they do not control cache effects or support speedup claims.

## Answer scoring

Generation uses the production context selection, relevance gate, Llama prompt and citation nodes, with the fixed research scope. Outputs contain exact answer hashes, supplied source contexts, structural audits, failures, and response latency. Structural validity does not establish citation entailment, correctness, or hallucination rates. The implementation's existing `unsupported_claims` structural audit field means evidence is not yet adjudicated and must not be presented as confirmed hallucination.

Have human reviewers assess every successful prediction in `answers.<split>.json`, creating one JSONL record per prediction:

```json
{"id":"existing-question-id","answer_sha256":"copy-the-exact-prediction-hash","provenance":"human","reviewer_id":"actual-reviewer","rationale":"Reviewer-authored assessment","correct":true,"hallucination_present":false,"claims":[{"text":"exact claim from this answer","label":"supported","passage_ids":["supplied-context-chunk-id"]}],"citation_reviews":[{"source_index":1,"supports_claim":true}]}
```

Use only `supported`, `contradicted`, or `unsupported` claim labels. Assess every factual claim and every unique inline reference, including invalid references. Abstentions may have no claims. The example values are schema illustrations, not real judgments. Then:

```powershell
.\research\scripts\RUN_NINE_CHAPTER_RESEARCH.ps1 -Phase ScoreAnswers -RunId nine_science_01 -ReviewedDataset '.\research\datasets\nine_chapters\answers.test.reviewed.jsonl' -Split test
```

This produces correctness, claim faithfulness, contradicted/unsupported counts, citation-support precision, hallucination frequency, and appropriate-abstention agreement, separately recording generation failures. Scores are conditional on successful answers; failures remain visible and should also be reported. No semantic metric is available before actual human review.

## Publication limits

This is a **nine-chapter evaluation**, never a complete thirteen-chapter experiment. Missing chapters introduce selection bias toward documents that ingest successfully. Fifty questions and a 32-question held-out split limit statistical power; curriculum coverage, exhaustive relevance judgments, hardware dependence and cold/warm model state are threats to validity. No educational effectiveness or full-textbook generalization is established. The generated `IEEE_REPORT.md` contains verified host metrics only when available; all pending tables must remain marked unavailable.
