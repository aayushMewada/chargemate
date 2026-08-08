from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreatePaymentOrderRequest(BaseModel):
    """Validated request to begin payment for one held booking."""

    model_config = ConfigDict(extra="forbid")

    booking_id: UUID
    booking_version: int = Field(ge=1)
    idempotency_key: UUID
