from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable
from uuid import UUID

from sqlalchemy import select, update

from chargemate.extensions import db
from chargemate.models.booking import Booking, BookingStatus
from chargemate.models.payment import Payment, PaymentStatus
from chargemate.models.refund import Refund, RefundStatus
from chargemate.payments.razorpay import (
    RazorpayRefund,
    RazorpayRefundError,
    fetch_razorpay_refund,
)


RefundFetcher = Callable[..., RazorpayRefund]


@dataclass(frozen=True)
class RefundSnapshot:
    """Provider inputs copied before the database transaction closes."""

    refund_id: UUID
    provider_refund_id: str
    provider_payment_id: str
    amount_subunits: int
    currency: str


def expire_stale_booking_holds(now: datetime, batch_size: int = 100) -> int:
    """Expire one locked batch of abandoned unpaid booking holds."""

    try:
        booking_ids = list(
            db.session.scalars(
                select(Booking.id)
                .where(
                    Booking.status == BookingStatus.HELD,
                    Booking.hold_expires_at <= now,
                )
                .order_by(Booking.hold_expires_at, Booking.id)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            ).all()
        )
        if not booking_ids:
            db.session.commit()
            return 0

        result = db.session.execute(
            update(Booking)
            .where(
                Booking.id.in_(booking_ids),
                Booking.status == BookingStatus.HELD,
                Booking.hold_expires_at <= now,
            )
            .values(
                status=BookingStatus.EXPIRED,
                version=Booking.version + 1,
            )
        )
        expired_count = result.rowcount
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return expired_count


def reconcile_pending_refunds(
    *,
    key_id: str,
    key_secret: str,
    batch_size: int = 100,
    fetcher: RefundFetcher = fetch_razorpay_refund,
) -> dict[str, int]:
    """Fetch pending refund states without holding locks during HTTP calls."""

    snapshots = _pending_refund_snapshots(batch_size)
    counts = {"checked": 0, "processed": 0, "failed": 0, "errors": 0}
    for snapshot in snapshots:
        counts["checked"] += 1
        try:
            provider_refund = fetcher(
                key_id=key_id,
                key_secret=key_secret,
                refund_id=snapshot.provider_refund_id,
                payment_id=snapshot.provider_payment_id,
                amount_subunits=snapshot.amount_subunits,
                currency=snapshot.currency,
            )
        except RazorpayRefundError:
            counts["errors"] += 1
            continue

        outcome = _apply_reconciled_refund(snapshot.refund_id, provider_refund)
        if outcome in ("processed", "failed"):
            counts[outcome] += 1
    return counts


def _pending_refund_snapshots(batch_size: int) -> list[RefundSnapshot]:
    rows = db.session.execute(
        select(Refund, Payment)
        .join(Payment, Refund.payment_id == Payment.id)
        .where(
            Refund.status == RefundStatus.PENDING,
            Refund.provider_refund_id.is_not(None),
            Payment.provider_payment_id.is_not(None),
        )
        .order_by(Refund.created_at, Refund.id)
        .limit(batch_size)
    ).all()
    snapshots = [
        RefundSnapshot(
            refund_id=refund.id,
            provider_refund_id=refund.provider_refund_id,
            provider_payment_id=payment.provider_payment_id,
            amount_subunits=refund.amount_subunits,
            currency=refund.currency,
        )
        for refund, payment in rows
    ]
    db.session.commit()
    return snapshots


def _apply_reconciled_refund(
    refund_id: UUID,
    provider_refund: RazorpayRefund,
) -> str:
    try:
        refund = db.session.scalar(
            select(Refund).where(Refund.id == refund_id).with_for_update()
        )
        if refund is None or refund.status != RefundStatus.PENDING:
            db.session.commit()
            return "unchanged"

        payment = db.session.scalar(
            select(Payment)
            .where(Payment.id == refund.payment_id)
            .with_for_update()
        )
        if provider_refund.status == "processed":
            refund.status = RefundStatus.PROCESSED
            refund.processed_at = datetime.now(UTC)
            refund.last_error_code = None
            payment.status = PaymentStatus.REFUNDED
        elif provider_refund.status == "failed":
            refund.status = RefundStatus.FAILED
            refund.last_error_code = "provider_refund_failed"
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return provider_refund.status
