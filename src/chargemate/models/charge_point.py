from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from chargemate.extensions import db
from chargemate.models.base import TimestampMixin, UUIDPrimaryKeyMixin


if TYPE_CHECKING:
    from chargemate.models.booking import Booking
    from chargemate.models.charging_session import ChargingSession
    from chargemate.models.station import ChargingStation


class ConnectorType(StrEnum):
    """Physical connector standards supported by ChargeMate."""

    CCS_2 = "ccs_2"
    TYPE_2 = "type_2"
    CHADEMO = "chademo"
    GB_T = "gb_t"
    BHARAT_DC_001 = "bharat_dc_001"


class PowerType(StrEnum):
    """Electrical current supplied by a charge point."""

    AC = "ac"
    DC = "dc"


class ChargePointStatus(StrEnum):
    """Current operational state of an individual charge point."""

    AVAILABLE = "available"
    OUT_OF_SERVICE = "out_of_service"
    MAINTENANCE = "maintenance"
    RETIRED = "retired"


class ChargePoint(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    """One independently bookable charging unit at a station."""

    __tablename__ = "charge_points"
    __table_args__ = (
        UniqueConstraint("station_id", "code", name="station_code"),
        CheckConstraint("max_power_kw > 0", name="positive_max_power_kw"),
        CheckConstraint("booking_fee >= 0", name="non_negative_booking_fee"),
    )

    station_id: Mapped[UUID] = mapped_column(
        ForeignKey("charging_stations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    connector_type: Mapped[ConnectorType] = mapped_column(
        Enum(
            ConnectorType,
            name="connector_type",
            values_callable=lambda connectors: [connector.value for connector in connectors],
        ),
        nullable=False,
    )
    power_type: Mapped[PowerType] = mapped_column(
        Enum(
            PowerType,
            name="power_type",
            values_callable=lambda power_types: [power_type.value for power_type in power_types],
        ),
        nullable=False,
    )
    max_power_kw: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    booking_fee: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("50.00"),
        server_default="50.00",
    )
    is_bookable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    status: Mapped[ChargePointStatus] = mapped_column(
        Enum(
            ChargePointStatus,
            name="charge_point_status",
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        nullable=False,
        default=ChargePointStatus.AVAILABLE,
        server_default=ChargePointStatus.AVAILABLE.value,
    )

    station: Mapped["ChargingStation"] = relationship(back_populates="charge_points")
    bookings: Mapped[list["Booking"]] = relationship(
        back_populates="charge_point",
        passive_deletes=True,
    )
    charging_sessions: Mapped[list["ChargingSession"]] = relationship(
        back_populates="charge_point",
        passive_deletes=True,
    )
