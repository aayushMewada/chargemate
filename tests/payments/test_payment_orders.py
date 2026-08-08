from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select

from chargemate.extensions import db
from chargemate.models.booking import Booking, BookingStatus
from chargemate.models.charge_point import (
    ChargePoint,
    ConnectorType,
    PowerType,
)
from chargemate.models.payment import Payment, PaymentStatus
from chargemate.models.station import ChargingStation, StationStatus
from chargemate.payments.razorpay import RazorpayOrder, RazorpayOrderError


PASSWORD = "Payment-Test-Password-2026"


def _register_login_and_booking(client, app, suffix: str) -> tuple[dict, str]:
    registration = client.post(
        "/auth/register",
        json={
            "email": f"{suffix}@example.com",
            "username": suffix,
            "password": PASSWORD,
            "full_name": "Payment Test User",
            "phone": None,
        },
    )
    user = registration.get_json()["user"]
    login = client.post(
        "/auth/login",
        json={"identifier": user["email"], "password": PASSWORD},
    )
    access_token = login.get_json()["access_token"]

    with app.app_context():
        station = ChargingStation(
            owner_id=UUID(user["id"]),
            name=f"{suffix} Station",
            address_line_1="101 Payment Road",
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
            booking_fee=Decimal("75.00"),
        )
        db.session.add(station)
        db.session.commit()
        charge_point_id = str(charge_point.id)

    starts_at = datetime.now(UTC) + timedelta(hours=1)
    booking_response = client.post(
        "/bookings",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "charge_point_id": charge_point_id,
            "starts_at": starts_at.isoformat(),
            "ends_at": (starts_at + timedelta(hours=1)).isoformat(),
        },
    )
    assert booking_response.status_code == 201
    return booking_response.get_json()["booking"], access_token


def _payment_payload(booking: dict, idempotency_key=None) -> dict:
    return {
        "booking_id": booking["id"],
        "booking_version": booking["version"],
        "idempotency_key": str(idempotency_key or uuid4()),
    }


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _configure_test_razorpay(app, monkeypatch) -> None:
    monkeypatch.setitem(app.config, "RAZORPAY_KEY_ID", "rzp_test_public_key")
    monkeypatch.setitem(app.config, "RAZORPAY_KEY_SECRET", "test-secret")


def test_payment_order_is_created_and_idempotently_replayed(
    client,
    app,
    monkeypatch,
):
    booking, access_token = _register_login_and_booking(
        client,
        app,
        "payment_order_user",
    )
    _configure_test_razorpay(app, monkeypatch)
    provider_calls = []

    def fake_create_order(**kwargs):
        provider_calls.append(kwargs)
        return RazorpayOrder(
            id="order_test_123",
            amount_subunits=kwargs["amount_subunits"],
            currency=kwargs["currency"],
            status="created",
        )

    monkeypatch.setattr(
        "chargemate.payments.service.create_razorpay_order",
        fake_create_order,
    )
    payload = _payment_payload(booking)

    first = client.post(
        "/payments/orders",
        headers=_headers(access_token),
        json=payload,
    )
    repeated = client.post(
        "/payments/orders",
        headers=_headers(access_token),
        json=payload,
    )

    assert first.status_code == 201
    assert repeated.status_code == 201
    assert len(provider_calls) == 1
    assert first.get_json() == repeated.get_json()
    body = first.get_json()
    assert body["payment"]["status"] == "order_created"
    assert body["payment"]["amount_subunits"] == 7500
    assert body["booking"] == {
        "id": booking["id"],
        "status": "payment_pending",
        "version": 2,
    }
    assert body["checkout"]["key_id"] == "rzp_test_public_key"


def test_stale_booking_version_does_not_call_provider(client, app, monkeypatch):
    booking, access_token = _register_login_and_booking(
        client,
        app,
        "stale_payment_user",
    )
    _configure_test_razorpay(app, monkeypatch)

    def unexpected_provider_call(**_kwargs):
        raise AssertionError("provider should not be called")

    monkeypatch.setattr(
        "chargemate.payments.service.create_razorpay_order",
        unexpected_provider_call,
    )
    payload = _payment_payload(booking)
    payload["booking_version"] = 99

    response = client.post(
        "/payments/orders",
        headers=_headers(access_token),
        json=payload,
    )

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "payment_state_conflict"


def test_provider_failure_is_recorded_and_booking_hold_is_restored(
    client,
    app,
    monkeypatch,
):
    booking, access_token = _register_login_and_booking(
        client,
        app,
        "failed_payment_user",
    )
    _configure_test_razorpay(app, monkeypatch)

    def failing_create_order(**_kwargs):
        raise RazorpayOrderError

    monkeypatch.setattr(
        "chargemate.payments.service.create_razorpay_order",
        failing_create_order,
    )
    response = client.post(
        "/payments/orders",
        headers=_headers(access_token),
        json=_payment_payload(booking),
    )

    assert response.status_code == 502
    with app.app_context():
        payment = db.session.scalar(select(Payment))
        restored_booking = db.session.get(Booking, UUID(booking["id"]))
        assert payment.status == PaymentStatus.FAILED
        assert payment.last_error_code == "provider_order_failed"
        assert restored_booking.status == BookingStatus.HELD
        assert restored_booking.version == 3


def test_missing_provider_configuration_returns_503(client, app, monkeypatch):
    booking, access_token = _register_login_and_booking(
        client,
        app,
        "unconfigured_payment_user",
    )
    monkeypatch.setitem(app.config, "RAZORPAY_KEY_ID", None)
    monkeypatch.setitem(app.config, "RAZORPAY_KEY_SECRET", None)

    response = client.post(
        "/payments/orders",
        headers=_headers(access_token),
        json=_payment_payload(booking),
    )

    assert response.status_code == 503
    with app.app_context():
        assert db.session.scalar(select(Payment)) is None
