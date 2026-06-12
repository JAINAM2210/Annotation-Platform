import { FormEvent, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { LogOut, UserCheck } from 'lucide-react';
import { registerProfile } from '../../api/client';
import { useAuth } from '../../auth/AuthContext';
import { getCountryOptions, getStateOptions } from '../../lib/locations';
import { errorMessage, type Message } from '../../lib/status';
import { Button, Field, SelectControl } from '../../ui/Primitives';
import type { RegisterProfilePayload, SignupRole } from '../../types';
import { AuthShell } from './AuthShell';

const roleOptions = [
  { value: 'annotator', label: 'Annotator', description: 'Create relation annotations for assigned papers.' },
  { value: 'reviewer', label: 'Reviewer', description: 'Review access requests and annotation work.' },
];

export function CompleteProfilePage() {
  const navigate = useNavigate();
  const { firebaseUser, getAccessToken, syncCurrentUser, signOutUser } = useAuth();
  const [form, setForm] = useState<RegisterProfilePayload>({
    full_name: firebaseUser?.displayName ?? '',
    role: 'annotator',
    designation: '',
    institute: '',
    state: '',
    country: '',
  });
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<Message | null>(null);
  const countryOptions = useMemo(() => getCountryOptions(), []);
  const stateOptions = useMemo(() => getStateOptions(form.country), [form.country]);

  function handleCountryChange(country: string) {
    setForm((current) => ({ ...current, country, state: '' }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setMessage(null);
    try {
      const token = await getAccessToken(true);
      await registerProfile(token, {
        full_name: form.full_name.trim(),
        role: form.role,
        designation: form.designation.trim(),
        institute: form.institute.trim(),
        state: form.state.trim(),
        country: form.country.trim(),
      });
      await syncCurrentUser(true);
      navigate('/', { replace: true });
    } catch (error) {
      setMessage({ type: 'error', text: errorMessage(error) });
    } finally {
      setLoading(false);
    }
  }

  async function handleSignOut() {
    await signOutUser();
    navigate('/signin', { replace: true });
  }

  return (
    <AuthShell title="Complete profile" summary={`Signed in as ${firebaseUser?.email ?? 'your Firebase account'}.`} message={message}>
      <form className="form-grid auth-form auth-form--split" onSubmit={handleSubmit}>
        <Field label="Full name">
          <input
            autoComplete="name"
            value={form.full_name}
            onChange={(event) => setForm({ ...form, full_name: event.target.value })}
            required
          />
        </Field>
        <Field label="Role">
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
        <Button className="auth-form__full" type="submit" icon={UserCheck} disabled={loading}>{loading ? 'Registering...' : 'Register profile'}</Button>
      </form>
      <div className="button-row">
        <Button variant="secondary" icon={LogOut} onClick={handleSignOut}>Sign out</Button>
      </div>
    </AuthShell>
  );
}
