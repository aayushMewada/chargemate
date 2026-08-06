from typing import cast

from flask import Blueprint, current_app
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from chargemate.extensions import db


health_blueprint = Blueprint("health", __name__)


@health_blueprint.get("/health")
@health_blueprint.get("/health/live")
def liveness() -> tuple[dict[str, str], int]:
    """Report whether the Flask process can serve requests."""
    return {"status": "healthy"}, 200


@health_blueprint.get("/health/ready")
def readiness() -> tuple[dict[str, object], int]:
    """Report whether the application dependencies are available."""
    services = {
        "postgres": _postgres_is_healthy(),
        "redis": _redis_is_healthy(),
    }
    is_ready = all(status == "healthy" for status in services.values())

    return {
        "status": "ready" if is_ready else "not_ready",
        "services": services,
    }, 200 if is_ready else 503


def _postgres_is_healthy() -> str:
    """Check PostgreSQL with a minimal query."""
    try:
        with db.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        current_app.logger.exception("PostgreSQL readiness check failed.")
        return "unhealthy"

    return "healthy"


def _redis_is_healthy() -> str:
    """Check Redis with its PING command."""
    redis_client = cast(Redis, current_app.extensions["redis"])

    try:
        redis_client.ping()
    except RedisError:
        current_app.logger.exception("Redis readiness check failed.")
        return "unhealthy"

    return "healthy"
