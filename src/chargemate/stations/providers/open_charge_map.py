from typing import Any

import httpx

from chargemate.stations.schemas import ExternalStationSearchQuery


OPEN_CHARGE_MAP_POI_URL = "https://api.openchargemap.io/v3/poi/"
OPEN_CHARGE_MAP_DETAILS_URL = "https://openchargemap.org/site/poi/details"
PROVIDER_TIMEOUT_SECONDS = 5.0


class ExternalStationProviderError(Exception):
    """Raised when Open Charge Map cannot provide a valid response."""


def fetch_open_charge_map_stations(
    query: ExternalStationSearchQuery,
    api_key: str,
) -> list[dict[str, Any]]:
    """Fetch and normalize nearby open-data charging locations."""

    try:
        response = httpx.get(
            OPEN_CHARGE_MAP_POI_URL,
            params={
                "key": api_key,
                "output": "json",
                "latitude": str(query.latitude),
                "longitude": str(query.longitude),
                "distance": str(query.radius_km),
                "distanceunit": "KM",
                "maxresults": query.max_results,
                "compact": "false",
                "verbose": "false",
                "opendata": "true",
            },
            headers={"User-Agent": "ChargeMate/0.1"},
            timeout=PROVIDER_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError, TypeError) as error:
        raise ExternalStationProviderError from error

    if not isinstance(payload, list):
        raise ExternalStationProviderError

    stations = []
    for point_of_interest in payload:
        normalized = _normalize_station(point_of_interest)
        if normalized is not None:
            stations.append(normalized)
    return stations


def _normalize_station(point_of_interest: Any) -> dict[str, Any] | None:
    if not isinstance(point_of_interest, dict):
        return None

    address = _mapping(point_of_interest.get("AddressInfo"))
    external_id = point_of_interest.get("ID")
    latitude = address.get("Latitude")
    longitude = address.get("Longitude")
    if external_id is None or not _valid_coordinates(latitude, longitude):
        return None

    status = _mapping(point_of_interest.get("StatusType"))
    operator = _mapping(point_of_interest.get("OperatorInfo"))
    data_provider = _mapping(point_of_interest.get("DataProvider"))
    country = _mapping(address.get("Country"))

    return {
        "source": "open_charge_map",
        "external_id": str(external_id),
        "name": address.get("Title") or f"Charging station {external_id}",
        "address": {
            "line_1": address.get("AddressLine1"),
            "town": address.get("Town"),
            "state": address.get("StateOrProvince"),
            "postal_code": address.get("Postcode"),
            "country_code": country.get("ISOCode"),
        },
        "latitude": float(latitude),
        "longitude": float(longitude),
        "distance_km": _optional_float(address.get("Distance")),
        "operator": operator.get("Title"),
        "usage_cost": point_of_interest.get("UsageCost"),
        "is_operational": status.get("IsOperational"),
        "status": status.get("Title"),
        "connections": _normalize_connections(
            point_of_interest.get("Connections")
        ),
        "data_provider": data_provider.get("Title"),
        "details_url": f"{OPEN_CHARGE_MAP_DETAILS_URL}/{external_id}",
        "bookable": False,
    }


def _normalize_connections(connections: Any) -> list[dict[str, Any]]:
    if not isinstance(connections, list):
        return []

    normalized = []
    for connection in connections:
        if not isinstance(connection, dict):
            continue
        connection_type = _mapping(connection.get("ConnectionType"))
        current_type = _mapping(connection.get("CurrentType"))
        normalized.append(
            {
                "type": connection_type.get("Title"),
                "power_kw": _optional_float(connection.get("PowerKW")),
                "current_type": current_type.get("Title"),
                "quantity": connection.get("Quantity"),
            }
        )
    return normalized


def _valid_coordinates(latitude: Any, longitude: Any) -> bool:
    try:
        latitude_value = float(latitude)
        longitude_value = float(longitude)
    except (TypeError, ValueError):
        return False
    return -90 <= latitude_value <= 90 and -180 <= longitude_value <= 180


def _optional_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
