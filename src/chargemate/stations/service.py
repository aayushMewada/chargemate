from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from chargemate.extensions import db
from chargemate.models.charge_point import ChargePoint, ChargePointStatus
from chargemate.models.station import ChargingStation, StationStatus
from chargemate.models.user import User
from chargemate.stations.schemas import StationCreateRequest, StationSearchQuery


class StationConflictError(Exception):
    """Raised when station data conflicts with a database constraint."""


@dataclass(frozen=True)
class StationPage:
    """One page of public stations plus pagination metadata."""

    items: list[ChargingStation]
    total: int
    page: int
    per_page: int


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


def find_public_stations(query: StationSearchQuery) -> StationPage:
    """Return active stations matching optional public search filters."""

    filters = [ChargingStation.status == StationStatus.ACTIVE]

    if query.city is not None:
        filters.append(func.lower(ChargingStation.city) == query.city.lower())

    charge_point_filters = []
    if query.connector_type is not None:
        charge_point_filters.append(
            ChargePoint.connector_type == query.connector_type
        )
    if query.min_power_kw is not None:
        charge_point_filters.append(ChargePoint.max_power_kw >= query.min_power_kw)

    if charge_point_filters:
        charge_point_filters.append(
            ChargePoint.status == ChargePointStatus.AVAILABLE
        )
        charge_point_filters.append(ChargePoint.is_bookable.is_(True))
        filters.append(
            ChargingStation.charge_points.any(and_(*charge_point_filters))
        )

    total = db.session.scalar(
        select(func.count()).select_from(ChargingStation).where(*filters)
    )
    stations = db.session.scalars(
        select(ChargingStation)
        .options(selectinload(ChargingStation.charge_points))
        .where(*filters)
        .order_by(ChargingStation.name, ChargingStation.id)
        .offset((query.page - 1) * query.per_page)
        .limit(query.per_page)
    ).all()

    return StationPage(
        items=list(stations),
        total=total or 0,
        page=query.page,
        per_page=query.per_page,
    )


def get_public_station(station_id: UUID) -> ChargingStation | None:
    """Return an active station with its charge points, if it exists."""

    return db.session.scalar(
        select(ChargingStation)
        .options(selectinload(ChargingStation.charge_points))
        .where(
            ChargingStation.id == station_id,
            ChargingStation.status == StationStatus.ACTIVE,
        )
    )
