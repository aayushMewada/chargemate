from flask import Flask

from chargemate.health import health_blueprint


def create_app() -> Flask:
    """Create and configure the ChargeMate Flask application."""
    app = Flask(__name__)
    app.register_blueprint(health_blueprint)
    return app
