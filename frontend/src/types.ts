export type DatasetKey = 'raw';

export type DatasetInfo = {
  key: DatasetKey;
  label: string;
  path: string;
};

export type PaperAssignmentState = {
  assignment_id: string;
  status: AssignmentStatus;
  annotator_id: string | null;
  reviewer_id: string | null;
  latest_submission_id: string | null;
  latest_submission_status: SubmissionStatus | null;
  latest_submission_version: number | null;
  latest_review_comment: string | null;
};

export type PaperSummary = {
  paper_id: string;
  title: string;
  doi: string;
  has_edited_version: boolean;
  assignment: PaperAssignmentState | null;
};

export type SentenceRecord = {
  sentence_id: string;
  paper_id: string;
  sentence_index: number;
  text: string;
};

export type ParagraphRecord = {
  paragraph_id: string;
  paper_id: string;
  paragraph_index: number;
  text: string;
  sentence_ids: string[];
};

export type ParagraphCommentRecord = {
  paragraph_id: string;
  comment_text: string;
};

export type MentionRecord = {
  mention_id: string;
  sentence_id: string;
  paper_id: string;
  text: string;
  schema_type: string;
  ner_label: string;
  token_start: number | null;
  token_end: number | null;
};

export type RelationRecord = {
  relation_id: string;
  logical_relation_id: string;
  sentence_id: string;
  paper_id: string;
  paper_title: string;
  doi: string;
  subject_text: string;
  subject_type: string;
  predicate: string;
  object_text: string;
  object_type: string;
  confidence: number;
  accepted: boolean;
  evidence_text: string;
  relation_origin: string;
  inherited_from: string;
  support_sentence_ids: string;
  support_paragraph_id: string;
};

export type RevisionInfo = {
  submission_id: string;
  version: number;
  status: SubmissionStatus;
  parent_submission_id: string | null;
  parent_version: number | null;
  created_by_id: string | null;
  editor_role: string;
  created_at: string | null;
};

export type ModifiedRelationRecord = {
  before: RelationRecord;
  after: RelationRecord;
};

export type ParagraphCommentChange = {
  paragraph_id: string;
  before_text: string;
  after_text: string;
};

export type RevisionChanges = {
  parent_submission_id: string;
  parent_version: number;
  added: RelationRecord[];
  removed: RelationRecord[];
  modified: ModifiedRelationRecord[];
  unchanged_count: number;
  paragraph_comments: ParagraphCommentChange[];
};

export type PaperDetailResponse = {
  paper: PaperSummary;
  sentences: SentenceRecord[];
  paragraphs: ParagraphRecord[];
  mentions: MentionRecord[];
  relations: RelationRecord[];
  paragraph_comments: ParagraphCommentRecord[];
  source: string;
  warnings: string[];
  assignment: PaperAssignmentState | null;
  revision: RevisionInfo | null;
  changes: RevisionChanges | null;
};


export type UserRole = 'annotator' | 'reviewer' | 'admin';
export type SignupRole = 'annotator' | 'reviewer';
export type UserStatus = 'pending' | 'approved' | 'rejected';

export type UserRead = {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  designation: string;
  institute: string;
  state: string;
  country: string;
  status: UserStatus;
  is_active: boolean;
  email_verified: boolean;
  created_at: string;
  updated_at: string;
  approved_at: string | null;
  approved_by_id: string | null;
  rejection_reason: string | null;
  email_verified_at: string | null;
};

export type RegisterProfilePayload = {
  full_name: string;
  role: SignupRole;
  designation: string;
  institute: string;
  state: string;
  country: string;
};


export type AssignmentStatus = 'assigned' | 'in_progress' | 'submitted' | 'review_in_progress' | 'returned' | 'approved' | 'cancelled';
export type SubmissionStatus = 'draft' | 'submitted' | 'review_draft' | 'returned' | 'approved' | 'superseded';

export type AssignmentRead = {
  id: string;
  paper_id: string;
  paper_title: string;
  doi: string;
  annotator_id: string | null;
  annotator_name: string;
  annotator_email: string;
  reviewer_id: string | null;
  reviewer_name: string;
  reviewer_email: string;
  status: AssignmentStatus;
  assigned_at: string | null;
  started_at: string | null;
  submitted_at: string | null;
  completed_at: string | null;
  due_at: string | null;
  latest_submission_id: string | null;
  latest_submission_status: SubmissionStatus | null;
  latest_submission_version: number | null;
  latest_review_comment: string | null;
};

export type AssignmentCreatePayload = {
  paper_id: string;
  annotator_id: string;
  due_at?: string | null;
};

export type AssignmentOptionsResponse = {
  papers: PaperSummary[];
  annotators: UserRead[];
};

export type PaperAssignmentHistoryResponse = {
  paper: PaperSummary;
  assignments: AssignmentRead[];
};

export type SubmitResponse = {
  assignment: AssignmentRead;
  submission_id: string;
};

export type ReviewSubmissionSummary = {
  submission_id: string;
  assignment: AssignmentRead;
  version: number;
  status: SubmissionStatus;
  created_at: string | null;
  submitted_at: string | null;
};

export type ReviewSubmissionDetail = {
  submission: ReviewSubmissionSummary;
  paper: PaperDetailResponse;
  decisions: Array<{ decision: string | null; comment: string | null; created_at: string | null }>;
};

export type ExportFormat = 'csv' | 'json';
