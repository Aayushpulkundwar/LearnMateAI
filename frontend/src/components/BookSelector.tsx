import React from 'react';
import { Document } from '../types';
import { BookOpen, Layers, GraduationCap, FileText } from 'lucide-react';

interface BookSelectorProps {
  documents: Document[];
  selectedDocId?: string;
  selectedSubject?: string;
  selectedGrade?: string;
  selectedChapter?: string;
  onDocChange: (docId?: string) => void;
  onSubjectChange: (subject?: string) => void;
  onGradeChange: (grade?: string) => void;
  onChapterChange: (chapter?: string) => void;
}

export const BookSelector: React.FC<BookSelectorProps> = ({
  documents,
  selectedDocId,
  selectedSubject,
  selectedGrade,
  selectedChapter,
  onDocChange,
  onSubjectChange,
  onGradeChange,
  onChapterChange,
}) => {
  const subjects = Array.from(new Set(documents.map((d) => d.subject).filter(Boolean)));
  const grades = Array.from(new Set(documents.map((d) => d.grade).filter(Boolean)));
  const chapters = Array.from(new Set(documents.map((d) => d.chapter).filter(Boolean)));

  return (
    <div className="selector-bar">
      <div className="selector-group">
        <label className="selector-label">
          <BookOpen className="icon" size={16} /> Textbook Document
        </label>
        <select
          value={selectedDocId || ''}
          onChange={(e) => onDocChange(e.target.value || undefined)}
          className="selector-input"
        >
          <option value="">-- All Prescribed Textbooks --</option>
          {documents.map((doc) => (
            <option key={doc.id} value={doc.id}>
              {doc.title} ({doc.processing_status})
            </option>
          ))}
        </select>
      </div>

      <div className="selector-group">
        <label className="selector-label">
          <GraduationCap className="icon" size={16} /> Grade / Class
        </label>
        <select
          value={selectedGrade || ''}
          onChange={(e) => onGradeChange(e.target.value || undefined)}
          className="selector-input"
        >
          <option value="">-- All Grades --</option>
          {grades.map((g) => (
            <option key={g} value={g}>
              Grade {g}
            </option>
          ))}
        </select>
      </div>

      <div className="selector-group">
        <label className="selector-label">
          <Layers className="icon" size={16} /> Subject
        </label>
        <select
          value={selectedSubject || ''}
          onChange={(e) => onSubjectChange(e.target.value || undefined)}
          className="selector-input"
        >
          <option value="">-- All Subjects --</option>
          {subjects.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      <div className="selector-group">
        <label className="selector-label">
          <FileText className="icon" size={16} /> Chapter
        </label>
        <select
          value={selectedChapter || ''}
          onChange={(e) => onChapterChange(e.target.value || undefined)}
          className="selector-input"
        >
          <option value="">-- All Chapters --</option>
          {chapters.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
};
