from datetime import UTC, datetime, timedelta

from flask import current_app
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from chargemate.bookings.schemas import BookingHoldRequest
from chargemate.extensions import db
from chargemate.models.booking import Booking, BookingStatus
from chargemate.models.charge_point import ChargePoint, ChargePointStatus
from chargemate.models.station import StationStatus
from chargemate.models.user import User


DEFAULT_HOLD_MINUTES = 10
BLOCKING_BOOKING_STATUSES = (
    BookingStatus.HELD,
    BookingStatus.PAYMENT_PENDING,
    BookingStatus.CONFIRMED,
    BookingStatus.ACTIVE,
)


class BookingTimeError(Exception):
    """Raised when a requested booking time is not acceptable."""


class BookingUnavailableError(Exception):
    """Raised when a charge point or requested time slot cannot be held."""


def create_booking_hold(user: User, payload: BookingHoldRequest) -> Booking:
    """Lock a charge point and atomically create a temporary booking hold."""

    now = datetime.now(UTC)
    if payload.starts_at <= now:
        raise BookingTimeError

    try:
        charge_point = db.session.scalar(
            select(ChargePoint)
            .options(joinedload(ChargePoint.station))
            .where(ChargePoint.id == payload.charge_point_id)
            .with_for_update()
        )
        if not _charge_point_accepts_bookings(charge_point):
            raise BookingUnavailableError

        _expire_stale_holds(charge_point.id, now)
        if _has_overlapping_booking(
            charge_point.id,
            payload.starts_at,
            payload.ends_at,
        ):
            raise BookingUnavailableError

        hold_minutes = current_app.config.get(
            "BOOKING_HOLD_MINUTES",
            DEFAULT_HOLD_MINUTES,
        )
        booking = Booking(
            user_id=user.id,
            charge_point_id=charge_point.id,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
            hold_expires_at=now + timedelta(minutes=hold_minutes),
            status=BookingStatus.HELD,
        )
        db.session.add(booking)
        db.session.commit()
    except BookingUnavailableError:
        db.session.rollback()
        raise
    except IntegrityError as error:
        db.session.rollback()
        raise BookingUnavailableError from error
    except Exception:
        db.session.rollback()
        raise

    return booking


def _charge_point_accepts_bookings(charge_point: ChargePoint | None) -> bool:
    return bool(
        charge_point is not None
        and charge_point.is_bookable
        and charge_point.status == ChargePointStatus.AVAILABLE
        and charge_point.station.status == StationStatus.ACTIVE
    )


def _expire_stale_holds(charge_point_id, now: datetime) -> None:
    db.session.execute(
        update(Booking)
        .where(
            Booking.charge_point_id == charge_point_id,
            Booking.status == BookingStatus.HELD,
            Booking.hold_expires_at <= now,
        )
        .values(
            status=BookingStatus.EXPIRED,
            version=Booking.version + 1,
        )
    )


def _has_overlapping_booking(
    charge_point_id,
    starts_at: datetime,
    ends_at: datetime,
) -> bool:
    booking_id = db.session.scalar(
        select(Booking.id)
        .where(
            Booking.charge_point_id == charge_point_id,
            Booking.status.in_(BLOCKING_BOOKING_STATUSES),
            Booking.starts_at < ends_at,
            Booking.ends_at > starts_at,
        )
        .limit(1)
    )
    return booking_id is not None
