from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from chargemate.extensions import db
from chargemate.models.base import TimestampMixin, UUIDPrimaryKeyMixin


if TYPE_CHECKING:
    from chargemate.models.charge_point import ChargePoint
    from chargemate.models.user import User


class StationStatus(StrEnum):
    """Operational state of a charging station."""

    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"
    MAINTENANCE = "maintenance"


class ChargingStation(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    """A physical location containing one or more bookable charge points."""

    __tablename__ = "charging_stations"
    __table_args__ = (
        CheckConstraint(
            "latitude >= -90 AND latitude <= 90",
            name="valid_latitude",
        ),
        CheckConstraint(
            "longitude >= -180 AND longitude <= 180",
            name="valid_longitude",
        ),
        CheckConstraint(
            "country_code = upper(country_code)",
            name="country_code_uppercase",
        ),
        Index("ix_charging_stations_city_status", "city", "status"),
    )

    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    address_line_1: Mapped[str] = mapped_column(String(255), nullable=False)
    address_line_2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(20), nullable=False)
    country_code: Mapped[str] = mapped_column(
        String(2),
        nullable=False,
        default="IN",
        server_default="IN",
    )
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="Asia/Kolkata",
        server_default="Asia/Kolkata",
    )
    phone: Mapped[str | None] = mapped_column(String(20))
    is_24_hours: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    status: Mapped[StationStatus] = mapped_column(
        Enum(
            StationStatus,
            name="station_status",
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        nullable=False,
        default=StationStatus.DRAFT,
        server_default=StationStatus.DRAFT.value,
    )

    owner: Mapped["User"] = relationship(back_populates="charging_stations")
    charge_points: Mapped[list["ChargePoint"]] = relationship(
        back_populates="station",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
