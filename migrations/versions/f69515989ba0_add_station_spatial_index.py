"""add station spatial index

Revision ID: f69515989ba0
Revises: 11b18d6722e7
Create Date: 2026-08-08 02:28:49.267149

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'f69515989ba0'
down_revision = '11b18d6722e7'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE INDEX ix_charging_stations_location_gist
        ON charging_stations
        USING gist (
            (
                ST_SetSRID(
                    ST_MakePoint(
                        longitude::double precision,
                        latitude::double precision
                    ),
                    4326
                )::geography
            )
        )
        """
    )


def downgrade():
    op.execute(
        "DROP INDEX IF EXISTS ix_charging_stations_location_gist"
    )
