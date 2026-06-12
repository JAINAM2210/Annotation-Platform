import { useEffect, useMemo, useState } from 'react';
import { CalendarDays, ClipboardList, RefreshCw, XCircle } from 'lucide-react';
import {
  cancelAssignment,
  createAssignment,
} from '../../api/client';
import { useAuth } from '../../auth/AuthContext';
import { errorMessage, formatDate, type Message } from '../../lib/status';
import { Button, DataTable, EmptyState, Field, MessageBanner, SectionHeader, SelectControl, StatusPill } from '../../ui/Primitives';
import type { AssignmentRead, AssignmentStatus } from '../../types';
import { useWorkspaceData } from './WorkspaceDataContext';

const activeAssignmentStatuses: AssignmentStatus[] = ['assigned', 'in_progress', 'submitted', 'returned'];

function assignmentTone(status: AssignmentStatus) {
  if (status === 'approved') return 'approved' as const;
  if (status === 'cancelled' || status === 'returned') return 'rejected' as const;
  if (status === 'submitted') return 'info' as const;
  return 'pending' as const;
}

export function AssignmentsPage() {
  const { currentUser, getAccessToken, mayManageAnnotators, mayManageReviewers } = useAuth();
  const {
    assignments,
    assignmentOptions,
    assignmentForm: form,
    setAssignmentForm,
    selectedAssignmentHistoryPaperId,
    setSelectedAssignmentHistoryPaperId,
    assignmentHistories,
    ensureAssignmentHistory,
    ensureAssignments,
    ensureAssignmentOptions,
    refreshEditorAfterWorkflowChange,
  } = useWorkspaceData();
  const canAssign = Boolean(mayManageAnnotators || mayManageReviewers || currentUser?.role === 'admin' || currentUser?.role === 'reviewer');
  const [loading, setLoading] = useState('');
  const [message, setMessage] = useState<Message>({ type: 'info', text: 'Assignments ready' });

  const paperOptions = useMemo(() => [...assignmentOptions.data.papers]
    .sort((left, right) => (left.title || left.paper_id).localeCompare(right.title || right.paper_id, undefined, { sensitivity: 'base' }))
    .map((paper) => ({
      value: paper.paper_id,
      label: paper.title || paper.paper_id,
      description: paper.doi ? `DOI: ${paper.doi}` : 'DOI not available',
      meta: paper.assignment ? paper.assignment.status : paper.paper_id,
      previewTitle: paper.title || paper.paper_id,
      previewDescription: paper.assignment ? `${paper.paper_id} · ${paper.assignment.status}` : paper.paper_id,
      disabled: Boolean(paper.assignment && activeAssignmentStatuses.includes(paper.assignment.status)),
    })), [assignmentOptions.data.papers]);

  const historyPaperOptions = useMemo(() => [...assignmentOptions.data.papers]
    .sort((left, right) => (left.title || left.paper_id).localeCompare(right.title || right.paper_id, undefined, { sensitivity: 'base' }))
    .map((paper) => ({
      value: paper.paper_id,
      label: paper.title || paper.paper_id,
      description: paper.doi ? `DOI: ${paper.doi}` : 'DOI not available',
      meta: paper.assignment ? paper.assignment.status : paper.paper_id,
      previewTitle: paper.title || paper.paper_id,
      previewDescription: paper.assignment ? `${paper.paper_id} · ${paper.assignment.status}` : paper.paper_id,
    })), [assignmentOptions.data.papers]);

  const annotatorOptions = useMemo(() => assignmentOptions.data.annotators.map((annotator) => ({
    value: annotator.id,
    label: annotator.full_name,
    description: [annotator.email, annotator.institute].filter(Boolean).join(' · '),
  })), [assignmentOptions.data.annotators]);

  const selectedHistoryResource = selectedAssignmentHistoryPaperId ? assignmentHistories[selectedAssignmentHistoryPaperId] : undefined;
  const selectedHistory = selectedHistoryResource?.data ?? null;
  const historyAssignments = selectedHistory?.assignments ?? [];
  const activeHistoryAssignment = historyAssignments.find((assignment) => activeAssignmentStatuses.includes(assignment.status)) ?? null;

  async function refreshAssignments(force = false) {
    await ensureAssignments(force);
    if (canAssign) await ensureAssignmentOptions(force);
    if (canAssign && selectedAssignmentHistoryPaperId) await ensureAssignmentHistory(selectedAssignmentHistoryPaperId, force);
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
    void run('load-assignments', async () => {
      await ensureAssignments(false);
      if (canAssign) await ensureAssignmentOptions(false);
    });
  }, [canAssign, ensureAssignmentOptions, ensureAssignments]);

  useEffect(() => {
    if (!canAssign || assignmentOptions.data.papers.length === 0) return;
    if (selectedAssignmentHistoryPaperId && assignmentOptions.data.papers.some((paper) => paper.paper_id === selectedAssignmentHistoryPaperId)) return;
    const preferredPaperId = form.paper_id && assignmentOptions.data.papers.some((paper) => paper.paper_id === form.paper_id)
      ? form.paper_id
      : assignmentOptions.data.papers[0]?.paper_id ?? '';
    if (preferredPaperId) setSelectedAssignmentHistoryPaperId(preferredPaperId);
  }, [assignmentOptions.data.papers, canAssign, form.paper_id, selectedAssignmentHistoryPaperId, setSelectedAssignmentHistoryPaperId]);

  useEffect(() => {
    if (!canAssign || !selectedAssignmentHistoryPaperId) return;
    void ensureAssignmentHistory(selectedAssignmentHistoryPaperId, false).catch((error) => {
      setMessage({ type: 'error', text: errorMessage(error) });
    });
  }, [canAssign, ensureAssignmentHistory, selectedAssignmentHistoryPaperId]);

  function handleCreateAssignment() {
    void run('create-assignment', async () => {
      const token = await getAccessToken();
      const assignment = await createAssignment(token, {
        paper_id: form.paper_id,
        annotator_id: form.annotator_id,
        due_at: form.due_at ? new Date(form.due_at).toISOString() : null,
      });
      setMessage({ type: 'success', text: `${assignment.paper_id} assigned to ${assignment.annotator_name}` });
      setAssignmentForm((current) => ({ ...current, paper_id: '' }));
      await refreshEditorAfterWorkflowChange(assignment.paper_id);
    });
  }

  function handleCancelAssignment(assignment: AssignmentRead) {
    if (!window.confirm(`Cancel assignment for ${assignment.paper_id}?`)) return;
    void run(`cancel-${assignment.id}`, async () => {
      const token = await getAccessToken();
      await cancelAssignment(token, assignment.id);
      setMessage({ type: 'success', text: `${assignment.paper_id} assignment cancelled` });
      await refreshEditorAfterWorkflowChange(assignment.paper_id);
    });
  }

  const isRefreshing = assignments.refreshing || assignmentOptions.refreshing || Boolean(selectedHistoryResource?.refreshing);
  const loadError = assignments.error || assignmentOptions.error;

  return (
    <main className="workspace-page">
      <SectionHeader
        eyebrow="Workflow"
        title="Assignments"
        description={canAssign ? 'Assign papers to approved annotators and track progress.' : 'Track papers assigned to you for annotation.'}
        actions={<Button variant="secondary" size="compact" icon={RefreshCw} onClick={() => void run('refresh-assignments', () => refreshAssignments(true))} disabled={Boolean(loading)}>Refresh</Button>}
      />
      <MessageBanner type={message.type} text={message.text} />
      {isRefreshing ? <MessageBanner type="info" text="Refreshing assignments in the background." /> : null}
      {loadError ? <MessageBanner type="error" text={loadError} /> : null}

      {canAssign ? (
        <section className="management-card management-card--wide assignment-create-card">
          <div className="management-heading">
            <div><ClipboardList aria-hidden="true" size={18} /><h3>Create assignment</h3></div>
            <span className="muted">One active annotator per paper</span>
          </div>
          <div className="assignment-form">
            <Field label="Paper">
              <SelectControl
                value={form.paper_id}
                options={paperOptions}
                onChange={(paper_id) => setAssignmentForm((current) => ({ ...current, paper_id }))}
                ariaLabel="Choose paper to assign"
                placeholder={assignmentOptions.initialLoading ? 'Loading papers...' : 'Select paper'}
                descriptionMode="tooltip"
                className="select-control--paper"
                searchable
                searchPlaceholder="Search papers..."
                disabled={assignmentOptions.initialLoading}
              />
            </Field>
            <Field label="Annotator">
              <SelectControl
                value={form.annotator_id}
                options={annotatorOptions}
                onChange={(annotator_id) => setAssignmentForm((current) => ({ ...current, annotator_id }))}
                ariaLabel="Choose annotator"
                placeholder={assignmentOptions.initialLoading ? 'Loading annotators...' : 'Select annotator'}
                disabled={assignmentOptions.initialLoading}
              />
            </Field>
            <Field label="Due date">
              <input type="date" value={form.due_at} onChange={(event) => setAssignmentForm((current) => ({ ...current, due_at: event.target.value }))} />
            </Field>
            <Button icon={CalendarDays} onClick={handleCreateAssignment} disabled={!form.paper_id || !form.annotator_id || Boolean(loading)}>Assign</Button>
          </div>
        </section>
      ) : null}

      <section className="management-card management-card--wide">
        <div className="management-heading">
          <div><ClipboardList aria-hidden="true" size={18} /><h3>{canAssign ? 'All relevant assignments' : 'My assignments'}</h3></div>
          <span className="muted">{assignments.initialLoading ? 'Loading...' : `${assignments.data.length} loaded`}</span>
        </div>

        {canAssign ? (
          <div className="assignment-history-panel">
            <div className="assignment-history-panel__top">
              <div>
                <p className="eyebrow">Paper trail</p>
                <h4>Assignment history</h4>
                <p>Select any paper, including currently unassignable papers, to inspect its assignment trail.</p>
              </div>
              <Field label="Paper history">
                <SelectControl
                  value={selectedAssignmentHistoryPaperId}
                  options={historyPaperOptions}
                  onChange={setSelectedAssignmentHistoryPaperId}
                  ariaLabel="Choose paper history"
                  placeholder={assignmentOptions.initialLoading ? 'Loading papers...' : 'Select paper'}
                  descriptionMode="tooltip"
                  className="select-control--paper"
                  searchable
                  searchPlaceholder="Search paper history..."
                  disabled={assignmentOptions.initialLoading || historyPaperOptions.length === 0}
                />
              </Field>
            </div>

            {!selectedAssignmentHistoryPaperId ? (
              <EmptyState icon={ClipboardList} title="No paper selected" description="Select a paper to inspect its assignment history." />
            ) : selectedHistoryResource?.initialLoading ? (
              <div className="loading-card">Loading paper history...</div>
            ) : selectedHistoryResource?.error ? (
              <MessageBanner type="error" text={selectedHistoryResource.error} />
            ) : selectedHistory ? (
              <>
                <div className="assignment-history-summary">
                  <div><span>Paper</span><strong>{selectedHistory.paper.paper_id}</strong></div>
                  <div><span>Current state</span><strong>{activeHistoryAssignment ? 'Active assignment' : 'Available for assignment'}</strong></div>
                  <div><span>Trail entries</span><strong>{historyAssignments.length}</strong></div>
                  <div><span>DOI</span><strong>{selectedHistory.paper.doi || '-'}</strong></div>
                </div>
                {activeHistoryAssignment ? <StatusPill tone={assignmentTone(activeHistoryAssignment.status)}>{activeHistoryAssignment.status}</StatusPill> : null}
                {historyAssignments.length === 0 ? (
                  <EmptyState icon={ClipboardList} title="This paper has not been assigned yet." description="There is no assignment trail for this paper." />
                ) : (
                  <DataTable className="assignment-history-table">
                    <table>
                      <thead><tr><th>Assigned</th><th>Annotator</th><th>Reviewer</th><th>Status</th><th>Version</th><th>Due</th><th>Started</th><th>Submitted</th><th>Completed</th></tr></thead>
                      <tbody>
                        {historyAssignments.map((assignment) => (
                          <tr key={assignment.id}>
                            <td>{formatDate(assignment.assigned_at)}</td>
                            <td><strong>{assignment.annotator_name || '-'}</strong><span>{assignment.annotator_email}</span></td>
                            <td><strong>{assignment.reviewer_name || '-'}</strong><span>{assignment.reviewer_email}</span></td>
                            <td><StatusPill tone={assignmentTone(assignment.status)}>{assignment.status}</StatusPill></td>
                            <td>{assignment.latest_submission_version ? `v${assignment.latest_submission_version}` : '-'}</td>
                            <td>{formatDate(assignment.due_at)}</td>
                            <td>{formatDate(assignment.started_at)}</td>
                            <td>{formatDate(assignment.submitted_at)}</td>
                            <td>{formatDate(assignment.completed_at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </DataTable>
                )}
              </>
            ) : null}
          </div>
        ) : null}

        {assignments.initialLoading ? (
          <div className="loading-card">Loading assignments...</div>
        ) : assignments.data.length === 0 ? (
          <EmptyState icon={ClipboardList} title="No assignments yet" description={canAssign ? 'Create an assignment to begin the annotation workflow.' : 'Your reviewer has not assigned a paper yet.'} />
        ) : (
          <DataTable>
            <table>
              <thead><tr><th>Paper</th><th>Annotator</th><th>Reviewer</th><th>Status</th><th>Version</th><th>Due</th><th>Submitted</th><th>Action</th></tr></thead>
              <tbody>
                {assignments.data.map((assignment) => (
                  <tr key={assignment.id}>
                    <td><strong>{assignment.paper_id}</strong><span>{assignment.paper_title}</span></td>
                    <td><strong>{assignment.annotator_name || '-'}</strong><span>{assignment.annotator_email}</span></td>
                    <td><strong>{assignment.reviewer_name || '-'}</strong><span>{assignment.reviewer_email}</span></td>
                    <td><StatusPill tone={assignmentTone(assignment.status)}>{assignment.status}</StatusPill></td>
                    <td>{assignment.latest_submission_version ? `v${assignment.latest_submission_version}` : '-'}</td>
                    <td>{formatDate(assignment.due_at)}</td>
                    <td>{formatDate(assignment.submitted_at)}</td>
                    <td>
                      {canAssign && assignment.status !== 'approved' && assignment.status !== 'cancelled' ? (
                        <Button variant="danger" size="compact" icon={XCircle} onClick={() => handleCancelAssignment(assignment)} disabled={Boolean(loading)}>Cancel</Button>
                      ) : <span className="muted">-</span>}
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
