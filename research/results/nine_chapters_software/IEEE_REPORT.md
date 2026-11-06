# LearnMateAI: A Controlled RAG Evaluation Protocol for Nine Class 10 Science Chapters

## Abstract

LearnMateAI combines BGE-M3 embeddings, PostgreSQL dense and full-text retrieval, reciprocal-rank fusion, and Llama 3 8B generation. This record presents verified software testing and a reproducible protocol for a nine-chapter evaluation. Chapters 1, 2, 3, 7, 9, 10, 11, 12, and 13 are included. Chapters 4, 5, 6, and 8 are excluded because of unresolved ingestion failures. No complete thirteen-chapter evaluation is claimed. Retrieval and semantic answer-quality measurements remain pending host execution and human judgments.

## I. Corpus

The project owner reports nine completed documents, 643 indexed chunks, and 1024-dimensional embeddings. The supplied registration manifest identifies the approved documents below. Per-chapter chunk counts and a data/vector corpus fingerprint must be verified and exported by the read-only host freeze; no values have been inferred from the total.

| Chapter | Approved document ID | Per-document chunks |
| --- | --- | --- |
| 1 | 6b418b53-971c-4547-b4ac-e0eae9fdff92 | Pending host verification |
| 2 | 93116cc1-6a00-4968-9268-59db13424b09 | Pending host verification |
| 3 | 4a8d4852-5979-45ca-b5b2-44b994ec2385 | Pending host verification |
| 7 | 1360321a-7a0d-417a-a1d4-560a635693e1 | Pending host verification |
| 9 | a92321fa-f136-4203-95e3-550530be58f7 | Pending host verification |
| 10 | 925e4a60-1e33-4394-a333-485a7682e584 | Pending host verification |
| 11 | c9981302-fda6-45bc-ab4e-c142379f0035 | Pending host verification |
| 12 | c71bbe0c-0206-4a2c-bb13-d6fa2802f9b4 | Pending host verification |
| 13 | 672dfbdf-af01-4c86-9321-f034f6d25aa9 | Pending host verification |

## II. Methods

The research runner filters SQL candidate generation by both an immutable document allowlist and a frozen chunk-ID set. Subsequent completion or indexing of an excluded chapter cannot admit it into retrieval. Snapshot fingerprints include every included chunk's text, page metadata, ID, and vector fingerprint. A changed snapshot invalidates evaluation. The workflow performs no ingestion, retry, migration, deletion, or database write.

Fifty machine-authored candidate questions are supplied with 18 development and 32 test records. All require human verification of source coverage, answerability, reference answers, relevance judgments and evidence spans. Candidate passage suggestions are not verified gold. Human reviewers must assess the included corpus for additional relevant passages. No held-out tuning is performed by the runner.

Dense, lexical and hybrid modes use the same questions, snapshot and top-k=10. Dense executes vector SQL only; lexical executes full-text SQL only; hybrid uses both with RRF. P@5, R@5, MRR@10 and nDCG@10 use binary human relevance labels. Per-query retrieval, embedding and total latency are separately exported; p50/p95 are empirical interpolated quantiles. Single-pass latency remains sensitive to caching and query order.

## III. Software Evidence

Backend regression suite: **134 passed in 4.03 seconds**, recorded in the accompanying JUnit XML and test log. These cover authentication, authorization, ingestion, extraction, retrieval, citation logic, and research scope safeguards using local fixtures/mocks. Frontend regression tests: 2 passed. Production frontend build: passed with Vite 5.4.21 in 2.84 seconds. Live API/database checks are pending host execution and must be reported separately.

Environment: Windows 11 build 26200; Python 3.14.4. Base code revision: `2788f3ef56f5bc261d4081dbc859c831c6ff4646`; the worktree contains uncommitted changes. A revision alone does not identify the modified experiment code; the host runner also exports its diff and settings.

## IV. Research Results

| Measurement | Evidence status |
| --- | --- |
| Precision@5 / Recall@5 / MRR@10 / nDCG@10 | Unavailable: human relevance review and live run pending |
| Retrieval latency p50 / p95 | Unavailable: live run pending |
| Correctness / faithfulness / hallucination frequency | Unavailable: exact generated answers require human review |
| Citation support precision | Unavailable: human claim-to-source judgments pending |
| Appropriate abstention / response latency | Unavailable: reviewed answerability and live predictions pending |

No zero-valued accuracy, fabricated confidence interval, or inferred generation outcome is reported.

## V. Threats to Validity

The evaluation covers nine of thirteen chapters, selected by successful ingestion. This selection may favor simpler document layouts or different scientific topics; results cannot be generalized to failed chapters. A 50-question sample and 32-question held-out subset limit precision and statistical power. Incomplete relevance judgments bias recall estimates. Software fixture success does not establish factual answer quality, citation entailment, educational benefit, or live operational reliability. Hardware, cache state, model loading and generation variability affect latency. Human reviews must remain independent of test-set tuning.

## VI. Reproducibility

Use `research/NINE_CHAPTER_PROTOCOL.md` for exact Windows PowerShell commands. Host preparation exports `corpus.json`, `environment.json`, `ollama_models.json`, candidate source references, API/database/retrieval smoke traces, and an updated IEEE report. Reviewed evaluation adds JSON/CSV predictions and aggregate metrics. Human answer scoring adds semantic-quality metrics only after explicit review of exact answer hashes.
