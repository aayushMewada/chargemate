from flask import Blueprint, g, request
from pydantic import ValidationError

from chargemate.auth.decorators import access_token_required
from chargemate.bookings.schemas import (
    BookingHoldRequest,
    BookingListQuery,
    CancelBookingRequest,
)
from chargemate.bookings.cancellation import cancel_booking_with_refund
from chargemate.bookings.service import (
    BookingStateConflictError,
    BookingTimeError,
    BookingUnavailableError,
    create_booking_hold,
    find_user_bookings,
    get_user_booking,
)
from chargemate.models.booking import Booking
from chargemate.models.refund import Refund, RefundStatus


bookings_blueprint = Blueprint("bookings", __name__, url_prefix="/bookings")


@bookings_blueprint.get("/me")
@access_token_required
def list_my_bookings():
    """Return the authenticated user's filtered booking history."""

    try:
        query = BookingListQuery.model_validate(request.args)
    except ValidationError as error:
        return _validation_error_response(error)

    booking_page = find_user_bookings(g.current_user.id, query)
    return {
        "bookings": [_serialize_booking(booking) for booking in booking_page.items],
        "pagination": {
            "page": booking_page.page,
            "per_page": booking_page.per_page,
            "total": booking_page.total,
            "pages": (
                booking_page.total + booking_page.per_page - 1
            )
            // booking_page.per_page,
        },
    }, 200


@bookings_blueprint.get("/<uuid:booking_id>")
@access_token_required
def get_my_booking(booking_id):
    """Return one booking only when it belongs to the authenticated user."""

    booking = get_user_booking(g.current_user.id, booking_id)
    if booking is None:
        return _booking_not_found_response()
    return {"booking": _serialize_booking(booking)}, 200


@bookings_blueprint.post("/<uuid:booking_id>/cancel")
@access_token_required
def cancel_my_booking(booking_id):
    """Cancel a booking and initiate a full refund when money was captured."""

    try:
        payload = CancelBookingRequest.model_validate(request.get_json(silent=True))
        outcome = cancel_booking_with_refund(
            g.current_user.id,
            booking_id,
            payload.version,
        )
    except ValidationError as error:
        return _validation_error_response(error)
    except BookingStateConflictError:
        return {
            "error": {
                "code": "booking_state_conflict",
                "message": "The booking changed or can no longer be cancelled.",
            }
        }, 409

    response = {"booking": _serialize_booking(outcome.booking)}
    if outcome.refund is None:
        return response, 200

    response["refund"] = _serialize_refund(outcome.refund)
    if outcome.provider_error or outcome.refund.status == RefundStatus.FAILED:
        response["error"] = {
            "code": "refund_provider_unavailable",
            "message": (
                "The booking was cancelled, but the refund requires attention."
            ),
        }
        return response, 502
    if outcome.refund.status in (RefundStatus.REQUESTED, RefundStatus.PENDING):
        return response, 202
    return response, 200


@bookings_blueprint.post("")
@access_token_required
def create_booking():
    """Create a short-lived hold for an available charging time slot."""

    try:
        payload = BookingHoldRequest.model_validate(request.get_json(silent=True))
        booking = create_booking_hold(g.current_user, payload)
    except ValidationError as error:
        return _validation_error_response(error)
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


def _serialize_refund(refund: Refund) -> dict:
    return {
        "id": str(refund.id),
        "payment_id": str(refund.payment_id),
        "status": refund.status.value,
        "amount": float(refund.amount),
        "currency": refund.currency,
        "provider_refund_id": refund.provider_refund_id,
        "processed_at": (
            refund.processed_at.isoformat()
            if refund.processed_at is not None
            else None
        ),
    }


def _validation_error_response(error: ValidationError) -> tuple[dict, int]:
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


def _booking_not_found_response() -> tuple[dict, int]:
    return {
        "error": {
            "code": "booking_not_found",
            "message": "The booking was not found.",
        }
    }, 404
