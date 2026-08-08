from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from flask import current_app
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from chargemate.extensions import db
from chargemate.models.booking import Booking, BookingStatus
from chargemate.models.payment import Payment, PaymentProvider, PaymentStatus
from chargemate.models.user import User
from chargemate.payments.razorpay import (
    RazorpayOrder,
    RazorpayOrderError,
    create_razorpay_order,
)
from chargemate.payments.schemas import CreatePaymentOrderRequest


CURRENCY_SUBUNITS = 100


class PaymentConfigurationError(Exception):
    """Raised when required provider credentials are unavailable."""


class PaymentStateConflictError(Exception):
    """Raised when a booking or idempotent attempt cannot start checkout."""


class PaymentProviderError(Exception):
    """Raised after a provider failure has been recorded and compensated."""


@dataclass(frozen=True)
class CheckoutOrder:
    """Safe order details required by a future frontend checkout widget."""

    payment: Payment
    booking: Booking
    public_key_id: str


@dataclass(frozen=True)
class PaymentAttemptSnapshot:
    """Values needed for the provider call after the DB transaction closes."""

    payment_id: UUID
    booking_id: UUID
    amount_subunits: int
    currency: str


def create_payment_order(
    user: User,
    payload: CreatePaymentOrderRequest,
) -> CheckoutOrder:
    """Create an idempotent local attempt and matching Razorpay order."""

    key_id = current_app.config.get("RAZORPAY_KEY_ID")
    key_secret = current_app.config.get("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret:
        raise PaymentConfigurationError

    existing = db.session.scalar(
        select(Payment).where(Payment.idempotency_key == payload.idempotency_key)
    )
    if existing is not None:
        return _existing_checkout(existing, user.id, payload.booking_id, key_id)

    attempt = _begin_payment_attempt(user, payload)
    receipt = f"cm_{attempt.payment_id}"

    try:
        provider_order = create_razorpay_order(
            key_id=key_id,
            key_secret=key_secret,
            amount_subunits=attempt.amount_subunits,
            currency=attempt.currency,
            receipt=receipt,
            notes={
                "payment_id": str(attempt.payment_id),
                "booking_id": str(attempt.booking_id),
            },
        )
    except RazorpayOrderError as error:
        _compensate_provider_failure(
            attempt.payment_id,
            attempt.booking_id,
        )
        raise PaymentProviderError from error

    finalized_payment, finalized_booking = _finalize_provider_order(
        attempt.payment_id,
        attempt.booking_id,
        provider_order,
    )
    return CheckoutOrder(
        payment=finalized_payment,
        booking=finalized_booking,
        public_key_id=key_id,
    )


def _begin_payment_attempt(
    user: User,
    payload: CreatePaymentOrderRequest,
) -> PaymentAttemptSnapshot:
    now = datetime.now(UTC)
    try:
        booking = db.session.scalar(
            select(Booking)
            .where(
                Booking.id == payload.booking_id,
                Booking.user_id == user.id,
            )
            .with_for_update()
        )
        if not _booking_can_enter_payment(booking, payload.booking_version, now):
            raise PaymentStateConflictError

        amount = booking.total_amount
        amount_subunits = _to_currency_subunits(amount)
        payment = Payment(
            booking_id=booking.id,
            user_id=user.id,
            provider=PaymentProvider.RAZORPAY,
            status=PaymentStatus.INITIATED,
            amount=amount,
            amount_subunits=amount_subunits,
            currency=booking.currency,
            idempotency_key=payload.idempotency_key,
        )
        booking.status = BookingStatus.PAYMENT_PENDING
        booking.version += 1
        db.session.add(payment)
        db.session.flush()
        attempt = PaymentAttemptSnapshot(
            payment_id=payment.id,
            booking_id=booking.id,
            amount_subunits=payment.amount_subunits,
            currency=payment.currency,
        )
        db.session.commit()
    except PaymentStateConflictError:
        db.session.rollback()
        raise
    except IntegrityError as error:
        db.session.rollback()
        raise PaymentStateConflictError from error
    except Exception:
        db.session.rollback()
        raise

    return attempt


def _finalize_provider_order(
    payment_id: UUID,
    booking_id: UUID,
    provider_order: RazorpayOrder,
) -> tuple[Payment, Booking]:
    try:
        payment = db.session.scalar(
            select(Payment).where(Payment.id == payment_id).with_for_update()
        )
        booking = db.session.scalar(
            select(Booking).where(Booking.id == booking_id).with_for_update()
        )
        if (
            payment.status != PaymentStatus.INITIATED
            or booking.status != BookingStatus.PAYMENT_PENDING
        ):
            payment.provider_order_id = provider_order.id
            payment.status = PaymentStatus.FAILED
            payment.last_error_code = "booking_state_changed"
            db.session.commit()
            raise PaymentStateConflictError

        payment.provider_order_id = provider_order.id
        payment.status = PaymentStatus.ORDER_CREATED
        db.session.commit()
    except PaymentStateConflictError:
        raise
    except Exception:
        db.session.rollback()
        raise

    return payment, booking


def _compensate_provider_failure(payment_id: UUID, booking_id: UUID) -> None:
    now = datetime.now(UTC)
    try:
        payment = db.session.scalar(
            select(Payment).where(Payment.id == payment_id).with_for_update()
        )
        booking = db.session.scalar(
            select(Booking).where(Booking.id == booking_id).with_for_update()
        )
        if payment.status == PaymentStatus.INITIATED:
            payment.status = PaymentStatus.FAILED
            payment.last_error_code = "provider_order_failed"
        if booking.status == BookingStatus.PAYMENT_PENDING:
            booking.status = (
                BookingStatus.HELD
                if _timestamp_is_after(booking.hold_expires_at, now)
                else BookingStatus.EXPIRED
            )
            booking.version += 1
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def _existing_checkout(
    payment: Payment,
    user_id: UUID,
    booking_id: UUID,
    key_id: str,
) -> CheckoutOrder:
    if (
        payment.user_id != user_id
        or payment.booking_id != booking_id
        or payment.status != PaymentStatus.ORDER_CREATED
    ):
        raise PaymentStateConflictError
    booking = db.session.get(Booking, booking_id)
    return CheckoutOrder(payment=payment, booking=booking, public_key_id=key_id)


def _booking_can_enter_payment(
    booking: Booking | None,
    expected_version: int,
    now: datetime,
) -> bool:
    return bool(
        booking is not None
        and booking.status == BookingStatus.HELD
        and booking.version == expected_version
        and _timestamp_is_after(booking.hold_expires_at, now)
        and booking.total_amount is not None
        and booking.total_amount > 0
    )


def _to_currency_subunits(amount: Decimal) -> int:
    subunits = amount * CURRENCY_SUBUNITS
    if subunits != subunits.to_integral_value():
        raise PaymentStateConflictError
    return int(subunits)


def _timestamp_is_after(
    timestamp: datetime | None,
    reference: datetime,
) -> bool:
    if timestamp is None:
        return False
    if timestamp.tzinfo is None:
        # SQLite drops timezone metadata in tests. Stored values are UTC.
        timestamp = timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC) > reference.astimezone(UTC)
