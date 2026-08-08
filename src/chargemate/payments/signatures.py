import hashlib
import hmac


def verify_checkout_signature(
    *,
    order_id: str,
    payment_id: str,
    supplied_signature: str,
    key_secret: str,
) -> bool:
    """Verify Razorpay Checkout's order/payment HMAC signature."""

    message = f"{order_id}|{payment_id}".encode("utf-8")
    return _verify_hmac(message, supplied_signature, key_secret)


def verify_webhook_signature(
    *,
    raw_body: bytes,
    supplied_signature: str,
    webhook_secret: str,
) -> bool:
    """Verify a webhook against the exact raw request bytes."""

    return _verify_hmac(raw_body, supplied_signature, webhook_secret)


def sha256_hex(value: bytes) -> str:
    """Return a stable fingerprint without storing the webhook body."""

    return hashlib.sha256(value).hexdigest()


def _verify_hmac(message: bytes, supplied_signature: str, secret: str) -> bool:
    expected = hmac.new(
        secret.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()
    try:
        return hmac.compare_digest(expected, supplied_signature)
    except TypeError:
        return False
