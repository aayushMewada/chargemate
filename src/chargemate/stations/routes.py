from decimal import Decimal

from flask import Blueprint, g, request
from pydantic import ValidationError

from chargemate.auth.decorators import roles_required
from chargemate.models.charge_point import ChargePoint
from chargemate.models.station import ChargingStation
from chargemate.models.user import UserRole
from chargemate.stations.schemas import StationCreateRequest
from chargemate.stations.service import StationConflictError, create_station


stations_blueprint = Blueprint("stations", __name__, url_prefix="/stations")


@stations_blueprint.post("")
@roles_required(UserRole.STATION_ADMIN, UserRole.SYSTEM_ADMIN)
def create_charging_station():
    """Create a station owned by the authenticated administrator."""

    try:
        payload = StationCreateRequest.model_validate(request.get_json(silent=True))
        station = create_station(g.current_user, payload)
    except ValidationError as error:
        return {
            "error": {
                "code": "validation_error",
                "message": "The station data is invalid.",
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
    except StationConflictError:
        return {
            "error": {
                "code": "station_conflict",
                "message": "The station conflicts with existing data.",
            }
        }, 409

    return {"station": _serialize_station(station)}, 201


def _serialize_station(station: ChargingStation) -> dict:
    return {
        "id": str(station.id),
        "owner_id": str(station.owner_id),
        "name": station.name,
        "description": station.description,
        "address_line_1": station.address_line_1,
        "address_line_2": station.address_line_2,
        "city": station.city,
        "state": station.state,
        "postal_code": station.postal_code,
        "country_code": station.country_code,
        "latitude": _decimal_to_float(station.latitude),
        "longitude": _decimal_to_float(station.longitude),
        "timezone": station.timezone,
        "phone": station.phone,
        "is_24_hours": station.is_24_hours,
        "status": station.status.value,
        "charge_points": [
            _serialize_charge_point(charge_point)
            for charge_point in station.charge_points
        ],
        "created_at": station.created_at.isoformat(),
    }


def _serialize_charge_point(charge_point: ChargePoint) -> dict:
    return {
        "id": str(charge_point.id),
        "code": charge_point.code,
        "connector_type": charge_point.connector_type.value,
        "power_type": charge_point.power_type.value,
        "max_power_kw": _decimal_to_float(charge_point.max_power_kw),
        "is_bookable": charge_point.is_bookable,
        "status": charge_point.status.value,
    }


def _decimal_to_float(value: Decimal) -> float:
    return float(value)
