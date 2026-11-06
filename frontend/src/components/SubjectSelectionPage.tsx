import React, { useEffect } from 'react';
import { BookOpen, RefreshCw } from 'lucide-react';
import { StudentProfile } from '../types';
import { useStudySession } from '../context/StudySessionContext';
import scienceIllustration from '../assets/science-learning-illustration.png';

export const SubjectSelectionPage: React.FC<{ student: StudentProfile; onSelect: (subjectId: string) => void; onLogout: () => void }> = ({ student, onSelect, onLogout }) => {
  const { subjects, loading, error, loadSubjects, chooseSubject } = useStudySession();
  useEffect(() => { loadSubjects().catch(() => undefined); }, [loadSubjects]);
  return <main className="selection-page"><section className="welcome-copy"><p className="eyebrow">YOUR LEARNING SPACE</p><h1>Welcome{student.display_name ? `, ${student.display_name}` : ''}.</h1><p>Pick a subject and we’ll keep every explanation grounded in your registered class curriculum.</p><span className="grade-pill">{student.grade_name}</span></section><section className="subject-showcase">{loading && <p><RefreshCw className="spin" size={14} /> Loading your curriculum…</p>}{error && <><p className="auth-error">{error}</p><button className="text-button" onClick={() => loadSubjects().catch(() => undefined)}>Try again</button></>}{!loading && !error && subjects.length === 0 && <p>No subjects are available for your grade yet.</p>}{subjects.map(subject => <article key={subject.id} className="subject-hero-card"><div><span className="subject-icon"><BookOpen /></span><p className="eyebrow">AVAILABLE SUBJECT</p><h2>{subject.name}</h2><p>Explore chapters, ask grounded questions, and build confidence at your own pace.</p><button className="primary-button" onClick={() => { chooseSubject(subject); onSelect(subject.id); }}>Start learning</button></div><img src={scienceIllustration} alt="Open science book with an atom and chemistry flask" /></article>)}</section></main>;
};
