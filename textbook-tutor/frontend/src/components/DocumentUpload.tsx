import React, { useState } from 'react';
import { uploadDocument } from '../api/client';
import { UploadCloud, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';

interface DocumentUploadProps {
  onUploadSuccess: () => void;
}

export const DocumentUpload: React.FC<DocumentUploadProps> = ({ onUploadSuccess }) => {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [subject, setSubject] = useState('');
  const [grade, setGrade] = useState('');
  const [chapter, setChapter] = useState('');

  const [isUploading, setIsUploading] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [isError, setIsError] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file || !title) return;

    setIsUploading(true);
    setStatusMsg('Uploading PDF to MinIO object storage...');
    setIsError(false);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('title', title);
      if (subject) formData.append('subject', subject);
      if (grade) formData.append('grade', grade);
      if (chapter) formData.append('chapter', chapter);

      const doc = await uploadDocument(formData);
      setStatusMsg(`Textbook uploaded! Processing started (Status: ${doc.processing_status})`);
      setFile(null);
      setTitle('');
      setSubject('');
      setGrade('');
      setChapter('');
      onUploadSuccess();
    } catch (err: any) {
      setIsError(true);
      setStatusMsg(err.response?.data?.detail || 'Document upload failed');
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="upload-card">
      <div className="upload-header">
        <UploadCloud size={20} className="icon" />
        <h4>Upload Prescribed Textbook (PDF)</h4>
      </div>

      <form onSubmit={handleSubmit} className="upload-form">
        <div className="form-group">
          <label>Book Title *</label>
          <input
            type="text"
            required
            placeholder="e.g. NCERT Class 10 Science"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Subject</label>
            <input
              type="text"
              placeholder="e.g. Science"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
            />
          </div>
          <div className="form-group">
            <label>Grade / Class</label>
            <input
              type="text"
              placeholder="e.g. 10"
              value={grade}
              onChange={(e) => setGrade(e.target.value)}
            />
          </div>
        </div>

        <div className="form-group">
          <label>Chapter Name</label>
          <input
            type="text"
            placeholder="e.g. Chemical Reactions and Equations"
            value={chapter}
            onChange={(e) => setChapter(e.target.value)}
          />
        </div>

        <div className="form-group">
          <label>Textbook PDF File *</label>
          <input
            type="file"
            accept=".pdf"
            required
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
        </div>

        <button type="submit" disabled={isUploading || !file || !title} className="upload-btn">
          {isUploading ? (
            <>
              <Loader2 className="spinner" size={16} /> Uploading...
            </>
          ) : (
            'Start Ingestion Pipeline'
          )}
        </button>
      </form>

      {statusMsg && (
        <div className={`status-banner ${isError ? 'error' : 'success'}`}>
          {isError ? <AlertCircle size={16} /> : <CheckCircle2 size={16} />}
          <span>{statusMsg}</span>
        </div>
      )}
    </div>
  );
};
