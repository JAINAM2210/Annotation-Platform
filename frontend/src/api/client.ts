import type {
  AssignmentCreatePayload,
  AssignmentOptionsResponse,
  AssignmentRead,
  DatasetInfo,
  ExportFormat,
  PaperAssignmentHistoryResponse,
  PaperDetailResponse,
  ParagraphCommentRecord,
  PaperSummary,
  RegisterProfilePayload,
  RelationRecord,
  ReviewSubmissionDetail,
  ReviewSubmissionSummary,
  SubmissionStatus,
  SubmitResponse,
  UserRead,
  UserRole,
  UserStatus,
} from '../types';

const API_BASE = import.meta.env.VITE_API_BASE || '/api';
const API_TIMEOUT_MS = 20000;

type ErrorPayload = {
  detail?: unknown;
};

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}


async function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), API_TIMEOUT_MS);
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError(408, 'Request timed out. Check that the backend is running and reachable.');
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

function formatDetail(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === 'object' && 'msg' in item) return String((item as { msg: unknown }).msg);
        return JSON.stringify(item);
      })
      .join('; ');
  }
  if (detail && typeof detail === 'object') {
    const structured = detail as { message?: unknown; hint?: unknown; code?: unknown; paper_id?: unknown };
    const message = typeof structured.message === 'string' ? structured.message : '';
    const hint = typeof structured.hint === 'string' ? structured.hint : '';
    const code = typeof structured.code === 'string' ? structured.code : '';
    const prefix = code ? `${code}: ` : '';
    if (message && hint) return `${prefix}${message} ${hint}`;
    if (message) return `${prefix}${message}`;
    return JSON.stringify(detail);
  }
  return 'Request failed';
}

async function parseError(response: Response): Promise<ApiError> {
  let payload: ErrorPayload = {};
  try {
    payload = await response.json();
  } catch {
    payload = {};
  }
  return new ApiError(response.status, formatDetail(payload.detail));
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) throw await parseError(response);
  return response.json() as Promise<T>;
}

function authHeader(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` };
}

export async function registerProfile(token: string, payload: RegisterProfilePayload): Promise<UserRead> {
  return readJson<UserRead>(await apiFetch(`${API_BASE}/auth/register-profile`, {
    method: 'POST',
    headers: { ...authHeader(token), 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }));
}

export async function fetchMe(token: string): Promise<UserRead> {
  return readJson<UserRead>(await apiFetch(`${API_BASE}/auth/me`, { headers: authHeader(token) }));
}

export async function fetchReviewerSignupRequests(token: string, status: UserStatus = 'pending'): Promise<UserRead[]> {
  return readJson<UserRead[]>(await apiFetch(`${API_BASE}/admin/signup-requests?status=${status}&role=reviewer`, { headers: authHeader(token) }));
}

export async function approveReviewerSignupRequest(token: string, userId: string): Promise<UserRead> {
  return readJson<UserRead>(await apiFetch(`${API_BASE}/admin/signup-requests/${userId}/approve`, { method: 'POST', headers: authHeader(token) }));
}

export async function rejectReviewerSignupRequest(token: string, userId: string, reason: string): Promise<UserRead> {
  return readJson<UserRead>(await apiFetch(`${API_BASE}/admin/signup-requests/${userId}/reject`, {
    method: 'POST',
    headers: { ...authHeader(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason: reason.trim() || null }),
  }));
}

export async function reopenReviewerSignupRequest(token: string, userId: string): Promise<UserRead> {
  return readJson<UserRead>(await apiFetch(`${API_BASE}/admin/signup-requests/${userId}/reopen`, { method: 'POST', headers: authHeader(token) }));
}

export async function fetchAnnotatorSignupRequests(token: string, status: UserStatus = 'pending'): Promise<UserRead[]> {
  return readJson<UserRead[]>(await apiFetch(`${API_BASE}/reviewer/signup-requests?status=${status}`, { headers: authHeader(token) }));
}

export async function approveAnnotatorSignupRequest(token: string, userId: string): Promise<UserRead> {
  return readJson<UserRead>(await apiFetch(`${API_BASE}/reviewer/signup-requests/${userId}/approve`, { method: 'POST', headers: authHeader(token) }));
}

export async function rejectAnnotatorSignupRequest(token: string, userId: string, reason: string): Promise<UserRead> {
  return readJson<UserRead>(await apiFetch(`${API_BASE}/reviewer/signup-requests/${userId}/reject`, {
    method: 'POST',
    headers: { ...authHeader(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason: reason.trim() || null }),
  }));
}

export async function reopenAnnotatorSignupRequest(token: string, userId: string): Promise<UserRead> {
  return readJson<UserRead>(await apiFetch(`${API_BASE}/reviewer/signup-requests/${userId}/reopen`, { method: 'POST', headers: authHeader(token) }));
}

export async function fetchAdminUsers(token: string): Promise<UserRead[]> {
  return readJson<UserRead[]>(await apiFetch(`${API_BASE}/admin/users`, { headers: authHeader(token) }));
}

export async function deleteAdminUser(token: string, userId: string): Promise<void> {
  const response = await apiFetch(`${API_BASE}/admin/users/${userId}`, { method: 'DELETE', headers: authHeader(token) });
  if (!response.ok) throw await parseError(response);
}

export async function reactivateAdminUser(token: string, userId: string): Promise<UserRead> {
  return readJson<UserRead>(await apiFetch(`${API_BASE}/admin/users/${userId}/reactivate`, { method: 'POST', headers: authHeader(token) }));
}


export async function fetchAssignments(token: string): Promise<AssignmentRead[]> {
  return readJson<AssignmentRead[]>(await apiFetch(`${API_BASE}/assignments`, { headers: authHeader(token) }));
}

export async function fetchAssignmentOptions(token: string): Promise<AssignmentOptionsResponse> {
  return readJson<AssignmentOptionsResponse>(await apiFetch(`${API_BASE}/assignments/options`, { headers: authHeader(token) }));
}

export async function fetchPaperAssignmentHistory(token: string, paperId: string): Promise<PaperAssignmentHistoryResponse> {
  return readJson<PaperAssignmentHistoryResponse>(await apiFetch(`${API_BASE}/assignments/papers/${encodeURIComponent(paperId)}/history`, { headers: authHeader(token) }));
}

export async function createAssignment(token: string, payload: AssignmentCreatePayload): Promise<AssignmentRead> {
  return readJson<AssignmentRead>(await apiFetch(`${API_BASE}/assignments`, {
    method: 'POST',
    headers: { ...authHeader(token), 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }));
}

export async function cancelAssignment(token: string, assignmentId: string): Promise<AssignmentRead> {
  return readJson<AssignmentRead>(await apiFetch(`${API_BASE}/assignments/${assignmentId}/cancel`, { method: 'POST', headers: authHeader(token) }));
}

export async function submitAssignment(token: string, assignmentId: string): Promise<SubmitResponse> {
  return readJson<SubmitResponse>(await apiFetch(`${API_BASE}/assignments/${assignmentId}/submit`, { method: 'POST', headers: authHeader(token) }));
}

export async function fetchReviewSubmissions(token: string, status: SubmissionStatus = 'submitted'): Promise<ReviewSubmissionSummary[]> {
  return readJson<ReviewSubmissionSummary[]>(await apiFetch(`${API_BASE}/review/submissions?status=${status}`, { headers: authHeader(token) }));
}

export async function fetchReviewSubmissionDetail(token: string, submissionId: string): Promise<ReviewSubmissionDetail> {
  return readJson<ReviewSubmissionDetail>(await apiFetch(`${API_BASE}/review/submissions/${submissionId}`, { headers: authHeader(token) }));
}

export async function returnReviewSubmission(token: string, submissionId: string, comment: string): Promise<ReviewSubmissionSummary> {
  return readJson<ReviewSubmissionSummary>(await apiFetch(`${API_BASE}/review/submissions/${submissionId}/return`, {
    method: 'POST',
    headers: { ...authHeader(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({ comment: comment.trim() || null }),
  }));
}

export async function approveReviewSubmission(token: string, submissionId: string, comment: string): Promise<ReviewSubmissionSummary> {
  return readJson<ReviewSubmissionSummary>(await apiFetch(`${API_BASE}/review/submissions/${submissionId}/approve`, {
    method: 'POST',
    headers: { ...authHeader(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({ comment: comment.trim() || null }),
  }));
}

export async function downloadFinalAnnotations(token: string, paperId: string, format: ExportFormat): Promise<{ blob: Blob; filename: string }> {
  const response = await apiFetch(`${API_BASE}/exports/papers/${paperId}?format=${format}`, { headers: authHeader(token) });
  if (!response.ok) throw await parseError(response);
  const disposition = response.headers.get('Content-Disposition') || '';
  const match = disposition.match(/filename=\"?([^\";]+)\"?/i);
  return { blob: await response.blob(), filename: match?.[1] || `${paperId}_final_annotations.${format}` };
}

export async function fetchDatasets(token: string): Promise<DatasetInfo[]> {
  return readJson(await apiFetch(`${API_BASE}/datasets`, { headers: authHeader(token) }));
}

export async function fetchSchemaPredicates(token: string): Promise<string[]> {
  return readJson(await apiFetch(`${API_BASE}/schema/predicates`, { headers: authHeader(token) }));
}

export async function fetchDirectSchemaPredicates(token: string): Promise<string[]> {
  return readJson(await apiFetch(`${API_BASE}/schema/predicates/direct`, { headers: authHeader(token) }));
}

export async function addDirectSchemaPredicate(token: string, predicate: string): Promise<string[]> {
  return readJson(await apiFetch(`${API_BASE}/schema/predicates/direct`, {
    method: 'POST',
    headers: { ...authHeader(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({ predicate }),
  }));
}

export async function fetchPapers(token: string): Promise<PaperSummary[]> {
  return readJson(await apiFetch(`${API_BASE}/papers`, { headers: authHeader(token) }));
}

export async function fetchPaper(token: string, paperId: string): Promise<PaperDetailResponse> {
  return readJson(await apiFetch(`${API_BASE}/paper/${paperId}`, { headers: authHeader(token) }));
}

export async function savePaperRelations(
  token: string,
  paperId: string,
  relations: RelationRecord[],
  paragraphComments: ParagraphCommentRecord[],
  editorMode: 'sentence' | 'paragraph',
  baseSubmissionId?: string | null
) {
  return readJson<{ saved_to: string }>(await apiFetch(`${API_BASE}/paper/${paperId}/relations/save`, {
    method: 'POST',
    headers: { ...authHeader(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({
      dataset: 'raw',
      paper_id: paperId,
      relations,
      paragraph_comments: paragraphComments,
      editor_mode: editorMode,
      base_submission_id: baseSubmissionId ?? null,
    }),
  }));
}

export async function saveParagraphComments(
  token: string,
  paperId: string,
  paragraphComments: ParagraphCommentRecord[]
) {
  return readJson<{ saved_to: string }>(await apiFetch(`${API_BASE}/paper/${paperId}/paragraph-comments/save`, {
    method: 'POST',
    headers: { ...authHeader(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({ paper_id: paperId, paragraph_comments: paragraphComments }),
  }));
}

export function canManageAnnotators(user: UserRead | null): boolean {
  return Boolean(user?.is_active && user.status === 'approved' && (user.role === 'reviewer' || user.role === 'admin'));
}

export function canManageReviewers(user: UserRead | null): boolean {
  return Boolean(user?.is_active && user.status === 'approved' && user.role === 'admin');
}

export function roleLabel(role: UserRole): string {
  return role;
}
