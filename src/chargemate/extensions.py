from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from redis import Redis
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for every SQLAlchemy model."""


db = SQLAlchemy(model_class=Base)


def init_extensions(app: Flask) -> None:
    """Connect Flask extensions to an application instance."""
    db.init_app(app)

    redis_client = Redis.from_url(
        app.config["REDIS_URL"],
        decode_responses=True,
    )
    app.extensions["redis"] = redis_client
