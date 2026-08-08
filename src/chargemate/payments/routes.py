from flask import Blueprint, g, request
from pydantic import ValidationError

from chargemate.auth.decorators import access_token_required
from chargemate.payments.schemas import CreatePaymentOrderRequest
from chargemate.payments.service import (
    PaymentConfigurationError,
    PaymentProviderError,
    PaymentStateConflictError,
    create_payment_order,
)


payments_blueprint = Blueprint("payments", __name__, url_prefix="/payments")


@payments_blueprint.post("/orders")
@access_token_required
def create_checkout_order():
    """Create or replay an idempotent Razorpay checkout order."""

    try:
        payload = CreatePaymentOrderRequest.model_validate(
            request.get_json(silent=True)
        )
        checkout = create_payment_order(g.current_user, payload)
    except ValidationError as error:
        return {
            "error": {
                "code": "validation_error",
                "message": "The payment order data is invalid.",
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
    except PaymentConfigurationError:
        return {
            "error": {
                "code": "payment_provider_not_configured",
                "message": "The payment provider is unavailable.",
            }
        }, 503
    except PaymentStateConflictError:
        return {
            "error": {
                "code": "payment_state_conflict",
                "message": "Payment cannot be started for this booking state.",
            }
        }, 409
    except PaymentProviderError:
        return {
            "error": {
                "code": "payment_provider_unavailable",
                "message": "The payment provider is temporarily unavailable.",
            }
        }, 502

    payment = checkout.payment
    booking = checkout.booking
    return {
        "payment": {
            "id": str(payment.id),
            "status": payment.status.value,
            "amount": float(payment.amount),
            "amount_subunits": payment.amount_subunits,
            "currency": payment.currency,
            "provider": payment.provider.value,
            "provider_order_id": payment.provider_order_id,
        },
        "booking": {
            "id": str(booking.id),
            "status": booking.status.value,
            "version": booking.version,
        },
        "checkout": {
            "key_id": checkout.public_key_id,
            "order_id": payment.provider_order_id,
            "amount": payment.amount_subunits,
            "currency": payment.currency,
        },
    }, 201
