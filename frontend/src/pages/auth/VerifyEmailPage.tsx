import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { LogOut, MailCheck, RefreshCw, Send } from 'lucide-react';
import { sendEmailVerification } from 'firebase/auth';
import { useAuth } from '../../auth/AuthContext';
import { errorMessage, type Message } from '../../lib/status';
import { Button, StatusPill } from '../../ui/Primitives';
import { AuthShell } from './AuthShell';

const RESEND_COOLDOWN_SECONDS = 60;

export function VerifyEmailPage() {
  const navigate = useNavigate();
  const { firebaseUser, currentUser, isFirebaseVerified, syncCurrentUser, signOutUser } = useAuth();
  const [cooldown, setCooldown] = useState(0);
  const [loading, setLoading] = useState('');
  const [message, setMessage] = useState<Message | null>(null);

  const verified = Boolean(isFirebaseVerified || currentUser?.email_verified);

  useEffect(() => {
    if (!verified) return;
    navigate('/', { replace: true });
  }, [navigate, verified]);

  useEffect(() => {
    if (cooldown <= 0) return undefined;
    const timer = window.setInterval(() => setCooldown((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearInterval(timer);
  }, [cooldown]);

  async function handleResend() {
    if (!firebaseUser || cooldown > 0) return;
    setLoading('resend');
    setMessage(null);
    try {
      await sendEmailVerification(firebaseUser);
      setCooldown(RESEND_COOLDOWN_SECONDS);
      setMessage({ type: 'success', text: 'Verification email sent.' });
    } catch (error) {
      setMessage({ type: 'error', text: errorMessage(error) });
    } finally {
      setLoading('');
    }
  }

  async function handleRefresh() {
    setLoading('refresh');
    setMessage(null);
    try {
      await syncCurrentUser(true);
      navigate('/', { replace: true });
    } catch (error) {
      setMessage({ type: 'error', text: errorMessage(error) });
    } finally {
      setLoading('');
    }
  }

  async function handleSignOut() {
    await signOutUser();
    navigate('/signin', { replace: true });
  }

  return (
    <AuthShell title="Verify email" summary={firebaseUser?.email ?? 'Check your inbox.'} message={message}>
      <div className="status-card">
        <StatusPill tone="pending" icon={MailCheck}>verification required</StatusPill>
        <p>Verify this Firebase account before continuing. Open the verification link, then refresh the account status here.</p>
        <p className="auth-verification-note">Cannot find the email? Check your Spam or Junk folder for the account verification message.</p>
      </div>
      <div className="button-row">
        <Button variant="success" icon={RefreshCw} onClick={handleRefresh} disabled={loading === 'refresh'}>
          {loading === 'refresh' ? 'Refreshing...' : 'Refresh status'}
        </Button>
        <Button variant="secondary" icon={Send} onClick={handleResend} disabled={loading === 'resend' || cooldown > 0}>
          {cooldown > 0 ? `Resend in ${cooldown}s` : 'Resend email'}
        </Button>
        <Button variant="secondary" icon={LogOut} onClick={handleSignOut}>Sign out</Button>
      </div>
    </AuthShell>
  );
}
