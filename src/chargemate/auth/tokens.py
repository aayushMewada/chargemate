from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import secrets
from typing import Any
from uuid import UUID, uuid4

from flask import current_app
import jwt
from jwt import InvalidTokenError

from chargemate.models.user import User, UserRole


class AccessTokenError(Exception):
    """Raised when an access token cannot be safely accepted."""


@dataclass(frozen=True, slots=True)
class IssuedAccessToken:
    """A signed access token and its server-calculated metadata."""

    value: str
    expires_at: datetime
    token_id: UUID


@dataclass(frozen=True, slots=True)
class IssuedRefreshToken:
    """A raw refresh token, its digest, and its expiration time."""

    value: str
    digest: str
    expires_at: datetime


def issue_access_token(
    user: User,
    session_id: UUID,
    *,
    now: datetime | None = None,
) -> IssuedAccessToken:
    """Create a signed, short-lived JWT for one authenticated session."""
    issued_at = _aware_utc(now)
    expires_at = issued_at + timedelta(
        minutes=current_app.config["JWT_ACCESS_TOKEN_MINUTES"]
    )
    token_id = uuid4()
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "type": "access",
        "sid": str(session_id),
        "jti": str(token_id),
        "iat": issued_at,
        "exp": expires_at,
        "iss": current_app.config["JWT_ISSUER"],
        "aud": current_app.config["JWT_AUDIENCE"],
    }
    value = jwt.encode(
        payload,
        current_app.config["JWT_SECRET_KEY"],
        algorithm=current_app.config["JWT_ALGORITHM"],
    )
    return IssuedAccessToken(value, expires_at, token_id)


def decode_access_token(token: str) -> dict[str, Any]:
    """Verify an access token and return its trusted claims."""
    try:
        payload = jwt.decode(
            token,
            current_app.config["JWT_SECRET_KEY"],
            algorithms=[current_app.config["JWT_ALGORITHM"]],
            audience=current_app.config["JWT_AUDIENCE"],
            issuer=current_app.config["JWT_ISSUER"],
            options={
                "require": [
                    "sub",
                    "role",
                    "type",
                    "sid",
                    "jti",
                    "iat",
                    "exp",
                    "iss",
                    "aud",
                ]
            },
        )
        if payload["type"] != "access":
            raise AccessTokenError("Access token is invalid or expired.")

        UUID(payload["sub"])
        UUID(payload["sid"])
        UUID(payload["jti"])
        UserRole(payload["role"])
    except (InvalidTokenError, KeyError, TypeError, ValueError) as error:
        raise AccessTokenError("Access token is invalid or expired.") from error

    return payload


def issue_refresh_token(
    *,
    now: datetime | None = None,
) -> IssuedRefreshToken:
    """Create a high-entropy opaque refresh token and its stored digest."""
    issued_at = _aware_utc(now)
    expires_at = issued_at + timedelta(
        days=current_app.config["JWT_REFRESH_TOKEN_DAYS"]
    )
    value = secrets.token_urlsafe(48)
    return IssuedRefreshToken(value, hash_refresh_token(value), expires_at)


def hash_refresh_token(token: str) -> str:
    """Return the SHA-256 hexadecimal digest stored in PostgreSQL."""
    return sha256(token.encode("utf-8")).hexdigest()


def _aware_utc(value: datetime | None) -> datetime:
    """Return an aware UTC timestamp and reject ambiguous naive input."""
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        raise ValueError("Token timestamps must include timezone information.")
    return value.astimezone(UTC)
