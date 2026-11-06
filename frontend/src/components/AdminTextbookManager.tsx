import React, { useEffect, useMemo, useState } from 'react';
import { AlertCircle, CheckCircle2, FileText, Loader2, RefreshCw, UploadCloud } from 'lucide-react';
import { getDocumentStatus, listAdminChapters, listAdminGrades, listAdminSubjects, listDocuments, uploadDocument } from '../api/client';
import { CurriculumChapter, CurriculumSubject, Document, Grade } from '../types';

const statusLabel = (status: Document['processing_status']) => ({ pending: 'Queued for ingestion', processing: 'Extracting and embedding', completed: 'Ready for retrieval', failed: 'Ingestion failed' }[status] || status);

export const AdminTextbookManager: React.FC = () => {
  const [grades, setGrades] = useState<Grade[]>([]); const [subjects, setSubjects] = useState<CurriculumSubject[]>([]); const [chapters, setChapters] = useState<CurriculumChapter[]>([]); const [documents, setDocuments] = useState<Document[]>([]);
  const [gradeId, setGradeId] = useState(''); const [subjectId, setSubjectId] = useState(''); const [chapterId, setChapterId] = useState(''); const [title, setTitle] = useState(''); const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(true); const [uploading, setUploading] = useState(false); const [message, setMessage] = useState(''); const [error, setError] = useState('');
  const selectedGrade = useMemo(() => grades.find(item => item.id === gradeId), [grades, gradeId]);
  const selectedSubject = useMemo(() => subjects.find(item => item.id === subjectId), [subjects, subjectId]);
  const selectedChapter = useMemo(() => chapters.find(item => item.id === chapterId), [chapters, chapterId]);
  const refreshDocuments = () => listDocuments().then(setDocuments).catch(() => setError('Uploaded textbooks could not be loaded.'));

  useEffect(() => { Promise.all([listAdminGrades(), listDocuments()]).then(([curriculum, textbookRows]) => { setGrades(curriculum); setDocuments(textbookRows); }).catch(err => setError(err.response?.data?.detail || 'Administrator curriculum is unavailable.')).finally(() => setLoading(false)); }, []);
  useEffect(() => { setSubjectId(''); setChapterId(''); setSubjects([]); setChapters([]); if (gradeId) listAdminSubjects(gradeId).then(setSubjects).catch(err => setError(err.response?.data?.detail || 'Subjects are unavailable.')); }, [gradeId]);
  useEffect(() => { setChapterId(''); setChapters([]); if (subjectId) listAdminChapters(subjectId).then(setChapters).catch(err => setError(err.response?.data?.detail || 'Chapters are unavailable.')); }, [subjectId]);
  useEffect(() => {
    const active = documents.some(document => document.processing_status === 'pending' || document.processing_status === 'processing');
    if (!active) return;
    const timer = window.setInterval(() => Promise.all(documents.filter(document => document.processing_status === 'pending' || document.processing_status === 'processing').map(document => getDocumentStatus(document.id))).then(updated => setDocuments(current => current.map(document => ({ ...document, ...(updated.find(item => item.id === document.id) || {}) })))).catch(() => undefined), 5000);
    return () => window.clearInterval(timer);
  }, [documents]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); if (!file || !title.trim() || !gradeId || !subjectId) return;
    setUploading(true); setMessage(''); setError('');
    const form = new FormData(); form.append('file', file); form.append('title', title.trim()); form.append('grade_id', gradeId); form.append('subject_id', subjectId);
    if (chapterId) form.append('chapter_id', chapterId);
    if (selectedGrade) form.append('grade', selectedGrade.name); if (selectedSubject) form.append('subject', selectedSubject.name); if (selectedChapter) form.append('chapter', selectedChapter.name);
    try { const document = await uploadDocument(form); setDocuments(current => [document, ...current]); setMessage('PDF uploaded. The existing Celery ingestion pipeline is now processing it.'); setTitle(''); setFile(null); setChapterId(''); }
    catch (err: any) { setError(err.response?.data?.detail || 'Document upload failed.'); }
    finally { setUploading(false); }
  };

  if (loading) return <main className="dashboard-shell"><div className="dashboard-loading"><RefreshCw className="spin" /> Loading textbook management…</div></main>;
  return <main className="dashboard-shell admin-textbooks"><div className="dashboard-heading"><div><p className="eyebrow">ADMINISTRATION</p><h2>Textbook management</h2><p>Attach every PDF to its normalized curriculum before the existing ingestion pipeline begins.</p></div></div>{error && <p className="auth-error">{error}</p>}
    <div className="dashboard-split"><section className="dashboard-panel"><h3>Upload a textbook PDF</h3><form className="admin-upload-form" onSubmit={submit}><label>Textbook title<input value={title} onChange={event => setTitle(event.target.value)} required /></label><label>Grade<select value={gradeId} onChange={event => setGradeId(event.target.value)} required><option value="">Select grade</option>{grades.map(grade => <option key={grade.id} value={grade.id}>{grade.name}</option>)}</select></label><label>Subject<select value={subjectId} onChange={event => setSubjectId(event.target.value)} disabled={!gradeId} required><option value="">Select Science subject</option>{subjects.map(subject => <option key={subject.id} value={subject.id}>{subject.name}</option>)}</select></label><label>Chapter <small>(optional for multi-chapter textbooks)</small><select value={chapterId} onChange={event => setChapterId(event.target.value)} disabled={!subjectId}><option value="">Whole subject / multiple chapters</option>{chapters.map(chapter => <option key={chapter.id} value={chapter.id}>Chapter {chapter.chapter_number}: {chapter.name}</option>)}</select></label><label>PDF file<input type="file" accept="application/pdf,.pdf" onChange={event => setFile(event.target.files?.[0] || null)} required /></label><button className="dashboard-primary" disabled={uploading || !file || !title.trim() || !gradeId || !subjectId}>{uploading ? <><Loader2 className="spin" size={16} /> Uploading</> : <><UploadCloud size={16} /> Start ingestion</>}</button></form>{message && <p className="admin-success"><CheckCircle2 size={16} /> {message}</p>}</section>
      <section className="dashboard-panel"><div className="section-title"><div><p className="eyebrow">INGESTION QUEUE</p><h3>Uploaded textbooks</h3></div><button className="text-button" onClick={refreshDocuments}>Refresh</button></div>{documents.length ? <div className="admin-document-list">{documents.map(document => <article key={document.id}><FileText size={19} /><div><b>{document.title}</b><small>{document.grade || 'Unmapped grade'} · {document.subject || 'Unmapped subject'}{document.chapter ? ` · ${document.chapter}` : ''}</small><span className={`document-status ${document.processing_status}`}>{statusLabel(document.processing_status)}</span></div>{document.processing_status === 'failed' && <AlertCircle className="auth-error" size={18} />}</article>)}</div> : <p className="dashboard-empty compact">No textbook uploads yet.</p>}</section></div>
  </main>;
};
