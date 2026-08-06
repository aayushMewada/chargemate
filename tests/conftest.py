from collections.abc import Iterator

import pytest
from flask import Flask
from flask.testing import FlaskClient

from chargemate import create_app
from chargemate.config import TestingConfig
from chargemate.extensions import db


@pytest.fixture
def app() -> Iterator[Flask]:
    """Provide a fresh application and in-memory database for each test."""
    test_app = create_app(TestingConfig)

    with test_app.app_context():
        db.create_all()

    yield test_app

    with test_app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def db_app(app: Flask) -> Iterator[Flask]:
    """Keep an application context open for direct service tests."""
    with app.app_context():
        yield app


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Provide Flask's in-process HTTP client for endpoint tests."""
    return app.test_client()
