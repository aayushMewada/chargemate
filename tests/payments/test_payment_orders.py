import hashlib
import hmac
import json
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
from chargemate.models.payment_webhook_event import PaymentWebhookEvent
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


def _create_mocked_payment_order(client, app, monkeypatch, suffix: str):
    booking, access_token = _register_login_and_booking(client, app, suffix)
    _configure_test_razorpay(app, monkeypatch)

    def fake_create_order(**kwargs):
        return RazorpayOrder(
            id=f"order_{suffix}",
            amount_subunits=kwargs["amount_subunits"],
            currency=kwargs["currency"],
            status="created",
        )

    monkeypatch.setattr(
        "chargemate.payments.service.create_razorpay_order",
        fake_create_order,
    )
    order_response = client.post(
        "/payments/orders",
        headers=_headers(access_token),
        json=_payment_payload(booking),
    )
    assert order_response.status_code == 201
    return booking, access_token, order_response.get_json()


def _hmac_signature(message: bytes, secret: str) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()


def _webhook_payload(event_type: str, order_id: str, payment_id: str) -> bytes:
    return json.dumps(
        {
            "event": event_type,
            "payload": {
                "payment": {
                    "entity": {
                        "id": payment_id,
                        "order_id": order_id,
                        "amount": 7500,
                        "currency": "INR",
                    }
                }
            },
        },
        separators=(",", ":"),
    ).encode("utf-8")


def _post_webhook(client, raw_body: bytes, event_id: str, secret: str):
    return client.post(
        "/payments/webhooks/razorpay",
        data=raw_body,
        content_type="application/json",
        headers={
            "X-Razorpay-Event-Id": event_id,
            "X-Razorpay-Signature": _hmac_signature(raw_body, secret),
        },
    )


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


def test_checkout_signature_marks_payment_authorized(client, app, monkeypatch):
    booking, access_token, order = _create_mocked_payment_order(
        client,
        app,
        monkeypatch,
        "verify_checkout_user",
    )
    order_id = order["payment"]["provider_order_id"]
    payment_id = "pay_verified_123"
    signature = _hmac_signature(
        f"{order_id}|{payment_id}".encode("utf-8"),
        "test-secret",
    )

    response = client.post(
        "/payments/verify",
        headers=_headers(access_token),
        json={
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.get_json()["payment"]["status"] == "authorized"
    with app.app_context():
        stored_booking = db.session.get(Booking, UUID(booking["id"]))
        assert stored_booking.status == BookingStatus.PAYMENT_PENDING


def test_invalid_checkout_signature_changes_nothing(client, app, monkeypatch):
    _, access_token, order = _create_mocked_payment_order(
        client,
        app,
        monkeypatch,
        "invalid_signature_user",
    )

    response = client.post(
        "/payments/verify",
        headers=_headers(access_token),
        json={
            "razorpay_order_id": order["payment"]["provider_order_id"],
            "razorpay_payment_id": "pay_tampered",
            "razorpay_signature": "0" * 64,
        },
    )

    assert response.status_code == 400
    with app.app_context():
        payment = db.session.scalar(select(Payment))
        assert payment.status == PaymentStatus.ORDER_CREATED
        assert payment.provider_payment_id is None


def test_captured_webhook_confirms_booking_and_duplicate_is_noop(
    client,
    app,
    monkeypatch,
):
    booking, _, order = _create_mocked_payment_order(
        client,
        app,
        monkeypatch,
        "captured_webhook_user",
    )
    webhook_secret = "webhook-test-secret"
    monkeypatch.setitem(app.config, "RAZORPAY_WEBHOOK_SECRET", webhook_secret)
    raw_body = _webhook_payload(
        "payment.captured",
        order["payment"]["provider_order_id"],
        "pay_captured_123",
    )

    first = _post_webhook(client, raw_body, "event_capture_1", webhook_secret)
    duplicate = _post_webhook(client, raw_body, "event_capture_1", webhook_secret)

    assert first.status_code == 200
    assert first.get_json()["status"] == "processed"
    assert duplicate.status_code == 200
    assert duplicate.get_json()["status"] == "duplicate"
    with app.app_context():
        payment = db.session.scalar(select(Payment))
        stored_booking = db.session.get(Booking, UUID(booking["id"]))
        events = db.session.scalars(select(PaymentWebhookEvent)).all()
        assert payment.status == PaymentStatus.CAPTURED
        assert stored_booking.status == BookingStatus.CONFIRMED
        assert stored_booking.version == 3
        assert len(events) == 1


def test_invalid_webhook_signature_is_rejected(client, app, monkeypatch):
    webhook_secret = "webhook-test-secret"
    monkeypatch.setitem(app.config, "RAZORPAY_WEBHOOK_SECRET", webhook_secret)
    raw_body = _webhook_payload(
        "payment.captured",
        "order_unknown",
        "pay_unknown",
    )

    response = client.post(
        "/payments/webhooks/razorpay",
        data=raw_body,
        content_type="application/json",
        headers={
            "X-Razorpay-Event-Id": "event_invalid_signature",
            "X-Razorpay-Signature": "0" * 64,
        },
    )

    assert response.status_code == 400
    with app.app_context():
        assert db.session.scalar(select(PaymentWebhookEvent)) is None


def test_capture_after_cancellation_does_not_resurrect_booking(
    client,
    app,
    monkeypatch,
):
    booking, access_token, order = _create_mocked_payment_order(
        client,
        app,
        monkeypatch,
        "cancelled_capture_user",
    )
    cancellation = client.post(
        f"/bookings/{booking['id']}/cancel",
        headers=_headers(access_token),
        json={"version": 2},
    )
    assert cancellation.status_code == 200
    webhook_secret = "webhook-test-secret"
    monkeypatch.setitem(app.config, "RAZORPAY_WEBHOOK_SECRET", webhook_secret)
    raw_body = _webhook_payload(
        "payment.captured",
        order["payment"]["provider_order_id"],
        "pay_captured_after_cancel",
    )

    response = _post_webhook(
        client,
        raw_body,
        "event_capture_after_cancel",
        webhook_secret,
    )

    assert response.status_code == 200
    with app.app_context():
        payment = db.session.scalar(select(Payment))
        stored_booking = db.session.get(Booking, UUID(booking["id"]))
        assert payment.status == PaymentStatus.CAPTURED
        assert payment.last_error_code == "captured_after_booking_closed"
        assert stored_booking.status == BookingStatus.CANCELLED


def test_failed_webhook_restores_the_booking_hold(client, app, monkeypatch):
    booking, _, order = _create_mocked_payment_order(
        client,
        app,
        monkeypatch,
        "failed_webhook_user",
    )
    webhook_secret = "webhook-test-secret"
    monkeypatch.setitem(app.config, "RAZORPAY_WEBHOOK_SECRET", webhook_secret)
    raw_body = _webhook_payload(
        "payment.failed",
        order["payment"]["provider_order_id"],
        "pay_failed_123",
    )

    response = _post_webhook(
        client,
        raw_body,
        "event_payment_failed",
        webhook_secret,
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "processed"
    with app.app_context():
        payment = db.session.scalar(select(Payment))
        stored_booking = db.session.get(Booking, UUID(booking["id"]))
        assert payment.status == PaymentStatus.FAILED
        assert stored_booking.status == BookingStatus.HELD
        assert stored_booking.version == 3


def test_webhook_amount_mismatch_does_not_confirm_booking(
    client,
    app,
    monkeypatch,
):
    booking, _, order = _create_mocked_payment_order(
        client,
        app,
        monkeypatch,
        "amount_mismatch_user",
    )
    webhook_secret = "webhook-test-secret"
    monkeypatch.setitem(app.config, "RAZORPAY_WEBHOOK_SECRET", webhook_secret)
    payload = json.loads(
        _webhook_payload(
            "payment.captured",
            order["payment"]["provider_order_id"],
            "pay_wrong_amount",
        )
    )
    payload["payload"]["payment"]["entity"]["amount"] = 1
    raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    response = _post_webhook(
        client,
        raw_body,
        "event_amount_mismatch",
        webhook_secret,
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "ignored"
    with app.app_context():
        payment = db.session.scalar(select(Payment))
        stored_booking = db.session.get(Booking, UUID(booking["id"]))
        assert payment.status == PaymentStatus.ORDER_CREATED
        assert payment.last_error_code == "provider_amount_mismatch"
        assert stored_booking.status == BookingStatus.PAYMENT_PENDING
        assert stored_booking.version == 2
