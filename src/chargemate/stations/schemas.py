from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from chargemate.models.charge_point import ConnectorType, PowerType


class ChargePointCreateRequest(BaseModel):
    """Validated input for one charge point created with a station."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: str = Field(min_length=1, max_length=50)
    connector_type: ConnectorType
    power_type: PowerType
    max_power_kw: Decimal = Field(gt=0, max_digits=7, decimal_places=2)
    is_bookable: bool = True

    @field_validator("code")
    @classmethod
    def normalize_code(cls, code: str) -> str:
        return code.upper()


class StationCreateRequest(BaseModel):
    """Validated input for a station and its initial charge points."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    address_line_1: str = Field(min_length=3, max_length=255)
    address_line_2: str | None = Field(default=None, max_length=255)
    city: str = Field(min_length=2, max_length=100)
    state: str = Field(min_length=2, max_length=100)
    postal_code: str = Field(min_length=3, max_length=20)
    country_code: str = Field(default="IN", min_length=2, max_length=2)
    latitude: Decimal = Field(ge=-90, le=90, max_digits=9, decimal_places=6)
    longitude: Decimal = Field(ge=-180, le=180, max_digits=9, decimal_places=6)
    timezone: str = Field(default="Asia/Kolkata", min_length=1, max_length=64)
    phone: str | None = Field(default=None, min_length=7, max_length=20)
    is_24_hours: bool = False
    charge_points: list[ChargePointCreateRequest] = Field(
        min_length=1,
        max_length=100,
    )

    @field_validator("country_code")
    @classmethod
    def normalize_country_code(cls, country_code: str) -> str:
        return country_code.upper()

    @model_validator(mode="after")
    def charge_point_codes_are_unique(self) -> "StationCreateRequest":
        codes = [charge_point.code for charge_point in self.charge_points]
        if len(codes) != len(set(codes)):
            raise ValueError("charge point codes must be unique within a station")
        return self


class StationSearchQuery(BaseModel):
    """Validated filters and pagination for public station discovery."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    city: str | None = Field(default=None, min_length=2, max_length=100)
    connector_type: ConnectorType | None = None
    min_power_kw: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=7,
        decimal_places=2,
    )
    latitude: Decimal | None = Field(
        default=None,
        ge=-90,
        le=90,
        max_digits=9,
        decimal_places=6,
    )
    longitude: Decimal | None = Field(
        default=None,
        ge=-180,
        le=180,
        max_digits=9,
        decimal_places=6,
    )
    radius_km: Decimal | None = Field(
        default=None,
        gt=0,
        le=200,
        max_digits=6,
        decimal_places=2,
    )
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def spatial_filters_are_complete(self) -> "StationSearchQuery":
        spatial_values = (self.latitude, self.longitude, self.radius_km)
        if any(value is not None for value in spatial_values) and not all(
            value is not None for value in spatial_values
        ):
            raise ValueError(
                "latitude, longitude, and radius_km must be provided together"
            )
        return self

    @property
    def has_spatial_filter(self) -> bool:
        return self.latitude is not None


class ExternalStationSearchQuery(BaseModel):
    """Bounded nearby search accepted by the external-station endpoint."""

    model_config = ConfigDict(extra="forbid")

    latitude: Decimal = Field(
        ge=-90,
        le=90,
        max_digits=9,
        decimal_places=6,
    )
    longitude: Decimal = Field(
        ge=-180,
        le=180,
        max_digits=9,
        decimal_places=6,
    )
    radius_km: Decimal = Field(
        default=25,
        gt=0,
        le=100,
        max_digits=5,
        decimal_places=2,
    )
    max_results: int = Field(default=50, ge=1, le=100)
