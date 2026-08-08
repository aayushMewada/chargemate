from uuid import UUID

from sqlalchemy import func, select

from chargemate.extensions import db
from chargemate.models.charge_point import ChargePoint
from chargemate.models.station import ChargingStation, StationStatus
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


def _create_station(client, access_token: str, payload: dict | None = None) -> dict:
    response = client.post(
        "/stations",
        headers={"Authorization": f"Bearer {access_token}"},
        json=payload or _station_payload(),
    )
    assert response.status_code == 201
    return response.get_json()["station"]


def _activate_station(app, station_id: str) -> None:
    with app.app_context():
        station = db.session.get(ChargingStation, UUID(station_id))
        station.status = StationStatus.ACTIVE
        db.session.commit()


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


def test_public_list_returns_only_active_stations(client, app):
    user = _register_user(client, "public_list_admin")
    _promote_user(app, user["id"], UserRole.STATION_ADMIN)
    access_token = _login(client, user["email"])
    active_station = _create_station(client, access_token)

    draft_payload = _station_payload()
    draft_payload["name"] = "ChargeMate Draft Station"
    _create_station(client, access_token, draft_payload)
    _activate_station(app, active_station["id"])

    response = client.get("/stations?city=indore&page=1&per_page=10")

    assert response.status_code == 200
    body = response.get_json()
    assert [station["id"] for station in body["stations"]] == [
        active_station["id"]
    ]
    assert body["pagination"] == {
        "page": 1,
        "per_page": 10,
        "total": 1,
        "pages": 1,
    }


def test_public_list_filters_on_the_same_available_charge_point(client, app):
    user = _register_user(client, "filter_station_admin")
    _promote_user(app, user["id"], UserRole.STATION_ADMIN)
    access_token = _login(client, user["email"])
    station = _create_station(client, access_token)
    _activate_station(app, station["id"])

    matching = client.get(
        "/stations?connector_type=ccs_2&min_power_kw=50"
    )
    non_matching = client.get(
        "/stations?connector_type=type_2&min_power_kw=50"
    )

    assert matching.status_code == 200
    assert matching.get_json()["pagination"]["total"] == 1
    assert non_matching.status_code == 200
    assert non_matching.get_json()["pagination"]["total"] == 0


def test_public_station_detail_hides_draft_station(client, app):
    user = _register_user(client, "detail_station_admin")
    _promote_user(app, user["id"], UserRole.STATION_ADMIN)
    access_token = _login(client, user["email"])
    station = _create_station(client, access_token)

    hidden_response = client.get(f"/stations/{station['id']}")
    _activate_station(app, station["id"])
    visible_response = client.get(f"/stations/{station['id']}")

    assert hidden_response.status_code == 404
    assert visible_response.status_code == 200
    assert visible_response.get_json()["station"]["id"] == station["id"]


def test_public_list_rejects_invalid_or_unknown_query_parameters(client):
    invalid_page = client.get("/stations?page=0")
    unknown_filter = client.get("/stations?secret_status=active")
    incomplete_location = client.get(
        "/stations?latitude=22.75&longitude=75.89"
    )

    assert invalid_page.status_code == 422
    assert invalid_page.get_json()["error"]["code"] == "validation_error"
    assert unknown_filter.status_code == 422
    assert unknown_filter.get_json()["error"]["code"] == "validation_error"
    assert incomplete_location.status_code == 422
    assert incomplete_location.get_json()["error"]["code"] == "validation_error"


def test_station_admin_lists_only_owned_stations(client, app):
    first_user = _register_user(client, "owned_station_admin")
    _promote_user(app, first_user["id"], UserRole.STATION_ADMIN)
    first_token = _login(client, first_user["email"])
    owned_station = _create_station(client, first_token)

    second_user = _register_user(client, "other_station_admin")
    _promote_user(app, second_user["id"], UserRole.STATION_ADMIN)
    second_token = _login(client, second_user["email"])
    _create_station(client, second_token)

    response = client.get(
        "/stations/mine",
        headers={"Authorization": f"Bearer {first_token}"},
    )

    assert response.status_code == 200
    assert response.get_json()["pagination"]["total"] == 1
    assert response.get_json()["stations"][0]["id"] == owned_station["id"]


def test_station_update_increments_version(client, app):
    user = _register_user(client, "update_station_admin")
    _promote_user(app, user["id"], UserRole.STATION_ADMIN)
    token = _login(client, user["email"])
    station = _create_station(client, token)

    response = client.patch(
        f"/stations/{station['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "version": 1,
            "name": "ChargeMate Updated Station",
            "status": "active",
        },
    )

    assert response.status_code == 200
    updated = response.get_json()["station"]
    assert updated["name"] == "ChargeMate Updated Station"
    assert updated["status"] == "active"
    assert updated["version"] == 2


def test_stale_station_update_is_rejected(client, app):
    user = _register_user(client, "stale_station_admin")
    _promote_user(app, user["id"], UserRole.STATION_ADMIN)
    token = _login(client, user["email"])
    station = _create_station(client, token)
    first = client.patch(
        f"/stations/{station['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"version": 1, "name": "First Dashboard Edit"},
    )

    stale = client.patch(
        f"/stations/{station['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"version": 1, "name": "Stale Dashboard Edit"},
    )

    assert first.status_code == 200
    assert stale.status_code == 409
    assert stale.get_json()["error"]["code"] == "station_state_conflict"


def test_station_admin_cannot_edit_another_owners_station(client, app):
    owner = _register_user(client, "protected_station_owner")
    _promote_user(app, owner["id"], UserRole.STATION_ADMIN)
    owner_token = _login(client, owner["email"])
    station = _create_station(client, owner_token)

    other = _register_user(client, "station_update_intruder")
    _promote_user(app, other["id"], UserRole.STATION_ADMIN)
    other_token = _login(client, other["email"])
    response = client.patch(
        f"/stations/{station['id']}",
        headers={"Authorization": f"Bearer {other_token}"},
        json={"version": 1, "name": "Unauthorized Edit"},
    )

    assert response.status_code == 404


def test_charge_point_update_increments_its_own_version(client, app):
    user = _register_user(client, "update_point_admin")
    _promote_user(app, user["id"], UserRole.STATION_ADMIN)
    token = _login(client, user["email"])
    station = _create_station(client, token)
    charge_point = station["charge_points"][0]

    response = client.patch(
        f"/stations/{station['id']}/charge-points/{charge_point['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "version": 1,
            "booking_fee": "99.00",
            "is_bookable": False,
        },
    )

    assert response.status_code == 200
    updated = response.get_json()["charge_point"]
    assert updated["booking_fee"] == 99.0
    assert updated["is_bookable"] is False
    assert updated["version"] == 2


def test_station_without_bookable_charge_point_cannot_activate(client, app):
    user = _register_user(client, "activation_rule_admin")
    _promote_user(app, user["id"], UserRole.STATION_ADMIN)
    token = _login(client, user["email"])
    station = _create_station(client, token)

    for charge_point in station["charge_points"]:
        response = client.patch(
            f"/stations/{station['id']}/charge-points/{charge_point['id']}",
            headers={"Authorization": f"Bearer {token}"},
            json={"version": 1, "is_bookable": False},
        )
        assert response.status_code == 200

    activation = client.patch(
        f"/stations/{station['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"version": 1, "status": "active"},
    )

    assert activation.status_code == 409
    assert activation.get_json()["error"]["code"] == "station_state_conflict"
