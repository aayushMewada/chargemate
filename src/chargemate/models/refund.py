from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from chargemate.extensions import db
from chargemate.models.base import TimestampMixin, UUIDPrimaryKeyMixin


if TYPE_CHECKING:
    from chargemate.models.payment import Payment


class RefundStatus(StrEnum):
    """Lifecycle states of one full-payment refund."""

    REQUESTED = "requested"
    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"


class Refund(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    """A durable, idempotent request to return a captured payment."""

    __tablename__ = "refunds"
    __table_args__ = (
        CheckConstraint("amount > 0", name="positive_amount"),
        CheckConstraint("amount_subunits > 0", name="positive_amount_subunits"),
    )

    payment_id: Mapped[UUID] = mapped_column(
        ForeignKey("payments.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    status: Mapped[RefundStatus] = mapped_column(
        Enum(
            RefundStatus,
            name="refund_status",
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        nullable=False,
        default=RefundStatus.REQUESTED,
        server_default=RefundStatus.REQUESTED.value,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    amount_subunits: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    receipt: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    provider_refund_id: Mapped[str | None] = mapped_column(
        String(100),
        unique=True,
    )
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    payment: Mapped["Payment"] = relationship(back_populates="refund")
