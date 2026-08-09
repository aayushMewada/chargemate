from flask import Blueprint, g, request
from pydantic import ValidationError

from chargemate.auth.decorators import access_token_required, roles_required
from chargemate.charging_sessions.schemas import (
    ChargingSessionListQuery,
    CompleteChargingSessionRequest,
    StartChargingSessionRequest,
)
from chargemate.charging_sessions.service import (
    ChargingSessionMeterError,
    ChargingSessionForbiddenError,
    ChargingSessionStateConflictError,
    ChargingSessionTimeError,
    complete_charging_session,
    find_user_charging_sessions,
    get_user_charging_session,
    start_charging_session,
)
from chargemate.models.charging_session import ChargingSession
from chargemate.models.user import UserRole


charging_sessions_blueprint = Blueprint(
    "charging_sessions",
    __name__,
    url_prefix="/charging-sessions",
)


@charging_sessions_blueprint.post("")
@roles_required(UserRole.STATION_ADMIN, UserRole.SYSTEM_ADMIN)
def start_session():
    """Start metered usage for one confirmed, user-owned booking."""

    try:
        payload = StartChargingSessionRequest.model_validate(
            request.get_json(silent=True)
        )
        charging_session = start_charging_session(g.current_user, payload)
    except ValidationError as error:
        return _validation_error_response(error)
    except ChargingSessionTimeError:
        return {
            "error": {
                "code": "outside_charging_window",
                "message": "The booking cannot be started at this time.",
            }
        }, 422
    except ChargingSessionForbiddenError:
        return _forbidden_response()
    except ChargingSessionStateConflictError:
        return _state_conflict_response()

    return {"charging_session": _serialize_session(charging_session)}, 201


@charging_sessions_blueprint.post("/<uuid:session_id>/complete")
@roles_required(UserRole.STATION_ADMIN, UserRole.SYSTEM_ADMIN)
def complete_session(session_id):
    """Complete an active session using its final cumulative meter reading."""

    try:
        payload = CompleteChargingSessionRequest.model_validate(
            request.get_json(silent=True)
        )
        charging_session = complete_charging_session(
            g.current_user,
            session_id,
            payload,
        )
    except ValidationError as error:
        return _validation_error_response(error)
    except ChargingSessionMeterError:
        return {
            "error": {
                "code": "invalid_meter_reading",
                "message": "The final meter reading cannot move backwards.",
            }
        }, 422
    except ChargingSessionForbiddenError:
        return _forbidden_response()
    except ChargingSessionStateConflictError:
        return _state_conflict_response()

    return {"charging_session": _serialize_session(charging_session)}, 200


@charging_sessions_blueprint.get("/me")
@access_token_required
def list_my_sessions():
    """Return the authenticated user's filtered charging history."""

    try:
        query = ChargingSessionListQuery.model_validate(request.args)
    except ValidationError as error:
        return _validation_error_response(error)

    page = find_user_charging_sessions(g.current_user.id, query)
    return {
        "charging_sessions": [_serialize_session(item) for item in page.items],
        "pagination": {
            "page": page.page,
            "per_page": page.per_page,
            "total": page.total,
            "pages": (page.total + page.per_page - 1) // page.per_page,
        },
    }, 200


@charging_sessions_blueprint.get("/<uuid:session_id>")
@access_token_required
def get_my_session(session_id):
    """Return one session only when it belongs to the current user."""

    charging_session = get_user_charging_session(g.current_user.id, session_id)
    if charging_session is None:
        return {
            "error": {
                "code": "charging_session_not_found",
                "message": "The charging session was not found.",
            }
        }, 404
    return {"charging_session": _serialize_session(charging_session)}, 200


def _serialize_session(charging_session: ChargingSession) -> dict:
    return {
        "id": str(charging_session.id),
        "booking_id": str(charging_session.booking_id),
        "charge_point_id": str(charging_session.charge_point_id),
        "charge_point": {
            "id": str(charging_session.charge_point.id),
            "code": charging_session.charge_point.code,
            "connector_type": charging_session.charge_point.connector_type.value,
            "power_type": charging_session.charge_point.power_type.value,
            "max_power_kw": float(charging_session.charge_point.max_power_kw),
            "station": {
                "id": str(charging_session.charge_point.station.id),
                "name": charging_session.charge_point.station.name,
                "city": charging_session.charge_point.station.city,
                "state": charging_session.charge_point.station.state,
            },
        },
        "booking_window": {
            "starts_at": charging_session.booking.starts_at.isoformat(),
            "ends_at": charging_session.booking.ends_at.isoformat(),
        },
        "status": charging_session.status.value,
        "started_at": charging_session.started_at.isoformat(),
        "ended_at": (
            charging_session.ended_at.isoformat()
            if charging_session.ended_at is not None
            else None
        ),
        "meter_start_kwh": float(charging_session.meter_start_kwh),
        "meter_end_kwh": (
            float(charging_session.meter_end_kwh)
            if charging_session.meter_end_kwh is not None
            else None
        ),
        "energy_consumed_kwh": (
            float(charging_session.energy_consumed_kwh)
            if charging_session.energy_consumed_kwh is not None
            else None
        ),
        "version": charging_session.version,
        "created_at": charging_session.created_at.isoformat(),
    }


def _validation_error_response(error: ValidationError) -> tuple[dict, int]:
    return {
        "error": {
            "code": "validation_error",
            "message": "The charging-session data is invalid.",
            "details": [
                {
                    "location": list(detail["loc"]),
                    "message": detail["msg"],
                    "type": detail["type"],
                }
                for detail in error.errors(
                    include_url=False,
                    include_input=False,
                )
            ],
        }
    }, 422


def _state_conflict_response() -> tuple[dict, int]:
    return {
        "error": {
            "code": "charging_session_state_conflict",
            "message": "The booking or charging session state has changed.",
        }
    }, 409


def _forbidden_response() -> tuple[dict, int]:
    return {
        "error": {
            "code": "forbidden",
            "message": "You do not control this charge point.",
        }
    }, 403
