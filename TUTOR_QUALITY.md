# Tutor quality and explanation depth

## Findings

The frontend already transmitted the normal chat depth selection. The backend only populated tutoring preferences for requests with a study-topic ID; ordinary subject chat left them empty and generation fell back to Standard. Even where preferences arrived, the prompt only asked for a named depth, without teaching instructions, the authenticated student's grade, or a distinct output budget. Mastery guidance could also conflict with a Detailed request. Retrying a failed chat retained its old depth even after the selector changed.

The generic context-only prompt emphasized restriction over teaching and did not discourage copying or context introductions. Citation cards included all supplied passages even when the answer did not reference them. There was no evidence that the recent quiz implementation replaced the tutor prompt; quiz JSON options are request-specific.

Hybrid retrieval treated question boilerplate as full-text search terms. Positive but negligible lexical scores admitted weak context. Exercises could outrank explanatory prose. Context metadata could retain text outside the actual displayed budget.

## Implementation

Depth is a validated `brief | standard | detailed` value. An omitted value defaults to Standard; invalid values, including explicit null, return 422. Authorized grade and selected depth reach the generation prompt for every ordinary chat, regardless of mastery metadata. Retries use the current selection.

Teacher instructions request a direct, grade-appropriate explanation in the model's own words, supported examples, careful attribution, explicit evidence limitations, and no invented facts or equations. Brief aims for 40–80 words; Standard 120–220; Detailed 250–450. These are generation instructions, never output truncation or padding.

Tutor generation uses temperature 0.2, context window 8192, and output budgets 256/512/1024 tokens respectively. Native model stops and the configured local model remain unchanged. The observed runtime model is **llama3:8b**, despite the requested project description naming Llama 3.1. Quiz JSON still uses its existing 4096/2400 budget. Generation has at most two attempts within one existing 300-second deadline. Repairs receive the original evidence and specific validation feedback, rather than anchoring on potentially unsupported prose in a rejected draft. No fallback answer is fabricated.

Checks reject whole-passage copying, invalid/missing citation labels, context introductions, and detectable unbalanced chemical equations presented as balanced. Reaction equations must cite passages containing their actual species. These checks are structural safeguards, **not a general semantic entailment or scientific correctness proof**.

Tutor-only retrieval reuses BGE-M3, PostgreSQL full-text search, pgvector, and RRF. It removes question boilerplate from the lexical query and prioritizes explanatory passages inside the existing candidate pool. Original questions still reach embeddings. Top-K remains 5, candidate multiplier 4, dense relevance threshold 0.55, lexical threshold 0.08. Completed/embedded documents and existing grade, subject, chapter and document restrictions apply. No schema, corpus, model, authentication, quiz retrieval, or embeddings were changed.

Exact duplicate context is removed; weak lexical noise no longer bypasses context selection. Source metadata reflects only visible evidence. Cards contain only referenced passages and retain the actual source number, document/chapter/page and measured cosine score, including lexical-only matches.

## Measured retrieval

`backend/verification/tutor_retrieval.json` records the five real questions against Class 10 Science using the same query embeddings before and after the change. Rankings are measured observations, not human relevance labels.

| Question | Observed result |
|---|---|
| Chemical reaction | Definition page 1 remains first; lexical score improves from 0.049 to 0.241. |
| Photosynthesis | Removing boilerplate finds a passage at the existing lexical threshold; available evidence is limited to Our Environment. |
| Acids and bases | Introductory comparison page 1 replaces soap discussion page 17 at the top. |
| Magnesium in oxygen | Chemical Reactions explanatory passages replace weakly matched Metals context. |
| Displacement | Explanatory page 11 replaces an exercise on page 16 at the top. |

## Files changed for this task

- `backend/app/api/routes/query.py`: propagate authenticated grade and selected mode.
- `backend/app/schemas/query.py`: validate the three supported modes.
- `backend/app/graph/nodes.py`: educational retrieval, teacher prompts, bounded repair, referenced-only citations.
- `backend/app/services/tutor_prompt.py`: grade-aware depth profiles.
- `backend/app/services/tutor_answer_quality.py`: synthesis, citation and reaction-equation safeguards.
- `backend/app/services/retrieval_quality.py`: lexical normalization and explanatory-prose ranking.
- `backend/app/services/retrieval_service.py`: opt-in tutor ranking and real cosine scores for lexical-only matches.
- `backend/app/services/context_selection.py`: deduplication and meaningful lexical support.
- `backend/app/services/grounded_context.py`: accurate visible context and source numbering.
- `backend/app/services/llm_service.py`: per-request generation budgets, preserving quiz defaults.
- `frontend/src/App.tsx`, `frontend/src/state/tutorConversation.ts`: retain question context while respecting the current retry depth.
- `frontend/tests/tutorConversation.test.mjs`: depth selection during chat, after quizzes, and on retry.
- `backend/tests/test_tutor_depth.py`, `backend/tests/test_tutor_depth_api.py`: deterministic depth, prompt, authorization, copying, citation, equation and real database/API regressions with mocked external model calls.
- `backend/tests/test_grounded_generation.py`, `backend/tests/test_context_selection.py`, `backend/tests/test_llm_service.py`: update grounded fixtures and verify context/budget contracts.
- `backend/scripts/verify_tutor_depth.py`: reproducible real retrieval and authenticated live Ollama checks; temporary accounts and sessions roll back.
- `backend/tests/tutor_depth.postman.js`: running OpenAPI contract assertions.
- `backend/verification/tutor_retrieval.json`, `backend/verification/tutor_live_depths.json`, `backend/verification/tutor_live_others.json`: actual verification output when each command is run.
- `TUTOR_QUALITY.md`: this report. Other pre-existing workspace changes belong to earlier work.

## Verification

Backend regression suite: 99 tests passed with `RUN_TUTOR_INTEGRATION=1 RUN_QUIZ_INTEGRATION=1`. External LLM responses are mocked in this suite; authorization and assessment tests use PostgreSQL. Expected failure-path logs are intentional tests.

Frontend: 24 tests passed; `npm run build` passed. Covered ordinary questions, completed quizzes, follow-ups, multiple quizzes, retry recovery, retained results, and all depth payload values. No real browser interaction is claimed.

Live results are recorded separately in the verification JSON files; final observations are appended below after the final run.

Reproduce retrieval with `docker compose exec -T api python -m scripts.verify_tutor_depth`. Run live depth checks with `--live depths`, and the other four concepts with `--live others`. These commands use the real configured models, not fixtures. `--depth brief|standard|detailed` rechecks one mode while preserving the other recorded results. Earlier failed calibration responses are retained in `backend/verification/tutor_depth_calibration_failed.json` rather than presented as successful verification.

## Limitations

Local CPU inference is slow and a repair can approach the existing timeout. The model can still misattribute a prose claim or omit useful detail; structural validation cannot prove every statement follows from its source. Some PDFs remain failed, including Life Processes, so a full photosynthesis mechanism cannot be grounded from that chapter. Existing SSE delivery still follows completed generation rather than native token streaming. Browser UI testing was unavailable in this environment. No new dependencies or database migrations were needed.
