from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from chargemate.extensions import db
from chargemate.maintenance.service import (
    expire_stale_booking_holds,
    reconcile_pending_refunds,
)
from chargemate.models.booking import Booking, BookingStatus
from chargemate.models.charge_point import ChargePoint, ConnectorType, PowerType
from chargemate.models.payment import Payment, PaymentProvider, PaymentStatus
from chargemate.models.refund import Refund, RefundStatus
from chargemate.models.station import ChargingStation, StationStatus
from chargemate.models.user import User
from chargemate.payments.razorpay import RazorpayRefund, RazorpayRefundError


def _create_user_and_charge_point() -> tuple[User, ChargePoint]:
    user = User(
        email=f"maintenance-{uuid4()}@example.com",
        username=f"maintenance_{uuid4().hex}",
        full_name="Maintenance Test User",
    )
    user.set_password("Maintenance-Test-Password-2026")
    station = ChargingStation(
        owner=user,
        name="Maintenance Test Station",
        address_line_1="101 Worker Road",
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
        code="CP-WORKER-01",
        connector_type=ConnectorType.CCS_2,
        power_type=PowerType.DC,
        max_power_kw=Decimal("60.00"),
        booking_fee=Decimal("75.00"),
    )
    db.session.add(user)
    db.session.commit()
    return user, charge_point


def _create_booking(
    user: User,
    charge_point: ChargePoint,
    *,
    hold_expires_at: datetime,
) -> Booking:
    starts_at = datetime.now(UTC) + timedelta(hours=1)
    booking = Booking(
        user_id=user.id,
        charge_point_id=charge_point.id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        hold_expires_at=hold_expires_at,
        status=BookingStatus.HELD,
        total_amount=Decimal("75.00"),
        currency="INR",
    )
    db.session.add(booking)
    db.session.commit()
    return booking


def _create_pending_refund() -> tuple[Payment, Refund]:
    user, charge_point = _create_user_and_charge_point()
    now = datetime.now(UTC)
    booking = _create_booking(
        user,
        charge_point,
        hold_expires_at=now,
    )
    booking.status = BookingStatus.CANCELLED
    payment = Payment(
        booking_id=booking.id,
        user_id=user.id,
        provider=PaymentProvider.RAZORPAY,
        status=PaymentStatus.CAPTURED,
        amount=Decimal("75.00"),
        amount_subunits=7500,
        currency="INR",
        idempotency_key=uuid4(),
        provider_order_id=f"order_{uuid4().hex}",
        provider_payment_id=f"pay_{uuid4().hex}",
    )
    db.session.add(payment)
    db.session.flush()
    refund = Refund(
        payment_id=payment.id,
        status=RefundStatus.PENDING,
        amount=payment.amount,
        amount_subunits=payment.amount_subunits,
        currency=payment.currency,
        receipt=f"cmr_{uuid4().hex}",
        provider_refund_id=f"rfnd_{uuid4().hex}",
    )
    db.session.add(refund)
    db.session.commit()
    return payment, refund


def test_stale_hold_is_expired_without_touching_future_hold(db_app):
    user, charge_point = _create_user_and_charge_point()
    now = datetime.now(UTC)
    stale = _create_booking(
        user,
        charge_point,
        hold_expires_at=now - timedelta(minutes=1),
    )
    future = _create_booking(
        user,
        charge_point,
        hold_expires_at=now + timedelta(minutes=5),
    )

    count = expire_stale_booking_holds(now)

    assert count == 1
    assert db.session.get(Booking, stale.id).status == BookingStatus.EXPIRED
    assert db.session.get(Booking, stale.id).version == 2
    assert db.session.get(Booking, future.id).status == BookingStatus.HELD


def test_stale_hold_expiration_respects_batch_size(db_app):
    user, charge_point = _create_user_and_charge_point()
    now = datetime.now(UTC)
    for offset in range(3):
        _create_booking(
            user,
            charge_point,
            hold_expires_at=now - timedelta(minutes=offset + 1),
        )

    first_count = expire_stale_booking_holds(now, batch_size=2)
    second_count = expire_stale_booking_holds(now, batch_size=2)

    assert first_count == 2
    assert second_count == 1


def test_reconciliation_marks_processed_refund_and_payment(db_app):
    payment, refund = _create_pending_refund()

    def processed_fetcher(**kwargs):
        return RazorpayRefund(
            id=kwargs["refund_id"],
            payment_id=kwargs["payment_id"],
            amount_subunits=kwargs["amount_subunits"],
            currency=kwargs["currency"],
            status="processed",
        )

    result = reconcile_pending_refunds(
        key_id="test-key",
        key_secret="test-secret",
        fetcher=processed_fetcher,
    )

    assert result == {"checked": 1, "processed": 1, "failed": 0, "errors": 0}
    assert db.session.get(Refund, refund.id).status == RefundStatus.PROCESSED
    assert db.session.get(Payment, payment.id).status == PaymentStatus.REFUNDED


def test_reconciliation_records_provider_failed_refund(db_app):
    _, refund = _create_pending_refund()

    def failed_fetcher(**kwargs):
        return RazorpayRefund(
            id=kwargs["refund_id"],
            payment_id=kwargs["payment_id"],
            amount_subunits=kwargs["amount_subunits"],
            currency=kwargs["currency"],
            status="failed",
        )

    result = reconcile_pending_refunds(
        key_id="test-key",
        key_secret="test-secret",
        fetcher=failed_fetcher,
    )

    assert result["failed"] == 1
    stored = db.session.get(Refund, refund.id)
    assert stored.status == RefundStatus.FAILED
    assert stored.last_error_code == "provider_refund_failed"


def test_provider_error_leaves_pending_refund_for_next_run(db_app):
    _, refund = _create_pending_refund()

    def unavailable_fetcher(**_kwargs):
        raise RazorpayRefundError

    result = reconcile_pending_refunds(
        key_id="test-key",
        key_secret="test-secret",
        fetcher=unavailable_fetcher,
    )

    assert result["errors"] == 1
    assert db.session.get(Refund, refund.id).status == RefundStatus.PENDING
