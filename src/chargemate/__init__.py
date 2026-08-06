from flask import Flask

from chargemate.config import BaseConfig, get_config
from chargemate.extensions import init_extensions
from chargemate.health import health_blueprint


def create_app(config: type[BaseConfig] | None = None) -> Flask:
    """Create and configure the ChargeMate Flask application."""
    app = Flask(__name__)
    app.config.from_object(config or get_config())
    init_extensions(app)
    app.register_blueprint(health_blueprint)
    return app
