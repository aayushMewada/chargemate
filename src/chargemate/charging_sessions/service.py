from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from chargemate.charging_sessions.schemas import (
    ChargingSessionListQuery,
    CompleteChargingSessionRequest,
    StartChargingSessionRequest,
)
from chargemate.extensions import db
from chargemate.models.booking import Booking, BookingStatus
from chargemate.models.charge_point import ChargePoint
from chargemate.models.charging_session import (
    ChargingSession,
    ChargingSessionStatus,
)
from chargemate.models.user import User, UserRole


EARLY_START_MINUTES = 15


class ChargingSessionStateConflictError(Exception):
    """Raised when a booking or session changed from the expected state."""


class ChargingSessionTimeError(Exception):
    """Raised when a confirmed booking is outside its usable time window."""


class ChargingSessionMeterError(Exception):
    """Raised when cumulative meter readings move backwards."""


class ChargingSessionForbiddenError(Exception):
    """Raised when an operator does not control the selected charge point."""


@dataclass(frozen=True)
class ChargingSessionPage:
    """One page of a user's charging sessions and pagination metadata."""

    items: list[ChargingSession]
    total: int
    page: int
    per_page: int


def start_charging_session(
    operator: User,
    payload: StartChargingSessionRequest,
) -> ChargingSession:
    """Atomically turn one confirmed booking into active charger usage."""

    now = datetime.now(UTC)
    try:
        booking = db.session.scalar(
            select(Booking)
            .where(Booking.id == payload.booking_id)
            .with_for_update()
        )
        if (
            booking is None
            or booking.status != BookingStatus.CONFIRMED
            or booking.version != payload.booking_version
        ):
            raise ChargingSessionStateConflictError
        if not _inside_start_window(booking, now):
            raise ChargingSessionTimeError

        charge_point = db.session.scalar(
            select(ChargePoint)
            .where(ChargePoint.id == booking.charge_point_id)
            .with_for_update()
        )
        if not _operator_controls_charge_point(operator, charge_point):
            raise ChargingSessionForbiddenError
        active_session_id = db.session.scalar(
            select(ChargingSession.id)
            .where(
                ChargingSession.charge_point_id == booking.charge_point_id,
                ChargingSession.status == ChargingSessionStatus.ACTIVE,
            )
            .limit(1)
        )
        if active_session_id is not None:
            raise ChargingSessionStateConflictError

        charging_session = ChargingSession(
            booking_id=booking.id,
            user_id=booking.user_id,
            charge_point_id=booking.charge_point_id,
            status=ChargingSessionStatus.ACTIVE,
            started_at=now,
            meter_start_kwh=payload.meter_start_kwh,
        )
        booking.status = BookingStatus.ACTIVE
        booking.version += 1
        db.session.add(charging_session)
        db.session.commit()
    except (
        ChargingSessionForbiddenError,
        ChargingSessionStateConflictError,
        ChargingSessionTimeError,
    ):
        db.session.rollback()
        raise
    except IntegrityError as error:
        db.session.rollback()
        raise ChargingSessionStateConflictError from error
    except Exception:
        db.session.rollback()
        raise

    return charging_session


def complete_charging_session(
    operator: User,
    session_id: UUID,
    payload: CompleteChargingSessionRequest,
) -> ChargingSession:
    """Finish an active session and calculate consumed energy atomically."""

    now = datetime.now(UTC)
    try:
        charging_session = db.session.scalar(
            select(ChargingSession)
            .where(ChargingSession.id == session_id)
            .with_for_update()
        )
        if (
            charging_session is None
            or charging_session.status != ChargingSessionStatus.ACTIVE
            or charging_session.version != payload.version
        ):
            raise ChargingSessionStateConflictError
        if payload.meter_end_kwh < charging_session.meter_start_kwh:
            raise ChargingSessionMeterError

        booking = db.session.scalar(
            select(Booking)
            .where(Booking.id == charging_session.booking_id)
            .with_for_update()
        )
        if booking.status != BookingStatus.ACTIVE:
            raise ChargingSessionStateConflictError
        charge_point = db.session.scalar(
            select(ChargePoint)
            .where(ChargePoint.id == charging_session.charge_point_id)
            .with_for_update()
        )
        if not _operator_controls_charge_point(operator, charge_point):
            raise ChargingSessionForbiddenError

        charging_session.status = ChargingSessionStatus.COMPLETED
        charging_session.ended_at = now
        charging_session.meter_end_kwh = payload.meter_end_kwh
        charging_session.energy_consumed_kwh = (
            payload.meter_end_kwh - charging_session.meter_start_kwh
        )
        charging_session.version += 1
        booking.status = BookingStatus.COMPLETED
        booking.version += 1
        db.session.commit()
    except (
        ChargingSessionForbiddenError,
        ChargingSessionMeterError,
        ChargingSessionStateConflictError,
    ):
        db.session.rollback()
        raise
    except Exception:
        db.session.rollback()
        raise

    return charging_session


def find_user_charging_sessions(
    user_id: UUID,
    query: ChargingSessionListQuery,
) -> ChargingSessionPage:
    """Return a filtered page of sessions owned by one user."""

    filters = [ChargingSession.user_id == user_id]
    if query.status is not None:
        filters.append(ChargingSession.status == query.status)

    total = db.session.scalar(
        select(func.count()).select_from(ChargingSession).where(*filters)
    )
    sessions = db.session.scalars(
        select(ChargingSession)
        .where(*filters)
        .order_by(ChargingSession.started_at.desc(), ChargingSession.id)
        .offset((query.page - 1) * query.per_page)
        .limit(query.per_page)
    ).all()
    return ChargingSessionPage(
        items=list(sessions),
        total=total or 0,
        page=query.page,
        per_page=query.per_page,
    )


def get_user_charging_session(
    user_id: UUID,
    session_id: UUID,
) -> ChargingSession | None:
    """Return one charging session only when the user owns it."""

    return db.session.scalar(
        select(ChargingSession).where(
            ChargingSession.id == session_id,
            ChargingSession.user_id == user_id,
        )
    )


def _inside_start_window(booking: Booking, now: datetime) -> bool:
    starts_at = _as_utc(booking.starts_at)
    ends_at = _as_utc(booking.ends_at)
    earliest_start = starts_at - timedelta(minutes=EARLY_START_MINUTES)
    return earliest_start <= now < ends_at


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _operator_controls_charge_point(
    operator: User,
    charge_point: ChargePoint | None,
) -> bool:
    return bool(
        charge_point is not None
        and (
            operator.role == UserRole.SYSTEM_ADMIN
            or charge_point.station.owner_id == operator.id
        )
    )
