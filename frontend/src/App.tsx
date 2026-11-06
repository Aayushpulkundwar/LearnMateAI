import React, { useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import { HelpCircle, Send, Sparkles } from 'lucide-react';
import { AuthPanel } from './components/AuthPanel';
import { AppShell } from './components/AppShell';
import { AdminTextbookManager } from './components/AdminTextbookManager';
import { ChapterSelectionPage } from './components/ChapterSelectionPage';
import { DiagnosticAssessment } from './components/DiagnosticAssessment';
import { MessageThread } from './components/MessageThread';
import { TutorQuiz } from './components/TutorQuiz';
import { createTutorConversation, isQuizRequest } from './state/tutorConversation';
import { RecommendedLearning } from './components/RecommendedLearning';
import { StudentDashboard } from './components/StudentDashboard';
import { StudentProfilePanel } from './components/StudentProfilePanel';
import { SubjectSelectionPage } from './components/SubjectSelectionPage';
import { StudySessionProvider, useStudySession } from './context/StudySessionContext';
import { getMyProfile, listDocuments, logoutStudent, sendQuery, summarizeChapter, generateQuiz, getQuizAttempt } from './api/client';
import { shouldSkipLogin } from './config/developmentMode';
import { AssessmentAttempt, Document, StudentProfile } from './types';

const usePath = () => {
  const [path, setPath] = useState(window.location.pathname);
  useEffect(() => { const listener = () => setPath(window.location.pathname); window.addEventListener('popstate', listener); return () => window.removeEventListener('popstate', listener); }, []);
  const navigate = (next: string) => { window.history.pushState({}, '', next); setPath(next); };
  return { path, navigate };
};

const TutorWorkspace: React.FC<{ navigate: (path: string) => void; studentId: string }> = ({ navigate, studentId }) => {
  const { selection, loadSubjects, chooseSubject, clearChapter, clearSelection } = useStudySession();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [inputQuestion, setInputQuestion] = useState('');
  const [quizDifficulty, setQuizDifficulty] = useState<'easy' | 'medium' | 'hard'>('medium');
  const [quizCount, setQuizCount] = useState(10);
  const [explanationDepth, setExplanationDepth] = useState<'brief' | 'standard' | 'detailed'>('standard');
  const conversation = useMemo(() => {
    let storage: Storage | undefined;
    try { storage = window.sessionStorage; } catch { /* Storage is optional. */ }
    return createTutorConversation({ studentId, subject_id: selection?.subjectId, chapter_id: selection?.chapterId }, {
      query: sendQuery, quiz: generateQuiz, summarize: summarizeChapter, getAttempt: getQuizAttempt,
    }, storage);
  }, [studentId, selection?.subjectId, selection?.chapterId]);
  const state = useSyncExternalStore(conversation.subscribe, conversation.getSnapshot, conversation.getSnapshot);
  useEffect(() => { conversation.activate(); void conversation.restoreLegacyQuiz(); }, [conversation]);
  const document = selection?.chapterId ? documents.find(item => item.chapter_id === selection.chapterId) : documents[0];
  useEffect(() => { if (selection?.subjectId) return; loadSubjects().then(subjects => { if (subjects[0]) chooseSubject(subjects[0]); }).catch(() => undefined); }, [selection?.subjectId, loadSubjects, chooseSubject]);
  useEffect(() => {
    let active = true;
    setDocuments([]);
    if (selection?.subjectId) listDocuments(undefined, undefined, selection.subjectId, selection.chapterId).then(rows => { if (active) setDocuments(rows); }).catch(() => undefined);
    return () => { active = false; };
  }, [selection?.subjectId, selection?.chapterId]);
  const send = (event: React.FormEvent) => {
    event.preventDefault();
    const question = inputQuestion.trim();
    if (!question || state.chatLoading || (isQuizRequest(question) && state.quizLoading)) return;
    setInputQuestion('');
    void conversation.ask(question, explanationDepth);
  };
  const title = selection?.chapterName || `${selection?.subjectName || 'Science'} · All Science`;
  return <main className="tutor-workspace"><div className="tutor-heading"><div><p className="eyebrow">AI TUTOR</p><h1>{title}</h1><p>{selection?.chapterId ? 'Ask anything from this chapter. Answers include textbook citations.' : 'General Science chat searches all textbook material authorized for your class.'}</p></div><div>{selection?.subjectId && <button className="secondary-button" onClick={() => navigate(`/subjects/${selection.subjectId}/chapters`)}>Change chapter</button>}{selection?.chapterId && <button className="secondary-button" onClick={clearChapter}>All Science</button>}<button className="text-button" onClick={() => { clearSelection(); navigate('/subjects'); }}>Change subject</button></div></div><section className="chat-section"><MessageThread key={`${studentId}:${selection?.subjectId}:${selection?.chapterId || 'all'}`} entries={state.entries} followRequest={state.followRequest} onRetry={entryId => { void conversation.retry(entryId, explanationDepth); }} chatLoading={state.chatLoading} renderQuiz={entry => entry.attempt ? <TutorQuiz attempt={entry.attempt} initialReview={entry.review} onReviewed={review => conversation.reviewed(entry.id, review)} onExplainQuestion={number => { void conversation.ask(`Explain question ${number}.`, explanationDepth, entry.id); }} chatLoading={state.chatLoading} /> : <section className="tutor-quiz" aria-label="Quiz generation" aria-busy={entry.status === 'generating'}>{entry.status === 'generating' ? <p role="status">Designing and checking concept questions. Local generation may take several minutes...</p> : <><p role="alert" className="auth-error">{entry.error}</p><button type="button" className="text-button" disabled={state.quizLoading} onClick={() => { void conversation.retry(entry.id); }}>Retry quiz</button></>}</section>} /><div className="input-section"><fieldset className="depth-control"><legend>Explanation depth</legend>{(['brief', 'standard', 'detailed'] as const).map(depth => <button key={depth} type="button" className={explanationDepth === depth ? 'active' : ''} onClick={() => setExplanationDepth(depth)}>{depth}</button>)}</fieldset><form onSubmit={send} className="input-form"><label className="sr-only" htmlFor="tutor-question">Ask your question</label><input id="tutor-question" className="chat-input" value={inputQuestion} onChange={event => setInputQuestion(event.target.value)} placeholder={selection?.chapterName ? `Ask about ${selection.chapterName}…` : 'Ask a Science question…'} /><button type="submit" disabled={state.chatLoading || !inputQuestion.trim()} className="send-btn" aria-label="Send question"><Send size={18} /></button></form><div className="secondary-actions"><label>Quiz difficulty <select aria-label="Quiz difficulty" value={quizDifficulty} disabled={state.quizLoading} onChange={event => setQuizDifficulty(event.target.value as 'easy' | 'medium' | 'hard')}><option value="easy">Easy ? Remember and understand</option><option value="medium">Medium ? Apply and analyze</option><option value="hard">Hard ? Reason and evaluate</option></select></label><label>Questions <select aria-label="Quiz question count" value={quizCount} disabled={state.quizLoading} onChange={event => setQuizCount(Number(event.target.value))}>{[3, 5, 10].map(count => <option key={count} value={count}>{count}</option>)}</select></label><button disabled={!document || state.summaryLoading} onClick={() => { if (document) void conversation.summarize(document.id, selection?.chapterName); }} className="action-chip"><Sparkles size={14} /> Summarize chapter</button><button disabled={!selection?.subjectId || state.quizLoading} onClick={() => { void conversation.generate(undefined, undefined, quizDifficulty, quizCount); }} className="action-chip"><HelpCircle size={14} /> {state.quizLoading ? 'Generating your quiz...' : 'Generate quiz'}</button>{!document && <span className="auth-error">Your AI Tutor is ready. No Science textbook is available for your class yet. Uploads are managed by your administrator.</span>}</div></div></section></main>;
};

const DevelopmentModeDashboard: React.FC = () => <main className="development-dashboard">
  <p className="development-mode-indicator">Development Mode</p>
  <h1>LearnMateAI dashboard</h1>
  <p>Login is skipped only for this development build. You are not signed in, and protected learning records, documents, uploads, and administrative actions remain unavailable.</p>
  <p>Use a normal authenticated session to test student-specific or administrator workflows.</p>
</main>;

const AppContent: React.FC = () => {
  const [student, setStudent] = useState<StudentProfile | null>(null); const [ready, setReady] = useState(false); const [attempt, setAttempt] = useState<AssessmentAttempt | undefined>();
  const { path, navigate } = usePath(); const { selection, loadSubjects, loadChapters, clearSelection } = useStudySession();
  useEffect(() => { getMyProfile().then(setStudent).catch(() => setStudent(null)).finally(() => setReady(true)); }, []);
  useEffect(() => { if (!student) return; loadSubjects().then(subjects => { const saved = selection; if (!saved) return; if (!subjects.some(subject => subject.id === saved.subjectId)) { clearSelection(); return; } if (saved.chapterId) loadChapters(saved.subjectId).catch(clearSelection); }).catch(() => undefined); }, [student, loadSubjects, loadChapters, clearSelection]);
  const logout = async () => { try { await logoutStudent(); } finally { setStudent(null); navigate('/login'); } };
  if (!ready) return <main className="auth-page">Loading secure session…</main>;
  if (!student && shouldSkipLogin(import.meta.env.DEV, import.meta.env.VITE_SKIP_LOGIN)) return <DevelopmentModeDashboard />;
  if (!student) return <AuthPanel onAuthenticated={(profile) => { setStudent(profile); navigate('/subjects'); }} />;
  const openTutor = () => { navigate(selection?.chapterId ? `/study/${selection.chapterId}` : '/tutor'); };
  const shell = (content: React.ReactNode) => <AppShell student={student} path={path} navigate={navigate} onLogout={logout} onOpenTutor={openTutor}>{content}</AppShell>;
  if (path === '/subjects' || path === '/' || path === '/login') return shell(<SubjectSelectionPage student={student} onLogout={logout} onSelect={id => navigate(`/subjects/${id}/chapters`)} />);
  const chapterRoute = path.match(/^\/subjects\/([^/]+)\/chapters$/);
  if (chapterRoute) return shell(<ChapterSelectionPage subjectId={chapterRoute[1]} onBack={() => navigate('/subjects')} onStudy={chapterId => navigate(`/study/${chapterId}`)} />);
  if (path === '/tutor' || path.startsWith('/study/')) return shell(<TutorWorkspace navigate={navigate} studentId={student.id} />);
  if (path === '/admin/textbooks') return student.is_admin ? shell(<AdminTextbookManager />) : shell(<main className="dashboard-shell"><section className="dashboard-error"><h2>Administrator access required</h2><p>This textbook-management area is not available to student accounts.</p></section></main>);
  if (path === '/dashboard') return shell(<StudentDashboard student={student} onOpenTutor={openTutor} onStartAssessment={() => navigate('/diagnostic')} onStudy={openTutor} onViewResults={() => navigate('/diagnostic')} />);
  if (path === '/practice' && attempt) return shell(<TutorQuiz key={attempt.id} attempt={attempt} />);
  if (path === '/diagnostic' || path === '/assessment') return shell(<DiagnosticAssessment initialSubject={selection?.subjectId} initialAttempt={attempt} onBack={() => navigate('/dashboard')} />);
  if (path === '/progress' || path === '/weekly-assignments' || path === '/learning') return shell(<RecommendedLearning onStudy={openTutor} onAttempt={created => { setAttempt(created); navigate(created.questions.some(question => question.question_type) ? '/practice' : '/diagnostic'); }} />);
  if (path === '/profile') return shell(<StudentProfilePanel student={student} onUpdated={setStudent} onBack={() => navigate('/dashboard')} />);
  navigate('/dashboard'); return null;
};

export const App: React.FC = () => <StudySessionProvider><AppContent /></StudySessionProvider>;
