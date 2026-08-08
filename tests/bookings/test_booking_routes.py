from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from chargemate.extensions import db
from chargemate.models.booking import Booking, BookingStatus
from chargemate.models.charge_point import (
    ChargePoint,
    ChargePointStatus,
    ConnectorType,
    PowerType,
)
from chargemate.models.station import ChargingStation, StationStatus


PASSWORD = "Booking-Test-Password-2026"


def _register_and_login(client, suffix: str) -> tuple[dict, str]:
    registration = client.post(
        "/auth/register",
        json={
            "email": f"{suffix}@example.com",
            "username": suffix,
            "password": PASSWORD,
            "full_name": "Booking Test User",
            "phone": None,
        },
    )
    assert registration.status_code == 201
    user = registration.get_json()["user"]

    login = client.post(
        "/auth/login",
        json={"identifier": user["email"], "password": PASSWORD},
    )
    assert login.status_code == 200
    return user, login.get_json()["access_token"]


def _create_charge_point(
    app,
    owner_id: str,
    *,
    status: ChargePointStatus = ChargePointStatus.AVAILABLE,
    is_bookable: bool = True,
) -> str:
    with app.app_context():
        station = ChargingStation(
            owner_id=UUID(owner_id),
            name="Booking Test Station",
            address_line_1="101 Test Road",
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
            code="CP-01",
            connector_type=ConnectorType.CCS_2,
            power_type=PowerType.DC,
            max_power_kw=Decimal("60.00"),
            status=status,
            is_bookable=is_bookable,
        )
        db.session.add(station)
        db.session.commit()
        return str(charge_point.id)


def _booking_payload(
    charge_point_id: str,
    starts_at: datetime,
    ends_at: datetime,
) -> dict:
    return {
        "charge_point_id": charge_point_id,
        "starts_at": starts_at.isoformat(),
        "ends_at": ends_at.isoformat(),
    }


def _authorization(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def test_user_creates_temporary_booking_hold(client, app):
    user, access_token = _register_and_login(client, "booking_hold_user")
    charge_point_id = _create_charge_point(app, user["id"])
    starts_at = datetime.now(UTC) + timedelta(hours=1)

    response = client.post(
        "/bookings",
        headers=_authorization(access_token),
        json=_booking_payload(
            charge_point_id,
            starts_at,
            starts_at + timedelta(hours=1),
        ),
    )

    assert response.status_code == 201
    booking = response.get_json()["booking"]
    assert booking["user_id"] == user["id"]
    assert booking["charge_point_id"] == charge_point_id
    assert booking["status"] == "held"
    assert booking["version"] == 1
    assert booking["hold_expires_at"] is not None


def test_overlapping_booking_is_rejected(client, app):
    user, access_token = _register_and_login(client, "overlap_user")
    charge_point_id = _create_charge_point(app, user["id"])
    starts_at = datetime.now(UTC) + timedelta(hours=1)
    first_payload = _booking_payload(
        charge_point_id,
        starts_at,
        starts_at + timedelta(hours=1),
    )
    overlapping_payload = _booking_payload(
        charge_point_id,
        starts_at + timedelta(minutes=30),
        starts_at + timedelta(minutes=90),
    )

    assert client.post(
        "/bookings",
        headers=_authorization(access_token),
        json=first_payload,
    ).status_code == 201
    response = client.post(
        "/bookings",
        headers=_authorization(access_token),
        json=overlapping_payload,
    )

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "booking_unavailable"


def test_adjacent_half_open_booking_slots_are_allowed(client, app):
    user, access_token = _register_and_login(client, "adjacent_user")
    charge_point_id = _create_charge_point(app, user["id"])
    starts_at = datetime.now(UTC) + timedelta(hours=1)
    boundary = starts_at + timedelta(hours=1)

    first = client.post(
        "/bookings",
        headers=_authorization(access_token),
        json=_booking_payload(charge_point_id, starts_at, boundary),
    )
    second = client.post(
        "/bookings",
        headers=_authorization(access_token),
        json=_booking_payload(
            charge_point_id,
            boundary,
            boundary + timedelta(hours=1),
        ),
    )

    assert first.status_code == 201
    assert second.status_code == 201


def test_expired_hold_releases_its_time_slot(client, app):
    user, access_token = _register_and_login(client, "expired_hold_user")
    charge_point_id = _create_charge_point(app, user["id"])
    starts_at = datetime.now(UTC) + timedelta(hours=1)
    payload = _booking_payload(
        charge_point_id,
        starts_at,
        starts_at + timedelta(hours=1),
    )
    first = client.post(
        "/bookings",
        headers=_authorization(access_token),
        json=payload,
    )
    first_booking_id = first.get_json()["booking"]["id"]

    with app.app_context():
        booking = db.session.get(Booking, UUID(first_booking_id))
        booking.hold_expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.session.commit()

    replacement = client.post(
        "/bookings",
        headers=_authorization(access_token),
        json=payload,
    )

    assert replacement.status_code == 201
    with app.app_context():
        expired_booking = db.session.get(Booking, UUID(first_booking_id))
        assert expired_booking.status == BookingStatus.EXPIRED
        assert expired_booking.version == 2


def test_unavailable_charge_point_cannot_be_held(client, app):
    user, access_token = _register_and_login(client, "unavailable_point_user")
    charge_point_id = _create_charge_point(
        app,
        user["id"],
        status=ChargePointStatus.MAINTENANCE,
    )
    starts_at = datetime.now(UTC) + timedelta(hours=1)

    response = client.post(
        "/bookings",
        headers=_authorization(access_token),
        json=_booking_payload(
            charge_point_id,
            starts_at,
            starts_at + timedelta(hours=1),
        ),
    )

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "booking_unavailable"
