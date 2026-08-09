from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from flask import current_app
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from chargemate.auth.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterUserRequest,
)
from chargemate.auth.tokens import (
    IssuedAccessToken,
    IssuedRefreshToken,
    hash_refresh_token,
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


class RefreshTokenError(Exception):
    """Raised when a refresh token cannot produce a new token pair."""


class PasswordChangeError(Exception):
    """Raised when an authenticated password change cannot be accepted."""


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


def rotate_auth_session(raw_refresh_token: str) -> IssuedSessionTokens:
    """Rotate an active refresh session and detect revoked-token reuse."""
    now = datetime.now(UTC)
    token_hash = hash_refresh_token(raw_refresh_token)
    issued_tokens: IssuedSessionTokens | None = None
    refresh_failed = False

    with db.session.begin():
        session = db.session.scalar(
            select(AuthSession)
            .where(AuthSession.token_hash == token_hash)
            .with_for_update()
        )

        if session is None:
            refresh_failed = True
        elif session.is_revoked:
            _revoke_token_family(session.family_id, now)
            refresh_failed = True
        elif _is_expired(session.expires_at, now):
            session.revoked_at = now
            refresh_failed = True
        elif not session.user.is_active:
            _revoke_token_family(session.family_id, now)
            refresh_failed = True
        else:
            replacement_token = issue_refresh_token(now=now)
            replacement_session = AuthSession(
                user_id=session.user_id,
                token_hash=replacement_token.digest,
                family_id=session.family_id,
                expires_at=replacement_token.expires_at,
            )
            db.session.add(replacement_session)
            db.session.flush()

            session.revoked_at = now
            session.last_used_at = now
            session.replaced_by_id = replacement_session.id

            access_token = issue_access_token(
                session.user,
                replacement_session.id,
                now=now,
            )
            issued_tokens = IssuedSessionTokens(
                replacement_session,
                access_token,
                replacement_token,
            )

    if refresh_failed or issued_tokens is None:
        raise RefreshTokenError("Refresh token is invalid or expired.")

    return issued_tokens


def revoke_auth_session(session_id: UUID, user_id: UUID) -> bool:
    """Idempotently revoke one session owned by the authenticated user."""
    try:
        session = db.session.scalar(
            select(AuthSession)
            .where(
                AuthSession.id == session_id,
                AuthSession.user_id == user_id,
            )
            .with_for_update()
        )
        was_revoked = session is not None and not session.is_revoked
        if was_revoked:
            session.revoked_at = datetime.now(UTC)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return was_revoked


def revoke_all_auth_sessions(user_id: UUID) -> int:
    """Revoke every active refresh session belonging to one user."""
    try:
        result = db.session.execute(
            update(AuthSession)
            .where(
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return result.rowcount


def change_user_password(
    user_id: UUID,
    data: ChangePasswordRequest,
) -> None:
    """Change a password and atomically revoke every login session."""

    now = datetime.now(UTC)
    try:
        user = db.session.scalar(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
        )
        if user is None or not user.check_password(
            data.current_password.get_secret_value()
        ):
            raise PasswordChangeError("Current password is incorrect.")
        new_password = data.new_password.get_secret_value()
        if user.check_password(new_password):
            raise PasswordChangeError(
                "New password must be different from the current password."
            )

        user.set_password(new_password)
        db.session.execute(
            update(AuthSession)
            .where(
                AuthSession.user_id == user.id,
                AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        db.session.commit()
    except PasswordChangeError:
        db.session.rollback()
        raise
    except Exception:
        db.session.rollback()
        raise


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


def _is_expired(expires_at: datetime, now: datetime) -> bool:
    """Compare expiration safely when a test database returns naive time."""
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= now


def _revoke_token_family(family_id: UUID, revoked_at: datetime) -> None:
    """Revoke every still-active refresh session in a rotation family."""
    db.session.execute(
        update(AuthSession)
        .where(
            AuthSession.family_id == family_id,
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=revoked_at)
    )
