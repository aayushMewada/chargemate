import hashlib
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from flask import current_app, g, jsonify, request
from redis import RedisError


P = ParamSpec("P")
R = TypeVar("R")

RATE_LIMIT_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {current, ttl}
"""


def rate_limit(
    scope: str,
    *,
    requests_config: str,
    window_config: str = "RATE_LIMIT_WINDOW_SECONDS",
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Limit a route per client using an atomic Redis fixed window."""

    def decorator(view: Callable[P, R]) -> Callable[P, R]:
        @wraps(view)
        def wrapped(*args: P.args, **kwargs: P.kwargs):
            if not current_app.config.get("RATE_LIMITING_ENABLED", True):
                return view(*args, **kwargs)

            limit = int(current_app.config[requests_config])
            window_seconds = int(current_app.config[window_config])
            key = _rate_limit_key(scope, _client_address())
            try:
                count, ttl = current_app.extensions["redis"].eval(
                    RATE_LIMIT_SCRIPT,
                    1,
                    key,
                    window_seconds,
                )
                count = int(count)
                ttl = max(int(ttl), 0)
            except (RedisError, TypeError, ValueError):
                current_app.logger.warning(
                    "Rate-limit check failed for scope %s.",
                    scope,
                    exc_info=True,
                )
                return view(*args, **kwargs)

            g.rate_limit = {
                "limit": limit,
                "remaining": max(limit - count, 0),
                "retry_after": ttl,
            }
            if count <= limit:
                return view(*args, **kwargs)

            response = jsonify(
                {
                    "error": {
                        "code": "rate_limit_exceeded",
                        "message": "Too many requests. Please try again later.",
                    }
                }
            )
            response.status_code = 429
            response.headers["Retry-After"] = str(ttl)
            return response

        return wrapped

    return decorator


def _client_address() -> str:
    if current_app.config.get("TRUST_PROXY_HEADERS", False):
        forwarded_for = request.headers.get("X-Forwarded-For", "")
        first_address = forwarded_for.split(",", 1)[0].strip()
        if first_address:
            return first_address
    return request.remote_addr or "unknown"


def _rate_limit_key(scope: str, client_address: str) -> str:
    digest = hashlib.sha256(client_address.encode("utf-8")).hexdigest()
    return f"chargemate:rate-limit:{scope}:{digest}"
