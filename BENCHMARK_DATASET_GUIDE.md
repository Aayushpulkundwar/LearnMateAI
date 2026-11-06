# Retrieval Benchmark Dataset and Annotation Guide

This repository intentionally contains no fabricated benchmark labels. Add approved, reviewable data under a versioned directory such as `backend/evaluation/datasets/<dataset-version>/` and run it with `python -m scripts.run_retrieval_benchmark`.

## JSON/JSONL schema

Each line (JSONL) or array member (JSON) must be one of:

```json
{
  "id": "stable-example-id",
  "schema_version": "1.0",
  "split": "dev",
  "question": "Student question copied verbatim",
  "document_id": "document-uuid",
  "chapter_id": "chapter-uuid",
  "topic_id": "topic-uuid",
  "gold_passage_ids": ["chunk-uuid"],
  "answerable": true,
  "filters": {
    "document_id": "document-uuid",
    "grade_id": "grade-uuid",
    "subject_id": "subject-uuid",
    "chapter_id": "chapter-uuid"
  },
  "reference_answer": "A reviewer-authored textbook-grounded answer.",
  "evidence_spans": [{"passage_id": "chunk-uuid", "start_char": 0, "end_char": 42}],
  "claims": [{
    "id": "claim-1",
    "text": "A factual claim from the reference answer.",
    "reviews": [{"reviewer_id": "reviewer-id", "label": "supported", "rationale": "Directly stated on source page 12.", "provenance": "human"}],
    "machine_suggestions": [{"label": "supported", "provenance": "machine"}],
    "adjudication": {"adjudicator_id": "lead-reviewer", "label": "supported", "provenance": "human"}
  }]
}
```

`gold_chunk_ids` is accepted as a backward-compatible alias. `answerable: true` requires at least one gold passage. Unsupported questions use `answerable: false` and an empty gold list.

## Annotation protocol

1. Use only approved textbook material already ingested into the isolated staging environment.
2. Record immutable document/chunk IDs and source page after independently locating the supporting passage.
3. Mark a question answerable only when the passage directly supports a complete textbook-grounded answer; do not use model knowledge as evidence.
4. Assign `dev` and `test` before tuning. Tune thresholds only with `dev`; never move examples after observing test outcomes.
5. Keep `machine_suggestions` separate from `reviews` and `adjudication`; only human adjudications become benchmark ground truth. Require a second reviewer for disputed labels and retain the rationale. Do not place student PII, credentials, or copyrighted full passages in the dataset.
6. Save runner JSON reports beside the dataset version; reports include per-query traces, configurations, metrics, and latency.

## Reproducible commands

```powershell
cd backend
python -m scripts.run_retrieval_benchmark evaluation/datasets/v1/retrieval.jsonl reports/v1-dev.json --split dev --calibrate
python -m scripts.run_retrieval_benchmark evaluation/datasets/v1/retrieval.jsonl reports/v1-test.json --split test
python -m scripts.review_dataset validate evaluation/datasets/v1/retrieval.jsonl
python -m scripts.review_dataset agreement evaluation/datasets/v1/retrieval.jsonl
python -m scripts.review_dataset review evaluation/datasets/v1/retrieval.jsonl --id question-1 --claim-id claim-1 --reviewer reviewer-a --label supported --rationale "Directly stated in the evidence span."
python -m scripts.review_dataset adjudicate evaluation/datasets/v1/retrieval.jsonl --id question-1 --claim-id claim-1 --adjudicator lead-reviewer --label supported --rationale "Resolved after independent review."
python -m scripts.review_dataset export-csv reports/v1-test.json reports/v1-test.csv
```
