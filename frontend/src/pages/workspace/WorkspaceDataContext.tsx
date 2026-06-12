import { createContext, ReactNode, useCallback, useContext, useMemo, useRef, useState } from 'react';
import {
  fetchAdminUsers,
  fetchAnnotatorSignupRequests,
  fetchAssignmentOptions,
  fetchAssignments,
  fetchPaper,
  fetchPaperAssignmentHistory,
  fetchPapers,
  fetchReviewerSignupRequests,
  fetchReviewSubmissionDetail,
  fetchReviewSubmissions,
} from '../../api/client';
import { useAuth } from '../../auth/AuthContext';
import { errorMessage } from '../../lib/status';
import type {
  AssignmentOptionsResponse,
  AssignmentRead,
  ExportFormat,
  PaperAssignmentHistoryResponse,
  PaperDetailResponse,
  PaperSummary,
  ReviewSubmissionDetail,
  RelationRecord,
  ReviewSubmissionSummary,
  SubmissionStatus,
  UserRead,
  UserStatus,
} from '../../types';

const STALE_AFTER_MS = 120000;

export type WorkspaceResource<T> = {
  data: T;
  initialLoading: boolean;
  refreshing: boolean;
  error: string;
  lastLoadedAt: number;
};

type RequestStatusState = {
  annotator: UserStatus;
  reviewer: UserStatus;
};

type AssignmentFormState = {
  paper_id: string;
  annotator_id: string;
  due_at: string;
};

export type EditorDraftState = {
  relations: RelationRecord[];
  baselineRelations: RelationRecord[];
  history: RelationRecord[][];
  dirty: boolean;
  currentSentenceIndex: number;
};

type WorkspaceDataContextValue = {
  papers: WorkspaceResource<PaperSummary[]>;
  paperDetails: Record<string, WorkspaceResource<PaperDetailResponse | null>>;
  selectedPaperId: string;
  setSelectedPaperId: (paperId: string) => void;
  editorDrafts: Record<string, EditorDraftState>;
  setEditorDraft: (paperId: string, updater: EditorDraftState | ((current: EditorDraftState | undefined) => EditorDraftState)) => void;
  resetEditorDraftFromDetail: (paperId: string, detail: PaperDetailResponse) => void;
  assignments: WorkspaceResource<AssignmentRead[]>;
  assignmentOptions: WorkspaceResource<AssignmentOptionsResponse>;
  assignmentForm: AssignmentFormState;
  setAssignmentForm: (updater: AssignmentFormState | ((current: AssignmentFormState) => AssignmentFormState)) => void;
  selectedAssignmentHistoryPaperId: string;
  setSelectedAssignmentHistoryPaperId: (paperId: string) => void;
  assignmentHistories: Record<string, WorkspaceResource<PaperAssignmentHistoryResponse | null>>;
  ensureAssignmentHistory: (paperId: string, force?: boolean) => Promise<PaperAssignmentHistoryResponse | null>;
  exportPaperId: string;
  setExportPaperId: (paperId: string) => void;
  exportFormat: ExportFormat;
  setExportFormat: (format: ExportFormat) => void;
  reviewStatusFilter: SubmissionStatus;
  setReviewStatusFilter: (status: SubmissionStatus) => void;
  reviewQueues: Record<SubmissionStatus, WorkspaceResource<ReviewSubmissionSummary[]>>;
  reviewDetails: Record<string, WorkspaceResource<ReviewSubmissionDetail | null>>;
  selectedSubmissionByStatus: Partial<Record<SubmissionStatus, string>>;
  setSelectedSubmissionForStatus: (status: SubmissionStatus, submissionId: string) => void;
  requestStatus: RequestStatusState;
  setRequestStatus: (role: keyof RequestStatusState, status: UserStatus) => void;
  annotatorRequests: Record<UserStatus, WorkspaceResource<UserRead[]>>;
  reviewerRequests: Record<UserStatus, WorkspaceResource<UserRead[]>>;
  users: WorkspaceResource<UserRead[]>;
  ensurePapers: (force?: boolean) => Promise<PaperSummary[]>;
  ensurePaperDetail: (paperId: string, force?: boolean) => Promise<PaperDetailResponse | null>;
  ensureAssignments: (force?: boolean) => Promise<AssignmentRead[]>;
  ensureAssignmentOptions: (force?: boolean) => Promise<AssignmentOptionsResponse>;
  ensureReviewQueue: (status: SubmissionStatus, force?: boolean) => Promise<ReviewSubmissionSummary[]>;
  ensureReviewDetail: (submissionId: string, force?: boolean) => Promise<ReviewSubmissionDetail | null>;
  ensureAnnotatorRequests: (status: UserStatus, force?: boolean) => Promise<UserRead[]>;
  ensureReviewerRequests: (status: UserStatus, force?: boolean) => Promise<UserRead[]>;
  ensureUsers: (force?: boolean) => Promise<UserRead[]>;
  refreshEditorAfterWorkflowChange: (paperId?: string) => Promise<void>;
};

const WorkspaceDataContext = createContext<WorkspaceDataContextValue | null>(null);

function now() {
  return Date.now();
}

function makeResource<T>(data: T): WorkspaceResource<T> {
  return { data, initialLoading: true, refreshing: false, error: '', lastLoadedAt: 0 };
}

function isFresh(resource: Pick<WorkspaceResource<unknown>, 'lastLoadedAt'>) {
  return resource.lastLoadedAt > 0 && now() - resource.lastLoadedAt < STALE_AFTER_MS;
}

const emptyAssignmentOptions: AssignmentOptionsResponse = { papers: [], annotators: [] };
const statuses: UserStatus[] = ['pending', 'approved', 'rejected'];
const submissionStatuses: SubmissionStatus[] = ['draft', 'submitted', 'returned', 'approved', 'superseded'];

function makeUserRequestResources() {
  return statuses.reduce((acc, status) => {
    acc[status] = makeResource<UserRead[]>([]);
    return acc;
  }, {} as Record<UserStatus, WorkspaceResource<UserRead[]>>);
}

function makeReviewQueueResources() {
  return submissionStatuses.reduce((acc, status) => {
    acc[status] = makeResource<ReviewSubmissionSummary[]>([]);
    return acc;
  }, {} as Record<SubmissionStatus, WorkspaceResource<ReviewSubmissionSummary[]>>);
}

export function WorkspaceDataProvider({ children }: { children: ReactNode }) {
  const { getAccessToken } = useAuth();
  const inFlight = useRef(new Map<string, Promise<unknown>>());
  const [papers, setPapers] = useState(() => makeResource<PaperSummary[]>([]));
  const [paperDetails, setPaperDetails] = useState<Record<string, WorkspaceResource<PaperDetailResponse | null>>>({});
  const [selectedPaperId, setSelectedPaperId] = useState('');
  const [editorDrafts, setEditorDrafts] = useState<Record<string, EditorDraftState>>({});
  const [assignments, setAssignments] = useState(() => makeResource<AssignmentRead[]>([]));
  const [assignmentOptions, setAssignmentOptions] = useState(() => makeResource<AssignmentOptionsResponse>(emptyAssignmentOptions));
  const [assignmentForm, setAssignmentForm] = useState<AssignmentFormState>({ paper_id: '', annotator_id: '', due_at: '' });
  const [selectedAssignmentHistoryPaperId, setSelectedAssignmentHistoryPaperId] = useState('');
  const [assignmentHistories, setAssignmentHistories] = useState<Record<string, WorkspaceResource<PaperAssignmentHistoryResponse | null>>>({});
  const [exportPaperId, setExportPaperId] = useState('');
  const [exportFormat, setExportFormat] = useState<ExportFormat>('csv');
  const [reviewStatusFilter, setReviewStatusFilter] = useState<SubmissionStatus>('submitted');
  const [reviewQueues, setReviewQueues] = useState(() => makeReviewQueueResources());
  const [reviewDetails, setReviewDetails] = useState<Record<string, WorkspaceResource<ReviewSubmissionDetail | null>>>({});
  const [selectedSubmissionByStatus, setSelectedSubmissionByStatus] = useState<Partial<Record<SubmissionStatus, string>>>({});
  const [requestStatus, setRequestStatusState] = useState<RequestStatusState>({ annotator: 'pending', reviewer: 'pending' });
  const [annotatorRequests, setAnnotatorRequests] = useState(() => makeUserRequestResources());
  const [reviewerRequests, setReviewerRequests] = useState(() => makeUserRequestResources());
  const [users, setUsers] = useState(() => makeResource<UserRead[]>([]));


  const setEditorDraft = useCallback((paperId: string, updater: EditorDraftState | ((current: EditorDraftState | undefined) => EditorDraftState)) => {
    if (!paperId) return;
    setEditorDrafts((current) => ({
      ...current,
      [paperId]: typeof updater === 'function' ? updater(current[paperId]) : updater,
    }));
  }, []);

  const resetEditorDraftFromDetail = useCallback((paperId: string, detail: PaperDetailResponse) => {
    if (!paperId) return;
    setEditorDrafts((current) => {
      const existing = current[paperId];
      if (existing?.dirty) return current;
      return {
        ...current,
        [paperId]: {
          relations: detail.relations,
          baselineRelations: detail.relations,
          history: [],
          dirty: false,
          currentSentenceIndex: detail.sentences[0]?.sentence_index ?? 1,
        },
      };
    });
  }, []);

  function dedupe<T>(key: string, loader: () => Promise<T>): Promise<T> {
    const existing = inFlight.current.get(key) as Promise<T> | undefined;
    if (existing) return existing;
    const request = loader().finally(() => inFlight.current.delete(key));
    inFlight.current.set(key, request);
    return request;
  }

  const ensurePapers = useCallback(async (force = false) => {
    if (!force && papers.lastLoadedAt && isFresh(papers)) return papers.data;
    const hadData = papers.lastLoadedAt > 0;
    setPapers((current) => ({ ...current, initialLoading: !hadData, refreshing: hadData, error: '' }));
    return dedupe('papers', async () => {
      try {
        const token = await getAccessToken();
        const items = await fetchPapers(token);
        setPapers({ data: items, initialLoading: false, refreshing: false, error: '', lastLoadedAt: now() });
        setSelectedPaperId((current) => (current && items.some((item) => item.paper_id === current) ? current : items[0]?.paper_id ?? ''));
        return items;
      } catch (error) {
        const text = errorMessage(error);
        setPapers((current) => ({ ...current, initialLoading: false, refreshing: false, error: text }));
        throw error;
      }
    });
  }, [getAccessToken, papers]);

  const ensurePaperDetail = useCallback(async (paperId: string, force = false) => {
    if (!paperId) return null;
    const current = paperDetails[paperId] ?? makeResource<PaperDetailResponse | null>(null);
    if (!force && current.lastLoadedAt && isFresh(current)) return current.data;
    const hadData = current.lastLoadedAt > 0;
    setPaperDetails((items) => ({
      ...items,
      [paperId]: { ...(items[paperId] ?? current), initialLoading: !hadData, refreshing: hadData, error: '' },
    }));
    return dedupe(`paper:${paperId}`, async () => {
      try {
        const token = await getAccessToken();
        const detail = await fetchPaper(token, paperId);
        setPaperDetails((items) => ({
          ...items,
          [paperId]: { data: detail, initialLoading: false, refreshing: false, error: '', lastLoadedAt: now() },
        }));
        resetEditorDraftFromDetail(paperId, detail);
        return detail;
      } catch (error) {
        const text = errorMessage(error);
        setPaperDetails((items) => ({
          ...items,
          [paperId]: { ...(items[paperId] ?? current), initialLoading: false, refreshing: false, error: text },
        }));
        throw error;
      }
    });
  }, [getAccessToken, paperDetails, resetEditorDraftFromDetail]);

  const ensureAssignments = useCallback(async (force = false) => {
    if (!force && assignments.lastLoadedAt && isFresh(assignments)) return assignments.data;
    const hadData = assignments.lastLoadedAt > 0;
    setAssignments((current) => ({ ...current, initialLoading: !hadData, refreshing: hadData, error: '' }));
    return dedupe('assignments', async () => {
      try {
        const token = await getAccessToken();
        const items = await fetchAssignments(token);
        setAssignments({ data: items, initialLoading: false, refreshing: false, error: '', lastLoadedAt: now() });
        return items;
      } catch (error) {
        const text = errorMessage(error);
        setAssignments((current) => ({ ...current, initialLoading: false, refreshing: false, error: text }));
        throw error;
      }
    });
  }, [assignments, getAccessToken]);

  const ensureAssignmentOptions = useCallback(async (force = false) => {
    if (!force && assignmentOptions.lastLoadedAt && isFresh(assignmentOptions)) return assignmentOptions.data;
    const hadData = assignmentOptions.lastLoadedAt > 0;
    setAssignmentOptions((current) => ({ ...current, initialLoading: !hadData, refreshing: hadData, error: '' }));
    return dedupe('assignment-options', async () => {
      try {
        const token = await getAccessToken();
        const data = await fetchAssignmentOptions(token);
        setAssignmentOptions({ data, initialLoading: false, refreshing: false, error: '', lastLoadedAt: now() });
        setAssignmentForm((current) => ({
          ...current,
          paper_id: current.paper_id || data.papers.find((paper) => !paper.assignment)?.paper_id || data.papers[0]?.paper_id || '',
          annotator_id: current.annotator_id || data.annotators[0]?.id || '',
        }));
        return data;
      } catch (error) {
        const text = errorMessage(error);
        setAssignmentOptions((current) => ({ ...current, initialLoading: false, refreshing: false, error: text }));
        throw error;
      }
    });
  }, [assignmentOptions, getAccessToken]);

  const ensureAssignmentHistory = useCallback(async (paperId: string, force = false) => {
    if (!paperId) return null;
    const current = assignmentHistories[paperId] ?? makeResource<PaperAssignmentHistoryResponse | null>(null);
    if (!force && current.lastLoadedAt && isFresh(current)) return current.data;
    const hadData = current.lastLoadedAt > 0;
    setAssignmentHistories((items) => ({
      ...items,
      [paperId]: { ...(items[paperId] ?? current), initialLoading: !hadData, refreshing: hadData, error: '' },
    }));
    return dedupe(`assignment-history:${paperId}`, async () => {
      try {
        const token = await getAccessToken();
        const detail = await fetchPaperAssignmentHistory(token, paperId);
        setAssignmentHistories((items) => ({
          ...items,
          [paperId]: { data: detail, initialLoading: false, refreshing: false, error: '', lastLoadedAt: now() },
        }));
        return detail;
      } catch (error) {
        const text = errorMessage(error);
        setAssignmentHistories((items) => ({
          ...items,
          [paperId]: { ...(items[paperId] ?? current), initialLoading: false, refreshing: false, error: text },
        }));
        throw error;
      }
    });
  }, [assignmentHistories, getAccessToken]);

  const ensureReviewQueue = useCallback(async (status: SubmissionStatus, force = false) => {
    const resource = reviewQueues[status];
    if (!force && resource.lastLoadedAt && isFresh(resource)) return resource.data;
    const hadData = resource.lastLoadedAt > 0;
    setReviewQueues((items) => ({ ...items, [status]: { ...items[status], initialLoading: !hadData, refreshing: hadData, error: '' } }));
    return dedupe(`review-queue:${status}`, async () => {
      try {
        const token = await getAccessToken();
        const items = await fetchReviewSubmissions(token, status);
        setReviewQueues((current) => ({
          ...current,
          [status]: { data: items, initialLoading: false, refreshing: false, error: '', lastLoadedAt: now() },
        }));
        setSelectedSubmissionByStatus((current) => ({
          ...current,
          [status]: current[status] && items.some((item) => item.submission_id === current[status]) ? current[status] : items[0]?.submission_id ?? '',
        }));
        return items;
      } catch (error) {
        const text = errorMessage(error);
        setReviewQueues((current) => ({ ...current, [status]: { ...current[status], initialLoading: false, refreshing: false, error: text } }));
        throw error;
      }
    });
  }, [getAccessToken, reviewQueues]);

  const ensureReviewDetail = useCallback(async (submissionId: string, force = false) => {
    if (!submissionId) return null;
    const current = reviewDetails[submissionId] ?? makeResource<ReviewSubmissionDetail | null>(null);
    if (!force && current.lastLoadedAt && isFresh(current)) return current.data;
    const hadData = current.lastLoadedAt > 0;
    setReviewDetails((items) => ({
      ...items,
      [submissionId]: { ...(items[submissionId] ?? current), initialLoading: !hadData, refreshing: hadData, error: '' },
    }));
    return dedupe(`review-detail:${submissionId}`, async () => {
      try {
        const token = await getAccessToken();
        const detail = await fetchReviewSubmissionDetail(token, submissionId);
        setReviewDetails((items) => ({
          ...items,
          [submissionId]: { data: detail, initialLoading: false, refreshing: false, error: '', lastLoadedAt: now() },
        }));
        return detail;
      } catch (error) {
        const text = errorMessage(error);
        setReviewDetails((items) => ({
          ...items,
          [submissionId]: { ...(items[submissionId] ?? current), initialLoading: false, refreshing: false, error: text },
        }));
        throw error;
      }
    });
  }, [getAccessToken, reviewDetails]);

  const ensureAnnotatorRequests = useCallback(async (status: UserStatus, force = false) => {
    const resource = annotatorRequests[status];
    if (!force && resource.lastLoadedAt && isFresh(resource)) return resource.data;
    const hadData = resource.lastLoadedAt > 0;
    setAnnotatorRequests((items) => ({ ...items, [status]: { ...items[status], initialLoading: !hadData, refreshing: hadData, error: '' } }));
    return dedupe(`annotator-requests:${status}`, async () => {
      try {
        const token = await getAccessToken();
        const items = await fetchAnnotatorSignupRequests(token, status);
        setAnnotatorRequests((current) => ({ ...current, [status]: { data: items, initialLoading: false, refreshing: false, error: '', lastLoadedAt: now() } }));
        return items;
      } catch (error) {
        const text = errorMessage(error);
        setAnnotatorRequests((current) => ({ ...current, [status]: { ...current[status], initialLoading: false, refreshing: false, error: text } }));
        throw error;
      }
    });
  }, [annotatorRequests, getAccessToken]);

  const ensureReviewerRequests = useCallback(async (status: UserStatus, force = false) => {
    const resource = reviewerRequests[status];
    if (!force && resource.lastLoadedAt && isFresh(resource)) return resource.data;
    const hadData = resource.lastLoadedAt > 0;
    setReviewerRequests((items) => ({ ...items, [status]: { ...items[status], initialLoading: !hadData, refreshing: hadData, error: '' } }));
    return dedupe(`reviewer-requests:${status}`, async () => {
      try {
        const token = await getAccessToken();
        const items = await fetchReviewerSignupRequests(token, status);
        setReviewerRequests((current) => ({ ...current, [status]: { data: items, initialLoading: false, refreshing: false, error: '', lastLoadedAt: now() } }));
        return items;
      } catch (error) {
        const text = errorMessage(error);
        setReviewerRequests((current) => ({ ...current, [status]: { ...current[status], initialLoading: false, refreshing: false, error: text } }));
        throw error;
      }
    });
  }, [getAccessToken, reviewerRequests]);

  const ensureUsers = useCallback(async (force = false) => {
    if (!force && users.lastLoadedAt && isFresh(users)) return users.data;
    const hadData = users.lastLoadedAt > 0;
    setUsers((current) => ({ ...current, initialLoading: !hadData, refreshing: hadData, error: '' }));
    return dedupe('users', async () => {
      try {
        const token = await getAccessToken();
        const items = await fetchAdminUsers(token);
        setUsers({ data: items, initialLoading: false, refreshing: false, error: '', lastLoadedAt: now() });
        return items;
      } catch (error) {
        const text = errorMessage(error);
        setUsers((current) => ({ ...current, initialLoading: false, refreshing: false, error: text }));
        throw error;
      }
    });
  }, [getAccessToken, users]);

  const setSelectedSubmissionForStatus = useCallback((status: SubmissionStatus, submissionId: string) => {
    setSelectedSubmissionByStatus((current) => ({ ...current, [status]: submissionId }));
  }, []);

  const setRequestStatus = useCallback((role: keyof RequestStatusState, status: UserStatus) => {
    setRequestStatusState((current) => ({ ...current, [role]: status }));
  }, []);

  const refreshEditorAfterWorkflowChange = useCallback(async (paperId?: string) => {
    const targetPaperId = paperId || selectedPaperId;
    await Promise.all([
      ensureAssignments(true).catch(() => undefined),
      ensureAssignmentOptions(true).catch(() => undefined),
      ensurePapers(true).catch(() => undefined),
      targetPaperId ? ensurePaperDetail(targetPaperId, true).catch(() => undefined) : Promise.resolve(undefined),
      targetPaperId ? ensureAssignmentHistory(targetPaperId, true).catch(() => undefined) : Promise.resolve(undefined),
    ]);
  }, [ensureAssignmentHistory, ensureAssignmentOptions, ensureAssignments, ensurePaperDetail, ensurePapers, selectedPaperId]);

  const value = useMemo<WorkspaceDataContextValue>(() => ({
    papers,
    paperDetails,
    selectedPaperId,
    setSelectedPaperId,
    editorDrafts,
    setEditorDraft,
    resetEditorDraftFromDetail,
    assignments,
    assignmentOptions,
    assignmentForm,
    setAssignmentForm,
    selectedAssignmentHistoryPaperId,
    setSelectedAssignmentHistoryPaperId,
    assignmentHistories,
    ensureAssignmentHistory,
    exportPaperId,
    setExportPaperId,
    exportFormat,
    setExportFormat,
    reviewStatusFilter,
    setReviewStatusFilter,
    reviewQueues,
    reviewDetails,
    selectedSubmissionByStatus,
    setSelectedSubmissionForStatus,
    requestStatus,
    setRequestStatus,
    annotatorRequests,
    reviewerRequests,
    users,
    ensurePapers,
    ensurePaperDetail,
    ensureAssignments,
    ensureAssignmentOptions,
    ensureReviewQueue,
    ensureReviewDetail,
    ensureAnnotatorRequests,
    ensureReviewerRequests,
    ensureUsers,
    refreshEditorAfterWorkflowChange,
  }), [
    annotatorRequests,
    assignmentForm,
    assignmentHistories,
    assignmentOptions,
    assignments,
    editorDrafts,
    ensureAnnotatorRequests,
    ensureAssignmentHistory,
    ensureAssignmentOptions,
    ensureAssignments,
    ensurePaperDetail,
    ensurePapers,
    ensureReviewDetail,
    ensureReviewQueue,
    ensureReviewerRequests,
    ensureUsers,
    exportFormat,
    exportPaperId,
    paperDetails,
    papers,
    refreshEditorAfterWorkflowChange,
    requestStatus,
    resetEditorDraftFromDetail,
    reviewerRequests,
    reviewDetails,
    reviewQueues,
    reviewStatusFilter,
    selectedAssignmentHistoryPaperId,
    selectedPaperId,
    selectedSubmissionByStatus,
    setEditorDraft,
    setRequestStatus,
    setSelectedSubmissionForStatus,
    users,
  ]);

  return <WorkspaceDataContext.Provider value={value}>{children}</WorkspaceDataContext.Provider>;
}

export function useWorkspaceData() {
  const value = useContext(WorkspaceDataContext);
  if (!value) throw new Error('useWorkspaceData must be used inside WorkspaceDataProvider');
  return value;
}
