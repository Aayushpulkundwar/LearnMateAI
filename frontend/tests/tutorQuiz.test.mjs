import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import vm from 'node:vm';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { build } from 'esbuild';

const compiled = await build({
  entryPoints: [fileURLToPath(new URL('../src/components/TutorQuiz.tsx', import.meta.url))],
  bundle: true, write: false, format: 'cjs', platform: 'node', external: ['react'],
  plugins: [{ name: 'unused-api', setup(build) {
    build.onResolve({ filter: /api\/client$/ }, () => ({ path: 'api', namespace: 'unused-api' }));
    build.onLoad({ filter: /.*/, namespace: 'unused-api' }, () => ({ contents: 'export const getQuizReview = () => {}; export const submitDiagnostic = () => {};', loader: 'js' }));
  } }],
});
const module = { exports: {} };
vm.runInNewContext(compiled.outputFiles[0].text, { module, exports: module.exports, require: createRequire(import.meta.url) });
const { TutorQuiz } = module.exports;
const attempt = { id: 'test-attempt', status: 'in_progress', questions: Array.from({ length: 10 }, (_, index) => ({
  id: `question-${index}`, question_text: `Textbook question ${index + 1}`, display_order: index + 1,
  options: ['First', 'Second', 'Third', 'Fourth'].map((option_text, number) => ({ id: `option-${index}-${number}`, option_text })),
})) };

test('quiz renders one question, four selectable options, and navigation without exposing keys', () => {
  const html = renderToStaticMarkup(React.createElement(TutorQuiz, { attempt }));
  assert.match(html, /Question 1 of 10/);
  assert.equal((html.match(/type="radio"/g) || []).length, 4);
  assert.match(html, /Previous Question/); assert.match(html, /Next Question/); assert.match(html, /Submit Quiz/);
  assert.ok(!html.includes('Correct answer:'));
  assert.ok(!html.includes('Textbook question 2'));
});

test('submitted attempts offer result recovery instead of answer selection', () => {
  const html = renderToStaticMarkup(React.createElement(TutorQuiz, { attempt: { ...attempt, status: 'submitted' } }));
  assert.match(html, /Quiz submitted/); assert.match(html, /Load results/);
  assert.ok(!html.includes('type="radio"'));
});

const threadCompiled = await build({
  entryPoints: [fileURLToPath(new URL('../src/components/MessageThread.tsx', import.meta.url))],
  bundle: true, write: false, format: 'cjs', platform: 'node', external: ['react'],
});
const threadModule = { exports: {} };
vm.runInNewContext(threadCompiled.outputFiles[0].text, { module: threadModule, exports: threadModule.exports, require: createRequire(import.meta.url) });
const { MessageThread, isNearConversationBottom } = threadModule.exports;

test('rendered conversation places new messages below completed results and retains additional quizzes', () => {
  const review = { result: { total_questions: 1, correct: 0, incorrect: 1, unanswered: 0, accuracy: 0 }, questions: [{
    id: 'old-question', question_text: 'Older quiz question', selected_option_id: 'wrong',
    options: [{ id: 'correct', option_text: 'Correct term', is_correct: true }, { id: 'wrong', option_text: 'Wrong term', is_correct: false }],
    explanation: 'Saved explanation', source_title: 'NCERT Science', chapter_name: 'Chemical Reactions', source_page: 4,
  }] };
  const message = (id, content, sender) => ({ kind: 'message', id, message: { id, content, sender, timestamp: '10:00' } });
  const entries = [message('before', 'Question before quiz', 'user'),
    { kind: 'quiz', id: 'first-quiz', status: 'ready', attempt: { ...attempt, status: 'submitted' }, review },
    message('after', 'Question after quiz', 'user'), message('reply', 'Response after quiz', 'assistant'),
    { kind: 'quiz', id: 'second-quiz', status: 'ready', attempt: { ...attempt, id: 'second-attempt' } }];
  const html = renderToStaticMarkup(React.createElement(MessageThread, {
    entries, followRequest: 1, chatLoading: false, onRetry() {},
    renderQuiz: entry => React.createElement(TutorQuiz, { attempt: entry.attempt, initialReview: entry.review, onExplainQuestion() {} }),
  }));
  let previous = -1;
  for (const text of ['Question before quiz', 'Quiz results', 'Saved explanation', 'Question after quiz', 'Response after quiz', 'Question 1 of 10']) {
    const position = html.indexOf(text); assert.ok(position > previous, `${text} must retain chronological order`); previous = position;
  }
  assert.match(html, /NCERT Science/); assert.match(html, /Page 4/);
  assert.match(html, /Correct answer: Correct term/); assert.match(html, /Your answer: Wrong term/);
  assert.match(html, /Explain question 1/);
});

test('scroll following distinguishes the newest messages from manual review of older content', () => {
  assert.equal(isNearConversationBottom(1000, 400, 600), true);
  assert.equal(isNearConversationBottom(1000, 400, 520), true);
  assert.equal(isNearConversationBottom(1000, 400, 519), false);
  assert.equal(isNearConversationBottom(1000, 400, 0), false);
});
