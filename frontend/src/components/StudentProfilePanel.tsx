import React, { useState } from 'react';
import { listGrades, updateMyProfile } from '../api/client';
import { Grade, StudentProfile } from '../types';

interface Props { student: StudentProfile; onUpdated: (student: StudentProfile) => void; onBack: () => void; }

export const StudentProfilePanel: React.FC<Props> = ({ student, onUpdated, onBack }) => {
  const [displayName, setDisplayName] = useState(student.display_name || '');
  const [gradeId, setGradeId] = useState(student.grade_id);
  const [message, setMessage] = useState<string | null>(null);
  const [grades, setGrades] = useState<Grade[]>([]);
  React.useEffect(() => { listGrades().then(setGrades).catch(() => setMessage('Grades are unavailable.')); }, []);
  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    try {
      onUpdated(await updateMyProfile({ display_name: displayName || undefined, grade_id: gradeId }));
      setMessage('Profile updated.');
    } catch (err: any) {
      setMessage(err.response?.data?.detail || 'Profile update failed.');
    }
  };
  return <main className="auth-page"><form className="auth-card" onSubmit={save}>
    <h2>Student profile</h2>
    <p>{student.email}</p>
    <label>Display name<input value={displayName} maxLength={255} onChange={(e) => setDisplayName(e.target.value)} /></label>
    <label>Grade<select value={gradeId} required onChange={(e) => setGradeId(e.target.value)}>{grades.map((grade) => <option key={grade.id} value={grade.id}>{grade.name}</option>)}</select></label>
    <p>Current grade: {student.grade_name}</p>
    {message && <p>{message}</p>}
    <button className="upload-btn">Save profile</button>
    <button className="auth-link" type="button" onClick={onBack}>Back to tutor</button>
  </form></main>;
};
