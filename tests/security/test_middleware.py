from uuid import UUID, uuid4

from redis import RedisError


LOGIN_PAYLOAD = {
    "identifier": "missing@example.com",
    "password": "Incorrect-Password-2026",
}


class FakeRateLimitRedis:
    """Small deterministic substitute for the Redis Lua result."""

    def __init__(self):
        self.counters = {}

    def eval(self, _script, _key_count, key, window_seconds):
        self.counters[key] = self.counters.get(key, 0) + 1
        return [self.counters[key], window_seconds]


class FailingRateLimitRedis:
    def eval(self, *_args):
        raise RedisError("Redis unavailable")


def _enable_login_limit(app, redis_client, limit: int = 2):
    app.config["RATE_LIMITING_ENABLED"] = True
    app.config["LOGIN_RATE_LIMIT_REQUESTS"] = limit
    app.config["RATE_LIMIT_WINDOW_SECONDS"] = 60
    app.extensions["redis"] = redis_client


def test_response_contains_request_identity_and_security_headers(client):
    request_id = str(uuid4())

    response = client.get("/health", headers={"X-Request-ID": request_id})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == request_id
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Content-Security-Policy"] == (
        "default-src 'none'; frame-ancestors 'none'"
    )


def test_invalid_request_id_is_replaced(client):
    response = client.get(
        "/health",
        headers={"X-Request-ID": "not-a-uuid"},
    )

    generated_id = response.headers["X-Request-ID"]
    assert generated_id != "not-a-uuid"
    assert str(UUID(generated_id)) == generated_id


def test_login_rate_limit_returns_429_with_retry_headers(client, app):
    _enable_login_limit(app, FakeRateLimitRedis())

    first = client.post("/auth/login", json=LOGIN_PAYLOAD)
    second = client.post("/auth/login", json=LOGIN_PAYLOAD)
    blocked = client.post("/auth/login", json=LOGIN_PAYLOAD)

    assert first.status_code == 401
    assert second.status_code == 401
    assert blocked.status_code == 429
    assert blocked.get_json()["error"]["code"] == "rate_limit_exceeded"
    assert blocked.headers["Retry-After"] == "60"
    assert blocked.headers["X-RateLimit-Limit"] == "2"
    assert blocked.headers["X-RateLimit-Remaining"] == "0"


def test_rate_limits_are_isolated_by_client_address(client, app):
    _enable_login_limit(app, FakeRateLimitRedis(), limit=1)

    first_client = client.post(
        "/auth/login",
        json=LOGIN_PAYLOAD,
        environ_base={"REMOTE_ADDR": "192.0.2.10"},
    )
    second_client = client.post(
        "/auth/login",
        json=LOGIN_PAYLOAD,
        environ_base={"REMOTE_ADDR": "192.0.2.11"},
    )

    assert first_client.status_code == 401
    assert second_client.status_code == 401


def test_rate_limiter_fails_open_when_redis_is_unavailable(client, app):
    _enable_login_limit(app, FailingRateLimitRedis(), limit=1)

    first = client.post("/auth/login", json=LOGIN_PAYLOAD)
    second = client.post("/auth/login", json=LOGIN_PAYLOAD)

    assert first.status_code == 401
    assert second.status_code == 401


def test_hsts_is_only_added_when_enabled(client, app):
    without_hsts = client.get("/health")
    app.config["ENABLE_HSTS"] = True
    with_hsts = client.get("/health")

    assert "Strict-Transport-Security" not in without_hsts.headers
    assert with_hsts.headers["Strict-Transport-Security"] == (
        "max-age=31536000; includeSubDomains"
    )
