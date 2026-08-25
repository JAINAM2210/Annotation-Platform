from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


@dataclass
class FakeFirebaseUser:
    uid: str
    email: str
    email_verified: bool
    name: str
    disabled: bool = False


class FakeFirebaseAuth:
    def __init__(self):
        self._users_by_token: dict[str, FakeFirebaseUser] = {}
        self._users_by_uid: dict[str, FakeFirebaseUser] = {}
        self._counter = 0

    def add_user(self, email: str, *, verified: bool, name: str | None = None) -> str:
        self._counter += 1
        uid = f"uid-{self._counter}"
        token = f"token-{self._counter}"
        user = FakeFirebaseUser(uid=uid, email=email.lower(), email_verified=verified, name=name or email.split("@")[0])
        self._users_by_token[token] = user
        self._users_by_uid[uid] = user
        return token

    def set_verified(self, token: str, verified: bool) -> None:
        self._users_by_token[token].email_verified = verified

    def verify_token(self, token: str):
        from app.firebase_auth import FirebaseIdentity, FirebaseTokenError

        user = self._users_by_token.get(token)
        if user is None or user.disabled:
            raise FirebaseTokenError("Invalid Firebase authentication token")
        return FirebaseIdentity(uid=user.uid, email=user.email, email_verified=user.email_verified, name=user.name)

    def disable_user(self, firebase_uid: str) -> None:
        user = self._users_by_uid.get(firebase_uid)
        if user is not None:
            user.disabled = True

    def enable_user(self, firebase_uid: str) -> None:
        user = self._users_by_uid.get(firebase_uid)
        if user is not None:
            user.disabled = False


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'platform_auth_test.db'}")
    monkeypatch.setenv("AUTH_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("AUTH_ADMIN_FULL_NAME", "Primary Admin")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "demo-project")
    monkeypatch.setenv("FIREBASE_SERVICE_ACCOUNT_PATH", str(tmp_path / "firebase-service-account.json"))
    (tmp_path / "firebase-service-account.json").write_text('{"type":"service_account"}', encoding="utf-8")

    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]

    from app import auth_services, dependencies
    from app.main import app

    fake_firebase = FakeFirebaseAuth()
    monkeypatch.setattr(dependencies, "verify_firebase_token", fake_firebase.verify_token)
    monkeypatch.setattr(auth_services, "disable_firebase_user", fake_firebase.disable_user)
    monkeypatch.setattr(auth_services, "enable_firebase_user", fake_firebase.enable_user)

    with TestClient(app) as test_client:
        test_client.fake_firebase = fake_firebase  # type: ignore[attr-defined]
        yield test_client


def firebase_token(client: TestClient, email: str, *, verified: bool, name: str | None = None) -> str:
    return client.fake_firebase.add_user(email=email, verified=verified, name=name)  # type: ignore[attr-defined]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def register_profile(
    client: TestClient,
    token: str,
    *,
    full_name: str,
    role: str,
    designation: str = "",
    institute: str = "",
    state: str = "",
    country: str = "",
) -> dict:
    response = client.post(
        "/auth/register-profile",
        headers=auth_headers(token),
        json={
            "full_name": full_name,
            "role": role,
            "designation": designation,
            "institute": institute,
            "state": state,
            "country": country,
        },
    )
    assert response.status_code == 200
    return response.json()


def refresh_me(client: TestClient, token: str) -> dict:
    response = client.get("/auth/me", headers=auth_headers(token))
    assert response.status_code == 200
    return response.json()


def admin_token(client: TestClient) -> str:
    return firebase_token(client, "admin@example.com", verified=True, name="Primary Admin")


def test_verified_bootstrap_admin_is_created_only_as_first_admin(client: TestClient):
    unverified_admin = firebase_token(client, "admin@example.com", verified=False)
    missing = client.get("/auth/me", headers=auth_headers(unverified_admin))
    assert missing.status_code == 404

    verified_admin = admin_token(client)
    admin = refresh_me(client, verified_admin)
    assert admin["role"] == "admin"
    assert admin["status"] == "approved"

    reviewer_token = firebase_token(client, "reviewer@example.com", verified=True)
    reviewer = register_profile(client, reviewer_token, full_name="Reviewer", role="reviewer")
    approve = client.post(f"/admin/signup-requests/{reviewer['id']}/approve", headers=auth_headers(verified_admin))
    assert approve.status_code == 200


def test_public_admin_registration_is_rejected(client: TestClient):
    token = firebase_token(client, "someone@example.com", verified=True)
    response = client.post("/auth/register-profile", headers=auth_headers(token), json={"full_name": "Someone", "role": "admin"})
    assert response.status_code == 400


def test_profile_metadata_fields_round_trip(client: TestClient):
    token = firebase_token(client, "metadata@example.com", verified=True)
    created = register_profile(
        client,
        token,
        full_name="Metadata User",
        role="annotator",
        designation="Research Scholar",
        institute="Plasma Lab",
        state="Gujarat",
        country="India",
    )
    refreshed = refresh_me(client, token)
    assert created["id"] == refreshed["id"]
    assert refreshed["designation"] == "Research Scholar"
    assert refreshed["institute"] == "Plasma Lab"
    assert refreshed["state"] == "Gujarat"
    assert refreshed["country"] == "India"


def test_unverified_users_are_hidden_from_approval_queues(client: TestClient):
    admin = admin_token(client)
    refresh_me(client, admin)
    annotator = firebase_token(client, "annotator@example.com", verified=False)
    reviewer = firebase_token(client, "reviewer@example.com", verified=False)
    register_profile(client, annotator, full_name="Annotator", role="annotator")
    register_profile(client, reviewer, full_name="Reviewer", role="reviewer")

    annotators = client.get("/reviewer/signup-requests?status=pending", headers=auth_headers(admin))
    reviewers = client.get("/admin/signup-requests?status=pending&role=reviewer", headers=auth_headers(admin))
    assert annotators.status_code == 200
    assert reviewers.status_code == 200
    assert annotators.json() == []
    assert reviewers.json() == []


def test_pending_user_cannot_access_editor_apis(client: TestClient):
    token = firebase_token(client, "pending@example.com", verified=True)
    register_profile(client, token, full_name="Pending", role="annotator")
    response = client.get("/papers", headers=auth_headers(token))
    assert response.status_code == 403
    assert response.json()["detail"] == "User has not been approved"


def test_approved_user_can_access_editor_apis(client: TestClient):
    admin = admin_token(client)
    refresh_me(client, admin)
    annotator_token = firebase_token(client, "approved-annotator@example.com", verified=True)
    annotator = register_profile(client, annotator_token, full_name="Approved Annotator", role="annotator")
    approve = client.post(f"/reviewer/signup-requests/{annotator['id']}/approve", headers=auth_headers(admin))
    papers = client.get("/papers", headers=auth_headers(annotator_token))
    predicates = client.get("/schema/predicates/direct", headers=auth_headers(annotator_token))
    assert approve.status_code == 200
    assert papers.status_code == 200
    assert isinstance(papers.json(), list)
    assert predicates.status_code == 200


def test_admin_can_approve_reviewer_and_reviewer_can_approve_annotator(client: TestClient):
    admin = admin_token(client)
    refresh_me(client, admin)
    reviewer_token = firebase_token(client, "approved-reviewer@example.com", verified=True)
    reviewer = register_profile(client, reviewer_token, full_name="Approved Reviewer", role="reviewer")
    approve_reviewer = client.post(f"/admin/signup-requests/{reviewer['id']}/approve", headers=auth_headers(admin))
    assert approve_reviewer.status_code == 200

    annotator_token = firebase_token(client, "queue-annotator@example.com", verified=True)
    annotator = register_profile(client, annotator_token, full_name="Queue Annotator", role="annotator")
    approve_annotator = client.post(f"/reviewer/signup-requests/{annotator['id']}/approve", headers=auth_headers(reviewer_token))
    assert approve_annotator.status_code == 200
    assert approve_annotator.json()["status"] == "approved"


def test_admin_can_deactivate_and_reactivate_user(client: TestClient):
    admin = admin_token(client)
    refresh_me(client, admin)
    annotator_token = firebase_token(client, "lifecycle@example.com", verified=True)
    annotator = register_profile(client, annotator_token, full_name="Lifecycle", role="annotator")
    client.post(f"/reviewer/signup-requests/{annotator['id']}/approve", headers=auth_headers(admin))

    deactivate = client.delete(f"/admin/users/{annotator['id']}", headers=auth_headers(admin))
    blocked = client.get("/papers", headers=auth_headers(annotator_token))
    reactivate = client.post(f"/admin/users/{annotator['id']}/reactivate", headers=auth_headers(admin))
    allowed = client.get("/papers", headers=auth_headers(annotator_token))

    assert deactivate.status_code == 204
    assert blocked.status_code == 401
    assert reactivate.status_code == 200
    assert reactivate.json()["is_active"] is True
    assert allowed.status_code == 200


def seed_editor_paper(
    paper_id: str = "paper_db_001",
    *,
    with_mapping: bool = True,
    with_suggestion: bool = True,
    with_relation_predicate: bool = True,
    mention_has_paper_id: bool = True,
    suggestion_has_paper_id: bool = True,
) -> dict[str, str]:
    from uuid import uuid4

    from sqlalchemy import text

    from app.database import engine

    ids = {
        "paper": str(uuid4()),
        "sentence": str(uuid4()),
        "paragraph": str(uuid4()),
        "mention_subject": str(uuid4()),
        "mention_object": str(uuid4()),
        "suggestion_set": str(uuid4()),
        "suggestion": str(uuid4()),
    }
    with engine.begin() as connection:
        connection.execute(text(
            """
            INSERT INTO papers (id, paper_id, title, doi, citation, text_path, bio_path, source_text, created_at)
            VALUES (:id, :paper_id, :title, :doi, '', '', '', :source_text, CURRENT_TIMESTAMP)
            """
        ), {"id": ids["paper"], "paper_id": paper_id, "title": "DB Paper", "doi": "10/test", "source_text": "Plasma source measures voltage."})
        connection.execute(text(
            """
            INSERT INTO sentences (id, paper_id, sentence_key, sentence_index, text)
            VALUES (:id, :paper_uuid, :sentence_key, 1, :text)
            """
        ), {"id": ids["sentence"], "paper_uuid": ids["paper"], "sentence_key": f"{paper_id}:s0001", "text": "Plasma source measures voltage."})
        connection.execute(text(
            """
            INSERT INTO paragraphs (id, paper_id, paragraph_key, paragraph_index, text)
            VALUES (:id, :paper_uuid, :paragraph_key, 1, :text)
            """
        ), {"id": ids["paragraph"], "paper_uuid": ids["paper"], "paragraph_key": f"{paper_id}:p0001", "text": "Plasma source measures voltage."})
        if with_mapping:
            connection.execute(text(
                """
                INSERT INTO paragraph_sentences (paragraph_id, sentence_id, position)
                VALUES (:paragraph_id, :sentence_id, 1)
                """
            ), {"paragraph_id": ids["paragraph"], "sentence_id": ids["sentence"]})
        mention_paper_uuid = ids["paper"] if mention_has_paper_id else None
        connection.execute(text(
            """
            INSERT INTO entity_mentions (id, mention_key, paper_id, sentence_id, text, ner_label, schema_type, token_start, token_end)
            VALUES (:id, :mention_key, :paper_uuid, :sentence_id, :text, :ner_label, :schema_type, :token_start, :token_end)
            """
        ), {"id": ids["mention_subject"], "mention_key": f"{paper_id}:s0001:m001", "paper_uuid": mention_paper_uuid, "sentence_id": ids["sentence"], "text": "Plasma source", "ner_label": "", "schema_type": "Plasma Source", "token_start": 0, "token_end": 1})
        connection.execute(text(
            """
            INSERT INTO entity_mentions (id, mention_key, paper_id, sentence_id, text, ner_label, schema_type, token_start, token_end)
            VALUES (:id, :mention_key, :paper_uuid, :sentence_id, :text, :ner_label, :schema_type, :token_start, :token_end)
            """
        ), {"id": ids["mention_object"], "mention_key": f"{paper_id}:s0001:m002", "paper_uuid": mention_paper_uuid, "sentence_id": ids["sentence"], "text": "voltage", "ner_label": "", "schema_type": "Quantity", "token_start": 3, "token_end": 3})
        if with_relation_predicate:
            connection.execute(text(
                """
                INSERT INTO relation_predicates (id, predicate, subject_type, object_type, is_custom, created_by_id, created_at)
                VALUES (:id, 'measures', 'Plasma Source', 'Quantity', 0, NULL, CURRENT_TIMESTAMP)
                """
            ), {"id": str(uuid4())})
        if with_suggestion:
            connection.execute(text(
                """
                INSERT INTO suggestion_sets (id, paper_id, source_type, source_file, is_latest, imported_at)
                VALUES (:id, :paper_uuid, 'test', 'test.csv', 1, CURRENT_TIMESTAMP)
                """
            ), {"id": ids["suggestion_set"], "paper_uuid": ids["paper"]})
            connection.execute(text(
                """
                INSERT INTO suggested_relations (
                    id, suggestion_set_id, paper_id, relation_key, sentence_id, support_paragraph_id,
                    subject_mention_id, object_mention_id, subject_text, subject_type, predicate,
                    object_text, object_type, confidence, accepted, evidence_text, relation_origin,
                    inherited_from, raw_payload
                ) VALUES (
                    :id, :suggestion_set_id, :paper_uuid, :relation_key, :sentence_id, :paragraph_id,
                    :subject_mention_id, :object_mention_id, 'Plasma source', 'Plasma Source', 'measures',
                    'voltage', 'Quantity', 1.0, 1, 'Plasma source measures voltage.', 'test', '', NULL
                )
                """
            ), {
                "id": ids["suggestion"],
                "suggestion_set_id": ids["suggestion_set"],
                "paper_uuid": ids["paper"] if suggestion_has_paper_id else None,
                "relation_key": f"{paper_id}:r0001",
                "sentence_id": ids["sentence"],
                "paragraph_id": ids["paragraph"],
                "subject_mention_id": ids["mention_subject"],
                "object_mention_id": ids["mention_object"],
            })
            connection.execute(text(
                """
                INSERT INTO suggested_relation_support_sentences (suggested_relation_id, sentence_id)
                VALUES (:suggestion_id, :sentence_id)
                """
            ), {"suggestion_id": ids["suggestion"], "sentence_id": ids["sentence"]})
    return ids


def seed_editor_gap_paper(paper_id: str = "paper_db_gap") -> None:
    from uuid import uuid4

    from sqlalchemy import text

    from app.database import engine

    paper_uuid = str(uuid4())
    sentence_rows = [
        (str(uuid4()), f"{paper_id}:s0001", 1, "Alpha plasma starts."),
        (str(uuid4()), f"{paper_id}:s0002", 2, "Beta voltage rises."),
        (str(uuid4()), f"{paper_id}:s0003", 3, "This detached source sentence is not present in a paragraph."),
        (str(uuid4()), f"{paper_id}:s0004", 4, "Delta discharge glows."),
        (str(uuid4()), f"{paper_id}:s0005", 5, "Epsilon current falls."),
        (str(uuid4()), f"{paper_id}:s0006", 6, "Another skipped source sentence."),
        (str(uuid4()), f"{paper_id}:s0007", 7, "Co-axial dielectric-barrier discharge is stable after the gap."),
    ]
    paragraph_rows = [
        (str(uuid4()), f"{paper_id}:p0001", 1, "Alpha plasma starts. Beta voltage rises."),
        (str(uuid4()), f"{paper_id}:p0002", 2, "Delta discharge glows. Epsilon current falls."),
        (str(uuid4()), f"{paper_id}:p0003", 3, "Coaxial dielectric barrier discharge is stable after the gap."),
    ]

    with engine.begin() as connection:
        connection.execute(text(
            """
            INSERT INTO papers (id, paper_id, title, doi, citation, text_path, bio_path, source_text, created_at)
            VALUES (:id, :paper_id, :title, :doi, '', '', '', :source_text, CURRENT_TIMESTAMP)
            """
        ), {
            "id": paper_uuid,
            "paper_id": paper_id,
            "title": "Gap Inference Paper",
            "doi": "10/gap",
            "source_text": " ".join(row[3] for row in sentence_rows),
        })
        for sentence_uuid, sentence_key, sentence_index, sentence_text in sentence_rows:
            connection.execute(text(
                """
                INSERT INTO sentences (id, paper_id, sentence_key, sentence_index, text)
                VALUES (:id, :paper_uuid, :sentence_key, :sentence_index, :text)
                """
            ), {
                "id": sentence_uuid,
                "paper_uuid": paper_uuid,
                "sentence_key": sentence_key,
                "sentence_index": sentence_index,
                "text": sentence_text,
            })
        for paragraph_uuid, paragraph_key, paragraph_index, paragraph_text in paragraph_rows:
            connection.execute(text(
                """
                INSERT INTO paragraphs (id, paper_id, paragraph_key, paragraph_index, text)
                VALUES (:id, :paper_uuid, :paragraph_key, :paragraph_index, :text)
                """
            ), {
                "id": paragraph_uuid,
                "paper_uuid": paper_uuid,
                "paragraph_key": paragraph_key,
                "paragraph_index": paragraph_index,
                "text": paragraph_text,
            })
        connection.execute(text(
            """
            INSERT INTO entity_mentions (id, mention_key, paper_id, sentence_id, text, ner_label, schema_type, token_start, token_end)
            VALUES (:id, :mention_key, NULL, :sentence_id, :text, '', :schema_type, :token_start, :token_end)
            """
        ), {
            "id": str(uuid4()),
            "mention_key": f"{paper_id}:s0004:m001",
            "sentence_id": sentence_rows[3][0],
            "text": "Delta discharge",
            "schema_type": "Plasma Process",
            "token_start": 0,
            "token_end": 1,
        })


def test_db_backed_editor_infers_later_paragraphs_after_skipped_source_sentences(client: TestClient):
    token = admin_token(client)
    refresh_me(client, token)
    seed_editor_gap_paper()

    response = client.get("/paper/paper_db_gap", headers=auth_headers(token))

    assert response.status_code == 200
    payload = response.json()
    paragraphs = {paragraph["paragraph_index"]: paragraph for paragraph in payload["paragraphs"]}
    assert paragraphs[1]["sentence_ids"] == ["paper_db_gap:s0001", "paper_db_gap:s0002"]
    assert paragraphs[2]["sentence_ids"] == ["paper_db_gap:s0004", "paper_db_gap:s0005"]
    assert paragraphs[3]["sentence_ids"] == ["paper_db_gap:s0007"]
    assert any(mention["sentence_id"] == "paper_db_gap:s0004" for mention in payload["mentions"])
    assert not any("paragraph_sentences" in warning for warning in payload["warnings"])
    assert not any("Entity highlights could not be inferred" in warning for warning in payload["warnings"])


def test_db_backed_editor_returns_complete_paper_detail(client: TestClient):
    token = admin_token(client)
    refresh_me(client, token)
    seed_editor_paper("paper_db_complete")

    response = client.get("/paper/paper_db_complete", headers=auth_headers(token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["paper"]["paper_id"] == "paper_db_complete"
    assert payload["sentences"][0]["sentence_id"] == "paper_db_complete:s0001"
    assert payload["paragraphs"][0]["sentence_ids"] == ["paper_db_complete:s0001"]
    assert payload["mentions"][0]["paper_id"] == "paper_db_complete"
    assert payload["relations"][0]["relation_id"] == "paper_db_complete:r0001"
    assert payload["warnings"] == []


def test_db_backed_editor_warns_when_suggestions_are_missing(client: TestClient):
    token = admin_token(client)
    refresh_me(client, token)
    seed_editor_paper("paper_db_no_relations", with_suggestion=False)

    response = client.get("/paper/paper_db_no_relations", headers=auth_headers(token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["relations"] == []
    assert any("No relation suggestions" in warning for warning in payload["warnings"])


def test_db_backed_editor_infers_sentence_membership_without_paragraph_sentences(client: TestClient):
    token = admin_token(client)
    refresh_me(client, token)
    seed_editor_paper("paper_db_no_mapping", with_mapping=False, mention_has_paper_id=False)

    response = client.get("/paper/paper_db_no_mapping", headers=auth_headers(token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["paragraphs"][0]["paragraph_id"] == "paper_db_no_mapping:p0001"
    assert payload["paragraphs"][0]["sentence_ids"] == ["paper_db_no_mapping:s0001"]
    assert payload["mentions"][0]["paper_id"] == "paper_db_no_mapping"
    assert not any("paragraph_sentences" in warning for warning in payload["warnings"])


def test_db_backed_editor_loads_suggestions_through_suggestion_sets(client: TestClient):
    token = admin_token(client)
    refresh_me(client, token)
    seed_editor_paper(
        "paper_db_suggestion_set_only",
        with_mapping=False,
        with_relation_predicate=False,
        mention_has_paper_id=False,
        suggestion_has_paper_id=False,
    )

    detail = client.get("/paper/paper_db_suggestion_set_only", headers=auth_headers(token))
    predicates = client.get("/schema/predicates", headers=auth_headers(token))
    direct_predicates = client.get("/schema/predicates/direct", headers=auth_headers(token))

    assert detail.status_code == 200
    payload = detail.json()
    assert payload["relations"][0]["relation_id"] == "paper_db_suggestion_set_only:r0001"
    assert payload["relations"][0]["support_paragraph_id"] == "paper_db_suggestion_set_only:p0001"
    assert predicates.status_code == 200
    assert "measures" in predicates.json()
    assert direct_predicates.status_code == 200
    assert direct_predicates.json() == []


def test_saving_suggestion_preserves_suggested_relation_provenance(client: TestClient):
    _, reviewer_token, _, annotator_token, annotator = approved_reviewer_and_annotator(client)
    ids = seed_editor_paper("paper_db_save_provenance", suggestion_has_paper_id=False)

    assignment = client.post(
        "/assignments",
        headers=auth_headers(reviewer_token),
        json={"paper_id": "paper_db_save_provenance", "annotator_id": annotator["id"]},
    ).json()
    detail = client.get("/paper/paper_db_save_provenance", headers=auth_headers(annotator_token)).json()
    relation = detail["relations"][0]
    save = client.post(
        "/paper/paper_db_save_provenance/relations/save",
        headers=auth_headers(annotator_token),
        json={"dataset": "raw", "paper_id": "paper_db_save_provenance", "editor_mode": "paragraph", "relations": [relation]},
    )

    from sqlalchemy import text
    from app.database import engine

    with engine.connect() as connection:
        row = connection.execute(text(
            """
            SELECT asr.suggested_relation_id, asr.action
            FROM annotation_submission_relations asr
            JOIN annotation_submissions sub ON sub.id = asr.submission_id
            WHERE sub.assignment_id = :assignment_id
            ORDER BY sub.version DESC
            LIMIT 1
            """
        ), {"assignment_id": assignment["id"]}).mappings().first()

    assert save.status_code == 200
    assert row is not None
    assert row["suggested_relation_id"] == ids["suggestion"]
    assert row["action"] == "keep"


def test_paragraph_comments_are_saved_and_loaded_with_submission(client: TestClient):
    _, reviewer_token, reviewer, annotator_token, annotator = approved_reviewer_and_annotator(client)
    ids = seed_editor_paper("paper_db_paragraph_comment")

    assignment = client.post(
        "/assignments",
        headers=auth_headers(reviewer_token),
        json={"paper_id": "paper_db_paragraph_comment", "annotator_id": annotator["id"]},
    ).json()
    detail = client.get("/paper/paper_db_paragraph_comment", headers=auth_headers(annotator_token)).json()
    relation = detail["relations"][0]
    paragraph_id = detail["paragraphs"][0]["paragraph_id"]

    save = client.post(
        "/paper/paper_db_paragraph_comment/relations/save",
        headers=auth_headers(annotator_token),
        json={
            "dataset": "raw",
            "paper_id": "paper_db_paragraph_comment",
            "editor_mode": "paragraph",
            "relations": [relation],
            "paragraph_comments": [{"paragraph_id": paragraph_id, "comment_text": "  Verify the direction of this relation.  "}],
        },
    )
    loaded = client.get("/paper/paper_db_paragraph_comment", headers=auth_headers(annotator_token))

    assert save.status_code == 200
    assert loaded.status_code == 200
    assert loaded.json()["paragraph_comments"] == [{
        "paragraph_id": paragraph_id,
        "comment_text": "Verify the direction of this relation.",
    }]

    submission_id = client.post(
        f"/assignments/{assignment['id']}/submit",
        headers=auth_headers(annotator_token),
    ).json()["submission_id"]
    review_detail = client.get(
        f"/review/submissions/{submission_id}",
        headers=auth_headers(reviewer_token),
    )

    from sqlalchemy import text
    from app.database import engine

    with engine.connect() as connection:
        stored = connection.execute(text(
            """
            SELECT paragraph_id, author_id, comment_text
            FROM annotation_paragraph_comments
            WHERE submission_id = :submission_id
            """
        ), {"submission_id": submission_id}).mappings().one()

    assert review_detail.status_code == 200
    assert review_detail.json()["paper"]["paragraph_comments"][0]["comment_text"] == "Verify the direction of this relation."
    assert stored["paragraph_id"] == ids["paragraph"]
    assert stored["author_id"] == annotator["id"]
    assert stored["comment_text"] == "Verify the direction of this relation."

    reviewer_update = client.post(
        "/paper/paper_db_paragraph_comment/paragraph-comments/save",
        headers=auth_headers(reviewer_token),
        json={
            "paper_id": "paper_db_paragraph_comment",
            "paragraph_comments": [{"paragraph_id": paragraph_id, "comment_text": "Reviewer updated this paragraph comment."}],
        },
    )
    updated_editor = client.get("/paper/paper_db_paragraph_comment", headers=auth_headers(reviewer_token))

    with engine.connect() as connection:
        annotator_snapshot = connection.execute(text(
            """
            SELECT author_id, comment_text
            FROM annotation_paragraph_comments
            WHERE submission_id = :submission_id
            """
        ), {"submission_id": submission_id}).mappings().one()
        reviewer_stored = connection.execute(text(
            """
            SELECT sub.id AS submission_id, sub.parent_submission_id, sub.editor_role,
                   comment.author_id, comment.comment_text
            FROM annotation_submissions sub
            JOIN annotation_paragraph_comments comment ON comment.submission_id = sub.id
            WHERE sub.assignment_id = :assignment_id
            ORDER BY sub.version DESC
            LIMIT 1
            """
        ), {"assignment_id": assignment["id"]}).mappings().one()

    assert reviewer_update.status_code == 200
    assert updated_editor.status_code == 200
    assert updated_editor.json()["paragraph_comments"] == [{
        "paragraph_id": paragraph_id,
        "comment_text": "Reviewer updated this paragraph comment.",
    }]
    assert annotator_snapshot["author_id"] == annotator["id"]
    assert annotator_snapshot["comment_text"] == "Verify the direction of this relation."
    assert reviewer_stored["author_id"] == reviewer["id"]
    assert reviewer_stored["comment_text"] == "Reviewer updated this paragraph comment."
    assert reviewer_stored["submission_id"] != submission_id
    assert reviewer_stored["parent_submission_id"] == submission_id
    assert reviewer_stored["editor_role"] == "reviewer"

    reviewer_clear = client.post(
        "/paper/paper_db_paragraph_comment/paragraph-comments/save",
        headers=auth_headers(reviewer_token),
        json={"paper_id": "paper_db_paragraph_comment", "paragraph_comments": []},
    )
    cleared_editor = client.get("/paper/paper_db_paragraph_comment", headers=auth_headers(reviewer_token))
    assert reviewer_clear.status_code == 200
    assert cleared_editor.json()["paragraph_comments"] == []

    reviewer_add = client.post(
        "/paper/paper_db_paragraph_comment/paragraph-comments/save",
        headers=auth_headers(reviewer_token),
        json={
            "paper_id": "paper_db_paragraph_comment",
            "paragraph_comments": [{"paragraph_id": paragraph_id, "comment_text": "Reviewer added a replacement comment."}],
        },
    )
    assert reviewer_add.status_code == 200

    annotator_forbidden = client.post(
        "/paper/paper_db_paragraph_comment/paragraph-comments/save",
        headers=auth_headers(annotator_token),
        json={"paper_id": "paper_db_paragraph_comment", "paragraph_comments": []},
    )
    assert annotator_forbidden.status_code == 403


def test_free_form_relation_uses_the_full_paragraph_as_evidence(client: TestClient):
    _, reviewer_token, _, annotator_token, annotator = approved_reviewer_and_annotator(client)
    seed_editor_paper("paper_free_form_evidence")
    client.post(
        "/assignments",
        headers=auth_headers(reviewer_token),
        json={"paper_id": "paper_free_form_evidence", "annotator_id": annotator["id"]},
    )
    detail = client.get("/paper/paper_free_form_evidence", headers=auth_headers(annotator_token)).json()
    paragraph = detail["paragraphs"][0]
    relation = {
        **detail["relations"][0],
        "relation_id": "custom_test_free_form",
        "sentence_id": "",
        "subject_text": "custom subject",
        "subject_type": "custom",
        "predicate": "customPredicate",
        "object_text": "custom object",
        "object_type": "custom",
        "evidence_text": "",
        "relation_origin": "",
        "support_sentence_ids": "",
        "support_paragraph_id": paragraph["paragraph_id"],
    }

    saved = client.post(
        "/paper/paper_free_form_evidence/relations/save",
        headers=auth_headers(annotator_token),
        json={
            "dataset": "raw",
            "paper_id": "paper_free_form_evidence",
            "editor_mode": "paragraph",
            "relations": [relation],
        },
    )
    reloaded = client.get("/paper/paper_free_form_evidence", headers=auth_headers(annotator_token))

    assert saved.status_code == 200
    assert reloaded.status_code == 200
    assert reloaded.json()["relations"][0]["evidence_text"] == paragraph["text"]
    assert reloaded.json()["relations"][0]["relation_origin"] == "manual_edit"


def test_db_backed_editor_missing_paper_returns_structured_404(client: TestClient):
    token = admin_token(client)
    refresh_me(client, token)

    response = client.get("/paper/does_not_exist", headers=auth_headers(token))

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "paper_not_found"
    assert "hint" in response.json()["detail"]


def test_db_backed_editor_save_failure_is_local_and_structured(client: TestClient, monkeypatch):
    from app.data_errors import DataServiceError
    from app.services import db_editor_service

    token = admin_token(client)
    refresh_me(client, token)
    seed_editor_paper("paper_db_save_failure")

    def fail_save(*args, **kwargs):
        raise DataServiceError(503, "relation_save_failed", "Relations could not be saved.", "Your unsaved work is still visible.", "paper_db_save_failure")

    monkeypatch.setattr(db_editor_service, "save_relations", fail_save)
    failed = client.post(
        "/paper/paper_db_save_failure/relations/save",
        headers=auth_headers(token),
        json={"dataset": "raw", "paper_id": "paper_db_save_failure", "editor_mode": "paragraph", "relations": []},
    )
    papers = client.get("/papers", headers=auth_headers(token))

    assert failed.status_code == 503
    assert failed.json()["detail"]["code"] == "relation_save_failed"
    assert papers.status_code == 200


def approved_reviewer_and_annotator(client: TestClient):
    admin = admin_token(client)
    refresh_me(client, admin)
    reviewer_token = firebase_token(client, "workflow-reviewer@example.com", verified=True, name="Workflow Reviewer")
    reviewer = register_profile(client, reviewer_token, full_name="Workflow Reviewer", role="reviewer")
    client.post(f"/admin/signup-requests/{reviewer['id']}/approve", headers=auth_headers(admin))
    annotator_token = firebase_token(client, "workflow-annotator@example.com", verified=True, name="Workflow Annotator")
    annotator = register_profile(client, annotator_token, full_name="Workflow Annotator", role="annotator")
    client.post(f"/reviewer/signup-requests/{annotator['id']}/approve", headers=auth_headers(reviewer_token))
    return admin, reviewer_token, reviewer, annotator_token, annotator


def test_reviewer_can_browse_all_papers_but_edit_only_owned_assignments(client: TestClient):
    _, reviewer_token, _, annotator_token, annotator = approved_reviewer_and_annotator(client)
    seed_editor_paper("paper_reviewer_assigned")
    seed_editor_paper("paper_reviewer_browse_only", with_relation_predicate=False)
    assignment = client.post(
        "/assignments",
        headers=auth_headers(reviewer_token),
        json={"paper_id": "paper_reviewer_assigned", "annotator_id": annotator["id"]},
    )
    assert assignment.status_code == 200

    reviewer_papers = client.get("/papers", headers=auth_headers(reviewer_token))
    browse_only_detail = client.get("/paper/paper_reviewer_browse_only", headers=auth_headers(reviewer_token))
    assert reviewer_papers.status_code == 200
    assert {paper["paper_id"] for paper in reviewer_papers.json()} == {
        "paper_reviewer_assigned",
        "paper_reviewer_browse_only",
    }
    assert browse_only_detail.status_code == 200
    assert browse_only_detail.json()["assignment"] is None

    browse_only_save = client.post(
        "/paper/paper_reviewer_browse_only/relations/save",
        headers=auth_headers(reviewer_token),
        json={
            "dataset": "raw",
            "paper_id": "paper_reviewer_browse_only",
            "editor_mode": "paragraph",
            "relations": browse_only_detail.json()["relations"],
        },
    )
    assert browse_only_save.status_code == 403

    annotator_papers = client.get("/papers", headers=auth_headers(annotator_token))
    annotator_unassigned_detail = client.get(
        "/paper/paper_reviewer_browse_only",
        headers=auth_headers(annotator_token),
    )
    assert annotator_papers.status_code == 200
    assert [paper["paper_id"] for paper in annotator_papers.json()] == ["paper_reviewer_assigned"]
    assert annotator_unassigned_detail.status_code == 403


def test_assignment_due_date_rejects_past_dates_and_accepts_today(client: TestClient):
    _, reviewer_token, _, _, annotator = approved_reviewer_and_annotator(client)
    seed_editor_paper("paper_assignment_due_date")
    past_due_at = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    today_due_at = datetime.now(timezone.utc).date()

    past = client.post(
        "/assignments",
        headers=auth_headers(reviewer_token),
        json={
            "paper_id": "paper_assignment_due_date",
            "annotator_id": annotator["id"],
            "due_at": past_due_at.isoformat(),
        },
    )
    today = client.post(
        "/assignments",
        headers=auth_headers(reviewer_token),
        json={
            "paper_id": "paper_assignment_due_date",
            "annotator_id": annotator["id"],
            "due_at": today_due_at.isoformat(),
        },
    )

    assert past.status_code == 400
    assert past.json()["detail"] == "Assignment due date cannot be earlier than today"
    assert today.status_code == 200
    assert today.json()["due_at"] == today_due_at.isoformat()


def test_assignment_submit_review_approve_and_export_flow(client: TestClient):
    _, reviewer_token, _, annotator_token, annotator = approved_reviewer_and_annotator(client)
    seed_editor_paper("paper_workflow_approve")

    create = client.post(
        "/assignments",
        headers=auth_headers(reviewer_token),
        json={"paper_id": "paper_workflow_approve", "annotator_id": annotator["id"]},
    )
    assert create.status_code == 200
    assignment = create.json()
    assert assignment["status"] == "assigned"

    duplicate = client.post(
        "/assignments",
        headers=auth_headers(reviewer_token),
        json={"paper_id": "paper_workflow_approve", "annotator_id": annotator["id"]},
    )
    assert duplicate.status_code == 400

    papers = client.get("/papers", headers=auth_headers(annotator_token))
    assert papers.status_code == 200
    assert [paper["paper_id"] for paper in papers.json()] == ["paper_workflow_approve"]

    detail = client.get("/paper/paper_workflow_approve", headers=auth_headers(annotator_token))
    assert detail.status_code == 200
    relation = detail.json()["relations"][0]
    save = client.post(
        "/paper/paper_workflow_approve/relations/save",
        headers=auth_headers(annotator_token),
        json={"dataset": "raw", "paper_id": "paper_workflow_approve", "editor_mode": "paragraph", "relations": [relation]},
    )
    assert save.status_code == 200

    submit = client.post(f"/assignments/{assignment['id']}/submit", headers=auth_headers(annotator_token))
    assert submit.status_code == 200
    submission_id = submit.json()["submission_id"]

    blocked_save = client.post(
        "/paper/paper_workflow_approve/relations/save",
        headers=auth_headers(annotator_token),
        json={"dataset": "raw", "paper_id": "paper_workflow_approve", "editor_mode": "paragraph", "relations": [relation]},
    )
    assert blocked_save.status_code == 400

    queue = client.get("/review/submissions?status=submitted", headers=auth_headers(reviewer_token))
    assert queue.status_code == 200
    assert queue.json()[0]["submission_id"] == submission_id

    approve = client.post(
        f"/review/submissions/{submission_id}/approve",
        headers=auth_headers(reviewer_token),
        json={"comment": "Looks good"},
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"

    exported = client.get("/exports/papers/paper_workflow_approve?format=csv", headers=auth_headers(reviewer_token))
    assert exported.status_code == 200
    assert "Plasma source" in exported.text
    assert "measures" in exported.text
    assert "sentence_id" not in exported.text.splitlines()[0].split(",")
    assert "confidence" not in exported.text.splitlines()[0].split(",")


def test_export_uses_only_the_latest_approved_submission(client: TestClient):
    from uuid import uuid4

    from sqlalchemy import text

    from app.database import engine

    _, reviewer_token, reviewer, annotator_token, annotator = approved_reviewer_and_annotator(client)
    ids = seed_editor_paper("paper_latest_approved_export")

    def approve_version(predicate: str) -> str:
        assignment = client.post(
            "/assignments",
            headers=auth_headers(reviewer_token),
            json={"paper_id": "paper_latest_approved_export", "annotator_id": annotator["id"]},
        ).json()
        detail = client.get("/paper/paper_latest_approved_export", headers=auth_headers(annotator_token)).json()
        relation = {**detail["relations"][0], "predicate": predicate}
        saved = client.post(
            "/paper/paper_latest_approved_export/relations/save",
            headers=auth_headers(annotator_token),
            json={
                "dataset": "raw",
                "paper_id": "paper_latest_approved_export",
                "editor_mode": "paragraph",
                "relations": [relation],
            },
        )
        assert saved.status_code == 200
        submission_id = client.post(
            f"/assignments/{assignment['id']}/submit",
            headers=auth_headers(annotator_token),
        ).json()["submission_id"]
        approved = client.post(
            f"/review/submissions/{submission_id}/approve",
            headers=auth_headers(reviewer_token),
            json={"comment": f"Approved {predicate}"},
        )
        assert approved.status_code == 200
        return submission_id

    first_submission_id = approve_version("firstApprovedPredicate")
    second_submission_id = approve_version("latestApprovedPredicate")
    assert first_submission_id != second_submission_id

    with engine.begin() as connection:
        first_relation_id = connection.execute(text(
            "SELECT id FROM annotation_submission_relations WHERE submission_id = :submission_id LIMIT 1"
        ), {"submission_id": first_submission_id}).scalar_one()
        connection.execute(text(
            """
            INSERT INTO final_annotations (
                id, paper_id, approved_submission_id, source_submission_relation_id, approved_by_id,
                sentence_id, support_paragraph_id, subject_text, subject_type, predicate,
                object_text, object_type, confidence, evidence_text, relation_origin, approved_at
            ) VALUES (
                :id, :paper_id, :submission_id, :source_relation_id, :approved_by_id,
                :sentence_id, :paragraph_id, 'old subject', 'custom', 'staleApprovedPredicate',
                'old object', 'custom', 1.0, 'old evidence', 'test', :approved_at
            )
            """
        ), {
            "id": str(uuid4()),
            "paper_id": ids["paper"],
            "submission_id": first_submission_id,
            "source_relation_id": first_relation_id,
            "approved_by_id": reviewer["id"],
            "sentence_id": ids["sentence"],
            "paragraph_id": ids["paragraph"],
            "approved_at": "2999-01-01 00:00:00",
        })

    exported = client.get(
        "/exports/papers/paper_latest_approved_export?format=json",
        headers=auth_headers(reviewer_token),
    )

    assert exported.status_code == 200
    records = exported.json()
    assert [record["predicate"] for record in records] == ["latestApprovedPredicate"]
    assert "sentence_id" not in records[0]
    assert "confidence" not in records[0]


def test_reviewer_can_return_and_annotator_can_resubmit(client: TestClient):
    _, reviewer_token, _, annotator_token, annotator = approved_reviewer_and_annotator(client)
    seed_editor_paper("paper_workflow_return")

    assignment = client.post(
        "/assignments",
        headers=auth_headers(reviewer_token),
        json={"paper_id": "paper_workflow_return", "annotator_id": annotator["id"]},
    ).json()
    detail = client.get("/paper/paper_workflow_return", headers=auth_headers(annotator_token)).json()
    relation = detail["relations"][0]
    client.post(
        "/paper/paper_workflow_return/relations/save",
        headers=auth_headers(annotator_token),
        json={"dataset": "raw", "paper_id": "paper_workflow_return", "editor_mode": "paragraph", "relations": [relation]},
    )
    submission_id = client.post(f"/assignments/{assignment['id']}/submit", headers=auth_headers(annotator_token)).json()["submission_id"]

    returned = client.post(
        f"/review/submissions/{submission_id}/return",
        headers=auth_headers(reviewer_token),
        json={"comment": "Please check evidence"},
    )
    assert returned.status_code == 200
    assert returned.json()["status"] == "returned"

    returned_detail = client.get("/paper/paper_workflow_return", headers=auth_headers(annotator_token))
    assert returned_detail.status_code == 200
    assert returned_detail.json()["assignment"]["status"] == "returned"
    assert "Please check evidence" in returned_detail.json()["assignment"]["latest_review_comment"]

    relation["predicate"] = "relatesTo"
    resave = client.post(
        "/paper/paper_workflow_return/relations/save",
        headers=auth_headers(annotator_token),
        json={
            "dataset": "raw",
            "paper_id": "paper_workflow_return",
            "editor_mode": "paragraph",
            "base_submission_id": submission_id,
            "relations": [relation],
        },
    )
    assert resave.status_code == 200
    resubmit = client.post(f"/assignments/{assignment['id']}/submit", headers=auth_headers(annotator_token))
    assert resubmit.status_code == 200
    assert resubmit.json()["assignment"]["status"] == "submitted"


def test_reviewer_edits_create_immutable_revision_and_bidirectional_diff(client: TestClient):
    from sqlalchemy import text

    from app.database import engine

    _, reviewer_token, reviewer, annotator_token, annotator = approved_reviewer_and_annotator(client)
    seed_editor_paper("paper_revision_handoff")
    assignment = client.post(
        "/assignments",
        headers=auth_headers(reviewer_token),
        json={"paper_id": "paper_revision_handoff", "annotator_id": annotator["id"]},
    ).json()

    annotator_detail = client.get("/paper/paper_revision_handoff", headers=auth_headers(annotator_token)).json()
    initial_relation = annotator_detail["relations"][0]
    client.post(
        "/paper/paper_revision_handoff/relations/save",
        headers=auth_headers(annotator_token),
        json={
            "dataset": "raw",
            "paper_id": "paper_revision_handoff",
            "editor_mode": "paragraph",
            "relations": [initial_relation],
        },
    )
    annotator_submission_id = client.post(
        f"/assignments/{assignment['id']}/submit",
        headers=auth_headers(annotator_token),
    ).json()["submission_id"]

    reviewer_detail = client.get("/paper/paper_revision_handoff", headers=auth_headers(reviewer_token)).json()
    reviewer_relation = {**reviewer_detail["relations"][0], "predicate": "reviewerUpdatedPredicate"}
    reviewer_save = client.post(
        "/paper/paper_revision_handoff/relations/save",
        headers=auth_headers(reviewer_token),
        json={
            "dataset": "raw",
            "paper_id": "paper_revision_handoff",
            "editor_mode": "paragraph",
            "base_submission_id": annotator_submission_id,
            "relations": [reviewer_relation],
            "paragraph_comments": [{
                "paragraph_id": reviewer_detail["paragraphs"][0]["paragraph_id"],
                "comment_text": "Reviewer changed the predicate.",
            }],
        },
    )
    assert reviewer_save.status_code == 200

    reviewer_draft = client.get("/paper/paper_revision_handoff", headers=auth_headers(reviewer_token)).json()
    reviewer_submission_id = reviewer_draft["revision"]["submission_id"]
    assert reviewer_draft["assignment"]["status"] == "review_in_progress"
    assert reviewer_draft["revision"]["status"] == "review_draft"
    assert reviewer_draft["revision"]["parent_submission_id"] == annotator_submission_id
    assert reviewer_draft["revision"]["created_by_id"] == reviewer["id"]
    assert reviewer_draft["changes"]["modified"][0]["before"]["predicate"] == initial_relation["predicate"]
    assert reviewer_draft["changes"]["modified"][0]["after"]["predicate"] == "reviewerUpdatedPredicate"
    assert reviewer_draft["changes"]["paragraph_comments"][0]["after_text"] == "Reviewer changed the predicate."

    with engine.connect() as connection:
        original_predicate = connection.execute(text(
            "SELECT predicate FROM annotation_submission_relations WHERE submission_id = :submission_id"
        ), {"submission_id": annotator_submission_id}).scalar_one()
    assert original_predicate == initial_relation["predicate"]

    returned = client.post(
        f"/review/submissions/{reviewer_submission_id}/return",
        headers=auth_headers(reviewer_token),
        json={"comment": "Please review my predicate update."},
    )
    assert returned.status_code == 200
    annotator_returned = client.get("/paper/paper_revision_handoff", headers=auth_headers(annotator_token)).json()
    assert annotator_returned["revision"]["status"] == "returned"
    assert annotator_returned["changes"]["modified"][0]["after"]["predicate"] == "reviewerUpdatedPredicate"
    assert "Please review my predicate update." in annotator_returned["assignment"]["latest_review_comment"]

    annotator_revision = {**annotator_returned["relations"][0], "object_text": "annotator revised object"}
    annotator_resave = client.post(
        "/paper/paper_revision_handoff/relations/save",
        headers=auth_headers(annotator_token),
        json={
            "dataset": "raw",
            "paper_id": "paper_revision_handoff",
            "editor_mode": "paragraph",
            "base_submission_id": reviewer_submission_id,
            "relations": [annotator_revision],
            "paragraph_comments": annotator_returned["paragraph_comments"],
        },
    )
    assert annotator_resave.status_code == 200
    resubmitted = client.post(
        f"/assignments/{assignment['id']}/submit",
        headers=auth_headers(annotator_token),
    )
    assert resubmitted.status_code == 200

    reviewer_resubmission = client.get("/paper/paper_revision_handoff", headers=auth_headers(reviewer_token)).json()
    assert reviewer_resubmission["revision"]["parent_submission_id"] == reviewer_submission_id
    assert reviewer_resubmission["changes"]["modified"][0]["before"]["object_text"] != "annotator revised object"
    assert reviewer_resubmission["changes"]["modified"][0]["after"]["object_text"] == "annotator revised object"

    stale_save = client.post(
        "/paper/paper_revision_handoff/relations/save",
        headers=auth_headers(reviewer_token),
        json={
            "dataset": "raw",
            "paper_id": "paper_revision_handoff",
            "editor_mode": "paragraph",
            "base_submission_id": annotator_submission_id,
            "relations": reviewer_resubmission["relations"],
        },
    )
    assert stale_save.status_code == 409

    resubmitted_submission_id = reviewer_resubmission["revision"]["submission_id"]
    final_reviewer_relation = {
        **reviewer_resubmission["relations"][0],
        "predicate": "finalReviewerApprovedPredicate",
    }
    final_reviewer_save = client.post(
        "/paper/paper_revision_handoff/relations/save",
        headers=auth_headers(reviewer_token),
        json={
            "dataset": "raw",
            "paper_id": "paper_revision_handoff",
            "editor_mode": "paragraph",
            "base_submission_id": resubmitted_submission_id,
            "relations": [final_reviewer_relation],
            "paragraph_comments": reviewer_resubmission["paragraph_comments"],
        },
    )
    assert final_reviewer_save.status_code == 200
    final_reviewer_draft = client.get("/paper/paper_revision_handoff", headers=auth_headers(reviewer_token)).json()
    final_reviewer_submission_id = final_reviewer_draft["revision"]["submission_id"]
    approved = client.post(
        f"/review/submissions/{final_reviewer_submission_id}/approve",
        headers=auth_headers(reviewer_token),
        json={"comment": "Approved after final reviewer edit."},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    exported = client.get(
        "/exports/papers/paper_revision_handoff?format=json",
        headers=auth_headers(reviewer_token),
    )
    assert exported.status_code == 200
    assert exported.json()[0]["predicate"] == "finalReviewerApprovedPredicate"
