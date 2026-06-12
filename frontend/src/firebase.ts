import { getApp, getApps, initializeApp, type FirebaseApp } from 'firebase/app';
import { browserSessionPersistence, getAuth, setPersistence } from 'firebase/auth';

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

function getOrCreateApp(): FirebaseApp {
  return getApps().length > 0 ? getApp() : initializeApp(firebaseConfig);
}

export const firebaseApp = getOrCreateApp();
export const firebaseAuth = getAuth(firebaseApp);

let persistencePromise: Promise<void> | null = null;

export function ensureFirebaseSessionPersistence(): Promise<void> {
  if (!persistencePromise) {
    persistencePromise = setPersistence(firebaseAuth, browserSessionPersistence);
  }
  return persistencePromise;
}
