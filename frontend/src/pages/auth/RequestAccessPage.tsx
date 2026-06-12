import { FormEvent, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, ArrowRight, UserPlus } from 'lucide-react';
import { createUserWithEmailAndPassword, sendEmailVerification } from 'firebase/auth';
import { registerProfile } from '../../api/client';
import { useAuth } from '../../auth/AuthContext';
import { ensureFirebaseSessionPersistence, firebaseAuth } from '../../firebase';
import { getCountryOptions, getStateOptions } from '../../lib/locations';
import { errorMessage, type Message } from '../../lib/status';
import { Button, Field, SelectControl } from '../../ui/Primitives';
import type { RegisterProfilePayload, SignupRole } from '../../types';
import { AuthShell } from './AuthShell';

const roleOptions = [
  { value: 'annotator', label: 'Annotator', description: 'Create relation annotations for assigned papers.' },
  { value: 'reviewer', label: 'Reviewer', description: 'Review access requests and annotation work.' },
];

type SignupForm = RegisterProfilePayload & {
  email: string;
  password: string;
  confirmPassword: string;
};

type SignupStep = 'account' | 'profile';

export function RequestAccessPage() {
  const navigate = useNavigate();
  const { syncCurrentUser } = useAuth();
  const [form, setForm] = useState<SignupForm>({
    full_name: '',
    email: '',
    password: '',
    confirmPassword: '',
    role: 'annotator',
    designation: '',
    institute: '',
    state: '',
    country: '',
  });
  const [step, setStep] = useState<SignupStep>('account');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<Message | null>(null);
  const countryOptions = useMemo(() => getCountryOptions(), []);
  const stateOptions = useMemo(() => getStateOptions(form.country), [form.country]);

  function handleCountryChange(country: string) {
    setForm((current) => ({ ...current, country, state: '' }));
  }

  function validateAccountStep() {
    const email = form.email.trim();
    if (!email) {
      setMessage({ type: 'error', text: 'Enter your email address.' });
      return false;
    }
    if (form.password.length < 8) {
      setMessage({ type: 'error', text: 'Use a password with at least 8 characters.' });
      return false;
    }
    if (form.password !== form.confirmPassword) {
      setMessage({ type: 'error', text: 'Password and confirm password do not match.' });
      return false;
    }
    setMessage(null);
    return true;
  }

  function continueToProfile() {
    if (!validateAccountStep()) return;
    setStep('profile');
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (step === 'account') {
      continueToProfile();
      return;
    }
    if (!validateAccountStep()) {
      setStep('account');
      return;
    }
    if (!form.full_name.trim()) {
      setMessage({ type: 'error', text: 'Enter your full name.' });
      return;
    }

    setLoading(true);
    setMessage(null);
    try {
      await ensureFirebaseSessionPersistence();
      const credential = await createUserWithEmailAndPassword(firebaseAuth, form.email.trim(), form.password);
      await sendEmailVerification(credential.user);
      const token = await credential.user.getIdToken();
      await registerProfile(token, {
        full_name: form.full_name.trim(),
        role: form.role,
        designation: form.designation.trim(),
        institute: form.institute.trim(),
        state: form.state.trim(),
        country: form.country.trim(),
      });
      await syncCurrentUser(true);
      navigate('/verify-email', { replace: true });
    } catch (error) {
      setMessage({ type: 'error', text: errorMessage(error) });
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell title="Request access" summary="Create your sign-in account first, then tell reviewers who you are." message={message}>
      <div className="auth-stepper" aria-label="Request access progress">
        <div className={`auth-step ${step === 'account' ? 'auth-step--active' : 'auth-step--done'}`}>
          <span className="auth-step__index">1</span>
          <div><strong>Account</strong><span>Email and password</span></div>
        </div>
        <div className={`auth-step ${step === 'profile' ? 'auth-step--active' : ''}`}>
          <span className="auth-step__index">2</span>
          <div><strong>Profile</strong><span>Role and institute</span></div>
        </div>
      </div>

      <form className={`form-grid auth-form ${step === 'account' ? 'auth-form--single' : 'auth-form--split'}`} onSubmit={handleSubmit}>
        {step === 'account' ? (
          <>
            <Field label="Email">
              <input
                type="email"
                autoComplete="email"
                value={form.email}
                onChange={(event) => setForm({ ...form, email: event.target.value })}
                required
              />
            </Field>
            <Field label="Password" hint="Use at least 8 characters.">
              <input
                type="password"
                autoComplete="new-password"
                minLength={8}
                value={form.password}
                onChange={(event) => setForm({ ...form, password: event.target.value })}
                required
              />
            </Field>
            <Field label="Confirm password">
              <input
                type="password"
                autoComplete="new-password"
                minLength={8}
                value={form.confirmPassword}
                onChange={(event) => setForm({ ...form, confirmPassword: event.target.value })}
                required
              />
            </Field>
            <div className="auth-form__full auth-form__actions auth-form__actions--end">
              <Button type="submit" icon={ArrowRight}>Continue</Button>
            </div>
          </>
        ) : (
          <>
            <div className="auth-form__full auth-account-summary">
              <span>Signing up with</span>
              <strong>{form.email.trim()}</strong>
              <button type="button" onClick={() => setStep('account')}>Edit account</button>
            </div>
            <Field label="Full name">
              <input
                autoComplete="name"
                value={form.full_name}
                onChange={(event) => setForm({ ...form, full_name: event.target.value })}
                required
              />
            </Field>
            <Field label="Requested role">
              <SelectControl
                value={form.role}
                options={roleOptions}
                onChange={(value) => setForm({ ...form, role: value as SignupRole })}
                ariaLabel="Choose requested platform role"
              />
            </Field>
            <Field label="Designation">
              <input
                autoComplete="organization-title"
                value={form.designation}
                onChange={(event) => setForm({ ...form, designation: event.target.value })}
              />
            </Field>
            <Field label="Institute">
              <input
                autoComplete="organization"
                value={form.institute}
                onChange={(event) => setForm({ ...form, institute: event.target.value })}
              />
            </Field>
            <Field label="Country">
              <SelectControl
                value={form.country}
                options={countryOptions}
                onChange={handleCountryChange}
                ariaLabel="Choose country"
                placeholder="Select country"
                searchable
                searchPlaceholder="Search countries..."
              />
            </Field>
            <Field label="State / region">
              <SelectControl
                value={form.state}
                options={stateOptions}
                onChange={(state) => setForm({ ...form, state })}
                ariaLabel="Choose state or region"
                placeholder={!form.country ? 'Select country first' : stateOptions.length === 0 ? 'No states/regions available' : 'Select state/region'}
                disabled={!form.country || stateOptions.length === 0}
                searchable
                searchPlaceholder="Search states/regions..."
              />
            </Field>
            <div className="auth-form__full auth-form__actions">
              <Button type="button" variant="secondary" icon={ArrowLeft} onClick={() => setStep('account')} disabled={loading}>Back</Button>
              <Button type="submit" icon={UserPlus} disabled={loading}>{loading ? 'Creating request...' : 'Create request'}</Button>
            </div>
          </>
        )}
      </form>
      <div className="auth-links">
        <Link to="/signin">Already have access?</Link>
      </div>
    </AuthShell>
  );
}
