from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from chargemate.auth.schemas import LoginRequest, RegisterUserRequest
from chargemate.auth.service import (
    AuthenticationError,
    RegistrationConflictError,
    authenticate_user,
    register_user,
)
from chargemate.extensions import db
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
