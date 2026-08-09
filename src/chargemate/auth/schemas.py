from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
)


class RegisterUserRequest(BaseModel):
    """Validated JSON accepted by the public registration endpoint."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    username: Annotated[
        str,
        Field(min_length=3, max_length=50, pattern=r"^[a-z0-9_]+$"),
    ]
    password: Annotated[str, Field(min_length=12, max_length=128)]
    full_name: Annotated[str, Field(min_length=2, max_length=100)]
    phone: Annotated[
        str | None,
        Field(pattern=r"^\+[1-9]\d{7,14}$"),
    ] = None

    @field_validator("email", "username", mode="before")
    @classmethod
    def normalize_identifiers(cls, value: Any) -> Any:
        """Store identifiers in the canonical form required by PostgreSQL."""
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("full_name", mode="before")
    @classmethod
    def normalize_full_name(cls, value: Any) -> Any:
        """Remove accidental surrounding and repeated whitespace."""
        if isinstance(value, str):
            return " ".join(value.split())
        return value

    @field_validator("phone", mode="before")
    @classmethod
    def normalize_phone(cls, value: Any) -> Any:
        """Treat a blank optional phone number as absent."""
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class LoginRequest(BaseModel):
    """Validated credentials accepted by the login endpoint."""

    model_config = ConfigDict(extra="forbid")

    identifier: Annotated[str, Field(min_length=3, max_length=255)]
    password: Annotated[SecretStr, Field(min_length=1, max_length=128)]

    @field_validator("identifier", mode="before")
    @classmethod
    def normalize_identifier(cls, value: Any) -> Any:
        """Normalize either an email address or username for lookup."""
        if isinstance(value, str):
            return value.strip().lower()
        return value


class ChangePasswordRequest(BaseModel):
    """Validated current and replacement passwords for an active account."""

    model_config = ConfigDict(extra="forbid")

    current_password: Annotated[SecretStr, Field(min_length=1, max_length=128)]
    new_password: Annotated[SecretStr, Field(min_length=12, max_length=128)]
