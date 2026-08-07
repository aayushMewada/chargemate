from uuid import UUID

from sqlalchemy import func, select

from chargemate.extensions import db
from chargemate.models.charge_point import ChargePoint
from chargemate.models.station import ChargingStation
from chargemate.models.user import User, UserRole


PASSWORD = "Station-Test-Password-2026"


def _register_user(client, suffix: str) -> dict:
    response = client.post(
        "/auth/register",
        json={
            "email": f"{suffix}@example.com",
            "username": suffix,
            "password": PASSWORD,
            "full_name": "Station Test User",
            "phone": None,
        },
    )
    assert response.status_code == 201
    return response.get_json()["user"]


def _promote_user(app, user_id: str, role: UserRole) -> None:
    with app.app_context():
        user = db.session.get(User, UUID(user_id))
        user.role = role
        db.session.commit()


def _login(client, identity: str) -> str:
    response = client.post(
        "/auth/login",
        json={"identifier": identity, "password": PASSWORD},
    )
    assert response.status_code == 200
    return response.get_json()["access_token"]


def _station_payload() -> dict:
    return {
        "name": "ChargeMate Vijay Nagar",
        "description": "Fast charging near the city centre.",
        "address_line_1": "101 Scheme Number 54",
        "address_line_2": None,
        "city": "Indore",
        "state": "Madhya Pradesh",
        "postal_code": "452010",
        "country_code": "in",
        "latitude": 22.753284,
        "longitude": 75.893696,
        "timezone": "Asia/Kolkata",
        "phone": None,
        "is_24_hours": True,
        "charge_points": [
            {
                "code": "cp-01",
                "connector_type": "ccs_2",
                "power_type": "dc",
                "max_power_kw": 60,
                "is_bookable": True,
            },
            {
                "code": "cp-02",
                "connector_type": "type_2",
                "power_type": "ac",
                "max_power_kw": 22,
                "is_bookable": True,
            },
        ],
    }


def test_station_admin_creates_station_and_charge_points(client, app):
    user = _register_user(client, "station_admin")
    _promote_user(app, user["id"], UserRole.STATION_ADMIN)
    access_token = _login(client, user["email"])

    response = client.post(
        "/stations",
        headers={"Authorization": f"Bearer {access_token}"},
        json=_station_payload(),
    )

    assert response.status_code == 201
    station = response.get_json()["station"]
    assert station["owner_id"] == user["id"]
    assert station["country_code"] == "IN"
    assert station["status"] == "draft"
    assert [point["code"] for point in station["charge_points"]] == [
        "CP-01",
        "CP-02",
    ]

    with app.app_context():
        station_count = db.session.scalar(
            select(func.count()).select_from(ChargingStation)
        )
        charge_point_count = db.session.scalar(
            select(func.count()).select_from(ChargePoint)
        )

    assert station_count == 1
    assert charge_point_count == 2


def test_regular_user_cannot_create_station(client):
    user = _register_user(client, "regular_station_user")
    access_token = _login(client, user["email"])

    response = client.post(
        "/stations",
        headers={"Authorization": f"Bearer {access_token}"},
        json=_station_payload(),
    )

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"


def test_duplicate_charge_point_codes_are_rejected(client, app):
    user = _register_user(client, "duplicate_code_admin")
    _promote_user(app, user["id"], UserRole.STATION_ADMIN)
    access_token = _login(client, user["email"])
    payload = _station_payload()
    payload["charge_points"][1]["code"] = "CP-01"

    response = client.post(
        "/stations",
        headers={"Authorization": f"Bearer {access_token}"},
        json=payload,
    )

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "validation_error"

    with app.app_context():
        station_count = db.session.scalar(
            select(func.count()).select_from(ChargingStation)
        )

    assert station_count == 0
