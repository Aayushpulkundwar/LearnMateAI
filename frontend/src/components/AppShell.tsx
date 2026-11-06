import React, { useEffect, useRef, useState } from 'react';
import { BarChart3, BookOpen, Brain, ClipboardCheck, LayoutDashboard, Menu, X } from 'lucide-react';
type Item = { label: string; icon: React.ElementType; href: string; disabled?: boolean };
export const AppShell: React.FC<React.PropsWithChildren<{ path: string; navigate: (path: string) => void; onOpenTutor: () => void }>> = ({ path, navigate, onOpenTutor, children }) => {
  const [open, setOpen] = useState(false);
  const isTutor = path === '/tutor' || path.startsWith('/study/');
  const shellRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!isTutor) return;
    const shell = shellRef.current;
    const viewport = window.visualViewport;
    // Dynamic viewport units do not account for the keyboard in every browser.
    const resize = () => {
      if (viewport && viewport.scale !== 1) return;
      shell?.style.setProperty('--tutor-viewport-height', `${viewport?.height ?? window.innerHeight}px`);
    };
    resize();
    viewport?.addEventListener('resize', resize);
    window.addEventListener('resize', resize);
    return () => {
      viewport?.removeEventListener('resize', resize);
      window.removeEventListener('resize', resize);
      shell?.style.removeProperty('--tutor-viewport-height');
    };
  }, [isTutor]);
  const items: Item[] = [
    { label: 'Dashboard', icon: LayoutDashboard, href: '/' }, { label: 'My Subjects', icon: BookOpen, href: '/subjects' },
    { label: 'AI Tutor', icon: Brain, href: '/tutor' },
    { label: 'Diagnostic Test', icon: ClipboardCheck, href: '/diagnostic' }, { label: 'My Progress', icon: BarChart3, href: '/progress' },
  ];
  return <div ref={shellRef} className={`product-shell${isTutor ? ' product-shell--tutor' : ''}`}><button className="mobile-menu" aria-label="Open navigation" onClick={() => setOpen(true)}><Menu /></button>{open && <button className="nav-backdrop" aria-label="Close navigation" onClick={() => setOpen(false)} />}
    <aside className={`product-sidebar ${open ? 'is-open' : ''}`}><div className="sidebar-brand"><span className="brand-mark"><Brain size={21} /></span><span>LearnMate<span>AI</span></span><button aria-label="Close navigation" className="sidebar-close" onClick={() => setOpen(false)}><X /></button></div><nav aria-label="Student navigation">{items.map(item => { const Icon = item.icon; const active = path === item.href || (item.href === '/' && path === '/dashboard') || (item.href === '/subjects' && path.startsWith('/subjects')) || (item.href === '/tutor' && path.startsWith('/study/')); return <button key={item.label} className={active ? 'active' : ''} onClick={() => { if (item.label === 'AI Tutor') onOpenTutor(); else navigate(item.href); setOpen(false); }}><Icon size={18} />{item.label}</button>; })}</nav><div className="sidebar-student"><div className="student-avatar">G</div><div><b>Guest workspace</b><small>No account needed</small></div></div></aside>
    <section className="shell-main"><header className="topbar"><div><p className="topbar-label">Current learning</p><strong>Explore your learning workspace</strong></div><span className="profile-chip"><span>G</span><b>Guest</b></span></header><div className="shell-content">{children}</div></section>
  </div>;
};
