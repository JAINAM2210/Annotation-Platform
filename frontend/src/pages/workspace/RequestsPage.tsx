import { useEffect, useState } from 'react';
import { Check, Inbox, RefreshCw, ShieldCheck, X } from 'lucide-react';
import {
  approveAnnotatorSignupRequest,
  approveReviewerSignupRequest,
  rejectAnnotatorSignupRequest,
  rejectReviewerSignupRequest,
} from '../../api/client';
import { useAuth } from '../../auth/AuthContext';
import { errorMessage, formatDate, type Message } from '../../lib/status';
import { Button, EmptyState, Field, MessageBanner, SectionHeader, StatusPill } from '../../ui/Primitives';
import type { UserRead, UserStatus } from '../../types';
import { useWorkspaceData } from './WorkspaceDataContext';

function statusTone(status: UserStatus) {
  if (status === 'approved') return 'approved' as const;
  if (status === 'rejected') return 'rejected' as const;
  return 'pending' as const;
}

function StatusTabs({ value, onChange }: { value: UserStatus; onChange: (status: UserStatus) => void }) {
  const statuses: UserStatus[] = ['pending', 'approved', 'rejected'];
  return (
    <div className="status-tabs" role="tablist" aria-label="Request status">
      {statuses.map((status) => (
        <button
          key={status}
          type="button"
          className={value === status ? 'active' : ''}
          onClick={() => onChange(status)}
        >
          {status}
        </button>
      ))}
    </div>
  );
}

function RequestList({
  items,
  emptyText,
  loading,
  initialLoading,
  rejectReasons,
  onReasonChange,
  onApprove,
  onReject,
}: {
  items: UserRead[];
  emptyText: string;
  loading: string;
  initialLoading: boolean;
  rejectReasons: Record<string, string>;
  onReasonChange: (userId: string, reason: string) => void;
  onApprove: (userId: string) => void;
  onReject: (userId: string) => void;
}) {
  if (initialLoading) return <div className="loading-card">Loading requests...</div>;
  if (items.length === 0) return <EmptyState icon={Inbox} title={emptyText} description="New verified users will appear here when they request access." />;

  return (
    <div className="request-list">
      {items.map((request) => (
        <article className="request-row" key={request.id}>
          <div className="request-main">
            <div>
              <strong>{request.full_name}</strong>
              <span>{request.email}</span>
            </div>
            <div className="request-meta">
              <span>Created {formatDate(request.created_at)}</span>
              {request.designation || request.institute ? <span>{[request.designation, request.institute].filter(Boolean).join(' · ')}</span> : null}
              {request.state || request.country ? <span>{[request.state, request.country].filter(Boolean).join(', ')}</span> : null}
            </div>
          </div>
          <div className="request-badges">
            <StatusPill tone="role">{request.role}</StatusPill>
            <StatusPill tone={statusTone(request.status)}>{request.status}</StatusPill>
            <StatusPill tone={request.email_verified ? 'approved' : 'pending'}>{request.email_verified ? 'verified' : 'unverified'}</StatusPill>
          </div>
          {request.status === 'pending' ? (
            <div className="request-actions">
              <Field label="Reject reason">
                <input
                  value={rejectReasons[request.id] ?? ''}
                  onChange={(event) => onReasonChange(request.id, event.target.value)}
                  placeholder="Optional note"
                />
              </Field>
              <Button variant="success" icon={Check} onClick={() => onApprove(request.id)} disabled={Boolean(loading)}>Approve</Button>
              <Button variant="danger" icon={X} onClick={() => onReject(request.id)} disabled={Boolean(loading)}>Reject</Button>
            </div>
          ) : null}
        </article>
      ))}
    </div>
  );
}

export function RequestsPage() {
  const { getAccessToken, mayManageAnnotators, mayManageReviewers } = useAuth();
  const {
    requestStatus,
    setRequestStatus,
    annotatorRequests,
    reviewerRequests,
    ensureAnnotatorRequests,
    ensureReviewerRequests,
    ensureUsers,
    ensureAssignmentOptions,
  } = useWorkspaceData();
  const [rejectReasons, setRejectReasons] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState('');
  const [message, setMessage] = useState<Message>({ type: 'info', text: 'Requests ready' });

  const annotatorResource = annotatorRequests[requestStatus.annotator];
  const reviewerResource = reviewerRequests[requestStatus.reviewer];

  async function refreshRequests(force = false) {
    const tasks: Promise<unknown>[] = [];
    if (mayManageAnnotators) tasks.push(ensureAnnotatorRequests(requestStatus.annotator, force));
    if (mayManageReviewers) tasks.push(ensureReviewerRequests(requestStatus.reviewer, force));
    await Promise.all(tasks);
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
    void run('load-requests', () => refreshRequests(false));
  }, [annotatorRequests, ensureAnnotatorRequests, ensureReviewerRequests, mayManageAnnotators, mayManageReviewers, requestStatus.annotator, requestStatus.reviewer, reviewerRequests]);

  function handleApproveAnnotator(userId: string) {
    void run(`approve-annotator-${userId}`, async () => {
      const token = await getAccessToken();
      const user = await approveAnnotatorSignupRequest(token, userId);
      setMessage({ type: 'success', text: `${user.email} approved as annotator` });
      await Promise.all([ensureAnnotatorRequests(requestStatus.annotator, true), ensureUsers(true).catch(() => []), ensureAssignmentOptions(true).catch(() => undefined)]);
    });
  }

  function handleRejectAnnotator(userId: string) {
    void run(`reject-annotator-${userId}`, async () => {
      const token = await getAccessToken();
      const user = await rejectAnnotatorSignupRequest(token, userId, rejectReasons[userId] ?? '');
      setMessage({ type: 'success', text: `${user.email} rejected` });
      await Promise.all([ensureAnnotatorRequests(requestStatus.annotator, true), ensureUsers(true).catch(() => []), ensureAssignmentOptions(true).catch(() => undefined)]);
    });
  }

  function handleApproveReviewer(userId: string) {
    void run(`approve-reviewer-${userId}`, async () => {
      const token = await getAccessToken();
      const user = await approveReviewerSignupRequest(token, userId);
      setMessage({ type: 'success', text: `${user.email} approved as reviewer` });
      await Promise.all([ensureReviewerRequests(requestStatus.reviewer, true), ensureUsers(true).catch(() => [])]);
    });
  }

  function handleRejectReviewer(userId: string) {
    void run(`reject-reviewer-${userId}`, async () => {
      const token = await getAccessToken();
      const user = await rejectReviewerSignupRequest(token, userId, rejectReasons[userId] ?? '');
      setMessage({ type: 'success', text: `${user.email} rejected` });
      await Promise.all([ensureReviewerRequests(requestStatus.reviewer, true), ensureUsers(true).catch(() => [])]);
    });
  }

  return (
    <main className="workspace-page">
      <SectionHeader
        eyebrow="Access control"
        title="Approval requests"
        description="Review verified users before they enter the annotation workspace."
        actions={<Button variant="secondary" size="compact" icon={RefreshCw} onClick={() => void run('refresh-requests', () => refreshRequests(true))} disabled={Boolean(loading)}>Refresh</Button>}
      />
      <MessageBanner type={message.type} text={message.text} />
      {annotatorResource.refreshing || reviewerResource.refreshing ? <MessageBanner type="info" text="Refreshing request queues in the background." /> : null}
      {annotatorResource.error || reviewerResource.error ? <MessageBanner type="error" text={annotatorResource.error || reviewerResource.error} /> : null}
      <section className="management-panel">
        {mayManageAnnotators ? (
          <div className="management-card">
            <div className="management-heading">
              <div><ShieldCheck aria-hidden="true" size={18} /><h3>Annotator requests</h3></div>
              <StatusTabs value={requestStatus.annotator} onChange={(status) => setRequestStatus('annotator', status)} />
            </div>
            <RequestList
              items={annotatorResource.data}
              emptyText={`No ${requestStatus.annotator} annotator requests`}
              loading={loading}
              initialLoading={annotatorResource.initialLoading}
              rejectReasons={rejectReasons}
              onReasonChange={(userId, reason) => setRejectReasons((current) => ({ ...current, [userId]: reason }))}
              onApprove={handleApproveAnnotator}
              onReject={handleRejectAnnotator}
            />
          </div>
        ) : null}
        {mayManageReviewers ? (
          <div className="management-card">
            <div className="management-heading">
              <div><ShieldCheck aria-hidden="true" size={18} /><h3>Reviewer requests</h3></div>
              <StatusTabs value={requestStatus.reviewer} onChange={(status) => setRequestStatus('reviewer', status)} />
            </div>
            <RequestList
              items={reviewerResource.data}
              emptyText={`No ${requestStatus.reviewer} reviewer requests`}
              loading={loading}
              initialLoading={reviewerResource.initialLoading}
              rejectReasons={rejectReasons}
              onReasonChange={(userId, reason) => setRejectReasons((current) => ({ ...current, [userId]: reason }))}
              onApprove={handleApproveReviewer}
              onReject={handleRejectReviewer}
            />
          </div>
        ) : null}
      </section>
    </main>
  );
}
