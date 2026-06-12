import { lazy, Suspense } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './auth/AuthContext';
import { AccountStatusPage } from './pages/auth/AccountStatusPage';
import { ForgotPasswordPage } from './pages/auth/ForgotPasswordPage';
import { SignInPage } from './pages/auth/SignInPage';
import { VerifyEmailPage } from './pages/auth/VerifyEmailPage';
import { AssignmentsPage } from './pages/workspace/AssignmentsPage';
import { EditorPage } from './pages/workspace/EditorPage';
import { ExportsPage } from './pages/workspace/ExportsPage';
import { RequestsPage } from './pages/workspace/RequestsPage';
import { ReviewPage } from './pages/workspace/ReviewPage';
import { UsersPage } from './pages/workspace/UsersPage';
import { WorkspaceLayout } from './pages/workspace/WorkspaceLayout';
import {
  PublicOnlyRoute,
  RequireAdminAccess,
  RequireApprovedUser,
  RequireFirebaseSession,
  RequireMissingProfile,
  RequireRequestsAccess,
  RootRedirect,
} from './routes/RouteGuards';
import { ThemeProvider } from './theme/ThemeContext';
import { LoadingScreen } from './ui/LoadingScreen';

const RequestAccessPage = lazy(() => import('./pages/auth/RequestAccessPage').then((module) => ({ default: module.RequestAccessPage })));
const CompleteProfilePage = lazy(() => import('./pages/auth/CompleteProfilePage').then((module) => ({ default: module.CompleteProfilePage })));

export default function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <AuthProvider>
          <Suspense fallback={<LoadingScreen label="Loading page..." />}>
          <Routes>
            <Route path="/" element={<RootRedirect />} />
            <Route element={<PublicOnlyRoute />}>
              <Route path="/signin" element={<SignInPage />} />
              <Route path="/request-access" element={<RequestAccessPage />} />
              <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            </Route>
            <Route element={<RequireMissingProfile />}>
              <Route path="/complete-profile" element={<CompleteProfilePage />} />
            </Route>
            <Route element={<RequireFirebaseSession />}>
              <Route path="/verify-email" element={<VerifyEmailPage />} />
              <Route path="/account-status" element={<AccountStatusPage />} />
            </Route>
            <Route element={<RequireApprovedUser />}>
              <Route path="/app" element={<WorkspaceLayout />}>
                <Route index element={<Navigate to="/app/editor" replace />} />
                <Route path="editor" element={<EditorPage />} />
                <Route path="assignments" element={<AssignmentsPage />} />
                <Route path="exports" element={<ExportsPage />} />
                <Route element={<RequireRequestsAccess />}>
                  <Route path="requests" element={<RequestsPage />} />
                  <Route path="review" element={<ReviewPage />} />
                </Route>
                <Route element={<RequireAdminAccess />}>
                  <Route path="users" element={<UsersPage />} />
                </Route>
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          </Suspense>
        </AuthProvider>
      </BrowserRouter>
    </ThemeProvider>
  );
}
