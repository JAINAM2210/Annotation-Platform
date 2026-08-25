import { useEffect, useMemo, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { CheckCircle2, ClipboardList, Download, FileText, LogOut, Moon, SearchCheck, ShieldCheck, Sun, Users } from 'lucide-react';
import { useAuth } from '../../auth/AuthContext';
import { useTheme } from '../../theme/ThemeContext';
import { Button, IconButton, StatusPill } from '../../ui/Primitives';
import { useWorkspaceData, WorkspaceDataProvider } from './WorkspaceDataContext';

const REVIEW_SEEN_STORAGE_PREFIX = 'annotationPlatform.seenReviewSubmissions';

function reviewSeenStorageKey(userId: string) {
  return `${REVIEW_SEEN_STORAGE_PREFIX}.${userId}`;
}

function readSeenReviewSubmissions(userId: string) {
  if (!userId) return new Set<string>();
  try {
    const value = JSON.parse(window.localStorage.getItem(reviewSeenStorageKey(userId)) ?? '[]');
    return new Set<string>(Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []);
  } catch {
    return new Set<string>();
  }
}

function writeSeenReviewSubmissions(userId: string, submissionIds: Set<string>) {
  try {
    window.localStorage.setItem(reviewSeenStorageKey(userId), JSON.stringify([...submissionIds]));
  } catch {
    // The in-memory state still clears the badge when browser storage is unavailable.
  }
}

function WorkspaceFrame() {
  const navigate = useNavigate();
  const location = useLocation();
  const { currentUser, isFirebaseVerified, mayManageAnnotators, mayManageReviewers, isAdmin, signOutUser } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const {
    annotatorRequests,
    reviewerRequests,
    reviewQueues,
    ensureAnnotatorRequests,
    ensureReviewerRequests,
    ensureReviewQueue,
  } = useWorkspaceData();
  const [seenReviewSubmissionIds, setSeenReviewSubmissionIds] = useState<Set<string>>(() => new Set());
  const ThemeIcon = theme === 'light' ? Moon : Sun;
  const pendingRequestCount = (mayManageAnnotators ? annotatorRequests.pending.data.length : 0)
    + (mayManageReviewers ? reviewerRequests.pending.data.length : 0);
  const canReview = mayManageAnnotators || mayManageReviewers;
  const submittedReviewIds = useMemo(
    () => reviewQueues.submitted.data
      .filter((submission) => submission.status === 'submitted')
      .map((submission) => submission.submission_id),
    [reviewQueues.submitted.data]
  );
  const pendingReviewCount = canReview
    ? submittedReviewIds.filter((submissionId) => !seenReviewSubmissionIds.has(submissionId)).length
    : 0;

  useEffect(() => {
    setSeenReviewSubmissionIds(readSeenReviewSubmissions(currentUser?.id ?? ''));
  }, [currentUser?.id]);

  useEffect(() => {
    const userId = currentUser?.id ?? '';
    if (!userId || !canReview || !location.pathname.startsWith('/app/review') || submittedReviewIds.length === 0) return;
    setSeenReviewSubmissionIds((current) => {
      const next = new Set(current);
      let changed = false;
      submittedReviewIds.forEach((submissionId) => {
        if (next.has(submissionId)) return;
        next.add(submissionId);
        changed = true;
      });
      if (!changed) return current;
      writeSeenReviewSubmissions(userId, next);
      return next;
    });
  }, [canReview, currentUser?.id, location.pathname, submittedReviewIds]);

  useEffect(() => {
    const refreshPendingRequests = (force: boolean) => {
      const tasks: Promise<unknown>[] = [];
      if (mayManageAnnotators) tasks.push(ensureAnnotatorRequests('pending', force));
      if (mayManageReviewers) tasks.push(ensureReviewerRequests('pending', force));
      if (canReview) tasks.push(ensureReviewQueue('submitted', force));
      void Promise.all(tasks).catch(() => undefined);
    };

    refreshPendingRequests(false);
    const intervalId = window.setInterval(() => refreshPendingRequests(true), 60000);
    return () => window.clearInterval(intervalId);
  }, [canReview, ensureAnnotatorRequests, ensureReviewQueue, ensureReviewerRequests, mayManageAnnotators, mayManageReviewers]);

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
          {canReview ? (
            <NavLink to="/app/review" aria-label={`Review${pendingReviewCount ? `, ${pendingReviewCount} submitted papers` : ''}`}>
              <SearchCheck aria-hidden="true" size={15} /> Review
              {pendingReviewCount > 0 ? (
                <span className="nav-notification" role="status" aria-label={`${pendingReviewCount} papers awaiting review`}>
                  {pendingReviewCount > 99 ? '99+' : pendingReviewCount}
                </span>
              ) : null}
            </NavLink>
          ) : null}
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
