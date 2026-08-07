from typing import Any

from flask import Blueprint, request
from pydantic import ValidationError

from chargemate.auth.schemas import LoginRequest, RegisterUserRequest
from chargemate.auth.service import (
    AuthenticationError,
    RegistrationConflictError,
    authenticate_user,
    register_user,
)
from chargemate.models.user import User


auth_blueprint = Blueprint("auth", __name__, url_prefix="/auth")


@auth_blueprint.post("/register")
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
def login() -> tuple[dict[str, Any], int]:
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

    return {"user": _serialize_user(user)}, 200


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
