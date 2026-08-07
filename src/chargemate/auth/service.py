from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from flask import current_app
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from chargemate.auth.schemas import LoginRequest, RegisterUserRequest
from chargemate.auth.tokens import (
    IssuedAccessToken,
    IssuedRefreshToken,
    issue_access_token,
    issue_refresh_token,
)
from chargemate.extensions import db
from chargemate.models.auth_session import AuthSession
from chargemate.models.user import User


USER_IDENTITY_CONSTRAINTS = {
    "uq_users_email",
    "uq_users_phone",
    "uq_users_username",
}

DUMMY_PASSWORD_HASH = generate_password_hash(
    "not-a-real-user-password",
    method="scrypt",
)


class RegistrationConflictError(Exception):
    """Raised when registration identifiers already belong to a user."""


class AuthenticationError(Exception):
    """Raised when credentials cannot authenticate an active user."""


@dataclass(frozen=True, slots=True)
class IssuedSessionTokens:
    """The persisted session and tokens created for one successful login."""

    session: AuthSession
    access_token: IssuedAccessToken
    refresh_token: IssuedRefreshToken


def register_user(data: RegisterUserRequest) -> User:
    """Create and persist a user from validated registration data."""
    identifiers = [
        User.email == str(data.email),
        User.username == data.username,
    ]
    if data.phone is not None:
        identifiers.append(User.phone == data.phone)

    try:
        with db.session.begin():
            existing_user = db.session.execute(
                select(User.id).where(or_(*identifiers)).limit(1)
            ).first()
            if existing_user is not None:
                raise RegistrationConflictError(
                    "Registration details are already in use."
                )

            user = User(
                email=str(data.email),
                username=data.username,
                full_name=data.full_name,
                phone=data.phone,
            )
            user.set_password(data.password)
            db.session.add(user)
    except IntegrityError as error:
        constraint_name = getattr(
            getattr(error.orig, "diag", None),
            "constraint_name",
            None,
        )
        if constraint_name in USER_IDENTITY_CONSTRAINTS:
            raise RegistrationConflictError(
                "Registration details are already in use."
            ) from error

        raise

    return user


def authenticate_user(data: LoginRequest) -> User:
    """Verify credentials and update the user's login security state."""
    identifier = data.identifier
    password = data.password.get_secret_value()
    now = datetime.now(UTC)
    authenticated_user: User | None = None
    authentication_failed = False

    with db.session.begin():
        user = db.session.scalar(
            select(User).where(
                or_(
                    User.email == identifier,
                    User.username == identifier,
                )
            )
        )

        if user is None:
            check_password_hash(DUMMY_PASSWORD_HASH, password)
            authentication_failed = True
        else:
            password_matches = user.check_password(password)

            if _is_account_locked(user, now) or not user.is_active:
                authentication_failed = True
            else:
                if user.locked_until is not None:
                    user.failed_login_attempts = 0
                    user.locked_until = None

                if not password_matches:
                    _record_failed_login(user, now)
                    authentication_failed = True
                else:
                    user.failed_login_attempts = 0
                    user.locked_until = None
                    authenticated_user = user

    if authentication_failed or authenticated_user is None:
        raise AuthenticationError("Invalid identifier or password.")

    return authenticated_user


def create_auth_session(user: User) -> IssuedSessionTokens:
    """Persist a refresh session and issue its initial token pair."""
    refresh_token = issue_refresh_token()

    with db.session.begin():
        session = AuthSession(
            user=user,
            token_hash=refresh_token.digest,
            expires_at=refresh_token.expires_at,
        )
        db.session.add(session)
        db.session.flush()
        access_token = issue_access_token(user, session.id)

    return IssuedSessionTokens(session, access_token, refresh_token)


def _is_account_locked(user: User, now: datetime) -> bool:
    """Return whether the user's lockout time is still in the future."""
    if user.locked_until is None:
        return False

    locked_until = user.locked_until
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=UTC)

    return locked_until > now


def _record_failed_login(user: User, now: datetime) -> None:
    """Increment failures and lock the account when the limit is reached."""
    user.failed_login_attempts += 1
    maximum_attempts = current_app.config["LOGIN_MAX_FAILED_ATTEMPTS"]

    if user.failed_login_attempts >= maximum_attempts:
        lockout_minutes = current_app.config["LOGIN_LOCKOUT_MINUTES"]
        user.locked_until = now + timedelta(minutes=lockout_minutes)
