import { useEffect, useMemo, useState } from 'react';
import { CheckCircle2, MessageSquareReply, RefreshCw, SearchCheck } from 'lucide-react';
import {
  approveReviewSubmission,
  returnReviewSubmission,
} from '../../api/client';
import { useAuth } from '../../auth/AuthContext';
import { errorMessage, formatDate, type Message } from '../../lib/status';
import { Button, DataTable, EmptyState, Field, MessageBanner, SectionHeader, StatusPill } from '../../ui/Primitives';
import type { SubmissionStatus } from '../../types';
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

export function ReviewPage() {
  const { getAccessToken } = useAuth();
  const {
    reviewStatusFilter: statusFilter,
    setReviewStatusFilter: setStatusFilter,
    reviewQueues,
    reviewDetails,
    selectedSubmissionByStatus,
    setSelectedSubmissionForStatus,
    ensureReviewQueue,
    ensureReviewDetail,
    refreshEditorAfterWorkflowChange,
  } = useWorkspaceData();
  const [comment, setComment] = useState('');
  const [loading, setLoading] = useState('');
  const [message, setMessage] = useState<Message>({ type: 'info', text: 'Review queue ready' });

  const queueResource = reviewQueues[statusFilter];
  const submissions = queueResource.data;
  const selectedSubmissionId = selectedSubmissionByStatus[statusFilter] ?? '';
  const selectedSummary = useMemo(
    () => submissions.find((submission) => submission.submission_id === selectedSubmissionId) ?? submissions[0],
    [selectedSubmissionId, submissions]
  );
  const detailResource = selectedSummary?.submission_id ? reviewDetails[selectedSummary.submission_id] : undefined;
  const detail = detailResource?.data ?? null;

  async function refreshQueue(force = false) {
    await ensureReviewQueue(statusFilter, force);
  }

  async function loadDetail(submissionId: string, force = false) {
    if (!submissionId) return;
    await ensureReviewDetail(submissionId, force);
    setComment('');
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

  useEffect(() => {
    if (selectedSummary?.submission_id) {
      void run('load-review-detail', () => loadDetail(selectedSummary.submission_id, false));
    }
  }, [ensureReviewDetail, selectedSummary?.submission_id]);

  function handleReturn() {
    if (!detail) return;
    void run('return-submission', async () => {
      const token = await getAccessToken();
      await returnReviewSubmission(token, detail.submission.submission_id, comment);
      setMessage({ type: 'success', text: `${detail.submission.assignment.paper_id} returned to annotator` });
      await Promise.all([
        ensureReviewQueue(statusFilter, true),
        ensureReviewQueue('returned', true),
        refreshEditorAfterWorkflowChange(detail.submission.assignment.paper_id),
      ]);
    });
  }

  function handleApprove() {
    if (!detail) return;
    void run('approve-submission', async () => {
      const token = await getAccessToken();
      await approveReviewSubmission(token, detail.submission.submission_id, comment);
      setMessage({ type: 'success', text: `${detail.submission.assignment.paper_id} approved as final annotation` });
      await Promise.all([
        ensureReviewQueue(statusFilter, true),
        ensureReviewQueue('approved', true),
        refreshEditorAfterWorkflowChange(detail.submission.assignment.paper_id),
      ]);
    });
  }

  return (
    <main className="workspace-page review-page">
      <SectionHeader
        eyebrow="Review"
        title="Annotation review"
        description="Inspect submitted relation sets and either approve final annotations or return work with comments."
        actions={<Button variant="secondary" size="compact" icon={RefreshCw} onClick={() => void run('refresh-review', () => refreshQueue(true))} disabled={Boolean(loading)}>Refresh</Button>}
      />
      <MessageBanner type={message.type} text={message.text} />
      {queueResource.refreshing || detailResource?.refreshing ? <MessageBanner type="info" text="Refreshing review data in the background." /> : null}
      {queueResource.error || detailResource?.error ? <MessageBanner type="error" text={queueResource.error || detailResource?.error || ''} /> : null}

      <section className="management-panel review-panel">
        <div className="management-card">
          <div className="management-heading">
            <div><SearchCheck aria-hidden="true" size={18} /><h3>Queue</h3></div>
            <StatusTabs value={statusFilter} onChange={setStatusFilter} />
          </div>
          {queueResource.initialLoading ? (
            <div className="loading-card">Loading review queue...</div>
          ) : submissions.length === 0 ? (
            <EmptyState icon={SearchCheck} title={`No ${statusFilter} submissions`} description="Submitted assignments will appear here for review." />
          ) : (
            <div className="request-list">
              {submissions.map((submission) => (
                <button
                  key={submission.submission_id}
                  type="button"
                  className={`review-row ${submission.submission_id === selectedSummary?.submission_id ? 'review-row--active' : ''}`}
                  onClick={() => setSelectedSubmissionForStatus(statusFilter, submission.submission_id)}
                >
                  <strong>{submission.assignment.paper_id}</strong>
                  <span>{submission.assignment.paper_title}</span>
                  <small>{submission.assignment.annotator_name} · v{submission.version} · {formatDate(submission.submitted_at)}</small>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="management-card review-detail-card">
          <div className="management-heading">
            <div><MessageSquareReply aria-hidden="true" size={18} /><h3>Submission detail</h3></div>
            {detail ? <StatusPill tone={detail.submission.status === 'approved' ? 'approved' : detail.submission.status === 'returned' ? 'rejected' : 'info'}>{detail.submission.status}</StatusPill> : null}
          </div>
          {detailResource?.initialLoading ? (
            <div className="loading-card">Loading submission...</div>
          ) : !detail ? (
            <EmptyState icon={MessageSquareReply} title="Select a submission" description="Choose a queue item to inspect its relation set." />
          ) : (
            <div className="review-detail">
              <div className="review-summary-grid">
                <div><span>Paper</span><strong>{detail.submission.assignment.paper_id}</strong></div>
                <div><span>Annotator</span><strong>{detail.submission.assignment.annotator_name}</strong></div>
                <div><span>Version</span><strong>v{detail.submission.version}</strong></div>
                <div><span>Submitted</span><strong>{formatDate(detail.submission.submitted_at)}</strong></div>
              </div>
              {detail.decisions.length > 0 ? (
                <div className="review-comments">
                  {detail.decisions.map((decision, index) => (
                    <MessageBanner key={`${decision.created_at}-${index}`} type="info" text={`${decision.decision}: ${decision.comment || 'No comment'} (${formatDate(decision.created_at)})`} />
                  ))}
                </div>
              ) : null}
              {detail.paper.paragraph_comments.length > 0 ? (
                <section className="review-paragraph-comments">
                  <h4>Annotator paragraph comments</h4>
                  <div className="review-paragraph-comments__list">
                    {detail.paper.paragraph_comments.map((paragraphComment) => {
                      const paragraph = detail.paper.paragraphs.find((item) => item.paragraph_id === paragraphComment.paragraph_id);
                      return (
                        <div key={paragraphComment.paragraph_id} className="review-paragraph-comment">
                          <span>Paragraph {paragraph?.paragraph_index ?? paragraphComment.paragraph_id}</span>
                          <p>{paragraphComment.comment_text}</p>
                        </div>
                      );
                    })}
                  </div>
                </section>
              ) : null}
              <DataTable>
                <table>
                  <thead><tr><th>Subject</th><th>Predicate</th><th>Object</th><th>Evidence</th></tr></thead>
                  <tbody>
                    {detail.paper.relations.map((relation) => (
                      <tr key={relation.relation_id}>
                        <td><strong>{relation.subject_text}</strong><span>{relation.subject_type}</span></td>
                        <td>{relation.predicate}</td>
                        <td><strong>{relation.object_text}</strong><span>{relation.object_type}</span></td>
                        <td>{relation.evidence_text || relation.support_sentence_ids || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </DataTable>
              {['submitted', 'review_draft'].includes(detail.submission.status) ? (
                <div className="review-actions">
                  <Field label="Reviewer comment">
                    <textarea value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Add approval note or return reason" rows={3} />
                  </Field>
                  <div className="button-row">
                    <Button variant="danger" icon={MessageSquareReply} onClick={handleReturn} disabled={Boolean(loading)}>Return</Button>
                    <Button variant="success" icon={CheckCircle2} onClick={handleApprove} disabled={Boolean(loading)}>Approve final</Button>
                  </div>
                </div>
              ) : null}
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
