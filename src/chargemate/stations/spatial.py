from sqlalchemy import Double, cast, func, literal, literal_column
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.types import UserDefinedType

from chargemate.models.station import ChargingStation


WGS84_SRID = 4326
METRES_PER_KILOMETRE = 1000


class Geography(UserDefinedType):
    """Minimal PostgreSQL type used to cast WGS84 points to geography."""

    cache_ok = True

    def get_col_spec(self, **_kwargs) -> str:
        return "geography"


def station_geography() -> ColumnElement:
    """Build an index-compatible geography point from station coordinates."""

    return _geography_point(
        ChargingStation.longitude,
        ChargingStation.latitude,
    )


def search_geography(latitude, longitude) -> ColumnElement:
    """Build a safely parameterized geography point for a user's location."""

    return _geography_point(literal(longitude), literal(latitude))


def _geography_point(longitude, latitude) -> ColumnElement:
    # PostGIS uses X/Y order, which means longitude must come before latitude.
    geometry = func.ST_SetSRID(
        func.ST_MakePoint(
            cast(longitude, Double),
            cast(latitude, Double),
        ),
        literal_column(str(WGS84_SRID)),
    )
    return cast(geometry, Geography())
