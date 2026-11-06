import React, { createContext, useCallback, useContext, useState } from 'react';
import { listCurriculumChapters, listCurriculumSubjects } from '../api/client';
import { CurriculumChapter, CurriculumSubject } from '../types';

type Selection = { subjectId: string; subjectName: string; chapterId?: string; chapterName?: string };
type StudySessionValue = {
  selection: Selection | null; subjects: CurriculumSubject[]; chapters: CurriculumChapter[];
  loading: boolean; error: string | null;
  loadSubjects: () => Promise<CurriculumSubject[]>;
  loadChapters: (subjectId: string) => Promise<CurriculumChapter[]>;
  chooseSubject: (subject: CurriculumSubject) => void;
  chooseChapter: (chapter: CurriculumChapter) => void;
  clearChapter: () => void;
  clearSelection: () => void;
};

const key = 'learnmate_study_selection';
const StudySessionContext = createContext<StudySessionValue | undefined>(undefined);

function readSaved(): Selection | null {
  try { const value = sessionStorage.getItem(key); return value ? JSON.parse(value) as Selection : null; } catch { return null; }
}
function save(value: Selection | null) { if (value) sessionStorage.setItem(key, JSON.stringify(value)); else sessionStorage.removeItem(key); }

export const StudySessionProvider: React.FC<React.PropsWithChildren> = ({ children }) => {
  const [selection, setSelection] = useState<Selection | null>(readSaved);
  const [subjects, setSubjects] = useState<CurriculumSubject[]>([]);
  const [chapters, setChapters] = useState<CurriculumChapter[]>([]);
  const [loading, setLoading] = useState(false); const [error, setError] = useState<string | null>(null);
  const commit = useCallback((next: Selection | null) => { setSelection(next); save(next); }, []);
  const loadSubjects = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const result = await listCurriculumSubjects(); setSubjects(result);
      const saved = readSaved();
      if (saved && !result.some(subject => subject.id === saved.subjectId)) { commit(null); setChapters([]); }
      return result;
    } catch (err: any) { setError(err.response?.status === 401 ? 'Your session has expired. Please log in again.' : 'Unable to load your curriculum.'); throw err; }
    finally { setLoading(false); }
  }, [commit]);
  const loadChapters = useCallback(async (subjectId: string) => {
    setLoading(true); setError(null);
    try {
      const result = await listCurriculumChapters(subjectId); setChapters(result);
      const saved = readSaved();
      if (saved?.subjectId === subjectId && saved.chapterId && !result.some(chapter => chapter.id === saved.chapterId)) commit({ subjectId: saved.subjectId, subjectName: saved.subjectName });
      return result;
    } catch (err: any) { setError(err.response?.status === 401 ? 'Your session has expired. Please log in again.' : 'Unable to load chapters.'); throw err; }
    finally { setLoading(false); }
  }, [commit]);
  const chooseSubject = useCallback((subject: CurriculumSubject) => { setChapters([]); commit({ subjectId: subject.id, subjectName: subject.name }); }, [commit]);
  const chooseChapter = useCallback((chapter: CurriculumChapter) => { if (selection) commit({ ...selection, chapterId: chapter.id, chapterName: chapter.name }); }, [commit, selection]);
  const clearChapter = useCallback(() => { if (selection) commit({ subjectId: selection.subjectId, subjectName: selection.subjectName }); }, [commit, selection]);
  const clearSelection = useCallback(() => { setChapters([]); commit(null); }, [commit]);
  return <StudySessionContext.Provider value={{ selection, subjects, chapters, loading, error, loadSubjects, loadChapters, chooseSubject, chooseChapter, clearChapter, clearSelection }}>{children}</StudySessionContext.Provider>;
};
export const useStudySession = () => { const value = useContext(StudySessionContext); if (!value) throw new Error('StudySessionProvider is required.'); return value; };
