from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from chargemate.extensions import db
from chargemate.models.booking import Booking, BookingStatus
from chargemate.models.charge_point import ChargePoint, ConnectorType, PowerType
from chargemate.models.charging_session import (
    ChargingSession,
    ChargingSessionStatus,
)
from chargemate.models.station import ChargingStation, StationStatus
from chargemate.models.user import User, UserRole


PASSWORD = "Charging-Session-Test-Password-2026"


def _register_and_login(client, app, suffix: str) -> tuple[dict, str]:
    registration = client.post(
        "/auth/register",
        json={
            "email": f"{suffix}@example.com",
            "username": suffix,
            "password": PASSWORD,
            "full_name": "Charging Session User",
            "phone": None,
        },
    )
    user = registration.get_json()["user"]
    with app.app_context():
        stored_user = db.session.get(User, UUID(user["id"]))
        stored_user.role = UserRole.STATION_ADMIN
        db.session.commit()
    login = client.post(
        "/auth/login",
        json={"identifier": user["email"], "password": PASSWORD},
    )
    return user, login.get_json()["access_token"]


def _authorization(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _create_confirmed_booking(
    app,
    user_id: str,
    *,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    charge_point_id: UUID | None = None,
) -> Booking:
    with app.app_context():
        if charge_point_id is None:
            station = ChargingStation(
                owner_id=UUID(user_id),
                name="Charging Session Test Station",
                address_line_1="101 Session Road",
                city="Indore",
                state="Madhya Pradesh",
                postal_code="452010",
                country_code="IN",
                latitude=Decimal("22.753284"),
                longitude=Decimal("75.893696"),
                status=StationStatus.ACTIVE,
            )
            charge_point = ChargePoint(
                station=station,
                code="CP-SESSION-01",
                connector_type=ConnectorType.CCS_2,
                power_type=PowerType.DC,
                max_power_kw=Decimal("60.00"),
                booking_fee=Decimal("75.00"),
            )
            db.session.add(station)
            db.session.flush()
            charge_point_id = charge_point.id

        now = datetime.now(UTC)
        booking = Booking(
            user_id=UUID(user_id),
            charge_point_id=charge_point_id,
            starts_at=starts_at or now - timedelta(minutes=5),
            ends_at=ends_at or now + timedelta(minutes=55),
            hold_expires_at=now,
            status=BookingStatus.CONFIRMED,
            total_amount=Decimal("75.00"),
            currency="INR",
        )
        db.session.add(booking)
        db.session.commit()
        db.session.refresh(booking)
        db.session.expunge(booking)
        return booking


def _start_session(client, token: str, booking: Booking, version: int = 1):
    return client.post(
        "/charging-sessions",
        headers=_authorization(token),
        json={
            "booking_id": str(booking.id),
            "booking_version": version,
            "meter_start_kwh": "1000.125",
        },
    )


def test_confirmed_booking_starts_charging_session(client, app):
    user, token = _register_and_login(client, app, "start_session_user")
    booking = _create_confirmed_booking(app, user["id"])

    response = _start_session(client, token, booking)

    assert response.status_code == 201
    body = response.get_json()["charging_session"]
    assert body["status"] == "active"
    assert body["meter_start_kwh"] == 1000.125
    assert body["version"] == 1
    assert body["charge_point"]["code"] == "CP-SESSION-01"
    assert body["charge_point"]["station"]["name"] == (
        "Charging Session Test Station"
    )
    assert body["booking_window"]["starts_at"] is not None
    with app.app_context():
        stored_booking = db.session.get(Booking, booking.id)
        assert stored_booking.status == BookingStatus.ACTIVE
        assert stored_booking.version == 2


def test_booking_cannot_start_before_early_window(client, app):
    user, token = _register_and_login(client, app, "early_session_user")
    now = datetime.now(UTC)
    booking = _create_confirmed_booking(
        app,
        user["id"],
        starts_at=now + timedelta(hours=1),
        ends_at=now + timedelta(hours=2),
    )

    response = _start_session(client, token, booking)

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "outside_charging_window"


def test_stale_booking_version_cannot_start_session(client, app):
    user, token = _register_and_login(client, app, "stale_session_user")
    booking = _create_confirmed_booking(app, user["id"])

    response = _start_session(client, token, booking, version=99)

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == (
        "charging_session_state_conflict"
    )


def test_regular_user_cannot_submit_charger_meter_readings(client, app):
    user, token = _register_and_login(client, app, "regular_meter_user")
    booking = _create_confirmed_booking(app, user["id"])
    with app.app_context():
        stored_user = db.session.get(User, UUID(user["id"]))
        stored_user.role = UserRole.USER
        db.session.commit()

    response = _start_session(client, token, booking)

    assert response.status_code == 403
    with app.app_context():
        assert db.session.query(ChargingSession).count() == 0


def test_session_completion_calculates_energy_and_completes_booking(client, app):
    user, token = _register_and_login(client, app, "complete_session_user")
    booking = _create_confirmed_booking(app, user["id"])
    started = _start_session(client, token, booking).get_json()[
        "charging_session"
    ]

    response = client.post(
        f"/charging-sessions/{started['id']}/complete",
        headers=_authorization(token),
        json={"version": 1, "meter_end_kwh": "1012.875"},
    )

    assert response.status_code == 200
    completed = response.get_json()["charging_session"]
    assert completed["status"] == "completed"
    assert completed["energy_consumed_kwh"] == 12.75
    assert completed["version"] == 2
    with app.app_context():
        stored_booking = db.session.get(Booking, booking.id)
        assert stored_booking.status == BookingStatus.COMPLETED
        assert stored_booking.version == 3


def test_final_meter_reading_cannot_move_backwards(client, app):
    user, token = _register_and_login(client, app, "meter_session_user")
    booking = _create_confirmed_booking(app, user["id"])
    started = _start_session(client, token, booking).get_json()[
        "charging_session"
    ]

    response = client.post(
        f"/charging-sessions/{started['id']}/complete",
        headers=_authorization(token),
        json={"version": 1, "meter_end_kwh": "999.000"},
    )

    assert response.status_code == 422
    with app.app_context():
        charging_session = db.session.get(
            ChargingSession,
            UUID(started["id"]),
        )
        assert charging_session.status == ChargingSessionStatus.ACTIVE


def test_active_session_blocks_second_booking_on_same_charge_point(client, app):
    user, token = _register_and_login(client, app, "occupied_point_user")
    first_booking = _create_confirmed_booking(app, user["id"])
    second_booking = _create_confirmed_booking(
        app,
        user["id"],
        charge_point_id=first_booking.charge_point_id,
    )
    first = _start_session(client, token, first_booking)

    second = _start_session(client, token, second_booking)

    assert first.status_code == 201
    assert second.status_code == 409


def test_user_can_list_only_their_own_charging_sessions(client, app):
    first_user, first_token = _register_and_login(
        client,
        app,
        "session_owner",
    )
    booking = _create_confirmed_booking(app, first_user["id"])
    started = _start_session(client, first_token, booking).get_json()[
        "charging_session"
    ]
    _, second_token = _register_and_login(
        client,
        app,
        "session_other_user",
    )

    owner_list = client.get(
        "/charging-sessions/me",
        headers=_authorization(first_token),
    )
    other_list = client.get(
        "/charging-sessions/me",
        headers=_authorization(second_token),
    )
    other_detail = client.get(
        f"/charging-sessions/{started['id']}",
        headers=_authorization(second_token),
    )

    assert owner_list.status_code == 200
    assert owner_list.get_json()["pagination"]["total"] == 1
    assert other_list.status_code == 200
    assert other_list.get_json()["pagination"]["total"] == 0
    assert other_detail.status_code == 404
