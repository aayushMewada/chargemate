import os

from dotenv import load_dotenv


load_dotenv()


class BaseConfig:
    """Configuration shared by every application environment."""

    SECRET_KEY = os.getenv("SECRET_KEY")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    REDIS_URL = os.getenv("REDIS_URL")
    OPEN_CHARGE_MAP_API_KEY = os.getenv("OPEN_CHARGE_MAP_API_KEY")
    RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
    RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
    RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET")

    LOGIN_MAX_FAILED_ATTEMPTS = 5
    LOGIN_LOCKOUT_MINUTES = 15
    JWT_ACCESS_TOKEN_MINUTES = 15
    JWT_REFRESH_TOKEN_DAYS = 30
    JWT_ALGORITHM = "HS256"
    JWT_ISSUER = "chargemate-api"
    JWT_AUDIENCE = "chargemate-client"

    REFRESH_COOKIE_NAME = "refresh_token"
    REFRESH_COOKIE_PATH = "/auth"
    REFRESH_COOKIE_HTTPONLY = True
    REFRESH_COOKIE_SECURE = False
    REFRESH_COOKIE_SAMESITE = "Lax"

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    RATE_LIMITING_ENABLED = True
    RATE_LIMIT_WINDOW_SECONDS = 60
    REGISTER_RATE_LIMIT_REQUESTS = 5
    LOGIN_RATE_LIMIT_REQUESTS = 10
    REFRESH_RATE_LIMIT_REQUESTS = 30
    EXTERNAL_STATION_RATE_LIMIT_REQUESTS = 30
    TRUST_PROXY_HEADERS = False
    ENABLE_HSTS = False


class DevelopmentConfig(BaseConfig):
    """Configuration used while developing locally."""

    DEBUG = True


class TestingConfig(BaseConfig):
    """Configuration used by automated tests."""

    TESTING = True
    SECRET_KEY = "testing-only-secret-key"
    JWT_SECRET_KEY = "testing-only-jwt-secret-key-at-least-32-bytes"
    SQLALCHEMY_DATABASE_URI = "sqlite+pysqlite:///:memory:"
    REDIS_URL = "redis://localhost:6379/15"
    RATE_LIMITING_ENABLED = False


class ProductionConfig(BaseConfig):
    """Configuration used by the deployed application."""

    SESSION_COOKIE_SECURE = True
    REFRESH_COOKIE_SECURE = True
    ENABLE_HSTS = True


CONFIGURATIONS: dict[str, type[BaseConfig]] = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config() -> type[BaseConfig]:
    """Return the configuration selected by APP_ENV."""
    environment = os.getenv("APP_ENV", "development").lower()

    try:
        configuration = CONFIGURATIONS[environment]
    except KeyError as error:
        supported = ", ".join(CONFIGURATIONS)
        raise RuntimeError(
            f"Unsupported APP_ENV '{environment}'. Choose one of: {supported}."
        ) from error

    required_values = {
        "SECRET_KEY": configuration.SECRET_KEY,
        "JWT_SECRET_KEY": configuration.JWT_SECRET_KEY,
        "DATABASE_URL": configuration.SQLALCHEMY_DATABASE_URI,
        "REDIS_URL": configuration.REDIS_URL,
    }
    missing_values = [name for name, value in required_values.items() if not value]

    if missing_values:
        missing = ", ".join(missing_values)
        raise RuntimeError(f"Missing required environment values: {missing}.")

    return configuration
