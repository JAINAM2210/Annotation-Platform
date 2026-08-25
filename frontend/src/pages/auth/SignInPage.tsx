import { FormEvent, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { LogIn } from 'lucide-react';
import { signInWithEmailAndPassword } from 'firebase/auth';
import { useAuth } from '../../auth/AuthContext';
import { ensureFirebaseSessionPersistence, firebaseAuth } from '../../firebase';
import { errorMessage, type Message } from '../../lib/status';
import { Button, Field } from '../../ui/Primitives';
import { PasswordInput } from '../../ui/PasswordInput';
import { AuthShell } from './AuthShell';

export function SignInPage() {
  const navigate = useNavigate();
  const { syncCurrentUser } = useAuth();
  const [form, setForm] = useState({ email: '', password: '' });
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<Message | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setMessage(null);
    try {
      await ensureFirebaseSessionPersistence();
      await signInWithEmailAndPassword(firebaseAuth, form.email.trim(), form.password);
      const profile = await syncCurrentUser(true);
      navigate(profile?.role === 'reviewer' ? '/app/review' : '/', { replace: true });
    } catch (error) {
      setMessage({ type: 'error', text: errorMessage(error) });
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell title="Sign in" summary="Use your approved platform account." message={message}>
      <form className="form-grid auth-form" onSubmit={handleSubmit}>
        <Field label="Email">
          <input
            type="email"
            autoComplete="email"
            value={form.email}
            onChange={(event) => setForm({ ...form, email: event.target.value })}
            required
          />
        </Field>
        <Field label="Password">
          <PasswordInput
            autoComplete="current-password"
            value={form.password}
            onChange={(event) => setForm({ ...form, password: event.target.value })}
            required
          />
        </Field>
        <Button type="submit" icon={LogIn} disabled={loading}>{loading ? 'Signing in...' : 'Sign in'}</Button>
      </form>
      <div className="auth-links">
        <Link to="/forgot-password">Forgot password?</Link>
        <Link to="/request-access">Request access</Link>
      </div>
    </AuthShell>
  );
}
