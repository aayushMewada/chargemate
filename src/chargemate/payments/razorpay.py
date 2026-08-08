from dataclasses import dataclass
from typing import Any

import httpx


RAZORPAY_ORDERS_URL = "https://api.razorpay.com/v1/orders"
RAZORPAY_TIMEOUT_SECONDS = 5.0


class RazorpayOrderError(Exception):
    """Raised when Razorpay does not create a valid order."""


@dataclass(frozen=True)
class RazorpayOrder:
    """Provider fields ChargeMate trusts after validating the response."""

    id: str
    amount_subunits: int
    currency: str
    status: str


def create_razorpay_order(
    *,
    key_id: str,
    key_secret: str,
    amount_subunits: int,
    currency: str,
    receipt: str,
    notes: dict[str, str],
) -> RazorpayOrder:
    """Create and validate one Razorpay order using server-side credentials."""

    try:
        response = httpx.post(
            RAZORPAY_ORDERS_URL,
            auth=(key_id, key_secret),
            json={
                "amount": amount_subunits,
                "currency": currency,
                "receipt": receipt,
                "notes": notes,
            },
            timeout=RAZORPAY_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, TypeError, ValueError) as error:
        raise RazorpayOrderError from error

    if not _valid_order_payload(payload, amount_subunits, currency):
        raise RazorpayOrderError

    return RazorpayOrder(
        id=payload["id"],
        amount_subunits=payload["amount"],
        currency=payload["currency"],
        status=payload["status"],
    )


def _valid_order_payload(
    payload: Any,
    expected_amount_subunits: int,
    expected_currency: str,
) -> bool:
    return bool(
        isinstance(payload, dict)
        and isinstance(payload.get("id"), str)
        and payload.get("id").startswith("order_")
        and payload.get("amount") == expected_amount_subunits
        and payload.get("currency") == expected_currency
        and payload.get("status") == "created"
    )
