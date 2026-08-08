from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from chargemate.extensions import db
from chargemate.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class WebhookEventStatus(StrEnum):
    """Processing outcome for one authenticated provider event."""

    RECEIVED = "received"
    PROCESSED = "processed"
    IGNORED = "ignored"


class PaymentWebhookEvent(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    """A durable idempotency record for a Razorpay webhook delivery."""

    __tablename__ = "payment_webhook_events"

    provider: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="razorpay",
        server_default="razorpay",
    )
    provider_event_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[WebhookEventStatus] = mapped_column(
        Enum(
            WebhookEventStatus,
            name="webhook_event_status",
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        nullable=False,
        default=WebhookEventStatus.RECEIVED,
        server_default=WebhookEventStatus.RECEIVED.value,
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
