from flask import Flask

from chargemate import models  # noqa: F401
from chargemate.auth.routes import auth_blueprint
from chargemate.bookings.routes import bookings_blueprint
from chargemate.charging_sessions.routes import charging_sessions_blueprint
from chargemate.payments.routes import payments_blueprint
from chargemate.stations.routes import stations_blueprint
from chargemate.config import BaseConfig, get_config
from chargemate.extensions import init_extensions
from chargemate.health import health_blueprint
from chargemate.security.middleware import init_security_middleware


def create_app(config: type[BaseConfig] | None = None) -> Flask:
    """Create and configure the ChargeMate Flask application."""
    app = Flask(__name__)
    app.config.from_object(config or get_config())
    init_extensions(app)
    init_security_middleware(app)
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(bookings_blueprint)
    app.register_blueprint(charging_sessions_blueprint)
    app.register_blueprint(payments_blueprint)
    app.register_blueprint(stations_blueprint)
    app.register_blueprint(health_blueprint)
    return app
