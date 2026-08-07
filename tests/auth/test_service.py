from uuid import UUID
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from chargemate.auth.schemas import LoginRequest, RegisterUserRequest
from chargemate.auth.service import (
    AuthenticationError,
    RegistrationConflictError,
    RefreshTokenError,
    authenticate_user,
    create_auth_session,
    register_user,
    rotate_auth_session,
)
from chargemate.auth.tokens import decode_access_token
from chargemate.extensions import db
from chargemate.models.auth_session import AuthSession
from chargemate.models.user import User, UserRole


def registration_data(**overrides: str | None) -> RegisterUserRequest:
    """Build valid registration data with optional field overrides."""
    values = {
        "email": "driver@example.com",
        "username": "driver_one",
        "password": "a-long-test-password",
        "full_name": "Test Driver",
        "phone": "+919876543210",
    }
    values.update(overrides)
    return RegisterUserRequest(**values)


def login_data(
    identifier: str = "driver@example.com",
    password: str = "a-long-test-password",
) -> LoginRequest:
    """Build validated login credentials."""
    return LoginRequest(identifier=identifier, password=password)


def test_register_user_persists_user_and_hashes_password(db_app) -> None:
    data = registration_data()

    user = register_user(data)
    stored_user = db.session.scalar(select(User).where(User.id == user.id))

    assert stored_user is not None
    assert stored_user.email == "driver@example.com"
    assert stored_user.role is UserRole.USER
    assert stored_user.password_hash != data.password
    assert stored_user.check_password(data.password)


def test_register_user_rejects_existing_identity(db_app) -> None:
    register_user(registration_data())
    db.session.remove()

    with pytest.raises(RegistrationConflictError):
        register_user(
            registration_data(
                username="another_driver",
                phone=None,
            )
        )

    user_count = db.session.scalar(select(func.count()).select_from(User))
    assert user_count == 1


def test_register_user_translates_concurrent_unique_violation(
    db_app,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_error = SimpleNamespace(
        diag=SimpleNamespace(constraint_name="uq_users_email")
    )
    integrity_error = IntegrityError("INSERT", {}, original_error)

    def raise_integrity_error():
        raise integrity_error

    monkeypatch.setattr(db.session, "begin", raise_integrity_error)

    with pytest.raises(RegistrationConflictError):
        register_user(registration_data())


def test_authenticate_user_accepts_valid_credentials(db_app) -> None:
    register_user(registration_data())
    db.session.remove()

    user = authenticate_user(login_data(identifier="driver_one"))

    assert user.email == "driver@example.com"
    assert user.failed_login_attempts == 0
    assert user.locked_until is None


def test_authenticate_user_records_failed_password(db_app) -> None:
    register_user(registration_data())
    db.session.remove()

    with pytest.raises(AuthenticationError):
        authenticate_user(login_data(password="incorrect-password"))

    user = db.session.scalar(
        select(User).where(User.email == "driver@example.com")
    )
    assert user is not None
    assert user.failed_login_attempts == 1
    assert user.locked_until is None


def test_authenticate_user_locks_account_after_five_failures(db_app) -> None:
    register_user(registration_data())
    db.session.remove()

    for _ in range(5):
        with pytest.raises(AuthenticationError):
            authenticate_user(login_data(password="incorrect-password"))

    with pytest.raises(AuthenticationError):
        authenticate_user(login_data())

    user = db.session.scalar(
        select(User).where(User.email == "driver@example.com")
    )
    assert user is not None
    assert user.failed_login_attempts == 5
    assert user.locked_until is not None


def test_authenticate_user_hides_unknown_accounts(db_app) -> None:
    with pytest.raises(AuthenticationError) as error:
        authenticate_user(login_data(identifier="missing@example.com"))

    assert str(error.value) == "Invalid identifier or password."


def test_create_auth_session_stores_only_refresh_digest(db_app) -> None:
    user = register_user(registration_data())

    issued = create_auth_session(user)
    claims = decode_access_token(issued.access_token.value)
    session_id = UUID(claims["sid"])
    user_id = UUID(claims["sub"])

    db.session.remove()
    stored_session = db.session.scalar(
        select(AuthSession).where(AuthSession.id == session_id)
    )

    assert stored_session is not None
    assert stored_session.user_id == user_id
    assert stored_session.token_hash == issued.refresh_token.digest
    assert stored_session.token_hash != issued.refresh_token.value
    assert claims["sub"] == str(user_id)


def test_rotate_auth_session_revokes_old_and_creates_replacement(db_app) -> None:
    user = register_user(registration_data())
    initial = create_auth_session(user)
    initial_claims = decode_access_token(initial.access_token.value)
    initial_session_id = UUID(initial_claims["sid"])

    db.session.remove()
    rotated = rotate_auth_session(initial.refresh_token.value)
    rotated_claims = decode_access_token(rotated.access_token.value)
    replacement_session_id = UUID(rotated_claims["sid"])

    db.session.remove()
    initial_session = db.session.get(AuthSession, initial_session_id)
    replacement_session = db.session.get(AuthSession, replacement_session_id)

    assert initial_session is not None
    assert replacement_session is not None
    assert initial_session.is_revoked
    assert initial_session.last_used_at is not None
    assert initial_session.replaced_by_id == replacement_session.id
    assert replacement_session.family_id == initial_session.family_id
    assert not replacement_session.is_revoked
    assert replacement_session.token_hash == rotated.refresh_token.digest


def test_rotate_auth_session_revokes_family_when_old_token_is_reused(
    db_app,
) -> None:
    user = register_user(registration_data())
    initial = create_auth_session(user)

    db.session.remove()
    rotated = rotate_auth_session(initial.refresh_token.value)
    replacement_session_id = UUID(
        decode_access_token(rotated.access_token.value)["sid"]
    )

    db.session.remove()
    with pytest.raises(RefreshTokenError):
        rotate_auth_session(initial.refresh_token.value)

    db.session.remove()
    replacement_session = db.session.get(AuthSession, replacement_session_id)
    assert replacement_session is not None
    assert replacement_session.is_revoked
