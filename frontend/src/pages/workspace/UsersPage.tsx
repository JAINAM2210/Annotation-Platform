import { useEffect, useMemo, useState } from 'react';
import { Power, RefreshCw, RotateCcw, Users } from 'lucide-react';
import {
  deleteAdminUser,
  reactivateAdminUser,
} from '../../api/client';
import { useAuth } from '../../auth/AuthContext';
import { errorMessage, formatDate, type Message } from '../../lib/status';
import { Button, DataTable, EmptyState, MessageBanner, SectionHeader, StatusPill } from '../../ui/Primitives';
import type { UserRead, UserStatus } from '../../types';
import { useWorkspaceData } from './WorkspaceDataContext';

function statusTone(status: UserStatus) {
  if (status === 'approved') return 'approved' as const;
  if (status === 'rejected') return 'rejected' as const;
  return 'pending' as const;
}

export function UsersPage() {
  const { getAccessToken, currentUser } = useAuth();
  const { users, ensureUsers } = useWorkspaceData();
  const [loading, setLoading] = useState('');
  const [message, setMessage] = useState<Message>({ type: 'info', text: 'Users ready' });
  const sortedUsers = useMemo(() => [...users.data].sort((left, right) => right.created_at.localeCompare(left.created_at)), [users.data]);

  async function refreshUsers(force = false) {
    await ensureUsers(force);
  }

  async function run(label: string, action: () => Promise<void>) {
    setLoading(label);
    try {
      await action();
    } catch (error) {
      setMessage({ type: 'error', text: errorMessage(error) });
    } finally {
      setLoading('');
    }
  }

  useEffect(() => {
    void run('load-users', () => refreshUsers(false));
  }, [ensureUsers]);

  function handleDeactivateUser(user: UserRead) {
    if (!window.confirm(`Deactivate ${user.email}?`)) return;
    void run(`deactivate-${user.id}`, async () => {
      const token = await getAccessToken();
      await deleteAdminUser(token, user.id);
      setMessage({ type: 'success', text: `${user.email} deactivated` });
      await refreshUsers(true);
    });
  }

  function handleReactivateUser(user: UserRead) {
    if (!window.confirm(`Reactivate ${user.email}?`)) return;
    void run(`reactivate-${user.id}`, async () => {
      const token = await getAccessToken();
      await reactivateAdminUser(token, user.id);
      setMessage({ type: 'success', text: `${user.email} reactivated` });
      await refreshUsers(true);
    });
  }

  return (
    <main className="workspace-page">
      <SectionHeader
        eyebrow="Administration"
        title="Users"
        description="Manage platform profile state without changing annotation data."
        actions={<Button variant="secondary" size="compact" icon={RefreshCw} onClick={() => void run('refresh-users', () => refreshUsers(true))} disabled={Boolean(loading)}>Refresh</Button>}
      />
      <MessageBanner type={message.type} text={message.text} />
      {users.refreshing ? <MessageBanner type="info" text="Refreshing users in the background." /> : null}
      {users.error ? <MessageBanner type="error" text={users.error} /> : null}
      <section className="management-card management-card--wide">
        <div className="management-heading">
          <div><Users aria-hidden="true" size={18} /><h3>Platform users</h3></div>
          <span className="muted">{users.initialLoading ? 'Loading...' : `${users.data.length} loaded`}</span>
        </div>
        {users.initialLoading ? (
          <div className="loading-card">Loading users...</div>
        ) : sortedUsers.length === 0 ? (
          <EmptyState icon={Users} title="No users loaded" description="Platform users will appear here after profile registration." />
        ) : (
          <DataTable>
            <table>
              <thead><tr><th>Name</th><th>Email</th><th>Institute</th><th>Role</th><th>Status</th><th>Active</th><th>Created</th><th>Action</th></tr></thead>
              <tbody>
                {sortedUsers.map((user) => (
                  <tr key={user.id}>
                    <td><strong>{user.full_name}</strong>{user.designation ? <span>{user.designation}</span> : null}</td>
                    <td>{user.email}</td>
                    <td>{user.institute || '-'}</td>
                    <td><StatusPill tone="role">{user.role}</StatusPill></td>
                    <td><StatusPill tone={statusTone(user.status)}>{user.status}</StatusPill></td>
                    <td><StatusPill tone={user.is_active ? 'approved' : 'rejected'}>{user.is_active ? 'active' : 'inactive'}</StatusPill></td>
                    <td>{formatDate(user.created_at)}</td>
                    <td>
                      {user.is_active ? (
                        <Button variant="danger" size="compact" icon={Power} disabled={user.id === currentUser?.id || Boolean(loading)} onClick={() => handleDeactivateUser(user)}>Deactivate</Button>
                      ) : (
                        <Button variant="secondary" size="compact" icon={RotateCcw} disabled={Boolean(loading)} onClick={() => handleReactivateUser(user)}>Reactivate</Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </DataTable>
        )}
      </section>
    </main>
  );
}
