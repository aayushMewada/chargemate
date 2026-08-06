from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from chargemate.auth.schemas import RegisterUserRequest
from chargemate.extensions import db
from chargemate.models.user import User


USER_IDENTITY_CONSTRAINTS = {
    "uq_users_email",
    "uq_users_phone",
    "uq_users_username",
}


class RegistrationConflictError(Exception):
    """Raised when registration identifiers already belong to a user."""


def register_user(data: RegisterUserRequest) -> User:
    """Create and persist a user from validated registration data."""
    identifiers = [
        User.email == str(data.email),
        User.username == data.username,
    ]
    if data.phone is not None:
        identifiers.append(User.phone == data.phone)

    try:
        with db.session.begin():
            existing_user = db.session.execute(
                select(User.id).where(or_(*identifiers)).limit(1)
            ).first()
            if existing_user is not None:
                raise RegistrationConflictError(
                    "Registration details are already in use."
                )

            user = User(
                email=str(data.email),
                username=data.username,
                full_name=data.full_name,
                phone=data.phone,
            )
            user.set_password(data.password)
            db.session.add(user)
    except IntegrityError as error:
        constraint_name = getattr(
            getattr(error.orig, "diag", None),
            "constraint_name",
            None,
        )
        if constraint_name in USER_IDENTITY_CONSTRAINTS:
            raise RegistrationConflictError(
                "Registration details are already in use."
            ) from error

        raise

    return user
