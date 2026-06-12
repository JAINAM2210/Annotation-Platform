import { useEffect, useMemo, useState } from 'react';
import { Download, FileDown, RefreshCw } from 'lucide-react';
import { downloadFinalAnnotations } from '../../api/client';
import { useAuth } from '../../auth/AuthContext';
import { errorMessage, type Message } from '../../lib/status';
import { Button, EmptyState, Field, MessageBanner, SectionHeader, SelectControl, StatusPill } from '../../ui/Primitives';
import type { ExportFormat, PaperSummary } from '../../types';
import { useWorkspaceData } from './WorkspaceDataContext';

export function ExportsPage() {
  const { currentUser, getAccessToken } = useAuth();
  const {
    assignments,
    assignmentOptions,
    exportPaperId: paperId,
    setExportPaperId: setPaperId,
    exportFormat: format,
    setExportFormat: setFormat,
    ensureAssignments,
    ensureAssignmentOptions,
  } = useWorkspaceData();
  const [loading, setLoading] = useState('');
  const [message, setMessage] = useState<Message>({ type: 'info', text: 'Exports ready' });

  const paperOptionsSource: PaperSummary[] = useMemo(() => {
    if (currentUser?.role === 'admin' || currentUser?.role === 'reviewer') return assignmentOptions.data.papers;
    return assignments.data
      .filter((assignment) => assignment.status === 'approved')
      .map((assignment) => ({
        paper_id: assignment.paper_id,
        title: assignment.paper_title,
        doi: assignment.doi,
        has_edited_version: false,
        assignment: {
          assignment_id: assignment.id,
          status: assignment.status,
          annotator_id: assignment.annotator_id,
          reviewer_id: assignment.reviewer_id,
          latest_submission_id: assignment.latest_submission_id,
          latest_submission_status: assignment.latest_submission_status,
          latest_submission_version: assignment.latest_submission_version,
          latest_review_comment: assignment.latest_review_comment,
        },
      }));
  }, [assignmentOptions.data.papers, assignments.data, currentUser?.role]);

  const paperOptions = useMemo(() => [...paperOptionsSource]
    .sort((left, right) => (left.title || left.paper_id).localeCompare(right.title || right.paper_id, undefined, { sensitivity: 'base' }))
    .map((paper) => ({
      value: paper.paper_id,
      label: paper.title || paper.paper_id,
      description: paper.doi ? `DOI: ${paper.doi}` : 'DOI not available',
      meta: paper.assignment?.status ?? paper.paper_id,
      previewTitle: paper.title || paper.paper_id,
      previewDescription: paper.assignment?.status ? `${paper.paper_id} · ${paper.assignment.status}` : paper.paper_id,
    })), [paperOptionsSource]);

  async function refreshExportPapers(force = false) {
    await ensureAssignments(force);
    if (currentUser?.role === 'admin' || currentUser?.role === 'reviewer') await ensureAssignmentOptions(force);
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
    void run('load-export-papers', () => refreshExportPapers(false));
  }, [currentUser?.role, ensureAssignmentOptions, ensureAssignments]);

  useEffect(() => {
    if (paperId && paperOptionsSource.some((paper) => paper.paper_id === paperId)) return;
    setPaperId(paperOptionsSource[0]?.paper_id ?? '');
  }, [paperId, paperOptionsSource, setPaperId]);

  function handleDownload() {
    if (!paperId) return;
    void run('download-export', async () => {
      const token = await getAccessToken();
      const result = await downloadFinalAnnotations(token, paperId, format);
      const href = URL.createObjectURL(result.blob);
      const link = document.createElement('a');
      link.href = href;
      link.download = result.filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(href);
      setMessage({ type: 'success', text: `${result.filename} downloaded` });
    });
  }

  const approvedCount = assignments.data.filter((assignment) => assignment.status === 'approved').length;
  const loadError = assignments.error || assignmentOptions.error;
  const isInitialLoading = assignments.initialLoading || ((currentUser?.role === 'admin' || currentUser?.role === 'reviewer') && assignmentOptions.initialLoading);
  const isRefreshing = assignments.refreshing || assignmentOptions.refreshing;

  return (
    <main className="workspace-page">
      <SectionHeader
        eyebrow="Export"
        title="Final annotations"
        description="Download approved final annotations. Drafts and submitted work are never exported from here."
        actions={<Button variant="secondary" size="compact" icon={RefreshCw} onClick={() => void run('refresh-export-papers', () => refreshExportPapers(true))} disabled={Boolean(loading)}>Refresh</Button>}
      />
      <MessageBanner type={message.type} text={message.text} />
      {isRefreshing ? <MessageBanner type="info" text="Refreshing export options in the background." /> : null}
      {loadError ? <MessageBanner type="error" text={loadError} /> : null}

      <section className="management-card management-card--wide export-card">
        <div className="management-heading">
          <div><FileDown aria-hidden="true" size={18} /><h3>Download final output</h3></div>
          <StatusPill tone="approved">{approvedCount} approved assignment{approvedCount === 1 ? '' : 's'}</StatusPill>
        </div>
        {isInitialLoading ? (
          <div className="loading-card">Loading export options...</div>
        ) : paperOptions.length === 0 ? (
          <EmptyState icon={FileDown} title="No exportable papers yet" description="Approved final annotations will appear here after reviewer approval." />
        ) : (
          <div className="export-form">
            <Field label="Paper">
              <SelectControl
                value={paperId}
                options={paperOptions}
                onChange={setPaperId}
                ariaLabel="Choose paper to export"
                descriptionMode="tooltip"
                className="select-control--paper"
                searchable
                searchPlaceholder="Search papers..."
              />
            </Field>
            <Field label="Format">
              <SelectControl
                value={format}
                options={[{ value: 'csv', label: 'CSV', description: 'Spreadsheet-friendly relation table.' }, { value: 'json', label: 'JSON', description: 'Structured final annotation records.' }]}
                onChange={(value) => setFormat(value as ExportFormat)}
                ariaLabel="Choose export format"
              />
            </Field>
            <Button icon={Download} onClick={handleDownload} disabled={!paperId || Boolean(loading)}>{loading === 'download-export' ? 'Preparing...' : 'Download'}</Button>
          </div>
        )}
      </section>
    </main>
  );
}
