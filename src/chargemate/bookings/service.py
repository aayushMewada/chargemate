from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from flask import current_app
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import contains_eager, joinedload, selectinload

from chargemate.bookings.schemas import BookingHoldRequest, BookingListQuery
from chargemate.extensions import db
from chargemate.models.booking import Booking, BookingStatus
from chargemate.models.charge_point import ChargePoint, ChargePointStatus
from chargemate.models.payment import Payment
from chargemate.models.station import StationStatus
from chargemate.models.user import User


DEFAULT_HOLD_MINUTES = 10
BLOCKING_BOOKING_STATUSES = (
    BookingStatus.HELD,
    BookingStatus.PAYMENT_PENDING,
    BookingStatus.CONFIRMED,
    BookingStatus.ACTIVE,
)
CANCELLABLE_BOOKING_STATUSES = (
    BookingStatus.HELD,
    BookingStatus.PAYMENT_PENDING,
    BookingStatus.CONFIRMED,
)


class BookingTimeError(Exception):
    """Raised when a requested booking time is not acceptable."""


class BookingUnavailableError(Exception):
    """Raised when a charge point or requested time slot cannot be held."""


class BookingStateConflictError(Exception):
    """Raised when a booking changed or can no longer be cancelled."""


@dataclass(frozen=True)
class BookingPage:
    """One page of a user's bookings plus pagination metadata."""

    items: list[Booking]
    total: int
    page: int
    per_page: int


def create_booking_hold(user: User, payload: BookingHoldRequest) -> Booking:
    """Lock a charge point and atomically create a temporary booking hold."""

    now = datetime.now(UTC)
    if payload.starts_at <= now:
        raise BookingTimeError

    try:
        charge_point = db.session.scalar(
            _locked_charge_point_statement(payload.charge_point_id)
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
            total_amount=charge_point.booking_fee,
            currency="INR",
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


def _locked_charge_point_statement(charge_point_id: UUID):
    """Load and lock a charge point and its required parent station.

    An explicit inner join matters here. PostgreSQL cannot apply FOR UPDATE to
    the nullable side of the outer join produced by joinedload(). Every charge
    point has a non-null station_id, so an inner join correctly represents the
    data model and lets PostgreSQL lock both rows for the booking transaction.
    """
    return (
        select(ChargePoint)
        .join(ChargePoint.station)
        .options(contains_eager(ChargePoint.station))
        .where(ChargePoint.id == charge_point_id)
        .with_for_update()
    )


def find_user_bookings(user_id: UUID, query: BookingListQuery) -> BookingPage:
    """Expire stale holds and return a filtered page owned by one user."""

    _expire_user_stale_holds(user_id, datetime.now(UTC))
    db.session.commit()

    filters = [Booking.user_id == user_id]
    if query.status is not None:
        filters.append(Booking.status == query.status)

    total = db.session.scalar(
        select(func.count()).select_from(Booking).where(*filters)
    )
    bookings = db.session.scalars(
        select(Booking)
        .options(
            joinedload(Booking.charge_point).joinedload(ChargePoint.station),
            selectinload(Booking.payments).joinedload(Payment.refund),
        )
        .where(*filters)
        .order_by(Booking.starts_at.desc(), Booking.id)
        .offset((query.page - 1) * query.per_page)
        .limit(query.per_page)
    ).all()
    return BookingPage(
        items=list(bookings),
        total=total or 0,
        page=query.page,
        per_page=query.per_page,
    )


def get_user_booking(user_id: UUID, booking_id: UUID) -> Booking | None:
    """Return one user-owned booking after applying hold expiration."""

    _expire_user_stale_holds(user_id, datetime.now(UTC))
    db.session.commit()
    return db.session.scalar(
        select(Booking)
        .options(
            joinedload(Booking.charge_point).joinedload(ChargePoint.station),
            selectinload(Booking.payments).joinedload(Payment.refund),
        )
        .where(
            Booking.id == booking_id,
            Booking.user_id == user_id,
        )
    )


def cancel_user_booking(
    user_id: UUID,
    booking_id: UUID,
    expected_version: int,
) -> Booking:
    """Cancel a booking only if its current state and version still match."""

    now = datetime.now(UTC)
    try:
        result = db.session.execute(
            update(Booking)
            .where(
                Booking.id == booking_id,
                Booking.user_id == user_id,
                Booking.version == expected_version,
                Booking.status.in_(CANCELLABLE_BOOKING_STATUSES),
                or_(
                    Booking.status != BookingStatus.HELD,
                    Booking.hold_expires_at > now,
                ),
            )
            .values(
                status=BookingStatus.CANCELLED,
                cancelled_at=now,
                version=Booking.version + 1,
            )
        )
        if result.rowcount != 1:
            db.session.rollback()
            raise BookingStateConflictError
        db.session.commit()
    except BookingStateConflictError:
        raise
    except Exception:
        db.session.rollback()
        raise

    return db.session.get(Booking, booking_id)


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


def _expire_user_stale_holds(user_id: UUID, now: datetime) -> None:
    db.session.execute(
        update(Booking)
        .where(
            Booking.user_id == user_id,
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
