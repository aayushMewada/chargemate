from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from flask import current_app
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from chargemate.bookings.service import BookingStateConflictError
from chargemate.extensions import db
from chargemate.models.booking import Booking, BookingStatus
from chargemate.models.payment import Payment, PaymentStatus
from chargemate.models.refund import Refund, RefundStatus
from chargemate.payments.razorpay import (
    RazorpayRefund,
    RazorpayRefundError,
    create_razorpay_refund,
)
from chargemate.payments.service import timestamp_is_after


DIRECT_CANCELLATION_STATUSES = (
    BookingStatus.HELD,
    BookingStatus.PAYMENT_PENDING,
)


@dataclass(frozen=True)
class CancellationOutcome:
    """Final local state returned after cancellation and refund handling."""

    booking: Booking
    refund: Refund | None
    provider_error: bool = False


@dataclass(frozen=True)
class RefundRequestSnapshot:
    """Immutable provider inputs captured before releasing database locks."""

    refund_id: UUID
    booking_id: UUID
    payment_id: UUID
    provider_payment_id: str
    amount_subunits: int
    currency: str
    receipt: str


def cancel_booking_with_refund(
    user_id: UUID,
    booking_id: UUID,
    expected_version: int,
) -> CancellationOutcome:
    """Cancel a booking and refund captured money without a long transaction."""

    prepared = _prepare_cancellation(user_id, booking_id, expected_version)
    if isinstance(prepared, CancellationOutcome):
        return prepared

    key_id = current_app.config.get("RAZORPAY_KEY_ID")
    key_secret = current_app.config.get("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret:
        return _record_refund_failure(prepared, "provider_not_configured")

    try:
        provider_refund = create_razorpay_refund(
            key_id=key_id,
            key_secret=key_secret,
            payment_id=prepared.provider_payment_id,
            amount_subunits=prepared.amount_subunits,
            currency=prepared.currency,
            receipt=prepared.receipt,
            notes={
                "refund_id": str(prepared.refund_id),
                "booking_id": str(prepared.booking_id),
            },
        )
    except RazorpayRefundError:
        return _record_refund_failure(prepared, "provider_refund_failed")

    return _finalize_refund(prepared, provider_refund)


def _prepare_cancellation(
    user_id: UUID,
    booking_id: UUID,
    expected_version: int,
) -> CancellationOutcome | RefundRequestSnapshot:
    now = datetime.now(UTC)
    try:
        booking = db.session.scalar(
            select(Booking)
            .where(Booking.id == booking_id, Booking.user_id == user_id)
            .with_for_update()
        )
        if booking is None:
            raise BookingStateConflictError

        if booking.status == BookingStatus.CANCELLED:
            outcome = _existing_cancellation(booking)
            if outcome.refund is None:
                raise BookingStateConflictError
            db.session.commit()
            return outcome

        if booking.version != expected_version:
            raise BookingStateConflictError

        if booking.status in DIRECT_CANCELLATION_STATUSES:
            if (
                booking.status == BookingStatus.HELD
                and not timestamp_is_after(booking.hold_expires_at, now)
            ):
                raise BookingStateConflictError
            booking.status = BookingStatus.CANCELLED
            booking.cancelled_at = now
            booking.version += 1
            db.session.commit()
            return CancellationOutcome(
                booking=db.session.get(Booking, booking_id),
                refund=None,
            )

        if booking.status != BookingStatus.CONFIRMED:
            raise BookingStateConflictError

        payment = db.session.scalar(
            select(Payment)
            .where(
                Payment.booking_id == booking.id,
                Payment.status == PaymentStatus.CAPTURED,
            )
            .with_for_update()
        )
        if payment is None or payment.provider_payment_id is None:
            raise BookingStateConflictError

        refund_id = uuid4()
        refund = Refund(
            id=refund_id,
            payment_id=payment.id,
            status=RefundStatus.REQUESTED,
            amount=payment.amount,
            amount_subunits=payment.amount_subunits,
            currency=payment.currency,
            receipt=f"cmr_{refund_id.hex}",
        )
        booking.status = BookingStatus.CANCELLED
        booking.cancelled_at = now
        booking.version += 1
        db.session.add(refund)
        prepared = RefundRequestSnapshot(
            refund_id=refund_id,
            booking_id=booking_id,
            payment_id=payment.id,
            provider_payment_id=payment.provider_payment_id,
            amount_subunits=payment.amount_subunits,
            currency=payment.currency,
            receipt=refund.receipt,
        )
        db.session.commit()
    except BookingStateConflictError:
        db.session.rollback()
        raise
    except IntegrityError as error:
        db.session.rollback()
        raise BookingStateConflictError from error
    except Exception:
        db.session.rollback()
        raise

    return prepared


def _existing_cancellation(booking: Booking) -> CancellationOutcome:
    refund = db.session.scalar(
        select(Refund)
        .join(Payment, Refund.payment_id == Payment.id)
        .where(Payment.booking_id == booking.id)
    )
    return CancellationOutcome(booking=booking, refund=refund)


def _record_refund_failure(
    prepared: RefundRequestSnapshot,
    error_code: str,
) -> CancellationOutcome:
    try:
        refund = db.session.scalar(
            select(Refund)
            .where(Refund.id == prepared.refund_id)
            .with_for_update()
        )
        if refund.status == RefundStatus.REQUESTED:
            refund.status = RefundStatus.FAILED
            refund.last_error_code = error_code
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return CancellationOutcome(
        booking=db.session.get(Booking, prepared.booking_id),
        refund=refund,
        provider_error=True,
    )


def _finalize_refund(
    prepared: RefundRequestSnapshot,
    provider_refund: RazorpayRefund,
) -> CancellationOutcome:
    try:
        refund = db.session.scalar(
            select(Refund)
            .where(Refund.id == prepared.refund_id)
            .with_for_update()
        )
        payment = db.session.scalar(
            select(Payment)
            .where(Payment.id == prepared.payment_id)
            .with_for_update()
        )
        if refund.status != RefundStatus.REQUESTED:
            db.session.commit()
            return CancellationOutcome(
                booking=db.session.get(Booking, prepared.booking_id),
                refund=refund,
            )

        refund.provider_refund_id = provider_refund.id
        if provider_refund.status == "processed":
            refund.status = RefundStatus.PROCESSED
            refund.processed_at = datetime.now(UTC)
            payment.status = PaymentStatus.REFUNDED
        elif provider_refund.status == "pending":
            refund.status = RefundStatus.PENDING
        else:
            refund.status = RefundStatus.FAILED
            refund.last_error_code = "provider_refund_failed"
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        raise BookingStateConflictError from error
    except Exception:
        db.session.rollback()
        raise

    return CancellationOutcome(
        booking=db.session.get(Booking, prepared.booking_id),
        refund=refund,
        provider_error=refund.status == RefundStatus.FAILED,
    )
