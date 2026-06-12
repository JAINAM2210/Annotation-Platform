import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Clock3, LogOut, RefreshCw } from 'lucide-react';
import { useAuth } from '../../auth/AuthContext';
import { errorMessage, type Message } from '../../lib/status';
import { Button, StatusPill } from '../../ui/Primitives';
import { AuthShell } from './AuthShell';

function statusMessage(status: string | undefined, isActive: boolean | undefined, rejectionReason: string | null | undefined) {
  if (!isActive) return 'This account is inactive. Contact an administrator if you need access restored.';
  if (status === 'pending') return 'Your request is waiting for approval. You will be able to open the editor after approval.';
  if (status === 'rejected') return rejectionReason || 'Your request was rejected.';
  return 'Your account is not ready yet.';
}

function statusTone(status: string | undefined, isActive: boolean | undefined) {
  if (!isActive) return 'rejected' as const;
  if (status === 'approved') return 'approved' as const;
  if (status === 'rejected') return 'rejected' as const;
  return 'pending' as const;
}

export function AccountStatusPage() {
  const navigate = useNavigate();
  const { currentUser, syncCurrentUser, signOutUser } = useAuth();
  const [loading, setLoading] = useState('');
  const [message, setMessage] = useState<Message | null>(null);

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
    <AuthShell title="Account status" summary={currentUser?.email ?? 'Your platform profile'} message={message}>
      <div className="status-card">
        {currentUser ? <StatusPill tone={statusTone(currentUser.status, currentUser.is_active)} icon={Clock3}>{currentUser.is_active ? currentUser.status : 'inactive'}</StatusPill> : null}
        <p>{statusMessage(currentUser?.status, currentUser?.is_active, currentUser?.rejection_reason)}</p>
      </div>
      <div className="button-row">
        <Button variant="success" icon={RefreshCw} onClick={handleRefresh} disabled={loading === 'refresh'}>
          {loading === 'refresh' ? 'Refreshing...' : 'Refresh status'}
        </Button>
        <Button variant="secondary" icon={LogOut} onClick={handleSignOut}>Sign out</Button>
      </div>
    </AuthShell>
  );
}
