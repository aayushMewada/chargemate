from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from typing import Any, ParamSpec, TypeVar
from uuid import UUID

from flask import g, request
from sqlalchemy import select

from chargemate.auth.tokens import AccessTokenError, decode_access_token
from chargemate.extensions import db
from chargemate.models.auth_session import AuthSession
from chargemate.models.user import User, UserRole


P = ParamSpec("P")
R = TypeVar("R")


def access_token_required(view: Callable[P, R]) -> Callable[P, R | tuple[dict, int]]:
    """Require a valid bearer token and active user for a Flask view."""

    @wraps(view)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R | tuple[dict, int]:
        authorization = request.headers.get("Authorization", "")
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return _unauthorized_response()

        try:
            claims = decode_access_token(parts[1])
        except AccessTokenError:
            return _unauthorized_response()

        try:
            user_id = UUID(claims["sub"])
            session_id = UUID(claims["sid"])
        except (KeyError, TypeError, ValueError):
            return _unauthorized_response()

        user = db.session.get(User, user_id)
        active_session_id = db.session.scalar(
            select(AuthSession.id).where(
                AuthSession.id == session_id,
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > datetime.now(UTC),
            )
        )
        if user is None or not user.is_active or active_session_id is None:
            return _unauthorized_response()

        g.current_user = user
        g.access_claims = claims
        return view(*args, **kwargs)

    return wrapped


def roles_required(
    *allowed_roles: UserRole,
) -> Callable[[Callable[P, R]], Callable[P, R | tuple[dict, int]]]:
    """Require a valid access token and membership in an allowed role."""

    def decorator(view: Callable[P, R]) -> Callable[P, R | tuple[dict, int]]:
        @wraps(view)
        def authorized_view(*args: P.args, **kwargs: P.kwargs):
            if g.current_user.role not in allowed_roles:
                return {
                    "error": {
                        "code": "forbidden",
                        "message": "You do not have permission to perform this action.",
                    }
                }, 403
            return view(*args, **kwargs)

        return access_token_required(authorized_view)

    return decorator


def _unauthorized_response() -> tuple[dict[str, Any], int]:
    """Return one generic response for every access-token failure."""
    return {
        "error": {
            "code": "unauthorized",
            "message": "A valid access token is required.",
        }
    }, 401
