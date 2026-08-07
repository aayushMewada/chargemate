from sqlalchemy.exc import IntegrityError

from chargemate.extensions import db
from chargemate.models.charge_point import ChargePoint
from chargemate.models.station import ChargingStation
from chargemate.models.user import User
from chargemate.stations.schemas import StationCreateRequest


class StationConflictError(Exception):
    """Raised when station data conflicts with a database constraint."""


def create_station(owner: User, payload: StationCreateRequest) -> ChargingStation:
    """Create a station and all its initial charge points atomically."""

    station_data = payload.model_dump(exclude={"charge_points"})
    station = ChargingStation(owner_id=owner.id, **station_data)

    station.charge_points = [
        ChargePoint(**charge_point.model_dump())
        for charge_point in payload.charge_points
    ]

    try:
        db.session.add(station)
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        raise StationConflictError from error
    except Exception:
        db.session.rollback()
        raise

    return station
