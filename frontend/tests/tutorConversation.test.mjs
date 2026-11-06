import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { transform } from 'esbuild';

const source = await readFile(new URL('../src/state/tutorConversation.ts', import.meta.url), 'utf8');
const { code } = await transform(source, { loader: 'ts', format: 'esm', target: 'es2020' });
const { createTutorConversation, isQuizRequest } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
const scope = { studentId: 'student-1', subject_id: 'science-10', chapter_id: undefined };
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };
const storage = () => { const values = new Map(); return { getItem: key => values.get(key) || null, setItem: (key, value) => values.set(key, value), values }; };
const citation = { document_id: 'ncert', document_title: 'NCERT Science', page_number: 4, snippet: 'Textbook evidence', similarity_score: .88 };
const response = question => ({ question, answer: `Tutor answer: ${question}`, citations: [citation], is_refused: false });
const attempt = number => ({ id: `attempt-${number}`, status: 'in_progress', questions: [1, 2, 3].map(index => ({
  id: `aq-${number}-${index}`, question_text: `Textbook question ${index}`, display_order: index,
  options: ['Correct term', 'Incorrect term', 'Other term', 'Another term'].map((option_text, option) => ({ id: `option-${index}-${option}`, option_text })),
})) });
const review = number => ({ result: { total_questions: 3, correct: 2, incorrect: 1, unanswered: 0, accuracy: 66.67 }, questions: attempt(number).questions.map((item, index) => ({
  ...item, selected_option_id: item.options[index === 2 ? 1 : 0].id,
  options: item.options.map((option, index) => ({ ...option, is_correct: index === 0 })),
  explanation: 'Textbook evidence: chemical reactions produce new substances.', source_document_id: 'ncert', source_chunk_id: `chunk-${index}`,
  source_title: 'NCERT Science', chapter_name: 'Chemical Reactions and Equations', source_page: 4,
})) });
function setup(overrides = {}, saved = storage(), selectedScope = scope) {
  const calls = { query: [], quiz: [], summarize: [] };
  let number = 0;
  const api = {
    query: async request => { calls.query.push(request); return response(request.question); },
    quiz: async request => { calls.quiz.push(request); return attempt(++number); },
    summarize: async request => { calls.summarize.push(request); return { summary: 'Summary', key_takeaways: ['Key point'], citations: [citation] }; },
    getAttempt: async () => attempt(1), ...overrides,
  };
  return { store: createTutorConversation(selectedScope, api, saved), calls, api, saved };
}
const quizzes = store => store.getSnapshot().entries.filter(entry => entry.kind === 'quiz');
const messages = store => store.getSnapshot().entries.filter(entry => entry.kind === 'message');

test('question → quiz → results → question → incorrect-answer explanation → another quiz preserves ordered history', async () => {
  const { store, calls, saved, api } = setup();
  await store.ask('What is a chemical reaction?');
  await store.generate();
  const first = quizzes(store)[0];
  store.reviewed(first.id, review(1)); // Same callback used after the existing submit/results API completes.
  await store.ask('What is a balanced equation?');
  const after = store.getSnapshot().entries;
  assert.equal(after[2].id, first.id);
  assert.equal(after[3].message.content, 'What is a balanced equation?');
  assert.match(after[4].message.content, /Tutor answer/);
  await store.ask('Explain question 3.', 'detailed');
  const request = calls.query.at(-1);
  assert.equal(request.document_id, 'ncert');
  assert.equal(request.subject_id, 'science-10');
  assert.equal(request.explanation_depth, 'detailed');
  assert.match(request.question, /Textbook question 3/);
  assert.match(request.question, /Student's answer: Incorrect term/);
  assert.match(request.question, /Graded answer: Correct term/);
  await store.ask('Give me another quiz');
  assert.equal(quizzes(store).length, 2);
  assert.equal(quizzes(store)[0].review.result.accuracy, 66.67);
  assert.equal(quizzes(store)[1].attempt.id, 'attempt-2');
  assert.equal(calls.quiz.length, 2);
  assert.equal(calls.query.length, 3);
  assert.deepEqual(messages(store)[1].message.citations, [citation]);
  assert.equal(store.getSnapshot().chatLoading, false);
  assert.equal(store.getSnapshot().quizLoading, false);
  const restored = createTutorConversation(scope, api, saved);
  assert.equal(quizzes(restored).length, 2);
  assert.equal(quizzes(restored)[0].review.questions[2].source_page, 4);
  assert.equal(messages(restored)[0].message.content, 'What is a chemical reaction?');
});

test('chat works while quiz generation is pending; duplicate generation is ignored', async () => {
  const pending = deferred(); let quizCalls = 0;
  const { store } = setup({ quiz: async () => { quizCalls++; return pending.promise; } });
  const generation = store.generate();
  assert.equal(store.getSnapshot().quizLoading, true);
  assert.equal(store.getSnapshot().chatLoading, false);
  await store.generate();
  await store.ask('What is rusting?');
  assert.equal(store.getSnapshot().quizLoading, true);
  assert.equal(quizCalls, 1);
  assert.equal(store.getSnapshot().entries[1].message.content, 'What is rusting?');
  assert.match(store.getSnapshot().entries[2].message.content, /Tutor answer/);
  pending.resolve(attempt(1)); await generation;
  assert.equal(store.getSnapshot().entries[0].attempt.id, 'attempt-1');
  assert.equal(store.getSnapshot().quizLoading, false);
});

test('duplicate sends are suppressed synchronously, while the quiz button remains independent', async () => {
  const pending = deferred(); let queryCalls = 0;
  const { store } = setup({ query: async () => { queryCalls++; return pending.promise; } });
  const sent = store.ask('First question');
  await store.ask('First question');
  assert.equal(queryCalls, 1);
  assert.equal(store.getSnapshot().chatLoading, true);
  await store.generate();
  assert.equal(quizzes(store).length, 1);
  pending.resolve(response('First question')); await sent;
  assert.equal(store.getSnapshot().chatLoading, false);
  assert.equal(messages(store).length, 2);
});

test('quiz failure never locks chat; retry keeps the original timeline position', async () => {
  let count = 0;
  const { store } = setup({ quiz: async () => { if (++count === 1) throw new Error('model failure'); return attempt(2); } });
  await store.generate();
  const failed = quizzes(store)[0];
  assert.equal(failed.status, 'error');
  assert.equal(store.getSnapshot().quizLoading, false);
  await store.ask('Explain oxidation');
  await store.retry(failed.id);
  assert.equal(store.getSnapshot().entries[0].id, failed.id);
  assert.equal(store.getSnapshot().entries[0].attempt.id, 'attempt-2');
  assert.equal(quizzes(store).length, 1);
  assert.equal(messages(store).length, 2);
});

test('a failed additional quiz preserves the earlier score, answers, and references', async () => {
  let count = 0;
  const { store } = setup({ quiz: async () => { if (++count === 2) throw new Error('model failure'); return attempt(1); } });
  await store.generate(); const first = quizzes(store)[0]; store.reviewed(first.id, review(1));
  await store.generate();
  assert.equal(quizzes(store)[0].review.result.accuracy, 66.67);
  assert.equal(quizzes(store)[0].review.questions[2].source_document_id, 'ncert');
  assert.equal(quizzes(store)[1].status, 'error');
  await store.ask('Continue our conversation');
  assert.equal(store.getSnapshot().entries.at(-1).message.isRefused, false);
  assert.equal(store.getSnapshot().entries[0].id, first.id);
});

test('chat failure resets the lock; retry replaces the failed reply and later questions still work', async () => {
  let count = 0;
  const { store } = setup({ query: async request => { if (++count === 1) throw new Error('offline'); return response(request.question); } });
  await store.ask('What is a reaction?');
  const failed = messages(store)[1];
  assert.ok(failed.retry);
  assert.equal(store.getSnapshot().chatLoading, false);
  await store.retry(failed.id);
  assert.equal(messages(store).length, 2);
  assert.equal(messages(store)[1].id, failed.id);
  assert.equal(messages(store)[1].retry, undefined);
  await store.ask('What is corrosion?');
  assert.equal(messages(store).length, 4);
  assert.equal(store.getSnapshot().chatLoading, false);
});

test('reviewing an older quiz explains that quiz rather than silently switching to the latest one', async () => {
  const { store, calls } = setup();
  await store.generate(); const first = quizzes(store)[0]; store.reviewed(first.id, review(1));
  await store.generate(); const second = quizzes(store)[1];
  const secondReview = review(2); secondReview.questions[2].question_text = 'A different question';
  store.reviewed(second.id, secondReview);
  await store.ask('Explain question 3.', 'standard', first.id);
  assert.match(calls.query.at(-1).question, /Textbook question 3/);
  assert.ok(!calls.query.at(-1).question.includes('A different question'));
  await store.ask('Explain my incorrect answer');
  assert.match(calls.query.at(-1).question, /A different question/);
});

test('natural-language quiz commands use the same quiz API; ordinary questions do not', async () => {
  const { store, calls } = setup();
  for (const text of ['Generate a quiz on chemical reactions', 'Give me another quiz', 'Can you create a quiz?']) {
    assert.equal(isQuizRequest(text), true); await store.ask(text);
  }
  assert.equal(calls.quiz.length, 3);
  assert.equal(calls.query.length, 0);
  for (const text of ['Explain question 3', 'What is a quiz?', 'What is a chemical reaction?']) assert.equal(isQuizRequest(text), false);
  await store.ask('   ');
  assert.equal(calls.query.length, 0);
});

test('summary failure and overlapping summary requests cannot lock chat or quiz state', async () => {
  const pending = deferred();
  const { store } = setup({ summarize: async () => pending.promise });
  const summary = store.summarize('ncert');
  await store.ask('Another textbook question');
  await store.generate();
  assert.equal(store.getSnapshot().summaryLoading, true);
  assert.equal(store.getSnapshot().chatLoading, false);
  pending.reject(new Error('summary failed')); await summary;
  assert.equal(store.getSnapshot().summaryLoading, false);
  assert.equal(quizzes(store).length, 1);
  await store.ask('Continue after failure');
  assert.match(messages(store).at(-1).message.content, /Tutor answer/);
});

test('storage failures do not prevent conversation; histories are isolated by student and scope', async () => {
  const unavailable = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('quota'); } };
  const { store } = setup({}, unavailable);
  await store.ask('Hello'); await store.generate();
  assert.equal(store.getSnapshot().entries.length, 3);
  const saved = storage(); const first = setup({}, saved);
  await first.store.ask('Private student conversation');
  assert.equal(setup({}, saved, { ...scope, studentId: 'another-student' }).store.getSnapshot().entries.length, 0);
  assert.equal(setup({}, saved, { ...scope, chapter_id: 'another-chapter' }).store.getSnapshot().entries.length, 0);
});

test('responses from an old scope instance cannot overwrite a reopened conversation history', async () => {
  const pending = deferred(); const saved = storage();
  const old = setup({ query: async () => pending.promise }, saved);
  const sent = old.store.ask('Old pending question');
  const reopened = setup({}, saved);
  assert.equal(reopened.store.getSnapshot().chatLoading, false);
  await reopened.store.ask('New question');
  pending.resolve(response('Old pending question')); await sent;
  const restored = createTutorConversation(scope, reopened.api, saved);
  assert.ok(messages(restored).some(entry => entry.message.content === 'New question'));
});

test('an unused render-time store does not take ownership from a committed conversation', async () => {
  const pending = deferred(); const saved = storage();
  const current = setup({ query: async () => pending.promise }, saved);
  const sent = current.store.ask('Current question');
  setup({}, saved); // React may discard a render or invoke a memo factory twice.
  pending.resolve(response('Current question')); await sent;
  const restored = createTutorConversation(scope, current.api, saved);
  assert.match(messages(restored).at(-1).message.content, /Tutor answer/);
});

test('legacy attempt recovery is ownership checked and cannot remove current messages', async () => {
  const saved = storage(); saved.setItem('learnmate_quiz:science-10:all', 'old-attempt');
  const pending = deferred(); const { store } = setup({ getAttempt: async () => pending.promise }, saved);
  const restoration = store.restoreLegacyQuiz();
  await store.ask('Current question');
  pending.resolve(attempt(1)); await restoration;
  assert.equal(messages(store).length, 2); assert.equal(quizzes(store).length, 1);
  assert.equal(store.getSnapshot().entries[0].kind, 'quiz');
  const denied = setup({ getAttempt: async () => { throw new Error('not owned'); } }, saved, { ...scope, studentId: 'different-student' });
  await denied.store.restoreLegacyQuiz();
  assert.equal(quizzes(denied.store).length, 0);
});

test('only explicit sends request forced scrolling; replies and review updates do not', async () => {
  const pending = deferred(); const { store } = setup({ query: async () => pending.promise });
  const sent = store.ask('Question'); const requested = store.getSnapshot().followRequest;
  pending.resolve(response('Question')); await sent;
  assert.equal(store.getSnapshot().followRequest, requested);
  await store.generate(); const quiz = quizzes(store)[0]; const afterQuiz = store.getSnapshot().followRequest;
  store.reviewed(quiz.id, review(1));
  assert.equal(store.getSnapshot().followRequest, afterQuiz);
});

test('all depth selections survive normal chat and post-quiz follow-ups', async () => {
  const { store, calls } = setup();
  for (const depth of ['brief', 'standard', 'detailed']) {
    await store.ask('What is a chemical reaction?', depth);
    assert.equal(calls.query.at(-1).explanation_depth, depth);
  }
  await store.generate(); const quiz = quizzes(store)[0]; store.reviewed(quiz.id, review(1));
  for (const depth of ['brief', 'standard', 'detailed']) {
    await store.ask('Explain question 3.', depth);
    assert.equal(calls.query.at(-1).explanation_depth, depth);
    assert.equal(calls.query.at(-1).document_id, 'ncert');
  }
  assert.equal(quizzes(store)[0].review.result.accuracy, 66.67);
});

test('retry uses the currently selected depth while retaining the failed question context', async () => {
  let count = 0; const requests = [];
  const { store } = setup({ query: async request => { requests.push(request); if (++count === 1) throw new Error('offline'); return response(request.question); } });
  await store.ask('What is a chemical reaction?', 'detailed');
  await store.retry(messages(store)[1].id, 'brief');
  assert.equal(requests[0].explanation_depth, 'detailed');
  assert.equal(requests[1].explanation_depth, 'brief');
  assert.equal(requests[1].question, 'What is a chemical reaction?');
});
