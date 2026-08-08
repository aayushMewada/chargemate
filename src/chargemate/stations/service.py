from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, func, literal, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from chargemate.extensions import db
from chargemate.models.charge_point import ChargePoint, ChargePointStatus
from chargemate.models.charging_session import (
    ChargingSession,
    ChargingSessionStatus,
)
from chargemate.models.station import ChargingStation, StationStatus
from chargemate.models.user import User, UserRole
from chargemate.stations.cache import invalidate_station_searches
from chargemate.stations.schemas import (
    ChargePointUpdateRequest,
    OwnedStationListQuery,
    StationCreateRequest,
    StationSearchQuery,
    StationUpdateRequest,
)
from chargemate.stations.spatial import (
    METRES_PER_KILOMETRE,
    search_geography,
    station_geography,
)


class StationConflictError(Exception):
    """Raised when station data conflicts with a database constraint."""


class StationNotFoundError(Exception):
    """Raised when an administrator cannot access a station resource."""


class StationStateConflictError(Exception):
    """Raised when an expected version or operational rule does not match."""


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


@dataclass(frozen=True)
class OwnedStationPage:
    """One page of stations belonging to an administrator."""

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

    invalidate_station_searches()
    return station


def find_owned_stations(
    owner_id: UUID,
    query: OwnedStationListQuery,
) -> OwnedStationPage:
    """Return all station states belonging to one dashboard owner."""

    filters = [ChargingStation.owner_id == owner_id]
    total = db.session.scalar(
        select(func.count()).select_from(ChargingStation).where(*filters)
    )
    stations = db.session.scalars(
        select(ChargingStation)
        .options(selectinload(ChargingStation.charge_points))
        .where(*filters)
        .order_by(ChargingStation.created_at.desc(), ChargingStation.id)
        .offset((query.page - 1) * query.per_page)
        .limit(query.per_page)
    ).all()
    return OwnedStationPage(
        items=list(stations),
        total=total or 0,
        page=query.page,
        per_page=query.per_page,
    )


def update_station(
    operator: User,
    station_id: UUID,
    payload: StationUpdateRequest,
) -> ChargingStation:
    """Update an owned station only when the dashboard version is current."""

    try:
        station = db.session.scalar(
            select(ChargingStation)
            .options(selectinload(ChargingStation.charge_points))
            .where(ChargingStation.id == station_id)
            .with_for_update()
        )
        if not _operator_controls_station(operator, station):
            raise StationNotFoundError
        if station.version != payload.version:
            raise StationStateConflictError

        changes = payload.model_dump(exclude={"version"}, exclude_unset=True)
        if changes.get("status") == StationStatus.ACTIVE and not any(
            point.is_bookable and point.status == ChargePointStatus.AVAILABLE
            for point in station.charge_points
        ):
            raise StationStateConflictError
        for field, value in changes.items():
            setattr(station, field, value)
        station.version += 1
        db.session.commit()
    except (StationNotFoundError, StationStateConflictError):
        db.session.rollback()
        raise
    except IntegrityError as error:
        db.session.rollback()
        raise StationConflictError from error
    except Exception:
        db.session.rollback()
        raise

    invalidate_station_searches()
    return station


def update_charge_point(
    operator: User,
    station_id: UUID,
    charge_point_id: UUID,
    payload: ChargePointUpdateRequest,
) -> ChargePoint:
    """Update one owned charger with locks and optimistic concurrency."""

    try:
        station = db.session.scalar(
            select(ChargingStation)
            .where(ChargingStation.id == station_id)
            .with_for_update()
        )
        if not _operator_controls_station(operator, station):
            raise StationNotFoundError
        charge_point = db.session.scalar(
            select(ChargePoint)
            .where(
                ChargePoint.id == charge_point_id,
                ChargePoint.station_id == station_id,
            )
            .with_for_update()
        )
        if charge_point is None:
            raise StationNotFoundError
        if charge_point.version != payload.version:
            raise StationStateConflictError

        changes = payload.model_dump(exclude={"version"}, exclude_unset=True)
        disables_charger = (
            changes.get("is_bookable") is False
            or (
                "status" in changes
                and changes["status"] != ChargePointStatus.AVAILABLE
            )
        )
        if disables_charger and _has_active_charging_session(charge_point.id):
            raise StationStateConflictError
        for field, value in changes.items():
            setattr(charge_point, field, value)
        charge_point.version += 1
        db.session.commit()
    except (StationNotFoundError, StationStateConflictError):
        db.session.rollback()
        raise
    except IntegrityError as error:
        db.session.rollback()
        raise StationConflictError from error
    except Exception:
        db.session.rollback()
        raise

    invalidate_station_searches()
    return charge_point


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


def _operator_controls_station(
    operator: User,
    station: ChargingStation | None,
) -> bool:
    return bool(
        station is not None
        and (
            operator.role == UserRole.SYSTEM_ADMIN
            or station.owner_id == operator.id
        )
    )


def _has_active_charging_session(charge_point_id: UUID) -> bool:
    return db.session.scalar(
        select(ChargingSession.id)
        .where(
            ChargingSession.charge_point_id == charge_point_id,
            ChargingSession.status == ChargingSessionStatus.ACTIVE,
        )
        .limit(1)
    ) is not None
