# Annotation Platform

Firebase-authenticated relation annotation platform for low-temperature plasma papers.

## What It Does

- Uses Firebase Auth for signup, signin, email verification, password reset, and browser sessions.
- Uses the platform backend database for roles, approval status, active/inactive users, and admin/reviewer approval workflows.
- Uses Aiven/PostgreSQL-backed paper, mention, suggestion, draft, review, final annotation, and export data.
- Supports the complete workflow: assign paper, save draft, submit, review, return/approve, finalize, and export.
- Restricts annotators to assigned papers. Reviewers see assignments they own; admins can see all papers.
- Allows admins to approve reviewers and manage users.
- Allows reviewers/admins to approve annotators and manage annotation workflow.

## Firebase Setup

1. Create or reuse a Firebase project.
2. Enable Email/Password under Firebase Authentication.
3. Create the first admin user manually in Firebase Authentication.
4. Verify that admin email in Firebase.
5. Download a Firebase service account JSON and place it at `backend/firebase-service-account.json`.
6. Set backend and frontend env files from the examples.

The first admin is created in the platform database only when no admin exists yet, the Firebase email is verified, and the email exactly matches `AUTH_ADMIN_EMAIL`.

## Backend

```bash
cd Annotation_Platform/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Backend env:

```env
DATABASE_URL=sqlite:///./annotation_auth.db
AUTH_ADMIN_EMAIL=admin@example.com
AUTH_ADMIN_FULL_NAME=Primary Admin
FIREBASE_PROJECT_ID=your-firebase-project-id
FIREBASE_SERVICE_ACCOUNT_PATH=./firebase-service-account.json
```

## Frontend

```bash
cd Annotation_Platform/frontend
npm install
cp .env.example .env.local
npm run dev:poll
```

Frontend env:

```env
VITE_FIREBASE_API_KEY=your-firebase-web-api-key
VITE_FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=your-firebase-project-id
VITE_FIREBASE_APP_ID=your-firebase-app-id
VITE_API_BASE=/api
```

Open `http://localhost:5173`.

## Main API Groups

- `POST /auth/register-profile`
- `GET /auth/me`
- `GET /admin/signup-requests`
- `POST /admin/signup-requests/{user_id}/approve`
- `POST /admin/signup-requests/{user_id}/reject`
- `GET /admin/users`
- `DELETE /admin/users/{user_id}`
- `POST /admin/users/{user_id}/reactivate`
- `GET /reviewer/signup-requests`
- `POST /reviewer/signup-requests/{user_id}/approve`
- `POST /reviewer/signup-requests/{user_id}/reject`
- `GET /assignments`
- `GET /assignments/options`
- `POST /assignments`
- `POST /assignments/{assignment_id}/cancel`
- `POST /assignments/{assignment_id}/submit`
- `GET /review/submissions`
- `GET /review/submissions/{submission_id}`
- `POST /review/submissions/{submission_id}/return`
- `POST /review/submissions/{submission_id}/approve`
- `GET /exports/papers/{paper_id}?format=csv|json`
- `GET /papers`
- `GET /paper/{paper_id}`
- `POST /paper/{paper_id}/relations/save`

Authenticated API calls require:

```text
Authorization: Bearer <firebase_id_token>
```

## Test

```bash
cd Annotation_Platform/backend
python3 -m pytest
```

```bash
cd Annotation_Platform/frontend
npm run build
```
