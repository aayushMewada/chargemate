from flask import Blueprint


health_blueprint = Blueprint("health", __name__)


@health_blueprint.get("/health")
def health() -> tuple[dict[str, str], int]:
    """Report whether the web application is running."""
    return {"status": "healthy"}, 200
