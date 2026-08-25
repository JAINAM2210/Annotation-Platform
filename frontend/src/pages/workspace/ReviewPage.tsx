import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, Clock3, FileText, GitBranch, Link2, RefreshCw, SearchCheck, UserRound } from 'lucide-react';
import { errorMessage, formatDate, type Message } from '../../lib/status';
import { Button, EmptyState, MessageBanner, SectionHeader, StatusPill } from '../../ui/Primitives';
import type { ReviewSubmissionSummary, SubmissionStatus } from '../../types';
import { useWorkspaceData } from './WorkspaceDataContext';

const reviewStatuses: SubmissionStatus[] = ['submitted', 'returned', 'approved'];

function StatusTabs({ value, onChange }: { value: SubmissionStatus; onChange: (status: SubmissionStatus) => void }) {
  return (
    <div className="status-tabs" role="tablist" aria-label="Review status">
      {reviewStatuses.map((status) => (
        <button key={status} type="button" className={value === status ? 'active' : ''} onClick={() => onChange(status)}>{status}</button>
      ))}
    </div>
  );
}

function submissionTone(status: SubmissionStatus) {
  if (status === 'approved') return 'approved' as const;
  if (status === 'returned') return 'rejected' as const;
  if (status === 'review_draft') return 'pending' as const;
  return 'info' as const;
}

export function ReviewPage() {
  const navigate = useNavigate();
  const {
    reviewStatusFilter: statusFilter,
    setReviewStatusFilter: setStatusFilter,
    reviewQueues,
    ensureReviewQueue,
    setSelectedPaperId,
  } = useWorkspaceData();
  const [loading, setLoading] = useState('');
  const [message, setMessage] = useState<Message>({ type: 'info', text: 'Select a paper to continue in the Editor.' });

  const queueResource = reviewQueues[statusFilter];
  const submissions = queueResource.data;

  async function refreshQueue(force = false) {
    await ensureReviewQueue(statusFilter, force);
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
    void run('load-review-queue', () => refreshQueue(false));
  }, [ensureReviewQueue, statusFilter]);

  function openInEditor(submission: ReviewSubmissionSummary) {
    setSelectedPaperId(submission.assignment.paper_id);
    navigate('/app/editor');
  }

  return (
    <main className="workspace-page review-page">
      <SectionHeader
        eyebrow="Review"
        title="Annotation review queue"
        description="Choose a submitted paper to inspect its relations, edit the reviewer draft, return it, or approve it from the Editor."
        actions={<Button variant="secondary" size="compact" icon={RefreshCw} onClick={() => void run('refresh-review', () => refreshQueue(true))} disabled={Boolean(loading)}>Refresh</Button>}
      />
      <MessageBanner type={message.type} text={message.text} />
      {queueResource.refreshing ? <MessageBanner type="info" text="Refreshing review submissions in the background." /> : null}
      {queueResource.error ? <MessageBanner type="error" text={queueResource.error} /> : null}

      <section className="management-panel review-queue-panel">
        <div className="management-card">
          <div className="management-heading">
            <div><SearchCheck aria-hidden="true" size={18} /><h3>Papers</h3></div>
            <StatusTabs value={statusFilter} onChange={setStatusFilter} />
          </div>
          {queueResource.initialLoading ? (
            <div className="loading-card">Loading review queue...</div>
          ) : submissions.length === 0 ? (
            <EmptyState icon={SearchCheck} title={`No ${statusFilter} submissions`} description="Submitted assignments will appear here for review." />
          ) : (
            <div className="request-list review-paper-list">
              {submissions.map((submission) => {
                const rowContent = (
                  <>
                  <span className="review-row__heading">
                    <span className="review-row__paper">
                      <span className="review-row__paper-icon"><FileText aria-hidden="true" size={18} /></span>
                      <span>
                        <strong>{submission.assignment.paper_title || submission.assignment.paper_id}</strong>
                        <small>{submission.assignment.paper_id}</small>
                      </span>
                    </span>
                    <StatusPill tone={submissionTone(submission.status)}>{submission.status.replace(/_/g, ' ')}</StatusPill>
                  </span>
                  <span className="review-row__metadata">
                    <span className="review-row__metadata-item">
                      <Link2 aria-hidden="true" size={16} />
                      <span><small>DOI</small><strong>{submission.assignment.doi || 'Not available'}</strong></span>
                    </span>
                    <span className="review-row__metadata-item">
                      <UserRound aria-hidden="true" size={16} />
                      <span><small>Annotator</small><strong>{submission.assignment.annotator_name || submission.assignment.annotator_email || 'Not available'}</strong></span>
                    </span>
                    <span className="review-row__metadata-item">
                      <GitBranch aria-hidden="true" size={16} />
                      <span><small>Version</small><strong>Version {submission.version}</strong></span>
                    </span>
                    <span className="review-row__metadata-item">
                      <Clock3 aria-hidden="true" size={16} />
                      <span><small>Submitted</small><strong>{formatDate(submission.submitted_at)}</strong></span>
                    </span>
                  </span>
                  {submission.status === 'submitted' ? (
                    <span className="review-row__open">Open in Editor <ArrowRight aria-hidden="true" size={15} /></span>
                  ) : null}
                  </>
                );
                return submission.status === 'submitted' ? (
                  <button
                    key={submission.submission_id}
                    type="button"
                    className="review-row review-row--queue"
                    onClick={() => openInEditor(submission)}
                  >
                    {rowContent}
                  </button>
                ) : (
                  <article key={submission.submission_id} className="review-row review-row--queue review-row--static">
                    {rowContent}
                  </article>
                );
              })}
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
