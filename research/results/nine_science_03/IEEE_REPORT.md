# LearnMateAI: Retrieval Evaluation on Nine Class 10 Science Chapters

## Abstract

This bounded study covers chapters 1, 2, 3, 7, 9, 10, 11, 12, and 13. Chapters 4, 5, 6, and 8 are excluded because of unresolved ingestion failures. This is not a complete 13-chapter evaluation.

## I. Corpus and protocol

Corpus SHA-256: `d9c6dd16c44bf402f26e922449c988a4e19d8bf4edd285addb1999d6f8f06bb8`. Nine allowlisted documents, 643 chunks, 1024-dimensional embeddings. Both document and frozen chunk IDs constrain SQL candidates before ranking. No excluded document is queried or retried.

| Chapter | Document ID | Chunks | Dimension |
| --- | --- | ---: | ---: |
| 1 | 6b418b53-971c-4547-b4ac-e0eae9fdff92 | 44 | 1024 |
| 2 | 93116cc1-6a00-4968-9268-59db13424b09 | 83 | 1024 |
| 3 | 4a8d4852-5979-45ca-b5b2-44b994ec2385 | 84 | 1024 |
| 7 | 1360321a-7a0d-417a-a1d4-560a635693e1 | 68 | 1024 |
| 9 | a92321fa-f136-4203-95e3-550530be58f7 | 124 | 1024 |
| 10 | 925e4a60-1e33-4394-a333-485a7682e584 | 45 | 1024 |
| 11 | c9981302-fda6-45bc-ab4e-c142379f0035 | 99 | 1024 |
| 12 | c71bbe0c-0206-4a2c-bb13-d6fa2802f9b4 | 57 | 1024 |
| 13 | 672dfbdf-af01-4c86-9321-f034f6d25aa9 | 39 | 1024 |

## II. Retrieval results

Gold passages require human review. Reference answers and evidence spans must come only from the frozen included corpus. Dev/test splits are fixed before evaluation; this runner performs no threshold tuning.

No reviewed benchmark was executed; retrieval metrics are unavailable.

## III. Answer evaluation

Generated answers and source contexts are saved for human assessment of correctness, claim support, contradictions, hallucinations, and citation entailment. Structural source-reference checks alone cannot establish factual correctness. Semantic quality metrics remain unavailable until those exact predictions are reviewed.

## IV. Software verification

Keep software test logs and API/database smoke results separate from research accuracy. See host execution logs; this report does not infer live test success.

## V. Threats to validity

Excluding four chapters introduces selection bias toward successfully parsed material and limits curricular coverage. Fifty questions yield limited statistical power. Incomplete relevance judgments can underestimate recall. Single-pass timings depend on caching, query order, hardware and model load. Lexical latency excludes embeddings; embedding/total latency are separate traces. No claim extends to the full textbook or educational learning gains.
