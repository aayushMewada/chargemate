from decimal import Decimal

from flask import Blueprint, current_app, g, request
from pydantic import ValidationError

from chargemate.auth.decorators import roles_required
from chargemate.models.charge_point import ChargePoint
from chargemate.models.station import ChargingStation
from chargemate.models.user import UserRole
from chargemate.security.rate_limit import rate_limit
from chargemate.stations.external_service import find_external_stations
from chargemate.stations.providers.open_charge_map import (
    ExternalStationProviderError,
)
from chargemate.stations.cache import (
    get_cached_station_search,
    store_station_search,
)
from chargemate.stations.schemas import (
    ChargePointUpdateRequest,
    ExternalStationSearchQuery,
    OwnedStationListQuery,
    StationCreateRequest,
    StationSearchQuery,
    StationUpdateRequest,
)
from chargemate.stations.service import (
    StationConflictError,
    StationNotFoundError,
    StationStateConflictError,
    create_station,
    find_owned_stations,
    find_public_stations,
    get_public_station,
    update_charge_point,
    update_station,
)


stations_blueprint = Blueprint("stations", __name__, url_prefix="/stations")


@stations_blueprint.get("/external")
@rate_limit(
    "stations:external",
    requests_config="EXTERNAL_STATION_RATE_LIMIT_REQUESTS",
)
def list_external_charging_stations():
    """Return normalized open-data charging locations near a coordinate."""

    try:
        query = ExternalStationSearchQuery.model_validate(request.args)
        stations = find_external_stations(query)
    except ValidationError as error:
        return _validation_error_response(error)
    except ExternalStationProviderError:
        current_app.logger.warning(
            "External charging-station provider is unavailable."
        )
        return {
            "error": {
                "code": "external_station_provider_unavailable",
                "message": "External charging stations are temporarily unavailable.",
            }
        }, 503

    return {
        "stations": stations,
        "source": "open_charge_map",
        "bookable": False,
    }, 200


@stations_blueprint.get("")
def list_charging_stations():
    """Return a filtered, paginated list of active stations."""

    try:
        query = StationSearchQuery.model_validate(request.args)
    except ValidationError as error:
        return _validation_error_response(error)

    cache_key, cached_response = get_cached_station_search(query)
    if cached_response is not None:
        return cached_response, 200

    station_page = find_public_stations(query)
    response_body = {
        "stations": [
            _serialize_station(
                result.station,
                distance_km=result.distance_km,
            )
            for result in station_page.items
        ],
        "pagination": {
            "page": station_page.page,
            "per_page": station_page.per_page,
            "total": station_page.total,
            "pages": (
                station_page.total + station_page.per_page - 1
            )
            // station_page.per_page,
        },
    }
    store_station_search(cache_key, response_body)
    return response_body, 200


@stations_blueprint.get("/<uuid:station_id>")
def get_charging_station(station_id):
    """Return one active station or a generic not-found response."""

    station = get_public_station(station_id)
    if station is None:
        return {
            "error": {
                "code": "station_not_found",
                "message": "The charging station was not found.",
            }
        }, 404

    return {"station": _serialize_station(station)}, 200


@stations_blueprint.get("/mine")
@roles_required(UserRole.STATION_ADMIN, UserRole.SYSTEM_ADMIN)
def list_my_stations():
    """Return all station states owned by the current administrator."""

    try:
        query = OwnedStationListQuery.model_validate(request.args)
    except ValidationError as error:
        return _validation_error_response(error)

    page = find_owned_stations(g.current_user.id, query)
    return {
        "stations": [_serialize_station(station) for station in page.items],
        "pagination": {
            "page": page.page,
            "per_page": page.per_page,
            "total": page.total,
            "pages": (page.total + page.per_page - 1) // page.per_page,
        },
    }, 200


@stations_blueprint.post("")
@roles_required(UserRole.STATION_ADMIN, UserRole.SYSTEM_ADMIN)
def create_charging_station():
    """Create a station owned by the authenticated administrator."""

    try:
        payload = StationCreateRequest.model_validate(request.get_json(silent=True))
        station = create_station(g.current_user, payload)
    except ValidationError as error:
        return _validation_error_response(error)
    except StationConflictError:
        return {
            "error": {
                "code": "station_conflict",
                "message": "The station conflicts with existing data.",
            }
        }, 409

    return {"station": _serialize_station(station)}, 201


@stations_blueprint.patch("/<uuid:station_id>")
@roles_required(UserRole.STATION_ADMIN, UserRole.SYSTEM_ADMIN)
def update_my_station(station_id):
    """Update an owned station using its expected version."""

    try:
        payload = StationUpdateRequest.model_validate(request.get_json(silent=True))
        station = update_station(g.current_user, station_id, payload)
    except ValidationError as error:
        return _validation_error_response(error)
    except StationNotFoundError:
        return _station_not_found_response()
    except StationStateConflictError:
        return _state_conflict_response()
    except StationConflictError:
        return _station_conflict_response()

    return {"station": _serialize_station(station)}, 200


@stations_blueprint.patch(
    "/<uuid:station_id>/charge-points/<uuid:charge_point_id>"
)
@roles_required(UserRole.STATION_ADMIN, UserRole.SYSTEM_ADMIN)
def update_my_charge_point(station_id, charge_point_id):
    """Update one charge point belonging to an owned station."""

    try:
        payload = ChargePointUpdateRequest.model_validate(
            request.get_json(silent=True)
        )
        charge_point = update_charge_point(
            g.current_user,
            station_id,
            charge_point_id,
            payload,
        )
    except ValidationError as error:
        return _validation_error_response(error)
    except StationNotFoundError:
        return _station_not_found_response()
    except StationStateConflictError:
        return _state_conflict_response()
    except StationConflictError:
        return _station_conflict_response()

    return {"charge_point": _serialize_charge_point(charge_point)}, 200


def _serialize_station(
    station: ChargingStation,
    *,
    distance_km: float | None = None,
) -> dict:
    serialized = {
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
        "version": station.version,
        "charge_points": [
            _serialize_charge_point(charge_point)
            for charge_point in station.charge_points
        ],
        "created_at": station.created_at.isoformat(),
    }
    if distance_km is not None:
        serialized["distance_km"] = round(distance_km, 2)
    return serialized


def _serialize_charge_point(charge_point: ChargePoint) -> dict:
    return {
        "id": str(charge_point.id),
        "code": charge_point.code,
        "connector_type": charge_point.connector_type.value,
        "power_type": charge_point.power_type.value,
        "max_power_kw": _decimal_to_float(charge_point.max_power_kw),
        "booking_fee": _decimal_to_float(charge_point.booking_fee),
        "is_bookable": charge_point.is_bookable,
        "status": charge_point.status.value,
        "version": charge_point.version,
    }


def _decimal_to_float(value: Decimal) -> float:
    return float(value)


def _validation_error_response(error: ValidationError) -> tuple[dict, int]:
    return {
        "error": {
            "code": "validation_error",
            "message": "The request data is invalid.",
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


def _station_not_found_response() -> tuple[dict, int]:
    return {
        "error": {
            "code": "station_not_found",
            "message": "The charging station was not found.",
        }
    }, 404


def _state_conflict_response() -> tuple[dict, int]:
    return {
        "error": {
            "code": "station_state_conflict",
            "message": "The station data changed or violates an operational rule.",
        }
    }, 409


def _station_conflict_response() -> tuple[dict, int]:
    return {
        "error": {
            "code": "station_conflict",
            "message": "The station conflicts with existing data.",
        }
    }, 409
