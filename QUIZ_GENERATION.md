# Tutor quiz generation

The previous implementation passed a generic generation instruction through the
chat semantic-relevance gate, restricted All Science to the first document, and
returned a hardcoded question after that gate. The Class 10 Science corpus itself
was present: nine completed PDFs, 643 readable embedded chunks, and 1024-dimensional
vectors. The unrelated unmapped database test documents are excluded.

## API contract

`POST /api/v1/query/quiz` requires the existing authenticated student cookie.

```json
{"subject_id":"<Science subject UUID>","num_questions":10}
```

Add `chapter_id` for a chapter quiz. Omit it for All Science. The old optional
`document_id` and chapter-name hints remain accepted and authorized. The grade
always comes from the authenticated student. The question count defaults to 10,
with a maximum of 10; all generated practice questions have medium difficulty.

A successful response is `201` with the existing `AttemptView` shape: `id`,
`status`, `coverage_warning`, and ordered questions containing public option IDs
and text. There are **no answer keys or explanations** in this response.

- Resume: `GET /api/v1/assessments/attempts/{id}`.
- Submit: `POST /api/v1/assessments/attempts/{id}/submit` with the existing
  `answers: [{attempt_question_id, selected_option_id}]` payload.
- Review: `GET /api/v1/assessments/attempts/{id}/results`, available after submission.
  Reviews include score, explanations, correct options, source document/chunk/page,
  textbook title, and chapter name. Access remains restricted to the owner.

## Grounding and persistence

The existing retrieval service samples completed, embedded chunks inside the
authorized grade/subject, interleaving chapters. Chapter mode also accepts a
whole-subject document when its stored chunk label matches the selected normalized
chapter. Unmapped documents and chunks without verified chapter lineage are not
used to invent curriculum associations.

No embeddings are generated for quizzes. Context is capped at 6000 characters.
The existing Ollama integration uses JSON-schema-constrained batches of at most
five questions. The model selects scientific terms and distractors; the server
builds completion MCQs by blanking each term in an exact source sentence.
Pydantic validates candidates; four distinct options, a valid single answer
index, source lineage, verbatim answer evidence, and duplicate checks are required.
Explanations quote actual stored source text rather than trusting a generated
explanation. Four generation rounds share a 300-second
deadline; the frontend has a 310-second request limit.

Practice attempts reuse the assessment tables and deterministic submission path.
Submissions update existing mastery and recommendation services and are idempotent.
Where no curated topic mapping exists, evidence is explicitly labeled **Chapter
practice**. It is chapter-level evidence, not a fine-grained concept diagnosis.
Generated questions remain in `review` status so they do not silently enter the
validated diagnostic question bank. Automated text grounding is not a substitute
for editorial review of question ambiguity or pedagogical difficulty.

No schema migration or new runtime dependency is required. Quiz requests insert
normal practice questions, options, assessments, and attempts; submissions create
the existing answer/evaluation/mastery records.

## Ingestion recovery

An empty extraction is now a failed ingestion rather than a completed empty
document. The existing ingestion worker retains its advisory lock, atomic chunk
replacement, and completed-document no-op protection.

To retry selected failed or pending uploads that have been unclaimed for over
15 minutes, run from an interactive local/staging terminal:

```powershell
docker compose exec api python -m scripts.retry_failed_documents <document-id>
```

Inspect the database identity and selected documents, then type `RETRY_FAILED`.
The script waits for each selected task before dispatching another. It never
restarts active processing, uploads a duplicate PDF, or assigns curriculum IDs.
Four existing Class 10 chapter PDFs were failed at inspection and are excluded
from quizzes until their ingestion is repaired. They are not automatically retried.

## Reproducible verification

```powershell
docker compose exec -e RUN_QUIZ_INTEGRATION=1 api python -m unittest tests.test_tutor_quiz -v
docker compose exec api python -m scripts.verify_tutor_quiz
docker compose exec api python -m scripts.verify_tutor_quiz --chapter-number 1
cd frontend
npm test
npm run build
```

The integration suite uses real local PostgreSQL and controlled model responses
to exercise authorization, missing/processing/empty content, both scopes,
whole-book chapter labels, bounded retries/timeouts, scoring, answer-key privacy,
citations, and mastery idempotency. The smoke script instead calls the actual
Ollama model and existing NCERT corpus. Both roll back their test database writes.
CPU-only inference can take several minutes or reach the bounded deadline.

### Results from this implementation

- 58 backend unit/integration tests passed, plus 12 existing citation and grounded-generation tests.
- 6 frontend tests passed; TypeScript and the production Vite build passed.
- Live Ollama + existing NCERT corpus: a 10-question All Science quiz passed generation,
  answer-key privacy, 100% scoring with known correct answers, source references,
  mastery updates across six chapters, and idempotent resubmission.
- Live Ollama + NCERT Chapter 1: the same checks passed for a 10-question chapter quiz.
- Postman authentication checks: both assertions passed against the expected HTTP 401
  response (the CLI reports exit 1 for this deliberately unauthorized HTTP request).
- Raw PDF storage, 643 readable chunks, and 1024-dimensional embeddings were verified.
- No temporary test accounts or isolated test grades remained after the rollback checks.
- Browser visual/click verification could not run because the browser access host
  and native computer-use connection were unavailable; UI rendering was checked
  with the real React components in the frontend test suite.

## Files changed for this fix

- `backend/app/api/routes/query.py`
- `backend/app/api/routes/assessments.py`
- `backend/app/schemas/query.py`
- `backend/app/schemas/assessment.py`
- `backend/app/schemas/__init__.py`
- `backend/app/services/tutor_quiz_service.py` (new)
- `backend/app/services/retrieval_service.py`
- `backend/app/services/llm_service.py`
- `backend/app/tasks/ingestion.py`
- `backend/scripts/retry_failed_documents.py`
- `backend/scripts/verify_tutor_quiz.py` (new)
- `backend/tests/test_tutor_quiz.py` (new)
- `backend/tests/test_llm_service.py`
- `backend/tests/test_ingestion_embeddings.py`
- `backend/tests/tutor_quiz_auth.postman.js` (new)
- `frontend/src/App.tsx`
- `frontend/src/components/TutorQuiz.tsx` (new)
- `frontend/src/components/MessageThread.tsx`
- `frontend/src/api/client.ts`
- `frontend/src/types/index.ts`
- `frontend/src/index.css`
- `frontend/tests/tutorQuiz.test.mjs` (new)
- `QUIZ_GENERATION.md` (new)
