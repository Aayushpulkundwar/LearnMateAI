import React, { useEffect, useMemo, useState } from 'react';
import { AlertCircle, ArrowRight, BookOpen, Brain, BarChart3, ClipboardList, RefreshCw, Sparkles, Target } from 'lucide-react';
import {
  getAnalyticsOverview, getAssessmentHistory, getChapterAnalytics, getMasteryOverview,
  getPerformanceTrends, getSubjectAnalytics, getSubjectMastery, getTopicMasteryHistory,
  listAssessmentSubjects,
} from '../api/client';
import { AnalyticsOverview, AssessmentHistoryItem, MasteryHistoryItem, MasteryItem, PerformanceMetric, StudentProfile, SubjectAnalytics } from '../types';

type Props = { student: StudentProfile; onOpenTutor: () => void; onStartAssessment: (subjectId?: string) => void; onStudy: (subjectId?: string, topicId?: string) => void; onViewResults: (attemptId: string) => void };
const short = (id: string) => id.slice(0, 8);
const label = (kind: string, id: string) => `${kind} ${short(id)}`;
const score = (value?: number | null) => value == null ? '—' : `${Math.round(value)}%`;
const date = (value: string) => new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
const tone = (classification?: string) => classification === 'Strong' ? 'strong' : classification === 'Developing' ? 'developing' : classification === 'Needs Improvement' ? 'needs-improvement' : 'insufficient';

function TrendChart({ history }: { history: AssessmentHistoryItem[] }) {
  if (!history.length) return <div className="dashboard-empty compact">Complete assessments to reveal your progress trend.</div>;
  const points = [...history].reverse();
  const width = 620, height = 180, pad = 20;
  const coords = points.map((point, index) => {
    const x = points.length === 1 ? width / 2 : pad + index * ((width - pad * 2) / (points.length - 1));
    const y = height - pad - (point.accuracy / 100) * (height - pad * 2);
    return `${x},${y}`;
  }).join(' ');
  return <div className="trend-chart" aria-label="Assessment accuracy trend"><svg viewBox={`0 0 ${width} ${height}`} role="img"><line x1={pad} x2={width - pad} y1={height - pad} y2={height - pad} /><line x1={pad} x2={width - pad} y1={height / 2} y2={height / 2} /><polyline points={coords} />{points.map((point, index) => { const [x, y] = coords.split(' ')[index].split(','); return <circle key={point.attempt_id} cx={x} cy={y} r="5"><title>{`${date(point.submitted_at)}: ${score(point.accuracy)}`}</title></circle>; })}</svg><div className="trend-axis"><span>{date(points[0].submitted_at)}</span><span>Latest: {score(points[points.length - 1].accuracy)}</span></div></div>;
}

export const StudentDashboard: React.FC<Props> = ({ student, onOpenTutor, onStartAssessment, onStudy, onViewResults }) => {
  const [subjects, setSubjects] = useState<{ id: string; name: string }[]>([]);
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [history, setHistory] = useState<AssessmentHistoryItem[]>([]);
  const [mastery, setMastery] = useState<MasteryItem[]>([]);
  const [selectedSubject, setSelectedSubject] = useState<string>('');
  const [subjectAnalytics, setSubjectAnalytics] = useState<SubjectAnalytics | null>(null);
  const [chapters, setChapters] = useState<PerformanceMetric[]>([]);
  const [subjectMastery, setSubjectMastery] = useState<MasteryItem[]>([]);
  const [topicHistory, setTopicHistory] = useState<MasteryHistoryItem[]>([]);
  const [selectedTopic, setSelectedTopic] = useState<MasteryItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true); setError('');
    const [subjectsResult, overviewResult, historyResult, masteryResult, trendsResult] = await Promise.allSettled([
      listAssessmentSubjects(), getAnalyticsOverview(), getAssessmentHistory(), getMasteryOverview(), getPerformanceTrends(),
    ]);
    if (subjectsResult.status === 'rejected') {
      setError(subjectsResult.reason?.response?.data?.detail || 'Your available subjects could not be loaded. Please try again.');
    } else {
      const availableSubjects = subjectsResult.value;
      setSubjects(availableSubjects);
      setOverview(overviewResult.status === 'fulfilled' ? overviewResult.value : { subjects: [], total_attempts: 0 });
      const attempts = historyResult.status === 'fulfilled' ? historyResult.value : [];
      const trends = trendsResult.status === 'fulfilled' ? trendsResult.value : { points: [] };
      setHistory(trends.points.length ? trends.points : attempts);
      setMastery(masteryResult.status === 'fulfilled' ? masteryResult.value : []);
      setSelectedSubject(current => current || availableSubjects[0]?.id || '');
    }
    setLoading(false);
  };
  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (!selectedSubject) { setSubjectAnalytics(null); setChapters([]); setSubjectMastery([]); return; }
    setDetailLoading(true);
    Promise.all([getSubjectAnalytics(selectedSubject), getChapterAnalytics(selectedSubject), getSubjectMastery(selectedSubject)])
      .then(([analytics, chapterMetrics, masteryItems]) => { setSubjectAnalytics(analytics); setChapters(chapterMetrics); setSubjectMastery(masteryItems); })
      .catch(() => { setSubjectAnalytics(null); setChapters([]); setSubjectMastery([]); })
      .finally(() => setDetailLoading(false));
  }, [selectedSubject]);

  const subjectMap = useMemo(() => new Map(subjects.map(item => [item.id, item.name])), [subjects]);
  const metrics = useMemo(() => new Map((overview?.subjects || []).map(item => [item.subject_id, item])), [overview]);
  const average = overview?.subjects.length ? overview.subjects.reduce((sum, item) => sum + item.accuracy * item.total_questions, 0) / overview.subjects.reduce((sum, item) => sum + item.total_questions, 0) : null;
  const needsAttention = mastery.filter(item => item.classification === 'Needs Improvement').length;
  const recommendations = mastery.filter(item => item.classification === 'Needs Improvement' || item.classification === 'Developing').sort((a, b) => a.mastery_score - b.mastery_score).slice(0, 4);
  const openTopic = async (topic: MasteryItem) => { setSelectedTopic(topic); setTopicHistory([]); try { setTopicHistory(await getTopicMasteryHistory(topic.topic_id)); } catch { /* topic remains useful without history */ } };

  if (loading) return <main className="dashboard-shell"><div className="dashboard-loading"><RefreshCw className="spin" /> Loading your learning dashboard…</div></main>;
  if (error) return <main className="dashboard-shell"><section className="dashboard-error"><AlertCircle /><h2>Dashboard unavailable</h2><p>{error}</p><button className="dashboard-primary" onClick={load}>Try again</button></section></main>;

  const empty = !overview?.total_attempts;
  return <main className="dashboard-shell">
    <div className="dashboard-heading"><div><p className="eyebrow">{student.grade_name} · Student workspace</p><h2>Welcome to LearnMateAI{student.display_name ? `, ${student.display_name}` : ''}!</h2><p>Use your assessment evidence to decide what to study next.</p></div><button className="dashboard-primary" onClick={() => onStartAssessment(selectedSubject || undefined)}><ClipboardList size={17} /> Start assessment</button></div>
    {empty && <section className="dashboard-empty hero-empty"><Sparkles size={28} /><h3>Start learning Science with your AI tutor.</h3><p>No learning progress recorded yet. Choose a chapter, ask a textbook-grounded question, or take a diagnostic assessment.</p><div className="card-actions"><button className="dashboard-primary" onClick={() => onStudy()}>Start learning</button><button className="dashboard-primary" onClick={onOpenTutor}>Open AI Tutor</button><button className="dashboard-primary" onClick={() => onStartAssessment(selectedSubject || undefined)}>Take diagnostic test</button></div></section>}
    <section className="stat-grid" aria-label="Academic overview">
      <article><BookOpen /><span>Subjects enrolled</span><strong>{subjects.length}</strong></article><article><ClipboardList /><span>Assessments completed</span><strong>{overview?.total_attempts || 0}</strong></article><article><BarChart3 /><span>Average score</span><strong>{score(average)}</strong></article><article><Target /><span>Topics requiring attention</span><strong>{needsAttention}</strong></article>
    </section>
    <section className="dashboard-section"><div className="section-title"><div><p className="eyebrow">Subject performance</p><h3>Keep your momentum going</h3></div></div><div className="subject-grid">{subjects.map(subject => { const metric = metrics.get(subject.id); return <article className="subject-card" key={subject.id}><div className="subject-card-top"><BookOpen /><span className={`status-pill ${tone(metric?.classification)}`}>{metric?.classification || 'No evidence yet'}</span></div><h4>{subject.name}</h4><div className="subject-score"><strong>{score(metric?.accuracy)}</strong><span>latest evidence</span></div><p>{metric?.attempt_count || 0} assessment{metric?.attempt_count === 1 ? '' : 's'} · {metric?.total_questions || 0} questions</p><div className="card-actions"><button onClick={() => setSelectedSubject(subject.id)}>View analytics</button><button onClick={() => onStartAssessment(subject.id)}>Start assessment</button><button onClick={() => onStudy(subject.id)}>Study subject</button></div></article>; })}</div></section>
    <section className="dashboard-section dashboard-split"><article className="dashboard-panel"><div className="section-title"><div><p className="eyebrow">Performance trends</p><h3>Assessment accuracy</h3></div></div><TrendChart history={history} /></article><article className="dashboard-panel"><div className="section-title"><div><p className="eyebrow">Recent assessments</p><h3>Your latest activity</h3></div></div>{history.length ? <div className="recent-list">{history.slice(0, 5).map(item => <div key={item.attempt_id}><span>{date(item.submitted_at)}<small>{subjectMap.get(item.subject_id) || label('Subject', item.subject_id)}</small></span><strong>{score(item.accuracy)}</strong><button onClick={() => onViewResults(item.attempt_id)}>View results</button></div>)}</div> : <div className="dashboard-empty compact">No completed assessments yet.</div>}</article></section>
    <section className="dashboard-section curriculum-section"><div className="section-title"><div><p className="eyebrow">Learning detail</p><h3>Chapter performance and concept mastery</h3></div><label className="subject-select">Subject<select value={selectedSubject} onChange={e => setSelectedSubject(e.target.value)}>{subjects.map(subject => <option value={subject.id} key={subject.id}>{subject.name}</option>)}</select></label></div>{detailLoading ? <div className="dashboard-empty compact">Loading subject evidence…</div> : <div className="curriculum-grid"><article className="dashboard-panel"><h4>Chapter performance</h4>{chapters.length ? <div className="metric-list">{chapters.map(chapter => <div key={chapter.id}><span><b>{label('Chapter', chapter.id)}</b><small>{chapter.total_questions} questions · {chapter.provisional ? 'Provisional evidence' : 'Sufficient evidence'}</small></span><strong>{score(chapter.accuracy)}</strong><span className={`status-pill ${tone(chapter.classification)}`}>{chapter.classification}</span><button onClick={() => onStudy(selectedSubject)}>Study chapter</button></div>)}</div> : <div className="dashboard-empty compact">Complete a subject assessment to see chapter performance.</div>}</article><article className="dashboard-panel"><h4>Concept mastery</h4><p className="panel-description">Select a topic to review its evidence and trend.</p>{subjectMastery.length ? <div className="heatmap" role="list">{subjectMastery.map(topic => <button key={topic.topic_id} className={`heat-cell ${tone(topic.classification)}`} onClick={() => openTopic(topic)} aria-label={`${label('Topic', topic.topic_id)}: ${topic.classification}, ${score(topic.mastery_score)}`}><span>{label('Topic', topic.topic_id)}</span><b>{score(topic.mastery_score)}</b><small>{topic.evidence_count} evidence</small></button>)}</div> : <div className="dashboard-empty compact">Topic mastery will appear after completed assessments.</div>}</article></div>}</section>
    <section className="dashboard-section"><div className="section-title"><div><p className="eyebrow">Personalized recommendations</p><h3>Focus where evidence indicates a gap</h3></div></div>{recommendations.length ? <div className="recommendation-grid">{recommendations.map(topic => <article key={topic.topic_id}><Brain /><div><h4>{label('Topic', topic.topic_id)}</h4><p>{topic.classification === 'Needs Improvement' ? 'Recent assessment evidence indicates this concept needs attention.' : 'Continue practising to strengthen this developing concept.'}</p><small>{topic.evidence_count} evidence items · {topic.confidence_level}</small></div><div className="card-actions"><button onClick={() => onStudy(selectedSubject)}>Study now</button><button onClick={() => onStartAssessment(selectedSubject)}>Practice</button></div></article>)}</div> : <div className="dashboard-empty compact">Recommendations will be based on your completed assessment evidence.</div>}</section>
    {selectedTopic && <div className="topic-dialog-backdrop" role="presentation" onMouseDown={() => setSelectedTopic(null)}><section className="topic-dialog" role="dialog" aria-modal="true" aria-labelledby="topic-title" onMouseDown={e => e.stopPropagation()}><button className="dialog-close" onClick={() => setSelectedTopic(null)}>×</button><p className="eyebrow">Concept performance</p><h3 id="topic-title">{label('Topic', selectedTopic.topic_id)}</h3><strong className={`topic-score ${tone(selectedTopic.classification)}`}>{score(selectedTopic.mastery_score)}</strong><p>{selectedTopic.classification} · {selectedTopic.evidence_count} evidence items · {selectedTopic.confidence_level}</p><h4>Mastery history</h4>{topicHistory.length ? <ul>{topicHistory.map(point => <li key={`${point.recorded_at}-${point.assessment_attempt_id}`}>{date(point.recorded_at)} <span>{score(point.previous_score)} → {score(point.updated_score)}</span></li>)}</ul> : <p className="panel-description">No earlier mastery changes are available yet.</p>}<button className="dashboard-primary" onClick={() => onStudy(selectedSubject, selectedTopic.topic_id)}>Study this topic <ArrowRight size={16} /></button></section></div>}
  </main>;
};
