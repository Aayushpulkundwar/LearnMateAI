# IEEE Research Results — LearnMateAI RAG Comparison

## A. Dataset and experimental setup

The evaluation scope is limited to nine NCERT Class 10 Science chapters (1, 2, 3, 7, 9, 10, 11, 12, 13); it is not a complete 13-chapter evaluation. Chapters 4, 5, 6, and 8 were excluded due to unresolved ingestion failures. The frozen snapshot is `nine_science_03` with SHA-256 `d9c6dd16c44bf402f26e922449c988a4e19d8bf4edd285addb1999d6f8f06bb8` and 643 indexed passages. The selected question set contains 40 candidate questions (18 development, 22 selected held-out); the original 32-question test set remains authoritative. Per-chapter distribution: 1: 5, 2: 5, 3: 5, 7: 5, 9: 4, 10: 4, 11: 4, 12: 4, 13: 4.

The frozen configuration identifies BGE-M3 `bge-m3` (digest `7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab`) and Llama 3 8B `llama3:8b` (digest `365c0bd3c000a25d28ddbf732fe1c6add414de7275464c4e4d1c3b5fcb5d8ad1`). See `system_configuration.json` for implementation paths and the distinction between frozen runtime evidence and source defaults. Retrieval conditions are dense vector similarity, PostgreSQL FTS (not BM25), and the implemented hybrid fusion. No settings were tuned on held-out outcomes.

Human relevance judgments and answer-quality scores are reportable only after independent review and explicit adjudication. Candidate passages and generated answers are not ground truth.

## B. Retrieval findings

Dense, PostgreSQL FTS, and hybrid traces are present and passed frozen-run/schema/allowlist validation: 40/40 successful queries per condition (120 total), 10 ranked chunks per query, no retrieval failures. The traces used randomized condition order with seed 20261030 and no explicit warm-up; cache state was uncontrolled. These are execution checks, not relevance metrics. P@5, R@5, MRR@10, nDCG@10, and the scored comparison table are withheld because the 402-candidate-per-reviewer relevance worksheets are entirely blank and there is no adjudicated `gold.json`.

## C. RAG versus retrieval-free generation

Retrieval-free technical generation completed for 10/10 development questions (`nine-01`, `nine-02`, `nine-07`, `nine-08`, `nine-13`, `nine-14`, `nine-19`, `nine-20`, `nine-25`, `nine-26`) using `llama3:8b` digest `365c0bd3c000a25d28ddbf732fe1c6add414de7275464c4e4d1c3b5fcb5d8ad1`, temperature 0.2. Mean response latency: 8.163 s; median: 7.946 s; p95 (linear interpolation): 13.724 s. These are operational measurements, not answer-quality metrics.

LearnMateAI RAG answers and two-reviewer answer-quality judgments are unavailable; no correctness, faithfulness, explanation-quality, or citation-support scores are claimed.

## D. Technical interpretation and limitations

No comparative effectiveness conclusion is supported by the currently available artifacts. The frozen corpus covers nine chapters selected after four chapter-ingestion failures; this limited coverage and failure-driven chapter selection may create selection bias and limits generalization to the full curriculum. Question labels are currently unverified. This report does not claim that LearnMateAI outperforms commercial assistants.
