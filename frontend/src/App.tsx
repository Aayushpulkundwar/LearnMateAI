import React, { useEffect, useState } from 'react';
import { AppShell } from './components/AppShell';
import { PublicWorkspace } from './components/PublicWorkspace';

export const publicPath = (path: string): string =>
  /^\/(login|register|signup)\/?$/.test(path) ? '/' : path;

export const App: React.FC = () => {
  const [path, setPath] = useState(() => publicPath(window.location.pathname));
  useEffect(() => {
    // Replace retired authentication URLs so Back cannot reopen an auth page.
    if (window.location.pathname !== path) window.history.replaceState({}, '', path);
    const onBack = () => setPath(publicPath(window.location.pathname));
    window.addEventListener('popstate', onBack);
    return () => window.removeEventListener('popstate', onBack);
  }, [path]);
  const navigate = (next: string) => {
    const destination = publicPath(next);
    window.history.pushState({}, '', destination);
    setPath(destination);
  };
  return <AppShell path={path} navigate={navigate} onOpenTutor={() => navigate('/tutor')}>
    <PublicWorkspace path={path} navigate={navigate} />
  </AppShell>;
};
