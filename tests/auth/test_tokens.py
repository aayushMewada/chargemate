from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from chargemate.auth.tokens import (
    AccessTokenError,
    decode_access_token,
    hash_refresh_token,
    issue_access_token,
    issue_refresh_token,
)
from chargemate.models.user import User, UserRole


def token_user() -> User:
    """Build the minimum user data required for an access token."""
    return User(id=uuid4(), role=UserRole.USER)


def test_access_token_contains_verified_session_claims(db_app) -> None:
    user = token_user()
    session_id = uuid4()

    issued = issue_access_token(user, session_id)
    claims = decode_access_token(issued.value)

    assert claims["sub"] == str(user.id)
    assert claims["sid"] == str(session_id)
    assert claims["jti"] == str(issued.token_id)
    assert claims["role"] == "user"
    assert claims["type"] == "access"


def test_access_token_rejects_signature_tampering(db_app) -> None:
    issued = issue_access_token(token_user(), uuid4())

    with pytest.raises(AccessTokenError):
        decode_access_token(f"{issued.value}tampered")


def test_refresh_tokens_are_unique_and_hashed(db_app) -> None:
    now = datetime.now(UTC)

    first = issue_refresh_token(now=now)
    second = issue_refresh_token(now=now)

    assert first.value != second.value
    assert first.digest != second.digest
    assert first.digest == hash_refresh_token(first.value)
    assert len(first.digest) == 64
    assert first.expires_at == now + timedelta(days=30)


def test_token_issuance_rejects_naive_timestamps(db_app) -> None:
    naive_time = datetime.now()

    with pytest.raises(ValueError):
        issue_refresh_token(now=naive_time)
