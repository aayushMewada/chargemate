from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from chargemate.auth.schemas import RegisterUserRequest
from chargemate.auth.service import RegistrationConflictError, register_user
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
