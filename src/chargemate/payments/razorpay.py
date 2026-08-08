from dataclasses import dataclass
from typing import Any

import httpx


RAZORPAY_ORDERS_URL = "https://api.razorpay.com/v1/orders"
RAZORPAY_PAYMENTS_URL = "https://api.razorpay.com/v1/payments"
RAZORPAY_TIMEOUT_SECONDS = 5.0


class RazorpayOrderError(Exception):
    """Raised when Razorpay does not create a valid order."""


class RazorpayRefundError(Exception):
    """Raised when Razorpay does not create a valid refund."""


@dataclass(frozen=True)
class RazorpayOrder:
    """Provider fields ChargeMate trusts after validating the response."""

    id: str
    amount_subunits: int
    currency: str
    status: str


@dataclass(frozen=True)
class RazorpayRefund:
    """Validated refund fields returned by Razorpay."""

    id: str
    payment_id: str
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


def create_razorpay_refund(
    *,
    key_id: str,
    key_secret: str,
    payment_id: str,
    amount_subunits: int,
    currency: str,
    receipt: str,
    notes: dict[str, str],
) -> RazorpayRefund:
    """Request and validate one normal full refund from Razorpay."""

    try:
        response = httpx.post(
            f"{RAZORPAY_PAYMENTS_URL}/{payment_id}/refund",
            auth=(key_id, key_secret),
            json={
                "amount": amount_subunits,
                "speed": "normal",
                "receipt": receipt,
                "notes": notes,
            },
            timeout=RAZORPAY_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, TypeError, ValueError) as error:
        raise RazorpayRefundError from error

    if not _valid_refund_payload(
        payload,
        payment_id,
        amount_subunits,
        currency,
    ):
        raise RazorpayRefundError

    return RazorpayRefund(
        id=payload["id"],
        payment_id=payload["payment_id"],
        amount_subunits=payload["amount"],
        currency=payload["currency"],
        status=payload["status"],
    )


def fetch_razorpay_refund(
    *,
    key_id: str,
    key_secret: str,
    refund_id: str,
    payment_id: str,
    amount_subunits: int,
    currency: str,
) -> RazorpayRefund:
    """Fetch and validate the latest provider state of one refund."""

    try:
        response = httpx.get(
            f"https://api.razorpay.com/v1/refunds/{refund_id}",
            auth=(key_id, key_secret),
            timeout=RAZORPAY_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, TypeError, ValueError) as error:
        raise RazorpayRefundError from error

    if not _valid_refund_payload(
        payload,
        payment_id,
        amount_subunits,
        currency,
    ) or payload["id"] != refund_id:
        raise RazorpayRefundError

    return RazorpayRefund(
        id=payload["id"],
        payment_id=payload["payment_id"],
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


def _valid_refund_payload(
    payload: Any,
    expected_payment_id: str,
    expected_amount_subunits: int,
    expected_currency: str,
) -> bool:
    return bool(
        isinstance(payload, dict)
        and isinstance(payload.get("id"), str)
        and payload.get("id").startswith("rfnd_")
        and payload.get("payment_id") == expected_payment_id
        and payload.get("amount") == expected_amount_subunits
        and payload.get("currency") == expected_currency
        and payload.get("status") in {"pending", "processed", "failed"}
    )
