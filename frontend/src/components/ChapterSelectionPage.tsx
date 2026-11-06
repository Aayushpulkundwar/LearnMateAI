import React, { useEffect, useState } from 'react';
import { ArrowLeft, BookOpen, RefreshCw } from 'lucide-react';
import { getChapterAnalytics } from '../api/client';
import { useStudySession } from '../context/StudySessionContext';
import { PerformanceMetric } from '../types';

export const ChapterSelectionPage: React.FC<{ subjectId: string; onStudy: (chapterId: string) => void; onBack: () => void }> = ({ subjectId, onStudy, onBack }) => {
  const { selection, chapters, loading, error, loadChapters, chooseChapter } = useStudySession();
  const [progress, setProgress] = useState<Map<string, PerformanceMetric>>(new Map());

  useEffect(() => { loadChapters(subjectId).catch(() => undefined); }, [subjectId, loadChapters]);
  useEffect(() => {
    let active = true;
    getChapterAnalytics(subjectId)
      .then(metrics => { if (active) setProgress(new Map(metrics.map(metric => [metric.id, metric]))); })
      .catch(() => { if (active) setProgress(new Map()); });
    return () => { active = false; };
  }, [subjectId]);

  return <main className="auth-page"><section className="auth-card curriculum-card">
    <button className="auth-link" onClick={onBack}><ArrowLeft size={15} /> Change subject</button>
    <h2>{selection?.subjectName || 'Science'} chapters</h2><p>Choose a chapter to begin your tutoring session.</p>
    {loading && <p><RefreshCw className="spin" size={14} /> Loading chapters…</p>}
    {error && <><p className="auth-error">{error}</p><button className="auth-link" onClick={() => loadChapters(subjectId).catch(() => undefined)}>Try again</button></>}
    {!loading && !error && chapters.length === 0 && <p>No chapters are available for this subject yet.</p>}
    <div className="chapter-list">{chapters.map(chapter => {
      const metric = progress.get(chapter.id);
      return <article key={chapter.id} className="chapter-card"><BookOpen size={18} /><div><b>Chapter {chapter.chapter_number}</b><p>{chapter.name}</p>{metric ? <small className="chapter-progress">{Math.round(metric.accuracy)}% assessment accuracy · {metric.classification}</small> : <small className="chapter-progress">No assessment evidence yet</small>}</div><button className="upload-btn" onClick={() => { chooseChapter(chapter); onStudy(chapter.id); }}>Study</button></article>;
    })}</div>
  </section></main>;
};
