from collections.abc import Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar
from uuid import UUID

from flask import g, request

from chargemate.auth.tokens import AccessTokenError, decode_access_token
from chargemate.extensions import db
from chargemate.models.user import User


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

        user = db.session.get(User, UUID(claims["sub"]))
        if user is None or not user.is_active:
            return _unauthorized_response()

        g.current_user = user
        g.access_claims = claims
        return view(*args, **kwargs)

    return wrapped


def _unauthorized_response() -> tuple[dict[str, Any], int]:
    """Return one generic response for every access-token failure."""
    return {
        "error": {
            "code": "unauthorized",
            "message": "A valid access token is required.",
        }
    }, 401
