import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { LoadingScreen } from '../ui/LoadingScreen';

function SessionErrorScreen({ message }: { message: string }) {
  return (
    <main className="route-loading">
      <div className="status-card">
        <strong>Session could not be loaded</strong>
        <p>{message}</p>
      </div>
    </main>
  );
}

function nextRouteForSession({
  hasFirebaseUser,
  hasProfile,
  isVerified,
  isApproved,
}: {
  hasFirebaseUser: boolean;
  hasProfile: boolean;
  isVerified: boolean;
  isApproved: boolean;
}) {
  if (!hasFirebaseUser) return '/signin';
  if (!isVerified) return '/verify-email';
  if (!hasProfile) return '/complete-profile';
  if (!isApproved) return '/account-status';
  return '/app/editor';
}

export function RootRedirect() {
  const { authReady, firebaseUser, currentUser, isFirebaseVerified, isApproved, sessionError } = useAuth();
  if (!authReady) return sessionError ? <SessionErrorScreen message={sessionError} /> : <LoadingScreen label="Loading session..." />;
  if (sessionError && firebaseUser && !currentUser) return <SessionErrorScreen message={sessionError} />;

  return (
    <Navigate
      to={nextRouteForSession({
        hasFirebaseUser: Boolean(firebaseUser),
        hasProfile: Boolean(currentUser),
        isVerified: Boolean(isFirebaseVerified || currentUser?.email_verified),
        isApproved,
      })}
      replace
    />
  );
}

export function PublicOnlyRoute() {
  const { authReady, firebaseUser, sessionError } = useAuth();
  if (!authReady) return sessionError ? <SessionErrorScreen message={sessionError} /> : <LoadingScreen label="Loading session..." />;
  if (firebaseUser) return <Navigate to="/" replace />;
  return <Outlet />;
}

export function RequireFirebaseSession() {
  const { authReady, firebaseUser, sessionError } = useAuth();
  if (!authReady) return sessionError ? <SessionErrorScreen message={sessionError} /> : <LoadingScreen label="Loading session..." />;
  if (!firebaseUser) return <Navigate to="/signin" replace />;
  return <Outlet />;
}

export function RequireMissingProfile() {
  const { authReady, firebaseUser, currentUser, isFirebaseVerified, sessionError } = useAuth();
  if (!authReady) return sessionError ? <SessionErrorScreen message={sessionError} /> : <LoadingScreen label="Loading session..." />;
  if (sessionError && firebaseUser && !currentUser) return <SessionErrorScreen message={sessionError} />;
  if (!firebaseUser) return <Navigate to="/signin" replace />;
  if (!isFirebaseVerified) return <Navigate to="/verify-email" replace />;
  if (currentUser) return <Navigate to="/" replace />;
  return <Outlet />;
}

export function RequireApprovedUser() {
  const { authReady, firebaseUser, currentUser, isFirebaseVerified, isApproved, sessionError } = useAuth();
  if (!authReady) return sessionError ? <SessionErrorScreen message={sessionError} /> : <LoadingScreen label="Loading session..." />;
  if (sessionError && firebaseUser && !currentUser) return <SessionErrorScreen message={sessionError} />;
  if (!firebaseUser) return <Navigate to="/signin" replace />;
  if (!(isFirebaseVerified || currentUser?.email_verified)) return <Navigate to="/verify-email" replace />;
  if (!currentUser) return <Navigate to="/complete-profile" replace />;
  if (!isApproved) return <Navigate to="/account-status" replace />;
  return <Outlet />;
}

export function RequireRequestsAccess() {
  const { mayManageAnnotators, mayManageReviewers } = useAuth();
  if (!mayManageAnnotators && !mayManageReviewers) return <Navigate to="/app/editor" replace />;
  return <Outlet />;
}

export function RequireAdminAccess() {
  const { isAdmin } = useAuth();
  if (!isAdmin) return <Navigate to="/app/editor" replace />;
  return <Outlet />;
}
