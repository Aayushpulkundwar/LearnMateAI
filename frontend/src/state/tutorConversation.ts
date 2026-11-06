import type { AssessmentAttempt, Message, QueryRequest, QueryResponse, QuizRequest, QuizReview, SummarizeRequest, SummarizeResponse } from '../types';

export type TextEntry = { kind: 'message'; id: string; message: Message; pending?: boolean; retry?: QueryRequest };
export type QuizEntry = { kind: 'quiz'; id: string; status: 'generating' | 'ready' | 'error'; request?: QuizRequest; attempt?: AssessmentAttempt; review?: QuizReview; error?: string };
export type ConversationEntry = TextEntry | QuizEntry;
export type ConversationState = {
  entries: ConversationEntry[]; chatLoading: boolean; quizLoading: boolean; summaryLoading: boolean;
  chatError: string | null; quizError: string | null; summaryError: string | null; followRequest: number;
};
type Storage = Pick<globalThis.Storage, 'getItem' | 'setItem'>;
type Dependencies = {
  query: (request: QueryRequest) => Promise<QueryResponse>;
  quiz: (request: QuizRequest) => Promise<AssessmentAttempt>;
  summarize: (request: SummarizeRequest) => Promise<SummarizeResponse>;
  getAttempt: (id: string) => Promise<AssessmentAttempt>;
};
type Scope = { subject_id?: string; chapter_id?: string; studentId: string };
let sequence = 0;
const storageOwners = new Map<string, symbol>();
const id = () => `tutor-${Date.now()}-${++sequence}`;
const failure = (error: any, fallback: string) => typeof error?.response?.data?.detail === 'string' ? error.response.data.detail : fallback;

export function isQuizRequest(text: string): boolean {
  return /^(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?(?:generate|create|make|start|give|prepare)\b[^?]*\bquiz\b/i.test(text.trim());
}

export function quizReviewContext(question: string, entries: ConversationEntry[], quizId?: string): Partial<QueryRequest> {
  const quiz = [...entries].reverse().find((entry): entry is QuizEntry => entry.kind === 'quiz' && !!entry.review && (!quizId || entry.id === quizId));
  if (!quiz?.review) return {};
  const reference = question.match(/\b(?:question|q)\s*#?\s*(\d+)\b/i);
  const index = reference ? Number(reference[1]) - 1 : /\b(incorrect|wrong|mistake)\b/i.test(question)
    ? quiz.review.questions.findIndex(item => !item.options.some(option => option.id === item.selected_option_id && option.is_correct)) : -1;
  const item = quiz.review.questions[index];
  if (!item) return {};
  const selected = item.options.find(option => option.id === item.selected_option_id)?.option_text || 'Unanswered';
  const correct = item.options.find(option => option.is_correct)?.option_text || '';
  return {
    document_id: item.source_document_id || undefined,
    question: `${question}\n\nThe student is reviewing question ${index + 1} of a submitted quiz. Verify and explain using the retrieved textbook passages, with citations.\nQuiz question: ${item.question_text}\nStudent's answer: ${selected}\nGraded answer: ${correct}\nTextbook reference: ${item.source_title || ''}, ${item.chapter_name || ''}, page ${item.source_page ?? 'unknown'}.\nSaved textbook evidence: ${item.explanation || ''}`,
  };
}

/** One ordered conversation; independent request flags, with no React closure locks. */
export function createTutorConversation(scope: Scope, api: Dependencies, storage?: Storage) {
  const key = `learnmate_conversation:${scope.studentId}:${scope.subject_id || ''}:${scope.chapter_id || 'all'}`;
  const legacyKey = `learnmate_quiz:${scope.subject_id || ''}:${scope.chapter_id || 'all'}`;
  const owner = Symbol(key);
  let activated = false;
  const activate = () => { activated = true; storageOwners.set(key, owner); };
  let restored: ConversationEntry[] = [];
  try {
    const saved = JSON.parse(storage?.getItem(key) || '[]');
    if (Array.isArray(saved)) restored = saved.filter(entry => entry && typeof entry.id === 'string' && (
      entry.kind === 'message' && typeof entry.message?.content === 'string' || entry.kind === 'quiz' && (entry.attempt?.id || entry.status === 'error' || entry.status === 'generating')
    )).map(entry => entry.kind === 'quiz' && entry.status === 'generating'
      ? { ...entry, status: 'error', error: 'Quiz generation was interrupted. Try again.' }
      : entry.kind === 'message' && entry.pending
        ? { ...entry, pending: false, message: { ...entry.message, content: 'The response was interrupted. Please retry.', isRefused: true } } : entry);
  } catch { /* A storage failure must never disable the tutor. */ }
  let state: ConversationState = { entries: restored, chatLoading: false, quizLoading: false, summaryLoading: false, chatError: null, quizError: null, summaryError: null, followRequest: 0 };
  const listeners = new Set<() => void>();
  const update = (patch: Partial<ConversationState>) => {
    if (!activated) activate();
    state = { ...state, ...patch };
    try { if (storageOwners.get(key) === owner) storage?.setItem(key, JSON.stringify(state.entries)); } catch { /* Keep the in-memory conversation usable. */ }
    listeners.forEach(listener => listener());
  };
  const replace = (entryId: string, entry: ConversationEntry) => update({ entries: state.entries.map(item => item.id === entryId ? entry : item) });
  const textEntry = (content: string, sender: Message['sender'] = 'assistant'): TextEntry => {
    const entryId = id();
    return { kind: 'message', id: entryId, message: { id: entryId, sender, content, timestamp: new Date().toLocaleTimeString() } };
  };
  const beginResponse = (question: string, request: QueryRequest, retryId?: string) => {
    const entry = { ...textEntry('LearnMateAI is thinking...'), pending: true, retry: request };
    if (retryId) {
      entry.id = retryId; entry.message.id = retryId;
      replace(retryId, entry);
    } else update({ entries: [...state.entries, textEntry(question, 'user'), entry] });
    update({ chatLoading: true, chatError: null, followRequest: state.followRequest + 1 });
    return entry;
  };
  async function ask(question: string, depth: QueryRequest['explanation_depth'] = 'standard', quizId?: string, retryId?: string, originalRequest?: QueryRequest) {
    const trimmed = question.trim();
    if (!trimmed || state.chatLoading) return;
    if (!retryId && isQuizRequest(trimmed)) { await generate(trimmed, undefined, /\bhard\b/i.test(trimmed) ? 'hard' : /\beasy\b/i.test(trimmed) ? 'easy' : 'medium'); return; }
    const request: QueryRequest = originalRequest || { question: trimmed, subject_id: scope.subject_id, chapter_id: scope.chapter_id, explanation_depth: depth, ...quizReviewContext(trimmed, state.entries, quizId) };
    const entry = beginResponse(trimmed, request, retryId);
    try {
      if (!scope.subject_id) throw new Error('missing-scope');
      const result = await api.query(request);
      replace(entry.id, { kind: 'message', id: entry.id, message: { ...entry.message, content: result.answer, citations: result.citations, isRefused: result.is_refused } });
    } catch (error) {
      const message = !scope.subject_id ? 'Your Science curriculum is not available yet. Please contact your administrator.' : failure(error, 'Unable to reach the tutor. Please retry or ask another question.');
      replace(entry.id, { ...entry, pending: false, message: { ...entry.message, content: message, isRefused: true } });
      update({ chatError: message });
    } finally { update({ chatLoading: false }); }
  }
  async function generate(userMessage?: string, retryId?: string, difficulty: QuizRequest['difficulty'] = 'medium', count = 10) {
    if (state.quizLoading || !scope.subject_id) return;
    const previous = state.entries.find((item): item is QuizEntry => item.kind === 'quiz' && item.id === retryId);
    const request = previous?.request || { subject_id: scope.subject_id, chapter_id: scope.chapter_id, num_questions: count, difficulty };
    const entry: QuizEntry = { kind: 'quiz', id: retryId || id(), status: 'generating', request };
    if (retryId) replace(retryId, entry);
    else update({ entries: [...state.entries, ...(userMessage ? [textEntry(userMessage, 'user')] : []), entry] });
    update({ quizLoading: true, quizError: null, followRequest: state.followRequest + 1 });
    try {
      const attempt = await api.quiz(request);
      replace(entry.id, { ...entry, status: 'ready', attempt });
    } catch (error) {
      const message = failure(error, 'Quiz generation failed. Please try again.');
      replace(entry.id, { ...entry, status: 'error', error: message });
      update({ quizError: message });
    } finally { update({ quizLoading: false }); }
  }
  async function summarize(document_id: string, chapter?: string) {
    if (state.summaryLoading) return;
    const entry = { ...textEntry('Summarizing your chapter...'), pending: true };
    update({ entries: [...state.entries, entry], summaryLoading: true, summaryError: null, followRequest: state.followRequest + 1 });
    try {
      const result = await api.summarize({ document_id, chapter });
      replace(entry.id, { kind: 'message', id: entry.id, message: { ...entry.message, content: `Chapter summary:\n\n${result.summary}\n\nKey takeaways:\n${result.key_takeaways.map(item => `• ${item}`).join('\n')}`, citations: result.citations } });
    } catch (error) {
      const message = failure(error, 'Unable to summarize this textbook material. Please try again.');
      replace(entry.id, { kind: 'message', id: entry.id, message: { ...entry.message, content: message, isRefused: true } });
      update({ summaryError: message });
    } finally { update({ summaryLoading: false }); }
  }
  function reviewed(entryId: string, review: QuizReview) {
    const entry = state.entries.find((item): item is QuizEntry => item.kind === 'quiz' && item.id === entryId);
    if (entry?.attempt) replace(entryId, { ...entry, review, attempt: { ...entry.attempt, status: 'submitted', score: review.result.accuracy } });
  }
  async function restoreLegacyQuiz() {
    if (state.entries.some(entry => entry.kind === 'quiz')) return;
    const position = state.entries.length;
    try {
      const saved = storage?.getItem(legacyKey);
      if (!saved) return;
      const attempt = await api.getAttempt(saved); // Existing ownership check is authoritative.
      if (!state.entries.some(entry => entry.kind === 'quiz' && entry.attempt?.id === attempt.id)) {
        const entries = [...state.entries];
        entries.splice(position, 0, { kind: 'quiz', id: id(), status: 'ready', attempt });
        update({ entries });
      }
    } catch { /* An old or another account's attempt must not replace this history. */ }
  }
  return {
    activate,
    getSnapshot: () => state,
    subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    ask, generate, summarize, reviewed, restoreLegacyQuiz,
    retry: (entryId: string, depth?: QueryRequest['explanation_depth']) => {
      const entry = state.entries.find(item => item.id === entryId);
      if (entry?.kind === 'quiz') return generate(undefined, entryId);
      if (entry?.kind === 'message' && entry.retry) {
        const request = { ...entry.retry, explanation_depth: depth ?? entry.retry.explanation_depth };
        return ask(request.question, request.explanation_depth, undefined, entry.id, request);
      }
    },
  };
}
