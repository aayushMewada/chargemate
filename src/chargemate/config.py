import os

from dotenv import load_dotenv


load_dotenv()


class BaseConfig:
    """Configuration shared by every application environment."""

    SECRET_KEY = os.getenv("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    REDIS_URL = os.getenv("REDIS_URL")

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"


class DevelopmentConfig(BaseConfig):
    """Configuration used while developing locally."""

    DEBUG = True


class TestingConfig(BaseConfig):
    """Configuration used by automated tests."""

    TESTING = True
    SECRET_KEY = "testing-only-secret-key"
    SQLALCHEMY_DATABASE_URI = "sqlite+pysqlite:///:memory:"
    REDIS_URL = "redis://localhost:6379/15"


class ProductionConfig(BaseConfig):
    """Configuration used by the deployed application."""

    SESSION_COOKIE_SECURE = True


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
        "DATABASE_URL": configuration.SQLALCHEMY_DATABASE_URI,
        "REDIS_URL": configuration.REDIS_URL,
    }
    missing_values = [name for name, value in required_values.items() if not value]

    if missing_values:
        missing = ", ".join(missing_values)
        raise RuntimeError(f"Missing required environment values: {missing}.")

    return configuration
