from datetime import datetime, timedelta
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from chargemate.models.booking import BookingStatus


MAXIMUM_BOOKING_DURATION = timedelta(hours=8)


class BookingHoldRequest(BaseModel):
    """Validated request for temporarily holding a charging time slot."""

    model_config = ConfigDict(extra="forbid")

    charge_point_id: UUID
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode="after")
    def validate_time_range(self) -> "BookingHoldRequest":
        if self.starts_at.utcoffset() is None or self.ends_at.utcoffset() is None:
            raise ValueError("starts_at and ends_at must include a timezone")
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be later than starts_at")
        if self.ends_at - self.starts_at > MAXIMUM_BOOKING_DURATION:
            raise ValueError("a booking cannot exceed eight hours")
        return self


class BookingListQuery(BaseModel):
    """Validated filters and pagination for a user's booking history."""

    model_config = ConfigDict(extra="forbid")

    status: BookingStatus | None = None
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)


class CancelBookingRequest(BaseModel):
    """The booking version the client expects to cancel."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
