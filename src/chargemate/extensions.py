from flask import Flask
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from redis import Redis
from rq import Queue
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class for every SQLAlchemy model."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


db = SQLAlchemy(model_class=Base)
migrate = Migrate()


def init_extensions(app: Flask) -> None:
    """Connect Flask extensions to an application instance."""
    db.init_app(app)
    migrate.init_app(app, db)

    redis_client = Redis.from_url(
        app.config["REDIS_URL"],
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    app.extensions["redis"] = redis_client

    rq_redis = Redis.from_url(
        app.config["REDIS_URL"],
        decode_responses=False,
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    app.extensions["rq_redis"] = rq_redis
    app.extensions["maintenance_queue"] = Queue(
        app.config["RQ_MAINTENANCE_QUEUE"],
        connection=rq_redis,
        default_timeout=app.config["RQ_JOB_TIMEOUT_SECONDS"],
    )
