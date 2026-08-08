from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreatePaymentOrderRequest(BaseModel):
    """Validated request to begin payment for one held booking."""

    model_config = ConfigDict(extra="forbid")

    booking_id: UUID
    booking_version: int = Field(ge=1)
    idempotency_key: UUID


class VerifyCheckoutPaymentRequest(BaseModel):
    """Razorpay fields returned to the frontend after successful checkout."""

    model_config = ConfigDict(extra="forbid")

    razorpay_order_id: str = Field(min_length=1, max_length=100)
    razorpay_payment_id: str = Field(min_length=1, max_length=100)
    razorpay_signature: str = Field(min_length=64, max_length=64)
