from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from chargemate.auth.tokens import issue_refresh_token
from chargemate.extensions import db
from chargemate.models.auth_session import AuthSession
from chargemate.models.user import User


def test_auth_session_is_persisted_and_linked_to_user(db_app) -> None:
    refresh_token = issue_refresh_token()
    user = User(
        email="session-user@example.com",
        username="session_user",
        full_name="Session User",
    )
    user.set_password("a-long-test-password")
    session = AuthSession(
        user=user,
        token_hash=refresh_token.digest,
        expires_at=refresh_token.expires_at,
    )

    with db.session.begin():
        db.session.add(session)
        db.session.flush()
        session_id = session.id

    db.session.remove()
    stored_session = db.session.scalar(
        select(AuthSession).where(AuthSession.id == session_id)
    )

    assert stored_session is not None
    assert stored_session.user.email == "session-user@example.com"
    assert stored_session.family_id is not None
    assert not stored_session.is_revoked

    stored_session.revoked_at = datetime.now(UTC) + timedelta(seconds=1)
    assert stored_session.is_revoked
