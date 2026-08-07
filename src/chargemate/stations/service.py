from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, func, literal, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from chargemate.extensions import db
from chargemate.models.charge_point import ChargePoint, ChargePointStatus
from chargemate.models.station import ChargingStation, StationStatus
from chargemate.models.user import User
from chargemate.stations.schemas import StationCreateRequest, StationSearchQuery
from chargemate.stations.spatial import (
    METRES_PER_KILOMETRE,
    search_geography,
    station_geography,
)


class StationConflictError(Exception):
    """Raised when station data conflicts with a database constraint."""


@dataclass(frozen=True)
class StationPage:
    """One page of public stations plus pagination metadata."""

    items: list["StationSearchResult"]
    total: int
    page: int
    per_page: int


@dataclass(frozen=True)
class StationSearchResult:
    """A public station and its optional distance from the search point."""

    station: ChargingStation
    distance_km: float | None


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

    distance_metres = literal(None)
    ordering = [ChargingStation.name, ChargingStation.id]
    if query.has_spatial_filter:
        station_location = station_geography()
        search_location = search_geography(query.latitude, query.longitude)
        radius_metres = float(query.radius_km * METRES_PER_KILOMETRE)
        distance_metres = func.ST_Distance(
            station_location,
            search_location,
        )
        filters.append(
            func.ST_DWithin(
                station_location,
                search_location,
                radius_metres,
            )
        )
        ordering = [distance_metres, ChargingStation.id]

    total = db.session.scalar(
        select(func.count()).select_from(ChargingStation).where(*filters)
    )
    rows = db.session.execute(
        select(
            ChargingStation,
            distance_metres.label("distance_metres"),
        )
        .options(selectinload(ChargingStation.charge_points))
        .where(*filters)
        .order_by(*ordering)
        .offset((query.page - 1) * query.per_page)
        .limit(query.per_page)
    ).all()

    items = [
        StationSearchResult(
            station=station,
            distance_km=(
                float(distance) / METRES_PER_KILOMETRE
                if distance is not None
                else None
            ),
        )
        for station, distance in rows
    ]

    return StationPage(
        items=items,
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
