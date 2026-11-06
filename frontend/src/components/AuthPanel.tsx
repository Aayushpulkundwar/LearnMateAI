import React, { useState } from 'react';
import { listGrades, loginStudent, registerStudent } from '../api/client';
import { Grade, StudentProfile } from '../types';

interface AuthPanelProps {
  onAuthenticated: (student: StudentProfile) => void;
}

export const GradeSelect: React.FC<{
  grades: Grade[]; value: string; loading: boolean; onChange: (id: string) => void;
}> = ({ grades, value, loading, onChange }) => <label>Grade
  <select value={value} required disabled={loading || !grades.length} onChange={(event) => onChange(event.target.value)}>
    <option value="">{loading ? 'Loading grades...' : 'Select your grade'}</option>
    {grades.map((grade) => <option key={grade.id} value={grade.id}>{grade.name}</option>)}
  </select>
</label>;

export const AuthPanel: React.FC<AuthPanelProps> = ({ onAuthenticated }) => {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [gradeId, setGradeId] = useState('');
  const [grades, setGrades] = useState<Grade[]>([]);
  const [gradesLoading, setGradesLoading] = useState(false);
  const [gradesError, setGradesError] = useState<string | null>(null);
  const [gradesRequest, setGradesRequest] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const result = mode === 'login'
        ? await loginStudent({ email, password })
        : await registerStudent({ email, password, display_name: displayName || undefined, grade_id: gradeId });
      onAuthenticated(result.student);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Unable to authenticate. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => {
    if (mode !== 'register') return;
    let active = true;
    setGradesLoading(true);
    setGradesError(null);
    listGrades().then((rows) => {
      if (!active) return;
      if (!rows.length) throw new Error('No grades configured');
      setGrades(rows);
      setGradeId((selected) => rows.some((grade) => grade.id === selected) ? selected : '');
    }).catch(() => {
      if (!active) return;
      setGrades([]);
      setGradeId('');
      setGradesError('Unable to load grades. Check your connection and try again.');
    }).finally(() => { if (active) setGradesLoading(false); });
    return () => { active = false; };
  }, [mode, gradesRequest]);

  return <main className="auth-page">
    <form className="auth-card" onSubmit={submit}>
      <h2>{mode === 'login' ? 'Welcome back' : 'Create your student account'}</h2>
      <p>Use your account to keep learning activity and progress private.</p>
      {mode === 'register' && <>
        <label>Display name<input value={displayName} maxLength={255} onChange={(e) => setDisplayName(e.target.value)} /></label>
        <GradeSelect grades={grades} value={gradeId} loading={gradesLoading} onChange={setGradeId} />
        {gradesError && <div role="alert"><p className="auth-error">{gradesError}</p><button type="button" className="auth-link" onClick={() => setGradesRequest((value) => value + 1)}>Retry loading grades</button></div>}
      </>}
      <label>Email<input type="email" value={email} required onChange={(e) => setEmail(e.target.value)} /></label>
      <label>Password<input type="password" value={password} required minLength={mode === 'register' ? 12 : 1} onChange={(e) => setPassword(e.target.value)} /></label>
      {error && <p className="auth-error">{error}</p>}
      <button className="upload-btn" disabled={loading || (mode === 'register' && (gradesLoading || !gradeId || !!gradesError))}>{loading ? 'Please wait…' : mode === 'login' ? 'Log in' : 'Register'}</button>
      <button type="button" className="auth-link" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(null); }}>
        {mode === 'login' ? 'Need an account? Register' : 'Already have an account? Log in'}
      </button>
    </form>
  </main>;
};
