import { createContext, ReactNode, useContext, useEffect, useMemo, useState } from 'react';
import { onAuthStateChanged, signOut as firebaseSignOut, type User as FirebaseUser } from 'firebase/auth';
import { ApiError, canManageAnnotators, canManageReviewers, fetchMe } from '../api/client';
import { ensureFirebaseSessionPersistence, firebaseAuth } from '../firebase';
import type { UserRead } from '../types';

type AuthContextValue = {
  authReady: boolean;
  firebaseUser: FirebaseUser | null;
  currentUser: UserRead | null;
  sessionError: string;
  isFirebaseVerified: boolean;
  isApproved: boolean;
  isAdmin: boolean;
  mayManageAnnotators: boolean;
  mayManageReviewers: boolean;
  getAccessToken: (forceRefresh?: boolean) => Promise<string>;
  syncCurrentUser: (forceRefresh?: boolean) => Promise<UserRead | null>;
  signOutUser: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

const AUTH_TIMEOUT_MS = 12000;

function withTimeout<T>(promise: Promise<T>, message: string, timeoutMs = AUTH_TIMEOUT_MS): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error(message)), timeoutMs);
    promise
      .then(resolve, reject)
      .finally(() => window.clearTimeout(timer));
  });
}

function formatAuthError(error: unknown): string {
  if (error instanceof ApiError) return `${error.status}: ${error.message}`;
  if (error instanceof Error) return error.message;
  return 'Unable to load the session';
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [authReady, setAuthReady] = useState(false);
  const [firebaseUser, setFirebaseUser] = useState<FirebaseUser | null>(null);
  const [currentUser, setCurrentUser] = useState<UserRead | null>(null);
  const [sessionError, setSessionError] = useState('');
  const [isFirebaseVerified, setIsFirebaseVerified] = useState(false);

  async function getAccessToken(forceRefresh = false) {
    const activeUser = firebaseAuth.currentUser;
    if (!activeUser) throw new Error('No active Firebase session');
    if (forceRefresh) await activeUser.reload();
    setIsFirebaseVerified(activeUser.emailVerified);
    return withTimeout(activeUser.getIdToken(forceRefresh), 'Firebase token request timed out. Check internet access and Firebase configuration.');
  }

  async function syncCurrentUser(forceRefresh = false): Promise<UserRead | null> {
    const activeUser = firebaseAuth.currentUser;
    if (!activeUser) {
      setFirebaseUser(null);
      setCurrentUser(null);
      setIsFirebaseVerified(false);
      return null;
    }

    const token = await getAccessToken(forceRefresh);
    setFirebaseUser(activeUser);
    try {
      const profile = await fetchMe(token);
      setCurrentUser(profile);
      setSessionError('');
      return profile;
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        setCurrentUser(null);
        setSessionError('');
        return null;
      }
      setSessionError(formatAuthError(error));
      throw error;
    }
  }

  async function signOutUser() {
    await firebaseSignOut(firebaseAuth);
    setFirebaseUser(null);
    setCurrentUser(null);
    setIsFirebaseVerified(false);
    setSessionError('');
  }

  useEffect(() => {
    let cancelled = false;
    let authStateResolved = false;

    const startupTimer = window.setTimeout(() => {
      if (cancelled || authStateResolved) return;
      setSessionError('Firebase session initialization timed out. Refresh the page, then check Firebase config and network access if this repeats.');
      setFirebaseUser(firebaseAuth.currentUser);
      setCurrentUser(null);
      setAuthReady(true);
    }, AUTH_TIMEOUT_MS);

    ensureFirebaseSessionPersistence().catch((error) => {
      if (!cancelled) {
        setSessionError(formatAuthError(error));
        setAuthReady(true);
      }
    });

    const unsubscribe = onAuthStateChanged(firebaseAuth, (nextUser) => {
      authStateResolved = true;
      window.clearTimeout(startupTimer);
      if (cancelled) return;
      setAuthReady(false);
      setFirebaseUser(nextUser);
      setIsFirebaseVerified(nextUser?.emailVerified ?? false);

      if (!nextUser) {
        setCurrentUser(null);
        setSessionError('');
        setAuthReady(true);
        return;
      }

      withTimeout(syncCurrentUser(false), 'Platform session sync timed out. Check that the backend is running and Firebase token verification is working.')
        .catch((error) => {
          if (!cancelled) {
            setCurrentUser(null);
            setSessionError(formatAuthError(error));
          }
        })
        .finally(() => {
          if (!cancelled) setAuthReady(true);
        });
    });

    return () => {
      cancelled = true;
      window.clearTimeout(startupTimer);
      unsubscribe();
    };
  }, []);

  const isApproved = Boolean(
    currentUser?.is_active &&
    currentUser.status === 'approved' &&
    (isFirebaseVerified || currentUser.email_verified)
  );
  const isAdmin = Boolean(isApproved && currentUser?.role === 'admin');
  const mayManageAnnotators = canManageAnnotators(currentUser) && isApproved;
  const mayManageReviewers = canManageReviewers(currentUser) && isApproved;

  const value = useMemo<AuthContextValue>(() => ({
    authReady,
    firebaseUser,
    currentUser,
    sessionError,
    isFirebaseVerified,
    isApproved,
    isAdmin,
    mayManageAnnotators,
    mayManageReviewers,
    getAccessToken,
    syncCurrentUser,
    signOutUser,
  }), [authReady, firebaseUser, currentUser, sessionError, isFirebaseVerified, isApproved, isAdmin, mayManageAnnotators, mayManageReviewers]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider');
  return value;
}
