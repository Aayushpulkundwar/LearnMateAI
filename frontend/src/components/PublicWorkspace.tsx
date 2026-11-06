import React, { useState } from 'react';
import { BookOpen, Brain, ClipboardList, Send, Target } from 'lucide-react';

type Props = { path: string; navigate: (path: string) => void };
const unavailable = 'This feature is unavailable in this public deployment. It requires a private student session and supporting backend services.';

const AvailabilityNotice = () => <p className="availability-notice" role="status">{unavailable} No student records are loaded or saved here.</p>;

const features = [
  { title: 'My Subjects', description: 'Explore subjects and textbook chapters.', path: '/subjects', icon: BookOpen },
  { title: 'AI Tutor', description: 'Explore the tutor workspace and question controls.', path: '/tutor', icon: Brain },
  { title: 'Assessments & Quizzes', description: 'View the assessment and quiz workspace.', path: '/assessment', icon: ClipboardList },
  { title: 'Concept Mastery', description: 'View progress and concept mastery tracking.', path: '/progress', icon: Target },
];

const PublicTutor: React.FC<{ navigate: Props['navigate'] }> = ({ navigate }) => {
  const [question, setQuestion] = useState('');
  const [depth, setDepth] = useState('standard');
  return <main className="tutor-workspace">
    <div className="tutor-heading"><div><p className="eyebrow">AI TUTOR</p><h1>Your learning workspace</h1><p>Explore the interface for textbook-grounded questions.</p></div><button className="secondary-button" onClick={() => navigate('/subjects')}>Browse subjects</button></div>
    <section className="chat-section" aria-label="AI Tutor">
      <div className="message-thread"><AvailabilityNotice /><p>Questions, chapter summaries and generated quizzes are unavailable here.</p></div>
      <div className="input-section">
        <fieldset className="depth-control"><legend>Explanation depth</legend>{['brief', 'standard', 'detailed'].map(value => <button key={value} type="button" aria-pressed={depth === value} className={depth === value ? 'active' : ''} onClick={() => setDepth(value)}>{value}</button>)}</fieldset>
        <form className="input-form" onSubmit={event => event.preventDefault()}>
          <label className="sr-only" htmlFor="tutor-question">Ask your question</label><input id="tutor-question" className="chat-input" value={question} onChange={event => setQuestion(event.target.value)} placeholder="Explore the question input" aria-describedby="tutor-unavailable" />
          <button className="send-btn" type="submit" disabled aria-label="Send question unavailable"><Send size={18} /></button>
        </form>
        <p id="tutor-unavailable" className="quiz-notice">Sending questions is unavailable in this deployment. Drafts stay on this page and are not saved.</p>
        <div className="secondary-actions"><label>Quiz difficulty <select defaultValue="medium"><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option></select></label><label>Questions <select defaultValue="10">{[3, 5, 10].map(count => <option key={count}>{count}</option>)}</select></label><button className="action-chip" disabled>Summarize chapter</button><button className="action-chip" disabled>Generate quiz</button></div>
      </div>
    </section>
  </main>;
};

export const PublicWorkspace: React.FC<Props> = ({ path, navigate }) => {
  if (path === '/tutor' || path.startsWith('/study/')) return <PublicTutor navigate={navigate} />;
  if (path === '/subjects' || /^\/subjects\/[^/]+\/chapters\/?$/.test(path)) {
    const chapters = path !== '/subjects';
    return <main className="dashboard-shell"><div className="dashboard-heading"><div><p className="eyebrow">CURRICULUM</p><h1>{chapters ? 'Chapters' : 'My Subjects'}</h1><p>Subjects and chapters follow the private student curriculum.</p></div></div><AvailabilityNotice /><section className="dashboard-panel"><h2>{chapters ? 'Chapter navigation unavailable' : 'Subject navigation unavailable'}</h2><p>No private curriculum is loaded in this deployment.</p><div className="card-actions"><button onClick={() => navigate(chapters ? '/subjects' : '/')}>{chapters ? 'Back to subjects' : 'Back to dashboard'}</button><button onClick={() => navigate('/tutor')}>Explore AI Tutor</button></div></section></main>;
  }
  if (['/assessment', '/diagnostic', '/practice', '/quiz'].includes(path)) return <main className="dashboard-shell"><div className="dashboard-heading"><div><p className="eyebrow">ASSESSMENTS</p><h1>Assessments &amp; Quizzes</h1><p>Diagnostic assessments and textbook-grounded practice.</p></div></div><AvailabilityNotice /><section className="dashboard-panel"><h2>Diagnostic assessment</h2><label>Subject <select disabled aria-label="Assessment subject"><option>Subjects unavailable</option></select></label><div className="card-actions"><button disabled>Start assessment</button><button disabled>Generate quiz</button><button onClick={() => navigate('/')}>Back to dashboard</button></div><p>Questions, results and assessment history are unavailable. No scores are recorded.</p></section></main>;
  if (['/progress', '/learning', '/weekly-assignments'].includes(path)) return <main className="dashboard-shell"><div className="dashboard-heading"><div><p className="eyebrow">MY PROGRESS</p><h1>Concept mastery tracking</h1></div></div><AvailabilityNotice /><div className="dashboard-split">{['Chapter performance', 'Concept mastery', 'Assessment history', 'Recommended learning'].map(title => <section key={title} className="dashboard-panel"><h2>{title}</h2><p>Private learning evidence is unavailable in this deployment.</p></section>)}</div></main>;
  if (path.startsWith('/admin') || path === '/profile') return <main className="dashboard-shell"><section className="dashboard-error"><h1>{path.startsWith('/admin') ? 'Administration unavailable' : 'Student profile unavailable'}</h1><AvailabilityNotice /><button className="dashboard-primary" onClick={() => navigate('/')}>Back to dashboard</button></section></main>;
  return <main className="dashboard-shell">
    <div className="dashboard-heading"><div><p className="eyebrow">YOUR LEARNING SPACE</p><h1>Welcome to LearnMateAI</h1><p>Explore your dashboard. No account is needed.</p></div></div>
    <AvailabilityNotice />
    <section className="subject-grid" aria-label="Learning workspaces">{features.map(({ title, description, path: destination, icon: Icon }) => <article key={destination} className="subject-card"><Icon aria-hidden="true" /><h2>{title}</h2><p>{description}</p><button className="dashboard-primary" onClick={() => navigate(destination)}>Open {title}</button></article>)}</section>
    <section className="dashboard-section stat-grid" aria-label="Academic overview">{['Assessments completed', 'Average score', 'Topics mastered', 'Learning progress'].map(label => <article key={label}><span>{label}</span><strong aria-label="Unavailable">—</strong><small>Student evidence unavailable</small></article>)}</section>
  </main>;
};
