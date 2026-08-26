from __future__ import annotations

from dataclasses import dataclass

from app import firebase_auth


@dataclass(frozen=True)
class FakeUidIdentifier:
    uid: str


@dataclass(frozen=True)
class FakeUserRecord:
    uid: str
    email_verified: bool


class FakeGetUsersResult:
    def __init__(self, users: list[FakeUserRecord]):
        self.users = users


class FakeAuthModule:
    UidIdentifier = FakeUidIdentifier

    def __init__(self):
        self.batch_sizes: list[int] = []

    def get_users(self, identifiers: list[FakeUidIdentifier], *, app: object) -> FakeGetUsersResult:
        del app
        self.batch_sizes.append(len(identifiers))
        return FakeGetUsersResult(
            [FakeUserRecord(identifier.uid, identifier.uid.endswith("0")) for identifier in identifiers]
        )


def test_email_verification_lookup_deduplicates_and_batches_firebase_uids(monkeypatch):
    fake_auth = FakeAuthModule()
    monkeypatch.setattr(firebase_auth, "_load_firebase_modules", lambda: (object(), fake_auth, object()))
    monkeypatch.setattr(firebase_auth, "get_firebase_app", lambda: object())
    firebase_uids = [f"uid-{index}" for index in range(205)] + ["uid-0", "", "   "]

    statuses = firebase_auth.get_firebase_email_verification_statuses(firebase_uids)

    assert fake_auth.batch_sizes == [100, 100, 5]
    assert len(statuses) == 205
    assert statuses["uid-0"] is True
    assert statuses["uid-1"] is False
