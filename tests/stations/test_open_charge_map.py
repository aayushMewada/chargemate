import httpx
import pytest

from chargemate.stations.providers.open_charge_map import (
    ExternalStationProviderError,
    fetch_open_charge_map_stations,
)
from chargemate.stations.schemas import ExternalStationSearchQuery


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


def _external_query() -> ExternalStationSearchQuery:
    return ExternalStationSearchQuery(
        latitude="22.753284",
        longitude="75.893696",
        radius_km="25",
        max_results=50,
    )


def test_open_charge_map_response_is_normalized(monkeypatch):
    captured_request = {}
    provider_payload = [
        {
            "ID": 12345,
            "AddressInfo": {
                "Title": "Public Fast Charger",
                "AddressLine1": "Vijay Nagar",
                "Town": "Indore",
                "StateOrProvince": "Madhya Pradesh",
                "Postcode": "452010",
                "Country": {"ISOCode": "IN"},
                "Latitude": 22.753284,
                "Longitude": 75.893696,
                "Distance": 2.4,
            },
            "OperatorInfo": {"Title": "Example Operator"},
            "StatusType": {"Title": "Operational", "IsOperational": True},
            "UsageCost": "Paid",
            "Connections": [
                {
                    "ConnectionType": {"Title": "CCS (Type 2)"},
                    "CurrentType": {"Title": "DC"},
                    "PowerKW": 60,
                    "Quantity": 2,
                }
            ],
            "DataProvider": {"Title": "Open Charge Map Contributors"},
            "UnexpectedPrivateField": "must not be proxied",
        }
    ]

    def fake_get(url, **kwargs):
        captured_request["url"] = url
        captured_request.update(kwargs)
        return FakeResponse(provider_payload)

    monkeypatch.setattr(httpx, "get", fake_get)

    stations = fetch_open_charge_map_stations(
        _external_query(),
        "test-api-key",
    )

    assert captured_request["params"]["key"] == "test-api-key"
    assert captured_request["params"]["opendata"] == "true"
    assert stations == [
        {
            "source": "open_charge_map",
            "external_id": "12345",
            "name": "Public Fast Charger",
            "address": {
                "line_1": "Vijay Nagar",
                "town": "Indore",
                "state": "Madhya Pradesh",
                "postal_code": "452010",
                "country_code": "IN",
            },
            "latitude": 22.753284,
            "longitude": 75.893696,
            "distance_km": 2.4,
            "operator": "Example Operator",
            "usage_cost": "Paid",
            "is_operational": True,
            "status": "Operational",
            "connections": [
                {
                    "type": "CCS (Type 2)",
                    "power_kw": 60.0,
                    "current_type": "DC",
                    "quantity": 2,
                }
            ],
            "data_provider": "Open Charge Map Contributors",
            "details_url": "https://openchargemap.org/site/poi/details/12345",
            "bookable": False,
        }
    ]


def test_open_charge_map_network_failure_is_converted(monkeypatch):
    def failing_get(url, **_kwargs):
        request = httpx.Request("GET", url)
        raise httpx.ConnectTimeout("provider timed out", request=request)

    monkeypatch.setattr(httpx, "get", failing_get)

    with pytest.raises(ExternalStationProviderError):
        fetch_open_charge_map_stations(_external_query(), "test-api-key")


def test_external_station_route_uses_normalized_service(client, monkeypatch):
    expected = [{"source": "open_charge_map", "external_id": "123"}]
    monkeypatch.setattr(
        "chargemate.stations.routes.find_external_stations",
        lambda _query: expected,
    )

    response = client.get(
        "/stations/external"
        "?latitude=22.753284&longitude=75.893696&radius_km=25"
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "stations": expected,
        "source": "open_charge_map",
        "bookable": False,
    }


def test_external_station_route_requires_coordinates(client):
    response = client.get("/stations/external?radius_km=25")

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "validation_error"
