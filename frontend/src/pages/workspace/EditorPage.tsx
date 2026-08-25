import { useCallback, useEffect, useMemo, useState } from 'react';
import type { CSSProperties, KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent } from 'react';
import { AlertTriangle, CheckCircle2, Database, FileText, MessageSquareReply, RefreshCw, RotateCcw, Save, ScrollText, Send } from 'lucide-react';
import {
  addDirectSchemaPredicate,
  approveReviewSubmission,
  returnReviewSubmission,
  savePaperRelations,
  submitAssignment,
} from '../../api/client';
import { useAuth } from '../../auth/AuthContext';
import ParagraphEditor, { type ParagraphRevisionChanges } from '../../components/ParagraphEditor';
import { errorMessage, type Message } from '../../lib/status';
import { Button, EmptyState, MessageBanner, ProgressBar, SelectControl, StatusPill } from '../../ui/Primitives';
import type {
  MentionRecord,
  PaperAssignmentState,
  PaperDetailResponse,
  ParagraphCommentRecord,
  ParagraphRecord,
  RelationRecord,
  SentenceRecord,
} from '../../types';
import { useWorkspaceData, type EditorDraftState } from './WorkspaceDataContext';

function relationsEqual(left: RelationRecord[], right: RelationRecord[]) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function paragraphCommentsEqual(left: Record<string, string>, right: Record<string, string>) {
  const normalized = (comments: Record<string, string>) => Object.fromEntries(
    Object.entries(comments)
      .filter(([, comment]) => comment.trim().length > 0)
      .sort(([leftId], [rightId]) => leftId.localeCompare(rightId))
  );
  return JSON.stringify(normalized(left)) === JSON.stringify(normalized(right));
}

function paragraphCommentMap(comments: ParagraphCommentRecord[] | undefined) {
  return Object.fromEntries((comments ?? []).map((comment) => [comment.paragraph_id, comment.comment_text]));
}

function editableRelations(items: RelationRecord[]) {
  return items;
}

const SIDEBAR_WIDTH_STORAGE_KEY = 'annotationPlatform.editorSidebarWidth';
const DEFAULT_SIDEBAR_WIDTH = 304;
const MIN_SIDEBAR_WIDTH = 248;
const MAX_SIDEBAR_WIDTH = 520;
const SIDEBAR_KEYBOARD_STEP = 24;

function clampSidebarWidth(value: number) {
  return Math.min(MAX_SIDEBAR_WIDTH, Math.max(MIN_SIDEBAR_WIDTH, Math.round(value)));
}

function initialSidebarWidth() {
  if (typeof window === 'undefined') return DEFAULT_SIDEBAR_WIDTH;
  const stored = Number(window.localStorage.getItem(SIDEBAR_WIDTH_STORAGE_KEY));
  return Number.isFinite(stored) && stored > 0 ? clampSidebarWidth(stored) : DEFAULT_SIDEBAR_WIDTH;
}

function emptyEditorCopy(role?: string) {
  if (role === 'admin') {
    return {
      title: 'No papers are available yet',
      description: 'Check the database paper import/population before starting annotation work.',
    };
  }
  if (role === 'reviewer') {
    return {
      title: 'No papers are available yet',
      description: 'Papers will appear here after they are imported into the platform database.',
    };
  }
  return {
    title: 'No papers assigned yet',
    description: 'Your reviewer or admin will assign a paper when it is ready.',
  };
}

function draftFromDetail(detail: PaperDetailResponse | null | undefined): EditorDraftState {
  const paragraphComments = paragraphCommentMap(detail?.paragraph_comments);
  return {
    relations: detail?.relations ?? [],
    baselineRelations: detail?.relations ?? [],
    paragraphComments,
    baselineParagraphComments: paragraphComments,
    history: [],
    dirty: false,
    currentSentenceIndex: detail?.sentences[0]?.sentence_index ?? (detail?.paragraphs.length ? 1 : 0),
  };
}

export function EditorPage() {
  const { currentUser, getAccessToken } = useAuth();
  const {
    papers: papersResource,
    paperDetails,
    selectedPaperId: paperId,
    setSelectedPaperId,
    editorDrafts,
    setEditorDraft,
    ensurePapers,
    ensurePaperDetail,
    ensureReviewQueue,
    refreshEditorAfterWorkflowChange,
  } = useWorkspaceData();
  const [loading, setLoading] = useState('');
  const [message, setMessage] = useState<Message>({ type: 'info', text: 'Workspace ready' });
  const [status, setStatus] = useState('');
  const [sidebarWidth, setSidebarWidth] = useState(initialSidebarWidth);
  const [isResizingSidebar, setIsResizingSidebar] = useState(false);

  const papers = papersResource.data;
  const selectedPaper = papers.find((paper) => paper.paper_id === paperId);
  const detailResource = paperId ? paperDetails[paperId] : undefined;
  const detail = detailResource?.data ?? null;
  const paperMeta = detail?.paper ?? null;
  const assignmentState: PaperAssignmentState | null = detail?.assignment ?? detail?.paper.assignment ?? null;
  const sentences = detail?.sentences ?? [];
  const paragraphs = detail?.paragraphs ?? [];
  const mentions = detail?.mentions ?? [];
  const sourceLabel = detail?.source ?? 'source';
  const warnings = detail?.warnings ?? [];
  const revision = detail?.revision ?? null;
  const changes = detail?.changes ?? null;
  const draftState = editorDrafts[paperId] ?? draftFromDetail(detail);
  const relations = draftState.relations;
  const baselineRelations = draftState.baselineRelations;
  const paragraphComments = draftState.paragraphComments;
  const history = draftState.history;
  const dirty = draftState.dirty;
  const currentSentenceIndex = draftState.currentSentenceIndex;
  const hasLoadedPaperList = papersResource.lastLoadedAt > 0;
  const noPapers = hasLoadedPaperList && papers.length === 0;
  const initialEditorLoading = papersResource.initialLoading || Boolean(paperId && detailResource?.initialLoading && !paperMeta);
  const editorError = papersResource.error || detailResource?.error || '';

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
    void run('load-papers', async () => {
      await ensurePapers(false);
    });
  }, [ensurePapers]);

  useEffect(() => {
    if (!paperId) {
      setStatus('');
      return;
    }
    const hasCachedDetail = Boolean(paperDetails[paperId]?.data);
    if (!hasCachedDetail) setStatus('Loading paper...');
    void ensurePaperDetail(paperId, false)
      .then(() => {
        setStatus('');
        setMessage({ type: 'success', text: 'Paper loaded' });
      })
      .catch((error) => {
        setStatus('');
        setMessage({ type: 'error', text: errorMessage(error) });
      });
  }, [ensurePaperDetail, paperDetails, paperId]);

  useEffect(() => {
    if (!paperId || !detail || editorDrafts[paperId]) return;
    setEditorDraft(paperId, draftFromDetail(detail));
  }, [detail, editorDrafts, paperId, setEditorDraft]);

  useEffect(() => {
    if (!paperId) return;
    setEditorDraft(paperId, (current) => ({
      ...(current ?? draftFromDetail(detail)),
      currentSentenceIndex: paragraphs.length > 0 ? Math.max(1, current?.currentSentenceIndex ?? 1) : 0,
    }));
  }, [detail, paperId, paragraphs.length, setEditorDraft]);

  useEffect(() => {
    window.localStorage.setItem(SIDEBAR_WIDTH_STORAGE_KEY, String(sidebarWidth));
  }, [sidebarWidth]);

  useEffect(() => {
    if (!paperId || paragraphs.length === 0) return undefined;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible.length === 0) return;
        const visibleIndex = Number(visible[0].target.getAttribute('data-progress-index') || '1');
        setEditorDraft(paperId, (current) => ({
          ...(current ?? draftFromDetail(detail)),
          currentSentenceIndex: visibleIndex,
        }));
      },
      { root: null, rootMargin: '-90px 0px -70% 0px', threshold: [0.05, 0.2, 0.5] }
    );
    const elements = Array.from(document.querySelectorAll<HTMLElement>('[data-progress-index]'));
    elements.forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, [detail, mentions, paperId, paragraphs, relations, sentences, setEditorDraft]);

  const mentionsBySentence = useMemo(() => {
    const grouped = new Map<string, MentionRecord[]>();
    mentions.forEach((mention) => {
      if (!grouped.has(mention.sentence_id)) grouped.set(mention.sentence_id, []);
      grouped.get(mention.sentence_id)!.push(mention);
    });
    return grouped;
  }, [mentions]);

  const sentenceById = useMemo(() => new Map(sentences.map((sentence) => [sentence.sentence_id, sentence])), [sentences]);

  const paragraphBySentenceId = useMemo(() => {
    const grouped = new Map<string, string>();
    paragraphs.forEach((paragraph) => paragraph.sentence_ids.forEach((sentenceId) => grouped.set(sentenceId, paragraph.paragraph_id)));
    return grouped;
  }, [paragraphs]);

  const paragraphIdsForRelation = useCallback((relation: RelationRecord) => {
    if (relation.support_paragraph_id) return [relation.support_paragraph_id];
    const sentenceIds = relation.support_sentence_ids
      ? relation.support_sentence_ids.split(';').filter(Boolean)
      : relation.sentence_id
        ? [relation.sentence_id]
        : [];
    return Array.from(new Set(
      sentenceIds
        .map((sentenceId) => paragraphBySentenceId.get(sentenceId))
        .filter((paragraphId): paragraphId is string => Boolean(paragraphId))
    ));
  }, [paragraphBySentenceId]);

  const relationsByParagraph = useMemo(() => {
    const grouped = new Map<string, RelationRecord[]>();
    relations.forEach((relation) => {
      paragraphIdsForRelation(relation).forEach((paragraphId) => {
        if (!grouped.has(paragraphId)) grouped.set(paragraphId, []);
        grouped.get(paragraphId)!.push(relation);
      });
    });
    return grouped;
  }, [paragraphIdsForRelation, relations]);

  const revisionChangesByParagraph = useMemo(() => {
    const grouped = new Map<string, ParagraphRevisionChanges>();
    if (!changes) return grouped;
    const ensureParagraphChanges = (paragraphId: string) => {
      if (!grouped.has(paragraphId)) {
        grouped.set(paragraphId, {
          parentVersion: changes.parent_version,
          addedRelationIds: new Set<string>(),
          removedRelations: [],
          modifiedRelations: [],
        });
      }
      return grouped.get(paragraphId)!;
    };
    paragraphs.forEach((paragraph) => ensureParagraphChanges(paragraph.paragraph_id));
    changes.added.forEach((relation) => {
      paragraphIdsForRelation(relation).forEach((paragraphId) => {
        ensureParagraphChanges(paragraphId).addedRelationIds.add(relation.logical_relation_id || relation.relation_id);
      });
    });
    changes.removed.forEach((relation) => {
      paragraphIdsForRelation(relation).forEach((paragraphId) => {
        ensureParagraphChanges(paragraphId).removedRelations.push(relation);
      });
    });
    changes.modified.forEach((change) => {
      paragraphIdsForRelation(change.after).forEach((paragraphId) => {
        ensureParagraphChanges(paragraphId).modifiedRelations.push(change);
      });
    });
    changes.paragraph_comments.forEach((commentChange) => {
      ensureParagraphChanges(commentChange.paragraph_id).commentChange = commentChange;
    });
    return grouped;
  }, [changes, paragraphIdsForRelation, paragraphs]);

  const totalItems = paragraphs.length;
  const progressPercent = totalItems > 0 ? Math.min(100, Math.round((currentSentenceIndex / totalItems) * 100)) : 0;
  const activeAssignment = assignmentState ?? selectedPaper?.assignment ?? null;
  const annotatorEditableStatuses = new Set(['assigned', 'in_progress', 'returned']);
  const reviewerEditableStatuses = new Set(['submitted', 'review_in_progress']);
  const isReviewerEditor = currentUser?.role === 'reviewer' || currentUser?.role === 'admin';
  const canEditRelations = Boolean(
    activeAssignment
    && (
      (currentUser?.role === 'annotator' && annotatorEditableStatuses.has(activeAssignment.status))
      || (isReviewerEditor && reviewerEditableStatuses.has(activeAssignment.status))
    )
  );
  const canEditComments = canEditRelations;
  const readOnly = !canEditRelations;
  const commentsReadOnly = !canEditComments;
  const canSubmit = Boolean(canEditRelations && currentUser?.role === 'annotator' && activeAssignment?.latest_submission_status === 'draft' && !dirty);
  const canCompleteReview = Boolean(
    canEditRelations
    && isReviewerEditor
    && ['submitted', 'review_draft'].includes(activeAssignment?.latest_submission_status ?? '')
    && !dirty
  );
  const editorAccessMessage = !activeAssignment
    ? isReviewerEditor
      ? 'You can inspect this paper, but you can edit only papers assigned to you after the annotator submits them.'
      : 'Create an assignment before editing this paper.'
    : isReviewerEditor && canEditRelations
      ? 'You are editing a reviewer draft. Save it before returning or approving this version.'
    : activeAssignment.status === 'submitted'
      ? 'This assignment has been submitted for review.'
      : activeAssignment.status === 'review_in_progress'
        ? 'The reviewer is currently editing this submission.'
      : activeAssignment.status === 'approved'
        ? 'This assignment has been approved and is read-only.'
        : activeAssignment.status === 'cancelled'
          ? 'This assignment was cancelled and is read-only.'
          : isReviewerEditor
            ? 'No submitted revision is ready for reviewer editing yet.'
            : '';
  const paperOptions = useMemo(() => [...papers]
    .sort((left, right) => (left.title || left.paper_id).localeCompare(right.title || right.paper_id, undefined, { sensitivity: 'base' }))
    .map((paper) => ({
      value: paper.paper_id,
      label: paper.title || paper.paper_id,
      description: paper.doi ? `DOI: ${paper.doi}` : 'DOI not available',
      meta: paper.paper_id,
      previewTitle: paper.title || paper.paper_id,
      previewDescription: paper.has_edited_version ? `${paper.paper_id} · edited` : paper.paper_id,
    })), [papers]);

  const commitRelations = (updater: (current: RelationRecord[]) => RelationRecord[]) => {
    if (!canEditRelations || !paperId) return;
    setEditorDraft(paperId, (current) => {
      const base = current ?? draftState;
      const next = updater(base.relations);
      return {
        ...base,
        relations: next,
        history: [...base.history, base.relations],
        dirty: !relationsEqual(editableRelations(next), editableRelations(base.baselineRelations))
          || !paragraphCommentsEqual(base.paragraphComments, base.baselineParagraphComments),
      };
    });
  };

  const commitParagraphComment = (paragraphId: string, commentText: string) => {
    if (!canEditComments || !paperId) return;
    setEditorDraft(paperId, (current) => {
      const base = current ?? draftState;
      const nextComments = { ...base.paragraphComments, [paragraphId]: commentText };
      return {
        ...base,
        paragraphComments: nextComments,
        dirty: !relationsEqual(editableRelations(base.relations), editableRelations(base.baselineRelations))
          || !paragraphCommentsEqual(nextComments, base.baselineParagraphComments),
      };
    });
  };

  async function handleSave() {
    if (!paperId || !canEditRelations) return;
    await run('save-relations', async () => {
      const token = await getAccessToken();
      const currentRelations = editableRelations(relations);
      const currentParagraphComments = Object.entries(paragraphComments)
        .filter(([, commentText]) => commentText.trim().length > 0)
        .map(([paragraphId, commentText]) => ({ paragraph_id: paragraphId, comment_text: commentText }));
      const result = await savePaperRelations(
        token,
        paperId,
        currentRelations,
        currentParagraphComments,
        'paragraph',
        revision?.submission_id ?? activeAssignment?.latest_submission_id ?? null,
      );
      setStatus(`Saved to ${result.saved_to}`);
      setEditorDraft(paperId, (current) => ({
        ...(current ?? draftState),
        relations: currentRelations,
        baselineRelations: currentRelations,
        paragraphComments,
        baselineParagraphComments: paragraphComments,
        history: [],
        dirty: false,
      }));
      await refreshEditorAfterWorkflowChange(paperId);
      if (isReviewerEditor) await ensureReviewQueue('submitted', true);
      setMessage({ type: 'success', text: isReviewerEditor ? 'Reviewer draft saved' : 'Draft saved' });
    });
  }

  async function handleSubmitAssignment() {
    if (!activeAssignment || !canSubmit) return;
    await run('submit-assignment', async () => {
      const token = await getAccessToken();
      await submitAssignment(token, activeAssignment.assignment_id);
      await refreshEditorAfterWorkflowChange(paperId);
      setMessage({ type: 'success', text: 'Submitted for review' });
    });
  }

  async function handleReturnToAnnotator() {
    if (!activeAssignment?.latest_submission_id || !canCompleteReview) return;
    await run('return-submission', async () => {
      const token = await getAccessToken();
      await returnReviewSubmission(token, activeAssignment.latest_submission_id!, '');
      await Promise.all([
        refreshEditorAfterWorkflowChange(paperId),
        ensureReviewQueue('submitted', true),
      ]);
      setMessage({ type: 'success', text: 'Returned to the annotator with this revision preserved' });
    });
  }

  async function handleApproveReview() {
    if (!activeAssignment?.latest_submission_id || !canCompleteReview) return;
    await run('approve-submission', async () => {
      const token = await getAccessToken();
      await approveReviewSubmission(token, activeAssignment.latest_submission_id!, '');
      await Promise.all([
        refreshEditorAfterWorkflowChange(paperId),
        ensureReviewQueue('submitted', true),
      ]);
      setMessage({ type: 'success', text: 'Latest reviewer-visible revision approved as final' });
    });
  }

  async function handleAddDirectPredicate(predicate: string) {
    const token = await getAccessToken();
    await addDirectSchemaPredicate(token, predicate);
  }

  function handleUndo() {
    if (!paperId) return;
    setEditorDraft(paperId, (current) => {
      const base = current ?? draftState;
      if (base.history.length === 0) return base;
      const previous = base.history[base.history.length - 1];
      return {
        ...base,
        relations: previous,
        history: base.history.slice(0, -1),
        dirty: !relationsEqual(editableRelations(previous), editableRelations(base.baselineRelations))
          || !paragraphCommentsEqual(base.paragraphComments, base.baselineParagraphComments),
      };
    });
  }

  const handleSidebarResizeStart = useCallback((event: ReactPointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    let nextWidth = sidebarWidth;
    const startX = event.clientX;
    const startWidth = sidebarWidth;

    setIsResizingSidebar(true);

    const handlePointerMove = (moveEvent: PointerEvent) => {
      nextWidth = clampSidebarWidth(startWidth + moveEvent.clientX - startX);
      setSidebarWidth(nextWidth);
    };

    const handlePointerEnd = () => {
      setSidebarWidth(nextWidth);
      setIsResizingSidebar(false);
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerEnd);
      window.removeEventListener('pointercancel', handlePointerEnd);
    };

    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerEnd);
    window.addEventListener('pointercancel', handlePointerEnd);
  }, [sidebarWidth]);

  const handleSidebarResizeKeyDown = useCallback((event: ReactKeyboardEvent<HTMLButtonElement>) => {
    if (event.key === 'ArrowLeft') {
      event.preventDefault();
      setSidebarWidth((current) => clampSidebarWidth(current - SIDEBAR_KEYBOARD_STEP));
    }
    if (event.key === 'ArrowRight') {
      event.preventDefault();
      setSidebarWidth((current) => clampSidebarWidth(current + SIDEBAR_KEYBOARD_STEP));
    }
    if (event.key === 'Home') {
      event.preventDefault();
      setSidebarWidth(MIN_SIDEBAR_WIDTH);
    }
    if (event.key === 'End') {
      event.preventDefault();
      setSidebarWidth(MAX_SIDEBAR_WIDTH);
    }
  }, []);

  const emptyCopy = emptyEditorCopy(currentUser?.role);

  function renderMainPanel() {
    if (paperMeta) {
      return (
        <>
          <header className="paper-header">
            <div>
              <p className="eyebrow">Current paper</p>
              <h2>{paperMeta.title}</h2>
              <p><FileText aria-hidden="true" size={15} /> DOI: {paperMeta.doi || 'Not provided'}</p>
            </div>
            <div className="paper-header__badges">
              {activeAssignment ? <StatusPill tone={activeAssignment.status === 'approved' ? 'approved' : activeAssignment.status === 'returned' ? 'rejected' : 'info'}>{activeAssignment.status}</StatusPill> : <StatusPill tone="pending">unassigned</StatusPill>}
              {selectedPaper?.has_edited_version ? <StatusPill tone="info">edited version</StatusPill> : null}
            </div>
          </header>
          <div className="editor-toolbar">
            <div className="editor-toolbar__summary">
              <div className="editor-toolbar__title">Editing progress</div>
              <div className="editor-toolbar__meta">Paragraph {currentSentenceIndex} of {totalItems}<span className="editor-toolbar__dot">/</span>{progressPercent}% through paper</div>
            </div>
            <div className="editor-toolbar__actions">
              {detailResource?.refreshing ? <StatusPill tone="info">Refreshing</StatusPill> : null}
              <StatusPill tone={dirty ? 'pending' : 'approved'}>{dirty ? 'Unsaved' : 'Saved'}</StatusPill>
              <Button variant="secondary" icon={RotateCcw} onClick={handleUndo} disabled={!canEditRelations || history.length === 0}>Undo</Button>
              <Button icon={Save} onClick={handleSave} disabled={!paperId || !canEditRelations || loading === 'save-relations'}>
                {loading === 'save-relations' ? 'Saving...' : 'Save draft'}
              </Button>
              {currentUser?.role === 'annotator' ? (
                <Button variant="success" icon={Send} onClick={handleSubmitAssignment} disabled={!canSubmit || loading === 'submit-assignment'}>
                  {loading === 'submit-assignment' ? 'Submitting...' : 'Submit'}
                </Button>
              ) : null}
              {isReviewerEditor ? (
                <>
                  <Button variant="danger" icon={MessageSquareReply} onClick={handleReturnToAnnotator} disabled={!canCompleteReview || loading === 'return-submission'}>
                    {loading === 'return-submission' ? 'Returning...' : 'Return'}
                  </Button>
                  <Button variant="success" icon={CheckCircle2} onClick={handleApproveReview} disabled={!canCompleteReview || loading === 'approve-submission'}>
                    {loading === 'approve-submission' ? 'Approving...' : 'Approve final'}
                  </Button>
                </>
              ) : null}
            </div>
            <div className="editor-toolbar__progress">
              <ProgressBar value={progressPercent} label="Paper annotation progress" />
            </div>
          </div>
          {editorAccessMessage ? <MessageBanner type="info" text={editorAccessMessage} /> : null}
          {activeAssignment?.latest_review_comment ? <MessageBanner type="info" text={`Reviewer comment: ${activeAssignment.latest_review_comment}`} /> : null}
          {warnings.length > 0 ? (
            <div className="warning-stack">
              {warnings.map((warning) => <MessageBanner key={warning} type="info" text={warning} />)}
            </div>
          ) : null}
          <div className="paragraph-stack">
            {paragraphs.length === 0 ? <EmptyState icon={AlertTriangle} title="No editable paragraphs" description="This paper is present, but its sentence or paragraph data is not ready yet." /> : null}
            {paragraphs.map((paragraph) => (
              <ParagraphEditor
                key={paragraph.paragraph_id}
                paperId={paperMeta.paper_id}
                paperTitle={paperMeta.title}
                doi={paperMeta.doi}
                paragraph={paragraph}
                sentences={paragraph.sentence_ids.map((sentenceId) => sentenceById.get(sentenceId)).filter((sentence): sentence is SentenceRecord => Boolean(sentence))}
                mentionsBySentence={mentionsBySentence}
                relations={relationsByParagraph.get(paragraph.paragraph_id) ?? []}
                revisionChanges={revisionChangesByParagraph.get(paragraph.paragraph_id)}
                comment={paragraphComments[paragraph.paragraph_id] ?? ''}
                onAddPredicate={handleAddDirectPredicate}
                onDelete={(relationId) => commitRelations((current) => current.filter((item) => (item.logical_relation_id || item.relation_id) !== relationId))}
                onAdd={(relation) => commitRelations((current) => [...current, relation])}
                onUpdate={(relation) => commitRelations((current) => current.map((item) => (
                  item.logical_relation_id === relation.logical_relation_id ? relation : item
                )))}
                onCommentChange={(commentText) => commitParagraphComment(paragraph.paragraph_id, commentText)}
                readOnly={readOnly}
                commentReadOnly={commentsReadOnly}
              />
            ))}
          </div>
        </>
      );
    }

    if (initialEditorLoading) return <div className="loading-card">Loading workspace...</div>;

    if (editorError) {
      return (
        <div className="status-card editor-empty-card">
          <EmptyState icon={AlertTriangle} title="Editor data could not be loaded" description={editorError} />
          <div className="button-row">
            <Button variant="secondary" icon={RefreshCw} onClick={() => void run('refresh-editor', async () => { await ensurePapers(true); if (paperId) await ensurePaperDetail(paperId, true); })} disabled={Boolean(loading)}>Retry</Button>
          </div>
        </div>
      );
    }

    if (noPapers || !paperId) {
      return (
        <div className="status-card editor-empty-card">
          <EmptyState icon={ScrollText} title={emptyCopy.title} description={emptyCopy.description} />
        </div>
      );
    }

    return <div className="loading-card">Loading paper...</div>;
  }

  return (
    <div
      className={`app-shell${isResizingSidebar ? ' app-shell--resizing' : ''}`}
      style={{ '--editor-sidebar-width': `${sidebarWidth}px` } as CSSProperties}
    >
      <aside className="sidebar">
        <div className="sidebar__sticky">
          <div className="rail-heading">
            <span className="rail-heading__icon"><ScrollText aria-hidden="true" size={18} /></span>
            <div>
              <p className="eyebrow">Workspace</p>
              <h2>Relation Editor</h2>
            </div>
          </div>
          <div className="paper-picker">
            <label className="field">
              <span>Change paper</span>
              <SelectControl
                value={paperId}
                options={paperOptions}
                onChange={setSelectedPaperId}
                ariaLabel="Change paper"
                placeholder={papersResource.initialLoading ? 'Loading papers...' : 'No assigned papers'}
                disabled={paperOptions.length === 0 || papersResource.initialLoading}
                className="select-control--paper"
                descriptionMode="tooltip"
                searchable
                searchPlaceholder="Search papers..."
              />
            </label>
            {selectedPaper ? (
              <div className="selected-paper-card" title={selectedPaper.title}>
                <span>{selectedPaper.paper_id}</span>
                <strong>{selectedPaper.title}</strong>
                <small>{selectedPaper.doi || 'DOI not available'}</small>
              </div>
            ) : null}
          </div>
          <div className="rail-card">
            <div className="rail-stat"><span>Papers</span><strong>{papers.length}</strong></div>
            <div className="rail-stat"><span>Paragraphs</span><strong>{totalItems}</strong></div>
            <div className="rail-stat"><span>Relations</span><strong>{relations.length}</strong></div>
          </div>
          <div className="status-block">
            <StatusPill tone={dirty ? 'pending' : 'approved'}>{dirty ? 'unsaved changes' : 'all changes saved'}</StatusPill>
            <p className="muted"><Database aria-hidden="true" size={14} /> Source: {paperMeta ? sourceLabel : 'not loaded'}</p>
            <p className="muted">Undo steps: {history.length}</p>
            {papersResource.refreshing || detailResource?.refreshing ? <p className="muted">Refreshing in background...</p> : null}
            {status ? <p className="muted">{status}</p> : null}
            <MessageBanner type={message.type} text={message.text} />
          </div>
        </div>
      </aside>

      <button
        type="button"
        className="sidebar-resizer"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize editor sidebar"
        aria-valuemin={MIN_SIDEBAR_WIDTH}
        aria-valuemax={MAX_SIDEBAR_WIDTH}
        aria-valuenow={sidebarWidth}
        aria-valuetext={`${sidebarWidth}px`}
        title="Drag to resize sidebar"
        onPointerDown={handleSidebarResizeStart}
        onKeyDown={handleSidebarResizeKeyDown}
      />

      <main className="main-panel">
        {renderMainPanel()}
      </main>
    </div>
  );
}
