import { FormEvent, useState } from 'react';
import { Link } from 'react-router-dom';
import { Mail } from 'lucide-react';
import { sendPasswordResetEmail } from 'firebase/auth';
import { firebaseAuth } from '../../firebase';
import { errorMessage, type Message } from '../../lib/status';
import { Button, Field } from '../../ui/Primitives';
import { AuthShell } from './AuthShell';

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<Message | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setMessage(null);
    try {
      await sendPasswordResetEmail(firebaseAuth, email.trim());
      setMessage({ type: 'success', text: 'Password reset email sent.' });
    } catch (error) {
      setMessage({ type: 'error', text: errorMessage(error) });
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell title="Reset password" summary="Enter the email linked to your platform account." message={message}>
      <form className="form-grid auth-form" onSubmit={handleSubmit}>
        <Field label="Email">
          <input
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
        </Field>
        <Button type="submit" icon={Mail} disabled={loading}>{loading ? 'Sending...' : 'Send reset email'}</Button>
      </form>
      <div className="auth-links">
        <Link to="/signin">Return to sign in</Link>
      </div>
    </AuthShell>
  );
}
