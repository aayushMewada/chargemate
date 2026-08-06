from typing import Any

from flask import Blueprint, request
from pydantic import ValidationError

from chargemate.auth.schemas import RegisterUserRequest
from chargemate.auth.service import RegistrationConflictError, register_user
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
                "message": "Registration data is invalid.",
                "details": details,
            }
        }, 422

    try:
        user = register_user(registration_data)
    except RegistrationConflictError as error:
        return _error_response("registration_conflict", str(error), 409)

    return {"user": _serialize_user(user)}, 201


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
