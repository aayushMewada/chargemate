from flask import Blueprint, current_app, g, request
from pydantic import ValidationError

from chargemate.auth.decorators import access_token_required
from chargemate.payments.schemas import (
    CreatePaymentOrderRequest,
    VerifyCheckoutPaymentRequest,
)
from chargemate.payments.service import (
    PaymentConfigurationError,
    PaymentProviderError,
    PaymentStateConflictError,
    PaymentVerificationError,
    create_payment_order,
    verify_checkout_payment,
)
from chargemate.payments.webhooks import (
    WebhookAuthenticationError,
    WebhookPayloadError,
    process_razorpay_webhook,
)


payments_blueprint = Blueprint("payments", __name__, url_prefix="/payments")


@payments_blueprint.post("/verify")
@access_token_required
def verify_checkout():
    """Verify the signed browser callback and record authorization."""

    try:
        payload = VerifyCheckoutPaymentRequest.model_validate(
            request.get_json(silent=True)
        )
        payment = verify_checkout_payment(g.current_user, payload)
    except ValidationError as error:
        return _validation_error_response(error)
    except PaymentConfigurationError:
        return _provider_not_configured_response()
    except PaymentVerificationError:
        return {
            "error": {
                "code": "payment_verification_failed",
                "message": "The payment details could not be verified.",
            }
        }, 400

    return {
        "payment": {
            "id": str(payment.id),
            "status": payment.status.value,
            "provider_order_id": payment.provider_order_id,
            "provider_payment_id": payment.provider_payment_id,
        }
    }, 200


@payments_blueprint.post("/webhooks/razorpay")
def razorpay_webhook():
    """Authenticate and idempotently process a Razorpay webhook."""

    webhook_secret = current_app.config.get("RAZORPAY_WEBHOOK_SECRET")
    if not webhook_secret:
        return _provider_not_configured_response()

    try:
        outcome = process_razorpay_webhook(
            raw_body=request.get_data(cache=True, as_text=False),
            supplied_signature=request.headers.get("X-Razorpay-Signature"),
            provider_event_id=request.headers.get("X-Razorpay-Event-Id"),
            webhook_secret=webhook_secret,
        )
    except WebhookAuthenticationError:
        return {
            "error": {
                "code": "invalid_webhook_signature",
                "message": "The webhook could not be authenticated.",
            }
        }, 400
    except WebhookPayloadError:
        return {
            "error": {
                "code": "invalid_webhook_payload",
                "message": "The webhook payload is invalid.",
            }
        }, 400

    return {"status": outcome.status}, 200


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
        return _validation_error_response(error)
    except PaymentConfigurationError:
        return _provider_not_configured_response()
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


def _validation_error_response(error: ValidationError) -> tuple[dict, int]:
    return {
        "error": {
            "code": "validation_error",
            "message": "The payment data is invalid.",
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


def _provider_not_configured_response() -> tuple[dict, int]:
    return {
        "error": {
            "code": "payment_provider_not_configured",
            "message": "The payment provider is unavailable.",
        }
    }, 503
