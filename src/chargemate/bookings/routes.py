from flask import Blueprint, g, request
from pydantic import ValidationError

from chargemate.auth.decorators import access_token_required
from chargemate.bookings.schemas import BookingHoldRequest
from chargemate.bookings.service import (
    BookingTimeError,
    BookingUnavailableError,
    create_booking_hold,
)
from chargemate.models.booking import Booking


bookings_blueprint = Blueprint("bookings", __name__, url_prefix="/bookings")


@bookings_blueprint.post("")
@access_token_required
def create_booking():
    """Create a short-lived hold for an available charging time slot."""

    try:
        payload = BookingHoldRequest.model_validate(request.get_json(silent=True))
        booking = create_booking_hold(g.current_user, payload)
    except ValidationError as error:
        return {
            "error": {
                "code": "validation_error",
                "message": "The booking data is invalid.",
                "details": [
                    {
                        "location": list(detail["loc"]),
                        "message": detail["msg"],
                        "type": detail["type"],
                    }
                    for detail in error.errors(
                        include_url=False,
                        include_input=False,
                    )
                ],
            }
        }, 422
    except BookingTimeError:
        return {
            "error": {
                "code": "invalid_booking_time",
                "message": "The booking must start in the future.",
            }
        }, 422
    except BookingUnavailableError:
        return {
            "error": {
                "code": "booking_unavailable",
                "message": "The charging slot is unavailable.",
            }
        }, 409

    return {"booking": _serialize_booking(booking)}, 201


def _serialize_booking(booking: Booking) -> dict:
    return {
        "id": str(booking.id),
        "user_id": str(booking.user_id),
        "charge_point_id": str(booking.charge_point_id),
        "starts_at": booking.starts_at.isoformat(),
        "ends_at": booking.ends_at.isoformat(),
        "hold_expires_at": booking.hold_expires_at.isoformat(),
        "status": booking.status.value,
        "total_amount": (
            float(booking.total_amount)
            if booking.total_amount is not None
            else None
        ),
        "currency": booking.currency,
        "version": booking.version,
        "created_at": booking.created_at.isoformat(),
    }
