from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from chargemate.extensions import db
from chargemate.models.base import TimestampMixin, UUIDPrimaryKeyMixin


if TYPE_CHECKING:
    from chargemate.models.booking import Booking
    from chargemate.models.user import User


class PaymentProvider(StrEnum):
    """External payment systems supported by ChargeMate."""

    RAZORPAY = "razorpay"


class PaymentStatus(StrEnum):
    """Lifecycle states of one payment attempt."""

    INITIATED = "initiated"
    ORDER_CREATED = "order_created"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    FAILED = "failed"
    REFUNDED = "refunded"


class Payment(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    """A provider payment attempt for a booking's snapshotted amount."""

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="positive_amount"),
        CheckConstraint("amount_subunits > 0", name="positive_amount_subunits"),
        Index("ix_payments_booking_status", "booking_id", "status"),
        Index("ix_payments_user_created", "user_id", "created_at"),
    )

    booking_id: Mapped[UUID] = mapped_column(
        ForeignKey("bookings.id", ondelete="RESTRICT"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider: Mapped[PaymentProvider] = mapped_column(
        Enum(
            PaymentProvider,
            name="payment_provider",
            values_callable=lambda providers: [provider.value for provider in providers],
        ),
        nullable=False,
        default=PaymentProvider.RAZORPAY,
        server_default=PaymentProvider.RAZORPAY.value,
    )
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(
            PaymentStatus,
            name="payment_status",
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        nullable=False,
        default=PaymentStatus.INITIATED,
        server_default=PaymentStatus.INITIATED.value,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    amount_subunits: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="INR",
        server_default="INR",
    )
    idempotency_key: Mapped[UUID] = mapped_column(nullable=False, unique=True)
    provider_order_id: Mapped[str | None] = mapped_column(
        String(100),
        unique=True,
    )
    provider_payment_id: Mapped[str | None] = mapped_column(
        String(100),
        unique=True,
    )
    last_error_code: Mapped[str | None] = mapped_column(String(100))

    booking: Mapped["Booking"] = relationship(back_populates="payments")
    user: Mapped["User"] = relationship(back_populates="payments")
