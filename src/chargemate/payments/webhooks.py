import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from chargemate.extensions import db
from chargemate.models.booking import Booking, BookingStatus
from chargemate.models.payment import Payment, PaymentStatus
from chargemate.models.payment_webhook_event import (
    PaymentWebhookEvent,
    WebhookEventStatus,
)
from chargemate.payments.service import timestamp_is_after
from chargemate.payments.signatures import sha256_hex, verify_webhook_signature


SUPPORTED_PAYMENT_EVENTS = {
    "payment.authorized",
    "payment.captured",
    "payment.failed",
}


class WebhookAuthenticationError(Exception):
    """Raised when a webhook signature or event identity is invalid."""


class WebhookPayloadError(Exception):
    """Raised when an authenticated supported event has an invalid body."""


@dataclass(frozen=True)
class WebhookOutcome:
    """Safe processing result returned to Razorpay."""

    status: str


def process_razorpay_webhook(
    *,
    raw_body: bytes,
    supplied_signature: str | None,
    provider_event_id: str | None,
    webhook_secret: str,
) -> WebhookOutcome:
    """Authenticate, deduplicate, and apply one Razorpay payment event."""

    if (
        not supplied_signature
        or not provider_event_id
        or not verify_webhook_signature(
            raw_body=raw_body,
            supplied_signature=supplied_signature,
            webhook_secret=webhook_secret,
        )
    ):
        raise WebhookAuthenticationError

    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as error:
        raise WebhookPayloadError from error

    if not isinstance(payload, dict) or not isinstance(payload.get("event"), str):
        raise WebhookPayloadError

    payload_hash = sha256_hex(raw_body)
    duplicate = _existing_event(provider_event_id, payload_hash)
    if duplicate:
        return WebhookOutcome(status="duplicate")

    event = PaymentWebhookEvent(
        provider="razorpay",
        provider_event_id=provider_event_id,
        event_type=payload["event"],
        payload_hash=payload_hash,
        status=WebhookEventStatus.RECEIVED,
    )
    try:
        db.session.add(event)
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        if _existing_event(provider_event_id, payload_hash):
            return WebhookOutcome(status="duplicate")
        raise WebhookAuthenticationError

    try:
        if payload["event"] not in SUPPORTED_PAYMENT_EVENTS:
            event.status = WebhookEventStatus.IGNORED
        else:
            entity = _payment_entity(payload)
            _apply_payment_event(payload["event"], entity, event)
        event.processed_at = datetime.now(UTC)
        db.session.commit()
    except WebhookPayloadError:
        db.session.rollback()
        raise
    except Exception:
        db.session.rollback()
        raise

    return WebhookOutcome(status=event.status.value)


def _existing_event(provider_event_id: str, payload_hash: str) -> bool:
    existing = db.session.scalar(
        select(PaymentWebhookEvent).where(
            PaymentWebhookEvent.provider_event_id == provider_event_id
        )
    )
    if existing is None:
        return False
    if existing.payload_hash != payload_hash:
        raise WebhookAuthenticationError
    return True


def _payment_entity(payload: dict[str, Any]) -> dict[str, Any]:
    payment_payload = payload.get("payload")
    if not isinstance(payment_payload, dict):
        raise WebhookPayloadError
    payment_wrapper = payment_payload.get("payment")
    if not isinstance(payment_wrapper, dict):
        raise WebhookPayloadError
    entity = payment_wrapper.get("entity")
    if not isinstance(entity, dict):
        raise WebhookPayloadError
    return entity


def _apply_payment_event(
    event_type: str,
    entity: dict[str, Any],
    event: PaymentWebhookEvent,
) -> None:
    order_id = entity.get("order_id")
    payment_id = entity.get("id")
    if not isinstance(order_id, str) or not isinstance(payment_id, str):
        raise WebhookPayloadError

    payment = db.session.scalar(
        select(Payment)
        .where(Payment.provider_order_id == order_id)
        .with_for_update()
    )
    if payment is None:
        event.status = WebhookEventStatus.IGNORED
        return

    if not _provider_amount_matches(payment, entity):
        payment.last_error_code = "provider_amount_mismatch"
        event.status = WebhookEventStatus.IGNORED
        return
    if (
        payment.provider_payment_id is not None
        and payment.provider_payment_id != payment_id
    ):
        payment.last_error_code = "provider_payment_id_mismatch"
        event.status = WebhookEventStatus.IGNORED
        return

    payment.provider_payment_id = payment_id
    if event_type == "payment.authorized":
        if payment.status == PaymentStatus.ORDER_CREATED:
            payment.status = PaymentStatus.AUTHORIZED
        event.status = WebhookEventStatus.PROCESSED
        return
    if event_type == "payment.captured":
        _apply_captured_payment(payment)
        event.status = WebhookEventStatus.PROCESSED
        return
    if event_type == "payment.failed":
        _apply_failed_payment(payment)
        event.status = WebhookEventStatus.PROCESSED


def _apply_captured_payment(payment: Payment) -> None:
    if payment.status == PaymentStatus.REFUNDED:
        return
    payment.status = PaymentStatus.CAPTURED
    booking = db.session.scalar(
        select(Booking)
        .where(Booking.id == payment.booking_id)
        .with_for_update()
    )
    if booking.status == BookingStatus.PAYMENT_PENDING:
        booking.status = BookingStatus.CONFIRMED
        booking.version += 1
    elif booking.status != BookingStatus.CONFIRMED:
        payment.last_error_code = "captured_after_booking_closed"


def _apply_failed_payment(payment: Payment) -> None:
    if payment.status in (PaymentStatus.CAPTURED, PaymentStatus.REFUNDED):
        return
    payment.status = PaymentStatus.FAILED
    booking = db.session.scalar(
        select(Booking)
        .where(Booking.id == payment.booking_id)
        .with_for_update()
    )
    if booking.status == BookingStatus.PAYMENT_PENDING:
        now = datetime.now(UTC)
        booking.status = (
            BookingStatus.HELD
            if timestamp_is_after(booking.hold_expires_at, now)
            else BookingStatus.EXPIRED
        )
        booking.version += 1


def _provider_amount_matches(payment: Payment, entity: dict[str, Any]) -> bool:
    return bool(
        entity.get("amount") == payment.amount_subunits
        and entity.get("currency") == payment.currency
    )
