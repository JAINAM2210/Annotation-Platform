import { useEffect } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { CheckCircle2, ClipboardList, Download, FileText, LogOut, Moon, SearchCheck, ShieldCheck, Sun, Users } from 'lucide-react';
import { useAuth } from '../../auth/AuthContext';
import { useTheme } from '../../theme/ThemeContext';
import { Button, IconButton, StatusPill } from '../../ui/Primitives';
import { useWorkspaceData, WorkspaceDataProvider } from './WorkspaceDataContext';

function WorkspaceFrame() {
  const navigate = useNavigate();
  const { currentUser, isFirebaseVerified, mayManageAnnotators, mayManageReviewers, isAdmin, signOutUser } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const {
    annotatorRequests,
    reviewerRequests,
    ensureAnnotatorRequests,
    ensureReviewerRequests,
  } = useWorkspaceData();
  const ThemeIcon = theme === 'light' ? Moon : Sun;
  const pendingRequestCount = (mayManageAnnotators ? annotatorRequests.pending.data.length : 0)
    + (mayManageReviewers ? reviewerRequests.pending.data.length : 0);

  useEffect(() => {
    const refreshPendingRequests = (force: boolean) => {
      const tasks: Promise<unknown>[] = [];
      if (mayManageAnnotators) tasks.push(ensureAnnotatorRequests('pending', force));
      if (mayManageReviewers) tasks.push(ensureReviewerRequests('pending', force));
      void Promise.all(tasks).catch(() => undefined);
    };

    refreshPendingRequests(false);
    const intervalId = window.setInterval(() => refreshPendingRequests(true), 60000);
    return () => window.clearInterval(intervalId);
  }, [ensureAnnotatorRequests, ensureReviewerRequests, mayManageAnnotators, mayManageReviewers]);

  async function handleSignOut() {
    await signOutUser();
    navigate('/signin', { replace: true });
  }

  return (
    <div className="workspace-root">
      <header className="workspace-topbar">
        <div className="workspace-brand">
          <span className="brand-mark brand-mark--workspace"><span className="brand-mark__logo">AP</span><span>Annotation Platform</span></span>
          <span>Low Temperature Plasma</span>
        </div>
        <nav className="workspace-nav" aria-label="Workspace">
          <NavLink to="/app/editor"><FileText aria-hidden="true" size={15} /> Editor</NavLink>
          <NavLink to="/app/assignments"><ClipboardList aria-hidden="true" size={15} /> Assignments</NavLink>
          {mayManageAnnotators || mayManageReviewers ? (
            <NavLink to="/app/requests" aria-label={`Requests${pendingRequestCount ? `, ${pendingRequestCount} pending` : ''}`}>
              <ShieldCheck aria-hidden="true" size={15} /> Requests
              {pendingRequestCount > 0 ? (
                <span className="nav-notification" role="status" aria-label={`${pendingRequestCount} pending account requests`}>
                  {pendingRequestCount > 99 ? '99+' : pendingRequestCount}
                </span>
              ) : null}
            </NavLink>
          ) : null}
          {mayManageAnnotators || mayManageReviewers ? <NavLink to="/app/review"><SearchCheck aria-hidden="true" size={15} /> Review</NavLink> : null}
          <NavLink to="/app/exports"><Download aria-hidden="true" size={15} /> Exports</NavLink>
          {isAdmin ? <NavLink to="/app/users"><Users aria-hidden="true" size={15} /> Users</NavLink> : null}
        </nav>
        <div className="workspace-user">
          {currentUser ? (
            <div className="workspace-user__meta">
              <strong>{currentUser.full_name}</strong>
              <span>{currentUser.role} · {currentUser.status}</span>
            </div>
          ) : null}
          {currentUser ? <StatusPill tone={isFirebaseVerified || currentUser.email_verified ? 'approved' : 'pending'} icon={CheckCircle2}>{isFirebaseVerified || currentUser.email_verified ? 'verified' : 'unverified'}</StatusPill> : null}
          <IconButton label={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'} icon={ThemeIcon} onClick={toggleTheme} />
          <Button variant="secondary" size="compact" icon={LogOut} onClick={handleSignOut}>Sign out</Button>
        </div>
      </header>
      <Outlet />
    </div>
  );
}

export function WorkspaceLayout() {
  return (
    <WorkspaceDataProvider>
      <WorkspaceFrame />
    </WorkspaceDataProvider>
  );
}
