from time import perf_counter
from uuid import UUID, uuid4

from flask import Flask, g, request


def init_security_middleware(app: Flask) -> None:
    """Install request identity, timing, and response security headers."""

    @app.before_request
    def prepare_request_context() -> None:
        g.request_id = _request_id(request.headers.get("X-Request-ID"))
        g.request_started_at = perf_counter()

    @app.after_request
    def secure_response(response):
        response.headers["X-Request-ID"] = g.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'"
        )

        rate_limit = getattr(g, "rate_limit", None)
        if rate_limit is not None:
            response.headers["X-RateLimit-Limit"] = str(rate_limit["limit"])
            response.headers["X-RateLimit-Remaining"] = str(
                rate_limit["remaining"]
            )
        if app.config.get("ENABLE_HSTS", False):
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        duration_ms = (perf_counter() - g.request_started_at) * 1000
        app.logger.info(
            "request_complete method=%s path=%s status=%s duration_ms=%.2f "
            "request_id=%s",
            request.method,
            request.path,
            response.status_code,
            duration_ms,
            g.request_id,
        )
        return response


def _request_id(candidate: str | None) -> str:
    if candidate:
        try:
            return str(UUID(candidate))
        except (ValueError, AttributeError):
            pass
    return str(uuid4())
