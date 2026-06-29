# Annotation Platform Manual Testing Audit

Project root: `/home/student/Kalp/SELC_Projects/KG_manmeet/relation-editor/Annotation_Platform`

Audit basis: static inspection of the actual React/Vite frontend and FastAPI backend code. No functionality below is assumed. Items marked "Not implemented" are not present in the inspected code.

Key roles:

| Code role | Product role | Backend enum |
|---|---|---|
| ANN | Annotator | `annotator` |
| REV | Reviewer | `reviewer` |
| ADM | Super Admin | `admin` |

## Part 1: System Inventory

### Frontend Routes, Pages, and Access

| Name | Route | Location | Purpose | Roles allowed |
|---|---|---|---|---|
| Root redirect | `/` | `frontend/src/App.tsx`, `frontend/src/routes/RouteGuards.tsx` | Routes users to sign in, complete profile, verify email, account status, or editor based on session/profile state. | Public, session-aware |
| Sign in | `/signin` | `frontend/src/pages/auth/SignInPage.tsx` | Firebase email/password sign-in and platform session sync. | Public only |
| Request access | `/request-access` | `frontend/src/pages/auth/RequestAccessPage.tsx` | Two-step Firebase signup plus platform profile registration for annotator/reviewer. | Public only |
| Forgot password | `/forgot-password` | `frontend/src/pages/auth/ForgotPasswordPage.tsx` | Sends Firebase password reset email. | Public only |
| Complete profile | `/complete-profile` | `frontend/src/pages/auth/CompleteProfilePage.tsx` | Registers backend profile for a signed-in Firebase user with no platform profile. | Firebase session, missing profile |
| Verify email | `/verify-email` | `frontend/src/pages/auth/VerifyEmailPage.tsx` | Shows email verification status, resend email, refresh status, sign out. | Firebase session |
| Account status | `/account-status` | `frontend/src/pages/auth/AccountStatusPage.tsx` | Shows pending/rejected/inactive approval state. | Firebase session with profile not approved/active |
| Workspace layout | `/app/*` | `frontend/src/pages/workspace/WorkspaceLayout.tsx` | Authenticated shell, nav, theme, user status, sign out. | Approved, active, verified users |
| Editor | `/app/editor` | `frontend/src/pages/workspace/EditorPage.tsx` | Paper selection, paragraph editor, relation add/delete, draft save, annotator submit. | ANN, REV, ADM with backend paper visibility rules |
| Assignments | `/app/assignments` | `frontend/src/pages/workspace/AssignmentsPage.tsx` | View assignments; REV/ADM can create/cancel and inspect history. | ANN view own; REV own; ADM all |
| Requests | `/app/requests` | `frontend/src/pages/workspace/RequestsPage.tsx` | Approve/reject annotator requests; admin also manages reviewer requests. | REV, ADM |
| Review | `/app/review` | `frontend/src/pages/workspace/ReviewPage.tsx` | Inspect submitted/returned/approved submissions and return/approve submitted work. | REV, ADM |
| Exports | `/app/exports` | `frontend/src/pages/workspace/ExportsPage.tsx` | Download final annotations in CSV/JSON. | ANN approved own papers only; REV/ADM any final paper |
| Users | `/app/users` | `frontend/src/pages/workspace/UsersPage.tsx` | Admin user list, deactivate, reactivate. | ADM only |
| Catch-all redirect | `*` | `frontend/src/App.tsx` | Redirects unknown route to `/`. | Public, session-aware |

### Navigation Items

| Nav item | Location | Visible to | Destination | Notes |
|---|---|---|---|---|
| Editor | `WorkspaceLayout.tsx` | ANN, REV, ADM | `/app/editor` | Backend visibility still enforced. |
| Assignments | `WorkspaceLayout.tsx` | ANN, REV, ADM | `/app/assignments` | Create controls shown only to REV/ADM. |
| Requests | `WorkspaceLayout.tsx` | REV, ADM | `/app/requests` | Guarded by `RequireRequestsAccess`. |
| Review | `WorkspaceLayout.tsx` | REV, ADM | `/app/review` | Guarded by `RequireRequestsAccess`. |
| Exports | `WorkspaceLayout.tsx` | ANN, REV, ADM | `/app/exports` | Backend export authorization differs by role. |
| Users | `WorkspaceLayout.tsx` | ADM | `/app/users` | Guarded by `RequireAdminAccess`. |

### Forms, Modals, Tables, and Controls

| Item | Location | Purpose | Roles allowed |
|---|---|---|---|
| Sign-in form | `SignInPage.tsx` | Email/password login. | Public |
| Request access account step | `RequestAccessPage.tsx` | Email/password/confirm password. | Public |
| Request access profile step | `RequestAccessPage.tsx` | Full name, role, designation, institute, country, state. | Public |
| Forgot password form | `ForgotPasswordPage.tsx` | Email for reset link. | Public |
| Complete profile form | `CompleteProfilePage.tsx` | Registers backend profile after Firebase-only session. | Firebase session |
| Verify email actions | `VerifyEmailPage.tsx` | Resend, refresh, sign out. | Firebase session |
| Account status actions | `AccountStatusPage.tsx` | Refresh, sign out. | Firebase session |
| Paper picker | `EditorPage.tsx` | Select visible paper. | ANN assigned, REV owned, ADM all |
| Sidebar resizer | `EditorPage.tsx` | Drag/keyboard resize editor sidebar, persists to localStorage. | ANN, REV, ADM |
| Paragraph relation composer | `ParagraphEditor.tsx` | Select two highlighted entities, enter predicate, add relation. | ANN/ADM editable assignments; REV read-only |
| Free-form relation composer | `ParagraphEditor.tsx` | Add custom head-predicate-tail relation for paragraph. | ANN/ADM editable assignments; REV read-only |
| Relation delete button | `RelationPill.tsx` | Remove relation from draft. | ANN/ADM editable assignments; REV read-only |
| Save draft button | `EditorPage.tsx` | Persist current relation set as draft submission. | ANN/ADM if assigned/editable; backend blocks REV direct edit |
| Submit button | `EditorPage.tsx` | Submit latest saved draft for review. | Assigned ANN only |
| Create assignment form | `AssignmentsPage.tsx` | Paper, annotator, due date. | REV, ADM |
| Assignment history selector/table | `AssignmentsPage.tsx` | Inspect paper assignment trail. | REV, ADM |
| Assignments table | `AssignmentsPage.tsx` | List assignments and cancel active ones. | ANN own; REV own; ADM all |
| Request status tabs | `RequestsPage.tsx` | Pending/approved/rejected queues. | REV, ADM |
| Request approval cards | `RequestsPage.tsx` | Approve/reject users with optional reason. | REV annotators; ADM annotators and reviewers |
| Review status tabs | `ReviewPage.tsx` | Submitted/returned/approved queues. | REV, ADM |
| Review detail table | `ReviewPage.tsx` | Relation set under review. | REV owner; ADM all |
| Reviewer comment form | `ReviewPage.tsx` | Return/approve submitted work. | REV owner; ADM all |
| Export form | `ExportsPage.tsx` | Paper and format selector, download. | ANN approved own; REV/ADM any final |
| Users table | `UsersPage.tsx` | User metadata, status, active state. | ADM only |
| Deactivate/reactivate confirmation | `UsersPage.tsx` | Browser `window.confirm` before state change. | ADM only |

### Backend Services and Middleware

| Name | Location | Purpose | Roles/access |
|---|---|---|---|
| FastAPI app | `backend/app/main.py` | App, CORS, router registration, editor APIs. | Mixed |
| Auth dependencies | `backend/app/dependencies.py` | Firebase bearer auth, profile sync, approved/admin/reviewer guards. | All protected APIs |
| Firebase auth wrapper | `backend/app/firebase_auth.py` | Verify ID token, disable/enable Firebase users. | Backend only |
| Auth/profile service | `backend/app/auth_services.py` | Register/sync profile, bootstrap admin, deactivate/reactivate. | Backend only |
| DB setup | `backend/app/database.py` | SQLAlchemy engine/session/create_all and user profile column migration. | Backend only |
| Editor DB service | `backend/app/services/db_editor_service.py` | Papers, paper detail, schema predicates, draft save. | Protected APIs |
| Workflow service | `backend/app/services/workflow_service.py` | Assignments, submissions, reviews, final copy, export, audit events. | Protected APIs |
| Legacy CSV editor service | `backend/app/services/editor_service.py`, `data_loader.py` | CSV-backed older editor implementation. Not imported by live routes. | Not externally reachable in inspected routes |
| Data error wrapper | `backend/app/data_errors.py` | Structured data-service error payload. | Backend only |

### Database Models

| Model/table | Location | Purpose | Main actions |
|---|---|---|---|
| `user_profiles` | `backend/app/models.py` | Platform profile, role, status, active, email verified. | Register, approve, reject, deactivate, reactivate, sync |
| `papers` | `models.py` | Paper metadata and source text paths/content. | Read, assignment target |
| `sentences` | `models.py` | Sentence text and external sentence keys. | Read, relation support |
| `paragraphs` | `models.py` | Paragraph text and external paragraph keys. | Read, relation support |
| `paragraph_sentences` | `models.py` | Sentence membership in paragraph. | Read/fallback inference in editor |
| `entity_mentions` | `models.py` | Typed entity mentions linked to sentences. | Read, manual relation source |
| `relation_predicates` | `models.py` | Direct/custom predicates. | Read, add custom predicate |
| `suggestion_sets` | `models.py` | Imported suggestion batches per paper. | Read latest suggestions |
| `suggested_relations` | `models.py` | Initial relation suggestions. | Read, mapped into annotation submission relations |
| `suggested_relation_support_sentences` | `models.py` | Suggested relation support sentence links. | Read |
| `annotation_assignments` | `models.py` | Paper assignment to annotator/reviewer and workflow status. | Create, cancel, status transitions |
| `annotation_submissions` | `models.py` | Versioned draft/submitted/returned/approved submissions. | Save draft, submit, return, approve |
| `annotation_submission_relations` | `models.py` | Relations stored inside a submission. | Insert on draft save |
| `annotation_relation_support_sentences` | `models.py` | Support sentence links for submission relation rows. | Insert/delete by cascade |
| `review_decisions` | `models.py` | Reviewer return/approval decisions and comments. | Insert on return/approve |
| `final_annotations` | `models.py` | Approved final relation rows per paper. | Replace on approval, read export |
| `final_annotation_support_sentences` | `models.py` | Support sentence links for final rows. | Replace on approval |
| `export_jobs` | `models.py` | Records completed direct export requests. | Insert on export |
| `audit_events` | `models.py` | Best-effort workflow audit log. | Insert on assignment/submission/export actions |

### Authentication and Authorization Mechanisms

| Mechanism | Location | Behavior | Test notes |
|---|---|---|---|
| Firebase email/password auth | `frontend/src/firebase.ts`, auth pages | Uses Firebase web SDK. | Login/signup/reset/verify are Firebase-dependent. |
| Browser session persistence | `frontend/src/firebase.ts` | Uses `browserSessionPersistence`. | Session survives refresh in same tab/session, not long-term local persistence. |
| Backend bearer token | `backend/app/dependencies.py` | `Authorization: Bearer <firebase_id_token>` required by all protected APIs. | Missing/malformed/expired token should return 401. |
| Firebase token verification | `backend/app/firebase_auth.py` | Uses Firebase Admin `verify_id_token`. | Bad config returns 503, invalid token returns 401. |
| Platform profile sync | `auth_services.py`, `dependencies.py` | Syncs Firebase UID/email/verification into `user_profiles`. | Missing profile returns 404 on `/auth/me`. |
| Approval gate | `require_approved_user` | Requires active user, verified email, approved status. | Pending/rejected/unverified blocked with 403; inactive with 401. |
| Admin gate | `require_admin` | Requires role `admin`. | REV/ANN receive 403. |
| Reviewer/admin gate | `require_reviewer_or_admin` | Requires role `reviewer` or `admin`. | ANN receives 403. |
| Ownership checks | `workflow_service.py` | Reviewer must own assignment/submission unless admin; annotator must own assignment. | Direct ID access must be tested for IDOR. |
| Paper visibility | `db_editor_service.py` with `workflow_service.visible_paper_uuids` | Non-admin users see assigned/owned papers only. | Direct `/paper/{paper_id}` and `/papers` must be tested. |

## Part 2: API Audit

Common protected API errors unless noted: `401` missing/invalid token or inactive user; `403` unverified, unapproved, insufficient role, or ownership failure; `404` missing profile/entity; `422` Pydantic validation; `503` Firebase/database/configuration failure.

| Method | Endpoint | Purpose | Required role | Auth | Request params/body | Response schema | Status codes | Tables affected/read |
|---|---|---|---|---|---|---|---|---|
| GET | `/health` | Health check. | Public | No | None | `{status:string}` | 200 | None |
| POST | `/auth/register-profile` | Create/update platform profile for Firebase user. Admin public registration rejected. | Firebase user, no approval required | Yes | Body `RegisterProfileRequest`: `full_name`, `role=annotator|reviewer`, optional metadata | `UserRead` | 200, 400, 401, 409, 422, 503 | Writes `user_profiles` |
| GET | `/auth/me` | Return synced platform profile. | Registered Firebase user | Yes | None | `UserRead` | 200, 401, 404, 409, 503 | Reads/writes `user_profiles` sync fields |
| GET | `/admin/signup-requests?status=&role=reviewer` | List verified active reviewer requests by status. | ADM | Yes | Query `status`, `role=reviewer` only | `UserRead[]` | 200, 400, 401, 403, 422 | Reads `user_profiles` |
| POST | `/admin/signup-requests/{user_id}/approve` | Approve pending reviewer. | ADM | Yes | Path `user_id` | `UserRead` | 200, 400, 401, 403, 404 | Updates `user_profiles` |
| POST | `/admin/signup-requests/{user_id}/reject` | Reject pending reviewer. | ADM | Yes | Path `user_id`; body `RejectRequest.reason` | `UserRead` | 200, 400, 401, 403, 404, 422 | Updates `user_profiles` |
| GET | `/admin/users` | List all platform users. | ADM | Yes | None | `UserRead[]` | 200, 401, 403 | Reads `user_profiles` |
| DELETE | `/admin/users/{user_id}` | Deactivate user and disable Firebase account. | ADM | Yes | Path `user_id` | Empty | 204, 400, 401, 403, 404, 503 | Updates `user_profiles`, Firebase user |
| POST | `/admin/users/{user_id}/reactivate` | Reactivate inactive user and enable Firebase account. | ADM | Yes | Path `user_id` | `UserRead` | 200, 400, 401, 403, 404, 503 | Updates `user_profiles`, Firebase user |
| GET | `/reviewer/signup-requests?status=` | List verified active annotator requests by status. | REV, ADM | Yes | Query `status` | `UserRead[]` | 200, 401, 403, 422 | Reads `user_profiles` |
| POST | `/reviewer/signup-requests/{user_id}/approve` | Approve pending annotator. | REV, ADM | Yes | Path `user_id` | `UserRead` | 200, 400, 401, 403, 404 | Updates `user_profiles` |
| POST | `/reviewer/signup-requests/{user_id}/reject` | Reject pending annotator. | REV, ADM | Yes | Path `user_id`; body `RejectRequest.reason` | `UserRead` | 200, 400, 401, 403, 404, 422 | Updates `user_profiles` |
| GET | `/reviewer/users` | List all users. | REV, ADM | Yes | None | `UserRead[]` | 200, 401, 403 | Reads `user_profiles`. Note: no frontend client call found. |
| GET | `/assignments` | List assignments visible to current user. | ANN, REV, ADM approved | Yes | None | `AssignmentRead[]` | 200, 401, 403 | Reads `annotation_assignments`, `papers`, `user_profiles`, `annotation_submissions`, `review_decisions` |
| GET | `/assignments/options` | Papers and approved annotators for creating assignment. | REV, ADM | Yes | None | `AssignmentOptionsResponse` | 200, 401, 403 | Reads `papers`, `annotation_assignments`, `annotation_submissions`, `user_profiles` |
| GET | `/assignments/papers/{paper_id}/history` | Assignment trail for paper. | REV, ADM | Yes | Path external `paper_id` | `PaperAssignmentHistoryResponse` | 200, 401, 403, 404 | Reads `papers`, `annotation_assignments`, `user_profiles`, `annotation_submissions` |
| POST | `/assignments` | Create assignment for approved active verified annotator. | REV, ADM | Yes | Body `AssignmentCreateRequest`: `paper_id`, `annotator_id`, optional `due_at` | `AssignmentRead` | 200, 400, 401, 403, 404, 422, 503 | Inserts `annotation_assignments`, `audit_events`; reads `papers`, `user_profiles` |
| POST | `/assignments/{assignment_id}/cancel` | Cancel non-approved assignment. | Owning REV or ADM | Yes | Path `assignment_id` | `AssignmentRead` | 200, 400, 401, 403, 404, 503 | Updates `annotation_assignments`, inserts `audit_events` |
| POST | `/assignments/{assignment_id}/submit` | Submit latest saved draft. | Assigned ANN | Yes | Path `assignment_id` | `SubmitResponse` | 200, 400, 401, 403, 404, 503 | Updates `annotation_submissions`, `annotation_assignments`, inserts `audit_events` |
| GET | `/review/submissions?status=` | List review submissions by status. | REV, ADM | Yes | Query `status=submitted|returned|approved` | `ReviewSubmissionSummary[]` | 200, 400, 401, 403 | Reads `annotation_submissions`, `annotation_assignments`, `papers`, `user_profiles` |
| GET | `/review/submissions/{submission_id}` | Submission detail with relations and decisions. | Owning REV or ADM | Yes | Path `submission_id` | `ReviewSubmissionDetail` | 200, 401, 403, 404, 503 | Reads submissions, assignments, paper detail tables, `review_decisions` |
| POST | `/review/submissions/{submission_id}/return` | Return submitted work with optional comment. | Owning REV or ADM | Yes | Body `ReviewDecisionRequest.comment` | `ReviewSubmissionSummary` | 200, 400, 401, 403, 404, 422, 503 | Inserts `review_decisions`, updates `annotation_submissions`, `annotation_assignments`, inserts `audit_events` |
| POST | `/review/submissions/{submission_id}/approve` | Approve submitted work and replace final annotations. | Owning REV or ADM | Yes | Body `ReviewDecisionRequest.comment` | `ReviewSubmissionSummary` | 200, 400, 401, 403, 404, 422, 503 | Deletes/inserts `final_annotations`, `final_annotation_support_sentences`; inserts `review_decisions`, updates submission/assignment, inserts `audit_events` |
| GET | `/exports/papers/{paper_id}?format=csv|json` | Download approved final annotations. | ANN for approved own paper; REV, ADM any | Yes | Path `paper_id`; query `format` | File response | 200, 400, 401, 403, 404 | Reads `final_annotations`, support/paper tables; inserts `export_jobs`, `audit_events` |
| GET | `/datasets` | List editor datasets. | ANN, REV, ADM approved | Yes | None | `DatasetInfo[]` | 200, 401, 403 | No DB write |
| GET | `/schema/predicates` | List all predicates including suggested relation predicates. | ANN, REV, ADM approved | Yes | None | `string[]` | 200, 401, 403, 503 | Reads `relation_predicates`, `suggested_relations` |
| GET | `/schema/predicates/direct` | List direct/custom predicates only. | ANN, REV, ADM approved | Yes | None | `string[]` | 200, 401, 403, 503 | Reads `relation_predicates` |
| POST | `/schema/predicates/direct` | Add custom predicate if not present. | ANN, REV, ADM approved | Yes | Body `CustomPredicatePayload.predicate` | `string[]` | 200, 401, 403, 422, 503 | Inserts `relation_predicates` |
| GET | `/papers?dataset=raw` | List visible papers. | ANN, REV, ADM approved | Yes | Optional query `dataset`, ignored | `PaperSummary[]` | 200, 401, 403, 503 | Reads `papers`, assignments/submissions |
| GET | `/paper/{paper_id}?dataset=raw` | Load visible paper detail. | ANN assigned; REV owned; ADM all | Yes | Path `paper_id`; optional query `dataset`, ignored | `PaperDetailResponse` | 200, 401, 403, 404, 503 | Reads paper, sentence, paragraph, mention, suggestion/submission tables |
| POST | `/paper/{paper_id}/relations/save` | Save current relation set as new draft submission. | Editable assignment owner; backend blocks REV direct edit | Yes | Body `PaperEditorPayload`: `dataset`, `paper_id`, `editor_mode`, `relations[]` | `{saved_to:string}` | 200, 400, 401, 403, 404, 422, 503 | Inserts `annotation_submissions`, `annotation_submission_relations`, `annotation_relation_support_sentences`; updates `annotation_assignments` |
| POST | `/paper/{paper_id}/relations/add` | Echoes a relation payload; not persisted. | ANN, REV, ADM approved | Yes | Body `AddRelationPayload` | `RelationRecord` | 200, 400, 401, 403, 422 | No DB write. Note: no frontend client call found. |

## Part 3: Role-Based Testing

### Annotator Test Cases

| Test Case ID | Feature | Preconditions | Test steps | Expected result | Priority |
|---|---|---|---|---|---|
| RB-ANN-001 | Login redirect | ANN approved, verified, active. | Sign in with valid credentials. | User lands on `/app/editor`; nav shows Editor, Assignments, Exports only. | High |
| RB-ANN-002 | Empty editor state | ANN has no assignments. | Open `/app/editor`. | Empty state says no papers assigned; paper picker disabled; no save/submit possible. | High |
| RB-ANN-003 | Paper visibility | ANN has one assigned paper and another unassigned paper exists. | Open Editor paper picker. | Only assigned paper appears. | High |
| RB-ANN-004 | Direct paper URL authorization | ANN has paper A, not paper B. | Call `GET /paper/{paperB}` with ANN token. | API returns 403; UI cannot load paper B. | High |
| RB-ANN-005 | Paragraph highlights | Assigned paper has sentences and mentions. | Open paper; inspect paragraphs. | Paragraphs render, typed mentions are clickable, warnings shown only for missing data. | Medium |
| RB-ANN-006 | Add selected relation | Editable assignment. | Click two entity highlights, enter predicate, click Add selected. | Relation pill appears, dirty state becomes Unsaved. | High |
| RB-ANN-007 | Add free-form relation | Editable assignment. | Enter Head, Relation, Tail, click Add free-form. | Relation pill appears with custom subject/object, dirty state becomes Unsaved. | High |
| RB-ANN-008 | Delete relation | Editable assignment with relation. | Click relation delete icon. | Relation removed; undo stack increments; dirty state shown. | High |
| RB-ANN-009 | Undo relation edit | Relation changed and undo stack exists. | Click Undo. | Previous relation set restored; dirty reflects baseline comparison. | Medium |
| RB-ANN-010 | Save draft | Editable assignment with dirty changes. | Click Save draft. | `POST /paper/{id}/relations/save` succeeds; assignment becomes `in_progress`; saved state shown. | High |
| RB-ANN-011 | Submit saved draft | Latest submission status is `draft`, no unsaved changes. | Click Submit. | `POST /assignments/{id}/submit` succeeds; assignment/submission becomes `submitted`; editor read-only. | High |
| RB-ANN-012 | Submit blocked when dirty | Draft saved, then make new change. | Attempt Submit. | Submit button disabled until Save draft succeeds. | High |
| RB-ANN-013 | Returned work edit | Reviewer returned submission with comment. | ANN opens paper. | Comment shown; editor editable; save creates new draft version; submit resubmits. | High |
| RB-ANN-014 | Approved work export | Assignment approved. | Open Exports, select paper, choose CSV/JSON, download. | File downloads; only approved own papers appear. | High |
| RB-ANN-015 | Forbidden nav direct access | ANN approved. | Browse to `/app/requests`, `/app/review`, `/app/users`. | UI redirects to `/app/editor`. | High |

### Reviewer Test Cases

| Test Case ID | Feature | Preconditions | Test steps | Expected result | Priority |
|---|---|---|---|---|---|
| RB-REV-001 | Login/nav | REV approved, verified, active. | Sign in. | Nav shows Editor, Assignments, Requests, Review, Exports; no Users. | High |
| RB-REV-002 | Approve annotator request | Verified pending annotator exists. | Open Requests -> Annotator pending -> Approve. | User status becomes approved; request queue refreshes. | High |
| RB-REV-003 | Reject annotator request | Verified pending annotator exists. | Enter optional reason, click Reject. | User status rejected and reason stored/displayable. | High |
| RB-REV-004 | Reviewer cannot manage reviewer requests | REV signed in. | Call admin reviewer request endpoint. | 403 from `/admin/signup-requests`. | High |
| RB-REV-005 | Assignment options | Approved annotators and papers exist. | Open Assignments. | Create assignment form lists papers and approved verified annotators. | High |
| RB-REV-006 | Create assignment | Paper has no active assignment. | Select paper, annotator, due date, click Assign. | Assignment created with reviewer_id=current reviewer and status `assigned`. | High |
| RB-REV-007 | Duplicate assignment blocked | Paper already active. | Attempt assignment for same paper. | Paper disabled in UI; direct API returns 400. | High |
| RB-REV-008 | Cancel owned assignment | Owned assignment not approved. | Click Cancel and confirm. | Assignment status `cancelled`, completed_at set. | High |
| RB-REV-009 | Cannot cancel another reviewer's assignment | Assignment owned by reviewer B. | Reviewer A calls cancel endpoint. | 403. | High |
| RB-REV-010 | Editor read-only | REV opens paper under review. | Attempt relation edit/save. | UI hides composers; backend save returns 403 for reviewer direct edit. | High |
| RB-REV-011 | Review submitted work | Owned submitted submission exists. | Open Review submitted tab and select submission. | Detail relation table and metadata render. | High |
| RB-REV-012 | Return submission | Submitted owned work exists. | Enter comment, click Return. | Submission and assignment become returned; decision row inserted. | High |
| RB-REV-013 | Approve submission | Submitted owned work exists. | Click Approve final. | Submission/assignment approved; final annotations replaced; export possible. | High |
| RB-REV-014 | Review status filters | Returned and approved submissions exist. | Switch submitted/returned/approved tabs. | Each queue shows only selected status. | Medium |
| RB-REV-015 | Export final paper | Final annotations exist. | Open Exports and download CSV/JSON. | Reviewer can export final annotations. | High |

### Super Admin Test Cases

| Test Case ID | Feature | Preconditions | Test steps | Expected result | Priority |
|---|---|---|---|---|---|
| RB-ADM-001 | Bootstrap admin | No admin exists; Firebase email matches `AUTH_ADMIN_EMAIL`, verified. | Call `/auth/me` after Firebase sign-in. | Admin profile auto-created and approved. | High |
| RB-ADM-002 | Public admin registration rejected | Firebase user tries role `admin` via register profile. | POST `/auth/register-profile`. | 400 "Admin users cannot register publicly". | High |
| RB-ADM-003 | Admin nav | ADM approved. | Sign in. | Nav shows all workspace items including Users. | High |
| RB-ADM-004 | Reviewer request list | Verified pending reviewer exists. | Open Requests reviewer pending tab. | Reviewer request is visible. | High |
| RB-ADM-005 | Approve reviewer | Verified pending reviewer exists. | Click Approve. | Reviewer status approved. | High |
| RB-ADM-006 | Reject reviewer | Verified pending reviewer exists. | Enter reason, click Reject. | Reviewer status rejected with reason. | High |
| RB-ADM-007 | Manage annotator requests | Verified pending annotator exists. | Open annotator pending tab. | Admin can approve/reject annotator through reviewer endpoints. | High |
| RB-ADM-008 | List users | Users exist. | Open Users. | All user profiles display sorted by created_at desc. | High |
| RB-ADM-009 | Deactivate user | Non-self active user exists. | Click Deactivate and confirm. | `is_active=false`; Firebase user disabled; target blocked from APIs. | High |
| RB-ADM-010 | Reactivate user | Inactive user exists. | Click Reactivate and confirm. | `is_active=true`; Firebase user enabled. | High |
| RB-ADM-011 | Self-deactivation blocked | Admin row visible. | Try deactivation self through UI/API. | UI disables; direct API returns 400. | High |
| RB-ADM-012 | Assignment all-access | Assignments exist across reviewers. | Open Assignments. | Admin sees all assignment rows and histories. | High |
| RB-ADM-013 | Review all-access | Submitted work across reviewers exists. | Open Review. | Admin can inspect/return/approve any submission. | High |
| RB-ADM-014 | Editor all-paper visibility | Papers exist without assignments. | Open Editor. | Admin can list/open all papers but cannot save unless editable assignment exists. | Medium |
| RB-ADM-015 | Export all final annotations | Final annotations exist. | Download CSV and JSON for any paper. | Export succeeds and export job is recorded. | High |

## Part 4: Authentication Testing

| Test Case ID | Feature | Preconditions | Test steps | Expected result | Priority |
|---|---|---|---|---|---|
| AUTH-001 | Login valid | Approved active verified user exists. | Enter valid email/password on `/signin`. | Firebase sign-in succeeds, `/auth/me` succeeds, route redirects based on role/status. | High |
| AUTH-002 | Login invalid password | User exists. | Enter wrong password. | Firebase error shown; no route transition. | High |
| AUTH-003 | Login unknown email | Email not registered. | Submit sign-in. | Firebase error shown; no backend profile created. | High |
| AUTH-004 | Logout | Signed in. | Click Sign out. | Firebase signs out; state cleared; user lands on `/signin`; protected routes redirect. | High |
| AUTH-005 | Session refresh | Signed in, browser session active. | Refresh `/app/editor`. | `onAuthStateChanged` restores session and reloads `/auth/me`. | High |
| AUTH-006 | Session timeout | Backend/Firebase token invalid or expired. | Force expired token or wait expiry and call API. | API returns 401; UI displays session/API error. | High |
| AUTH-007 | Password reset | Existing email. | Submit `/forgot-password`. | Firebase reset email sent; success message shown. | Medium |
| AUTH-008 | Password reset invalid email | Invalid/unregistered email. | Submit reset. | Firebase error shown. | Medium |
| AUTH-009 | Email verification refresh | User profile exists but Firebase email unverified. | Open `/verify-email`, verify externally, click Refresh status. | Backend sync updates `email_verified`; user proceeds to account status/editor. | High |
| AUTH-010 | Resend verification cooldown | Unverified user. | Click Resend twice quickly. | First sends email, second disabled until 60 seconds. | Medium |
| AUTH-011 | Remember me | Any user. | Inspect sign-in page. | No Remember me control exists; browser session persistence only. | Low |
| AUTH-012 | Multi-tab behavior | Same browser session. | Sign in tab A, open tab B, then sign out in tab A. | Tab B should lose Firebase session on refresh/API call and redirect to sign-in. | High |
| AUTH-013 | Unauthorized direct route | Signed out. | Browse to `/app/editor`, `/complete-profile`, `/verify-email`. | Protected routes redirect to `/signin` except public pages. | High |
| AUTH-014 | Missing backend profile | Firebase user exists with no profile. | Sign in and call `/auth/me`. | `/auth/me` returns 404; UI routes to `/complete-profile`. | High |
| AUTH-015 | Inactive user login | User `is_active=false`. | Sign in and call `/auth/me` or `/papers`. | Backend returns 401 "User is inactive or no longer exists". | High |

## Part 5: Authorization Testing

| Test Case ID | Violation | Exact page/API to test | Preconditions | Expected result | Priority |
|---|---|---|---|---|---|
| AUTHZ-001 | ANN opens requests page | `/app/requests` | Approved ANN. | UI redirects to `/app/editor`. | High |
| AUTHZ-002 | ANN opens review page | `/app/review` | Approved ANN. | UI redirects to `/app/editor`. | High |
| AUTHZ-003 | ANN opens users page | `/app/users` | Approved ANN. | UI redirects to `/app/editor`. | High |
| AUTHZ-004 | ANN calls admin signup list | `GET /admin/signup-requests?status=pending&role=reviewer` | ANN token. | 403. | High |
| AUTHZ-005 | ANN calls reviewer signup list | `GET /reviewer/signup-requests?status=pending` | ANN token. | 403. | High |
| AUTHZ-006 | ANN calls assignment options | `GET /assignments/options` | ANN token. | 403. | High |
| AUTHZ-007 | ANN creates assignment | `POST /assignments` | ANN token. | 403. | High |
| AUTHZ-008 | ANN reviews submission | `GET /review/submissions` | ANN token. | 403. | High |
| AUTHZ-009 | ANN exports non-owned final paper | `GET /exports/papers/{paper_id}` | Paper not approved for ANN. | 403. | High |
| AUTHZ-010 | ANN opens unassigned paper | `GET /paper/{paper_id}` | Paper not assigned to ANN. | 403. | High |
| AUTHZ-011 | REV opens users page | `/app/users` | Approved REV. | UI redirects to editor. | High |
| AUTHZ-012 | REV calls admin users | `GET /admin/users` | REV token. | 403. | High |
| AUTHZ-013 | REV approves reviewer | `POST /admin/signup-requests/{id}/approve` | REV token. | 403. | High |
| AUTHZ-014 | REV cancels other reviewer's assignment | `POST /assignments/{id}/cancel` | Assignment reviewer_id != REV. | 403. | High |
| AUTHZ-015 | REV reviews other reviewer's submission | `GET /review/submissions/{id}` | Submission assignment reviewer_id != REV. | 403. | High |
| AUTHZ-016 | REV direct content edit | `POST /paper/{paper_id}/relations/save` | REV owns assignment. | 403 "Reviewers cannot edit submitted annotation content directly". | High |
| AUTHZ-017 | Pending user accesses editor API | `GET /papers` | Registered pending verified user. | 403 "User has not been approved". | High |
| AUTHZ-018 | Unverified user accesses approved API | `GET /papers` | Registered unverified user. | 403 "Email has not been verified". | High |
| AUTHZ-019 | Inactive user accesses API | `GET /papers` | Inactive profile token. | 401. | High |
| AUTHZ-020 | Admin self deactivate | `DELETE /admin/users/{self_id}` | ADM token. | 400. | High |

## Part 6: Workflow Testing

| Test Case ID | Workflow | Path | Preconditions | Expected result | Priority |
|---|---|---|---|---|---|
| WF-001 | Access request to approval | Request access -> verify email -> reviewer/admin approval -> login | New annotator. | Pending request hidden until verified; after approval user reaches editor. | High |
| WF-002 | Reviewer onboarding | Request reviewer -> verify email -> admin approval -> login | New reviewer. | Admin approves reviewer; reviewer gains Requests/Review/Assignments controls. | High |
| WF-003 | Assignment happy path | Create assignment -> annotator sees paper | REV/ADM and approved annotator. | `annotation_assignments.status='assigned'`; paper visible to annotator. | High |
| WF-004 | Duplicate assignment failure | Try active duplicate | Existing assignment status assigned/in_progress/submitted/returned. | UI disables paper; API returns 400. | High |
| WF-005 | Draft save happy path | Open assigned paper -> add/delete relation -> Save draft | ANN assigned. | New draft version inserted; assignment status in_progress; relations persisted. | High |
| WF-006 | Draft save validation | Save with mismatched path/body paper_id | Editable assignment. | 400 `paper_id mismatch`. | High |
| WF-007 | Submit happy path | Save draft -> Submit | ANN has latest draft and no dirty changes. | Old submitted/returned drafts superseded; latest draft submitted; assignment submitted. | High |
| WF-008 | Submit without draft | Click direct API submit before save | Assigned ANN. | 400 "Save a draft before submitting." | High |
| WF-009 | Review return path | Submitted -> reviewer comment -> Return | Owning REV/ADM. | Decision inserted; submission and assignment returned; annotator can edit. | High |
| WF-010 | Resubmission after return | Returned -> ANN saves new draft -> Submit | Returned assignment. | New version submitted; previous returned/superseded state preserved. | High |
| WF-011 | Review approval path | Submitted -> Approve final | Owning REV/ADM. | Final annotations replaced for paper; assignment approved; export enabled. | High |
| WF-012 | Approve non-submitted failure | Return/approved submission -> approve again | REV/ADM. | 400 "Only submitted work can be approved." | High |
| WF-013 | Cancel path | Active assignment -> Cancel | Owning REV/ADM, not approved. | Assignment status cancelled, completed_at set; paper available again. | High |
| WF-014 | Cancel approved failure | Approved assignment. | Call cancel. | 400 "Approved assignments cannot be cancelled". | High |
| WF-015 | Export path | Approved final annotations -> download CSV/JSON | Final rows exist. | File response correct content type/name; export job/audit event recorded. | High |
| WF-016 | Export no final rows | Approved assignment but no final rows or never approved paper. | Download export. | 404 "No final annotations are available for this paper". | High |
| WF-017 | Custom predicate workflow | Add selected relation with new predicate. | Editable paper. | `relation_predicates` gets custom row; relation added to draft. | Medium |

## Part 7: Negative Testing

| Test Case ID | Area | Input/action | Expected result | Priority |
|---|---|---|---|---|
| NEG-001 | Signup | Empty email. | UI validation prevents continue. | High |
| NEG-002 | Signup | Password shorter than 8 chars. | UI shows length error. | High |
| NEG-003 | Signup | Password and confirm mismatch. | UI shows mismatch error. | High |
| NEG-004 | Profile | Empty full name. | UI/backend validation blocks. | High |
| NEG-005 | Profile | Role `admin` in request body. | 400 from `/auth/register-profile`. | High |
| NEG-006 | Reject reason | More than 1000 chars. | 422 from reject endpoints. | Medium |
| NEG-007 | Review comment | More than 2000 chars. | 422 from return/approve endpoints. | Medium |
| NEG-008 | Assignment create | Empty paper_id or annotator_id. | 422 or 404. | High |
| NEG-009 | Assignment create | Annotator ID belongs to reviewer/admin. | 400 "Only approved, active, verified annotators can be assigned". | High |
| NEG-010 | Assignment create | Pending/unverified/inactive annotator. | 400. | High |
| NEG-011 | Assignment history | Invalid paper_id. | 404 "Paper not found". | Medium |
| NEG-012 | Paper detail | Invalid paper_id. | 404 structured `paper_not_found`. | High |
| NEG-013 | Save relations | No active assignment. | 403 "Create or open an active assignment before saving annotations". | High |
| NEG-014 | Save relations | Invalid relation payload type/missing fields. | 422. | High |
| NEG-015 | Save relations | Unknown sentence/support IDs. | Save skips unknown support links; verify resulting DB does not create invalid FK rows. | Medium |
| NEG-016 | Submit | Assignment status submitted/approved/cancelled. | 400 cannot submit. | High |
| NEG-017 | Return | Submission already returned/approved. | 400. | High |
| NEG-018 | Approve | Submission already returned/approved. | 400. | High |
| NEG-019 | Export | `format=xml` or empty. | 400 "Export format must be csv or json". | High |
| NEG-020 | Export | No final annotations. | 404. | High |
| NEG-021 | Network | Backend offline during page load. | UI shows timeout/error banner, no crash. | High |
| NEG-022 | Network | Refresh during Save draft. | On reload, last committed draft only should appear; no partial relation rows. | High |
| NEG-023 | Concurrency | Two tabs save same assignment. | Versions increment; latest version is loaded; no DB integrity errors. | High |
| NEG-024 | Concurrency | Reviewer approves while annotator edits stale returned/submitted assignment. | Save/submit blocked according to latest assignment status. | High |
| NEG-025 | Data gaps | Paper has no sentences/mentions/relations. | Warnings/empty states render; no editor crash. | Medium |
| NEG-026 | File upload | Try to find upload UI/API. | Not implemented in inspected code; no upload surface should exist. | Low |

## Part 8: Security Testing

| Test Case ID | Risk | Exact URLs/APIs | Test | Expected result |
|---|---|---|---|---|
| SEC-001 | Broken access control | All `/admin/*` | Use ANN and REV tokens. | 403 except ADM. |
| SEC-002 | Broken access control | `/reviewer/*`, `/assignments/options`, `/review/*` | Use ANN token. | 403. |
| SEC-003 | IDOR paper access | `GET /paper/{paper_id}` | ANN/REV requests paper outside assignment/ownership. | 403. |
| SEC-004 | IDOR assignment cancel | `POST /assignments/{assignment_id}/cancel` | Reviewer cancels another reviewer's assignment. | 403. |
| SEC-005 | IDOR submission detail | `GET /review/submissions/{submission_id}` | Reviewer reads another reviewer's submission. | 403. |
| SEC-006 | IDOR export | `GET /exports/papers/{paper_id}` | ANN exports non-approved or non-owned paper. | 403. |
| SEC-007 | JWT missing | Any protected API, for example `GET /papers` | No Authorization header. | 401 with Bearer challenge. |
| SEC-008 | JWT tampering | Any protected API | Modify token payload/signature. | 401 invalid token. |
| SEC-009 | JWT expired | Any protected API | Use expired Firebase ID token. | 401 invalid token. |
| SEC-010 | Session hijack | Browser devtools/local storage/cookies | Confirm no custom app token in localStorage; Firebase session only. | No backend token stored manually by app code. |
| SEC-011 | CSRF | Protected write APIs | Submit cross-site form without bearer token. | Request fails 401. Note: CORS is `allow_origins=["*"]` with credentials, review deployment policy. |
| SEC-012 | XSS user profile | Signup full_name/institute fields | Enter `<script>alert(1)</script>`, view Requests/Users/topbar. | Rendered as text by React, no script execution. |
| SEC-013 | XSS relation fields | Free-form relation fields and predicate | Enter HTML/script, save, review/export. | UI renders text; CSV/JSON contains escaped or inert data. |
| SEC-014 | SQL injection | Path/query/body IDs and predicate/comment fields | Use `' OR 1=1 --` in `paper_id`, `user_id`, predicate. | Parameterized queries prevent injection; 404/validation or literal value. |
| SEC-015 | File upload vulnerability | UI/API search | No upload endpoint in inspected code. | No file upload attack surface. |
| SEC-016 | Rate limiting | `/signin`, `/auth/register-profile`, approval APIs | Rapid repeated attempts. | Not implemented in inspected code/Firebase may throttle auth; document deployment control. |
| SEC-017 | Sensitive data exposure | `/admin/users`, `/reviewer/users`, `/auth/me` | Inspect response body. | No password/token fields. Reviewer `/reviewer/users` exposes all users to REV; verify product accepts this. |
| SEC-018 | CORS policy | All APIs | Browser origin other than app origin. | Current backend allows all origins; deployment should restrict origins before release. |
| SEC-019 | Admin bootstrap abuse | `/auth/me` with `AUTH_ADMIN_EMAIL` | Try unverified same email and verified after admin exists. | Unverified not promoted; public admin registration rejected; no second bootstrap. |
| SEC-020 | Audit integrity | Assignment/review/export APIs | Perform action and inspect `audit_events`. | Audit exists where implemented; action still succeeds if audit insert fails. |

## Part 9: Database Consistency Testing

Use the configured database from `backend/.env` `DATABASE_URL`. Validation queries below use external IDs where possible; replace placeholders.

| Action | API/UI | Tables affected | Expected DB changes | Validation queries |
|---|---|---|---|---|
| Register profile | `POST /auth/register-profile` | `user_profiles` | New row with role annotator/reviewer, pending status, Firebase UID/email, metadata. | `SELECT email, role, status, is_active, email_verified FROM user_profiles WHERE email=:email;` |
| Sync current user | `GET /auth/me` | `user_profiles` | Updates firebase_uid/email/full_name/email_verified fields if changed. | `SELECT firebase_uid, email_verified, email_verified_at FROM user_profiles WHERE id=:user_id;` |
| Approve reviewer | `POST /admin/signup-requests/{id}/approve` | `user_profiles` | `status='approved'`, `approved_by_id`, `approved_at`, null rejection reason. | `SELECT status, approved_by_id, approved_at, rejection_reason FROM user_profiles WHERE id=:id;` |
| Reject reviewer | `POST /admin/signup-requests/{id}/reject` | `user_profiles` | `status='rejected'`, `approved_at=NULL`, reason set. | `SELECT status, approved_at, rejection_reason FROM user_profiles WHERE id=:id;` |
| Approve/reject annotator | `/reviewer/signup-requests/{id}/*` | `user_profiles` | Same as reviewer approval/rejection, approver may be REV/ADM. | Same query as above. |
| Deactivate user | `DELETE /admin/users/{id}` | `user_profiles`, Firebase | `is_active=false`; Firebase account disabled. | `SELECT is_active FROM user_profiles WHERE id=:id;` |
| Reactivate user | `POST /admin/users/{id}/reactivate` | `user_profiles`, Firebase | `is_active=true`; Firebase account enabled. | `SELECT is_active FROM user_profiles WHERE id=:id;` |
| Add custom predicate | `POST /schema/predicates/direct` | `relation_predicates` | New custom predicate row only if lower-case duplicate not present. | `SELECT predicate,is_custom,created_by_id FROM relation_predicates WHERE lower(predicate)=lower(:predicate);` |
| Create assignment | `POST /assignments` | `annotation_assignments`, `audit_events` | New assignment `assigned`, reviewer=current user, annotator selected, paper uuid set. | `SELECT status, annotator_id, reviewer_id, due_at FROM annotation_assignments WHERE id=:id;` |
| Cancel assignment | `POST /assignments/{id}/cancel` | `annotation_assignments`, `audit_events` | `status='cancelled'`, `completed_at` set. | `SELECT status, completed_at FROM annotation_assignments WHERE id=:id;` |
| Save draft | `POST /paper/{paper_id}/relations/save` | `annotation_assignments`, `annotation_submissions`, `annotation_submission_relations`, `annotation_relation_support_sentences` | Assignment assigned/returned -> in_progress; new draft version; relation/support rows inserted. | `SELECT version,status FROM annotation_submissions WHERE assignment_id=:id ORDER BY version DESC;` and `SELECT count(*) FROM annotation_submission_relations WHERE submission_id=:submission_id;` |
| Submit assignment | `POST /assignments/{id}/submit` | `annotation_submissions`, `annotation_assignments`, `audit_events` | Latest draft -> submitted; older draft/submitted/returned -> superseded; assignment submitted. | `SELECT status,submitted_at FROM annotation_submissions WHERE id=:submission_id; SELECT status,submitted_at FROM annotation_assignments WHERE id=:assignment_id;` |
| Return submission | `POST /review/submissions/{id}/return` | `review_decisions`, `annotation_submissions`, `annotation_assignments`, `audit_events` | Decision returned inserted; submission/assignment returned. | `SELECT decision,comment FROM review_decisions WHERE submission_id=:id ORDER BY created_at DESC;` |
| Approve submission | `POST /review/submissions/{id}/approve` | `final_annotations`, `final_annotation_support_sentences`, `review_decisions`, `annotation_submissions`, `annotation_assignments`, `audit_events` | Existing final rows for paper deleted/replaced; submission/assignment approved. | `SELECT count(*) FROM final_annotations WHERE approved_submission_id=:id; SELECT status FROM annotation_submissions WHERE id=:id;` |
| Export final | `GET /exports/papers/{paper_id}` | `export_jobs`, `audit_events` | Completed export job inserted if final rows exist. | `SELECT format,status,file_path FROM export_jobs WHERE paper_id=(SELECT id FROM papers WHERE paper_id=:paper_id) ORDER BY created_at DESC LIMIT 1;` |

## Part 10: Regression Test Suite

| Priority | Area | Checklist item |
|---|---|---|
| P0 | Auth | Valid login, logout, Firebase token rejection, missing profile, pending/unverified/inactive gates. |
| P0 | Authorization | ANN blocked from requests/review/admin APIs; REV blocked from admin APIs; ownership checks for paper/assignment/submission/export. |
| P0 | Workflow | New annotator signup -> verify -> approve -> assignment -> draft save -> submit -> review approve -> export. |
| P0 | Draft persistence | Save relation set creates correct submission version and reloads latest draft. |
| P0 | Review persistence | Return and approve update submission/assignment states and decisions correctly. |
| P0 | Final annotations | Approval replaces final rows and export returns exact approved relation set. |
| P0 | Admin | Bootstrap admin, reviewer approval, user deactivate/reactivate. |
| P1 | UI | Editor empty/loading/error states, paper picker, relation add/delete/undo, sidebar resize. |
| P1 | Requests | Annotator/reviewer request tabs by status, reject reasons, verified-only queues. |
| P1 | Assignments | Duplicate active assignment prevention, cancellation, history table. |
| P1 | Exports | CSV and JSON download, no final rows error, invalid format error. |
| P1 | Data gaps | Missing sentences/mentions/relations render warnings without crash. |
| P1 | Security | XSS in profile/relation/comment fields; SQL injection strings in IDs and bodies. |
| P2 | Theme | Light/dark toggle persists visually across auth/workspace. |
| P2 | Accessibility | Keyboard operation for select controls, sidebar resizer, buttons, tab controls. |
| P2 | Legacy endpoint | `/paper/{id}/relations/add` echo endpoint behavior and need for removal/coverage decision. |

Existing automated coverage observed: `backend/tests/test_auth_integration.py` covers auth/profile approval and several DB-backed editor reads. Gaps: assignment create/cancel, draft save, submit, review return/approve, export, frontend route guards, and most authorization violations.

## Part 11: Test Execution Sheet

Copy this table into Excel and fill Result/Notes during execution.

| Test Case ID | Feature | Role | Result | Notes |
|---|---|---|---|---|
| RB-ANN-001 | Login redirect | Annotator |  |  |
| RB-ANN-002 | Empty editor state | Annotator |  |  |
| RB-ANN-003 | Paper visibility | Annotator |  |  |
| RB-ANN-004 | Direct paper URL authorization | Annotator |  |  |
| RB-ANN-005 | Paragraph highlights | Annotator |  |  |
| RB-ANN-006 | Add selected relation | Annotator |  |  |
| RB-ANN-007 | Add free-form relation | Annotator |  |  |
| RB-ANN-008 | Delete relation | Annotator |  |  |
| RB-ANN-009 | Undo relation edit | Annotator |  |  |
| RB-ANN-010 | Save draft | Annotator |  |  |
| RB-ANN-011 | Submit saved draft | Annotator |  |  |
| RB-ANN-012 | Submit blocked when dirty | Annotator |  |  |
| RB-ANN-013 | Returned work edit | Annotator |  |  |
| RB-ANN-014 | Approved work export | Annotator |  |  |
| RB-ANN-015 | Forbidden nav direct access | Annotator |  |  |
| RB-REV-001 | Login/nav | Reviewer |  |  |
| RB-REV-002 | Approve annotator request | Reviewer |  |  |
| RB-REV-003 | Reject annotator request | Reviewer |  |  |
| RB-REV-004 | Reviewer cannot manage reviewer requests | Reviewer |  |  |
| RB-REV-005 | Assignment options | Reviewer |  |  |
| RB-REV-006 | Create assignment | Reviewer |  |  |
| RB-REV-007 | Duplicate assignment blocked | Reviewer |  |  |
| RB-REV-008 | Cancel owned assignment | Reviewer |  |  |
| RB-REV-009 | Cannot cancel another reviewer's assignment | Reviewer |  |  |
| RB-REV-010 | Editor read-only | Reviewer |  |  |
| RB-REV-011 | Review submitted work | Reviewer |  |  |
| RB-REV-012 | Return submission | Reviewer |  |  |
| RB-REV-013 | Approve submission | Reviewer |  |  |
| RB-REV-014 | Review status filters | Reviewer |  |  |
| RB-REV-015 | Export final paper | Reviewer |  |  |
| RB-ADM-001 | Bootstrap admin | Super Admin |  |  |
| RB-ADM-002 | Public admin registration rejected | Super Admin |  |  |
| RB-ADM-003 | Admin nav | Super Admin |  |  |
| RB-ADM-004 | Reviewer request list | Super Admin |  |  |
| RB-ADM-005 | Approve reviewer | Super Admin |  |  |
| RB-ADM-006 | Reject reviewer | Super Admin |  |  |
| RB-ADM-007 | Manage annotator requests | Super Admin |  |  |
| RB-ADM-008 | List users | Super Admin |  |  |
| RB-ADM-009 | Deactivate user | Super Admin |  |  |
| RB-ADM-010 | Reactivate user | Super Admin |  |  |
| RB-ADM-011 | Self-deactivation blocked | Super Admin |  |  |
| RB-ADM-012 | Assignment all-access | Super Admin |  |  |
| RB-ADM-013 | Review all-access | Super Admin |  |  |
| RB-ADM-014 | Editor all-paper visibility | Super Admin |  |  |
| RB-ADM-015 | Export all final annotations | Super Admin |  |  |
| AUTH-001 | Login valid | All |  |  |
| AUTH-002 | Login invalid password | Public |  |  |
| AUTH-003 | Login unknown email | Public |  |  |
| AUTH-004 | Logout | All |  |  |
| AUTH-005 | Session refresh | All |  |  |
| AUTH-006 | Session timeout | All |  |  |
| AUTH-007 | Password reset | Public |  |  |
| AUTH-008 | Password reset invalid email | Public |  |  |
| AUTH-009 | Email verification refresh | Pending user |  |  |
| AUTH-010 | Resend verification cooldown | Pending user |  |  |
| AUTH-011 | Remember me | Public |  |  |
| AUTH-012 | Multi-tab behavior | All |  |  |
| AUTH-013 | Unauthorized direct route | Public |  |  |
| AUTH-014 | Missing backend profile | Firebase user |  |  |
| AUTH-015 | Inactive user login | Inactive user |  |  |
| AUTHZ-001 | ANN opens requests page | Annotator |  |  |
| AUTHZ-002 | ANN opens review page | Annotator |  |  |
| AUTHZ-003 | ANN opens users page | Annotator |  |  |
| AUTHZ-004 | ANN calls admin signup list | Annotator |  |  |
| AUTHZ-005 | ANN calls reviewer signup list | Annotator |  |  |
| AUTHZ-006 | ANN calls assignment options | Annotator |  |  |
| AUTHZ-007 | ANN creates assignment | Annotator |  |  |
| AUTHZ-008 | ANN reviews submission | Annotator |  |  |
| AUTHZ-009 | ANN exports non-owned final paper | Annotator |  |  |
| AUTHZ-010 | ANN opens unassigned paper | Annotator |  |  |
| AUTHZ-011 | REV opens users page | Reviewer |  |  |
| AUTHZ-012 | REV calls admin users | Reviewer |  |  |
| AUTHZ-013 | REV approves reviewer | Reviewer |  |  |
| AUTHZ-014 | REV cancels other reviewer's assignment | Reviewer |  |  |
| AUTHZ-015 | REV reviews other reviewer's submission | Reviewer |  |  |
| AUTHZ-016 | REV direct content edit | Reviewer |  |  |
| AUTHZ-017 | Pending user accesses editor API | Pending |  |  |
| AUTHZ-018 | Unverified user accesses approved API | Unverified |  |  |
| AUTHZ-019 | Inactive user accesses API | Inactive |  |  |
| AUTHZ-020 | Admin self deactivate | Super Admin |  |  |
| WF-001 | Access request to approval | Public/Reviewer |  |  |
| WF-002 | Reviewer onboarding | Public/Super Admin |  |  |
| WF-003 | Assignment happy path | Reviewer/Admin |  |  |
| WF-004 | Duplicate assignment failure | Reviewer/Admin |  |  |
| WF-005 | Draft save happy path | Annotator |  |  |
| WF-006 | Draft save validation | Annotator |  |  |
| WF-007 | Submit happy path | Annotator |  |  |
| WF-008 | Submit without draft | Annotator |  |  |
| WF-009 | Review return path | Reviewer/Admin |  |  |
| WF-010 | Resubmission after return | Annotator |  |  |
| WF-011 | Review approval path | Reviewer/Admin |  |  |
| WF-012 | Approve non-submitted failure | Reviewer/Admin |  |  |
| WF-013 | Cancel path | Reviewer/Admin |  |  |
| WF-014 | Cancel approved failure | Reviewer/Admin |  |  |
| WF-015 | Export path | All |  |  |
| WF-016 | Export no final rows | All |  |  |
| WF-017 | Custom predicate workflow | Annotator/Admin |  |  |
| NEG-001 | Signup empty email | Public |  |  |
| NEG-002 | Signup short password | Public |  |  |
| NEG-003 | Signup mismatch password | Public |  |  |
| NEG-004 | Empty full name | Public/Firebase user |  |  |
| NEG-005 | Admin role registration | Public/Firebase user |  |  |
| NEG-006 | Reject reason length | Reviewer/Admin |  |  |
| NEG-007 | Review comment length | Reviewer/Admin |  |  |
| NEG-008 | Assignment empty fields | Reviewer/Admin |  |  |
| NEG-009 | Assign non-annotator | Reviewer/Admin |  |  |
| NEG-010 | Assign pending/unverified/inactive annotator | Reviewer/Admin |  |  |
| NEG-011 | Invalid assignment history paper | Reviewer/Admin |  |  |
| NEG-012 | Invalid paper detail | All |  |  |
| NEG-013 | Save without active assignment | All |  |  |
| NEG-014 | Invalid relation payload | Annotator/Admin |  |  |
| NEG-015 | Unknown support IDs | Annotator/Admin |  |  |
| NEG-016 | Submit invalid status | Annotator |  |  |
| NEG-017 | Return invalid status | Reviewer/Admin |  |  |
| NEG-018 | Approve invalid status | Reviewer/Admin |  |  |
| NEG-019 | Invalid export format | All |  |  |
| NEG-020 | Export no final annotations | All |  |  |
| NEG-021 | Backend offline | All |  |  |
| NEG-022 | Refresh during save | Annotator |  |  |
| NEG-023 | Concurrent saves | Annotator |  |  |
| NEG-024 | Concurrent approve/edit | Annotator/Reviewer |  |  |
| NEG-025 | Missing paper data | All |  |  |
| NEG-026 | File upload absence | All |  |  |
| SEC-001 | Admin broken access control | All |  |  |
| SEC-002 | Reviewer broken access control | All |  |  |
| SEC-003 | Paper IDOR | Annotator/Reviewer |  |  |
| SEC-004 | Assignment cancel IDOR | Reviewer |  |  |
| SEC-005 | Submission detail IDOR | Reviewer |  |  |
| SEC-006 | Export IDOR | Annotator |  |  |
| SEC-007 | Missing JWT | Public |  |  |
| SEC-008 | Tampered JWT | All |  |  |
| SEC-009 | Expired JWT | All |  |  |
| SEC-010 | Session hijack storage check | All |  |  |
| SEC-011 | CSRF write attempt | Public |  |  |
| SEC-012 | XSS profile fields | Public/Admin/Reviewer |  |  |
| SEC-013 | XSS relation fields | Annotator/Reviewer |  |  |
| SEC-014 | SQL injection probes | All |  |  |
| SEC-015 | File upload vulnerability | All |  |  |
| SEC-016 | Rate limiting | Public/Admin |  |  |
| SEC-017 | Sensitive data exposure | Reviewer/Admin |  |  |
| SEC-018 | CORS policy | Public |  |  |
| SEC-019 | Admin bootstrap abuse | Public/Admin |  |  |
| SEC-020 | Audit integrity | Reviewer/Admin |  |  |
