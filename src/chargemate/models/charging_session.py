from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from chargemate.extensions import db
from chargemate.models.base import TimestampMixin, UUIDPrimaryKeyMixin


if TYPE_CHECKING:
    from chargemate.models.booking import Booking
    from chargemate.models.charge_point import ChargePoint
    from chargemate.models.user import User


class ChargingSessionStatus(StrEnum):
    """Lifecycle states for actual charger usage."""

    ACTIVE = "active"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"


class ChargingSession(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    """Metered charger usage created from one confirmed booking."""

    __tablename__ = "charging_sessions"
    __table_args__ = (
        CheckConstraint("meter_start_kwh >= 0", name="non_negative_meter_start"),
        CheckConstraint(
            "meter_end_kwh IS NULL OR meter_end_kwh >= meter_start_kwh",
            name="valid_meter_end",
        ),
        CheckConstraint(
            "energy_consumed_kwh IS NULL OR energy_consumed_kwh >= 0",
            name="non_negative_energy_consumed",
        ),
        CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at",
            name="valid_end_time",
        ),
        CheckConstraint("version > 0", name="positive_version"),
        Index("ix_charging_sessions_user_status", "user_id", "status"),
        Index("ix_charging_sessions_charge_point_status", "charge_point_id", "status"),
    )

    booking_id: Mapped[UUID] = mapped_column(
        ForeignKey("bookings.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    charge_point_id: Mapped[UUID] = mapped_column(
        ForeignKey("charge_points.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[ChargingSessionStatus] = mapped_column(
        Enum(
            ChargingSessionStatus,
            name="charging_session_status",
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        nullable=False,
        default=ChargingSessionStatus.ACTIVE,
        server_default=ChargingSessionStatus.ACTIVE.value,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    meter_start_kwh: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    meter_end_kwh: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    energy_consumed_kwh: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )

    booking: Mapped["Booking"] = relationship(back_populates="charging_session")
    user: Mapped["User"] = relationship(back_populates="charging_sessions")
    charge_point: Mapped["ChargePoint"] = relationship(
        back_populates="charging_sessions"
    )
