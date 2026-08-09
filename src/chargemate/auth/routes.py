from typing import Any
from uuid import UUID

from flask import Blueprint, Response, current_app, g, jsonify, request
from pydantic import ValidationError

from chargemate.auth.decorators import access_token_required
from chargemate.auth.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterUserRequest,
)
from chargemate.auth.service import (
    AuthenticationError,
    IssuedSessionTokens,
    PasswordChangeError,
    RefreshTokenError,
    RegistrationConflictError,
    authenticate_user,
    change_user_password,
    create_auth_session,
    register_user,
    revoke_all_auth_sessions,
    revoke_auth_session,
    rotate_auth_session,
)
from chargemate.auth.tokens import IssuedRefreshToken
from chargemate.models.user import User
from chargemate.security.rate_limit import rate_limit


auth_blueprint = Blueprint("auth", __name__, url_prefix="/auth")


@auth_blueprint.post("/register")
@rate_limit("auth:register", requests_config="REGISTER_RATE_LIMIT_REQUESTS")
def register() -> tuple[dict[str, Any], int]:
    """Register a user from a validated JSON request."""
    if not request.is_json:
        return _error_response(
            "unsupported_media_type",
            "Content-Type must be application/json.",
            415,
        )

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _error_response(
            "invalid_json",
            "Request body must be a valid JSON object.",
            400,
        )

    try:
        registration_data = RegisterUserRequest.model_validate(payload)
    except ValidationError as error:
        return _validation_error_response(error, "Registration data is invalid.")

    try:
        user = register_user(registration_data)
    except RegistrationConflictError as error:
        return _error_response("registration_conflict", str(error), 409)

    return {"user": _serialize_user(user)}, 201


@auth_blueprint.post("/login")
@rate_limit("auth:login", requests_config="LOGIN_RATE_LIMIT_REQUESTS")
def login() -> Response | tuple[dict[str, Any], int]:
    """Authenticate a user from an email address or username."""
    if not request.is_json:
        return _error_response(
            "unsupported_media_type",
            "Content-Type must be application/json.",
            415,
        )

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _error_response(
            "invalid_json",
            "Request body must be a valid JSON object.",
            400,
        )

    try:
        login_data = LoginRequest.model_validate(payload)
    except ValidationError as error:
        return _validation_error_response(error, "Login data is invalid.")

    try:
        user = authenticate_user(login_data)
    except AuthenticationError as error:
        return _error_response("invalid_credentials", str(error), 401)

    issued = create_auth_session(user)
    return _token_response(user, issued)


@auth_blueprint.post("/refresh")
@rate_limit("auth:refresh", requests_config="REFRESH_RATE_LIMIT_REQUESTS")
def refresh() -> Response | tuple[dict[str, Any], int]:
    """Rotate the refresh cookie and issue a new access token."""
    raw_refresh_token = request.cookies.get(
        current_app.config["REFRESH_COOKIE_NAME"]
    )
    if not raw_refresh_token:
        return _error_response(
            "invalid_refresh_token",
            "Refresh token is invalid or expired.",
            401,
        )

    try:
        issued = rotate_auth_session(raw_refresh_token)
    except RefreshTokenError as error:
        response = jsonify(
            {
                "error": {
                    "code": "invalid_refresh_token",
                    "message": str(error),
                }
            }
        )
        response.status_code = 401
        _clear_refresh_cookie(response)
        return response

    return _token_response(issued.session.user, issued)


@auth_blueprint.get("/me")
@access_token_required
def current_user() -> tuple[dict[str, Any], int]:
    """Return the safe profile of the authenticated user."""
    return {"user": _serialize_user(g.current_user)}, 200


@auth_blueprint.post("/logout")
@access_token_required
def logout() -> Response:
    """Revoke the current login session and remove its refresh cookie."""
    revoke_auth_session(
        UUID(g.access_claims["sid"]),
        g.current_user.id,
    )
    response = Response(status=204)
    _clear_refresh_cookie(response)
    return response


@auth_blueprint.post("/logout-all")
@access_token_required
def logout_all() -> Response:
    """Revoke every refresh session owned by the authenticated user."""
    revoke_all_auth_sessions(g.current_user.id)
    response = Response(status=204)
    _clear_refresh_cookie(response)
    return response


@auth_blueprint.post("/change-password")
@access_token_required
def change_password() -> Response | tuple[dict[str, Any], int]:
    """Replace the password and revoke every existing login session."""

    try:
        payload = ChangePasswordRequest.model_validate(
            request.get_json(silent=True)
        )
        change_user_password(g.current_user.id, payload)
    except ValidationError as error:
        return _validation_error_response(error, "Password data is invalid.")
    except PasswordChangeError as error:
        return _error_response("password_change_rejected", str(error), 422)

    response = Response(status=204)
    _clear_refresh_cookie(response)
    return response


def _token_response(user: User, issued: IssuedSessionTokens) -> Response:
    """Return an access token and rotate the protected refresh cookie."""
    response = jsonify(
        {
            "access_token": issued.access_token.value,
            "token_type": "Bearer",
            "expires_in": (
                current_app.config["JWT_ACCESS_TOKEN_MINUTES"] * 60
            ),
            "user": _serialize_user(user),
        }
    )
    _set_refresh_cookie(response, issued.refresh_token)
    return response


def _serialize_user(user: User) -> dict[str, Any]:
    """Return only user fields that are safe for a public API response."""
    return {
        "id": str(user.id),
        "email": user.email,
        "username": user.username,
        "full_name": user.full_name,
        "phone": user.phone,
        "role": user.role.value,
        "created_at": user.created_at.isoformat(),
    }


def _error_response(
    code: str,
    message: str,
    status: int,
) -> tuple[dict[str, Any], int]:
    """Build the consistent error envelope used by authentication routes."""
    return {"error": {"code": code, "message": message}}, status


def _validation_error_response(
    error: ValidationError,
    message: str,
) -> tuple[dict[str, Any], int]:
    """Serialize validation errors without returning rejected input values."""
    details = [
        {
            "field": ".".join(str(part) for part in issue["loc"]),
            "message": issue["msg"],
            "type": issue["type"],
        }
        for issue in error.errors()
    ]
    return {
        "error": {
            "code": "validation_error",
            "message": message,
            "details": details,
        }
    }, 422


def _set_refresh_cookie(
    response: Response,
    refresh_token: IssuedRefreshToken,
) -> None:
    """Store a refresh token using the configured browser protections."""
    response.set_cookie(
        key=current_app.config["REFRESH_COOKIE_NAME"],
        value=refresh_token.value,
        expires=refresh_token.expires_at,
        httponly=current_app.config["REFRESH_COOKIE_HTTPONLY"],
        secure=current_app.config["REFRESH_COOKIE_SECURE"],
        samesite=current_app.config["REFRESH_COOKIE_SAMESITE"],
        path=current_app.config["REFRESH_COOKIE_PATH"],
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Tell the browser to remove its current refresh-token cookie."""
    response.delete_cookie(
        key=current_app.config["REFRESH_COOKIE_NAME"],
        path=current_app.config["REFRESH_COOKIE_PATH"],
        httponly=current_app.config["REFRESH_COOKIE_HTTPONLY"],
        secure=current_app.config["REFRESH_COOKIE_SECURE"],
        samesite=current_app.config["REFRESH_COOKIE_SAMESITE"],
    )
    PasswordChangeError,
