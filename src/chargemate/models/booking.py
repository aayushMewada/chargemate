from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from chargemate.extensions import db
from chargemate.models.base import TimestampMixin, UUIDPrimaryKeyMixin


if TYPE_CHECKING:
    from chargemate.models.charge_point import ChargePoint
    from chargemate.models.user import User


class BookingStatus(StrEnum):
    """Lifecycle states for a charging-slot reservation."""

    HELD = "held"
    PAYMENT_PENDING = "payment_pending"
    CONFIRMED = "confirmed"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class Booking(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    """A time-bounded reservation for one independently bookable charge point."""

    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="positive_duration"),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint(
            "total_amount IS NULL OR total_amount >= 0",
            name="non_negative_total_amount",
        ),
        Index("ix_bookings_user_status", "user_id", "status"),
        Index(
            "ix_bookings_charge_point_start",
            "charge_point_id",
            "starts_at",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    charge_point_id: Mapped[UUID] = mapped_column(
        ForeignKey("charge_points.id", ondelete="RESTRICT"),
        nullable=False,
    )
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    ends_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    hold_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    status: Mapped[BookingStatus] = mapped_column(
        Enum(
            BookingStatus,
            name="booking_status",
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        nullable=False,
        default=BookingStatus.HELD,
        server_default=BookingStatus.HELD.value,
    )
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="INR",
        server_default="INR",
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="bookings")
    charge_point: Mapped["ChargePoint"] = relationship(back_populates="bookings")
