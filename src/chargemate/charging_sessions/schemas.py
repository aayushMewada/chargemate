from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from chargemate.models.charging_session import ChargingSessionStatus


class StartChargingSessionRequest(BaseModel):
    """Validated request to start using a confirmed booking."""

    model_config = ConfigDict(extra="forbid")

    booking_id: UUID
    booking_version: int = Field(ge=1)
    meter_start_kwh: Decimal = Field(ge=0, max_digits=12, decimal_places=3)


class CompleteChargingSessionRequest(BaseModel):
    """Expected session version and final cumulative meter reading."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    meter_end_kwh: Decimal = Field(ge=0, max_digits=12, decimal_places=3)


class ChargingSessionListQuery(BaseModel):
    """Validated filters and pagination for charging history."""

    model_config = ConfigDict(extra="forbid")

    status: ChargingSessionStatus | None = None
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)


class ChargingOperationListQuery(BaseModel):
    """Pagination and optional station filter for an operator queue."""

    model_config = ConfigDict(extra="forbid")

    station_id: UUID | None = None
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)
