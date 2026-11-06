import React, { useEffect, useState } from 'react';
import { getQuizReview, submitDiagnostic } from '../api/client';
import { AssessmentAttempt, QuizReview } from '../types';

export const TutorQuiz: React.FC<{
  attempt: AssessmentAttempt; initialReview?: QuizReview; onReviewed?: (review: QuizReview) => void;
  onExplainQuestion?: (number: number) => void; chatLoading?: boolean;
}> = ({ attempt, initialReview, onReviewed, onExplainQuestion, chatLoading }) => {
  const [index, setIndex] = useState(0);
  const storageKey = `learnmate_quiz_answers:${attempt.id}`;
  const [answers, setAnswers] = useState<Record<string, string>>(() => {
    try {
      const saved = JSON.parse(sessionStorage.getItem(storageKey) || '{}');
      if (!saved || typeof saved !== 'object' || Array.isArray(saved)) return {};
      return Object.fromEntries(Object.entries(saved).filter(([id, value]) => attempt.questions.some(question => question.id === id && question.options.some(option => option.id === value)))) as Record<string, string>;
    } catch { return {}; }
  });
  const [review, setReview] = useState<QuizReview | null>(initialReview || null);
  const [submitted, setSubmitted] = useState(attempt.status === 'submitted');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    try { sessionStorage.setItem(storageKey, JSON.stringify(answers)); } catch { /* Storage is optional. */ }
  }, [answers, storageKey]);
  const loadReview = async () => {
    setBusy(true); setError('');
    try { const result = await getQuizReview(attempt.id); setReview(result); onReviewed?.(result); }
    catch { setError('Your quiz was submitted. Results could not be loaded; try again.'); }
    finally { setBusy(false); }
  };
  useEffect(() => { if (attempt.status === 'submitted' && !initialReview) void loadReview(); }, [attempt.id]);
  const submit = async () => {
    if (busy) return;
    setBusy(true); setError('');
    try {
      await submitDiagnostic(attempt.id, Object.entries(answers).map(([attempt_question_id, selected_option_id]) => ({ attempt_question_id, selected_option_id })));
      setSubmitted(true);
      const result = await getQuizReview(attempt.id);
      setReview(result); onReviewed?.(result);
    } catch (err: any) { setError(err.response?.data?.detail || 'Unable to finish the quiz request. Retry safely; a submitted quiz is scored only once.'); }
    finally { setBusy(false); }
  };
  if (review) return <section className="tutor-quiz" aria-label="Quiz results">
    <h2>Quiz results</h2>
    <p className="quiz-score">Score: {review.result.correct} / {review.result.total_questions} · {review.result.accuracy}%</p>
    <p>{review.result.correct} correct · {review.result.incorrect} incorrect · {review.result.unanswered} unanswered</p>
    <p>Concept practice evidence has been saved. Recommendations use your accumulated assessment evidence.</p>
    {review.questions.map((question, number) => <article className="quiz-review" key={question.id}>
      <h3>{number + 1}. {question.question_text}</h3>
      {question.concept && <p>Concept: {question.concept} ? {question.difficulty} ? {question.question_type}</p>}
      <p>Your answer: {question.options.find(option => option.id === question.selected_option_id)?.option_text || 'Unanswered'}</p>
      <p><strong>Correct answer: {question.options.find(option => option.is_correct)?.option_text}</strong></p>
      <p>{question.explanation}</p>
      {question.evidence && <blockquote>{question.evidence}</blockquote>}
      <p className="quiz-reference">{question.source_title || 'Textbook'}{question.chapter_name && ` · ${question.chapter_name}`}{question.source_page != null && ` · Page ${question.source_page}`}</p>
      {onExplainQuestion && <button type="button" className="text-button" disabled={chatLoading} onClick={() => onExplainQuestion(number + 1)}>Explain question {number + 1}</button>}
    </article>)}
  </section>;
  const question = attempt.questions[index];
  return <section className="tutor-quiz" aria-label="Textbook practice quiz" aria-busy={busy}>
    <p className="eyebrow">TEXTBOOK PRACTICE · MEDIUM</p>
    {attempt.coverage_warning && <p className="quiz-notice">{attempt.coverage_warning}</p>}
    {submitted ? <><h2>Quiz submitted</h2><button className="secondary-button" disabled={busy} onClick={loadReview}>{busy ? 'Loading results...' : 'Load results'}</button></> : <>
      <h2>Question {index + 1} of {attempt.questions.length}</h2>
      {question.concept && <p>{question.concept} ? {question.question_type}</p>}
      <fieldset className="quiz-options" disabled={busy}>
        <legend>{question.question_text}</legend>
        {question.options.map((option, number) => <label key={option.id} className={answers[question.id] === option.id ? 'selected' : ''}>
          <input type="radio" name={`quiz-${question.id}`} value={option.id} checked={answers[question.id] === option.id} onChange={() => setAnswers(previous => ({ ...previous, [question.id]: option.id }))} />
          <span><b>{String.fromCharCode(65 + number)}.</b> {option.option_text}</span>
        </label>)}
      </fieldset>
      <p>{Object.keys(answers).length} of {attempt.questions.length} answered. Unanswered questions receive no credit.</p>
      <div className="quiz-navigation">
        <button className="text-button" disabled={busy || index === 0} onClick={() => setIndex(index - 1)}>Previous Question</button>
        {index < attempt.questions.length - 1 && <button className="secondary-button" disabled={busy} onClick={() => setIndex(index + 1)}>Next Question</button>}
        <button className="secondary-button" disabled={busy} onClick={submit}>{busy ? 'Submitting...' : 'Submit Quiz'}</button>
      </div>
    </>}
    {error && <p role="alert" className="auth-error">{error}</p>}
  </section>;
};
