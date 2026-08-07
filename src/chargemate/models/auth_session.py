from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from chargemate.extensions import db
from chargemate.models.base import TimestampMixin, UUIDPrimaryKeyMixin


if TYPE_CHECKING:
    from chargemate.models.user import User


class AuthSession(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    """A stored, revocable generation of a user's refresh token."""

    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint(
            "expires_at > created_at",
            name="expires_after_creation",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
    )
    family_id: Mapped[UUID] = mapped_column(
        Uuid,
        nullable=False,
        default=uuid4,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    replaced_by_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("auth_sessions.id", ondelete="SET NULL"),
        unique=True,
    )

    user: Mapped["User"] = relationship(back_populates="auth_sessions")
    replacement: Mapped["AuthSession | None"] = relationship(
        remote_side="AuthSession.id",
        foreign_keys=[replaced_by_id],
        post_update=True,
    )

    @property
    def is_revoked(self) -> bool:
        """Return whether this refresh-token generation was revoked."""
        return self.revoked_at is not None
